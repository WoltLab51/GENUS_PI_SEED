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

from genus import self_calibration, sources

# Declarative inference rules -- the SEED (the starting hypothesis before the graph has spoken).
# These are no longer the last word: GENUS learns from its own graph which predicates actually
# behave transitively/symmetrically (see transitivity_evidence / is_transitive below) and treats
# the seed as a fallback only where evidence is thin -- self-calibration applied to the rules of
# its OWN reasoning. The engine (traversal + justification) stays fixed; the rule-spec is learned.
TRANSITIVE_PREDICATES = {"is_a", "part_of"}
SYMMETRIC_PREDICATES = {"synonym", "antonym"}

# Enough closed triangles / mirrored pairs to trust a rule as *learned* from the data rather than
# assumed -- a few independent vindications, like MIN_LIFECYCLE for beliefs. A seed, not a law:
# the *active* value is self-calibrated (calibrated_transitivity_min) and recorded by the periodic
# scan under this experience key, so the hot path reads it cheaply (stored_transitivity_threshold).
MIN_VINDICATIONS = 3
TRANSITIVITY_CALIBRATION_KEY = "rule_calibration:transitivity"

# Symmetry needs a RATE, not a raw count: a symmetric predicate mirrors *systematically* (most
# edges have their reverse), whereas a non-symmetric one shows only incidental mirrors -- e.g.
# is_a had 6 mirrored pairs out of 6091 (0.1%), which are acyclic-violating CYCLES, not symmetry.
# Transitivity, by contrast, stays a count: genuine transitivity yields a low closed-triangle rate
# (sources rarely re-assert the grandparent edge), so absence of a high rate is expected there.
# A seed rate: the *active* value is self-calibrated (calibrated_symmetry_rate) and recorded by the
# scan under this key, read cheaply on the hot path (stored_symmetry_rate) -- like transitivity.
MIN_SYMMETRY_RATE = 0.10
SYMMETRY_CALIBRATION_KEY = "rule_calibration:symmetry"

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
          edges: dict[str, list[tuple[str, str]]] | None = None,
          transitive: bool | None = None, symmetric: bool | None = None) -> list[dict]:
    """Derive ``(subject, predicate, object)`` relations not directly asserted, each with
    its premise chain and a composed trust (the weakest premise). Transitive predicates
    chain (A→B, B→C ⇒ A→C); symmetric ones mirror (A→B ⇒ B→A). Read-only; returns only the
    *derived* edges, never the asserted ones. Pass a pre-built ``edges`` adjacency (from
    :func:`_edges`) to reuse across many calls -- it is identical for every subject of one
    predicate, so building it once avoids rescanning the whole graph per call.

    Whether ``predicate`` chains/mirrors is now **learned** (``is_transitive``/``is_symmetric``
    from the graph's own vindications, seed as fallback) rather than a hardcoded set -- GENUS
    reasons by the rules it has itself confirmed. Pass ``transitive``/``symmetric`` to decide once
    and reuse the decision across a whole closure (as with ``edges``)."""
    if edges is None:
        edges = _edges(conn, predicate)
    if transitive is None:
        transitive = is_transitive(conn, predicate, edges)
    if symmetric is None:
        symmetric = is_symmetric(conn, predicate, edges)
    if not transitive and not symmetric:
        return []

    direct = {obj for obj, _ in edges.get(subject, [])}  # directly asserted from subject

    trust_cache: dict[str, float] = {}

    def trust_of(source: str) -> float:
        if source not in trust_cache:
            trust_cache[source] = sources.source_trust(conn, source)
        return trust_cache[source]

    derived: dict[str, dict] = {}  # object -> {chain, trust}; first (shortest) wins

    if transitive:
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

    if symmetric:
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
    transitive = is_transitive(conn, predicate, edges)   # the learned rule, decided once, reused
    symmetric = is_symmetric(conn, predicate, edges)
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
                      for d in infer(conn, concept, predicate, edges=edges,
                                     transitive=transitive, symmetric=symmetric)]

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


# --- learning the rules of GENUS's own reasoning -------------------------------------------
#
# The first SYSTEME step: GENUS does not just USE inference rules, it LEARNS which ones hold,
# from its own graph. Whether a predicate is transitive is a *hypothesis the data can vindicate*:
# a closed triangle (A-P->B, B-P->C with A-P->C also asserted) is the transitive prediction
# confirmed by an independent assertion. Count enough of those and the rule is learned; find none
# and GENUS keeps only the seed hypothesis. Read-time and glass-box -- the vindications ARE the
# reason. This turns the core's own machinery on the core's own reasoning (self-reference).

def transitivity_evidence(conn, predicate: str, edges=None, stop_at: int | None = None) -> dict:
    """Evidence that ``predicate`` is transitive: closed triangles that vindicate the rule, out
    of all 2-step chains that offered the chance. Returns a few example triangles for the trace.
    ``stop_at`` returns as soon as that many vindications are found -- the *decision* only needs
    to know the threshold is met, so is_transitive need not scan the whole graph on the hot path."""
    if edges is None:
        edges = _edges(conn, predicate)
    asserted = {(subj, obj) for subj, objs in edges.items() for obj, _ in objs}
    chains = vindications = 0
    examples: list[tuple[str, str, str]] = []
    for a, objs in edges.items():
        for b in {obj for obj, _ in objs}:
            for c, _ in edges.get(b, []):
                if c == a:
                    continue
                chains += 1
                if (a, c) in asserted:
                    vindications += 1
                    if len(examples) < 5:
                        examples.append((a, b, c))
                    if stop_at is not None and vindications >= stop_at:
                        return {"predicate": predicate, "vindications": vindications,
                                "chains": chains, "examples": examples}
    return {"predicate": predicate, "vindications": vindications, "chains": chains, "examples": examples}


def _vindications_per_predicate(conn) -> dict[str, int]:
    """Closed-triangle counts for every predicate at once, in one indexed query (no per-predicate
    adjacency building) -- the population the transitivity threshold is calibrated from."""
    rows = conn.execute(
        """
        SELECT r1.predicate AS predicate, COUNT(*) AS n
        FROM relation_projection r1
        JOIN relation_projection r2
          ON r2.subject = r1.object AND r2.predicate = r1.predicate
        JOIN relation_projection r3
          ON r3.subject = r1.subject AND r3.object = r2.object AND r3.predicate = r1.predicate
        WHERE r1.object <> r1.subject AND r2.object <> r1.subject
        GROUP BY r1.predicate
        """
    ).fetchall()
    return {row["predicate"]: row["n"] for row in rows}


def calibrated_transitivity_min(conn) -> int:
    """The transitivity threshold GENUS learns from the natural gap in its OWN data, instead of a
    typed-in constant. Closed-triangle counts across predicates fall into a low (incidental) and a
    high (rule-like) group; the widest gap between the positive counts is the cut, and a predicate
    is transitive when it sits above the incidental group. Falls back to the seed MIN_VINDICATIONS
    when the population is too thin to show a gap. Self-calibration turned on the rules of reasoning
    themselves: the parameter is derived, not decreed (see [[self-calibration-no-presets]])."""
    return self_calibration.widest_gap_count_threshold(
        _vindications_per_predicate(conn).values(), MIN_VINDICATIONS
    )


def stored_transitivity_threshold(conn) -> int | None:
    """The self-calibrated threshold the periodic scan has RECORDED (experience
    ``rule_calibration:transitivity``), read here with a single indexed lookup so the hot path
    uses the derived value without recomputing the heavy cross-predicate calibration per query.
    ``None`` when no calibration has been recorded yet -- then the seed stands. This is the
    BeliefStability pattern: batch-compute the characterization, record it, read it cheaply."""
    row = conn.execute(
        "SELECT pattern FROM experience_log WHERE experience_key = ?",
        (TRANSITIVITY_CALIBRATION_KEY,),
    ).fetchone()
    if row is None:
        return None
    import json
    value = json.loads(row["pattern"]).get("threshold")
    return int(value) if value is not None else None


def symmetry_evidence(conn, predicate: str, edges=None) -> dict:
    """Evidence that ``predicate`` is symmetric: asserted edges whose mirror is also asserted."""
    if edges is None:
        edges = _edges(conn, predicate)
    asserted = {(subj, obj) for subj, objs in edges.items() for obj, _ in objs}
    pairs = mirrored = 0
    examples: list[tuple[str, str]] = []
    for a, objs in edges.items():
        for b in {obj for obj, _ in objs}:
            if a == b:
                continue
            pairs += 1
            if (b, a) in asserted:
                mirrored += 1
                if len(examples) < 5:
                    examples.append((a, b))
    return {"predicate": predicate, "mirrored": mirrored, "pairs": pairs, "examples": examples}


def _mirror_rates_per_predicate(conn) -> dict[str, float]:
    """Mirror rate (mirrored / pairs) for every predicate at once, via indexed SQL -- the
    population the symmetry rate is calibrated from (a systematic mirror sits far above the
    incidental ones)."""
    pairs = {r["predicate"]: r["n"] for r in conn.execute(
        "SELECT predicate, COUNT(*) AS n FROM relation_projection WHERE subject <> object GROUP BY predicate"
    )}
    mirrored = {r["predicate"]: r["n"] for r in conn.execute(
        "SELECT r1.predicate AS predicate, COUNT(*) AS n FROM relation_projection r1 "
        "JOIN relation_projection r2 ON r2.predicate = r1.predicate "
        "AND r2.subject = r1.object AND r2.object = r1.subject "
        "WHERE r1.subject <> r1.object GROUP BY r1.predicate"
    )}
    return {p: mirrored.get(p, 0) / n for p, n in pairs.items() if n > 0}


def calibrated_symmetry_rate(conn) -> float:
    """The symmetry-rate cut GENUS learns from the natural gap in its own data (systematic mirrors
    -- synonym ~0.23 -- sit far above incidental ones -- is_a ~0.001). The widest gap between the
    positive rates gives the cut (its midpoint); falls back to the seed ``MIN_SYMMETRY_RATE`` when
    the population is too thin. Self-calibration on the rules of reasoning, the symmetry twin of
    ``calibrated_transitivity_min``."""
    return self_calibration.widest_gap_rate_cut(
        _mirror_rates_per_predicate(conn).values(), MIN_SYMMETRY_RATE
    )


def stored_symmetry_rate(conn) -> float | None:
    """The self-calibrated symmetry rate the scan has recorded (experience
    ``rule_calibration:symmetry``), read with one cheap indexed lookup; ``None`` until first scan."""
    row = conn.execute(
        "SELECT pattern FROM experience_log WHERE experience_key = ?",
        (SYMMETRY_CALIBRATION_KEY,),
    ).fetchone()
    if row is None:
        return None
    import json
    value = json.loads(row["pattern"]).get("rate")
    return float(value) if value is not None else None


def is_transitive(conn, predicate: str, edges=None, threshold: int | None = None) -> bool:
    """Whether GENUS reasons transitively over ``predicate`` -- LEARNED from the graph once it has
    spoken (>= the threshold in closed triangles), else the seed hypothesis. Open-world: absence of
    vindication is not proof against; it just leaves the seed standing.

    ``threshold`` defaults to the value the periodic scan has self-calibrated and recorded
    (``stored_transitivity_threshold``, read with one cheap indexed lookup), falling back to the
    seed ``MIN_VINDICATIONS`` when nothing is recorded yet. So the hot path reasons by the *derived*
    threshold without paying the heavy cross-predicate calibration per query."""
    if threshold is None:
        threshold = stored_transitivity_threshold(conn)
        if threshold is None:
            threshold = MIN_VINDICATIONS
    if transitivity_evidence(conn, predicate, edges, stop_at=threshold)["vindications"] >= threshold:
        return True
    return predicate in TRANSITIVE_PREDICATES


def is_symmetric(conn, predicate: str, edges=None, rate: float | None = None) -> bool:
    """Whether GENUS mirrors ``predicate`` -- LEARNED when mirroring is *systematic* (enough
    mirrored pairs AND a high enough rate), else the seed. The rate gate is what keeps a handful
    of incidental is_a cycles from being mistaken for symmetry. ``rate`` defaults to the value the
    scan self-calibrated and recorded (``stored_symmetry_rate``, one cheap lookup), seed as
    fallback -- so the hot path uses the *derived* cut, like transitivity."""
    if rate is None:
        rate = stored_symmetry_rate(conn)
        if rate is None:
            rate = MIN_SYMMETRY_RATE
    ev = symmetry_evidence(conn, predicate, edges)
    if ev["mirrored"] >= MIN_VINDICATIONS and ev["pairs"] and ev["mirrored"] / ev["pairs"] >= rate:
        return True
    return predicate in SYMMETRIC_PREDICATES


# --- the acyclicity self-check: a transitive hierarchy must be a DAG ----------------------
#
# Transitivity has a structural consequence GENUS can check on itself. If a predicate is
# transitive AND its edges close a cycle A->...->A, transitivity derives A is_a A and every node
# in the ring collapses into every other -- the hierarchy stops telling anything apart. So a
# transitive predicate must be ACYCLIC; a cycle is a self-contradiction in GENUS's own reasoning,
# not a fact. `symmetry_evidence` only ever meets 2-cycles (mirrored pairs) as a by-product of
# asking "is this symmetric?"; a real hierarchy can hide longer rings (A->B->C->A) it cannot see.
# This is the honest, complete check -- cycles of ANY length. Read-time and glass-box: each cycle
# is returned as its node ring so the contradiction can be shown and, where a direction is clearly
# wrong, the offending edge retracted (`reactors.retract_relation`).

# A hierarchy cycle longer than this is inconceivable; a recursion guard, not a semantic limit.
_MAX_CYCLE_LEN = 64


def cycles(conn, predicate: str, edges=None, limit: int = 100) -> list[list[str]]:
    """Every simple cycle in the ``predicate`` graph -- the acyclicity self-check. Each cycle is a
    list of nodes ``[a, b, c]`` meaning ``a->b->c->a``, rotated to start at its smallest node so a
    ring is reported exactly once (never once per rotation). Empty for an acyclic graph (a DAG --
    the healthy case). Bounded by ``limit`` cycles so the read stays cheap on a large graph; the
    ``> start`` pruning means each ring is enumerated only from its minimum node."""
    if edges is None:
        edges = _edges(conn, predicate)
    adj = {subj: sorted({obj for obj, _ in objs}) for subj, objs in edges.items()}
    found: list[list[str]] = []

    def walk(start: str, node: str, path: list[str], seen: set[str]) -> None:
        if len(found) >= limit or len(path) > _MAX_CYCLE_LEN:
            return
        for nxt in adj.get(node, ()):
            if nxt == start:              # closed the ring back to its minimum node
                found.append(list(path))
                if len(found) >= limit:
                    return
            elif nxt > start and nxt not in seen:  # only nodes above the root -> each ring once
                walk(start, nxt, path + [nxt], seen | {nxt})

    for start in sorted(adj):
        if len(found) >= limit:
            break
        walk(start, start, [start], {start})
    return found


def reaches(conn, start: str, target: str, predicate: str, max_depth: int = MAX_DEPTH) -> bool:
    """Does ``start`` reach ``target`` via ``predicate`` (start ->* target)? A bounded BFS over
    indexed per-node lookups, so it touches only the path -- cheap enough to run at assertion time,
    unlike building the whole adjacency. The depth bound matches the closure's."""
    if start == target:
        return True
    seen = {start}
    frontier = [start]
    for _ in range(max_depth):
        nxt: list[str] = []
        for node in frontier:
            for row in sources.relations(conn, subject=node, predicate=predicate):
                obj = row["object"]
                if obj == target:
                    return True
                if obj not in seen:
                    seen.add(obj)
                    nxt.append(obj)
        if not nxt:
            break
        frontier = nxt
    return False


def closes_cycle(conn, subject: str, predicate: str, object_: str) -> bool:
    """Would asserting ``subject -predicate-> object_`` close a ring? True iff ``object_`` already
    reaches ``subject`` AND the predicate is (learned) transitive -- then subject→object→…→subject
    derives ``subject is_a subject`` and the hierarchy collapses: a self-contradiction, not a fact.
    Reachability is checked first (cheap, targeted); the transitivity decision only when a ring
    actually formed (rare), so the common assertion stays fast."""
    if not reaches(conn, object_, subject, predicate):
        return False
    return is_transitive(conn, predicate)
