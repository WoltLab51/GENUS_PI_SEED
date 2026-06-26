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
