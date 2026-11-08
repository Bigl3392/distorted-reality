"""Scoring service (M2). Computes the overall index from the answer sum and nothing else.

Public surface = overall index + one fixed generic recommendation + optional keyed commitment (G5 Option 1).
This module loads only the public question file and the frozen reference scorer. It reads no process settings and no other file (G19).
The commitment key, when used, is passed in by the caller.
"""
import importlib.util
import os
import re

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUESTIONS_PATH = os.path.join(ROOT, "scan", "questions.public.yaml")
GENERIC_ERROR = "15 integer answers in 1..6 required"
LIMITATIONS = [
    "System-specific results are suppressed in public, by design, to protect the private association.",
    "The deployed product computes only the overall index and performs no system-specific scoring.",
]
RECOMMENDATION = "Review the AP reconciliation workflow evidence with the council."
_RUN_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")
_QID = re.compile(r"^[0-9a-f]{8}$")


def _load_reference():
    spec = importlib.util.spec_from_file_location("reference_scoring", os.path.join(ROOT, "schemas", "reference_scoring.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_ref = _load_reference()


class QuestionsError(Exception):
    pass


class ScanRejected(Exception):
    """Always carries the same generic text, whatever was wrong with the input (AT-G5-3)."""

    def __init__(self):
        super().__init__(GENERIC_ERROR)


def validate_questions(d):
    if not isinstance(d, dict) or set(d) != {"scale", "prompt", "items"}:
        raise QuestionsError("questions file must have exactly scale, prompt, items")
    items = d["items"]
    if not isinstance(items, list) or len(items) != 15:
        raise QuestionsError("exactly 15 items required")
    ids = []
    for q in items:
        if not isinstance(q, dict) or set(q) != {"id", "text"} or not isinstance(q["id"], str) or not _QID.match(q["id"]):
            raise QuestionsError("each item must be {id: 8 hex, text}")
        ids.append(q["id"])
    if len(set(ids)) != 15:
        raise QuestionsError("item ids must be unique")
    return d


def load_questions():
    with open(QUESTIONS_PATH, encoding="utf-8") as f:
        return validate_questions(yaml.safe_load(f))


_IDS = frozenset(q["id"] for q in load_questions()["items"])


def score(run_id, answers, commit_key=None):
    if not isinstance(run_id, str) or not _RUN_ID.match(run_id):
        raise ScanRejected()
    if not isinstance(answers, dict) or set(answers) != _IDS:
        raise ScanRejected()
    try:
        overall = _ref.overall(answers)
    except ValueError:
        raise ScanRejected() from None
    result = {
        "label": "SYNTHETIC",
        "scan_version": "2",
        "run_id": run_id,
        "intake_variant": "paraphrase",
        "overall": overall,
        "recommendation": RECOMMENDATION,
        "limitations": list(LIMITATIONS),
        "routes_present": False,
        "fees_present": False,
    }
    if commit_key is not None:
        result["answers_commitment"] = _ref.commitment(answers, run_id, commit_key)
    return result
