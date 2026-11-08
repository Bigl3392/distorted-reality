"""Test-only builders for I-10 journals and I-12 packets. Not product code."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

ZERO_SHA256 = "0" * 64
REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_RULE = REPO_ROOT / "schemas" / "decision_rule.yaml"


def assert_ascii_only(obj: Any) -> None:
    if isinstance(obj, str):
        if any(ord(ch) > 127 for ch in obj):
            raise ValueError("non-ASCII data refused")
    elif isinstance(obj, dict):
        for key, value in obj.items():
            assert_ascii_only(key)
            assert_ascii_only(value)
    elif isinstance(obj, list):
        for item in obj:
            assert_ascii_only(item)


def canonical_json(obj: Any) -> bytes:
    assert_ascii_only(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_entry(entry: dict[str, Any]) -> str:
    body = {k: v for k, v in entry.items() if k != "entry_sha256"}
    return sha256_hex(canonical_json(body))


def hash_packet(packet: dict[str, Any]) -> str:
    body = {k: v for k, v in packet.items() if k != "packet_sha256"}
    return sha256_hex(canonical_json(body))


def append_entry(
    entries: list[dict[str, Any]],
    *,
    run_id: str,
    kind: str,
    actor: str,
    data: dict[str, Any],
    ts: str = "2026-11-05T15:00:00Z",
) -> dict[str, Any]:
    seq = len(entries)
    prev = entries[-1]["entry_sha256"] if entries else ZERO_SHA256
    draft = {
        "seq": seq,
        "ts": ts,
        "run_id": run_id,
        "kind": kind,
        "actor": actor,
        "data": data,
        "prev_sha256": prev,
    }
    draft["entry_sha256"] = hash_entry(draft)
    entries.append(draft)
    return draft


def make_event(
    *,
    case_id: str = "inv-0001",
    step_id: int = 1,
    status: str = "completed",
    evidence_ref: str | None = "ev-0001",
    timestamp: str = "2026-11-05T15:00:00Z",
) -> dict[str, Any]:
    return {
        "label": "SYNTHETIC",
        "source_type": "SYNTHETIC",
        "case_id": case_id,
        "step_id": step_id,
        "role": "Receiving Clerk",
        "action": "log delivery",
        "input": "note",
        "output": "ok",
        "timestamp": timestamp,
        "duration_min": 1.0,
        "expected_duration_min": 1.0,
        "handoff_to": None,
        "status": status,
        "evidence_ref": evidence_ref,
        "stall_flag": False,
        "location": "Midtown OKC",
        "holiday_window": "none",
        "close_ref": "inventory_vs_cogs",
    }


def make_claim(
    *,
    claim_id: str,
    case_id: str,
    step_id: int,
    evidence_ref: str | None,
    result: str,
) -> dict[str, Any]:
    return {
        "claim_id": claim_id,
        "step_id": step_id,
        "case_id": case_id,
        "claimed": "step done",
        "evidence_ref": evidence_ref,
        "result": result,
        "reason": "fixture",
    }


def make_claim_check(
    *,
    run_id: str,
    path_id: str,
    claims: list[dict[str, Any]],
) -> dict[str, Any]:
    supported = sum(1 for c in claims if c["result"] == "SUPPORTED")
    unsupported = sum(1 for c in claims if c["result"] == "UNSUPPORTED")
    contradicted = sum(1 for c in claims if c["result"] == "CONTRADICTED")
    return {
        "run_id": run_id,
        "path_id": path_id,
        "claims_total": len(claims),
        "supported": supported,
        "unsupported": unsupported,
        "contradicted": contradicted,
        "claims": claims,
        "recomputed_by": "control_plane",
    }


def make_receipt(
    *,
    run_id: str,
    path_id: str,
    attempt: int,
    events: list[dict[str, Any]],
    claim_check: dict[str, Any],
    metrics_recomputed: dict[str, Any],
    metrics_self_reported: dict[str, Any] | None,
    metrics_discrepancy: bool,
    exit_status: int = 0,
    termination: str = "normal",
    journal_head_sha256: str = ZERO_SHA256,
) -> dict[str, Any]:
    events_sha = sha256_hex(canonical_json(events))
    return {
        "run_id": run_id,
        "path_id": path_id,
        "attempt": attempt,
        "sandbox_id": f"ctr-{path_id}-{attempt}",
        "image_digest": "sha256:" + ("a" * 64),
        "created_at": "2026-11-05T15:00:00Z",
        "started_at": "2026-11-05T15:00:00Z",
        "ended_at": "2026-11-05T15:00:00Z",
        "destroyed_at": "2026-11-05T15:00:00Z",
        "destroy_verified": True,
        "caps": {
            "wall_seconds": 30,
            "memory_mb": 256,
            "pids": 64,
            "cpus": 1,
            "stdout_bytes": 524288,
        },
        "docker_flags_sha256": "b" * 64,
        "exit_status": exit_status,
        "termination": termination,
        "peak_memory_mb": 10.0,
        "stdout_sha256": "c" * 64,
        "events_sha256": events_sha,
        "events_count": len(events),
        "secret_scan": {"canary_present_in_env": False, "scan_passed": True},
        "metrics_recomputed": metrics_recomputed,
        "metrics_self_reported": metrics_self_reported,
        "metrics_discrepancy": metrics_discrepancy,
        "claim_check": claim_check,
        "journal_head_sha256": journal_head_sha256,
    }


def _dataset() -> dict[str, Any]:
    return {
        "label": "SYNTHETIC",
        "dataset_id": "eo-recv-v1",
        "case_count": 2,
        "row_count": 4,
    }


def _mri() -> dict[str, Any]:
    return {"inventory_id": "mri-1", "files": 1}


def _scan() -> dict[str, Any]:
    return {"overall_index": 0.5, "recommendation": "generic"}


def build_complete_bundle(
    bundle_dir: Path,
    *,
    tamper_journal_seq: int | None = None,
    alter_rule: bool = False,
    hide_discrepancy: bool = False,
    outcome_result: str = "PATH_PREFERRED_UNDER_ASSUMPTIONS",
    preferred_path_id: str = "path-b",
) -> Path:
    """Build a minimal integrity-correct complete packet bundle under bundle_dir."""
    bundle_dir.mkdir(parents=True, exist_ok=True)
    run_id = "run-m9t1"
    rule_bytes = SCHEMA_RULE.read_bytes()
    rule_sha = sha256_hex(rule_bytes)
    if alter_rule:
        (bundle_dir / "decision_rule.yaml").write_bytes(rule_bytes + b"\n# tampered\n")
    else:
        shutil.copyfile(SCHEMA_RULE, bundle_dir / "decision_rule.yaml")

    events = [
        make_event(case_id="inv-0001", step_id=1, evidence_ref="ev-0001", status="completed"),
        make_event(case_id="inv-0002", step_id=1, evidence_ref="ev-0002", status="completed"),
    ]
    (bundle_dir / "events.json").write_text(
        json.dumps(events, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n",
        encoding="ascii",
    )

    dataset = _dataset()
    mri = _mri()
    scan = _scan()

    entries: list[dict[str, Any]] = []
    append_entry(entries, run_id=run_id, kind="run_created", actor="control", data={})
    append_entry(
        entries,
        run_id=run_id,
        kind="dataset_loaded",
        actor="control",
        data={"manifest_sha256": sha256_hex(canonical_json(dataset))},
    )
    append_entry(
        entries,
        run_id=run_id,
        kind="mri_done",
        actor="control",
        data={"inventory_sha256": sha256_hex(canonical_json(mri))},
    )
    append_entry(
        entries,
        run_id=run_id,
        kind="scan_done",
        actor="control",
        data={"scan_sha256": sha256_hex(canonical_json(scan))},
    )
    append_entry(
        entries,
        run_id=run_id,
        kind="council_done",
        actor="control",
        data={"decision_rule_sha256": rule_sha, "rule_frozen": True},
    )

    claims_a = [
        make_claim(
            claim_id="clm-a1",
            case_id="inv-0001",
            step_id=1,
            evidence_ref="ev-0001",
            result="SUPPORTED",
        )
    ]
    claims_b = [
        make_claim(
            claim_id="clm-b1",
            case_id="inv-0002",
            step_id=1,
            evidence_ref="ev-0002",
            result="SUPPORTED",
        )
    ]
    cc_a = make_claim_check(run_id=run_id, path_id="path-a", claims=claims_a)
    cc_b = make_claim_check(run_id=run_id, path_id="path-b", claims=claims_b)

    # path-b wins by exceptions_caught margin >= 3
    metrics_a = {
        "exceptions_caught": 10,
        "unsupported_claims": 0,
        "false_alarms": 0,
        "manual_touches": 1,
    }
    metrics_b = {
        "exceptions_caught": 14,
        "unsupported_claims": 0,
        "false_alarms": 0,
        "manual_touches": 1,
    }
    self_a = dict(metrics_a)
    self_b = dict(metrics_b)
    disc_a = False
    disc_b = False
    if hide_discrepancy:
        self_a["exceptions_caught"] = 99
        disc_a = False  # dishonest packet: values differ but flag false

    receipt_a = make_receipt(
        run_id=run_id,
        path_id="path-a",
        attempt=1,
        events=events,
        claim_check=cc_a,
        metrics_recomputed=metrics_a,
        metrics_self_reported=self_a,
        metrics_discrepancy=disc_a,
    )
    receipt_b = make_receipt(
        run_id=run_id,
        path_id="path-b",
        attempt=1,
        events=events,
        claim_check=cc_b,
        metrics_recomputed=metrics_b,
        metrics_self_reported=self_b,
        metrics_discrepancy=disc_b,
    )

    for path_id, attempt, cc in (
        ("path-a", 1, cc_a),
        ("path-b", 1, cc_b),
    ):
        append_entry(
            entries,
            run_id=run_id,
            kind="sandbox_created",
            actor="control",
            data={"sandbox_id": f"ctr-{path_id}-{attempt}", "path_id": path_id},
        )
        append_entry(
            entries,
            run_id=run_id,
            kind="claim_check",
            actor="control",
            data={
                "path_id": path_id,
                "attempt": attempt,
                "claim_check_sha256": sha256_hex(canonical_json(cc)),
            },
        )

    n_before_packet = len(entries)
    head = entries[-1]["entry_sha256"]

    packet: dict[str, Any] = {
        "label": "SYNTHETIC",
        "packet_version": "1",
        "run_id": run_id,
        "built_at": "2026-11-05T15:00:00Z",
        "claim_statement": (
            "The calculation executed successfully under these assumptions. "
            "This does not establish that any intervention will improve an actual business."
        ),
        "synthetic_notice": "ALL DATA IN THIS PACKET IS SYNTHETIC.",
        "dataset": dataset,
        "mri": mri,
        "scan": scan,
        "council": {"note": "minimal-for-integrity"},
        "decision_rule": {
            "sha256": rule_sha,
            "frozen_before_execution": True,
            "text": "dr-3way-v1",
        },
        "executions": [receipt_a, receipt_b],
        "outcome": {
            "result": outcome_result,
            "preferred_path_id": preferred_path_id,
            "basis": "rule satisfied on recomputed metrics",
        },
        "assumptions": ["synthetic"],
        "unknowns": ["timing-model"],
        "executed": ["two paths"],
        "did_not_prove": [
            "that any intervention improves a real business",
            "that the synthetic data represents any real operation",
            "that the sandbox is immune to container-escape vulnerabilities",
        ],
        "limitations": [
            "System-specific results are suppressed in public, by design, to protect the private association.",
            "The deployed product computes only the overall index and performs no system-specific scoring.",
        ],
        "containment": {
            "stress_test_run": False,
            "stress_termination": None,
            "control_plane_heartbeat_gap_max_ms": 0,
        },
        "approval_gate": {
            "status": "PENDING",
            "external_action_taken": False,
            "confirmed_at": None,
        },
        "assurance_tier": "T0",
        "journal": {"head_sha256": head, "entries": n_before_packet},
    }
    packet_hash = hash_packet(packet)
    packet["packet_sha256"] = packet_hash

    append_entry(
        entries,
        run_id=run_id,
        kind="packet_built",
        actor="control",
        data={"packet_sha256": packet_hash},
    )

    if tamper_journal_seq is not None:
        # Flip one character in the data of the named seq after hashing (breaks chain).
        target = entries[tamper_journal_seq]
        raw = dict(target)
        raw["data"] = dict(raw["data"])
        raw["data"]["tamper"] = "x"
        # Keep stored entry_sha256 as the old (now wrong) hash so verifier detects mismatch.
        entries[tamper_journal_seq] = raw

    lines = [
        json.dumps(e, sort_keys=True, separators=(",", ":"), ensure_ascii=True) for e in entries
    ]
    (bundle_dir / "journal.jsonl").write_text("\n".join(lines) + "\n", encoding="ascii")
    (bundle_dir / "packet.json").write_text(
        json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n",
        encoding="ascii",
    )
    return bundle_dir


def build_incomplete_bundle(
    bundle_dir: Path,
    *,
    tamper: bool = False,
    include_decision_rule: bool = True,
    include_rule_file: bool = True,
    rule_file_bytes: bytes | None = None,
) -> Path:
    """Build an INCOMPLETE integrity bundle.

    include_decision_rule=False reproduces the clarified conventions case:
    INCOMPLETE with no decision_rule section — rule file (if present) is NOT CHECKED.
    """
    bundle_dir.mkdir(parents=True, exist_ok=True)
    run_id = "run-m9inc"
    rule_bytes = SCHEMA_RULE.read_bytes()
    rule_sha = sha256_hex(rule_bytes)
    if include_rule_file:
        (bundle_dir / "decision_rule.yaml").write_bytes(
            rule_file_bytes if rule_file_bytes is not None else rule_bytes
        )

    dataset = _dataset()
    entries: list[dict[str, Any]] = []
    append_entry(entries, run_id=run_id, kind="run_created", actor="control", data={})
    append_entry(
        entries,
        run_id=run_id,
        kind="dataset_loaded",
        actor="control",
        data={"manifest_sha256": sha256_hex(canonical_json(dataset))},
    )
    if include_decision_rule:
        append_entry(
            entries,
            run_id=run_id,
            kind="council_done",
            actor="control",
            data={"decision_rule_sha256": rule_sha, "rule_frozen": True},
        )
    n_before = len(entries)
    head = entries[-1]["entry_sha256"]

    packet: dict[str, Any] = {
        "label": "SYNTHETIC",
        "packet_version": "1",
        "packet_status": "INCOMPLETE",
        "run_id": run_id,
        "built_at": "2026-11-05T15:00:00Z",
        "claim_statement": (
            "The calculation executed successfully under these assumptions. "
            "This does not establish that any intervention will improve an actual business."
        ),
        "synthetic_notice": "ALL DATA IN THIS PACKET IS SYNTHETIC.",
        "failed_at": "COUNCIL_CRITIC" if include_decision_rule else "SCAN_DONE",
        "failure_reason": "critic unparseable" if include_decision_rule else "failed before council",
        "dataset": dataset,
        "outcome": {
            "result": "NO_SUFFICIENT_EVIDENCE",
            "preferred_path_id": None,
            "basis": "run failed closed",
        },
        "did_not_prove": ["that any intervention improves a real business"],
        "limitations": [
            (
                "Run failed closed at COUNCIL_CRITIC"
                if include_decision_rule
                else "Run failed closed at SCAN_DONE"
            ),
            "System-specific results are suppressed in public, by design, to protect the private association.",
        ],
        "approval_gate": {
            "status": "PENDING",
            "external_action_taken": False,
            "confirmed_at": None,
        },
        "assurance_tier": "T0",
        "journal": {"head_sha256": head, "entries": n_before},
    }
    if include_decision_rule:
        packet["decision_rule"] = {
            "sha256": rule_sha,
            "frozen_before_execution": True,
            "text": "dr-3way-v1",
        }
    packet_hash = hash_packet(packet)
    packet["packet_sha256"] = packet_hash
    append_entry(
        entries,
        run_id=run_id,
        kind="error",
        actor="control",
        data={"packet_sha256": packet_hash, "failed_at": "COUNCIL_CRITIC"},
    )
    if tamper:
        entries[0]["data"] = {"tampered": True}

    lines = [
        json.dumps(e, sort_keys=True, separators=(",", ":"), ensure_ascii=True) for e in entries
    ]
    (bundle_dir / "journal.jsonl").write_text("\n".join(lines) + "\n", encoding="ascii")
    (bundle_dir / "packet.json").write_text(
        json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n",
        encoding="ascii",
    )
    return bundle_dir
