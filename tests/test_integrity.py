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


def test_integrity_check_preserves_event_log(conn):
    for value in [92, 93, 94, 40, 41, 42]:
        observe_cpu_value(conn, value)
    before = integrity.snapshot_event_log(conn)

    result = integrity.check(conn)
    after = integrity.snapshot_event_log(conn)

    assert result["ok"] is True
    assert after == before


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
