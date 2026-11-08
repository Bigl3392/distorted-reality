"""models.yaml loader. The app refuses to start on any UNSET, a missing role, an unknown key, or a template file."""
import json
import os
from dataclasses import dataclass

from . import _schemas

BASE_URL = "https://api.vultrinference.com/v1"
CALL_ROLES = ("evidence", "path", "critic", "decision", "coder", "guard")


class ModelsError(Exception):
    pass


@dataclass(frozen=True)
class Role:
    name: str
    model_id: str
    temperature: float
    max_tokens: int


@dataclass(frozen=True)
class ModelsConfig:
    base_url: str
    roles: dict
    guard_enabled: bool
    fallback_applies_to: tuple
    fallback_model_id: str
    excluded: tuple

    def role(self, name):
        if name not in CALL_ROLES:
            raise ModelsError(f"unknown role {name!r}")
        if name == "guard" and not self.guard_enabled:
            raise ModelsError("guard role is disabled (default OFF)")
        if name not in self.roles:
            raise ModelsError(f"role {name!r} not configured")
        return self.roles[name]

    def fallback_for(self, name):
        self.role(name)
        if name not in self.fallback_applies_to:
            raise ModelsError(f"budget fallback does not apply to role {name!r}")
        return self.fallback_model_id


def _has_unset(o):
    if isinstance(o, dict):
        return any(_has_unset(v) for v in o.values())
    if isinstance(o, list):
        return any(_has_unset(v) for v in o)
    return o == "UNSET"


def load_models(source):
    """source: dict (JSON form) or a path to models.yaml / models.json."""
    if isinstance(source, (str, os.PathLike)):
        with open(source, encoding="utf-8") as f:
            text = f.read()
        if str(source).endswith((".yaml", ".yml")):
            import yaml
            data = yaml.safe_load(text)
        else:
            data = json.loads(text)
    else:
        data = source
    if not isinstance(data, dict):
        raise ModelsError("models file is not a mapping")
    errs = _schemas.errors("models.schema.json", data)
    if errs:
        raise ModelsError("models file fails schema: " + "; ".join(errs[:3]))
    if data.get("models_status") != "PINNED":
        raise ModelsError("models_status must be PINNED at runtime (TEMPLATE refuses to start)")
    if _has_unset(data):
        raise ModelsError("models file contains UNSET")
    if data["base_url"] != BASE_URL:
        raise ModelsError("base_url must be the Vultr Serverless Inference constant")
    roles = {}
    for name, r in data["roles"].items():
        roles[name] = Role(name, r["model_id"], r["temperature"], r["max_tokens"])
    if roles["critic"].model_id == roles["path"].model_id or roles["decision"].model_id == roles["path"].model_id:
        raise ModelsError("critic and decision ids must differ from the path id")
    guard = data["roles"].get("guard", {})
    fb = data["budget_fallback"]
    excluded = tuple(data["excluded"])
    used = {r.model_id for r in roles.values()} | {fb["model_id"]}
    if used & set(excluded):
        raise ModelsError("an excluded model id is in use")
    return ModelsConfig(
        base_url=data["base_url"],
        roles=roles,
        guard_enabled=bool(guard.get("enabled", False)),
        fallback_applies_to=tuple(fb["applies_to"]),
        fallback_model_id=fb["model_id"],
        excluded=excluded,
    )
