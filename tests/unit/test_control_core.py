"""M5 control-plane core tests (RED first): journal, state machine, pre-registered rule, claim checker, metric recompute.
Covers AT-E2 (journal tamper), AT-E3 (rule change), AT-E4 (dangling evidence_ref), AT-E5 (discrepancy), AT-E6 (tie),
AT-E7 (council vs rule), AT-11, AT-10 (journal part). No live inference, no sandbox, no key.
Interpretations I-7..I-10 (decisions/DR-INT-001) cover what the frozen spec leaves open.
"""
import copy
import hashlib
import json
import os
import shutil
import tempfile
import unittest

from broker import _schemas

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
T0 = "2026-11-05T15:00:00Z"


def clock():
    return T0


class TestJournal(unittest.TestCase):
    def make(self, **kw):
        from control.journal import Journal
        return Journal("run-001", clock=clock, **kw)

    def test_entries_validate_chain_and_start_at_zero_genesis(self):
        j = self.make()
        e0 = j.append("run_created", "control", {"x": 1})
        e1 = j.append("dataset_loaded", "control", {"dataset_sha256": "a" * 64})
        for e in (e0, e1):
            self.assertEqual(_schemas.errors("journal_entry.schema.json", e), [])
        self.assertEqual((e0["seq"], e1["seq"]), (0, 1))
        self.assertEqual(e0["prev_sha256"], "0" * 64)
        self.assertEqual(e1["prev_sha256"], e0["entry_sha256"])
        self.assertEqual(j.head_sha256, e1["entry_sha256"])

    def test_entry_hash_is_sha256_of_sorted_compact_json_of_all_other_fields(self):
        j = self.make()
        e = j.append("run_created", "control", {"b": 2, "a": 1})
        body = {k: v for k, v in e.items() if k != "entry_sha256"}
        want = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()
        self.assertEqual(e["entry_sha256"], want)

    def test_verify_chain_ok_and_names_the_seq_of_a_flipped_byte_ATE2(self):
        from control.journal import verify_chain
        j = self.make()
        for i in range(5):
            j.append("agent_call", "broker", {"n": i})
        ok = verify_chain(j.entries)
        self.assertTrue(ok.ok)
        bad = copy.deepcopy(j.entries)
        bad[3]["data"]["n"] = 99
        r = verify_chain(bad)
        self.assertFalse(r.ok)
        self.assertEqual(r.bad_seq, 3)

    def test_removed_or_reordered_entries_are_detected(self):
        from control.journal import verify_chain
        j = self.make()
        for i in range(4):
            j.append("agent_call", "broker", {"n": i})
        gap = [j.entries[0], j.entries[2], j.entries[3]]
        self.assertFalse(verify_chain(gap).ok)
        swapped = [j.entries[1], j.entries[0], j.entries[2], j.entries[3]]
        self.assertFalse(verify_chain(swapped).ok)
        self.assertFalse(verify_chain(j.entries[1:]).ok)  # first entry must be seq 0 with zero prev

    def test_tampered_entry_with_its_own_hash_recomputed_is_caught_by_the_next_link(self):
        from control.journal import _hash, verify_chain
        j = self.make()
        for i in range(4):
            j.append("agent_call", "broker", {"n": i})
        forged = copy.deepcopy(j.entries)
        forged[1]["data"]["n"] = 99
        forged[1]["entry_sha256"] = _hash({k: v for k, v in forged[1].items() if k != "entry_sha256"})  # attacker re-hashes only this entry
        r = verify_chain(forged)
        self.assertFalse(r.ok)
        self.assertEqual(r.bad_seq, 2)  # entry 2 still points at the old hash of entry 1

    def test_unknown_kind_or_actor_refused(self):
        from control.journal import JournalError
        j = self.make()
        with self.assertRaises(JournalError):
            j.append("made_up_kind", "control", {})
        with self.assertRaises(JournalError):
            j.append("run_created", "somebody", {})

    def test_secret_values_and_non_ascii_are_refused(self):
        from control.journal import JournalError
        j = self.make(forbidden=["SECRET-VALUE-123"])
        with self.assertRaises(JournalError):
            j.append("error", "control", {"msg": "boom SECRET-VALUE-123 boom"})
        with self.assertRaises(JournalError):
            j.append("error", "control", {"msg": "café"})
        self.assertEqual(j.entries, [])  # nothing written on refusal

    def test_file_persistence_roundtrip_and_no_overwrite(self):
        from control.journal import Journal, JournalError, load_journal, verify_chain
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "journal.jsonl")
            j = Journal("run-001", path=p, clock=clock)
            j.append("run_created", "control", {})
            j.append("dataset_loaded", "control", {})
            entries = load_journal(p)
            self.assertEqual(entries, j.entries)
            self.assertTrue(verify_chain(entries).ok)
            with self.assertRaises(JournalError):
                Journal("run-001", path=p, clock=clock)  # append-only: never reopen/overwrite
            with open(p, "rb") as f:
                raw = bytearray(f.read())
            i = raw.index(b'"run_created"')
            raw[i + 5] ^= 0x01
            with open(p, "wb") as f:
                f.write(bytes(raw))
            self.assertFalse(verify_chain(load_journal(p)).ok)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestStateMachine(unittest.TestCase):
    HAPPY = ["DATASET_LOADED", "MRI_DONE", "SCAN_DONE", "COUNCIL_EVIDENCE", "COUNCIL_PATHS", "COUNCIL_CRITIC",
             "COUNCIL_DECISION", "DECISION_RULE_FROZEN", "EXEC_PATH", "EXEC_PATH", "CLAIM_CHECKED", "PACKET_BUILT",
             "AWAITING_APPROVAL", "APPROVED_VIEWED"]

    def walk(self, sm, names):
        for n in names:
            sm.advance(n)

    def test_happy_path_and_revision_branch(self):
        from control.states import StateMachine
        sm = StateMachine()
        self.walk(sm, self.HAPPY)
        self.assertEqual(sm.state, "APPROVED_VIEWED")
        sm2 = StateMachine()
        self.walk(sm2, self.HAPPY[:6] + ["COUNCIL_REVISION"] + self.HAPPY[6:])
        self.assertEqual(sm2.state, "APPROVED_VIEWED")

    def test_correction_branch_after_claim_check(self):
        from control.states import StateMachine
        sm = StateMachine()
        self.walk(sm, self.HAPPY[:10] + ["CLAIM_CHECKED", "EXEC_CORRECTION", "PACKET_BUILT"])
        self.assertEqual(sm.state, "PACKET_BUILT")

    def test_no_state_skips(self):
        from control.states import IllegalTransition, StateMachine
        for skip_to in ("MRI_DONE", "EXEC_PATH", "PACKET_BUILT", "APPROVED_VIEWED", "DECISION_RULE_FROZEN"):
            with self.subTest(skip_to):
                with self.assertRaises(IllegalTransition):
                    StateMachine().advance(skip_to)

    def test_no_execution_before_the_rule_is_frozen(self):
        from control.states import IllegalTransition, StateMachine
        sm = StateMachine()
        self.walk(sm, self.HAPPY[:7])  # up to COUNCIL_DECISION
        with self.assertRaises(IllegalTransition):
            sm.advance("EXEC_PATH")

    def test_any_state_can_fail_closed_and_failure_is_terminal_with_failed_at(self):
        from control.states import IllegalTransition, StateMachine
        sm = StateMachine()
        self.walk(sm, self.HAPPY[:3])  # CREATED -> DATASET_LOADED -> MRI_DONE -> SCAN_DONE
        sm.fail_closed("model mismatch")
        self.assertEqual(sm.state, "FAILED_CLOSED")
        self.assertEqual(sm.failed_at, "SCAN_DONE")
        self.assertEqual(sm.failure_reason, "model mismatch")
        with self.assertRaises(IllegalTransition):
            sm.advance("COUNCIL_EVIDENCE")
        with self.assertRaises(IllegalTransition):
            sm.fail_closed("again")

    def test_terminal_states_do_not_advance(self):
        from control.states import IllegalTransition, StateMachine
        for last in ("APPROVED_VIEWED", "EXPIRED"):
            sm = StateMachine()
            self.walk(sm, self.HAPPY[:-1] + [last])
            with self.assertRaises(IllegalTransition):
                sm.advance("AWAITING_APPROVAL")


RULE_PATH = os.path.join(ROOT, "schemas", "decision_rule.yaml")


def res(claims="CLAIMS_HOLD", caught=10, false_alarms=0, touches=5, cycle=30.0, unsupported=0):
    return {"claims_verdict": claims, "metrics": {"exceptions_caught": caught, "false_alarms": false_alarms,
                                                   "manual_touches": touches, "median_cycle_min": cycle,
                                                   "unsupported_claims": unsupported}}


class TestRule(unittest.TestCase):
    def rule(self):
        from control.rule import load_rule
        return load_rule(RULE_PATH)

    def test_rule_loads_hashes_file_bytes_and_matches_x9(self):
        from control.rule import load_rule
        r = load_rule(RULE_PATH)
        with open(RULE_PATH, "rb") as f:
            self.assertEqual(r.sha256, hashlib.sha256(f.read()).hexdigest())
        self.assertEqual(r.data["rule_id"], "dr-3way-v1")
        self.assertEqual(r.data["minimum_margin"]["exceptions_caught"], 3)

    def test_changed_rule_changes_hash_and_is_detected_ATE3(self):
        from control.rule import load_rule, verify_frozen
        r = load_rule(RULE_PATH)
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "decision_rule.yaml")
            with open(RULE_PATH, "rb") as f:
                raw = f.read()
            with open(p, "wb") as f:
                f.write(raw.replace(b"exceptions_caught: 3", b"exceptions_caught: 1"))
            self.assertNotEqual(load_rule(p).sha256, r.sha256)
            self.assertTrue(verify_frozen(RULE_PATH, r.sha256))
            self.assertFalse(verify_frozen(p, r.sha256))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_invalid_rule_structure_refused(self):
        from control.rule import RuleError, parse_rule
        bad = {"rule_id": "dr-x", "eligibility": {}}
        with self.assertRaises(RuleError):
            parse_rule(json.dumps(bad).encode())

    def test_clear_winner_under_assumptions(self):
        from control.rule import evaluate
        out = evaluate(self.rule(), {"path-a": res(caught=10), "path-b": res(caught=14)}, cases_total=200)
        self.assertEqual(out["result"], "PATH_PREFERRED_UNDER_ASSUMPTIONS")
        self.assertEqual(out["preferred_path_id"], "path-b")

    def test_margin_below_three_is_no_sufficient_evidence_ATE6_AT11(self):
        from control.rule import evaluate
        out = evaluate(self.rule(), {"path-a": res(caught=10), "path-b": res(caught=12)}, cases_total=200)
        self.assertEqual(out["result"], "NO_SUFFICIENT_EVIDENCE")
        self.assertIsNone(out["preferred_path_id"])
        # a better secondary metric does NOT rescue an exceptions_caught tie within the margin
        out = evaluate(self.rule(), {"path-a": res(caught=10, touches=9), "path-b": res(caught=10, touches=1)}, cases_total=200)
        self.assertEqual(out["result"], "NO_SUFFICIENT_EVIDENCE")

    def test_exactly_three_is_enough(self):
        from control.rule import evaluate
        out = evaluate(self.rule(), {"path-a": res(caught=10), "path-b": res(caught=13)}, cases_total=200)
        self.assertEqual(out["preferred_path_id"], "path-b")

    def test_failing_claims_make_a_path_ineligible_whatever_its_metrics(self):
        from control.rule import evaluate
        out = evaluate(self.rule(), {"path-a": res(claims="CLAIMS_FAIL", caught=100, unsupported=2),
                                     "path-b": res(caught=10), "path-c": res(caught=3)}, cases_total=200)
        self.assertEqual(out["result"], "PATH_PREFERRED_UNDER_ASSUMPTIONS")
        self.assertEqual(out["preferred_path_id"], "path-b")
        self.assertIn("path-a", out["ineligible"])

    def test_claims_fail_verdict_alone_makes_a_path_ineligible(self):
        from control.rule import evaluate
        out = evaluate(self.rule(), {"path-a": res(claims="CLAIMS_FAIL", caught=100, unsupported=0),
                                     "path-b": res(caught=10), "path-c": res(caught=2)}, cases_total=200)
        self.assertIn("path-a", out["ineligible"])
        self.assertEqual(out["preferred_path_id"], "path-b")

    def test_too_many_false_alarms_is_ineligible(self):
        from control.rule import evaluate
        out = evaluate(self.rule(), {"path-a": res(caught=50, false_alarms=21), "path-b": res(caught=10)}, cases_total=200)
        self.assertIn("path-a", out["ineligible"])
        self.assertEqual(out["result"], "NO_SUFFICIENT_EVIDENCE")  # I-8: only one eligible path, no comparator
        ok = evaluate(self.rule(), {"path-a": res(caught=50, false_alarms=20), "path-b": res(caught=10)}, cases_total=200)
        self.assertEqual(ok["preferred_path_id"], "path-a")  # 20 / 200 = 0.10 is allowed (<=)

    def test_fewer_than_two_eligible_is_no_sufficient_evidence_I8(self):
        from control.rule import evaluate
        out = evaluate(self.rule(), {"path-a": res(caught=50)}, cases_total=200)
        self.assertEqual(out["result"], "NO_SUFFICIENT_EVIDENCE")
        out = evaluate(self.rule(), {}, cases_total=200)
        self.assertEqual(out["result"], "NO_SUFFICIENT_EVIDENCE")

    def test_unsupported_claims_over_max_is_ineligible_even_if_verdict_says_hold(self):
        from control.rule import evaluate
        out = evaluate(self.rule(), {"path-a": res(caught=50, unsupported=1), "path-b": res(caught=10), "path-c": res(caught=2)}, cases_total=200)
        self.assertIn("path-a", out["ineligible"])

    def test_council_and_rule_disagree_both_shown_and_rule_stands_ATE7(self):
        from control.rule import combine, evaluate
        out = evaluate(self.rule(), {"path-a": res(caught=10), "path-b": res(caught=20)}, cases_total=200)
        c = combine(out, {"recommended_path_id": "path-a", "no_winner": False})
        self.assertFalse(c["agree"])
        self.assertEqual(c["council_recommended_path_id"], "path-a")
        self.assertEqual(c["rule_preferred_path_id"], "path-b")
        self.assertEqual(c["outcome_stands"], "rule")
        agree = combine(out, {"recommended_path_id": "path-b", "no_winner": False})
        self.assertTrue(agree["agree"])

    def test_evaluate_is_deterministic_in_dict_order(self):
        from control.rule import evaluate
        a = {"path-a": res(caught=10), "path-b": res(caught=20)}
        b = dict(reversed(list(a.items())))
        self.assertEqual(evaluate(self.rule(), a, 200), evaluate(self.rule(), b, 200))


def ev(case, step, ts, status="completed", ref=None, **kw):
    e = {"label": "SYNTHETIC", "source_type": "SYNTHETIC", "case_id": case, "step_id": step, "role": "Receiving Clerk",
         "action": "a", "input": "i", "output": "o", "timestamp": ts, "duration_min": 1, "expected_duration_min": 1,
         "handoff_to": None, "status": status, "evidence_ref": ref, "stall_flag": False, "location": "Midtown OKC",
         "holiday_window": "none", "close_ref": None}
    e.update(kw)
    return e


EVENTS = [
    ev("inv-0001", 3, "2026-11-05T10:00:00Z", ref="rcpt-0001", output="receipt rcpt-0001"),
    ev("inv-0001", 5, "2026-11-05T11:00:00Z", status="claimed-complete", ref="rcpt-0001"),
    ev("inv-0002", 3, "2026-11-05T10:00:00Z", status="failed", ref="rcpt-0002"),
    ev("inv-0002", 5, "2026-11-05T11:00:00Z", status="claimed-complete", ref="rcpt-0002"),
    ev("inv-0003", 5, "2026-11-05T11:00:00Z", status="claimed-complete", ref=None),
    ev("inv-0004", 3, "2026-11-05T12:30:00Z", ref="rcpt-0004"),
    ev("inv-0004", 5, "2026-11-05T11:00:00Z", status="claimed-complete", ref="rcpt-0004"),
    ev("inv-0005", 3, "2026-11-05T10:00:00Z", status="claimed-complete", ref="rcpt-0005"),
    ev("inv-0005", 5, "2026-11-05T11:00:00Z", status="claimed-complete", ref="rcpt-0005"),
]


def claim(case, step, ref, claimed="matched"):
    return {"case_id": case, "step_id": step, "claimed": claimed, "evidence_ref": ref}


class TestClaims(unittest.TestCase):
    def check(self, claims, **kw):
        from control.claims import check_claims
        return check_claims("run-001", "path-b", claims, EVENTS, **kw)

    def test_supported_when_evidence_exists_same_case_earlier_and_completed(self):
        r = self.check([claim("inv-0001", 5, "rcpt-0001")])
        self.assertEqual(r["claims"][0]["result"], "SUPPORTED")
        self.assertEqual((r["claims_total"], r["supported"], r["unsupported"], r["contradicted"]), (1, 1, 0, 0))
        self.assertEqual(_schemas.errors("claim_check.schema.json", r), [])
        self.assertEqual(r["recomputed_by"], "control_plane")

    def test_null_and_dangling_refs_are_unsupported_ATE4(self):
        r = self.check([claim("inv-0003", 5, None), claim("inv-0001", 5, "rcpt-9999"), claim("inv-0001", 5, "")])
        self.assertEqual([c["result"] for c in r["claims"]], ["UNSUPPORTED"] * 3)
        self.assertEqual(r["unsupported"], 3)

    def test_evidence_from_another_case_is_unsupported(self):
        r = self.check([claim("inv-0001", 5, "rcpt-0002")])
        self.assertEqual(r["claims"][0]["result"], "UNSUPPORTED")

    def test_evidence_that_postdates_the_claim_is_unsupported(self):
        r = self.check([claim("inv-0004", 5, "rcpt-0004")])
        self.assertEqual(r["claims"][0]["result"], "UNSUPPORTED")
        self.assertIn("postdates", r["claims"][0]["reason"])

    def test_evidence_from_a_later_step_is_unsupported(self):
        r = self.check([claim("inv-0001", 3, "rcpt-0001")])  # claimed at step 3 using step-3 evidence is fine
        self.assertEqual(r["claims"][0]["result"], "SUPPORTED")
        evs = EVENTS + [ev("inv-0006", 6, "2026-11-05T09:00:00Z", ref="x-0006"), ev("inv-0006", 4, "2026-11-05T10:00:00Z", status="claimed-complete", ref="x-0006")]
        from control.claims import check_claims
        r2 = check_claims("run-001", "path-b", [claim("inv-0006", 4, "x-0006")], evs)
        self.assertEqual(r2["claims"][0]["result"], "UNSUPPORTED")
        self.assertIn("later step", r2["claims"][0]["reason"])

    def test_evidence_that_records_a_failure_is_contradicted(self):
        r = self.check([claim("inv-0002", 5, "rcpt-0002")])
        self.assertEqual(r["claims"][0]["result"], "CONTRADICTED")
        self.assertEqual(r["contradicted"], 1)

    def test_evidence_that_is_itself_an_unevidenced_claim_is_unsupported(self):
        r = self.check([claim("inv-0005", 5, "rcpt-0005")])
        self.assertEqual(r["claims"][0]["result"], "UNSUPPORTED")

    def test_ground_truth_hook_can_contradict_an_otherwise_supported_claim(self):
        r = self.check([claim("inv-0001", 5, "rcpt-0001")], contradicts=lambda c, e: True)
        self.assertEqual(r["claims"][0]["result"], "CONTRADICTED")

    def test_unknown_claimed_step_cannot_be_checked_so_is_unsupported(self):
        r = self.check([claim("inv-0001", 7, "rcpt-0001")])
        self.assertEqual(r["claims"][0]["result"], "UNSUPPORTED")

    def test_verdict_holds_only_with_zero_unsupported_and_zero_contradicted(self):
        from control.claims import verdict
        self.assertEqual(verdict(self.check([claim("inv-0001", 5, "rcpt-0001")])), "CLAIMS_HOLD")
        self.assertEqual(verdict(self.check([claim("inv-0001", 5, "rcpt-0001"), claim("inv-0003", 5, None)])), "CLAIMS_FAIL")
        self.assertEqual(verdict(self.check([claim("inv-0002", 5, "rcpt-0002")])), "CLAIMS_FAIL")

    def test_claim_ids_are_assigned_unique_and_schema_valid(self):
        r = self.check([claim("inv-0001", 5, "rcpt-0001")] * 3)
        ids = [c["claim_id"] for c in r["claims"]]
        self.assertEqual(len(set(ids)), 3)
        self.assertEqual(_schemas.errors("claim_check.schema.json", r), [])

    def test_empty_claims_is_zero_not_a_pass_by_default(self):
        r = self.check([])
        self.assertEqual(r["claims_total"], 0)


class TestMetrics(unittest.TestCase):
    def test_recompute_against_ground_truth(self):
        from control.metrics import recompute
        out = {"flagged_cases": ["inv-1", "inv-2", "inv-3", "inv-9"], "manual_touch_cases": ["inv-1", "inv-1", "inv-4"]}
        cc = {"unsupported": 2, "contradicted": 1}
        m = recompute(out, truth_exception_cases={"inv-1", "inv-2", "inv-5"}, claim_check=cc)
        self.assertEqual(m["exceptions_caught"], 2)
        self.assertEqual(m["false_alarms"], 2)
        self.assertEqual(m["unsupported_claims"], 3)
        self.assertEqual(m["manual_touches"], 2)  # distinct cases
        self.assertNotIn("median_cycle_min", m)  # not invented: no timing model is defined (I-9)

    def test_median_cycle_only_from_an_explicit_per_case_map(self):
        from control.metrics import recompute
        m = recompute({"flagged_cases": [], "manual_touch_cases": []}, set(), {"unsupported": 0, "contradicted": 0},
                      cycle_min_by_case={"a": 10.0, "b": 30.0, "c": 20.0})
        self.assertEqual(m["median_cycle_min"], 20.0)

    def test_self_reported_never_used_and_discrepancy_flagged_ATE5(self):
        from control.metrics import discrepancy
        rec = {"exceptions_caught": 5, "false_alarms": 1}
        self.assertFalse(discrepancy({"exceptions_caught": 5}, rec))
        self.assertTrue(discrepancy({"exceptions_caught": 6}, rec))
        self.assertFalse(discrepancy(None, rec))
        self.assertTrue(discrepancy({"median_cycle_min": 1.0000011}, {"median_cycle_min": 1.0}))
        self.assertFalse(discrepancy({"median_cycle_min": 1.0000009}, {"median_cycle_min": 1.0}))

    def test_wrong_shapes_fail_closed(self):
        from control.metrics import MetricsError, recompute
        with self.assertRaises(MetricsError):
            recompute({"flagged_cases": "inv-1", "manual_touch_cases": []}, set(), {"unsupported": 0, "contradicted": 0})


if __name__ == "__main__":
    unittest.main()
