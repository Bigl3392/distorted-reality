"""Run orchestrator (M5). Drives one run through the spec state machine (section 3.3) and emits the journal, receipts and packet.

One Orchestrator instance serves one run (it owns that run's broker). Everything that touches a model, a container or the dataset
is injected: `broker` (M3), `runner` (M4's interface, see `Runner` below), `dataset` (M1's interface, see `Dataset`).

Runner interface (M4 implements; tests use a scripted fake):
    run(job: dict /* C2 */, code: str, events: list[dict], *, attempt: int, emit: callable(kind, data)) -> {"receipt": {...}, "response": {...}}
    The runner MUST call emit("sandbox_created", ...) before creating the container and emit("sandbox_started"|"sandbox_ended"|
    "sandbox_destroyed", ...) as it goes. receipt holds sandbox_id, image_digest, created_at, started_at, ended_at, destroyed_at,
    destroy_verified, docker_flags_sha256, exit_status, termination, peak_memory_mb, stdout_sha256, secret_scan. response is the SB1 stdout.
Dataset interface (M1 implements): dataset_id, manifest, events (visible fields only), truth_exceptions (sealed; never leaves this class),
    schema (field description for the coder), cases_total, mri(run_id) -> mri_inventory.

Fail closed everywhere: any exception after creation becomes FAILED_CLOSED, one `error` journal entry, and an INCOMPLETE packet.
"""
import copy
import datetime
import hashlib
import json
import os
import re

from broker import _schemas
from council import run as council_run
from scan import service as scan_service

from . import approval, claims, metrics, packet, rule as rule_mod
from .journal import Journal, canonical
from .states import IllegalTransition, StateMachine

_RUN_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")
# CONTAINMENT_SPEC section 4 defaults (BUILD may tighten, never loosen).
DEFAULT_CAPS = {"wall_seconds": 30, "memory_mb": 256, "pids": 64, "cpus": 1, "stdout_bytes": 524288}
CONSTRAINTS = ["No external action is taken without human approval.",
               "Only the fields in the dataset schema may be used.",
               "Every completion claim must cite recorded evidence."]
TEST_ID = "test-3way"


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha(obj):
    return hashlib.sha256(canonical(obj).encode("ascii")).hexdigest()


def _ascii(text, limit=300):
    return str(text).encode("ascii", "replace").decode("ascii")[:limit]


class RunRecord:
    def __init__(self, run_id, journal, run_dir):
        self.run_id, self.journal, self.run_dir = run_id, journal, run_dir
        self.state = StateMachine()
        self.label = "CREATED"          # finer-grained than the state: EXEC_PATH_2 etc., used for failed_at
        self.packet = None              # pending (or INCOMPLETE) packet
        self.packet_confirmed = None
        self.viewed = False
        self.mri = self.scan = self.manifest = self.rule = self.council = None
        self.executions, self.sections, self.call_cursor = [], {}, 0


class Orchestrator:
    def __init__(self, *, broker, runner, dataset, rule_path, runs_dir=None, clock=None, seed, assurance_tier="T0",
                 commit_key=None, caps=None, forbidden=()):
        self.broker, self.runner, self.dataset = broker, runner, dataset
        self.rule_path, self.runs_dir, self.seed = rule_path, runs_dir, seed
        self.clock, self.tier, self.commit_key = clock or _now, assurance_tier, commit_key
        self.caps = dict(caps or DEFAULT_CAPS)
        self.forbidden = tuple(forbidden)

    @property
    def question_ids(self):
        return [q["id"] for q in scan_service.load_questions()["items"]]

    # ---- files --------------------------------------------------------------------------------------------------------------
    def _write(self, run, name, text):
        if run.run_dir:
            with open(os.path.join(run.run_dir, name), "w", encoding="utf-8", newline="\n") as f:
                f.write(text)

    def _emit(self, run, kind, actor, data):
        return run.journal.append(kind, actor, data)

    def _flush_calls(self, run):
        recs = self.broker.records
        for r in recs[run.call_cursor:]:
            self._emit(run, "agent_call", "broker", {k: r[k] for k in (
                "call_id", "role", "requested_model", "response_model", "model_match", "tokens_in", "tokens_out",
                "prompt_sha256", "response_sha256")})
        run.call_cursor = len(recs)

    # ---- stages -------------------------------------------------------------------------------------------------------------
    def create(self, run_id):
        if not isinstance(run_id, str) or not _RUN_ID.match(run_id):
            raise ValueError("invalid run id")
        run_dir = None
        if self.runs_dir:
            run_dir = os.path.join(self.runs_dir, run_id)
            os.makedirs(run_dir)
        run = RunRecord(run_id, Journal(run_id, os.path.join(run_dir, "journal.jsonl") if run_dir else None,
                                        clock=self.clock, forbidden=self.forbidden), run_dir)
        run.call_cursor = len(self.broker.records)
        try:
            self._emit(run, "run_created", "control", {"dataset_id": self.dataset.dataset_id})
            run.manifest = copy.deepcopy(self.dataset.manifest)
            self._emit(run, "dataset_loaded", "control", {"dataset_sha256": run.manifest["dataset_sha256"], "manifest_sha256": sha(run.manifest)})
            self._advance(run, "DATASET_LOADED")
            mri = self.dataset.mri(run_id)
            bad = _schemas.errors("mri_inventory.schema.json", mri)
            if bad:
                raise ValueError("MRI output fails its schema: " + bad[0])
            run.mri = mri
            self._emit(run, "mri_done", "control", {"inventory_sha256": sha(mri)})
            self._advance(run, "MRI_DONE")
        except Exception as e:
            self._fail(run, e)
        return run

    def intake(self, run, answers):
        if run.state.state != "MRI_DONE":
            raise IllegalTransition(f"intake needs MRI_DONE, run is {run.state.state}")
        scan = scan_service.score(run.run_id, answers, self.commit_key)     # ScanRejected propagates; state does not advance
        run.scan = scan
        self._emit(run, "scan_done", "control", {"scan_sha256": sha(scan), "overall": scan["overall"]})
        self._advance(run, "SCAN_DONE")
        return scan

    def proceed(self, run):
        if run.state.state != "SCAN_DONE":
            raise IllegalTransition(f"proceed needs SCAN_DONE, run is {run.state.state}")
        try:
            self._council(run)
            self._execute_all(run)
            self._build(run)
        except Exception as e:
            self._fail(run, e)
        return run

    # ---- helpers ------------------------------------------------------------------------------------------------------------
    def _advance(self, run, to, label=None):
        run.state.advance(to)
        run.label = label or to

    def _fail(self, run, exc):
        if run.state.state in ("FAILED_CLOSED", "APPROVED_VIEWED", "EXPIRED"):
            return
        reason = exc.reason if hasattr(exc, "reason") and isinstance(exc.reason, str) else f"{type(exc).__name__}: {exc}"
        reason = _ascii(reason)
        failed_at = run.label
        p = None
        # F-M12-05: the API reads run.state and run.packet separately, so a client that sees FAILED_CLOSED must find the INCOMPLETE
        # packet already there. Everything is therefore built first, with the state still in flight, and the state flips last
        # (finally: the run always ends FAILED_CLOSED, even when the packet cannot be built).
        try:
            ctx = {"run_id": run.run_id, "built_at": self.clock(), "failed_at": failed_at, "failure_reason": reason,
                   "assurance_tier": self.tier}
            for k, v in (("dataset", run.manifest), ("mri", run.mri), ("scan", run.scan), ("council", run.council)):
                if v is not None:
                    ctx[k] = v
            if run.rule is not None and run.executions:
                ctx["executions"] = run.executions
            self._flush_calls_safe(run)
            ctx["journal"] = {"head_sha256": run.journal.head_sha256, "entries": len(run.journal.entries)}
            try:
                p = packet.build_incomplete(ctx)
            except packet.PacketError:
                ctx.pop("executions", None)
                ctx.pop("council", None)
                try:
                    p = packet.build_incomplete(ctx)
                except packet.PacketError:
                    p = None                                   # no packet is served (404) rather than an invented one
            data = {"failed_at": failed_at, "reason": reason}
            if p is not None:
                data["packet_sha256"] = p["packet_sha256"]
            self._emit(run, "error", "control", data)
            if p is not None:
                self._store(run, "incomplete", ctx, p)
        finally:
            run.packet = p
            run.state.fail_closed(reason)
            run.state.failed_at = failed_at

    def _flush_calls_safe(self, run):
        try:
            self._flush_calls(run)
        except Exception:
            pass

    def _store(self, run, kind, ctx, p):
        self._write(run, "inputs.json", canonical({"kind": kind, "ctx": ctx}))
        self._write(run, "packet.json", packet.dumps(p) + "\n")

    # ---- council ------------------------------------------------------------------------------------------------------------
    def _council(self, run):
        with open(self.rule_path, "rb") as f:
            raw = f.read()
        run.rule = rule_mod.parse_rule(raw)
        run.rule_text = raw.decode("utf-8")
        self._write(run, "decision_rule.yaml", run.rule_text)

        def on_stage(name):
            self._advance(run, name)

        ci = {"contract": "C1", "run_id": run.run_id, "mri": run.mri, "scan": run.scan, "constraints": list(CONSTRAINTS),
              "test_definition": {"test_id": TEST_ID, "description": "three-way comparison of surviving paths on the same synthetic dataset",
                                  "metrics": ["exceptions_caught", "false_alarms", "unsupported_claims", "manual_touches"],
                                  "decision_rule_sha256": run.rule.sha256}}
        try:
            res = council_run.run_council(self.broker, ci, seed=self.seed, on_stage=on_stage)
        finally:
            self._flush_calls_safe(run)
        run.council, run.council_result = res.run, res
        if run.state.state != "COUNCIL_DECISION":
            self._advance(run, "COUNCIL_DECISION")
        if res.status != "COMPLETE":
            raise council_run.CouncilFailedClosed("fewer than 2 paths survived the Critic: " + "; ".join(res.notes))
        self._advance(run, "DECISION_RULE_FROZEN")
        self._emit(run, "council_done", "control", {
            "council_sha256": sha(res.run), "status": res.status, "survivors": list(res.survivors), "notes": list(res.notes),
            "decision_rule_sha256": run.rule.sha256, "rule_frozen": True})

    # ---- execution ----------------------------------------------------------------------------------------------------------
    def _check_rule_frozen(self, run):
        if not rule_mod.verify_frozen(self.rule_path, run.rule.sha256):
            raise RuntimeError("decision rule file changed after freeze")

    def _final_paths(self, run):
        c = run.council
        paths = c["revision"]["paths"] if c["revision"]["performed"] else c["initial_paths"]
        return {p["path_id"]: p for p in paths}

    def _execute_all(self, run):
        events = copy.deepcopy(self.dataset.events)
        run.events_sha = sha(events)
        run.events = events
        self._write(run, "events.json", canonical(events) + "\n")
        by_id = self._final_paths(run)
        survivors = list(run.council_result.survivors)
        run.results, run.failed_attempts = {}, {}
        self._exec_pending = {}
        for k, pid in enumerate(survivors, 1):
            self._advance(run, "EXEC_PATH", label=f"EXEC_PATH_{k}")
            self._attempt(run, by_id[pid], 1, None)
        self._advance(run, "CLAIM_CHECKED")
        # one bounded correction per path whose first attempt failed its claim check or ended in error
        for k, pid in enumerate(survivors, 1):
            if self._needs_correction(run, pid):
                self._advance(run, "EXEC_CORRECTION", label=f"EXEC_CORRECTION_{k}")
                self._attempt(run, by_id[pid], 2, self._feedback(run, pid))

    def _needs_correction(self, run, pid):
        r = run.results[pid]
        return (not r["ok"]) or r["claims_verdict"] != "CLAIMS_HOLD"

    def _feedback(self, run, pid):
        r = run.results[pid]
        if not r["ok"]:
            return [{"problem": "the previous attempt did not return a valid result", "detail": _ascii(r.get("error") or "invalid output", 200)}]
        return [{"case_id": c["case_id"], "step_id": c["step_id"], "problem": c["reason"]}
                for c in r["claim_check"]["claims"] if c["result"] != "SUPPORTED"][:20]

    def _attempt(self, run, path, attempt, feedback):
        self._check_rule_frozen(run)
        pid = path["path_id"]
        coded = council_run.compile_apply(self.broker, path, self.dataset.schema, feedback)
        self._flush_calls(run)
        job = {"contract": "C2", "run_id": run.run_id, "path_id": pid, "intervention": path["intervention"],
               "dataset_id": self.dataset.dataset_id, "dataset_sha256": run.manifest["dataset_sha256"], "test_id": TEST_ID,
               "decision_rule_sha256": run.rule.sha256, "caps": dict(self.caps), "network": "none", "secrets_in_job": False,
               "approval_required_for_external_action": True}
        bad = _schemas.errors("blackbox_job.schema.json", job)
        if bad:
            raise ValueError("job refused: " + bad[0])
        kinds_before = [e["kind"] for e in run.journal.entries]
        out = self.runner.run(job, coded.code, copy.deepcopy(run.events), attempt=attempt,
                              emit=lambda kind, data: self._emit(run, kind, "runner", data))
        new = [e["kind"] for e in run.journal.entries][len(kinds_before):]
        if new.count("sandbox_created") != 1 or new.count("sandbox_destroyed") != 1:
            raise RuntimeError(f"runner did not journal exactly one create and one destroy for {pid} attempt {attempt}")
        rc = out["receipt"]
        if rc.get("destroy_verified") is not True:
            raise RuntimeError(f"sandbox destroy not verified for {pid} attempt {attempt}")
        resp = out["response"]
        resp_ok = not _schemas.errors("sb1_response.schema.json", resp) and resp.get("ok") is True and rc.get("termination") == "normal"
        events = run.events
        if resp_ok:
            cc = claims.check_claims(run.run_id, pid, resp["resolutions"], events)
            recomputed = metrics.recompute(resp, self.dataset.truth_exceptions, cc)
            self_rep = {k: v for k, v in (resp.get("self_metrics") or {}).items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
            discrepancy = metrics.discrepancy(self_rep, recomputed)
        else:
            cc = claims.check_claims(run.run_id, pid, [], events)
            recomputed = {"exceptions_caught": 0, "false_alarms": 0, "unsupported_claims": 0, "manual_touches": 0}
            self_rep, discrepancy = {}, False
        verdict = claims.verdict(cc)
        self._emit(run, "claim_check", "control", {"path_id": pid, "attempt": attempt, "supported": cc["supported"], "unsupported": cc["unsupported"],
                                                   "contradicted": cc["contradicted"], "claim_check_sha256": sha(cc), "verdict": verdict})
        receipt = {"run_id": run.run_id, "path_id": pid, "attempt": attempt, **{k: rc[k] for k in (
            "sandbox_id", "image_digest", "created_at", "started_at", "ended_at", "destroyed_at", "destroy_verified", "docker_flags_sha256",
            "exit_status", "termination", "peak_memory_mb", "stdout_sha256", "secret_scan")},
            "caps": dict(self.caps), "events_sha256": run.events_sha, "events_count": len(events),
            "metrics_recomputed": recomputed, "metrics_self_reported": self_rep, "metrics_discrepancy": discrepancy,
            "claim_check": cc, "journal_head_sha256": run.journal.head_sha256}
        bad = _schemas.errors("blackbox_run.schema.json", receipt)
        if bad:
            raise ValueError("receipt fails its schema: " + bad[0])
        run.executions.append(receipt)
        run.results[pid] = {"ok": resp_ok, "claims_verdict": verdict, "metrics": recomputed, "claim_check": cc, "receipt": receipt,
                            "error": None if resp_ok else (resp.get("error") if isinstance(resp, dict) else None)}

    # ---- packet -------------------------------------------------------------------------------------------------------------
    def _build(self, run):
        self._check_rule_frozen(run)
        eligible_input = {pid: {"claims_verdict": r["claims_verdict"], "metrics": r["metrics"]} for pid, r in run.results.items() if r["ok"]}
        outcome = rule_mod.evaluate(run.rule, eligible_input, self.dataset.cases_total)
        excluded = [pid for pid, r in run.results.items() if not r["ok"]]
        if excluded:
            outcome = dict(outcome, basis=outcome["basis"] + f" Paths excluded because the final attempt did not complete normally: {', '.join(sorted(excluded))}.")
        dec = run.council["decision"]
        ctx = {"run_id": run.run_id, "built_at": self.clock(), "dataset": run.manifest, "mri": run.mri, "scan": run.scan, "council": run.council,
               "rule": {"sha256": run.rule.sha256, "text": run.rule_text}, "executions": run.executions,
               "rule_outcome": {k: outcome[k] for k in ("result", "preferred_path_id", "basis")},
               "council_recommended_path_id": None if dec["no_winner"] else dec["recommended_path_id"],
               "containment": {"stress_test_run": False, "stress_termination": None, "control_plane_heartbeat_gap_max_ms": None},
               "approval": {"status": "PENDING", "confirmed_at": None}, "assurance_tier": self.tier,
               "journal": {"head_sha256": run.journal.head_sha256, "entries": len(run.journal.entries)},
               "median_cycle_computed": False}
        p = packet.build_packet(ctx)
        self._advance(run, "PACKET_BUILT")
        self._emit(run, "packet_built", "control", {"packet_sha256": p["packet_sha256"], "outcome": p["outcome"]["result"]})
        run.packet, run.ctx = p, ctx
        self._store(run, "complete", ctx, p)
        self._advance(run, "AWAITING_APPROVAL")

    # ---- approval gate ------------------------------------------------------------------------------------------------------
    def view(self, run):
        approval.require_viewable(run.state.state, run.packet)
        if run.viewed:                      # idempotent: a repeated view changes nothing and adds no journal entry
            return run.packet
        self._emit(run, "approval", "human", {"viewer_action": "viewed", "external_action_taken": False, "packet_sha256": run.packet["packet_sha256"]})
        run.viewed = True
        return run.packet

    def confirm(self, run):
        approval.require_confirmable(run.state.state, run.viewed)
        ctx = dict(run.ctx, built_at=run.packet["built_at"],
                   approval={"status": "VIEWED_CONFIRMED", "confirmed_at": self.clock()},
                   journal={"head_sha256": run.journal.head_sha256, "entries": len(run.journal.entries)})
        p = packet.build_packet(ctx)
        self._emit(run, "approval", "human", {"viewer_action": "confirmed", "external_action_taken": False, "packet_sha256": p["packet_sha256"]})
        self._advance(run, "APPROVED_VIEWED")
        run.packet_confirmed = p
        self._write(run, "packet_confirmed.json", packet.dumps(p) + "\n")
        return p

    def expire(self, run):
        if run.state.state != "AWAITING_APPROVAL":
            raise approval.ApprovalError(f"run is {run.state.state}: only a run awaiting approval can expire")
        self._emit(run, "approval", "control", {"viewer_action": "expired", "external_action_taken": False, "packet_sha256": run.packet["packet_sha256"]})
        self._advance(run, "EXPIRED")


def rebuild_packet(run_dir):
    """AT-10: rebuild the pending (or INCOMPLETE) packet from the stored inputs and check it against the journal."""
    from .journal import load_journal, verify_chain
    with open(os.path.join(run_dir, "inputs.json"), encoding="utf-8") as f:
        stored = json.load(f)
    p = packet.build_packet(stored["ctx"]) if stored["kind"] == "complete" else packet.build_incomplete(stored["ctx"])
    entries = load_journal(os.path.join(run_dir, "journal.jsonl"))
    v = verify_chain(entries)
    if not v.ok:
        raise packet.PacketError("journal chain broken: " + v.reason)
    n = p["journal"]["entries"]
    if n >= len(entries) or entries[n - 1]["entry_sha256"] != p["journal"]["head_sha256"] or entries[n]["data"].get("packet_sha256") != p["packet_sha256"]:
        raise packet.PacketError("rebuilt packet does not match the journal")
    return p
