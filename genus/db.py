from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schema.sql"


class DatabaseNotFoundError(FileNotFoundError):
    """An existing GENUS ledger was required, but no database exists there."""


def connect(path: str | Path = "genus.sqlite3") -> sqlite3.Connection:
    # Streu-DB-Schutz (live gefunden, 2026-07-04): ein Befehl ohne GENUS_DB_PATH legte
    # still eine leere Datenbank im Arbeitsverzeichnis an und schrieb 27 Events daran
    # vorbei am echten Ledger. Das Anlegen bleibt erlaubt (frische Installationen,
    # Tests) -- aber es passiert nie mehr LAUTLOS.
    neu = str(path) != ":memory:" and not Path(path).exists()
    conn = sqlite3.connect(path)
    init_schema(conn)
    if neu:
        print(f"[DB] NEU angelegt: {Path(path).resolve()} — beabsichtigt? "
              f"(Das echte Ledger wählt GENUS_DB_PATH; ohne die Variable entsteht "
              f"sonst still eine leere Streu-DB im Arbeitsverzeichnis.)",
              file=sys.stderr)
    return conn


def connect_readonly(path: str | Path = "genus.sqlite3") -> sqlite3.Connection:
    """Open an existing ledger without creating or migrating anything.

    Diagnostics must not turn a typo or a missing ``GENUS_DB_PATH`` into a fresh
    scatter database.  SQLite's ``mode=ro`` closes the race left by a plain
    ``Path.exists`` check, while ``query_only`` also guards against accidental
    writes through the returned connection.
    """
    if str(path) == ":memory:":
        raise DatabaseNotFoundError(
            "read-only diagnostics require an existing file-backed GENUS database"
        )

    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise DatabaseNotFoundError(
            f"GENUS database does not exist: {resolved} "
            "(set GENUS_DB_PATH to the existing ledger)"
        )

    conn = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA query_only = ON")
    return conn


def ledger_metrics(
    conn: sqlite3.Connection,
    *,
    event_count: int | None = None,
    db_path: str | Path | None = None,
) -> dict:
    """Return read-time storage and recent-growth metrics for the ledger.

    No state is persisted.  File-backed databases include the WAL in their
    physical storage total; in-memory databases use SQLite's allocated pages so
    tests and embedded callers still receive meaningful values.
    """
    if event_count is None:
        event_count = int(
            conn.execute("SELECT COUNT(*) AS count FROM event_log").fetchone()["count"]
        )

    events_24h = int(
        conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM event_log
            WHERE created_at >= strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-24 hours')
            """
        ).fetchone()["count"]
    )
    events_7d = int(
        conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM event_log
            WHERE created_at >= strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-7 days')
            """
        ).fetchone()["count"]
    )

    page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
    page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
    free_pages = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
    allocated_bytes = page_size * page_count

    path = _database_path(conn, db_path)
    if path is None:
        main_bytes = allocated_bytes
        wal_bytes = 0
    else:
        main_bytes = path.stat().st_size if path.is_file() else allocated_bytes
        wal_path = Path(f"{path}-wal")
        wal_bytes = wal_path.stat().st_size if wal_path.is_file() else 0

    storage_bytes = main_bytes + wal_bytes
    bytes_per_event = (
        round(storage_bytes / event_count, 1) if event_count else None
    )
    return {
        "storage_bytes": int(storage_bytes),
        "main_bytes": int(main_bytes),
        "wal_bytes": int(wal_bytes),
        "free_bytes": int(free_pages * page_size),
        "bytes_per_event": bytes_per_event,
        "events_24h": events_24h,
        "events_7d": events_7d,
        "estimated_daily_growth_bytes": (
            round(bytes_per_event * events_24h) if bytes_per_event is not None else 0
        ),
    }


def _database_path(
    conn: sqlite3.Connection, explicit_path: str | Path | None
) -> Path | None:
    if explicit_path is not None and str(explicit_path) != ":memory:":
        return Path(explicit_path).expanduser().resolve()
    row = conn.execute(
        "SELECT file FROM pragma_database_list WHERE name = 'main'"
    ).fetchone()
    if row is None or not row["file"]:
        return None
    return Path(row["file"])


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
