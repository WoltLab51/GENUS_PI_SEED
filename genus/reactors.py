from __future__ import annotations

import json

from genus import ledger, rules


def observe_cpu_reading(conn, reading: dict) -> dict:
    observation_id = ledger.append(
        conn,
        "observation_created",
        {
            "source": reading["source"],
            "raw_value": reading["raw_value"],
            "unit": reading["unit"],
            "interval": reading["interval"],
        },
    )
    events = process_observation(conn, observation_id)
    return {"observation_id": observation_id, "events": events}


def process_observation(conn, observation_id: int) -> list[dict]:
    observation = _load_event(conn, observation_id)
    if observation["event_type"] != "observation_created":
        raise ValueError("process_observation requires observation_created")

    payload = json.loads(observation["payload"])
    evidence_id = ledger.append(
        conn,
        "evidence_recorded",
        {
            "observation_id": observation_id,
            "metric_key": rules.METRIC_KEY,
            "metric_value": payload["raw_value"],
        },
    )
    events = [
        {
            "event_type": "evidence_recorded",
            "id": evidence_id,
            "metric_key": rules.METRIC_KEY,
            "metric_value": payload["raw_value"],
        }
    ]
    events.extend({"event_type": event_type} for event_type in rules.apply_cpu_threshold(conn))
    return events


def _load_event(conn, event_id: int):
    row = conn.execute("SELECT * FROM event_log WHERE id = ?", (event_id,)).fetchone()
    if row is None:
        raise ValueError(f"event not found: {event_id}")
    return row
