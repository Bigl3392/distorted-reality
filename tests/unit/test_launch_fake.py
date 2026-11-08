"""The fake-backed loopback launcher serves the real M5 app over real HTTP on 127.0.0.1 and tears down cleanly. Fakes only."""
import unittest

from tests.fakes import flow_trace


class TestLauncher(unittest.TestCase):
    def test_complete_scenario_over_real_loopback_http_and_clean_teardown(self):
        trace, r = flow_trace.flow("complete")
        self.assertEqual((r["healthz"], r["create"], r["intake"], r["start"]), (200, 201, 200, 202))
        self.assertEqual(r["state"], "AWAITING_APPROVAL")
        self.assertEqual(r["packet"]["outcome"]["preferred_path_id"], "path-a")
        self.assertEqual(r["confirmed"]["approval_gate"]["status"], "VIEWED_CONFIRMED")
        self.assertEqual(r["root_status"], 200)
        self.assertEqual(r["teardown"], {"exit_code": 0, "tmp_dir_removed": True})
        self.assertTrue(r["manifest"]["base_url"].startswith("http://127.0.0.1:"))

    def test_incomplete_and_refusal_and_unset_limits_controls(self):
        _, inc = flow_trace.flow("incomplete")
        self.assertEqual(inc["state"], "FAILED_CLOSED")
        self.assertEqual(inc["packet"]["packet_status"], "INCOMPLETE")
        _, ref = flow_trace.flow("refusal")
        self.assertEqual(ref["start"], 409)
        self.assertEqual(ref["start_body"]["mode"], "recorded")
        self.assertEqual(ref["start_body"]["recorded_runs"], [])
        _, uns = flow_trace.flow("complete", per_ip="UNSET", ttl="UNSET")
        self.assertEqual(uns["create"], 503)

    def test_tie_and_correction_controls(self):
        _, tie = flow_trace.flow("tie")
        self.assertEqual(tie["packet"]["outcome"]["result"], "NO_SUFFICIENT_EVIDENCE")
        _, cor = flow_trace.flow("correction")
        self.assertIn(("path-a", 2), cor["attempts"])

    def test_launcher_refuses_a_missing_limit_argument(self):
        import subprocess, sys
        r = subprocess.run([sys.executable, "-m", "tests.fakes.launch_fake", "--scenario", "complete"], cwd=flow_trace.ROOT,
                           capture_output=True, text=True, timeout=60)
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
