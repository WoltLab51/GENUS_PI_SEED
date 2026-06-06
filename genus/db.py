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
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
