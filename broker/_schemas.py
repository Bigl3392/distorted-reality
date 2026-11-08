"""Schema access for broker and council. Loads the frozen files in ../schemas (AT-C2: never a copy)."""
import functools
import glob
import json
import os

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

SCHEMA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "schemas")


@functools.lru_cache(maxsize=1)
def _registry():
    resources = []
    for p in sorted(glob.glob(os.path.join(SCHEMA_DIR, "*.schema.json")) + [os.path.join(SCHEMA_DIR, "common.defs.json")]):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        resources.append((d["$id"], Resource.from_contents(d)))
    return Registry().with_resources(resources)


@functools.lru_cache(maxsize=None)
def validator(schema_file):
    with open(os.path.join(SCHEMA_DIR, schema_file), encoding="utf-8") as f:
        d = json.load(f)
    return Draft202012Validator(d, registry=_registry(), format_checker=Draft202012Validator.FORMAT_CHECKER)


def errors(schema_file, instance):
    return sorted(e.message[:200] for e in validator(schema_file).iter_errors(instance))
