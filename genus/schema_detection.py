from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Literal


SchemaStatus = Literal["current", "historical", "unknown"]

SCHEMA_FINGERPRINT_SCHEMA = "genus-sqlite-schema-inventory-v1"

# Derived once from the committed schema.sql at 5ba0f5e using the inventory
# domain above. Runtime detection deliberately does not read schema.sql.
CURRENT_SCHEMA_FINGERPRINT = (
    "2d7e1497bba0a34e141e821b2cd15f8ab71f571454da84f1b128844fcce493ab"
)
HISTORICAL_V1_1_SCHEMA_FINGERPRINT = (
    "e73837d56217169b1365a75ca404d6512ff7c9655d3e5dc993ba12b368d446a3"
)


@dataclass(frozen=True)
class SchemaDetection:
    status: SchemaStatus
    schema_id: str | None
    fingerprint: str
    current: bool
    migration_required: bool | None


class SchemaDetectionError(RuntimeError):
    """Raised when schema detection is attempted outside the read-only boundary."""


def detect_schema(conn: sqlite3.Connection) -> SchemaDetection:
    """Classify a SQLite schema using only deterministic read-only inspection."""
    if int(conn.execute("PRAGMA query_only").fetchone()[0]) != 1:
        raise SchemaDetectionError(
            "schema detection requires a genus.db.connect_readonly connection"
        )

    fingerprint = _schema_fingerprint(_schema_inventory(conn))
    if fingerprint == CURRENT_SCHEMA_FINGERPRINT:
        return SchemaDetection(
            status="current",
            schema_id="current",
            fingerprint=fingerprint,
            current=True,
            migration_required=False,
        )
    if fingerprint == HISTORICAL_V1_1_SCHEMA_FINGERPRINT:
        return SchemaDetection(
            status="historical",
            schema_id="historical-v1.1",
            fingerprint=fingerprint,
            current=False,
            migration_required=True,
        )
    return SchemaDetection(
        status="unknown",
        schema_id=None,
        fingerprint=fingerprint,
        current=False,
        migration_required=None,
    )


def _schema_inventory(conn: sqlite3.Connection) -> dict[str, Any]:
    table_names = [
        row[0]
        for row in conn.execute(
            """
            SELECT name
            FROM sqlite_schema
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        )
    ]

    tables: dict[str, list[dict[str, Any]]] = {}
    indexes: list[dict[str, Any]] = []
    for table_name in table_names:
        quoted_table = _quote_identifier(table_name)
        tables[table_name] = [
            {
                "cid": int(row[0]),
                "name": row[1],
                "type": row[2],
                "not_null": bool(row[3]),
                "default": row[4],
                "primary_key": int(row[5]),
            }
            for row in conn.execute(f"PRAGMA table_info({quoted_table})")
        ]
        for row in conn.execute(f"PRAGMA index_list({quoted_table})"):
            index_name = row[1]
            if index_name.startswith("sqlite_"):
                continue
            quoted_index = _quote_identifier(index_name)
            columns = [
                info[2]
                for info in conn.execute(f"PRAGMA index_info({quoted_index})")
            ]
            indexes.append(
                {
                    "name": index_name,
                    "table": table_name,
                    "unique": bool(row[2]),
                    "partial": bool(row[4]),
                    "columns": columns,
                }
            )

    triggers = [
        {"name": row[0], "table": row[1]}
        for row in conn.execute(
            """
            SELECT name, tbl_name
            FROM sqlite_schema
            WHERE type = 'trigger' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        )
    ]
    indexes.sort(key=lambda item: item["name"])
    return {"tables": tables, "indexes": indexes, "triggers": triggers}


def _schema_fingerprint(inventory: dict[str, Any]) -> str:
    canonical = json.dumps(
        inventory,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'
