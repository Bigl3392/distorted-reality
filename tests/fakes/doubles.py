"""Scripted test doubles shared by the unit tests and the loopback launcher: a fake dataset (stands in for M1), a scripted runner
(stands in for M4) and the scenario scripts. Synthetic only. Nothing here executes model-written code, starts Docker or reaches a service.
The fake model server is tests/fakes/fake_vultr.py."""
import copy
import json
import os

from tests.fakes.fake_vultr import Reply
from tests.unit.test_broker import fixture
from tests.unit.test_council import jr

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RULE_SRC = os.path.join(ROOT, "schemas", "decision_rule.yaml")
MANIFEST = fixture("dataset_manifest__valid.json")
MRI = fixture("mri_inventory__valid.json")
RECEIPT = fixture("blackbox_run__valid.json")
EVENT = fixture("dataset_event__valid.json")
CASES = [f"inv-{i:04d}" for i in range(1, 11)]
TRUTH = set(CASES[:5])
GT_MARKER = "GT_MARKER_zz_do_not_leak"
CODE = jr({"code": "def apply(events):\n    return {}\n"})


def make_events():
    rows = []
    for n, case in enumerate(CASES, 1):
        for step in (1, 2):
            e = copy.deepcopy(EVENT)
            e.update(case_id=case, step_id=step, status="completed", evidence_ref=f"rcpt-{n:04d}-{step}",
                     timestamp=f"2026-11-05T15:{n:02d}:{step:02d}Z")
            rows.append(e)
    return rows


class FakeDataset:
    dataset_id = "eo-recv-v1"
    manifest = MANIFEST
    events = make_events()
    truth_exceptions = TRUTH
    schema = {"fields": ["case_id", "step_id", "status", "evidence_ref", "timestamp"]}
    cases_total = len(CASES)
    _gt_marker = GT_MARKER  # lives only on the sealed side; must never reach a prompt, a runner or a journal

    def mri(self, run_id):
        m = copy.deepcopy(MRI)
        m["run_id"] = run_id
        return m


def resolutions(cases, bad=()):
    out = []
    for case in cases:
        n = CASES.index(case) + 1
        ref = "rcpt-9999-1" if case in bad else f"rcpt-{n:04d}-1"
        out.append({"case_id": case, "step_id": 1, "claimed": "matched", "evidence_ref": ref})
    return out


def response(flag, bad=(), self_metrics=None, touched=()):
    return {"contract": "SB1", "ok": True, "flagged_cases": list(flag), "resolutions": resolutions(flag, bad),
            "manual_touch_cases": list(touched), "self_metrics": self_metrics or {}, "error": None}


class FakeRunner:
    """Stands in for M4. Returns scripted SB1 responses; emits the journal entries a real runner must emit."""

    def __init__(self, script, destroy_verified=True, skip_destroy_entry=False):
        self.script, self.calls = script, []
        self.destroy_verified, self.skip_destroy_entry = destroy_verified, skip_destroy_entry

    def run(self, job, code, events, *, attempt, emit):
        self.calls.append({"job": job, "code": code, "events": events, "attempt": attempt})
        sid = f"ctr-{job['path_id']}-a{attempt}"
        emit("sandbox_created", {"sandbox_id": sid, "path_id": job["path_id"], "attempt": attempt})
        emit("sandbox_started", {"sandbox_id": sid})
        emit("sandbox_ended", {"sandbox_id": sid, "termination": "normal", "exit_status": 0})
        if not self.skip_destroy_entry:
            emit("sandbox_destroyed", {"sandbox_id": sid, "destroy_verified": self.destroy_verified})
        r = {k: RECEIPT[k] for k in ("image_digest", "created_at", "started_at", "ended_at", "destroyed_at", "docker_flags_sha256",
                                     "exit_status", "termination", "peak_memory_mb", "stdout_sha256", "secret_scan")}
        r.update(sandbox_id=sid, destroy_verified=self.destroy_verified)
        resp = self.script[(job["path_id"], attempt)]
        return {"receipt": r, "response": resp}


HAPPY = {("path-a", 1): response(CASES[:5]), ("path-b", 1): response(CASES[:2]), ("path-c", 1): response(CASES[:1])}


