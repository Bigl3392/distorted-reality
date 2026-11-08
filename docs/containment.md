# Containment

Model-written code runs only inside a container created for one path and one attempt, then destroyed. This page says exactly what is configured and what is **not** claimed.

## Container configuration
```
docker create --name dr-<run>-<path>-a<attempt> --network none \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,nodev,size=32m \
  --cap-drop ALL --security-opt no-new-privileges --user 65534:65534 \
  --memory <MEM>m --memory-swap <MEM>m --pids-limit <PIDS> --cpus <CPUS> \
  --ulimit nofile=64:64 --ulimit fsize=16777216 --ulimit core=0 --ipc none \
  --env PYTHONHASHSEED=0 --env PYTHONDONTWRITEBYTECODE=1 \
  --label dr.run=<run> --label dr.deadline=<epoch> -i <image by digest> /harness/run.py
```
No bind mounts, no privileged mode, no Docker socket, no environment file, no devices, no host PID, network or IPC namespace. Input is one JSON document on stdin; output is one JSON document on stdout, capped. The flag set is hashed into the receipt, and a unit test asserts that the builder cannot emit a forbidden flag.

## Caps (defaults; may be tightened, never loosened)
| Cap | Default | Hard maximum in the job schema |
|---|---|---|
| Wall time | 30 s | 120 s |
| Memory (no swap) | 256 MB | 1024 MB |
| PIDs | 64 | 256 |
| CPUs | 1 | 2 |
| stdout | 512 KiB | 1 MiB |

The termination reason is recorded as `normal`, `timeout_killed`, `oom_killed`, `pids_killed` or `error`; an out-of-memory kill is read from the runtime's own state, never inferred.

## Lifecycle and watchdogs
journal `sandbox_created` -> create -> start -> wait or kill at the deadline -> inspect -> read capped output -> remove -> confirm no container with that name remains -> journal `sandbox_destroyed` with `destroy_verified`. An unverified destroy fails the run closed and the packet says so. Three watchdog layers: an alarm inside the harness, the controller's deadline kill, and a systemd timer on the sandbox host that removes any labeled container past its deadline even if the controller has crashed.

## Secret hygiene
The inference key exists only in the control VM's environment file. It is never passed as a Docker argument, an environment flag or on stdin. A canary test puts a random secret in the controller's environment, runs a probe payload that dumps the environment, `/proc/self/environ`, a filesystem listing and an attempt to read `/proc/1/environ`, and passes only if the canary appears nowhere. A negative control injects the canary into the container on purpose; the same test must then fail.

## The runaway test
The stress payload is self-written and does four things: allocates memory in 8 MB chunks until killed, spawns busy workers up to the pids limit, tries one outbound connection (expected to fail), and walks a few directories looking for a canary. It is operator-triggered only and is not exposed publicly. While it runs, a separate process polls `/healthz` every 100 ms; the maximum gap between successful responses is recorded in the packet.

## What this does not claim
This shows resource isolation under cgroup limits for the tested payloads. It does not claim immunity to container-escape vulnerabilities, isolation equivalent to a separate machine, or any property beyond the tests listed above. `[CONFIRM AT SUBMISSION: results of the containment tests on the deployed hosts]`
