import json

from genus import integrity, ledger
from tests.conftest import observe_cpu_value


def test_integrity_check_passes_after_observations(conn):
    for value in [92, 93, 94, 40, 41, 42]:
        observe_cpu_value(conn, value)

    result = integrity.check(conn)

    assert result["ok"] is True
    assert result["issues"] == []
    assert result["events"] > 0
    assert result["proposals"] == 2
    assert result["inquiries"] == 1


def test_integrity_check_preserves_event_log(conn):
    for value in [92, 93, 94, 40, 41, 42]:
        observe_cpu_value(conn, value)
    before = integrity.snapshot_event_log(conn)
    projection_before = integrity.snapshot_projections(conn)

    result = integrity.check(conn)
    after = integrity.snapshot_event_log(conn)
    projection_after = integrity.snapshot_projections(conn)

    assert result["ok"] is True
    assert after == before
    assert projection_after == projection_before


def test_integrity_check_detects_projection_drift_without_rebuilding_live_db(conn):
    for _ in range(3):
        observe_cpu_value(conn, 92.0)
    conn.execute(
        "UPDATE belief_projection SET derivation = ? WHERE claim_key = ?",
        ("manual:drift", "system.load"),
    )
    drifted_before = integrity.snapshot_projections(conn)

    result = integrity.check(conn)
    drifted_after = integrity.snapshot_projections(conn)

    assert result["ok"] is False
    assert "projection state changed after replay" in result["issues"]
    assert drifted_after == drifted_before


def test_integrity_check_rejects_known_broken_event(conn):
    payload = json.dumps({"manipuliert": True}, sort_keys=True, separators=(",", ":"))
    conn.execute(
        "INSERT INTO event_log (event_type, payload) VALUES (?, ?)",
        ("observation_created", payload),
    )

    result = integrity.check(conn)

    assert result["ok"] is False
    assert any(
        "observation_created missing keys" in issue
        for issue in result["issues"]
    )


def test_validate_event_contract_detects_missing_required_key(conn):
    ledger.append(conn, "observation_created", {"source": "mock", "unit": "percent"})

    issues = integrity.validate_event_contract(conn)

    assert any("missing keys: raw_value" in issue for issue in issues)


def test_validate_event_contract_detects_invalid_json(conn):
    conn.execute(
        "INSERT INTO event_log (event_type, payload) VALUES (?, ?)",
        ("observation_created", "{not-json"),
    )

    issues = integrity.validate_event_contract(conn)

    assert any("payload is not valid JSON" in issue for issue in issues)


def test_validate_event_contract_accepts_inquiry_created(conn):
    ledger.append(
        conn,
        "inquiry_created",
        {
            "inquiry_id": 1,
            "inquiry_type": "CauseInquiry",
            "claim_key": "system.load",
            "source_belief": 1,
            "source_event": 2,
            "question_key": "cause.changed_state",
            "payload": {"changed_from": "high", "changed_to": "normal"},
            "state": "open",
        },
    )

    issues = integrity.validate_event_contract(conn)

    assert issues == []


def test_validate_event_contract_accepts_experience_recorded(conn):
    ledger.append(
        conn,
        "experience_recorded",
        {
            "experience_id": 1,
            "experience_key": "activity_daily_rhythm:system.activity:active",
            "experience_type": "ActivityDailyRhythm",
            "subject_key": "system.activity",
            "pattern": {
                "hours_utc": [14],
                "value": "active",
                "count": 3,
            },
            "supporting_events": [1, 2, 3],
            "derivation": "rule:activity_daily_rhythm_v1",
            "summary": "system.activity is repeatedly active around 14:00 UTC",
        },
    )

    issues = integrity.validate_event_contract(conn)

    assert issues == []


def test_validate_event_contract_accepts_state_changed(conn):
    ledger.append(
        conn,
        "state_changed",
        {
            "state_id": 1,
            "state_key": "system.pressure",
            "state_value": "elevated",
            "previous_state_id": None,
            "derivation": "rule:system_pressure_state_v1",
            "supporting_beliefs": [1, 2],
            "components": {
                "system.activity": "active",
                "system.load": "high",
                "pressure_high_count": 1,
            },
            "reason": "active or unknown activity with high resource pressure",
        },
    )

    issues = integrity.validate_event_contract(conn)

    assert issues == []


def test_validate_schema_detects_confidence_column(conn):
    conn.execute("ALTER TABLE belief_projection ADD COLUMN confidence REAL")

    issues = integrity.validate_schema(conn)

    assert "belief_projection must not store confidence" in issues


def test_validate_schema_detects_empty_derivation(conn):
    conn.execute(
        """
        INSERT INTO belief_projection
            (claim_key, claim_value, state, derivation, supporting_events)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("system.load", "high", "active", "", json.dumps([1])),
    )

    issues = integrity.validate_schema(conn)

    assert "belief_projection contains empty derivation" in issues
