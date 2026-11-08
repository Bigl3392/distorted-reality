"""Fake Vultr Serverless Inference server for tests (M3). Local only, stdlib only, no network beyond 127.0.0.1.

Speaks just enough of the OpenAI-compatible /v1/chat/completions shape for the broker tests.
Behaviour is scripted per request: a queue of Reply objects; when the queue is empty it answers 500.
It records every request (path, headers, parsed body) so tests can assert what the broker sent.
"""
import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional


@dataclass
class Reply:
    content: str = "{}"
    model: Optional[str] = None      # None = echo the requested model; set to simulate a mismatch
    status: int = 200
    prompt_tokens: Optional[int] = 10
    completion_tokens: Optional[int] = 5
    raw_body: Optional[str] = None   # if set, sent verbatim (used for error bodies)
    omit_usage: bool = False


@dataclass
class Recorded:
    path: str
    headers: dict
    body: dict


class FakeVultr:
    def __init__(self):
        self.queue = []
        self.requests = []
        self._lock = threading.Lock()
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):  # silence
                pass

            def do_POST(self):
                n = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(n).decode("utf-8")
                try:
                    body = json.loads(raw)
                except Exception:
                    body = {"_unparseable": raw}
                with outer._lock:
                    outer.requests.append(Recorded(self.path, {k.lower(): v for k, v in self.headers.items()}, body))
                    reply = outer.queue.pop(0) if outer.queue else Reply(status=500, raw_body="no scripted reply")
                if reply.raw_body is not None:
                    payload = reply.raw_body.encode("utf-8")
                else:
                    resp = {
                        "id": "fake-1",
                        "object": "chat.completion",
                        "model": reply.model if reply.model is not None else body.get("model"),
                        "choices": [{"index": 0, "message": {"role": "assistant", "content": reply.content}, "finish_reason": "stop"}],
                    }
                    if not reply.omit_usage:
                        resp["usage"] = {"prompt_tokens": reply.prompt_tokens, "completion_tokens": reply.completion_tokens}
                    payload = json.dumps(resp).encode("utf-8")
                self.send_response(reply.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self._srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self._thread = threading.Thread(target=self._srv.serve_forever, daemon=True)

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self._srv.server_address[1]}/v1"

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._srv.shutdown()
        self._srv.server_close()

    def script(self, *replies):
        with self._lock:
            self.queue.extend(replies)
