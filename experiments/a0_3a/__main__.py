"""Command line entry point for the repository-local A0.3a experiment."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping

from genus import anchor, db, ledger, sealing

from . import harness


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain one JSON object")
    return value


def _expected(receipt_path: Path | None) -> tuple[Mapping[str, str] | None, str | None]:
    if receipt_path is None:
        return None, None
    value = _read_json(receipt_path)
    projection = value.get("projections") or value.get("projection_after")
    if not isinstance(projection, dict):
        raise ValueError("expected receipt has no projection object")
    digests = projection.get("digests")
    digest_set = projection.get("digest_set_sha256")
    if not isinstance(digests, dict) or not isinstance(digest_set, str):
        raise ValueError("expected receipt has no projection digests")
    return digests, digest_set


def _atomic_phase(directory: Path, phase: str, fields: Mapping[str, Any]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    allowed = {
        key: value
        for key, value in fields.items()
        if key in {"processed", "fixed_head", "event_count", "head_id"}
        and isinstance(value, (int, type(None)))
    }
    target = directory / f"phase-{phase}.json"
    temporary = directory / f"phase-{phase}.tmp"
    temporary.write_text(
        json.dumps({"phase": phase, "metrics": allowed}, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(target)


def _phase_callback(
    directory: Path,
    wait_phase: str | None,
    wait_timeout: float,
):
    mid_replay_emitted = False

    def callback(phase: str, fields: Mapping[str, Any]) -> None:
        nonlocal mid_replay_emitted
        emitted = phase
        if phase == "batch_complete" and not mid_replay_emitted:
            emitted = "mid_replay"
            mid_replay_emitted = True
        _atomic_phase(directory, emitted, fields)
        if emitted == wait_phase:
            release = directory / f"release-{emitted}"
            deadline = time.monotonic() + wait_timeout
            while not release.exists():
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"release barrier for {emitted} timed out")
                time.sleep(0.01)

    return callback


def _cmd_generate(args: argparse.Namespace) -> int:
    receipt = harness.generate_synthetic_database(
        args.database,
        harness.SyntheticSpec(
            event_count=args.events,
            batch_size=args.batch_size,
            payload_bytes=args.payload_bytes,
            seed=args.seed,
        ),
        disposable_root=args.disposable_root,
    )
    harness.write_receipt(args.receipt, receipt)
    print(json.dumps({"events": args.events, "receipt": Path(args.receipt).name}))
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    digests, digest_set = _expected(args.expected)
    receipt = harness.run_option_b(
        args.database,
        disposable_root=args.disposable_root,
        batch_size=args.batch_size,
        expected_projection_digests=digests,
        expected_projection_set_sha256=digest_set,
        timeout_seconds=args.timeout,
        sample_interval_seconds=args.sample_interval,
    )
    receipt["concurrency"] = {
        "reader_old_or_new_only": None,
        "writer_block_seconds": None,
        "writer_timeout": None,
        "state": "not_run",
    }
    receipt["fault_injection"] = {
        "kill_phase": None,
        "reopen_result": None,
        "recovery_seconds": None,
        "state": "not_run",
    }
    harness.write_receipt(args.receipt, receipt)
    print(json.dumps({"outcome": receipt["outcome"], "receipt": Path(args.receipt).name}))
    return 0


def _cmd_worker(args: argparse.Namespace) -> int:
    digests, digest_set = _expected(args.expected)
    callback = _phase_callback(args.control_dir, args.wait_phase, args.wait_timeout)
    safety = harness.validate_disposable_target(args.database, args.disposable_root)
    try:
        receipt = harness.run_option_b(
            args.database,
            disposable_root=args.disposable_root,
            batch_size=args.batch_size,
            expected_projection_digests=digests,
            expected_projection_set_sha256=digest_set,
            fault_after=args.fault_after,
            timeout_seconds=args.timeout,
            sample_interval_seconds=args.sample_interval,
            progress=callback,
        )
    except BaseException as exc:
        committed = isinstance(exc, harness.PostCommitProgressError)
        reported_error = exc.__cause__ if committed and exc.__cause__ is not None else exc
        harness.write_receipt(
            args.receipt,
            {
                "schema": harness.RECEIPT_SCHEMA,
                "outcome": "committed" if committed else "rolled_back",
                "post_commit_progress": "failed" if committed else "not_reached",
                "error_type": type(reported_error).__name__,
                "payloads_logged": False,
                "safety": safety.receipt(),
                "product_path_activated": safety.product_path_match,
            },
        )
        return 2
    harness.write_receipt(args.receipt, receipt)
    return 0


def _cmd_matrix(args: argparse.Namespace) -> int:
    root: Path = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    counts = [int(value) for value in args.counts.split(",")]
    cases: list[dict[str, Any]] = []
    for count in counts:
        label = f"synthetic-{count}"
        database = root / f"{label}.sqlite3"
        generation_path = root / f"{label}-generation.json"
        measurement_path = root / f"{label}-measurement.json"
        generation = harness.generate_synthetic_database(
            database,
            harness.SyntheticSpec(
                event_count=count,
                batch_size=args.batch_size,
                payload_bytes=args.payload_bytes,
                seed=args.seed,
            ),
            disposable_root=root,
        )
        harness.write_receipt(generation_path, generation)
        measurement = harness.run_option_b(
            database,
            disposable_root=root,
            batch_size=args.batch_size,
            expected_projection_digests=generation["projections"]["digests"],
            expected_projection_set_sha256=generation["projections"]["digest_set_sha256"],
            timeout_seconds=args.timeout,
            sample_interval_seconds=args.sample_interval,
        )
        measurement["concurrency"] = {"state": "separate_fault_matrix"}
        measurement["fault_injection"] = {"state": "separate_fault_matrix"}
        harness.write_receipt(measurement_path, measurement)
        cases.append(
            {
                "label": label,
                "events": count,
                "generation_seconds": generation["duration_seconds"],
                "duration_seconds": measurement["duration_seconds"],
                "peak_rss_bytes": measurement["peak_rss_bytes"],
                "db_highwater_bytes": measurement["storage_highwater_bytes"]["db"],
                "wal_highwater_bytes": measurement["storage_highwater_bytes"]["wal"],
                "oracle_match": True,
                "seal_match": not measurement["integrity"]["seal_issues"],
                "ledger_unchanged": measurement["ledger_before"] == measurement["ledger_after"],
                "receipt": measurement_path.name,
            }
        )
        print(json.dumps(cases[-1], sort_keys=True), flush=True)
    summary = {
        "schema": "genus-a0-3a-local-matrix-v1",
        "batch_size": args.batch_size,
        "payload_bytes": args.payload_bytes,
        "event_mix": [
            "assertion_recorded", "observation_created", "evidence_recorded",
            "relation_asserted",
        ],
        "cases": cases,
        "payloads_logged": False,
        "budgets_applied": False,
    }
    harness.write_receipt(root / "matrix-summary.json", summary)
    return 0


def _cmd_golden(args: argparse.Namespace) -> int:
    from tests import golden_ledger_support as golden

    root: Path = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    candidate = golden.load_candidate()
    before = golden.bundle_bytes_snapshot(candidate)
    conn = golden.import_fixture(root / "import", candidate)
    database = golden.database_file(conn)
    conn.close()
    harness.register_disposable_database(database, root)
    expected = {
        table: candidate.oracle["expected_projections"][table]["sha256"]
        for table in harness.PROJECTION_TABLES
    }
    receipt = harness.run_option_b(
        database,
        disposable_root=root,
        batch_size=args.batch_size,
        expected_projection_digests=expected,
        expected_projection_set_sha256=candidate.oracle["projection_digest_set_sha256"],
        sample_interval_seconds=args.sample_interval,
    )
    verify = db.connect_readonly(database)
    try:
        snapshot = golden.projection_snapshot(verify, candidate.oracle)
        golden.assert_snapshot_matches_oracle(snapshot, candidate.oracle)
        seal_issues = sealing.verify_chain(verify)
        anchor_issues = anchor.verify_anchor(
            verify, candidate.anchor, core_id=candidate.anchor["core_id"]
        )
    finally:
        verify.close()
    golden.assert_bundle_unchanged(candidate, before)
    receipt["golden"] = {
        "all_twelve_projection_oracles": True,
        "seal_match": not seal_issues,
        "anchor_match": not anchor_issues,
        "fixture_unchanged": True,
    }
    harness.write_receipt(root / "golden-measurement.json", receipt)
    return 0


def _cmd_historical(args: argparse.Namespace) -> int:
    from genus import schema_detection
    from tests import historical_sqlite_support as historical

    root: Path = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    source_copy = root / "historical-copy.sqlite3"
    current = root / "historical-rehydrated-current.sqlite3"
    shutil.copy2(historical.DATABASE_PATH, source_copy)
    harness.register_disposable_database(source_copy, root)
    before = harness.file_snapshot(source_copy)
    ro = db.connect_readonly(source_copy)
    try:
        detection = schema_detection.detect_schema(ro)
    finally:
        ro.close()
    rehydration = harness.rehydrate_historical_copy(
        source_copy, current, disposable_root=root, batch_size=args.batch_size
    )
    after = harness.file_snapshot(source_copy)
    if before != after:
        raise harness.HarnessError("historical copy changed")
    current_projection = db.connect_readonly(current)
    try:
        expected = harness.stream_projection_digests(current_projection, args.batch_size)
    finally:
        current_projection.close()
    measurement = harness.run_option_b(
        current,
        disposable_root=root,
        batch_size=args.batch_size,
        expected_projection_digests=expected["digests"],
        expected_projection_set_sha256=expected["digest_set_sha256"],
        sample_interval_seconds=args.sample_interval,
    )
    receipt = {
        "schema": "genus-a0-3a-historical-matrix-v1",
        "recognized_as": detection.schema_id,
        "source_unchanged": before == after,
        "rehydration": rehydration,
        "measurement": measurement,
        "migration_claimed": False,
        "payloads_logged": False,
    }
    harness.write_receipt(root / "historical-measurement.json", receipt)
    return 0


def _wait_for(path: Path, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while not path.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError(f"phase {path.name} did not arrive")
        time.sleep(0.01)


def _projection(path: Path, batch_size: int) -> dict[str, Any]:
    conn = db.connect_readonly(path)
    try:
        return harness.stream_projection_digests(conn, batch_size)
    finally:
        conn.close()


def _cmd_faults(args: argparse.Namespace) -> int:
    root: Path = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    base = root / "fault-base.sqlite3"
    generation = harness.generate_synthetic_database(
        base,
        harness.SyntheticSpec(args.events, args.batch_size, args.payload_bytes, args.seed),
        disposable_root=root,
    )
    expected_path = root / "fault-expected.json"
    harness.write_receipt(expected_path, generation)
    results: list[dict[str, Any]] = []
    for phase in ("mid_replay", "pre_commit", "commit_returned"):
        database = root / f"kill-{phase}.sqlite3"
        shutil.copy2(base, database)
        harness.register_disposable_database(database, root)
        stale = sqlite3.connect(database)
        stale.execute(
            "DELETE FROM value_projection WHERE event_id=(SELECT MAX(event_id) FROM value_projection)"
        )
        stale.commit()
        stale.close()
        old = _projection(database, args.batch_size)
        control = root / f"control-{phase}"
        worker_receipt = root / f"worker-{phase}.json"
        process = subprocess.Popen(
            [
                sys.executable, "-m", "experiments.a0_3a", "_worker",
                str(database), "--batch-size", str(args.batch_size),
                "--disposable-root", str(root),
                "--expected", str(expected_path), "--receipt", str(worker_receipt),
                "--control-dir", str(control), "--wait-phase", phase,
                "--wait-timeout", str(args.phase_timeout),
            ],
            cwd=Path.cwd(),
        )
        _wait_for(control / f"phase-{phase}.json", args.phase_timeout)
        killed_at = time.perf_counter()
        process.kill()
        process.wait(timeout=args.phase_timeout)
        recovered = _projection(database, args.batch_size)
        recovery_seconds = time.perf_counter() - killed_at
        if recovered["digests"] == old["digests"]:
            reopen = "old"
        elif recovered["digests"] == generation["projections"]["digests"]:
            reopen = "new"
        else:
            reopen = "intermediate"
        retry = None
        if reopen == "old":
            retry = harness.run_option_b(
                database,
                disposable_root=root,
                batch_size=args.batch_size,
                expected_projection_digests=generation["projections"]["digests"],
                expected_projection_set_sha256=generation["projections"]["digest_set_sha256"],
                sample_interval_seconds=args.sample_interval,
            )["outcome"]
        results.append(
            {
                "kill_phase": phase,
                "reopen_result": reopen,
                "recovery_seconds": recovery_seconds,
                "retry_result": retry,
                "old_or_new_only": reopen in {"old", "new"},
            }
        )
    if any(result["reopen_result"] == "intermediate" for result in results):
        raise harness.HarnessError("kill matrix exposed an intermediate projection state")
    receipt = {
        "schema": "genus-a0-3a-kill-matrix-v1",
        "events": args.events,
        "batch_size": args.batch_size,
        "results": results,
        "power_loss_claimed": False,
        "commit_syscall_coverage": "pre/post barriers, not literal power loss",
        "payloads_logged": False,
    }
    harness.write_receipt(root / "kill-matrix.json", receipt)
    return 0


def _cmd_concurrency(args: argparse.Namespace) -> int:
    root: Path = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    database = root / "concurrency.sqlite3"
    generation = harness.generate_synthetic_database(
        database,
        harness.SyntheticSpec(args.events, args.batch_size, args.payload_bytes, args.seed),
        disposable_root=root,
    )
    expected_path = root / "concurrency-expected.json"
    harness.write_receipt(expected_path, generation)
    stale = sqlite3.connect(database)
    stale.execute(
        "DELETE FROM value_projection WHERE event_id=(SELECT MAX(event_id) FROM value_projection)"
    )
    stale.commit()
    stale.close()
    old = _projection(database, args.batch_size)
    control = root / "concurrency-control"
    worker_receipt = root / "concurrency-worker.json"
    process = subprocess.Popen(
        [
            sys.executable, "-m", "experiments.a0_3a", "_worker",
            str(database), "--batch-size", str(args.batch_size),
            "--disposable-root", str(root),
            "--expected", str(expected_path), "--receipt", str(worker_receipt),
            "--control-dir", str(control), "--wait-phase", "pre_commit",
            "--wait-timeout", str(args.phase_timeout),
        ],
        cwd=Path.cwd(),
    )
    _wait_for(control / "phase-pre_commit.json", args.phase_timeout)
    reader_samples = [_projection(database, args.batch_size) for _ in range(3)]
    writer = sqlite3.connect(database, timeout=args.writer_timeout, isolation_level=None)
    writer_started = time.perf_counter()
    writer_timed_out = False
    try:
        try:
            writer.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).casefold():
                raise
            writer_timed_out = True
        else:
            writer.rollback()
    finally:
        writer_block_seconds = time.perf_counter() - writer_started
        writer.close()
    (control / "release-pre_commit").write_text("release\n", encoding="ascii")
    process.wait(timeout=args.phase_timeout)
    if process.returncode != 0:
        raise harness.HarnessError(f"concurrency worker exited {process.returncode}")
    complete = _projection(database, args.batch_size)
    worker_result = _read_json(worker_receipt)
    if not all(sample["digests"] == old["digests"] for sample in reader_samples):
        raise harness.HarnessError("reader observed a non-old state before commit")
    if complete["digests"] != generation["projections"]["digests"]:
        raise harness.HarnessError("reader did not observe the complete new state after commit")

    fixed_head = int(worker_result["fixed_head"])
    writer_conn = db.connect(database)
    try:
        appended_id = ledger.append(
            writer_conn,
            "observation_created",
            {"raw_value": 1, "source": "synthetic.concurrent-writer", "unit": "synthetic"},
        )
        writer_conn.commit()
    finally:
        writer_conn.close()
    read = db.connect_readonly(database)
    try:
        read.execute("BEGIN")
        current = harness.capture_fence(read)
        prefix = harness.ReplayFence(
            head_id=fixed_head,
            event_count=int(worker_result["event_count"]),
            min_id=1 if fixed_head else None,
            epoch_event_id=1 if fixed_head else None,
            head_seal=worker_result["ledger_after"]["head_seal"],
        )
        prefix_binding = harness.stream_ledger_binding(read, prefix, args.batch_size)
        read.commit()
    finally:
        read.close()
    receipt = {
        "schema": "genus-a0-3a-concurrency-matrix-v1",
        "events_at_fixed_head": worker_result["event_count"],
        "fixed_head": fixed_head,
        "batch_size": args.batch_size,
        "reader_samples": len(reader_samples) + 1,
        "reader_old_or_new_only": True,
        "reader_before_commit": "old",
        "reader_after_commit": "new",
        "writer_block_seconds": writer_block_seconds,
        "writer_timeout": writer_timed_out,
        "writer_timeout_config_seconds": args.writer_timeout,
        "subsequent_writer_succeeded_after_commit": appended_id == fixed_head + 1,
        "later_event_id": appended_id,
        "later_event_appended_after_commit": appended_id == fixed_head + 1,
        "fixed_head_prefix_unchanged": prefix_binding == worker_result["ledger_after"],
        "current_head_after_writer": current.head_id,
        "payloads_logged": False,
    }
    harness.write_receipt(root / "concurrency-matrix.json", receipt)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    generate = sub.add_parser("generate")
    generate.add_argument("database", type=Path)
    generate.add_argument("--disposable-root", type=Path, required=True)
    generate.add_argument("--events", type=int, required=True)
    generate.add_argument("--batch-size", type=int, default=1024)
    generate.add_argument("--payload-bytes", type=int, default=256)
    generate.add_argument("--seed", type=int, default=3)
    generate.add_argument("--receipt", type=Path, required=True)
    generate.set_defaults(func=_cmd_generate)

    run = sub.add_parser("run")
    run.add_argument("database", type=Path)
    run.add_argument("--disposable-root", type=Path, required=True)
    run.add_argument("--batch-size", type=int, default=1024)
    run.add_argument("--expected", type=Path)
    run.add_argument("--receipt", type=Path, required=True)
    run.add_argument("--timeout", type=float, default=5.0)
    run.add_argument("--sample-interval", type=float, default=0.02)
    run.set_defaults(func=_cmd_run)

    matrix = sub.add_parser("matrix")
    matrix.add_argument("output_dir", type=Path)
    matrix.add_argument(
        "--counts",
        default="0,1,1023,1024,1025,10000,100000,1000000",
    )
    matrix.add_argument("--batch-size", type=int, default=1024)
    matrix.add_argument("--payload-bytes", type=int, default=256)
    matrix.add_argument("--seed", type=int, default=3)
    matrix.add_argument("--timeout", type=float, default=5.0)
    matrix.add_argument("--sample-interval", type=float, default=0.02)
    matrix.set_defaults(func=_cmd_matrix)

    golden = sub.add_parser("golden")
    golden.add_argument("output_dir", type=Path)
    golden.add_argument("--batch-size", type=int, default=7)
    golden.add_argument("--sample-interval", type=float, default=0.005)
    golden.set_defaults(func=_cmd_golden)

    historical_cmd = sub.add_parser("historical")
    historical_cmd.add_argument("output_dir", type=Path)
    historical_cmd.add_argument("--batch-size", type=int, default=3)
    historical_cmd.add_argument("--sample-interval", type=float, default=0.005)
    historical_cmd.set_defaults(func=_cmd_historical)

    faults = sub.add_parser("faults")
    faults.add_argument("output_dir", type=Path)
    faults.add_argument("--events", type=int, default=1000)
    faults.add_argument("--batch-size", type=int, default=64)
    faults.add_argument("--payload-bytes", type=int, default=256)
    faults.add_argument("--seed", type=int, default=3)
    faults.add_argument("--phase-timeout", type=float, default=30.0)
    faults.add_argument("--sample-interval", type=float, default=0.005)
    faults.set_defaults(func=_cmd_faults)

    concurrency = sub.add_parser("concurrency")
    concurrency.add_argument("output_dir", type=Path)
    concurrency.add_argument("--events", type=int, default=1000)
    concurrency.add_argument("--batch-size", type=int, default=64)
    concurrency.add_argument("--payload-bytes", type=int, default=256)
    concurrency.add_argument("--seed", type=int, default=3)
    concurrency.add_argument("--writer-timeout", type=float, default=0.25)
    concurrency.add_argument("--phase-timeout", type=float, default=30.0)
    concurrency.set_defaults(func=_cmd_concurrency)

    worker = sub.add_parser("_worker", help=argparse.SUPPRESS)
    worker.add_argument("database", type=Path)
    worker.add_argument("--disposable-root", type=Path, required=True)
    worker.add_argument("--batch-size", type=int, required=True)
    worker.add_argument("--expected", type=Path)
    worker.add_argument("--receipt", type=Path, required=True)
    worker.add_argument("--control-dir", type=Path, required=True)
    worker.add_argument(
        "--wait-phase", choices=("mid_replay", "pre_commit", "commit_returned")
    )
    worker.add_argument("--wait-timeout", type=float, default=30.0)
    worker.add_argument("--fault-after", type=int)
    worker.add_argument("--timeout", type=float, default=5.0)
    worker.add_argument("--sample-interval", type=float, default=0.005)
    worker.set_defaults(func=_cmd_worker)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
