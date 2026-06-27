from __future__ import annotations

from genus import ledger


# The learning-program engine. First application: weather self-forecasting -- GENUS
# predicts the next observation, the future grades it, and its forecast error is the
# learning curve. Forecasts are recorded as raw facts (forecast_made, forecast_scored),
# like observations: no projection, so replay is unaffected. The forecast itself is
# a self-calibrated daily-cycle mean (no fixed model), computed read-time from the
# ledger. The same engine will later point at richer, verifiable domains.


def _hour(created_at: str) -> int:
    # created_at is ISO like 2026-06-27T07:56:07.674Z -> hour of day (UTC).
    return int(created_at[11:13])


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


def forecast_value(conn, metric_key: str, target_hour: int):
    # Predict the value at target_hour as the mean of all past readings at that hour
    # of day. As days accumulate the hourly mean stabilises and the forecast improves
    # -- a learned daily rhythm, no fixed model. Cold start (no reading yet for that
    # hour) falls back to the overall mean. Returns (value, support, method).
    readings = _readings(conn, metric_key)
    same_hour = [v for (ts, v) in readings if _hour(ts) == target_hour]
    if same_hour:
        return sum(same_hour) / len(same_hour), len(same_hour), "hourly_cycle_mean"
    if readings:
        vals = [v for (_, v) in readings]
        return sum(vals) / len(vals), len(vals), "overall_mean"
    return None, 0, "none"


def _latest_reading(conn, metric_key: str):
    row = conn.execute(
        """
        SELECT created_at, json_extract(payload, '$.metric_value') AS v
        FROM event_log
        WHERE event_type = 'evidence_recorded'
          AND json_extract(payload, '$.metric_key') = ?
        ORDER BY id DESC LIMIT 1
        """,
        (metric_key,),
    ).fetchone()
    return (row["created_at"], float(row["v"])) if row else None


def _pending_forecast(conn, metric_key: str):
    # The latest forecast for this metric that has not yet been scored.
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


def run_forecast_cycle(conn, metric_key: str) -> list[dict]:
    # One turn of the 24/7 loop, run after a fresh observation arrives: (1) score the
    # last un-scored forecast against the value that just came in -- the self-test --
    # then (2) forecast the next observation. The accumulating error is the curve.
    try:
        events: list[dict] = []
        latest = _latest_reading(conn, metric_key)
        if latest is None:
            return events
        actual_ts, actual = latest
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
        next_hour = (_hour(actual_ts) + 1) % 24
        predicted, support, method = forecast_value(conn, metric_key, next_hour)
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


def curve(conn, metric_key: str | None = None) -> dict:
    # The learning curve, read-time: is GENUS's forecast error shrinking over time?
    sql = (
        "SELECT json_extract(payload, '$.error') AS e FROM event_log "
        "WHERE event_type = 'forecast_scored'"
    )
    params: tuple = ()
    if metric_key is not None:
        sql += " AND json_extract(payload, '$.metric_key') = ?"
        params = (metric_key,)
    sql += " ORDER BY id"
    errors = [float(row["e"]) for row in conn.execute(sql, params).fetchall()]
    n = len(errors)
    if n == 0:
        return {
            "scored": 0,
            "mean_error": None,
            "early_mean_error": None,
            "recent_mean_error": None,
            "improving": None,
        }
    window = min(n, 20)
    early_mean = sum(errors[:window]) / window
    recent_mean = sum(errors[-window:]) / window
    return {
        "scored": n,
        "mean_error": sum(errors) / n,
        "early_mean_error": early_mean,
        "recent_mean_error": recent_mean,
        "improving": (recent_mean < early_mean) if n >= 2 else None,
    }
