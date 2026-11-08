"""Control-side runner. No Docker access occurs at import. A verified lock is mandatory."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
import threading
import time

from broker._schemas import errors

DEFAULT_CAPS = {"wall_seconds": 30, "memory_mb": 256, "pids": 64, "cpus": 1, "stdout_bytes": 524288}
ID = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")
DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")


class SandboxError(RuntimeError):
    pass


@dataclass(frozen=True)
class ImageLock:
    docker_engine_version: str
    image_digest: str
    base_image: str


def load_lock(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        lock = ImageLock(**data)
    except (OSError, ValueError, TypeError) as exc:
        raise SandboxError("G4: image/version lock missing or invalid") from exc
    if not lock.docker_engine_version or "<" in lock.docker_engine_version:
        raise SandboxError("G4: exact Docker Engine version required")
    if not DIGEST.fullmatch(lock.image_digest) or not re.fullmatch(r"python:3\.12-slim@sha256:[a-f0-9]{64}", lock.base_image):
        raise SandboxError("G4: pinned base and built-image digests required")
    return lock


def flags(job, lock, *, attempt, deadline_epoch):
    failures = errors("blackbox_job.schema.json", job)
    if failures:
        raise SandboxError("C2 refused: " + failures[0])
    if type(attempt) is not int or attempt not in (1, 2):
        raise SandboxError("only attempts 1 and 2 are allowed")
    if not DIGEST.fullmatch(lock.image_digest):
        raise SandboxError("image digest is not pinned")
    caps = job["caps"]
    if any(caps[k] > ceiling for k, ceiling in DEFAULT_CAPS.items()):
        raise SandboxError("caps may tighten but never loosen defaults")
    return [
        "create", "--name", f"dr-{job['run_id']}-{job['path_id']}-a{attempt}",
        "--network", "none", "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=32m",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--user", "65534:65534",
        "--memory", f"{caps['memory_mb']}m", "--memory-swap", f"{caps['memory_mb']}m",
        "--memory-reservation", f"{caps['memory_mb']//2}m", "--pids-limit", str(caps["pids"]),
        "--cpus", str(caps["cpus"]), "--ulimit", "nofile=64:64", "--ulimit", "fsize=16777216",
        "--ulimit", "core=0", "--ipc", "none", "--env", "PYTHONHASHSEED=0",
        "--env", "PYTHONDONTWRITEBYTECODE=1", "--label", "dr.run=" + job["run_id"],
        "--label", "dr.deadline=" + str(int(deadline_epoch)), "-i",
        "dr-sandbox@" + lock.image_digest, "/harness/run.py",
    ]


@dataclass
class CommandResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    timed_out: bool = False
    overflow: bool = False


class DockerExecutor:
    """Bounded pipe reader. Uses argv only; never a shell or an env-file."""
    def __init__(self, *, docker="docker", host=None):
        self.prefix = [docker] + (["--host", host] if host else [])

    def call(self, args, *, stdin=b"", deadline=None, limit=524288):
        if deadline is None:
            raise SandboxError("an explicit operation deadline is required")
        # Restrict inherited settings to transport configuration. Inference keys never reach CLI env.
        import os
        env = {k: os.environ[k] for k in ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "SSH_AUTH_SOCK") if k in os.environ}
        proc = subprocess.Popen(self.prefix + list(args), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env=env, shell=False)
        captured = [bytearray(), bytearray()]
        overflow = threading.Event()
        def drain(pipe, index):
            try:
                while block := pipe.read(8192):
                    room = max(0, limit - len(captured[index]))
                    captured[index].extend(block[:room])
                    if len(block) > room:
                        overflow.set()
                        proc.kill()
            finally:
                pipe.close()
        def feed():
            try:
                proc.stdin.write(stdin)
                proc.stdin.flush()
            except (BrokenPipeError, OSError):
                pass
            finally:
                proc.stdin.close()
        readers = [threading.Thread(target=drain, args=(proc.stdout,0), daemon=True),
                   threading.Thread(target=drain, args=(proc.stderr,1), daemon=True)]
        writer = threading.Thread(target=feed, daemon=True)
        for thread in readers + [writer]:
            thread.start()
        expired = False
        try:
            proc.wait(timeout=max(0, deadline-time.monotonic()))
        except subprocess.TimeoutExpired:
            expired = True
            proc.kill()
            proc.wait()
        for thread in readers + [writer]:
            thread.join()
        return CommandResult(proc.returncode, bytes(captured[0]), bytes(captured[1]), expired, overflow.is_set())


@dataclass
class Execution:
    sandbox_id: str
    output: dict | None
    termination: str
    exit_status: int
    destroy_verified: bool
    flags_sha256: str
    stdout_sha256: str
    docker_version: dict
    created_at: str
    started_at: str
    ended_at: str
    destroyed_at: str
    lock: ImageLock
    caps: dict

    def receipt(self, *, job, attempt, metrics, self_metrics, discrepancy, claim_check, journal_head_sha256,
                events_sha256, events_count, secret_scan):
        """M5 supplies computed evidence; runner never invents successful claims or secret scans."""
        receipt = {
            "run_id": job["run_id"], "path_id": job["path_id"], "attempt": attempt, "sandbox_id": self.sandbox_id,
            "image_digest": self.lock.image_digest, "created_at": self.created_at, "started_at": self.started_at,
            "ended_at": self.ended_at, "destroyed_at": self.destroyed_at, "destroy_verified": self.destroy_verified,
            "caps": self.caps, "docker_flags_sha256": self.flags_sha256, "exit_status": self.exit_status,
            "termination": self.termination, "peak_memory_mb": None, "stdout_sha256": self.stdout_sha256,
            "events_sha256": events_sha256, "events_count": events_count, "secret_scan": secret_scan,
            "metrics_recomputed": metrics, "metrics_self_reported": self_metrics, "metrics_discrepancy": discrepancy,
            "claim_check": claim_check, "journal_head_sha256": journal_head_sha256,
        }
        failures = errors("blackbox_run.schema.json", receipt)
        if failures:
            raise SandboxError("R1 invalid: " + failures[0])
        return receipt


def run_job(job, code, events, *, lock, executor, attempt=1, journal=None, clock=None, operation_seconds=None, lock_path=None):
    """operation_seconds must be chosen by operator for real DockerExecutor; no hidden HTTP/CLI timeout."""
    from datetime import datetime, timezone
    if isinstance(executor, DockerExecutor):
        pinned = load_lock(lock_path or Path(__file__).resolve().parents[1] / "docker_image.lock")
        if pinned != lock:
            raise SandboxError("G4: supplied image/version differs from on-disk lock")
    stamp = clock or (lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    emit = journal or (lambda kind, data: None)
    request = {"contract": "SB1", "code": code, "events": events, "caps": job["caps"]}
    failures = errors("sb1_request.schema.json", request)
    if failures:
        raise SandboxError("SB1 input refused: " + failures[0])
    dataset_bytes = b"".join(json.dumps(e, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii") + b"\n" for e in events)
    if hashlib.sha256(dataset_bytes).hexdigest() != job["dataset_sha256"]:
        raise SandboxError("dataset hash differs from C2")
    if isinstance(executor, DockerExecutor) and (operation_seconds is None or operation_seconds <= 0):
        raise SandboxError("G4: explicit operator-approved Docker command deadline required")
    command = flags(job, lock, attempt=attempt, deadline_epoch=time.time()+job["caps"]["wall_seconds"])
    flag_hash = hashlib.sha256(json.dumps(command, separators=(",", ":")).encode()).hexdigest()
    def call(args, *, stdin=b"", wall=None):
        budget = wall if wall is not None else operation_seconds
        return executor.call(args, stdin=stdin, deadline=time.monotonic()+budget if budget is not None else None,
                             limit=job["caps"]["stdout_bytes"])
    def require(result, what):
        if result.returncode != 0 or result.timed_out or result.overflow:
            raise SandboxError(what + " failed")
        return result
    version = require(call(["version", "--format", "{{json .}}"]), "docker version")
    observed = json.loads(version.stdout)
    version_data = {side: {key: value for key, value in observed.get(side, {}).items()
                          if key in ("Version", "ApiVersion", "GitCommit", "GoVersion", "Os", "Arch", "BuildTime")}
                    for side in ("Client", "Server")}
    if version_data.get("Server", {}).get("Version") != lock.docker_engine_version:
        raise SandboxError("G4: Docker server version differs from pinned lock")
    created = stamp()
    emit("sandbox_created", {"run_id": job["run_id"], "phase": "requested", "docker_flags_sha256": flag_hash,
                             "docker_version": version_data, "image_digest": lock.image_digest, "caps": job["caps"]})
    sandbox_id = None
    # Name is known before create, so cleanup can target it even if create returns an unusable response.
    cleanup_id = command[command.index("--name")+1]
    result = None
    try:
        create = require(call(command), "docker create")
        sandbox_id = create.stdout.decode("ascii").strip()
        if not re.fullmatch(r"[a-f0-9]{6,64}", sandbox_id):
            raise SandboxError("docker create returned an invalid container id")
        cleanup_id = sandbox_id
        started = stamp()
        emit("sandbox_started", {"sandbox_id": sandbox_id})
        started_result = call(["start", "-a", "-i", sandbox_id],
                              stdin=json.dumps(request, separators=(",", ":"), allow_nan=False).encode(),
                              wall=job["caps"]["wall_seconds"])
        if started_result.timed_out or started_result.overflow:
            require(call(["kill", sandbox_id]), "docker kill")
        inspected = require(call(["inspect", sandbox_id]), "docker inspect")
        state = json.loads(inspected.stdout)[0]["State"]
        termination = ("oom_killed" if state["OOMKilled"] else
                       "timeout_killed" if started_result.timed_out else
                       "error" if started_result.overflow or state["ExitCode"] != 0 or started_result.returncode != 0 else "normal")
        output = None
        if termination == "normal":
            try:
                output = json.loads(started_result.stdout)
            except (ValueError, UnicodeError) as exc:
                raise SandboxError("sandbox stdout is not SB1 JSON") from exc
            failures = errors("sb1_response.schema.json", output)
            if failures:
                raise SandboxError("SB1 output refused: " + failures[0])
            if output["ok"] is not True:
                termination = "error"
        ended = state["FinishedAt"]
        started = state["StartedAt"]
        emit("sandbox_ended", {"sandbox_id": sandbox_id, "termination": termination, "exit_status": state["ExitCode"],
                              "stdout_truncated": started_result.overflow, "docker_flags_sha256": flag_hash})
        result = Execution(sandbox_id, output, termination, state["ExitCode"], False, flag_hash,
                           hashlib.sha256(started_result.stdout).hexdigest(), version_data,
                           created, started, ended, "", lock, dict(job["caps"]))
    except Exception as exc:
        if isinstance(exc, SandboxError):
            raise
        raise SandboxError("sandbox lifecycle failed: " + type(exc).__name__) from None
    finally:
        removed = call(["rm", "-f", "-v", cleanup_id])
        remaining = call(["ps", "-a", "--no-trunc", "--filter", "id="+cleanup_id, "--format", "{{.ID}}"])
        verified = (removed.returncode == 0 and not removed.timed_out and not removed.overflow
                    and remaining.returncode == 0 and not remaining.timed_out and not remaining.overflow and not remaining.stdout.strip())
        destroyed = stamp()
        emit("sandbox_destroyed", {"sandbox_id": cleanup_id, "destroy_verified": verified})
        if not verified:
            raise SandboxError("destroy verification failed; run must fail closed")
        if result is not None:
            result.destroy_verified = True
            result.destroyed_at = destroyed
    return result
