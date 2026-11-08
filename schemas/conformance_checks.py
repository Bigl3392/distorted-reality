"""Rev 4 conformance checks that JSON Schema cannot express. Run: python3 -I conformance_checks.py (needs PyYAML; reads only files in schemas/).
Checks: G18 range reconciliation, X9 pin, R04 pins, SB1 golden round trip (AT-C4). Public-safe: ships with schemas/."""
import json, glob, os, re, sys, importlib.util
import yaml
here = os.path.dirname(os.path.abspath(__file__))
results = []
def check(name, ok, detail=""):
    results.append(ok); print("PASS" if ok else "FAIL", name, "" if ok else detail)
spec = importlib.util.spec_from_file_location("reference_scoring", f"{here}/reference_scoring.py"); rs = importlib.util.module_from_spec(spec); spec.loader.exec_module(rs)

# ---- 1. G18: one definition everywhere ----
vals = [rs.half_up(s / 90 * 100) for s in range(15, 91)]
check("G18 attainable range is exactly 17..100 over all 76 answer totals", min(vals) == 17 and max(vals) == 100 and len(vals) == 76)
check("G18 monotonic non-decreasing over all 76 totals", all(a <= b for a, b in zip(vals, vals[1:])))
sc = json.load(open(f"{here}/scan_result.schema.json"))["properties"]["overall"]
check("scan_result.schema overall min/max equals G18 range", sc.get("minimum") == min(vals) and sc.get("maximum") == max(vals), str(sc))
def walk(o, key, out):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == key and isinstance(v, int) and not isinstance(v, bool): out.append(v)
            walk(v, key, out)
    elif isinstance(o, list):
        for v in o: walk(v, key, out)
found = []
for p in glob.glob(f"{here}/fixtures/*.json"):
    if "INVALID" in os.path.basename(p): continue
    walk(json.load(open(p)), "overall", found)
check("every overall in a valid fixture lies in 17..100", bool(found) and all(17 <= v <= 100 for v in found), str(found))
stale = [os.path.basename(p) for p in glob.glob(f"{here}/*.schema.json") if p != f"{here}/scan_result.schema.json" and '"overall"' in open(p).read()]
check("no other schema re-declares overall", not stale, str(stale))

# ---- 2. X9 pin (BUILD co-sign at freeze review) ----
X9 = {"rule_id": "dr-3way-v1",
      "eligibility": {"claims_verdict": "CLAIMS_HOLD", "unsupported_claims_max": 0, "false_alarms_max_fraction_of_cases": 0.1},
      "ranking": [{"metric": "exceptions_caught"}, {"metric": "manual_touches"}, {"metric": "median_cycle_min"}],
      "minimum_margin": {"exceptions_caught": 3},
      "outcomes": ["PATH_PREFERRED_UNDER_ASSUMPTIONS", "NO_SUFFICIENT_EVIDENCE"],
      "notes": "Synthetic data. A preferred path is preferred under these assumptions only."}
check("decision_rule.yaml equals the X9 co-signed rule", yaml.safe_load(open(f"{here}/decision_rule.yaml")) == X9)
check("decision_rule.yaml equals its JSON fixture mirror", json.load(open(f"{here}/fixtures/decision_rule__valid.json")) == X9)

# ---- 3. R04 pins and family separation ----
m = yaml.safe_load(open(f"{here}/models.example.yaml")); r = {k: v["model_id"] for k, v in m["roles"].items()}
R04 = {"evidence": "mimo-v2.6-flash", "path": "glm-5.3", "critic": "deepseek-v4.1-flash-1017", "decision": "mimo-v2.6-pro", "coder": "glm-5.3", "guard": "nemotron-3.5-content-safety"}
check("models.example.yaml role ids equal R04", r == R04, str(r))
check("models.example.yaml budget fallback / exclusions equal R04", m["budget_fallback"]["model_id"] == "glm-5.3-flash" and m["excluded"] == ["raon-1-mini-preview", "auk"])
check("critic and decision ids differ from path id", r["critic"] != r["path"] and r["decision"] != r["path"])
check("guard defaults OFF", m["roles"]["guard"]["enabled"] is False)
check("template carries no invented temperature / max_tokens", all(v["temperature"] == "UNSET" and v["max_tokens"] == "UNSET" for v in m["roles"].values()))

# ---- 4. SB1 golden round trip (AT-C4, reference harness; golden code only, never untrusted code) ----
req = json.load(open(f"{here}/fixtures/sb1_request__valid.json")); gold_src = open(f"{here}/golden/sb1_golden_apply.py").read()
check("SB1 request code equals golden apply.py source", req["code"] == gold_src)
ns = {}; exec(compile(req["code"], "apply.py", "exec"), ns)
import copy
out = ns["apply"](copy.deepcopy(req["events"])); got = json.dumps({"contract": "SB1", "ok": True, **out}, sort_keys=True, separators=(",", ":"))
check("SB1 golden stdout is byte-identical", got == open(f"{here}/golden/sb1_golden_stdout.json").read())

print("conformance checks:", len(results), "| failures:", results.count(False)); sys.exit(results.count(False))
