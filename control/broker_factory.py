"""Real-key broker factory (composition root). The inference key comes from the process environment only, is held inside BrokerClient and a
closure, and is never printed, logged, stored in a file or put in an error message. Tests pass a fake key through a plain dict; nothing here
reads a file that could hold a real one. No limit is invented: token and rate limits come from DR_* variables and stay UNSET unless set.
"""
import os

from broker.client import BrokerClient
from broker.limits import DailyBudget, limits_from_env
from broker.models import load_models

KEY_VAR = "VULTR_INFERENCE_API_KEY"


def _key(env):
    from .api import ConfigError
    value = env.get(KEY_VAR)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{KEY_VAR} is not set in the environment")
    return value


def make_broker_factory(env=None, *, models, public=True, transport=None, clock=None):
    """Returns `factory()` -> a new BrokerClient per run, all sharing one process-wide DailyBudget.
    `models`: a pinned models dict or a path to models.yaml (load_models refuses TEMPLATE and any UNSET)."""
    env = os.environ if env is None else env
    key = _key(env)
    cfg = load_models(models)
    limits = limits_from_env(env)
    daily = DailyBudget()

    def factory():
        return BrokerClient(models=cfg, api_key=key, limits=limits, daily=daily, public=public, transport=transport, clock=clock)
    return factory


def key_scanner(env=None):
    """Returns a callable yielding the secret values a runner's output must not contain. The key lives only in the closure."""
    key = _key(os.environ if env is None else env)
    return lambda: (key,)
