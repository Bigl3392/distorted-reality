"""M5 orchestrator tests (RED first). Fake Vultr server, scripted fake runner (stands in for M4), in-memory fake dataset (stands in for M1).
Nothing here executes model code, contacts a real service, or needs Docker. All author-run.
Conventions under test: I-12 (packet hash/journal coverage), I-13 (events.json bundle), pre-registration (rule hash journaled before any sandbox)."""
import copy
import hashlib
import json
import os
import shutil
import tempfile
import unittest

from tests.fakes.fake_vultr import FakeVultr, Reply
from tests.unit.test_broker import KEY, fixture, make_client
from tests.unit.test_council import EVIDENCE, critic_reply, decision_reply, jr, paths_reply

from tests.fakes.doubles import (CASES, CODE, EVENT, GT_MARKER, HAPPY, MANIFEST, MRI, RECEIPT, ROOT, RULE_SRC, TRUTH, FakeDataset,  # noqa: F401
                                  FakeRunner, make_events, resolutions, response)


class Env:
    def __init__(self, test, runner_script=None, replies=None, **runner_kw):
        self.tmp = tempfile.mkdtemp()
        test.addCleanup(shutil.rmtree, self.tmp, True)
        self.rule = os.path.join(self.tmp, "decision_rule.yaml")
        shutil.copy(RULE_SRC, self.rule)
        self.server = FakeVultr().__enter__()
        test.addCleanup(self.server.__exit__, None, None, None)
        self.server.script(*(replies if replies is not None else [jr(EVIDENCE), paths_reply(), critic_reply(), decision_reply(),
                                                                   CODE, CODE, CODE]))
        self.runner = FakeRunner(runner_script or HAPPY, **runner_kw)
        self.clock = iter(f"2026-11-05T16:{m:02d}:{s:02d}Z" for m in range(60) for s in range(60))
        from control.orchestrator import Orchestrator
        self.orch = Orchestrator(broker=make_client(self.server), runner=self.runner, dataset=FakeDataset(), rule_path=self.rule,
                                 runs_dir=self.tmp, clock=lambda: next(self.clock), seed=7, assurance_tier="T0")

    def go(self, run_id="run-001"):
        run = self.orch.create(run_id)
        self.orch.intake(run, dict.fromkeys(self.orch.question_ids, 3))
        self.orch.proceed(run)
        return run


class TestHappyRun(unittest.TestCase):
    def test_reaches_awaiting_approval_with_valid_chain_and_packet(self):
        from broker import _schemas
        from control.journal import verify_chain
        env = Env(self)
        run = env.go()
        self.assertEqual(run.state.state, "AWAITING_APPROVAL")
        self.assertTrue(verify_chain(run.journal.entries).ok)
        self.assertEqual(_schemas.errors("evidence_packet.schema.json", run.packet), [])
        self.assertEqual(run.packet["outcome"]["result"], "PATH_PREFERRED_UNDER_ASSUMPTIONS")
        self.assertEqual(run.packet["outcome"]["preferred_path_id"], "path-a")
        self.assertEqual([c["attempt"] for c in env.runner.calls], [1, 1, 1])

    def test_state_history_follows_the_spec_machine(self):
        run = Env(self).go()
        h = run.state.history
        for a, b in [("CREATED", "DATASET_LOADED"), ("MRI_DONE", "SCAN_DONE"), ("COUNCIL_DECISION", "DECISION_RULE_FROZEN"),
                     ("CLAIM_CHECKED", "PACKET_BUILT"), ("PACKET_BUILT", "AWAITING_APPROVAL")]:
            self.assertEqual(h[h.index(a) + 1], b)

    def test_rule_hash_is_journaled_before_any_sandbox_pre_registration(self):
        env = Env(self)
        run = env.go()
        kinds = [e["kind"] for e in run.journal.entries]
        done = next(e for e in run.journal.entries if e["kind"] == "council_done")
        with open(env.rule, "rb") as f:
            want = hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(done["data"]["decision_rule_sha256"], want)
        self.assertIs(done["data"]["rule_frozen"], True)
        self.assertLess(kinds.index("council_done"), kinds.index("sandbox_created"))
        self.assertEqual(run.packet["decision_rule"]["sha256"], want)

    def test_every_attempt_has_create_and_destroy_AT_13(self):
        run = Env(self).go()
        kinds = [e["kind"] for e in run.journal.entries]
        self.assertEqual(kinds.count("sandbox_created"), 3)
        self.assertEqual(kinds.count("sandbox_destroyed"), 3)

    def test_packet_journal_coverage_and_hash_follow_I12(self):
        from control import packet
        run = Env(self).go()
        p = run.packet
        n = p["journal"]["entries"]
        self.assertEqual(run.journal.entries[n - 1]["entry_sha256"], p["journal"]["head_sha256"])
        nxt = run.journal.entries[n]
        self.assertEqual(nxt["kind"], "packet_built")
        self.assertEqual(nxt["data"]["packet_sha256"], p["packet_sha256"])
        self.assertEqual(p["packet_sha256"], packet.packet_hash(p))

    def test_section_hashes_are_journaled_I12(self):
        from control.journal import canonical
        run = Env(self).go()
        by = {e["kind"]: e for e in run.journal.entries}
        h = lambda o: hashlib.sha256(canonical(o).encode("ascii")).hexdigest()
        self.assertEqual(by["dataset_loaded"]["data"]["manifest_sha256"], h(run.packet["dataset"]))
        self.assertEqual(by["mri_done"]["data"]["inventory_sha256"], h(run.packet["mri"]))
        self.assertEqual(by["scan_done"]["data"]["scan_sha256"], h(run.packet["scan"]))

    def test_events_bundle_matches_receipts_I13(self):
        from control.journal import canonical
        env = Env(self)
        run = env.go()
        with open(os.path.join(env.tmp, "run-001", "events.json"), encoding="utf-8") as f:
            ev = json.load(f)
        want = hashlib.sha256(canonical(ev).encode("ascii")).hexdigest()
        for ex in run.packet["executions"]:
            self.assertEqual(ex["events_sha256"], want)
            self.assertEqual(ex["events_count"], len(ev))

    def test_runner_job_is_a_valid_C2_with_no_secret_AT_15_adjacent(self):
        from broker import _schemas
        env = Env(self)
        env.go()
        for c in env.runner.calls:
            self.assertEqual(_schemas.errors("blackbox_job.schema.json", c["job"]), [])
            self.assertEqual(c["job"]["network"], "none")
            self.assertIs(c["job"]["secrets_in_job"], False)
            self.assertNotIn(KEY, json.dumps(c["job"]) + c["code"] + json.dumps(c["events"]))

    def test_ground_truth_never_leaves_the_control_plane_AT_E8(self):
        env = Env(self)
        run = env.go()
        blob = json.dumps([r.body for r in env.server.requests]) + json.dumps(env.runner.calls) + json.dumps(run.journal.entries)
        self.assertNotIn(GT_MARKER, blob)
        self.assertNotIn("truth_exceptions", blob)

    def test_rebuild_from_stored_inputs_is_byte_identical_AT_10(self):
        from control import orchestrator
        env = Env(self)
        run = env.go()
        got = orchestrator.rebuild_packet(os.path.join(env.tmp, "run-001"))
        self.assertEqual(got, run.packet)


class TestClaimsAndMetrics(unittest.TestCase):
    def test_dangling_evidence_is_unsupported_then_one_correction_AT_E4(self):
        script = dict(HAPPY)
        script[("path-a", 1)] = response(CASES[:5], bad=[CASES[0]])
        script[("path-a", 2)] = response(CASES[:5])
        env = Env(self, script, replies=[jr(EVIDENCE), paths_reply(), critic_reply(), decision_reply(), CODE, CODE, CODE, CODE])
        run = env.go()
        a = [e for e in run.packet["executions"] if e["path_id"] == "path-a"]
        self.assertEqual([x["attempt"] for x in a], [1, 2])
        self.assertEqual(a[0]["claim_check"]["unsupported"], 1)
        self.assertEqual(a[1]["claim_check"]["unsupported"], 0)
        self.assertIn("CLAIM_CHECKED", run.state.history)
        self.assertIn("EXEC_CORRECTION", run.state.history)
        last_coder = [r.body for r in env.server.requests][-1]
        self.assertIn("dangling evidence_ref", json.dumps(last_coder))

    def test_correction_that_still_fails_makes_the_path_ineligible_no_second_correction(self):
        script = dict(HAPPY)
        script[("path-a", 1)] = response(CASES[:5], bad=[CASES[0]])
        script[("path-a", 2)] = response(CASES[:5], bad=[CASES[0]])
        env = Env(self, script, replies=[jr(EVIDENCE), paths_reply(), critic_reply(), decision_reply(), CODE, CODE, CODE, CODE])
        run = env.go()
        self.assertEqual(len([c for c in env.runner.calls if c["job"]["path_id"] == "path-a"]), 2)
        self.assertNotEqual(run.packet["outcome"]["preferred_path_id"], "path-a")

    def test_self_reported_metrics_differing_from_recompute_are_flagged_not_reconciled_AT_E5(self):
        script = dict(HAPPY)
        script[("path-a", 1)] = response(CASES[:5], self_metrics={"exceptions_caught": 99})
        run = Env(self, script).go()
        a = next(e for e in run.packet["executions"] if e["path_id"] == "path-a")
        self.assertIs(a["metrics_discrepancy"], True)
        self.assertEqual(a["metrics_recomputed"]["exceptions_caught"], 5)
        self.assertEqual(a["metrics_self_reported"]["exceptions_caught"], 99)

    def test_attempt_that_errors_is_corrected_once_then_excluded_not_counted_as_zero_I14(self):
        err = fixture("sb1_response__valid_error.json")
        script = dict(HAPPY)
        script[("path-c", 1)] = err
        script[("path-c", 2)] = err
        env = Env(self, script, replies=[jr(EVIDENCE), paths_reply(), critic_reply(), decision_reply(), CODE, CODE, CODE, CODE])
        run = env.go()
        self.assertEqual(len([c for c in env.runner.calls if c["job"]["path_id"] == "path-c"]), 2)
        self.assertEqual(run.state.state, "AWAITING_APPROVAL")
        self.assertEqual(run.packet["outcome"]["preferred_path_id"], "path-a")
        self.assertIn("excluded", run.packet["outcome"]["basis"])
        self.assertIn("path-c", run.packet["outcome"]["basis"])

    def test_errored_paths_never_count_as_zero_score_comparators_I14(self):
        err = fixture("sb1_response__valid_error.json")
        script = {("path-a", 1): response(CASES[:5]), ("path-b", 1): err, ("path-b", 2): err, ("path-c", 1): err, ("path-c", 2): err}
        env = Env(self, script, replies=[jr(EVIDENCE), paths_reply(), critic_reply(), decision_reply(), CODE, CODE, CODE, CODE, CODE])
        run = env.go()
        self.assertEqual(run.state.state, "AWAITING_APPROVAL")
        self.assertEqual(run.packet["outcome"]["result"], "NO_SUFFICIENT_EVIDENCE")
        self.assertIsNone(run.packet["outcome"]["preferred_path_id"])

    def test_tie_within_margin_is_no_sufficient_evidence_AT_E6(self):
        script = dict(HAPPY)
        script[("path-b", 1)] = response(CASES[:4])
        run = Env(self, script).go()
        self.assertEqual(run.packet["outcome"]["result"], "NO_SUFFICIENT_EVIDENCE")
        self.assertIsNone(run.packet["outcome"]["preferred_path_id"])

    def test_council_recommendation_and_rule_outcome_both_shown_AT_E7(self):
        env = Env(self, replies=[jr(EVIDENCE), paths_reply(), critic_reply(), decision_reply("option-1"), CODE, CODE, CODE])
        run = env.go()
        rec = run.packet["council"]["decision"]["recommended_path_id"]
        self.assertIn(rec, run.packet["outcome"]["basis"] + " " + str(run.packet["outcome"]["preferred_path_id"]))
        self.assertEqual(run.packet["outcome"]["preferred_path_id"], "path-a")


class TestFailClosed(unittest.TestCase):
    def assertFailed(self, env, run, at):
        from broker import _schemas
        from control.journal import verify_chain
        self.assertEqual(run.state.state, "FAILED_CLOSED")
        self.assertEqual(run.state.failed_at, at)
        self.assertTrue(verify_chain(run.journal.entries).ok)
        self.assertEqual(run.journal.entries[-1]["kind"], "error")
        self.assertEqual(_schemas.errors("evidence_packet_incomplete.schema.json", run.packet), [])
        self.assertEqual(run.packet["outcome"]["result"], "NO_SUFFICIENT_EVIDENCE")
        self.assertEqual(run.journal.entries[-1]["data"]["packet_sha256"], run.packet["packet_sha256"])

    def test_model_mismatch_fails_closed_AT_12(self):
        env = Env(self, replies=[Reply(content=json.dumps(EVIDENCE), model="some-other-model")])
        run = env.go()
        self.assertFailed(env, run, "COUNCIL_EVIDENCE")
        self.assertEqual(env.runner.calls, [])

    def test_unreadable_council_output_fails_closed(self):
        env = Env(self, replies=[Reply(content="not json"), Reply(content="still not json")])
        run = env.go()
        self.assertFailed(env, run, "COUNCIL_EVIDENCE")

    def test_fewer_than_two_survivors_ends_with_no_sufficient_evidence_and_says_why(self):
        from tests.unit.test_council import PATHS
        flag = {"verdict": "FAIL", "findings": [{"path_id": "path-a", "kind": "strawman", "detail": "d"},
                                                 {"path_id": "path-b", "kind": "overlap", "detail": "d"}]}
        same = paths_reply(PATHS)
        env = Env(self, replies=[jr(EVIDENCE), paths_reply(), jr(flag), same])
        run = env.go()
        self.assertEqual(run.state.state, "FAILED_CLOSED")
        self.assertIn("fewer than 2", run.packet["failure_reason"])
        self.assertEqual(env.runner.calls, [])

    def test_unverified_destroy_fails_closed_and_the_packet_says_so(self):
        env = Env(self, destroy_verified=False)
        run = env.go()
        self.assertEqual(run.state.state, "FAILED_CLOSED")
        self.assertIn("destroy", run.packet["failure_reason"])

    def test_missing_destroy_journal_entry_fails_closed(self):
        env = Env(self, skip_destroy_entry=True)
        run = env.go()
        self.assertEqual(run.state.state, "FAILED_CLOSED")

    def test_rule_file_changed_after_freeze_fails_closed_AT_E3(self):
        env = Env(self)
        orig = env.runner.run

        def tamper(*a, **k):
            with open(env.rule, "a", encoding="utf-8") as f:
                f.write("# edited after freeze\n")
            return orig(*a, **k)
        env.runner.run = tamper
        run = env.go()
        self.assertEqual(run.state.state, "FAILED_CLOSED")
        self.assertIn("decision rule", run.packet["failure_reason"])

    def test_a_reader_never_sees_FAILED_CLOSED_without_the_packet_F_M12_05(self):
        """F-M12-05: the API reports run.state and serves run.packet from two attributes. A client that sees FAILED_CLOSED must
        be able to fetch the INCOMPLETE packet at once, so the packet has to exist before the state flips."""
        import threading
        import time
        from unittest import mock
        from control import packet
        env = Env(self, replies=[Reply(content=json.dumps(EVIDENCE), model="some-other-model")])
        run = env.orch.create("run-f05")
        env.orch.intake(run, dict.fromkeys(env.orch.question_ids, 3))
        real = packet.build_incomplete

        def slow(ctx):
            time.sleep(0.3)                                  # widens the window the browser run hit; the invariant must not depend on speed
            return real(ctx)
        seen, stop = [], threading.Event()

        def reader():
            while not stop.is_set():
                state = run.state.state                      # same order as api._status then api._section: state first, packet after
                if state == "FAILED_CLOSED":
                    seen.append(run.packet is not None)
                    return
        t = threading.Thread(target=reader, daemon=True)
        with mock.patch.object(packet, "build_incomplete", slow):
            t.start()
            env.orch.proceed(run)
        t.join(5)                                            # the reader returns by itself once it has seen FAILED_CLOSED
        stop.set()
        self.assertEqual(seen, [True], "a reader saw FAILED_CLOSED before the INCOMPLETE packet was available")
        self.assertEqual(run.state.state, "FAILED_CLOSED")
        self.assertEqual(run.state.failed_at, "COUNCIL_EVIDENCE")

    def test_state_is_not_failed_while_the_incomplete_packet_is_being_built_F_M12_05(self):
        from unittest import mock
        from control import packet
        env = Env(self, replies=[Reply(content=json.dumps(EVIDENCE), model="some-other-model")])
        run = env.orch.create("run-f05b")
        env.orch.intake(run, dict.fromkeys(env.orch.question_ids, 3))
        real, at_build = packet.build_incomplete, []

        def probe(ctx):
            at_build.append((run.state.state, run.packet))
            return real(ctx)
        with mock.patch.object(packet, "build_incomplete", probe):
            env.orch.proceed(run)
        self.assertEqual(len(at_build), 1)
        self.assertNotEqual(at_build[0][0], "FAILED_CLOSED")
        self.assertEqual(run.state.state, "FAILED_CLOSED")
        self.assertIsNotNone(run.packet)

    def test_unbuildable_incomplete_packet_still_fails_closed_with_a_journaled_error_F_M12_05(self):
        """If even the stripped INCOMPLETE packet cannot be built, the run must still end FAILED_CLOSED (never stay in flight),
        proceed must not raise, the journal must say why, and the packet is absent (404) rather than invented."""
        from unittest import mock
        from control import packet
        from control.journal import verify_chain
        env = Env(self, replies=[Reply(content=json.dumps(EVIDENCE), model="some-other-model")])
        run = env.orch.create("run-f05c")
        env.orch.intake(run, dict.fromkeys(env.orch.question_ids, 3))

        def broken(ctx):
            raise packet.PacketError("cannot build")
        with mock.patch.object(packet, "build_incomplete", broken):
            env.orch.proceed(run)
        self.assertEqual(run.state.state, "FAILED_CLOSED")
        self.assertEqual(run.state.failed_at, "COUNCIL_EVIDENCE")
        self.assertIsNone(run.packet)
        self.assertTrue(verify_chain(run.journal.entries).ok)
        last = run.journal.entries[-1]
        self.assertEqual(last["kind"], "error")
        self.assertNotIn("packet_sha256", last["data"])

    def test_no_state_is_skipped_calling_proceed_before_intake_is_refused(self):
        from control.states import IllegalTransition
        env = Env(self)
        run = env.orch.create("run-002")
        with self.assertRaises(IllegalTransition):
            env.orch.proceed(run)

    def test_bad_intake_is_refused_with_the_generic_error_and_state_does_not_advance(self):
        from scan.service import ScanRejected
        env = Env(self)
        run = env.orch.create("run-003")
        ids = list(env.orch.question_ids)
        with self.assertRaises(ScanRejected):
            env.orch.intake(run, dict.fromkeys(ids[:14], 3))
        self.assertEqual(run.state.state, "MRI_DONE")


class TestApprovalGate(unittest.TestCase):
    def test_confirm_requires_a_prior_view(self):
        from control.approval import ApprovalError
        env = Env(self)
        run = env.go()
        with self.assertRaises(ApprovalError):
            env.orch.confirm(run)

    def test_view_then_confirm_builds_a_distinct_valid_packet_with_no_external_action_AT_21(self):
        from broker import _schemas
        from control.journal import verify_chain
        env = Env(self)
        run = env.go()
        pending = run.packet["packet_sha256"]
        env.orch.view(run)
        confirmed = env.orch.confirm(run)
        self.assertEqual(run.state.state, "APPROVED_VIEWED")
        self.assertNotEqual(confirmed["packet_sha256"], pending)
        self.assertEqual(confirmed["approval_gate"]["status"], "VIEWED_CONFIRMED")
        self.assertIs(confirmed["approval_gate"]["external_action_taken"], False)
        self.assertEqual(_schemas.errors("evidence_packet.schema.json", confirmed), [])
        ap = [e for e in run.journal.entries if e["kind"] == "approval"]
        self.assertEqual([a["data"]["viewer_action"] for a in ap], ["viewed", "confirmed"])
        self.assertTrue(all(a["data"]["external_action_taken"] is False for a in ap))
        self.assertEqual(ap[-1]["data"]["packet_sha256"], confirmed["packet_sha256"])
        self.assertTrue(verify_chain(run.journal.entries).ok)

    def test_nothing_is_sent_anywhere_after_approve_AT_21(self):
        env = Env(self)
        run = env.go()
        env.orch.view(run)
        before, calls = len(env.server.requests), len(env.runner.calls)
        env.orch.confirm(run)
        self.assertEqual(len(env.server.requests), before)
        self.assertEqual(len(env.runner.calls), calls)

    def test_expiry_moves_to_EXPIRED_and_blocks_confirm(self):
        from control.approval import ApprovalError
        env = Env(self)
        run = env.go()
        env.orch.view(run)
        env.orch.expire(run)
        self.assertEqual(run.state.state, "EXPIRED")
        with self.assertRaises(ApprovalError):
            env.orch.confirm(run)

    def test_repeated_view_is_idempotent_and_repeated_confirm_is_refused_with_no_effect(self):
        from control.approval import ApprovalError
        env = Env(self)
        run = env.go()
        p1 = env.orch.view(run)
        n = len(run.journal.entries)
        p2 = env.orch.view(run)
        self.assertEqual(p1["packet_sha256"], p2["packet_sha256"])
        self.assertEqual(len(run.journal.entries), n)          # no second 'viewed' entry
        done = env.orch.confirm(run)
        n = len(run.journal.entries)
        with self.assertRaises(ApprovalError):
            env.orch.confirm(run)
        with self.assertRaises(ApprovalError):
            env.orch.view(run)
        self.assertEqual(len(run.journal.entries), n)
        self.assertEqual(run.packet_confirmed["packet_sha256"], done["packet_sha256"])

    def test_expired_run_cannot_be_viewed_or_approved(self):
        from control.approval import ApprovalError
        env = Env(self)
        run = env.go()
        env.orch.expire(run)
        with self.assertRaises(ApprovalError):
            env.orch.view(run)

    def test_failed_run_cannot_be_approved(self):
        from control.approval import ApprovalError
        env = Env(self, replies=[Reply(content="x", model="other")])
        run = env.go()
        with self.assertRaises(ApprovalError):
            env.orch.view(run)


if __name__ == "__main__":
    unittest.main()
