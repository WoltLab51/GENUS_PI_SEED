from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "historical_sqlite_v1"
DATABASE_PATH = FIXTURE_ROOT / "legacy_v1.sqlite3"
EVENTS_PATH = FIXTURE_ROOT / "events.jsonl"
SCHEMA_PATH = FIXTURE_ROOT / "schema.sql"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"
REVIEW_PATH = FIXTURE_ROOT / "HUMAN_REVIEW.md"
README_PATH = FIXTURE_ROOT / "README.md"

SOURCE_COMMIT = "2bf67e6ded3164ad5d4a977954639cc294568633"
SOURCE_COMMIT_DATE = "2026-06-12T11:33:48+02:00"
SOURCE_COMMIT_MESSAGE = "Implement v1.1 ledger sealing"
SOURCE_SCHEMA_SHA256 = (
    "1ef8229402abb6203623f38fbc3a7fb35cf74c6c60bb4c6908c62d36cd9c5ddb"
)
CURRENT_SCHEMA_SHA256 = (
    "3aea8c5bbd126f8b6f99e34cf8eda0f54a91f717636e6a57d43dbeaeec042066"
)
FIXTURE_SCHEMA = "genus-historical-sqlite-fixture-v1"
EVENT_LINE_SCHEMA = "genus-golden-ledger-fixture-v1"
EVENT_STREAM_DIGEST_SCHEMA = "genus-golden-ledger-event-stream-digest-v1"
SCHEMA_FINGERPRINT_SCHEMA = "genus-sqlite-schema-inventory-v1"
STATUS = "accepted"

_FIELD_SEPARATOR = "\x1f"
_RECORD_SEPARATOR = "\x1e"
_EVENT_FIELDS = {"id", "event_type", "payload", "created_at", "prev_seal", "seal"}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_pretty_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def load_events(path: Path = EVENTS_PATH) -> list[dict[str, Any]]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise AssertionError("events.jsonl must not contain a UTF-8 BOM")
    if b"\r" in raw or not raw.endswith(b"\n") or raw.endswith(b"\n\n"):
        raise AssertionError("events.jsonl must use LF and exactly one final newline")

    events: list[dict[str, Any]] = []
    rebuilt = bytearray()
    for line in raw.splitlines():
        event = json.loads(line, parse_constant=_reject_nonfinite)
        if set(event) != _EVENT_FIELDS:
            raise AssertionError(f"unexpected event field set: {sorted(event)}")
        rebuilt.extend(
            json.dumps(
                event,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        rebuilt.extend(b"\n")
        events.append(event)

    if bytes(rebuilt) != raw:
        raise AssertionError("events.jsonl is not in canonical byte form")
    if [event["id"] for event in events] != list(range(1, len(events) + 1)):
        raise AssertionError("event IDs must be contiguous from one")
    return events


def event_stream_records(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for event in sorted(events, key=lambda item: int(item["id"])):
        records.append(
            {
                "created_at": event["created_at"],
                "event_type": event["event_type"],
                "id": int(event["id"]),
                "payload_text": json.dumps(
                    event["payload"],
                    ensure_ascii=True,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "prev_seal": event["prev_seal"],
                "seal": event["seal"],
            }
        )
    return records


def event_stream_sha256(events: Iterable[dict[str, Any]]) -> str:
    return sha256_bytes(canonical_json_bytes(event_stream_records(events)))


def export_events(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, event_type, payload, created_at, prev_seal, seal
        FROM event_log
        ORDER BY id
        """
    ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "event_type": row["event_type"],
            "payload": json.loads(row["payload"], parse_constant=_reject_nonfinite),
            "created_at": row["created_at"],
            "prev_seal": row["prev_seal"],
            "seal": row["seal"],
        }
        for row in rows
    ]


def schema_inventory(conn: sqlite3.Connection) -> dict[str, Any]:
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
                "cid": int(row["cid"]),
                "name": row["name"],
                "type": row["type"],
                "not_null": bool(row["notnull"]),
                "default": row["dflt_value"],
                "primary_key": int(row["pk"]),
            }
            for row in conn.execute(f"PRAGMA table_info({quoted_table})")
        ]
        for row in conn.execute(f"PRAGMA index_list({quoted_table})"):
            index_name = row["name"]
            if index_name.startswith("sqlite_"):
                continue
            quoted_index = _quote_identifier(index_name)
            columns = [
                info["name"]
                for info in conn.execute(f"PRAGMA index_info({quoted_index})")
            ]
            indexes.append(
                {
                    "name": index_name,
                    "table": table_name,
                    "unique": bool(row["unique"]),
                    "partial": bool(row["partial"]),
                    "columns": columns,
                }
            )

    triggers = [
        {"name": row["name"], "table": row["tbl_name"]}
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


def schema_fingerprint_sha256(inventory: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(inventory))


def database_pragmas(conn: sqlite3.Connection) -> dict[str, Any]:
    return {
        "application_id": int(conn.execute("PRAGMA application_id").fetchone()[0]),
        "encoding": conn.execute("PRAGMA encoding").fetchone()[0],
        "freelist_count": int(conn.execute("PRAGMA freelist_count").fetchone()[0]),
        "journal_mode": conn.execute("PRAGMA journal_mode").fetchone()[0],
        "page_count": int(conn.execute("PRAGMA page_count").fetchone()[0]),
        "page_size": int(conn.execute("PRAGMA page_size").fetchone()[0]),
        "user_version": int(conn.execute("PRAGMA user_version").fetchone()[0]),
    }


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    raw = path.read_bytes()
    manifest = json.loads(raw, parse_constant=_reject_nonfinite)
    if canonical_pretty_json_bytes(manifest) != raw:
        raise AssertionError("manifest.json is not in canonical pretty byte form")
    return manifest


def build_database(
    target: Path,
    *,
    schema_bytes: bytes,
    events: list[dict[str, Any]],
) -> None:
    if target.exists():
        raise FileExistsError(f"refusing to overwrite existing database: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA page_size = 4096")
        conn.execute("PRAGMA auto_vacuum = NONE")
        conn.execute("PRAGMA journal_mode = DELETE")
        conn.execute("PRAGMA application_id = 0")
        conn.execute("PRAGMA user_version = 0")
        conn.executescript(schema_bytes.decode("utf-8"))
        with conn:
            conn.executemany(
                """
                INSERT INTO event_log
                    (id, event_type, payload, created_at, prev_seal, seal)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        event["id"],
                        event["event_type"],
                        json.dumps(
                            event["payload"],
                            ensure_ascii=True,
                            allow_nan=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        event["created_at"],
                        event["prev_seal"],
                        event["seal"],
                    )
                    for event in events
                ],
            )
            conn.execute(
                """
                INSERT INTO belief_projection (
                    id, claim_key, claim_value, state, derivation,
                    supporting_events, contradicting_events, created_at,
                    last_updated_at, superseded_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    1,
                    "synthetic.temperature",
                    "nominal",
                    "active",
                    "fixture:legacy-v1",
                    "[1,2,6]",
                    "[]",
                    events[2]["created_at"],
                    events[6]["created_at"],
                    None,
                ),
            )
    finally:
        conn.close()
    assert_no_sidecars(target)


def verify_seal_chain(events: list[dict[str, Any]]) -> dict[str, str]:
    epoch = next(event for event in events if event["event_type"] == "ledger_epoch_opened")
    prefix_max_id = int(epoch["payload"]["prefix_max_id"])
    prefix = [event for event in events if int(event["id"]) <= prefix_max_id]
    records = [
        _FIELD_SEPARATOR.join(
            (
                str(event["id"]),
                event["event_type"],
                json.dumps(
                    event["payload"],
                    ensure_ascii=True,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                event["created_at"],
            )
        )
        for event in prefix
    ]
    genesis = sha256_bytes(_RECORD_SEPARATOR.join(records).encode("utf-8"))
    if genesis != epoch["payload"]["genesis_digest"] or epoch["prev_seal"] != genesis:
        raise AssertionError("historical genesis binding does not match")

    previous = genesis
    for event in events[prefix_max_id:]:
        payload_text = json.dumps(
            event["payload"],
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        expected = sha256_bytes(
            _FIELD_SEPARATOR.join(
                (previous, event["event_type"], payload_text)
            ).encode("utf-8")
        )
        if event["prev_seal"] != previous or event["seal"] != expected:
            raise AssertionError(f"historical seal mismatch at event {event['id']}")
        previous = expected
    return {"genesis_digest": genesis, "head_seal": previous}


def assert_no_sidecars(database_path: Path) -> None:
    for suffix in ("-journal", "-shm", "-wal"):
        sidecar = Path(f"{database_path}{suffix}")
        if sidecar.exists():
            raise AssertionError(f"unexpected SQLite sidecar: {sidecar}")


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _reject_nonfinite(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")
