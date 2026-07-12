import json
from datetime import datetime, timedelta, timezone

from genus.confidence import calculate_confidence
from genus import ledger, projection
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


def test_confidence_saturates_below_sticky_raw_count_ceiling():
    now = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
    supporting = evidence_series(now, count=100, spacing_seconds=300)

    confidence = calculate_confidence(supporting, [], "system.activity", now=now)

    assert 0.89 <= confidence <= 0.92
    assert confidence < 0.93


def test_fresh_contradiction_moves_saturated_belief():
    now = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
    supporting = evidence_series(now, count=100, spacing_seconds=300)

    confidence = calculate_confidence(
        supporting,
        [now],
        "system.activity",
        now=now,
    )

    assert 0.81 <= confidence <= 0.84


def test_old_evidence_decays_toward_low_confidence():
    now = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
    old_supporting = [
        now - timedelta(hours=6),
        now - timedelta(hours=7),
        now - timedelta(hours=8),
    ]

    confidence = calculate_confidence(old_supporting, [], "system.activity", now=now)

    assert confidence == 0.0


def test_projection_confidence_uses_each_evidence_timestamp(conn):
    now = datetime.now(timezone.utc)
    event_ids = []
    for age_days in [0, 1, 2]:
        event_ids.append(
            insert_evidence_event(
                conn,
                created_at=now - timedelta(days=age_days),
            )
        )
    belief_id = projection.create_belief(
        conn,
        "system.activity",
        "idle",
        "rule:activity_binary_v1",
        event_ids,
    )
    row = projection.get_belief(conn, belief_id)

    belief = projection.belief_with_confidence(conn, row)

    assert belief["supporting"] == 3
    assert belief["confidence"] < 0.55


def test_confidence_decreases_with_contradicting_evidence():
    now = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
    supporting = [now for _ in range(5)]
    contradicting = [now for _ in range(3)]
    high = calculate_confidence(supporting, [], "system.activity", now=now)
    lower = calculate_confidence(supporting, contradicting, "system.activity", now=now)

    assert lower < high


def test_belief_exposes_contested_epistemic_state_when_counterevidence_dominates(conn):
    supporting = ledger.append(
        conn, "evidence_recorded",
        {"metric_key": "system.load", "metric_value": 1.0, "source_observation": 1},
    )
    belief_id = projection.next_belief_id(conn)
    projection.apply_belief_created(conn, {
        "belief_id": belief_id,
        "claim_key": "system.load",
        "claim_value": "normal",
        "derivation": "test",
        "supporting_events": [supporting],
    })
    for value in (2.0, 3.0):
        evidence_id = ledger.append(
            conn, "evidence_recorded",
            {"metric_key": "system.load", "metric_value": value,
             "source_observation": int(value)},
        )
        projection.apply_belief_weakened(conn, {
            "belief_id": belief_id, "contradicting_event": evidence_id,
        })

    belief = projection.belief_with_confidence(conn, projection.get_belief(conn, belief_id))

    assert belief["confidence"] < 0.5
    assert belief["epistemic_state"] == projection.CONTESTED


def test_clock_shares_the_inert_disk_halflife():
    now = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
    # A few hours old: under network's 30-minute decay this is nearly gone,
    # but system.clock is inert and keeps its weight like system.disk.
    old_supporting = [now - timedelta(hours=3), now - timedelta(hours=4)]

    clock = calculate_confidence(old_supporting, [], "system.clock", now=now)
    disk = calculate_confidence(old_supporting, [], "system.disk", now=now)
    repo = calculate_confidence(old_supporting, [], "repo.activity", now=now)
    network = calculate_confidence(old_supporting, [], "system.network", now=now)

    churn = calculate_confidence(old_supporting, [], "repo.churn", now=now)
    disk_trend = calculate_confidence(old_supporting, [], "disk.trend", now=now)

    assert clock == disk      # same inert (one-day) class
    assert repo == disk       # commit rhythm is inert too
    assert churn == disk      # churn rhythm is inert too
    assert disk_trend == disk # disk trend is inert too
    assert clock > network    # network's 30-minute half-life decays faster


def test_confidence_is_not_stored(conn):
    columns = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(belief_projection)").fetchall()
    ]

    assert "confidence" not in columns


def evidence_series(
    now: datetime,
    count: int,
    spacing_seconds: int,
) -> list[datetime]:
    return [now - timedelta(seconds=spacing_seconds * i) for i in range(count)]


def insert_evidence_event(conn, created_at: datetime) -> int:
    payload = {
        "observation_id": 1,
        "metric_key": "system.activity",
        "metric_value": 0.0,
    }
    cur = conn.execute(
        """
        INSERT INTO event_log (event_type, payload, created_at)
        VALUES (?, ?, ?)
        """,
        (
            "evidence_recorded",
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            created_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        ),
    )
    return int(cur.lastrowid)


# --- Phase 0 der Ziel-Architektur: die EINE Belief-Zustandsmaschine -----------------


def test_belief_uebergang_erstellen_bestaetigen_abloesen(conn):
    # Vorher lebte diese Entscheidung dreimal wortgleich (rules._record_value_belief,
    # rules.apply_binary_rule, operation._record_operation_belief) -- jetzt einmal.
    r1 = projection.belief_uebergang(
        conn, claim_key="test.zustand", claim_value="ruhig",
        derivation="test_v1", supporting_events=[1],
    )
    assert (r1["event_type"], r1["fresh"]) == ("belief_created", True)

    r2 = projection.belief_uebergang(
        conn, claim_key="test.zustand", claim_value="ruhig",
        derivation="test_v1", supporting_events=[2],
    )
    assert (r2["event_type"], r2["fresh"]) == ("belief_confirmed", False)
    assert r2["belief_id"] == r1["belief_id"]

    r3 = projection.belief_uebergang(
        conn, claim_key="test.zustand", claim_value="unruhig",
        derivation="test_v1", supporting_events=[3],
    )
    assert (r3["event_type"], r3["fresh"]) == ("belief_superseded", True)
    assert r3["belief_id"] != r1["belief_id"]

    alt = projection.get_belief(conn, r1["belief_id"])
    assert alt["state"] == "superseded"
    aktiv = projection.active_belief(conn, "test.zustand")
    assert aktiv["claim_value"] == "unruhig"


def test_belief_uebergang_abloese_grund_traegt_reason_key(conn):
    # Der Binary-Pfad nennt historisch den metric_key im Ablöse-Grund, nicht den
    # claim_key -- verhalten-erhaltend als Parameter beibehalten.
    projection.belief_uebergang(
        conn, claim_key="test.claim", claim_value="an",
        derivation="test_v1", supporting_events=[1],
    )
    projection.belief_uebergang(
        conn, claim_key="test.claim", claim_value="aus",
        derivation="test_v1", supporting_events=[2], reason_key="test.metrik",
    )
    row = conn.execute(
        "SELECT payload FROM event_log WHERE event_type = 'belief_superseded' "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert json.loads(row["payload"])["reason"] == "test.metrik_changed_to_aus"
