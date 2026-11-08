"""Strict role-output parsing. Every parser fails closed with ParseError. Nothing here ever treats ambiguity as PASS."""
import ast
import functools
import json
import re

from jsonschema import Draft202012Validator

from broker import _schemas

HARD_KINDS = ("strawman", "hidden_constraint_violation", "overlap")
_FENCE = re.compile(r"\A```(?:json)?[ \t]*\r?\n(.*?)\r?\n?```\Z", re.S)


class ParseError(Exception):
    pass


def parse_role_json(text):
    """Single JSON object, no prose. One extraction attempt for a lone fenced block is allowed."""
    if not isinstance(text, str):
        raise ParseError("response is not text")
    s = text.strip()
    m = _FENCE.match(s)
    if m:
        s = m.group(1).strip()
    try:
        obj = json.loads(s)
    except Exception:
        raise ParseError("not a single JSON document") from None
    if not isinstance(obj, dict):
        raise ParseError("top level is not an object")
    return obj


@functools.lru_cache(maxsize=None)
def _frag(*keys):
    import os
    with open(os.path.join(_schemas.SCHEMA_DIR, "council_run.schema.json"), encoding="utf-8") as f:
        node = json.load(f)
    node = node["properties"]
    for k in keys[:-1]:
        node = node[k]["properties"]
    node = node[keys[-1]]
    return Draft202012Validator(node, format_checker=Draft202012Validator.FORMAT_CHECKER)


def _check(v, inst, what):
    errs = sorted(e.message[:120] for e in v.iter_errors(inst))
    if errs:
        raise ParseError(f"{what}: {errs[0]}")


def _only_keys(obj, keys, what):
    if set(obj) != set(keys):
        raise ParseError(f"{what}: keys must be exactly {sorted(keys)}")


def parse_evidence(obj):
    _only_keys(obj, ("facts", "constraints", "uncertainties"), "evidence")
    for k in obj:
        if not isinstance(obj[k], list) or not all(isinstance(x, str) for x in obj[k]):
            raise ParseError(f"evidence.{k} must be a list of strings")
    return {k: list(obj[k]) for k in ("facts", "constraints", "uncertainties")}


def parse_paths(obj, expect_ids=None):
    """Exactly 3 distinct paths. For a revision, the id set must equal the original id set."""
    _only_keys(obj, ("paths",), "paths")
    paths = obj["paths"]
    _check(_frag("initial_paths"), paths, "paths")
    ids = [p["path_id"] for p in paths]
    if len(set(ids)) != len(ids):
        raise ParseError("duplicate path_id")
    if expect_ids is not None and set(ids) != set(expect_ids):
        raise ParseError("revision must keep the same path ids")
    return paths


def parse_critic(obj, path_ids):
    """Returns (verdict, findings). The port, not the model, enforces: any hard finding => FAIL."""
    _only_keys(obj, ("verdict", "findings"), "critic")
    if obj["verdict"] not in ("PASS", "FAIL"):
        raise ParseError("critic verdict must be PASS or FAIL")
    _check(_frag("critic", "findings"), obj["findings"], "critic.findings")
    for f in obj["findings"]:
        if f["path_id"] not in path_ids:
            raise ParseError("critic finding names an unknown path_id")
    verdict = obj["verdict"]
    if any(f["kind"] in HARD_KINDS for f in obj["findings"]):
        verdict = "FAIL"
    return verdict, obj["findings"]


def parse_decision(obj, labels):
    _only_keys(obj, ("recommended_label", "no_winner", "comparison"), "decision")
    if not isinstance(obj["no_winner"], bool):
        raise ParseError("no_winner must be boolean")
    rl = obj["recommended_label"]
    if obj["no_winner"]:
        if rl is not None:
            raise ParseError("no_winner true requires recommended_label null")
    elif rl not in labels:
        raise ParseError("recommended_label is not a known neutral label")
    _check(_frag("decision", "comparison"), obj["comparison"], "decision.comparison")
    for c in obj["comparison"]:
        if c["label"] not in labels:
            raise ParseError("comparison names an unknown label")
    return {"recommended_label": rl, "no_winner": obj["no_winner"], "comparison": obj["comparison"]}


def parse_coder(obj):
    """Syntax check only (ast.parse). Safety is the container, not this check."""
    _only_keys(obj, ("code",), "coder")
    code = obj["code"]
    if not isinstance(code, str) or not code.strip():
        raise ParseError("code must be non-empty text")
    try:
        ast.parse(code)
    except SyntaxError:
        raise ParseError("code does not parse") from None
    return code
