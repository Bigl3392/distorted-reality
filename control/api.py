"""HTTP API (M5). A stdlib WSGI application: no web framework, so there is no dependency to pin (I-15; the spec allows "FastAPI or Flask" and
leaves the choice to the lead; a different choice is a code change). Serve it behind Caddy on loopback; `serve()` is for local use only.

The API never sees the inference key, the sealed ground truth or the sandbox. It drives Orchestrator objects supplied by `factory(run_id)`.
Public surface (G5 Option 1): the overall index and one generic recommendation only; invalid intake always gets the same generic 422.
No numeric limit is invented: per-IP run limit and download-link TTL are UNSET unless configured, and UNSET means refuse (public mode).
"""
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import threading
from dataclasses import dataclass
from typing import Callable, Optional
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server
from socketserver import ThreadingMixIn

from broker import _schemas
from scan import service as scan_service

from . import approval, orchestrator, packet
from .journal import canonical
from .states import IllegalTransition

GENERIC = scan_service.GENERIC_ERROR
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{43}$")
MAX_BODY = 65536   # implementation guard for request bodies (intake is ~1 KiB); not a spec limit


class ConfigError(Exception):
    pass


@dataclass
class ApiConfig:
    public: bool = True
    operator_token: Optional[str] = None
    per_ip_runs_per_hour: Optional[int] = None      # None = UNSET
    download_ttl_seconds: Optional[int] = None      # None = UNSET
    live_inference_allowed: Callable[[], bool] = lambda: False
    recorded_dir: Optional[str] = None
    runs_dir: Optional[str] = None                  # DR_RUNS_DIR: where each run's journal and bundle files live
    static_dir: Optional[str] = None
    trust_proxy: bool = False
    max_body: int = MAX_BODY


def _pos_int(env, name):
    v = env.get(name, "UNSET")
    if v == "UNSET":
        return None
    if not (isinstance(v, str) and v.isascii() and v.isdigit() and int(v) > 0):
        raise ConfigError(f"{name} must be UNSET or a positive integer")
    return int(v)


def config_from_env(env, **over):
    tok = env.get("DR_OPERATOR_TOKEN") or None
    if tok is not None and len(tok) < 32:
        raise ConfigError("DR_OPERATOR_TOKEN must be at least 32 characters")
    c = dict(operator_token=tok, per_ip_runs_per_hour=_pos_int(env, "DR_RATE_LIMIT_RUNS_PER_IP_PER_HOUR"),
             download_ttl_seconds=_pos_int(env, "DR_PACKET_LINK_TTL_SECONDS"),
             recorded_dir=env.get("DR_RECORDED_RUNS_DIR") or None, runs_dir=env.get("DR_RUNS_DIR") or None, static_dir=env.get("DR_STATIC_DIR") or None,
             trust_proxy=env.get("DR_TRUST_PROXY") == "1")
    c.update(over)
    return ApiConfig(**c)


class Limiter:
    """Sliding one-hour window per bucket. limit None (UNSET) refuses everyone except operator calls."""

    def __init__(self, limit, now):
        self.limit, self.now, self.hits, self.lock = limit, now, {}, threading.Lock()

    def allow(self, bucket, operator):
        if operator:
            return True
        if self.limit is None:
            return False
        t = self.now()
        with self.lock:
            hits = [h for h in self.hits.get(bucket, []) if t - h < 3600]
            ok = len(hits) < self.limit
            if ok:
                hits.append(t)
            self.hits[bucket] = hits
            return ok


class HttpError(Exception):
    def __init__(self, status, body):
        self.status, self.body = status, body


class App:
    def __init__(self, factory, dataset, config, now=None):
        import time
        self._factory, self._dataset, self.cfg = factory, dataset, config
        self._now = now or time.time
        self._limiter = Limiter(config.per_ip_runs_per_hour, self._now)
        self._runs, self._threads, self._links = {}, {}, {}
        self._lock = threading.Lock()
        R = lambda p: re.compile("^" + p + "$")
        self._routes = [
            ("GET", R(r"/healthz"), self._healthz),
            ("GET", R(r"/api/v1/datasets"), self._datasets),
            ("GET", R(r"/api/v1/intake"), self._intake_questions),
            ("POST", R(r"/api/v1/runs"), self._create),
            ("GET", R(r"/api/v1/runs/(?P<rid>[^/]+)"), self._status),
            ("POST", R(r"/api/v1/runs/(?P<rid>[^/]+)/intake"), self._intake),
            ("POST", R(r"/api/v1/runs/(?P<rid>[^/]+)/start"), self._start),
            ("GET", R(r"/api/v1/runs/(?P<rid>[^/]+)/(?P<part>mri|scan|council|executions|journal|packet)"), self._section),
            ("POST", R(r"/api/v1/runs/(?P<rid>[^/]+)/approve"), self._approve),
            ("POST", R(r"/api/v1/runs/(?P<rid>[^/]+)/download-link"), self._link),
            ("GET", R(r"/api/v1/download/(?P<tok>[^/]+)/(?P<part>packet|journal|events|rule)"), self._download),
            ("GET", R(r"/api/v1/recorded-runs"), self._recorded_list),
            ("GET", R(r"/api/v1/recorded-runs/(?P<rec>[^/]+)"), self._recorded_one),
            ("POST", R(r"/api/v1/operator/stress"), self._stress),
        ]

    # ---- WSGI ---------------------------------------------------------------------------------------------------------------
    def __call__(self, environ, start_response):
        try:
            status, body, headers = self._dispatch(environ)
        except HttpError as e:
            status, body, headers = e.status, e.body, {}
        except Exception:
            status, body, headers = 500, {"error": "internal error"}, {}
        if isinstance(body, (dict, list)):
            payload, ctype = json.dumps(body).encode("utf-8"), "application/json; charset=utf-8"
        elif isinstance(body, str):
            payload, ctype = body.encode("utf-8"), "text/plain; charset=utf-8"
        else:
            payload, ctype = body, "application/octet-stream"
        h = {"Content-Type": ctype, "Content-Length": str(len(payload)), "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store",
             "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY"}
        h.update(headers)
        start_response(f"{status} {_REASON.get(status, 'Status')}", list(h.items()))
        return [payload]

    def _dispatch(self, environ):
        method, path = environ["REQUEST_METHOD"], environ.get("PATH_INFO", "/")
        if path.startswith("/api/") or path == "/healthz":
            allowed = False
            for m, rx, fn in self._routes:
                mt = rx.match(path)
                if mt:
                    allowed = True
                    if m == method:
                        return fn(environ, **mt.groupdict())
            raise HttpError(405 if allowed else 404, {"error": "method not allowed" if allowed else "not found"})
        if method not in ("GET", "HEAD"):
            raise HttpError(404, {"error": "not found"})
        return self._static(path)

    # ---- helpers ------------------------------------------------------------------------------------------------------------
    def _body(self, environ, strict=True):
        try:
            n = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            n = 0
        if n > self.cfg.max_body:
            raise HttpError(413, {"error": "request too large"})
        raw = environ["wsgi.input"].read(n) if n else b""
        if not raw:
            return {}
        try:
            v = json.loads(raw.decode("utf-8"))
        except ValueError:
            if strict:
                raise HttpError(400, {"error": "invalid request"}) from None
            return None
        return v

    def _is_operator(self, environ):
        tok, have = self.cfg.operator_token, environ.get("HTTP_X_OPERATOR_TOKEN", "")
        return bool(tok) and hmac.compare_digest(tok.encode(), have.encode("utf-8", "replace"))

    def _bucket(self, environ):
        ip = environ.get("REMOTE_ADDR", "")
        if self.cfg.trust_proxy:
            xff = environ.get("HTTP_X_FORWARDED_FOR", "")
            if xff:
                ip = xff.split(",")[-1].strip()
        return hashlib.sha256(ip.encode()).hexdigest()[:16]

    def _get(self, rid):
        if not _ID.match(rid) or rid not in self._runs:
            raise HttpError(404, {"error": "run not found"})
        return self._runs[rid]

    def join(self, rid, timeout=None):
        t = self._threads.get(rid)
        if t:
            t.join(timeout)

    # ---- handlers -----------------------------------------------------------------------------------------------------------
    def _healthz(self, environ):
        return 200, {"ok": True}, {}

    def _datasets(self, environ):
        d = self._dataset
        return 200, {"datasets": [{"dataset_id": d.dataset_id, "label": "SYNTHETIC", "case_count": d.cases_total}]}, {}

    def _intake_questions(self, environ):
        q = scan_service.load_questions()
        return 200, {"scale": q["scale"], "prompt": q["prompt"], "items": q["items"]}, {}

    def _create(self, environ):
        body = self._body(environ)
        if not isinstance(body, dict) or body.get("dataset_id") != self._dataset.dataset_id:
            raise HttpError(404, {"error": "unknown dataset"})
        op = self._is_operator(environ)
        if self.cfg.public and not op and self.cfg.per_ip_runs_per_hour is None:
            raise HttpError(503, {"error": "service limits are not configured: new runs are disabled",
                                  "recorded_runs_url": "/api/v1/recorded-runs"})
        if not self._limiter.allow(self._bucket(environ), op):
            raise HttpError(429, {"error": "run limit reached for now"})
        rid = "run-" + secrets.token_hex(6)
        orch = self._factory(rid)
        run = orch.create(rid)
        with self._lock:
            self._runs[rid] = (orch, run)
        return 201, {"run_id": rid, "state": run.state.state, "mri": run.mri}, {}

    def _status(self, environ, rid):
        orch, run = self._get(rid)
        out = {"run_id": rid, "state": run.state.state, "history": list(run.state.history), "label": run.label}
        if run.state.state == "FAILED_CLOSED":
            out.update(failed_at=run.state.failed_at, failure_reason=run.state.failure_reason)
        if run.packet is not None:
            out["outcome"] = run.packet["outcome"]
        return 200, out, {}

    def _intake(self, environ, rid):
        orch, run = self._get(rid)
        body = self._body(environ, strict=False)
        if run.state.state != "MRI_DONE":
            raise HttpError(409, {"error": f"run is {run.state.state}"})
        answers = body.get("answers") if isinstance(body, dict) else None
        try:
            scan = orch.intake(run, answers)
        except scan_service.ScanRejected:
            raise HttpError(422, {"error": GENERIC}) from None
        return 200, scan, {}

    def _start(self, environ, rid):
        orch, run = self._get(rid)
        if run.state.state != "SCAN_DONE" or rid in self._threads:
            raise HttpError(409, {"error": f"run is {run.state.state}"})
        if not self.cfg.live_inference_allowed():
            raise HttpError(409, {"mode": "recorded", "error": "live inference is not available; a recorded real run can be viewed instead",
                                  "recorded_runs": self._recorded()})
        t = threading.Thread(target=orch.proceed, args=(run,), daemon=True)
        self._threads[rid] = t
        t.start()
        return 202, {"run_id": rid, "state": "STARTED"}, {}

    def _section(self, environ, rid, part):
        orch, run = self._get(rid)
        if part == "journal":
            return 200, {"entries": list(run.journal.entries)}, {}
        v = {"mri": run.mri, "scan": run.scan, "council": run.council, "executions": run.executions or None,
             "packet": run.packet_confirmed or run.packet}[part]
        if v is None:
            raise HttpError(404, {"error": f"{part} not available yet"})
        return 200, v, {}

    def _approve(self, environ, rid):
        orch, run = self._get(rid)
        body = self._body(environ)
        action = body.get("action") if isinstance(body, dict) else None
        if action not in ("view", "confirm"):
            raise HttpError(400, {"error": "action must be view or confirm"})
        try:
            p = orch.view(run) if action == "view" else orch.confirm(run)
        except approval.ApprovalError as e:
            raise HttpError(409, {"error": str(e)}) from None
        return 200, {"packet": p}, {}

    def _link(self, environ, rid):
        orch, run = self._get(rid)
        if self.cfg.download_ttl_seconds is None:
            raise HttpError(503, {"error": "download links are disabled until the link lifetime is configured"})
        if run.packet is None:
            raise HttpError(409, {"error": "no packet yet"})
        if run.packet.get("packet_status") != "INCOMPLETE" and not run.viewed and run.packet_confirmed is None:
            raise HttpError(409, {"error": "view the packet before downloading it"})
        tok = secrets.token_urlsafe(32)
        exp = self._now() + self.cfg.download_ttl_seconds
        self._links[tok] = (rid, exp)
        base = f"/api/v1/download/{tok}"
        return 200, {"url": base, "parts": {p: f"{base}/{p}" for p in ("packet", "journal", "events", "rule")},
                     "expires_in_seconds": self.cfg.download_ttl_seconds}, {}

    def _download(self, environ, tok, part):
        link = self._links.get(tok) if _TOKEN.match(tok) else None
        if link is None:
            raise HttpError(404, {"error": "not found"})
        rid, exp = link
        if self._now() > exp:
            self._links.pop(tok, None)
            raise HttpError(410, {"error": "link expired"})
        orch, run = self._get(rid)
        if part == "packet":
            p = run.packet_confirmed or run.packet
            run.journal.append("packet_downloaded", "control", {"packet_sha256": p["packet_sha256"], "ts": orch.clock()})
            return 200, p, {"Content-Disposition": f'attachment; filename="{rid}-packet.json"'}
        if part == "journal":
            return 200, "".join(canonical(e) + "\n" for e in run.journal.entries), {"Content-Disposition": f'attachment; filename="{rid}-journal.jsonl"'}
        if part == "events":
            return 200, canonical(run.events) + "\n" if getattr(run, "events", None) is not None else "[]\n", {}
        return 200, getattr(run, "rule_text", ""), {}

    # ---- recorded runs (never fabricated: only validated files an operator placed there) -----------------------------------
    def _recorded(self):
        d, out = self.cfg.recorded_dir, []
        if not d or not os.path.isdir(d):
            return out
        for name in sorted(os.listdir(d)):
            rec = self._load_recorded(name)
            if rec:
                out.append({"recorded_run_id": name, "recorded_on": rec["meta"].get("recorded_on"), "run_id": rec["packet"]["run_id"]})
        return out

    def _load_recorded(self, name):
        if not _ID.match(name) or not self.cfg.recorded_dir:
            return None
        base = os.path.join(self.cfg.recorded_dir, name)
        try:
            with open(os.path.join(base, "packet.json"), encoding="utf-8") as f:
                p = json.load(f)
        except (OSError, ValueError):
            return None
        if not isinstance(p, dict) or _schemas.errors("evidence_packet.schema.json", p) or p.get("packet_sha256") != packet.packet_hash(p):
            return None             # served only if it validates AND its own hash recomputes
        try:
            with open(os.path.join(base, "meta.json"), encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            meta = {}
        return {"packet": p, "meta": meta if isinstance(meta, dict) else {}}

    def _recorded_list(self, environ):
        return 200, {"recorded_runs": self._recorded()}, {}

    def _recorded_one(self, environ, rec):
        r = self._load_recorded(rec)
        if r is None:
            raise HttpError(404, {"error": "not found"})
        return 200, {"recorded": True, "label": "RECORDED REAL RUN", "recorded_run_id": rec,
                     "recorded_on": r["meta"].get("recorded_on"), "packet": r["packet"]}, {}

    # ---- operator-only ------------------------------------------------------------------------------------------------------
    def _stress(self, environ):
        if not self._is_operator(environ):
            raise HttpError(404, {"error": "not found"})
        raise HttpError(501, {"error": "the stress test is not part of this build: it needs the sandbox runner and an explicit authorization"})

    # ---- static files -------------------------------------------------------------------------------------------------------
    def _static(self, path):
        root = self.cfg.static_dir
        if not root or "\x00" in path or "\\" in path:
            raise HttpError(404, {"error": "not found"})
        root = os.path.realpath(root)
        target = os.path.realpath(os.path.join(root, path.lstrip("/")))
        if not (target == root or target.startswith(root + os.sep)) or not os.path.isfile(target):
            target = os.path.join(root, "index.html")       # single-page-app fallback; never a path outside root
            if not os.path.isfile(target):
                raise HttpError(404, {"error": "not found"})
        with open(target, "rb") as f:
            data = f.read()
        ctype = mimetypes.guess_type(target)[0] or "application/octet-stream"
        return 200, data, {"Content-Type": ctype, "Content-Security-Policy": "default-src 'self'"}


_REASON = {200: "OK", 201: "Created", 202: "Accepted", 400: "Bad Request", 404: "Not Found", 405: "Method Not Allowed", 409: "Conflict",
           410: "Gone", 413: "Payload Too Large", 422: "Unprocessable Entity", 429: "Too Many Requests", 500: "Internal Server Error",
           501: "Not Implemented", 503: "Service Unavailable"}


class _Threaded(ThreadingMixIn, WSGIServer):
    daemon_threads = True
    request_queue_size = 128   # stdlib default is 5: a burst of concurrent clients stalled ~1.2 s on a SYN retransmit (T-022); 128 is the conventional value, not a limit


class _Quiet(WSGIRequestHandler):
    def log_message(self, *a):
        pass


def serve(app, port, host="127.0.0.1"):
    """Local use only. Production sits behind Caddy; this binds loopback unless told otherwise."""
    return make_server(host, port, app, server_class=_Threaded, handler_class=_Quiet)
