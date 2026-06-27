from __future__ import annotations

import datetime

from genus import ledger


# The learning-program engine. It predicts the next observation of a metric, the
# future grades it, and the accumulating error is the learning curve. Forecasts are
# raw facts (forecast_made, forecast_scored), like observations: no projection, so
# replay is unaffected. The forecast is a self-calibrated cycle mean -- no fixed
# model -- and the engine is generic over both the metric and the cycle period
# (hour-of-day or weekday), so it serves signals of any cadence: weather (hourly),
# system metrics (5-minutely), repo (daily). The next observation's bucket is found
# from the metric's own typical gap, so the cadence need not be configured.

MIN_HISTORY = 2  # need two readings to estimate the cadence and a baseline
RECENT_GAPS = 12  # how many recent intervals to estimate the typical gap from


def _dt(created_at: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(created_at.replace("Z", "+00:00"))


def _bucket(moment: datetime.datetime, cycle: str) -> int:
    if cycle == "hour":
        return moment.hour
    if cycle == "weekday":
        return moment.weekday()
    raise ValueError(f"unknown cycle: {cycle}")


def _readings(conn, metric_key: str) -> list[tuple[str, float]]:
    rows = conn.execute(
        """
        SELECT created_at, json_extract(payload, '$.metric_value') AS v
        FROM event_log
        WHERE event_type = 'evidence_recorded'
          AND json_extract(payload, '$.metric_key') = ?
        ORDER BY id
        """,
        (metric_key,),
    ).fetchall()
    return [(row["created_at"], float(row["v"])) for row in rows]


def _next_observation_bucket(readings: list[tuple[str, float]], cycle: str):
    # Estimate the next observation's time = latest + the median recent gap, then
    # take its cycle bucket. This adapts to any cadence: a 5-minute metric stays in
    # the same hour, an hourly one rolls to the next hour, a daily one to the next
    # weekday -- without configuring the cadence.
    if len(readings) < MIN_HISTORY:
        return None
    times = [_dt(ts) for (ts, _) in readings][-(RECENT_GAPS + 1):]
    gaps = sorted((b - a).total_seconds() for a, b in zip(times, times[1:]))
    median_gap = gaps[len(gaps) // 2]
    next_moment = times[-1] + datetime.timedelta(seconds=median_gap)
    return _bucket(next_moment, cycle)


def forecast_value(conn, metric_key: str, cycle: str, target_bucket: int):
    # Predict the value in target_bucket as the mean of all past readings in that
    # bucket (the learned cycle). Cold start falls back to the overall mean.
    readings = _readings(conn, metric_key)
    same = [v for (ts, v) in readings if _bucket(_dt(ts), cycle) == target_bucket]
    if same:
        return sum(same) / len(same), len(same), f"{cycle}_cycle_mean"
    if readings:
        vals = [v for (_, v) in readings]
        return sum(vals) / len(vals), len(vals), "overall_mean"
    return None, 0, "none"


def _latest_reading(conn, metric_key: str):
    row = conn.execute(
        """
        SELECT json_extract(payload, '$.metric_value') AS v
        FROM event_log
        WHERE event_type = 'evidence_recorded'
          AND json_extract(payload, '$.metric_key') = ?
        ORDER BY id DESC LIMIT 1
        """,
        (metric_key,),
    ).fetchone()
    return float(row["v"]) if row else None


def _pending_forecast(conn, metric_key: str):
    row = conn.execute(
        """
        SELECT id, json_extract(payload, '$.predicted_value') AS p
        FROM event_log
        WHERE event_type = 'forecast_made'
          AND json_extract(payload, '$.metric_key') = ?
          AND id NOT IN (
              SELECT json_extract(payload, '$.forecast_event')
              FROM event_log WHERE event_type = 'forecast_scored'
          )
        ORDER BY id DESC LIMIT 1
        """,
        (metric_key,),
    ).fetchone()
    return (int(row["id"]), float(row["p"])) if row else None


def run_forecast_cycle(conn, metric_key: str, cycle: str) -> list[dict]:
    # One turn of the loop, after a fresh observation: (1) score the last un-scored
    # forecast against the value that just arrived -- the self-test -- then (2)
    # forecast the next observation. Forecasting waits for MIN_HISTORY readings.
    try:
        events: list[dict] = []
        actual = _latest_reading(conn, metric_key)
        if actual is None:
            return events
        pending = _pending_forecast(conn, metric_key)
        if pending is not None:
            forecast_id, predicted = pending
            scored_id = ledger.append(
                conn,
                "forecast_scored",
                {
                    "forecast_event": forecast_id,
                    "metric_key": metric_key,
                    "predicted_value": predicted,
                    "actual_value": actual,
                    "error": abs(predicted - actual),
                },
            )
            events.append({"event_type": "forecast_scored", "id": scored_id})
        readings = _readings(conn, metric_key)
        target = _next_observation_bucket(readings, cycle)
        if target is not None:
            predicted, support, method = forecast_value(conn, metric_key, cycle, target)
            if predicted is not None:
                made_id = ledger.append(
                    conn,
                    "forecast_made",
                    {
                        "metric_key": metric_key,
                        "predicted_value": predicted,
                        "method": method,
                        "support": support,
                    },
                )
                events.append({"event_type": "forecast_made", "id": made_id})
        conn.commit()
        return events
    except Exception:
        conn.rollback()
        raise


def forecasted_metrics(conn) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT json_extract(payload, '$.metric_key') AS m
        FROM event_log WHERE event_type = 'forecast_scored' ORDER BY m
        """
    ).fetchall()
    return [row["m"] for row in rows]


def curve(conn, metric_key: str) -> dict:
    # The learning curve for one metric, read-time: is its forecast error shrinking?
    errors = [
        float(row["e"])
        for row in conn.execute(
            """
            SELECT json_extract(payload, '$.error') AS e FROM event_log
            WHERE event_type = 'forecast_scored'
              AND json_extract(payload, '$.metric_key') = ?
            ORDER BY id
            """,
            (metric_key,),
        ).fetchall()
    ]
    n = len(errors)
    if n == 0:
        return {"metric_key": metric_key, "scored": 0, "mean_error": None,
                "early_mean_error": None, "recent_mean_error": None, "improving": None}
    window = min(n, 20)
    early_mean = sum(errors[:window]) / window
    recent_mean = sum(errors[-window:]) / window
    return {
        "metric_key": metric_key,
        "scored": n,
        "mean_error": sum(errors) / n,
        "early_mean_error": early_mean,
        "recent_mean_error": recent_mean,
        "improving": (recent_mean < early_mean) if n >= 2 else None,
    }


def curves(conn) -> list[dict]:
    return [curve(conn, metric_key) for metric_key in forecasted_metrics(conn)]
