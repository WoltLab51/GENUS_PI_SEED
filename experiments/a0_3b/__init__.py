"""A0.3b same-file shadow-generation experiment.

The package is deliberately outside :mod:`genus` and is never imported by the
product runtime.  It may operate only on A0.3a-marked disposable databases.
"""

from .harness import (  # noqa: F401
    DEFAULT_BATCH_BYTES,
    DEFAULT_BATCH_EVENTS,
    METADATA_SCHEMA,
    PROJECTION_TABLES,
    RECEIPT_SCHEMA,
    active_reader,
    append_routed,
    build_shadow,
    catch_up_shadow,
    cutover_shadow,
    generation_status,
    initialize_shadow,
    recover,
    run_shadow_prototype,
    stream_generation_digests,
    verify_shadow,
)
