from __future__ import annotations

import json

from genus import ledger, projection


ACTIVE = "active"
SUPERSEDED = "superseded"
STATE_KEY = "system.pressure"
DERIVATION = "rule:system_pressure_state_v1"
ELEVATED = "elevated"
LATENT = "latent"
NOMINAL = "nominal"
ACTIVITY_CLAIM_KEY = "system.activity"
PRESSURE_CLAIM_KEYS = (
    "system.load",
    "system.memory",
    "system.disk",
    "system.temperature",
)


def refresh(conn) -> list[dict]:
    candidate = derive_pressure_state(conn)
    if candidate is None:
        return []
    current = active_state(conn, candidate["state_key"])
    if current is not None and _same_state(current, candidate):
        return []

    event_id = record_state_changed_event(
        conn,
        candidate,
        previous_state_id=int(current["id"]) if current is not None else None,
    )
    return [
        {
            "event_type": "state_changed",
            "id": event_id,
            "state_key": candidate["state_key"],
            "state_value": candidate["state_value"],
        }
    ]


def derive_pressure_state(conn) -> dict | None:
    rows = _active_relevant_beliefs(conn)
    if not rows:
        return None

    pressure_rows = [row for row in rows if row["claim_key"] in PRESSURE_CLAIM_KEYS]
    high_rows = [row for row in pressure_rows if row["claim_value"] == "high"]
    activity = next(
        (row for row in rows if row["claim_key"] == ACTIVITY_CLAIM_KEY),
        None,
    )

    if high_rows:
        if activity is not None and activity["claim_value"] == "idle":
            state_value = LATENT
            reason = "high resource pressure while activity is idle"
        else:
            state_value = ELEVATED
            reason = "active or unknown activity with high resource pressure"
        supporting_rows = ([activity] if activity is not None else []) + high_rows
    else:
        state_value = NOMINAL
        reason = "no active high resource pressure belief"
        supporting_rows = rows

    supporting_beliefs = sorted(int(row["id"]) for row in supporting_rows)
    components = {
        row["claim_key"]: row["claim_value"]
        for row in sorted(rows, key=lambda item: (item["claim_key"], item["id"]))
    }
    components["pressure_high_count"] = len(high_rows)
    if activity is not None:
        components["activity"] = activity["claim_value"]

    return {
        "state_key": STATE_KEY,
        "state_value": state_value,
        "derivation": DERIVATION,
        "supporting_beliefs": supporting_beliefs,
        "components": components,
        "reason": reason,
    }


def record_state_changed_event(
    conn, candidate: dict, previous_state_id: int | None = None
) -> int:
    state_id = next_state_id(conn)
    event_payload = {
        "state_id": state_id,
        "state_key": candidate["state_key"],
        "state_value": candidate["state_value"],
        "previous_state_id": previous_state_id,
        "derivation": candidate["derivation"],
        "supporting_beliefs": candidate["supporting_beliefs"],
        "components": candidate["components"],
        "reason": candidate["reason"],
    }
    event_id = ledger.append(conn, "state_changed", event_payload)
    event_payload["_event_created_at"] = ledger.event_created_at(conn, event_id)
    apply_state_changed(conn, event_payload)
    return event_id


def apply_state_changed(conn, payload: dict) -> int:
    previous_state_id = payload.get("previous_state_id")
    state_id = int(payload["state_id"])
    created_at = payload.get("_event_created_at")
    conn.execute(
        """
        INSERT INTO state_projection
            (id, state_key, state_value, status, derivation, supporting_beliefs,
             components, reason, created_at, last_updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?,
                COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')))
        """,
        (
            state_id,
            payload["state_key"],
            payload["state_value"],
            ACTIVE,
            payload["derivation"],
            _json(payload["supporting_beliefs"]),
            _json(payload["components"]),
            payload["reason"],
            created_at,
            created_at,
        ),
    )
    if previous_state_id is not None:
        conn.execute(
            """
            UPDATE state_projection
            SET status = ?,
                superseded_by = ?,
                last_updated_at = COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            WHERE id = ?
            """,
            (SUPERSEDED, state_id, created_at, int(previous_state_id)),
        )
    return state_id


def active_state(conn, state_key: str = STATE_KEY):
    return conn.execute(
        """
        SELECT * FROM state_projection
        WHERE state_key = ? AND status = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (state_key, ACTIVE),
    ).fetchone()


def get_state(conn, state_id: int):
    row = conn.execute(
        "SELECT * FROM state_projection WHERE id = ?",
        (state_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"state not found: {state_id}")
    return row


def list_active_states(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM state_projection
        WHERE status = ?
        ORDER BY state_key, id
        """,
        (ACTIVE,),
    ).fetchall()
    return [state_dict(row) for row in rows]


def state_dict(row) -> dict:
    data = dict(row)
    data["supporting_beliefs"] = json.loads(row["supporting_beliefs"])
    data["components"] = json.loads(row["components"])
    return data


def next_state_id(conn) -> int:
    row = conn.execute(
        "SELECT seq FROM sqlite_sequence WHERE name = 'state_projection'"
    ).fetchone()
    if row is not None:
        return int(row["seq"]) + 1
    row = conn.execute(
        "SELECT COALESCE(MAX(id), 0) AS max_id FROM state_projection"
    ).fetchone()
    return int(row["max_id"]) + 1


def _active_relevant_beliefs(conn) -> list[dict]:
    keys = (ACTIVITY_CLAIM_KEY, *PRESSURE_CLAIM_KEYS)
    placeholders = ",".join("?" for _ in keys)
    rows = conn.execute(
        f"""
        SELECT id, claim_key, claim_value
        FROM belief_projection
        WHERE state = ?
          AND claim_key IN ({placeholders})
        ORDER BY claim_key, id
        """,
        (projection.ACTIVE, *keys),
    ).fetchall()
    return [dict(row) for row in rows]


def _same_state(current, candidate: dict) -> bool:
    return (
        current["state_value"] == candidate["state_value"]
        and current["supporting_beliefs"] == _json(candidate["supporting_beliefs"])
        and current["components"] == _json(candidate["components"])
    )


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
