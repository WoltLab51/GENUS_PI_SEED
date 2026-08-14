from __future__ import annotations

import hashlib
import importlib.util
import os
import sqlite3
from pathlib import Path

import pytest
from click.testing import CliRunner

from genus import cli, db, schema_detection, startup


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


def _create_near_miss_database(path: Path) -> None:
    _create_current_database(path)
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE INDEX idx_a0_1b_near_miss ON event_log(id)")
        conn.commit()
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


def _event_count(path: Path) -> int:
    conn = db.connect_readonly(path)
    try:
        return int(conn.execute("SELECT COUNT(*) FROM event_log").fetchone()[0])
    finally:
        conn.close()


def _forbid_writable_initialization(monkeypatch) -> dict[str, int]:
    calls = {"connect": 0, "init_schema": 0}

    def forbidden_connect(*_args, **_kwargs):
        calls["connect"] += 1
        raise AssertionError("db.connect must remain unreachable behind a rejected gate")

    def forbidden_init_schema(*_args, **_kwargs):
        calls["init_schema"] += 1
        raise AssertionError("init_schema must remain unreachable behind a rejected gate")

    monkeypatch.setattr(db, "connect", forbidden_connect)
    monkeypatch.setattr(db, "init_schema", forbidden_init_schema)
    return calls


def test_current_schema_promotes_the_detected_connection_without_reopening(
    monkeypatch, tmp_path
):
    path = tmp_path / "current.sqlite3"
    _create_current_database(path)
    original_detect = schema_detection.detect_schema
    original_init_schema = db.init_schema
    original_sqlite_connect = sqlite3.connect
    seen: dict[str, sqlite3.Connection | int] = {}
    sqlite_connect_calls: list[tuple[object, bool]] = []

    def observed_sqlite_connect(database, *args, **kwargs):
        sqlite_connect_calls.append((database, bool(kwargs.get("uri"))))
        return original_sqlite_connect(database, *args, **kwargs)

    def observed_detect(conn):
        seen["detected"] = conn
        seen["query_only_during_detection"] = int(
            conn.execute("PRAGMA query_only").fetchone()[0]
        )
        return original_detect(conn)

    def observed_init_schema(conn):
        seen["initialized"] = conn
        seen["query_only_during_initialization"] = int(
            conn.execute("PRAGMA query_only").fetchone()[0]
        )
        return original_init_schema(conn)

    def forbidden_reopen(*_args, **_kwargs):
        raise AssertionError("the checked database must never be reopened by path")

    monkeypatch.setattr(schema_detection, "detect_schema", observed_detect)
    monkeypatch.setattr(db, "init_schema", observed_init_schema)
    monkeypatch.setattr(db, "connect", forbidden_reopen)
    monkeypatch.setattr(startup.sqlite3, "connect", observed_sqlite_connect)

    conn = startup.connect(path)
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_schema WHERE type = 'table'"
        ).fetchone()[0] > 0
        assert conn.row_factory is sqlite3.Row
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        conn.close()

    assert seen["detected"] is conn
    assert seen["initialized"] is conn
    assert seen["query_only_during_detection"] == 1
    assert seen["query_only_during_initialization"] == 0
    assert len(sqlite_connect_calls) == 1
    assert sqlite_connect_calls[0][1] is True
    assert "mode=rw" in str(sqlite_connect_calls[0][0])


def test_old_reopen_swap_seam_is_unreachable_and_unknown_database_is_untouched(
    monkeypatch, tmp_path
):
    current_path = tmp_path / "current.sqlite3"
    unknown_path = tmp_path / "unknown.sqlite3"
    displaced_path = tmp_path / "displaced-current.sqlite3"
    _create_current_database(current_path)
    _create_unknown_database(unknown_path)
    unknown_before = _snapshot(unknown_path)
    attack_calls = 0

    def swap_at_the_old_reopen_seam(configured_path):
        nonlocal attack_calls
        attack_calls += 1
        os.replace(current_path, displaced_path)
        os.replace(unknown_path, current_path)
        raise AssertionError(f"unchecked database reopened at {configured_path}")

    monkeypatch.setattr(db, "connect", swap_at_the_old_reopen_seam)

    conn = startup.connect(current_path)
    try:
        assert conn.execute("PRAGMA query_only").fetchone()[0] == 0
    finally:
        conn.close()

    assert attack_calls == 0
    assert not displaced_path.exists()
    assert _snapshot(unknown_path) == unknown_before
    assert unknown_before[3] == (False, False, False)


@pytest.mark.parametrize(
    ("kind", "expected_error", "expected_message"),
    [
        (
            "historical",
            startup.StartupMigrationRequiredError,
            "Migration erforderlich",
        ),
        ("unknown", startup.StartupUnknownSchemaError, "unbekanntes Schema"),
        ("near-miss", startup.StartupUnknownSchemaError, "unbekanntes Schema"),
    ],
)
def test_rejected_schema_never_reaches_writable_initialization_and_stays_unchanged(
    monkeypatch,
    tmp_path,
    kind,
    expected_error,
    expected_message,
):
    if kind == "historical":
        path = HISTORICAL_DATABASE_PATH
    else:
        path = tmp_path / f"{kind}.sqlite3"
        if kind == "unknown":
            _create_unknown_database(path)
        else:
            _create_near_miss_database(path)

    before = _snapshot(path)
    before_event_count = _event_count(path) if kind != "unknown" else None
    calls = _forbid_writable_initialization(monkeypatch)

    with pytest.raises(expected_error, match=expected_message):
        startup.connect(path)

    assert calls == {"connect": 0, "init_schema": 0}
    assert _snapshot(path) == before
    assert before[3] == (False, False, False)
    if before_event_count is not None:
        assert _event_count(path) == before_event_count


def test_missing_database_is_not_created_and_never_reaches_writable_initialization(
    monkeypatch, tmp_path
):
    path = tmp_path / "missing.sqlite3"
    calls = _forbid_writable_initialization(monkeypatch)

    with pytest.raises(startup.StartupDatabaseMissingError, match="Datenbank fehlt"):
        startup.connect(path)

    assert calls == {"connect": 0, "init_schema": 0}
    assert not path.exists()
    assert all(
        not Path(f"{path}{suffix}").exists() for suffix in SQLITE_SIDECAR_SUFFIXES
    )


def test_cli_write_command_uses_the_same_gate_and_fails_before_connect(
    monkeypatch, tmp_path
):
    path = tmp_path / "unknown.sqlite3"
    _create_unknown_database(path)
    before = _snapshot(path)
    monkeypatch.setenv("GENUS_DB_PATH", str(path))
    calls = _forbid_writable_initialization(monkeypatch)

    result = CliRunner().invoke(cli.main, ["replay"])

    assert result.exit_code == 1
    assert "unbekanntes Schema" in result.output
    assert calls == {"connect": 0, "init_schema": 0}
    assert _snapshot(path) == before


def test_db_status_remains_read_only_and_bypasses_the_writable_startup_gate(
    monkeypatch, tmp_path
):
    path = tmp_path / "current.sqlite3"
    _create_current_database(path)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("db status must not use the writable startup gate")

    monkeypatch.setattr(startup, "connect", forbidden)

    result = CliRunner().invoke(cli.main, ["db", "status", "--path", str(path)])

    assert result.exit_code == 0
    assert "Schema status: current" in result.output
    assert "Database modified: no" in result.output


def test_productive_status_service_uses_the_shared_gate(monkeypatch, tmp_path):
    script = ROOT / "deploy" / "export_pi_status.py"
    spec = importlib.util.spec_from_file_location("a0_1b_export_pi_status", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    path = tmp_path / "configured.sqlite3"
    output = tmp_path / "status.json"
    calls: list[str] = []

    class GateReached(RuntimeError):
        pass

    def observed_gate(configured_path):
        calls.append(str(configured_path))
        raise GateReached

    monkeypatch.setenv("GENUS_CORE_ID", "test-core")
    monkeypatch.setenv("GENUS_DB_PATH", str(path))
    monkeypatch.setattr(module.startup, "connect", observed_gate)
    monkeypatch.setattr("sys.argv", ["export_pi_status.py", str(output)])

    with pytest.raises(GateReached):
        module.main()

    assert calls == [str(path)]
    assert not path.exists()
    assert not output.exists()


def test_all_direct_normal_file_backed_entrypoints_use_the_shared_gate():
    entrypoints = (
        "deploy/chat_word_learning.py",
        "deploy/export_pi_status.py",
        "deploy/gleiche_ziele_ab.sh",
        "deploy/hand_ausfuehren.sh",
        "deploy/migriere_notizen.sh",
        "deploy/morgen_push.sh",
        "deploy/nacht_konsolidierung.sh",
        "deploy/saet_persoenlichkeit.sh",
        "deploy/seed_orte.sh",
        "deploy/seed_verstehen.sh",
        "deploy/seed_ziele.sh",
        "deploy/telegram_bot.py",
    )

    for relative_path in entrypoints:
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "startup.connect(" in source, relative_path
        assert "db.connect(" not in source, relative_path


def test_backfill_presence_query_is_read_only_and_cannot_create_a_database():
    source = (ROOT / "deploy" / "backfill_gender.sh").read_text(encoding="utf-8")

    assert "db.connect_readonly(" in source
    assert "sqlite3.connect(" not in source


def test_exact_detection_semantics_remain_owned_by_a0_1a(tmp_path):
    path = tmp_path / "current.sqlite3"
    _create_current_database(path)
    conn = db.connect_readonly(path)
    try:
        result = schema_detection.detect_schema(conn)
    finally:
        conn.close()

    assert result.status == "current"
    assert result.fingerprint == schema_detection.CURRENT_SCHEMA_FINGERPRINT
