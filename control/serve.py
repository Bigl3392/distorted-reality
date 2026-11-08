"""Real launcher for the M5 app (F-M7-03): `python -m control.serve --port N`, behind Caddy on loopback.

It builds the stdlib WSGI `App` from the process environment (names in `.env.example`), wiring the real pieces that already exist: the M1 dataset,
the M4 runner with the inference key in its secret scan, the real-key broker factory. Public mode by default: `live_inference_allowed` stays False,
so no run can reach a model. Operator mode (I-4) is an explicit opt-in, `DR_OPERATOR_MODE=1`: live inference on and the broker in operator mode
(UNSET limits do not refuse), allowed only with `DR_OPERATOR_TOKEN` set and the per-IP limit UNSET, because that create gate (only the operator
token can create a run) is what keeps live inference operator-only.

Refuses to start, with a message that names the setting and never a value, when anything is unresolved: the key, the pinned models file (a TEMPLATE
or UNSET value refuses), the dataset seed, the operator's Docker deadline (`DR_OPERATION_SECONDS`, no default), the G4 image lock, the runs
directory, and the opt-in for the provisional (synthetic, no sourced weather) dataset (`DR_ALLOW_PROVISIONAL_DATASET=1`, G14). Binds loopback only.
`create_app()` is the factory form for a WSGI server, should one be chosen instead of the stdlib `serve()`.
"""
import argparse
import math
import re
import sys
from pathlib import Path

from broker.models import ModelsError
from sandbox.runner import DockerExecutor, SandboxError, load_lock

from .api import App, ConfigError, config_from_env, serve as _stdlib_serve

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = ROOT / "docker_image.lock"          # the path M4's run_job reads by default
RULE_PATH = ROOT / "schemas" / "decision_rule.yaml"
_LOOPBACK = ("127.0.0.1", "::1", "localhost")
_SSH_HOST = re.compile(r"^ssh://[A-Za-z0-9_.-]+@[A-Za-z0-9_.:-]+$")


def _seed(env):
    v = env.get("DR_DATASET_SEED")
    if not (isinstance(v, str) and v.isascii() and v.isdigit()):
        raise ConfigError("DR_DATASET_SEED must be a non-negative integer")
    return int(v)


def _seconds(env):
    v = env.get("DR_OPERATION_SECONDS")
    try:
        n = float(v)
    except (TypeError, ValueError):
        n = float("nan")
    if not (math.isfinite(n) and n > 0):
        raise ConfigError("DR_OPERATION_SECONDS must be a positive number chosen by the operator (no default)")
    return n


def _docker_host(env):
    v = env.get("DR_DOCKER_HOST") or ""
    if v and not _SSH_HOST.match(v):
        raise ConfigError("DR_DOCKER_HOST must be empty (local Docker, T0) or ssh://user@host (T1)")
    return v


def _operator_mode(env):
    """`DR_OPERATOR_MODE=1` is the only opt-in (I-4); unset, empty or `0` is public mode; anything else refuses."""
    v = env.get("DR_OPERATOR_MODE")
    if v in (None, "", "0"):
        return False
    if v != "1":
        raise ConfigError("DR_OPERATOR_MODE must be 1 (operator mode) or unset")
    return True


def build_app(env, *, executor=None):
    """Builds the WSGI app. `executor=None` means the real DockerExecutor (nothing is spawned until a run starts)."""
    from .broker_factory import key_scanner, make_broker_factory
    from .compose import make_real_factory, make_real_runner
    from .dataset_adapter import BundledDataset
    from .orchestrator import _now
    from dataset.generator import build_synthetic

    seed = _seed(env)
    seconds = _seconds(env)
    host = _docker_host(env)
    operator = _operator_mode(env)
    cfg = config_from_env(env, public=True)
    if operator:
        # Live inference on, public rules kept. What keeps it operator-only is the create gate: while the per-IP limit is UNSET only a
        # request carrying the operator token can create a run, and only a created run can be started. So both must hold or we refuse.
        if not cfg.operator_token:
            raise ConfigError("DR_OPERATOR_MODE=1 requires DR_OPERATOR_TOKEN")
        if cfg.per_ip_runs_per_hour is not None:
            raise ConfigError("DR_OPERATOR_MODE=1 requires DR_RATE_LIMIT_RUNS_PER_IP_PER_HOUR to be UNSET (the public must not be able to create runs)")
        cfg.live_inference_allowed = lambda: True
    lock_path = env.get("DR_IMAGE_LOCK") or str(DEFAULT_LOCK)
    try:
        lock = load_lock(lock_path)
    except SandboxError as exc:
        raise ConfigError(f"DR_IMAGE_LOCK: {exc}") from None
    models = env.get("DR_MODELS_FILE")
    if not models:
        raise ConfigError("DR_MODELS_FILE is required")
    if not RULE_PATH.is_file():
        raise ConfigError("decision rule file is missing from the tree")
    try:
        broker_factory = make_broker_factory(env, models=models, public=not operator)
    except ModelsError as exc:
        raise ConfigError(f"DR_MODELS_FILE refused: {exc}") from None
    except OSError:
        raise ConfigError("DR_MODELS_FILE could not be read") from None
    executor = executor if executor is not None else DockerExecutor(host=host or None)
    runner = make_real_runner(env, lock=lock, executor=executor, operation_seconds=seconds, lock_path=lock_path)
    dataset = BundledDataset(build_synthetic(seed=seed), clock=_now)
    factory = make_real_factory(cfg, dataset=dataset, runner=runner, broker_factory=broker_factory, rule_path=str(RULE_PATH), seed=seed,
                                allow_provisional=env.get("DR_ALLOW_PROVISIONAL_DATASET") == "1",
                                assurance_tier="T1" if host else "T0", forbidden=key_scanner(env)())
    app = App(factory, dataset, cfg)
    app.operator_mode = operator
    return app


def create_app(env=None, executor=None):
    import os
    return build_app(os.environ if env is None else env, executor=executor)


def _port(text):
    try:
        n = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("not a port number") from None
    if not 1 <= n <= 65535:
        raise argparse.ArgumentTypeError("port out of range")
    return n


def _serve_forever(app, port, host):
    server = _stdlib_serve(app, port, host)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv=None, *, env=None, executor=None, serve_fn=None):
    import os
    ap = argparse.ArgumentParser(prog="python -m control.serve", description="Serve the M5 app on loopback (behind Caddy).")
    ap.add_argument("--port", type=_port)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--check", action="store_true", help="build everything and exit without serving")
    args = ap.parse_args(argv)
    if args.port is None and not args.check:
        ap.error("--port is required unless --check is given")
    if args.host not in _LOOPBACK:
        print("refused: the app binds loopback only (Caddy fronts it); --host must be a loopback address", file=sys.stderr)
        return 2
    try:
        app = build_app(os.environ if env is None else env, executor=executor)
    except ConfigError as exc:
        print(f"configuration refused: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # value-free: never print the exception text, it may carry a protected value
        print(f"startup failed: {type(exc).__name__}", file=sys.stderr)
        return 2
    if args.check:
        print("ok: configuration builds; nothing was served" + ("; operator mode (live inference on, operator-created runs only)" if app.operator_mode else ""))
        return 0
    print(f"serving on {args.host}:{args.port}" + ("; operator mode (live inference on, operator-created runs only)" if app.operator_mode else ""), flush=True)
    (serve_fn or _serve_forever)(app, args.port, args.host)
    return 0


if __name__ == "__main__":
    sys.exit(main())
