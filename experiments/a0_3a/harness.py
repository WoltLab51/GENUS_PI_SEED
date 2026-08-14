"""A0.3a test-only measurement harness for transactional bounded replay.

This module deliberately lives outside :mod:`genus`. It does not replace or
activate the product replay/integrity paths. It measures one candidate topology:

``BEGIN IMMEDIATE -> fixed head -> bounded rebuild -> bounded checks -> COMMIT``.

The batch size is only a memory boundary. It is never a commit boundary. All
receipts are aggregate-only: payloads and absolute database paths are excluded.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import sqlite3
import sys
import threading
import time
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

import psutil

from genus import db, event_router, integrity, response_outcomes, sealing


RECEIPT_SCHEMA = "genus-a0-3a-measurement-receipt-v1"
LEDGER_DIGEST_SCHEMA = "genus-a0-3a-ledger-stream-v1"
PROJECTION_DIGEST_SCHEMA = "genus-golden-ledger-projection-digest-v1"
PROJECTION_DIGEST_SET_SCHEMA = "genus-golden-ledger-projection-digest-set-v1"
DISPOSABLE_MARKER_SCHEMA = "genus-a0-3a-disposable-target-v1"
DISPOSABLE_MARKER_PURPOSE = "a0-3a-measurement-harness"
DISPOSABLE_MARKER_SUFFIX = ".a0-3a-disposable.json"

EVENT_COLUMNS = ("id", "event_type", "payload", "created_at", "prev_seal", "seal")
PROJECTION_TABLES = tuple(event_router.REPLAY_PROJEKTIONSTABELLEN)
_EXPECTED_TARGETS = {
    "response_feedback_log",
    "response_outcome_log",
    "rule_projection",
    "governance_log",
    "operation_log",
    "inquiry_log",
    "proposal_log",
    "experience_log",
    "state_projection",
    "belief_projection",
    "relation_projection",
    "value_projection",
}
if set(PROJECTION_TABLES) != _EXPECTED_TARGETS:
    raise RuntimeError("A0.3a projection inventory no longer names exactly twelve targets")

PROJECTION_SPECS: dict[str, dict[str, tuple[str, ...]]] = {
    "belief_projection": {
        "columns": (
            "id", "claim_key", "claim_value", "state", "derivation",
            "supporting_events", "contradicting_events", "created_at",
            "last_updated_at", "superseded_by",
        ),
        "sort_by": ("id",),
    },
    "experience_log": {
        "columns": (
            "id", "experience_key", "experience_type", "subject_key", "pattern",
            "supporting_events", "derivation", "summary", "created_at",
        ),
        "sort_by": ("id",),
    },
    "governance_log": {
        "columns": (
            "id", "action", "target_type", "target_id", "decision", "override",
            "policy_results", "reason", "created_at",
        ),
        "sort_by": ("id",),
    },
    "inquiry_log": {
        "columns": (
            "id", "inquiry_type", "claim_key", "source_belief", "source_event",
            "question_key", "payload", "state", "created_at", "answer", "resolved_at",
        ),
        "sort_by": ("id",),
    },
    "operation_log": {
        "columns": (
            "id", "operation_type", "check_key", "status", "target", "payload",
            "derivation", "source_event", "created_at", "last_updated_at",
        ),
        "sort_by": ("id",),
    },
    "proposal_log": {
        "columns": (
            "id", "proposal_type", "claim_key", "claim_value", "source_belief",
            "source_event", "payload", "state", "decision", "reviewed_at", "created_at",
        ),
        "sort_by": ("id",),
    },
    "relation_projection": {
        "columns": (
            "id", "subject", "predicate", "object", "source", "derivation",
            "created_at", "last_updated_at",
        ),
        "sort_by": ("id",),
    },
    "response_feedback_log": {
        "columns": (
            "feedback_event_id", "response_id", "signal", "corrected_intent",
            "source", "created_at",
        ),
        "sort_by": ("feedback_event_id",),
    },
    "response_outcome_log": {
        "columns": (
            "response_id", "channel", "outcome", "readings", "answer_mode",
            "feedback_eligible", "created_at",
        ),
        "sort_by": ("response_id",),
    },
    "rule_projection": {
        "columns": (
            "id", "rule_key", "rule_type", "subject_key", "spec", "status",
            "source_proposal", "derivation", "created_at",
        ),
        "sort_by": ("id",),
    },
    "state_projection": {
        "columns": (
            "id", "state_key", "state_value", "status", "derivation",
            "supporting_beliefs", "components", "reason", "created_at",
            "last_updated_at", "superseded_by",
        ),
        "sort_by": ("id",),
    },
    "value_projection": {
        "columns": ("event_id", "claim_key", "value", "source", "created_at"),
        "sort_by": ("event_id",),
    },
}

JSON_COLUMNS: dict[str, frozenset[str]] = {
    "belief_projection": frozenset({"supporting_events", "contradicting_events"}),
    "experience_log": frozenset({"pattern", "supporting_events"}),
    "governance_log": frozenset({"policy_results"}),
    "inquiry_log": frozenset({"payload"}),
    "operation_log": frozenset({"payload"}),
    "proposal_log": frozenset({"payload"}),
    "relation_projection": frozenset(),
    "response_feedback_log": frozenset(),
    "response_outcome_log": frozenset({"readings"}),
    "rule_projection": frozenset({"spec"}),
    "state_projection": frozenset({"supporting_beliefs", "components"}),
    "value_projection": frozenset(),
}

_SEQUENCE_TABLES = (
    "rule_projection", "governance_log", "operation_log", "inquiry_log",
    "proposal_log", "experience_log", "state_projection", "belief_projection",
    "relation_projection",
)


class HarnessError(RuntimeError):
    """The experimental topology violated a measured invariant."""


class InjectedFault(HarnessError):
    """A deterministic test-only failure was injected."""


class OracleMismatch(HarnessError):
    """The rebuilt projection digest set differs from its independent expectation."""


class PostCommitProgressError(HarnessError):
    """Telemetry failed after SQLite had already committed successfully."""


class DisposableTargetError(HarnessError):
    """A writable target is not provably disposable and must not be opened."""


@dataclass(frozen=True)
class DisposableTargetEvidence:
    """Path-free proof that the fail-closed disposable-target gate passed."""

    database_path: Path
    disposable_root: Path
    marker_path: Path
    marker_sha256: str
    protected_paths_checked: int
    strict_containment: bool
    database_is_symlink: bool
    marker_is_symlink: bool
    product_path_match: bool
    root_contains_product_path: bool

    def receipt(self) -> dict[str, Any]:
        return {
            "schema": DISPOSABLE_MARKER_SCHEMA,
            "validated": True,
            "database_label": self.database_path.name,
            "marker_label": self.marker_path.name,
            "marker_sha256": self.marker_sha256,
            "marker_fields_exact": True,
            "purpose": DISPOSABLE_MARKER_PURPOSE,
            "strict_containment": self.strict_containment,
            "database_is_symlink": self.database_is_symlink,
            "marker_is_symlink": self.marker_is_symlink,
            "protected_paths_checked": self.protected_paths_checked,
            "product_path_match": self.product_path_match,
            "root_contains_product_path": self.root_contains_product_path,
            "absolute_paths_logged": False,
        }


@dataclass(frozen=True)
class _DisposableLocation:
    database_path: Path
    disposable_root: Path
    marker_path: Path
    protected_paths_checked: int
    strict_containment: bool
    database_is_symlink: bool
    marker_is_symlink: bool
    product_path_match: bool
    root_contains_product_path: bool


def disposable_marker_path(database_path: Path | str) -> Path:
    """Return the sidecar marker name without opening the database."""
    return Path(f"{Path(database_path)}{DISPOSABLE_MARKER_SUFFIX}")


def _protected_product_paths() -> tuple[Path, ...]:
    candidates: list[Path] = []
    configured = os.environ.get("GENUS_DB_PATH")
    if configured and configured != ":memory:":
        candidates.append(Path(configured).expanduser().resolve(strict=False))
    candidates.extend(
        (
            (Path.home() / ".genus" / "genus.sqlite3").resolve(strict=False),
            (Path.cwd() / "genus.sqlite3").resolve(strict=False),
        )
    )
    return tuple(dict.fromkeys(candidates))


def _same_existing_file(left: Path, right: Path) -> bool:
    """Return whether two paths identify one existing file, including hardlinks."""
    if left == right:
        return True
    try:
        return left.samefile(right)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise DisposableTargetError(
            "cannot verify database identity against a protected product path"
        ) from exc


def _inspect_disposable_location(
    database_path: Path | str,
    disposable_root: Path | str,
    *,
    require_database: bool,
) -> _DisposableLocation:
    if str(database_path) == ":memory:":
        raise DisposableTargetError("in-memory databases are not disposable file targets")

    raw_root = Path(disposable_root).expanduser()
    if raw_root.is_symlink():
        raise DisposableTargetError("disposable root must not be a symlink")
    try:
        root = raw_root.resolve(strict=True)
    except FileNotFoundError as exc:
        raise DisposableTargetError("disposable root does not exist") from exc
    if not root.is_dir():
        raise DisposableTargetError("disposable root is not a directory")

    raw_database = Path(database_path).expanduser()
    database_is_symlink = raw_database.is_symlink()
    if database_is_symlink:
        raise DisposableTargetError("database target must not be a symlink")
    try:
        database = raw_database.resolve(strict=require_database)
    except FileNotFoundError as exc:
        raise DisposableTargetError("disposable database does not exist") from exc
    if require_database and not database.is_file():
        raise DisposableTargetError("disposable database is not a regular file")

    try:
        relative_database = database.relative_to(root)
    except ValueError as exc:
        raise DisposableTargetError("database is outside the disposable root") from exc
    strict_containment = relative_database != Path(".")
    if not strict_containment:
        raise DisposableTargetError("database must be strictly inside the disposable root")

    marker = disposable_marker_path(database)
    marker_is_symlink = marker.is_symlink()
    if marker_is_symlink:
        raise DisposableTargetError("disposable marker must not be a symlink")
    if marker.exists() and not marker.is_file():
        raise DisposableTargetError("disposable marker is not a regular file")

    protected = _protected_product_paths()
    product_path_match = any(
        _same_existing_file(database, protected_path)
        for protected_path in protected
    )
    root_contains_product_path = any(
        protected_path == root or root in protected_path.parents
        for protected_path in protected
    )
    if product_path_match:
        raise DisposableTargetError("database matches a protected product path")
    if root_contains_product_path:
        raise DisposableTargetError("disposable root contains a protected product path")

    return _DisposableLocation(
        database_path=database,
        disposable_root=root,
        marker_path=marker,
        protected_paths_checked=len(protected),
        strict_containment=strict_containment,
        database_is_symlink=database_is_symlink,
        marker_is_symlink=marker_is_symlink,
        product_path_match=product_path_match,
        root_contains_product_path=root_contains_product_path,
    )


def _expected_disposable_marker(database_path: Path) -> dict[str, str]:
    return {
        "schema": DISPOSABLE_MARKER_SCHEMA,
        "database": database_path.name,
        "purpose": DISPOSABLE_MARKER_PURPOSE,
    }


def register_disposable_database(
    database_path: Path | str,
    disposable_root: Path | str,
) -> Path:
    """Register one completed experiment DB using an exact, path-free marker."""
    location = _inspect_disposable_location(
        database_path, disposable_root, require_database=True
    )
    expected = _expected_disposable_marker(location.database_path)
    encoded = json.dumps(expected, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    marker = location.marker_path
    if marker.exists():
        try:
            existing = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise DisposableTargetError("disposable marker is unreadable or invalid") from exc
        if existing != expected:
            raise DisposableTargetError("disposable marker fields are not exact")
        return marker
    try:
        with marker.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded)
    except FileExistsError as exc:
        raise DisposableTargetError("disposable marker appeared during registration") from exc
    return marker


def validate_disposable_target(
    database_path: Path | str,
    disposable_root: Path | str,
) -> DisposableTargetEvidence:
    """Fail closed before sampling or SQLite-open unless target proof is exact."""
    location = _inspect_disposable_location(
        database_path, disposable_root, require_database=True
    )
    marker = location.marker_path
    if not marker.exists():
        raise DisposableTargetError("disposable marker does not exist")
    try:
        if marker.stat().st_size > 4096:
            raise DisposableTargetError("disposable marker is unexpectedly large")
        marker_bytes = marker.read_bytes()
        marker_value = json.loads(marker_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DisposableTargetError("disposable marker is unreadable or invalid") from exc
    if marker_value != _expected_disposable_marker(location.database_path):
        raise DisposableTargetError("disposable marker fields are not exact")
    return DisposableTargetEvidence(
        database_path=location.database_path,
        disposable_root=location.disposable_root,
        marker_path=marker,
        marker_sha256=hashlib.sha256(marker_bytes).hexdigest(),
        protected_paths_checked=location.protected_paths_checked,
        strict_containment=location.strict_containment,
        database_is_symlink=location.database_is_symlink,
        marker_is_symlink=location.marker_is_symlink,
        product_path_match=location.product_path_match,
        root_contains_product_path=location.root_contains_product_path,
    )


@dataclass(frozen=True)
class ReplayFence:
    head_id: int | None
    event_count: int
    min_id: int | None
    epoch_event_id: int | None
    head_seal: str | None


@dataclass(frozen=True)
class SyntheticSpec:
    event_count: int
    batch_size: int = 1_024
    payload_bytes: int = 256
    seed: int = 3

    def __post_init__(self) -> None:
        if self.event_count < 0:
            raise ValueError("event_count must be non-negative")
        if self.batch_size < 1:
            raise ValueError("batch_size must be positive")
        if self.payload_bytes < 0:
            raise ValueError("payload_bytes must be non-negative")


def _quote(identifier: str) -> str:
    if not identifier or not identifier.replace("_", "a").isalnum() or identifier[0].isdigit():
        raise HarnessError(f"unsafe SQLite identifier: {identifier!r}")
    return f'"{identifier}"'


def _row_dict(row: sqlite3.Row | Sequence[Any], columns: Sequence[str]) -> dict[str, Any]:
    if isinstance(row, sqlite3.Row):
        return {column: row[column] for column in columns}
    return dict(zip(columns, row, strict=True))


def _normalize_json(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise HarnessError("non-finite projection value")
        return 0.0 if value == 0.0 else value
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [_normalize_json(item) for item in value]
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise HarnessError("JSON object key is not text")
            normalized_key = unicodedata.normalize("NFC", key)
            if normalized_key in normalized:
                raise HarnessError("NFC normalization collides JSON object keys")
            normalized[normalized_key] = _normalize_json(item)
        return normalized
    raise HarnessError(f"unsupported projection type: {type(value).__name__}")


def _projection_value(table: str, column: str, value: Any) -> Any:
    if isinstance(value, bytes):
        raise HarnessError(f"{table}.{column} contains a BLOB")
    if column in JSON_COLUMNS[table] and value is not None:
        if not isinstance(value, str):
            raise HarnessError(f"{table}.{column} JSON value is not SQLite TEXT")
        try:
            value = json.loads(value, parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON number: {token}")
            ))
        except (json.JSONDecodeError, ValueError) as exc:
            raise HarnessError(f"{table}.{column} contains invalid JSON TEXT") from exc
        value = json.dumps(
            _normalize_json(value), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        )
    return _normalize_json(value)


def _sha256_json(value: Any, *, ensure_ascii: bool = False) -> str:
    encoded = json.dumps(
        _normalize_json(value), ensure_ascii=ensure_ascii, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def capture_fence(conn: sqlite3.Connection) -> ReplayFence:
    """Capture the fixed replay head inside a caller-owned transaction."""
    if not conn.in_transaction:
        raise HarnessError("capture_fence requires an active caller-owned transaction")
    count, min_id, head_id = conn.execute(
        "SELECT COUNT(*), MIN(id), MAX(id) FROM event_log"
    ).fetchone()
    epoch = conn.execute(
        "SELECT id FROM event_log WHERE event_type = ? ORDER BY id LIMIT 1",
        (sealing.EPOCH_EVENT,),
    ).fetchone()
    head_seal = None
    if head_id is not None:
        head_seal = conn.execute(
            "SELECT seal FROM event_log WHERE id = ?", (int(head_id),)
        ).fetchone()[0]
    return ReplayFence(
        head_id=None if head_id is None else int(head_id),
        event_count=int(count),
        min_id=None if min_id is None else int(min_id),
        epoch_event_id=None if epoch is None else int(epoch[0]),
        head_seal=head_seal,
    )


def iter_event_batches(
    conn: sqlite3.Connection,
    fence: ReplayFence,
    batch_size: int,
) -> Iterator[list[dict[str, Any]]]:
    """Yield ordered keyset batches bounded by ``fence.head_id``."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    if fence.head_id is None:
        return
    last = fence.min_id - 1 if fence.min_id is not None else 0
    selected = ", ".join(EVENT_COLUMNS)
    while True:
        rows = conn.execute(
            f"SELECT {selected} FROM event_log "
            "WHERE id > ? AND id <= ? ORDER BY id LIMIT ?",
            (last, fence.head_id, batch_size),
        ).fetchall()
        if not rows:
            break
        batch = [_row_dict(row, EVENT_COLUMNS) for row in rows]
        for event in batch:
            event_id = int(event["id"])
            if event_id <= last or event_id > fence.head_id:
                raise HarnessError("keyset stream escaped fixed head or lost monotonicity")
            last = event_id
        yield batch


def stream_ledger_binding(
    conn: sqlite3.Connection,
    fence: ReplayFence,
    batch_size: int,
) -> dict[str, Any]:
    """Digest all six event fields without retaining the ledger in memory."""
    digest = hashlib.sha256((LEDGER_DIGEST_SCHEMA + "\0").encode("ascii"))
    processed = 0
    first_id: int | None = None
    last_id: int | None = None
    for batch in iter_event_batches(conn, fence, batch_size):
        for event in batch:
            digest.update(b"R")
            for column in EVENT_COLUMNS:
                value = event[column]
                if value is None:
                    digest.update(b"N")
                else:
                    encoded = str(value).encode("utf-8")
                    digest.update(b"V")
                    digest.update(len(encoded).to_bytes(8, "big"))
                    digest.update(encoded)
            event_id = int(event["id"])
            first_id = event_id if first_id is None else first_id
            last_id = event_id
            processed += 1
    if processed != fence.event_count:
        raise HarnessError(
            f"fixed-head stream processed {processed}, expected {fence.event_count}"
        )
    return {
        "schema": LEDGER_DIGEST_SCHEMA,
        "event_count": processed,
        "min_id": first_id,
        "fixed_head": last_id,
        "head_seal": fence.head_seal,
        "sha256": digest.hexdigest(),
    }


def stream_projection_digests(
    conn: sqlite3.Connection,
    batch_size: int,
) -> dict[str, Any]:
    """Compute the exact A0.2 row digests for all twelve projection tables."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    digests: dict[str, str] = {}
    counts: dict[str, int] = {}
    for table in PROJECTION_TABLES:
        spec = PROJECTION_SPECS[table]
        columns = spec["columns"]
        sort_by = spec["sort_by"]
        actual_columns = {
            row[1] for row in conn.execute(f"PRAGMA table_info({_quote(table)})").fetchall()
        }
        if actual_columns != set(columns):
            raise HarnessError(f"{table} columns differ from the pinned A0.2 contract")
        selected = ", ".join(_quote(column) for column in columns)
        ordered = ", ".join(_quote(column) for column in sort_by)
        cursor = conn.execute(
            f"SELECT {selected} FROM {_quote(table)} ORDER BY {ordered}"
        )
        digest = hashlib.sha256()
        digest.update(b"[")
        count = 0
        previous_key: tuple[Any, ...] | None = None
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            for raw in rows:
                row = _row_dict(raw, columns)
                normalized = {
                    column: _projection_value(table, column, row[column])
                    for column in columns
                }
                key = tuple(normalized[column] for column in sort_by)
                if previous_key is not None and key <= previous_key:
                    raise HarnessError(f"{table}.sort_by is not a unique total order")
                previous_key = key
                if count:
                    digest.update(b",")
                digest.update(json.dumps(
                    normalized, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":"), allow_nan=False,
                ).encode("utf-8"))
                count += 1
        digest.update(b"]")
        digests[table] = digest.hexdigest()
        counts[table] = count
    digest_set = _sha256_json(digests, ensure_ascii=False)
    return {
        "row_digest_schema": PROJECTION_DIGEST_SCHEMA,
        "digest_set_schema": PROJECTION_DIGEST_SET_SCHEMA,
        "digests": digests,
        "counts": counts,
        "digest_set_sha256": digest_set,
    }


def verify_chain_bounded(
    conn: sqlite3.Connection,
    fence: ReplayFence,
    batch_size: int,
    *,
    issue_limit: int = 50,
) -> list[str]:
    """Streaming equivalent of the current seal check at one fixed head."""
    if fence.epoch_event_id is None:
        return []
    epoch = conn.execute(
        "SELECT id,payload,prev_seal,seal FROM event_log WHERE id = ?",
        (fence.epoch_event_id,),
    ).fetchone()
    if epoch is None:
        return ["fixed epoch event disappeared"]
    try:
        meta = json.loads(epoch[1])
        genesis = meta["genesis_digest"]
        prefix_max_id = int(meta["prefix_max_id"])
        prefix_count = int(meta["prefix_count"])
        algo = meta["algo"]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return ["ledger_epoch_opened payload is malformed"]
    issues: list[str] = []

    def add(issue: str) -> None:
        if len(issues) < issue_limit:
            issues.append(issue)

    if algo != sealing.ALGO:
        add(f"ledger_epoch_opened has unsupported algo {algo}")
    prefix_digest = hashlib.sha256()
    prefix_seen = 0
    last = 0
    while prefix_max_id > 0:
        rows = conn.execute(
            "SELECT id,event_type,payload,created_at FROM event_log "
            "WHERE id > ? AND id <= ? ORDER BY id LIMIT ?",
            (last, prefix_max_id, batch_size),
        ).fetchall()
        if not rows:
            break
        for row in rows:
            if prefix_seen:
                prefix_digest.update(b"\x1e")
            record = "\x1f".join((str(row[0]), row[1], row[2], row[3]))
            prefix_digest.update(record.encode("utf-8"))
            prefix_seen += 1
            last = int(row[0])
    computed_genesis = (
        prefix_digest.hexdigest()
        if prefix_seen
        else hashlib.sha256(sealing.GENESIS_SEED.encode("utf-8")).hexdigest()
    )
    if prefix_seen != prefix_count:
        add("ledger genesis prefix count mismatch")
    if computed_genesis != genesis:
        add("ledger genesis digest mismatch (pre-epoch history altered)")
    prev = genesis
    last = prefix_max_id
    while fence.head_id is not None and last < fence.head_id:
        rows = conn.execute(
            "SELECT id,event_type,payload,created_at,prev_seal,seal FROM event_log "
            "WHERE id > ? AND id <= ? ORDER BY id LIMIT ?",
            (last, fence.head_id, batch_size),
        ).fetchall()
        if not rows:
            break
        for row in rows:
            row_id = int(row[0])
            if row[4] is None or row[5] is None:
                add(f"event {row_id} after epoch is missing a seal")
                return issues
            if row[4] != prev:
                add(f"event {row_id} prev_seal mismatch")
                return issues
            expected = sealing.compute_seal(prev, row[1], row[2])
            if expected != row[5]:
                add(f"event {row_id} seal mismatch (content or order altered)")
                return issues
            prev = row[5]
            last = row_id
    return issues


def validate_event_contract_bounded(
    conn: sqlite3.Connection,
    fence: ReplayFence,
    batch_size: int,
    *,
    issue_limit: int = 100,
) -> list[str]:
    """Stream the current event contract with SQLite-backed duplicate state."""
    issues: list[str] = []

    def add(issue: str) -> None:
        if len(issues) < issue_limit:
            issues.append(issue)

    conn.execute(
        "CREATE TEMP TABLE IF NOT EXISTS a03_seen "
        "(kind TEXT NOT NULL, key TEXT NOT NULL, PRIMARY KEY(kind,key)) WITHOUT ROWID"
    )
    conn.execute("DELETE FROM a03_seen")
    conn.execute(
        "CREATE TEMP TABLE IF NOT EXISTS a03_response "
        "(id INTEGER PRIMARY KEY, eligible INTEGER NOT NULL) WITHOUT ROWID"
    )
    conn.execute("DELETE FROM a03_response")

    def mark_once(kind: str, key: Any, duplicate_issue: str) -> None:
        try:
            conn.execute("INSERT INTO a03_seen(kind,key) VALUES (?,?)", (kind, str(key)))
        except sqlite3.IntegrityError:
            add(duplicate_issue)

    expected_id = fence.min_id
    processed = 0
    for batch in iter_event_batches(conn, fence, batch_size):
        for row in batch:
            row_id = int(row["id"])
            if expected_id is not None and row_id != expected_id:
                add("event_log ids are not contiguous")
            expected_id = row_id + 1
            processed += 1
            event_type = str(row["event_type"])
            try:
                payload = json.loads(row["payload"])
            except json.JSONDecodeError:
                add(f"event {row_id} payload is not valid JSON")
                continue
            if not isinstance(payload, dict):
                add(f"event {row_id} payload must be a JSON object")
                continue
            required = integrity.REQUIRED_EVENT_KEYS.get(event_type)
            if required is None:
                add(f"event {row_id} has unknown event_type {event_type}")
                continue
            missing = sorted(required - set(payload))
            if missing:
                add(f"event {row_id} {event_type} missing keys: {', '.join(missing)}")
                continue
            if event_type == response_outcomes.OUTCOME_EVENT:
                payload_issues = response_outcomes.outcome_payload_issues(payload)
                for issue in payload_issues:
                    add(f"event {row_id} {event_type} {issue}")
                if not payload_issues:
                    conn.execute(
                        "INSERT OR REPLACE INTO a03_response(id,eligible) VALUES (?,?)",
                        (row_id, int(bool(payload["feedback_eligible"]))),
                    )
                continue
            if event_type == response_outcomes.FEEDBACK_EVENT:
                payload_issues = response_outcomes.feedback_payload_issues(payload)
                for issue in payload_issues:
                    add(f"event {row_id} {event_type} {issue}")
                if not payload_issues:
                    response_id = int(payload["response_id"])
                    found = conn.execute(
                        "SELECT eligible FROM a03_response WHERE id=?", (response_id,)
                    ).fetchone()
                    if found is None:
                        add(
                            f"event {row_id} {event_type} response_id {response_id} "
                            "does not reference an earlier valid response outcome"
                        )
                    elif not bool(found[0]):
                        add(
                            f"event {row_id} {event_type} response_id {response_id} "
                            "is not feedback eligible"
                        )
                continue
            if event_type in {"belief_created", "belief_superseded"} and not payload.get("derivation"):
                add(f"event {row_id} {event_type} has empty derivation")
            if event_type == "contradiction_detected" and not (
                payload.get("belief_id") or payload.get("claim_key")
            ):
                add(f"event {row_id} contradiction_detected needs belief_id or claim_key")
            if event_type in {"experience_recorded", "state_changed", "rule_proposed"} and not payload.get("derivation"):
                add(f"event {row_id} {event_type} has empty derivation")
            if event_type == "rule_activated":
                if not payload.get("derivation"):
                    add(f"event {row_id} rule_activated has empty derivation")
                mark_once("rule", payload["rule_key"], f"rule {payload['rule_key']} activated more than once")
            if event_type == "constraint_checked" and payload["result"] not in {"pass", "violation"}:
                add(f"event {row_id} constraint_checked has invalid result")
            if event_type == "policy_evaluated" and payload["result"] not in {"pass", "block"}:
                add(f"event {row_id} policy_evaluated has invalid result")
            if event_type == "governance_decision":
                if payload["decision"] not in {"allowed", "blocked"}:
                    add(f"event {row_id} governance_decision has invalid decision")
                if payload["action"] not in {"proposal.review", "rule.activate", "operation.recovery"}:
                    add(f"event {row_id} governance_decision has invalid action")
                if payload["target_type"] not in {"proposal", "operation_recovery"}:
                    add(f"event {row_id} governance_decision has invalid target_type")
            if event_type == "operation_check_recorded":
                if payload["status"] not in {"ok", "fail"}:
                    add(f"event {row_id} operation_check_recorded has invalid status")
                if not payload.get("derivation"):
                    add(f"event {row_id} operation_check_recorded has empty derivation")
                if not payload.get("target"):
                    add(f"event {row_id} operation_check_recorded has empty target")
            if event_type == "operation_recovery_attempted":
                if payload["action"] not in {"restart_network", "reboot"}:
                    add(f"event {row_id} operation_recovery_attempted has invalid action")
                if not payload.get("derivation"):
                    add(f"event {row_id} operation_recovery_attempted has empty derivation")
            if event_type == "operation_recovery_result":
                if payload["result"] not in {"succeeded", "failed", "scheduled"}:
                    add(f"event {row_id} operation_recovery_result has invalid result")
                if not payload.get("derivation"):
                    add(f"event {row_id} operation_recovery_result has empty derivation")
            if event_type == sealing.EPOCH_EVENT:
                if payload["algo"] != sealing.ALGO:
                    add(f"event {row_id} ledger_epoch_opened has invalid algo")
                if not isinstance(payload["genesis_digest"], str):
                    add(f"event {row_id} ledger_epoch_opened has invalid genesis_digest")
                try:
                    prefix_count = int(payload["prefix_count"])
                    prefix_max = int(payload["prefix_max_id"])
                except (TypeError, ValueError):
                    add(f"event {row_id} ledger_epoch_opened has invalid prefix values")
                else:
                    if prefix_count < 0:
                        add(f"event {row_id} ledger_epoch_opened has invalid prefix_count")
                    if prefix_max < 0:
                        add(f"event {row_id} ledger_epoch_opened has invalid prefix_max_id")
            if event_type == "proposal_reviewed":
                if payload["decision"] not in {"accepted", "rejected"}:
                    add(f"event {row_id} proposal_reviewed has invalid decision")
                mark_once("proposal", payload["proposal_id"], f"proposal {payload['proposal_id']} reviewed more than once")
            if event_type == "inquiry_resolved":
                if not str(payload["answer"]).strip():
                    add(f"event {row_id} inquiry_resolved has empty answer")
                mark_once("inquiry", payload["inquiry_id"], f"inquiry {payload['inquiry_id']} resolved more than once")
            if event_type == "inquiries_reconciled":
                inquiry_ids = payload["inquiry_ids"]
                if not isinstance(inquiry_ids, list) or not inquiry_ids:
                    add(f"event {row_id} inquiries_reconciled has no inquiry ids")
                    continue
                if not str(payload["answer"]).strip():
                    add(f"event {row_id} inquiries_reconciled has empty answer")
                if len(inquiry_ids) != len(set(inquiry_ids)):
                    add(f"event {row_id} inquiries_reconciled has duplicate inquiry ids")
                for inquiry_id in inquiry_ids:
                    mark_once("inquiry", inquiry_id, f"inquiry {inquiry_id} resolved more than once")
    if processed != fence.event_count:
        add(f"event contract processed {processed}, expected {fence.event_count}")
    return issues


def _clear_projections(conn: sqlite3.Connection) -> None:
    for table in PROJECTION_TABLES:
        conn.execute(f"DELETE FROM {_quote(table)}")
    placeholders = ",".join("?" for _ in _SEQUENCE_TABLES)
    conn.execute(f"DELETE FROM sqlite_sequence WHERE name IN ({placeholders})", _SEQUENCE_TABLES)


def replay_bounded_in_txn(
    conn: sqlite3.Connection,
    fence: ReplayFence,
    batch_size: int,
    *,
    fault_after: int | None = None,
    progress: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Rebuild all projections inside, but never own, the active transaction."""
    if not conn.in_transaction:
        raise HarnessError("bounded replay requires an active caller-owned transaction")
    _clear_projections(conn)
    if progress:
        progress("targets_cleared", {"fixed_head": fence.head_id, "event_count": fence.event_count})
    processed = 0
    first_id: int | None = None
    last_id: int | None = None
    max_payload_bytes = 0
    max_batch_payload_bytes = 0
    for batch in iter_event_batches(conn, fence, batch_size):
        batch_payload_bytes = 0
        for event in batch:
            payload_bytes = len(str(event["payload"]).encode("utf-8"))
            max_payload_bytes = max(max_payload_bytes, payload_bytes)
            batch_payload_bytes += payload_bytes
            event_router.apply_event(conn, event)
            processed += 1
            event_id = int(event["id"])
            first_id = event_id if first_id is None else first_id
            last_id = event_id
            if fault_after is not None and processed == fault_after:
                raise InjectedFault(f"projector fault after event {processed}")
        max_batch_payload_bytes = max(max_batch_payload_bytes, batch_payload_bytes)
        if progress:
            progress("batch_complete", {"processed": processed, "fixed_head": fence.head_id})
    if processed != fence.event_count:
        raise HarnessError(f"bounded replay processed {processed}, expected {fence.event_count}")
    if first_id != fence.min_id or last_id != fence.head_id:
        raise HarnessError("bounded replay first/last ids differ from the fixed fence")
    if fence.head_id is not None:
        above = conn.execute("SELECT COUNT(*) FROM event_log WHERE id > ?", (fence.head_id,)).fetchone()[0]
        if above:
            raise HarnessError("writer event became visible inside fixed-head transaction")
    return {
        "processed": processed,
        "first_id": first_id,
        "last_id": last_id,
        "strictly_ordered": True,
        "exactly_once": True,
        "processed_above_fixed_head": 0,
        "max_payload_bytes": max_payload_bytes,
        "max_batch_payload_bytes": max_batch_payload_bytes,
    }


class _Sampler:
    def __init__(self, path: Path, interval_seconds: float) -> None:
        self.path = path
        self.interval_seconds = interval_seconds
        self.stop = threading.Event()
        self.peak_rss = 0
        self.highwater = {"db": 0, "wal": 0, "shm": 0, "journal": 0}
        self.samples = 0
        self._thread = threading.Thread(target=self._run, name="a03-sampler", daemon=True)

    def _sample(self) -> None:
        try:
            self.peak_rss = max(self.peak_rss, psutil.Process().memory_info().rss)
        except psutil.Error:
            pass
        paths = {
            "db": self.path,
            "wal": Path(str(self.path) + "-wal"),
            "shm": Path(str(self.path) + "-shm"),
            "journal": Path(str(self.path) + "-journal"),
        }
        for key, candidate in paths.items():
            try:
                size = candidate.stat().st_size
            except FileNotFoundError:
                size = 0
            self.highwater[key] = max(self.highwater[key], size)
        self.samples += 1

    def _run(self) -> None:
        while not self.stop.wait(self.interval_seconds):
            self._sample()

    def __enter__(self) -> _Sampler:
        self._sample()
        self._thread.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self._sample()
        self.stop.set()
        self._thread.join(timeout=max(1.0, self.interval_seconds * 4))
        self._sample()


def _open_existing(path: Path, *, timeout_seconds: float = 5.0) -> sqlite3.Connection:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    conn = sqlite3.connect(
        resolved.as_uri() + "?mode=rw", uri=True, timeout=timeout_seconds,
        isolation_level=None,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(f"PRAGMA busy_timeout={max(0, round(timeout_seconds * 1000))}")
    return conn


def run_option_b(
    database_path: Path | str,
    *,
    disposable_root: Path | str,
    batch_size: int,
    expected_projection_digests: Mapping[str, str] | None = None,
    expected_projection_set_sha256: str | None = None,
    fault_after: int | None = None,
    timeout_seconds: float = 5.0,
    sample_interval_seconds: float = 0.02,
    progress: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Measure the experimental Option-B topology on an existing disposable DB."""
    safety = validate_disposable_target(database_path, disposable_root)
    path = safety.database_path
    started = time.perf_counter_ns()
    conn: sqlite3.Connection | None = None
    outcome = "rolled_back"
    committed = False
    with _Sampler(path, sample_interval_seconds) as sampler:
        try:
            conn = _open_existing(path, timeout_seconds=timeout_seconds)
            conn.execute("BEGIN IMMEDIATE")
            if progress:
                progress("txn_started", {})
            fence = capture_fence(conn)
            if progress:
                progress("head_captured", asdict(fence))
            ledger_before = stream_ledger_binding(conn, fence, batch_size)
            projections_before = stream_projection_digests(conn, batch_size)
            replay = replay_bounded_in_txn(conn, fence, batch_size, fault_after=fault_after, progress=progress)
            schema_issues = integrity.validate_schema(conn)
            contract_issues = validate_event_contract_bounded(conn, fence, batch_size)
            seal_issues = verify_chain_bounded(conn, fence, batch_size)
            projections_after = stream_projection_digests(conn, batch_size)
            ledger_after = stream_ledger_binding(conn, fence, batch_size)
            if ledger_after != ledger_before:
                raise HarnessError("ledger changed during replay")
            if schema_issues or contract_issues or seal_issues:
                raise HarnessError(
                    "pre-commit integrity failed: "
                    + "; ".join((schema_issues + contract_issues + seal_issues)[:10])
                )
            expected_digests = (
                dict(expected_projection_digests)
                if expected_projection_digests is not None
                else projections_before["digests"]
            )
            expected_set = (
                expected_projection_set_sha256
                if expected_projection_set_sha256 is not None
                else projections_before["digest_set_sha256"]
            )
            if (
                projections_after["digests"] != expected_digests
                or projections_after["digest_set_sha256"] != expected_set
            ):
                raise OracleMismatch("rebuilt projections differ from expected digests")
            if progress:
                progress("pre_commit", {"processed": replay["processed"]})
            conn.commit()
            outcome = "committed"
            committed = True
            if progress:
                try:
                    progress("commit_returned", {})
                except BaseException as exc:
                    raise PostCommitProgressError(
                        "post-commit progress callback failed after a successful commit"
                    ) from exc
        except BaseException:
            if not committed and conn is not None and conn.in_transaction:
                conn.rollback()
            raise
        finally:
            if conn is not None:
                conn.close()
    duration = (time.perf_counter_ns() - started) / 1_000_000_000
    return {
        "schema": RECEIPT_SCHEMA,
        "runtime": {
            "platform": platform.system(),
            "platform_release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
            "implementation": sys.implementation.name,
        },
        "source": {"label": path.name, "absolute_path_logged": False},
        "topology": "option-b-experimental-single-transaction",
        "event_count": fence.event_count,
        "fixed_head": fence.head_id,
        "batch_size": batch_size,
        "duration_seconds": duration,
        "peak_rss_bytes": sampler.peak_rss,
        "storage_highwater_bytes": dict(sampler.highwater),
        "sample_interval_seconds": sample_interval_seconds,
        "samples": sampler.samples,
        "replay": replay,
        "ledger_before": ledger_before,
        "ledger_after": ledger_after,
        "projection_before": projections_before,
        "projection_after": projections_after,
        "integrity": {
            "schema_issues": schema_issues,
            "event_contract_issues": contract_issues,
            "seal_issues": seal_issues,
            "ok": not (schema_issues or contract_issues or seal_issues),
            "bounded_prototype": True,
            "production_integrity_called": False,
        },
        "anchor": {"state": "not_supplied"},
        "outcome": outcome,
        "payloads_logged": False,
        "safety": safety.receipt(),
        "product_path_activated": safety.product_path_match,
    }


def _timestamp(event_id: int) -> str:
    value = datetime(2030, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=event_id)
    return value.isoformat(timespec="microseconds")


def _pad_payload(payload: dict[str, Any], payload_bytes: int) -> dict[str, Any]:
    base = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    padding = max(0, payload_bytes - len(base.encode("utf-8")) - 13)
    if padding:
        payload["padding"] = "x" * padding
    return payload


def _synthetic_event(
    event_id: int,
    payload_bytes: int,
    seed: int,
) -> tuple[str, dict[str, Any]]:
    """Return a deterministic projected/raw mix with coherent references."""
    source = f"synthetic.source.{(event_id + seed) % 17}"
    cycle = (event_id - 2) % 4
    if cycle == 0:
        event_type = "assertion_recorded"
        payload: dict[str, Any] = {
            "claim_key": f"synthetic.metric.{(event_id + seed) % 257}",
            "claim_value": event_id,
            "derivation": "experiment:a0_3a:v1",
            "source": source,
        }
    elif cycle == 1:
        event_type = "observation_created"
        payload = {
            "raw_value": event_id,
            "source": source,
            "unit": "synthetic",
        }
    elif cycle == 2:
        event_type = "evidence_recorded"
        payload = {
            "metric_key": f"synthetic.metric.{(event_id + seed) % 257}",
            "metric_value": event_id,
            "observation_id": event_id - 1,
            "source": source,
        }
    else:
        event_type = "relation_asserted"
        payload = {
            "subject": f"synthetic.node.{event_id:09d}.a",
            "predicate": "verwandt",
            "object": f"synthetic.node.{event_id:09d}.b",
            "source": source,
            "derivation": "experiment:a0_3a:v1",
        }
    return event_type, _pad_payload(payload, payload_bytes)


def generate_synthetic_database(
    database_path: Path | str,
    spec: SyntheticSpec,
    *,
    disposable_root: Path | str,
) -> dict[str, Any]:
    """Create a deterministic Current-schema test DB without an unbounded setup list."""
    location = _inspect_disposable_location(
        database_path, disposable_root, require_database=False
    )
    path = location.database_path
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter_ns()
    conn = db.connect(path)
    conn.execute("PRAGMA synchronous=OFF")
    inserted = 0
    previous_seal: str | None = None
    relation_id = 0
    try:
        if spec.event_count:
            genesis = hashlib.sha256(sealing.GENESIS_SEED.encode("utf-8")).hexdigest()
            epoch_payload = {
                "algo": sealing.ALGO,
                "genesis_digest": genesis,
                "prefix_count": 0,
                "prefix_max_id": 0,
            }
            epoch_text = json.dumps(epoch_payload, sort_keys=True, separators=(",", ":"))
            previous_seal = sealing.compute_seal(genesis, sealing.EPOCH_EVENT, epoch_text)
            conn.execute(
                "INSERT INTO event_log(id,event_type,payload,created_at,prev_seal,seal) VALUES (?,?,?,?,?,?)",
                (1, sealing.EPOCH_EVENT, epoch_text, _timestamp(1), genesis, previous_seal),
            )
            inserted = 1
        next_id = 2
        while next_id <= spec.event_count:
            stop = min(spec.event_count + 1, next_id + spec.batch_size)
            event_rows: list[tuple[Any, ...]] = []
            projection_rows: list[tuple[Any, ...]] = []
            relation_rows: list[tuple[Any, ...]] = []
            for event_id in range(next_id, stop):
                event_type, payload = _synthetic_event(
                    event_id, spec.payload_bytes, spec.seed
                )
                payload_text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                created_at = _timestamp(event_id)
                if previous_seal is None:
                    raise HarnessError("sealed synthetic stream lost its previous seal")
                seal = sealing.compute_seal(previous_seal, event_type, payload_text)
                event_rows.append(
                    (event_id, event_type, payload_text, created_at, previous_seal, seal)
                )
                if event_type == "assertion_recorded":
                    projection_rows.append(
                        (
                            event_id, payload["claim_key"], payload["claim_value"],
                            payload["source"], created_at,
                        )
                    )
                elif event_type == "evidence_recorded":
                    projection_rows.append(
                        (
                            event_id, payload["metric_key"], payload["metric_value"],
                            payload["source"], created_at,
                        )
                    )
                elif event_type == "relation_asserted":
                    relation_id += 1
                    relation_rows.append(
                        (
                            relation_id, payload["subject"], payload["predicate"],
                            payload["object"], payload["source"], payload["derivation"],
                            created_at, created_at,
                        )
                    )
                previous_seal = seal
            conn.executemany(
                "INSERT INTO event_log(id,event_type,payload,created_at,prev_seal,seal) VALUES (?,?,?,?,?,?)",
                event_rows,
            )
            conn.executemany(
                "INSERT INTO value_projection(event_id,claim_key,value,source,created_at) VALUES (?,?,?,?,?)",
                projection_rows,
            )
            conn.executemany(
                "INSERT INTO relation_projection(id,subject,predicate,object,source,derivation,created_at,last_updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                relation_rows,
            )
            conn.commit()
            inserted += len(event_rows)
            next_id = stop
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()
    register_disposable_database(path, disposable_root)
    verify = _open_existing(path)
    try:
        verify.execute("BEGIN")
        fence = capture_fence(verify)
        ledger = stream_ledger_binding(verify, fence, spec.batch_size)
        projections = stream_projection_digests(verify, spec.batch_size)
        seal_issues = verify_chain_bounded(verify, fence, spec.batch_size)
        verify.commit()
    finally:
        verify.close()
    if inserted != spec.event_count or seal_issues:
        raise HarnessError(f"synthetic generation failed: inserted={inserted}, seal_issues={seal_issues}")
    return {
        "schema": "genus-a0-3a-synthetic-generation-v1",
        "runtime": {
            "platform": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
        },
        "event_count": spec.event_count,
        "batch_size": spec.batch_size,
        "payload_target_bytes": spec.payload_bytes,
        "duration_seconds": (time.perf_counter_ns() - started) / 1_000_000_000,
        "ledger": ledger,
        "projections": projections,
        "database_bytes": path.stat().st_size,
        "payloads_logged": False,
    }


def file_snapshot(path: Path | str) -> dict[str, Any]:
    """Hash a small fixture file and capture exact mutation/sidecar evidence."""
    resolved = Path(path).resolve()
    stat = resolved.stat()
    digest = hashlib.sha256()
    with resolved.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return {
        "bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": digest.hexdigest(),
        "sidecars": {
            suffix: Path(str(resolved) + suffix).exists()
            for suffix in ("-wal", "-shm", "-journal")
        },
    }


def rehydrate_historical_copy(
    historical_path: Path | str,
    current_path: Path | str,
    *,
    disposable_root: Path | str,
    batch_size: int,
) -> dict[str, Any]:
    """Export events read-only into a fresh Current DB; this is not a migration."""
    source_safety = validate_disposable_target(historical_path, disposable_root)
    source_path = source_safety.database_path
    target_location = _inspect_disposable_location(
        current_path, disposable_root, require_database=False
    )
    target_path = target_location.database_path
    before = file_snapshot(source_path)
    source = sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True, isolation_level=None)
    source.row_factory = sqlite3.Row
    source.execute("PRAGMA query_only=ON")
    if source.execute("PRAGMA query_only").fetchone()[0] != 1:
        source.close()
        raise HarnessError("historical source is not query_only")
    if target_path.exists():
        source.close()
        raise FileExistsError(target_path)
    target = db.connect(target_path)
    copied = 0
    try:
        cursor = source.execute(
            "SELECT id,event_type,payload,created_at,prev_seal,seal FROM event_log ORDER BY id"
        )
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            target.executemany(
                "INSERT INTO event_log(id,event_type,payload,created_at,prev_seal,seal) VALUES (?,?,?,?,?,?)",
                [tuple(row[column] for column in EVENT_COLUMNS) for row in rows],
            )
            copied += len(rows)
        target.commit()
        target.execute("BEGIN IMMEDIATE")
        fence = capture_fence(target)
        replay_bounded_in_txn(target, fence, batch_size)
        target.commit()
    except BaseException:
        if target.in_transaction:
            target.rollback()
        raise
    finally:
        target.close()
        source.close()
    register_disposable_database(target_path, disposable_root)
    after = file_snapshot(source_path)
    if before != after:
        raise HarnessError("historical source changed during read-only export")
    return {
        "schema": "genus-a0-3a-historical-rehydration-v1",
        "method": "historical_export_to_disposable_current",
        "events_copied": copied,
        "source_unchanged": True,
        "source_sidecars_absent": not any(after["sidecars"].values()),
        "migration_claimed": False,
    }


def write_receipt(path: Path | str, receipt: Mapping[str, Any]) -> None:
    """Write one aggregate-only receipt outside product paths."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(
        _normalize_json(dict(receipt)), ensure_ascii=True, sort_keys=True,
        indent=2, allow_nan=False,
    ) + "\n"
    target.write_text(encoded, encoding="utf-8", newline="\n")
