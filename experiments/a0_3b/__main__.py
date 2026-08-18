"""CLI for the repository-local A0.3b shadow/cutover experiment.

Commands that write operate only on marked disposable database copies inside
an explicit disposable root.  The module is experimental evidence only and
writes aggregate, payload-free, absolute-path-free receipts.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path, PureWindowsPath
from typing import Any, Callable

from experiments.a0_3a import harness as a03a
from genus import anchor, db, schema_detection, sealing

from . import harness


DEFAULT_MATRIX_COUNTS = (10_000, 100_000, 1_000_000)
COMMON_FAULT_PHASES = (
    "build_batch_pre_commit",
    "build_batch_post_commit",
    "build_complete",
    "catch_up_batch_opened",
    "catch_up_batch_pre_commit",
    "catch_up_batch_post_commit",
    "catch_up_complete",
    "validation_opened",
    "g3_bounded_purge_opened",
    "g3_bounded_purge_batch_pre_commit",
    "g3_bounded_purge_batch_committed",
    "g3_bounded_purge_complete",
    "g3_second_replay_opened",
    "g3_second_replay_batch_opened",
    "g3_second_replay_batch_pre_commit",
    "g3_second_replay_batch_post_commit",
    "g3_second_replay_complete",
    "validation_digests_computed",
    "validation_pre_commit",
    "validation_post_commit",
    "sync_batch_opened",
    "sync_batch_pre_commit",
    "sync_batch_post_commit",
    "sync_admission_opened",
    "sync_admission_pre_commit",
    "sync_admission_post_commit",
)
A_FAULT_PHASES = (
    *COMMON_FAULT_PHASES,
    "verify_complete",
    "cutover_pointer_changed",
    "cutover_pre_commit",
    "cutover_post_commit",
)
B_FAULT_PHASES = (
    *COMMON_FAULT_PHASES,
    "sync_admission_armed",
    "b_sync_route_exercised",
    "cutover_opened",
    "cutover_head_bound",
    "cutover_pointer_changed",
    "cutover_pre_commit",
    "cutover_post_commit",
    "verify_complete",
)
FAULT_PHASES = A_FAULT_PHASES


def _strict_child(path: Path, root: Path, *, label: str) -> Path:
    resolved_root = root.resolve(strict=True)
    candidate = path.expanduser().absolute()
    try:
        relative = candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise a03a.DisposableTargetError(
            f"{label} must be a strict child of the disposable root"
        ) from exc
    cursor = resolved_root
    for part in relative.parts:
        cursor /= part
        if cursor.is_symlink():
            raise a03a.DisposableTargetError(f"{label} may not traverse a symlink")
    resolved = candidate.resolve()
    if resolved == resolved_root or not resolved.is_relative_to(resolved_root):
        raise a03a.DisposableTargetError(
            f"{label} must be a strict child of the disposable root"
        )
    return resolved


def _root(path: Path) -> Path:
    candidate = path.expanduser().absolute()
    if candidate.is_symlink():
        raise a03a.DisposableTargetError("disposable root may not be a symlink")
    try:
        root = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise a03a.DisposableTargetError(
            "disposable root must already exist"
        ) from exc
    if not root.is_dir():
        raise a03a.DisposableTargetError("disposable root is not a directory")
    a03a._inspect_disposable_location(
        root / ".a0-3b-root-preflight.sqlite3",
        root,
        require_database=False,
    )
    return root


def _output_dir(path: Path, disposable_root: Path) -> tuple[Path, Path]:
    root = _root(disposable_root)
    candidate = path.expanduser().absolute()
    if candidate.is_symlink():
        raise a03a.DisposableTargetError("output directory may not be a symlink")
    if candidate.exists():
        raise FileExistsError("output directory must be fresh")
    output = _strict_child(candidate, root, label="output directory")
    if candidate.parent.resolve(strict=True) != root:
        raise a03a.DisposableTargetError(
            "output directory must be an immediate child of the disposable root"
        )
    a03a._inspect_disposable_location(
        output / ".a0-3b-output-preflight.sqlite3",
        root,
        require_database=False,
    )
    output.mkdir()
    return output, root


def _receipt_target(path: Path, disposable_root: Path) -> tuple[Path, Path]:
    root = _root(disposable_root)
    if path.is_symlink():
        raise a03a.DisposableTargetError("receipt target may not be a symlink")
    target = _strict_child(path, root, label="receipt")
    parent = path.expanduser().absolute().parent.resolve(strict=True)
    if not parent.is_dir() or not parent.is_relative_to(root):
        raise a03a.DisposableTargetError(
            "receipt parent must already exist inside the disposable root"
        )
    if target.exists():
        raise FileExistsError("receipt target must be fresh")
    return target, root


def _copy_fresh_database(source: Path, destination: Path, root: Path) -> Path:
    if source.is_symlink() or not source.is_file():
        raise a03a.DisposableTargetError("database copy source must be a regular file")
    location = a03a._inspect_disposable_location(
        destination,
        root,
        require_database=False,
    )
    target = location.database_path
    marker = a03a.disposable_marker_path(target)
    if target.exists() or marker.exists():
        raise FileExistsError("database copy target and marker must both be fresh")
    with source.open("rb") as input_stream, target.open("xb") as output_stream:
        shutil.copyfileobj(input_stream, output_stream)
    a03a.register_disposable_database(target, root)
    return target


def _without_database_path_notice(operation: Callable[[], Any]) -> Any:
    sink = StringIO()
    with redirect_stdout(sink), redirect_stderr(sink):
        return operation()


def _looks_absolute(value: str) -> bool:
    return Path(value).is_absolute() or PureWindowsPath(value).is_absolute()


def _assert_receipt_safe(value: Any, trail: str = "receipt") -> None:
    if isinstance(value, Path):
        raise ValueError(f"{trail} contains a Path object")
    if isinstance(value, str):
        if _looks_absolute(value):
            raise ValueError(f"{trail} contains an absolute path")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            name = str(key)
            folded = name.casefold()
            if folded in {"payload", "event_payload", "raw_payload"}:
                raise ValueError(f"{trail}.{name} contains an event payload")
            _assert_receipt_safe(item, f"{trail}.{name}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _assert_receipt_safe(item, f"{trail}[{index}]")


def _write_receipt(
    path: Path, disposable_root: Path, receipt: Mapping[str, Any]
) -> Path:
    target, _ = _receipt_target(path, disposable_root)
    _assert_receipt_safe(receipt)
    a03a.write_receipt(target, receipt)
    return target


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain one JSON object")
    return value


def _expected_projection(
    path: Path | None, disposable_root: Path
) -> tuple[dict[str, str] | None, str | None]:
    if path is None:
        return None, None
    root = _root(disposable_root)
    expected_path = _strict_child(path, root, label="expected receipt")
    value = _read_json(expected_path)
    projection = (
        value.get("projections")
        or value.get("active_projection_digests", {}).get("projections")
        or value.get("projection_after")
    )
    if not isinstance(projection, dict):
        raise ValueError("expected receipt has no projection object")
    digests = projection.get("digests")
    digest_set = projection.get("digest_set_sha256")
    if not isinstance(digests, dict) or not isinstance(digest_set, str):
        raise ValueError("expected receipt has no projection digests")
    if set(digests) != set(harness.PROJECTION_TABLES) or not all(
        isinstance(value, str) for value in digests.values()
    ):
        raise ValueError("expected receipt does not bind exactly twelve projections")
    return dict(digests), digest_set


def _assert_expected(
    receipt: Mapping[str, Any],
    expected_digests: Mapping[str, str] | None,
    expected_set: str | None,
) -> None:
    if expected_digests is None and expected_set is None:
        return
    active = receipt.get("active_projection_digests")
    if not isinstance(active, Mapping):
        raise harness.ShadowHarnessError("prototype receipt has no active digests")
    projection = active.get("projections")
    if not isinstance(projection, Mapping):
        raise harness.ShadowHarnessError("prototype receipt has no projection digest set")
    if projection.get("digests") != expected_digests:
        raise harness.ShadowHarnessError("active projection digests differ from the oracle")
    if projection.get("digest_set_sha256") != expected_set:
        raise harness.ShadowHarnessError("active projection digest-set differs from the oracle")


def _run_prototype(
    database: Path,
    *,
    disposable_root: Path,
    batch_events: int,
    batch_bytes: int,
    expected_digests: Mapping[str, str] | None = None,
    expected_set: str | None = None,
) -> dict[str, Any]:
    receipt = harness.run_shadow_prototype(
        database,
        disposable_root=disposable_root,
        batch_events=batch_events,
        batch_bytes=batch_bytes,
    )
    verify = receipt.get("verify")
    verify = verify if isinstance(verify, Mapping) else {}
    cutover = receipt.get("cutover")
    cutover = cutover if isinstance(cutover, Mapping) else {}
    selected_mode = receipt.get("selected_final_sync_mode")
    sync_route_used = receipt.get("sync_route_used")
    final_sync_gate = bool(
        selected_mode == "a_bounded_fence"
        and sync_route_used is False
        and verify.get("selected_final_sync_mode") == "a_bounded_fence"
        and verify.get("sync_route_used") is False
        and cutover.get("selected_final_sync_mode") == "a_bounded_fence"
        and cutover.get("sync_route_used") is False
        and cutover.get("outcome") == "complete_new"
        and cutover.get("committed") is True
    )
    receipt["final_sync_decision"] = {
        "selected_final_sync_mode": selected_mode,
        "decision_reason": verify.get("decision_reason"),
        "fallback_used": sync_route_used is True,
        "fallback_reason": (
            verify.get("decision_reason") if sync_route_used is True else None
        ),
        "gate_pass": final_sync_gate,
    }
    receipt["budgets_pass"] = bool(receipt.get("budgets_pass") and final_sync_gate)
    _assert_expected(receipt, expected_digests, expected_set)
    return receipt


def _cmd_generate(args: argparse.Namespace) -> int:
    root = _root(args.disposable_root)
    database = _strict_child(args.database, root, label="database")
    receipt = _without_database_path_notice(
        lambda: a03a.generate_synthetic_database(
            database,
            a03a.SyntheticSpec(
                event_count=args.events,
                batch_size=args.generation_batch_size,
                payload_bytes=args.payload_bytes,
                seed=args.seed,
            ),
            disposable_root=root,
        )
    )
    target = _write_receipt(args.receipt, root, receipt)
    print(json.dumps({"events": args.events, "receipt": target.name}, sort_keys=True))
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    root = _root(args.disposable_root)
    database = _strict_child(args.database, root, label="database")
    expected_digests, expected_set = _expected_projection(args.expected, root)
    receipt = _run_prototype(
        database,
        disposable_root=root,
        batch_events=args.batch_events,
        batch_bytes=args.batch_bytes,
        expected_digests=expected_digests,
        expected_set=expected_set,
    )
    target = _write_receipt(args.receipt, root, receipt)
    print(
        json.dumps(
            {
                "active_generation_id": receipt["active_generation_id"],
                "budgets_pass": receipt["budgets_pass"],
                "receipt": target.name,
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["budgets_pass"] else 2


def _parse_counts(raw: str) -> tuple[int, ...]:
    try:
        counts = tuple(int(item.strip()) for item in raw.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("counts must be comma-separated integers") from exc
    if not counts or any(item < 0 for item in counts) or len(set(counts)) != len(counts):
        raise argparse.ArgumentTypeError("counts must be unique non-negative integers")
    return counts


def _matrix_case(receipt: Mapping[str, Any], *, events: int, label: str) -> dict[str, Any]:
    build = receipt["build"]
    cutover = receipt["cutover"]
    recovery = receipt["recovery"]
    return {
        "label": label,
        "events": events,
        "build_seconds": build["duration_seconds"],
        "build_transactions": build["batch_count"],
        "max_batch_transaction_seconds": build["max_batch_transaction_seconds"],
        "catch_up_rounds": receipt["catch_up"]["catch_up_rounds"],
        "final_fence_seconds": cutover["final_fence_seconds"],
        "selected_final_sync_mode": receipt["selected_final_sync_mode"],
        "fallback_used": receipt["final_sync_decision"]["fallback_used"],
        "fallback_reason": receipt["final_sync_decision"]["fallback_reason"],
        "overall_max_write_transaction_seconds": receipt["budgets"][
            "all_experimental_write_transactions"
        ]["measured_seconds"],
        "recovery_seconds": recovery["duration_seconds"],
        "peak_rss_bytes": receipt["peak_rss_bytes"],
        "wal_highwater_bytes": receipt["storage_highwater_bytes"]["wal"],
        "ledger_unchanged": receipt["ledger_unchanged"],
        "all_twelve_match": receipt["verify"]["all_twelve_match"],
        "active_generation_id": receipt["active_generation_id"],
        "budgets_pass": receipt["budgets_pass"],
        "receipt": f"{label}-shadow.json",
    }


def _cmd_matrix(args: argparse.Namespace) -> int:
    if os.environ.get("CI", "").casefold() in {"1", "true", "yes"}:
        raise harness.ShadowHarnessError(
            "the 10k/100k/1M measurement matrix is intentionally not a CI job"
        )
    output, root = _output_dir(args.output_dir, args.disposable_root)
    counts = _parse_counts(args.counts)
    cases: list[dict[str, Any]] = []
    for count in counts:
        label = f"synthetic-{count}"
        database = output / f"{label}.sqlite3"
        generation = _without_database_path_notice(
            lambda: a03a.generate_synthetic_database(
                database,
                a03a.SyntheticSpec(
                    event_count=count,
                    batch_size=args.generation_batch_size,
                    payload_bytes=args.payload_bytes,
                    seed=args.seed,
                ),
                disposable_root=root,
            )
        )
        _write_receipt(output / f"{label}-generation.json", root, generation)
        measurement = _run_prototype(
            database,
            disposable_root=root,
            batch_events=args.batch_events,
            batch_bytes=args.batch_bytes,
            expected_digests=generation["projections"]["digests"],
            expected_set=generation["projections"]["digest_set_sha256"],
        )
        _write_receipt(output / f"{label}-shadow.json", root, measurement)
        case = _matrix_case(measurement, events=count, label=label)
        cases.append(case)
        print(json.dumps(case, sort_keys=True), flush=True)
        if not measurement["budgets_pass"]:
            break
    summary = {
        "schema": "genus-a0-3b-local-matrix-v1",
        "counts": list(counts),
        "default_counts": list(DEFAULT_MATRIX_COUNTS),
        "manual_measurement_not_ci": True,
        "batch_events": args.batch_events,
        "batch_bytes": args.batch_bytes,
        "cases": cases,
        "budgets_pass": len(cases) == len(counts)
        and all(case["budgets_pass"] for case in cases),
        "payloads_logged": False,
        "absolute_paths_logged": False,
    }
    _write_receipt(output / "matrix-summary.json", root, summary)
    return 0 if summary["budgets_pass"] else 2


def _cmd_golden(args: argparse.Namespace) -> int:
    from tests import golden_ledger_support as golden

    output, root = _output_dir(args.output_dir, args.disposable_root)
    candidate = golden.load_candidate()
    fixture_before = golden.bundle_bytes_snapshot(candidate)
    conn = _without_database_path_notice(
        lambda: golden.import_fixture(output / "import", candidate)
    )
    database = golden.database_file(conn)
    # Direct fixture import intentionally populates only event_log.  Establish G1
    # with the already accepted bounded A0.3a replay before proving G2/G3.
    conn.execute("BEGIN IMMEDIATE")
    a03a.replay_bounded_in_txn(
        conn, a03a.capture_fence(conn), args.batch_events
    )
    conn.commit()
    conn.close()
    a03a.register_disposable_database(database, root)
    expected = {
        table: candidate.oracle["expected_projections"][table]["sha256"]
        for table in harness.PROJECTION_TABLES
    }
    measurement = _run_prototype(
        database,
        disposable_root=root,
        batch_events=args.batch_events,
        batch_bytes=args.batch_bytes,
        expected_digests=expected,
        expected_set=candidate.oracle["projection_digest_set_sha256"],
    )
    verify = db.connect_readonly(database)
    try:
        seal_issues = sealing.verify_chain(verify)
        anchor_issues = anchor.verify_anchor(
            verify, candidate.anchor, core_id=candidate.anchor["core_id"]
        )
    finally:
        verify.close()
    golden.assert_bundle_unchanged(candidate, fixture_before)
    receipt = {
        "schema": "genus-a0-3b-golden-proof-v1",
        "measurement": measurement,
        "golden": {
            "all_twelve_projection_oracles": True,
            "seal_match": not seal_issues,
            "historical_prefix_anchor_match": not anchor_issues,
            "anchor_scope": "historical-prefix",
            "anchor_issue_count": len(anchor_issues),
            "fixture_unchanged": True,
        },
        "payloads_logged": False,
        "absolute_paths_logged": False,
    }
    target = _write_receipt(output / "golden-shadow.json", root, receipt)
    passed = not seal_issues and not anchor_issues and measurement["budgets_pass"]
    print(json.dumps({"pass": passed, "receipt": target.name}, sort_keys=True))
    return 0 if passed else 2


def _cmd_historical(args: argparse.Namespace) -> int:
    from tests import historical_sqlite_support as historical

    output, root = _output_dir(args.output_dir, args.disposable_root)
    source = output / "historical-copy.sqlite3"
    current = output / "historical-rehydrated-current.sqlite3"
    source = _copy_fresh_database(historical.DATABASE_PATH, source, root)
    before = a03a.file_snapshot(source)
    ro = db.connect_readonly(source)
    try:
        detected = schema_detection.detect_schema(ro)
    finally:
        ro.close()
    if (
        detected.status != "historical"
        or detected.schema_id != "historical-v1.1"
        or detected.fingerprint
        != schema_detection.HISTORICAL_V1_1_SCHEMA_FINGERPRINT
    ):
        raise harness.ShadowHarnessError(
            "historical fixture was not recognized by its exact pinned fingerprint"
        )
    rehydration = _without_database_path_notice(
        lambda: a03a.rehydrate_historical_copy(
            source,
            current,
            disposable_root=root,
            batch_size=args.batch_events,
        )
    )
    after = a03a.file_snapshot(source)
    if before != after:
        raise harness.ShadowHarnessError("historical copy changed during rehydration")
    current_ro = db.connect_readonly(current)
    try:
        current_detected = schema_detection.detect_schema(current_ro)
    finally:
        current_ro.close()
    if (
        current_detected.status != "current"
        or current_detected.schema_id != "current"
        or current_detected.fingerprint != schema_detection.CURRENT_SCHEMA_FINGERPRINT
    ):
        raise harness.ShadowHarnessError(
            "rehydrated copy was not recognized by the exact Current fingerprint"
        )
    measurement = _run_prototype(
        current,
        disposable_root=root,
        batch_events=args.batch_events,
        batch_bytes=args.batch_bytes,
    )
    receipt = {
        "schema": "genus-a0-3b-historical-proof-v1",
        "schema_status": detected.status,
        "recognized_as": detected.schema_id,
        "schema_fingerprint": detected.fingerprint,
        "historical_detection_pass": True,
        "source_unchanged": True,
        "rehydrated_schema_status": current_detected.status,
        "rehydrated_schema_id": current_detected.schema_id,
        "rehydrated_schema_fingerprint": current_detected.fingerprint,
        "rehydration": rehydration,
        "measurement": measurement,
        "migration_claimed": False,
        "payloads_logged": False,
        "absolute_paths_logged": False,
    }
    target = _write_receipt(output / "historical-shadow.json", root, receipt)
    print(
        json.dumps(
            {
                "recognized_as": detected.schema_id,
                "budgets_pass": measurement["budgets_pass"],
                "receipt": target.name,
            },
            sort_keys=True,
        )
    )
    return 0 if measurement["budgets_pass"] else 2


def _cmd_concurrency(args: argparse.Namespace) -> int:
    output, root = _output_dir(args.output_dir, args.disposable_root)
    database = output / "concurrency.sqlite3"
    generation = _without_database_path_notice(
        lambda: a03a.generate_synthetic_database(
            database,
            a03a.SyntheticSpec(
                event_count=args.events,
                batch_size=args.generation_batch_size,
                payload_bytes=args.payload_bytes,
                seed=args.seed,
            ),
            disposable_root=root,
        )
    )
    _write_receipt(output / "concurrency-generation.json", root, generation)
    harness.initialize_shadow(database, disposable_root=root)
    receipt = harness.run_concurrency_probe(
        database,
        disposable_root=root,
        writer_interval_seconds=args.writer_interval,
        batch_events=args.batch_events,
        batch_bytes=args.batch_bytes,
        short_reader_interval_seconds=args.reader_interval,
    )
    latency = receipt["writer_latency"]
    reader = receipt["reader"]
    verify = receipt.get("verify")
    verify = verify if isinstance(verify, Mapping) else {}
    admission = verify.get("sync_admission")
    admission = admission if isinstance(admission, Mapping) else {}
    cutover = receipt["cutover"]
    phase_latency = receipt.get("writer_latency_by_phase")
    phase_latency = phase_latency if isinstance(phase_latency, Mapping) else {}
    phase_overhead = receipt.get("writer_phase_overhead")
    phase_overhead = phase_overhead if isinstance(phase_overhead, Mapping) else {}
    verify_write_max = verify.get("write_transaction_max_seconds")
    verify_write_max = (
        verify_write_max if isinstance(verify_write_max, Mapping) else {}
    )

    phase_write_max: dict[str, float | None] = {
        "build": receipt["build"].get("max_write_transaction_seconds"),
        "catch_up": receipt["catch_up"].get("max_write_transaction_seconds"),
        "verify_and_sync": verify_write_max.get("overall"),
        "sync_admission_fence": admission.get("fence_seconds"),
        "cutover_fence": cutover.get("final_fence_seconds"),
        # End-to-end writer latency includes its lock wait, so it is a stricter
        # upper bound than the writer transaction duration itself.
        "observed_routed_writer_end_to_end": latency.get("max_seconds"),
    }
    numeric_write_max = [
        float(value) for value in phase_write_max.values() if value is not None
    ]
    write_evidence_complete = all(
        value is not None for value in phase_write_max.values()
    )
    overall_write_max = max(numeric_write_max, default=None)
    write_transaction_gate = {
        "limit_seconds": harness.WRITER_BLOCK_BUDGET_SECONDS,
        "phase_max_seconds": phase_write_max,
        "overall_max_seconds": overall_write_max,
        "evidence_complete": write_evidence_complete,
        "pass": bool(
            write_evidence_complete
            and overall_write_max is not None
            and overall_write_max <= harness.WRITER_BLOCK_BUDGET_SECONDS
            and verify_write_max.get("pass") is True
        ),
    }
    receipt["all_experimental_write_transactions"] = write_transaction_gate

    g1_phase = phase_latency.get("g1_only")
    g2_phase = phase_latency.get("g2_only")
    triple_phase = phase_latency.get("sync_triple")
    phase_evidence_complete = bool(
        isinstance(g1_phase, Mapping)
        and isinstance(g2_phase, Mapping)
        and isinstance(triple_phase, Mapping)
        and int(g1_phase.get("committed_count", 0)) > 0
        and int(g2_phase.get("committed_count", 0)) > 0
        and int(triple_phase.get("committed_count", 0)) == 0
        and "sync_minus_g1_p50_seconds" in phase_overhead
        and "sync_over_g1_p50_ratio" in phase_overhead
    )
    receipt["writer_phase_evidence_complete"] = phase_evidence_complete
    receipt["final_sync_decision"] = {
        "selected_final_sync_mode": verify.get("selected_final_sync_mode"),
        "decision_reason": admission.get("decision_reason"),
        "fallback_used": False,
        "fallback_reason": None,
        "sync_route_used": verify.get("sync_route_used"),
    }
    receipt["budgets_pass"] = bool(
        receipt.get("concurrency_gate_pass") is True
        and receipt.get("writer_evidence_complete") is True
        and latency["sample_count"] > 0
        and latency["committed_count"] > 0
        and latency["total_sample_count"] == latency["sample_count"]
        and latency["samples_truncated"] is False
        and latency["dropped_sample_count"] == 0
        and latency["timeouts"] == 0
        and latency["errors"] == 0
        and not latency["starvation"]
        and latency["within_max_block_budget"]
        and latency["observed_attempt_rate_per_second"] is not None
        and latency["observed_attempt_rate_per_second"] > 0
        and latency["committed_arrival_rate_per_second"] is not None
        and latency["committed_arrival_rate_per_second"] > 0
        and reader["short_transaction_count"] > 0
        and reader.get("evidence_complete") is True
        and reader["samples_truncated"] is False
        and reader["failure_count"] == 0
        and reader["failure_samples_truncated"] is False
        and reader["reader_thread_alive_after_join"] is False
        and reader["writer_thread_alive_after_join"] is False
        and reader["coherent_old_or_new_only"]
        and phase_evidence_complete
        and receipt["peak_rss_bytes"] <= harness.RSS_BUDGET_BYTES
        and receipt["storage_highwater_bytes"]["wal"] <= harness.WAL_BUDGET_BYTES
        and verify.get("selected_final_sync_mode") == "a_bounded_fence"
        and verify.get("sync_route_used") is False
        and admission.get("selected_final_sync_mode") == "a_bounded_fence"
        and admission.get("sync_route_used") is False
        and admission.get("committed") is True
        and admission.get("within_writer_block_budget") is True
        and cutover.get("selected_final_sync_mode") == "a_bounded_fence"
        and cutover.get("sync_route_used") is False
        and cutover.get("outcome") == "complete_new"
        and cutover.get("committed") is True
        and cutover.get("within_writer_block_budget") is True
        and write_transaction_gate["pass"]
    )
    target = _write_receipt(output / "concurrency.json", root, receipt)
    print(
        json.dumps(
            {
                "budgets_pass": receipt["budgets_pass"],
                "writer_samples": latency["sample_count"],
                "receipt": target.name,
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["budgets_pass"] else 2


def _atomic_phase(directory: Path, phase: str, fields: Mapping[str, Any]) -> None:
    safe_fields = {
        key: value
        for key, value in fields.items()
        if isinstance(value, (bool, int, float, type(None)))
    }
    value = {"phase": phase, "metrics": safe_fields}
    _assert_receipt_safe(value)
    target = directory / f"phase-{phase}.json"
    temporary = directory / f"phase-{phase}.tmp"
    temporary.write_text(
        json.dumps(value, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(target)


def _phase_callback(
    directory: Path,
    *,
    stage: str,
    wait_phase: str | None,
    fault_phase: str | None,
    wait_timeout: float,
) -> Callable[[str, Mapping[str, Any]], None]:
    def callback(phase: str, fields: Mapping[str, Any]) -> None:
        # Harness phases that already name their lifecycle are globally unique;
        # only generic batch phases receive the caller's stage prefix.
        external = (
            phase
            if phase.startswith(
                ("catch_up_", "validation_", "g3_", "sync_", "cutover_")
            )
            else f"{stage}_{phase}"
        )
        _atomic_phase(directory, external, fields)
        if external == fault_phase:
            raise harness.InjectedFault(f"injected at {external}")
        if external == wait_phase:
            release = directory / f"release-{external}"
            deadline = time.monotonic() + wait_timeout
            while not release.exists():
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"release barrier for {external} timed out")
                time.sleep(0.01)

    return callback


def _worker_phase(
    directory: Path,
    phase: str,
    *,
    wait_phase: str | None,
    fault_phase: str | None,
    wait_timeout: float,
) -> None:
    _atomic_phase(directory, phase, {})
    if phase == fault_phase:
        raise harness.InjectedFault(f"injected at {phase}")
    if phase == wait_phase:
        release = directory / f"release-{phase}"
        deadline = time.monotonic() + wait_timeout
        while not release.exists():
            if time.monotonic() >= deadline:
                raise TimeoutError(f"release barrier for {phase} timed out")
            time.sleep(0.01)


def _cmd_worker(args: argparse.Namespace) -> int:
    root = _root(args.disposable_root)
    database = _strict_child(args.database, root, label="database")
    control = _strict_child(args.control_dir, root, label="control directory")
    control.mkdir(parents=True, exist_ok=True)
    try:
        initialized = harness.initialize_shadow(database, disposable_root=root)
        _worker_phase(
            control,
            "initialized",
            wait_phase=args.wait_phase,
            fault_phase=args.fault_phase,
            wait_timeout=args.wait_timeout,
        )
        build = harness.build_shadow(
            database,
            disposable_root=root,
            batch_events=args.batch_events,
            batch_bytes=args.batch_bytes,
            fault=_phase_callback(
                control,
                stage="build",
                wait_phase=args.wait_phase,
                fault_phase=args.fault_phase,
                wait_timeout=args.wait_timeout,
            ),
        )
        _worker_phase(
            control,
            "build_complete",
            wait_phase=args.wait_phase,
            fault_phase=args.fault_phase,
            wait_timeout=args.wait_timeout,
        )
        for sequence in range(args.between_stage_events):
            harness.append_routed(
                database,
                "assertion_recorded",
                {
                    "claim_key": f"a0.3b.worker.{sequence}",
                    "claim_value": sequence,
                    "source": "experiment:a0_3b",
                    "derivation": "experiment:a0_3b:worker:v1",
                },
                disposable_root=root,
            )
        catchup = harness.catch_up_shadow(
            database,
            disposable_root=root,
            batch_events=args.batch_events,
            batch_bytes=args.batch_bytes,
            fault=_phase_callback(
                control,
                stage="catch_up",
                wait_phase=args.wait_phase,
                fault_phase=args.fault_phase,
                wait_timeout=args.wait_timeout,
            ),
        )
        _worker_phase(
            control,
            "catch_up_complete",
            wait_phase=args.wait_phase,
            fault_phase=args.fault_phase,
            wait_timeout=args.wait_timeout,
        )
        verify_phase_callback = _phase_callback(
            control,
            stage="verify",
            wait_phase=args.wait_phase,
            fault_phase=args.fault_phase,
            wait_timeout=args.wait_timeout,
        )
        sync_tail_injected = False

        def verify_fault_callback(
            phase: str, fields: Mapping[str, Any]
        ) -> None:
            nonlocal sync_tail_injected
            verify_phase_callback(phase, fields)
            if phase == "validation_opened" and not sync_tail_injected:
                # W is already captured.  One routed post-W event makes the
                # paired sync-preparation crash boundaries deterministic.
                harness.append_routed(
                    database,
                    "assertion_recorded",
                    {
                        "claim_key": "a0.3b.worker.sync-tail",
                        "claim_value": 1,
                        "source": "experiment:a0_3b",
                        "derivation": "experiment:a0_3b:worker-sync-tail:v1",
                    },
                    disposable_root=root,
                )
                sync_tail_injected = True

        selected_mode = args.final_sync_mode
        verify = harness.verify_shadow(
            database,
            disposable_root=root,
            batch_events=args.batch_events,
            batch_bytes=args.batch_bytes,
            require_active_match=True,
            atomic_cutover=selected_mode == "a",
            fault=verify_fault_callback,
        )
        if selected_mode == "a":
            cutover = verify.get("cutover")
            if (
                verify.get("selected_final_sync_mode") != "a_bounded_fence"
                or verify.get("sync_route_used") is not False
                or not isinstance(cutover, Mapping)
                or cutover.get("outcome") != "complete_new"
                or cutover.get("committed") is not True
            ):
                raise harness.CutoverNotReady(
                    "A bounded-fence verification did not complete the cutover"
                )
        else:
            admission = verify.get("sync_admission")
            if (
                verify.get("selected_final_sync_mode") != "b_routed_sync"
                or verify.get("sync_route_used") is not True
                or not isinstance(admission, Mapping)
                or admission.get("outcome") != "sync_armed"
                or admission.get("committed") is not True
            ):
                raise harness.CutoverNotReady(
                    "explicit B experiment did not arm routed synchronization"
                )
            routed = harness.append_routed(
                database,
                "assertion_recorded",
                {
                    "claim_key": "a0.3b.worker.b-sync-route",
                    "claim_value": 1,
                    "source": "experiment:a0_3b",
                    "derivation": "experiment:a0_3b:worker-b-sync-route:v1",
                },
                disposable_root=root,
            )
            if routed.get("routed_generation_count") != 3:
                raise harness.ShadowHarnessError(
                    "B experiment did not observe one routed triple-write"
                )
            _worker_phase(
                control,
                "b_sync_route_exercised",
                wait_phase=args.wait_phase,
                fault_phase=args.fault_phase,
                wait_timeout=args.wait_timeout,
            )
            cutover = harness.cutover_shadow(
                database,
                disposable_root=root,
                fault=_phase_callback(
                    control,
                    stage="cutover",
                    wait_phase=args.wait_phase,
                    fault_phase=args.fault_phase,
                    wait_timeout=args.wait_timeout,
                ),
            )
            if (
                cutover.get("selected_final_sync_mode") != "b_routed_sync"
                or cutover.get("sync_route_used") is not True
                or cutover.get("outcome") != "complete_new"
                or cutover.get("committed") is not True
            ):
                raise harness.CutoverNotReady(
                    "explicit B routed-sync experiment did not complete cutover"
                )
        _worker_phase(
            control,
            "verify_complete",
            wait_phase=args.wait_phase,
            fault_phase=args.fault_phase,
            wait_timeout=args.wait_timeout,
        )
        recovery = harness.recover(database, disposable_root=root)
        receipt = {
            "schema": harness.RECEIPT_SCHEMA,
            "operation": "worker_pipeline",
            "selected_final_sync_mode": verify["selected_final_sync_mode"],
            "initialized": initialized,
            "build": build,
            "catch_up": catchup,
            "verify": verify,
            "cutover": cutover,
            "recovery": recovery,
            "payloads_logged": False,
            "absolute_paths_logged": False,
        }
        _write_receipt(args.receipt, root, receipt)
        return 0
    except BaseException as exc:
        try:
            recovery = harness.recover(database, disposable_root=root)
        except BaseException as recovery_exc:
            recovery = {"error_type": type(recovery_exc).__name__}
        receipt = {
            "schema": harness.RECEIPT_SCHEMA,
            "operation": "worker_pipeline",
            "outcome": "error",
            "error_type": type(exc).__name__,
            "recovery": recovery,
            "payloads_logged": False,
            "absolute_paths_logged": False,
        }
        _write_receipt(args.receipt, root, receipt)
        return 2


def _wait_for(path: Path, process: subprocess.Popen[bytes], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while not path.exists():
        returncode = process.poll()
        if returncode is not None:
            raise ChildProcessError(
                f"fault worker exited with status {returncode} before {path.name}"
            )
        if time.monotonic() >= deadline:
            raise TimeoutError(f"phase {path.name} did not arrive")
        time.sleep(0.01)


def _kill_and_reap(process: subprocess.Popen[bytes], timeout: float) -> None:
    if process.poll() is None:
        process.kill()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout)


def _fault_classification(recovery: Mapping[str, Any]) -> str:
    if not (
        recovery.get("extended_schema_valid") is True
        and recovery.get("reader_ready") is True
        and recovery.get("writer_ready") is True
        and recovery.get("within_recovery_budget") is True
        and recovery.get("retryable_now") is True
    ):
        return "invalid"
    classification = str(recovery["classification"])
    active = recovery.get("active_generation_id")
    if classification.startswith("OLD_ACTIVE_") and active == "g1":
        return "complete_old"
    if classification == "NEW_ACTIVE_OLD_RETIRED" and active == "g2":
        return "complete_new"
    return "invalid"


def _retry_complete_old_to_new(
    database: Path,
    *,
    disposable_root: Path,
    initial_recovery: Mapping[str, Any],
    batch_events: int,
    batch_bytes: int,
    final_sync_mode: str,
    max_attempts: int = 5,
) -> dict[str, Any]:
    recovery = dict(initial_recovery)
    steps: list[dict[str, Any]] = []
    started = time.perf_counter_ns()
    selected_mode_id = (
        "a_bounded_fence" if final_sync_mode == "a" else "b_routed_sync"
    )
    for attempt in range(1, max_attempts + 1):
        initial_outcome = _fault_classification(recovery)
        if initial_outcome == "complete_new":
            return {
                "required": True,
                "selected_final_sync_mode": selected_mode_id,
                "attempted": bool(steps),
                "pass": bool(steps),
                "attempt_count": len(steps),
                "steps": steps,
                "final_recovery_classification": recovery["classification"],
                "duration_seconds": (
                    time.perf_counter_ns() - started
                )
                / 1_000_000_000,
            }
        if initial_outcome != "complete_old":
            break
        classification = str(recovery["classification"])
        try:
            if classification == "OLD_ACTIVE_SYNC_ARMED":
                operation = "cutover_retry"
                operation_receipt = harness.cutover_shadow(
                    database,
                    disposable_root=disposable_root,
                )
            else:
                operation = f"verify_sync_cutover_retry_{final_sync_mode}"
                verification = harness.verify_shadow(
                    database,
                    disposable_root=disposable_root,
                    batch_events=batch_events,
                    batch_bytes=batch_bytes,
                    require_active_match=True,
                    atomic_cutover=final_sync_mode == "a",
                )
                operation_receipt = verification.get("cutover")
                if final_sync_mode == "b":
                    admission = verification.get("sync_admission")
                    if (
                        not isinstance(admission, Mapping)
                        or admission.get("outcome") != "sync_armed"
                        or admission.get("committed") is not True
                    ):
                        raise harness.CutoverNotReady(
                            "B retry did not arm routed synchronization"
                        )
                    routed = harness.append_routed(
                        database,
                        "assertion_recorded",
                        {
                            "claim_key": f"a0.3b.retry.b-sync-route.{attempt}",
                            "claim_value": attempt,
                            "source": "experiment:a0_3b",
                            "derivation": "experiment:a0_3b:retry-b-sync-route:v1",
                        },
                        disposable_root=disposable_root,
                    )
                    if routed.get("routed_generation_count") != 3:
                        raise harness.ShadowHarnessError(
                            "B retry did not exercise routed triple-write"
                        )
                    operation_receipt = harness.cutover_shadow(
                        database,
                        disposable_root=disposable_root,
                    )
                if not isinstance(operation_receipt, Mapping):
                    operation_receipt = {
                        "outcome": "sync_not_committed",
                        "committed": False,
                    }
            step: dict[str, Any] = {
                "attempt": attempt,
                "operation": operation,
                "operation_outcome": operation_receipt.get("outcome"),
                "operation_committed": operation_receipt.get("committed") is True,
            }
        except BaseException as exc:
            step = {
                "attempt": attempt,
                "operation": (
                    "cutover_retry"
                    if classification == "OLD_ACTIVE_SYNC_ARMED"
                    else f"verify_sync_cutover_retry_{final_sync_mode}"
                ),
                "operation_outcome": "error",
                "operation_committed": False,
                "error_type": type(exc).__name__,
            }
        recovery = harness.recover(database, disposable_root=disposable_root)
        step["recovery_classification"] = recovery["classification"]
        steps.append(step)
    return {
        "required": True,
        "selected_final_sync_mode": selected_mode_id,
        "attempted": bool(steps),
        "pass": False,
        "attempt_count": len(steps),
        "steps": steps,
        "final_recovery_classification": recovery.get("classification"),
        "duration_seconds": (time.perf_counter_ns() - started) / 1_000_000_000,
    }


def _cmd_faults(args: argparse.Namespace) -> int:
    output, root = _output_dir(args.output_dir, args.disposable_root)
    allowed_phases = A_FAULT_PHASES if args.final_sync_mode == "a" else B_FAULT_PHASES
    selected_mode_id = (
        "a_bounded_fence" if args.final_sync_mode == "a" else "b_routed_sync"
    )
    raw_phases = args.phases or ",".join(allowed_phases)
    phases = tuple(phase.strip() for phase in raw_phases.split(","))
    if not phases or any(not phase for phase in phases) or len(set(phases)) != len(phases):
        raise ValueError("fault phases must be a unique, non-empty list")
    for phase in phases:
        if phase not in allowed_phases:
            raise ValueError(
                f"unsupported {args.final_sync_mode.upper()} fault phase: {phase}"
            )
    base = output / "fault-base.sqlite3"
    generation = _without_database_path_notice(
        lambda: a03a.generate_synthetic_database(
            base,
            a03a.SyntheticSpec(
                event_count=args.events,
                batch_size=args.generation_batch_size,
                payload_bytes=args.payload_bytes,
                seed=args.seed,
            ),
            disposable_root=root,
        )
    )
    _write_receipt(output / "fault-generation.json", root, generation)
    results: list[dict[str, Any]] = []
    repo_root = Path(__file__).resolve().parents[2]
    for phase in phases:
        database = output / f"fault-{phase}.sqlite3"
        control = output / f"control-{phase}"
        worker_receipt = output / f"worker-{phase}.json"
        if any(path.exists() for path in (database, control, worker_receipt)):
            raise FileExistsError(
                f"fault control artifacts already exist for phase {phase}"
            )
        database = _copy_fresh_database(base, database, root)
        process = subprocess.Popen(
            [
                sys.executable,
                "-B",
                "-m",
                "experiments.a0_3b",
                "_worker",
                str(database),
                "--disposable-root",
                str(root),
                "--receipt",
                str(worker_receipt),
                "--control-dir",
                str(control),
                "--wait-phase",
                phase,
                "--wait-timeout",
                str(args.phase_timeout),
                "--between-stage-events",
                str(args.between_stage_events),
                "--final-sync-mode",
                args.final_sync_mode,
                "--batch-events",
                str(args.batch_events),
                "--batch-bytes",
                str(args.batch_bytes),
            ],
            cwd=repo_root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        killed_at: int | None = None
        try:
            _wait_for(
                control / f"phase-{phase}.json", process, args.phase_timeout
            )
            killed_at = time.perf_counter_ns()
        finally:
            _kill_and_reap(process, args.phase_timeout)
        if killed_at is None:
            raise harness.ShadowHarnessError(
                f"fault worker did not reach phase {phase}"
            )
        recovery = harness.recover(database, disposable_root=root)
        recovery_seconds = (time.perf_counter_ns() - killed_at) / 1_000_000_000
        outcome = _fault_classification(recovery)
        if outcome == "complete_old":
            retry = _retry_complete_old_to_new(
                database,
                disposable_root=root,
                initial_recovery=recovery,
                batch_events=args.batch_events,
                batch_bytes=args.batch_bytes,
                final_sync_mode=args.final_sync_mode,
            )
        elif outcome == "complete_new":
            retry = {
                "required": False,
                "selected_final_sync_mode": selected_mode_id,
                "attempted": False,
                "pass": True,
                "attempt_count": 0,
                "steps": [],
                "final_recovery_classification": recovery["classification"],
                "duration_seconds": 0.0,
            }
        else:
            retry = {
                "required": False,
                "selected_final_sync_mode": selected_mode_id,
                "attempted": False,
                "pass": False,
                "attempt_count": 0,
                "steps": [],
                "final_recovery_classification": recovery.get("classification"),
                "duration_seconds": 0.0,
            }
        final_recovery = harness.recover(database, disposable_root=root)
        final_outcome = _fault_classification(final_recovery)
        complete_new_reopen_pass = bool(
            retry["pass"] and final_outcome == "complete_new"
        )
        result = {
            "phase": phase,
            "selected_final_sync_mode": selected_mode_id,
            "outcome": outcome,
            "recovery_classification": recovery["classification"],
            "recovery_seconds": recovery_seconds,
            "within_recovery_budget": recovery_seconds <= harness.RECOVERY_BUDGET_SECONDS,
            "old_or_new_only": outcome in {"complete_old", "complete_new"},
            "retry_to_complete_new": retry,
            "retry_pass": retry["pass"],
            "final_recovery_classification": final_recovery["classification"],
            "complete_new_reopen_pass": complete_new_reopen_pass,
        }
        results.append(result)
        print(json.dumps(result, sort_keys=True), flush=True)
    receipt = {
        "schema": "genus-a0-3b-fault-matrix-v1",
        "selected_final_sync_mode": selected_mode_id,
        "sync_route_experiment": args.final_sync_mode == "b",
        "phases": list(phases),
        "results": results,
        "crash_reopen_old_or_new_only": all(item["old_or_new_only"] for item in results),
        "recovery_budget_pass": all(item["within_recovery_budget"] for item in results),
        "complete_old_retry_pass": all(item["retry_pass"] for item in results),
        "complete_new_reopen_pass": all(
            item["complete_new_reopen_pass"] for item in results
        ),
        "literal_power_loss_claimed": False,
        "payloads_logged": False,
        "absolute_paths_logged": False,
    }
    target = _write_receipt(output / "fault-matrix.json", root, receipt)
    passed = bool(
        receipt["crash_reopen_old_or_new_only"]
        and receipt["recovery_budget_pass"]
        and receipt["complete_old_retry_pass"]
        and receipt["complete_new_reopen_pass"]
    )
    print(json.dumps({"pass": passed, "receipt": target.name}, sort_keys=True))
    return 0 if passed else 2


def _cmd_recover(args: argparse.Namespace) -> int:
    root = _root(args.disposable_root)
    database = _strict_child(args.database, root, label="database")
    receipt = harness.recover(
        database,
        disposable_root=root,
        timeout_seconds=args.timeout,
    )
    target = _write_receipt(args.receipt, root, receipt)
    valid = _fault_classification(receipt) in {"complete_old", "complete_new"}
    print(
        json.dumps(
            {
                "classification": receipt["classification"],
                "valid": valid,
                "receipt": target.name,
            },
            sort_keys=True,
        )
    )
    return 0 if valid and receipt["within_recovery_budget"] else 2


def _add_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--disposable-root",
        type=Path,
        required=True,
        help="explicit non-product root containing every writable artifact",
    )


def _add_batch_caps(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--batch-events", type=int, default=harness.DEFAULT_BATCH_EVENTS)
    parser.add_argument("--batch-bytes", type=int, default=harness.DEFAULT_BATCH_BYTES)


def _add_synthetic(parser: argparse.ArgumentParser, *, events: int | None) -> None:
    if events is None:
        parser.add_argument("--events", type=int, required=True)
    else:
        parser.add_argument("--events", type=int, default=events)
    parser.add_argument("--generation-batch-size", type=int, default=1024)
    parser.add_argument("--payload-bytes", type=int, default=256)
    parser.add_argument("--seed", type=int, default=3)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    generate = sub.add_parser("generate", help="create one marked synthetic Current DB")
    generate.add_argument("database", type=Path)
    _add_root(generate)
    _add_synthetic(generate, events=None)
    generate.add_argument("--receipt", type=Path, required=True)
    generate.set_defaults(func=_cmd_generate)

    run = sub.add_parser("run", help="run the writer-free shadow/cutover proof")
    run.add_argument("database", type=Path)
    _add_root(run)
    _add_batch_caps(run)
    run.add_argument("--expected", type=Path)
    run.add_argument("--receipt", type=Path, required=True)
    run.set_defaults(func=_cmd_run)

    matrix = sub.add_parser(
        "matrix", help="manual 10k/100k/1M matrix; deliberately refused in CI"
    )
    matrix.add_argument("output_dir", type=Path)
    _add_root(matrix)
    _add_batch_caps(matrix)
    matrix.add_argument("--generation-batch-size", type=int, default=1024)
    matrix.add_argument("--payload-bytes", type=int, default=256)
    matrix.add_argument("--seed", type=int, default=3)
    matrix.add_argument(
        "--counts",
        default=",".join(str(item) for item in DEFAULT_MATRIX_COUNTS),
        help="comma-separated event counts (default: 10000,100000,1000000)",
    )
    matrix.set_defaults(func=_cmd_matrix)

    golden = sub.add_parser("golden", help="run against an imported Golden Ledger")
    golden.add_argument("output_dir", type=Path)
    _add_root(golden)
    _add_batch_caps(golden)
    golden.set_defaults(func=_cmd_golden)

    historical = sub.add_parser(
        "historical", help="rehydrate and test a copy of historical-v1.1"
    )
    historical.add_argument("output_dir", type=Path)
    _add_root(historical)
    _add_batch_caps(historical)
    historical.set_defaults(func=_cmd_historical)

    concurrency = sub.add_parser(
        "concurrency", help="run writer, long/short readers and shadow work together"
    )
    concurrency.add_argument("output_dir", type=Path)
    _add_root(concurrency)
    _add_batch_caps(concurrency)
    _add_synthetic(concurrency, events=10_000)
    concurrency.add_argument("--writer-interval", type=float, default=0.005)
    concurrency.add_argument("--reader-interval", type=float, default=0.003)
    concurrency.set_defaults(func=_cmd_concurrency)

    faults = sub.add_parser("faults", help="kill/reopen matrix at named worker phases")
    faults.add_argument("output_dir", type=Path)
    _add_root(faults)
    _add_batch_caps(faults)
    _add_synthetic(faults, events=10_000)
    faults.add_argument(
        "--phases",
        help="comma-separated phases; defaults to the selected A or B matrix",
    )
    faults.add_argument(
        "--final-sync-mode",
        choices=("a", "b"),
        default="a",
        help="A bounded-fence candidate (default) or explicit B routed-sync experiment",
    )
    faults.add_argument("--phase-timeout", type=float, default=30.0)
    faults.add_argument("--between-stage-events", type=int, default=3)
    faults.set_defaults(func=_cmd_faults)

    recover = sub.add_parser("recover", help="classify one reopened A0.3b database")
    recover.add_argument("database", type=Path)
    _add_root(recover)
    recover.add_argument("--timeout", type=float, default=5.0)
    recover.add_argument("--receipt", type=Path, required=True)
    recover.set_defaults(func=_cmd_recover)

    worker = sub.add_parser("_worker", help=argparse.SUPPRESS)
    worker.add_argument("database", type=Path)
    _add_root(worker)
    _add_batch_caps(worker)
    worker.add_argument("--receipt", type=Path, required=True)
    worker.add_argument("--control-dir", type=Path, required=True)
    worker.add_argument("--wait-phase")
    worker.add_argument("--fault-phase")
    worker.add_argument("--wait-timeout", type=float, default=30.0)
    worker.add_argument("--between-stage-events", type=int, default=3)
    worker.add_argument("--final-sync-mode", choices=("a", "b"), default="a")
    worker.set_defaults(func=_cmd_worker)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as exc:
        print(
            json.dumps(
                {"outcome": "error", "error_type": type(exc).__name__},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
