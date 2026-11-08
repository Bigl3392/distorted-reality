"""M3 council-port unit tests (RED first). Fake Vultr server only; no live inference, no key.

Interpretations recorded in HANDOFF (spec is silent, not defective):
 I-1 survivors = paths with no hard Critic finding, plus hard-flagged paths whose intervention CHANGED in the single revision.
 I-2 an unparseable Critic records FAIL / unparseable_failed_closed, performs no revision (no findings to act on), and the run continues.
"""
import copy
import json
import os
import unittest

from tests.fakes.fake_vultr import FakeVultr, Reply
from tests.unit.test_broker import fixture, make_client

CR_VALID = fixture("council_run__valid.json")
PATHS = CR_VALID["initial_paths"]
CI = fixture("council_input__valid.json")
EVIDENCE = {"facts": ["f1"], "constraints": ["c1"], "uncertainties": ["u1"]}


def jr(obj):
    return Reply(content=json.dumps(obj))


def paths_reply(paths=None):
    return jr({"paths": copy.deepcopy(paths or PATHS)})


def critic_reply(verdict="PASS", findings=None):
    return jr({"verdict": verdict, "findings": findings or []})


def decision_reply(label="option-1", no_winner=False):
    return jr({"recommended_label": None if no_winner else label, "no_winner": no_winner,
               "comparison": [{"label": "option-1", "rationale": "r", "risks": ["k"], "confidence": "low"}]})


def run(server, seed=7, replies=()):
    from council.run import run_council
    server.script(*replies)
    return run_council(make_client(server), copy.deepcopy(CI), seed=seed)


class TestParsing(unittest.TestCase):
    def test_plain_json_object_ok(self):
        from council.parsing import parse_role_json
        self.assertEqual(parse_role_json(' {"a": 1} \n'), {"a": 1})

    def test_one_fenced_block_is_allowed(self):
        from council.parsing import parse_role_json
        self.assertEqual(parse_role_json('```json\n{"a": 1}\n```'), {"a": 1})

    def test_prose_around_json_is_rejected(self):
        from council.parsing import ParseError, parse_role_json
        for bad in ('Sure! {"a": 1}', '{"a": 1} thanks', "", "[1,2]", "not json", '```json\n{"a":1}\n``` and more'):
            with self.subTest(bad):
                with self.assertRaises(ParseError):
                    parse_role_json(bad)


class TestHappyPath(unittest.TestCase):
    def test_four_calls_complete_and_record_validates(self):
        from broker import _schemas
        with FakeVultr() as s:
            res = run(s, replies=[jr(EVIDENCE), paths_reply(), critic_reply(), decision_reply()])
        self.assertEqual(res.status, "COMPLETE")
        self.assertEqual(_schemas.errors("council_run.schema.json", res.run), [])
        self.assertEqual(len(res.run["agent_calls"]), 4)
        self.assertEqual(res.run["revision"], {"performed": False, "count": 0, "paths": None})
        self.assertEqual(res.run["evidence"]["sources"], ["mri", "scan"])
        self.assertEqual(sorted(res.survivors), ["path-a", "path-b", "path-c"])
        self.assertEqual(res.run["models"]["critic"], "deepseek-v4.1-flash-1017")
        lm = res.run["shuffle"]["label_map"]
        self.assertEqual(sorted(lm.values()), ["path-a", "path-b", "path-c"])
        self.assertEqual(res.run["decision"]["recommended_path_id"], lm["option-1"])
        self.assertTrue(res.run["decision"]["qualitative_only"])

    def test_shuffle_is_seeded_and_deterministic(self):
        from council.shuffle import label_map
        ids = ["path-a", "path-b", "path-c"]
        self.assertEqual(label_map(ids, 7), label_map(ids, 7))
        self.assertEqual(sorted(label_map(ids, 7)), ["option-1", "option-2", "option-3"])
        self.assertTrue(any(label_map(ids, k) != label_map(ids, 7) for k in range(1, 40)))

    def test_decision_prompt_is_blind_no_path_ids_or_titles(self):
        with FakeVultr() as s:
            run(s, replies=[jr(EVIDENCE), paths_reply(), critic_reply(), decision_reply()])
            body = json.dumps(s.requests[3].body["messages"])
        for pid in ("path-a", "path-b", "path-c"):
            self.assertNotIn(pid, body)
        self.assertIn("option-1", body)

    def test_no_ground_truth_or_key_in_any_prompt(self):
        from tests.unit.test_broker import KEY
        with FakeVultr() as s:
            run(s, replies=[jr(EVIDENCE), paths_reply(), critic_reply(), decision_reply()])
            blob = json.dumps([r.body for r in s.requests]).lower()
        self.assertNotIn("ground_truth", blob)
        self.assertNotIn(KEY.lower(), blob)

    def test_no_winner_is_allowed(self):
        with FakeVultr() as s:
            res = run(s, replies=[jr(EVIDENCE), paths_reply(), critic_reply(), decision_reply(no_winner=True)])
        self.assertTrue(res.run["decision"]["no_winner"])
        self.assertIsNone(res.run["decision"]["recommended_label"])
        self.assertIsNone(res.run["decision"]["recommended_path_id"])


class TestPathRule(unittest.TestCase):
    def test_wrong_path_count_retries_once_then_fails_closed_AT06(self):
        from council.run import CouncilFailedClosed
        two = copy.deepcopy(PATHS[:2])
        with FakeVultr() as s:
            s.script(jr(EVIDENCE), paths_reply(two), paths_reply(two))
            from council.run import run_council
            with self.assertRaises(CouncilFailedClosed):
                run_council(make_client(s), copy.deepcopy(CI), seed=7)
            self.assertEqual(len(s.requests), 3)  # evidence + path + exactly one retry

    def test_one_retry_can_recover(self):
        two = copy.deepcopy(PATHS[:2])
        with FakeVultr() as s:
            res = run(s, replies=[jr(EVIDENCE), paths_reply(two), paths_reply(), critic_reply(), decision_reply()])
        self.assertEqual(res.status, "COMPLETE")
        self.assertEqual(len(res.run["agent_calls"]), 5)  # the failed attempt is still visible

    def test_duplicate_path_ids_rejected(self):
        from council.run import CouncilFailedClosed, run_council
        dup = copy.deepcopy(PATHS)
        dup[1]["path_id"] = dup[0]["path_id"]
        with FakeVultr() as s:
            s.script(jr(EVIDENCE), paths_reply(dup), paths_reply(dup))
            with self.assertRaises(CouncilFailedClosed):
                run_council(make_client(s), copy.deepcopy(CI), seed=7)


class TestCritic(unittest.TestCase):
    def test_unparseable_critic_is_FAIL_not_PASS_AT07(self):
        with FakeVultr() as s:
            res = run(s, replies=[jr(EVIDENCE), paths_reply(), Reply(content="Looks fine to me!"), decision_reply()])
        self.assertEqual(res.run["critic"], {"verdict": "FAIL", "findings": [], "parse_status": "unparseable_failed_closed"})
        self.assertEqual(res.run["revision"]["count"], 0)  # I-2
        self.assertTrue(any("critic" in n for n in res.notes))

    def test_pass_with_a_hard_finding_is_coerced_to_FAIL(self):
        finding = {"path_id": "path-b", "kind": "strawman", "detail": "weak"}
        with FakeVultr() as s:
            res = run(s, replies=[jr(EVIDENCE), paths_reply(), critic_reply("PASS", [finding]),
                                  paths_reply(self._changed("path-b")), decision_reply()])
        self.assertEqual(res.run["critic"]["verdict"], "FAIL")
        self.assertEqual(res.run["revision"]["performed"], True)

    def test_finding_for_unknown_path_is_unparseable(self):
        finding = {"path_id": "path-zzz", "kind": "overlap", "detail": "x"}
        with FakeVultr() as s:
            res = run(s, replies=[jr(EVIDENCE), paths_reply(), critic_reply("FAIL", [finding]), decision_reply()])
        self.assertEqual(res.run["critic"]["parse_status"], "unparseable_failed_closed")

    @staticmethod
    def _changed(pid):
        ps = copy.deepcopy(PATHS)
        for p in ps:
            if p["path_id"] == pid:
                p["intervention"]["summary"] += " (revised)"
        return ps

    def test_revision_happens_once_and_never_twice(self):
        f = [{"path_id": "path-b", "kind": "strawman", "detail": "weak"}]
        with FakeVultr() as s:
            res = run(s, replies=[jr(EVIDENCE), paths_reply(), critic_reply("FAIL", f), paths_reply(self._changed("path-b")), decision_reply()])
            n_calls = len(s.requests)
        self.assertEqual(n_calls, 5)  # evidence, path, critic, ONE revision, decision
        self.assertEqual(res.run["revision"]["count"], 1)
        self.assertEqual(len(res.run["revision"]["paths"]), 3)
        self.assertEqual(sorted(res.survivors), ["path-a", "path-b", "path-c"])

    def test_flagged_path_unchanged_by_revision_is_not_a_survivor(self):
        f = [{"path_id": "path-b", "kind": "overlap", "detail": "same as a"}]
        with FakeVultr() as s:
            res = run(s, replies=[jr(EVIDENCE), paths_reply(), critic_reply("FAIL", f), paths_reply(), decision_reply()])
        self.assertEqual(sorted(res.survivors), ["path-a", "path-c"])
        self.assertEqual(sorted(res.run["shuffle"]["label_map"].values()), ["path-a", "path-c"])
        self.assertEqual(res.status, "COMPLETE")

    def test_fewer_than_two_survivors_ends_NO_SUFFICIENT_EVIDENCE_without_decision(self):
        f = [{"path_id": "path-a", "kind": "strawman", "detail": "x"}, {"path_id": "path-b", "kind": "overlap", "detail": "y"}]
        from broker import _schemas
        with FakeVultr() as s:
            res = run(s, replies=[jr(EVIDENCE), paths_reply(), critic_reply("FAIL", f), paths_reply()])
            n_calls = len(s.requests)
        self.assertEqual(n_calls, 4)  # no decision call
        self.assertEqual(res.status, "NO_SUFFICIENT_EVIDENCE")
        self.assertEqual(res.survivors, ["path-c"])
        self.assertEqual(_schemas.errors("council_run.schema.json", res.run), [])
        d = res.run["decision"]
        self.assertTrue(d["no_winner"])
        self.assertIsNone(d["recommended_label"])
        self.assertEqual(d["comparison"], [])
        self.assertTrue(any("fewer than 2" in n for n in res.notes))

    def test_revision_that_changes_path_ids_fails_closed(self):
        from council.run import CouncilFailedClosed, run_council
        f = [{"path_id": "path-b", "kind": "strawman", "detail": "weak"}]
        bad = copy.deepcopy(PATHS)
        bad[1]["path_id"] = "path-x1"
        with FakeVultr() as s:
            s.script(jr(EVIDENCE), paths_reply(), critic_reply("FAIL", f), paths_reply(bad), paths_reply(bad))
            with self.assertRaises(CouncilFailedClosed):
                run_council(make_client(s), copy.deepcopy(CI), seed=7)


class TestDecision(unittest.TestCase):
    def test_unknown_label_retries_once_then_fails_closed(self):
        from council.run import CouncilFailedClosed, run_council
        with FakeVultr() as s:
            s.script(jr(EVIDENCE), paths_reply(), critic_reply(), decision_reply("option-9"), decision_reply("option-9"))
            with self.assertRaises(CouncilFailedClosed):
                run_council(make_client(s), copy.deepcopy(CI), seed=7)
            self.assertEqual(len(s.requests), 5)

    def test_winner_and_no_winner_together_is_inconsistent(self):
        from council.run import CouncilFailedClosed, run_council
        bad = jr({"recommended_label": "option-1", "no_winner": True, "comparison": []})
        with FakeVultr() as s:
            s.script(jr(EVIDENCE), paths_reply(), critic_reply(), bad, bad)
            with self.assertRaises(CouncilFailedClosed):
                run_council(make_client(s), copy.deepcopy(CI), seed=7)


class TestFailClosedOnBroker(unittest.TestCase):
    def test_model_mismatch_propagates_AT12(self):
        from broker import ModelMismatch
        from council.run import run_council
        with FakeVultr() as s:
            s.script(jr(EVIDENCE), paths_reply(), Reply(content=json.dumps({"verdict": "PASS", "findings": []}), model="deepseek-v4.1-flash"))
            with self.assertRaises(ModelMismatch):
                run_council(make_client(s), copy.deepcopy(CI), seed=7)

    def test_limits_unset_in_public_mode_refuses_before_any_call(self):
        from broker import LiveInferenceRefused
        from council.run import run_council
        with FakeVultr() as s:
            with self.assertRaises(LiveInferenceRefused):
                run_council(make_client(s, public=True), copy.deepcopy(CI), seed=7)
            self.assertEqual(s.requests, [])


class TestCoder(unittest.TestCase):
    def test_compile_returns_parseable_code(self):
        from council.run import compile_apply
        code = "def apply(events):\n    return {'flagged_cases': [], 'resolutions': [], 'manual_touch_cases': [], 'self_metrics': {}, 'error': None}\n"
        with FakeVultr() as s:
            s.script(jr({"code": code}))
            out = compile_apply(make_client(s), PATHS[0], {"fields": ["case_id"]})
            body = json.dumps(s.requests[0].body["messages"])
        self.assertEqual(out.code, code)
        self.assertEqual(s.requests[0].body["model"], "glm-5.3")
        self.assertIn("apply(events", body)
        self.assertIn("case_id", body)
        self.assertNotIn("ground_truth", body.lower())

    def test_syntax_error_retries_once_then_fails_closed(self):
        from council.run import CouncilFailedClosed, compile_apply
        with FakeVultr() as s:
            s.script(jr({"code": "def apply(:"}), jr({"code": "def apply(:"}))
            with self.assertRaises(CouncilFailedClosed):
                compile_apply(make_client(s), PATHS[0], {"fields": []})
            self.assertEqual(len(s.requests), 2)

    def test_non_string_code_is_rejected(self):
        from council.run import CouncilFailedClosed, compile_apply
        with FakeVultr() as s:
            s.script(jr({"code": 5}), jr({"code": 5}))
            with self.assertRaises(CouncilFailedClosed):
                compile_apply(make_client(s), PATHS[0], {"fields": []})


if __name__ == "__main__":
    unittest.main()
