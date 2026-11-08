"""Council orchestration: Evidence -> Path (exactly 3) -> Critic -> at most one revision -> Decision on shuffled neutral labels.

Fails closed everywhere. A Critic that cannot be parsed is FAIL, never PASS. Model/budget/limit errors from the broker propagate untouched.
"""
import json
from dataclasses import dataclass, field

from broker import _schemas

from . import parsing, prompts
from .shuffle import label_map


class CouncilFailedClosed(Exception):
    def __init__(self, reason, calls=None):
        super().__init__(reason)
        self.reason = reason
        self.calls = calls or []


@dataclass
class CouncilResult:
    run: dict
    status: str          # COMPLETE | NO_SUFFICIENT_EVIDENCE
    survivors: list
    notes: list = field(default_factory=list)


@dataclass
class CoderResult:
    code: str
    records: list


def _blind(obj, path_ids):
    """Decision sees neutral labels only: model-written text may name a path_id, so every id is scrubbed from option text."""
    if isinstance(obj, str):
        for pid in path_ids:
            obj = obj.replace(pid, "[option]")
        return obj
    if isinstance(obj, list):
        return [_blind(x, path_ids) for x in obj]
    if isinstance(obj, dict):
        return {k: _blind(v, path_ids) for k, v in obj.items()}
    return obj


def _ask(broker, role, messages, parse):
    """One call, plus exactly one retry on a parse failure. A second failure is FAILED_CLOSED."""
    last = None
    for _ in range(2):
        r = broker.call(role, messages)
        try:
            return parse(parsing.parse_role_json(r.text))
        except parsing.ParseError as e:
            last = str(e)
    raise CouncilFailedClosed(f"{role} output unusable after one retry: {last}", broker.records)


def run_council(broker, council_input, *, seed, on_stage=None):
    errs = _schemas.errors("council_input.schema.json", council_input)
    if errs:
        raise CouncilFailedClosed("council input fails C1 schema: " + errs[0])
    ci = council_input
    start = len(broker.records)
    notes = []

    stage = on_stage or (lambda name: None)
    stage("COUNCIL_EVIDENCE")
    ev = _ask(broker, "evidence", prompts.evidence(ci), parsing.parse_evidence)
    stage("COUNCIL_PATHS")
    paths = _ask(broker, "path", prompts.paths(ci, ev), parsing.parse_paths)
    ids = [p["path_id"] for p in paths]

    # Critic: unparseable => FAIL (AT-07). The port enforces hard findings => FAIL.
    stage("COUNCIL_CRITIC")
    critic_text = broker.call("critic", prompts.critic(ci, ev, paths)).text
    try:
        verdict, findings = parsing.parse_critic(parsing.parse_role_json(critic_text), set(ids))
        critic = {"verdict": verdict, "findings": findings, "parse_status": "parsed"}
    except parsing.ParseError:
        critic = {"verdict": "FAIL", "findings": [], "parse_status": "unparseable_failed_closed"}
        notes.append("critic output unparseable: recorded FAIL, no review claim")

    hard = {f["path_id"] for f in critic["findings"] if f["kind"] in parsing.HARD_KINDS}
    current = paths
    revision = {"performed": False, "count": 0, "paths": None}
    if critic["verdict"] == "FAIL" and hard:
        stage("COUNCIL_REVISION")
        revised = _ask(broker, "path", prompts.revision(ci, ev, paths, critic["findings"]),
                       lambda o: parsing.parse_paths(o, expect_ids=ids))
        revision = {"performed": True, "count": 1, "paths": revised}
        current = revised
    old = {p["path_id"]: json.dumps(p["intervention"], sort_keys=True) for p in paths}
    new = {p["path_id"]: json.dumps(p["intervention"], sort_keys=True) for p in current}
    # I-1: survivors = not hard-flagged, or hard-flagged and changed by the single revision.
    survivors = [pid for pid in ids if pid not in hard or (revision["performed"] and new[pid] != old[pid])]
    by_id = {p["path_id"]: p for p in current}

    lm = label_map(survivors, seed)
    if len(survivors) < 2:
        status = "NO_SUFFICIENT_EVIDENCE"
        notes.append(f"fewer than 2 paths survived the Critic ({len(survivors)}): no decision made")
        decision = {"recommended_label": None, "recommended_path_id": None, "no_winner": True, "comparison": [], "qualitative_only": True}
    else:
        status = "COMPLETE"
        stage("COUNCIL_DECISION")
        options = {label: _blind(by_id[pid]["intervention"], ids) for label, pid in lm.items()}
        d = _ask(broker, "decision", prompts.decision(ci, ev, options), lambda o: parsing.parse_decision(o, set(lm)))
        decision = {"recommended_label": d["recommended_label"],
                    "recommended_path_id": lm[d["recommended_label"]] if d["recommended_label"] else None,
                    "no_winner": d["no_winner"], "comparison": d["comparison"], "qualitative_only": True}

    calls = [dict(r) for r in broker.records[start:]]
    run = {
        "label": "SYNTHETIC",
        "run_id": ci["run_id"],
        "models": {r["role"]: r["requested_model"] for r in calls},
        "evidence": {**ev, "sources": ["mri", "scan"]},
        "initial_paths": paths,
        "critic": critic,
        "revision": revision,
        "shuffle": {"seed": int(seed), "label_map": lm},
        "decision": decision,
        "agent_calls": calls,
    }
    bad = _schemas.errors("council_run.schema.json", run)
    if bad:
        raise CouncilFailedClosed("assembled council record fails schema: " + bad[0], calls)
    return CouncilResult(run=run, status=status, survivors=survivors, notes=notes)


def compile_apply(broker, path, dataset_schema, feedback=None):
    """Coder role: Path intervention + dataset SCHEMA -> apply.py source. Never sees ground truth."""
    start = len(broker.records)
    code = _ask(broker, "coder", prompts.coder(path, dataset_schema, feedback), parsing.parse_coder)
    return CoderResult(code=code, records=[dict(r) for r in broker.records[start:]])
