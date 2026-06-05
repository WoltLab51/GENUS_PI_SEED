from genus.confidence import calculate_confidence
from tests.conftest import observe_cpu_value


def test_high_cpu_creates_belief(conn):
    for _ in range(3):
        observe_cpu_value(conn, 92.0)

    row = conn.execute(
        "SELECT * FROM belief_projection WHERE claim_key = 'system.load' AND claim_value = 'high'"
    ).fetchone()

    assert row["state"] == "active"


def test_low_after_high_supersedes_belief(conn):
    for _ in range(3):
        observe_cpu_value(conn, 92.0)
    old = conn.execute(
        "SELECT * FROM belief_projection WHERE claim_value = 'high'"
    ).fetchone()

    for _ in range(3):
        observe_cpu_value(conn, 40.0)

    old_after = conn.execute(
        "SELECT * FROM belief_projection WHERE id = ?",
        (old["id"],),
    ).fetchone()
    new = conn.execute(
        "SELECT * FROM belief_projection WHERE claim_value = 'normal'"
    ).fetchone()

    assert old_after["state"] == "superseded"
    assert new["state"] == "active"
    assert old_after["superseded_by"] == new["id"]


def test_superseded_belief_is_not_deleted(conn):
    for _ in range(3):
        observe_cpu_value(conn, 92.0)
    old_id = conn.execute("SELECT id FROM belief_projection").fetchone()["id"]
    for _ in range(3):
        observe_cpu_value(conn, 40.0)

    row = conn.execute("SELECT * FROM belief_projection WHERE id = ?", (old_id,)).fetchone()

    assert row is not None
    assert row["state"] == "superseded"


def test_confidence_decreases_with_contradicting_evidence():
    high = calculate_confidence(5, 0, 0)
    lower = calculate_confidence(5, 3, 0)

    assert lower < high


def test_confidence_is_not_stored(conn):
    columns = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(belief_projection)").fetchall()
    ]

    assert "confidence" not in columns
