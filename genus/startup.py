from __future__ import annotations

import sqlite3
from pathlib import Path

from genus import db, schema_detection


class StartupDatabaseError(RuntimeError):
    """A normal writable GENUS start was refused before initialization."""


class StartupDatabaseMissingError(StartupDatabaseError):
    """The configured database is absent, so normal startup must not create it."""


class StartupMigrationRequiredError(StartupDatabaseError):
    """The database is recognized but requires an explicit future migration."""


class StartupUnknownSchemaError(StartupDatabaseError):
    """The database schema is not one of the accepted exact inventories."""


def connect(path: str | Path = "genus.sqlite3") -> sqlite3.Connection:
    """Open a normal writable runtime connection only for the current schema.

    The existing file is opened once with ``mode=rw``.  That same SQLite connection is
    read-only during detection, then becomes writable only after an exact ``current``
    classification.  This function never provisions, migrates, or repairs a database.
    """
    configured_path = Path(path).expanduser().resolve()
    if not configured_path.is_file():
        raise StartupDatabaseMissingError(
            f"GENUS-Start verweigert: Datenbank fehlt; keine automatische Erzeugung ({configured_path})"
        )

    try:
        conn = sqlite3.connect(f"{configured_path.as_uri()}?mode=rw", uri=True)
    except sqlite3.OperationalError as exc:
        if not configured_path.is_file():
            raise StartupDatabaseMissingError(
                "GENUS-Start verweigert: Datenbank fehlt; "
                f"keine automatische Erzeugung ({configured_path})"
            ) from exc
        raise StartupDatabaseError(
            f"GENUS-Start verweigert: Datenbank kann nicht geöffnet werden ({configured_path})"
        ) from exc

    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = ON")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        result = schema_detection.detect_schema(conn)

        if result.status == "historical":
            raise StartupMigrationRequiredError(
                "GENUS-Start verweigert: Migration erforderlich "
                f"(erkannt: {result.schema_id}, fingerprint: {result.fingerprint})"
            )
        if result.status != "current":
            raise StartupUnknownSchemaError(
                "GENUS-Start verweigert: unbekanntes Schema "
                f"(fingerprint: {result.fingerprint})"
            )

        conn.execute("PRAGMA query_only = OFF")
        if int(conn.execute("PRAGMA query_only").fetchone()[0]) != 0:
            raise StartupDatabaseError(
                "GENUS-Start verweigert: geprüfte Datenbank blieb read-only"
            )
        db.init_schema(conn)
        return conn
    except BaseException:
        conn.close()
        raise
