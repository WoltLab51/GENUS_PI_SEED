"""A0.3c runtime prerequisite and copy-only live-readiness evidence."""

from .harness import (  # noqa: F401
    RUNTIME_IDENTITY_SCHEMA,
    RUNTIME_MANIFEST_SCHEMA,
    acquire_product_copies,
    run_readiness_candidate,
    create_gate_receipt,
    create_runtime_manifest,
    finish_series_attempt,
    gate_command_argv,
    initialize_series_journal,
    reserve_series_attempt,
    runtime_identity,
    verify_series_journal,
    verify_run_series,
    verify_runtime_manifest,
)
