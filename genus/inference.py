"""Inference — the first reasoning primitive: derive new relations from known ones.

The *engine* (graph traversal + justification) is the given primitive; *which* predicates
are transitive/symmetric is a declarative spec (the seed below — later taught/learned as
rule-specs through the proposal→governance pipeline). Derived relations are **not** stored
as assertions: they have no source, they have a *justification* (the premise chain + the
rule). Read-time and glass-box — every derived edge carries the chain that produced it,
and its trust is the **weakest premise** (a chain is only as strong as its weakest link).
"""
from __future__ import annotations

from collections import deque

from genus import sources

# Declarative inference rules -- the seed. Later these become taught/learned rule-specs;
# the engine below stays fixed (it is the frame, given).
TRANSITIVE_PREDICATES = {"is_a", "part_of"}
SYMMETRIC_PREDICATES = {"synonym", "antonym"}

# Structural bound on the chain length, so traversal can't run away (like the evidence
# window). A safety bound, not an epistemic threshold.
MAX_DEPTH = 6


def _premise(subject: str, predicate: str, object_: str, source: str) -> dict:
    return {"subject": subject, "predicate": predicate, "object": object_, "source": source}


def _edges(conn, predicate: str) -> dict[str, list[tuple[str, str]]]:
    adjacency: dict[str, list[tuple[str, str]]] = {}
    for relation in sources.relations(conn, predicate=predicate):
        adjacency.setdefault(relation["subject"], []).append(
            (relation["object"], relation["source"])
        )
    return adjacency


def infer(conn, subject: str, predicate: str, max_depth: int = MAX_DEPTH) -> list[dict]:
    """Derive ``(subject, predicate, object)`` relations not directly asserted, each with
    its premise chain and a composed trust (the weakest premise). Transitive predicates
    chain (A→B, B→C ⇒ A→C); symmetric ones mirror (A→B ⇒ B→A). Read-only; returns only the
    *derived* edges, never the asserted ones."""
    if predicate not in TRANSITIVE_PREDICATES and predicate not in SYMMETRIC_PREDICATES:
        return []

    edges = _edges(conn, predicate)
    direct = {obj for obj, _ in edges.get(subject, [])}  # directly asserted from subject

    trust_cache: dict[str, float] = {}

    def trust_of(source: str) -> float:
        if source not in trust_cache:
            trust_cache[source] = sources.source_trust(conn, source)
        return trust_cache[source]

    derived: dict[str, dict] = {}  # object -> {chain, trust}; first (shortest) wins

    if predicate in TRANSITIVE_PREDICATES:
        queue = deque(
            (obj, [_premise(subject, predicate, obj, source)], trust_of(source))
            for obj, source in edges.get(subject, [])
        )
        seen = {subject} | direct
        while queue:
            node, chain, min_trust = queue.popleft()
            if len(chain) >= max_depth:
                continue
            for obj, source in edges.get(node, []):
                if obj == subject:
                    continue
                composed = min(min_trust, trust_of(source))
                new_chain = chain + [_premise(node, predicate, obj, source)]
                if obj not in direct and obj not in derived:
                    derived[obj] = {"chain": new_chain, "trust": round(composed, 3)}
                if obj not in seen:
                    seen.add(obj)
                    queue.append((obj, new_chain, composed))

    if predicate in SYMMETRIC_PREDICATES:
        for other, objs in edges.items():
            for obj, source in objs:
                if obj == subject and other != subject and other not in direct and other not in derived:
                    derived[other] = {
                        "chain": [_premise(other, predicate, subject, source)],
                        "trust": round(trust_of(source), 3),
                    }

    return [
        {"subject": subject, "predicate": predicate, "object": obj,
         "trust": data["trust"], "chain": data["chain"]}
        for obj, data in sorted(derived.items())
    ]
