from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path

import pytest
from click.testing import CliRunner

from genus import cli, db, schema_detection
from tests import historical_sqlite_support as historical


ROOT = Path(__file__).parents[1]
CURRENT_SCHEMA_PATH = ROOT / "schema.sql"
HISTORICAL_DATABASE_PATH = (
    ROOT / "tests" / "fixtures" / "historical_sqlite_v1" / "legacy_v1.sqlite3"
)
SQLITE_SIDECAR_SUFFIXES = ("-journal", "-shm", "-wal")


def _create_current_database(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(CURRENT_SCHEMA_PATH.read_text(encoding="utf-8"))
    finally:
        conn.close()


def _create_unknown_database(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE foreign_data (id INTEGER PRIMARY KEY, value TEXT)")
        conn.commit()
    finally:
        conn.close()


def _detect(path: Path) -> schema_detection.SchemaDetection:
    conn = db.connect_readonly(path)
    try:
        return schema_detection.detect_schema(conn)
    finally:
        conn.close()


def _snapshot(path: Path) -> tuple[str, int, int, tuple[bool, ...]]:
    stat = path.stat()
    return (
        hashlib.sha256(path.read_bytes()).hexdigest(),
        stat.st_size,
        stat.st_mtime_ns,
        tuple(Path(f"{path}{suffix}").exists() for suffix in SQLITE_SIDECAR_SUFFIXES),
    )


def _accepted_fixture_fingerprint(path: Path) -> str:
    conn = db.connect_readonly(path)
    try:
        return historical.schema_fingerprint_sha256(historical.schema_inventory(conn))
    finally:
        conn.close()


def test_detects_current_schema_from_committed_schema_sql(tmp_path):
    path = tmp_path / "current.sqlite3"
    _create_current_database(path)

    result = _detect(path)

    assert result == schema_detection.SchemaDetection(
        status="current",
        schema_id="current",
        fingerprint=schema_detection.CURRENT_SCHEMA_FINGERPRINT,
        current=True,
        migration_required=False,
    )
    assert result.fingerprint == _accepted_fixture_fingerprint(path)
    assert result.fingerprint == (
        "2d7e1497bba0a34e141e821b2cd15f8ab71f571454da84f1b128844fcce493ab"
    )


def test_detects_accepted_historical_v1_1_fixture_without_modifying_it():
    before = _snapshot(HISTORICAL_DATABASE_PATH)

    result = _detect(HISTORICAL_DATABASE_PATH)

    assert result == schema_detection.SchemaDetection(
        status="historical",
        schema_id="historical-v1.1",
        fingerprint=schema_detection.HISTORICAL_V1_1_SCHEMA_FINGERPRINT,
        current=False,
        migration_required=True,
    )
    assert result.fingerprint == _accepted_fixture_fingerprint(
        HISTORICAL_DATABASE_PATH
    )
    assert result.fingerprint == (
        "e73837d56217169b1365a75ca404d6512ff7c9655d3e5dc993ba12b368d446a3"
    )
    assert _snapshot(HISTORICAL_DATABASE_PATH) == before


def test_unknown_schema_is_fail_closed(tmp_path):
    path = tmp_path / "unknown.sqlite3"
    _create_unknown_database(path)

    result = _detect(path)

    assert result.status == "unknown"
    assert result.schema_id is None
    assert len(result.fingerprint) == 64
    assert result.current is False
    assert result.migration_required is None


def test_one_extra_index_is_an_unknown_near_miss(tmp_path):
    path = tmp_path / "near-miss.sqlite3"
    _create_current_database(path)
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE INDEX idx_a0_1a_near_miss ON event_log(id)")
        conn.commit()
    finally:
        conn.close()

    result = _detect(path)

    assert result.status == "unknown"
    assert result.fingerprint not in {
        schema_detection.CURRENT_SCHEMA_FINGERPRINT,
        schema_detection.HISTORICAL_V1_1_SCHEMA_FINGERPRINT,
    }


def test_detection_requires_the_connect_readonly_boundary(tmp_path):
    path = tmp_path / "writable.sqlite3"
    _create_current_database(path)
    conn = sqlite3.connect(path)
    try:
        with pytest.raises(
            schema_detection.SchemaDetectionError,
            match="connect_readonly",
        ):
            schema_detection.detect_schema(conn)
    finally:
        conn.close()


def test_detection_executes_only_select_and_pragma(tmp_path):
    path = tmp_path / "traced.sqlite3"
    _create_current_database(path)
    conn = db.connect_readonly(path)
    statements: list[str] = []
    conn.set_trace_callback(statements.append)
    try:
        schema_detection.detect_schema(conn)
    finally:
        conn.close()

    assert statements
    assert all(
        statement.lstrip().upper().startswith(("SELECT ", "PRAGMA "))
        for statement in statements
    )


@pytest.mark.parametrize("kind", ["current", "historical", "unknown"])
def test_detection_preserves_bytes_size_mtime_and_sidecars(tmp_path, kind):
    if kind == "historical":
        path = HISTORICAL_DATABASE_PATH
    else:
        path = tmp_path / f"{kind}.sqlite3"
        if kind == "current":
            _create_current_database(path)
        else:
            _create_unknown_database(path)

    assert os.access(path, os.W_OK), "test process must have write access to the DB"
    before = _snapshot(path)

    _detect(path)

    assert _snapshot(path) == before
    assert before[3] == (False, False, False)


@pytest.mark.parametrize(
    ("kind", "expected_exit", "expected_lines"),
    [
        (
            "current",
            0,
            [
                "Schema status: current",
                "Schema id: current",
                f"Schema fingerprint: {schema_detection.CURRENT_SCHEMA_FINGERPRINT}",
                "Current schema: yes",
                "Migration required: no",
                "Database modified: no",
            ],
        ),
        (
            "historical",
            2,
            [
                "Schema status: historical",
                "Schema id: historical-v1.1",
                "Schema fingerprint: "
                f"{schema_detection.HISTORICAL_V1_1_SCHEMA_FINGERPRINT}",
                "Current schema: no",
                "Migration required: yes",
                "Database modified: no",
            ],
        ),
        (
            "unknown",
            3,
            None,
        ),
    ],
)
def test_db_status_cli_reports_classification_and_exit_code(
    tmp_path, kind, expected_exit, expected_lines
):
    if kind == "historical":
        path = HISTORICAL_DATABASE_PATH
    else:
        path = tmp_path / f"{kind}.sqlite3"
        if kind == "current":
            _create_current_database(path)
        else:
            _create_unknown_database(path)
    before = _snapshot(path)

    result = CliRunner().invoke(cli.main, ["db", "status", "--path", str(path)])

    assert result.exit_code == expected_exit
    lines = result.output.splitlines()
    if expected_lines is None:
        assert lines == [
            "Schema status: unknown",
            "Schema id: unknown",
            f"Schema fingerprint: {_detect(path).fingerprint}",
            "Current schema: no",
            "Migration required: unknown",
            "Database modified: no",
        ]
    else:
        assert lines == expected_lines
    assert _snapshot(path) == before


def test_db_status_cli_uses_env_path_and_never_calls_writable_connect(
    monkeypatch, tmp_path
):
    path = tmp_path / "current.sqlite3"
    _create_current_database(path)
    monkeypatch.setenv("GENUS_DB_PATH", str(path))

    def forbidden(*_args, **_kwargs):
        raise AssertionError("writable initialization path was called")

    monkeypatch.setattr(db, "connect", forbidden)
    monkeypatch.setattr(db, "init_schema", forbidden)

    result = CliRunner().invoke(cli.main, ["db", "status"])

    assert result.exit_code == 0
    assert "Schema status: current" in result.output


def test_db_status_missing_path_is_an_error_and_creates_nothing(tmp_path):
    path = tmp_path / "missing.sqlite3"

    result = CliRunner().invoke(
        cli.main,
        ["db", "status", "--path", str(path)],
    )

    assert result.exit_code == 1
    assert "database does not exist" in result.output
    assert not path.exists()
    assert all(
        not Path(f"{path}{suffix}").exists() for suffix in SQLITE_SIDECAR_SUFFIXES
    )
