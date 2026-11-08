"""Vultr Serverless Inference client. One class, one base URL constant, key never leaves this module."""
import datetime
import hashlib
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from .limits import DailyBudget, Limits
from .models import BASE_URL, ModelsConfig


class BrokerError(Exception):
    """Fail-closed error. The message is always redacted."""


class ModelMismatch(BrokerError):
    def __init__(self, msg, record):
        super().__init__(msg)
        self.record = record


class BudgetExceeded(BrokerError):
    pass


class LiveInferenceRefused(BrokerError):
    pass


@dataclass(frozen=True)
class CallResult:
    text: str
    record: dict
    fallback_used: bool


class UrllibTransport:
    """POST JSON to base_url + path. timeout_s is deliberately UNSET by default: no value was ruled (see HANDOFF)."""

    def __init__(self, base_url=BASE_URL, timeout_s=None):
        self.base_url = base_url
        self.timeout_s = timeout_s

    def post(self, path, headers, body):
        req = urllib.request.Request(self.base_url + path, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")


_BEARER = re.compile(r"Bearer\s+\S+", re.I)


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class BrokerClient:
    def __init__(self, models: ModelsConfig, api_key: str, limits: Limits, daily: DailyBudget,
                 public: bool = True, transport=None, clock=None):
        if not api_key:
            raise BrokerError("no inference key supplied")
        self.__key = api_key
        self._models = models
        self._limits = limits
        self._daily = daily
        self._public = public
        self._transport = transport or UrllibTransport()
        self._clock = clock or _now
        self._failed = None
        self._n = 0
        self.tokens_used = 0
        self.records = []
        self.log = []

    def __repr__(self):
        return f"BrokerClient(public={self._public}, calls={self._n}, tokens_used={self.tokens_used})"

    def _redact(self, text):
        return _BEARER.sub("Bearer [REDACTED]", str(text).replace(self.__key, "[REDACTED]"))

    def call(self, role, messages, *, use_fallback=False) -> CallResult:
        if self._failed is not None:
            raise self._failed
        cfg = self._models.role(role)
        model_id = self._models.fallback_for(role) if use_fallback else cfg.model_id
        if self._public and not self._limits.fully_set:
            raise LiveInferenceRefused("limits are UNSET: live public inference refused, serve the recorded run")
        if self._limits.run_token_cap is not None and self.tokens_used >= self._limits.run_token_cap:
            raise BudgetExceeded("per-run token cap reached")
        if self._limits.daily_token_budget is not None and self._daily.used >= self._limits.daily_token_budget:
            raise BudgetExceeded("daily token budget reached")

        body = {"model": model_id, "messages": messages, "temperature": cfg.temperature, "max_tokens": cfg.max_tokens}
        prompt_sha = _sha(json.dumps(messages, sort_keys=True, separators=(",", ":")))
        started = self._clock()
        try:
            status, text = self._transport.post(
                "/chat/completions",
                {"Content-Type": "application/json", "Authorization": "Bearer " + self.__key},
                json.dumps(body).encode("utf-8"),
            )
        except Exception as e:  # network failure: fail closed, redacted
            raise BrokerError("transport failure: " + self._redact(type(e).__name__ + ": " + str(e))) from None
        ended = self._clock()
        if status != 200:
            raise BrokerError(f"HTTP {status}: " + self._redact(text[:200]))
        try:
            resp = json.loads(text)
            content = resp["choices"][0]["message"]["content"]
            resp_model = resp.get("model")
            usage = resp["usage"]
            tin, tout = usage["prompt_tokens"], usage["completion_tokens"]
            if type(tin) is not int or type(tout) is not int or tin < 0 or tout < 0:     # F2: usage may never reduce or skip consumption
                raise ValueError("bad usage")
        except Exception:
            raise BrokerError("malformed or incomplete inference response (usage and content are required)") from None
        if not isinstance(content, str):
            raise BrokerError("response content is not text")
        resp_model = resp_model if isinstance(resp_model, str) else ""
        raw_content = content
        content = content.replace(self.__key, "[REDACTED]")        # F1: model text is never allowed to carry the key onward
        model_match = resp_model == model_id                       # strict comparison on the RAW string, before any scrubbing
        resp_model = self._redact(resp_model)                      # F1b: response metadata is scrubbed too (record, ModelMismatch.record, records)

        self._n += 1
        self.tokens_used += tin + tout
        self._daily.add(tin + tout)
        record = {
            "call_id": f"call-{self._n:03d}",
            "role": role,
            "requested_model": model_id,
            "response_model": resp_model,
            "model_match": model_match,
            "started": started,
            "ended": ended,
            "prompt_sha256": prompt_sha,
            "response_sha256": _sha(raw_content),
            "tokens_in": tin,
            "tokens_out": tout,
        }
        self.records.append(record)
        self.log.append({"call_id": record["call_id"], "role": role, "model": model_id, "model_match": record["model_match"]})
        if not record["model_match"]:
            self._failed = ModelMismatch("response.model != requested model: run fails closed", record)
            raise self._failed
        if self._limits.run_token_cap is not None and self.tokens_used > self._limits.run_token_cap:
            raise BudgetExceeded("per-run token cap exceeded")
        if self._limits.daily_token_budget is not None and self._daily.used > self._limits.daily_token_budget:
            raise BudgetExceeded("daily token budget exceeded")        # F3: the crossing call is counted, then fails closed
        return CallResult(content, record, use_fallback)
