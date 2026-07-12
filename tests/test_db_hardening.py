import sqlite3

import pytest
from click.testing import CliRunner

from genus import cli, db


def test_file_db_enables_wal_busy_timeout_and_metric_index(tmp_path):
    conn = db.connect(str(tmp_path / "genus.sqlite3"))
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        indexes = {row["name"] for row in conn.execute("PRAGMA index_list(event_log)")}
        assert "idx_event_log_metric" in indexes
    finally:
        conn.close()


# --- Streu-DB-Schutz (Fund 2026-07-04): nie mehr LAUTLOS eine neue Datenbank ----------


def test_neue_datenbank_wird_laut_angelegt(tmp_path, capsys):
    from genus import db

    pfad = tmp_path / "frisch.sqlite3"
    conn = db.connect(pfad)
    conn.close()
    assert "NEU angelegt" in capsys.readouterr().err


def test_bestehende_datenbank_bleibt_still(tmp_path, capsys):
    from genus import db

    pfad = tmp_path / "bestehend.sqlite3"
    db.connect(pfad).close()
    capsys.readouterr()   # die Anlage-Warnung verwerfen
    db.connect(pfad).close()
    assert "NEU angelegt" not in capsys.readouterr().err


def test_memory_datenbank_bleibt_still(capsys):
    from genus import db

    db.connect(":memory:").close()
    assert "NEU angelegt" not in capsys.readouterr().err


def test_readonly_connection_requires_existing_database_and_creates_nothing(tmp_path):
    path = tmp_path / "missing.sqlite3"

    with pytest.raises(db.DatabaseNotFoundError, match="does not exist"):
        db.connect_readonly(path)

    assert not path.exists()


def test_readonly_connection_cannot_write_or_migrate(tmp_path):
    path = tmp_path / "existing.sqlite3"
    db.connect(path).close()
    before = path.stat()

    conn = db.connect_readonly(path)
    try:
        assert conn.execute("PRAGMA query_only").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute(
                "INSERT INTO event_log (event_type, payload) VALUES (?, ?)",
                ("observation_created", "{}"),
            )
    finally:
        conn.close()

    after = path.stat()
    assert after.st_size == before.st_size
    assert after.st_mtime_ns == before.st_mtime_ns


def test_ledger_metrics_report_physical_size_and_recent_growth(conn):
    conn.execute(
        """
        INSERT INTO event_log (event_type, payload, created_at)
        VALUES ('observation_created', '{}', strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
               ('observation_created', '{}', strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-2 days')),
               ('observation_created', '{}', strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-10 days'))
        """
    )

    metrics = db.ledger_metrics(conn, event_count=3)

    assert metrics["storage_bytes"] > 0
    assert metrics["main_bytes"] > 0
    assert metrics["bytes_per_event"] > 0
    assert metrics["events_24h"] == 1
    assert metrics["events_7d"] == 2
    assert metrics["estimated_daily_growth_bytes"] > 0


@pytest.mark.parametrize(
    "command",
    [
        ["doctor"],
        ["integrity", "check"],
        ["ledger", "verify"],
        ["ledger", "head"],
        ["ledger", "tail"],
        ["ask", "status"],
    ],
)
def test_readonly_diagnostic_commands_fail_without_creating_database(
    monkeypatch, tmp_path, command
):
    path = tmp_path / "missing.sqlite3"
    monkeypatch.setenv("GENUS_DB_PATH", str(path))

    result = CliRunner().invoke(cli.main, command)

    assert result.exit_code != 0
    assert "database does not exist" in result.output
    assert not path.exists()


def test_anchor_verify_fails_without_creating_database(monkeypatch, tmp_path):
    path = tmp_path / "missing.sqlite3"
    artifact = tmp_path / "anchor.json"
    artifact.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("GENUS_DB_PATH", str(path))

    result = CliRunner().invoke(
        cli.main, ["ledger", "anchor", "verify", str(artifact)]
    )

    assert result.exit_code != 0
    assert "database does not exist" in result.output
    assert not path.exists()
