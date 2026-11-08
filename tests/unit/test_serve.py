"""F-M7-03: the real launcher `control.serve`. It builds the M5 app from the process environment (names in .env.example), refuses to start on any
unresolved setting, and binds loopback only. Tests use a plain dict for the environment, a fake key, M4's FakeDocker and a temp directory.
Nothing here starts Docker, opens a socket to a service or reads a real key."""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

from sandbox.runner import DockerExecutor
from sandbox.tests.test_runner import FakeDocker
from tests.unit.test_broker import KEY, pinned

LOCK = {"docker_engine_version": "fixture-only", "image_digest": "sha256:" + "a" * 64, "base_image": "python:3.12-slim@sha256:" + "b" * 64}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.models = os.path.join(self.tmp, "models.json")
        with open(self.models, "w", encoding="utf-8") as f:
            json.dump(pinned(), f)
        self.lock = os.path.join(self.tmp, "docker_image.lock")
        with open(self.lock, "w", encoding="utf-8") as f:
            json.dump(LOCK, f)
        self.runs = os.path.join(self.tmp, "runs")
        os.mkdir(self.runs)

    def env(self, **over):
        e = {"VULTR_INFERENCE_API_KEY": KEY, "DR_MODELS_FILE": self.models, "DR_DATASET_SEED": "20261103", "DR_RUNS_DIR": self.runs,
             "DR_IMAGE_LOCK": self.lock, "DR_OPERATION_SECONDS": "60", "DR_ALLOW_PROVISIONAL_DATASET": "1", "DR_DOCKER_HOST": "",
             "DR_RUN_TOKEN_CAP": "UNSET", "DR_DAILY_TOKEN_BUDGET": "UNSET", "DR_RATE_LIMIT_RUNS_PER_IP_PER_HOUR": "UNSET",
             "DR_PACKET_LINK_TTL_SECONDS": "UNSET"}
        e.update(over)
        return {k: v for k, v in e.items() if v is not None}

    def build(self, **over):
        from control.serve import build_app
        executor = over.pop("executor", FakeDocker())
        return build_app(self.env(**over), executor=executor)


class TestBuildApp(Base):
    def test_builds_a_wsgi_app_that_answers_healthz(self):
        app = self.build()
        got = {}
        body = b"".join(app({"REQUEST_METHOD": "GET", "PATH_INFO": "/healthz", "REMOTE_ADDR": "127.0.0.1", "wsgi.input": io.BytesIO(b"")},
                            lambda status, headers: got.setdefault("status", status)))
        self.assertTrue(got["status"].startswith("200"), got)
        self.assertTrue(body)

    def test_public_mode_never_allows_live_inference(self):
        app = self.build()
        self.assertTrue(app.cfg.public)
        self.assertFalse(app.cfg.live_inference_allowed())

    def test_missing_key_refuses_without_naming_a_value(self):
        from control.api import ConfigError
        with self.assertRaises(ConfigError) as cm:
            self.build(VULTR_INFERENCE_API_KEY=None)
        self.assertNotIn(KEY, str(cm.exception))

    def test_blank_key_refuses(self):
        from control.api import ConfigError
        with self.assertRaises(ConfigError):
            self.build(VULTR_INFERENCE_API_KEY="   ")

    def test_template_models_file_refuses_to_start(self):
        from control.api import ConfigError
        template = os.path.join(self.tmp, "models.yaml")
        shutil.copy(os.path.join(os.path.dirname(__file__), "..", "..", "models.example.yaml"), template)
        with self.assertRaises(ConfigError) as cm:
            self.build(DR_MODELS_FILE=template)
        self.assertNotIn(KEY, str(cm.exception))

    def test_missing_or_unreadable_models_file_refuses(self):
        from control.api import ConfigError
        with self.assertRaises(ConfigError):
            self.build(DR_MODELS_FILE=None)
        with self.assertRaises(ConfigError):
            self.build(DR_MODELS_FILE=os.path.join(self.tmp, "absent.json"))

    def test_runs_directory_is_required_in_public_mode(self):
        from control.api import ConfigError
        with self.assertRaises(ConfigError):
            self.build(DR_RUNS_DIR=None)

    def test_provisional_dataset_needs_an_explicit_opt_in(self):
        from control.api import ConfigError
        for v in (None, "", "0", "yes"):
            with self.assertRaises(ConfigError, msg=repr(v)):
                self.build(DR_ALLOW_PROVISIONAL_DATASET=v)
        self.build(DR_ALLOW_PROVISIONAL_DATASET="1")

    def test_dataset_seed_must_be_an_integer(self):
        from control.api import ConfigError
        for v in (None, "", "abc", "-1", "1.5"):
            with self.assertRaises(ConfigError, msg=repr(v)):
                self.build(DR_DATASET_SEED=v)

    def test_operation_seconds_has_no_default(self):
        from control.api import ConfigError
        for v in (None, "", "0", "-5", "abc", "UNSET", "nan", "inf"):
            with self.assertRaises(ConfigError, msg=repr(v)):
                self.build(DR_OPERATION_SECONDS=v)

    def test_image_lock_must_be_valid(self):
        from control.api import ConfigError
        bad = os.path.join(self.tmp, "bad.lock")
        with open(bad, "w", encoding="utf-8") as f:
            json.dump(dict(LOCK, docker_engine_version="<<G4_DOCKER_VERSION>>"), f)
        with self.assertRaises(ConfigError):
            self.build(DR_IMAGE_LOCK=bad)
        with self.assertRaises(ConfigError):
            self.build(DR_IMAGE_LOCK=os.path.join(self.tmp, "absent.lock"))

    def test_default_lock_path_is_the_one_m4_reads(self):
        from control import serve
        self.assertTrue(str(serve.DEFAULT_LOCK).endswith("docker_image.lock"))
        self.assertEqual(serve.DEFAULT_LOCK.parent, serve.ROOT)

    def test_invalid_limit_settings_refuse(self):
        from control.api import ConfigError
        with self.assertRaises(ConfigError):
            self.build(DR_RATE_LIMIT_RUNS_PER_IP_PER_HOUR="many")

    def test_short_operator_token_refuses(self):
        from control.api import ConfigError
        with self.assertRaises(ConfigError):
            self.build(DR_OPERATOR_TOKEN="short")

    def test_key_is_not_in_the_app_repr_or_the_runner_repr(self):
        app = self.build()
        self.assertNotIn(KEY, repr(app))
        self.assertNotIn(KEY, repr(app.cfg))


class TestRunnerWiring(Base):
    def orch(self, **over):
        return self.build(**over)._factory("run-abc123")

    def test_the_real_runner_is_wired_with_the_key_scanner_not_fixture_mode(self):
        o = self.orch()
        self.assertEqual(o.runner.scan_mode, "configured")

    def test_local_docker_is_tier_t0_and_ssh_host_is_t1(self):
        from control.serve import build_app
        t0 = build_app(self.env(DR_DOCKER_HOST=""), executor=None)._factory("run-abc123")
        self.assertEqual(t0.tier, "T0")
        self.assertIsInstance(t0.runner._executor, DockerExecutor)
        self.assertEqual(t0.runner._executor.prefix, ["docker"])
        t1 = build_app(self.env(DR_DOCKER_HOST="ssh://runner@203.0.113.9"), executor=None)._factory("run-abc123")
        self.assertEqual(t1.tier, "T1")
        self.assertEqual(t1.runner._executor.prefix, ["docker", "--host", "ssh://runner@203.0.113.9"])

    def test_only_ssh_or_unix_docker_hosts_are_accepted(self):
        from control.api import ConfigError
        from control.serve import build_app
        for v in ("tcp://203.0.113.9:2375", "http://x", "runner@host", "ssh://", "ssh://x y"):
            with self.assertRaises(ConfigError, msg=v):
                build_app(self.env(DR_DOCKER_HOST=v), executor=None)

    def test_the_runner_carries_the_operator_deadline(self):
        o = self.orch(DR_OPERATION_SECONDS="45")
        self.assertEqual(o.runner._seconds, 45.0)

    def test_the_lock_path_reaches_m4_so_its_on_disk_check_applies(self):
        o = self.orch()
        self.assertEqual(str(o.runner._lock_path), self.lock)

    def test_the_journal_refuses_the_key_value(self):
        o = self.orch()
        self.assertIn(KEY, o.forbidden)

    def test_each_run_gets_its_own_broker_sharing_one_daily_budget(self):
        app = self.build()
        a, b = app._factory("run-aaaaaa"), app._factory("run-bbbbbb")
        self.assertIsNot(a.broker, b.broker)
        self.assertIs(a.broker._daily, b.broker._daily)


class TestMain(Base):
    def run_main(self, argv, **over):
        from control.serve import main
        out, err = io.StringIO(), io.StringIO()
        calls = []
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = main(argv, env=self.env(**over), executor=FakeDocker(), serve_fn=lambda app, port, host: calls.append((port, host)))
        return rc, out.getvalue(), err.getvalue(), calls

    def test_serves_on_loopback_with_the_given_port(self):
        rc, out, err, calls = self.run_main(["--port", "8000"])
        self.assertEqual((rc, calls), (0, [(8000, "127.0.0.1")]))
        self.assertNotIn(KEY, out + err)

    def test_port_is_required_and_numeric(self):
        for argv in ([], ["--port", "abc"], ["--port", "0"], ["--port", "70000"]):
            with self.assertRaises(SystemExit) as cm:
                self.run_main(argv)
            self.assertEqual(cm.exception.code, 2, argv)

    def test_refuses_a_non_loopback_host(self):
        for host in ("0.0.0.0", "203.0.113.9", "::"):
            rc, _, err, calls = self.run_main(["--port", "8000", "--host", host])
            self.assertEqual((rc, calls), (2, []), host)
            self.assertIn("loopback", err)

    def test_check_builds_everything_and_serves_nothing(self):
        rc, out, err, calls = self.run_main(["--check"])
        self.assertEqual((rc, calls), (0, []))
        self.assertIn("ok", out.lower())
        self.assertNotIn(KEY, out + err)

    def test_config_error_exits_2_with_a_value_free_message(self):
        rc, out, err, calls = self.run_main(["--port", "8000"], DR_OPERATION_SECONDS="abc", DR_OPERATOR_TOKEN="x" * 40)
        self.assertEqual((rc, calls), (2, []))
        self.assertIn("DR_OPERATION_SECONDS", err)
        self.assertNotIn("abc", err.replace("DR_OPERATION_SECONDS", ""))
        self.assertNotIn(KEY, out + err)
        self.assertNotIn("x" * 40, out + err)

    def test_unexpected_failure_does_not_print_a_traceback_with_values(self):
        from control import serve
        orig = serve.build_app
        serve.build_app = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom " + KEY))
        try:
            rc, out, err, calls = self.run_main(["--port", "8000"])
        finally:
            serve.build_app = orig
        self.assertEqual((rc, calls), (2, []))
        self.assertNotIn(KEY, out + err)

    def test_create_app_builds_from_the_process_environment(self):
        from control import serve
        saved = dict(os.environ)
        try:
            os.environ.update(self.env())
            app = serve.create_app(executor=FakeDocker())
        finally:
            os.environ.clear()
            os.environ.update(saved)
        self.assertTrue(callable(app))


TOKEN = "t" * 40


class TestOperatorMode(Base):
    """I-4: the first measured run needs live calls while the public limits are UNSET. `DR_OPERATOR_MODE=1` turns that on, and only together with
    an operator token and an UNSET per-IP limit, so the create gate (operator-only while the limit is UNSET) is what keeps live inference
    operator-only. Without the opt-in the launcher is public mode exactly as before."""

    def call(self, app, method, path, body=None, token=None):
        raw = json.dumps(body).encode() if body is not None else b""
        environ = {"REQUEST_METHOD": method, "PATH_INFO": path, "REMOTE_ADDR": "203.0.113.9", "wsgi.input": io.BytesIO(raw),
                   "CONTENT_LENGTH": str(len(raw)), "CONTENT_TYPE": "application/json"}
        if token:
            environ["HTTP_X_OPERATOR_TOKEN"] = token
        got = {}
        data = b"".join(app(environ, lambda status, headers: got.setdefault("status", status)))
        return int(got["status"].split()[0]), data

    def op(self, **over):
        return self.build(DR_OPERATOR_MODE="1", DR_OPERATOR_TOKEN=TOKEN, **over)

    def test_the_opt_in_turns_live_inference_on_and_keeps_public_create_rules(self):
        app = self.op()
        self.assertTrue(app.cfg.live_inference_allowed())
        self.assertTrue(app.cfg.public)

    def test_without_the_opt_in_live_inference_stays_off_even_with_a_token(self):
        for v in (None, "", "0"):
            app = self.build(DR_OPERATOR_MODE=v, DR_OPERATOR_TOKEN=TOKEN)
            self.assertFalse(app.cfg.live_inference_allowed(), repr(v))

    def test_anything_but_1_refuses(self):
        from control.api import ConfigError
        for v in ("true", "yes", "2", "on", " 1"):
            with self.assertRaises(ConfigError, msg=repr(v)):
                self.build(DR_OPERATOR_MODE=v, DR_OPERATOR_TOKEN=TOKEN)

    def test_operator_mode_needs_an_operator_token(self):
        from control.api import ConfigError
        with self.assertRaises(ConfigError) as cm:
            self.build(DR_OPERATOR_MODE="1")
        self.assertIn("DR_OPERATOR_TOKEN", str(cm.exception))
        self.assertNotIn(KEY, str(cm.exception))

    def test_operator_mode_refuses_when_the_public_create_gate_would_be_open(self):
        from control.api import ConfigError
        with self.assertRaises(ConfigError) as cm:
            self.op(DR_RATE_LIMIT_RUNS_PER_IP_PER_HOUR="5")
        self.assertIn("DR_RATE_LIMIT_RUNS_PER_IP_PER_HOUR", str(cm.exception))

    def test_the_broker_is_built_in_operator_mode_only_when_opted_in(self):
        from unittest import mock
        from control import broker_factory
        seen = []
        real = broker_factory.make_broker_factory

        def spy(env=None, **kw):
            seen.append(kw.get("public"))
            return real(env, **kw)
        with mock.patch.object(broker_factory, "make_broker_factory", spy):
            self.build()
            self.op()
        self.assertEqual(seen, [True, False])

    def test_the_public_cannot_create_a_run_in_operator_mode(self):
        app = self.op()
        body = {"dataset_id": app._dataset.dataset_id}
        for token in (None, "wrong" * 10, ""):
            status, data = self.call(app, "POST", "/api/v1/runs", body, token=token)
            self.assertEqual(status, 503, (token, data))
        self.assertEqual(app._runs, {})

    def test_the_operator_can_create_a_run_in_operator_mode(self):
        app = self.op()
        status, data = self.call(app, "POST", "/api/v1/runs", {"dataset_id": app._dataset.dataset_id}, token=TOKEN)
        self.assertEqual(status, 201, data)
        self.assertNotIn(TOKEN.encode(), data)

    def test_check_names_the_mode_and_prints_no_secret(self):
        from control.serve import main
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = main(["--check"], env=self.env(DR_OPERATOR_MODE="1", DR_OPERATOR_TOKEN=TOKEN), executor=FakeDocker())
        self.assertEqual(rc, 0)
        self.assertIn("operator mode", out.getvalue())
        self.assertNotIn(KEY, out.getvalue() + err.getvalue())
        self.assertNotIn(TOKEN, out.getvalue() + err.getvalue())


class TestServerClass(unittest.TestCase):
    """Baseline run (T-022): with the stdlib default listen backlog of 5, 20 concurrent clients saw a stall of about 1.24 s (a SYN retransmit);
    with 128 the worst case was about 12 ms. AT-18 bounds the healthz gap at 1000 ms, so the backlog is raised. 128 is the conventional socket
    value, not a product limit; the kernel caps it at net.core.somaxconn."""

    def test_listen_backlog_is_above_the_stdlib_default(self):
        from control.api import _Threaded
        self.assertGreaterEqual(_Threaded.request_queue_size, 128)


if __name__ == "__main__":
    unittest.main()
