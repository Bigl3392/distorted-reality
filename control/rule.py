"""Pre-registered decision rule (EVIDENCE_SPEC section 6). The rule file is hashed and journaled before any execution.

A preferred path exists only if the best eligible path beats the runner-up by the frozen margin on exceptions_caught.
Otherwise NO_SUFFICIENT_EVIDENCE. The council's qualitative recommendation is shown alongside; the rule outcome stands.
"""
import hashlib
from dataclasses import dataclass

import yaml

from broker import _schemas

PREFERRED = "PATH_PREFERRED_UNDER_ASSUMPTIONS"
NONE_ = "NO_SUFFICIENT_EVIDENCE"


class RuleError(Exception):
    pass


@dataclass(frozen=True)
class Rule:
    data: dict
    sha256: str


def parse_rule(raw: bytes):
    try:
        data = yaml.safe_load(raw)
    except Exception:
        raise RuleError("rule is not valid YAML") from None
    errs = _schemas.errors("decision_rule.schema.json", data) if isinstance(data, dict) else ["not a mapping"]
    if errs:
        raise RuleError("rule fails decision_rule schema: " + errs[0])
    return Rule(data=data, sha256=hashlib.sha256(raw).hexdigest())


def load_rule(path):
    with open(path, "rb") as f:
        return parse_rule(f.read())


def verify_frozen(path, expected_sha256):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest() == expected_sha256


def evaluate(rule, results, cases_total):
    d = rule.data
    elig = d["eligibility"]
    margin = d["minimum_margin"]["exceptions_caught"]
    eligible, ineligible = {}, {}
    for pid in sorted(results):
        r = results[pid]
        m = r["metrics"]
        if r["claims_verdict"] != elig["claims_verdict"]:
            ineligible[pid] = "claims verdict is " + r["claims_verdict"]
        elif m["unsupported_claims"] > elig["unsupported_claims_max"]:
            ineligible[pid] = "unsupported claims exceed the maximum"
        elif m["false_alarms"] / cases_total > elig["false_alarms_max_fraction_of_cases"] + 1e-12:
            ineligible[pid] = "false alarms exceed the allowed fraction of cases"
        else:
            eligible[pid] = m
    ranked = sorted(eligible, key=lambda p: (-eligible[p]["exceptions_caught"], eligible[p]["manual_touches"],
                                             eligible[p].get("median_cycle_min", float("inf")), p))
    base = {"rule_id": d["rule_id"], "rule_sha256": rule.sha256, "eligible": ranked, "ineligible": ineligible}
    if len(ranked) < 2:
        return dict(base, result=NONE_, preferred_path_id=None, basis="fewer than 2 eligible paths: no comparison is possible")
    gap = eligible[ranked[0]]["exceptions_caught"] - eligible[ranked[1]]["exceptions_caught"]
    if gap < margin:
        return dict(base, result=NONE_, preferred_path_id=None,
                    basis=f"best beats runner-up by {gap} on exceptions_caught; the frozen rule requires at least {margin}")
    return dict(base, result=PREFERRED, preferred_path_id=ranked[0],
                basis=f"best beats runner-up by {gap} on exceptions_caught (frozen margin {margin}); preferred under these assumptions only")


def combine(rule_outcome, council_decision):
    council_id = None if council_decision.get("no_winner") else council_decision.get("recommended_path_id")
    rule_id = rule_outcome["preferred_path_id"]
    return {"rule_outcome": rule_outcome["result"], "rule_preferred_path_id": rule_id,
            "council_recommended_path_id": council_id, "agree": council_id == rule_id, "outcome_stands": "rule"}
