from __future__ import annotations

import json

from genus import learning, ledger, rules


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
