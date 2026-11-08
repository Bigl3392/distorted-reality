"""Fake-backed loopback launcher: the real M5 WSGI app (control.api) served over HTTP on 127.0.0.1, with the web app's built files served from
the same origin, backed ONLY by test doubles (a scripted fake model server, a scripted fake runner, a fake dataset).

No real broker key, model, Docker, runner, or network beyond 127.0.0.1. Intended for the M12 browser tests and for flow traces.
Run from the repository root:   python -m tests.fakes.launch_fake --scenario complete --per-ip-runs-per-hour 50 --download-ttl-seconds 600 --exit-on-stdin-eof

There is no default for the two numeric controls: the caller supplies a number or the literal UNSET. The numbers below are the caller's test values, not
product settings. One run at a time per launch (the fake model server has one reply queue, re-scripted for every new run).

Prints one JSON line on stdout when ready (base_url, scenario, pid, identities, source hashes, controls). Teardown: close stdin (with
--exit-on-stdin-eof), send SIGINT, or call stop(). The temporary directory is removed unless --keep is given.
"""
import argparse
import copy
import hashlib
import json
import os
import shutil
import sys
import tempfile
import threading

from broker.client import BrokerClient, UrllibTransport
from broker.limits import DailyBudget, Limits
from broker.models import load_models
from control.api import ApiConfig, App, serve
from control.compose import make_factory
from control.orchestrator import Orchestrator
from tests.fakes.doubles import CASES, CODE, FakeDataset, FakeRunner, HAPPY, response
from tests.fakes.fake_vultr import FakeVultr, Reply
from tests.unit.test_broker import fixture
from tests.unit.test_council import EVIDENCE, critic_reply, decision_reply, jr, paths_reply

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FAKE_KEY = "fake-launcher-key-NOT-A-SECRET"

SCENARIOS = {
    "complete": "three paths run once each; path-a is preferred under the rule (exceptions caught 5 vs 2 vs 1)",
    "correction": "path-a's first attempt cites a dangling evidence reference (UNSUPPORTED), one correction attempt succeeds; path-a is preferred",
    "tie": "path-a and path-b are within the frozen margin, so the outcome is NO_SUFFICIENT_EVIDENCE",
    "incomplete": "the first model reply names a different model: the run fails closed with an INCOMPLETE packet",
    "refusal": "live inference is not available: POST /runs/{id}/start answers 409 mode=recorded with an empty recorded-run list",
}


def _script(scenario):
    ok = [jr(EVIDENCE), paths_reply(), critic_reply(), decision_reply()]
    if scenario == "complete":
        return ok + [CODE] * 3, dict(HAPPY)
    if scenario == "correction":
        s = dict(HAPPY)
        s[("path-a", 1)] = response(CASES[:5], bad=[CASES[0]])
        s[("path-a", 2)] = response(CASES[:5])
        return ok + [CODE] * 4, s
    if scenario == "tie":
        s = dict(HAPPY)
        s[("path-b", 1)] = response(CASES[:4])
        return ok + [CODE] * 3, s
    if scenario == "incomplete":
        return [Reply(content=json.dumps(EVIDENCE), model="some-other-model")], dict(HAPPY)
    if scenario == "refusal":
        return ok + [CODE] * 3, dict(HAPPY)
    raise SystemExit(f"unknown scenario {scenario}")


def _limit(v):
    if v == "UNSET":
        return None
    if not (v.isascii() and v.isdigit() and int(v) > 0):
        raise SystemExit("limits must be UNSET or a positive integer")
    return int(v)


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class Launch:
    def __init__(self, scenario, per_ip, ttl, static_dir=None, port=0, keep=False):
        self.scenario, self.keep = scenario, keep
        self.tmp = tempfile.mkdtemp(prefix="dr-fake-")
        self.rule = os.path.join(self.tmp, "decision_rule.yaml")
        shutil.copy(os.path.join(ROOT, "schemas", "decision_rule.yaml"), self.rule)
        self.runs = os.path.join(self.tmp, "runs")
        self.recorded = os.path.join(self.tmp, "recorded")           # stays EMPTY: no recorded real run exists, none is invented
        os.makedirs(self.runs)
        os.makedirs(self.recorded)
        self.static = static_dir or os.path.join(ROOT, "web", "dist")
        self.server = FakeVultr().__enter__()
        self.dataset = FakeDataset()
        self.models = load_models(fixture("models__valid_pinned_fixture_values.json"))
        cfg = ApiConfig(public=True, operator_token=None, per_ip_runs_per_hour=per_ip, download_ttl_seconds=ttl,
                        live_inference_allowed=lambda: scenario != "refusal", recorded_dir=self.recorded, static_dir=self.static,
                        runs_dir=self.runs)
        self.cfg = cfg
        self.app = App(make_factory(cfg, self._build, broker_factory=self._broker, runner=None, dataset=self.dataset,
                                    rule_path=self.rule, seed=7, assurance_tier="T0"), self.dataset, cfg)
        self.httpd = serve(self.app, port)
        self.port = self.httpd.server_address[1]

    def _broker(self):
        replies, _ = _script(self.scenario)
        self.server.queue.clear()
        self.server.script(*replies)
        return BrokerClient(models=self.models, api_key=FAKE_KEY, limits=Limits(None, None), daily=DailyBudget(), public=False,
                            transport=UrllibTransport(self.server.base_url), clock=lambda: "2026-11-05T15:00:00Z")

    def _build(self, **kw):
        _, runner_script = _script(self.scenario)
        kw["runner"] = FakeRunner(runner_script)
        return Orchestrator(**kw)

    def manifest(self):
        src = {n: _sha(os.path.join(ROOT, n)) for n in (
            "tests/fakes/launch_fake.py", "tests/fakes/doubles.py", "tests/fakes/fake_vultr.py", "control/api.py", "control/orchestrator.py",
            "control/packet.py", "control/compose.py", "docs/API_M5.md", "schemas/decision_rule.yaml")}
        idx = os.path.join(self.static, "index.html")
        return {"launch": "ready", "base_url": f"http://127.0.0.1:{self.port}", "scenario": self.scenario, "pid": os.getpid(),
                "static_dir_has_index": os.path.isfile(idx), "static_index_sha256": _sha(idx) if os.path.isfile(idx) else None,
                "identities": {"dataset_id": self.dataset.dataset_id, "case_ids": list(CASES), "model_ids": {
                    r: self.models.role(r).model_id for r in ("evidence", "path", "critic", "decision", "coder")},
                    "key": "fake (never a real key)", "runner": "scripted FakeRunner", "model_server": "FakeVultr on loopback"},
                "tmp_dir": self.tmp, "source_sha256": src, "scenarios": SCENARIOS, "limits": {"per_ip_runs_per_hour": self.cfg.per_ip_runs_per_hour,
                                                                         "download_ttl_seconds": self.cfg.download_ttl_seconds},
                "recorded_runs": "none (the directory is empty by design)", "one_run_at_a_time": True}

    def serve_forever(self):
        self.httpd.serve_forever()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.server.__exit__(None, None, None)
        if not self.keep:
            shutil.rmtree(self.tmp, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", required=True, choices=sorted(SCENARIOS))
    ap.add_argument("--per-ip-runs-per-hour", required=True, help="a positive integer, or UNSET")
    ap.add_argument("--download-ttl-seconds", required=True, help="a positive integer, or UNSET")
    ap.add_argument("--port", type=int, default=0, help="0 = ephemeral; the bind address is always 127.0.0.1")
    ap.add_argument("--static-dir", default=None)
    ap.add_argument("--exit-on-stdin-eof", action="store_true")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args(argv)
    ln = Launch(a.scenario, _limit(a.per_ip_runs_per_hour), _limit(a.download_ttl_seconds), a.static_dir, a.port, a.keep)
    print(json.dumps(ln.manifest()), flush=True)
    if a.exit_on_stdin_eof:
        def watch():
            sys.stdin.read()
            threading.Thread(target=ln.httpd.shutdown, daemon=True).start()
        threading.Thread(target=watch, daemon=True).start()
    try:
        ln.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        ln.stop()


if __name__ == "__main__":
    main()
