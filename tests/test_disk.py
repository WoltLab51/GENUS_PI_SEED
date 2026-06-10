from genus import rules
from tests.conftest import observe_disk_value


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
