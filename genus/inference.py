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


def infer(conn, subject: str, predicate: str, max_depth: int = MAX_DEPTH,
          edges: dict[str, list[tuple[str, str]]] | None = None) -> list[dict]:
    """Derive ``(subject, predicate, object)`` relations not directly asserted, each with
    its premise chain and a composed trust (the weakest premise). Transitive predicates
    chain (A→B, B→C ⇒ A→C); symmetric ones mirror (A→B ⇒ B→A). Read-only; returns only the
    *derived* edges, never the asserted ones. Pass a pre-built ``edges`` adjacency (from
    :func:`_edges`) to reuse across many calls -- it is identical for every subject of one
    predicate, so building it once avoids rescanning the whole graph per call."""
    if predicate not in TRANSITIVE_PREDICATES and predicate not in SYMMETRIC_PREDICATES:
        return []

    if edges is None:
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


def infer_lexeme(conn, form: str, predicate: str, lang: str) -> list[dict]:
    """Reason about a *word*: map it to its concept(s) via ``expresses``, infer at the
    language-neutral concept level, then render the answers back as words in ``lang``.

    A word asserts no hierarchy of its own -- it *inherits* its concept's. This is
    sense-coherent **by construction**: each concept's is_a parent is a specific concept,
    so a chain stays within one sense-line and can never wander across senses (the cure
    for "Hund is_a Bevölkerung"). The chain begins at the word (the ``expresses`` step),
    so the justification is fully glass-box; trust is still the weakest premise.
    """
    key = sources.lexeme_key(form, lang)
    trust_cache: dict[str, float] = {}

    def trust_of(source: str) -> float:
        if source not in trust_cache:
            trust_cache[source] = sources.source_trust(conn, source)
        return trust_cache[source]

    edges = _edges(conn, predicate)  # built once; reused for direct parents AND every closure below
    by_object: dict[str, dict] = {}  # ancestor concept -> {chain, trust}; shortest wins
    for expr in sources.relations(conn, subject=key, predicate=sources.EXPRESSES):
        concept = expr["object"]
        head = _premise(key, sources.EXPRESSES, concept, expr["source"])
        head_trust = trust_of(expr["source"])

        # From the word's view *everything* is derived: direct concept parents first
        # (shortest chains), then the transitive ancestors. Both read from the one adjacency.
        ancestors: list[tuple[str, list[dict], float]] = [
            (obj, [_premise(concept, predicate, obj, source)], trust_of(source))
            for obj, source in edges.get(concept, [])
        ]
        ancestors += [(d["object"], d["chain"], d["trust"])
                      for d in infer(conn, concept, predicate, edges=edges)]

        for obj, chain, sub_trust in ancestors:
            if obj in by_object or obj == concept:
                continue
            by_object[obj] = {"chain": [head] + chain, "trust": round(min(head_trust, sub_trust), 3)}

    return [
        {"subject": form, "lang": lang, "predicate": predicate, "object": obj,
         "lexemes": sources.lexicalize(conn, obj, lang),
         "trust": data["trust"], "chain": data["chain"]}
        for obj, data in sorted(by_object.items())
    ]
