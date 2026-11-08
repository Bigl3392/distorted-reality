"""Role prompts. Inputs are the synthetic MRI inventory, the generic scan result, constraints and the test definition.
No ground truth, no key, no private configuration is ever placed in a prompt."""
import json

_ONE_JSON = "Reply with a single JSON object, no prose, no code fences."

_INTERVENTION = ('{"path_id": str, "title": str, "intervention": {"summary": str, "who_does_what": [{"role": str, "does": str}], '
                 '"order": [str], "checks": [str], "automation": [str], "distinct_from": str}}')


def _j(o):
    return json.dumps(o, sort_keys=True, ensure_ascii=False)


def _context(ci):
    scan = {k: ci["scan"][k] for k in ("overall", "recommendation", "limitations") if k in ci["scan"]}
    return {"mri": ci["mri"], "scan": scan, "constraints": ci["constraints"], "test_definition": ci["test_definition"]}


def evidence(ci):
    return [
        {"role": "system", "content": "You are the Evidence role of a decision council for a SYNTHETIC accounts-payable reconciliation workflow. "
         "State only what the inputs support. Separate facts, constraints and uncertainties. " + _ONE_JSON +
         ' Shape: {"facts": [str], "constraints": [str], "uncertainties": [str]}'},
        {"role": "user", "content": _j(_context(ci))},
    ]


def paths(ci, ev, previous_error=None):
    return [
        {"role": "system", "content": "You are the Path role. Propose exactly 3 materially different interventions for the workflow: they must differ in "
         "ownership, order, checks or automation, not just wording. Every intervention must be testable on the stated metrics. " + _ONE_JSON +
         ' Shape: {"paths": [' + _INTERVENTION + ", x3]}. path_id is a lowercase slug like path-a."},
        {"role": "user", "content": _j({"context": _context(ci), "evidence": ev})},
    ]


def critic(ci, ev, ps):
    return [
        {"role": "system", "content": "You are the Critic role. Check the 3 paths for strawmen (deliberately weak options), hidden constraint violations and "
         "overlap (paths that differ only in wording). " + _ONE_JSON +
         ' Shape: {"verdict": "PASS"|"FAIL", "findings": [{"path_id": str, "kind": "strawman"|"hidden_constraint_violation"|"overlap"|"other", "detail": str}]}. '
         "Any strawman, hidden_constraint_violation or overlap finding means verdict FAIL."},
        {"role": "user", "content": _j({"constraints": ci["constraints"], "evidence": ev, "paths": ps})},
    ]


def revision(ci, ev, ps, findings):
    return [
        {"role": "system", "content": "You are the Path role, revising once after the Critic's findings. Return all 3 paths with the SAME path_id values. "
         "Change the flagged paths so the findings no longer apply; keep the others as they are. " + _ONE_JSON +
         ' Shape: {"paths": [' + _INTERVENTION + ", x3]}"},
        {"role": "user", "content": _j({"context": _context(ci), "evidence": ev, "paths": ps, "critic_findings": findings})},
    ]


def decision(ci, ev, options):
    return [
        {"role": "system", "content": "You are the Decision role. Compare the options on the evidence and the stated constraints. Judgement is qualitative only. "
         "No winner is a valid answer if the evidence does not separate the options. " + _ONE_JSON +
         ' Shape: {"recommended_label": str|null, "no_winner": bool, "comparison": [{"label": str, "rationale": str, "risks": [str], "confidence": "low"|"medium"|"high"}]}. '
         "If no_winner is true, recommended_label must be null."},
        {"role": "user", "content": _j({"constraints": ci["constraints"], "evidence": ev, "options": options})},
    ]


def coder(path, dataset_schema, feedback=None):
    return [
        {"role": "system", "content": "You are the Coder role. Write Python (standard library only) that implements the intervention on a list of event dicts. "
         "Define apply(events: list[dict]) -> dict returning keys flagged_cases (list), resolutions (list), manual_touch_cases (list), "
         "self_metrics (dict) and error (null). Use only the fields in the dataset schema. " + _ONE_JSON + ' Shape: {"code": str}'},
        {"role": "user", "content": _j(dict({"intervention": path["intervention"], "title": path.get("title"), "dataset_schema": dataset_schema},
                                           **({"previous_attempt_feedback": feedback} if feedback else {})))},
    ]
