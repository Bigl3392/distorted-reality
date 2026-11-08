"""Claim-vs-evidence check (EVIDENCE_SPEC section 4), computed by the control plane from dataset events.

A claim is {case_id, step_id, claimed, evidence_ref}. Evidence is an event in the dataset carrying that evidence_ref.
Tests (a)-(e): exists; same case; from the claimed step or an earlier one; not later than the claimed event; recorded status consistent.
Interpretation I-7 (decisions/DR-INT-001): the spec names the five tests but not the step-type vocabulary, so (c) is structural
(no later step may prove an earlier one) and (e) uses the event status. A ground-truth conflict hook (`contradicts`) is supplied by the caller.
"""
from broker import _schemas

OK, NO, BAD = "SUPPORTED", "UNSUPPORTED", "CONTRADICTED"


def check_claims(run_id, path_id, claims, events, contradicts=None):
    by_ref, by_step = {}, {}
    for e in events:
        if e.get("evidence_ref"):
            by_ref.setdefault(e["evidence_ref"], []).append(e)
        by_step[(e["case_id"], e["step_id"])] = e
    out = []
    for i, c in enumerate(claims):
        ref = c.get("evidence_ref") or None
        result, reason = _judge(c, ref, by_ref, by_step, contradicts)
        out.append({"claim_id": c.get("claim_id") or f"clm-{i + 1:04d}", "step_id": c["step_id"], "case_id": c["case_id"],
                    "claimed": c["claimed"], "evidence_ref": c.get("evidence_ref"), "result": result, "reason": reason})
    cc = {"run_id": run_id, "path_id": path_id, "claims_total": len(out),
          "supported": sum(x["result"] == OK for x in out), "unsupported": sum(x["result"] == NO for x in out),
          "contradicted": sum(x["result"] == BAD for x in out), "claims": out, "recomputed_by": "control_plane"}
    errs = _schemas.errors("claim_check.schema.json", cc)
    if errs:
        raise ValueError("claim check fails its schema: " + errs[0])
    return cc


def _judge(c, ref, by_ref, by_step, contradicts):
    if ref is None:
        return NO, "no evidence_ref"
    all_with_ref = by_ref.get(ref)
    if not all_with_ref:
        return NO, "dangling evidence_ref"
    # an event that is itself only a claim ("claimed-complete") is never evidence, not even for itself
    cands = [e for e in all_with_ref if e["status"] != "claimed-complete"]
    if not cands:
        return NO, "the only events carrying this reference are unevidenced claims"
    same = [e for e in cands if e["case_id"] == c["case_id"]]
    if not same:
        return NO, "evidence belongs to a different case"
    claimed = by_step.get((c["case_id"], c["step_id"]))
    if claimed is None:
        return NO, "claimed step is not in the dataset"
    earlier = [e for e in same if e["step_id"] <= c["step_id"]]
    if not earlier:
        return NO, "evidence is from a later step"
    prior = [e for e in earlier if e["timestamp"] <= claimed["timestamp"]]
    if not prior:
        return NO, "evidence postdates the claim"
    done = [e for e in prior if e["status"] == "completed"]
    if done:
        if contradicts is not None and any(contradicts(c, e) for e in done):
            return BAD, "evidence conflicts with the claim"
        return OK, "evidence exists, same case, not later, status completed"
    return BAD, "evidence records a failed or stalled step"


def verdict(cc):
    return "CLAIMS_HOLD" if cc["unsupported"] == 0 and cc["contradicted"] == 0 else "CLAIMS_FAIL"
