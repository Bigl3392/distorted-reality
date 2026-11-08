def apply(events):
    """SB1 golden apply(): deterministic, stdlib only. Not a product path; it exists so the wire contract has a byte-exact round trip (AT-C4)."""
    flagged, res, manual = set(), [], set()
    for e in events:
        if e["status"] == "claimed-complete" and e["evidence_ref"] is None:
            flagged.add(e["case_id"])
        if e["status"] in ("claimed-complete", "completed"):
            res.append({"case_id": e["case_id"], "step_id": e["step_id"], "claimed": e["status"], "evidence_ref": e["evidence_ref"]})
        if e["status"] in ("stalled", "failed"):
            manual.add(e["case_id"])
    flagged = sorted(flagged)
    return {"flagged_cases": flagged, "resolutions": res, "manual_touch_cases": sorted(manual),
            "self_metrics": {"exceptions_caught": len(flagged)}, "error": None}
