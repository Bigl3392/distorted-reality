"""Scanner self-test. Author-run. Deny-list needles are assembled in temp trees."""
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.public_safe_check import (
    LICENSE_TEXT,
    PS_IDS,
    _dotenv_value,
    gitignore_missing,
    readme_missing,
    redact,
    scan,
    summary_text,
    write_report,
)

ROOT = Path(__file__).resolve().parents[2]
CLEAN = Path(__file__).resolve().parent / "fixtures" / "clean"


def _j(*parts):
    return "".join(parts)


FEE = "SYNTHETIC_FEE_TOKEN"
EXACT = "SYNTHETIC_EXACT_MARKER"
MARKER = _j("SYNC", "_KEY")
PERSONA = _j("Dar", "la")
FRAME = _j("lane-", "marker-synth")
SCORING = "synthetic_scoring_config"
KEY = _j("sk-", "fakefakefakefakefake", "12")


def deny_text():
    return "\n".join([
        "phrase " + FEE,
        "exact " + MARKER,
        "exact " + EXACT,
        "persona " + PERSONA,
        "framing " + FRAME,
        "scoring-name " + SCORING,
        "",
    ])


class ScannerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tree = Path(self.tmp.name) / "tree"
        self.tree.mkdir()
        self.deny = Path(self.tmp.name) / "deny.list"
        self.deny.write_text(deny_text(), encoding="utf-8")
        shutil.copytree(CLEAN, self.tree / "clean")

    def tearDown(self):
        self.tmp.cleanup()

    def run_scan(self, **kw):
        return scan(self.tree, deny_list=str(self.deny), **kw)

    def rules(self, report):
        return {item["rule"] for item in report.findings}

    def test_clean_tree_has_zero_findings_and_pending_lock(self):
        # The copied clean fixture is the whole tree for this assertion.
        report = scan(self.tree / "clean", deny_list=str(self.deny))
        self.assertEqual(report.findings, [])
        self.assertEqual(report.pending[0]["item"], "docker_image.lock")
        self.assertEqual(report.pending[0]["status"], "PENDING")
        self.assertNotIn("PASS", report.pending[0]["status"])
        ids = [rec["ps_id"] for rec in report.records]
        self.assertEqual(ids, PS_IDS)

    def test_lowercase_sync_key_is_not_flagged(self):
        report = scan(self.tree / "clean", deny_list=str(self.deny))
        self.assertNotIn("PS2", self.rules(report))

    def test_exact_marker_is_flagged_and_lowercase_is_not(self):
        (self.tree / "a.txt").write_text("token " + MARKER + "\n", encoding="utf-8")
        (self.tree / "b.txt").write_text("token sync_key\n", encoding="utf-8")
        report = self.run_scan()
        flagged = [item["file"] for item in report.findings if item["rule"] == "PS2"]
        self.assertIn("a.txt", flagged)
        self.assertNotIn("b.txt", flagged)

    def test_fee_phrase_is_flagged(self):
        (self.tree / "fee.txt").write_text("cost " + FEE + "\n", encoding="utf-8")
        report = self.run_scan()
        self.assertIn("PS3", self.rules(report))

    def test_secret_value_is_redacted_in_every_output(self):
        (self.tree / "secret.txt").write_text("key=" + KEY + "\n", encoding="utf-8")
        known = Path(self.tmp.name) / "known.txt"
        known.write_text(KEY + "\n", encoding="utf-8")
        encoded = base64.b64encode(KEY.encode()).decode()
        (self.tree / "encoded.txt").write_text(encoded + "\n", encoding="utf-8")
        report = self.run_scan(known_values=str(known))
        self.assertIn("PS1", self.rules(report))
        out = Path(self.tmp.name) / "out"
        text = summary_text(report) + json.dumps(report.findings)
        write_report(report, out, "unit")
        dumped = text + (out / "findings.json").read_text(encoding="utf-8")
        dumped += (out / "summary.txt").read_text(encoding="utf-8")
        dumped += (out / "records.yaml").read_text(encoding="utf-8")
        self.assertNotIn(KEY, dumped)
        self.assertNotIn(encoded, dumped)
        self.assertIn("...", redact(KEY))

    def test_env_example_name_is_not_a_finding_when_empty(self):
        report = scan(self.tree / "clean", deny_list=str(self.deny))
        self.assertNotIn("PS1", self.rules(report))

    def test_non_empty_secret_class_value_is_a_finding(self):
        (self.tree / ".env.example").write_text(
            "VULTR_INFERENCE_API_KEY=" + KEY + "\nDR_OPERATOR_TOKEN=\n",
            encoding="utf-8",
        )
        report = self.run_scan()
        self.assertIn("PS1", self.rules(report))
        blob = json.dumps(report.findings)
        self.assertNotIn(KEY, blob)

    def test_mount_path_ground_truth_persona_scoring_claim_session(self):
        (self.tree / "path.txt").write_text("see /mnt/c/somewhere\n", encoding="utf-8")
        (self.tree / "ground_truth.json").write_text("{}\n", encoding="utf-8")
        (self.tree / "who.txt").write_text(PERSONA + "\n", encoding="utf-8")
        (self.tree / "cfg.txt").write_text("path=" + SCORING + "\n", encoding="utf-8")
        (self.tree / "claim.txt").write_text("This will improve the close.\n", encoding="utf-8")
        (self.tree / "link.txt").write_text("https://example.com/session/abc\n", encoding="utf-8")
        report = self.run_scan()
        rules = self.rules(report)
        self.assertTrue({"PS9", "PS10", "PS12", "PS15"} <= rules)

    def test_provider_marker_and_answers_object(self):
        (self.tree / "provider.txt").write_text(_j("Back", "board") + "\n", encoding="utf-8")
        (self.tree / "public.json").write_text('{"answers": {"a": 1}}\n', encoding="utf-8")
        report = self.run_scan()
        self.assertIn("PS4", self.rules(report))
        self.assertIn("PS20", self.rules(report))

    def test_invalid_fixture_name_is_review_not_a_finding(self):
        name = "scan_result__INVALID_answers_object_present.json"
        (self.tree / name).write_text('{"answers": {"a": 1}}\n', encoding="utf-8")
        report = self.run_scan()
        self.assertNotIn("PS20", self.rules(report))
        self.assertEqual(len(report.review_items), 1)

    def test_license_bytes_and_a_broken_copy(self):
        good = self.tree / "LICENSE"
        good.write_bytes(LICENSE_TEXT.encode("utf-8"))
        report = self.run_scan()
        rec = {item["ps_id"]: item for item in report.records}
        self.assertEqual(rec["PS18"]["result"], "PASS")
        good.write_text(LICENSE_TEXT + "x", encoding="utf-8")
        report = self.run_scan()
        rec = {item["ps_id"]: item for item in report.records}
        self.assertEqual(rec["PS18"]["result"], "FAIL")

    def test_readme_sections_and_gitignore(self):
        text = "\n".join("# " + title for title in (
            "One-paragraph summary", "Demo", "What it does", "Vultr services used",
            "Architecture", "Containment", "Evidence packet", "Synthetic data statement",
            "What this does not prove", "Setup", "Reuse and originality disclosure",
            "Limitations", "License",
        ))
        self.assertEqual(readme_missing(text), [])
        self.assertEqual(len(readme_missing("")), 13)
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertEqual(gitignore_missing(ignore), [])

    def test_unpinned_requirement_fails_ps13(self):
        (self.tree / "requirements.txt").write_text("something latest\n", encoding="utf-8")
        report = self.run_scan()
        rec = {item["ps_id"]: item for item in report.records}
        self.assertEqual(rec["PS13"]["result"], "FAIL")

    def test_prior_package_identical_file(self):
        body = b"same-bytes\n"
        (self.tree / "copied.py").write_bytes(body)
        package = Path(self.tmp.name) / "prior"
        package.mkdir()
        (package / "copied.py").write_bytes(body)
        report = self.run_scan(prior_package=str(package))
        self.assertIn("PS6", self.rules(report))

    def test_archive_and_screenshot_leak(self):
        buf = Path(self.tmp.name) / "release.zip"
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("note.txt", KEY)
        shutil.copy(buf, self.tree / "release.zip")
        (self.tree / "shot.png").write_text(MARKER, encoding="utf-8")
        pdf = b"%PDF-1.1\n1 0 obj\n<< /Author (" + MARKER.encode() + b") >>\nendobj\n%%EOF\n"
        (self.tree / "slide.pdf").write_bytes(pdf)
        report = self.run_scan()
        rules = self.rules(report)
        self.assertIn("PS1", rules)
        self.assertIn("PS2", rules)
        blob = json.dumps(report.findings)
        self.assertNotIn(KEY, blob)

    def test_history_finds_a_removed_branch_value(self):
        repo = Path(self.tmp.name) / "hist"
        repo.mkdir()
        (repo / "note.txt").write_text("clean\n", encoding="utf-8")
        env = os.environ.copy()
        env["GIT_AUTHOR_NAME"] = "Fixture"
        env["GIT_AUTHOR_EMAIL"] = "fixture@example.com"
        env["GIT_COMMITTER_NAME"] = "Fixture"
        env["GIT_COMMITTER_EMAIL"] = "fixture@example.com"
        def git(*args):
            subprocess.run(["git", "-C", str(repo), *args], check=True, env=env, capture_output=True)
        git("init", "-b", "main")
        git("add", "note.txt")
        git("commit", "-m", "clean")
        git("checkout", "-b", "old")
        (repo / "note.txt").write_text(KEY + "\n", encoding="utf-8")
        git("add", "note.txt")
        git("commit", "-m", "leak")
        git("checkout", "main")
        report = scan(repo, deny_list=str(self.deny), history=True)
        self.assertIn("PS16", {item["rule"] for item in report.findings})
        rec = {item["ps_id"]: item for item in report.records}
        self.assertEqual(rec["PS16"]["result"], "FAIL")
        blob = json.dumps(report.findings)
        self.assertNotIn(KEY, blob)

    def test_cli_clean_exit_zero(self):
        out = Path(self.tmp.name) / "cli-out"
        proc = subprocess.run(
            [sys.executable, "-I", str(ROOT / "scripts" / "public_safe_check.py"),
             str(self.tree / "clean"), "--deny-list", str(self.deny), "--out", str(out)],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("findings=0", proc.stdout)
        self.assertTrue((out / "records.yaml").is_file())
        self.assertNotIn(KEY, proc.stdout)

    def test_product_root_files(self):
        lic = (ROOT / "LICENSE").read_bytes()
        self.assertEqual(lic, LICENSE_TEXT.encode("utf-8"))
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        for name in ("VULTR_INFERENCE_API_KEY", "DR_OPERATOR_TOKEN"):
            for line in example.splitlines():
                if line.startswith(name + "="):
                    self.assertEqual(_dotenv_value(line.split("=", 1)[1]), "")
        self.assertIn("https://api.vultrinference.com/v1", example)
        self.assertFalse((ROOT / "docker_image.lock").exists())
        copied = Path(self.tmp.name) / "env-example"
        copied.mkdir()
        (copied / ".env.example").write_text(example, encoding="utf-8")
        report = scan(copied, deny_list=str(self.deny))
        self.assertEqual(report.findings, [])


if __name__ == "__main__":
    unittest.main()
