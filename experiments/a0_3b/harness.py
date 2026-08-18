"""A0.3b same-file shadow generation and atomic cutover prototype.

This module is experimental evidence, not a product integration.  Every writable
entry point first reuses the A0.3a fail-closed disposable-target guard.  G1 is the
canonical set of twelve projection tables; G2 and the independent verifier are
physical, prefixed clones in the *same* disposable SQLite database.  Shadow
batches commit independently.  The final fence applies only a bounded tail to
both already-equal candidate generations and atomically changes one metadata
pointer.

Receipts contain aggregate measurements only.  They never contain event payloads
or absolute database paths.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import sqlite3
import sys
import threading
import time
import uuid
from collections import deque
from contextlib import AbstractContextManager, contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from itertools import zip_longest
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

import psutil

from experiments.a0_3a import harness as a03a
from genus import event_router, ledger, schema_detection, sealing


RECEIPT_SCHEMA = "genus-a0-3b-shadow-cutover-receipt-v1"
METADATA_SCHEMA = "genus-a0-3b-generation-metadata-v1"
BATCH_RECEIPT_SCHEMA = "genus-a0-3b-apply-receipt-v1"
SEQUENCE_DIGEST_SCHEMA = "genus-a0-3b-sequence-set-v1"
SYNC_PROOF_SCHEMA = "genus-a0-3b-routed-sync-proof-v1"
WRITE_TRANSACTION_RECEIPT_SCHEMA = "genus-a0-3b-write-transactions-v1"

DEFAULT_BATCH_EVENTS = 1_024
DEFAULT_BATCH_BYTES = 4 * 1024 * 1024
DEFAULT_FINAL_TAIL_EVENTS = 2_048
DEFAULT_FINAL_TAIL_BYTES = 8 * 1024 * 1024
MAX_BATCH_EVENTS = 8_192
MAX_BATCH_BYTES = 16 * 1024 * 1024
INTER_BATCH_WRITER_YIELD_SECONDS = 0.001
INTER_BATCH_WRITER_HANDOFF_TIMEOUT_SECONDS = 0.5

RSS_BUDGET_BYTES = 256 * 1024 * 1024
WAL_BUDGET_BYTES = 256 * 1024 * 1024
WRITER_BLOCK_BUDGET_SECONDS = 2.0
RECOVERY_BUDGET_SECONDS = 10.0
REBUILD_BUDGET_SECONDS = 180.0
MAX_WRITER_TELEMETRY_SAMPLES = 100_000
MAX_READER_TELEMETRY_SAMPLES = 100_000
MAX_FAILURE_TELEMETRY_SAMPLES = 1_024
MAX_PERSISTENT_RECEIPTS = 5_000_000

PROJECTION_TABLES = tuple(a03a.PROJECTION_TABLES)
PROJECTION_SPECS = a03a.PROJECTION_SPECS
SEQUENCE_TABLES = (
    "belief_projection",
    "experience_log",
    "governance_log",
    "inquiry_log",
    "operation_log",
    "proposal_log",
    "relation_projection",
    "rule_projection",
    "state_projection",
)
GENERATION_STATES = frozenset(
    {"building", "catching_up", "verified", "active", "retired"}
)
METADATA_TABLES = (
    "a03b_control",
    "a03b_generation",
    "a03b_projection_target",
    "a03b_apply_receipt",
    "a03b_verification",
    "a03b_operation_lock",
    "a03b_sync_session",
)
_TOKEN = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


class ShadowHarnessError(RuntimeError):
    """A fail-closed A0.3b invariant was violated."""


class SchemaInventoryError(ShadowHarnessError):
    """The disposable database no longer has the exact extended schema."""


class CutoverNotReady(ShadowHarnessError):
    """The verified shadow cannot safely cross the final fence."""


class InjectedFault(ShadowHarnessError):
    """A deterministic test fault was injected at a named phase."""


class PostCommitFault(ShadowHarnessError):
    """A callback failed after a transaction was durably committed."""


@dataclass(frozen=True)
class HeadFence:
    head_id: int | None
    event_count: int
    head_seal: str | None


@dataclass(frozen=True)
class BatchMeasurement:
    generation_id: str
    phase: str
    first_event_id: int | None
    last_event_id: int | None
    event_count: int
    payload_bytes: int
    transaction_seconds: float
    receipt_sha256: str


class BatchAggregate:
    """Bounded in-memory batch telemetry; full receipts remain in SQLite."""

    SAMPLE_LIMIT = 32

    def __init__(self) -> None:
        self.batch_count = 0
        self.processed_events = 0
        self.max_transaction_seconds = 0.0
        self.auxiliary_transaction_count = 0
        self.max_auxiliary_transaction_seconds = 0.0
        self.writer_yield_count = 0
        self.writer_yield_total_seconds = 0.0
        self.writer_yield_max_seconds = 0.0
        self.writer_yield_strategies: set[str] = set()
        self.first: list[BatchMeasurement] = []
        self.last: deque[BatchMeasurement] = deque(maxlen=self.SAMPLE_LIMIT)

    def add(self, item: BatchMeasurement) -> None:
        self.batch_count += 1
        self.processed_events += item.event_count
        self.max_transaction_seconds = max(
            self.max_transaction_seconds, item.transaction_seconds
        )
        if len(self.first) < self.SAMPLE_LIMIT:
            self.first.append(item)
        else:
            self.last.append(item)

    def merge(self, other: "BatchAggregate") -> None:
        self.batch_count += other.batch_count
        self.processed_events += other.processed_events
        self.max_transaction_seconds = max(
            self.max_transaction_seconds, other.max_transaction_seconds
        )
        self.auxiliary_transaction_count += other.auxiliary_transaction_count
        self.max_auxiliary_transaction_seconds = max(
            self.max_auxiliary_transaction_seconds,
            other.max_auxiliary_transaction_seconds,
        )
        self.writer_yield_count += other.writer_yield_count
        self.writer_yield_total_seconds += other.writer_yield_total_seconds
        self.writer_yield_max_seconds = max(
            self.writer_yield_max_seconds,
            other.writer_yield_max_seconds,
        )
        self.writer_yield_strategies.update(other.writer_yield_strategies)
        for item in other.first:
            if len(self.first) < self.SAMPLE_LIMIT:
                self.first.append(item)
            else:
                self.last.append(item)
        for item in other.last:
            self.last.append(item)

    def add_auxiliary(self, transaction_seconds: float) -> None:
        self.auxiliary_transaction_count += 1
        self.max_auxiliary_transaction_seconds = max(
            self.max_auxiliary_transaction_seconds, transaction_seconds
        )

    def add_writer_yield(self, yield_seconds: float, *, strategy: str) -> None:
        self.writer_yield_count += 1
        self.writer_yield_total_seconds += yield_seconds
        self.writer_yield_max_seconds = max(self.writer_yield_max_seconds, yield_seconds)
        self.writer_yield_strategies.add(strategy)

    def writer_yield_receipt(self) -> dict[str, Any]:
        strategy = (
            next(iter(self.writer_yield_strategies))
            if len(self.writer_yield_strategies) == 1
            else ("none" if not self.writer_yield_strategies else "mixed")
        )
        return {
            "strategy": strategy,
            "fallback_yield_seconds_per_batch": (
                INTER_BATCH_WRITER_YIELD_SECONDS
                if strategy == "bounded-scheduler-yield"
                else None
            ),
            "count": self.writer_yield_count,
            "total_seconds": self.writer_yield_total_seconds,
            "max_seconds": self.writer_yield_max_seconds,
            "outside_transactions": True,
        }

    @property
    def max_write_transaction_seconds(self) -> float:
        return max(
            self.max_transaction_seconds, self.max_auxiliary_transaction_seconds
        )

    def receipt_samples(self) -> list[dict[str, Any]]:
        items = list(self.first)
        known = {item.receipt_sha256 for item in items}
        items.extend(item for item in self.last if item.receipt_sha256 not in known)
        return [asdict(item) for item in items]


def _yield_to_competing_writer(conn: sqlite3.Connection) -> float:
    """Give a waiting SQLite writer one bounded scheduling opportunity."""
    if conn.in_transaction:
        raise ShadowHarnessError("writer handoff must occur outside a transaction")
    started = time.perf_counter_ns()
    time.sleep(INTER_BATCH_WRITER_YIELD_SECONDS)
    elapsed = (time.perf_counter_ns() - started) / 1_000_000_000
    if conn.in_transaction:
        raise ShadowHarnessError("writer handoff opened a transaction")
    return elapsed


def _combined_writer_yield_receipt(
    *aggregates: BatchAggregate,
) -> dict[str, Any]:
    combined = BatchAggregate()
    for aggregate in aggregates:
        combined.merge(aggregate)
    return combined.writer_yield_receipt()


@dataclass(frozen=True)
class GenerationStatus:
    generation_id: str
    role: str
    state: str
    built_through_event_id: int | None
    verified_through_event_id: int | None
    full_digest_verified_through_event_id: int | None
    built_event_count: int
    built_head_seal: str | None
    projection_digest_set_sha256: str | None
    sequence_digest_sha256: str


@dataclass(frozen=True)
class RecoveryReceipt:
    classification: str
    active_generation_id: str
    duration_seconds: float
    extended_schema_valid: bool
    writer_ready: bool
    reader_ready: bool


@dataclass(frozen=True)
class ReceiptChainState:
    generation_id: str
    last_batch_no: int
    last_receipt_sha256: str | None
    receipt_count: int


class _WriteTxnCollector:
    """Bounded aggregate evidence for every experimental writer transaction."""

    def __init__(self, scope: str):
        self.scope = scope
        self.attempt_count = 0
        self.transaction_count = 0
        self.committed_count = 0
        self.rolled_back_count = 0
        self.begin_error_count = 0
        self.open_transaction_count = 0
        self.max_transaction_seconds = 0.0
        self.max_lock_wait_seconds = 0.0
        self._phases: dict[str, dict[str, int | float]] = {}
        self._lock = threading.Lock()

    def _phase(self, phase: str) -> dict[str, int | float]:
        return self._phases.setdefault(
            phase,
            {
                "attempt_count": 0,
                "transaction_count": 0,
                "committed_count": 0,
                "rolled_back_count": 0,
                "begin_error_count": 0,
                "max_transaction_seconds": 0.0,
                "max_lock_wait_seconds": 0.0,
            },
        )

    def attempted(self, phase: str) -> None:
        with self._lock:
            self.attempt_count += 1
            self._phase(phase)["attempt_count"] += 1

    def opened(self, phase: str, lock_wait_seconds: float) -> None:
        with self._lock:
            self.transaction_count += 1
            self.open_transaction_count += 1
            self.max_lock_wait_seconds = max(
                self.max_lock_wait_seconds, lock_wait_seconds
            )
            values = self._phase(phase)
            values["transaction_count"] += 1
            values["max_lock_wait_seconds"] = max(
                float(values["max_lock_wait_seconds"]), lock_wait_seconds
            )

    def begin_error(self, phase: str, wait_seconds: float) -> None:
        with self._lock:
            self.begin_error_count += 1
            self.max_lock_wait_seconds = max(self.max_lock_wait_seconds, wait_seconds)
            values = self._phase(phase)
            values["begin_error_count"] += 1
            values["max_lock_wait_seconds"] = max(
                float(values["max_lock_wait_seconds"]), wait_seconds
            )

    def finished(
        self,
        phase: str,
        *,
        committed: bool,
        transaction_seconds: float,
    ) -> None:
        with self._lock:
            self.open_transaction_count -= 1
            if committed:
                self.committed_count += 1
            else:
                self.rolled_back_count += 1
            self.max_transaction_seconds = max(
                self.max_transaction_seconds, transaction_seconds
            )
            values = self._phase(phase)
            key = "committed_count" if committed else "rolled_back_count"
            values[key] += 1
            values["max_transaction_seconds"] = max(
                float(values["max_transaction_seconds"]), transaction_seconds
            )

    def receipt(self, *, exhaustive: bool = True) -> dict[str, Any]:
        with self._lock:
            phases = {
                phase: dict(values) for phase, values in sorted(self._phases.items())
            }
            complete = bool(
                self.open_transaction_count == 0
                and self.attempt_count
                == self.transaction_count + self.begin_error_count
                and self.transaction_count
                == self.committed_count + self.rolled_back_count
            )
            passed = bool(
                exhaustive
                and complete
                and self.begin_error_count == 0
                and self.max_transaction_seconds
                <= WRITER_BLOCK_BUDGET_SECONDS
            )
            return {
                "schema": WRITE_TRANSACTION_RECEIPT_SCHEMA,
                "scope": self.scope,
                "exhaustive": exhaustive,
                "evidence_complete": complete,
                "attempt_count": self.attempt_count,
                "transaction_count": self.transaction_count,
                "committed_count": self.committed_count,
                "rolled_back_count": self.rolled_back_count,
                "begin_error_count": self.begin_error_count,
                "open_transaction_count": self.open_transaction_count,
                "phase_stats": phases,
                "phase_max_transaction_seconds": {
                    phase: float(values["max_transaction_seconds"])
                    for phase, values in phases.items()
                },
                "overall_max_transaction_seconds": self.max_transaction_seconds,
                "overall_max_seconds": self.max_transaction_seconds,
                "max_lock_wait_seconds": self.max_lock_wait_seconds,
                "limit_seconds": WRITER_BLOCK_BUDGET_SECONDS,
                "pass": passed,
            }


class _WriteTransaction:
    def __init__(
        self,
        conn: sqlite3.Connection,
        collector: _WriteTxnCollector,
        phase: str,
        *,
        begin: bool = True,
    ):
        self.conn = conn
        self.collector = collector
        self.phase = phase
        self.attempt_ns = time.perf_counter_ns()
        self.lock_ns = self.attempt_ns
        self.finished_ns: int | None = None
        self.committed = False
        self.closed = False
        collector.attempted(phase)
        if begin:
            try:
                conn.execute("BEGIN IMMEDIATE")
            except BaseException:
                collector.begin_error(
                    phase,
                    (time.perf_counter_ns() - self.attempt_ns) / 1_000_000_000,
                )
                raise
            self.lock_ns = time.perf_counter_ns()
        collector.opened(
            phase, (self.lock_ns - self.attempt_ns) / 1_000_000_000
        )

    @property
    def transaction_seconds(self) -> float:
        end = time.perf_counter_ns() if self.finished_ns is None else self.finished_ns
        return (end - self.lock_ns) / 1_000_000_000

    @property
    def lock_wait_seconds(self) -> float:
        return (self.lock_ns - self.attempt_ns) / 1_000_000_000

    def commit(self) -> None:
        if self.closed:
            return
        try:
            self.conn.commit()
        except BaseException:
            if self.conn.in_transaction:
                self.conn.rollback()
            self._finish(committed=False)
            raise
        self._finish(committed=True)

    def rollback(self) -> None:
        if self.closed:
            return
        if self.conn.in_transaction:
            self.conn.rollback()
        self._finish(committed=False)

    def _finish(self, *, committed: bool) -> None:
        self.finished_ns = time.perf_counter_ns()
        self.closed = True
        self.committed = committed
        self.collector.finished(
            self.phase,
            committed=committed,
            transaction_seconds=self.transaction_seconds,
        )


@contextmanager
def _measured_write(
    conn: sqlite3.Connection,
    collector: _WriteTxnCollector,
    phase: str,
) -> Iterator[_WriteTransaction]:
    transaction = _WriteTransaction(conn, collector, phase)
    try:
        yield transaction
    except BaseException:
        transaction.rollback()
        raise
    else:
        transaction.commit()


def _merge_write_transaction_receipts(
    scope: str, receipts: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    phase_stats: dict[str, dict[str, int | float]] = {}
    counts = {
        "attempt_count": 0,
        "transaction_count": 0,
        "committed_count": 0,
        "rolled_back_count": 0,
        "begin_error_count": 0,
        "open_transaction_count": 0,
    }
    max_transaction = 0.0
    max_lock_wait = 0.0
    evidence_complete = True
    for receipt in receipts:
        evidence_complete = bool(
            evidence_complete
            and receipt.get("schema") == WRITE_TRANSACTION_RECEIPT_SCHEMA
            and receipt.get("exhaustive") is True
            and receipt.get("evidence_complete") is True
        )
        for key in counts:
            counts[key] += int(receipt.get(key, 0))
        max_transaction = max(
            max_transaction,
            float(receipt.get("overall_max_transaction_seconds", 0.0)),
        )
        max_lock_wait = max(
            max_lock_wait, float(receipt.get("max_lock_wait_seconds", 0.0))
        )
        raw_phases = receipt.get("phase_stats", {})
        if not isinstance(raw_phases, Mapping):
            evidence_complete = False
            continue
        for phase, raw_values in raw_phases.items():
            if not isinstance(raw_values, Mapping):
                evidence_complete = False
                continue
            values = phase_stats.setdefault(
                str(phase),
                {
                    "attempt_count": 0,
                    "transaction_count": 0,
                    "committed_count": 0,
                    "rolled_back_count": 0,
                    "begin_error_count": 0,
                    "max_transaction_seconds": 0.0,
                    "max_lock_wait_seconds": 0.0,
                },
            )
            for key in (
                "attempt_count",
                "transaction_count",
                "committed_count",
                "rolled_back_count",
                "begin_error_count",
            ):
                values[key] += int(raw_values.get(key, 0))
            for key in ("max_transaction_seconds", "max_lock_wait_seconds"):
                values[key] = max(
                    float(values[key]), float(raw_values.get(key, 0.0))
                )
    evidence_complete = bool(
        evidence_complete
        and counts["open_transaction_count"] == 0
        and counts["attempt_count"]
        == counts["transaction_count"] + counts["begin_error_count"]
        and counts["transaction_count"]
        == counts["committed_count"] + counts["rolled_back_count"]
    )
    passed = bool(
        evidence_complete
        and counts["begin_error_count"] == 0
        and max_transaction <= WRITER_BLOCK_BUDGET_SECONDS
    )
    receipt = {
        "schema": WRITE_TRANSACTION_RECEIPT_SCHEMA,
        "scope": scope,
        "exhaustive": evidence_complete,
        "evidence_complete": evidence_complete,
        **counts,
        "phase_stats": {phase: phase_stats[phase] for phase in sorted(phase_stats)},
        "phase_max_transaction_seconds": {
            phase: float(phase_stats[phase]["max_transaction_seconds"])
            for phase in sorted(phase_stats)
        },
        "overall_max_transaction_seconds": max_transaction,
        "overall_max_seconds": max_transaction,
        "max_lock_wait_seconds": max_lock_wait,
        "limit_seconds": WRITER_BLOCK_BUDGET_SECONDS,
        "pass": passed,
    }
    if evidence_complete:
        receipt["claim"] = "all_experimental_write_transactions"
    return receipt


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def sqlite_wal_reset_gate(version: str) -> dict[str, Any]:
    """Fail-closed live-eligibility gate for SQLite's documented WAL-reset fix.

    The 3.44 and 3.50 maintained branches received explicit backports; the main
    line is fixed at 3.51.3.  Other versions are deliberately *unconfirmed* even
    though disposable-copy experiments remain useful.
    """
    try:
        parts = tuple(int(part) for part in version.split("."))
        if len(parts) != 3:
            raise ValueError
    except (TypeError, ValueError):
        parts = ()
    confirmed = bool(
        parts
        and (
            parts >= (3, 51, 3)
            or ((3, 50, 7) <= parts < (3, 51, 0))
            or ((3, 44, 6) <= parts < (3, 45, 0))
        )
    )
    return {
        "sqlite_version": version,
        "wal_reset_fix": "confirmed" if confirmed else "unconfirmed",
        "live_eligibility": confirmed,
        "copy_experiment_allowed": True,
        "source": "sqlite-wal-documentation-2026",
    }


def _quote(identifier: str) -> str:
    if not _TOKEN.fullmatch(identifier) and identifier not in PROJECTION_TABLES:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,127}", identifier):
            raise ShadowHarnessError(f"unsafe SQLite identifier: {identifier!r}")
    return '"' + identifier.replace('"', '""') + '"'


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _open(path: Path, *, timeout_seconds: float = 5.0) -> sqlite3.Connection:
    resolved = path.resolve(strict=True)
    conn = sqlite3.connect(
        resolved.as_uri() + "?mode=rw",
        uri=True,
        isolation_level=None,
        timeout=timeout_seconds,
    )
    conn.row_factory = sqlite3.Row
    # Projection triggers are fail-closed.  Harness-owned replay transactions
    # temporarily replace this function with a narrowly scoped allow-list;
    # arbitrary sqlite connections do not have the function at all.
    conn.create_function("a03b_projection_write_allowed", 1, lambda _table: 0)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(f"PRAGMA busy_timeout={max(0, round(timeout_seconds * 1000))}")
    return conn


def _require_wal(conn: sqlite3.Connection, operation: str) -> None:
    mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
    if mode != "wal":
        raise ShadowHarnessError(f"{operation} requires WAL mode, got {mode}")


def _safety_path(
    database_path: Path | str, disposable_root: Path | str
) -> tuple[Path, dict[str, Any]]:
    evidence = a03a.validate_disposable_target(database_path, disposable_root)
    return evidence.database_path, evidence.receipt()


def _token(generation_id: str) -> str:
    if not _TOKEN.fullmatch(generation_id):
        raise ShadowHarnessError("generation_id is outside the fixed identifier domain")
    return generation_id


def _require_batch_caps(batch_events: int, batch_bytes: int | None = None) -> None:
    if not 1 <= batch_events <= MAX_BATCH_EVENTS:
        raise ShadowHarnessError(
            "batch event configuration exceeds the hard cap; "
            "hard boundedness caps are mandatory"
        )
    if batch_bytes is not None and not 1 <= batch_bytes <= MAX_BATCH_BYTES:
        raise ShadowHarnessError(
            "batch byte configuration exceeds the hard cap; "
            "hard boundedness caps are mandatory"
        )


def _physical_table(generation_id: str, logical_table: str) -> str:
    _token(generation_id)
    if logical_table not in PROJECTION_TABLES:
        raise ShadowHarnessError(f"unknown projection target: {logical_table}")
    return logical_table if generation_id == "g1" else f"a03b_{generation_id}__{logical_table}"


def _table_map(generation_id: str) -> dict[str, str]:
    return {table: _physical_table(generation_id, table) for table in PROJECTION_TABLES}


def _replace_identifier(sql: str, old: str, new: str) -> str:
    return re.sub(
        rf"(?<![A-Za-z0-9_]){re.escape(old)}(?![A-Za-z0-9_])",
        new,
        sql,
        flags=re.IGNORECASE,
    )


def _rewrite_projection_sql(sql: str, mapping: Mapping[str, str]) -> str:
    rewritten = sql
    # Longest first makes the operation stable even if names later share prefixes.
    for logical in sorted(mapping, key=len, reverse=True):
        rewritten = _replace_identifier(rewritten, logical, mapping[logical])
    return rewritten


_GENERATION_SQL_CACHE_LIMIT = 128


class GenerationConnection:
    """Minimal connection membrane used by unchanged current projectors."""

    def __init__(self, conn: sqlite3.Connection, generation_id: str):
        self.raw = conn
        self.generation_id = _token(generation_id)
        self.mapping = _table_map(generation_id)
        # Projectors execute a very small, repeated set of static statements.
        # Re-running twelve regex substitutions for every projected event made
        # the 1M replay CPU-bound.  Keep the cache connection-local and hard
        # bounded so scale does not change its memory footprint.
        self._rewrite_cache: dict[str, str] = {}

    def _rewrite(self, sql: str) -> str:
        cached = self._rewrite_cache.get(sql)
        if cached is not None:
            return cached
        rewritten = _rewrite_projection_sql(sql, self.mapping)
        if len(self._rewrite_cache) < _GENERATION_SQL_CACHE_LIMIT:
            self._rewrite_cache[sql] = rewritten
        return rewritten

    def execute(
        self, sql: str, parameters: Sequence[Any] | Mapping[str, Any] = ()
    ) -> sqlite3.Cursor:
        return self.raw.execute(self._rewrite(sql), parameters)

    def executemany(
        self, sql: str, parameters: Iterable[Sequence[Any] | Mapping[str, Any]]
    ) -> sqlite3.Cursor:
        return self.raw.executemany(self._rewrite(sql), parameters)

    @property
    def in_transaction(self) -> bool:
        return self.raw.in_transaction


@contextmanager
def _projection_write_guard(
    conn: sqlite3.Connection, generation_ids: Sequence[str]
) -> Iterator[None]:
    allowed = {
        _physical_table(generation_id, table)
        for generation_id in generation_ids
        for table in PROJECTION_TABLES
    }
    allowed.add("sqlite_sequence")
    write_actions = {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE}

    def authorize(
        action: int,
        arg1: str | None,
        _arg2: str | None,
        _db_name: str | None,
        _trigger: str | None,
    ) -> int:
        if action in write_actions and arg1 not in allowed:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    conn.create_function(
        "a03b_projection_write_allowed",
        1,
        lambda table: int(str(table) in allowed),
    )
    conn.set_authorizer(authorize)
    try:
        yield
    finally:
        conn.set_authorizer(None)
        conn.create_function("a03b_projection_write_allowed", 1, lambda _table: 0)


def _master_sql(conn: sqlite3.Connection, object_type: str, name: str) -> str:
    row = conn.execute(
        "SELECT sql FROM sqlite_schema WHERE type=? AND name=?", (object_type, name)
    ).fetchone()
    if row is None or row[0] is None:
        raise SchemaInventoryError(f"missing {object_type} definition: {name}")
    return str(row[0])


def _clone_projection_tables(conn: sqlite3.Connection, generation_id: str) -> None:
    mapping = _table_map(generation_id)
    if generation_id == "g1":
        return
    for logical in PROJECTION_TABLES:
        source = _master_sql(conn, "table", logical)
        create = _rewrite_projection_sql(source, mapping)
        create = re.sub(
            rf"^CREATE\s+TABLE\s+{re.escape(mapping[logical])}",
            f"CREATE TABLE IF NOT EXISTS {_quote(mapping[logical])}",
            create,
            count=1,
            flags=re.IGNORECASE,
        )
        conn.execute(create)
    for logical in PROJECTION_TABLES:
        for row in conn.execute(f"PRAGMA index_list({_quote(logical)})"):
            source_name = str(row[1])
            if source_name.startswith("sqlite_autoindex"):
                continue
            source_sql = _master_sql(conn, "index", source_name)
            target_name = f"a03b_{generation_id}__{source_name}"
            create = _rewrite_projection_sql(source_sql, mapping)
            create = _replace_identifier(create, source_name, target_name)
            create = re.sub(
                r"^CREATE\s+(UNIQUE\s+)?INDEX\s+",
                lambda match: "CREATE " + (match.group(1) or "") + "INDEX IF NOT EXISTS ",
                create,
                count=1,
                flags=re.IGNORECASE,
            )
            conn.execute(create)


def _install_generation_guards(conn: sqlite3.Connection, generation_id: str) -> None:
    """Reject every projection DML statement outside a routed guard context."""
    mapping = _table_map(generation_id)
    for logical, physical in mapping.items():
        for action in ("INSERT", "UPDATE", "DELETE"):
            trigger = f"a03b_{generation_id}__protect_{action.lower()}__{logical}"
            conn.execute(
                f"CREATE TRIGGER IF NOT EXISTS {_quote(trigger)} BEFORE {action} "
                f"ON {_quote(physical)} "
                f"WHEN a03b_projection_write_allowed({physical!r}) != 1 "
                "BEGIN SELECT RAISE(ABORT,'A0.3b unrouted projection write'); END"
            )


def _validate_generation_guards(conn: sqlite3.Connection) -> None:
    expected: dict[str, tuple[str, str]] = {}
    for generation_id in ("g1", "g2", "g3"):
        for logical, physical in _table_map(generation_id).items():
            for action in ("insert", "update", "delete"):
                name = f"a03b_{generation_id}__protect_{action}__{logical}"
                expected[name] = (physical, action)
    rows = conn.execute(
        "SELECT name,tbl_name,sql FROM sqlite_schema WHERE type='trigger' "
        "AND name GLOB 'a03b_g[123]__protect_*' ORDER BY name"
    ).fetchall()
    if [str(row["name"]) for row in rows] != sorted(expected):
        raise SchemaInventoryError("projection write-guard inventory changed")
    for row in rows:
        name = str(row["name"])
        physical, action = expected[name]
        sql = " ".join(str(row["sql"] or "").split()).lower()
        required = (
            f"before {action} on {_quote(physical)} "
            f"when a03b_projection_write_allowed({physical!r}) != 1 "
            "begin select raise(abort,'a0.3b unrouted projection write'); end"
        ).lower()
        if str(row["tbl_name"]) != physical or required not in sql:
            raise SchemaInventoryError(f"projection write guard changed: {name}")


_METADATA_SQL = f"""
CREATE TABLE IF NOT EXISTS a03b_generation (
  generation_id TEXT PRIMARY KEY,
  role TEXT NOT NULL CHECK(role IN ('base','shadow','verifier')),
  state TEXT NOT NULL CHECK(state IN ({','.join(repr(v) for v in sorted(GENERATION_STATES))})),
  build_target_event_id INTEGER,
  built_through_event_id INTEGER,
  verified_through_event_id INTEGER,
  full_digest_verified_through_event_id INTEGER,
  built_event_count INTEGER NOT NULL DEFAULT 0,
  built_head_seal TEXT,
  projection_digest_set_sha256 TEXT,
  sequence_digest_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL,
  verified_at TEXT,
  activated_at TEXT,
  retired_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS a03b_one_active_generation
  ON a03b_generation(state) WHERE state='active';
CREATE TABLE IF NOT EXISTS a03b_control (
  singleton INTEGER PRIMARY KEY CHECK(singleton=1),
  metadata_schema TEXT NOT NULL,
  active_generation_id TEXT NOT NULL REFERENCES a03b_generation(generation_id),
  sync_generation_id TEXT REFERENCES a03b_generation(generation_id),
  revision INTEGER NOT NULL,
  cutover_head_event_id INTEGER,
  exact_schema_sha256 TEXT,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS a03b_projection_target (
  generation_id TEXT NOT NULL REFERENCES a03b_generation(generation_id),
  logical_table TEXT NOT NULL,
  physical_table TEXT NOT NULL UNIQUE,
  PRIMARY KEY(generation_id,logical_table)
);
CREATE TABLE IF NOT EXISTS a03b_apply_receipt (
  generation_id TEXT NOT NULL REFERENCES a03b_generation(generation_id),
  batch_no INTEGER NOT NULL,
  phase TEXT NOT NULL,
  first_event_id INTEGER,
  last_event_id INTEGER,
  event_count INTEGER NOT NULL,
  payload_bytes INTEGER NOT NULL,
  ledger_batch_sha256 TEXT NOT NULL,
  prior_receipt_sha256 TEXT,
  receipt_sha256 TEXT NOT NULL,
  committed_at TEXT NOT NULL,
  PRIMARY KEY(generation_id,batch_no),
  UNIQUE(generation_id,receipt_sha256)
);
CREATE TABLE IF NOT EXISTS a03b_verification (
  generation_id TEXT NOT NULL REFERENCES a03b_generation(generation_id),
  through_event_id INTEGER NOT NULL,
  event_count INTEGER NOT NULL,
  ledger_sha256 TEXT NOT NULL,
  projection_digests_json TEXT NOT NULL,
  projection_digest_set_sha256 TEXT NOT NULL,
  sequences_json TEXT NOT NULL,
  sequence_digest_sha256 TEXT NOT NULL,
  second_replay_generation_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(generation_id,through_event_id)
);
CREATE TABLE IF NOT EXISTS a03b_operation_lock (
  generation_id TEXT PRIMARY KEY REFERENCES a03b_generation(generation_id),
  owner_token TEXT NOT NULL,
  owner_pid INTEGER NOT NULL,
  owner_process_started REAL NOT NULL,
  acquired_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS a03b_sync_session (
  singleton INTEGER PRIMARY KEY CHECK(singleton=1),
  state TEXT NOT NULL CHECK(state IN ('preparing','armed','cutover')),
  shadow_generation_id TEXT NOT NULL REFERENCES a03b_generation(generation_id),
  verifier_generation_id TEXT NOT NULL REFERENCES a03b_generation(generation_id),
  base_event_id INTEGER,
  base_event_count INTEGER NOT NULL,
  base_head_seal TEXT,
  base_ledger_sha256 TEXT NOT NULL,
  base_projection_digest_set_sha256 TEXT NOT NULL,
  base_sequence_digest_sha256 TEXT NOT NULL,
  synchronized_through_event_id INTEGER,
  synchronized_event_count INTEGER NOT NULL,
  synchronized_head_seal TEXT,
  synchronized_batch_count INTEGER NOT NULL,
  sync_chain_sha256 TEXT NOT NULL,
  synchronized_sequence_digest_sha256 TEXT NOT NULL,
  admitted_at TEXT,
  cutover_at TEXT
);
"""


def _schema_objects(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [
        {"type": str(row[0]), "name": str(row[1]), "table": str(row[2]), "sql": row[3]}
        for row in conn.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        )
    ]


def _schema_sha256(conn: sqlite3.Connection) -> str:
    return _sha256_json(_schema_objects(conn))


def _validate_extended_schema(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT metadata_schema,exact_schema_sha256 FROM a03b_control WHERE singleton=1"
    ).fetchone()
    if row is None or row[0] != METADATA_SCHEMA or not row[1]:
        raise SchemaInventoryError("A0.3b control record is missing or has the wrong schema")
    actual = _schema_sha256(conn)
    if actual != row[1]:
        raise SchemaInventoryError("A0.3b extended schema inventory changed")
    generations = [str(item[0]) for item in conn.execute(
        "SELECT generation_id FROM a03b_generation ORDER BY generation_id"
    )]
    if generations != ["g1", "g2", "g3"]:
        raise SchemaInventoryError("generation inventory is not exactly g1/g2/g3")
    for generation_id in generations:
        rows = conn.execute(
            "SELECT logical_table,physical_table FROM a03b_projection_target "
            "WHERE generation_id=? ORDER BY logical_table",
            (generation_id,),
        ).fetchall()
        expected = sorted(_table_map(generation_id).items())
        if [(str(item[0]), str(item[1])) for item in rows] != expected:
            raise SchemaInventoryError(f"projection target map changed for {generation_id}")
    _validate_generation_guards(conn)
    return actual


def _capture_head(conn: sqlite3.Connection) -> HeadFence:
    count, head = conn.execute("SELECT COUNT(*),MAX(id) FROM event_log").fetchone()
    head_seal = None
    if head is not None:
        head_seal = conn.execute("SELECT seal FROM event_log WHERE id=?", (head,)).fetchone()[0]
    return HeadFence(
        head_id=None if head is None else int(head),
        event_count=int(count),
        head_seal=head_seal,
    )


def _topology_snapshot(
    conn: sqlite3.Connection, *, verify_event_count: bool = False
) -> dict[str, Any]:
    """Validate pointer, states and routed watermarks in one SQLite snapshot."""
    control = conn.execute("SELECT * FROM a03b_control WHERE singleton=1").fetchone()
    if control is None:
        raise SchemaInventoryError("A0.3b control record disappeared")
    rows = conn.execute(
        "SELECT * FROM a03b_generation ORDER BY generation_id"
    ).fetchall()
    if [str(row["generation_id"]) for row in rows] != ["g1", "g2", "g3"]:
        raise SchemaInventoryError("generation topology is not exactly g1/g2/g3")
    statuses = {str(row["generation_id"]): _status_from_row(row) for row in rows}
    for generation_id in ("g1", "g2", "g3"):
        _require_current_sequence_digest(conn, generation_id)
    if {generation_id: status.role for generation_id, status in statuses.items()} != {
        "g1": "base",
        "g2": "shadow",
        "g3": "verifier",
    }:
        raise SchemaInventoryError("generation roles changed")
    active_rows = [status for status in statuses.values() if status.state == "active"]
    if len(active_rows) != 1:
        raise ShadowHarnessError("INVALID_ACTIVE_GENERATION_COUNT")
    active = active_rows[0]
    if active.generation_id != str(control["active_generation_id"]):
        raise ShadowHarnessError("INVALID_POINTER_STATE")
    if verify_event_count:
        head = _capture_head(conn)
    else:
        last = conn.execute(
            "SELECT id,seal FROM event_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        head = HeadFence(
            head_id=None if last is None else int(last["id"]),
            event_count=active.built_event_count,
            head_seal=None if last is None else last["seal"],
        )
    if (
        active.built_through_event_id != head.head_id
        or active.built_event_count != head.event_count
        or active.built_head_seal != head.head_seal
    ):
        raise ShadowHarnessError("INVALID_UNROUTED_TAIL")
    session = conn.execute(
        "SELECT * FROM a03b_sync_session WHERE singleton=1"
    ).fetchone()
    sync_id = control["sync_generation_id"]
    kind: str
    if sync_id is not None:
        if (
            active.generation_id != "g1"
            or str(sync_id) != "g2"
            or session is None
            or str(session["state"]) != "armed"
            or statuses["g2"].state != "catching_up"
            or statuses["g3"].state != "catching_up"
            or not _generation_matches_sync_watermark(statuses["g1"], session)
            or not _generation_matches_sync_watermark(statuses["g2"], session)
            or not _generation_matches_sync_watermark(statuses["g3"], session)
        ):
            raise ShadowHarnessError("INVALID_ARMED_SYNC_TOPOLOGY")
        _require_equal_sequence_boundary(
            conn,
            ("g1", "g2", "g3"),
            expected_digest=str(session["synchronized_sequence_digest_sha256"]),
        )
        kind = "old_active_sync_armed"
    elif active.generation_id == "g1":
        if session is None:
            kind = "old_active"
        elif (
            str(session["state"]) == "preparing"
            and statuses["g2"].state == "catching_up"
            and statuses["g3"].state == "catching_up"
            and _generation_matches_sync_watermark(statuses["g2"], session)
            and _generation_matches_sync_watermark(statuses["g3"], session)
            and statuses["g2"].built_event_count <= active.built_event_count
        ):
            _require_equal_sequence_boundary(
                conn,
                ("g2", "g3"),
                expected_digest=str(session["synchronized_sequence_digest_sha256"]),
            )
            kind = "old_active_sync_preparing"
        else:
            raise ShadowHarnessError("INVALID_PREPARING_SYNC_TOPOLOGY")
    else:
        if (
            active.generation_id != "g2"
            or session is None
            or str(session["state"]) != "cutover"
            or statuses["g1"].state != "retired"
            or statuses["g3"].state != "verified"
            or control["cutover_head_event_id"]
            != session["synchronized_through_event_id"]
            or not _generation_matches_sync_watermark(statuses["g1"], session)
            or not _generation_matches_sync_watermark(statuses["g3"], session)
            or statuses["g2"].verified_through_event_id != session["base_event_id"]
            or statuses["g3"].verified_through_event_id != session["base_event_id"]
            or statuses["g2"].full_digest_verified_through_event_id
            != session["base_event_id"]
            or statuses["g3"].full_digest_verified_through_event_id
            != session["base_event_id"]
            or statuses["g2"].projection_digest_set_sha256
            != session["base_projection_digest_set_sha256"]
            or statuses["g3"].projection_digest_set_sha256
            != session["base_projection_digest_set_sha256"]
        ):
            raise ShadowHarnessError("INVALID_CUTOVER_TOPOLOGY")
        _require_equal_sequence_boundary(
            conn,
            ("g1", "g3"),
            expected_digest=str(session["synchronized_sequence_digest_sha256"]),
        )
        kind = "new_active"
    return {
        "kind": kind,
        "control": control,
        "statuses": statuses,
        "active": active,
        "head": head,
        "session": session,
    }


def initialize_shadow(
    database_path: Path | str,
    *,
    disposable_root: Path | str,
    shadow_generation_id: str = "g2",
    verifier_generation_id: str = "g3",
) -> dict[str, Any]:
    """Install exact same-file G1/G2/G3 metadata on a disposable Current DB."""
    if (shadow_generation_id, verifier_generation_id) != ("g2", "g3"):
        raise ShadowHarnessError("the v1 prototype fixes shadow/verifier ids to g2/g3")
    path, safety = _safety_path(database_path, disposable_root)
    conn = _open(path)
    write_collector = _WriteTxnCollector("initialize_shadow")
    initialization_transaction: _WriteTransaction | None = None
    try:
        journal_mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
        if journal_mode != "wal":
            raise ShadowHarnessError("A0.3b concurrency proof requires WAL mode")
        exists = conn.execute(
            "SELECT 1 FROM sqlite_schema WHERE type='table' AND name='a03b_control'"
        ).fetchone()
        if exists:
            exact = _validate_extended_schema(conn)
            return {
                "schema": METADATA_SCHEMA,
                "already_initialized": True,
                "exact_schema_sha256": exact,
                "journal_mode": journal_mode,
                "write_transactions": write_collector.receipt(),
                "safety": safety,
            }
        conn.execute("PRAGMA query_only=ON")
        detected = schema_detection.detect_schema(conn)
        conn.execute("PRAGMA query_only=OFF")
        if detected.status != "current" or not detected.current:
            raise SchemaInventoryError(
                f"A0.3b requires an untouched Current schema, got {detected.status}"
            )
        # executescript otherwise performs an implicit pre-commit.  Put the BEGIN
        # inside the script so metadata DDL, clones, mappings and pointer appear as
        # one crash-atomic installation.
        initialization_transaction = _WriteTransaction(
            conn,
            write_collector,
            "initialization_ddl_and_metadata",
            begin=False,
        )
        conn.executescript("BEGIN IMMEDIATE;\n" + _METADATA_SQL)
        now = _utc_now()
        fence = _capture_head(conn)
        sequence_digests = {
            generation_id: _sequence_digest(conn, generation_id)
            for generation_id in ("g1", "g2", "g3")
        }
        conn.executemany(
            "INSERT INTO a03b_generation("
            "generation_id,role,state,build_target_event_id,built_through_event_id,"
            "verified_through_event_id,full_digest_verified_through_event_id,"
            "built_event_count,built_head_seal,sequence_digest_sha256,created_at,activated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                (
                    "g1", "base", "active", fence.head_id, fence.head_id, None,
                    None, fence.event_count, fence.head_seal, sequence_digests["g1"], now, now,
                ),
                ("g2", "shadow", "building", fence.head_id, None, None, None, 0, None, sequence_digests["g2"], now, None),
                ("g3", "verifier", "building", fence.head_id, None, None, None, 0, None, sequence_digests["g3"], now, None),
            ),
        )
        for generation_id in ("g2", "g3"):
            _clone_projection_tables(conn, generation_id)
        for generation_id in ("g1", "g2", "g3"):
            _install_generation_guards(conn, generation_id)
        target_rows = [
            (generation_id, logical, physical)
            for generation_id in ("g1", "g2", "g3")
            for logical, physical in sorted(_table_map(generation_id).items())
        ]
        conn.executemany(
            "INSERT INTO a03b_projection_target(generation_id,logical_table,physical_table) "
            "VALUES (?,?,?)",
            target_rows,
        )
        conn.execute(
            "INSERT INTO a03b_control(singleton,metadata_schema,active_generation_id,"
            "sync_generation_id,revision,cutover_head_event_id,exact_schema_sha256,updated_at) "
            "VALUES (1,?,'g1',NULL,0,NULL,NULL,?)",
            (METADATA_SCHEMA, now),
        )
        exact = _schema_sha256(conn)
        conn.execute(
            "UPDATE a03b_control SET exact_schema_sha256=? WHERE singleton=1", (exact,)
        )
        initialization_transaction.commit()
        _validate_extended_schema(conn)
        return {
            "schema": METADATA_SCHEMA,
            "already_initialized": False,
            "base_schema_fingerprint": detected.fingerprint,
            "exact_schema_sha256": exact,
            "journal_mode": journal_mode,
            "initial_head": asdict(fence),
            "generation_ids": ["g1", "g2", "g3"],
            "projection_target_count": len(target_rows),
            "write_transactions": write_collector.receipt(),
            "safety": safety,
        }
    except BaseException:
        if initialization_transaction is not None:
            initialization_transaction.rollback()
        elif conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()


def _status_row(conn: sqlite3.Connection, generation_id: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM a03b_generation WHERE generation_id=?", (_token(generation_id),)
    ).fetchone()
    if row is None:
        raise ShadowHarnessError(f"unknown generation: {generation_id}")
    return row


def _status_from_row(row: sqlite3.Row) -> GenerationStatus:
    return GenerationStatus(
        generation_id=str(row["generation_id"]),
        role=str(row["role"]),
        state=str(row["state"]),
        built_through_event_id=(
            None if row["built_through_event_id"] is None else int(row["built_through_event_id"])
        ),
        verified_through_event_id=(
            None
            if row["verified_through_event_id"] is None
            else int(row["verified_through_event_id"])
        ),
        full_digest_verified_through_event_id=(
            None
            if row["full_digest_verified_through_event_id"] is None
            else int(row["full_digest_verified_through_event_id"])
        ),
        built_event_count=int(row["built_event_count"]),
        built_head_seal=row["built_head_seal"],
        projection_digest_set_sha256=row["projection_digest_set_sha256"],
        sequence_digest_sha256=str(row["sequence_digest_sha256"]),
    )


def _claim_operations(
    conn: sqlite3.Connection,
    generation_roles: Mapping[str, str],
    *,
    allowed_states: frozenset[str],
    write_collector: _WriteTxnCollector,
) -> str:
    owner = uuid.uuid4().hex
    try:
        owner_pid = os.getpid()
        owner_process_started = float(psutil.Process(owner_pid).create_time())
    except (psutil.Error, OSError) as exc:
        raise ShadowHarnessError("cannot establish a persistent operation owner") from exc
    transaction = _WriteTransaction(conn, write_collector, "operation_claim")
    try:
        control = conn.execute(
            "SELECT active_generation_id,sync_generation_id "
            "FROM a03b_control WHERE singleton=1"
        ).fetchone()
        active = str(control["active_generation_id"])
        if control["sync_generation_id"] is not None:
            raise ShadowHarnessError(
                "routed sync is armed; only routed writers or metadata cutover may run"
            )
        session = conn.execute(
            "SELECT state FROM a03b_sync_session WHERE singleton=1"
        ).fetchone()
        if session is not None and str(session["state"]) == "preparing" and set(
            generation_roles
        ) != {"g2", "g3"}:
            raise ShadowHarnessError(
                "a prepared sync session may only be resumed by paired verification"
            )
        for generation_id, role in generation_roles.items():
            row = _status_row(conn, generation_id)
            if str(row["role"]) != role:
                raise ShadowHarnessError(
                    f"{generation_id} role is {row['role']}, expected {role}"
                )
            if generation_id == active or str(row["state"]) in {"active", "retired"}:
                raise ShadowHarnessError(f"refusing to mutate active/retired {generation_id}")
            if str(row["state"]) not in allowed_states:
                raise ShadowHarnessError(
                    f"{generation_id} state {row['state']} is not an allowed transition source"
                )
            conn.execute(
                "INSERT INTO a03b_operation_lock("
                "generation_id,owner_token,owner_pid,owner_process_started,acquired_at) "
                "VALUES (?,?,?,?,?)",
                (
                    generation_id,
                    owner,
                    owner_pid,
                    owner_process_started,
                    _utc_now(),
                ),
            )
        transaction.commit()
        return owner
    except sqlite3.IntegrityError as exc:
        transaction.rollback()
        raise ShadowHarnessError("generation already has an active operation") from exc
    except BaseException:
        transaction.rollback()
        raise


def _operation_lease_is_live(row: sqlite3.Row) -> bool:
    """Distinguish a live owner from a crash-stale persistent lease."""
    try:
        process = psutil.Process(int(row["owner_pid"]))
        expected_started = float(row["owner_process_started"])
        return bool(
            process.is_running()
            and abs(float(process.create_time()) - expected_started) < 0.001
        )
    except (KeyError, TypeError, ValueError, psutil.Error, OSError):
        return False


def _require_operation(
    conn: sqlite3.Connection, generation_id: str, owner: str
) -> None:
    row = conn.execute(
        "SELECT 1 FROM a03b_operation_lock WHERE generation_id=? AND owner_token=?",
        (generation_id, owner),
    ).fetchone()
    if row is None:
        raise ShadowHarnessError("generation operation lease was lost")


def _release_operations(
    conn: sqlite3.Connection,
    owner: str,
    *,
    write_collector: _WriteTxnCollector,
    strict: bool = True,
) -> None:
    transaction = _WriteTransaction(conn, write_collector, "operation_release")
    try:
        deleted = conn.execute(
            "DELETE FROM a03b_operation_lock WHERE owner_token=?", (owner,)
        ).rowcount
        if strict and deleted < 1:
            raise ShadowHarnessError("generation operation lease was not present")
        transaction.commit()
    except BaseException:
        transaction.rollback()
        raise


def generation_status(
    database_path: Path | str,
    *,
    disposable_root: Path | str,
) -> dict[str, Any]:
    path, safety = _safety_path(database_path, disposable_root)
    conn = _open(path)
    try:
        exact = _validate_extended_schema(conn)
        control = conn.execute("SELECT * FROM a03b_control WHERE singleton=1").fetchone()
        generations = [
            asdict(_status_from_row(row))
            for row in conn.execute("SELECT * FROM a03b_generation ORDER BY generation_id")
        ]
        return {
            "schema": METADATA_SCHEMA,
            "active_generation_id": str(control["active_generation_id"]),
            "sync_generation_id": control["sync_generation_id"],
            "revision": int(control["revision"]),
            "cutover_head_event_id": control["cutover_head_event_id"],
            "exact_schema_sha256": exact,
            "generations": generations,
            "safety": safety,
        }
    finally:
        conn.close()


def _bounded_clear_generation(
    conn: sqlite3.Connection,
    generation_id: str,
    *,
    owner: str,
    batch_rows: int,
    write_collector: _WriteTxnCollector,
    fault: Callable[[str, Mapping[str, Any]], None] | None,
) -> BatchAggregate:
    """Purge a reusable physical generation without one unbounded writer gate."""
    if not 1 <= batch_rows <= MAX_BATCH_EVENTS:
        raise ShadowHarnessError("bounded purge rows exceed the hard cap")
    if generation_id == "g1":
        raise ShadowHarnessError("the active base generation may never be cleared")
    aggregate = BatchAggregate()

    transaction_index = 0
    if generation_id == "g3":
        _emit_fault(
            fault,
            "g3_bounded_purge_opened",
            {"generation_id": generation_id, "batch_rows": batch_rows},
        )

    def emit_pre_commit(target_kind: str) -> None:
        if generation_id == "g3":
            _emit_fault(
                fault,
                "g3_bounded_purge_batch_pre_commit",
                {
                    "generation_id": generation_id,
                    "target_kind": target_kind,
                    "transaction_index": transaction_index + 1,
                },
            )

    mapping = _table_map(generation_id)
    for logical in PROJECTION_TABLES:
        physical = mapping[logical]
        key = str(PROJECTION_SPECS[logical]["sort_by"][0])
        while True:
            transaction = _WriteTransaction(
                conn, write_collector, "bounded_projection_purge"
            )
            try:
                _require_operation(conn, generation_id, owner)
                _require_current_sequence_digest(conn, generation_id)
                with _projection_write_guard(conn, (generation_id,)):
                    deleted = conn.execute(
                        f"DELETE FROM {_quote(physical)} WHERE {_quote(key)} IN ("
                        f"SELECT {_quote(key)} FROM {_quote(physical)} "
                        f"ORDER BY {_quote(key)} LIMIT ?)",
                        (batch_rows,),
                    ).rowcount
                emit_pre_commit("projection")
                transaction.commit()
            except BaseException:
                transaction.rollback()
                raise
            transaction_index += 1
            aggregate.add_auxiliary(transaction.transaction_seconds)
            if generation_id == "g3":
                _emit_fault(
                    fault,
                    "g3_bounded_purge_batch_committed",
                    {
                        "generation_id": generation_id,
                        "target_kind": "projection",
                        "logical_table": logical,
                        "deleted_rows": deleted,
                        "transaction_index": transaction_index,
                    },
                )
            if deleted < batch_rows:
                break
    for table in ("a03b_apply_receipt", "a03b_verification"):
        while True:
            transaction = _WriteTransaction(
                conn, write_collector, "bounded_metadata_purge"
            )
            try:
                _require_operation(conn, generation_id, owner)
                deleted = conn.execute(
                    f"DELETE FROM {_quote(table)} WHERE rowid IN ("
                    f"SELECT rowid FROM {_quote(table)} WHERE generation_id=? "
                    "ORDER BY rowid LIMIT ?)",
                    (generation_id, batch_rows),
                ).rowcount
                emit_pre_commit("metadata")
                transaction.commit()
            except BaseException:
                transaction.rollback()
                raise
            transaction_index += 1
            aggregate.add_auxiliary(transaction.transaction_seconds)
            if generation_id == "g3":
                _emit_fault(
                    fault,
                    "g3_bounded_purge_batch_committed",
                    {
                        "generation_id": generation_id,
                        "target_kind": "metadata",
                        "metadata_table": table,
                        "deleted_rows": deleted,
                        "transaction_index": transaction_index,
                    },
                )
            if deleted < batch_rows:
                break
    transaction = _WriteTransaction(conn, write_collector, "bounded_sequence_purge")
    try:
        _require_operation(conn, generation_id, owner)
        _require_current_sequence_digest(conn, generation_id)
        with _projection_write_guard(conn, (generation_id,)):
            conn.execute(
                "DELETE FROM sqlite_sequence WHERE name IN ("
                + ",".join("?" for _ in SEQUENCE_TABLES)
                + ")",
                tuple(mapping[table] for table in SEQUENCE_TABLES),
            )
        conn.execute(
            "UPDATE a03b_generation SET sequence_digest_sha256=? "
            "WHERE generation_id=?",
            (_sequence_digest(conn, generation_id), generation_id),
        )
        emit_pre_commit("sequence")
        transaction.commit()
    except BaseException:
        transaction.rollback()
        raise
    transaction_index += 1
    aggregate.add_auxiliary(transaction.transaction_seconds)
    if generation_id == "g3":
        _emit_fault(
            fault,
            "g3_bounded_purge_batch_committed",
            {
                "generation_id": generation_id,
                "target_kind": "sequence",
                "transaction_index": transaction_index,
            },
        )
        _emit_fault(
            fault,
            "g3_bounded_purge_complete",
            {
                "generation_id": generation_id,
                "transaction_count": transaction_index,
            },
        )
    return aggregate


def _event_batch(
    conn: sqlite3.Connection,
    *,
    after_id: int,
    through_id: int,
    batch_events: int,
    batch_bytes: int,
) -> tuple[list[sqlite3.Row], int]:
    if batch_events < 1 or batch_bytes < 1:
        raise ValueError("batch event and byte caps must be positive")
    if batch_events > MAX_BATCH_EVENTS or batch_bytes > MAX_BATCH_BYTES:
        raise ShadowHarnessError("batch configuration exceeds the hard boundedness caps")
    cursor = conn.execute(
        "SELECT id,event_type,payload,created_at,prev_seal,seal FROM event_log "
        "WHERE id>? AND id<=? ORDER BY id LIMIT ?",
        (after_id, through_id, batch_events),
    )
    selected: list[sqlite3.Row] = []
    total_bytes = 0
    for row in cursor:
        row_bytes = sum(
            0 if row[column] is None else len(str(row[column]).encode("utf-8"))
            for column in a03a.EVENT_COLUMNS
        )
        if selected and total_bytes + row_bytes > batch_bytes:
            break
        if row_bytes > batch_bytes:
            raise ShadowHarnessError(
                f"event {int(row['id'])} exceeds the configured hard batch byte cap"
            )
        selected.append(row)
        total_bytes += row_bytes
    return selected, total_bytes


def _batch_hash(rows: Sequence[sqlite3.Row]) -> str:
    digest = hashlib.sha256((BATCH_RECEIPT_SCHEMA + "\0").encode("ascii"))
    for row in rows:
        digest.update(b"R")
        for column in a03a.EVENT_COLUMNS:
            value = row[column]
            if value is None:
                digest.update(b"N")
            else:
                encoded = str(value).encode("utf-8")
                digest.update(b"V")
                digest.update(len(encoded).to_bytes(8, "big"))
                digest.update(encoded)
    return digest.hexdigest()


def _sync_seed(
    *,
    base_event_id: int | None,
    base_event_count: int,
    base_head_seal: str | None,
    base_ledger_sha256: str,
    base_projection_digest_set_sha256: str,
    base_sequence_digest_sha256: str,
) -> str:
    return _sha256_json(
        {
            "schema": SYNC_PROOF_SCHEMA,
            "kind": "verified_base",
            "base_event_id": base_event_id,
            "base_event_count": base_event_count,
            "base_head_seal": base_head_seal,
            "base_ledger_sha256": base_ledger_sha256,
            "base_projection_digest_set_sha256": (
                base_projection_digest_set_sha256
            ),
            "base_sequence_digest_sha256": base_sequence_digest_sha256,
        }
    )


def _sync_session(conn: sqlite3.Connection) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM a03b_sync_session WHERE singleton=1"
    ).fetchone()
    if row is None:
        raise ShadowHarnessError("routed sync session is missing")
    return row


def _advance_sync_proof(
    conn: sqlite3.Connection,
    rows: Sequence[sqlite3.Row],
    *,
    phase: str,
) -> str:
    """Advance the O(1) proof for a pair/triple-written immutable ledger batch."""
    if not rows:
        return str(_sync_session(conn)["sync_chain_sha256"])
    session = _sync_session(conn)
    if str(session["state"]) not in {"preparing", "armed"}:
        raise ShadowHarnessError("routed sync proof is not writable")
    previous_id = session["synchronized_through_event_id"]
    after_id = 0 if previous_id is None else int(previous_id)
    last_id = int(rows[-1]["id"])
    expected_rows = conn.execute(
        "SELECT id FROM event_log WHERE id>? AND id<=? ORDER BY id",
        (after_id, last_id),
    ).fetchall()
    if [int(item[0]) for item in expected_rows] != [int(row["id"]) for row in rows]:
        raise ShadowHarnessError("routed sync proof would skip or duplicate ledger rows")
    sequence_ids = (
        ("g1", "g2", "g3") if phase == "routed_writer_sync" else ("g2", "g3")
    )
    synchronized_sequence_digest = _require_equal_sequence_boundary(
        conn, sequence_ids
    )
    body = {
        "schema": SYNC_PROOF_SCHEMA,
        "kind": "synchronized_batch",
        "prior_sync_chain_sha256": str(session["sync_chain_sha256"]),
        "phase": phase,
        "first_event_id": int(rows[0]["id"]),
        "last_event_id": last_id,
        "event_count": len(rows),
        "ledger_batch_sha256": _batch_hash(rows),
    }
    chain = _sha256_json(body)
    updated = conn.execute(
        "UPDATE a03b_sync_session SET synchronized_through_event_id=?,"
        "synchronized_event_count=synchronized_event_count+?,"
        "synchronized_head_seal=?,synchronized_batch_count=synchronized_batch_count+1,"
        "sync_chain_sha256=?,synchronized_sequence_digest_sha256=? "
        "WHERE singleton=1 AND sync_chain_sha256=? "
        "AND state IN ('preparing','armed')",
        (
            last_id,
            len(rows),
            rows[-1]["seal"],
            chain,
            synchronized_sequence_digest,
            session["sync_chain_sha256"],
        ),
    ).rowcount
    if updated != 1:
        raise ShadowHarnessError("routed sync proof CAS failed")
    return chain


def _validate_controlled_tail(
    conn: sqlite3.Connection,
    rows: Sequence[sqlite3.Row],
    *,
    previous_seal: str | None,
) -> None:
    """Bind a bounded pre-admission tail to seals and routed-writer receipts."""
    if not rows:
        return
    if previous_seal is None:
        raise ShadowHarnessError("controlled sync tail has no sealed predecessor")
    first_id = int(rows[0]["id"])
    last_id = int(rows[-1]["id"])
    receipt_rows = conn.execute(
        "SELECT first_event_id,last_event_id,event_count,ledger_batch_sha256 "
        "FROM a03b_apply_receipt WHERE generation_id='g1' "
        "AND phase='routed_writer' AND first_event_id>=? AND last_event_id<=? "
        "ORDER BY first_event_id,batch_no",
        (first_id, last_id),
    ).fetchall()
    receipts: dict[int, sqlite3.Row] = {}
    for receipt in receipt_rows:
        receipt_id = int(receipt["first_event_id"])
        if receipt_id in receipts:
            raise ShadowHarnessError("duplicate routed-writer receipt in sync tail")
        receipts[receipt_id] = receipt
    expected_previous = previous_seal
    prior_id = 0
    for row in rows:
        row_id = int(row["id"])
        if row_id <= prior_id:
            raise ShadowHarnessError("sync tail event order is not strictly increasing")
        if row["prev_seal"] != expected_previous or row["seal"] is None:
            raise ShadowHarnessError("sync tail seal continuity failed")
        expected_seal = sealing.compute_seal(
            expected_previous, str(row["event_type"]), str(row["payload"])
        )
        if row["seal"] != expected_seal:
            raise ShadowHarnessError("sync tail content seal failed")
        receipt = receipts.get(row_id)
        if (
            receipt is None
            or int(receipt["last_event_id"]) != row_id
            or int(receipt["event_count"]) != 1
            or str(receipt["ledger_batch_sha256"]) != _batch_hash((row,))
        ):
            raise ShadowHarnessError(
                "sync tail is not bound to an exact routed-writer receipt"
            )
        prior_id = row_id
        expected_previous = str(row["seal"])


def _next_batch_no(conn: sqlite3.Connection, generation_id: str) -> int:
    return int(
        conn.execute(
            "SELECT COALESCE(MAX(batch_no),0)+1 FROM a03b_apply_receipt "
            "WHERE generation_id=?",
            (generation_id,),
        ).fetchone()[0]
    )


def _prior_receipt(conn: sqlite3.Connection, generation_id: str) -> str | None:
    row = conn.execute(
        "SELECT receipt_sha256 FROM a03b_apply_receipt WHERE generation_id=? "
        "ORDER BY batch_no DESC LIMIT 1",
        (generation_id,),
    ).fetchone()
    return None if row is None else str(row[0])


def _emit_fault(
    fault: Callable[[str, Mapping[str, Any]], None] | None,
    phase: str,
    evidence: Mapping[str, Any],
) -> None:
    if fault is not None:
        fault(phase, evidence)


def _apply_rows(
    conn: sqlite3.Connection,
    generation_ids: Sequence[str],
    rows: Sequence[sqlite3.Row],
) -> None:
    adapters = [GenerationConnection(conn, generation_id) for generation_id in generation_ids]
    with _projection_write_guard(conn, generation_ids):
        for row in rows:
            for adapter in adapters:
                event_router.apply_event(adapter, row)


def _record_batch(
    conn: sqlite3.Connection,
    generation_id: str,
    rows: Sequence[sqlite3.Row],
    payload_bytes: int,
    phase: str,
) -> tuple[int, str]:
    batch_no = _next_batch_no(conn, generation_id)
    prior = _prior_receipt(conn, generation_id)
    first_id = None if not rows else int(rows[0]["id"])
    last_id = None if not rows else int(rows[-1]["id"])
    ledger_sha = _batch_hash(rows)
    committed_at = _utc_now()
    body = {
        "schema": BATCH_RECEIPT_SCHEMA,
        "generation_id": generation_id,
        "batch_no": batch_no,
        "phase": phase,
        "first_event_id": first_id,
        "last_event_id": last_id,
        "event_count": len(rows),
        "payload_bytes": payload_bytes,
        "ledger_batch_sha256": ledger_sha,
        "prior_receipt_sha256": prior,
        "committed_at": committed_at,
    }
    receipt = _sha256_json(body)
    conn.execute(
        "INSERT INTO a03b_apply_receipt("
        "generation_id,batch_no,phase,first_event_id,last_event_id,event_count,"
        "payload_bytes,ledger_batch_sha256,prior_receipt_sha256,receipt_sha256,committed_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            generation_id,
            batch_no,
            phase,
            first_id,
            last_id,
            len(rows),
            payload_bytes,
            ledger_sha,
            prior,
            receipt,
            committed_at,
        ),
    )
    return batch_no, receipt


def _receipt_body_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "schema": BATCH_RECEIPT_SCHEMA,
        "generation_id": str(row["generation_id"]),
        "batch_no": int(row["batch_no"]),
        "phase": str(row["phase"]),
        "first_event_id": row["first_event_id"],
        "last_event_id": row["last_event_id"],
        "event_count": int(row["event_count"]),
        "payload_bytes": int(row["payload_bytes"]),
        "ledger_batch_sha256": str(row["ledger_batch_sha256"]),
        "prior_receipt_sha256": row["prior_receipt_sha256"],
        "committed_at": str(row["committed_at"]),
    }


def _validate_apply_receipt_chain(
    conn: sqlite3.Connection,
    generation_id: str,
    *,
    initial: ReceiptChainState | None = None,
    max_receipts: int = MAX_PERSISTENT_RECEIPTS,
) -> ReceiptChainState:
    """Recompute one complete or incremental persistent receipt hash chain."""
    after_batch = 0 if initial is None else initial.last_batch_no
    prior = None if initial is None else initial.last_receipt_sha256
    prior_count = 0 if initial is None else initial.receipt_count
    remaining = int(
        conn.execute(
            "SELECT COUNT(*) FROM a03b_apply_receipt "
            "WHERE generation_id=? AND batch_no>?",
            (generation_id, after_batch),
        ).fetchone()[0]
    )
    if remaining > max_receipts:
        raise ShadowHarnessError(
            f"{generation_id} receipt scan exceeds the hard cap"
        )
    expected_batch = after_batch + 1
    seen = 0
    cursor = conn.execute(
        "SELECT * FROM a03b_apply_receipt WHERE generation_id=? AND batch_no>? "
        "ORDER BY batch_no",
        (generation_id, after_batch),
    )
    for row in cursor:
        batch_no = int(row["batch_no"])
        event_count = int(row["event_count"])
        first_id = row["first_event_id"]
        last_id = row["last_event_id"]
        if batch_no != expected_batch:
            raise ShadowHarnessError(f"{generation_id} receipt batch numbers have a gap")
        if row["prior_receipt_sha256"] != prior:
            raise ShadowHarnessError(f"{generation_id} receipt prior hash changed")
        if event_count < 1 or first_id is None or last_id is None:
            raise ShadowHarnessError(f"{generation_id} receipt has an empty event range")
        if int(first_id) > int(last_id) or int(row["payload_bytes"]) < 0:
            raise ShadowHarnessError(f"{generation_id} receipt range is invalid")
        expected = _sha256_json(_receipt_body_from_row(row))
        if str(row["receipt_sha256"]) != expected:
            raise ShadowHarnessError(f"{generation_id} receipt hash changed")
        prior = expected
        expected_batch += 1
        seen += 1
    if seen != remaining:
        raise ShadowHarnessError(f"{generation_id} receipt scan count changed")
    return ReceiptChainState(
        generation_id=generation_id,
        last_batch_no=expected_batch - 1,
        last_receipt_sha256=prior,
        receipt_count=prior_count + seen,
    )


_SYNC_RECEIPT_PHASES = ("sync_prepare", "sync_admission", "routed_writer_sync")


def _sync_receipt_cursor(
    conn: sqlite3.Connection,
    generation_id: str,
    *,
    after_batch_no: int,
    base_event_id: int | None,
) -> sqlite3.Cursor:
    return conn.execute(
        "SELECT * FROM a03b_apply_receipt WHERE generation_id=? AND batch_no>? "
        "AND phase IN (?,?,?) AND first_event_id>? ORDER BY batch_no",
        (
            generation_id,
            after_batch_no,
            *_SYNC_RECEIPT_PHASES,
            base_event_id or 0,
        ),
    )


def _matching_sync_receipts(left: sqlite3.Row, right: sqlite3.Row) -> bool:
    fields = (
        "phase",
        "first_event_id",
        "last_event_id",
        "event_count",
        "payload_bytes",
        "ledger_batch_sha256",
    )
    return all(left[field] == right[field] for field in fields)


def _validate_persistent_proofs(
    conn: sqlite3.Connection,
    *,
    initial: Mapping[str, Any] | None = None,
    max_receipts: int = MAX_PERSISTENT_RECEIPTS,
) -> dict[str, Any]:
    """Recompute apply chains and the common sync chain from stored receipt fields."""
    session = _sync_session(conn)
    chain_initials: Mapping[str, ReceiptChainState] = (
        {} if initial is None else initial["apply_chains"]
    )
    chains = {
        generation_id: _validate_apply_receipt_chain(
            conn,
            generation_id,
            initial=chain_initials.get(generation_id),
            max_receipts=max_receipts,
        )
        for generation_id in ("g1", "g2", "g3")
    }
    if initial is None:
        sync_chain = _sync_seed(
            base_event_id=session["base_event_id"],
            base_event_count=int(session["base_event_count"]),
            base_head_seal=session["base_head_seal"],
            base_ledger_sha256=str(session["base_ledger_sha256"]),
            base_projection_digest_set_sha256=str(
                session["base_projection_digest_set_sha256"]
            ),
            base_sequence_digest_sha256=str(
                session["base_sequence_digest_sha256"]
            ),
        )
        synchronized_count = int(session["base_event_count"])
        synchronized_through = session["base_event_id"]
        synchronized_batches = 0
        after_batches = {generation_id: 0 for generation_id in ("g1", "g2", "g3")}
    else:
        sync_chain = str(initial["sync_chain_sha256"])
        synchronized_count = int(initial["synchronized_event_count"])
        synchronized_through = initial["synchronized_through_event_id"]
        synchronized_batches = int(initial["synchronized_batch_count"])
        after_batches = {
            generation_id: int(initial["apply_chains"][generation_id].last_batch_no)
            for generation_id in ("g1", "g2", "g3")
        }
    g2_cursor = _sync_receipt_cursor(
        conn,
        "g2",
        after_batch_no=after_batches["g2"],
        base_event_id=session["base_event_id"],
    )
    g3_cursor = _sync_receipt_cursor(
        conn,
        "g3",
        after_batch_no=after_batches["g3"],
        base_event_id=session["base_event_id"],
    )
    new_sync_batches = 0
    for g2_receipt, g3_receipt in zip_longest(g2_cursor, g3_cursor):
        if g2_receipt is None or g3_receipt is None or not _matching_sync_receipts(
            g2_receipt, g3_receipt
        ):
            raise ShadowHarnessError("g2/g3 synchronized receipt histories differ")
        body = {
            "schema": SYNC_PROOF_SCHEMA,
            "kind": "synchronized_batch",
            "prior_sync_chain_sha256": sync_chain,
            "phase": str(g2_receipt["phase"]),
            "first_event_id": int(g2_receipt["first_event_id"]),
            "last_event_id": int(g2_receipt["last_event_id"]),
            "event_count": int(g2_receipt["event_count"]),
            "ledger_batch_sha256": str(g2_receipt["ledger_batch_sha256"]),
        }
        sync_chain = _sha256_json(body)
        synchronized_count += int(g2_receipt["event_count"])
        synchronized_through = int(g2_receipt["last_event_id"])
        synchronized_batches += 1
        new_sync_batches += 1
        if new_sync_batches > max_receipts:
            raise ShadowHarnessError("sync proof scan exceeds the hard cap")
    if (
        sync_chain != str(session["sync_chain_sha256"])
        or synchronized_count != int(session["synchronized_event_count"])
        or synchronized_through != session["synchronized_through_event_id"]
        or synchronized_batches != int(session["synchronized_batch_count"])
    ):
        raise ShadowHarnessError("persistent routed sync chain changed")
    if synchronized_through is not None:
        seal = conn.execute(
            "SELECT seal FROM event_log WHERE id=?", (synchronized_through,)
        ).fetchone()
        if seal is None or seal[0] != session["synchronized_head_seal"]:
            raise ShadowHarnessError("persistent routed sync head seal changed")
    session_state = str(session["state"])
    sequence_ids = (
        ("g1", "g2", "g3")
        if session_state == "armed"
        else ("g1", "g3")
        if session_state == "cutover"
        else ("g2", "g3")
    )
    _require_equal_sequence_boundary(
        conn,
        sequence_ids,
        expected_digest=str(session["synchronized_sequence_digest_sha256"]),
    )
    return {
        "apply_chains": chains,
        "sync_chain_sha256": sync_chain,
        "synchronized_event_count": synchronized_count,
        "synchronized_through_event_id": synchronized_through,
        "synchronized_batch_count": synchronized_batches,
        "validated_receipt_count": sum(
            chain.receipt_count for chain in chains.values()
        ),
        "incremental_receipt_count": sum(
            chain.receipt_count
            - (0 if initial is None else initial["apply_chains"][generation_id].receipt_count)
            for generation_id, chain in chains.items()
        ),
    }


def _update_watermark(
    conn: sqlite3.Connection,
    generation_id: str,
    rows: Sequence[sqlite3.Row],
) -> None:
    if not rows:
        return
    last_id = int(rows[-1]["id"])
    head_seal = rows[-1]["seal"]
    sequence_digest = _sequence_digest(conn, generation_id)
    conn.execute(
        "UPDATE a03b_generation SET built_through_event_id=?,"
        "built_event_count=built_event_count+?,built_head_seal=?,"
        "verified_through_event_id=CASE WHEN state='active' "
        "THEN verified_through_event_id ELSE NULL END,"
        "projection_digest_set_sha256=CASE WHEN state='active' "
        "THEN projection_digest_set_sha256 ELSE NULL END,"
        "sequence_digest_sha256=? "
        "WHERE generation_id=?",
        (last_id, len(rows), head_seal, sequence_digest, generation_id),
    )


def _apply_one_batch(
    conn: sqlite3.Connection,
    *,
    generation_id: str,
    through_id: int,
    batch_events: int,
    batch_bytes: int,
    phase: str,
    owner: str,
    write_collector: _WriteTxnCollector,
    fault: Callable[[str, Mapping[str, Any]], None] | None,
) -> BatchMeasurement | None:
    transaction = _WriteTransaction(
        conn, write_collector, f"projection_batch:{generation_id}:{phase}"
    )
    committed = False
    try:
        _require_operation(conn, generation_id, owner)
        status = _status_from_row(_status_row(conn, generation_id))
        _require_current_sequence_digest(conn, generation_id)
        after = status.built_through_event_id or 0
        _emit_fault(fault, "batch_opened", {"generation_id": generation_id})
        if phase == "catch_up":
            _emit_fault(
                fault,
                "catch_up_batch_opened",
                {"generation_id": generation_id},
            )
        if generation_id == "g3" and phase == "independent_replay":
            _emit_fault(
                fault,
                "g3_second_replay_batch_opened",
                {"generation_id": generation_id},
            )
        rows, payload_bytes = _event_batch(
            conn,
            after_id=after,
            through_id=through_id,
            batch_events=batch_events,
            batch_bytes=batch_bytes,
        )
        if not rows:
            transaction.rollback()
            return None
        expected = conn.execute(
            "SELECT MIN(id) FROM event_log WHERE id>? AND id<=?", (after, through_id)
        ).fetchone()[0]
        if expected is None or int(rows[0]["id"]) != int(expected):
            raise ShadowHarnessError(
                "keyset batch did not start at the next ordered event"
            )
        _apply_rows(conn, (generation_id,), rows)
        _emit_fault(
            fault,
            "batch_applied",
            {"generation_id": generation_id, "event_count": len(rows)},
        )
        _update_watermark(conn, generation_id, rows)
        _emit_fault(
            fault,
            "watermark_updated",
            {"generation_id": generation_id, "through": int(rows[-1]["id"])},
        )
        _, receipt = _record_batch(conn, generation_id, rows, payload_bytes, phase)
        _emit_fault(fault, "batch_pre_commit", {"generation_id": generation_id})
        if phase == "catch_up":
            _emit_fault(
                fault,
                "catch_up_batch_pre_commit",
                {"generation_id": generation_id, "event_count": len(rows)},
            )
        if generation_id == "g3" and phase == "independent_replay":
            _emit_fault(
                fault,
                "g3_second_replay_batch_pre_commit",
                {"generation_id": generation_id, "event_count": len(rows)},
            )
        transaction.commit()
        committed = True
        elapsed = transaction.transaction_seconds
        measurement = BatchMeasurement(
            generation_id=generation_id,
            phase=phase,
            first_event_id=int(rows[0]["id"]),
            last_event_id=int(rows[-1]["id"]),
            event_count=len(rows),
            payload_bytes=payload_bytes,
            transaction_seconds=elapsed,
            receipt_sha256=receipt,
        )
        try:
            _emit_fault(fault, "batch_post_commit", asdict(measurement))
            if phase == "catch_up":
                _emit_fault(
                    fault,
                    "catch_up_batch_post_commit",
                    {
                        "generation_id": generation_id,
                        "event_count": len(rows),
                    },
                )
            if generation_id == "g3" and phase == "independent_replay":
                _emit_fault(
                    fault,
                    "g3_second_replay_batch_post_commit",
                    {
                        "generation_id": generation_id,
                        "event_count": len(rows),
                    },
                )
        except BaseException as exc:
            raise PostCommitFault("batch callback failed after commit") from exc
        return measurement
    except BaseException:
        if not committed:
            transaction.rollback()
        raise


def _prepare_generation(
    conn: sqlite3.Connection,
    generation_id: str,
    *,
    target: HeadFence,
    state: str,
    owner: str,
    force_reset: bool,
    write_collector: _WriteTxnCollector,
    fault: Callable[[str, Mapping[str, Any]], None] | None,
) -> BatchAggregate:
    if state not in {"building", "catching_up"}:
        raise ValueError(state)
    aggregate = BatchAggregate()
    transaction = _WriteTransaction(
        conn, write_collector, f"generation_prepare_metadata:{generation_id}"
    )
    try:
        _require_operation(conn, generation_id, owner)
        current = _status_from_row(_status_row(conn, generation_id))
        _require_current_sequence_digest(conn, generation_id)
        should_reset = force_reset or current.built_event_count == 0
        updated = conn.execute(
            "UPDATE a03b_generation SET state=?,build_target_event_id=?,"
            "verified_through_event_id=NULL,projection_digest_set_sha256=NULL,verified_at=NULL "
            "WHERE generation_id=? AND state IN ('building','catching_up','verified')",
            (state, target.head_id, generation_id),
        ).rowcount
        if updated != 1:
            raise ShadowHarnessError("generation prepare state CAS failed")
        if should_reset:
            conn.execute(
                "UPDATE a03b_generation SET built_through_event_id=NULL,"
                "verified_through_event_id=NULL,full_digest_verified_through_event_id=NULL,"
                "built_event_count=0,built_head_seal=NULL,projection_digest_set_sha256=NULL,"
                "verified_at=NULL,activated_at=NULL,retired_at=NULL WHERE generation_id=?",
                (generation_id,),
            )
        transaction.commit()
        aggregate.add_auxiliary(transaction.transaction_seconds)
    except BaseException:
        transaction.rollback()
        raise
    if should_reset:
        aggregate.merge(
            _bounded_clear_generation(
                conn,
                generation_id,
                owner=owner,
                batch_rows=DEFAULT_BATCH_EVENTS,
                write_collector=write_collector,
                fault=fault,
            )
        )
    return aggregate


def _build_generation(
    conn: sqlite3.Connection,
    generation_id: str,
    target: HeadFence,
    *,
    batch_events: int,
    batch_bytes: int,
    phase: str,
    reset: bool,
    owner: str,
    write_collector: _WriteTxnCollector,
    fault: Callable[[str, Mapping[str, Any]], None] | None,
    writer_handoff: Callable[[sqlite3.Connection], float],
    writer_handoff_strategy: str,
    force_reset: bool = False,
) -> BatchAggregate:
    measurements = BatchAggregate()
    if reset:
        measurements.merge(
            _prepare_generation(
                conn,
                generation_id,
                target=target,
                state="building",
                owner=owner,
                force_reset=force_reset,
                write_collector=write_collector,
                fault=fault,
            )
        )
    else:
        with _measured_write(
            conn, write_collector, f"generation_target_metadata:{generation_id}"
        ) as transaction:
            _require_operation(conn, generation_id, owner)
            conn.execute(
                "UPDATE a03b_generation SET build_target_event_id=? WHERE generation_id=?",
                (target.head_id, generation_id),
            )
        measurements.add_auxiliary(transaction.transaction_seconds)
    if target.head_id is None:
        with _measured_write(
            conn,
            write_collector,
            f"generation_empty_target_metadata:{generation_id}",
        ) as transaction:
            _require_operation(conn, generation_id, owner)
            conn.execute(
                "UPDATE a03b_generation SET build_target_event_id=NULL,built_event_count=0 "
                "WHERE generation_id=?",
                (generation_id,),
            )
        measurements.add_auxiliary(transaction.transaction_seconds)
        return measurements
    while True:
        status = _status_from_row(_status_row(conn, generation_id))
        if (status.built_through_event_id or 0) >= target.head_id:
            break
        item = _apply_one_batch(
            conn,
            generation_id=generation_id,
            through_id=target.head_id,
            batch_events=batch_events,
            batch_bytes=batch_bytes,
            phase=phase,
            owner=owner,
            write_collector=write_collector,
            fault=fault,
        )
        if item is None:
            raise ShadowHarnessError("generation stopped before its fixed target head")
        measurements.add(item)
        measurements.add_writer_yield(
            writer_handoff(conn), strategy=writer_handoff_strategy
        )
    final = _status_from_row(_status_row(conn, generation_id))
    if final.built_event_count != target.event_count:
        raise ShadowHarnessError(
            f"generation event count {final.built_event_count} != fixed count {target.event_count}"
        )
    return measurements


class _ResourceSampler(AbstractContextManager["_ResourceSampler"]):
    def __init__(self, path: Path, interval_seconds: float = 0.02):
        self.path = path
        self.interval_seconds = interval_seconds
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.peak_rss_bytes = 0
        self.highwater = {"database": 0, "wal": 0, "shm": 0, "journal": 0}
        self.samples = 0

    def _sample(self) -> None:
        try:
            rss = psutil.Process(os.getpid()).memory_info().rss
        except (psutil.Error, OSError):
            rss = 0
        self.peak_rss_bytes = max(self.peak_rss_bytes, int(rss))
        for key, suffix in (("database", ""), ("wal", "-wal"), ("shm", "-shm"), ("journal", "-journal")):
            candidate = Path(str(self.path) + suffix)
            try:
                size = candidate.stat().st_size
            except FileNotFoundError:
                size = 0
            self.highwater[key] = max(self.highwater[key], int(size))
        self.samples += 1

    def _loop(self) -> None:
        while not self.stop.wait(self.interval_seconds):
            self._sample()

    def __enter__(self) -> "_ResourceSampler":
        self._sample()
        self.thread.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.stop.set()
        self.thread.join(timeout=max(1.0, self.interval_seconds * 4))
        self._sample()


def build_shadow(
    database_path: Path | str,
    *,
    disposable_root: Path | str,
    generation_id: str = "g2",
    batch_events: int = DEFAULT_BATCH_EVENTS,
    batch_bytes: int = DEFAULT_BATCH_BYTES,
    sample_interval_seconds: float = 0.02,
    fault: Callable[[str, Mapping[str, Any]], None] | None = None,
    _writer_handoff: Callable[[sqlite3.Connection], float] | None = None,
) -> dict[str, Any]:
    """Build G2 to one fixed H0 using independently committed bounded batches."""
    _require_batch_caps(batch_events, batch_bytes)
    path, safety = _safety_path(database_path, disposable_root)
    conn = _open(path)
    write_collector = _WriteTxnCollector("build_shadow")
    started = time.perf_counter_ns()
    owner: str | None = None
    with _ResourceSampler(path, sample_interval_seconds) as sampler:
        try:
            _require_wal(conn, "shadow build")
            _validate_extended_schema(conn)
            owner = _claim_operations(
                conn,
                {generation_id: "shadow"},
                allowed_states=frozenset({"building", "catching_up"}),
                write_collector=write_collector,
            )
            target = _capture_head(conn)
            measurements = _build_generation(
                conn,
                generation_id,
                target,
                batch_events=batch_events,
                batch_bytes=batch_bytes,
                phase="shadow_build",
                reset=True,
                owner=owner,
                write_collector=write_collector,
                fault=fault,
                writer_handoff=_writer_handoff or _yield_to_competing_writer,
                writer_handoff_strategy=(
                    "cooperative-writer-admission-slot"
                    if _writer_handoff is not None
                    else "bounded-scheduler-yield"
                ),
            )
        finally:
            if conn.in_transaction:
                conn.rollback()
            if owner is not None:
                _release_operations(
                    conn,
                    owner,
                    write_collector=write_collector,
                    strict=False,
                )
            conn.close()
    elapsed = (time.perf_counter_ns() - started) / 1_000_000_000
    write_transactions = write_collector.receipt()
    return {
        "schema": RECEIPT_SCHEMA,
        "operation": "shadow_build",
        "generation_id": generation_id,
        "fixed_head": asdict(target),
        "batch_events": batch_events,
        "batch_bytes": batch_bytes,
        "batch_count": measurements.batch_count,
        "processed_events": measurements.processed_events,
        "duration_seconds": elapsed,
        "transaction_samples": measurements.receipt_samples(),
        "transaction_samples_truncated": (
            measurements.batch_count > len(measurements.receipt_samples())
        ),
        "max_batch_transaction_seconds": measurements.max_transaction_seconds,
        "auxiliary_transaction_count": measurements.auxiliary_transaction_count,
        "max_auxiliary_transaction_seconds": (
            measurements.max_auxiliary_transaction_seconds
        ),
        "max_write_transaction_seconds": max(
            measurements.max_write_transaction_seconds,
            float(write_transactions["overall_max_transaction_seconds"]),
        ),
        "post_batch_writer_yield": measurements.writer_yield_receipt(),
        "within_writer_block_budget": (
            write_transactions["pass"] is True
        ),
        "write_transactions": write_transactions,
        "peak_rss_bytes": sampler.peak_rss_bytes,
        "storage_highwater_bytes": dict(sampler.highwater),
        "payloads_logged": False,
        "absolute_paths_logged": False,
        "safety": safety,
    }


def catch_up_shadow(
    database_path: Path | str,
    *,
    disposable_root: Path | str,
    generation_id: str = "g2",
    batch_events: int = DEFAULT_BATCH_EVENTS,
    batch_bytes: int = DEFAULT_BATCH_BYTES,
    close_gap_events: int = 0,
    max_rounds: int = 100,
    fault: Callable[[str, Mapping[str, Any]], None] | None = None,
    _writer_handoff: Callable[[sqlite3.Connection], float] | None = None,
) -> dict[str, Any]:
    """Apply bounded Hprev+1..Hround rounds until the configured close gap."""
    _require_batch_caps(batch_events, batch_bytes)
    if not 1 <= max_rounds <= 10_000 or close_gap_events < 0:
        raise ShadowHarnessError("catch-up round/gap configuration exceeds hard caps")
    path, safety = _safety_path(database_path, disposable_root)
    conn = _open(path)
    write_collector = _WriteTxnCollector("catch_up_shadow")
    rounds: list[dict[str, Any]] = []
    all_batches = BatchAggregate()
    started = time.perf_counter_ns()
    owner: str | None = None
    try:
        _require_wal(conn, "shadow catch-up")
        _validate_extended_schema(conn)
        owner = _claim_operations(
            conn,
            {generation_id: "shadow"},
            allowed_states=frozenset({"building", "catching_up", "verified"}),
            write_collector=write_collector,
        )
        arrival_start = _capture_head(conn)
        with _measured_write(
            conn, write_collector, "catch_up_state_transition"
        ) as transition_transaction:
            _require_operation(conn, generation_id, owner)
            updated = conn.execute(
                "UPDATE a03b_generation SET state='catching_up' WHERE generation_id=? "
                "AND state IN ('building','catching_up','verified')",
                (generation_id,),
            ).rowcount
            if updated != 1:
                raise ShadowHarnessError("catch-up state CAS failed")
        all_batches.add_auxiliary(transition_transaction.transaction_seconds)
        for round_no in range(1, max_rounds + 1):
            round_started_ns = time.perf_counter_ns()
            before = _status_from_row(_status_row(conn, generation_id))
            target = _capture_head(conn)
            before_id = before.built_through_event_id or 0
            gap = int(
                conn.execute(
                    "SELECT COUNT(*) FROM event_log WHERE id>? AND id<=?",
                    (before_id, target.head_id or 0),
                ).fetchone()[0]
            )
            if gap <= close_gap_events:
                rounds.append(
                    {
                        "round": round_no,
                        "captured_head": target.head_id,
                        "tail_gap": gap,
                        "events": 0,
                        "duration_seconds": (
                            time.perf_counter_ns() - round_started_ns
                        )
                        / 1_000_000_000,
                        "catch_up_rate_events_per_second": 0.0,
                    }
                )
                break
            batches = _build_generation(
                conn,
                generation_id,
                target,
                batch_events=batch_events,
                batch_bytes=batch_bytes,
                phase="catch_up",
                reset=False,
                owner=owner,
                write_collector=write_collector,
                fault=fault,
                writer_handoff=_writer_handoff or _yield_to_competing_writer,
                writer_handoff_strategy=(
                    "cooperative-writer-admission-slot"
                    if _writer_handoff is not None
                    else "bounded-scheduler-yield"
                ),
            )
            all_batches.merge(batches)
            after = _status_from_row(_status_row(conn, generation_id))
            round_seconds = (
                time.perf_counter_ns() - round_started_ns
            ) / 1_000_000_000
            round_events = after.built_event_count - before.built_event_count
            rounds.append(
                {
                    "round": round_no,
                    "captured_head": target.head_id,
                    "tail_gap": gap,
                    "events": round_events,
                    "batch_count": batches.batch_count,
                    "duration_seconds": round_seconds,
                    "catch_up_rate_events_per_second": (
                        round_events / round_seconds if round_seconds > 0 else None
                    ),
                }
            )
            latest = _capture_head(conn)
            latest_gap = int(
                conn.execute(
                    "SELECT COUNT(*) FROM event_log WHERE id>? AND id<=?",
                    (after.built_through_event_id or 0, latest.head_id or 0),
                ).fetchone()[0]
            )
            if latest_gap <= close_gap_events:
                break
        else:
            raise ShadowHarnessError("catch-up did not close within max_rounds")
        final = _status_from_row(_status_row(conn, generation_id))
        head = _capture_head(conn)
        remaining_gap = int(
            conn.execute(
                "SELECT COUNT(*) FROM event_log WHERE id>? AND id<=?",
                (final.built_through_event_id or 0, head.head_id or 0),
            ).fetchone()[0]
        )
        duration_seconds = (time.perf_counter_ns() - started) / 1_000_000_000
        arrived_events = max(0, head.event_count - arrival_start.event_count)
        _emit_fault(
            fault,
            "catch_up_complete",
            {
                "generation_id": generation_id,
                "through": final.built_through_event_id,
                "remaining_tail_gap": remaining_gap,
                "round_count": len(rounds),
            },
        )
        if owner is not None:
            _release_operations(
                conn,
                owner,
                write_collector=write_collector,
                strict=False,
            )
            owner = None
        write_transactions = write_collector.receipt()
        return {
            "schema": RECEIPT_SCHEMA,
            "operation": "catch_up",
            "generation_id": generation_id,
            "rounds": rounds,
            "catch_up_rounds": len(rounds),
            "processed_events": all_batches.processed_events,
            "duration_seconds": duration_seconds,
            "catch_up_rate_events_per_second": (
                all_batches.processed_events / duration_seconds
                if duration_seconds > 0
                else None
            ),
            "observed_arrival_events": arrived_events,
            "event_arrival_rate_events_per_second": (
                arrived_events / duration_seconds if duration_seconds > 0 else None
            ),
            "remaining_tail_gap": remaining_gap,
            "max_batch_transaction_seconds": all_batches.max_transaction_seconds,
            "max_write_transaction_seconds": max(
                all_batches.max_write_transaction_seconds,
                float(write_transactions["overall_max_transaction_seconds"]),
            ),
            "post_batch_writer_yield": all_batches.writer_yield_receipt(),
            "within_writer_block_budget": (
                write_transactions["pass"] is True
            ),
            "write_transactions": write_transactions,
            "payloads_logged": False,
            "safety": safety,
        }
    finally:
        if conn.in_transaction:
            conn.rollback()
        if owner is not None:
            _release_operations(
                conn,
                owner,
                write_collector=write_collector,
                strict=False,
            )
        conn.close()


def _sequence_state(conn: sqlite3.Connection, generation_id: str) -> dict[str, int]:
    mapping = _table_map(generation_id)
    result: dict[str, int] = {}
    for logical in SEQUENCE_TABLES:
        row = conn.execute(
            "SELECT seq FROM sqlite_sequence WHERE name=?", (mapping[logical],)
        ).fetchone()
        result[logical] = 0 if row is None else int(row[0])
    return result


def _sequence_digest(conn: sqlite3.Connection, generation_id: str) -> str:
    return _sha256_json(_sequence_state(conn, generation_id))


def _require_current_sequence_digest(
    conn: sqlite3.Connection, generation_id: str
) -> dict[str, int]:
    """Reject sqlite_sequence drift before legitimate writes can bless it."""
    status = _status_from_row(_status_row(conn, generation_id))
    sequences = _sequence_state(conn, generation_id)
    if _sha256_json(sequences) != status.sequence_digest_sha256:
        raise ShadowHarnessError("INVALID_SEQUENCE_STATE")
    return sequences


def _require_equal_sequence_boundary(
    conn: sqlite3.Connection,
    generation_ids: Sequence[str],
    *,
    expected_digest: str | None = None,
) -> str:
    states = {
        generation_id: _require_current_sequence_digest(conn, generation_id)
        for generation_id in generation_ids
    }
    first = states[generation_ids[0]]
    if any(state != first for state in states.values()):
        raise ShadowHarnessError("INVALID_SEQUENCE_BOUNDARY")
    digest = _sha256_json(first)
    if expected_digest is not None and digest != expected_digest:
        raise ShadowHarnessError("INVALID_SYNCHRONIZED_SEQUENCE_DIGEST")
    return digest


def _stream_generation_digests_conn(
    conn: sqlite3.Connection, generation_id: str, batch_events: int
) -> dict[str, Any]:
    _require_current_sequence_digest(conn, generation_id)
    adapter = GenerationConnection(conn, generation_id)
    projection = a03a.stream_projection_digests(adapter, batch_events)
    sequences = _sequence_state(conn, generation_id)
    return {
        "generation_id": generation_id,
        "projections": projection,
        "sequences": sequences,
        "sequence_digest_schema": SEQUENCE_DIGEST_SCHEMA,
        "sequence_digest_sha256": _sha256_json(sequences),
    }


def stream_generation_digests(
    database_path: Path | str,
    generation_id: str,
    *,
    disposable_root: Path | str,
    batch_events: int = DEFAULT_BATCH_EVENTS,
) -> dict[str, Any]:
    _require_batch_caps(batch_events)
    path, safety = _safety_path(database_path, disposable_root)
    conn = _open(path)
    try:
        _require_wal(conn, "generation digest")
        _validate_extended_schema(conn)
        conn.execute("BEGIN")
        result = _stream_generation_digests_conn(conn, generation_id, batch_events)
        conn.commit()
        result["safety"] = safety
        return result
    finally:
        conn.close()


def _fence_through(conn: sqlite3.Connection, through_id: int | None) -> a03a.ReplayFence:
    if through_id is None:
        return a03a.ReplayFence(
            head_id=None,
            event_count=0,
            min_id=None,
            epoch_event_id=None,
            head_seal=None,
        )
    count, minimum = conn.execute(
        "SELECT COUNT(*),MIN(id) FROM event_log WHERE id<=?", (through_id,)
    ).fetchone()
    head = conn.execute(
        "SELECT seal FROM event_log WHERE id=?", (through_id,)
    ).fetchone()
    if head is None:
        raise ShadowHarnessError("generation watermark no longer names an event")
    epoch = conn.execute(
        "SELECT id FROM event_log WHERE event_type=? AND id<=? ORDER BY id LIMIT 1",
        ("ledger_epoch_opened", through_id),
    ).fetchone()
    return a03a.ReplayFence(
        head_id=through_id,
        event_count=int(count),
        min_id=None if minimum is None else int(minimum),
        epoch_event_id=None if epoch is None else int(epoch[0]),
        head_seal=head[0],
    )


def _record_verification(
    conn: sqlite3.Connection,
    generation_id: str,
    verifier_generation_id: str,
    fence: a03a.ReplayFence,
    ledger_binding: Mapping[str, Any],
    digest: Mapping[str, Any],
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO a03b_verification("
        "generation_id,through_event_id,event_count,ledger_sha256,"
        "projection_digests_json,projection_digest_set_sha256,sequences_json,"
        "sequence_digest_sha256,second_replay_generation_id,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            generation_id,
            fence.head_id or 0,
            fence.event_count,
            ledger_binding["sha256"],
            json.dumps(digest["projections"]["digests"], sort_keys=True, separators=(",", ":")),
            digest["projections"]["digest_set_sha256"],
            json.dumps(digest["sequences"], sort_keys=True, separators=(",", ":")),
            digest["sequence_digest_sha256"],
            verifier_generation_id,
            _utc_now(),
        ),
    )
    conn.execute(
        "UPDATE a03b_generation SET state='verified',verified_through_event_id=?,"
        "full_digest_verified_through_event_id=?,projection_digest_set_sha256=?,"
        "verified_at=? WHERE generation_id=?",
        (
            fence.head_id,
            fence.head_id,
            digest["projections"]["digest_set_sha256"],
            _utc_now(),
            generation_id,
        ),
    )


def _apply_sync_pair_batch(
    conn: sqlite3.Connection,
    *,
    generation_id: str,
    verifier_generation_id: str,
    through_id: int,
    batch_events: int,
    batch_bytes: int,
    owner: str,
    phase: str,
    write_collector: _WriteTxnCollector,
    fault: Callable[[str, Mapping[str, Any]], None] | None,
) -> BatchMeasurement | None:
    """Advance G2/G3 and their common proof in one bounded write transaction."""
    transaction = _WriteTransaction(
        conn, write_collector, f"sync_pair_batch:{phase}"
    )
    committed = False
    try:
        _require_wal(conn, "paired sync batch")
        _require_operation(conn, generation_id, owner)
        _require_operation(conn, verifier_generation_id, owner)
        shadow = _status_from_row(_status_row(conn, generation_id))
        verifier = _status_from_row(_status_row(conn, verifier_generation_id))
        session = _sync_session(conn)
        _require_equal_sequence_boundary(
            conn,
            (generation_id, verifier_generation_id),
            expected_digest=str(session["synchronized_sequence_digest_sha256"]),
        )
        if (
            shadow.state != "catching_up"
            or verifier.state != "catching_up"
            or shadow.built_through_event_id != verifier.built_through_event_id
            or shadow.built_event_count != verifier.built_event_count
            or shadow.built_head_seal != verifier.built_head_seal
        ):
            raise ShadowHarnessError("paired sync generations lost their common watermark")
        after = shadow.built_through_event_id or 0
        rows, payload_bytes = _event_batch(
            conn,
            after_id=after,
            through_id=through_id,
            batch_events=batch_events,
            batch_bytes=batch_bytes,
        )
        if not rows:
            transaction.rollback()
            return None
        _validate_controlled_tail(
            conn, rows, previous_seal=shadow.built_head_seal
        )
        _emit_fault(
            fault,
            "sync_batch_opened",
            {"event_count": len(rows), "phase": phase},
        )
        _apply_rows(conn, (generation_id, verifier_generation_id), rows)
        for target_id in (generation_id, verifier_generation_id):
            _update_watermark(conn, target_id, rows)
            _record_batch(conn, target_id, rows, payload_bytes, phase)
        chain = _advance_sync_proof(conn, rows, phase=phase)
        _emit_fault(
            fault,
            "sync_batch_pre_commit",
            {"event_count": len(rows), "phase": phase},
        )
        transaction.commit()
        committed = True
        measurement = BatchMeasurement(
            generation_id=f"{generation_id}+{verifier_generation_id}",
            phase=phase,
            first_event_id=int(rows[0]["id"]),
            last_event_id=int(rows[-1]["id"]),
            event_count=len(rows),
            payload_bytes=payload_bytes,
            transaction_seconds=transaction.transaction_seconds,
            receipt_sha256=chain,
        )
        try:
            _emit_fault(
                fault,
                "sync_batch_post_commit",
                {
                    "event_count": len(rows),
                    "phase": phase,
                    "lock_wait_seconds": transaction.lock_wait_seconds,
                    "transaction_seconds": measurement.transaction_seconds,
                },
            )
        except BaseException as exc:
            raise PostCommitFault("sync batch callback failed after commit") from exc
        return measurement
    except BaseException:
        if not committed:
            transaction.rollback()
        raise


def _prepare_sync_tail(
    conn: sqlite3.Connection,
    *,
    generation_id: str,
    verifier_generation_id: str,
    batch_events: int,
    batch_bytes: int,
    max_admission_tail_events: int,
    owner: str,
    write_collector: _WriteTxnCollector,
    fault: Callable[[str, Mapping[str, Any]], None] | None,
    writer_handoff: Callable[[sqlite3.Connection], float],
    writer_handoff_strategy: str,
    max_rounds: int = 100,
) -> tuple[BatchAggregate, int]:
    """Paired bounded catch-up until the remaining admission tail is small."""
    aggregate = BatchAggregate()
    for round_no in range(1, max_rounds + 1):
        target = _capture_head(conn)
        while True:
            status = _status_from_row(_status_row(conn, generation_id))
            if (status.built_through_event_id or 0) >= (target.head_id or 0):
                break
            measurement = _apply_sync_pair_batch(
                conn,
                generation_id=generation_id,
                verifier_generation_id=verifier_generation_id,
                through_id=target.head_id or 0,
                batch_events=batch_events,
                batch_bytes=batch_bytes,
                owner=owner,
                phase="sync_prepare",
                write_collector=write_collector,
                fault=fault,
            )
            if measurement is None:
                raise ShadowHarnessError("paired sync stopped before its fixed head")
            aggregate.add(measurement)
            aggregate.add_writer_yield(
                writer_handoff(conn), strategy=writer_handoff_strategy
            )
        shadow = _status_from_row(_status_row(conn, generation_id))
        verifier = _status_from_row(_status_row(conn, verifier_generation_id))
        if (
            shadow.built_through_event_id != target.head_id
            or verifier.built_through_event_id != target.head_id
            or shadow.built_event_count != target.event_count
            or verifier.built_event_count != target.event_count
        ):
            raise ShadowHarnessError("paired sync did not reach its fixed target")
        active = _status_from_row(_status_row(conn, "g1"))
        remaining = active.built_event_count - shadow.built_event_count
        if remaining < 0:
            raise ShadowHarnessError("sync candidate advanced beyond active generation")
        if remaining <= max_admission_tail_events:
            return aggregate, round_no
    raise ShadowHarnessError("paired sync did not bound the admission tail")


def _admit_synchronous_writes(
    conn: sqlite3.Connection,
    *,
    generation_id: str,
    verifier_generation_id: str,
    max_tail_events: int,
    max_tail_bytes: int,
    owner: str,
    proof_checkpoint: Mapping[str, Any],
    direct_cutover: bool,
    write_collector: _WriteTxnCollector,
    fault: Callable[[str, Mapping[str, Any]], None] | None,
) -> dict[str, Any]:
    """Close a bounded tail, then select A direct-CAS or B routed synchronization."""
    if not 1 <= max_tail_events <= MAX_BATCH_EVENTS:
        raise ShadowHarnessError("admission event cap exceeds the hard boundedness cap")
    if not 1 <= max_tail_bytes <= MAX_BATCH_BYTES:
        raise ShadowHarnessError("admission byte cap exceeds the hard boundedness cap")
    conn.execute(f"PRAGMA busy_timeout={round(WRITER_BLOCK_BUDGET_SECONDS * 1000)}")
    transaction = _WriteTransaction(
        conn,
        write_collector,
        "a_bounded_admission_and_cutover" if direct_cutover else "b_sync_admission",
    )
    attempt_ns = transaction.attempt_ns
    lock_ns = transaction.lock_ns
    committed = False
    try:
        _require_wal(conn, "sync admission")
        _validate_extended_schema(conn)
        topology = _topology_snapshot(conn)
        if topology["kind"] != "old_active_sync_preparing":
            raise CutoverNotReady("sync admission topology is not preparing")
        _require_operation(conn, generation_id, owner)
        _require_operation(conn, verifier_generation_id, owner)
        control = conn.execute(
            "SELECT active_generation_id,sync_generation_id,revision "
            "FROM a03b_control WHERE singleton=1"
        ).fetchone()
        if str(control["active_generation_id"]) != "g1":
            raise CutoverNotReady("sync admission requires g1 to remain active")
        if control["sync_generation_id"] is not None:
            raise CutoverNotReady("a routed sync generation is already armed")
        session = _sync_session(conn)
        if (
            str(session["state"]) != "preparing"
            or str(session["shadow_generation_id"]) != generation_id
            or str(session["verifier_generation_id"]) != verifier_generation_id
        ):
            raise CutoverNotReady("sync admission session metadata changed")
        shadow = _status_from_row(_status_row(conn, generation_id))
        verifier = _status_from_row(_status_row(conn, verifier_generation_id))
        active = _status_from_row(_status_row(conn, "g1"))
        if (
            shadow.state != "catching_up"
            or verifier.state != "catching_up"
            or shadow.built_through_event_id != verifier.built_through_event_id
            or shadow.built_event_count != verifier.built_event_count
            or shadow.built_head_seal != verifier.built_head_seal
        ):
            raise CutoverNotReady("sync candidates do not share one prepared state")
        last = conn.execute(
            "SELECT id,seal FROM event_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        ledger_head_id = None if last is None else int(last["id"])
        ledger_head_seal = None if last is None else last["seal"]
        if (
            active.built_through_event_id != ledger_head_id
            or active.built_head_seal != ledger_head_seal
        ):
            raise CutoverNotReady(
                "active routed-writer metadata does not bind the admission head"
            )
        tail_count = active.built_event_count - shadow.built_event_count
        if tail_count < 0:
            raise CutoverNotReady("sync candidate advanced beyond active generation")
        if tail_count > max_tail_events:
            transaction.rollback()
            return {
                "outcome": "not_ready_tail_bound",
                "committed": False,
                "tail_event_count": tail_count,
                "max_tail_events": max_tail_events,
                "max_tail_bytes": max_tail_bytes,
            }
        rows, record_bytes = _event_batch(
            conn,
            after_id=shadow.built_through_event_id or 0,
            through_id=ledger_head_id or 0,
            batch_events=max_tail_events,
            batch_bytes=max_tail_bytes,
        )
        if len(rows) != tail_count:
            transaction.rollback()
            return {
                "outcome": "not_ready_tail_bound",
                "committed": False,
                "tail_event_count": tail_count,
                "tail_record_bytes_at_least": record_bytes,
                "max_tail_events": max_tail_events,
                "max_tail_bytes": max_tail_bytes,
            }
        _validate_controlled_tail(
            conn, rows, previous_seal=shadow.built_head_seal
        )
        _emit_fault(
            fault,
            "sync_admission_opened",
            {"tail_event_count": tail_count, "tail_record_bytes": record_bytes},
        )
        if rows:
            _apply_rows(conn, (generation_id, verifier_generation_id), rows)
            for target_id in (generation_id, verifier_generation_id):
                _update_watermark(conn, target_id, rows)
                _record_batch(
                    conn, target_id, rows, record_bytes, "sync_admission"
                )
            _advance_sync_proof(conn, rows, phase="sync_admission")
        proof = _validate_persistent_proofs(
            conn,
            initial=proof_checkpoint,
            max_receipts=max(16, max_tail_events * 3 + 16),
        )
        shadow = _status_from_row(_status_row(conn, generation_id))
        verifier = _status_from_row(_status_row(conn, verifier_generation_id))
        session = _sync_session(conn)
        if not (
            shadow.built_through_event_id
            == verifier.built_through_event_id
            == active.built_through_event_id
            == session["synchronized_through_event_id"]
            and shadow.built_event_count
            == verifier.built_event_count
            == active.built_event_count
            == int(session["synchronized_event_count"])
            and shadow.built_head_seal
            == verifier.built_head_seal
            == active.built_head_seal
            == session["synchronized_head_seal"]
        ):
            raise CutoverNotReady("sync admission did not establish equal watermarks")
        if not _verified_base_receipts_valid(conn, session):
            raise CutoverNotReady("verified-base receipts changed before admission")
        _require_equal_sequence_boundary(
            conn,
            ("g1", generation_id, verifier_generation_id),
            expected_digest=str(session["synchronized_sequence_digest_sha256"]),
        )
        now = _utc_now()
        pointer_started_ns = time.perf_counter_ns()
        selected_mode: str
        if direct_cutover:
            selected_mode = "a_bounded_fence"
            if conn.execute(
                "UPDATE a03b_control SET active_generation_id=?,sync_generation_id=NULL,"
                "revision=revision+1,cutover_head_event_id=?,updated_at=? "
                "WHERE singleton=1 AND active_generation_id='g1' "
                "AND sync_generation_id IS NULL AND revision=?",
                (
                    generation_id,
                    shadow.built_through_event_id,
                    now,
                    int(control["revision"]),
                ),
            ).rowcount != 1:
                raise CutoverNotReady("A direct active-generation CAS failed")
            conn.execute(
                "UPDATE a03b_generation SET state='retired',retired_at=? "
                "WHERE generation_id='g1'",
                (now,),
            )
            conn.execute(
                "UPDATE a03b_generation SET state='active',activated_at=?,"
                "verified_through_event_id=?,projection_digest_set_sha256=? "
                "WHERE generation_id=?",
                (
                    now,
                    session["base_event_id"],
                    session["base_projection_digest_set_sha256"],
                    generation_id,
                ),
            )
            conn.execute(
                "UPDATE a03b_generation SET state='verified',verified_through_event_id=?,"
                "projection_digest_set_sha256=?,verified_at=? WHERE generation_id=?",
                (
                    session["base_event_id"],
                    session["base_projection_digest_set_sha256"],
                    now,
                    verifier_generation_id,
                ),
            )
            if conn.execute(
                "UPDATE a03b_sync_session SET state='cutover',admitted_at=?,cutover_at=? "
                "WHERE singleton=1 AND state='preparing'",
                (now, now),
            ).rowcount != 1:
                raise CutoverNotReady("A sync-session cutover CAS failed")
            conn.execute(
                "DELETE FROM a03b_operation_lock WHERE owner_token=?", (owner,)
            )
        else:
            selected_mode = "b_routed_sync"
            if conn.execute(
                "UPDATE a03b_sync_session SET state='armed',admitted_at=? "
                "WHERE singleton=1 AND state='preparing'",
                (now,),
            ).rowcount != 1:
                raise CutoverNotReady("sync session admission CAS failed")
            if conn.execute(
                "UPDATE a03b_control SET sync_generation_id=?,revision=revision+1,"
                "updated_at=? WHERE singleton=1 AND active_generation_id='g1' "
                "AND sync_generation_id IS NULL AND revision=?",
                (generation_id, now, int(control["revision"])),
            ).rowcount != 1:
                raise CutoverNotReady("sync-generation admission CAS failed")
            _emit_fault(
                fault,
                "sync_admission_armed",
                {"tail_event_count": tail_count, "mode": selected_mode},
            )
        precommit_seconds = (time.perf_counter_ns() - lock_ns) / 1_000_000_000
        if precommit_seconds > WRITER_BLOCK_BUDGET_SECONDS:
            transaction.rollback()
            return {
                "outcome": "not_ready_fence_budget",
                "committed": False,
                "selected_final_sync_mode": selected_mode,
                "tail_event_count": tail_count,
                "fence_seconds_before_rollback": precommit_seconds,
                "within_writer_block_budget": False,
            }
        if direct_cutover:
            _emit_fault(
                fault,
                "cutover_pointer_changed",
                {"revision": int(control["revision"]) + 1, "mode": selected_mode},
            )
            _emit_fault(fault, "cutover_pre_commit", {"mode": selected_mode})
        _emit_fault(fault, "sync_admission_pre_commit", {})
        precommit_seconds = (time.perf_counter_ns() - lock_ns) / 1_000_000_000
        if precommit_seconds > WRITER_BLOCK_BUDGET_SECONDS:
            transaction.rollback()
            return {
                "outcome": "not_ready_fence_budget",
                "committed": False,
                "selected_final_sync_mode": selected_mode,
                "tail_event_count": tail_count,
                "fence_seconds_before_rollback": precommit_seconds,
                "within_writer_block_budget": False,
            }
        transaction.commit()
        committed = True
        commit_ns = time.perf_counter_ns()
        receipt = {
            "outcome": "complete_new" if direct_cutover else "sync_armed",
            "committed": True,
            "selected_final_sync_mode": selected_mode,
            "sync_route_used": not direct_cutover,
            "decision_reason": (
                "bounded admission tail and pointer CAS completed in one fence"
                if direct_cutover
                else "explicit B routed-sync experiment requested"
            ),
            "tail_event_count": tail_count,
            "tail_record_bytes": record_bytes,
            "tail_projection_dml_in_fence": bool(rows),
            "pointer_metadata_and_commit_seconds": (
                commit_ns - pointer_started_ns
            )
            / 1_000_000_000,
            "lock_wait_seconds": (lock_ns - attempt_ns) / 1_000_000_000,
            "fence_seconds": (commit_ns - lock_ns) / 1_000_000_000,
            "within_writer_block_budget": (
                (commit_ns - lock_ns) / 1_000_000_000
                <= WRITER_BLOCK_BUDGET_SECONDS
            ),
            "sync_generation_id": None if direct_cutover else generation_id,
            "verifier_generation_id": verifier_generation_id,
            "operation_leases_released": direct_cutover,
            "synchronized_through_event_id": shadow.built_through_event_id,
            "synchronized_event_count": shadow.built_event_count,
            "sync_chain_sha256": str(session["sync_chain_sha256"]),
            "persistent_receipt_chains_recomputed": True,
            "validated_receipt_count": proof["validated_receipt_count"],
            "incremental_receipt_count_in_fence": proof[
                "incremental_receipt_count"
            ],
            "payloads_logged": False,
            "absolute_paths_logged": False,
        }
        try:
            _emit_fault(fault, "sync_admission_post_commit", receipt)
            if direct_cutover:
                _emit_fault(
                    fault,
                    "cutover_post_commit",
                    {"duration_seconds": receipt["fence_seconds"], "mode": selected_mode},
                )
        except BaseException as exc:
            raise PostCommitFault("sync admission callback failed after commit") from exc
        return receipt
    except BaseException:
        if not committed:
            transaction.rollback()
        raise


def verify_shadow(
    database_path: Path | str,
    *,
    disposable_root: Path | str,
    generation_id: str = "g2",
    verifier_generation_id: str = "g3",
    batch_events: int = DEFAULT_BATCH_EVENTS,
    batch_bytes: int = DEFAULT_BATCH_BYTES,
    require_active_match: bool = True,
    atomic_cutover: bool = False,
    max_admission_tail_events: int = DEFAULT_FINAL_TAIL_EVENTS,
    max_admission_tail_bytes: int = DEFAULT_FINAL_TAIL_BYTES,
    fault: Callable[[str, Mapping[str, Any]], None] | None = None,
    _writer_handoff: Callable[[sqlite3.Connection], float] | None = None,
) -> dict[str, Any]:
    """Verify at W, prove a bounded sync-forward, and arm routed triple-write."""
    _require_batch_caps(batch_events, batch_bytes)
    _require_batch_caps(max_admission_tail_events, max_admission_tail_bytes)
    path, safety = _safety_path(database_path, disposable_root)
    conn = _open(path)
    write_collector = _WriteTxnCollector("verify_shadow")
    started = time.perf_counter_ns()
    metadata_write_max = 0.0
    verification_metadata_transaction: _WriteTransaction | None = None
    owner: str | None = None
    try:
        _require_wal(conn, "shadow verification")
        _validate_extended_schema(conn)
        owner = _claim_operations(
            conn,
            {generation_id: "shadow", verifier_generation_id: "verifier"},
            allowed_states=frozenset({"building", "catching_up", "verified"}),
            write_collector=write_collector,
        )
        with _measured_write(
            conn, write_collector, "verification_session_reset"
        ) as metadata_transaction:
            _require_operation(conn, generation_id, owner)
            _require_operation(conn, verifier_generation_id, owner)
            conn.execute(
                "DELETE FROM a03b_sync_session WHERE singleton=1 AND state='preparing'"
            )
        metadata_write_max = max(
            metadata_write_max,
            metadata_transaction.transaction_seconds,
        )
        # Snapshot G1 and the ledger at W while normal routed writers continue in WAL.
        conn.execute("BEGIN")
        active_id = str(
            conn.execute(
                "SELECT active_generation_id FROM a03b_control WHERE singleton=1"
            ).fetchone()[0]
        )
        if active_id != "g1":
            raise ShadowHarnessError("v1 verification requires g1 to remain active")
        active_status = _status_from_row(_status_row(conn, "g1"))
        active_head = _capture_head(conn)
        watermark = active_head.head_id
        fence = _fence_through(conn, watermark)
        if active_status.built_through_event_id != watermark or (
            active_status.built_event_count != fence.event_count
        ):
            raise ShadowHarnessError(
                "active generation metadata does not bind the captured ledger head"
            )
        ledger_binding = a03a.stream_ledger_binding(conn, fence, batch_events)
        contract_issues = [
            issue
            for issue in a03a.validate_event_contract_bounded(conn, fence, batch_events)
            if issue != "event_log ids are not contiguous"
        ]
        seal_issues = a03a.verify_chain_bounded(conn, fence, batch_events)
        active_digest = _stream_generation_digests_conn(conn, "g1", batch_events)
        conn.commit()
        _emit_fault(fault, "validation_opened", {"through": watermark})
        if contract_issues or seal_issues:
            raise ShadowHarnessError(
                "bounded ledger verification failed: "
                + "; ".join((contract_issues + seal_issues)[:10])
            )

        # Catch G2 to the same W captured above, then replay independently to G3.
        with _measured_write(
            conn, write_collector, "verification_state_transition"
        ) as metadata_transaction:
            _require_operation(conn, generation_id, owner)
            transitioned = conn.execute(
                "UPDATE a03b_generation SET state='catching_up' WHERE generation_id=? "
                "AND state IN ('building','catching_up','verified')",
                (generation_id,),
            ).rowcount
            if transitioned != 1:
                raise ShadowHarnessError("shadow verification transition CAS failed")
        metadata_write_max = max(
            metadata_write_max,
            metadata_transaction.transaction_seconds,
        )
        existing_shadow = _status_from_row(_status_row(conn, generation_id))
        shadow_needs_rebase = (
            (existing_shadow.built_through_event_id or 0) > (watermark or 0)
            or existing_shadow.built_event_count > fence.event_count
        )
        shadow_batches = _build_generation(
            conn,
            generation_id,
            active_head,
            batch_events=batch_events,
            batch_bytes=batch_bytes,
            phase="verification_catch_up",
            reset=shadow_needs_rebase,
            owner=owner,
            write_collector=write_collector,
            fault=fault,
            writer_handoff=_writer_handoff or _yield_to_competing_writer,
            writer_handoff_strategy=(
                "cooperative-writer-admission-slot"
                if _writer_handoff is not None
                else "bounded-scheduler-yield"
            ),
            force_reset=shadow_needs_rebase,
        )
        second_started = time.perf_counter_ns()
        _emit_fault(
            fault,
            "g3_second_replay_opened",
            {"generation_id": verifier_generation_id, "through": watermark},
        )
        verifier_batches = _build_generation(
            conn,
            verifier_generation_id,
            HeadFence(watermark, fence.event_count, fence.head_seal),
            batch_events=batch_events,
            batch_bytes=batch_bytes,
            phase="independent_replay",
            reset=True,
            owner=owner,
            write_collector=write_collector,
            fault=fault,
            writer_handoff=_writer_handoff or _yield_to_competing_writer,
            writer_handoff_strategy=(
                "cooperative-writer-admission-slot"
                if _writer_handoff is not None
                else "bounded-scheduler-yield"
            ),
            force_reset=True,
        )
        _emit_fault(
            fault,
            "g3_second_replay_complete",
            {
                "generation_id": verifier_generation_id,
                "through": watermark,
                "batch_count": verifier_batches.batch_count,
            },
        )
        second_seconds = (time.perf_counter_ns() - second_started) / 1_000_000_000
        conn.execute("BEGIN")
        shadow_digest = _stream_generation_digests_conn(conn, generation_id, batch_events)
        verifier_digest = _stream_generation_digests_conn(
            conn, verifier_generation_id, batch_events
        )
        conn.commit()
        _emit_fault(fault, "validation_digests_computed", {"through": watermark})
        if (
            shadow_digest["projections"] != verifier_digest["projections"]
            or shadow_digest["sequences"] != verifier_digest["sequences"]
        ):
            raise ShadowHarnessError("shadow differs from independent replay")
        if (
            shadow_digest["projections"] != active_digest["projections"]
            or shadow_digest["sequences"] != active_digest["sequences"]
        ):
            raise ShadowHarnessError("shadow differs from active G1 at the bound head")
        verification_metadata_transaction = _WriteTransaction(
            conn, write_collector, "verification_receipts_and_sync_session"
        )
        _require_operation(conn, generation_id, owner)
        _require_operation(conn, verifier_generation_id, owner)
        current_shadow = _status_from_row(_status_row(conn, generation_id))
        current_verifier = _status_from_row(_status_row(conn, verifier_generation_id))
        if (
            _require_current_sequence_digest(conn, generation_id)
            != shadow_digest["sequences"]
            or _require_current_sequence_digest(conn, verifier_generation_id)
            != verifier_digest["sequences"]
        ):
            raise ShadowHarnessError("generation sequences changed during verification")
        if (
            current_shadow.built_through_event_id != watermark
            or current_verifier.built_through_event_id != watermark
            or current_shadow.built_event_count != fence.event_count
            or current_verifier.built_event_count != fence.event_count
        ):
            raise ShadowHarnessError("generation changed during verification")
        control = conn.execute(
            "SELECT active_generation_id,sync_generation_id "
            "FROM a03b_control WHERE singleton=1"
        ).fetchone()
        if control["active_generation_id"] != "g1":
            raise ShadowHarnessError("active pointer changed during verification")
        if control["sync_generation_id"] is not None:
            raise CutoverNotReady(
                "routed sync is already armed; complete or recover that cutover"
            )
        _emit_fault(fault, "validation_pre_commit", {"through": watermark})
        _record_verification(
            conn,
            generation_id,
            verifier_generation_id,
            fence,
            ledger_binding,
            shadow_digest,
        )
        _record_verification(
            conn,
            verifier_generation_id,
            generation_id,
            fence,
            ledger_binding,
            verifier_digest,
        )
        seed = _sync_seed(
            base_event_id=watermark,
            base_event_count=fence.event_count,
            base_head_seal=fence.head_seal,
            base_ledger_sha256=str(ledger_binding["sha256"]),
            base_projection_digest_set_sha256=str(
                shadow_digest["projections"]["digest_set_sha256"]
            ),
            base_sequence_digest_sha256=str(
                shadow_digest["sequence_digest_sha256"]
            ),
        )
        conn.execute("DELETE FROM a03b_sync_session")
        conn.execute(
            "INSERT INTO a03b_sync_session("
            "singleton,state,shadow_generation_id,verifier_generation_id,"
            "base_event_id,base_event_count,base_head_seal,base_ledger_sha256,"
            "base_projection_digest_set_sha256,base_sequence_digest_sha256,"
            "synchronized_through_event_id,"
            "synchronized_event_count,synchronized_head_seal,"
            "synchronized_batch_count,sync_chain_sha256,"
            "synchronized_sequence_digest_sha256,admitted_at,cutover_at) "
            "VALUES (1,'preparing',?,?,?,?,?,?,?,?,?,?,?,0,?,?,NULL,NULL)",
            (
                generation_id,
                verifier_generation_id,
                watermark,
                fence.event_count,
                fence.head_seal,
                ledger_binding["sha256"],
                shadow_digest["projections"]["digest_set_sha256"],
                shadow_digest["sequence_digest_sha256"],
                watermark,
                fence.event_count,
                fence.head_seal,
                seed,
                shadow_digest["sequence_digest_sha256"],
            ),
        )
        conn.execute(
            "UPDATE a03b_generation SET state='catching_up' "
            "WHERE generation_id IN (?,?)",
            (generation_id, verifier_generation_id),
        )
        verification_metadata_transaction.commit()
        metadata_write_max = max(
            metadata_write_max,
            verification_metadata_transaction.transaction_seconds,
        )
        try:
            _emit_fault(fault, "validation_post_commit", {"through": watermark})
        except BaseException as exc:
            raise PostCommitFault("validation callback failed after commit") from exc
        sync_batches = BatchAggregate()
        sync_rounds = 0
        admission: dict[str, Any] | None = None
        for _attempt in range(1, 21):
            prepared, rounds = _prepare_sync_tail(
                conn,
                generation_id=generation_id,
                verifier_generation_id=verifier_generation_id,
                batch_events=batch_events,
                batch_bytes=batch_bytes,
                max_admission_tail_events=max_admission_tail_events,
                owner=owner,
                write_collector=write_collector,
                fault=fault,
                writer_handoff=_writer_handoff or _yield_to_competing_writer,
                writer_handoff_strategy=(
                    "cooperative-writer-admission-slot"
                    if _writer_handoff is not None
                    else "bounded-scheduler-yield"
                ),
            )
            sync_batches.merge(prepared)
            sync_rounds += rounds
            if (
                shadow_batches.max_write_transaction_seconds
                > WRITER_BLOCK_BUDGET_SECONDS
                or verifier_batches.max_write_transaction_seconds
                > WRITER_BLOCK_BUDGET_SECONDS
                or sync_batches.max_write_transaction_seconds
                > WRITER_BLOCK_BUDGET_SECONDS
            ):
                raise ShadowHarnessError(
                    "experimental write transaction exceeded the 2s hard gate"
                )
            conn.execute("BEGIN")
            proof_checkpoint = _validate_persistent_proofs(conn)
            conn.commit()
            admission = _admit_synchronous_writes(
                conn,
                generation_id=generation_id,
                verifier_generation_id=verifier_generation_id,
                max_tail_events=max_admission_tail_events,
                max_tail_bytes=max_admission_tail_bytes,
                owner=owner,
                proof_checkpoint=proof_checkpoint,
                direct_cutover=atomic_cutover,
                write_collector=write_collector,
                fault=fault,
            )
            if admission["committed"]:
                break
        if admission is None or not admission["committed"]:
            raise ShadowHarnessError(
                "bounded routed-sync admission did not complete within 20 attempts"
            )
        if atomic_cutover:
            owner = None
            cutover_receipt: dict[str, Any] | None = {
                **admission,
                "operation": "cutover",
                "final_fence_seconds": admission["fence_seconds"],
                "metadata_only_pointer_change": True,
                "pointer_and_tail_same_fence": True,
                "unsynchronized_tail_event_count": 0,
                "final_sync_mechanism": "A:bounded-tail-plus-pointer-single-fence",
            }
        else:
            _release_operations(
                conn,
                owner,
                write_collector=write_collector,
            )
            owner = None
            cutover_receipt = None
        write_transactions = write_collector.receipt()
        overall_max_write = max(
            shadow_batches.max_write_transaction_seconds,
            verifier_batches.max_write_transaction_seconds,
            sync_batches.max_write_transaction_seconds,
            float(admission["fence_seconds"]),
            metadata_write_max,
            float(write_transactions["overall_max_transaction_seconds"]),
        )
        return {
            "schema": RECEIPT_SCHEMA,
            "operation": "verify_shadow",
            "generation_id": generation_id,
            "verifier_generation_id": verifier_generation_id,
            "through_event_id": watermark,
            "event_count": fence.event_count,
            "duration_seconds": (time.perf_counter_ns() - started) / 1_000_000_000,
            "second_replay_seconds": second_seconds,
            "second_replay_batches": verifier_batches.batch_count,
            "g3_bounded_reset_transaction_count": (
                verifier_batches.auxiliary_transaction_count
            ),
            "g3_bounded_reset_max_transaction_seconds": (
                verifier_batches.max_auxiliary_transaction_seconds
            ),
            "g3_reset_strategy": "bounded-table-and-metadata-delete-batches",
            "shadow_catch_up_batches": shadow_batches.batch_count,
            "sync_prepare_batches": sync_batches.batch_count,
            "sync_prepare_events": sync_batches.processed_events,
            "sync_prepare_rounds": sync_rounds,
            "post_batch_writer_yield": _combined_writer_yield_receipt(
                shadow_batches,
                verifier_batches,
                sync_batches,
            ),
            "sync_admission": admission,
            "selected_final_sync_mode": admission["selected_final_sync_mode"],
            "sync_route_used": admission["sync_route_used"],
            "decision_reason": admission["decision_reason"],
            "write_transaction_max_seconds": {
                "g2_verification_catch_up": (
                    shadow_batches.max_write_transaction_seconds
                ),
                "g3_second_replay": verifier_batches.max_write_transaction_seconds,
                "sync_prepare": sync_batches.max_write_transaction_seconds,
                "sync_admission": float(admission["fence_seconds"]),
                "cutover": (
                    float(admission["fence_seconds"]) if atomic_cutover else None
                ),
                "overall": overall_max_write,
                "verification_metadata": metadata_write_max,
                "limit": WRITER_BLOCK_BUDGET_SECONDS,
                "pass": (
                    overall_max_write <= WRITER_BLOCK_BUDGET_SECONDS
                    and write_transactions["pass"] is True
                ),
            },
            "write_transactions": write_transactions,
            "ledger": ledger_binding,
            "projection_digests": shadow_digest["projections"],
            "sequence_digest_sha256": shadow_digest["sequence_digest_sha256"],
            "sequences": shadow_digest["sequences"],
            "all_twelve_match": True,
            "all_nine_sequences_match": True,
            "active_match_checked": True,
            "active_generation_digest_set_sha256": active_digest["projections"][
                "digest_set_sha256"
            ],
            "event_contract_issues": [],
            "seal_issues": [],
            "cutover": cutover_receipt,
            "payloads_logged": False,
            "safety": safety,
        }
    except BaseException:
        if verification_metadata_transaction is not None:
            verification_metadata_transaction.rollback()
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        if conn.in_transaction:
            conn.rollback()
        if owner is not None:
            _release_operations(
                conn,
                owner,
                write_collector=write_collector,
                strict=False,
            )
        conn.close()


class ActiveReader(AbstractContextManager["ActiveReader"]):
    """One coherent reader transaction bound to exactly one generation."""

    def __init__(self, path: Path, timeout_seconds: float = 5.0):
        self.conn = _open(path, timeout_seconds=timeout_seconds)
        if str(self.conn.execute("PRAGMA journal_mode").fetchone()[0]).lower() != "wal":
            self.conn.close()
            raise ShadowHarnessError("generation reader requires WAL snapshot isolation")
        self.conn.execute("PRAGMA query_only=ON")
        self.conn.execute("BEGIN")
        # The first SELECT establishes a WAL snapshot before resolving the pointer.
        self.conn.execute("SELECT id FROM event_log ORDER BY id DESC LIMIT 1").fetchone()
        topology = _topology_snapshot(self.conn)
        self.generation_id = topology["active"].generation_id
        self.revision = int(topology["control"]["revision"])
        self.generation = GenerationConnection(self.conn, self.generation_id)
        self.closed = False

    def execute(
        self, sql: str, parameters: Sequence[Any] | Mapping[str, Any] = ()
    ) -> sqlite3.Cursor:
        return self.generation.execute(sql, parameters)

    def digest(self, batch_events: int = DEFAULT_BATCH_EVENTS) -> dict[str, Any]:
        _require_batch_caps(batch_events)
        return _stream_generation_digests_conn(
            self.conn, self.generation_id, batch_events
        )

    def close(self) -> None:
        if not self.closed:
            if self.conn.in_transaction:
                self.conn.rollback()
            self.conn.close()
            self.closed = True

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()


def active_reader(
    database_path: Path | str,
    *,
    disposable_root: Path | str,
    timeout_seconds: float = 5.0,
) -> ActiveReader:
    path, _ = _safety_path(database_path, disposable_root)
    probe = _open(path)
    try:
        _validate_extended_schema(probe)
    finally:
        probe.close()
    return ActiveReader(path, timeout_seconds=timeout_seconds)


def cutover_shadow(
    database_path: Path | str,
    *,
    disposable_root: Path | str,
    generation_id: str = "g2",
    verifier_generation_id: str = "g3",
    max_tail_events: int = DEFAULT_FINAL_TAIL_EVENTS,
    max_tail_bytes: int = DEFAULT_FINAL_TAIL_BYTES,
    timeout_seconds: float = 5.0,
    fault: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Metadata-only CAS after verified-base plus atomic routed synchronization."""
    _require_batch_caps(max_tail_events, max_tail_bytes)
    path, safety = _safety_path(database_path, disposable_root)
    conn = _open(path, timeout_seconds=timeout_seconds)
    write_collector = _WriteTxnCollector("cutover_shadow_b")
    prevalidation_started_ns = time.perf_counter_ns()
    committed = False
    try:
        _require_wal(conn, "metadata cutover")
        _validate_extended_schema(conn)
        conn.execute("BEGIN")
        topology = _topology_snapshot(conn)
        if topology["kind"] != "old_active_sync_armed":
            raise CutoverNotReady("B cutover requires an armed routed-sync topology")
        try:
            proof_checkpoint = _validate_persistent_proofs(conn)
        except ShadowHarnessError as exc:
            raise CutoverNotReady(
                "verified-base or persistent sync proof is invalid"
            ) from exc
        conn.commit()
        prevalidation_seconds = (
            time.perf_counter_ns() - prevalidation_started_ns
        ) / 1_000_000_000
        transaction = _WriteTransaction(
            conn, write_collector, "b_metadata_only_cutover"
        )
        attempt_ns = transaction.attempt_ns
        lock_ns = transaction.lock_ns
        _require_wal(conn, "metadata cutover")
        _validate_extended_schema(conn)
        topology = _topology_snapshot(conn)
        if topology["kind"] != "old_active_sync_armed":
            raise CutoverNotReady("B cutover topology changed after proof scan")
        try:
            proof = _validate_persistent_proofs(
                conn,
                initial=proof_checkpoint,
                max_receipts=MAX_BATCH_EVENTS * 3 + 16,
            )
        except ShadowHarnessError as exc:
            raise CutoverNotReady(
                "verified-base or incremental sync proof is invalid"
            ) from exc
        _emit_fault(fault, "cutover_opened", {})
        control = conn.execute("SELECT * FROM a03b_control WHERE singleton=1").fetchone()
        if (
            str(control["active_generation_id"]) != "g1"
            or str(control["sync_generation_id"]) != generation_id
        ):
            raise CutoverNotReady(
                "cutover requires g1 active with the explicit g2 sync route armed"
            )
        shadow = _status_from_row(_status_row(conn, generation_id))
        verifier = _status_from_row(_status_row(conn, verifier_generation_id))
        active = _status_from_row(_status_row(conn, "g1"))
        if (
            str(_status_row(conn, generation_id)["role"]) != "shadow"
            or str(_status_row(conn, verifier_generation_id)["role"]) != "verifier"
            or active.role != "base"
        ):
            raise CutoverNotReady("cutover generation roles changed")
        if (
            active.state != "active"
            or shadow.state != "catching_up"
            or verifier.state != "catching_up"
        ):
            raise CutoverNotReady("cutover generation states are not sync-armed")
        session = _sync_session(conn)
        if (
            str(session["state"]) != "armed"
            or str(session["shadow_generation_id"]) != generation_id
            or str(session["verifier_generation_id"]) != verifier_generation_id
        ):
            raise CutoverNotReady("routed sync session is not armed")
        if not _verified_base_receipts_valid(conn, session):
            raise CutoverNotReady(
                "verified-base receipt bodies changed before B cutover"
            )
        if not (
            active.built_through_event_id
            == shadow.built_through_event_id
            == verifier.built_through_event_id
            == session["synchronized_through_event_id"]
            and active.built_event_count
            == shadow.built_event_count
            == verifier.built_event_count
            == int(session["synchronized_event_count"])
            and active.built_head_seal
            == shadow.built_head_seal
            == verifier.built_head_seal
            == session["synchronized_head_seal"]
        ):
            raise CutoverNotReady("routed generations do not share the sync watermark")
        if conn.execute("SELECT 1 FROM a03b_operation_lock LIMIT 1").fetchone():
            raise CutoverNotReady("generation operation is still in progress")
        last = conn.execute(
            "SELECT id,seal FROM event_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        head_id = None if last is None else int(last["id"])
        head_seal = None if last is None else last["seal"]
        if (
            head_id != active.built_through_event_id
            or head_seal != active.built_head_seal
        ):
            raise CutoverNotReady("ledger head is outside routed synchronization")
        base_id = session["base_event_id"]
        receipt_head = 0 if base_id is None else int(base_id)
        verification_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM a03b_verification WHERE generation_id IN (?,?) "
                "AND through_event_id=? AND event_count=? "
                "AND ledger_sha256=? AND projection_digest_set_sha256=?",
                (
                    generation_id,
                    verifier_generation_id,
                    receipt_head,
                    int(session["base_event_count"]),
                    session["base_ledger_sha256"],
                    session["base_projection_digest_set_sha256"],
                ),
            ).fetchone()[0]
        )
        if verification_count != 2:
            raise CutoverNotReady("verified-base receipts are incomplete")
        if (
            shadow.full_digest_verified_through_event_id != base_id
            or verifier.full_digest_verified_through_event_id != base_id
        ):
            raise CutoverNotReady("verified-base watermark changed during synchronization")
        _require_equal_sequence_boundary(
            conn,
            ("g1", generation_id, verifier_generation_id),
            expected_digest=str(session["synchronized_sequence_digest_sha256"]),
        )
        _emit_fault(
            fault,
            "cutover_head_bound",
            {
                "synchronized_through_event_id": head_id,
                "synchronized_event_count": active.built_event_count,
            },
        )
        revision = int(control["revision"])
        now = _utc_now()
        updated = conn.execute(
            "UPDATE a03b_control SET active_generation_id=?,sync_generation_id=NULL,"
            "revision=revision+1,cutover_head_event_id=?,updated_at=? "
            "WHERE singleton=1 AND active_generation_id='g1' "
            "AND sync_generation_id=? AND revision=?",
            (generation_id, head_id, now, generation_id, revision),
        ).rowcount
        if updated != 1:
            raise CutoverNotReady("active generation CAS failed")
        conn.execute(
            "UPDATE a03b_generation SET state='retired',retired_at=? WHERE generation_id='g1'",
            (now,),
        )
        conn.execute(
            "UPDATE a03b_generation SET state='active',activated_at=?,"
            "verified_through_event_id=?,projection_digest_set_sha256=? "
            "WHERE generation_id=?",
            (
                now,
                session["base_event_id"],
                session["base_projection_digest_set_sha256"],
                generation_id,
            ),
        )
        conn.execute(
            "UPDATE a03b_generation SET state='verified',verified_through_event_id=?,"
            "projection_digest_set_sha256=?,verified_at=? WHERE generation_id=?",
            (
                session["base_event_id"],
                session["base_projection_digest_set_sha256"],
                now,
                verifier_generation_id,
            ),
        )
        if conn.execute(
            "UPDATE a03b_sync_session SET state='cutover',cutover_at=? "
            "WHERE singleton=1 AND state='armed'",
            (now,),
        ).rowcount != 1:
            raise CutoverNotReady("sync session cutover CAS failed")
        _emit_fault(fault, "cutover_pointer_changed", {"revision": revision + 1})
        _emit_fault(fault, "cutover_pre_commit", {})
        precommit_seconds = (time.perf_counter_ns() - lock_ns) / 1_000_000_000
        if precommit_seconds > WRITER_BLOCK_BUDGET_SECONDS:
            transaction.rollback()
            write_transactions = write_collector.receipt()
            return {
                "schema": RECEIPT_SCHEMA,
                "operation": "cutover",
                "outcome": "not_ready_fence_budget",
                "committed": False,
                "selected_final_sync_mode": "b_routed_sync",
                "sync_route_used": True,
                "final_fence_seconds": precommit_seconds,
                "within_writer_block_budget": False,
                "write_transactions": write_transactions,
                "safety": safety,
            }
        transaction.commit()
        committed = True
        commit_ns = time.perf_counter_ns()
        duration = (commit_ns - lock_ns) / 1_000_000_000
        write_transactions = write_collector.receipt()
        try:
            _emit_fault(fault, "cutover_post_commit", {"duration_seconds": duration})
        except BaseException as exc:
            raise PostCommitFault("cutover callback failed after commit") from exc
        return {
            "schema": RECEIPT_SCHEMA,
            "operation": "cutover",
            "outcome": "complete_new",
            "committed": True,
            "old_generation_id": "g1",
            "active_generation_id": generation_id,
            "retired_generation_id": "g1",
            "fixed_head": head_id,
            "verified_base_event_id": base_id,
            "selected_final_sync_mode": "b_routed_sync",
            "sync_route_used": True,
            "decision_reason": "explicit B routed-sync experiment requested",
            "synchronized_event_count": active.built_event_count,
            "synchronized_tail_event_count": (
                active.built_event_count - int(session["base_event_count"])
            ),
            "unsynchronized_tail_event_count": 0,
            "max_tail_events": max_tail_events,
            "max_tail_bytes": max_tail_bytes,
            "lock_wait_seconds": (lock_ns - attempt_ns) / 1_000_000_000,
            "proof_prevalidation_seconds": prevalidation_seconds,
            "final_fence_seconds": duration,
            "final_sync_mechanism": (
                "B:routed-triple-write-plus-metadata-only-pointer-CAS"
            ),
            "persistent_receipt_chains_recomputed": True,
            "validated_receipt_count": proof["validated_receipt_count"],
            "incremental_receipt_count_in_fence": proof[
                "incremental_receipt_count"
            ],
            "metadata_only_pointer_change": True,
            "table_ddl_in_final_fence": False,
            "within_writer_block_budget": (
                duration <= WRITER_BLOCK_BUDGET_SECONDS
                and write_transactions["pass"] is True
            ),
            "write_transactions": write_transactions,
            "safety": safety,
        }
    except BaseException:
        if not committed and "transaction" in locals():
            transaction.rollback()
        raise
    finally:
        conn.close()


def append_routed(
    database_path: Path | str,
    event_type: str,
    payload: Mapping[str, Any],
    *,
    disposable_root: Path | str,
    timeout_seconds: float = 5.0,
) -> dict[str, Any]:
    """Atomically append to ledger and every generation required by routing metadata."""
    path, safety = _safety_path(database_path, disposable_root)
    conn = _open(path, timeout_seconds=timeout_seconds)
    write_collector = _WriteTxnCollector("append_routed")
    transaction = _WriteTransaction(conn, write_collector, "routed_writer")
    attempt_ns = transaction.attempt_ns
    committed = False
    try:
        lock_ns = transaction.lock_ns
        _require_wal(conn, "routed writer")
        _validate_extended_schema(conn)
        topology = _topology_snapshot(conn)
        control = topology["control"]
        active_id = str(control["active_generation_id"])
        sync_id = control["sync_generation_id"]
        target_ids: tuple[str, ...]
        phase = "routed_writer"
        if sync_id is None:
            target_ids = (active_id,)
        else:
            if active_id != "g1" or str(sync_id) != "g2":
                raise ShadowHarnessError(
                    "sync_generation_id must route exactly g1/g2/g3 before cutover"
                )
            session = _sync_session(conn)
            g2 = _status_from_row(_status_row(conn, "g2"))
            g3 = _status_from_row(_status_row(conn, "g3"))
            g1 = _status_from_row(_status_row(conn, "g1"))
            if (
                str(session["state"]) != "armed"
                or str(session["shadow_generation_id"]) != "g2"
                or str(session["verifier_generation_id"]) != "g3"
                or g1.state != "active"
                or g2.state != "catching_up"
                or g3.state != "catching_up"
                or not (
                    g1.built_through_event_id
                    == g2.built_through_event_id
                    == g3.built_through_event_id
                )
                or g1.built_event_count != g2.built_event_count
                or g1.built_event_count != g3.built_event_count
                or g1.built_head_seal != g2.built_head_seal
                or g1.built_head_seal != g3.built_head_seal
                or g1.built_through_event_id
                != session["synchronized_through_event_id"]
                or g1.built_event_count != int(session["synchronized_event_count"])
                or g1.built_head_seal != session["synchronized_head_seal"]
            ):
                raise ShadowHarnessError("armed routed-sync invariant is incomplete")
            target_ids = ("g1", "g2", "g3")
            phase = "routed_writer_sync"
        event_id = ledger.append(conn, event_type, dict(payload))
        row = conn.execute(
            "SELECT id,event_type,payload,created_at,prev_seal,seal FROM event_log WHERE id=?",
            (event_id,),
        ).fetchone()
        if row is None:
            raise ShadowHarnessError("routed writer lost its inserted event")
        _apply_rows(conn, target_ids, (row,))
        payload_bytes = len(str(row["payload"]).encode("utf-8"))
        for target_id in target_ids:
            _update_watermark(conn, target_id, (row,))
            _record_batch(conn, target_id, (row,), payload_bytes, phase)
        sync_chain = None
        if sync_id is not None:
            sync_chain = _advance_sync_proof(conn, (row,), phase=phase)
        transaction.commit()
        committed = True
        commit_ns = time.perf_counter_ns()
        write_transactions = write_collector.receipt()
        return {
            "schema": RECEIPT_SCHEMA,
            "operation": "routed_writer",
            "event_id": event_id,
            "active_generation_id": active_id,
            "sync_generation_id": sync_id,
            "routed_generation_count": len(target_ids),
            "sync_chain_sha256": sync_chain,
            "lock_wait_seconds": (lock_ns - attempt_ns) / 1_000_000_000,
            "transaction_seconds": (commit_ns - lock_ns) / 1_000_000_000,
            "end_to_end_seconds": (commit_ns - attempt_ns) / 1_000_000_000,
            "committed": True,
            "write_transactions": write_transactions,
            "within_writer_block_budget": write_transactions["pass"] is True,
            "payload_logged": False,
            "safety": safety,
        }
    except BaseException:
        if not committed:
            transaction.rollback()
        raise
    finally:
        conn.close()


def _verification_digest_body_valid(row: sqlite3.Row) -> bool:
    """Recompute both compact verification digests from their persisted bodies."""
    try:
        projections = json.loads(str(row["projection_digests_json"]))
        sequences = json.loads(str(row["sequences_json"]))
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(projections, dict) or set(projections) != set(PROJECTION_TABLES):
        return False
    if not all(
        isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
        for value in projections.values()
    ):
        return False
    if not isinstance(sequences, dict) or set(sequences) != set(SEQUENCE_TABLES):
        return False
    if not all(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0
        for value in sequences.values()
    ):
        return False
    return bool(
        _sha256_json(projections) == str(row["projection_digest_set_sha256"])
        and _sha256_json(sequences) == str(row["sequence_digest_sha256"])
    )


def _verified_base_receipts_valid(
    conn: sqlite3.Connection, session: sqlite3.Row
) -> bool:
    base_id = session["base_event_id"]
    receipt_head = 0 if base_id is None else int(base_id)
    rows = conn.execute(
        "SELECT generation_id,event_count,ledger_sha256,"
        "projection_digests_json,projection_digest_set_sha256,sequences_json,"
        "sequence_digest_sha256,second_replay_generation_id "
        "FROM a03b_verification WHERE generation_id IN ('g2','g3') "
        "AND through_event_id=? ORDER BY generation_id",
        (receipt_head,),
    ).fetchall()
    if len(rows) != 2 or [str(row["generation_id"]) for row in rows] != ["g2", "g3"]:
        return False
    left, right = rows
    return bool(
        _verification_digest_body_valid(left)
        and _verification_digest_body_valid(right)
        and int(left["event_count"]) == int(session["base_event_count"])
        and int(right["event_count"]) == int(session["base_event_count"])
        and str(left["ledger_sha256"]) == str(session["base_ledger_sha256"])
        and left["ledger_sha256"] == right["ledger_sha256"]
        and str(left["projection_digest_set_sha256"])
        == str(session["base_projection_digest_set_sha256"])
        and left["projection_digest_set_sha256"]
        == right["projection_digest_set_sha256"]
        and left["sequence_digest_sha256"] == right["sequence_digest_sha256"]
        and str(left["sequence_digest_sha256"])
        == str(session["base_sequence_digest_sha256"])
        and left["projection_digests_json"] == right["projection_digests_json"]
        and left["sequences_json"] == right["sequences_json"]
        and str(left["second_replay_generation_id"]) == "g3"
        and str(right["second_replay_generation_id"]) == "g2"
    )


def _generation_matches_sync_watermark(
    status: GenerationStatus, session: sqlite3.Row
) -> bool:
    return bool(
        status.built_through_event_id == session["synchronized_through_event_id"]
        and status.built_event_count == int(session["synchronized_event_count"])
        and status.built_head_seal == session["synchronized_head_seal"]
    )


def recover(
    database_path: Path | str,
    *,
    disposable_root: Path | str,
    timeout_seconds: float = 5.0,
) -> dict[str, Any]:
    """Bounded metadata recovery classification after process death/reopen."""
    started = time.perf_counter_ns()
    path, safety = _safety_path(database_path, disposable_root)
    conn = _open(path, timeout_seconds=timeout_seconds)
    write_collector = _WriteTxnCollector("recover")
    writer_ready = False
    reader_ready = False
    try:
        try:
            _validate_extended_schema(conn)
        except SchemaInventoryError:
            return {
                **asdict(
                    RecoveryReceipt(
                        classification="INVALID_INVENTORY",
                        active_generation_id="",
                        duration_seconds=(
                            time.perf_counter_ns() - started
                        )
                        / 1_000_000_000,
                        extended_schema_valid=False,
                        writer_ready=False,
                        reader_ready=False,
                    )
                ),
                "schema": RECEIPT_SCHEMA,
                "within_recovery_budget": False,
                "safety": safety,
            }
        try:
            _require_wal(conn, "recovery")
        except ShadowHarnessError:
            duration = (time.perf_counter_ns() - started) / 1_000_000_000
            return {
                **asdict(
                    RecoveryReceipt(
                        classification="INVALID_JOURNAL_MODE",
                        active_generation_id="",
                        duration_seconds=duration,
                        extended_schema_valid=True,
                        writer_ready=False,
                        reader_ready=False,
                    )
                ),
                "schema": RECEIPT_SCHEMA,
                "within_recovery_budget": False,
                "safety": safety,
            }
        try:
            conn.execute("BEGIN")
            topology = _topology_snapshot(conn, verify_event_count=True)
            proof = None
            if topology["session"] is not None:
                proof = _validate_persistent_proofs(conn)
            conn.commit()
        except ShadowHarnessError as exc:
            if conn.in_transaction:
                conn.rollback()
            message = str(exc)
            classification = (
                "INVALID_UNROUTED_TAIL"
                if message == "INVALID_UNROUTED_TAIL"
                else "INVALID_PERSISTENT_PROOF"
                if "receipt" in message.lower() or "sync" in message.lower()
                else message
                if message.startswith("INVALID_")
                else "INVALID_TOPOLOGY"
            )
            duration = (time.perf_counter_ns() - started) / 1_000_000_000
            return {
                **asdict(
                    RecoveryReceipt(
                        classification=classification,
                        active_generation_id="",
                        duration_seconds=duration,
                        extended_schema_valid=True,
                        writer_ready=False,
                        reader_ready=False,
                    )
                ),
                "schema": RECEIPT_SCHEMA,
                "within_recovery_budget": False,
                "persistent_receipt_chains_recomputed": False,
                "safety": safety,
            }
        control = conn.execute("SELECT * FROM a03b_control WHERE singleton=1").fetchone()
        active_rows = conn.execute(
            "SELECT generation_id FROM a03b_generation WHERE state='active' ORDER BY generation_id"
        ).fetchall()
        lease_rows = conn.execute(
            "SELECT * FROM a03b_operation_lock ORDER BY generation_id"
        ).fetchall()
        live_leases = [row for row in lease_rows if _operation_lease_is_live(row)]
        stale_leases = [row for row in lease_rows if not _operation_lease_is_live(row)]
        session = conn.execute(
            "SELECT * FROM a03b_sync_session WHERE singleton=1"
        ).fetchone()
        if len(active_rows) != 1:
            classification = "INVALID_NO_ACTIVE" if not active_rows else "INVALID_MULTIPLE_ACTIVE"
        else:
            active_id = str(active_rows[0][0])
            if active_id != str(control["active_generation_id"]):
                classification = "INVALID_POINTER_STATE"
            else:
                head = _capture_head(conn)
                invalid_watermark = conn.execute(
                    "SELECT 1 FROM a03b_generation WHERE "
                    "COALESCE(built_through_event_id,0)>? OR "
                    "COALESCE(verified_through_event_id,0)>COALESCE(built_through_event_id,0) "
                    "LIMIT 1",
                    (head.head_id or 0,),
                ).fetchone()
                if invalid_watermark:
                    classification = "INVALID_WATERMARK"
                else:
                    g1 = _status_from_row(_status_row(conn, "g1"))
                    g2 = _status_from_row(_status_row(conn, "g2"))
                    g3 = _status_from_row(_status_row(conn, "g3"))
                    active = g1 if active_id == "g1" else g2
                    expected_count = int(
                        conn.execute(
                            "SELECT COUNT(*) FROM event_log WHERE id<=?",
                            (active.built_through_event_id or 0,),
                        ).fetchone()[0]
                    )
                    actual_seal = None
                    if active.built_through_event_id is not None:
                        found = conn.execute(
                            "SELECT seal FROM event_log WHERE id=?",
                            (active.built_through_event_id,),
                        ).fetchone()
                        actual_seal = None if found is None else found[0]
                    if (
                        active.built_event_count != expected_count
                        or active.built_head_seal != actual_seal
                    ):
                        classification = "INVALID_WATERMARK"
                    elif active_id == "g1" and g1.state == "active":
                        if session is None:
                            if control["sync_generation_id"] is None:
                                classification = "OLD_ACTIVE_SHADOW_RESUMABLE"
                            else:
                                classification = "AMBIGUOUS_SYNC_METADATA"
                        elif not _verified_base_receipts_valid(conn, session):
                            classification = "INVALID_VERIFIED_BASE"
                        elif (
                            str(session["state"]) == "preparing"
                            and control["sync_generation_id"] is None
                            and g2.state == "catching_up"
                            and g3.state == "catching_up"
                            and _generation_matches_sync_watermark(g2, session)
                            and _generation_matches_sync_watermark(g3, session)
                            and (g2.built_through_event_id or 0)
                            <= (g1.built_through_event_id or 0)
                            and g2.built_event_count <= g1.built_event_count
                        ):
                            classification = "OLD_ACTIVE_SYNC_PREPARING"
                        elif (
                            str(session["state"]) == "armed"
                            and str(control["sync_generation_id"]) == "g2"
                            and g2.state == "catching_up"
                            and g3.state == "catching_up"
                            and _generation_matches_sync_watermark(g1, session)
                            and _generation_matches_sync_watermark(g2, session)
                            and _generation_matches_sync_watermark(g3, session)
                        ):
                            classification = "OLD_ACTIVE_SYNC_ARMED"
                        else:
                            classification = "AMBIGUOUS_SYNC_METADATA"
                    else:
                        cutover_head = control["cutover_head_event_id"]
                        if (
                            active_id == "g2"
                            and g2.state == "active"
                            and g1.state == "retired"
                            and g3.state == "verified"
                            and g2.verified_through_event_id
                            == session["base_event_id"]
                            and g3.built_through_event_id == cutover_head
                            and g3.verified_through_event_id
                            == session["base_event_id"]
                            and session is not None
                            and str(session["state"]) == "cutover"
                            and control["sync_generation_id"] is None
                            and session["synchronized_through_event_id"] == cutover_head
                            and _generation_matches_sync_watermark(g1, session)
                            and _generation_matches_sync_watermark(g3, session)
                            and g2.built_event_count
                            >= int(session["synchronized_event_count"])
                            and g2.full_digest_verified_through_event_id
                            == session["base_event_id"]
                            and g3.full_digest_verified_through_event_id
                            == session["base_event_id"]
                            and g2.projection_digest_set_sha256
                            == session["base_projection_digest_set_sha256"]
                            and g3.projection_digest_set_sha256
                            == session["base_projection_digest_set_sha256"]
                            and _verified_base_receipts_valid(conn, session)
                            and not lease_rows
                        ):
                            classification = "NEW_ACTIVE_OLD_RETIRED"
                        else:
                            classification = "AMBIGUOUS_CUTOVER"
        valid = classification in {
            "OLD_ACTIVE_SHADOW_RESUMABLE",
            "OLD_ACTIVE_SYNC_PREPARING",
            "OLD_ACTIVE_SYNC_ARMED",
            "NEW_ACTIVE_OLD_RETIRED",
        }
        stale_leases_cleared = 0
        if valid:
            if stale_leases:
                with _measured_write(
                    conn, write_collector, "recovery_stale_lease_cleanup"
                ):
                    for lease in stale_leases:
                        stale_leases_cleared += conn.execute(
                            "DELETE FROM a03b_operation_lock WHERE generation_id=? "
                            "AND owner_token=? AND owner_pid=? AND owner_process_started=?",
                            (
                                lease["generation_id"],
                                lease["owner_token"],
                                lease["owner_pid"],
                                lease["owner_process_started"],
                            ),
                        ).rowcount
            conn.execute("BEGIN")
            conn.execute(
                "SELECT active_generation_id FROM a03b_control WHERE singleton=1"
            ).fetchone()
            conn.rollback()
            reader_ready = True
            if not live_leases:
                readiness_transaction = _WriteTransaction(
                    conn, write_collector, "recovery_writer_readiness_probe"
                )
                readiness_transaction.rollback()
                writer_ready = True
        duration = (time.perf_counter_ns() - started) / 1_000_000_000
        active = str(control["active_generation_id"])
        write_transactions = write_collector.receipt()
        return {
            **asdict(
                RecoveryReceipt(
                    classification=classification,
                    active_generation_id=active,
                    duration_seconds=duration,
                    extended_schema_valid=True,
                    writer_ready=writer_ready,
                    reader_ready=reader_ready,
                )
            ),
            "schema": RECEIPT_SCHEMA,
            "within_recovery_budget": (
                valid
                and not live_leases
                and duration <= RECOVERY_BUDGET_SECONDS
                and write_transactions["pass"] is True
            ),
            "write_transactions": write_transactions,
            "stale_operation_leases_cleared": stale_leases_cleared,
            "live_operation_lease_count": len(live_leases),
            "retryable_now": valid and not live_leases,
            "persistent_receipt_chains_recomputed": proof is not None,
            "validated_receipt_count": (
                0 if proof is None else proof["validated_receipt_count"]
            ),
            "safety": safety,
        }
    finally:
        conn.close()


def _quantile_nearest_rank(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, (int(percentile * len(ordered) + 0.999999)))
    return float(ordered[min(rank, len(ordered)) - 1])


def writer_latency_summary(
    samples: Sequence[Mapping[str, Any]], *, pending_age_seconds: float = 0.0
) -> dict[str, Any]:
    if len(samples) > MAX_WRITER_TELEMETRY_SAMPLES:
        raise ShadowHarnessError("writer telemetry input exceeds the hard cap")
    latencies = [
        float(sample["end_to_end_seconds"])
        for sample in samples
        if sample.get("end_to_end_seconds") is not None
    ]
    committed_latencies = [
        float(sample["end_to_end_seconds"])
        for sample in samples
        if sample.get("committed") and sample.get("end_to_end_seconds") is not None
    ]
    queue_delays = [float(sample.get("queue_delay_seconds", 0.0)) for sample in samples]
    commit_times = sorted(
        float(sample["commit_offset_seconds"])
        for sample in samples
        if sample.get("committed") and sample.get("commit_offset_seconds") is not None
    )
    intercommit = [right - left for left, right in zip(commit_times, commit_times[1:])]
    timeouts = sum(1 for sample in samples if sample.get("outcome") == "timeout")
    errors = sum(
        1
        for sample in samples
        if not sample.get("committed") and sample.get("outcome") != "timeout"
    )
    maximum = max(latencies, default=None)
    max_queue = max(queue_delays, default=0.0)
    max_intercommit = max(intercommit, default=0.0)
    starvation = bool(
        timeouts
        or errors
        or pending_age_seconds > WRITER_BLOCK_BUDGET_SECONDS
        or max_queue > WRITER_BLOCK_BUDGET_SECONDS
        or max_intercommit > WRITER_BLOCK_BUDGET_SECONDS
        or (maximum is not None and maximum > WRITER_BLOCK_BUDGET_SECONDS)
    )
    return {
        "sample_count": len(samples),
        "committed_count": len(committed_latencies),
        "p50_seconds": _quantile_nearest_rank(latencies, 0.50),
        "p95_seconds": _quantile_nearest_rank(latencies, 0.95),
        "p99_seconds": _quantile_nearest_rank(latencies, 0.99),
        "max_seconds": maximum,
        "timeouts": timeouts,
        "errors": errors,
        "max_pending_age_seconds": pending_age_seconds,
        "max_queue_delay_seconds": max_queue,
        "max_intercommit_gap_seconds": max_intercommit,
        "starvation": starvation,
        "within_max_block_budget": maximum is None or maximum <= WRITER_BLOCK_BUDGET_SECONDS,
    }


def run_concurrency_probe(
    database_path: Path | str,
    *,
    disposable_root: Path | str,
    writer_interval_seconds: float = 0.005,
    batch_events: int = DEFAULT_BATCH_EVENTS,
    batch_bytes: int = DEFAULT_BATCH_BYTES,
    short_reader_interval_seconds: float = 0.003,
) -> dict[str, Any]:
    """Run writer, long/short readers, build, catch-up, verify and cutover together."""
    _require_batch_caps(batch_events, batch_bytes)
    if writer_interval_seconds <= 0 or short_reader_interval_seconds <= 0:
        raise ShadowHarnessError("concurrency intervals must be positive")
    path, safety = _safety_path(database_path, disposable_root)
    probe_started = time.perf_counter()
    stop = threading.Event()
    writer_samples: deque[dict[str, Any]] = deque(
        maxlen=MAX_WRITER_TELEMETRY_SAMPLES
    )
    reader_generations: deque[str] = deque(
        maxlen=MAX_READER_TELEMETRY_SAMPLES
    )
    failures: deque[str] = deque(maxlen=MAX_FAILURE_TELEMETRY_SAMPLES)
    writer_sample_total = 0
    writer_committed_total = 0
    writer_timeout_total = 0
    writer_error_total = 0
    reader_sample_total = 0
    failure_total = 0
    lock = threading.Lock()
    writer_handoff_condition = threading.Condition()
    writer_commit_epoch = 0
    writer_handoff_requested = 0
    writer_handoff_completed = 0
    writer_handoff_timeouts = 0
    writer_handoff_total_seconds = 0.0
    writer_handoff_max_seconds = 0.0
    writer_handoff_commit_delta_total = 0
    writer_handoff_commit_delta_min: int | None = None
    writer_handoff_commit_delta_max = 0

    def cooperative_writer_handoff(conn: sqlite3.Connection) -> float:
        nonlocal writer_handoff_requested, writer_handoff_completed
        nonlocal writer_handoff_timeouts, writer_handoff_total_seconds
        nonlocal writer_handoff_max_seconds, writer_handoff_commit_delta_total
        nonlocal writer_handoff_commit_delta_min, writer_handoff_commit_delta_max
        if conn.in_transaction:
            raise ShadowHarnessError("writer admission slot must be outside a transaction")
        started = time.perf_counter()
        with writer_handoff_condition:
            baseline = writer_commit_epoch
            writer_handoff_requested += 1
            observed = writer_handoff_condition.wait_for(
                lambda: writer_commit_epoch > baseline or stop.is_set(),
                timeout=INTER_BATCH_WRITER_HANDOFF_TIMEOUT_SECONDS,
            )
            commit_delta = writer_commit_epoch - baseline
        elapsed = time.perf_counter() - started
        writer_handoff_total_seconds += elapsed
        writer_handoff_max_seconds = max(writer_handoff_max_seconds, elapsed)
        if conn.in_transaction:
            raise ShadowHarnessError("writer admission slot opened a transaction")
        if not observed or commit_delta < 1:
            writer_handoff_timeouts += 1
            raise ShadowHarnessError(
                "cooperative writer admission slot timed out before a real commit"
            )
        writer_handoff_completed += 1
        writer_handoff_commit_delta_total += commit_delta
        writer_handoff_commit_delta_min = (
            commit_delta
            if writer_handoff_commit_delta_min is None
            else min(writer_handoff_commit_delta_min, commit_delta)
        )
        writer_handoff_commit_delta_max = max(
            writer_handoff_commit_delta_max, commit_delta
        )
        return elapsed

    def writer_loop() -> None:
        nonlocal writer_committed_total, writer_error_total
        nonlocal writer_sample_total, writer_timeout_total
        nonlocal writer_commit_epoch
        sequence = 0
        origin = time.perf_counter()
        next_due = origin
        while not stop.is_set():
            delay = next_due - time.perf_counter()
            if delay > 0 and stop.wait(delay):
                break
            scheduled = next_due
            attempt = time.perf_counter()
            sequence += 1
            try:
                sample = append_routed(
                    path,
                    "assertion_recorded",
                    {
                        "claim_key": f"a03b.concurrent.{sequence % 97}",
                        "claim_value": sequence,
                        "source": "experiment:a0_3b",
                        "derivation": "experiment:a0_3b:concurrency:v1",
                    },
                    disposable_root=disposable_root,
                    timeout_seconds=2.0,
                )
            except sqlite3.OperationalError as exc:
                returned = time.perf_counter()
                sample = {
                    "committed": False,
                    "outcome": "timeout" if "locked" in str(exc).lower() else "error",
                    "end_to_end_seconds": returned - attempt,
                }
            except BaseException as exc:  # retained as aggregate type only
                returned = time.perf_counter()
                sample = {
                    "committed": False,
                    "outcome": type(exc).__name__,
                    "end_to_end_seconds": returned - attempt,
                }
            else:
                returned = time.perf_counter()
                sample["outcome"] = "committed"
            sample["queue_delay_seconds"] = max(0.0, attempt - scheduled)
            sample["attempt_offset_seconds"] = attempt - origin
            sample["commit_offset_seconds"] = (
                returned - origin if sample.get("committed") else None
            )
            next_due = returned + writer_interval_seconds
            with lock:
                writer_sample_total += 1
                if sample.get("committed"):
                    writer_committed_total += 1
                elif sample.get("outcome") == "timeout":
                    writer_timeout_total += 1
                else:
                    writer_error_total += 1
                writer_samples.append(sample)
            if sample.get("committed"):
                with writer_handoff_condition:
                    writer_commit_epoch += 1
                    writer_handoff_condition.notify_all()

    def short_reader_loop() -> None:
        nonlocal failure_total, reader_sample_total
        while not stop.is_set():
            try:
                with active_reader(path, disposable_root=disposable_root) as reader:
                    reader.execute("SELECT COUNT(*) FROM value_projection").fetchone()
                    generation = reader.generation_id
                with lock:
                    reader_sample_total += 1
                    reader_generations.append(generation)
            except BaseException as exc:
                with lock:
                    failure_total += 1
                    failures.append(type(exc).__name__)
            stop.wait(short_reader_interval_seconds)

    long_reader = active_reader(path, disposable_root=disposable_root)
    long_generation_before = long_reader.generation_id
    writer_thread = threading.Thread(target=writer_loop, daemon=True)
    reader_thread = threading.Thread(target=short_reader_loop, daemon=True)
    writer_thread.start()
    reader_thread.start()
    with _ResourceSampler(path) as sampler:
        try:
            build = build_shadow(
                path,
                disposable_root=disposable_root,
                batch_events=batch_events,
                batch_bytes=batch_bytes,
                _writer_handoff=cooperative_writer_handoff,
            )
            catchup = catch_up_shadow(
                path,
                disposable_root=disposable_root,
                batch_events=batch_events,
                batch_bytes=batch_bytes,
                close_gap_events=64,
                _writer_handoff=cooperative_writer_handoff,
            )
            final_sync_attempts = 0
            while True:
                final_sync_attempts += 1
                verify = verify_shadow(
                    path,
                    disposable_root=disposable_root,
                    batch_events=batch_events,
                    batch_bytes=batch_bytes,
                    atomic_cutover=True,
                    _writer_handoff=cooperative_writer_handoff,
                )
                cutover = verify["cutover"]
                if cutover["committed"]:
                    break
                if final_sync_attempts >= 20:
                    raise ShadowHarnessError(
                        "A bounded final fence did not pass within 20 attempts"
                    )
            long_reader.execute("SELECT COUNT(*) FROM value_projection").fetchone()
            long_generation_after = long_reader.generation_id
            with active_reader(path, disposable_root=disposable_root) as fresh_reader:
                fresh_generation = fresh_reader.generation_id
            post_cutover_deadline = time.monotonic() + max(
                0.1, writer_interval_seconds * 10
            )
            while time.monotonic() < post_cutover_deadline:
                with lock:
                    if any(
                        item.get("committed")
                        and item.get("active_generation_id") == "g2"
                        for item in writer_samples
                    ):
                        break
                time.sleep(min(0.005, writer_interval_seconds))
        finally:
            stop.set()
            with writer_handoff_condition:
                writer_handoff_condition.notify_all()
            writer_thread.join(timeout=5.0)
            reader_thread.join(timeout=5.0)
            long_reader.close()
    observation_seconds = time.perf_counter() - probe_started
    pending_age = max(
        (float(item.get("queue_delay_seconds", 0.0)) for item in writer_samples),
        default=0.0,
    )
    if writer_thread.is_alive():
        pending_age = max(pending_age, WRITER_BLOCK_BUDGET_SECONDS + 1.0)
    summary = writer_latency_summary(writer_samples, pending_age_seconds=pending_age)
    summary["total_sample_count"] = writer_sample_total
    summary["samples_truncated"] = writer_sample_total > len(writer_samples)
    summary["dropped_sample_count"] = max(
        0, writer_sample_total - len(writer_samples)
    )
    summary["committed_count"] = writer_committed_total
    summary["timeouts"] = writer_timeout_total
    summary["errors"] = writer_error_total
    summary["observation_seconds"] = observation_seconds
    summary["observed_attempt_rate_per_second"] = (
        writer_sample_total / observation_seconds if observation_seconds > 0 else None
    )
    summary["committed_arrival_rate_per_second"] = (
        writer_committed_total / observation_seconds
        if observation_seconds > 0
        else None
    )
    telemetry_complete = writer_sample_total == len(writer_samples)
    summary["starvation"] = bool(
        summary["starvation"]
        or not telemetry_complete
        or writer_timeout_total
        or writer_error_total
        or writer_thread.is_alive()
    )
    summary["within_max_block_budget"] = bool(
        summary["within_max_block_budget"] and telemetry_complete
    )
    phase_samples = {
        "g1_only": [
            item
            for item in writer_samples
            if item.get("committed")
            and item.get("active_generation_id") == "g1"
            and item.get("routed_generation_count") == 1
        ],
        "sync_triple": [
            item
            for item in writer_samples
            if item.get("committed") and item.get("routed_generation_count") == 3
        ],
        "g2_only": [
            item
            for item in writer_samples
            if item.get("committed")
            and item.get("active_generation_id") == "g2"
            and item.get("routed_generation_count") == 1
        ],
    }
    phase_latency = {
        phase: writer_latency_summary(items) for phase, items in phase_samples.items()
    }
    baseline_p50 = phase_latency["g1_only"]["p50_seconds"]
    sync_p50 = phase_latency["sync_triple"]["p50_seconds"]
    phase_overhead = {
        "sync_minus_g1_p50_seconds": (
            None if baseline_p50 is None or sync_p50 is None else sync_p50 - baseline_p50
        ),
        "sync_over_g1_p50_ratio": (
            None
            if baseline_p50 in {None, 0.0} or sync_p50 is None
            else sync_p50 / baseline_p50
        ),
    }
    reader_thread_alive = reader_thread.is_alive()
    writer_thread_alive = writer_thread.is_alive()
    generations_seen = sorted(set(reader_generations))
    reader_evidence_complete = (
        reader_sample_total == len(reader_generations)
        and failure_total == len(failures)
    )
    reader_coherent = (
        reader_sample_total > 0
        and reader_evidence_complete
        and not failures
        and failure_total == 0
        and not reader_thread_alive
        and set(generations_seen).issubset({"g1", "g2"})
        and long_generation_before == long_generation_after == "g1"
        and fresh_generation == "g2"
    )
    expected_handoffs = sum(
        int(receipt["count"])
        for receipt in (
            build["post_batch_writer_yield"],
            catchup["post_batch_writer_yield"],
            verify["post_batch_writer_yield"],
        )
    )
    writer_handoff = {
        "strategy": "cooperative-writer-admission-slot",
        "load_model": "closed_loop_single_writer",
        "think_time_seconds": writer_interval_seconds,
        "timeout_seconds_per_slot": INTER_BATCH_WRITER_HANDOFF_TIMEOUT_SECONDS,
        "expected_from_committed_batches": expected_handoffs,
        "requested": writer_handoff_requested,
        "completed": writer_handoff_completed,
        "timeouts": writer_handoff_timeouts,
        "total_wait_seconds": writer_handoff_total_seconds,
        "max_wait_seconds": writer_handoff_max_seconds,
        "commit_delta_total": writer_handoff_commit_delta_total,
        "commit_delta_min": writer_handoff_commit_delta_min,
        "commit_delta_max": writer_handoff_commit_delta_max,
        "exactly_one_commit_per_slot": bool(
            writer_handoff_requested == 0
            or (
                writer_handoff_commit_delta_min == 1
                and writer_handoff_commit_delta_max == 1
            )
        ),
        "outside_transactions": True,
    }
    writer_handoff["pass"] = bool(
        writer_handoff_requested == expected_handoffs
        and writer_handoff_completed == writer_handoff_requested
        and writer_handoff_timeouts == 0
        and writer_handoff_commit_delta_total == writer_handoff_completed
        and writer_handoff["exactly_one_commit_per_slot"] is True
        and writer_handoff_max_seconds
        <= INTER_BATCH_WRITER_HANDOFF_TIMEOUT_SECONDS
    )
    return {
        "schema": RECEIPT_SCHEMA,
        "operation": "concurrency_probe",
        "build": build,
        "catch_up": catchup,
        "verify": {
            "through_event_id": verify["through_event_id"],
            "all_twelve_match": verify["all_twelve_match"],
            "all_nine_sequences_match": verify["all_nine_sequences_match"],
            "selected_final_sync_mode": verify["selected_final_sync_mode"],
            "sync_route_used": verify["sync_route_used"],
            "second_replay_batches": verify["second_replay_batches"],
            "post_batch_writer_yield": verify["post_batch_writer_yield"],
            "sync_admission": verify["sync_admission"],
            "write_transaction_max_seconds": verify[
                "write_transaction_max_seconds"
            ],
        },
        "cutover": cutover,
        "final_sync_attempts": final_sync_attempts,
        "writer_latency": summary,
        "writer_latency_by_phase": phase_latency,
        "writer_phase_overhead": phase_overhead,
        "writer_handoff": writer_handoff,
        "writer_evidence_complete": telemetry_complete,
        "reader": {
            "short_transaction_count": reader_sample_total,
            "retained_sample_count": len(reader_generations),
            "samples_truncated": reader_sample_total > len(reader_generations),
            "evidence_complete": reader_evidence_complete,
            "generations_seen": generations_seen,
            "failures": list(failures),
            "failure_count": failure_total,
            "failure_samples_truncated": failure_total > len(failures),
            "reader_thread_alive_after_join": reader_thread_alive,
            "writer_thread_alive_after_join": writer_thread_alive,
            "long_reader_before": long_generation_before,
            "long_reader_after": long_generation_after,
            "fresh_reader_after": fresh_generation,
            "coherent_old_or_new_only": reader_coherent,
        },
        "peak_rss_bytes": sampler.peak_rss_bytes,
        "storage_highwater_bytes": dict(sampler.highwater),
        "concurrency_gate_pass": (
            telemetry_complete
            and writer_committed_total > 0
            and writer_timeout_total == 0
            and writer_error_total == 0
            and not writer_thread_alive
            and summary["within_max_block_budget"] is True
            and summary["starvation"] is False
            and writer_handoff["pass"] is True
            and reader_coherent
            and bool(cutover["within_writer_block_budget"])
            and bool(verify["write_transaction_max_seconds"]["pass"])
        ),
        "safety": safety,
        "payloads_logged": False,
    }


def _ledger_receipt(conn: sqlite3.Connection, batch_events: int) -> dict[str, Any]:
    conn.execute("BEGIN")
    fence = a03a.capture_fence(conn)
    binding = a03a.stream_ledger_binding(conn, fence, batch_events)
    seal_issues = a03a.verify_chain_bounded(conn, fence, batch_events)
    conn.commit()
    if seal_issues:
        raise ShadowHarnessError("ledger seal invariant failed: " + "; ".join(seal_issues[:5]))
    return {"fence": asdict(fence), "binding": binding, "seal_issues": []}


def run_shadow_prototype(
    database_path: Path | str,
    *,
    disposable_root: Path | str,
    batch_events: int = DEFAULT_BATCH_EVENTS,
    batch_bytes: int = DEFAULT_BATCH_BYTES,
    require_active_match: bool = True,
) -> dict[str, Any]:
    """Run the complete writer-free A0.3b proof on one disposable database."""
    _require_batch_caps(batch_events, batch_bytes)
    path, safety = _safety_path(database_path, disposable_root)
    with _ResourceSampler(path) as sampler:
        initialized = initialize_shadow(path, disposable_root=disposable_root)
        conn = _open(path)
        try:
            ledger_before = _ledger_receipt(conn, batch_events)
        finally:
            conn.close()
        build = build_shadow(
            path,
            disposable_root=disposable_root,
            batch_events=batch_events,
            batch_bytes=batch_bytes,
        )
        catchup = catch_up_shadow(
            path,
            disposable_root=disposable_root,
            batch_events=batch_events,
            batch_bytes=batch_bytes,
        )
        verify = verify_shadow(
            path,
            disposable_root=disposable_root,
            batch_events=batch_events,
            batch_bytes=batch_bytes,
            require_active_match=require_active_match,
            atomic_cutover=True,
        )
        cutover = verify["cutover"]
        recovery = recover(path, disposable_root=disposable_root)
        conn = _open(path)
        try:
            ledger_after = _ledger_receipt(conn, batch_events)
            active = str(
                conn.execute(
                    "SELECT active_generation_id FROM a03b_control WHERE singleton=1"
                ).fetchone()[0]
            )
            active_digest = _stream_generation_digests_conn(
                conn, active, batch_events
            )
        finally:
            conn.close()
    ledger_unchanged = ledger_before == ledger_after
    write_transactions = _merge_write_transaction_receipts(
        "run_shadow_prototype",
        (
            initialized["write_transactions"],
            build["write_transactions"],
            catchup["write_transactions"],
            verify["write_transactions"],
            recovery["write_transactions"],
        ),
    )
    budgets = {
        "peak_rss": {
            "limit_bytes": RSS_BUDGET_BYTES,
            "measured_bytes": sampler.peak_rss_bytes,
            "pass": sampler.peak_rss_bytes <= RSS_BUDGET_BYTES,
        },
        "wal_highwater": {
            "limit_bytes": WAL_BUDGET_BYTES,
            "measured_bytes": sampler.highwater["wal"],
            "pass": sampler.highwater["wal"] <= WAL_BUDGET_BYTES,
        },
        "initialization_write_transactions": {
            "limit_seconds": WRITER_BLOCK_BUDGET_SECONDS,
            "measured_seconds": initialized["write_transactions"][
                "overall_max_transaction_seconds"
            ],
            "pass": initialized["write_transactions"]["pass"],
        },
        "build_write_transactions": {
            "limit_seconds": WRITER_BLOCK_BUDGET_SECONDS,
            "measured_seconds": build["write_transactions"][
                "overall_max_transaction_seconds"
            ],
            "pass": (
                build["within_writer_block_budget"] is True
                and build["write_transactions"]["pass"] is True
            ),
        },
        "catch_up_write_transactions": {
            "limit_seconds": WRITER_BLOCK_BUDGET_SECONDS,
            "measured_seconds": catchup["write_transactions"][
                "overall_max_transaction_seconds"
            ],
            "pass": (
                catchup["within_writer_block_budget"] is True
                and catchup["write_transactions"]["pass"] is True
            ),
        },
        "verification_sync_and_cutover_write_transactions": {
            "limit_seconds": WRITER_BLOCK_BUDGET_SECONDS,
            "measured_seconds": verify["write_transactions"][
                "overall_max_transaction_seconds"
            ],
            "pass": (
                verify["write_transactions"]["pass"] is True
                and verify["write_transaction_max_seconds"]["pass"] is True
                and verify["sync_admission"]["within_writer_block_budget"] is True
                and cutover["within_writer_block_budget"] is True
            ),
        },
        "rebuild": {
            "limit_seconds": REBUILD_BUDGET_SECONDS,
            "measured_seconds": build["duration_seconds"],
            "pass": (
                build["duration_seconds"] <= REBUILD_BUDGET_SECONDS
                and build["within_writer_block_budget"] is True
                and build["write_transactions"]["pass"] is True
            ),
        },
        "final_fence": {
            "limit_seconds": WRITER_BLOCK_BUDGET_SECONDS,
            "measured_seconds": cutover["final_fence_seconds"],
            "pass": (
                cutover["final_fence_seconds"] <= WRITER_BLOCK_BUDGET_SECONDS
                and cutover["within_writer_block_budget"] is True
                and verify["sync_admission"]["within_writer_block_budget"] is True
            ),
        },
        "all_experimental_write_transactions": {
            "limit_seconds": WRITER_BLOCK_BUDGET_SECONDS,
            "measured_seconds": write_transactions[
                "overall_max_transaction_seconds"
            ],
            "evidence_complete": write_transactions["evidence_complete"],
            "transaction_count": write_transactions["transaction_count"],
            "pass": write_transactions["pass"],
        },
        "recovery": {
            "limit_seconds": RECOVERY_BUDGET_SECONDS,
            "measured_seconds": recovery["duration_seconds"],
            "pass": (
                recovery["duration_seconds"] <= RECOVERY_BUDGET_SECONDS
                and recovery["classification"] == "NEW_ACTIVE_OLD_RETIRED"
                and recovery["reader_ready"] is True
                and recovery["writer_ready"] is True
                and recovery["persistent_receipt_chains_recomputed"] is True
                and recovery["within_recovery_budget"] is True
                and recovery["write_transactions"]["pass"] is True
            ),
        },
    }
    return {
        "schema": RECEIPT_SCHEMA,
        "runtime": {
            "platform": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
            "implementation": sys.implementation.name,
            "sqlite_wal_reset_gate": sqlite_wal_reset_gate(sqlite3.sqlite_version),
        },
        "topology": "option-c-same-file-generation-pointer",
        "final_sync": cutover["final_sync_mechanism"],
        "selected_final_sync_mode": verify["selected_final_sync_mode"],
        "sync_route_used": verify["sync_route_used"],
        "dual_write_used": verify["sync_route_used"],
        "initialized": initialized,
        "build": build,
        "catch_up": catchup,
        "verify": verify,
        "cutover": cutover,
        "recovery": recovery,
        "ledger_before": ledger_before,
        "ledger_after": ledger_after,
        "ledger_unchanged": ledger_unchanged,
        "active_generation_id": active,
        "active_projection_digests": active_digest,
        "peak_rss_bytes": sampler.peak_rss_bytes,
        "storage_highwater_bytes": dict(sampler.highwater),
        "write_transactions": write_transactions,
        "budgets": budgets,
        "budgets_pass": ledger_unchanged and all(item["pass"] for item in budgets.values()),
        "product_runtime_integrated": False,
        "source_original_opened": "not_attested_by_harness",
        "product_path_activated": False,
        "unselected_b_overhead": {
            "selected": False,
            "measured_in_this_run": False,
            "overhead_claimed": False,
        },
        "payloads_logged": False,
        "absolute_paths_logged": False,
        "safety": safety,
    }
