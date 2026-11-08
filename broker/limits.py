"""Token limits (X7 = B). No number lives in code or spec. Limits are UNSET until an LDR_APPROVED record exists."""
import re
import threading
from dataclasses import dataclass
from typing import Optional

from . import _schemas


class LimitsError(Exception):
    pass


@dataclass(frozen=True)
class Limits:
    run_token_cap: Optional[int]
    daily_token_budget: Optional[int]
    runs_per_ip_per_hour: Optional[int] = None      # enforced by the HTTP layer; carried here so "any limit UNSET" (AT-L2) means all three

    @property
    def fully_set(self):
        return (self.run_token_cap is not None and self.daily_token_budget is not None
                and self.runs_per_ip_per_hour is not None)


class DailyBudget:
    """Process-wide token counter shared by every run's client."""

    def __init__(self):
        self._lock = threading.Lock()
        self._used = 0

    @property
    def used(self):
        with self._lock:
            return self._used

    def add(self, n):
        with self._lock:
            self._used += n
            return self._used


_POS_INT = re.compile(r"^[1-9][0-9]*$")


def _parse(name, raw):
    if raw is None or raw == "UNSET":
        return None
    if not isinstance(raw, str) or not _POS_INT.match(raw):
        raise LimitsError(f"{name} must be UNSET or a positive integer")
    return int(raw)


def limits_from_env(env):
    return Limits(
        _parse("DR_RUN_TOKEN_CAP", env.get("DR_RUN_TOKEN_CAP")),
        _parse("DR_DAILY_TOKEN_BUDGET", env.get("DR_DAILY_TOKEN_BUDGET")),
        _parse("DR_RATE_LIMIT_RUNS_PER_IP_PER_HOUR", env.get("DR_RATE_LIMIT_RUNS_PER_IP_PER_HOUR")),
    )


def limits_from_record(record):
    errs = _schemas.errors("limits_record.schema.json", record)
    if errs:
        raise LimitsError("limits record fails schema: " + "; ".join(errs[:3]))
    if record["record_status"] != "LDR_APPROVED":
        raise LimitsError("limits take effect only from an LDR_APPROVED record")
    p = record["proposed"]
    return Limits(p["run_token_cap"], p["daily_token_budget"], p["runs_per_ip_per_hour"])
