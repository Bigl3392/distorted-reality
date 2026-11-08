"""Composition helper: turns an ApiConfig plus the injected collaborators into the `factory(run_id)` the API needs.

Collaborators (a per-run broker, the runner, the dataset) come from the caller; the real ones (M4 runner, M1 dataset) do not exist yet,
so only fakes are wired in tests. In public mode a runs directory is mandatory: a deployed journal must be on disk, not in memory.
"""
from .api import ConfigError
from .orchestrator import Orchestrator


def make_factory(cfg, orchestrator_cls=Orchestrator, *, broker_factory, runner, dataset, rule_path, seed, assurance_tier="T0",
                 clock=None, commit_key=None, forbidden=()):
    if cfg.public and not cfg.runs_dir:
        raise ConfigError("DR_RUNS_DIR is required in public mode: journals must be written to disk")

    def factory(run_id):
        return orchestrator_cls(broker=broker_factory(), runner=runner, dataset=dataset, rule_path=rule_path, runs_dir=cfg.runs_dir,
                                clock=clock, seed=seed, assurance_tier=assurance_tier, commit_key=commit_key, forbidden=forbidden)
    return factory


def make_real_runner(env, *, lock, executor, operation_seconds=None, lock_path=None, clock=None):
    """Real M4 runner with the inference key (read from `env`, never printed) wired into its secret scan. Missing or blank key: ConfigError, never an
    unscanned runner. `operation_seconds` is the operator's Docker deadline; M4 refuses a real executor without it."""
    from .broker_factory import key_scanner
    from .runner_adapter import SandboxRunner
    return SandboxRunner(lock=lock, executor=executor, operation_seconds=operation_seconds, lock_path=lock_path, clock=clock,
                         secret_values=key_scanner(env))


def make_real_factory(cfg, *, dataset, runner, broker_factory, rule_path, seed, allow_provisional=False, **kw):
    """Composition root entry: real M1 dataset and real M4 runner behind the same interfaces. A provisional dataset (synthetic core, no sourced
    weather, G14) is refused unless `allow_provisional=True`, so a run on it cannot be recorded as the release run by accident."""
    if getattr(dataset, "provisional", False) and not allow_provisional:
        raise ConfigError("dataset is provisional (no sourced weather, G14): not a release dataset")
    return make_factory(cfg, broker_factory=broker_factory, runner=runner, dataset=dataset, rule_path=rule_path, seed=seed, **kw)
