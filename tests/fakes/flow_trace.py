"""Complete local flow trace over REAL loopback HTTP: launches tests/fakes/launch_fake.py as a subprocess, drives the whole flow with urllib,
records every request, then tears the launcher down by closing its stdin. Fakes only; no browser, no real model, runner or Docker.

   python -m tests.fakes.flow_trace [scenario ...]        (from the repository root; default: every scenario plus the UNSET-limits case)
The polling bound below is this tool's own patience, not a product setting.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
POLL_SECONDS, POLL_LIMIT = 0.2, 900


def launch(scenario, per_ip="50", ttl="600"):
    p = subprocess.Popen([sys.executable, "-m", "tests.fakes.launch_fake", "--scenario", scenario, "--per-ip-runs-per-hour", per_ip,
                          "--download-ttl-seconds", ttl, "--exit-on-stdin-eof"], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True)
    line = p.stdout.readline()
    if not line:
        raise RuntimeError("launcher produced no manifest: " + p.stderr.read()[:500])
    return p, json.loads(line)


def stop(p, manifest):
    p.stdin.close()
    p.wait(timeout=30)
    return {"exit_code": p.returncode, "tmp_dir_removed": not os.path.exists(manifest["tmp_dir"])}


class Client:
    def __init__(self, base, trace):
        self.base, self.trace = base, trace

    def call(self, method, path, body=None, note=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                status, raw = r.status, r.read()
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read()
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except ValueError:
            parsed = raw
        self.trace.append(f"{method} {path} -> {status}" + (f"   [{note(parsed)}]" if note and isinstance(parsed, dict) else ""))
        return status, parsed


def flow(scenario, per_ip="50", ttl="600"):
    trace = [f"## scenario `{scenario}` (per-ip {per_ip}, link ttl {ttl})"]
    p, m = launch(scenario, per_ip, ttl)
    result = {"scenario": scenario, "manifest": m}
    try:
        c = Client(m["base_url"], trace)
        trace.append(f"launcher ready at {m['base_url']} pid {m['pid']}; index served: {m['static_dir_has_index']}")
        st, _ = c.call("GET", "/healthz")
        result["healthz"] = st
        c.call("GET", "/api/v1/datasets", note=lambda b: f"{len(b['datasets'])} dataset")
        st, q = c.call("GET", "/api/v1/intake", note=lambda b: f"{len(b['items'])} questions")
        st, root = c.call("GET", "/")
        result["root_status"] = st
        if m["static_dir_has_index"] and isinstance(root, (bytes, bytearray)):
            for asset in sorted(set(re.findall(rb'(?:src|href)="(/assets/[^"]+)"', root))):
                st, _ = c.call("GET", asset.decode())
                result.setdefault("assets", []).append(st)
        st, run = c.call("POST", "/api/v1/runs", {"dataset_id": m["identities"]["dataset_id"]}, note=lambda b: f"state {b.get('state')}")
        result["create"] = st
        if st != 201:
            return trace, result
        rid = run["run_id"]
        answers = {i["id"]: 3 for i in q["items"]}
        st, scan = c.call("POST", f"/api/v1/runs/{rid}/intake", {"answers": answers}, note=lambda b: f"overall {b.get('overall')}")
        result["intake"] = st
        st, b = c.call("POST", f"/api/v1/runs/{rid}/start", {}, note=lambda b: json.dumps({k: b[k] for k in ("mode", "state") if k in b}))
        result["start"] = st
        if st != 202:
            result["start_body"] = b
            return trace, result
        for _ in range(POLL_LIMIT):
            req = urllib.request.urlopen(m["base_url"] + f"/api/v1/runs/{rid}")
            b = json.loads(req.read().decode())
            if b["state"] in ("AWAITING_APPROVAL", "FAILED_CLOSED"):
                break
            time.sleep(POLL_SECONDS)
        trace.append(f"GET /api/v1/runs/{rid} (polled until terminal) -> state {b['state']}"
                     + (f", failed_at {b.get('failed_at')}" if b["state"] == "FAILED_CLOSED" else ""))
        result["state"] = b["state"]
        st, pkt = c.call("GET", f"/api/v1/runs/{rid}/packet", note=lambda b: f"outcome {b['outcome']['result']} preferred {b['outcome']['preferred_path_id']}")
        result["packet"] = pkt
        st, ex = c.call("GET", f"/api/v1/runs/{rid}/executions") if b["state"] == "AWAITING_APPROVAL" else (None, None)
        if ex is not None:
            result["attempts"] = [(e["path_id"], e["attempt"]) for e in ex]
        if b["state"] == "AWAITING_APPROVAL":
            c.call("POST", f"/api/v1/runs/{rid}/approve", {"action": "confirm"}, note=lambda b: "confirm before view is refused")
            c.call("POST", f"/api/v1/runs/{rid}/approve", {"action": "view"})
            st, conf = c.call("POST", f"/api/v1/runs/{rid}/approve", {"action": "confirm"}, note=lambda b: b["packet"]["approval_gate"]["status"])
            result["confirmed"] = conf["packet"] if st == 200 else None
            st, link = c.call("POST", f"/api/v1/runs/{rid}/download-link", {}, note=lambda b: "parts " + ",".join(b["parts"]))
            if st == 200:
                for part, url in link["parts"].items():
                    c.call("GET", url)
        else:
            st, link = c.call("POST", f"/api/v1/runs/{rid}/download-link", {}, note=lambda b: "parts " + ",".join(b["parts"]))
        c.call("GET", f"/api/v1/runs/{rid}/journal", note=lambda b: f"{len(b['entries'])} entries")
        return trace, result
    finally:
        result["teardown"] = stop(p, m)
        trace.append(f"teardown: {result['teardown']}")


def main(names):
    names_given = bool(names)
    names = names or ["complete", "correction", "tie", "incomplete", "refusal"]
    out = []
    for n in names:
        t, r = flow(n)
        out += t + [""]
    if not names_given:
        t, r = flow("complete", per_ip="UNSET", ttl="UNSET")
        out += ["(limits UNSET variant of `complete`)"] + t + [""]
    print("\n".join(out))


if __name__ == "__main__":
    main(sys.argv[1:])
