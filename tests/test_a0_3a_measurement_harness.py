"""Focused contracts for the test-only A0.3a Option-B measurement harness.

The million-event experiment is deliberately absent from pytest.  These tests use
only disposable ``tmp_path`` databases; the accepted A0.2 fixtures are read-only
inputs and the production replay/integrity implementations are never modified.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

from experiments.a0_3a import harness
from genus import anchor, db, integrity, sealing
from tests import golden_ledger_support as golden
from tests import historical_sqlite_support as historical


QUICK_BATCH = 4


@pytest.fixture(autouse=True)
def _product_database_stays_outside_each_disposable_root(tmp_path, monkeypatch):
    """Keep the repository-wide fake product DB beside, not inside, this root."""
    monkeypatch.setenv("GENUS_DB_PATH", str(tmp_path.parent / "test-product.sqlite3"))


def _projection_state(path: Path, batch_size: int = QUICK_BATCH) -> dict:
    conn = db.connect_readonly(path)
    try:
        return harness.stream_projection_digests(conn, batch_size)
    finally:
        conn.close()


def _ledger_state(path: Path, batch_size: int = QUICK_BATCH) -> dict:
    conn = db.connect_readonly(path)
    try:
        conn.execute("BEGIN")
        fence = harness.capture_fence(conn)
        result = harness.stream_ledger_binding(conn, fence, batch_size)
        conn.commit()
        return result
    finally:
        conn.close()


def _delete_last_value_projection(path: Path) -> dict:
    """Create a distinguishable, committed old projection state without touching events."""
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "DELETE FROM value_projection WHERE event_id = "
            "(SELECT MAX(event_id) FROM value_projection)"
        )
        conn.commit()
    finally:
        conn.close()
    return _projection_state(path)


def _guard_snapshot(path: Path) -> dict:
    marker = harness.disposable_marker_path(path)
    return {
        "database": harness.file_snapshot(path),
        "marker_exists": marker.exists(),
        "marker_bytes": marker.read_bytes() if marker.exists() else None,
    }


def _assert_guard_failure_leaves_database_untouched(
    path: Path,
    disposable_root: Path,
    *,
    match: str,
) -> None:
    before = _guard_snapshot(path)
    opened = False
    sampled = False

    def fail_if_opened(*args, **kwargs):
        nonlocal opened
        opened = True
        raise AssertionError("SQLite open must not be reached")

    def fail_if_sampled(*args, **kwargs):
        nonlocal sampled
        sampled = True
        raise AssertionError("sampler must not be reached")

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(harness, "_open_existing", fail_if_opened)
        monkeypatch.setattr(harness, "_Sampler", fail_if_sampled)
        with pytest.raises(harness.DisposableTargetError, match=match):
            harness.run_option_b(
                path,
                disposable_root=disposable_root,
                batch_size=QUICK_BATCH,
                sample_interval_seconds=0.001,
            )
    assert opened is False
    assert sampled is False
    assert _guard_snapshot(path) == before


@pytest.mark.parametrize("event_count", [0, 1, QUICK_BATCH - 1, QUICK_BATCH, QUICK_BATCH + 1])
def test_quick_boundary_matrix_is_bounded_atomic_and_payload_free(tmp_path, event_count):
    path = tmp_path / f"synthetic-{event_count}.sqlite3"
    generated = harness.generate_synthetic_database(
        path,
        harness.SyntheticSpec(
            event_count=event_count,
            batch_size=QUICK_BATCH,
            payload_bytes=160,
            seed=11,
        ),
        disposable_root=tmp_path,
    )
    progress: list[tuple[str, dict]] = []

    receipt = harness.run_option_b(
        path,
        disposable_root=tmp_path,
        batch_size=QUICK_BATCH,
        expected_projection_digests=generated["projections"]["digests"],
        expected_projection_set_sha256=generated["projections"]["digest_set_sha256"],
        sample_interval_seconds=0.001,
        progress=lambda phase, fields: progress.append((phase, dict(fields))),
    )

    assert receipt["outcome"] == "committed"
    assert receipt["event_count"] == event_count
    assert receipt["fixed_head"] == (event_count or None)
    assert receipt["replay"] == {
        "processed": event_count,
        "first_id": 1 if event_count else None,
        "last_id": event_count or None,
        "strictly_ordered": True,
        "exactly_once": True,
        "processed_above_fixed_head": 0,
        "max_payload_bytes": receipt["replay"]["max_payload_bytes"],
        "max_batch_payload_bytes": receipt["replay"]["max_batch_payload_bytes"],
    }
    assert receipt["ledger_before"] == receipt["ledger_after"] == generated["ledger"]
    assert receipt["projection_after"]["digests"] == generated["projections"]["digests"]
    assert receipt["integrity"]["ok"] is True
    assert receipt["integrity"]["production_integrity_called"] is False
    assert receipt["payloads_logged"] is False
    assert receipt["source"] == {
        "label": path.name,
        "absolute_path_logged": False,
    }
    assert json.loads(
        harness.disposable_marker_path(path).read_text(encoding="utf-8")
    ) == {
        "schema": harness.DISPOSABLE_MARKER_SCHEMA,
        "database": path.name,
        "purpose": harness.DISPOSABLE_MARKER_PURPOSE,
    }
    safety = receipt["safety"]
    assert safety["validated"] is True
    assert safety["marker_fields_exact"] is True
    assert safety["strict_containment"] is True
    assert safety["database_is_symlink"] is False
    assert safety["marker_is_symlink"] is False
    assert safety["product_path_match"] is False
    assert safety["root_contains_product_path"] is False
    assert safety["absolute_paths_logged"] is False
    assert receipt["product_path_activated"] == safety["product_path_match"]
    serialized_progress = json.dumps(progress, sort_keys=True)
    assert "payload" not in serialized_progress.casefold()
    assert "claim_key" not in serialized_progress
    assert [phase for phase, _ in progress][0] == "txn_started"
    assert [phase for phase, _ in progress][-1] == "commit_returned"


def test_disposable_guard_missing_marker_fails_before_sqlite_open(tmp_path):
    path = tmp_path / "missing-marker.sqlite3"
    harness.generate_synthetic_database(
        path,
        harness.SyntheticSpec(event_count=5, batch_size=QUICK_BATCH),
        disposable_root=tmp_path,
    )
    harness.disposable_marker_path(path).unlink()

    _assert_guard_failure_leaves_database_untouched(
        path, tmp_path, match="marker does not exist"
    )


def test_disposable_guard_outside_root_fails_before_sqlite_open(tmp_path):
    allowed_root = tmp_path / "allowed"
    wrong_root = tmp_path / "wrong"
    allowed_root.mkdir()
    wrong_root.mkdir()
    path = allowed_root / "outside.sqlite3"
    harness.generate_synthetic_database(
        path,
        harness.SyntheticSpec(event_count=5, batch_size=QUICK_BATCH),
        disposable_root=allowed_root,
    )

    _assert_guard_failure_leaves_database_untouched(
        path, wrong_root, match="outside the disposable root"
    )


def test_disposable_guard_rejects_database_symlink_before_sqlite_open(tmp_path):
    path = tmp_path / "real.sqlite3"
    alias = tmp_path / "alias.sqlite3"
    harness.generate_synthetic_database(
        path,
        harness.SyntheticSpec(event_count=5, batch_size=QUICK_BATCH),
        disposable_root=tmp_path,
    )
    try:
        alias.symlink_to(path)
    except OSError as exc:
        pytest.skip(f"filesystem does not permit symlink creation: {exc}")

    before = _guard_snapshot(path)
    with pytest.raises(harness.DisposableTargetError, match="target must not be a symlink"):
        harness.run_option_b(
            alias,
            disposable_root=tmp_path,
            batch_size=QUICK_BATCH,
            sample_interval_seconds=0.001,
        )
    assert _guard_snapshot(path) == before
    assert not Path(f"{alias}-wal").exists()
    assert not Path(f"{alias}-shm").exists()
    assert not Path(f"{alias}-journal").exists()


def test_disposable_guard_rejects_marker_symlink_before_sqlite_open(tmp_path):
    path = tmp_path / "marker-link.sqlite3"
    harness.generate_synthetic_database(
        path,
        harness.SyntheticSpec(event_count=5, batch_size=QUICK_BATCH),
        disposable_root=tmp_path,
    )
    marker = harness.disposable_marker_path(path)
    marker_target = tmp_path / "marker-target.json"
    marker_target.write_bytes(marker.read_bytes())
    marker.unlink()
    try:
        marker.symlink_to(marker_target)
    except OSError as exc:
        pytest.skip(f"filesystem does not permit symlink creation: {exc}")

    _assert_guard_failure_leaves_database_untouched(
        path, tmp_path, match="marker must not be a symlink"
    )


def test_disposable_guard_rejects_exact_genus_db_path_before_sqlite_open(
    tmp_path, monkeypatch
):
    path = tmp_path / "configured-product.sqlite3"
    harness.generate_synthetic_database(
        path,
        harness.SyntheticSpec(event_count=5, batch_size=QUICK_BATCH),
        disposable_root=tmp_path,
    )
    monkeypatch.setenv("GENUS_DB_PATH", str(path))

    _assert_guard_failure_leaves_database_untouched(
        path, tmp_path, match="protected product path"
    )


def test_disposable_guard_rejects_product_database_hardlink_before_sqlite_open(
    tmp_path, monkeypatch
):
    product = tmp_path.parent / f"{tmp_path.name}-hardlink-product.sqlite3"
    alias = tmp_path / "hardlink-alias.sqlite3"
    product.write_bytes(b"protected product bytes")
    try:
        os.link(product, alias)
    except OSError as exc:
        pytest.skip(f"filesystem does not permit hardlink creation: {exc}")
    marker = harness.disposable_marker_path(alias)
    marker.write_text(
        json.dumps(
            {
                "schema": harness.DISPOSABLE_MARKER_SCHEMA,
                "database": alias.name,
                "purpose": harness.DISPOSABLE_MARKER_PURPOSE,
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    monkeypatch.setenv("GENUS_DB_PATH", str(product))
    opened = False
    sampled = False

    def fail_if_opened(*args, **kwargs):
        nonlocal opened
        opened = True
        raise AssertionError("SQLite open must not be reached")

    def fail_if_sampled(*args, **kwargs):
        nonlocal sampled
        sampled = True
        raise AssertionError("sampler must not be reached")

    monkeypatch.setattr(harness, "_open_existing", fail_if_opened)
    monkeypatch.setattr(harness, "_Sampler", fail_if_sampled)
    before = _guard_snapshot(alias)
    try:
        with pytest.raises(harness.DisposableTargetError, match="protected product path"):
            harness.run_option_b(
                alias,
                disposable_root=tmp_path,
                batch_size=QUICK_BATCH,
                sample_interval_seconds=0.001,
            )
        assert opened is False
        assert sampled is False
        assert _guard_snapshot(alias) == before
    finally:
        alias.unlink(missing_ok=True)
        product.unlink(missing_ok=True)


def test_disposable_guard_fails_closed_when_file_identity_cannot_be_verified(
    tmp_path, monkeypatch
):
    path = tmp_path / "identity-unverifiable.sqlite3"
    harness.generate_synthetic_database(
        path,
        harness.SyntheticSpec(event_count=5, batch_size=QUICK_BATCH),
        disposable_root=tmp_path,
    )
    protected = tmp_path.parent / "unreadable-product.sqlite3"
    monkeypatch.setenv("GENUS_DB_PATH", str(protected))
    real_samefile = Path.samefile

    def deny_identity_check(left, right):
        if Path(right) == protected.resolve(strict=False):
            raise PermissionError("simulated identity denial")
        return real_samefile(left, right)

    monkeypatch.setattr(Path, "samefile", deny_identity_check)
    _assert_guard_failure_leaves_database_untouched(
        path, tmp_path, match="cannot verify database identity"
    )


def test_disposable_guard_rejects_root_containing_genus_db_path_before_open(
    tmp_path, monkeypatch
):
    path = tmp_path / "otherwise-disposable.sqlite3"
    harness.generate_synthetic_database(
        path,
        harness.SyntheticSpec(event_count=5, batch_size=QUICK_BATCH),
        disposable_root=tmp_path,
    )
    monkeypatch.setenv("GENUS_DB_PATH", str(tmp_path / "live-product.sqlite3"))

    _assert_guard_failure_leaves_database_untouched(
        path, tmp_path, match="root contains a protected product path"
    )


def test_disposable_guard_requires_exact_marker_fields_before_sqlite_open(tmp_path):
    path = tmp_path / "altered-marker.sqlite3"
    harness.generate_synthetic_database(
        path,
        harness.SyntheticSpec(event_count=5, batch_size=QUICK_BATCH),
        disposable_root=tmp_path,
    )
    marker = harness.disposable_marker_path(path)
    value = json.loads(marker.read_text(encoding="utf-8"))
    value["extra"] = "not-allowed"
    marker.write_text(json.dumps(value), encoding="utf-8", newline="\n")

    _assert_guard_failure_leaves_database_untouched(
        path, tmp_path, match="marker fields are not exact"
    )


def test_fixed_head_keyset_stream_is_ordered_exact_once_and_excludes_later_id(tmp_path):
    path = tmp_path / "fixed-head.sqlite3"
    harness.generate_synthetic_database(
        path,
        harness.SyntheticSpec(event_count=11, batch_size=QUICK_BATCH),
        disposable_root=tmp_path,
    )
    conn = db.connect_readonly(path)
    try:
        conn.execute("BEGIN")
        captured = harness.capture_fence(conn)
        bounded = replace(
            captured,
            head_id=10,
            event_count=10,
            head_seal=conn.execute("SELECT seal FROM event_log WHERE id=10").fetchone()[0],
        )
        batches = list(harness.iter_event_batches(conn, bounded, QUICK_BATCH))
        ids = [int(event["id"]) for batch in batches for event in batch]
        conn.commit()
    finally:
        conn.close()

    assert [len(batch) for batch in batches] == [QUICK_BATCH, QUICK_BATCH, 2]
    assert ids == list(range(1, 11))
    assert len(ids) == len(set(ids))
    assert 11 not in ids


def test_golden_fixture_matches_all_twelve_oracles_and_bounded_checks(tmp_path):
    candidate = golden.load_candidate()
    original_bytes = golden.bundle_bytes_snapshot(candidate)
    conn = golden.import_fixture(tmp_path, candidate)
    database_path = golden.database_file(conn)
    try:
        conn.execute("BEGIN")
        fence = harness.capture_fence(conn)
        assert harness.validate_event_contract_bounded(conn, fence, 5) == (
            integrity.validate_event_contract(conn)
        ) == []
        assert harness.verify_chain_bounded(conn, fence, 5) == sealing.verify_chain(conn) == []
        conn.commit()
    finally:
        conn.close()
    harness.register_disposable_database(database_path, tmp_path)

    expected_digests = {
        table: candidate.oracle["expected_projections"][table]["sha256"]
        for table in harness.PROJECTION_TABLES
    }
    receipt = harness.run_option_b(
        database_path,
        disposable_root=tmp_path,
        batch_size=5,
        expected_projection_digests=expected_digests,
        expected_projection_set_sha256=candidate.oracle["projection_digest_set_sha256"],
        sample_interval_seconds=0.001,
    )

    verify = db.connect_readonly(database_path)
    try:
        snapshot = golden.projection_snapshot(verify, candidate.oracle)
        golden.assert_snapshot_matches_oracle(snapshot, candidate.oracle)
        assert harness.stream_projection_digests(verify, 5)["digests"] == expected_digests
        assert sealing.verify_chain(verify) == []
        assert anchor.verify_anchor(
            verify,
            candidate.anchor,
            core_id=candidate.anchor["core_id"],
        ) == []
    finally:
        verify.close()

    assert set(receipt["projection_after"]["digests"]) == set(harness.PROJECTION_TABLES)
    assert len(receipt["projection_after"]["digests"]) == 12
    assert receipt["projection_after"]["digest_set_sha256"] == (
        candidate.oracle["projection_digest_set_sha256"]
    )
    assert receipt["ledger_before"] == receipt["ledger_after"]
    golden.assert_bundle_unchanged(candidate, original_bytes)


def test_historical_fixture_copy_stays_byte_exact_and_rehydrates_separately(tmp_path):
    source_copy = tmp_path / "historical-copy.sqlite3"
    current = tmp_path / "rehydrated-current.sqlite3"
    shutil.copy2(historical.DATABASE_PATH, source_copy)
    harness.register_disposable_database(source_copy, tmp_path)
    before = harness.file_snapshot(source_copy)

    result = harness.rehydrate_historical_copy(
        source_copy,
        current,
        disposable_root=tmp_path,
        batch_size=3,
    )

    assert result == {
        "schema": "genus-a0-3a-historical-rehydration-v1",
        "method": "historical_export_to_disposable_current",
        "events_copied": 7,
        "source_unchanged": True,
        "source_sidecars_absent": True,
        "migration_claimed": False,
    }
    assert harness.file_snapshot(source_copy) == before
    assert source_copy.read_bytes() == historical.DATABASE_PATH.read_bytes()

    # The bounded contract verifier deliberately keeps duplicate-detection state in
    # TEMP tables.  Exercise that verifier on the disposable Current copy with a
    # read transaction; the historical source itself was opened query-only above.
    conn = sqlite3.connect(current, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN")
        fence = harness.capture_fence(conn)
        assert fence.event_count == 7
        assert harness.validate_event_contract_bounded(conn, fence, 3) == []
        assert harness.verify_chain_bounded(conn, fence, 3) == []
        projection = harness.stream_projection_digests(conn, 3)
        conn.commit()
    finally:
        conn.close()
    assert set(projection["digests"]) == set(harness.PROJECTION_TABLES)


def test_projector_fault_rolls_back_exactly_then_retry_commits(tmp_path):
    path = tmp_path / "projector-fault.sqlite3"
    generated = harness.generate_synthetic_database(
        path,
        harness.SyntheticSpec(event_count=13, batch_size=QUICK_BATCH),
        disposable_root=tmp_path,
    )
    old_projection = _delete_last_value_projection(path)
    ledger_before = _ledger_state(path)

    with pytest.raises(harness.InjectedFault, match="projector fault after event 6"):
        harness.run_option_b(
            path,
            disposable_root=tmp_path,
            batch_size=QUICK_BATCH,
            expected_projection_digests=generated["projections"]["digests"],
            expected_projection_set_sha256=generated["projections"]["digest_set_sha256"],
            fault_after=6,
            sample_interval_seconds=0.001,
        )

    assert _projection_state(path) == old_projection
    assert _ledger_state(path) == ledger_before

    retry = harness.run_option_b(
        path,
        disposable_root=tmp_path,
        batch_size=QUICK_BATCH,
        expected_projection_digests=generated["projections"]["digests"],
        expected_projection_set_sha256=generated["projections"]["digest_set_sha256"],
        sample_interval_seconds=0.001,
    )
    assert retry["outcome"] == "committed"
    assert retry["projection_after"] == generated["projections"]
    assert _ledger_state(path) == ledger_before


def test_oracle_mismatch_rolls_back_exactly_then_retry_commits(tmp_path):
    path = tmp_path / "oracle-mismatch.sqlite3"
    generated = harness.generate_synthetic_database(
        path,
        harness.SyntheticSpec(event_count=9, batch_size=QUICK_BATCH),
        disposable_root=tmp_path,
    )
    old_projection = _delete_last_value_projection(path)
    ledger_before = _ledger_state(path)
    wrong = dict(generated["projections"]["digests"])
    wrong["value_projection"] = "0" * 64

    with pytest.raises(harness.OracleMismatch, match="expected digests"):
        harness.run_option_b(
            path,
            disposable_root=tmp_path,
            batch_size=QUICK_BATCH,
            expected_projection_digests=wrong,
            expected_projection_set_sha256=generated["projections"]["digest_set_sha256"],
            sample_interval_seconds=0.001,
        )

    assert _projection_state(path) == old_projection
    assert _ledger_state(path) == ledger_before

    retry = harness.run_option_b(
        path,
        disposable_root=tmp_path,
        batch_size=QUICK_BATCH,
        expected_projection_digests=generated["projections"]["digests"],
        expected_projection_set_sha256=generated["projections"]["digest_set_sha256"],
        sample_interval_seconds=0.001,
    )
    assert retry["outcome"] == "committed"
    assert _projection_state(path)["digests"] == generated["projections"]["digests"]


def test_concurrent_reader_sees_committed_old_then_complete_new_only(tmp_path):
    path = tmp_path / "reader.sqlite3"
    generated = harness.generate_synthetic_database(
        path,
        harness.SyntheticSpec(event_count=65, batch_size=QUICK_BATCH),
        disposable_root=tmp_path,
    )
    old = _delete_last_value_projection(path)
    at_precommit = threading.Event()
    release_commit = threading.Event()
    outcome: dict[str, object] = {}

    def progress(phase: str, fields: dict) -> None:
        del fields
        if phase == "pre_commit":
            at_precommit.set()
            assert release_commit.wait(timeout=10)

    def worker() -> None:
        try:
            outcome["receipt"] = harness.run_option_b(
                path,
                disposable_root=tmp_path,
                batch_size=QUICK_BATCH,
                expected_projection_digests=generated["projections"]["digests"],
                expected_projection_set_sha256=generated["projections"]["digest_set_sha256"],
                sample_interval_seconds=0.001,
                progress=progress,
            )
        except BaseException as exc:  # surfaced in the main test thread
            outcome["error"] = exc

    thread = threading.Thread(target=worker, name="a03-reader-worker")
    thread.start()
    assert at_precommit.wait(timeout=10)
    while_open = _projection_state(path)
    release_commit.set()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert "error" not in outcome
    after_commit = _projection_state(path)

    assert while_open == old
    assert after_commit["digests"] == generated["projections"]["digests"]
    assert while_open["digest_set_sha256"] != after_commit["digest_set_sha256"]
    assert outcome["receipt"]["outcome"] == "committed"


def test_concurrent_writer_hits_timeout_while_replay_owns_gate(tmp_path):
    path = tmp_path / "writer.sqlite3"
    generated = harness.generate_synthetic_database(
        path,
        harness.SyntheticSpec(event_count=33, batch_size=QUICK_BATCH),
        disposable_root=tmp_path,
    )
    head_captured = threading.Event()
    release_replay = threading.Event()
    outcome: dict[str, object] = {}

    def progress(phase: str, fields: dict) -> None:
        del fields
        if phase == "head_captured":
            head_captured.set()
            assert release_replay.wait(timeout=10)

    def worker() -> None:
        try:
            outcome["receipt"] = harness.run_option_b(
                path,
                disposable_root=tmp_path,
                batch_size=QUICK_BATCH,
                expected_projection_digests=generated["projections"]["digests"],
                expected_projection_set_sha256=generated["projections"]["digest_set_sha256"],
                sample_interval_seconds=0.001,
                progress=progress,
            )
        except BaseException as exc:
            outcome["error"] = exc

    thread = threading.Thread(target=worker, name="a03-writer-worker")
    thread.start()
    assert head_captured.wait(timeout=10)
    ledger_before = _ledger_state(path)
    writer = sqlite3.connect(path, timeout=0.05, isolation_level=None)
    started = time.perf_counter()
    try:
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            writer.execute("BEGIN IMMEDIATE")
    finally:
        blocked_seconds = time.perf_counter() - started
        writer.close()
        release_replay.set()
    thread.join(timeout=10)

    assert not thread.is_alive()
    assert "error" not in outcome
    assert blocked_seconds >= 0.04
    assert _ledger_state(path) == ledger_before
    assert outcome["receipt"]["fixed_head"] == ledger_before["fixed_head"]


def test_subprocess_kill_boundary_reopens_only_old_or_new_and_precommit_retries(
    tmp_path,
):
    """Exercise OS hard-kill semantics through the real hidden worker CLI.

    ``Popen.kill`` maps to SIGKILL on POSIX and TerminateProcess on Windows.  The
    two deterministic barriers bracket SQLite's commit: before it, recovery must
    expose the old committed projection; after ``commit`` returned, the new one.
    """
    root = Path(__file__).resolve().parents[1]
    base = tmp_path / "kill-base.sqlite3"
    expected_path = tmp_path / "expected.json"
    generated = harness.generate_synthetic_database(
        base,
        harness.SyntheticSpec(event_count=41, batch_size=QUICK_BATCH),
        disposable_root=tmp_path,
    )
    harness.write_receipt(expected_path, generated)
    expected = generated["projections"]
    results: dict[str, str] = {}

    for phase, expected_reopen in (
        ("pre_commit", "old"),
        ("commit_returned", "new"),
    ):
        path = tmp_path / f"kill-{phase}.sqlite3"
        receipt_path = tmp_path / f"worker-{phase}.json"
        control = tmp_path / f"control-{phase}"
        shutil.copy2(base, path)
        harness.register_disposable_database(path, tmp_path)
        old = _delete_last_value_projection(path)
        ledger_before = _ledger_state(path)

        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "experiments.a0_3a",
                "_worker",
                str(path),
                "--disposable-root",
                str(tmp_path),
                "--batch-size",
                str(QUICK_BATCH),
                "--expected",
                str(expected_path),
                "--receipt",
                str(receipt_path),
                "--control-dir",
                str(control),
                "--wait-phase",
                phase,
                "--wait-timeout",
                "15",
                "--sample-interval",
                "0.001",
            ],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        phase_path = control / f"phase-{phase}.json"
        deadline = time.monotonic() + 15
        while not phase_path.exists():
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                pytest.fail(
                    f"worker exited before {phase}: rc={process.returncode}, "
                    f"stdout={stdout!r}, stderr={stderr!r}"
                )
            if time.monotonic() >= deadline:
                process.kill()
                process.wait(timeout=5)
                pytest.fail(f"worker did not reach {phase}")
            time.sleep(0.01)

        # Every coordination artifact is aggregate-only; no event body, source
        # path, or synthetic claim may leak through progress telemetry.
        for progress_path in control.glob("phase-*.json"):
            raw = progress_path.read_text(encoding="utf-8")
            value = json.loads(raw)
            assert set(value) == {"metrics", "phase"}
            assert set(value["metrics"]) <= {
                "processed",
                "fixed_head",
                "event_count",
                "head_id",
            }
            folded = raw.casefold()
            assert "payload" not in folded
            assert "claim_key" not in folded
            assert str(path.resolve()).casefold() not in folded

        process.kill()
        process.wait(timeout=15)
        assert process.returncode != 0
        recovered = _projection_state(path)
        if recovered["digests"] == old["digests"]:
            reopen = "old"
        elif recovered["digests"] == expected["digests"]:
            reopen = "new"
        else:
            reopen = "intermediate"
        results[phase] = reopen

        assert reopen == expected_reopen
        assert reopen in {"old", "new"}
        assert _ledger_state(path) == ledger_before
        assert not receipt_path.exists()

        if phase == "pre_commit":
            retry = harness.run_option_b(
                path,
                disposable_root=tmp_path,
                batch_size=QUICK_BATCH,
                expected_projection_digests=expected["digests"],
                expected_projection_set_sha256=expected["digest_set_sha256"],
                sample_interval_seconds=0.001,
            )
            assert retry["outcome"] == "committed"
            assert _projection_state(path)["digests"] == expected["digests"]
            assert _ledger_state(path) == ledger_before

    assert results == {"pre_commit": "old", "commit_returned": "new"}


def test_worker_reports_post_commit_progress_timeout_as_committed(tmp_path):
    root = Path(__file__).resolve().parents[1]
    path = tmp_path / "post-commit-timeout.sqlite3"
    expected_path = tmp_path / "post-commit-expected.json"
    receipt_path = tmp_path / "post-commit-worker.json"
    control = tmp_path / "post-commit-control"
    generated = harness.generate_synthetic_database(
        path,
        harness.SyntheticSpec(event_count=9, batch_size=QUICK_BATCH),
        disposable_root=tmp_path,
    )
    harness.write_receipt(expected_path, generated)
    old = _delete_last_value_projection(path)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "experiments.a0_3a",
            "_worker",
            str(path),
            "--disposable-root",
            str(tmp_path),
            "--batch-size",
            str(QUICK_BATCH),
            "--expected",
            str(expected_path),
            "--receipt",
            str(receipt_path),
            "--control-dir",
            str(control),
            "--wait-phase",
            "commit_returned",
            "--wait-timeout",
            "0.05",
            "--sample-interval",
            "0.001",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert completed.returncode == 2
    assert receipt["error_type"] == "TimeoutError"
    assert receipt["outcome"] == "committed"
    assert receipt["payloads_logged"] is False
    assert receipt["post_commit_progress"] == "failed"
    assert receipt["schema"] == harness.RECEIPT_SCHEMA
    assert receipt["safety"]["validated"] is True
    assert receipt["safety"]["product_path_match"] is False
    assert receipt["product_path_activated"] is False
    assert _projection_state(path)["digests"] == generated["projections"]["digests"]
    assert _projection_state(path)["digests"] != old["digests"]
