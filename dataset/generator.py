"""Deterministic synthetic AP data. No network or credentials; final generation requires sourced weather."""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import random

SEED = 20261103
LOCATIONS = ("Midtown OKC", "Riverside Tulsa", "Commons Norman", "Market Hall Edmond")
ROLES = ("Kitchen Manager", "Receiving Clerk", "AP Clerk", "Controller")
STEPS = (
    ("PO placed", "Kitchen Manager", "Receiving Clerk", None),
    ("Delivery counted", "Receiving Clerk", "Receiving Clerk", None),
    ("Receipt logged", "Receiving Clerk", "AP Clerk", "inventory_vs_cogs"),
    ("Invoice received", "AP Clerk", "AP Clerk", "payables_review"),
    ("Three-way match", "AP Clerk", "Kitchen Manager", "payables_review"),
    ("Exception review", "Kitchen Manager", "Controller", "uncategorized_zero"),
    ("Payment recommendation", "Controller", None, "variance_review"),
)
WEATHER_SOURCE = "Open-Meteo Historical Weather API (ERA5)"
WINTERS = ("2020-21", "2022-23", "2023-24", "2024-25", "2025-26")
STAMP = "2026-02-28T23:59:59Z"


class DatasetError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def encode_rows(rows):
    return b"".join(canonical(row) + b"\n" for row in rows)


def build_synthetic(*, seed=SEED, stamp=STAMP, weather_index=None):
    """Pure synthetic core, NOT a weather-complete release dataset. Never persists ground truth."""
    if type(seed) is not int or seed != SEED:
        raise DatasetError("the bundled dataset requires seed 20261103")
    rng = random.Random(seed)
    events, truth, faults = [], [], collections.defaultdict(list)
    windows = ("christmas", "new_years", "valentines", "none")
    centers = (dt.date(2025, 12, 25), dt.date(2026, 1, 1), dt.date(2026, 2, 14), dt.date(2026, 1, 22))
    for li, location in enumerate(LOCATIONS):
        for n in range(50):
            case_id = f"inv-{li * 50 + n + 1:04d}"
            wi = n % 4
            window = windows[wi]
            day = centers[wi] + dt.timedelta(days=rng.randint(-3, 3))
            weather = (weather_index or {}).get((location, day.isoformat()))
            weather_delay = 0
            if weather is not None:
                # Synthetic projection coefficients, not calibrated business effects.
                weather_delay = int(weather["precip_in"] > 0) * 4 + int(weather["tmin_f"] < 32) * 3
            fault_probability = (0.26, 0.22, 0.18, 0.10)[wi]
            exception_types = []
            if rng.random() < fault_probability:
                exception_types.append(rng.choice(("missing_receipt", "quantity_mismatch", "price_mismatch")))
            qty = rng.randint(10, 100)
            price = rng.randint(200, 2500)
            received_qty = qty - 1 if "quantity_mismatch" in exception_types else qty
            invoice_price = price + 100 if "price_mismatch" in exception_types else price
            truth.append({"case_id": case_id, "exception_types": exception_types,
                          "correct_resolution": "review_exception" if exception_types else "matched",
                          "po_quantity": qty, "received_quantity": received_qty,
                          "po_unit_price_cents": price, "invoice_unit_price_cents": invoice_price})
            for fault in exception_types:
                faults[fault].append(case_id)
            current = dt.datetime.combine(day, dt.time(8), tzinfo=dt.timezone.utc)
            payloads = [
                ({"request": "supplier goods"}, {"po_quantity": qty, "unit_price_cents": price}),
                ({"po_quantity": qty}, {"received_quantity": received_qty}),
                ({"received_quantity": received_qty}, {"receipt_quantity": received_qty}),
                ({"invoice": case_id}, {"invoice_quantity": qty, "invoice_unit_price_cents": invoice_price}),
                ({"po": case_id, "receipt": f"rcpt-{case_id}", "invoice": case_id}, {"state": "pending_review"}),
                ({"case": case_id}, {"state": "review_recorded"}),
                ({"case": case_id}, {"recommendation": "review_before_payment", "payment_made": False}),
            ]
            for si, (name, role, handoff, close_ref) in enumerate(STEPS, 1):
                expected = (5, 8, 5, 6, 10, 12, 5)[si - 1]
                duration = expected + rng.randint(0, 9) + weather_delay + (4 if wi < 3 else 0)
                current += dt.timedelta(minutes=duration)
                missing = "missing_receipt" in exception_types and si == 3
                status = "claimed-complete" if missing else ("stalled" if duration > expected * 2 else "completed")
                prefix = ("po", "cnt", "rcpt", "bill", "match", "review", "recommend")[si - 1]
                evidence = None if missing else f"{prefix}-{case_id}"
                inp, out = payloads[si - 1]
                events.append({
                    "label": "SYNTHETIC", "source_type": "DERIVED_SYNTHETIC" if weather is not None else "SYNTHETIC",
                    "case_id": case_id, "step_id": si, "role": role, "action": name,
                    "input": canonical(inp).decode(), "output": canonical(out).decode(),
                    "timestamp": current.isoformat().replace("+00:00", "Z"),
                    "duration_min": duration, "expected_duration_min": expected, "handoff_to": handoff,
                    "status": status, "evidence_ref": evidence, "stall_flag": status == "stalled",
                    "location": location, "holiday_window": window, "close_ref": close_ref,
                })
                current += dt.timedelta(minutes=rng.randint(1, 30))
    ground_truth = {
        "format_version": "1", "label": "SYNTHETIC", "seed": seed,
        "dataset_sha256": hashlib.sha256(encode_rows(events)).hexdigest(),
        "exceptional_case_ids": [c["case_id"] for c in truth if c["exception_types"]],
        "cases": truth,
    }
    seal = hashlib.sha256(canonical(ground_truth)).hexdigest()
    manifest = {
        "label": "SYNTHETIC", "dataset_id": "eo-ap-v1", "fictional_entity": "Ember & Oak Hospitality Group (EO-OKC-01)",
        "generator": "dataset.generator", "generator_version": "1.0.0", "seed": seed, "row_count": len(events),
        "case_count": 200, "roles": list(ROLES),
        "injected_faults": [{"fault_id": "fault-" + f.replace("_", "-"), "description": f.replace("_", " "),
                             "affected_cases": ids, "disclosed": True} for f, ids in sorted(faults.items())],
        "dataset_sha256": ground_truth["dataset_sha256"], "created": stamp,
        "limitations": ("Synthetic; no calibration to real operations. Projection coefficients are assumptions. "
                        + ("G14 weather data absent; synthetic core only. " if weather_index is None else "")
                        + "ground_truth_sha256=" + seal),
        "arm": "flagship", "period": {"start": "2025-12-01", "end": "2026-02-28"},
        "drivers": ["season", "holidays"] + (["weather"] if weather_index is not None else []),
        "cases_per_location": dict.fromkeys(LOCATIONS, 50), "external_public_facts": [],
        "explanation_layers": [{"kind": "monthly_baseline", "winters": ["2025-26"], "proof_period_only": True}],
    }
    baseline = [{"label": "SYNTHETIC", "source_type": "SYNTHETIC", "location": loc, "month": month,
                 "cogs_pct": 30 + li + mi, "waste_pct": 2 + mi / 10}
                for li, loc in enumerate(LOCATIONS) for mi, month in enumerate(("2025-12", "2026-01", "2026-02"))]
    return events, manifest, ground_truth, baseline


def weather_inputs(rows, provenance):
    if not rows or not isinstance(provenance, dict):
        raise DatasetError("G14: sourced weather rows and provenance are required")
    for key in ("request_parameters", "retrieved", "source"):
        if not provenance.get(key):
            raise DatasetError("weather provenance missing " + key)
    if provenance["source"] != WEATHER_SOURCE:
        raise DatasetError("weather source must match the frozen contract")
    index = {}
    expected = set()
    for winter in WINTERS:
        year = int(winter[:4])
        day, end = dt.date(year, 12, 1), dt.date(year + 1, 3, 1)
        while day < end:
            expected.update((loc, day.isoformat(), winter) for loc in LOCATIONS)
            day += dt.timedelta(days=1)
    schema = json.loads((Path(__file__).resolve().parents[1] / "schemas" / "weather_daily.schema.json").read_text())
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) - set(schema["properties"]) or set(schema["required"]) - set(row):
            raise DatasetError("weather row fields differ from frozen schema")
        try:
            dt.date.fromisoformat(row["retrieved"])
        except (TypeError, ValueError):
            raise DatasetError("weather retrieval date invalid") from None
        if row.get("snow_in") is not None and (type(row["snow_in"]) not in (int,float) or not math.isfinite(row["snow_in"]) or row["snow_in"] < 0):
            raise DatasetError("weather snow must be finite and nonnegative")
        if row.get("source_type") != "PUBLIC_FACT" or row.get("source") != WEATHER_SOURCE:
            raise DatasetError("weather row lacks approved PUBLIC_FACT source")
        key = (row.get("location"), row.get("date"), row.get("winter"))
        if key in seen or key not in expected:
            raise DatasetError("weather duplicate or date/winter/location outside required coverage")
        seen.add(key)
        if row["winter"] == "2020-21":
            if row.get("era_label") != "COVID-ERA" or row.get("explanation_layer_only") is not True:
                raise DatasetError("weather 2020-21 requires explanation-only COVID-ERA label")
        elif "era_label" in row or "explanation_layer_only" in row:
            raise DatasetError("weather era fields only apply to 2020-21")
        for name in ("tmax_f", "tmin_f", "precip_in"):
            value = row.get(name)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise DatasetError("weather numeric fields must be finite")
        if row["precip_in"] < 0 or row["tmin_f"] > row["tmax_f"]:
            raise DatasetError("weather values are inconsistent")
        if not row.get("retrieved"):
            raise DatasetError("weather retrieval date missing")
        if row["winter"] == "2025-26":
            index[(row["location"], row["date"])] = row
    if seen != expected:
        raise DatasetError("weather coverage is incomplete for four locations and five winters")
    return index


def generate(*, weather_rows, provenance, stamp=None):
    index = weather_inputs(weather_rows, provenance)
    if not isinstance(stamp, str):
        raise DatasetError("explicit creation timestamp is required")
    try:
        created = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        raise DatasetError("creation timestamp must be ISO 8601") from None
    if created.tzinfo is None:
        raise DatasetError("creation timestamp must have a timezone")
    events, manifest, truth, baseline = build_synthetic(stamp=stamp, weather_index=index)
    manifest["external_public_facts"] = [{"kind": "weather", "source": WEATHER_SOURCE, "retrieved": provenance["retrieved"]}]
    manifest["explanation_layers"].append({
        "kind": "weather_daily", "winters": list(WINTERS), "proof_period_only": False,
        "source": WEATHER_SOURCE, "era_labels": {"2020-21": "COVID-ERA"},
    })
    return events, manifest, truth, baseline


def write_bundle(destination, bundle, weather_rows, provenance):
    """CreateNew only. Truth is private control-host output, never a product source file."""
    target = Path(destination)
    if target.exists():
        raise DatasetError("output directory must not exist; sources are never overwritten")
    weather_inputs(weather_rows, provenance)
    target.mkdir(mode=0o700, parents=True)
    events, manifest, truth, baseline = bundle
    contents = {
        "dataset.jsonl": encode_rows(events), "manifest.json": canonical(manifest),
        "ground_truth.json": canonical(truth), "monthly_baseline.jsonl": encode_rows(baseline),
        "weather_daily.jsonl": encode_rows(weather_rows), "weather_provenance.json": canonical(provenance),
    }
    for name, content in contents.items():
        fd = os.open(target / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weather", required=True, help="approved G14 weather JSONL; no runtime fetch")
    parser.add_argument("--provenance", required=True, help="request parameters, retrieval date and source JSON")
    parser.add_argument("--output", required=True, help="new private output directory on control host")
    parser.add_argument("--created-at", required=True, help="actual UTC creation timestamp recorded by the operator")
    args = parser.parse_args()
    rows = [json.loads(line) for line in Path(args.weather).read_text().splitlines() if line.strip()]
    provenance = json.loads(Path(args.provenance).read_text())
    write_bundle(args.output, generate(weather_rows=rows, provenance=provenance, stamp=args.created_at), rows, provenance)


if __name__ == "__main__":
    main()
