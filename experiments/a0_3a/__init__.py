"""A0.3a bounded replay and integrity measurement harness."""

from .harness import (
    HarnessError,
    InjectedFault,
    OracleMismatch,
    ReplayFence,
    SyntheticSpec,
    capture_fence,
    generate_synthetic_database,
    run_option_b,
    stream_ledger_binding,
    stream_projection_digests,
)

__all__ = [
    "HarnessError",
    "InjectedFault",
    "OracleMismatch",
    "ReplayFence",
    "SyntheticSpec",
    "capture_fence",
    "generate_synthetic_database",
    "run_option_b",
    "stream_ledger_binding",
    "stream_projection_digests",
]
