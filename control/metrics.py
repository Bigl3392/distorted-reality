"""Metric recompute (EVIDENCE_SPEC sections 1 and 5). The control plane computes the numbers; self-reported metrics are never used.

median_cycle_min is computed ONLY from an explicit per-case map. The frozen spec says "under the path's resolution timing model"
but defines no such model, so none is invented here (I-9, open question for LDR/ARC).
"""
import statistics


class MetricsError(Exception):
    pass


def _ids(v, name):
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise MetricsError(f"{name} must be a list of case ids")
    return set(v)


def recompute(path_output, truth_exception_cases, claim_check, cycle_min_by_case=None):
    flagged = _ids(path_output.get("flagged_cases"), "flagged_cases")
    touched = _ids(path_output.get("manual_touch_cases"), "manual_touch_cases")
    truth = set(truth_exception_cases)
    m = {
        "exceptions_caught": len(flagged & truth),
        "false_alarms": len(flagged - truth),
        "unsupported_claims": claim_check["unsupported"] + claim_check["contradicted"],
        "manual_touches": len(touched),
    }
    if cycle_min_by_case:
        m["median_cycle_min"] = float(statistics.median(cycle_min_by_case.values()))
    return m


def discrepancy(self_reported, recomputed):
    if not self_reported:
        return False
    for k, v in self_reported.items():
        if k not in recomputed:
            continue
        r = recomputed[k]
        if isinstance(v, int) and isinstance(r, int) and not isinstance(v, bool):
            if v != r:
                return True
        elif abs(float(v) - float(r)) > 1e-6:
            return True
    return False
