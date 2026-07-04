from genus import db


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
