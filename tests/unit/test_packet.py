"""M5 packet builder tests (RED first). Interpretation I-12: packet_sha256 = SHA-256 of the canonical JSON (I-10 form) of the packet
without packet_sha256; packet.journal covers the entries that precede the entry which records the packet hash."""
import copy
import unittest

from tests.unit.test_broker import fixture

FULL = fixture("evidence_packet__valid.json")
INC = fixture("evidence_packet_incomplete__valid.json")


def ctx(**over):
    c = {
        "run_id": FULL["run_id"], "built_at": "2026-11-05T15:00:00Z",
        "dataset": FULL["dataset"], "mri": FULL["mri"], "scan": FULL["scan"], "council": FULL["council"],
        "rule": {"sha256": FULL["decision_rule"]["sha256"], "text": FULL["decision_rule"]["text"]},
        "executions": copy.deepcopy(FULL["executions"]),
        "rule_outcome": {"result": "PATH_PREFERRED_UNDER_ASSUMPTIONS", "preferred_path_id": "path-b", "basis": "best beats runner-up by 5 on exceptions_caught (frozen margin 3)"},
        "council_recommended_path_id": "path-b",
        "containment": {"stress_test_run": False, "stress_termination": None, "control_plane_heartbeat_gap_max_ms": None},
        "approval": {"status": "PENDING", "confirmed_at": None},
        "assurance_tier": "T0",
        "journal": {"head_sha256": "a" * 64, "entries": 20},
        "median_cycle_computed": False,
    }
    c.update(over)
    return c


class TestComplete(unittest.TestCase):
    def test_built_packet_validates_and_is_sealed(self):
        from broker import _schemas
        from control import packet
        p = packet.build_packet(ctx())
        self.assertEqual(_schemas.errors("evidence_packet.schema.json", p), [])
        self.assertEqual(p["packet_sha256"], packet.packet_hash(p))

    def test_rebuild_is_byte_identical(self):
        from control import packet
        a, b = packet.build_packet(ctx()), packet.build_packet(ctx())
        self.assertEqual(packet.dumps(a), packet.dumps(b))

    def test_any_change_breaks_the_hash(self):
        from control import packet
        p = packet.build_packet(ctx())
        p["outcome"]["preferred_path_id"] = "path-a"
        self.assertNotEqual(p["packet_sha256"], packet.packet_hash(p))

    def test_required_honesty_entries_always_present(self):
        from control import packet
        p = packet.build_packet(ctx())
        for s in ("that any intervention improves a real business", "that the synthetic data represents any real operation",
                  "that the sandbox is immune to container-escape vulnerabilities"):
            self.assertIn(s, p["did_not_prove"])
        self.assertIn("System-specific results are suppressed in public, by design, to protect the private association.", p["limitations"])
        self.assertIn("The deployed product computes only the overall index and performs no system-specific scoring.", p["limitations"])
        self.assertTrue(p["unknowns"] and p["assumptions"])

    def test_missing_median_cycle_is_stated_not_invented_I9(self):
        from control import packet
        p = packet.build_packet(ctx(median_cycle_computed=False))
        self.assertTrue(any("median_cycle_min" in u for u in p["unknowns"]))
        p2 = packet.build_packet(ctx(median_cycle_computed=True))
        self.assertFalse(any("median_cycle_min" in u for u in p2["unknowns"]))

    def test_rule_outcome_stands_when_council_disagrees_AT_E7(self):
        from control import packet
        p = packet.build_packet(ctx(council_recommended_path_id="path-a"))
        self.assertEqual(p["outcome"]["result"], "PATH_PREFERRED_UNDER_ASSUMPTIONS")
        self.assertEqual(p["outcome"]["preferred_path_id"], "path-b")
        self.assertIn("path-a", p["outcome"]["basis"])
        self.assertIn("rule outcome stands", p["outcome"]["basis"])

    def test_no_sufficient_evidence_has_no_preferred_path_AT_11(self):
        from broker import _schemas
        from control import packet
        p = packet.build_packet(ctx(rule_outcome={"result": "NO_SUFFICIENT_EVIDENCE", "preferred_path_id": None, "basis": "tie"},
                                    council_recommended_path_id="path-a"))
        self.assertEqual(_schemas.errors("evidence_packet.schema.json", p), [])
        self.assertIsNone(p["outcome"]["preferred_path_id"])

    def test_confirmed_packet_is_a_distinct_valid_packet_with_no_external_action(self):
        from broker import _schemas
        from control import packet
        pend = packet.build_packet(ctx())
        done = packet.build_packet(ctx(approval={"status": "VIEWED_CONFIRMED", "confirmed_at": "2026-11-05T15:10:00Z"},
                                       journal={"head_sha256": "b" * 64, "entries": 23}))
        self.assertEqual(_schemas.errors("evidence_packet.schema.json", done), [])
        self.assertNotEqual(pend["packet_sha256"], done["packet_sha256"])
        self.assertFalse(done["approval_gate"]["external_action_taken"])

    def test_fewer_than_two_executions_is_refused(self):
        from control import packet
        with self.assertRaises(packet.PacketError):
            packet.build_packet(ctx(executions=ctx()["executions"][:1]))

    def test_executed_lists_every_attempt_numbered(self):
        from control import packet
        p = packet.build_packet(ctx())
        self.assertEqual(len(p["executed"]), len(p["executions"]))
        self.assertTrue(all("attempt" in s for s in p["executed"]))


class TestIncomplete(unittest.TestCase):
    def inc(self, **over):
        c = {"run_id": INC["run_id"], "built_at": "2026-11-05T15:00:00Z", "failed_at": "COUNCIL_CRITIC",
             "failure_reason": "critic output could not be parsed",
             "dataset": INC["dataset"], "mri": INC["mri"], "scan": INC["scan"],
             "assurance_tier": "T0", "journal": {"head_sha256": "c" * 64, "entries": 9}}
        c.update(over)
        return c

    def test_incomplete_validates_and_is_sealed(self):
        from broker import _schemas
        from control import packet
        p = packet.build_incomplete(self.inc())
        self.assertEqual(_schemas.errors("evidence_packet_incomplete.schema.json", p), [])
        self.assertEqual(p["packet_sha256"], packet.packet_hash(p))
        self.assertEqual(p["outcome"]["result"], "NO_SUFFICIENT_EVIDENCE")
        self.assertIsNone(p["outcome"]["preferred_path_id"])

    def test_incomplete_states_failure_point_and_suppression_AT_04(self):
        from control import packet
        p = packet.build_incomplete(self.inc())
        self.assertTrue(any(l.startswith("Run failed closed at COUNCIL_CRITIC") for l in p["limitations"]))
        self.assertIn("System-specific results are suppressed in public, by design, to protect the private association.", p["limitations"])

    def test_incomplete_works_with_only_the_sections_that_exist(self):
        from broker import _schemas
        from control import packet
        c = self.inc(failed_at="MRI_DONE")
        for k in ("mri", "scan"):
            c.pop(k)
        p = packet.build_incomplete(c)
        self.assertEqual(_schemas.errors("evidence_packet_incomplete.schema.json", p), [])

    def test_basis_does_not_deny_a_comparison_when_receipts_exist_but_also_states_none_was_applied(self):
        from control import packet
        with_ex = packet.build_incomplete(self.inc(failed_at="EXEC_CORRECTION_2", executions=copy.deepcopy(FULL["executions"])))
        self.assertNotIn("no path was compared", with_ex["outcome"]["basis"])
        self.assertIn("receipts", with_ex["outcome"]["basis"])
        self.assertIn("was not applied", with_ex["outcome"]["basis"])
        without = packet.build_incomplete(self.inc())
        self.assertIn("no execution receipts", without["outcome"]["basis"])

    def test_incomplete_refuses_a_non_failure_state(self):
        from control import packet
        with self.assertRaises(packet.PacketError):
            packet.build_incomplete(self.inc(failed_at="PACKET_BUILT"))


if __name__ == "__main__":
    unittest.main()
