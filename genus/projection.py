from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterable

from genus import ledger
from genus.confidence import calculate_confidence


ACTIVE = "active"
SUPERSEDED = "superseded"
SUPPORTED = "supported"
CONTESTED = "contested"
UNCERTAIN = "uncertain"

# Learned confidence half-life: instead of a preset per claim_key, derive each
# belief's decay timescale from its own lived behaviour. H = observation span /
# number of flips = the mean time between belief changes. A belief that never
# flips earns a long half-life (slow decay, high earned confidence); one that
# flips constantly gets a short one (stays skeptical). No epistemic constants --
# span and flips are observed. The two floors below are structural, not epistemic.
LEARN_MIN_SPAN_SECONDS = 3600.0     # need ~an hour of tenure to learn a timescale
LEARN_MIN_HALFLIFE_SECONDS = 300.0  # never decay faster than the sensing cadence


def _parse_ts(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def learned_halflife(conn, claim_key: str) -> float | None:
    """Derive a belief's confidence half-life from its own flip history.

    Returns ``None`` when there is too little tenure to learn a timescale, so the
    caller falls back to the seed table. Read-time and replay-safe (confidence has
    no replay effect).
    """
    row = conn.execute(
        """
        SELECT COUNT(*) AS instances, MIN(created_at) AS first_at,
               MAX(last_updated_at) AS last_at
        FROM belief_projection
        WHERE claim_key = ?
        """,
        (claim_key,),
    ).fetchone()
    if not row or not row["instances"] or not row["first_at"] or not row["last_at"]:
        return None
    span = (_parse_ts(row["last_at"]) - _parse_ts(row["first_at"])).total_seconds()
    if span < LEARN_MIN_SPAN_SECONDS:
        return None
    flips = int(row["instances"]) - 1
    return max(span / max(flips, 1), LEARN_MIN_HALFLIFE_SECONDS)

# Structural bound on the projection's evidence lists. The full history always
# stays in event_log; the projection keeps only the most recent ids. This keeps
# the evidence-time lookup far under SQLite's parameter limit and makes each
# confirm O(window) instead of O(n). It is confidence-negligible: confidence
# weights evidence by 2^(-age/H), so events older than a few half-lives carry ~0,
# and W/(W+1) saturates for confident beliefs. A structural cap, not an epistemic
# threshold.
SUPPORTING_EVENTS_WINDOW = 1024


def _recent(ids: list[int]) -> list[int]:
    if len(ids) > SUPPORTING_EVENTS_WINDOW:
        return ids[-SUPPORTING_EVENTS_WINDOW:]
    return ids


def json_list(value: str | None) -> list[int]:
    if not value:
        return []
    parsed = json.loads(value)
    return list(parsed)


def encode_ids(values: Iterable[int]) -> str:
    return json.dumps(list(values), separators=(",", ":"))


def active_belief(conn, claim_key: str, claim_value: str | None = None):
    if claim_value is None:
        return conn.execute(
            """
            SELECT * FROM belief_projection
            WHERE claim_key = ? AND state = ?
            ORDER BY id DESC LIMIT 1
            """,
            (claim_key, ACTIVE),
        ).fetchone()
    return conn.execute(
        """
        SELECT * FROM belief_projection
        WHERE claim_key = ? AND claim_value = ? AND state = ?
        ORDER BY id DESC LIMIT 1
        """,
        (claim_key, claim_value, ACTIVE),
    ).fetchone()


def create_belief(
    conn,
    claim_key: str,
    claim_value: str,
    derivation: str,
    supporting_events: list[int],
    belief_id: int | None = None,
    created_at: str | None = None,
) -> int:
    if not derivation:
        raise ValueError("derivation must not be empty")
    supporting_events = _recent(list(supporting_events))
    if belief_id is not None:
        conn.execute(
            """
            INSERT INTO belief_projection
                (id, claim_key, claim_value, state, derivation,
                 supporting_events, created_at, last_updated_at)
            VALUES (?, ?, ?, ?, ?, ?, COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                    COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')))
            """,
            (
                belief_id,
                claim_key,
                claim_value,
                ACTIVE,
                derivation,
                encode_ids(supporting_events),
                created_at,
                created_at,
            ),
        )
        return belief_id
    cur = conn.execute(
        """
        INSERT INTO belief_projection
            (claim_key, claim_value, state, derivation,
             supporting_events, created_at, last_updated_at)
        VALUES (?, ?, ?, ?, ?, COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')))
        """,
        (
            claim_key,
            claim_value,
            ACTIVE,
            derivation,
            encode_ids(supporting_events),
            created_at,
            created_at,
        ),
    )
    return int(cur.lastrowid)


def confirm_belief(
    conn, belief_id: int, supporting_event: int, updated_at: str | None = None
) -> None:
    row = get_belief(conn, belief_id)
    supporting = json_list(row["supporting_events"])
    if supporting_event not in supporting:
        supporting.append(supporting_event)
    supporting = _recent(supporting)
    conn.execute(
        """
        UPDATE belief_projection
        SET supporting_events = ?,
            last_updated_at = COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        WHERE id = ?
        """,
        (encode_ids(supporting), updated_at, belief_id),
    )


def weaken_belief(
    conn, belief_id: int, contradicting_event: int, updated_at: str | None = None
) -> None:
    row = get_belief(conn, belief_id)
    contradicting = json_list(row["contradicting_events"])
    if contradicting_event not in contradicting:
        contradicting.append(contradicting_event)
    contradicting = _recent(contradicting)
    conn.execute(
        """
        UPDATE belief_projection
        SET contradicting_events = ?,
            last_updated_at = COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        WHERE id = ?
        """,
        (encode_ids(contradicting), updated_at, belief_id),
    )


def supersede_belief(
    conn, old_belief_id: int, new_belief_id: int, updated_at: str | None = None
) -> None:
    conn.execute(
        """
        UPDATE belief_projection
        SET state = ?,
            superseded_by = ?,
            last_updated_at = COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        WHERE id = ?
        """,
        (SUPERSEDED, new_belief_id, updated_at, old_belief_id),
    )


def belief_uebergang(
    conn,
    *,
    claim_key: str,
    claim_value: str,
    derivation: str,
    supporting_events: list[int],
    reason_key: str | None = None,
) -> dict:
    """Die EINE Belief-Zustandsmaschine (Phase 0 der Ziel-Architektur): schau nach dem
    aktiven Belief -- keiner: erstellen; gleicher Wert: bestätigen; anderer Wert:
    ablösen. Schreibt das Ledger-Event UND wendet die Projektion an, immer als Paar.

    Vorher lebte exakt diese Entscheidung dreimal wortgleich handgeschrieben
    (``rules._record_value_belief``, ``rules.apply_binary_rule`` inline,
    ``operation._record_operation_belief``) -- ein Bugfix an der Payload-Form musste an
    drei Stellen zugleich richtig sein. ``rules.apply_threshold`` bleibt bewusst eigen:
    seine Maschine ist wirklich anders (asymmetrisch -- bestätigt nur "high", löst nur
    high->normal ab, kennt ein "weaken"; Gleiches gleich, Ungleiches ungleich).

    ``reason_key`` überschreibt den Präfix des Ablöse-Grunds (der Binary-Pfad nennt
    historisch den metric_key, nicht den claim_key -- verhalten-erhaltend beibehalten).
    ``fresh`` im Ergebnis: hat der Belief den Wert FRISCH angenommen (erstellt oder
    abgelöst)? Ein Bestätigen ist kein Übergang -- Aufrufer, die auf einen schlechten
    Wert ein Proposal erheben, erheben es so einmal pro Episode, nicht pro Wiederholung.
    """
    active = active_belief(conn, claim_key)
    if active is None:
        belief_id = next_belief_id(conn)
        payload = {
            "belief_id": belief_id,
            "claim_key": claim_key,
            "claim_value": claim_value,
            "derivation": derivation,
            "supporting_events": list(supporting_events),
        }
        event_id = ledger.append(conn, "belief_created", payload)
        payload["_event_created_at"] = ledger.event_created_at(conn, event_id)
        apply_belief_created(conn, payload)
        return {"event_type": "belief_created", "belief_id": belief_id,
                "belief_event_id": event_id, "claim_value": claim_value, "fresh": True}

    if active["claim_value"] == claim_value:
        payload = {
            "belief_id": int(active["id"]),
            "new_supporting_event": supporting_events[-1],
        }
        event_id = ledger.append(conn, "belief_confirmed", payload)
        payload["_event_created_at"] = ledger.event_created_at(conn, event_id)
        apply_belief_confirmed(conn, payload)
        return {"event_type": "belief_confirmed", "belief_id": int(active["id"]),
                "belief_event_id": event_id, "claim_value": claim_value, "fresh": False}

    new_belief_id = next_belief_id(conn)
    payload = {
        "old_belief_id": int(active["id"]),
        "new_belief_id": new_belief_id,
        "claim_key": claim_key,
        "claim_value": claim_value,
        "derivation": derivation,
        "supporting_events": list(supporting_events),
        "reason": f"{reason_key or claim_key}_changed_to_{claim_value}",
    }
    event_id = ledger.append(conn, "belief_superseded", payload)
    payload["_event_created_at"] = ledger.event_created_at(conn, event_id)
    apply_belief_superseded(conn, payload)
    return {"event_type": "belief_superseded", "belief_id": new_belief_id,
            "belief_event_id": event_id, "claim_value": claim_value, "fresh": True}


def get_belief(conn, belief_id: int):
    row = conn.execute(
        "SELECT * FROM belief_projection WHERE id = ?",
        (belief_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"belief not found: {belief_id}")
    return row


def list_active_beliefs(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM belief_projection
        WHERE state = ?
        ORDER BY claim_key, claim_value, id
        """,
        (ACTIVE,),
    ).fetchall()
    return [belief_with_confidence(conn, row) for row in rows]


def belief_with_confidence(conn, row) -> dict:
    supporting = json_list(row["supporting_events"])
    contradicting = json_list(row["contradicting_events"])
    supporting_times = evidence_created_at_times(conn, supporting)
    contradicting_times = evidence_created_at_times(conn, contradicting)
    confidence = calculate_confidence(
        supporting_times,
        contradicting_times,
        claim_key=row["claim_key"],
        # learned per-belief half-life; None falls back to the seed table
        halflife_seconds=learned_halflife(conn, row["claim_key"]),
    )
    return {
        "id": row["id"],
        "claim_key": row["claim_key"],
        "claim_value": row["claim_value"],
        "state": row["state"],
        "derivation": row["derivation"],
        "supporting": len(supporting),
        "contradicting": len(contradicting),
        "confidence": confidence,
        "epistemic_state": epistemic_state(confidence, bool(contradicting)),
    }


def epistemic_state(confidence: float, has_counterevidence: bool) -> str:
    """Name whether an active projection is currently fit to support decisions.

    Confidence >= 0.5 means weighted support outweighs counterevidence plus the
    uncertainty prior in ``calculate_confidence``. A lower value with explicit
    counterevidence is contested; pure decay without contradiction is uncertain.
    """
    if confidence >= 0.5:
        return SUPPORTED
    return CONTESTED if has_counterevidence else UNCERTAIN


def evidence_created_at_times(conn, event_ids: list[int]) -> list[str]:
    if not event_ids:
        return []
    placeholders = ",".join("?" for _ in event_ids)
    rows = conn.execute(
        f"""
        SELECT created_at
        FROM event_log
        WHERE id IN ({placeholders})
        ORDER BY id
        """,
        event_ids,
    ).fetchall()
    return [row["created_at"] for row in rows]


def next_belief_id(conn) -> int:
    row = conn.execute(
        "SELECT seq FROM sqlite_sequence WHERE name = 'belief_projection'"
    ).fetchone()
    if row is not None:
        return int(row["seq"]) + 1
    row = conn.execute("SELECT COALESCE(MAX(id), 0) AS max_id FROM belief_projection").fetchone()
    return int(row["max_id"]) + 1


def apply_belief_created(conn, payload: dict) -> int:
    return create_belief(
        conn,
        payload["claim_key"],
        payload["claim_value"],
        payload["derivation"],
        list(payload["supporting_events"]),
        payload.get("belief_id"),
        payload.get("_event_created_at"),
    )


def apply_belief_confirmed(conn, payload: dict) -> None:
    confirm_belief(
        conn,
        int(payload["belief_id"]),
        int(payload["new_supporting_event"]),
        payload.get("_event_created_at"),
    )


def apply_belief_weakened(conn, payload: dict) -> None:
    weaken_belief(
        conn,
        int(payload["belief_id"]),
        int(payload["contradicting_event"]),
        payload.get("_event_created_at"),
    )


def apply_relation_asserted(conn, payload: dict) -> None:
    """Project a relation_asserted event into the indexed knowledge graph.

    One row per distinct (subject, predicate, object, source); re-assertion only
    refreshes last_updated_at. The event stays the truth; this is the fast view.
    """
    created_at = payload.get("_event_created_at")
    conn.execute(
        """
        INSERT INTO relation_projection
            (subject, predicate, object, source, derivation, created_at, last_updated_at)
        VALUES (?, ?, ?, ?, ?, COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')))
        ON CONFLICT(subject, predicate, object, source) DO UPDATE SET
            last_updated_at = COALESCE(excluded.last_updated_at, last_updated_at)
        """,
        (
            payload["subject"],
            payload["predicate"],
            payload["object"],
            payload["source"],
            payload["derivation"],
            created_at,
            created_at,
        ),
    )


def apply_relation_retracted(conn, payload: dict) -> None:
    """Remove a relation from the indexed graph -- a source taking an assertion back (a
    wrong acquisition, a corrected mapping). The retraction event is itself the truth and
    is replayed in order, so the projection rebuilds correctly. With ``source`` only that
    source's edge goes; without it, every source's copy of the triple is removed.
    """
    if payload.get("source"):
        conn.execute(
            "DELETE FROM relation_projection "
            "WHERE subject = ? AND predicate = ? AND object = ? AND source = ?",
            (payload["subject"], payload["predicate"], payload["object"], payload["source"]),
        )
    else:
        conn.execute(
            "DELETE FROM relation_projection WHERE subject = ? AND predicate = ? AND object = ?",
            (payload["subject"], payload["predicate"], payload["object"]),
        )


def apply_evidence_recorded(conn, payload: dict) -> None:
    """Project a sensor value-claim into the indexed value_projection (the fast read view
    for resolve / source_trust). The event stays the truth."""
    conn.execute(
        "INSERT OR REPLACE INTO value_projection (event_id, claim_key, value, source, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (payload["_event_id"], payload["metric_key"], payload["metric_value"],
         payload.get("source", "sensor"), payload["_event_created_at"]),
    )


def apply_assertion_recorded(conn, payload: dict) -> None:
    """Project an explicit value-claim into the indexed value_projection."""
    conn.execute(
        "INSERT OR REPLACE INTO value_projection (event_id, claim_key, value, source, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (payload["_event_id"], payload["claim_key"], payload["claim_value"],
         payload["source"], payload["_event_created_at"]),
    )


def apply_belief_superseded(conn, payload: dict) -> int:
    new_belief_id = create_belief(
        conn,
        payload["claim_key"],
        payload["claim_value"],
        payload["derivation"],
        list(payload["supporting_events"]),
        int(payload["new_belief_id"]),
        payload.get("_event_created_at"),
    )
    supersede_belief(
        conn,
        int(payload["old_belief_id"]),
        new_belief_id,
        payload.get("_event_created_at"),
    )
    return new_belief_id
