"""Defense-in-depth watchdog; operator installs on sandbox host. Never runs at import."""
import json
import subprocess
import time

def reap(*, docker, operation_seconds, now=None):
    if operation_seconds <= 0:
        raise ValueError("explicit command deadline required")
    def call(args):
        return subprocess.run([docker, *args], capture_output=True, check=True, timeout=operation_seconds, text=True)
    now = time.time() if now is None else now
    ids = call(["ps", "-aq", "--filter", "label=dr.run", "--filter", "label=dr.deadline"]).stdout.split()
    removed = []
    for container_id in ids:
        record = json.loads(call(["inspect", container_id]).stdout)[0]
        labels = record["Config"]["Labels"]
        try:
            deadline = int(labels["dr.deadline"])
        except (ValueError, KeyError):
            raise ValueError("invalid dr.deadline on labeled container") from None
        if now > deadline + 10:
            call(["rm", "-f", "-v", container_id])
            if call(["ps", "-aq", "--no-trunc", "--filter", "id="+container_id]).stdout.strip():
                raise RuntimeError("reaper destroy verification failed")
            removed.append(container_id)
    return removed

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--docker", required=True)
    parser.add_argument("--operation-seconds", required=True, type=float)
    args = parser.parse_args()
    print(json.dumps({"removed": reap(docker=args.docker, operation_seconds=args.operation_seconds)}))
