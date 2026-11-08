"""Acceptance and falsifier tests for tools/verify_packet.py (M9).

Author-run only until Peggy Sue validates. Builds journals via I-10; does not
trust frozen fixture placeholder hashes.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.tests.helpers import (
    SCHEMA_RULE,
    build_complete_bundle,
    build_incomplete_bundle,
    canonical_json,
    hash_entry,
    sha256_hex,
)
from tools import verify_packet

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY = REPO_ROOT / "tools" / "verify_packet.py"


class TestJournalCanonicalForm(unittest.TestCase):
    def test_entry_hash_is_sha256_of_sorted_compact_json_excluding_entry_sha256(self) -> None:
        entry = {
            "seq": 0,
            "ts": "2026-11-05T15:00:00Z",
            "run_id": "run-m9t1",
            "kind": "run_created",
            "actor": "control",
            "data": {},
            "prev_sha256": "0" * 64,
            "entry_sha256": "deadbeef",
        }
        expected = sha256_hex(
            canonical_json({k: v for k, v in entry.items() if k != "entry_sha256"})
        )
        self.assertEqual(hash_entry(entry), expected)


class TestATE1ValidPacket(unittest.TestCase):
    def test_at_e1_valid_packet_fixture_exits_0(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = build_complete_bundle(Path(tmp) / "ok")
            report = verify_packet.verify(bundle)
            self.assertTrue(report.ok, msg="\n".join(report.lines))
            self.assertEqual(report.exit_code, 0)
            joined = "\n".join(report.lines)
            self.assertIn("scan result: NOT INDEPENDENTLY RECOMPUTED", joined)

    def test_at_e1_cli_exits_0(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = build_complete_bundle(Path(tmp) / "ok")
            proc = subprocess.run(
                [sys.executable, "-W", "error", str(VERIFY), str(bundle)],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
            self.assertIn("scan result: NOT INDEPENDENTLY RECOMPUTED", proc.stdout)

    def test_at_e1_falsifier_broken_packet_hash_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = build_complete_bundle(Path(tmp) / "badhash")
            packet_path = bundle / "packet.json"
            packet = json.loads(packet_path.read_text(encoding="ascii"))
            packet["packet_sha256"] = "0" * 64
            packet_path.write_text(
                json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
                + "\n",
                encoding="ascii",
            )
            report = verify_packet.verify(bundle)
            self.assertFalse(report.ok)
            self.assertNotEqual(report.exit_code, 0)


class TestATE2AndE19TamperedJournal(unittest.TestCase):
    def test_at_e2_flip_journal_byte_nonzero_names_seq(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = build_complete_bundle(Path(tmp) / "flip", tamper_journal_seq=2)
            report = verify_packet.verify(bundle)
            self.assertFalse(report.ok)
            self.assertNotEqual(report.exit_code, 0)
            joined = "\n".join(report.lines)
            self.assertRegex(joined, r"seq\s*[=:]?\s*2|first bad seq.*2|bad seq 2")

    def test_at_e19_tampered_journal_line_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = build_complete_bundle(Path(tmp) / "tamp", tamper_journal_seq=1)
            report = verify_packet.verify(bundle)
            self.assertFalse(report.ok)
            self.assertNotEqual(report.exit_code, 0)
            joined = "\n".join(report.lines)
            self.assertRegex(joined, r"seq\s*[=:]?\s*1|first bad seq.*1|bad seq 1")

    def test_at_e2_falsifier_untampered_must_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = build_complete_bundle(Path(tmp) / "clean")
            report = verify_packet.verify(bundle)
            self.assertTrue(report.ok, msg="\n".join(report.lines))


class TestATE3DecisionRule(unittest.TestCase):
    def test_at_e3_change_decision_rule_after_freeze_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = build_complete_bundle(Path(tmp) / "rule", alter_rule=True)
            report = verify_packet.verify(bundle)
            self.assertFalse(report.ok)
            self.assertNotEqual(report.exit_code, 0)
            joined = "\n".join(report.lines).lower()
            self.assertTrue(
                "decision_rule" in joined or "rule" in joined,
                msg=joined,
            )

    def test_at_e3_falsifier_unchanged_rule_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = build_complete_bundle(Path(tmp) / "ruleok")
            # Prove the on-disk rule matches the frozen schema file bytes.
            self.assertEqual(
                (bundle / "decision_rule.yaml").read_bytes(),
                SCHEMA_RULE.read_bytes(),
            )
            report = verify_packet.verify(bundle)
            self.assertTrue(report.ok, msg="\n".join(report.lines))


class TestATE4ClaimRerun(unittest.TestCase):
    def test_at_e4_dangling_evidence_ref_is_unsupported(self) -> None:
        from tools.verify_packet import evaluate_claim

        events = [
            {
                "case_id": "inv-0001",
                "step_id": 1,
                "status": "completed",
                "evidence_ref": "other",
                "timestamp": "2026-11-05T15:00:00Z",
            }
        ]
        claim = {
            "claim_id": "clm-x",
            "case_id": "inv-0001",
            "step_id": 1,
            "evidence_ref": "missing-ref",
            "claimed": "done",
        }
        self.assertEqual(evaluate_claim(claim, events), "UNSUPPORTED")

    def test_at_e4_falsifier_matching_evidence_is_supported(self) -> None:
        from tools.verify_packet import evaluate_claim

        events = [
            {
                "case_id": "inv-0001",
                "step_id": 1,
                "status": "completed",
                "evidence_ref": "ev-0001",
                "timestamp": "2026-11-05T15:00:00Z",
            }
        ]
        claim = {
            "claim_id": "clm-x",
            "case_id": "inv-0001",
            "step_id": 1,
            "evidence_ref": "ev-0001",
            "claimed": "done",
        }
        self.assertEqual(evaluate_claim(claim, events), "SUPPORTED")


class TestATE5MetricsDiscrepancy(unittest.TestCase):
    def test_at_e5_hidden_discrepancy_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = build_complete_bundle(Path(tmp) / "disc", hide_discrepancy=True)
            report = verify_packet.verify(bundle)
            self.assertFalse(report.ok)
            self.assertNotEqual(report.exit_code, 0)
            joined = "\n".join(report.lines).lower()
            self.assertIn("discrepan", joined)

    def test_at_e5_falsifier_honest_discrepancy_flag_passes_integrity(self) -> None:
        # When values match and discrepancy is false, integrity holds.
        with tempfile.TemporaryDirectory() as tmp:
            bundle = build_complete_bundle(Path(tmp) / "nodisc")
            report = verify_packet.verify(bundle)
            self.assertTrue(report.ok, msg="\n".join(report.lines))


class TestATE11Incomplete(unittest.TestCase):
    def test_at_e11_incomplete_valid_exits_0_and_prints_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = build_incomplete_bundle(Path(tmp) / "inc")
            report = verify_packet.verify(bundle)
            self.assertTrue(report.ok, msg="\n".join(report.lines))
            self.assertEqual(report.exit_code, 0)
            joined = "\n".join(report.lines)
            self.assertIn(
                "INCOMPLETE: no outcome other than NO_SUFFICIENT_EVIDENCE is possible",
                joined,
            )
            self.assertIn("scan result: NOT INDEPENDENTLY RECOMPUTED", joined)

    def test_incomplete_without_decision_rule_section_rule_file_not_checked(self) -> None:
        """Conventions §3 clarified 2026-11-05: INCOMPLETE + no decision_rule => NOT CHECKED."""
        with tempfile.TemporaryDirectory() as tmp:
            bundle = build_incomplete_bundle(
                Path(tmp) / "inc-no-rule",
                include_decision_rule=False,
                include_rule_file=True,
                rule_file_bytes=b"rule_id: not-the-packet-rule\n",
            )
            report = verify_packet.verify(bundle)
            self.assertTrue(report.ok, msg="\n".join(report.lines))
            self.assertEqual(report.exit_code, 0)
            joined = "\n".join(report.lines)
            self.assertIn("NOT CHECKED", joined)
            self.assertRegex(
                joined,
                r"NOT CHECKED:.*decision_rule",
            )
            self.assertNotRegex(joined, r"FAIL:.*decision_rule")

    def test_incomplete_without_decision_rule_section_missing_rule_file_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = build_incomplete_bundle(
                Path(tmp) / "inc-no-rulefile",
                include_decision_rule=False,
                include_rule_file=False,
            )
            report = verify_packet.verify(bundle)
            self.assertTrue(report.ok, msg="\n".join(report.lines))
            self.assertEqual(report.exit_code, 0)

    def test_at_e11_falsifier_tampered_incomplete_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = build_incomplete_bundle(Path(tmp) / "incbad", tamper=True)
            report = verify_packet.verify(bundle)
            self.assertFalse(report.ok)
            self.assertNotEqual(report.exit_code, 0)


class TestATE10SchemaFixtures(unittest.TestCase):
    def test_at_e10_validate_schemas_zero_failures(self) -> None:
        script = REPO_ROOT / "schemas" / "validate_schemas.py"
        if not script.is_file():
            self.skipTest("validate_schemas.py not present")
        proc = subprocess.run(
            [sys.executable, "-W", "error", str(script)],
            cwd=str(REPO_ROOT / "schemas"),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)

    def test_at_e10_falsifier_invalid_fixture_name_exists(self) -> None:
        fixtures = REPO_ROOT / "schemas" / "fixtures"
        invalids = list(fixtures.glob("*INVALID*"))
        self.assertGreater(len(invalids), 0, "expected INVALID schema fixtures as falsifiers")


class TestExceptionsCaughtNotRecomputed(unittest.TestCase):
    def test_report_states_exceptions_caught_not_recomputed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = build_complete_bundle(Path(tmp) / "gt")
            report = verify_packet.verify(bundle)
            joined = "\n".join(report.lines).lower()
            self.assertTrue(
                "exceptions_caught" in joined and ("not" in joined or "cannot" in joined),
                msg=joined,
            )


if __name__ == "__main__":
    unittest.main()
