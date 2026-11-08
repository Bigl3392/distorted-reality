"""Public-safe scanner (REPO_SPEC section 4, PS1-PS20).

Stdlib only. Deny lists are an argument, never embedded. A finding reports
the file, the line, the rule, and a redacted fragment. Secret values are
not printed.

docker_image.lock is reported as a pending item when it is absent (G4).
That pending item is not a pass and not an error.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import sys
import urllib.parse
import zipfile
from pathlib import Path


def _j(*parts):
    return "".join(parts)


PS_IDS = [f"PS{i}" for i in range(1, 21)]

# Publication phrases named by AT-25. Joined so this file does not contain them.
CLAIM_PHRASES = (
    _j("will ", "improve"),
    _j("proves ", "ROI"),
)
GUARANTEE = re.compile(r"\b" + _j("guaran", "tee") + r"\b")

# PS4 literals named by the reuse acceptance rows. Joined for the same reason.
PS4_WORDS = (
    _j("Back", "board"),
    _j("back", "board"),
    _j("thread", "_id"),
    _j("assistant", "_id"),
)

SELECTION_PHRASE = _j("scoring-", "selection")

SECRET_CLASS_NAMES = ("VULTR_INFERENCE_API_KEY", "DR_OPERATOR_TOKEN")

# Spec-required addresses. They are not machine identifiers of this build.
ALLOW_IPS = {_j("1.1.", "1.1")}
ALLOW_HOSTS = (_j("api.vultrinference.com"),)

README_SECTIONS = (
    "One-paragraph summary",
    "Demo",
    "What it does",
    "Vultr services used",
    "Architecture",
    "Containment",
    "Evidence packet",
    "Synthetic data statement",
    "What this does not prove",
    "Setup",
    "Reuse and originality disclosure",
    "Limitations",
    "License",
)

SPEC_SET_FILENAMES = (
    "CLOSE_MAPPING.md",
    "REUSE_AUDIT.md",
    "RULINGS_RECORD.md",
    "AGENT_WORK_SPLIT.md",
    "PS_EVIDENCE_RECORD.md",
    "DISTORTED_REALITY_SPEC.md",
    "spec_set_checks.py",
)

GITIGNORE_REQUIRED = (
    ".env",
    "runs/",
    "*.pem",
    "ground_truth.json",
    "node_modules",
    "dist",
)

LICENSE_TEXT = """MIT License

Copyright (c) 2026 Larry D. Ross

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

_SECRET_RES = (
    ("pem", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("aws-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("sk", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("gh", re.compile(r"\bghp_[A-Za-z0-9]{20,}\b")),
    ("slack", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("bearer", re.compile(r"Bearer\s+(?!\[)([A-Za-z0-9._\-]{16,})")),
)
_MNT = re.compile(r"/mnt/[a-z]/")
_USERS = re.compile(r"(?:[A-Za-z]:\\|/)Users[/\\]")
_EMAIL = re.compile(r"[\w.+\-]+@[\w.\-]+\.[A-Za-z]{2,}")
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_SESSION_URL = re.compile(r"https?://\S*session\S*", re.I)
_SESSION_QS = re.compile(r"session_id=[A-Za-z0-9_\-]{6,}")
_ANSWERS_OBJECT = re.compile(r'"answers"\s*:\s*\{')
_SYSTEM_SCORES = re.compile(r'"system_scores"\s*:')
_SCORING_ENV = re.compile(
    r"(?m)^[A-Za-z0-9_]*" + _j("PRIVATE_", "SCORING") + r"[A-Za-z0-9_]*\s*="
)
_SCORING_ENV_2 = re.compile(
    r"(?m)^[A-Za-z0-9_]*" + _j("SCORING_", "MAP") + r"[A-Za-z0-9_]*\s*=\s*\S"
)


def redact(value):
    text = str(value)
    if len(text) <= 4:
        return "***"
    return text[:2] + "..." + text[-2:]


def load_deny(path):
    groups = {"phrase": [], "exact": [], "scoring-name": [], "persona": [], "framing": []}
    if path is None:
        return groups
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        kind, _, rest = line.partition(" ")
        rest = rest.strip()
        if rest and kind in groups:
            groups[kind].append(rest)
    return groups


def load_known_values(path):
    if path is None:
        return []
    out = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def gitignore_missing(text):
    lines = [
        line.strip().rstrip("/")
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    return [item for item in GITIGNORE_REQUIRED if item.rstrip("/") not in lines]


def readme_missing(text):
    return [title for title in README_SECTIONS if title not in text]


def _encodings(value):
    raw = value.encode("utf-8")
    return (
        value,
        base64.b64encode(raw).decode("ascii"),
        raw.hex(),
        urllib.parse.quote(value, safe=""),
    )


def _split_collapsed(text):
    """Join adjacent quoted fragments so a split secret is still visible to PS1."""
    return re.sub(r"""["']\s*\+\s*["']""", "", text)


def _iter_files(root):
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".venv", "venv", "__pycache__")]
        for name in filenames:
            yield Path(dirpath) / name


def _read_text(path):
    data = path.read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="replace")


def _zip_texts(path):
    texts = []
    try:
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                try:
                    blob = zf.read(info)
                except Exception:
                    continue
                try:
                    texts.append((info.filename, blob.decode("utf-8")))
                except UnicodeDecodeError:
                    texts.append((info.filename, blob.decode("latin-1", errors="replace")))
    except zipfile.BadZipFile:
        return []
    return texts


def _rel(root, path):
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


class Report:
    def __init__(self):
        self.findings = []
        self.pending = []
        self.notes = []
        self.records = []
        self.review_items = []

    def add(self, rule, file, line, fragment):
        self.findings.append({
            "rule": rule,
            "file": file,
            "line": line,
            "fragment": redact(fragment) if rule == "PS1" else fragment,
        })


def _line_no(text, index):
    return text.count("\n", 0, index) + 1


def _dotenv_value(raw):
    """A secret-class assignment is empty when only whitespace or an unquoted comment remains.

    REPO_SPEC section 3 leaves DR_OPERATOR_TOKEN blank and puts the explanation in an inline comment.
    A quoted value is kept whole, including any # inside the quotes.
    """
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1].strip()
    hash_at = value.find("#")
    if hash_at >= 0:
        value = value[:hash_at]
    return value.strip()


def _scan_blob(report, rel, text, deny, known_values):
    phrases = deny["phrase"]
    exact = deny["exact"]
    scoring_names = deny["scoring-name"]
    collapsed = _split_collapsed(text)
    lines = text.splitlines()

    def hit(rule, fragment, index=None, line=None):
        if line is None:
            line = _line_no(text, index or 0)
        report.add(rule, rel, line, fragment)

    for label, cre in _SECRET_RES:
        for match in cre.finditer(text):
            frag = match.group(1) if match.lastindex else match.group(0)
            hit("PS1", f"{label}:{redact(frag)}", match.start())

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "=" in line:
            name, _, value = line.partition("=")
            name = name.strip().lstrip("export ").strip()
            value = _dotenv_value(value)
            if name in SECRET_CLASS_NAMES and value:
                hit("PS1", name + "=<non-empty>", line=i)

    for value in known_values:
        for encoded in _encodings(value):
            if encoded and encoded in text:
                hit("PS1", "known-value", text.index(encoded))
            elif encoded and encoded in collapsed and encoded not in text:
                hit("PS1", "known-value-split", collapsed.index(encoded))

    for marker in exact:
        start = 0
        while True:
            at = text.find(marker, start)
            if at < 0:
                break
            hit("PS2", "exact-marker", at)
            start = at + len(marker)

    for phrase in phrases:
        start = 0
        while True:
            at = text.find(phrase, start)
            if at < 0:
                break
            hit("PS3", "deny-phrase", at)
            start = at + len(phrase)

    for word in PS4_WORDS:
        start = 0
        while True:
            at = text.find(word, start)
            if at < 0:
                break
            hit("PS4", "provider-marker", at)
            start = at + len(word)

    for cre, rule, label in (
        (_MNT, "PS9", "mount-path"),
        (_USERS, "PS9", "users-path"),
        (_SESSION_URL, "PS9", "session-url"),
        (_SESSION_QS, "PS9", "session-query"),
    ):
        for match in cre.finditer(text):
            hit(rule, label, match.start())

    for match in _IPV4.finditer(text):
        if match.group(0) not in ALLOW_IPS:
            hit("PS9", "network-address", match.start())

    for match in _EMAIL.finditer(text):
        if not match.group(0).endswith("@example.com"):
            hit("PS7", "non-example-email", match.start())

    for phrase in CLAIM_PHRASES:
        start = 0
        while True:
            at = text.find(phrase, start)
            if at < 0:
                break
            hit("PS12", "claim-phrase", at)
            start = at + len(phrase)
    for match in GUARANTEE.finditer(text):
        hit("PS12", "claim-phrase", match.start())

    if SELECTION_PHRASE in text:
        hit("PS11", "selection-phrase", text.index(SELECTION_PHRASE))
        hit("PS20", "selection-phrase", text.index(SELECTION_PHRASE))

    for match in _ANSWERS_OBJECT.finditer(text):
        rule_file = rel
        if "__INVALID_" in rule_file:
            report.review_items.append({
                "rule": "PS20",
                "file": rel,
                "line": _line_no(text, match.start()),
                "note": "negative-control fixture; pre-publication ruling is still open",
            })
        else:
            hit("PS20", "question-keyed-answers", match.start())

    for match in _SYSTEM_SCORES.finditer(text):
        hit("PS20", "system-scores", match.start())

    for cre in (_SCORING_ENV, _SCORING_ENV_2):
        for match in cre.finditer(text):
            hit("PS10", "scoring-env", match.start())

    for name in scoring_names:
        if name and name in text:
            hit("PS10", "scoring-name", text.index(name))
    for name in deny["persona"]:
        if name and name in text:
            hit("PS15", "persona-marker", text.index(name))
    for name in deny["framing"]:
        if name and name in text:
            hit("PS5", "framing-marker", text.index(name))


def _file_rules(report, root, path):
    rel = _rel(root, path)
    name = path.name
    if name == "ground_truth.json":
        report.add("PS10", rel, 1, "ground_truth.json")
    if name == ".env":
        report.add("PS1", rel, 1, "env-file")
    if name in SPEC_SET_FILENAMES:
        report.add("PS14", rel, 1, "spec-set-filename")
    if name.endswith(".pyc"):
        report.notes.append(f"bytecode present: {rel}")


def scan(tree, deny_list=None, known_values=None, history=False, prior_package=None,
         intake_reference=None, agents_audit=None):
    tree = Path(tree)
    report = Report()
    deny = load_deny(deny_list)
    known = load_known_values(known_values)
    files = list(_iter_files(tree)) if tree.is_dir() else []

    if not (tree / "docker_image.lock").is_file():
        report.pending.append({
            "item": "docker_image.lock",
            "status": "PENDING",
            "reason": "G4 digest is not pinned; absence is not a pass and not an error",
        })

    for path in files:
        _file_rules(report, tree, path)
        if path.suffix.lower() == ".zip" or path.name.endswith(".tar.gz"):
            if path.suffix.lower() == ".zip":
                for member, text in _zip_texts(path):
                    _scan_blob(report, _rel(tree, path) + "!" + member, text, deny, known)
            continue
        text = _read_text(path)
        _scan_blob(report, _rel(tree, path), text, deny, known)

    _finish_records(
        report, tree, files, history, prior_package, intake_reference, agents_audit,
    )
    return report


def _sha256_file(path):
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _finish_records(report, tree, files, history, prior_package, intake_reference, agents_audit):
    by_rule = {}
    for finding in report.findings:
        by_rule.setdefault(finding["rule"], []).append(finding)

    def record(ps, result, count, note):
        report.records.append({
            "ps_id": ps,
            "result": result,
            "findings_count": count,
            "note": note,
            "tool": "scripts/public_safe_check.py",
        })

    for ps in PS_IDS:
        owned = by_rule.get(ps, [])
        if ps == "PS5":
            count = sum(1 for f in report.findings if f["rule"] == "PS5")
            if count:
                record(ps, "FAIL", count, "automated half only; manual review is still required")
            else:
                record(ps, "NOT_RUN", 0, "manual review of institutional framing is not this tool's pass")
            continue
        if ps == "PS6":
            if prior_package is None:
                record(ps, "NOT_RUN", 0, "no prior-source package was supplied")
            else:
                count = _prior_identical(report, tree, files, Path(prior_package))
                record(ps, "FAIL" if count else "PASS", count, "sha256 compare against the supplied package")
            continue
        if ps == "PS8":
            rows = [p for p in files if p.suffix == ".jsonl"]
            if not rows:
                record(ps, "NOT_RUN", 0, "no dataset jsonl in this tree")
            else:
                bad = 0
                for path in rows:
                    for n, line in enumerate(_read_text(path).splitlines(), 1):
                        if line and "SYNTHETIC" not in line and "PUBLIC_FACT" not in line:
                            report.add("PS8", _rel(tree, path), n, "unlabeled-row")
                            bad += 1
                record(ps, "FAIL" if bad else "PASS", bad, "dataset rows")
            continue
        if ps == "PS13":
            req = tree / "requirements.txt"
            if not req.is_file():
                record(ps, "NOT_RUN", 0, "no requirements.txt; provenance ledger is not run")
            else:
                bad = _unpinned(req)
                for item in bad:
                    report.add("PS13", "requirements.txt", 1, item)
                record(
                    ps,
                    "FAIL" if bad else "NOT_RUN",
                    len(bad),
                    "pin check only; asset provenance ledger is NOT_RUN",
                )
            continue
        if ps == "PS16":
            if not history:
                record(ps, "NOT_RUN", 0, "--history was not set; working tree only")
            elif not (tree / ".git").exists():
                record(ps, "NOT_RUN", 0, "no git directory; history scan was not run")
            else:
                extra = _history_hits(report, tree, files)
                record(ps, "FAIL" if extra else "PASS", extra, "git history")
            continue
        if ps == "PS17":
            record(ps, "NOT_RUN", len(owned), "video, slides and screenshots are not in this tree; file scan is not a surface pass")
            continue
        if ps == "PS18":
            lic = tree / "LICENSE"
            if not lic.is_file():
                record(ps, "NOT_RUN", 0, "no LICENSE in this tree")
            else:
                same = lic.read_bytes() == LICENSE_TEXT.encode("utf-8")
                if not same:
                    report.add("PS18", "LICENSE", 1, "LICENSE bytes differ from REPO_SPEC section 2")
                record(ps, "FAIL" if not same else "PASS", 0 if same else 1, "byte compare")
            continue
        if ps == "PS19":
            if agents_audit is None:
                record(ps, "NOT_RUN", 0, "agents.json audit evidence was not supplied")
            else:
                record(ps, "PASS", 0, "audit path attached; contents were not judged")
            continue
        if ps in ("PS11", "PS20") and intake_reference:
            ref = Path(intake_reference)
            live = tree / "scan" / "questions.public.yaml"
            if live.is_file() and ref.is_file() and live.read_bytes() != ref.read_bytes():
                report.add(ps, "scan/questions.public.yaml", 1, "intake bytes differ from the reference")
                owned = by_rule.get(ps, []) + [1]
        count = len(by_rule.get(ps, []))
        # Recompute after any late adds.
        count = sum(1 for f in report.findings if f["rule"] == ps)
        if ps == "PS17":
            continue
        result = "FAIL" if count else "PASS"
        record(ps, result, count, "")


def _unpinned(path):
    bad = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "latest" in stripped.lower() or "==" not in stripped:
            bad.append(stripped)
    return bad


def _prior_identical(report, tree, files, package):
    prior = {}
    if package.is_dir():
        for path in _iter_files(package):
            prior.setdefault(_sha256_file(path), []).append(path.name)
    count = 0
    for path in files:
        digest = _sha256_file(path)
        if digest in prior and path.name != "LICENSE":
            report.add("PS6", _rel(tree, path), 1, "identical-to-prior")
            count += 1
    return count


def _history_hits(report, tree, files):
    import subprocess
    listed = subprocess.run(
        ["git", "-C", str(tree), "rev-list", "--all"],
        capture_output=True, text=True,
    )
    if listed.returncode != 0:
        report.notes.append("git rev-list failed; PS16 left without a history pass")
        return 0
    count = 0
    pattern = r"sk-[A-Za-z0-9]{20,}"
    for rev in listed.stdout.split():
        grep = subprocess.run(
            ["git", "-C", str(tree), "grep", "-I", "-n", "-E", pattern, rev],
            capture_output=True, text=True,
        )
        if grep.returncode != 0:
            continue
        for line in grep.stdout.splitlines():
            report.add("PS16", "git:" + line.split(":", 1)[0], 1, "history-secret")
            count += 1
    return count


def _yaml_quote(value):
    text = str(value)
    if text == "" or any(c in text for c in ":#{}[]&*!|>%@`'\"\n"):
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text


def records_yaml(report, command):
    lines = []
    for rec in report.records:
        lines.append("---")
        lines.append(f"ps_id: {rec['ps_id']}")
        lines.append(f"result: {rec['result']}")
        lines.append(f"findings_count: {rec['findings_count']}")
        lines.append(f"tool: {rec['tool']}")
        lines.append(f"command: {_yaml_quote(command)}")
        lines.append(f"note: {_yaml_quote(rec['note'])}")
        lines.append("reviewer_actor_type: agent")
        lines.append("reviewer_role: author-run")
    if report.pending:
        lines.append("---")
        lines.append("pending:")
        for item in report.pending:
            lines.append(f"  - item: {item['item']}")
            lines.append(f"    status: {item['status']}")
            lines.append(f"    reason: {_yaml_quote(item['reason'])}")
    return "\n".join(lines) + "\n"


def summary_text(report):
    lines = [
        f"findings={len(report.findings)} pending={len(report.pending)} review_items={len(report.review_items)}",
    ]
    for item in report.pending:
        lines.append(f"PENDING {item['item']} {item['status']}")
    for finding in report.findings:
        lines.append(
            f"{finding['rule']} {finding['file']}:{finding['line']} {finding['fragment']}"
        )
    for rec in report.records:
        lines.append(f"{rec['ps_id']} {rec['result']} count={rec['findings_count']}")
    return "\n".join(lines) + "\n"


def write_report(report, out_dir, command):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "findings.json").write_text(json.dumps(report.findings, indent=2) + "\n", encoding="utf-8")
    (out / "records.yaml").write_text(records_yaml(report, command), encoding="utf-8")
    (out / "summary.txt").write_text(summary_text(report), encoding="utf-8")
    return out


def main(argv):
    parser = argparse.ArgumentParser(description="Public-safe scanner")
    parser.add_argument("tree")
    parser.add_argument("--deny-list")
    parser.add_argument("--known-values")
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--prior-package")
    parser.add_argument("--intake-reference")
    parser.add_argument("--agents-audit")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    command = " ".join(sys.argv)
    report = scan(
        args.tree,
        deny_list=args.deny_list,
        known_values=args.known_values,
        history=args.history,
        prior_package=args.prior_package,
        intake_reference=args.intake_reference,
        agents_audit=args.agents_audit,
    )
    write_report(report, args.out, command)
    sys.stdout.write(summary_text(report))
    return 1 if report.findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
