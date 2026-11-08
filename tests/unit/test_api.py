"""M5 API tests (RED first). In-process WSGI calls; no sockets, no live service. Reuses the orchestrator test doubles."""
import io
import json
import os
import shutil
import tempfile
import unittest
import urllib.parse

from tests.unit.test_broker import fixture
from tests.unit.test_orchestrator import (CASES, CODE, EVIDENCE, HAPPY, Env, FakeDataset, jr, critic_reply, decision_reply, paths_reply)

GENERIC = "15 integer answers in 1..6 required"
OP = "operator-token-for-tests-only"


def call(app, method, path, body=None, ip="10.0.0.1", headers=None, raw=None):
    q = ""
    if "?" in path:
        path, q = path.split("?", 1)
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else b"")
    env = {"REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": q, "wsgi.input": io.BytesIO(data),
           "CONTENT_LENGTH": str(len(data)), "CONTENT_TYPE": "application/json", "REMOTE_ADDR": ip, "SERVER_NAME": "x", "SERVER_PORT": "80"}
    for k, v in (headers or {}).items():
        env["HTTP_" + k.upper().replace("-", "_")] = v
    out = {}

    def sr(status, hdrs):
        out["status"], out["headers"] = int(status.split()[0]), {k.lower(): v for k, v in hdrs}
    chunks = b"".join(app(env, sr))
    try:
        parsed = json.loads(chunks.decode("utf-8")) if chunks else None
    except ValueError:
        parsed = None
    return out["status"], out["headers"], parsed if parsed is not None else chunks


class Fixture:
    def __init__(self, test, **cfg):
        from control.api import ApiConfig, App
        self.t = test
        self.env = Env(test)
        self.clock = [1000.0]
        self.recorded = os.path.join(self.env.tmp, "recorded")
        os.makedirs(self.recorded)
        self.static = os.path.join(self.env.tmp, "static")
        os.makedirs(self.static)
        with open(os.path.join(self.static, "index.html"), "w") as f:
            f.write("<html>ok</html>")
        with open(os.path.join(self.env.tmp, "secret.txt"), "w") as f:
            f.write("SECRET-OUTSIDE-STATIC")
        c = dict(public=True, operator_token=OP, per_ip_runs_per_hour=5, download_ttl_seconds=60, live_inference_allowed=lambda: True,
                 recorded_dir=self.recorded, static_dir=self.static)
        c.update(cfg)
        self.built = []

        def factory(run_id):
            self.built.append(run_id)
            return self.env.orch

        self.app = App(factory, FakeDataset(), ApiConfig(**c), now=lambda: self.clock[0])

    def full_run(self, ip="10.0.0.1"):
        s, _, b = call(self.app, "POST", "/api/v1/runs", {"dataset_id": "eo-recv-v1"}, ip=ip)
        assert s == 201, (s, b)
        rid = b["run_id"]
        s, _, b = call(self.app, "POST", f"/api/v1/runs/{rid}/intake", {"answers": dict.fromkeys(self.env.orch.question_ids, 3)}, ip=ip)
        assert s == 200, (s, b)
        s, _, b = call(self.app, "POST", f"/api/v1/runs/{rid}/start", {}, ip=ip)
        assert s == 202, (s, b)
        self.app.join(rid)
        return rid


class TestStatic(unittest.TestCase):
    def test_healthz(self):
        f = Fixture(self)
        s, h, b = call(f.app, "GET", "/healthz")
        self.assertEqual((s, b["ok"]), (200, True))

    def test_datasets_lists_exactly_one_and_no_upload_route_exists_AT_01(self):
        f = Fixture(self)
        s, _, b = call(f.app, "GET", "/api/v1/datasets")
        self.assertEqual((s, len(b["datasets"])), (200, 1))
        for method in ("POST", "PUT", "PATCH"):
            for path in ("/api/v1/datasets", "/api/v1/datasets/upload", "/api/v1/upload", "/upload"):
                with self.subTest(method=method, path=path):
                    st = call(f.app, method, path, {"x": 1})[0]
                    # the listing path exists for GET only, so a write there is 405; every other upload-like path must be 404
                    self.assertEqual(st, 405 if path == "/api/v1/datasets" else 404)

    def test_intake_lists_15_opaque_questions(self):
        f = Fixture(self)
        s, _, b = call(f.app, "GET", "/api/v1/intake")
        self.assertEqual(len(b["items"]), 15)
        self.assertEqual({k for q in b["items"] for k in q}, {"id", "text"})

    def test_static_serves_index_and_blocks_traversal(self):
        f = Fixture(self)
        s, _, b = call(f.app, "GET", "/")
        self.assertEqual(s, 200)
        for p in ("/../secret.txt", "/..%2fsecret.txt", "/%2e%2e/secret.txt", "/static/../../secret.txt"):
            with self.subTest(p):
                s, _, b = call(f.app, "GET", p)
                self.assertNotIn(b"SECRET-OUTSIDE-STATIC", b if isinstance(b, bytes) else json.dumps(b).encode())

    def test_unknown_route_and_wrong_method(self):
        f = Fixture(self)
        self.assertEqual(call(f.app, "GET", "/nope/never")[0] in (404, 200), True)  # 200 only via SPA fallback to index
        self.assertEqual(call(f.app, "DELETE", "/api/v1/runs")[0], 405)
        self.assertEqual(call(f.app, "GET", "/api/v1/runs/zz-no-run")[0], 404)

    def test_error_bodies_leak_no_paths_or_tracebacks(self):
        f = Fixture(self)
        for args in [("GET", "/api/v1/runs/zz-no-run"), ("POST", "/api/v1/runs", None, "10.0.0.1", None, b"{not json")]:
            s, _, b = call(f.app, args[0], args[1], *args[2:]) if len(args) == 2 else call(f.app, args[0], args[1], ip=args[3], raw=args[5])
            text = json.dumps(b)
            self.assertNotIn("Traceback", text)
            self.assertNotIn(os.sep + "workspace", text)

    def test_oversized_body_is_413(self):
        f = Fixture(self)
        self.assertEqual(call(f.app, "POST", "/api/v1/runs", raw=b"x" * 70000)[0], 413)


class TestFlow(unittest.TestCase):
    def test_full_flow_through_approval_and_download(self):
        from broker import _schemas
        f = Fixture(self)
        rid = f.full_run()
        s, _, b = call(f.app, "GET", f"/api/v1/runs/{rid}")
        self.assertEqual(b["state"], "AWAITING_APPROVAL")
        s, _, pkt = call(f.app, "GET", f"/api/v1/runs/{rid}/packet")
        self.assertEqual(_schemas.errors("evidence_packet.schema.json", pkt), [])
        self.assertEqual(call(f.app, "POST", f"/api/v1/runs/{rid}/approve", {"action": "confirm"})[0], 409)
        self.assertEqual(call(f.app, "POST", f"/api/v1/runs/{rid}/approve", {"action": "view"})[0], 200)
        s, _, b = call(f.app, "POST", f"/api/v1/runs/{rid}/approve", {"action": "confirm"})
        self.assertEqual(s, 200)
        self.assertIs(b["packet"]["approval_gate"]["external_action_taken"], False)
        s, _, link = call(f.app, "POST", f"/api/v1/runs/{rid}/download-link", {})
        self.assertEqual(s, 200)
        tok = link["url"].rsplit("/", 1)[-1]
        self.assertGreaterEqual(len(tok), 32)
        for part in ("packet", "journal", "events", "rule"):
            self.assertEqual(call(f.app, "GET", f"{link['url']}/{part}")[0], 200, part)
        s, _, jr_ = call(f.app, "GET", f"/api/v1/runs/{rid}/journal")
        self.assertIn("packet_downloaded", [e["kind"] for e in jr_["entries"]])

    def test_repeated_view_is_200_same_packet_and_repeated_confirm_is_409_no_effect(self):
        f = Fixture(self)
        rid = f.full_run()
        a = call(f.app, "POST", f"/api/v1/runs/{rid}/approve", {"action": "view"})
        b = call(f.app, "POST", f"/api/v1/runs/{rid}/approve", {"action": "view"})
        self.assertEqual((a[0], b[0]), (200, 200))
        self.assertEqual(a[2]["packet"]["packet_sha256"], b[2]["packet"]["packet_sha256"])
        c1 = call(f.app, "POST", f"/api/v1/runs/{rid}/approve", {"action": "confirm"})
        n = len(call(f.app, "GET", f"/api/v1/runs/{rid}/journal")[2]["entries"])
        c2 = call(f.app, "POST", f"/api/v1/runs/{rid}/approve", {"action": "confirm"})
        self.assertEqual((c1[0], c2[0]), (200, 409))
        self.assertEqual(len(call(f.app, "GET", f"/api/v1/runs/{rid}/journal")[2]["entries"]), n)
        self.assertEqual(call(f.app, "GET", f"/api/v1/runs/{rid}/packet")[2]["packet_sha256"], c1[2]["packet"]["packet_sha256"])

    def test_oversized_intake_is_413_before_any_422_and_unknown_run_is_404_first(self):
        f = Fixture(self)
        rid = call(f.app, "POST", "/api/v1/runs", {"dataset_id": "eo-recv-v1"})[2]["run_id"]
        self.assertEqual(call(f.app, "POST", f"/api/v1/runs/{rid}/intake", raw=b"{" + b"x" * 70000)[0], 413)
        self.assertEqual(call(f.app, "POST", "/api/v1/runs/zz-nope/intake", raw=b"x" * 70000)[0], 404)

    def test_link_issued_before_confirm_serves_the_confirmed_packet_and_a_coherent_longer_journal(self):
        f = Fixture(self)
        rid = f.full_run()
        call(f.app, "POST", f"/api/v1/runs/{rid}/approve", {"action": "view"})
        link = call(f.app, "POST", f"/api/v1/runs/{rid}/download-link", {})[2]
        self.assertEqual(set(link["parts"]), {"packet", "journal", "events", "rule"})
        self.assertTrue(all(u.startswith(link["url"] + "/") for u in link["parts"].values()))
        self.assertEqual(call(f.app, "GET", link["url"])[0], 404)           # the url is a base, not a file
        pending = call(f.app, "GET", link["parts"]["packet"])[2]
        self.assertEqual(pending["approval_gate"]["status"], "PENDING")
        call(f.app, "POST", f"/api/v1/runs/{rid}/approve", {"action": "confirm"})
        pkt = call(f.app, "GET", link["parts"]["packet"])[2]
        self.assertEqual(pkt["approval_gate"]["status"], "VIEWED_CONFIRMED")
        _, _, text = call(f.app, "GET", link["parts"]["journal"])
        lines = [json.loads(l) for l in text.decode().splitlines()]
        n = pkt["journal"]["entries"]
        self.assertGreater(len(lines), n)
        self.assertEqual(lines[n - 1]["entry_sha256"], pkt["journal"]["head_sha256"])
        self.assertEqual((lines[n]["kind"], lines[n]["data"]["packet_sha256"]), ("approval", pkt["packet_sha256"]))

    def test_intake_errors_are_identical_whatever_was_wrong_AT_G5_3(self):
        f = Fixture(self)
        rid = call(f.app, "POST", "/api/v1/runs", {"dataset_id": "eo-recv-v1"})[2]["run_id"]
        ids = f.env.orch.question_ids
        bad = [{"answers": dict.fromkeys(ids[:14], 3)}, {"answers": dict.fromkeys(ids, 7)}, {"answers": dict.fromkeys(ids, "3")},
               {"answers": {"x": 1}}, {"nope": 1}, {"answers": list(range(15))}]
        seen = set()
        for b in bad:
            s, _, body = call(f.app, "POST", f"/api/v1/runs/{rid}/intake", b)
            self.assertEqual(s, 422)
            seen.add(json.dumps(body, sort_keys=True))
        s, _, body = call(f.app, "POST", f"/api/v1/runs/{rid}/intake", raw=b"{broken")
        seen.add(json.dumps(body, sort_keys=True))
        self.assertEqual(seen, {json.dumps({"error": GENERIC}, sort_keys=True)})

    def test_scan_response_is_the_fixed_public_shape_and_never_echoes_answers_AT_G5_1(self):
        from broker import _schemas
        f = Fixture(self)
        rid = call(f.app, "POST", "/api/v1/runs", {"dataset_id": "eo-recv-v1"})[2]["run_id"]
        s, _, b = call(f.app, "POST", f"/api/v1/runs/{rid}/intake", {"answers": dict.fromkeys(f.env.orch.question_ids, 3)})
        self.assertEqual(_schemas.errors("scan_result.schema.json", b), [])
        self.assertNotIn("answers", b)

    def test_unknown_dataset_is_404_and_start_before_intake_is_409(self):
        f = Fixture(self)
        self.assertEqual(call(f.app, "POST", "/api/v1/runs", {"dataset_id": "other"})[0], 404)
        rid = call(f.app, "POST", "/api/v1/runs", {"dataset_id": "eo-recv-v1"})[2]["run_id"]
        self.assertEqual(call(f.app, "POST", f"/api/v1/runs/{rid}/start", {})[0], 409)

    def test_failed_run_reports_state_and_incomplete_packet(self):
        from tests.fakes.fake_vultr import Reply
        f = Fixture(self)
        f.env.server.queue.clear()
        f.env.server.script(Reply(content="x", model="other"))
        rid = f.full_run()
        s, _, b = call(f.app, "GET", f"/api/v1/runs/{rid}")
        self.assertEqual(b["state"], "FAILED_CLOSED")
        s, _, pkt = call(f.app, "GET", f"/api/v1/runs/{rid}/packet")
        self.assertEqual(pkt["packet_status"], "INCOMPLETE")
        self.assertEqual(call(f.app, "POST", f"/api/v1/runs/{rid}/approve", {"action": "view"})[0], 409)


class TestLimitsAndGuards(unittest.TestCase):
    def test_public_mode_with_unset_per_ip_limit_refuses_run_creation(self):
        f = Fixture(self, per_ip_runs_per_hour=None)
        s, _, b = call(f.app, "POST", "/api/v1/runs", {"dataset_id": "eo-recv-v1"})
        self.assertEqual(s, 503)
        self.assertEqual(f.built, [])

    def test_operator_token_bypasses_unset_limit_in_operator_calls_only(self):
        f = Fixture(self, per_ip_runs_per_hour=None)
        s, _, b = call(f.app, "POST", "/api/v1/runs", {"dataset_id": "eo-recv-v1"}, headers={"X-Operator-Token": OP})
        self.assertEqual(s, 201)
        s, _, b = call(f.app, "POST", "/api/v1/runs", {"dataset_id": "eo-recv-v1"}, headers={"X-Operator-Token": "wrong"})
        self.assertEqual(s, 503)

    def test_per_ip_hourly_limit_and_window(self):
        f = Fixture(self, per_ip_runs_per_hour=2)
        self.assertEqual(f.app._limiter.allow("a", False), True)
        self.assertEqual(f.app._limiter.allow("a", False), True)
        self.assertEqual(f.app._limiter.allow("a", False), False)
        self.assertEqual(f.app._limiter.allow("b", False), True)
        f.clock[0] += 3601
        self.assertEqual(f.app._limiter.allow("a", False), True)

    def test_limiter_with_unset_limit_refuses_everyone_but_the_operator(self):
        from control.api import Limiter
        lim = Limiter(None, lambda: 0.0)
        self.assertFalse(lim.allow("a", False))
        self.assertTrue(lim.allow("a", True))

    def test_429_response_over_http_surface(self):
        f = Fixture(self, per_ip_runs_per_hour=1)
        self.assertEqual(call(f.app, "POST", "/api/v1/runs", {"dataset_id": "eo-recv-v1"}, ip="9.9.9.9")[0], 201)
        self.assertEqual(call(f.app, "POST", "/api/v1/runs", {"dataset_id": "eo-recv-v1"}, ip="9.9.9.9")[0], 429)

    def test_forwarded_header_ignored_unless_proxy_is_trusted(self):
        f = Fixture(self, per_ip_runs_per_hour=1)
        h = lambda ip: {"X-Forwarded-For": ip}
        self.assertEqual(call(f.app, "POST", "/api/v1/runs", {"dataset_id": "eo-recv-v1"}, ip="9.9.9.9", headers=h("1.1.1.1"))[0], 201)
        self.assertEqual(call(f.app, "POST", "/api/v1/runs", {"dataset_id": "eo-recv-v1"}, ip="9.9.9.9", headers=h("2.2.2.2"))[0], 429)

    def test_live_inference_not_allowed_serves_recorded_run_never_a_fabricated_one(self):
        f = Fixture(self, live_inference_allowed=lambda: False)
        rid = call(f.app, "POST", "/api/v1/runs", {"dataset_id": "eo-recv-v1"})[2]["run_id"]
        call(f.app, "POST", f"/api/v1/runs/{rid}/intake", {"answers": dict.fromkeys(f.env.orch.question_ids, 3)})
        s, _, b = call(f.app, "POST", f"/api/v1/runs/{rid}/start", {})
        self.assertEqual(s, 409)
        self.assertEqual(b["mode"], "recorded")
        self.assertEqual(b["recorded_runs"], [])          # nothing recorded yet: we say so, we invent nothing
        self.assertEqual(f.env.runner.calls, [])
        self.assertEqual(f.env.server.requests, [])

    def test_recorded_run_is_served_only_if_it_validates(self):
        from broker import _schemas
        f = Fixture(self, live_inference_allowed=lambda: False)
        from control import packet as pk
        good = fixture("evidence_packet__valid.json")
        good["packet_sha256"] = pk.packet_hash(good)       # the frozen fixture's own hash is a placeholder; seal it properly
        tampered = dict(good, run_id="run-999")             # content changed, hash left as is
        os.makedirs(os.path.join(f.recorded, "rec-hash"))
        with open(os.path.join(f.recorded, "rec-hash", "packet.json"), "w") as fh:
            json.dump(tampered, fh)
        self.assertEqual(call(f.app, "GET", "/api/v1/recorded-runs/rec-hash")[0], 404)
        os.makedirs(os.path.join(f.recorded, "rec-001"))
        with open(os.path.join(f.recorded, "rec-001", "packet.json"), "w") as fh:
            json.dump(good, fh)
        with open(os.path.join(f.recorded, "rec-001", "meta.json"), "w") as fh:
            json.dump({"recorded_run_id": "rec-001", "recorded_on": "2026-11-06"}, fh)
        os.makedirs(os.path.join(f.recorded, "rec-bad"))
        with open(os.path.join(f.recorded, "rec-bad", "packet.json"), "w") as fh:
            json.dump({"label": "SYNTHETIC"}, fh)
        s, _, b = call(f.app, "GET", "/api/v1/recorded-runs")
        self.assertEqual([r["recorded_run_id"] for r in b["recorded_runs"]], ["rec-001"])
        s, _, b = call(f.app, "GET", "/api/v1/recorded-runs/rec-001")
        self.assertEqual((s, b["recorded"]), (200, True))
        self.assertEqual(call(f.app, "GET", "/api/v1/recorded-runs/rec-bad")[0], 404)
        self.assertEqual(call(f.app, "GET", "/api/v1/recorded-runs/..%2f..%2fx")[0], 404)

    def test_download_disabled_while_ttl_unset_and_expires_when_set(self):
        f = Fixture(self, download_ttl_seconds=None)
        rid = f.full_run()
        call(f.app, "POST", f"/api/v1/runs/{rid}/approve", {"action": "view"})
        self.assertEqual(call(f.app, "POST", f"/api/v1/runs/{rid}/download-link", {})[0], 503)
        g = Fixture(self, download_ttl_seconds=60)
        rid = g.full_run()
        call(g.app, "POST", f"/api/v1/runs/{rid}/approve", {"action": "view"})
        s, _, link = call(g.app, "POST", f"/api/v1/runs/{rid}/download-link", {})
        self.assertEqual(call(g.app, "GET", link["url"] + "/packet")[0], 200)
        g.clock[0] += 61
        self.assertEqual(call(g.app, "GET", link["url"] + "/packet")[0], 410)
        self.assertEqual(call(g.app, "GET", "/api/v1/download/" + "a" * 43 + "/packet")[0], 404)

    def test_download_link_requires_the_packet_to_have_been_viewed(self):
        f = Fixture(self)
        rid = f.full_run()
        self.assertEqual(call(f.app, "POST", f"/api/v1/runs/{rid}/download-link", {})[0], 409)

    def test_stress_is_never_public_and_not_built_here(self):
        f = Fixture(self)
        self.assertEqual(call(f.app, "POST", "/api/v1/operator/stress", {})[0], 404)
        self.assertEqual(call(f.app, "POST", "/api/v1/operator/stress", {}, headers={"X-Operator-Token": "wrong"})[0], 404)
        self.assertEqual(call(f.app, "POST", "/api/v1/operator/stress", {}, headers={"X-Operator-Token": OP})[0], 501)

    def test_security_headers_present(self):
        f = Fixture(self)
        _, h, _ = call(f.app, "GET", "/healthz")
        self.assertEqual(h["x-content-type-options"], "nosniff")
        self.assertIn("no-store", h["cache-control"])


class TestConfig(unittest.TestCase):
    def test_env_parsing_unset_and_bad_values(self):
        from control.api import ConfigError, config_from_env
        c = config_from_env({"DR_RATE_LIMIT_RUNS_PER_IP_PER_HOUR": "UNSET", "DR_OPERATOR_TOKEN": ""})
        self.assertIsNone(c.per_ip_runs_per_hour)
        self.assertIsNone(c.operator_token)
        c = config_from_env({"DR_RATE_LIMIT_RUNS_PER_IP_PER_HOUR": "3", "DR_OPERATOR_TOKEN": "t" * 32})
        self.assertEqual(c.per_ip_runs_per_hour, 3)
        for bad in ("0", "-1", "abc", "1.5", ""):
            with self.subTest(bad):
                with self.assertRaises(ConfigError):
                    config_from_env({"DR_RATE_LIMIT_RUNS_PER_IP_PER_HOUR": bad})

    def test_runs_dir_is_read_from_env_and_reaches_every_orchestrator_RUNS_DIR(self):
        from control.api import config_from_env
        from control.compose import make_factory
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        cfg = config_from_env({"DR_RUNS_DIR": d})
        self.assertEqual(cfg.runs_dir, d)
        built = []
        f = make_factory(cfg, lambda **kw: built.append(kw) or object(), broker_factory=lambda: "B", runner="R", dataset="D", rule_path="P",
                         seed=1, assurance_tier="T0")
        f("run-aaa")
        self.assertEqual(built[0]["runs_dir"], d)
        self.assertEqual((built[0]["broker"], built[0]["runner"], built[0]["dataset"]), ("B", "R", "D"))

    def test_public_mode_without_runs_dir_refuses_to_compose_but_unset_env_means_none(self):
        from control.api import ApiConfig, ConfigError, config_from_env
        from control.compose import make_factory
        self.assertIsNone(config_from_env({}).runs_dir)
        self.assertIsNone(config_from_env({"DR_RUNS_DIR": ""}).runs_dir)
        with self.assertRaises(ConfigError):
            make_factory(ApiConfig(public=True), lambda **kw: None, broker_factory=lambda: "B", runner="R", dataset="D", rule_path="P", seed=1)
        make_factory(ApiConfig(public=False), lambda **kw: None, broker_factory=lambda: "B", runner="R", dataset="D", rule_path="P", seed=1)

    def test_short_operator_token_is_refused(self):
        from control.api import ConfigError, config_from_env
        with self.assertRaises(ConfigError):
            config_from_env({"DR_OPERATOR_TOKEN": "short"})


if __name__ == "__main__":
    unittest.main()
