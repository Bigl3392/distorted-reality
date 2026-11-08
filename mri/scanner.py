"""Read-only deterministic workflow inventory. Stamp is caller-supplied, never a hidden wall clock."""
from __future__ import annotations

import collections
import hashlib
import statistics

from dataset.generator import canonical, encode_rows


def scan(events, manifest, *, run_id, scanned_at):
    digest = hashlib.sha256(encode_rows(events)).hexdigest()
    if digest != manifest["dataset_sha256"]:
        raise ValueError("dataset hash mismatch")
    groups = collections.defaultdict(list)
    cases = collections.defaultdict(list)
    for event in events:
        groups[(event["location"], event["step_id"])].append(event)
        cases[event["case_id"]].append(event)
    steps, stall_points = [], []
    for (location, sid), rows in sorted(groups.items()):
        first = rows[0]
        rate = sum(e["stall_flag"] for e in rows) / len(rows)
        steps.append({
            "step_id": sid, "name": first["action"], "owner_role": first["role"],
            "input_type": "AP workflow record", "output_type": "AP evidence record", "size_rows": len(rows),
            "last_touched": max(e["timestamp"] for e in rows), "location": location, "handoff_to": first["handoff_to"],
            "median_duration_min": statistics.median(e["duration_min"] for e in rows),
            "expected_duration_min": statistics.median(e["expected_duration_min"] for e in rows),
            "stall_rate": rate, "claimed_complete_count": sum(e["status"] == "claimed-complete" for e in rows),
            "claimed_without_evidence_count": sum(e["status"] == "claimed-complete" and not e["evidence_ref"] for e in rows),
        })
        if rate:
            stall_points.append({"step_id": sid, "reason": location + ": duration exceeds expected window", "rate": rate})
    waits = collections.defaultdict(list)
    from datetime import datetime
    for rows in cases.values():
        rows = sorted(rows, key=lambda e: e["step_id"])
        for a, b in zip(rows, rows[1:]):
            if a["role"] != b["role"]:
                gap = (datetime.fromisoformat(b["timestamp"]) - datetime.fromisoformat(a["timestamp"])).total_seconds()/60 - b["duration_min"]
                waits[(a["role"], b["role"])].append(max(0, gap))
    result = {
        "label": "SYNTHETIC", "mri_version": "1", "run_id": run_id, "dataset_id": manifest["dataset_id"],
        "dataset_sha256": digest, "scanned_at": scanned_at, "read_only": True, "authorizes": "nothing", "steps": steps,
        "handoffs": [{"from_role": a, "to_role": b, "count": len(values), "median_wait_min": statistics.median(values)}
                     for (a,b), values in sorted(waits.items())], "stall_points": stall_points,
    }
    result["inventory_sha256"] = hashlib.sha256(canonical(result)).hexdigest()
    return result
