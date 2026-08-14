"""A0.2 accepted historical SQLite fixture.

The original binary is read-only evidence. Any write attempt uses a disposable
copy, and rebuilding creates a separate temporary database from the checked-in
historical schema rather than current runtime initialization.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from genus import db
from tests import historical_sqlite_support as historical


EXPECTED_FILES = {
    ".gitattributes",
    ".gitignore",
    "events.jsonl",
    "HUMAN_REVIEW.md",
    "legacy_v1.sqlite3",
    "manifest.json",
    "README.md",
    "schema.sql",
}
EXPECTED_TABLES = {
    "belief_projection",
    "event_log",
    "experience_log",
    "governance_log",
    "inquiry_log",
    "proposal_log",
    "rule_projection",
    "state_projection",
}
EXPECTED_CURRENT_MISSING_TABLES = {
    "operation_log",
    "relation_projection",
    "response_feedback_log",
    "response_outcome_log",
    "value_projection",
}
EXPECTED_CURRENT_MISSING_INDEXES = {
    "idx_event_log_metric",
    "idx_operation_log_check",
    "idx_relation_object",
    "idx_relation_predicate",
    "idx_relation_subject",
    "idx_response_feedback_response",
    "idx_response_outcome_channel_created",
    "idx_value_claim",
    "idx_value_source",
}


@pytest.fixture(autouse=True)
def original_fixture_is_immutable():
    before_bytes = historical.DATABASE_PATH.read_bytes()
    before_mtime = historical.DATABASE_PATH.stat().st_mtime_ns
    historical.assert_no_sidecars(historical.DATABASE_PATH)

    yield

    assert historical.DATABASE_PATH.read_bytes() == before_bytes
    assert historical.DATABASE_PATH.stat().st_mtime_ns == before_mtime
    historical.assert_no_sidecars(historical.DATABASE_PATH)


def _open_inventory(path: Path) -> dict:
    conn = db.connect_readonly(path)
    try:
        return historical.schema_inventory(conn)
    finally:
        conn.close()


def _manifest_inventory(inventory: dict) -> dict:
    return {
        "indexes": inventory["indexes"],
        "tables": {
            name: [column["name"] for column in columns]
            for name, columns in inventory["tables"].items()
        },
        "triggers": inventory["triggers"],
    }


def _projection_rows(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, claim_key, claim_value, state, derivation,
               supporting_events, contradicting_events, created_at,
               last_updated_at, superseded_by
        FROM belief_projection
        ORDER BY id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def test_accepted_inventory_and_human_gate_are_exact():
    assert {path.name for path in historical.FIXTURE_ROOT.iterdir()} == EXPECTED_FILES

    manifest = historical.load_manifest()
    assert manifest["fixture_schema"] == historical.FIXTURE_SCHEMA
    assert manifest["format_version"] == 1
    assert manifest["status"] == historical.STATUS
    assert manifest["human_review"] == {
        "decision": "accept",
        "review_date": "2026-08-14",
        "reviewer": "Ronny",
    }

    review = historical.REVIEW_PATH.read_text(encoding="utf-8")
    assert "Status: **ACCEPTED**" in review
    checked_boxes = [line for line in review.splitlines() if line.startswith("- [x]")]
    assert checked_boxes == ["- [x] Accept candidate"]
    open_boxes = [line for line in review.splitlines() if line.startswith("- [ ]")]
    assert len(open_boxes) == 21
    assert open_boxes[-2:] == [
        "- [ ] Reject candidate",
        "- [ ] Request changes",
    ]


def test_manifest_binds_historical_source_and_actual_file_bytes():
    manifest = historical.load_manifest()
    assert manifest["source"] == {
        "commit": historical.SOURCE_COMMIT,
        "commit_date": historical.SOURCE_COMMIT_DATE,
        "commit_message": historical.SOURCE_COMMIT_MESSAGE,
        "repository": "WoltLab51/GENUS_PI_SEED",
        "schema_path": "schema.sql",
    }
    assert historical.DATABASE_PATH.read_bytes()[:16] == b"SQLite format 3\x00"

    digests = manifest["digests"]
    assert digests["schema_sql_sha256"] == historical.SOURCE_SCHEMA_SHA256
    assert digests["schema_sql_sha256"] == historical.sha256_bytes(
        historical.SCHEMA_PATH.read_bytes()
    )
    assert digests["sqlite_sha256"] == historical.sha256_bytes(
        historical.DATABASE_PATH.read_bytes()
    )
    assert digests["events_jsonl_sha256"] == historical.sha256_bytes(
        historical.EVENTS_PATH.read_bytes()
    )


def test_schema_inventory_fingerprint_and_current_differences_are_independent():
    manifest = historical.load_manifest()
    historical_inventory = _open_inventory(historical.DATABASE_PATH)
    assert set(historical_inventory["tables"]) == EXPECTED_TABLES
    assert manifest["inventory"] == _manifest_inventory(historical_inventory)
    assert manifest["digests"]["schema_fingerprint_sha256"] == (
        historical.schema_fingerprint_sha256(historical_inventory)
    )

    current_schema_bytes = db.SCHEMA_PATH.read_bytes()
    current_schema_lf = current_schema_bytes.replace(b"\r\n", b"\n")
    comparison = manifest["current_schema_comparison"]
    assert comparison["current_commit"] == "0f6074707642d0b58543f122fbae18ff44a46ff6"
    assert comparison["current_schema_sha256_domain"] == "repository text normalized to LF"
    assert historical.sha256_bytes(current_schema_lf) == historical.CURRENT_SCHEMA_SHA256
    current = sqlite3.connect(":memory:")
    current.row_factory = sqlite3.Row
    try:
        current.executescript(current_schema_lf.decode("utf-8"))
        current_inventory = historical.schema_inventory(current)
    finally:
        current.close()

    missing_tables = set(current_inventory["tables"]) - set(historical_inventory["tables"])
    historical_indexes = {item["name"] for item in historical_inventory["indexes"]}
    current_indexes = {item["name"] for item in current_inventory["indexes"]}
    missing_indexes = current_indexes - historical_indexes
    assert missing_tables == EXPECTED_CURRENT_MISSING_TABLES
    assert missing_indexes == EXPECTED_CURRENT_MISSING_INDEXES
    assert set(manifest["current_schema_comparison"]["missing_tables"]) == missing_tables
    assert set(manifest["current_schema_comparison"]["missing_indexes"]) == missing_indexes
    assert manifest["current_schema_comparison"]["missing_event_log_columns"] == []


def test_readonly_connection_exports_exact_bound_event_stream_without_migration():
    events = historical.load_events()
    manifest = historical.load_manifest()
    before = historical.DATABASE_PATH.read_bytes()

    conn = db.connect_readonly(historical.DATABASE_PATH)
    try:
        assert conn.execute("PRAGMA query_only").fetchone()[0] == 1
        assert set(historical.schema_inventory(conn)["tables"]) == EXPECTED_TABLES
        exported = historical.export_events(conn)
    finally:
        conn.close()

    assert exported == events
    assert historical.event_stream_sha256(exported) == historical.event_stream_sha256(events)
    assert historical.event_stream_sha256(exported) == manifest["digests"][
        "event_stream_sha256"
    ]
    assert historical.DATABASE_PATH.read_bytes() == before


def test_synthetic_event_chain_and_projection_row_are_exact():
    events = historical.load_events()
    assert [event["id"] for event in events] == list(range(1, 8))
    assert [event["event_type"] for event in events] == [
        "observation_created",
        "evidence_recorded",
        "belief_created",
        "ledger_epoch_opened",
        "observation_created",
        "evidence_recorded",
        "belief_confirmed",
    ]
    assert all(event["prev_seal"] is None and event["seal"] is None for event in events[:3])
    seals = historical.verify_seal_chain(events)
    assert seals == {
        "genesis_digest": "d8e173efb82a4a2628467f214250ddaf3e4168162878f8d25a8bfd5f8896f6f6",
        "head_seal": "a8bfc218e11b190dc48e7b4cd20c99df416623110addce3a8ca93fd1fbee07d2",
    }

    conn = db.connect_readonly(historical.DATABASE_PATH)
    try:
        assert _projection_rows(conn) == [
            {
                "id": 1,
                "claim_key": "synthetic.temperature",
                "claim_value": "nominal",
                "state": "active",
                "derivation": "fixture:legacy-v1",
                "supporting_events": "[1,2,6]",
                "contradicting_events": "[]",
                "created_at": events[2]["created_at"],
                "last_updated_at": events[6]["created_at"],
                "superseded_by": None,
            }
        ]
    finally:
        conn.close()


def test_database_rebuild_uses_only_historical_schema_and_is_logically_identical(tmp_path):
    rebuilt = tmp_path / "rebuilt.sqlite3"
    events = historical.load_events()
    historical.build_database(
        rebuilt,
        schema_bytes=historical.SCHEMA_PATH.read_bytes(),
        events=events,
    )

    original = db.connect_readonly(historical.DATABASE_PATH)
    candidate = db.connect_readonly(rebuilt)
    try:
        assert historical.schema_inventory(candidate) == historical.schema_inventory(original)
        assert historical.database_pragmas(candidate) == historical.database_pragmas(original)
        assert historical.export_events(candidate) == historical.export_events(original)
        assert _projection_rows(candidate) == _projection_rows(original)
    finally:
        candidate.close()
        original.close()
    historical.assert_no_sidecars(rebuilt)


def test_write_attempt_uses_copy_and_readonly_mode_rejects_it(tmp_path):
    copied = tmp_path / "readonly-copy.sqlite3"
    shutil.copy2(historical.DATABASE_PATH, copied)
    before = copied.read_bytes()

    conn = db.connect_readonly(copied)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute(
                "INSERT INTO event_log (event_type, payload) VALUES (?, ?)",
                ("observation_created", "{}"),
            )
    finally:
        conn.close()

    assert copied.read_bytes() == before
    historical.assert_no_sidecars(copied)


@pytest.mark.parametrize("statement", ["UPDATE event_log SET payload = '{}' WHERE id = 1", "DELETE FROM event_log WHERE id = 1"])
def test_historical_append_only_triggers_are_checked_only_on_copy(tmp_path, statement):
    copied = tmp_path / "trigger-copy.sqlite3"
    shutil.copy2(historical.DATABASE_PATH, copied)
    before = copied.read_bytes()

    conn = sqlite3.connect(copied)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute(statement)
        conn.rollback()
    finally:
        conn.close()

    assert copied.read_bytes() == before
    historical.assert_no_sidecars(copied)


def test_database_content_is_synthetic_and_contains_no_product_identifiers():
    events = historical.load_events()
    serialized_events = json.dumps(events, ensure_ascii=False, sort_keys=True).lower()
    banned = (
        "ronny",
        "telegram",
        "woltlab",
        "hostname",
        "device_id",
        "chat_id",
        "token",
        "/home/",
        "c:\\\\users\\\\",
    )
    assert all(value not in serialized_events for value in banned)

    conn = db.connect_readonly(historical.DATABASE_PATH)
    try:
        database_values = [
            str(value).lower()
            for row in conn.execute(
                """
                SELECT event_type, payload, created_at, prev_seal, seal
                FROM event_log
                UNION ALL
                SELECT claim_key, claim_value, state, derivation, supporting_events
                FROM belief_projection
                """
            )
            for value in row
            if value is not None
        ]
    finally:
        conn.close()
    assert all(banned_value not in value for value in database_values for banned_value in banned)
