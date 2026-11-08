"""M4 runner behind M5's Runner interface: `run(job, code, events, *, attempt, emit) -> {"receipt", "response"}`.

Binding (PROPOSED_M5_M4_BINDING.md, answered in handoffs/M4/BINDING_REPLY_Walter.md): M4's `run_job` returns an `Execution`; M5 reads thirteen
fields from `receipt` and composes the rest of the R1 receipt itself. M5 never calls `Execution.receipt()`. This adapter maps, scans and binds. It
adds no timing, count or limit of its own: the Docker command deadline is the operator's `operation_seconds`.

`secret_scan` (M5 owns the composite; M4 never holds the key):
- Real dispatch needs an explicit scanner: `secret_values`, a callable naming every protected value (the inference key, via
  `broker_factory.key_scanner`). A runner with neither a scanner nor the explicit `fixture_unscanned=True` label is refused at construction. Fixture
  mode is for fakes only, is refused with a real DockerExecutor, and never reports `scan_passed: true`.
- Protected values are refused in code, events and the SB1 request bytes before they leave (stdin), and searched in the bounded raw stdout and
  stderr of every Docker call, the decoded SB1 values and keys, and each journal entry, in raw and JSON-escaped forms, on every path including
  non-normal ends and parser errors. A hit fails the run closed with a value-free SandboxError (no cause, no context), after M4 has cleaned up.
- Hashes are M4's hashes of the bytes it captured. Nothing is redacted or rewritten, so no hash is of altered bytes.
- `canary_present_in_env` is the frozen constant `false`. It is a documented configuration declaration (M4's DockerExecutor passes only PATH, HOME,
  USERPROFILE, SYSTEMROOT, SSH_AUTH_SOCK to the Docker CLI), NOT a per-run observation and NOT AT-15; the paired canary probe is NOT_RUN here.

Non-normal ends: when M4 returns an Execution with no output (stdout overflow gives termination "error"; OOM and timeout kills likewise), the adapter
returns a controller-generated SB1 failure envelope and journals one entry (`error`, `adapter_generated_response: true`) saying so, with M4's observed
termination, exit status and the hash of the captured stdout (for overflow, the bounded prefix). M5 already excludes such a path from the decision.
When M4 raises (bad JSON, invalid SB1 shape, preflight or transport failure, unverifiable cleanup) nothing is fabricated: the sanitized error
propagates and M5 fails closed. M4's own lock and deadline checks are kept: a real executor is observed through a DockerExecutor subclass.
"""
import json
import re

from sandbox.runner import DockerExecutor, SandboxError, run_job

from .api import ConfigError

_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")
_BLOCKED = "secret scan: a protected value was found in the dispatch or the sandbox output; the run fails closed"


class _Scan:
    """Known-value search over bytes, text and decoded structures. Never returns or stores a match."""

    def __init__(self, values):
        self._forms = [f for v in values for f in {v, json.dumps(v)[1:-1], json.dumps(v, ensure_ascii=False)[1:-1]} if f]
        self._values = list(values)

    def text(self, t):
        return isinstance(t, str) and any(f in t for f in self._forms)

    def raw(self, b):
        if not b:
            return False
        if any(f.encode("utf-8") in b for f in self._forms) or self.text(b.decode("utf-8", "replace")):
            return True
        try:
            return self.obj(json.loads(b))
        except (ValueError, UnicodeError, RecursionError):
            return False

    def obj(self, o):
        for s in _strings(o):
            if any(v in s for v in self._values):
                return True
        return self.text(json.dumps(o, sort_keys=True)) or self.text(json.dumps(o, sort_keys=True, ensure_ascii=False))


def _strings(o):
    stack = [o]
    while stack:
        x = stack.pop()
        if isinstance(x, str):
            yield x
        elif isinstance(x, dict):
            for k, v in x.items():
                stack.append(k)
                stack.append(v)
        elif isinstance(x, (list, tuple)):
            stack.extend(x)


class _Tap:
    """Records every command result and refuses protected bytes in stdin. Delegates to the real executor unchanged."""

    def _tap_before(self, stdin):
        if self._scan is not None and self._scan.raw(stdin):
            raise SandboxError(_BLOCKED)

    def _tap_after(self, result):
        self._sink.append(result)
        return result


class _TapDocker(_Tap, DockerExecutor):
    """A DockerExecutor subclass, so M4's `isinstance(executor, DockerExecutor)` lock and deadline checks still apply."""

    def __init__(self, inner, scan, sink):
        DockerExecutor.__init__(self)
        self.prefix, self._scan, self._sink = list(inner.prefix), scan, sink

    def call(self, args, *, stdin=b"", deadline=None, limit=524288):
        self._tap_before(stdin)
        return self._tap_after(DockerExecutor.call(self, args, stdin=stdin, deadline=deadline, limit=limit))


class _TapFake(_Tap):
    def __init__(self, inner, scan, sink):
        self._inner, self._scan, self._sink = inner, scan, sink

    def call(self, args, **kw):
        self._tap_before(kw.get("stdin", b""))
        return self._tap_after(self._inner.call(args, **kw))


class SandboxRunner:
    def __init__(self, *, lock, executor, operation_seconds=None, lock_path=None, clock=None, secret_values=None, fixture_unscanned=False):
        if fixture_unscanned:
            if secret_values is not None:
                raise ConfigError("fixture_unscanned and secret_values are mutually exclusive")
            if isinstance(executor, DockerExecutor):
                raise ConfigError("fixture_unscanned is for fakes only and is refused with a real Docker executor")
        elif secret_values is None:
            raise ConfigError("a real runner needs explicit secret_values wiring (broker_factory.key_scanner); an unscanned runner must be "
                              "labelled fixture_unscanned=True and is for fakes only")
        if isinstance(executor, DockerExecutor) and type(executor) is not DockerExecutor:
            raise ConfigError("a DockerExecutor subclass cannot be observed without bypassing M4's checks")
        self._lock, self._executor, self._seconds = lock, executor, operation_seconds
        self._lock_path, self._clock, self._secret_values = lock_path, clock, secret_values
        self.scan_mode = "fixture-unscanned" if fixture_unscanned else "configured"

    def _scanner(self):
        if self._secret_values is None:
            return None
        values = [v for v in self._secret_values() if isinstance(v, str) and v]
        if not values:
            raise SandboxError("secret scan is configured with no protected values; the run fails closed before dispatch")
        return _Scan(values)

    def run(self, job, code, events, *, attempt, emit):
        scan = self._scanner()
        if scan is not None and (scan.obj(code) or scan.obj(events) or scan.obj(job)):
            raise SandboxError(_BLOCKED)
        sink = []
        tap = (_TapDocker if isinstance(self._executor, DockerExecutor) else _TapFake)(self._executor, scan, sink)
        bind = {"path_id": job.get("path_id"), "attempt": attempt, "requested_name": f"dr-{job.get('run_id')}-{job.get('path_id')}-a{attempt}"}

        def journal(kind, data):
            data = dict(data)
            if kind.startswith("sandbox_"):
                for k, v in bind.items():
                    data.setdefault(k, v)
            if scan is not None and scan.obj(data):
                raise SandboxError(_BLOCKED)
            return emit(kind, data)

        failure = None
        try:
            ex = run_job(job, code, events, lock=self._lock, executor=tap, attempt=attempt, journal=journal, clock=self._clock,
                         operation_seconds=self._seconds, lock_path=self._lock_path)
        except SandboxError as exc:
            failure = str(exc)
        if failure is not None:  # raised outside the except block: no cause, no context
            if scan is not None and (scan.text(failure) or self._captured_hit(scan, sink)):
                raise SandboxError(_BLOCKED)
            raise SandboxError(failure)
        if scan is not None and self._captured_hit(scan, sink):
            raise SandboxError(_BLOCKED)
        generated = ex.output is None
        if generated and ex.termination == "normal":
            raise SandboxError("binding violation: a normal end returned no SB1 output")
        if dict(ex.caps) != dict(job["caps"]):
            raise SandboxError("binding violation: caps in the execution differ from the dispatched job")
        for name in ("created_at", "started_at", "ended_at", "destroyed_at"):
            ts = getattr(ex, name)
            if not isinstance(ts, str) or not _TS.match(ts) or ts.startswith("0001-"):
                raise SandboxError(f"binding violation: {name} is not a usable timestamp")
        response = ex.output if not generated else {"contract": "SB1", "ok": False, "error": f"sandbox ended: {ex.termination}"}
        if scan is not None and scan.obj(response):
            raise SandboxError(_BLOCKED)
        if generated:
            journal("error", {"adapter_generated_response": True, "detail": "sandbox returned no SB1 output; the failure envelope is controller-generated, "
                              "not container stdout", "sandbox_id": ex.sandbox_id, "termination": ex.termination, "exit_status": ex.exit_status,
                              "stdout_sha256": ex.stdout_sha256, **bind})
        receipt = {"sandbox_id": ex.sandbox_id, "image_digest": ex.lock.image_digest, "created_at": ex.created_at,
                   "started_at": ex.started_at, "ended_at": ex.ended_at, "destroyed_at": ex.destroyed_at,
                   "destroy_verified": ex.destroy_verified, "docker_flags_sha256": ex.flags_sha256, "exit_status": ex.exit_status,
                   "termination": ex.termination, "peak_memory_mb": None, "stdout_sha256": ex.stdout_sha256,
                   "secret_scan": {"canary_present_in_env": False, "scan_passed": scan is not None}}
        return {"receipt": receipt, "response": response}

    @staticmethod
    def _captured_hit(scan, sink):
        return any(scan.raw(r.stdout) or scan.raw(r.stderr) for r in sink)
