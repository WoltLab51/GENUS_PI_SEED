import sqlite3

from genus import event_router, integrity, rules
from genus.db import init_schema
from tests.conftest import observe_disk_value


def _observe_disk_series(conn, values):
    for value in values:
        observe_disk_value(conn, value)


def _fresh_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def test_high_disk_creates_belief(conn):
    for _ in range(3):
        observe_disk_value(conn, 90.0)

    row = conn.execute(
        """
        SELECT * FROM belief_projection
        WHERE claim_key = 'system.disk' AND claim_value = 'high'
        """
    ).fetchone()

    assert row["state"] == "active"


def test_low_after_high_disk_supersedes(conn):
    for _ in range(3):
        observe_disk_value(conn, 90.0)
    for _ in range(3):
        observe_disk_value(conn, 40.0)

    rows = conn.execute(
        "SELECT * FROM belief_projection WHERE claim_key = 'system.disk' ORDER BY id"
    ).fetchall()

    assert len(rows) == 2
    assert rows[0]["claim_value"] == "high"
    assert rows[0]["state"] == "superseded"
    assert rows[1]["claim_value"] == "normal"
    assert rows[1]["state"] == "active"


def test_disk_derivation_is_always_set(conn):
    for _ in range(3):
        observe_disk_value(conn, 90.0)

    row = conn.execute(
        "SELECT derivation FROM belief_projection WHERE claim_key = 'system.disk'"
    ).fetchone()

    assert row["derivation"] == rules.DISK_DERIVATION


def test_disk_thresholds_are_binding():
    assert rules.DISK_HIGH_THRESHOLD == 85.0
    assert rules.DISK_LOW_THRESHOLD == 60.0


def test_disk_trend_rising(conn):
    _observe_disk_series(conn, [50.0 + i for i in range(rules.TREND_WINDOW)])

    row = conn.execute(
        "SELECT * FROM belief_projection WHERE claim_key = 'disk.trend'"
    ).fetchone()
    assert row["claim_value"] == rules.TREND_RISING
    assert row["state"] == "active"
    assert row["derivation"] == rules.DISK_TREND_DERIVATION


def test_disk_trend_falling(conn):
    _observe_disk_series(conn, [73.0 - i for i in range(rules.TREND_WINDOW)])

    row = conn.execute(
        "SELECT * FROM belief_projection "
        "WHERE claim_key = 'disk.trend' AND state = 'active'"
    ).fetchone()
    assert row["claim_value"] == rules.TREND_FALLING


def test_disk_trend_stable_within_epsilon(conn):
    _observe_disk_series(conn, [50.0] * rules.TREND_WINDOW)

    row = conn.execute(
        "SELECT * FROM belief_projection WHERE claim_key = 'disk.trend'"
    ).fetchone()
    assert row["claim_value"] == rules.TREND_STABLE


def test_disk_trend_needs_full_window(conn):
    _observe_disk_series(conn, [50.0 + i for i in range(rules.TREND_WINDOW - 1)])

    row = conn.execute(
        "SELECT * FROM belief_projection WHERE claim_key = 'disk.trend'"
    ).fetchone()
    assert row is None


def test_disk_feeds_both_threshold_and_trend(conn):
    # Rising into high territory: the last three readings clear the high
    # threshold (system.disk=high) and the window's net change is positive
    # (disk.trend=rising). One metric, two beliefs, two epistemic forms.
    _observe_disk_series(conn, [70.0 + i for i in range(rules.TREND_WINDOW)])

    disk = conn.execute(
        "SELECT claim_value FROM belief_projection "
        "WHERE claim_key = 'system.disk' AND state = 'active'"
    ).fetchone()
    trend = conn.execute(
        "SELECT claim_value FROM belief_projection "
        "WHERE claim_key = 'disk.trend' AND state = 'active'"
    ).fetchone()
    assert disk["claim_value"] == "high"
    assert trend["claim_value"] == rules.TREND_RISING


def test_disk_trend_threshold_is_relative_to_own_scatter():
    # Same net change (+4) over the window, but a quiet disk calls it a rising
    # trend while a noisy disk calls it stable — the sensitivity is each core's
    # own scatter, never an imposed epsilon.
    quiet = _fresh_conn()
    noisy = _fresh_conn()
    _observe_disk_series(quiet, [50.0] + [50.0, 54.0] * 11 + [54.0])
    _observe_disk_series(noisy, [50.0] + [0.0, 100.0] * 11 + [54.0])

    quiet_belief = quiet.execute(
        "SELECT claim_value FROM belief_projection "
        "WHERE claim_key = 'disk.trend' AND state = 'active'"
    ).fetchone()
    noisy_belief = noisy.execute(
        "SELECT claim_value FROM belief_projection "
        "WHERE claim_key = 'disk.trend' AND state = 'active'"
    ).fetchone()
    quiet.close()
    noisy.close()

    assert quiet_belief["claim_value"] == rules.TREND_RISING
    assert noisy_belief["claim_value"] == rules.TREND_STABLE


def test_disk_trend_is_replay_stable_and_integrity_passes(conn):
    _observe_disk_series(conn, [70.0 + i for i in range(rules.TREND_WINDOW)])
    before = integrity.snapshot_projections(conn)

    event_router.replay(conn)
    after = integrity.snapshot_projections(conn)

    assert after == before
    assert integrity.check(conn)["ok"] is True
