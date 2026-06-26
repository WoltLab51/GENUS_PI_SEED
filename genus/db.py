from __future__ import annotations

import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schema.sql"


def connect(path: str | Path = "genus.sqlite3") -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Many short-lived processes (observe-all, state-refresh, the watchdog, the
    # membranes) write the same ledger on overlapping ~5-minute cycles. busy_timeout
    # makes a writer wait for a lock instead of failing with "database is locked";
    # WAL lets readers proceed without blocking the single writer. Both are no-ops
    # for the in-memory test databases.
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    _ensure_column(conn, "proposal_log", "decision", "TEXT")
    _ensure_column(conn, "proposal_log", "reviewed_at", "TEXT")
    _ensure_column(conn, "inquiry_log", "answer", "TEXT")
    # ADD COLUMN is append-compatible: it does not rewrite existing rows and
    # does not fire the append-only UPDATE trigger. Legacy rows stay unsealed.
    _ensure_column(conn, "event_log", "prev_seal", "TEXT")
    _ensure_column(conn, "event_log", "seal", "TEXT")
    conn.commit()


def _ensure_column(
    conn: sqlite3.Connection, table_name: str, column_name: str, definition: str
) -> None:
    columns = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")
