"""Composition root (LDR item 3): real M1 dataset and real M4 runner behind M5's interfaces, and a real-key broker factory.
Local only. M1 is exercised through build_synthetic() (PROVISIONAL: no G14 weather); M4 through its own FakeDocker double.
Nothing here starts Docker, reaches a service or reads a real key. The keys below are fake test values."""
import copy
import json
import os
import shutil
import tempfile
import unittest

from broker import _schemas
from sandbox.runner import ImageLock, SandboxError
from sandbox.tests.test_runner import FakeDocker, fixture
from tests.fakes.fake_vultr import FakeVultr, Reply
from tests.unit.test_broker import KEY, pinned
from tests.unit.test_council import EVIDENCE, critic_reply, decision_reply, jr, paths_reply
from tests.fakes.doubles import CODE, RULE_SRC

LOCK = ImageLock("fixture-only", "sha256:" + "a" * 64, "python:3.12-slim@sha256:" + "b" * 64)
NOW = "2026-11-07T12:00:00Z"
SECRET = "fake-secret-value-for-tests-0123456789"


def synthetic():
    from dataset.generator import build_synthetic
    return build_synthetic()


class ScriptedDocker(FakeDocker):
    """M4's FakeDocker, but `start` returns a chosen SB1 response instead of the fixture one."""

    def __init__(self, response, **kw):
        super().__init__(**kw)
        self.response = response

    def call(self, args, *, stdin=b"", deadline=None, limit=524288):
        from sandbox.runner import CommandResult
        if args[0] == "start" and not self.start_error and not self.overflow:
            self.commands.append(args)
            self.stdin_seen = stdin
            return CommandResult(0, json.dumps(self.response).encode(), b"")
        return super().call(args, stdin=stdin, deadline=deadline, limit=limit)


class TestBundledDataset(unittest.TestCase):
    def make(self):
        from control.dataset_adapter import BundledDataset
        return BundledDataset(synthetic(), clock=lambda: NOW)

    def test_exposes_the_interface_the_orchestrator_reads_and_it_validates(self):
        d = self.make()
        self.assertEqual(d.dataset_id, "eo-ap-v1")
        self.assertEqual(_schemas.errors("dataset_manifest.schema.json", d.manifest), [])
        self.assertEqual(len(d.events), d.manifest["row_count"])
        self.assertEqual(d.cases_total, 200)
        mri = d.mri("run-abc123")
        self.assertEqual(_schemas.errors("mri_inventory.schema.json", mri), [])
        self.assertEqual((mri["run_id"], mri["scanned_at"]), ("run-abc123", NOW))
        self.assertTrue(d.schema["fields"])

    def test_truth_is_exactly_M1s_exceptional_cases_and_stays_out_of_every_public_surface(self):
        d = self.make()
        _, _, truth, _ = synthetic()
        self.assertEqual(set(d.truth_exceptions), set(truth["exceptional_case_ids"]))
        self.assertTrue(d.truth_exceptions)
        public = json.dumps([d.manifest, d.mri("run-abc123"), d.events, d.schema], sort_keys=True)
        for needle in ("exceptional_case_ids", "correct_resolution", "exception_types"):
            self.assertNotIn(needle, public)
        self.assertNotIn("exceptional_case_ids", repr(vars(d)).replace("truth_exceptions", ""))

    def test_events_that_do_not_match_the_manifest_hash_are_refused(self):
        from control.dataset_adapter import BundledDataset
        from dataset.generator import DatasetError
        events, manifest, truth, baseline = synthetic()
        events = copy.deepcopy(events)
        events[0]["output"] += "x"
        with self.assertRaises(DatasetError):
            BundledDataset((events, manifest, truth, baseline), clock=lambda: NOW)

    def test_synthetic_core_is_marked_provisional_and_a_release_factory_refuses_it(self):
        from control.api import ConfigError, ApiConfig
        from control.compose import make_real_factory
        d = self.make()
        self.assertTrue(d.provisional)
        with self.assertRaises(ConfigError):
            make_real_factory(ApiConfig(public=False), dataset=d, runner=object(), broker_factory=lambda: None,
                              rule_path="x", seed=7)
        make_real_factory(ApiConfig(public=False), dataset=d, runner=object(), broker_factory=lambda: None,
                          rule_path="x", seed=7, allow_provisional=True)


class TestSandboxRunner(unittest.TestCase):
    def setUp(self):
        self.events, self.manifest, _, _ = synthetic()
        from dataset.generator import encode_rows
        import hashlib
        self.job = fixture("blackbox_job__valid.json")
        self.job.update(dataset_sha256=hashlib.sha256(encode_rows(self.events)).hexdigest(), run_id="run-abc123", path_id="path-a")
        self.response = fixture("sb1_response__valid_ok.json")

    def runner(self, docker, **kw):
        from control.runner_adapter import SandboxRunner
        kw.setdefault("secret_values", lambda: [SECRET])
        return SandboxRunner(lock=LOCK, executor=docker, clock=lambda: NOW, **kw)

    def go(self, docker, **kw):
        journal = []
        out = self.runner(docker, **kw).run(self.job, "def apply(events):\n    return {}\n", self.events, attempt=1,
                                            emit=lambda kind, data: journal.append((kind, data)))
        return out, journal

    def test_returns_the_fields_M5_reads_and_the_sb1_response(self):
        out, journal = self.go(ScriptedDocker(self.response))
        keys = {"sandbox_id", "image_digest", "created_at", "started_at", "ended_at", "destroyed_at", "destroy_verified",
                "docker_flags_sha256", "exit_status", "termination", "peak_memory_mb", "stdout_sha256", "secret_scan"}
        self.assertEqual(set(out["receipt"]), keys)
        self.assertEqual(out["response"], self.response)
        self.assertIs(out["receipt"]["destroy_verified"], True)
        self.assertEqual(out["receipt"]["termination"], "normal")
        self.assertEqual(out["receipt"]["image_digest"], LOCK.image_digest)
        self.assertEqual([k for k, _ in journal], ["sandbox_created", "sandbox_started", "sandbox_ended", "sandbox_destroyed"])

    def test_a_non_normal_end_gives_a_schema_valid_SB1_failure_not_None(self):
        out, _ = self.go(ScriptedDocker(self.response, oom=True))
        self.assertEqual(out["receipt"]["termination"], "oom_killed")
        self.assertEqual(_schemas.errors("sb1_response.schema.json", out["response"]), [])
        self.assertIs(out["response"]["ok"], False)

    def test_an_unverified_destroy_fails_closed(self):
        with self.assertRaisesRegex(SandboxError, "destroy"):
            self.go(ScriptedDocker(self.response, orphan=True))

    def test_the_secret_scan_is_computed_per_run_and_a_hit_fails_closed_without_echoing_the_secret(self):
        out, _ = self.go(ScriptedDocker(self.response), secret_values=lambda: [SECRET])
        self.assertEqual(out["receipt"]["secret_scan"], {"canary_present_in_env": False, "scan_passed": True})
        leaked = copy.deepcopy(self.response)
        leaked["resolutions"] = [{"case_id": "inv-0001", "step_id": 1, "claimed": "matched " + SECRET, "evidence_ref": None}]
        with self.assertRaises(SandboxError) as cm:
            self.go(ScriptedDocker(leaked), secret_values=lambda: [SECRET])
        self.assertNotIn(SECRET, str(cm.exception))
        self.assertNotIn(SECRET, repr(cm.exception))

    def test_the_inference_key_never_reaches_docker_arguments_or_stdin(self):
        d = ScriptedDocker(self.response)
        self.go(d, secret_values=lambda: [SECRET])
        self.assertNotIn(SECRET, json.dumps(d.commands))
        self.assertNotIn(SECRET.encode(), d.stdin_seen)


class NoisyDocker(FakeDocker):
    """FakeDocker whose `start` returns chosen raw stdout/stderr bytes, optionally overflowed, and whose `inspect` state can be chosen."""

    def __init__(self, stdout=b"", stderr=b"", *, state=None, **kw):
        super().__init__(**kw)
        self.stdout, self.stderr, self.state = stdout, stderr, state

    def call(self, args, *, stdin=b"", deadline=None, limit=524288):
        from sandbox.runner import CommandResult
        if args[0] == "start":
            self.commands.append(args)
            self.stdin_seen = stdin
            return CommandResult(0, self.stdout, self.stderr, overflow=self.overflow)
        if args[0] == "inspect" and self.state is not None:
            self.commands.append(args)
            return CommandResult(0, json.dumps([{"State": self.state}]).encode(), b"")
        return super().call(args, stdin=stdin, deadline=deadline, limit=limit)


def _chain_text(exc):
    import traceback
    return "".join(traceback.format_exception(exc))


CODE_OK = "def apply(events):\n    return {}\n"


class TestSandboxRunnerBinding(TestSandboxRunner):
    """Walter's conditions (handoffs/M4/BINDING_REPLY_Walter.md): explicit scanner wiring, full byte and decoded coverage, value-free
    errors, hashes of captured bytes, adapter-generated provenance, and M4's lock and deadline checks kept. Inherits setUp and helpers."""

    def good_bytes(self):
        return json.dumps(self.response).encode()

    def assertValueFree(self, exc, secret=SECRET):
        self.assertNotIn(secret, _chain_text(exc))
        self.assertNotIn(secret, repr(exc))
        self.assertIsNone(exc.__cause__)

    # -- explicit wiring -------------------------------------------------------------------------------------------------------
    def test_a_runner_with_no_scanner_wiring_is_refused_unless_it_is_labelled_a_fixture(self):
        from control.api import ConfigError
        from control.runner_adapter import SandboxRunner
        with self.assertRaises(ConfigError):
            SandboxRunner(lock=LOCK, executor=ScriptedDocker(self.response), clock=lambda: NOW)

    def test_fixture_mode_is_labelled_and_never_reports_a_passed_scan(self):
        from control.runner_adapter import SandboxRunner
        r = SandboxRunner(lock=LOCK, executor=ScriptedDocker(self.response), clock=lambda: NOW, fixture_unscanned=True)
        self.assertEqual(r.scan_mode, "fixture-unscanned")
        out = r.run(self.job, CODE_OK, self.events, attempt=1, emit=lambda k, d: None)
        self.assertEqual(out["receipt"]["secret_scan"], {"canary_present_in_env": False, "scan_passed": False})
        self.assertEqual(self.runner(ScriptedDocker(self.response)).scan_mode, "configured")

    def test_fixture_mode_cannot_be_combined_with_a_real_executor_or_a_scanner(self):
        from control.api import ConfigError
        from control.runner_adapter import SandboxRunner
        from sandbox.runner import DockerExecutor
        with self.assertRaises(ConfigError):
            SandboxRunner(lock=LOCK, executor=DockerExecutor(docker="MUST-NOT-EXECUTE"), fixture_unscanned=True, operation_seconds=1)
        with self.assertRaises(ConfigError):
            SandboxRunner(lock=LOCK, executor=ScriptedDocker(self.response), fixture_unscanned=True, secret_values=lambda: [SECRET])

    def test_a_configured_scanner_that_yields_no_values_fails_closed_before_any_dispatch(self):
        d = ScriptedDocker(self.response)
        with self.assertRaises(SandboxError):
            self.go(d, secret_values=lambda: ())
        self.assertEqual(d.commands, [])

    # -- stdin: the key never goes in -------------------------------------------------------------------------------------------
    def test_a_protected_value_in_code_or_events_is_refused_before_dispatch(self):
        bad_events = copy.deepcopy(self.events)
        bad_events[0]["output"] = SECRET
        cases = (("def apply(events):\n    return '" + SECRET + "'\n", self.events), (CODE_OK, bad_events))
        for n, (code, ev) in enumerate(cases):
            d = ScriptedDocker(self.response)
            with self.subTest(case=n), self.assertRaises(SandboxError) as cm:
                self.runner(d).run(self.job, code, ev, attempt=1, emit=lambda k, dd: None)
            self.assertValueFree(cm.exception)
            self.assertEqual(d.commands, [])

    # -- bounded raw output ------------------------------------------------------------------------------------------------------
    def test_a_protected_value_in_raw_stderr_fails_closed_after_cleanup_without_echo(self):
        d = NoisyDocker(self.good_bytes(), ("trace " + SECRET).encode())
        journal = []
        with self.assertRaises(SandboxError) as cm:
            self.runner(d).run(self.job, CODE_OK, self.events, attempt=1, emit=lambda k, dd: journal.append(k))
        self.assertValueFree(cm.exception)
        self.assertIn("sandbox_destroyed", journal)
        self.assertTrue(any(c[0] == "rm" for c in d.commands))

    def test_a_protected_value_in_raw_stdout_on_a_non_normal_end_fails_closed(self):
        for kw in ({"oom": True}, {"overflow": True}):
            d = NoisyDocker(("noise " + SECRET).encode(), b"", **kw)
            with self.subTest(kw=kw), self.assertRaises(SandboxError) as cm:
                self.go(d)
            self.assertValueFree(cm.exception)

    def test_a_protected_value_in_unparseable_or_schema_invalid_stdout_never_reaches_the_error(self):
        bad = dict(self.response, ok=SECRET)
        for raw in (("not json " + SECRET).encode(), json.dumps(bad).encode(), json.dumps(dict(self.response, extra=SECRET)).encode()):
            d = NoisyDocker(raw, b"")
            with self.subTest(raw=raw[:12]), self.assertRaises(SandboxError) as cm:
                self.go(d)
            self.assertValueFree(cm.exception)
            self.assertIsNone(cm.exception.__context__)

    def test_json_escaped_and_decoded_forms_are_found(self):
        tricky = 'k"e\\y-é-0123456789abcdef'
        leaked = copy.deepcopy(self.response)
        leaked["resolutions"] = [{"case_id": "inv-0001", "step_id": 1, "claimed": "saw " + tricky + " here", "evidence_ref": None}]
        with self.assertRaises(SandboxError) as cm:
            self.go(ScriptedDocker(leaked), secret_values=lambda: [tricky])
        self.assertValueFree(cm.exception, tricky)

    def test_a_protected_value_in_a_dict_key_of_the_response_is_found(self):
        leaked = dict(self.response)
        leaked["self_metrics"] = {SECRET: 1}
        with self.assertRaises(SandboxError) as cm:
            self.go(ScriptedDocker(leaked))
        self.assertValueFree(cm.exception)

    def test_a_clean_run_reports_a_passed_scan_from_the_configuration_declaration(self):
        out, _ = self.go(ScriptedDocker(self.response))
        self.assertEqual(out["receipt"]["secret_scan"], {"canary_present_in_env": False, "scan_passed": True})

    def test_protected_bytes_that_exist_only_in_the_serialized_request_are_stopped_before_start(self):
        d = ScriptedDocker(self.response)
        with self.assertRaises(SandboxError) as cm:
            self.go(d, secret_values=lambda: ['"contract":"SB1"'])
        self.assertFalse(any(c[0] == "start" for c in d.commands))
        self.assertNotIn("contract", str(cm.exception))

    def test_the_json_escaped_form_is_found_in_raw_non_json_stderr(self):
        tricky = 'k"e\\y-é-0123456789abcdef'
        noisy = NoisyDocker(self.good_bytes(), b"log: " + json.dumps(tricky).encode() + b" end")
        with self.assertRaises(SandboxError) as cm:
            self.go(noisy, secret_values=lambda: [tricky])
        self.assertValueFree(cm.exception, tricky)

    def test_a_protected_value_is_not_forwarded_into_the_journal(self):
        class LeakyVersion(ScriptedDocker):
            def call(self, args, **kw):
                from sandbox.runner import CommandResult
                if args[0] == "version":
                    self.commands.append(args)
                    return CommandResult(0, json.dumps({"Server": {"Version": "fixture-only", "GitCommit": SECRET}}).encode(), b"")
                return super().call(args, **kw)
        journal = []
        with self.assertRaises(SandboxError):
            self.runner(LeakyVersion(self.response)).run(self.job, CODE_OK, self.events, attempt=1, emit=lambda k, d: journal.append((k, d)))
        self.assertNotIn(SECRET, json.dumps(journal))

    # -- hashes and provenance ---------------------------------------------------------------------------------------------------
    def test_stdout_hash_is_the_hash_of_the_captured_bytes_not_of_a_synthesized_envelope(self):
        import hashlib
        raw = b"partial output before the kill"
        out, _ = self.go(NoisyDocker(raw, b"", overflow=True))
        self.assertEqual(out["receipt"]["termination"], "error")
        self.assertEqual(out["receipt"]["stdout_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(out["receipt"]["stdout_sha256"], hashlib.sha256(json.dumps(out["response"]).encode()).hexdigest())

    def test_overflow_returns_an_execution_with_no_output_and_the_envelope_is_marked_adapter_generated_in_the_journal(self):
        out, journal = self.go(NoisyDocker(b"x" * 10, b"", overflow=True))
        self.assertEqual((out["receipt"]["termination"], out["response"]["ok"]), ("error", False))
        marks = [d for k, d in journal if d.get("adapter_generated_response")]
        self.assertEqual(len(marks), 1)
        self.assertEqual(marks[0]["termination"], "error")
        self.assertEqual(marks[0]["stdout_sha256"], out["receipt"]["stdout_sha256"])
        ended = [d for k, d in journal if k == "sandbox_ended"][0]
        self.assertIs(ended["stdout_truncated"], True)

    def test_a_real_sb1_failure_response_is_kept_and_not_marked_adapter_generated(self):
        failing = fixture("sb1_response__valid_error.json")
        out, journal = self.go(ScriptedDocker(failing))
        self.assertEqual(out["response"], failing)
        self.assertFalse([1 for k, d in journal if d.get("adapter_generated_response")])

    def test_a_normal_end_without_output_is_a_binding_violation(self):
        from unittest import mock
        from sandbox.runner import Execution
        ex = Execution("abc123", None, "normal", 0, True, "f" * 64, "e" * 64, {}, NOW, NOW, NOW, NOW, LOCK, dict(self.job["caps"]))
        with mock.patch("control.runner_adapter.run_job", return_value=ex), self.assertRaises(SandboxError):
            self.go(ScriptedDocker(self.response))

    def test_caps_that_differ_from_the_dispatched_job_are_refused(self):
        from unittest import mock
        from sandbox.runner import Execution
        caps = dict(self.job["caps"], wall_seconds=1)
        ex = Execution("abc123", self.response, "normal", 0, True, "f" * 64, "e" * 64, {}, NOW, NOW, NOW, NOW, LOCK, caps)
        with mock.patch("control.runner_adapter.run_job", return_value=ex), self.assertRaisesRegex(SandboxError, "caps"):
            self.go(ScriptedDocker(self.response))

    def test_a_docker_not_started_sentinel_or_malformed_timestamp_is_not_accepted_as_evidence(self):
        for bad in ("0001-01-01T00:00:00Z", "yesterday", ""):
            state = {"ExitCode": 0, "OOMKilled": False, "StartedAt": bad, "FinishedAt": "2026-11-04T12:00:01Z"}
            with self.subTest(bad=bad), self.assertRaisesRegex(SandboxError, "timestamp"):
                self.go(NoisyDocker(self.good_bytes(), b"", state=state))

    def test_nanosecond_docker_timestamps_are_preserved_verbatim(self):
        state = {"ExitCode": 0, "OOMKilled": False, "StartedAt": "2026-11-04T12:00:00.123456789Z", "FinishedAt": "2026-11-04T12:00:01.987654321Z"}
        out, _ = self.go(NoisyDocker(self.good_bytes(), b"", state=state))
        self.assertEqual((out["receipt"]["started_at"], out["receipt"]["ended_at"]), ("2026-11-04T12:00:00.123456789Z", "2026-11-04T12:00:01.987654321Z"))

    def test_sandbox_journal_entries_are_bound_to_run_path_attempt_and_requested_name(self):
        _, journal = self.go(ScriptedDocker(self.response))
        for kind, data in journal:
            if kind.startswith("sandbox_"):
                self.assertEqual((data["path_id"], data["attempt"], data["requested_name"]), ("path-a", 1, "dr-run-abc123-path-a-a1"), kind)
        created = [d for k, d in journal if k == "sandbox_created"][0]
        self.assertEqual(created["phase"], "requested")

    # -- M4's lock and deadline checks are not bypassed ----------------------------------------------------------------------------
    def test_a_real_executor_still_meets_M4s_lock_and_deadline_checks(self):
        from control.runner_adapter import SandboxRunner
        from sandbox.runner import DockerExecutor

        def run(lock_path, secs):
            return SandboxRunner(lock=LOCK, executor=DockerExecutor(docker="MUST-NOT-EXECUTE"), clock=lambda: NOW,
                                 secret_values=lambda: [SECRET], operation_seconds=secs, lock_path=lock_path
                                 ).run(self.job, CODE_OK, self.events, attempt=1, emit=lambda k, d: None)
        with self.assertRaisesRegex(SandboxError, "G4"):
            run(os.path.join(tempfile.gettempdir(), "NO_SUCH_LOCK_dr"), 1)
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        lock_file = os.path.join(tmp, "docker_image.lock")
        with open(lock_file, "w", encoding="utf-8") as f:
            json.dump({"docker_engine_version": LOCK.docker_engine_version, "image_digest": LOCK.image_digest, "base_image": LOCK.base_image}, f)
        with self.assertRaisesRegex(SandboxError, "deadline"):
            run(lock_file, None)


class TestRealRunnerWiring(TestSandboxRunner):
    """compose.make_real_runner is the one place the inference key reaches the runner's scanner (from the environment, never printed)."""

    def make(self, docker, env=None, **kw):
        from control.compose import make_real_runner
        return make_real_runner({"VULTR_INFERENCE_API_KEY": KEY} if env is None else env, lock=LOCK, executor=docker, clock=lambda: NOW, **kw)

    def test_wires_the_key_into_the_scan_so_a_leak_of_the_key_fails_closed(self):
        r = self.make(ScriptedDocker(self.response))
        self.assertEqual(r.scan_mode, "configured")
        leaked = copy.deepcopy(self.response)
        leaked["resolutions"] = [{"case_id": "inv-0001", "step_id": 1, "claimed": "saw " + KEY, "evidence_ref": None}]
        with self.assertRaises(SandboxError) as cm:
            self.make(ScriptedDocker(leaked)).run(self.job, CODE_OK, self.events, attempt=1, emit=lambda k, d: None)
        self.assertNotIn(KEY, _chain_text(cm.exception))

    def test_a_missing_key_is_a_config_error_not_an_unscanned_runner(self):
        from control.api import ConfigError
        for env in ({}, {"VULTR_INFERENCE_API_KEY": " "}):
            with self.subTest(env=env), self.assertRaises(ConfigError):
                self.make(ScriptedDocker(self.response), env=env)


class TestBrokerFactory(unittest.TestCase):
    def env(self, **over):
        e = {"VULTR_INFERENCE_API_KEY": KEY}
        e.update(over)
        return e

    def make(self, env):
        from control.broker_factory import make_broker_factory
        return make_broker_factory(env, models=pinned())

    def test_builds_per_run_clients_that_share_one_daily_budget_and_never_show_the_key(self):
        f = self.make(self.env())
        a, b = f(), f()
        self.assertIsNot(a, b)
        self.assertIs(a._daily, b._daily)
        for obj in (a, b):
            self.assertNotIn(KEY, repr(obj))
            self.assertNotIn(KEY, str(obj))
        self.assertTrue(a._public)

    def test_missing_or_blank_key_is_a_config_error_that_names_the_variable_not_a_value(self):
        from control.api import ConfigError
        for env in ({}, {"VULTR_INFERENCE_API_KEY": ""}, {"VULTR_INFERENCE_API_KEY": "   "}):
            with self.subTest(env=env), self.assertRaises(ConfigError) as cm:
                self.make(env)
            self.assertIn("VULTR_INFERENCE_API_KEY", str(cm.exception))

    def test_limits_come_from_env_and_unset_stays_unset(self):
        f = self.make(self.env())
        self.assertIsNone(f()._limits.run_token_cap)
        self.assertFalse(f()._limits.fully_set)
        g = self.make(self.env(DR_RUN_TOKEN_CAP="1000", DR_DAILY_TOKEN_BUDGET="5000", DR_RATE_LIMIT_RUNS_PER_IP_PER_HOUR="3"))
        self.assertTrue(g()._limits.fully_set)

    def test_a_bad_limit_value_is_refused(self):
        from broker.limits import LimitsError
        with self.assertRaises(LimitsError):
            self.make(self.env(DR_RUN_TOKEN_CAP="lots"))

    def test_reads_only_its_variable_and_does_not_touch_the_process_environment(self):
        before = dict(os.environ)
        self.make(self.env())
        self.assertEqual(dict(os.environ), before)

    def test_a_template_models_file_is_refused(self):
        from broker.models import ModelsError
        from control.broker_factory import make_broker_factory
        bad = copy.deepcopy(pinned())
        bad["models_status"] = "TEMPLATE"
        with self.assertRaises(ModelsError):
            make_broker_factory(self.env(), models=bad)

    def test_key_scanner_finds_the_key_and_has_no_readable_key(self):
        from control.broker_factory import key_scanner
        scan = key_scanner(self.env())
        self.assertEqual(list(scan()), [KEY])
        self.assertNotIn(KEY, repr(scan))


class TestCompositionEndToEnd(unittest.TestCase):
    """Real M1 dataset (provisional synthetic) + real M4 runner (fake Docker) + M5 orchestrator + scripted council server."""

    def test_a_full_run_reaches_AWAITING_APPROVAL_with_a_valid_packet_and_no_truth_leak(self):
        from broker.client import BrokerClient, UrllibTransport
        from broker.limits import DailyBudget, Limits
        from broker.models import load_models
        from control.dataset_adapter import BundledDataset
        from control.journal import verify_chain
        from control.orchestrator import Orchestrator
        from control.runner_adapter import SandboxRunner
        events, manifest, truth, baseline = synthetic()
        dataset = BundledDataset((events, manifest, truth, baseline), clock=lambda: NOW)
        # only step-3 events with status "completed" are usable evidence (a stalled step is CONTRADICTED by claims.py, which is right)
        step3 = {e["case_id"]: e for e in events if e["step_id"] == 3 and e["evidence_ref"] and e["status"] == "completed"}
        flagged = [c for c in truth["exceptional_case_ids"] if c in step3][:3]
        self.assertTrue(flagged)
        response = {"contract": "SB1", "ok": True, "flagged_cases": flagged, "manual_touch_cases": [], "self_metrics": {}, "error": None,
                    "resolutions": [{"case_id": c, "step_id": 3, "claimed": "matched", "evidence_ref": step3[c]["evidence_ref"]} for c in flagged]}
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        rule = os.path.join(tmp, "decision_rule.yaml")
        shutil.copy(RULE_SRC, rule)
        server = FakeVultr().__enter__()
        self.addCleanup(server.__exit__, None, None, None)
        server.script(jr(EVIDENCE), paths_reply(), critic_reply(), decision_reply(), CODE, CODE, CODE)
        broker = BrokerClient(models=load_models(pinned()), api_key=KEY, limits=Limits(None, None), daily=DailyBudget(), public=False,
                              transport=UrllibTransport(server.base_url), clock=lambda: NOW)
        docker = ScriptedDocker(response)
        runner = SandboxRunner(lock=LOCK, executor=docker, clock=lambda: NOW, secret_values=lambda: [KEY])
        ticks = iter(f"2026-11-07T12:{m:02d}:{s:02d}Z" for m in range(60) for s in range(60))
        orch = Orchestrator(broker=broker, runner=runner, dataset=dataset, rule_path=rule, runs_dir=tmp, clock=lambda: next(ticks),
                            seed=7, assurance_tier="T0")
        run = orch.create("run-compose1")
        orch.intake(run, dict.fromkeys(orch.question_ids, 3))
        orch.proceed(run)
        self.assertEqual(run.state.state, "AWAITING_APPROVAL", getattr(run.state, "failure_reason", None))
        self.assertEqual(_schemas.errors("evidence_packet.schema.json", run.packet), [])
        self.assertTrue(verify_chain(run.journal.entries).ok)
        self.assertEqual(sum(1 for c in docker.commands if c[0] == "create"), len(run.executions))
        # the sealed truth never reached the sandbox or any journal entry
        blob = json.dumps(run.journal.entries) + json.dumps(docker.commands) + docker.stdin_seen.decode()
        for needle in ("exceptional_case_ids", "correct_resolution", "exception_types", "ground_truth"):
            self.assertNotIn(needle, blob)
        self.assertNotIn(KEY, blob)


if __name__ == "__main__":
    unittest.main()
