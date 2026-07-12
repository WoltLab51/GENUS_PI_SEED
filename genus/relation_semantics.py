"""Shared storage semantics for relation events and their projections."""
from __future__ import annotations


# Semantic proximity is undirected regardless of who asserted it. Its storage
# orientation must therefore be identical on live writes, retractions, and replay.
CANONICAL_PREDICATES = frozenset({"verwandt"})

# Only deterministic reruns are collapsible. Other repeated relations are genuine
# countable observations even when their four-tuple happens to be identical.
IDEMPOTENT_STREAMS = frozenset({("model:embedder", "verwandt")})


def canonical_pair(subject: str, predicate: str, object_: str) -> tuple[str, str]:
    if predicate in CANONICAL_PREDICATES:
        return tuple(sorted((subject, object_)))
    return subject, object_


def is_idempotent_stream(source: str, predicate: str) -> bool:
    return (source, predicate) in IDEMPOTENT_STREAMS
