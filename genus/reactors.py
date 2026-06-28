from __future__ import annotations

import json

from genus import inquiries, learning, ledger, rules, sources


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
    stays pure -- no fetch here. ``assertion_recorded`` is a raw fact (not projected),
    so it is replay-stable; source trust and consensus over the candidates are computed
    read-time in ``genus/sources.py``.
    """
    try:
        event_id = ledger.append(
            conn,
            "assertion_recorded",
            {
                "claim_key": claim_key,
                "claim_value": claim_value,
                "source": source,
                "derivation": derivation or f"source:{source}",
            },
        )
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


def process_observation(conn, observation_id: int) -> list[dict]:
    observation = _load_event(conn, observation_id)
    if observation["event_type"] != "observation_created":
        raise ValueError("process_observation requires observation_created")

    payload = json.loads(observation["payload"])
    metric_key = payload.get("metric_key", rules.CPU_METRIC_KEY)
    evidence_id = ledger.append(
        conn,
        "evidence_recorded",
        {
            "observation_id": observation_id,
            "metric_key": metric_key,
            "metric_value": payload["raw_value"],
            # Provenance into the knowledge layer: the membrane already tags every
            # observation with a source -- carry it so source trust can be learned
            # read-time (genus/sources.py). Optional on the contract; older
            # evidence_recorded events (pre-source) stay valid and replay clean.
            "source": payload.get("source", "sensor"),
        },
    )
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
