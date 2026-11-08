#!/usr/bin/env python3
"""M9 independent evidence-packet verifier (stdlib only).

Implements checks from EVIDENCE_SPEC sections 2-9 and
briefs/M9_INPUT_CONVENTIONS.md (I-7..I-14, I-10/I-12/I-13).
Does not import control/journal.py, claims.py, metrics.py, or packet.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ZERO_SHA256 = "0" * 64
SCAN_LINE = "scan result: NOT INDEPENDENTLY RECOMPUTED"
INCOMPLETE_LINE = "INCOMPLETE: no outcome other than NO_SUFFICIENT_EVIDENCE is possible"


@dataclass
class Report:
    ok: bool
    lines: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return 0 if self.ok else 1


def _ascii_ok(obj: Any) -> bool:
    if isinstance(obj, str):
        return all(ord(ch) < 128 for ch in obj)
    if isinstance(obj, dict):
        return all(_ascii_ok(k) and _ascii_ok(v) for k, v in obj.items())
    if isinstance(obj, list):
        return all(_ascii_ok(v) for v in obj)
    return True


def canonical_json(obj: Any) -> bytes:
    if not _ascii_ok(obj):
        raise ValueError("non-ASCII data refused")
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def entry_sha256(entry: dict[str, Any]) -> str:
    body = {k: v for k, v in entry.items() if k != "entry_sha256"}
    return sha256_hex(canonical_json(body))


def packet_sha256(packet: dict[str, Any]) -> str:
    body = {k: v for k, v in packet.items() if k != "packet_sha256"}
    return sha256_hex(canonical_json(body))


def evaluate_claim(claim: dict[str, Any], events: list[dict[str, Any]]) -> str:
    """I-7 / conventions §4: first-match decision order."""
    evidence_ref = claim.get("evidence_ref")
    if evidence_ref is None or evidence_ref == "":
        return "UNSUPPORTED"

    with_ref = [e for e in events if e.get("evidence_ref") == evidence_ref]
    if not with_ref:
        return "UNSUPPORTED"

    with_ref = [e for e in with_ref if e.get("status") != "claimed-complete"]
    if not with_ref:
        return "UNSUPPORTED"

    case_id = claim.get("case_id")
    with_case = [e for e in with_ref if e.get("case_id") == case_id]
    if not with_case:
        return "UNSUPPORTED"

    step_id = claim.get("step_id")
    matching_pair = [e for e in events if e.get("case_id") == case_id and e.get("step_id") == step_id]
    if not matching_pair:
        return "UNSUPPORTED"
    claimed_event = matching_pair[-1]

    with_step = [e for e in with_case if e.get("step_id", 0) <= step_id]
    if not with_step:
        return "UNSUPPORTED"

    claimed_ts = claimed_event.get("timestamp", "")
    with_ts = [e for e in with_step if e.get("timestamp", "") <= claimed_ts]
    if not with_ts:
        return "UNSUPPORTED"

    if any(e.get("status") == "completed" for e in with_ts):
        return "SUPPORTED"
    return "CONTRADICTED"


def _parse_decision_rule_yaml(text: str) -> dict[str, Any]:
    """Minimal YAML subset reader for decision_rule.yaml (stdlib only)."""
    # Strip comments carefully: keep quoted strings intact enough for our keys.
    lines: list[str] = []
    for raw in text.splitlines():
        if "#" in raw:
            in_single = False
            in_double = False
            cut = len(raw)
            for i, ch in enumerate(raw):
                if ch == "'" and not in_double:
                    in_single = not in_single
                elif ch == '"' and not in_single:
                    in_double = not in_double
                elif ch == "#" and not in_single and not in_double:
                    cut = i
                    break
            raw = raw[:cut]
        if raw.strip():
            lines.append(raw.rstrip())

    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]

    def parse_scalar(value: str) -> Any:
        value = value.strip()
        if value in ("true", "True"):
            return True
        if value in ("false", "False"):
            return False
        if value in ("null", "Null", "~", ""):
            return None
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            return value[1:-1]
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            if not inner:
                return []
            return [parse_scalar(part.strip()) for part in inner.split(",")]
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            return value

    for line in lines:
        indent = len(line) - len(line.lstrip(" "))
        content = line.lstrip(" ")
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if content.startswith("- "):
            item_body = content[2:].strip()
            if not isinstance(parent, list):
                # Should not happen with our rule file shape.
                continue
            if ":" in item_body:
                key, _, rest = item_body.partition(":")
                item: dict[str, Any] = {key.strip(): parse_scalar(rest)}
                parent.append(item)
                stack.append((indent, item))
            else:
                parent.append(parse_scalar(item_body))
            continue

        key, _, rest = content.partition(":")
        key = key.strip()
        rest = rest.strip()
        if not isinstance(parent, dict):
            continue
        if rest == "":
            # Lookahead: next higher-indent line starting with "- " => list.
            # Default to dict; list override when first child is list item —
            # for this file, ranking is a list, eligibility/minimum_margin are maps.
            if key == "ranking":
                parent[key] = []
                stack.append((indent, parent[key]))
            else:
                parent[key] = {}
                stack.append((indent, parent[key]))
        else:
            parent[key] = parse_scalar(rest)

    return root


def _metrics_differ(a: Any, b: Any) -> bool:
    if isinstance(a, int) and isinstance(b, int):
        return a != b
    try:
        return abs(float(a) - float(b)) > 1e-6
    except (TypeError, ValueError):
        return a != b


def _is_excluded(receipt: dict[str, Any]) -> bool:
    if receipt.get("termination") != "normal":
        return True
    if receipt.get("exit_status") != 0:
        return True
    return False


def _last_attempt_per_path(executions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for receipt in executions:
        path_id = receipt.get("path_id")
        attempt = receipt.get("attempt", 0)
        prev = best.get(path_id)
        if prev is None or attempt >= prev.get("attempt", 0):
            best[path_id] = receipt
    return list(best.values())


def _claims_verdict(claim_check: dict[str, Any]) -> str:
    if claim_check.get("unsupported", 0) == 0 and claim_check.get("contradicted", 0) == 0:
        return "CLAIMS_HOLD"
    return "CLAIMS_FAIL"


def _rank_key(receipt: dict[str, Any]) -> tuple:
    m = receipt.get("metrics_recomputed") or {}
    median = m.get("median_cycle_min")
    if median is None:
        median = float("inf")
    return (
        -int(m.get("exceptions_caught", 0)),
        int(m.get("manual_touches", 0)),
        float(median),
        str(receipt.get("path_id", "")),
    )


def _recompute_rule_outcome(
    rule: dict[str, Any],
    executions: list[dict[str, Any]],
    case_count: int,
) -> tuple[str, str | None, str]:
    eligibility = rule.get("eligibility") or {}
    required_verdict = eligibility.get("claims_verdict", "CLAIMS_HOLD")
    unsupported_max = eligibility.get("unsupported_claims_max", 0)
    fa_frac_max = eligibility.get("false_alarms_max_fraction_of_cases", 0.10)
    margin = (rule.get("minimum_margin") or {}).get("exceptions_caught", 3)

    eligible: list[dict[str, Any]] = []
    excluded: list[str] = []
    for receipt in _last_attempt_per_path(executions):
        path_id = str(receipt.get("path_id"))
        if _is_excluded(receipt):
            excluded.append(path_id)
            continue
        cc = receipt.get("claim_check") or {}
        verdict = _claims_verdict(cc)
        if verdict != required_verdict:
            continue
        m = receipt.get("metrics_recomputed") or {}
        unsupported = m.get("unsupported_claims", cc.get("unsupported", 0) + cc.get("contradicted", 0))
        if unsupported > unsupported_max:
            continue
        false_alarms = m.get("false_alarms", 0)
        if case_count > 0 and (false_alarms / case_count) > fa_frac_max:
            continue
        eligible.append(receipt)

    if len(eligible) < 2:
        basis = "fewer than 2 eligible paths"
        if excluded:
            basis += "; excluded=" + ",".join(excluded)
        return "NO_SUFFICIENT_EVIDENCE", None, basis

    ordered = sorted(eligible, key=_rank_key)
    best = ordered[0]
    runner = ordered[1]
    best_ex = int((best.get("metrics_recomputed") or {}).get("exceptions_caught", 0))
    runner_ex = int((runner.get("metrics_recomputed") or {}).get("exceptions_caught", 0))
    if best_ex - runner_ex >= margin:
        return (
            "PATH_PREFERRED_UNDER_ASSUMPTIONS",
            str(best.get("path_id")),
            "rule satisfied on recomputed metrics",
        )
    return "NO_SUFFICIENT_EVIDENCE", None, "margin not met"


class _Collector:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.failed = False

    def pass_(self, msg: str) -> None:
        self.lines.append(f"PASS: {msg}")

    def fail(self, msg: str) -> None:
        self.failed = True
        self.lines.append(f"FAIL: {msg}")

    def note(self, msg: str) -> None:
        self.lines.append(f"NOT CHECKED: {msg}")


def _load_journal(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"journal line {line_no} is not JSON: {exc}") from exc
    return entries


def verify_journal_chain(entries: list[dict[str, Any]], col: _Collector) -> int | None:
    """Return first bad seq, or None if chain is intact."""
    if not entries:
        col.fail("journal is empty")
        return -1
    for expected_seq, entry in enumerate(entries):
        seq = entry.get("seq")
        if seq != expected_seq:
            col.fail(f"journal seq gap or disorder: expected {expected_seq}, got {seq} (first bad seq {expected_seq})")
            return expected_seq
        try:
            if not _ascii_ok(entry):
                col.fail(f"journal seq {seq}: non-ASCII data refused")
                return seq
            recomputed = entry_sha256(entry)
        except ValueError as exc:
            col.fail(f"journal seq {seq}: {exc}")
            return seq
        if entry.get("entry_sha256") != recomputed:
            col.fail(f"journal chain break at seq {seq}: entry_sha256 mismatch (first bad seq {seq})")
            return seq
        expected_prev = ZERO_SHA256 if seq == 0 else entries[seq - 1]["entry_sha256"]
        if entry.get("prev_sha256") != expected_prev:
            col.fail(f"journal chain break at seq {seq}: prev_sha256 mismatch (first bad seq {seq})")
            return seq
    col.pass_(f"journal chain ok ({len(entries)} entries)")
    return None


def verify(bundle_dir: str | Path) -> Report:
    root = Path(bundle_dir)
    col = _Collector()

    packet_path = root / "packet.json"
    journal_path = root / "journal.jsonl"
    rule_path = root / "decision_rule.yaml"
    events_path = root / "events.json"

    if not packet_path.is_file():
        col.fail(f"missing {packet_path}")
        return Report(ok=False, lines=col.lines + [SCAN_LINE])
    if not journal_path.is_file():
        col.fail(f"missing {journal_path}")
        return Report(ok=False, lines=col.lines + [SCAN_LINE])

    try:
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        col.fail(f"packet.json: {exc}")
        return Report(ok=False, lines=col.lines + [SCAN_LINE])

    try:
        entries = _load_journal(journal_path)
    except ValueError as exc:
        col.fail(str(exc))
        return Report(ok=False, lines=col.lines + [SCAN_LINE])

    incomplete = packet.get("packet_status") == "INCOMPLETE"
    has_decision_rule_section = "decision_rule" in packet and packet.get("decision_rule") is not None
    # Conventions §3 (clarified 2026-11-05): INCOMPLETE with no decision_rule section —
    # decision_rule.yaml (if present) is not compared; check is NOT CHECKED, never FAIL.
    skip_rule_file_compare = incomplete and not has_decision_rule_section
    rule_bytes: bytes | None = None
    rule_file_sha: str | None = None
    if not skip_rule_file_compare:
        if not rule_path.is_file():
            col.fail(f"missing {rule_path}")
            return Report(ok=False, lines=col.lines + [SCAN_LINE])
        rule_bytes = rule_path.read_bytes()
        rule_file_sha = sha256_hex(rule_bytes)

    # --- journal chain ---
    verify_journal_chain(entries, col)

    # --- packet_sha256 ---
    try:
        recomputed_packet = packet_sha256(packet)
        if packet.get("packet_sha256") == recomputed_packet:
            col.pass_("packet_sha256 matches")
        else:
            col.fail(
                f"packet_sha256 mismatch: stated={packet.get('packet_sha256')} recomputed={recomputed_packet}"
            )
    except ValueError as exc:
        col.fail(f"packet_sha256: {exc}")

    # --- journal embedding vs recording entry ---
    journal_meta = packet.get("journal") or {}
    n = journal_meta.get("entries")
    head = journal_meta.get("head_sha256")
    if isinstance(n, int) and n >= 0 and len(entries) >= n + 1:
        if n == 0:
            col.fail("journal.entries is 0; expected at least the packet-recording entry after")
        else:
            if entries[n - 1].get("entry_sha256") == head:
                col.pass_("packet.journal.head_sha256 matches seq N-1")
            else:
                col.fail("packet.journal.head_sha256 does not match entry_sha256 of seq N-1")
            recording = entries[n]
            # Pending uses packet_built; confirmed uses approval; incomplete uses error.
            status = (packet.get("approval_gate") or {}).get("status")
            if incomplete:
                expected_kinds = {"error"}
            elif status == "VIEWED_CONFIRMED":
                expected_kinds = {"approval"}
            else:
                expected_kinds = {"packet_built"}
            if recording.get("kind") not in expected_kinds:
                col.fail(
                    f"journal seq {n} kind={recording.get('kind')} expected one of {sorted(expected_kinds)}"
                )
            else:
                col.pass_(f"journal seq {n} kind={recording.get('kind')} ok")
            rec_hash = (recording.get("data") or {}).get("packet_sha256")
            if rec_hash == packet.get("packet_sha256"):
                col.pass_("recording entry data.packet_sha256 matches packet")
            else:
                col.fail("recording entry data.packet_sha256 does not match packet.packet_sha256")
    else:
        col.fail("packet.journal.entries inconsistent with journal.jsonl length")

    # --- decision_rule ---
    if skip_rule_file_compare:
        col.note(
            "decision_rule.yaml not compared: INCOMPLETE packet has no decision_rule section "
            "(conventions §3 clarified 2026-11-05)"
        )
    else:
        packet_rule_sha = (packet.get("decision_rule") or {}).get("sha256")
        if packet_rule_sha == rule_file_sha:
            col.pass_("decision_rule.yaml sha256 matches packet.decision_rule.sha256")
        else:
            col.fail(
                f"decision_rule.yaml sha256 mismatch vs packet "
                f"(file={rule_file_sha} packet={packet_rule_sha})"
            )

        journaled_rule = None
        for entry in entries:
            if entry.get("kind") == "council_done":
                journaled_rule = (entry.get("data") or {}).get("decision_rule_sha256")
                break
        if journaled_rule is None:
            col.fail("no council_done entry with decision_rule_sha256 before sandbox")
        else:
            if journaled_rule == rule_file_sha and journaled_rule == packet_rule_sha:
                col.pass_("decision_rule sha256 matches journaled council_done hash")
            else:
                col.fail(
                    f"decision_rule hash disagreement file/journal/packet: "
                    f"{rule_file_sha}/{journaled_rule}/{packet_rule_sha}"
                )
            # Pre-registration: council_done before first sandbox_created
            sandbox_idxs = [i for i, e in enumerate(entries) if e.get("kind") == "sandbox_created"]
            council_idxs = [i for i, e in enumerate(entries) if e.get("kind") == "council_done"]
            if sandbox_idxs and council_idxs and council_idxs[0] > sandbox_idxs[0]:
                col.fail("council_done must appear before first sandbox_created (pre-registration)")
            elif sandbox_idxs and council_idxs:
                col.pass_("decision_rule frozen before first sandbox_created")

    # --- dataset / mri / scan journal hashes ---
    for kind, key, section in (
        ("dataset_loaded", "manifest_sha256", "dataset"),
        ("mri_done", "inventory_sha256", "mri"),
        ("scan_done", "scan_sha256", "scan"),
    ):
        obj = packet.get(section)
        if obj is None:
            if incomplete:
                col.note(f"{section} absent on incomplete packet")
            continue
        try:
            expected = sha256_hex(canonical_json(obj))
        except ValueError as exc:
            col.fail(f"{section} hash: {exc}")
            continue
        found = None
        for entry in entries:
            if entry.get("kind") == kind:
                found = (entry.get("data") or {}).get(key)
                break
        if found == expected:
            col.pass_(f"{kind} {key} matches packet.{section}")
        else:
            col.fail(f"{kind} {key} mismatch vs packet.{section}")

    # Always print scan honesty line.
    col.lines.append(SCAN_LINE)

    if incomplete:
        col.lines.append(INCOMPLETE_LINE)
        # Integrity-only for incomplete: chain + packet_sha256.
        # Rule-file compare only when packet has a decision_rule section (conventions §3).
        # Do not require events.json.
        return Report(ok=not col.failed, lines=col.lines)

    # --- complete packet: events + claims + metrics + rule ---
    if not events_path.is_file():
        col.fail("events.json required for complete packet")
        return Report(ok=False, lines=col.lines)

    try:
        events = json.loads(events_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        col.fail(f"events.json: {exc}")
        return Report(ok=False, lines=col.lines)

    if not isinstance(events, list):
        col.fail("events.json must be a JSON array")
        return Report(ok=False, lines=col.lines)

    try:
        events_hash = sha256_hex(canonical_json(events))
    except ValueError as exc:
        col.fail(f"events.json: {exc}")
        return Report(ok=False, lines=col.lines)

    executions = packet.get("executions") or []
    if len(executions) < 2:
        col.fail("complete packet requires >= 2 executions")

    for receipt in executions:
        path_id = receipt.get("path_id")
        if receipt.get("events_sha256") != events_hash:
            col.fail(f"execution {path_id}: events_sha256 mismatch")
        elif receipt.get("events_count") != len(events):
            col.fail(f"execution {path_id}: events_count mismatch")
        else:
            col.pass_(f"execution {path_id}: events_sha256/count ok")

        cc = receipt.get("claim_check") or {}
        # claim_check journal hash when present
        for entry in entries:
            if entry.get("kind") == "claim_check":
                data = entry.get("data") or {}
                if data.get("path_id") == path_id and data.get("attempt") == receipt.get("attempt"):
                    expected_cc = sha256_hex(canonical_json(cc))
                    if data.get("claim_check_sha256") != expected_cc:
                        col.fail(f"claim_check journal hash mismatch for {path_id}")
                    break

        if _is_excluded(receipt):
            col.pass_(f"execution {path_id}: excluded from ranking (termination/exit)")
            continue

        # Re-run claims
        recomputed_results: list[str] = []
        for claim in cc.get("claims") or []:
            got = evaluate_claim(claim, events)
            recomputed_results.append(got)
            if got != claim.get("result"):
                col.fail(
                    f"execution {path_id} claim_id={claim.get('claim_id')}: "
                    f"stored result {claim.get('result')} != recomputed {got}"
                )
        supported = sum(1 for r in recomputed_results if r == "SUPPORTED")
        unsupported = sum(1 for r in recomputed_results if r == "UNSUPPORTED")
        contradicted = sum(1 for r in recomputed_results if r == "CONTRADICTED")
        if (
            cc.get("claims_total") != len(recomputed_results)
            or cc.get("supported") != supported
            or cc.get("unsupported") != unsupported
            or cc.get("contradicted") != contradicted
        ):
            col.fail(f"execution {path_id}: claim aggregate mismatch after re-run")
        else:
            col.pass_(f"execution {path_id}: claim check re-run ok")

        # unsupported_claims metric
        m_re = receipt.get("metrics_recomputed") or {}
        expected_unsupported = unsupported + contradicted
        if m_re.get("unsupported_claims") != expected_unsupported:
            col.fail(
                f"execution {path_id}: metrics_recomputed.unsupported_claims "
                f"{m_re.get('unsupported_claims')} != {expected_unsupported}"
            )
        else:
            col.pass_(f"execution {path_id}: unsupported_claims metric ok")

        # discrepancy check
        m_self = receipt.get("metrics_self_reported")
        stated_disc = receipt.get("metrics_discrepancy")
        if m_self is None:
            actual_disc = False
        else:
            actual_disc = False
            for key in set(m_self) & set(m_re):
                if _metrics_differ(m_self[key], m_re[key]):
                    actual_disc = True
                    break
        if bool(stated_disc) != actual_disc:
            col.fail(
                f"execution {path_id}: metrics_discrepancy stated={stated_disc} actual={actual_disc}"
            )
        else:
            col.pass_(f"execution {path_id}: metrics_discrepancy ok")

    col.note(
        "exceptions_caught and false_alarms cannot be recomputed: ground truth is not in the packet"
    )
    col.note("median_cycle_min has no timing model (I-9); absence is not a failure")

    # Rule re-evaluation
    try:
        rule = _parse_decision_rule_yaml(rule_bytes.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - report parse problems as FAIL
        col.fail(f"decision_rule.yaml parse error: {exc}")
        return Report(ok=not col.failed, lines=col.lines)

    case_count = int((packet.get("dataset") or {}).get("case_count") or 0)
    result, preferred, basis = _recompute_rule_outcome(rule, executions, case_count)
    outcome = packet.get("outcome") or {}
    if outcome.get("result") != result:
        col.fail(f"outcome.result {outcome.get('result')} != recomputed {result}")
    elif outcome.get("preferred_path_id") != preferred:
        col.fail(
            f"outcome.preferred_path_id {outcome.get('preferred_path_id')} != recomputed {preferred}"
        )
    else:
        col.pass_(f"rule outcome ok: {result} preferred={preferred}")

    # Council recommendation must not override rule (AT-E7): we only check rule stands.
    col.pass_("council recommendation ignored for outcome (rule stands)")

    return Report(ok=not col.failed, lines=col.lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a Distorted Reality evidence packet bundle")
    parser.add_argument(
        "bundle_dir",
        type=str,
        help="Directory containing packet.json, journal.jsonl, decision_rule.yaml, events.json",
    )
    args = parser.parse_args(argv)
    report = verify(args.bundle_dir)
    sys.stdout.write("\n".join(report.lines) + "\n")
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
