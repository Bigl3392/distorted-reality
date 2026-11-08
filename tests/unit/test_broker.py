"""M3 broker unit tests (RED first). Stdlib unittest. Schemas are loaded from ../schemas (AT-C2: no copies).

Config values used here (temperature / max_tokens in models) come from the frozen fixture
schemas/fixtures/models__valid_pinned_fixture_values.json. They are SHAPE-TEST values, not configuration.
"""
import copy
import json
import os
import re
import unittest

from tests.fakes.fake_vultr import FakeVultr, Reply

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIX = os.path.join(ROOT, "schemas", "fixtures")
KEY = "test-key-NOT-A-REAL-SECRET-0123456789"


def fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


def pinned():
    return fixture("models__valid_pinned_fixture_values.json")


class TestModelsLoading(unittest.TestCase):
    def test_pinned_fixture_loads(self):
        from broker.models import load_models
        m = load_models(pinned())
        self.assertEqual(m.role("critic").model_id, "deepseek-v4.1-flash-1017")
        self.assertEqual(m.base_url, "https://api.vultrinference.com/v1")

    def test_template_with_unset_values_refuses_to_start(self):
        from broker.models import ModelsError, load_models
        with self.assertRaises(ModelsError):
            load_models(fixture("models__valid_template.json"))

    def test_each_invalid_fixture_refuses(self):
        from broker.models import ModelsError, load_models
        for name in sorted(os.listdir(FIX)):
            if name.startswith("models__INVALID"):
                with self.subTest(name):
                    with self.assertRaises(ModelsError):
                        load_models(fixture(name))

    def test_critic_and_decision_ids_must_differ_from_path(self):
        from broker.models import ModelsError, load_models
        d = pinned()
        d["roles"]["critic"]["model_id"] = d["roles"]["path"]["model_id"]
        with self.assertRaises(ModelsError):
            load_models(d)
        d = pinned()
        d["roles"]["decision"]["model_id"] = d["roles"]["path"]["model_id"]
        with self.assertRaises(ModelsError):
            load_models(d)

    def test_unknown_role_lookup_refused(self):
        from broker.models import ModelsError, load_models
        with self.assertRaises(ModelsError):
            load_models(pinned()).role("nope")

    def test_guard_is_off_by_default_and_refused_when_disabled(self):
        from broker.models import ModelsError, load_models
        m = load_models(pinned())
        self.assertFalse(m.guard_enabled)
        with self.assertRaises(ModelsError):
            m.role("guard")


class TestLimits(unittest.TestCase):
    def test_env_unset_means_none(self):
        from broker.limits import limits_from_env
        lim = limits_from_env({"DR_RUN_TOKEN_CAP": "UNSET", "DR_DAILY_TOKEN_BUDGET": "UNSET", "DR_RATE_LIMIT_RUNS_PER_IP_PER_HOUR": "UNSET"})
        self.assertIsNone(lim.run_token_cap)
        self.assertIsNone(lim.daily_token_budget)
        self.assertIsNone(lim.runs_per_ip_per_hour)
        self.assertFalse(lim.fully_set)

    def test_all_three_limits_are_required_for_fully_set_AT_L2(self):
        from broker.limits import Limits, limits_from_env
        self.assertFalse(Limits(5, 5, None).fully_set)
        self.assertFalse(Limits(5, None, 5).fully_set)
        self.assertFalse(Limits(None, 5, 5).fully_set)
        self.assertTrue(Limits(5, 5, 5).fully_set)
        lim = limits_from_env({"DR_RUN_TOKEN_CAP": "3", "DR_DAILY_TOKEN_BUDGET": "4", "DR_RATE_LIMIT_RUNS_PER_IP_PER_HOUR": "5"})
        self.assertEqual((lim.run_token_cap, lim.daily_token_budget, lim.runs_per_ip_per_hour), (3, 4, 5))

    def test_approved_record_carries_the_third_value(self):
        from broker.limits import limits_from_record
        rec = fixture("limits_record__valid_ldr_approved_fixture.json")
        self.assertEqual(limits_from_record(rec).runs_per_ip_per_hour, rec["proposed"]["runs_per_ip_per_hour"])

    def test_env_garbage_rejected(self):
        from broker.limits import LimitsError, limits_from_env
        for bad in ("0", "-5", "abc", "1.5", ""):
            with self.subTest(bad):
                with self.assertRaises(LimitsError):
                    limits_from_env({"DR_RUN_TOKEN_CAP": bad, "DR_DAILY_TOKEN_BUDGET": "UNSET"})

    def test_record_must_be_ldr_approved(self):
        from broker.limits import LimitsError, limits_from_record
        with self.assertRaises(LimitsError):
            limits_from_record(fixture("limits_record__valid_fixture.json"))
        lim = limits_from_record(fixture("limits_record__valid_ldr_approved_fixture.json"))
        self.assertTrue(lim.fully_set)

    def test_invalid_record_fixtures_rejected(self):
        from broker.limits import LimitsError, limits_from_record
        for name in sorted(os.listdir(FIX)):
            if name.startswith("limits_record__INVALID"):
                with self.subTest(name):
                    with self.assertRaises(LimitsError):
                        limits_from_record(fixture(name))


def make_client(server, limits=None, public=False, daily=None):
    from broker.client import BrokerClient, UrllibTransport
    from broker.limits import DailyBudget, Limits
    from broker.models import load_models
    return BrokerClient(
        models=load_models(pinned()),
        api_key=KEY,
        limits=limits or Limits(None, None),
        daily=daily or DailyBudget(),
        public=public,
        transport=UrllibTransport(server.base_url),
        clock=lambda: "2026-11-05T15:00:00Z",
    )


class TestBrokerCalls(unittest.TestCase):
    def test_success_sends_pinned_model_and_returns_record(self):
        with FakeVultr() as s:
            s.script(Reply(content='{"ok":1}', prompt_tokens=11, completion_tokens=7))
            c = make_client(s)
            r = c.call("evidence", [{"role": "user", "content": "hi"}])
        self.assertEqual(r.text, '{"ok":1}')
        sent = s.requests[0]
        self.assertEqual(sent.path, "/v1/chat/completions")
        self.assertEqual(sent.body["model"], "mimo-v2.6-flash")
        self.assertEqual(sent.headers["authorization"], "Bearer " + KEY)
        rec = r.record
        self.assertTrue(rec["model_match"])
        self.assertEqual((rec["tokens_in"], rec["tokens_out"]), (11, 7))
        self.assertRegex(rec["prompt_sha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(rec["response_sha256"], r"^[a-f0-9]{64}$")

    def test_record_fits_council_run_agent_call_schema(self):
        from jsonschema import Draft202012Validator
        with open(os.path.join(ROOT, "schemas", "council_run.schema.json"), encoding="utf-8") as f:
            schema = json.load(f)
        item = schema["properties"]["agent_calls"]["items"]
        with FakeVultr() as s:
            s.script(Reply())
            r = make_client(s).call("evidence", [{"role": "user", "content": "hi"}])
        errs = list(Draft202012Validator(item, format_checker=Draft202012Validator.FORMAT_CHECKER).iter_errors(r.record))
        self.assertEqual(errs, [])

    def test_model_mismatch_fails_closed_AT12(self):
        from broker.client import ModelMismatch
        with FakeVultr() as s:
            s.script(Reply(model="deepseek-v4.1-flash"), Reply())
            c = make_client(s)
            with self.assertRaises(ModelMismatch) as cm:
                c.call("critic", [{"role": "user", "content": "x"}])
            self.assertFalse(cm.exception.record["model_match"])
            self.assertEqual(cm.exception.record["response_model"], "deepseek-v4.1-flash")
            self.assertEqual(cm.exception.record["requested_model"], "deepseek-v4.1-flash-1017")
            # the run is failed closed: nothing more goes out
            n = len(s.requests)
            with self.assertRaises(ModelMismatch):
                c.call("evidence", [{"role": "user", "content": "y"}])
            self.assertEqual(len(s.requests), n)

    def test_missing_response_model_is_a_mismatch(self):
        from broker.client import ModelMismatch
        with FakeVultr() as s:
            s.script(Reply(model=""))
            with self.assertRaises(ModelMismatch):
                make_client(s).call("evidence", [{"role": "user", "content": "x"}])

    def test_missing_usage_fails_closed(self):
        from broker.client import BrokerError
        with FakeVultr() as s:
            s.script(Reply(omit_usage=True))
            with self.assertRaises(BrokerError):
                make_client(s).call("evidence", [{"role": "user", "content": "x"}])

    def test_http_error_fails_closed_without_retry(self):
        from broker.client import BrokerError
        with FakeVultr() as s:
            s.script(Reply(status=503, raw_body="busy"), Reply())
            with self.assertRaises(BrokerError):
                make_client(s).call("evidence", [{"role": "user", "content": "x"}])
            self.assertEqual(len(s.requests), 1)

    def test_key_is_redacted_from_errors(self):
        from broker.client import BrokerError
        with FakeVultr() as s:
            s.script(Reply(status=401, raw_body="bad credential Bearer " + KEY + " rejected"))
            with self.assertRaises(BrokerError) as cm:
                make_client(s).call("evidence", [{"role": "user", "content": "x"}])
        self.assertNotIn(KEY, str(cm.exception))
        self.assertNotIn(KEY, repr(cm.exception))

    def test_bare_key_without_bearer_prefix_is_redacted_too(self):
        from broker.client import BrokerError
        with FakeVultr() as s:
            s.script(Reply(status=400, raw_body='{"error":"invalid key ' + KEY + '"}'))
            with self.assertRaises(BrokerError) as cm:
                make_client(s).call("evidence", [{"role": "user", "content": "x"}])
        self.assertNotIn(KEY, str(cm.exception))
        self.assertIn("[REDACTED]", str(cm.exception))

    def test_key_is_not_in_client_repr_or_log(self):
        with FakeVultr() as s:
            s.script(Reply())
            c = make_client(s)
            c.call("evidence", [{"role": "user", "content": "x"}])
            self.assertNotIn(KEY, repr(c))
            self.assertNotIn(KEY, json.dumps(c.log))

    def test_unknown_or_disabled_role_never_calls_out(self):
        from broker.models import ModelsError
        with FakeVultr() as s:
            c = make_client(s)
            for role in ("nope", "guard"):
                with self.assertRaises(ModelsError):
                    c.call(role, [{"role": "user", "content": "x"}])
            self.assertEqual(s.requests, [])


class TestBudgets(unittest.TestCase):
    def test_public_mode_with_unset_limits_refuses_before_any_request_ATL2(self):
        from broker.client import LiveInferenceRefused
        with FakeVultr() as s:
            c = make_client(s, public=True)
            with self.assertRaises(LiveInferenceRefused):
                c.call("evidence", [{"role": "user", "content": "x"}])
            self.assertEqual(s.requests, [])

    def test_operator_mode_with_unset_limits_may_call_and_counts_tokens(self):
        with FakeVultr() as s:
            s.script(Reply(prompt_tokens=3, completion_tokens=4))
            c = make_client(s, public=False)
            c.call("evidence", [{"role": "user", "content": "x"}])
            self.assertEqual(c.tokens_used, 7)

    def test_run_cap_blocks_next_call_once_reached(self):
        from broker.client import BudgetExceeded
        from broker.limits import Limits
        with FakeVultr() as s:
            s.script(Reply(prompt_tokens=3, completion_tokens=4), Reply())
            c = make_client(s, limits=Limits(7, 1_000_000, 100), public=True)
            c.call("evidence", [{"role": "user", "content": "x"}])
            with self.assertRaises(BudgetExceeded):
                c.call("evidence", [{"role": "user", "content": "x"}])
            self.assertEqual(len(s.requests), 1)

    def test_run_cap_exceeded_by_a_single_call_is_reported(self):
        from broker.client import BudgetExceeded
        from broker.limits import Limits
        with FakeVultr() as s:
            s.script(Reply(prompt_tokens=30, completion_tokens=40))
            c = make_client(s, limits=Limits(10, 1_000_000, 100), public=True)
            with self.assertRaises(BudgetExceeded):
                c.call("evidence", [{"role": "user", "content": "x"}])

    def test_daily_budget_is_shared_across_clients(self):
        from broker.client import BudgetExceeded
        from broker.limits import DailyBudget, Limits
        daily = DailyBudget()
        lim = Limits(1_000_000, 12, 100)
        with FakeVultr() as s:
            s.script(Reply(prompt_tokens=6, completion_tokens=6), Reply())
            make_client(s, limits=lim, public=True, daily=daily).call("evidence", [{"role": "user", "content": "x"}])
            with self.assertRaises(BudgetExceeded):
                make_client(s, limits=lim, public=True, daily=daily).call("evidence", [{"role": "user", "content": "x"}])
            self.assertEqual(len(s.requests), 1)


class TestBrokerHardening(unittest.TestCase):
    """Findings F1-F3 from Walter's M3 validation (handoffs/M3/VALIDATION_Walter.md), plus the third-limit gap."""

    def test_content_that_echoes_the_key_is_redacted_in_the_result_and_the_log_F1(self):
        with FakeVultr() as s:
            s.script(Reply(content="here is " + KEY + " and Bearer " + KEY))
            c = make_client(s)
            r = c.call("evidence", [{"role": "user", "content": "x"}])
        self.assertNotIn(KEY, r.text)
        self.assertNotIn(KEY, json.dumps(r.record) + json.dumps(c.records) + json.dumps(c.log))
        self.assertIn("[REDACTED]", r.text)

    def test_response_model_that_reflects_the_key_is_redacted_everywhere_but_stays_a_strict_mismatch_F1b(self):
        from broker.client import ModelMismatch
        for reflected in (KEY, "evil-" + KEY + "-x", "Bearer " + KEY):
            with self.subTest(reflected=reflected):
                with FakeVultr() as s:
                    s.script(Reply(model=reflected))
                    c = make_client(s)
                    with self.assertRaises(ModelMismatch) as cm:
                        c.call("evidence", [{"role": "user", "content": "x"}])
                everything = json.dumps(cm.exception.record) + json.dumps(c.records) + json.dumps(c.log) + str(cm.exception) + repr(c)
                self.assertNotIn(KEY, everything)
                self.assertFalse(cm.exception.record["model_match"])
                self.assertIn("[REDACTED]", cm.exception.record["response_model"])
                self.assertGreater(c.tokens_used, 0)                      # accounting is preserved: the call was spent
                self.assertEqual(len(c.records), 1)

    def test_malformed_usage_fails_closed_and_cannot_reduce_consumption_F2(self):
        from broker.client import BrokerError
        for pt, ct in ((-20, -10), (-1, 5), (5, -1), (True, 3), (1.5, 2), ("7", 3), (None, 3)):
            with self.subTest(pt=pt, ct=ct):
                with FakeVultr() as s:
                    s.script(Reply(prompt_tokens=pt, completion_tokens=ct))
                    c = make_client(s)
                    with self.assertRaises(BrokerError):
                        c.call("evidence", [{"role": "user", "content": "x"}])
                    self.assertGreaterEqual(c.tokens_used, 0)

    def test_daily_budget_crossing_fails_closed_and_is_still_counted_F3(self):
        from broker.client import BudgetExceeded
        from broker.limits import DailyBudget, Limits
        daily = DailyBudget()
        with FakeVultr() as s:
            s.script(Reply(prompt_tokens=6, completion_tokens=6))
            c = make_client(s, limits=Limits(1_000_000, 10, 100), public=True, daily=daily)
            with self.assertRaises(BudgetExceeded):
                c.call("evidence", [{"role": "user", "content": "x"}])
        self.assertEqual(daily.used, 12)           # the tokens were spent, so they are counted

    def test_public_client_with_the_per_ip_limit_unset_refuses_before_any_http_F4(self):
        from broker.client import LiveInferenceRefused
        from broker.limits import Limits
        with FakeVultr() as s:
            c = make_client(s, limits=Limits(100, 100, None), public=True)
            with self.assertRaises(LiveInferenceRefused):
                c.call("evidence", [{"role": "user", "content": "x"}])
            self.assertEqual(s.requests, [])


class TestFallback(unittest.TestCase):
    def test_budget_fallback_only_for_path_and_coder_and_is_recorded(self):
        from broker.models import ModelsError
        with FakeVultr() as s:
            s.script(Reply(), Reply())
            c = make_client(s)
            r = c.call("path", [{"role": "user", "content": "x"}], use_fallback=True)
            self.assertEqual(s.requests[0].body["model"], "glm-5.3-flash")
            self.assertTrue(r.record["model_match"])
            self.assertTrue(r.fallback_used)
            with self.assertRaises(ModelsError):
                c.call("critic", [{"role": "user", "content": "x"}], use_fallback=True)


class TestEgressDiscipline(unittest.TestCase):
    def test_only_the_vultr_inference_host_appears_in_product_code_AT08(self):
        hosts, alltext = set(), []
        for pkg in ("broker", "council"):
            for dp, _, files in os.walk(os.path.join(ROOT, pkg)):
                for fn in files:
                    if fn.endswith(".py"):
                        with open(os.path.join(dp, fn), encoding="utf-8") as f:
                            txt = f.read()
                        alltext.append(txt.lower())
                        hosts |= set(re.findall(r"https?://([A-Za-z0-9.-]+)", txt))
        self.assertTrue(hosts <= {"api.vultrinference.com"}, hosts)
        self.assertNotIn("backboard", "".join(alltext))


if __name__ == "__main__":
    unittest.main()
