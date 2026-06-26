import sqlite3

from genus import ledger, rules
from genus.db import init_schema


def _fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def test_prior_distribution_is_bounded_to_recent_values(monkeypatch):
    monkeypatch.setattr(rules, "CALIBRATION_WINDOW", 5)
    conn = _fresh()
    for value in range(20):  # values 0..19, ids 1..20
        ledger.append(
            conn,
            "evidence_recorded",
            {"observation_id": 0, "metric_key": "m", "metric_value": float(value)},
        )
    conn.commit()

    dist = rules._prior_distribution(conn, "m", before_event_id=9999)

    # only the most recent CALIBRATION_WINDOW values, sorted
    assert dist == [15.0, 16.0, 17.0, 18.0, 19.0]
    conn.close()


def test_prior_distribution_stays_causal(monkeypatch):
    monkeypatch.setattr(rules, "CALIBRATION_WINDOW", 100)
    conn = _fresh()
    for value in range(10):
        ledger.append(
            conn,
            "evidence_recorded",
            {"observation_id": 0, "metric_key": "m", "metric_value": float(value)},
        )
    conn.commit()

    # only events with id < 4 (values 0,1,2) count
    dist = rules._prior_distribution(conn, "m", before_event_id=4)

    assert dist == [0.0, 1.0, 2.0]
    conn.close()
