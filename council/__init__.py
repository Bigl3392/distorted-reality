"""Council port (M3): role prompts, strict JSON parsing, seeded shuffle, fail-closed orchestration of the council method.

Ported METHOD only (REUSE_AUDIT): new code, no literal reuse. Makes calls only through the broker.
"""
from .run import CouncilFailedClosed, CouncilResult, CoderResult, compile_apply, run_council  # noqa: F401
