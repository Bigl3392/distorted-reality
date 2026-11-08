"""Inference broker (M3). The only code that ever sees the Vultr Serverless Inference key.

Pins a model per role, enforces per-run and daily token limits, fails closed on a model mismatch,
and redacts the key from everything it emits. See DISTORTED_REALITY_SPEC section 3.5.
"""
from .client import (  # noqa: F401
    BASE_URL,
    BrokerClient,
    BrokerError,
    BudgetExceeded,
    CallResult,
    LiveInferenceRefused,
    ModelMismatch,
    UrllibTransport,
)
from .limits import DailyBudget, Limits, LimitsError, limits_from_env, limits_from_record  # noqa: F401
from .models import ModelsConfig, ModelsError, load_models  # noqa: F401
