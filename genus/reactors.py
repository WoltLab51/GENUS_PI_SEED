from __future__ import annotations

import json

from genus import inquiries, learning, ledger, projection, relation_semantics, rules, sources


# Which metrics run a 24/7 learning program, and on which cycle period. The engine
# is generic; this map chooses the signals (diverse on purpose, to surface where the
# engine generalises) and each one's natural rhythm (hour-of-day vs weekday).
FORECAST_CYCLES = {
    rules.WEATHER_TEMP_METRIC_KEY: "hour",  # world, hourly
    rules.TEMPERATURE_METRIC_KEY: "hour",  # the Pi's own body, 5-minutely (cyclic)
    rules.DISK_METRIC_KEY: "hour",  # slow trend -- the diagnostic case
    rules.REPO_COMMITS_METRIC_KEY: "weekday",  # the human's rhythm, daily
}


def observe_cpu_reading(conn, reading: dict) -> dict:
    return observe_system_reading(conn, reading, rules.CPU_METRIC_KEY)


def observe_memory_reading(conn, reading: dict) -> dict:
    return observe_system_reading(conn, reading, rules.MEMORY_METRIC_KEY)


def observe_disk_reading(conn, reading: dict) -> dict:
    return observe_system_reading(conn, reading, rules.DISK_METRIC_KEY)


def observe_activity_reading(conn, reading: dict) -> dict:
    return observe_system_reading(conn, reading, rules.ACTIVITY_METRIC_KEY)


def observe_temperature_reading(conn, reading: dict) -> dict:
    return observe_system_reading(conn, reading, rules.TEMPERATURE_METRIC_KEY)


def observe_repo_reading(conn, reading: dict) -> dict:
    return observe_system_reading(conn, reading, rules.REPO_COMMITS_METRIC_KEY)


def observe_repo_lines_reading(conn, reading: dict) -> dict:
    return observe_system_reading(conn, reading, rules.REPO_LINES_METRIC_KEY)


def observe_weather_reading(conn, reading: dict) -> dict:
    return observe_system_reading(conn, reading, rules.WEATHER_TEMP_METRIC_KEY)


def observe_system_reading(conn, reading: dict, metric_key: str) -> dict:
    try:
        payload = dict(reading)
        payload["metric_key"] = metric_key
        observation_id = ledger.append(
            conn,
            "observation_created",
            payload,
        )
        events = process_observation(conn, observation_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    # The 24/7 learning loop, for every metric that runs a learning program: score the
    # last forecast against the value that just arrived, then forecast the next. Runs
    # on whatever cron observes the metric, so each program matches its own cadence.
    cycle = FORECAST_CYCLES.get(metric_key)
    if cycle is not None:
        events.extend(learning.run_forecast_cycle(conn, metric_key, cycle))
    return {"observation_id": observation_id, "events": events}


def observe_assertion(
    conn, claim_key: str, claim_value, source: str, derivation: str | None = None
) -> dict:
    """Record a claim asserted by a source -- the general WISSEN entry point.

    The value is fetched by the membrane (a second weather provider, an almanac, later
    you or a model) and handed in; only ``(claim, source, value)`` crosses. The core
    stays pure -- no fetch here. ``assertion_recorded`` is projected into
    ``value_projection`` and is replay-stable; source trust and consensus over the
    candidates are computed read-time in ``genus/sources.py``.
    """
    try:
        payload = {
            "claim_key": claim_key,
            "claim_value": claim_value,
            "source": source,
            "derivation": derivation or f"source:{source}",
        }
        event_id = ledger.append(conn, "assertion_recorded", payload)
        payload["_event_id"] = event_id
        payload["_event_created_at"] = ledger.event_created_at(conn, event_id)
        projection.apply_assertion_recorded(conn, payload)  # indexed value view, before resolve
        events = [{"event_type": "assertion_recorded", "id": event_id}]
        # The surprise loop, on knowledge: if trusted, live sources now disagree about
        # this claim, record the contradiction and raise one inquiry per open episode.
        # GENUS flags a conflict it cannot settle from its own sources -- the teacher-loop
        # seed. (Replay re-applies the stored events; the check runs only live.)
        resolution = sources.resolve(conn, claim_key)
        if resolution["contradiction"] and not _open_source_contradiction(conn, claim_key):
            contradiction_id = ledger.append(
                conn,
                "contradiction_detected",
                {"claim_key": claim_key, "reason": f"sources disagree on {claim_key}"},
            )
            events.append({"event_type": "contradiction_detected", "id": contradiction_id})
            live = {
                src: cand["value"]
                for src, cand in resolution["candidates"].items()
                if cand["live"]
            }
            inquiries.record_source_contradiction_inquiry(
                conn,
                claim_key=claim_key,
                source_event=contradiction_id,
                payload={"claim_key": claim_key, "candidates": live, "review_recommended": True},
            )
            events.append({"event_type": "inquiry_created"})
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"event_id": event_id, "events": events}


def _open_source_contradiction(conn, claim_key: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM inquiry_log WHERE inquiry_type = ? AND claim_key = ? AND state = 'open' LIMIT 1",
        (inquiries.SOURCE_CONTRADICTION_TYPE, claim_key),
    ).fetchone()
    return row is not None


def teach(conn, claim_key: str, value, source: str = "human") -> dict:
    """The teacher-loop: a human asserts a claim's value and settles any open conflict.

    The answer enters as an ordinary assertion from a human source -- no preset trust.
    It governs naturally: the disagreeing machine sources have driven each other's trust
    to ~0, so the human's seed trust outranks them and `resolve` picks the taught value;
    going forward, whichever source agreed with the human earns trust back. Any open
    SourceContradiction inquiry for this claim is then resolved -- GENUS asked, you
    answered.
    """
    result = observe_assertion(conn, claim_key, value, source)
    resolved = []
    try:
        rows = conn.execute(
            "SELECT id FROM inquiry_log WHERE inquiry_type = ? AND claim_key = ? AND state = 'open'",
            (inquiries.SOURCE_CONTRADICTION_TYPE, claim_key),
        ).fetchall()
        for row in rows:
            inquiries.record_inquiry_resolved_event(conn, int(row["id"]), f"{source}={value}")
            resolved.append(int(row["id"]))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"event_id": result["event_id"], "resolved_inquiries": resolved}


def teach_relation(
    conn, subject: str, predicate: str, object_: str, source: str = "human"
) -> dict:
    """The teacher-loop for the knowledge graph: a human (or, later, the LLM at the edge)
    asserts the correct relation and settles any open conflict.

    For a FUNCTIONAL predicate the taught object is authoritative, so competing objects are
    retracted first -- the wrong acquisition is taken back, not left to linger. The relation
    is then asserted from the (human) source, and any open relation-contradiction inquiry for
    ``(subject, predicate)`` is resolved -- GENUS asked, you answered. (Non-functional
    predicates legitimately keep several objects; use ``unrelate`` to drop a specific wrong
    edge there.)
    """
    rel_key = f"{subject}|{predicate}"
    retracted: list[str] = []
    if predicate in sources.FUNCTIONAL_PREDICATES:
        competitors = {
            row["object"]
            for row in sources.relations(conn, subject=subject, predicate=predicate)
            if row["object"] != object_
        }
        for obj in competitors:
            retract_relation(conn, subject, predicate, obj, reason=f"corrected by {source}")
            retracted.append(obj)
    result = observe_relation(conn, subject, predicate, object_, source)
    resolved: list[int] = []
    try:
        rows = conn.execute(
            "SELECT id FROM inquiry_log WHERE inquiry_type = ? AND claim_key = ? AND state = 'open'",
            (inquiries.SOURCE_CONTRADICTION_TYPE, rel_key),
        ).fetchall()
        for row in rows:
            inquiries.record_inquiry_resolved_event(
                conn, int(row["id"]), f"{source}: {subject} -[{predicate}]-> {object_}"
            )
            resolved.append(int(row["id"]))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {
        "event_id": result["event_id"],
        "resolved_inquiries": resolved,
        "retracted_objects": retracted,
    }


def observe_relation(
    conn, subject: str, predicate: str, object_: str, source: str, derivation: str | None = None,
    commit: bool = True,
) -> dict:
    """Record a relation between two entities -- networked knowledge, not just a value.

    The structure pillar of the WISSEN layer: a ``(subject, predicate, object)`` triple
    asserted by a source, e.g. ``(system.thermal, correlates_with, system.load)``. The
    fact is projected into ``relation_projection`` and is replay-stable; it is read as a
    graph via ``genus relations``. The same source-trust applies, so a relation from a
    distrusted source is held lightly.

    ``commit=False`` defers the commit to the caller -- for a bulk apply (tausende Kanten, z.B.
    der Verwandtschafts-Nachtlauf) hält der Aufrufer EINE Transaktion offen und committet
    gebündelt, statt pro Kante zu fsyncen. Ein Fehler rollt weiterhin sofort zurück."""
    try:
        subject, object_ = relation_semantics.canonical_pair(subject, predicate, object_)
        idempotent_stream = relation_semantics.is_idempotent_stream(source, predicate)
        if idempotent_stream:
            # ``verwandt`` is undirected. Canonicalising at the core boundary protects every
            # caller, not just today's materializer, while the reverse lookup also recognises
            # rows written by older releases in the opposite orientation.
            # The lock must precede the read. Otherwise two concurrent materializers can both
            # observe "missing" and append duplicate events before the projection conflict
            # collapses only their read model.
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
        payload = {
            "subject": subject,
            "predicate": predicate,
            "object": object_,
            "source": source,
            "derivation": derivation or f"source:{source}",
        }
        if idempotent_stream:
            existing = conn.execute(
                """
                SELECT derivation FROM relation_projection
                WHERE predicate = ? AND source = ?
                  AND ((subject = ? AND object = ?) OR (subject = ? AND object = ?))
                """,
                (predicate, source, subject, object_, object_, subject),
            ).fetchall()
            if any(row[0] == payload["derivation"] for row in existing):
                if commit:
                    conn.commit()
                return {"event_id": None, "events": [], "unchanged": True}
        event_id = ledger.append(conn, "relation_asserted", payload)
        payload["_event_created_at"] = ledger.event_created_at(conn, event_id)
        projection.apply_relation_asserted(conn, payload)
        events = [{"event_type": "relation_asserted", "id": event_id}]
        # Knowledge self-check: for a functional predicate, if sources now disagree on the
        # object, flag the contradiction and raise one inquiry -- the teacher-loop seed for
        # the knowledge graph (mirrors observe_assertion on the value side).
        rel_key = f"{subject}|{predicate}"
        contra = sources.relation_contradiction(conn, subject, predicate)
        if contra["contradiction"] and not _open_source_contradiction(conn, rel_key):
            contradiction_id = ledger.append(
                conn,
                "contradiction_detected",
                {"claim_key": rel_key, "reason": f"sources disagree on {subject} -[{predicate}]->"},
            )
            events.append({"event_type": "contradiction_detected", "id": contradiction_id})
            inquiries.record_source_contradiction_inquiry(
                conn,
                claim_key=rel_key,
                source_event=contradiction_id,
                payload={"subject": subject, "predicate": predicate,
                         "objects": contra["objects"], "review_recommended": True},
            )
            events.append({"event_type": "inquiry_created"})
        # Rule self-check: for an explicitly acyclic hierarchy predicate, a new edge that closes a
        # ring violates ACYCLICITY and collapses the hierarchy. A structural self-contradiction in
        # GENUS's own reasoning, not a fact.
        from genus import inference  # local: reactors is imported broadly; avoid an import cycle
        cyc_key = f"{subject}|{predicate}|{object_}|acyclic"
        if inference.closes_cycle(conn, subject, predicate, object_):
            contradiction_id = ledger.append(
                conn,
                "contradiction_detected",
                {"claim_key": cyc_key,
                 "reason": f"{predicate} cycle: {object_} already reaches {subject}"},
            )
            events.append({"event_type": "contradiction_detected", "id": contradiction_id})
            # Acyclicity is a hard structural invariant, not an ambiguous source
            # disagreement. Preserve the attempted assertion in the ledger, but remove
            # its projection in the same transaction instead of creating an unbounded
            # human backlog for something the graph can prove mechanically.
            retraction = {
                "subject": subject,
                "predicate": predicate,
                "object": object_,
                "source": source,
                "reason": "auto-rejected: acyclicity invariant",
            }
            retraction_id = ledger.append(conn, "relation_retracted", retraction)
            projection.apply_relation_retracted(conn, retraction)
            events.append({"event_type": "relation_retracted", "id": retraction_id})
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"event_id": event_id, "events": events, "unchanged": False}


def sae_fehlende(conn, tripel: list[tuple[str, str, str]], quelle: str) -> int:
    """Idempotenter Sä-Helfer (Phase 0 der Ziel-Architektur): sät nur die Tripel, die im
    Graphen noch fehlen, über den normalen Schreibpfad (``observe_relation`` -- Herkunft,
    Widerspruchs-Check, Zyklus-Check inklusive). Gibt die Zahl NEU gesäter Kanten zurück.

    Vorher lebte exakt dieses Idiom (vorhandene Tripel sammeln -> nur Fehlendes säen ->
    zählen) zweimal handgeschrieben in ``ziele.seed_ziele`` und ``verstehen.seed_raster``.
    ``erinnerung.migriere_notizen`` bleibt bewusst eigen: das ist Migrieren + Zurücknehmen,
    kein Säen -- Gleiches gleich, Ungleiches ungleich."""
    praedikate = sorted({p for _, p, _ in tripel})
    vorhanden = {
        (r["subject"], r["predicate"], r["object"])
        for p in praedikate
        for r in sources.relations(conn, predicate=p)
    }
    neu = 0
    for s, p, o in tripel:
        if (s, p, o) not in vorhanden:
            observe_relation(conn, s, p, o, quelle)
            vorhanden.add((s, p, o))   # ein doppeltes Tripel in der Liste sät nur einmal
            neu += 1
    return neu


def retract_relation(
    conn, subject: str, predicate: str, object_: str, source: str | None = None, reason: str | None = None
) -> dict:
    """Take a relation back -- the honest counterpart to acquiring one. A source can be
    wrong (a mis-resolved word, a corrected mapping); ``relation_retracted`` is projected
    by removing the edge from ``relation_projection`` on replay. With ``source`` only that
    source's edge goes; without it the triple is removed for every source.
    """
    try:
        subject, object_ = relation_semantics.canonical_pair(subject, predicate, object_)
        payload = {
            "subject": subject,
            "predicate": predicate,
            "object": object_,
            "source": source,
            "reason": reason or "retracted",
        }
        event_id = ledger.append(conn, "relation_retracted", payload)
        projection.apply_relation_retracted(conn, payload)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"event_id": event_id, "events": [{"event_type": "relation_retracted", "id": event_id}]}


def process_observation(conn, observation_id: int) -> list[dict]:
    observation = _load_event(conn, observation_id)
    if observation["event_type"] != "observation_created":
        raise ValueError("process_observation requires observation_created")

    payload = json.loads(observation["payload"])
    metric_key = payload.get("metric_key", rules.CPU_METRIC_KEY)
    evidence_payload = {
        "observation_id": observation_id,
        "metric_key": metric_key,
        "metric_value": payload["raw_value"],
        # Provenance into the knowledge layer: the membrane already tags every
        # observation with a source -- carry it so source trust can be learned
        # read-time (genus/sources.py). Optional on the contract; older
        # evidence_recorded events (pre-source) stay valid and replay clean.
        "source": payload.get("source", "sensor"),
    }
    evidence_id = ledger.append(conn, "evidence_recorded", evidence_payload)
    evidence_payload["_event_id"] = evidence_id
    evidence_payload["_event_created_at"] = ledger.event_created_at(conn, evidence_id)
    projection.apply_evidence_recorded(conn, evidence_payload)  # indexed value view
    events = [
        {
            "event_type": "evidence_recorded",
            "id": evidence_id,
            "metric_key": metric_key,
            "metric_value": payload["raw_value"],
        }
    ]
    # One uniform pass over the observation-reactor registry: each reactor is a
    # (conn, metric_key) -> list[event_type] module. Adding a rule type means
    # registering a reactor in rules.REACTORS, not adding a hand-written pass here.
    for reactor in rules.REACTORS:
        events.extend({"event_type": event_type} for event_type in reactor(conn, metric_key))
    return events


def _load_event(conn, event_id: int):
    row = conn.execute("SELECT * FROM event_log WHERE id = ?", (event_id,)).fetchone()
    if row is None:
        raise ValueError(f"event not found: {event_id}")
    return row
