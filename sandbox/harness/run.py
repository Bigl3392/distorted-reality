#!/usr/local/bin/python3
"""SB1 entry point, executed INSIDE the isolated container. Stdlib only."""
import contextlib
import json
import os
import signal
import sys

def timeout_handler(signum, frame):
    raise TimeoutError("sandbox wall cap reached")

def main():
    try:
        request = json.load(sys.stdin)
        if set(request) != {"contract", "code", "events", "caps"} or request["contract"] != "SB1":
            raise ValueError("invalid SB1 request")
        seconds = request["caps"]["wall_seconds"]
        if type(seconds) is not int or not 1 <= seconds <= 30:
            raise ValueError("invalid wall cap")
        if hasattr(signal, "SIGALRM"):
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(seconds)
        namespace = {"__name__": "sandbox_apply"}
        # stdout protocol is separate from incidental prints in model-written code.
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            exec(compile(request["code"], "<sandbox-apply>", "exec"), namespace)
            function = namespace.get("apply")
            if not callable(function):
                raise ValueError("apply(events) missing")
            response = function(request["events"])
        if not isinstance(response, dict) or set(response) != {"flagged_cases", "resolutions", "manual_touch_cases", "self_metrics", "error"}:
            raise ValueError("invalid apply return keys")
        response = {"contract": "SB1", "ok": True, **response}
    except BaseException as exc:
        # No exception values or payload text leave the harness.
        response = {"contract": "SB1", "ok": False, "error": type(exc).__name__}
    finally:
        if hasattr(signal, "SIGALRM"):
            signal.alarm(0)
    encoded = json.dumps(response, sort_keys=True, separators=(",", ":"), allow_nan=False)
    sys.stdout.write(encoded)

if __name__ == "__main__":
    main()
