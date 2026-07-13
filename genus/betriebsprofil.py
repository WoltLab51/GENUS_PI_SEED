"""Private, read-only 24/48/72-hour operating profile for GENUS.

The profile is evidence about the ledger, never another ledger producer.  A run is
started deliberately with a baseline and then captures three disjoint head-id
intervals.  Payloads are inspected only inside SQLite; persisted results contain
allowlisted aggregates and no free text, paths, subjects, objects, or raw sources.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import math
import os
import re
import stat
import tempfile
import time
from pathlib import Path
from typing import Iterator

from genus import db, integrity, thermometer


SCHEMA_VERSION = "genus-betriebsprofil-v1"
SCHEDULE = (("baseline", 0), ("h24", 24), ("h48", 48), ("h72", 72))
SNAPSHOT_FILES = {label: f"{label}.json" for label, _ in SCHEDULE}
MANIFEST_FILE = "manifest.json"
LOCK_FILE = "run.lock"
MAX_MANIFEST_BYTES = 256 * 1024
MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
MAX_CAPTURE_LATENESS_SECONDS = 2 * 60 * 60
MAX_HOURLY_BUCKETS = 76
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID = re.compile(r"^h0-1-[0-9]{8}T[0-9]{6}Z$")


class ProfileError(RuntimeError):
    """The private profile state is unsafe, corrupt, or inconsistent."""


# Audit/action traces are required for governance or operation, but are not new
# knowledge.  Every other known event belongs to the broad Erkenntnis stream.  A
# proven semantic no-op is subtracted from that stream separately below.
_OPERATING_EVENTS = frozenset(
    {
        "proposal_created",
        "proposal_reviewed",
        "rule_proposed",
        "state_changed",
        "constraint_checked",
        "policy_evaluated",
        "governance_decision",
        "operation_check_recorded",
        "operation_recovery_attempted",
        "operation_recovery_result",
        "ledger_epoch_opened",
        "werkzeug_registriert",
        "proposal_umgesetzt",
        "code_entwurf_erstellt",
        "code_entwurf_geprueft",
        "hand_vorgeschlagen",
        "hand_bestaetigt",
        "hand_ausgefuehrt",
        "hand_abgelehnt",
    }
)

_PRODUCER_FAMILIES = {
    "observation_created": "sensor_and_belief_loop",
    "evidence_recorded": "sensor_and_belief_loop",
    "belief_created": "sensor_and_belief_loop",
    "belief_confirmed": "sensor_and_belief_loop",
    "belief_weakened": "sensor_and_belief_loop",
    "belief_superseded": "sensor_and_belief_loop",
    "forecast_made": "sensor_and_belief_loop",
    "forecast_scored": "sensor_and_belief_loop",
    "assertion_recorded": "knowledge_acquisition",
    "relation_asserted": "knowledge_acquisition",
    "relation_retracted": "knowledge_acquisition",
    "contradiction_detected": "epistemic_review",
    "inquiry_created": "epistemic_review",
    "inquiry_resolved": "epistemic_review",
    "inquiries_reconciled": "epistemic_review",
    "experience_recorded": "maturation",
    "experience_recharacterized": "maturation",
    "rule_proposed": "maturation",
    "rule_activated": "maturation",
    "state_changed": "maturation",
    "proposal_created": "governed_change",
    "proposal_reviewed": "governed_change",
    "constraint_checked": "governed_change",
    "policy_evaluated": "governed_change",
    "governance_decision": "governed_change",
    "operation_check_recorded": "operations",
    "operation_recovery_attempted": "operations",
    "operation_recovery_result": "operations",
    "ledger_epoch_opened": "ledger_integrity",
    "werkzeug_registriert": "capability_work",
    "proposal_umgesetzt": "capability_work",
    "code_entwurf_erstellt": "capability_work",
    "code_entwurf_geprueft": "capability_work",
    "hand_vorgeschlagen": "governed_action",
    "hand_bestaetigt": "governed_action",
    "hand_ausgefuehrt": "governed_action",
    "hand_abgelehnt": "governed_action",
}


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso_utc(value: dt.datetime) -> str:
    if value.tzinfo is None:
        raise ProfileError("profile timestamps must be timezone-aware")
    value = value.astimezone(dt.timezone.utc)
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_utc(value: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ProfileError("profile manifest contains an invalid timestamp") from exc
    if parsed.tzinfo is None:
        raise ProfileError("profile manifest timestamp has no timezone")
    return parsed.astimezone(dt.timezone.utc)


def _canonical_event_timestamp(value) -> str | None:
    """Return only a generated UTC timestamp; never echo untrusted ledger text."""
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return iso_utc(parsed)


def _timestamp_valid_sql(column: str = "created_at") -> str:
    """SQLite predicate for GENUS' fixed millisecond UTC ledger timestamp."""
    digit_pattern = (
        "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T"
        "[0-9][0-9]:[0-9][0-9]:[0-9][0-9]."
        "[0-9][0-9][0-9]Z"
    )
    return (
        f"(typeof({column}) = 'text' AND length({column}) = 24 "
        f"AND {column} GLOB '{digit_pattern}' "
        f"AND substr({column}, 12, 2) BETWEEN '00' AND '23' "
        f"AND julianday({column}) IS NOT NULL "
        f"AND strftime('%Y-%m-%dT%H:%M:%fZ', {column}, '+0 seconds') = {column})"
    )


def default_output_dir(db_path: str | Path) -> Path:
    configured = os.environ.get("GENUS_PROFILE_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path(db_path).expanduser().resolve().parent / "betriebsprofil"


def _profile_root(db_path: str | Path, output_dir: str | Path | None) -> Path:
    candidate = Path(output_dir) if output_dir is not None else default_output_dir(db_path)
    # ``absolute`` normalizes '~' and relative paths without resolving a final symlink;
    # the latter must remain visible to the explicit lstat check.
    return Path(os.path.abspath(candidate.expanduser()))


def capture_due(
    db_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    start: bool = False,
    now: dt.datetime | None = None,
) -> dict:
    """Capture the next due point or return a side-effect-free no-op result.

    Without ``start=True`` a missing manifest remains missing.  This keeps a cron
    installation from silently starting a new evidence series.
    """
    candidate_now = now or utc_now()
    if candidate_now.tzinfo is None:
        raise ProfileError("profile capture time must be timezone-aware")
    observed_at = candidate_now.astimezone(dt.timezone.utc)
    root = _profile_root(db_path, output_dir)
    manifest_path = root / MANIFEST_FILE
    manifest_seen = manifest_path.exists()

    if not manifest_seen:
        _reject_orphaned_profile_evidence(root, manifest_path)
    if not manifest_seen and not start:
        return {"action": "not_started", "status": "not_started"}
    if not manifest_seen and start:
        # Fail before creating profile state when the configured ledger is absent.
        probe = db.connect_readonly(db_path)
        probe.close()

    _ensure_private_dir(root)
    with _profile_lock(root):
        if manifest_path.exists():
            if start:
                raise ProfileError("profile series already started")
            manifest = _read_manifest(manifest_path)
            _verify_capture_files(root, manifest)
        else:
            if manifest_seen:
                raise ProfileError("profile manifest disappeared during lock acquisition")
            _reject_orphaned_profile_evidence(root, manifest_path)
            if not start:
                return {"action": "not_started", "status": "not_started"}
            manifest = _new_manifest(observed_at)

        if manifest["status"] == "aborted":
            return {"action": "aborted", "status": "aborted"}
        if manifest["status"] == "complete":
            return {"action": "complete", "status": "complete"}

        next_item = _next_schedule_item(manifest)
        if next_item is None:
            return {"action": "complete", "status": "complete"}

        label, due_hours = next_item
        started_at = parse_utc(manifest["started_at"])
        due_at = started_at + dt.timedelta(hours=due_hours)
        if observed_at < due_at:
            return {
                "action": "not_due",
                "status": "running",
                "next_label": label,
                "due_at": iso_utc(due_at),
            }

        late_by_seconds = max(0.0, (observed_at - due_at).total_seconds())
        if label != "baseline" and late_by_seconds > MAX_CAPTURE_LATENESS_SECONDS:
            manifest.update(
                {
                    "status": "aborted",
                    "aborted_at": iso_utc(observed_at),
                    "missed_label": label,
                    "late_by_seconds": round(late_by_seconds, 3),
                }
            )
            _atomic_write(manifest_path, _json_bytes(manifest))
            return {
                "action": "aborted_missed",
                "status": "aborted",
                "missed_label": label,
                "late_by_seconds": round(late_by_seconds, 3),
            }

        previous = manifest["captures"][-1] if manifest["captures"] else None
        conn = db.connect_readonly(db_path)
        try:
            snapshot = _capture_snapshot(
                conn,
                db_path=Path(db_path),
                label=label,
                observed_at=observed_at,
                started_at=started_at,
                due_at=due_at,
                previous=previous,
            )
        finally:
            conn.close()

        snapshot_bytes = _json_bytes(snapshot)
        if len(snapshot_bytes) > MAX_SNAPSHOT_BYTES:
            raise ProfileError("profile snapshot exceeds the fixed size limit")
        filename = SNAPSHOT_FILES[label]
        _atomic_write(root / filename, snapshot_bytes)
        digest = hashlib.sha256(snapshot_bytes).hexdigest()
        capture = {
            "label": label,
            "file": filename,
            "sha256": digest,
            "captured_at": snapshot["captured_at"],
            "due_at": snapshot["due_at"],
            "actual_elapsed_seconds": snapshot["actual_elapsed_seconds"],
            "late_by_seconds": snapshot["late_by_seconds"],
            "head_event_id": snapshot["ledger"]["head_event_id"],
            "continuity_anchor_sha256": snapshot["ledger"][
                "continuity_anchor_sha256"
            ],
            "continuity_basis": snapshot["ledger"]["continuity_basis"],
            "database_file_identity_sha256": snapshot["ledger"][
                "database_file_identity_sha256"
            ],
        }
        manifest["captures"].append(capture)
        manifest["status"] = "complete" if label == "h72" else "running"
        if label == "h72":
            manifest["completed_at"] = snapshot["captured_at"]
        _atomic_write(manifest_path, _json_bytes(manifest))

        return {
            "action": "captured",
            "status": manifest["status"],
            "label": label,
            "captured_at": snapshot["captured_at"],
            "head_event_id": snapshot["ledger"]["head_event_id"],
            "events_in_interval": snapshot["interval"]["event_count"],
            "late_by_seconds": snapshot["late_by_seconds"],
        }


def profile_status(
    db_path: str | Path, *, output_dir: str | Path | None = None
) -> dict:
    root = _profile_root(db_path, output_dir)
    manifest_path = root / MANIFEST_FILE
    if not manifest_path.exists():
        _reject_orphaned_profile_evidence(root, manifest_path)
        return {"status": "not_started", "captures": []}
    _validate_private_dir(root)
    with _profile_lock(root):
        manifest = _read_manifest(manifest_path)
        _verify_capture_files(root, manifest)
    return {
        "schema_version": manifest["schema_version"],
        "run_id": manifest["run_id"],
        "status": manifest["status"],
        "started_at": manifest["started_at"],
        "captures": manifest["captures"],
        "next_label": (
            (_next_schedule_item(manifest) or (None, None))[0]
            if manifest["status"] == "running"
            else None
        ),
        "files_verified": True,
    }


def _new_manifest(started_at: dt.datetime) -> dict:
    compact = started_at.strftime("%Y%m%dT%H%M%SZ")
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": f"h0-1-{compact}",
        "status": "running",
        "started_at": iso_utc(started_at),
        "schedule_hours": [hours for _, hours in SCHEDULE],
        "captures": [],
        "methodology": _methodology(),
    }


def _methodology() -> dict:
    return {
        "interval_key": "event_id",
        "interval_form": "(previous_head_id,current_head_id]",
        "read_only": True,
        "payloads_persisted": False,
        "source_values_allowlisted": True,
        "physical_storage_is_point_in_time": True,
        "wal_is_volatile_allocation_not_growth": True,
        "producer_attribution": "inferred_from_event_type_not_observed_process_identity",
        "maximum_capture_lateness_seconds": MAX_CAPTURE_LATENESS_SECONDS,
        "local_hashes_are_corruption_detectors_not_external_anchors": True,
    }


def _next_schedule_item(manifest: dict) -> tuple[str, int] | None:
    captured = [item["label"] for item in manifest["captures"]]
    expected_prefix = [label for label, _ in SCHEDULE[: len(captured)]]
    if captured != expected_prefix:
        raise ProfileError("profile captures are not a valid schedule prefix")
    if len(captured) == len(SCHEDULE):
        return None
    return SCHEDULE[len(captured)]


def _reject_orphaned_profile_evidence(root: Path, manifest_path: Path) -> None:
    if manifest_path.is_symlink():
        raise ProfileError("profile manifest must not be a symlink")
    if not root.exists() and not root.is_symlink():
        return
    _validate_private_dir(root)
    for filename in SNAPSHOT_FILES.values():
        candidate = root / filename
        if candidate.exists() or candidate.is_symlink():
            raise ProfileError("profile snapshot exists without its manifest")


def _capture_snapshot(
    conn,
    *,
    db_path: Path,
    label: str,
    observed_at: dt.datetime,
    started_at: dt.datetime,
    due_at: dt.datetime,
    previous: dict | None,
) -> dict:
    started = time.perf_counter()
    captured_at = iso_utc(observed_at)
    database_identity = _database_file_identity(db_path)
    conn.execute("BEGIN")
    try:
        head = conn.execute(
            """
            SELECT COUNT(*) AS events, COALESCE(MAX(id), 0) AS head_id,
                   MIN(id) AS min_id
            FROM event_log
            """
        ).fetchone()
        head_id = int(head["head_id"])
        head_row = (
            conn.execute(
                """
                SELECT id, event_type, payload, created_at, prev_seal, seal
                FROM event_log WHERE id = ?
                """,
                (head_id,),
            ).fetchone()
            if head_id
            else None
        )
        first_row = conn.execute(
            "SELECT created_at FROM event_log ORDER BY id LIMIT 1"
        ).fetchone()

        if previous is not None:
            _verify_ledger_continuity(
                conn,
                previous=previous,
                current_head_id=head_id,
                database_identity=database_identity,
            )
        continuity_anchor, continuity_basis = _continuity_anchor(conn, head_id)

        if previous is None:
            previous_head = 0
            interval_start = observed_at - dt.timedelta(hours=24)
            where = (
                f"{_timestamp_valid_sql()} "
                "AND julianday(created_at) >= julianday(?) "
                "AND julianday(created_at) <= julianday(?) AND id <= ?"
            )
            params = (iso_utc(interval_start), captured_at, head_id)
            interval_kind = "baseline_lookback_24h"
            elapsed_seconds = 24 * 3600.0
            hourly_start = interval_start
        else:
            previous_head = int(previous["head_event_id"])
            where = "id > ? AND id <= ?"
            params = (previous_head, head_id)
            interval_kind = "head_id_delta"
            elapsed_seconds = max(
                0.001,
                (observed_at - parse_utc(previous["captured_at"])).total_seconds(),
            )
            hourly_start = parse_utc(previous["captured_at"])

        interval = _interval_metrics(
            conn,
            where,
            params,
            elapsed_seconds,
            hourly_start=hourly_start,
            hourly_end=observed_at,
        )
        history_48h = (
            _hourly_counts(
                conn,
                f"{_timestamp_valid_sql()} "
                "AND julianday(created_at) >= julianday(?) "
                "AND julianday(created_at) <= julianday(?) AND id <= ?",
                (
                    iso_utc(observed_at - dt.timedelta(hours=48)),
                    captured_at,
                    head_id,
                ),
                bucket_start=observed_at - dt.timedelta(hours=48),
                bucket_end=observed_at,
            )
            if previous is None
            else []
        )
        quality = _ledger_quality(
            conn, observed_at, int(head["events"]), head["min_id"], head_id
        )
        capabilities = _capability_metrics(conn)
        page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
        page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
        free_pages = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
    finally:
        conn.rollback()

    physical = _physical_storage(db_path)
    duration_ms = round((time.perf_counter() - started) * 1000, 1)
    actual_elapsed = max(0.0, (observed_at - started_at).total_seconds())
    late_by = max(0.0, (observed_at - due_at).total_seconds())
    known_types = frozenset(integrity.REQUIRED_EVENT_KEYS)
    raw_head_type = head_row["event_type"] if head_row is not None else None
    head_type = raw_head_type if raw_head_type in known_types else ("unknown" if raw_head_type else None)

    return {
        "schema_version": SCHEMA_VERSION,
        "label": label,
        "captured_at": captured_at,
        "due_at": iso_utc(due_at),
        "actual_elapsed_seconds": round(actual_elapsed, 3),
        "late_by_seconds": round(late_by, 3),
        "measurement_duration_ms": duration_ms,
        "ledger": {
            "event_count": int(head["events"]),
            "head_event_id": head_id,
            "head_event_type": head_type,
            "head_created_at": (
                _canonical_event_timestamp(head_row["created_at"])
                if head_row is not None
                else None
            ),
            "first_created_at": (
                _canonical_event_timestamp(first_row["created_at"])
                if first_row is not None
                else None
            ),
            "continuity_anchor_sha256": continuity_anchor,
            "continuity_basis": continuity_basis,
            "database_file_identity_sha256": database_identity,
        },
        "interval": {
            "kind": interval_kind,
            "start_head_exclusive": previous_head if previous is not None else None,
            "end_head_inclusive": head_id,
            "elapsed_seconds": round(elapsed_seconds, 3),
            **interval,
        },
        "baseline_history_48h": history_48h,
        "storage": {
            "page_size": page_size,
            "page_count": page_count,
            "free_pages": free_pages,
            "allocated_page_bytes": page_size * page_count,
            "used_page_bytes": page_size * (page_count - free_pages),
            **physical,
            "file_probe_relation": "immediately_after_read_transaction",
        },
        "data_quality": quality,
        "capability_indicators": capabilities,
        "privacy": {
            "payload_content_persisted": False,
            "raw_source_values_persisted": False,
            "entity_values_persisted": False,
            "filesystem_paths_persisted": False,
        },
    }


def _interval_metrics(
    conn,
    where: str,
    params: tuple,
    elapsed_seconds: float,
    *,
    hourly_start: dt.datetime,
    hourly_end: dt.datetime,
) -> dict:
    known = frozenset(integrity.REQUIRED_EVENT_KEYS)
    rows = conn.execute(
        f"SELECT event_type, COUNT(*) AS n FROM event_log WHERE {where} "
        "GROUP BY event_type ORDER BY n DESC, event_type",
        params,
    ).fetchall()
    event_types: dict[str, int] = {}
    for row in rows:
        raw_type, count = row["event_type"], int(row["n"])
        safe_type = raw_type if raw_type in known else "unknown"
        event_types[safe_type] = event_types.get(safe_type, 0) + count

    event_count = sum(event_types.values())
    valid_known_counts = _contract_valid_counts(
        conn, where, params, observed_at=hourly_end
    )
    avoidable = _semantic_similarity_repetitions(
        conn, where, params, observed_at=hourly_end
    )
    operating = sum(valid_known_counts.get(name, 0) for name in _OPERATING_EVENTS)
    valid_known_count = sum(valid_known_counts.values())
    unknown_or_invalid = max(event_count - valid_known_count, 0)
    knowledge = max(valid_known_count - operating - avoidable, 0)
    classification_total = knowledge + operating + avoidable + unknown_or_invalid
    if classification_total != event_count:
        raise ProfileError("profile event classifications do not reconcile")

    source_groups = _source_groups(conn, where, params)
    producer_groups: dict[str, int] = {}
    for event_type, count in valid_known_counts.items():
        family = _PRODUCER_FAMILIES.get(event_type, "knowledge_and_reasoning")
        producer_groups[family] = producer_groups.get(family, 0) + count
    producer_groups["unknown"] = unknown_or_invalid

    payload_sizes = conn.execute(
        f"SELECT COALESCE(SUM(length(CAST(payload AS BLOB))), 0) AS total_bytes, "
        f"COALESCE(MAX(length(CAST(payload AS BLOB))), 0) AS max_bytes "
        f"FROM event_log WHERE {where}",
        params,
    ).fetchone()
    hourly = _hourly_counts(
        conn,
        where,
        params,
        bucket_start=hourly_start,
        bucket_end=hourly_end,
    )
    rate = round(event_count * 86400.0 / elapsed_seconds, 1) if elapsed_seconds else None
    return {
        "event_count": event_count,
        "events_per_24h_normalized": rate,
        "event_types": event_types,
        "classification": {
            "erkenntnis": knowledge,
            "betriebsspur": operating,
            "vermeidbare_wiederholung": avoidable,
            "unklar": unknown_or_invalid,
        },
        "source_families": source_groups,
        "source_semantics": "epistemic_origin_not_observed_process_identity",
        "inferred_producer_families": producer_groups,
        "producer_semantics": "static_event_type_proxy_not_observed_process_identity",
        "hourly_utc": hourly,
        "payload_bytes_total": int(payload_sizes["total_bytes"]),
        "payload_bytes_max": int(payload_sizes["max_bytes"]),
        "semantic_repetition_rule": "model_embedder_verwandt_canonical_pair_same_derivation",
        "contract_invalid_or_unknown_events": unknown_or_invalid,
    }


def _contract_valid_counts(
    conn,
    where: str,
    params: tuple,
    *,
    observed_at: dt.datetime,
) -> dict[str, int]:
    cases = []
    for event_type, required in sorted(integrity.REQUIRED_EVENT_KEYS.items()):
        safe_payload = "CASE WHEN json_valid(payload) THEN payload ELSE '{}' END"
        missing = " OR ".join(
            f"json_type({safe_payload}, '$.{key}') IS NULL" for key in sorted(required)
        )
        valid = (
            "CASE WHEN json_valid(payload) = 0 THEN 0 "
            f"WHEN json_type({safe_payload}) <> 'object' THEN 0 "
            f"WHEN NOT {_timestamp_valid_sql()} THEN 0 "
            "WHEN julianday(created_at) > "
            "julianday((SELECT observed_at FROM capture_bound), '+5 minutes') THEN 0 "
            f"WHEN {missing or '0'} THEN 0 ELSE 1 END"
        )
        cases.append(f"WHEN '{event_type}' THEN {valid}")
    valid_case = "CASE event_type " + " ".join(cases) + " ELSE 0 END"
    rows = conn.execute(
        f"WITH capture_bound(observed_at) AS (VALUES (?)) "
        f"SELECT event_type, COALESCE(SUM({valid_case}), 0) AS valid "
        f"FROM event_log WHERE {where} GROUP BY event_type",
        (iso_utc(observed_at), *params),
    ).fetchall()
    known = frozenset(integrity.REQUIRED_EVENT_KEYS)
    return {
        row["event_type"]: int(row["valid"])
        for row in rows
        if row["event_type"] in known
    }


def _semantic_similarity_repetitions(
    conn,
    where: str,
    params: tuple,
    *,
    observed_at: dt.datetime,
) -> int:
    safe_payload = "CASE WHEN json_valid(payload) THEN payload ELSE '{}' END"
    row = conn.execute(
        f"""
        WITH valid_similarity AS (
            SELECT
                id,
                created_at,
                json_extract({safe_payload}, '$.subject') AS subject,
                json_extract({safe_payload}, '$.object') AS object,
                json_extract({safe_payload}, '$.derivation') AS derivation
            FROM event_log
            WHERE event_type = 'relation_asserted'
              AND json_valid(payload)
              AND json_type({safe_payload}) = 'object'
              AND {_timestamp_valid_sql()}
              AND julianday(created_at) <= julianday(?, '+5 minutes')
              AND json_type({safe_payload}, '$.subject') IS NOT NULL
              AND json_type({safe_payload}, '$.predicate') IS NOT NULL
              AND json_type({safe_payload}, '$.object') IS NOT NULL
              AND json_type({safe_payload}, '$.source') IS NOT NULL
              AND json_type({safe_payload}, '$.derivation') IS NOT NULL
              AND json_extract({safe_payload}, '$.source') = 'model:embedder'
              AND json_extract({safe_payload}, '$.predicate') = 'verwandt'
        ), canonicalized AS (
            SELECT
                id,
                created_at,
                CASE WHEN subject <= object THEN subject ELSE object END AS a,
                CASE WHEN subject <= object THEN object ELSE subject END AS b,
                derivation
            FROM valid_similarity
        ), ranked AS (
            SELECT
                id,
                created_at,
                ROW_NUMBER() OVER (
                    PARTITION BY a, b, derivation ORDER BY id
                ) AS occurrence
            FROM canonicalized
        )
        SELECT COALESCE(SUM(CASE WHEN occurrence > 1 THEN 1 ELSE 0 END), 0)
            AS repeats
        FROM ranked
        WHERE {where}
        """,
        (iso_utc(observed_at), *params),
    ).fetchone()
    return int(row["repeats"])


def _source_groups(conn, where: str, params: tuple) -> dict[str, int]:
    qualified_where = re.sub(
        r"\b(created_at|id)\b", lambda match: f"e.{match.group(1)}", where
    )
    rows = conn.execute(
        f"""
        WITH source_rows AS (
            SELECT CASE
                WHEN json_valid(e.payload) = 0 THEN NULL
                WHEN e.event_type = 'evidence_recorded' THEN
                    COALESCE(
                        json_extract(e.payload, '$.source'),
                        CASE WHEN json_valid(o.payload)
                             THEN json_extract(o.payload, '$.source') END,
                        'legacy_sensor_fallback'
                    )
                WHEN json_valid(e.payload) THEN
                    COALESCE(json_extract(e.payload, '$.source'),
                             json_extract(e.payload, '$.quelle'))
                ELSE NULL
            END AS source_value
            FROM event_log AS e
            LEFT JOIN event_log AS o
             ON e.event_type = 'evidence_recorded'
             AND o.id = CAST(
                 json_extract(
                     CASE WHEN json_valid(e.payload) THEN e.payload ELSE '{{}}' END,
                     '$.observation_id'
                 ) AS INTEGER
             )
             AND o.event_type = 'observation_created'
            WHERE {qualified_where}
        ), classified AS (
            SELECT CASE
                WHEN typeof(source_value) <> 'text' OR trim(source_value) = ''
                    THEN 'missing'
                WHEN lower(trim(source_value)) IN ('ronny', 'kuratiert')
                    THEN 'owner_or_curated'
                WHEN lower(trim(source_value)) = 'human' THEN 'human_other'
                WHEN lower(trim(source_value)) LIKE 'model:%' THEN 'model'
                WHEN lower(trim(source_value)) LIKE 'psutil.%'
                  OR lower(trim(source_value)) LIKE 'git.%'
                  OR lower(trim(source_value)) = 'sensor' THEN 'local_sensor'
                WHEN lower(trim(source_value)) IN
                     ('wikidata', 'wikidata-lexemes', 'dbnary')
                    THEN 'external_reference'
                WHEN lower(trim(source_value)) IN ('open-meteo', 'wttr.in')
                    THEN 'external_weather'
                WHEN lower(trim(source_value)) IN ('muster', 'gebaerde', 'code')
                  OR lower(trim(source_value)) LIKE 'werkstatt:%'
                    THEN 'deterministic_internal'
                WHEN lower(trim(source_value)) IN ('mock', 'test') THEN 'test_fixture'
                WHEN lower(trim(source_value)) = 'legacy_sensor_fallback'
                    THEN 'legacy_sensor_fallback'
                ELSE 'other'
            END AS family
            FROM source_rows
        )
        SELECT family, COUNT(*) AS n
        FROM classified
        GROUP BY family
        ORDER BY family
        """,
        params,
    ).fetchall()
    return {row["family"]: int(row["n"]) for row in rows}


def normalize_source(value) -> str:
    """Map an untrusted source value to a fixed privacy-safe family."""
    if not isinstance(value, str) or not value.strip():
        return "missing"
    source = value.strip().lower()
    if source in {"ronny", "kuratiert"}:
        return "owner_or_curated"
    if source == "human":
        return "human_other"
    if source.startswith("model:"):
        return "model"
    if source.startswith(("psutil.", "git.")) or source == "sensor":
        return "local_sensor"
    if source in {"wikidata", "wikidata-lexemes", "dbnary"}:
        return "external_reference"
    if source in {"open-meteo", "wttr.in"}:
        return "external_weather"
    if source in {"muster", "gebaerde", "code"} or source.startswith("werkstatt:"):
        return "deterministic_internal"
    if source in {"mock", "test"}:
        return "test_fixture"
    if source == "legacy_sensor_fallback":
        return "legacy_sensor_fallback"
    return "other"


def _hourly_counts(
    conn,
    where: str,
    params: tuple,
    *,
    bucket_start: dt.datetime,
    bucket_end: dt.datetime,
) -> list[dict]:
    rows = conn.execute(
        f"""
        SELECT CASE
            WHEN NOT {_timestamp_valid_sql()} THEN 'invalid_timestamp'
            WHEN julianday(created_at) < julianday(?) THEN 'before_window'
            WHEN julianday(created_at) > julianday(?) THEN 'after_window'
            ELSE COALESCE(
                strftime('%Y-%m-%dT%H:00:00Z', created_at),
                'invalid_timestamp'
            )
        END AS hour_utc,
        COUNT(*) AS events
        FROM event_log WHERE {where}
        GROUP BY hour_utc ORDER BY hour_utc
        """,
        (iso_utc(bucket_start), iso_utc(bucket_end), *params),
    ).fetchall()
    if len(rows) > MAX_HOURLY_BUCKETS:
        raise ProfileError("profile hourly aggregation exceeds its fixed bucket bound")
    return [
        {"hour_utc": row["hour_utc"], "events": int(row["events"])} for row in rows
    ]


def _ledger_quality(conn, observed_at, event_count: int, min_id, max_id: int) -> dict:
    row = conn.execute(
        f"""
        SELECT
            COALESCE(SUM(CASE WHEN json_valid(payload) = 0 THEN 1 ELSE 0 END), 0)
                AS invalid_json,
            COALESCE(SUM(CASE WHEN json_valid(payload) = 1
                                  AND json_type(payload) <> 'object' THEN 1 ELSE 0 END), 0)
                AS non_object_payload,
            COALESCE(SUM(CASE WHEN NOT {_timestamp_valid_sql()}
                              THEN 1 ELSE 0 END), 0)
                AS invalid_timestamp,
            COALESCE(SUM(CASE WHEN {_timestamp_valid_sql()}
                                  AND julianday(created_at) > julianday(?, '+5 minutes')
                              THEN 1 ELSE 0 END), 0) AS future_timestamp
        FROM event_log
        """,
        (iso_utc(observed_at),),
    ).fetchone()
    inversions = conn.execute(
        f"""
        SELECT COUNT(*) AS n FROM (
            SELECT created_jd, LAG(created_jd) OVER (ORDER BY id) AS previous_jd
            FROM (
                SELECT id,
                       CASE WHEN {_timestamp_valid_sql()}
                            THEN julianday(created_at) END AS created_jd
                FROM event_log
            )
        ) WHERE created_jd < previous_jd
        """
    ).fetchone()["n"]
    # A valid append-only ledger starts at one as well as remaining gap-free.
    missing_ids = max(0, max_id - event_count) if event_count else 0
    return {
        "scope": "full_ledger_at_capture",
        "minimum_event_id": int(min_id) if min_id is not None else None,
        "maximum_event_id": max_id,
        "event_ids_contiguous": missing_ids == 0,
        "missing_event_ids": missing_ids,
        "invalid_json_events": int(row["invalid_json"]),
        "non_object_payload_events": int(row["non_object_payload"]),
        "invalid_timestamp_events": int(row["invalid_timestamp"]),
        "future_timestamp_events": int(row["future_timestamp"]),
        "timestamp_inversions_by_event_id": int(inversions),
        "timestamp_is_not_interval_key": True,
    }


def _capability_metrics(conn) -> dict:
    def count(sql: str, params: tuple = ()) -> int:
        return int(conn.execute(sql, params).fetchone()[0])

    values = {
        "active_beliefs": count("SELECT COUNT(*) FROM belief_projection WHERE state = 'active'"),
        "relation_projection_rows": count("SELECT COUNT(*) FROM relation_projection"),
        "value_projection_rows": count("SELECT COUNT(*) FROM value_projection"),
        "experiences": count("SELECT COUNT(*) FROM experience_log"),
        "active_rules": count("SELECT COUNT(*) FROM rule_projection WHERE status = 'active'"),
        "open_inquiries": count("SELECT COUNT(*) FROM inquiry_log WHERE state = 'open'"),
        "pending_proposals": count("SELECT COUNT(*) FROM proposal_log WHERE state = 'pending'"),
    }
    try:
        bounded = thermometer.betriebsstand(conn)
        general = bounded["generalisierung"]
        gaps = bounded["luecken"]
        values["bounded_thermometer_available"] = True
        values["planner_intents"] = len(general["absichten_auf_planer"])
        values["planner_traffic_share"] = general["verkehr_ueber_planer"]
        values["seeded_intent_leaves"] = int(general["blaetter_gesaet"])
        values["actionable_intent_leaves"] = int(general["blaetter_handelbar"])
        values["intent_leaves_without_handler"] = len(gaps["blaetter_ohne_handler"])
        values["capabilities_not_live"] = len(gaps["faehigkeiten_nicht_live"])
    except Exception:  # a missing membrane-local counter must not abort ledger evidence
        values["bounded_thermometer_available"] = False
    values["scope"] = "bounded_projection_and_targeted_operating_counts"
    values["interpretation"] = "human_sensor_not_optimization_target"
    return values


def _database_file_identity(db_path: Path) -> str:
    """Hash a stable file identity without persisting a filesystem path."""
    try:
        info = db_path.expanduser().stat()
    except OSError as exc:
        raise ProfileError("cannot stat the configured ledger file") from exc
    identity = f"{int(info.st_dev)}:{int(info.st_ino)}".encode("ascii")
    return hashlib.sha256(b"genus-db-file-identity-v1\0" + identity).hexdigest()


def _continuity_anchor(
    conn, head_id: int, *, basis: str | None = None
) -> tuple[str, str]:
    """Hash every current row field in the prefix with bounded memory.

    A stored seal alone cannot detect payload or timestamp edits when the seal
    column itself is left untouched.  The profile therefore fingerprints the
    complete prefix even on an actively sealed ledger.
    """
    selected_basis = basis or "full_prefix"
    if selected_basis != "full_prefix":
        raise ProfileError("profile continuity basis is unsupported")

    digest = hashlib.sha256(b"genus-full-prefix-v1\0")
    cursor = conn.execute(
        """
        SELECT id, event_type, payload, created_at, prev_seal, seal
        FROM event_log WHERE id <= ? ORDER BY id
        """,
        (head_id,),
    )
    while True:
        rows = cursor.fetchmany(1024)
        if not rows:
            break
        for event in rows:
            digest.update(int(event["id"]).to_bytes(8, "big", signed=False))
            for value in (
                event["event_type"],
                event["payload"],
                event["created_at"],
                event["prev_seal"],
                event["seal"],
            ):
                if value is None:
                    digest.update(b"\xff" * 8)
                    continue
                encoded = str(value).encode("utf-8")
                digest.update(len(encoded).to_bytes(8, "big", signed=False))
                digest.update(encoded)
    return digest.hexdigest(), selected_basis


def _verify_ledger_continuity(
    conn,
    *,
    previous: dict,
    current_head_id: int,
    database_identity: str,
) -> None:
    previous_head = int(previous["head_event_id"])
    if current_head_id < previous_head:
        raise ProfileError("ledger head regressed since the previous capture")
    if previous["database_file_identity_sha256"] != database_identity:
        raise ProfileError("configured ledger file was replaced since the previous capture")
    actual_anchor, actual_basis = _continuity_anchor(
        conn,
        previous_head,
        basis=previous["continuity_basis"],
    )
    if actual_basis != previous["continuity_basis"] or actual_anchor != previous[
        "continuity_anchor_sha256"
    ]:
        raise ProfileError("ledger prefix changed since the previous capture")


def _physical_storage(db_path: Path) -> dict:
    resolved = db_path.expanduser().resolve()
    files = {
        "main_file": resolved,
        "wal_file": Path(f"{resolved}-wal"),
        "shm_file": Path(f"{resolved}-shm"),
    }
    result = {}
    for key, path in files.items():
        if not path.exists():
            result[f"{key}_bytes"] = 0
            result[f"{key}_mode"] = None
            continue
        info = path.stat()
        result[f"{key}_bytes"] = int(info.st_size)
        result[f"{key}_mode"] = f"{stat.S_IMODE(info.st_mode):04o}"
    return result


def _ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise ProfileError("profile output must be a real directory, not a symlink")
    os.chmod(path, 0o700)
    _validate_private_dir(path)


def _validate_private_dir(path: Path) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise ProfileError("profile output directory cannot be inspected") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise ProfileError("profile output must be a real directory, not a symlink")
    if os.name == "posix":
        if hasattr(os, "geteuid") and info.st_uid != os.geteuid():
            raise ProfileError("profile output directory has a different owner")
        if stat.S_IMODE(info.st_mode) & 0o077:
            raise ProfileError("profile output directory is not private (mode 0700 required)")


@contextlib.contextmanager
def _profile_lock(root: Path) -> Iterator[None]:
    lock_path = root / LOCK_FILE
    if lock_path.is_symlink():
        raise ProfileError("profile lock must not be a symlink")
    try:
        before = lock_path.lstat()
    except FileNotFoundError:
        before = None
    except OSError as exc:
        raise ProfileError("profile lock cannot be inspected") from exc
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise ProfileError("cannot safely open profile lock") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ProfileError("profile lock must be a regular file")
        if before is not None and (before.st_dev, before.st_ino) != (
            info.st_dev,
            info.st_ino,
        ):
            raise ProfileError("profile lock changed while it was opened")
        if os.name == "posix" and hasattr(os, "geteuid") and info.st_uid != os.geteuid():
            raise ProfileError("profile lock has a different owner")
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        else:
            os.chmod(lock_path, 0o600)
        handle = os.fdopen(descriptor, "r+b", buffering=0)
        descriptor = -1
    finally:
        if descriptor >= 0:
            os.close(descriptor)

    if os.fstat(handle.fileno()).st_size == 0:
        handle.write(b"\0")
        handle.flush()
        os.fsync(handle.fileno())
    handle.seek(0)
    locked = False
    try:
        if os.name == "nt":  # pragma: no cover - exercised on Windows CI/desktop
            try:
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                locked = True
            except OSError as exc:
                raise ProfileError("another profile capture is already running") from exc
        else:
            import fcntl

            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except BlockingIOError as exc:
                raise ProfileError("another profile capture is already running") from exc
        yield
    finally:
        if locked:
            if os.name == "nt":  # pragma: no cover - exercised on Windows CI/desktop
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _read_manifest(path: Path) -> dict:
    try:
        content = _read_bounded_regular_file(path, MAX_MANIFEST_BYTES)
        manifest = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProfileError("profile manifest is not valid JSON") from exc
    _validate_manifest(manifest)
    return manifest


def _validate_manifest(manifest) -> None:
    if not isinstance(manifest, dict):
        raise ProfileError("profile manifest must be a JSON object")
    status = manifest.get("status")
    if status not in {"running", "complete", "aborted"}:
        raise ProfileError("profile manifest status is unsupported")
    expected_keys = {
        "schema_version",
        "run_id",
        "status",
        "started_at",
        "schedule_hours",
        "captures",
        "methodology",
    }
    if status == "complete":
        expected_keys.add("completed_at")
    elif status == "aborted":
        expected_keys.update(
            {"aborted_at", "missed_label", "late_by_seconds"}
        )
    if set(manifest) != expected_keys:
        raise ProfileError("profile manifest fields differ from the fixed contract")
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise ProfileError("profile manifest schema is unsupported")
    if not isinstance(manifest["run_id"], str) or not _RUN_ID.fullmatch(
        manifest["run_id"]
    ):
        raise ProfileError("profile manifest run id is invalid")
    started_at = _validated_profile_timestamp(manifest["started_at"])
    expected_run_id = f"h0-1-{started_at.strftime('%Y%m%dT%H%M%SZ')}"
    if manifest["run_id"] != expected_run_id:
        raise ProfileError("profile manifest run id does not match its start")
    if manifest["schedule_hours"] != [hours for _, hours in SCHEDULE]:
        raise ProfileError("profile manifest schedule differs from the fixed contract")
    if manifest["methodology"] != _methodology():
        raise ProfileError("profile manifest methodology differs from the fixed contract")
    captures = manifest["captures"]
    if not isinstance(captures, list) or len(captures) > len(SCHEDULE):
        raise ProfileError("profile manifest captures must be a bounded list")

    expected_capture_keys = {
        "label",
        "file",
        "sha256",
        "captured_at",
        "due_at",
        "actual_elapsed_seconds",
        "late_by_seconds",
        "head_event_id",
        "continuity_anchor_sha256",
        "continuity_basis",
        "database_file_identity_sha256",
    }
    previous_head = -1
    previous_captured_at = started_at
    for index, capture in enumerate(captures):
        if not isinstance(capture, dict) or set(capture) != expected_capture_keys:
            raise ProfileError("profile manifest capture fields are invalid")
        expected_label, due_hours = SCHEDULE[index]
        if capture["label"] != expected_label:
            raise ProfileError("profile captures are not a valid schedule prefix")
        if capture["file"] != SNAPSHOT_FILES[expected_label]:
            raise ProfileError("profile manifest contains an invalid snapshot filename")
        for digest_key in (
            "sha256",
            "continuity_anchor_sha256",
            "database_file_identity_sha256",
        ):
            if not isinstance(capture[digest_key], str) or not _HEX64.fullmatch(
                capture[digest_key]
            ):
                raise ProfileError("profile manifest contains an invalid digest")
        if capture["continuity_basis"] != "full_prefix":
            raise ProfileError("profile manifest continuity basis is invalid")
        captured_at = _validated_profile_timestamp(capture["captured_at"])
        due_at = _validated_profile_timestamp(capture["due_at"])
        expected_due = started_at + dt.timedelta(hours=due_hours)
        if due_at != expected_due:
            raise ProfileError("profile capture due time differs from the fixed schedule")
        if captured_at < previous_captured_at or captured_at < due_at:
            raise ProfileError("profile capture times are not monotone")
        head_id = capture["head_event_id"]
        if isinstance(head_id, bool) or not isinstance(head_id, int) or head_id < 0:
            raise ProfileError("profile manifest head id is invalid")
        if head_id < previous_head:
            raise ProfileError("profile manifest head ids are not monotone")
        actual_elapsed = _nonnegative_number(capture["actual_elapsed_seconds"])
        late_by = _nonnegative_number(capture["late_by_seconds"])
        expected_elapsed = (captured_at - started_at).total_seconds()
        expected_late = (captured_at - due_at).total_seconds()
        if abs(actual_elapsed - expected_elapsed) > 0.001:
            raise ProfileError("profile capture elapsed time is inconsistent")
        if abs(late_by - expected_late) > 0.001:
            raise ProfileError("profile capture lateness is inconsistent")
        if expected_label != "baseline" and late_by > MAX_CAPTURE_LATENESS_SECONDS:
            raise ProfileError("profile capture exceeds the maximum lateness")
        previous_head = head_id
        previous_captured_at = captured_at

    if status == "running" and len(captures) == len(SCHEDULE):
        raise ProfileError("complete profile is marked as running")
    if status == "complete":
        if len(captures) != len(SCHEDULE):
            raise ProfileError("incomplete profile is marked complete")
        if _validated_profile_timestamp(manifest["completed_at"]) != previous_captured_at:
            raise ProfileError("profile completion time is inconsistent")
    if status == "aborted":
        if len(captures) >= len(SCHEDULE):
            raise ProfileError("complete profile cannot be marked aborted")
        next_label, due_hours = SCHEDULE[len(captures)]
        if manifest["missed_label"] != next_label:
            raise ProfileError("profile aborted at an unexpected schedule label")
        aborted_at = _validated_profile_timestamp(manifest["aborted_at"])
        late_by = _nonnegative_number(manifest["late_by_seconds"])
        expected_late = (
            aborted_at - (started_at + dt.timedelta(hours=due_hours))
        ).total_seconds()
        if late_by <= MAX_CAPTURE_LATENESS_SECONDS or abs(late_by - expected_late) > 0.001:
            raise ProfileError("profile abort lateness is inconsistent")


def _validated_profile_timestamp(value) -> dt.datetime:
    if not isinstance(value, str):
        raise ProfileError("profile manifest timestamp must be text")
    parsed = parse_utc(value)
    if iso_utc(parsed) != value:
        raise ProfileError("profile manifest timestamp is not canonical UTC")
    return parsed


def _nonnegative_number(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProfileError("profile manifest metric must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ProfileError("profile manifest metric must be finite and non-negative")
    return result


def _verify_capture_files(root: Path, manifest: dict) -> None:
    for capture in manifest["captures"]:
        label = capture.get("label")
        expected_file = SNAPSHOT_FILES.get(label)
        if expected_file is None or capture.get("file") != expected_file:
            raise ProfileError("profile manifest contains an invalid snapshot filename")
        content = _read_bounded_regular_file(root / expected_file, MAX_SNAPSHOT_BYTES)
        if hashlib.sha256(content).hexdigest() != capture.get("sha256"):
            raise ProfileError(f"profile snapshot hash mismatch: {label}")
        try:
            snapshot = json.loads(content.decode("utf-8"))
            ledger = snapshot["ledger"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ProfileError(f"profile snapshot structure is invalid: {label}") from exc
        expected = {
            "schema_version": SCHEMA_VERSION,
            "label": capture["label"],
            "captured_at": capture["captured_at"],
            "due_at": capture["due_at"],
            "actual_elapsed_seconds": capture["actual_elapsed_seconds"],
            "late_by_seconds": capture["late_by_seconds"],
        }
        if not isinstance(snapshot, dict) or any(
            snapshot.get(key) != value for key, value in expected.items()
        ):
            raise ProfileError(f"profile snapshot metadata mismatch: {label}")
        ledger_expected = {
            "head_event_id": capture["head_event_id"],
            "continuity_anchor_sha256": capture["continuity_anchor_sha256"],
            "continuity_basis": capture["continuity_basis"],
            "database_file_identity_sha256": capture[
                "database_file_identity_sha256"
            ],
        }
        if not isinstance(ledger, dict) or any(
            ledger.get(key) != value for key, value in ledger_expected.items()
        ):
            raise ProfileError(f"profile snapshot ledger mismatch: {label}")


def _read_bounded_regular_file(path: Path, maximum_bytes: int) -> bytes:
    try:
        before = path.lstat()
    except OSError as exc:
        raise ProfileError("cannot safely inspect profile evidence file") from exc
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
    ):
        raise ProfileError("profile evidence must be a regular file, not a symlink")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ProfileError("cannot safely open profile snapshot") from exc
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_size > maximum_bytes
        ):
            raise ProfileError("profile snapshot is not a bounded regular file")
        if (before.st_dev, before.st_ino) != (info.st_dev, info.st_ino):
            raise ProfileError("profile evidence changed while it was opened")
        if os.name == "posix":
            if hasattr(os, "geteuid") and info.st_uid != os.geteuid():
                raise ProfileError("profile evidence has a different owner")
            if stat.S_IMODE(info.st_mode) & 0o077:
                raise ProfileError("profile evidence is not private (mode 0600 required)")
        chunks = []
        remaining = maximum_bytes + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if len(content) > maximum_bytes:
            raise ProfileError("profile snapshot exceeds the size limit")
        return content
    finally:
        os.close(descriptor)


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _atomic_write(path: Path, content: bytes) -> None:
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        else:  # Windows exposes chmod(path), not fchmod(fd)
            os.chmod(temporary, 0o600)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        _fsync_directory(path.parent)
    finally:
        if fd >= 0:
            os.close(fd)
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:  # Windows cannot open directories this way
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
