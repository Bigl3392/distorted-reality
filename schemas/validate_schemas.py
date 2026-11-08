"""Validate every schema against Draft 2020-12, every fixture against its schema, and the two YAML reference files (rev 4).
Run: python3 -I validate_schemas.py   (needs jsonschema, referencing, PyYAML; BUILD records the pinned versions)"""
import json, glob, os, sys
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
here = os.path.dirname(os.path.abspath(__file__))
res = []
for p in sorted(glob.glob(f"{here}/*.schema.json")+[f"{here}/common.defs.json"]):
    d = json.load(open(p)); Draft202012Validator.check_schema(d); res.append((d["$id"], Resource.from_contents(d)))
reg = Registry().with_resources(res)
bad = 0
for p in sorted(glob.glob(f"{here}/fixtures/*.json")):
    name = os.path.basename(p); schema = name.split("__")[0] + ".schema.json"; expect_ok = not name.split("__")[1].startswith("INVALID")
    d = json.load(open(f"{here}/{schema}")); v = Draft202012Validator(d, registry=reg, format_checker=Draft202012Validator.FORMAT_CHECKER)
    errs = list(v.iter_errors(json.load(open(p)))); ok = not errs
    flag = "PASS" if ok == expect_ok else "FAIL"; bad += flag == "FAIL"
    print(flag, name, "" if ok == expect_ok else [e.message[:90] for e in errs][:2])
# rev 4: YAML reference files validated through their JSON form
yaml_checked = 0
for yml, schema in (("decision_rule.yaml", "decision_rule.schema.json"), ("models.example.yaml", "models.schema.json")):
    d = json.load(open(f"{here}/{schema}")); v = Draft202012Validator(d, registry=reg, format_checker=Draft202012Validator.FORMAT_CHECKER)
    errs = list(v.iter_errors(yaml.safe_load(open(f"{here}/{yml}")))); yaml_checked += 1
    bad += bool(errs); print("PASS" if not errs else "FAIL", yml, [e.message[:90] for e in errs][:2])
print("schemas:", len(res), "| fixtures checked:", len(glob.glob(f"{here}/fixtures/*.json")), "| yaml reference files:", yaml_checked, "| failures:", bad); sys.exit(bad)
