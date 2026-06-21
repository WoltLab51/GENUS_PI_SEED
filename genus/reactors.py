from __future__ import annotations

import json

from genus import ledger, rules


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
        return {"observation_id": observation_id, "events": events}
    except Exception:
        conn.rollback()
        raise


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
            "metric_key": payload.get("metric_key", rules.CPU_METRIC_KEY),
            "metric_value": payload["raw_value"],
        },
    )
    metric_key = payload.get("metric_key", rules.CPU_METRIC_KEY)
    events = [
        {
            "event_type": "evidence_recorded",
            "id": evidence_id,
            "metric_key": metric_key,
            "metric_value": payload["raw_value"],
        }
    ]
    events.extend({"event_type": event_type} for event_type in rules.apply_threshold(conn, metric_key))
    return events


def _load_event(conn, event_id: int):
    row = conn.execute("SELECT * FROM event_log WHERE id = ?", (event_id,)).fetchone()
    if row is None:
        raise ValueError(f"event not found: {event_id}")
    return row
