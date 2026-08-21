from __future__ import annotations

import json
import math
import shutil
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterator, Mapping

import pytest

from experiments.a0_3a import harness as a03a
from experiments.a0_3b import __main__ as a03b_cli
from experiments.a0_3b import harness
from genus import anchor, db, ledger
from tests import golden_ledger_support as golden
from tests import historical_sqlite_support as historical


BATCH_EVENTS = 4
BATCH_BYTES = 1024 * 1024


@pytest.fixture(autouse=True)
def _product_database_stays_outside_each_disposable_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep the suite-wide fake product DB beside the disposable experiment root."""
    monkeypatch.setenv("GENUS_DB_PATH", str(tmp_path.parent / "test-product.sqlite3"))


def _synthetic(
    tmp_path: Path,
    event_count: int,
    *,
    payload_bytes: int = 128,
    label: str = "ledger",
) -> tuple[Path, dict[str, Any]]:
    path = tmp_path / f"{label}.sqlite3"
    generated = a03a.generate_synthetic_database(
        path,
        a03a.SyntheticSpec(
            event_count=event_count,
            batch_size=BATCH_EVENTS,
            payload_bytes=payload_bytes,
            seed=17,
        ),
        disposable_root=tmp_path,
    )
    return path, generated


def _raw_projection_digest(path: Path) -> dict[str, Any]:
    conn = db.connect_readonly(path)
    try:
        return a03a.stream_projection_digests(conn, BATCH_EVENTS)
    finally:
        conn.close()


def _generation(receipt: Mapping[str, Any], generation_id: str) -> Mapping[str, Any]:
    return next(item for item in receipt["generations"] if item["generation_id"] == generation_id)


def _existing_relation_sequence(conn: sqlite3.Connection, generation_id: str) -> tuple[str, int]:
    for logical in harness.SEQUENCE_TABLES:
        physical = logical if generation_id == "g1" else f"a03b_{generation_id}__{logical}"
        row = conn.execute("SELECT seq FROM sqlite_sequence WHERE name=?", (physical,)).fetchone()
        if row is not None:
            return physical, int(row[0])
    raise AssertionError(f"no relation-owned sequence for {generation_id}")


def _prepare_verified(
    tmp_path: Path,
    *,
    event_count: int = 17,
    label: str = "verified",
) -> tuple[Path, dict[str, Any]]:
    path, generated = _synthetic(tmp_path, event_count, label=label)
    harness.initialize_shadow(path, disposable_root=tmp_path)
    harness.build_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
        sample_interval_seconds=0.001,
    )
    verified = harness.verify_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
        require_active_match=True,
        atomic_cutover=False,
    )
    return path, {"generated": generated, "verified": verified}


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for key, item in value.items():
            yield str(key)
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


@pytest.mark.parametrize("event_count", [0, 1, 3, 4, 5])
def test_boundary_matrix_builds_exact_twelve_tables_and_nine_sequences(
    tmp_path: Path, event_count: int
) -> None:
    path, generated = _synthetic(tmp_path, event_count, label=f"boundary-{event_count}")
    g1_before = _raw_projection_digest(path)

    initialized = harness.initialize_shadow(path, disposable_root=tmp_path)
    assert initialized["generation_ids"] == ["g1", "g2", "g3"]
    assert initialized["projection_target_count"] == 3 * len(harness.PROJECTION_TABLES)
    assert len(harness.PROJECTION_TABLES) == 12
    assert len(harness.SEQUENCE_TABLES) == 9

    built = harness.build_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
        sample_interval_seconds=0.001,
    )
    assert built["processed_events"] == event_count
    assert built["batch_count"] == math.ceil(event_count / BATCH_EVENTS)
    assert _raw_projection_digest(path) == g1_before

    caught_up = harness.catch_up_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
    )
    assert caught_up["remaining_tail_gap"] == 0

    verified = harness.verify_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
        require_active_match=True,
        atomic_cutover=False,
    )
    assert verified["all_twelve_match"] is True
    assert verified["all_nine_sequences_match"] is True
    assert set(verified["projection_digests"]["digests"]) == set(harness.PROJECTION_TABLES)
    assert set(verified["sequences"]) == set(harness.SEQUENCE_TABLES)
    assert verified["projection_digests"]["digests"] == generated["projections"]["digests"]

    cutover = harness.cutover_shadow(path, disposable_root=tmp_path)
    assert cutover["outcome"] == "complete_new"
    assert cutover["committed"] is True
    assert cutover["within_writer_block_budget"] is True
    with harness.active_reader(path, disposable_root=tmp_path) as reader:
        assert reader.generation_id == "g2"
        assert (
            reader.digest(BATCH_EVENTS)["projections"]["digests"]
            == generated["projections"]["digests"]
        )
    recovered = harness.recover(path, disposable_root=tmp_path)
    assert recovered["classification"] == "NEW_ACTIVE_OLD_RETIRED"
    assert recovered["within_recovery_budget"] is True


def test_build_catchup_and_atomic_cutover_keep_g1_visible_to_old_readers(
    tmp_path: Path,
) -> None:
    path, _ = _synthetic(tmp_path, 21, label="reader-cutover")
    harness.initialize_shadow(path, disposable_root=tmp_path)
    g1_at_h0 = harness.stream_generation_digests(
        path, "g1", disposable_root=tmp_path, batch_events=BATCH_EVENTS
    )
    harness.build_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
    )
    assert (
        harness.stream_generation_digests(
            path, "g1", disposable_root=tmp_path, batch_events=BATCH_EVENTS
        )["projections"]
        == g1_at_h0["projections"]
    )

    writer_receipts = [
        harness.append_routed(
            path,
            "assertion_recorded",
            {
                "claim_key": f"a03b.catchup.{index}",
                "claim_value": index,
                "source": "experiment:a0_3b:test",
                "derivation": "experiment:a0_3b:test:v1",
            },
            disposable_root=tmp_path,
        )
        for index in range(3)
    ]
    assert all(item["committed"] for item in writer_receipts)
    assert max(item["lock_wait_seconds"] for item in writer_receipts) <= 2.0

    caught_up = harness.catch_up_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=2,
        batch_bytes=BATCH_BYTES,
    )
    assert caught_up["processed_events"] == 3
    assert caught_up["remaining_tail_gap"] == 0
    harness.verify_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
        require_active_match=True,
        atomic_cutover=False,
    )

    pointer_changed = threading.Event()
    release_commit = threading.Event()
    outcome: dict[str, Any] = {}

    def fault(phase: str, _evidence: Mapping[str, Any]) -> None:
        if phase == "cutover_pointer_changed":
            pointer_changed.set()
            if not release_commit.wait(timeout=10):
                raise TimeoutError("cutover test barrier timed out")

    def worker() -> None:
        try:
            outcome["receipt"] = harness.cutover_shadow(path, disposable_root=tmp_path, fault=fault)
        except BaseException as exc:  # surfaced in the main test thread
            outcome["error"] = exc

    with harness.active_reader(path, disposable_root=tmp_path) as long_reader:
        assert long_reader.generation_id == "g1"
        old_digest = long_reader.digest(BATCH_EVENTS)
        thread = threading.Thread(target=worker, name="a03b-cutover-worker")
        thread.start()
        assert pointer_changed.wait(timeout=10)
        with harness.active_reader(path, disposable_root=tmp_path) as short_reader:
            assert short_reader.generation_id == "g1"
        assert long_reader.generation_id == "g1"
        assert long_reader.digest(BATCH_EVENTS) == old_digest
        release_commit.set()
        thread.join(timeout=10)
        assert not thread.is_alive()
        assert "error" not in outcome

    assert outcome["receipt"]["outcome"] == "complete_new"
    with harness.active_reader(path, disposable_root=tmp_path) as fresh_reader:
        assert fresh_reader.generation_id == "g2"
        assert (
            fresh_reader.digest(BATCH_EVENTS)["projections"]
            == (
                harness.stream_generation_digests(
                    path, "g1", disposable_root=tmp_path, batch_events=BATCH_EVENTS
                )["projections"]
            )
        )


def test_concurrency_probe_reports_writer_distribution_and_coherent_readers(
    tmp_path: Path,
) -> None:
    path, _ = _synthetic(tmp_path, 65, label="concurrency")
    harness.initialize_shadow(path, disposable_root=tmp_path)

    receipt = harness.run_concurrency_probe(
        path,
        disposable_root=tmp_path,
        writer_interval_seconds=0.002,
        short_reader_interval_seconds=0.002,
        batch_events=8,
        batch_bytes=BATCH_BYTES,
    )

    latency = receipt["writer_latency"]
    assert latency["sample_count"] >= 1
    assert latency["committed_count"] == latency["sample_count"]
    assert latency["timeouts"] == 0
    assert latency["errors"] == 0
    assert latency["starvation"] is False
    assert latency["within_max_block_budget"] is True
    assert (
        latency["p50_seconds"]
        <= latency["p95_seconds"]
        <= latency["p99_seconds"]
        <= latency["max_seconds"]
    )
    assert receipt["reader"]["coherent_old_or_new_only"] is True
    assert receipt["reader"]["long_reader_before"] == "g1"
    assert receipt["reader"]["long_reader_after"] == "g1"
    assert receipt["reader"]["fresh_reader_after"] == "g2"
    assert (
        receipt["reader"]["long_reader_snapshot_scope"]
        == "cutover_pre_commit_through_post_commit"
    )
    assert receipt["reader"]["bulk_replay_wal_pinned"] is False
    assert receipt["reader"]["short_transaction_count"] > 0
    assert receipt["reader"]["evidence_complete"] is True
    assert receipt["reader"]["samples_truncated"] is False
    assert receipt["reader"]["failure_samples_truncated"] is False
    assert receipt["reader"]["reader_thread_alive_after_join"] is False
    assert receipt["reader"]["writer_thread_alive_after_join"] is False
    assert receipt["cutover"]["within_writer_block_budget"] is True
    assert receipt["cutover"]["selected_final_sync_mode"] == "a_bounded_fence"
    assert receipt["cutover"]["sync_route_used"] is False
    assert receipt["verify"]["selected_final_sync_mode"] == "a_bounded_fence"
    assert receipt["verify"]["sync_route_used"] is False
    assert receipt["verify"]["write_transaction_max_seconds"]["pass"] is True
    assert latency["samples_truncated"] is False
    assert latency["dropped_sample_count"] == 0
    assert latency["observed_attempt_rate_per_second"] > 0
    assert latency["committed_arrival_rate_per_second"] > 0
    assert receipt["writer_evidence_complete"] is True
    assert set(receipt["writer_latency_by_phase"]) == {
        "g1_only",
        "sync_triple",
        "g2_only",
    }
    assert receipt["writer_latency_by_phase"]["g1_only"]["sample_count"] > 0
    assert receipt["writer_latency_by_phase"]["sync_triple"]["sample_count"] == 0
    assert receipt["writer_latency_by_phase"]["g2_only"]["sample_count"] > 0
    assert receipt["writer_phase_overhead"] == {
        "sync_minus_g1_p50_seconds": None,
        "sync_over_g1_p50_ratio": None,
    }
    assert receipt["catch_up"]["catch_up_rate_events_per_second"] is not None
    assert receipt["catch_up"]["event_arrival_rate_events_per_second"] is not None
    assert receipt["concurrency_gate_pass"] is True


def test_concurrency_long_reader_pins_only_the_atomic_cutover_fence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, _ = _synthetic(tmp_path, 65, label="concurrency-reader-fence")
    harness.initialize_shadow(path, disposable_root=tmp_path)
    original_verify = harness.verify_shadow
    original_active_reader = harness.active_reader
    original_admit = harness._admit_synchronous_writes
    cutover_precommit_depth = 0
    admission_attempts = 0
    main_reader_phases: list[str] = []
    main_readers: list[harness.ActiveReader] = []

    def tracked_verify(*args: Any, **kwargs: Any) -> dict[str, Any]:
        original_fault = kwargs["fault"]

        def tracked_fault(phase: str, evidence: Mapping[str, Any]) -> None:
            nonlocal cutover_precommit_depth
            if phase != "cutover_pre_commit":
                original_fault(phase, evidence)
                return
            cutover_precommit_depth += 1
            try:
                original_fault(phase, evidence)
            finally:
                cutover_precommit_depth -= 1

        kwargs["fault"] = tracked_fault
        return original_verify(*args, **kwargs)

    def tracked_active_reader(*args: Any, **kwargs: Any) -> harness.ActiveReader:
        reader = original_active_reader(*args, **kwargs)
        if threading.current_thread() is threading.main_thread():
            main_reader_phases.append(
                "cutover_pre_commit" if cutover_precommit_depth else "outside"
            )
            main_readers.append(reader)
        return reader

    def retry_first_admission(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal admission_attempts
        # Every reader from an earlier rolled-back fence must be gone before
        # verify_shadow starts any retry work.
        assert all(reader.closed for reader in main_readers)
        admission_attempts += 1
        if admission_attempts == 1:
            kwargs["fault"]("cutover_pre_commit", {})
            return {"outcome": "not_ready_fence_budget", "committed": False}
        return original_admit(*args, **kwargs)

    monkeypatch.setattr(harness, "verify_shadow", tracked_verify)
    monkeypatch.setattr(harness, "active_reader", tracked_active_reader)
    monkeypatch.setattr(harness, "_admit_synchronous_writes", retry_first_admission)
    receipt = harness.run_concurrency_probe(
        path,
        disposable_root=tmp_path,
        writer_interval_seconds=0.002,
        short_reader_interval_seconds=0.002,
        batch_events=8,
        batch_bytes=BATCH_BYTES,
    )

    # Both old readers are opened exactly inside their atomic pre-commit hook.
    # The first belongs to the forced non-committed attempt and is closed before
    # attempt two; the final main-thread reader is the post-commit fresh check.
    assert admission_attempts >= 2
    assert main_reader_phases[-1] == "outside"
    assert len(main_reader_phases) >= 3
    assert set(main_reader_phases[:-1]) == {"cutover_pre_commit"}
    assert all(reader.closed for reader in main_readers)
    assert receipt["reader"]["long_reader_before"] == "g1"
    assert receipt["reader"]["long_reader_after"] == "g1"
    assert receipt["reader"]["fresh_reader_after"] == "g2"
    assert (
        receipt["reader"]["long_reader_snapshot_scope"]
        == "cutover_pre_commit_through_post_commit"
    )
    assert receipt["reader"]["bulk_replay_wal_pinned"] is False
    assert receipt["reader"]["coherent_old_or_new_only"] is True
    assert receipt["verify"]["all_twelve_match"] is True
    assert receipt["verify"]["all_nine_sequences_match"] is True


def test_concurrency_closes_cutover_reader_when_precommit_hook_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, _ = _synthetic(tmp_path, 17, label="concurrency-reader-cleanup")
    harness.initialize_shadow(path, disposable_root=tmp_path)
    original_verify = harness.verify_shadow
    original_active_reader = harness.active_reader
    main_readers: list[harness.ActiveReader] = []

    def tracked_active_reader(*args: Any, **kwargs: Any) -> harness.ActiveReader:
        reader = original_active_reader(*args, **kwargs)
        if threading.current_thread() is threading.main_thread():
            main_readers.append(reader)
        return reader

    def failing_verify(*args: Any, **kwargs: Any) -> dict[str, Any]:
        original_fault = kwargs["fault"]

        def failing_fault(phase: str, evidence: Mapping[str, Any]) -> None:
            original_fault(phase, evidence)
            if phase == "cutover_pre_commit":
                raise harness.InjectedFault("after old reader binding")

        kwargs["fault"] = failing_fault
        return original_verify(*args, **kwargs)

    monkeypatch.setattr(harness, "active_reader", tracked_active_reader)
    monkeypatch.setattr(harness, "verify_shadow", failing_verify)
    with pytest.raises(harness.InjectedFault, match="old reader binding"):
        harness.run_concurrency_probe(
            path,
            disposable_root=tmp_path,
            writer_interval_seconds=0.002,
            short_reader_interval_seconds=0.002,
            batch_events=8,
            batch_bytes=BATCH_BYTES,
        )

    assert len(main_readers) == 1
    assert main_readers[0].closed is True


def test_inter_batch_handoff_admits_a_continuously_queued_writer(
    tmp_path: Path,
) -> None:
    path, _ = _synthetic(tmp_path, 49, label="inter-batch-writer-handoff")
    harness.initialize_shadow(path, disposable_root=tmp_path)

    receipt = harness.run_concurrency_probe(
        path,
        disposable_root=tmp_path,
        writer_interval_seconds=0.0005,
        short_reader_interval_seconds=0.001,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
    )

    build_handoff = receipt["build"]["post_batch_writer_yield"]
    verify_handoff = receipt["verify"]["post_batch_writer_yield"]
    replay_batch_count = receipt["verify"]["second_replay_batches"]
    writer_handoff = receipt["writer_handoff"]
    total_handoffs = (
        build_handoff["count"]
        + receipt["catch_up"]["post_batch_writer_yield"]["count"]
        + verify_handoff["count"]
    )

    assert receipt["build"]["batch_count"] >= 8
    assert replay_batch_count >= 8
    assert build_handoff["count"] == receipt["build"]["batch_count"]
    assert verify_handoff["count"] >= replay_batch_count
    assert build_handoff["strategy"] == "cooperative-writer-admission-slot"
    assert build_handoff["fallback_yield_seconds_per_batch"] is None
    assert verify_handoff["strategy"] == "cooperative-writer-admission-slot"
    assert verify_handoff["fallback_yield_seconds_per_batch"] is None
    assert build_handoff["outside_transactions"] is True
    assert verify_handoff["outside_transactions"] is True
    assert total_handoffs >= 16
    assert writer_handoff["strategy"] == "cooperative-writer-admission-slot"
    assert writer_handoff["load_model"] == "closed_loop_single_writer"
    assert writer_handoff["think_time_seconds"] == pytest.approx(0.0005)
    assert writer_handoff["expected_from_committed_batches"] == total_handoffs
    assert writer_handoff["requested"] == total_handoffs
    assert writer_handoff["completed"] == total_handoffs
    assert writer_handoff["timeouts"] == 0
    assert writer_handoff["commit_delta_total"] == total_handoffs
    assert writer_handoff["commit_delta_min"] == 1
    assert writer_handoff["commit_delta_max"] == 1
    assert writer_handoff["exactly_one_commit_per_slot"] is True
    assert writer_handoff["outside_transactions"] is True
    assert (
        writer_handoff["max_wait_seconds"]
        <= writer_handoff["timeout_seconds_per_slot"]
    )
    assert writer_handoff["pass"] is True

    latency = receipt["writer_latency"]
    assert latency["sample_count"] >= total_handoffs
    assert latency["committed_count"] == latency["sample_count"]
    assert latency["timeouts"] == 0
    assert latency["errors"] == 0
    assert latency["starvation"] is False
    assert latency["max_seconds"] < harness.WRITER_BLOCK_BUDGET_SECONDS
    assert latency["within_max_block_budget"] is True
    assert receipt["writer_evidence_complete"] is True
    assert receipt["verify"]["selected_final_sync_mode"] == "a_bounded_fence"
    assert receipt["verify"]["sync_route_used"] is False
    assert receipt["cutover"]["selected_final_sync_mode"] == "a_bounded_fence"
    assert receipt["cutover"]["sync_route_used"] is False
    assert receipt["writer_latency_by_phase"]["sync_triple"]["sample_count"] == 0
    assert receipt["concurrency_gate_pass"] is True


def test_writer_latency_percentiles_use_nearest_rank_and_flag_starvation() -> None:
    samples = [
        {"committed": True, "end_to_end_seconds": value}
        for value in (0.001, 0.002, 0.003, 0.004, 0.100)
    ]
    summary = harness.writer_latency_summary(samples)
    assert summary == {
        "sample_count": 5,
        "committed_count": 5,
        "p50_seconds": 0.003,
        "p95_seconds": 0.100,
        "p99_seconds": 0.100,
        "max_seconds": 0.100,
        "timeouts": 0,
        "errors": 0,
        "max_pending_age_seconds": 0.0,
        "max_queue_delay_seconds": 0.0,
        "max_intercommit_gap_seconds": 0.0,
        "starvation": False,
        "within_max_block_budget": True,
    }

    stopped = harness.writer_latency_summary(
        [*samples, {"committed": False, "outcome": "timeout"}],
        pending_age_seconds=2.001,
    )
    assert stopped["timeouts"] == 1
    assert stopped["starvation"] is True


@pytest.mark.parametrize(
    "fault_phase",
    ["batch_opened", "batch_applied", "watermark_updated", "batch_pre_commit"],
)
def test_build_batch_fault_rolls_back_projection_watermark_and_receipt(
    tmp_path: Path, fault_phase: str
) -> None:
    path, _ = _synthetic(tmp_path, 9, label=f"build-fault-{fault_phase}")
    harness.initialize_shadow(path, disposable_root=tmp_path)
    fired = False

    def fault(phase: str, _evidence: Mapping[str, Any]) -> None:
        nonlocal fired
        if phase == fault_phase and not fired:
            fired = True
            raise harness.InjectedFault(f"fault at {phase}")

    with pytest.raises(harness.InjectedFault, match=fault_phase):
        harness.build_shadow(
            path,
            disposable_root=tmp_path,
            batch_events=BATCH_EVENTS,
            batch_bytes=BATCH_BYTES,
            fault=fault,
        )
    assert fired is True
    status = harness.generation_status(path, disposable_root=tmp_path)
    g2 = _generation(status, "g2")
    assert g2["built_through_event_id"] is None
    assert g2["built_event_count"] == 0
    assert harness.recover(path, disposable_root=tmp_path)["classification"] == (
        "OLD_ACTIVE_SHADOW_RESUMABLE"
    )

    retry = harness.build_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
    )
    assert retry["processed_events"] == 9


@pytest.mark.parametrize(
    "fault_phase",
    ["cutover_head_bound", "cutover_pointer_changed", "cutover_pre_commit"],
)
def test_precommit_cutover_fault_recovers_complete_old_and_retry_is_complete_new(
    tmp_path: Path, fault_phase: str
) -> None:
    path, _ = _prepare_verified(tmp_path, label=f"cutover-fault-{fault_phase}")

    def fault(phase: str, _evidence: Mapping[str, Any]) -> None:
        if phase == fault_phase:
            raise harness.InjectedFault(f"fault at {phase}")

    with pytest.raises(harness.InjectedFault, match=fault_phase):
        harness.cutover_shadow(path, disposable_root=tmp_path, fault=fault)
    old = harness.recover(path, disposable_root=tmp_path)
    assert old["classification"] == "OLD_ACTIVE_SYNC_ARMED"
    assert old["active_generation_id"] == "g1"

    retry = harness.cutover_shadow(path, disposable_root=tmp_path)
    assert retry["outcome"] == "complete_new"
    assert harness.recover(path, disposable_root=tmp_path)["classification"] == (
        "NEW_ACTIVE_OLD_RETIRED"
    )


def test_postcommit_fault_is_classified_as_complete_new_not_rollback(
    tmp_path: Path,
) -> None:
    path, _ = _prepare_verified(tmp_path, label="postcommit-fault")

    def fault(phase: str, _evidence: Mapping[str, Any]) -> None:
        if phase == "cutover_post_commit":
            raise RuntimeError("telemetry failed after commit")

    with pytest.raises(harness.PostCommitFault, match="after commit"):
        harness.cutover_shadow(path, disposable_root=tmp_path, fault=fault)
    recovered = harness.recover(path, disposable_root=tmp_path)
    assert recovered["classification"] == "NEW_ACTIVE_OLD_RETIRED"
    assert recovered["active_generation_id"] == "g2"


def test_invalid_event_fails_closed_before_cutover(tmp_path: Path) -> None:
    invalid_path, _ = _synthetic(tmp_path, 5, label="invalid-event")
    harness.initialize_shadow(invalid_path, disposable_root=tmp_path)
    writer = db.connect(invalid_path)
    try:
        ledger.append(writer, "synthetic_invalid_event", {"synthetic": True})
        writer.commit()
    finally:
        writer.close()
    harness.build_shadow(
        invalid_path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
    )
    with pytest.raises(
        harness.ShadowHarnessError,
        match="ledger verification|active generation metadata",
    ):
        harness.verify_shadow(
            invalid_path,
            disposable_root=tmp_path,
            batch_events=BATCH_EVENTS,
            batch_bytes=BATCH_BYTES,
        )
    invalid_recovery = harness.recover(invalid_path, disposable_root=tmp_path)
    assert invalid_recovery["classification"] == "INVALID_UNROUTED_TAIL"
    assert invalid_recovery["active_generation_id"] == ""
    assert invalid_recovery["reader_ready"] is False
    assert invalid_recovery["writer_ready"] is False


def test_simulated_sqlite_full_rolls_back_batch_and_leaves_complete_old_active(
    tmp_path: Path,
) -> None:
    path, _ = _synthetic(tmp_path, 17, label="simulated-sqlite-full")
    harness.initialize_shadow(path, disposable_root=tmp_path)
    fault_receipt = {
        "fault_mode": "simulated",
        "sqlite_error": "SQLITE_FULL",
        "phase": "batch_pre_commit",
        "physical_enospc_claimed": False,
    }

    def fault(phase: str, _evidence: Mapping[str, Any]) -> None:
        if phase == fault_receipt["phase"]:
            raise sqlite3.OperationalError("database or disk is full")

    with pytest.raises(sqlite3.OperationalError, match="database or disk is full"):
        harness.build_shadow(
            path,
            disposable_root=tmp_path,
            batch_events=17,
            batch_bytes=BATCH_BYTES,
            fault=fault,
        )
    assert fault_receipt == {
        "fault_mode": "simulated",
        "sqlite_error": "SQLITE_FULL",
        "phase": "batch_pre_commit",
        "physical_enospc_claimed": False,
    }
    status = harness.generation_status(path, disposable_root=tmp_path)
    assert _generation(status, "g2")["built_event_count"] == 0
    recovered = harness.recover(path, disposable_root=tmp_path)
    assert recovered["classification"] == "OLD_ACTIVE_SHADOW_RESUMABLE"
    assert recovered["active_generation_id"] == "g1"

    retry = harness.build_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=17,
        batch_bytes=BATCH_BYTES,
    )
    assert retry["processed_events"] == 17


def test_golden_oracle_and_anchor_survive_shadow_cutover(tmp_path: Path) -> None:
    candidate = golden.load_candidate()
    fixture_before = golden.bundle_bytes_snapshot(candidate)
    conn = golden.import_fixture(tmp_path / "golden-import", candidate)
    path = golden.database_file(conn)
    conn.execute("BEGIN IMMEDIATE")
    a03a.replay_bounded_in_txn(conn, a03a.capture_fence(conn), 7)
    conn.commit()
    conn.close()
    a03a.register_disposable_database(path, tmp_path)

    receipt = harness.run_shadow_prototype(
        path,
        disposable_root=tmp_path,
        batch_events=7,
        batch_bytes=BATCH_BYTES,
    )
    assert receipt["ledger_unchanged"] is True
    assert receipt["active_generation_id"] == "g2"
    assert receipt["active_projection_digests"]["projections"]["digests"] == {
        table: candidate.oracle["expected_projections"][table]["sha256"]
        for table in harness.PROJECTION_TABLES
    }
    verify = db.connect_readonly(path)
    try:
        assert not anchor.verify_anchor(
            verify, candidate.anchor, core_id=candidate.anchor["core_id"]
        )
    finally:
        verify.close()
    golden.assert_bundle_unchanged(candidate, fixture_before)


def test_historical_source_is_unchanged_and_rehydrated_current_can_cut_over(
    tmp_path: Path,
) -> None:
    source = tmp_path / "historical.sqlite3"
    current = tmp_path / "historical-current.sqlite3"
    shutil.copy2(historical.DATABASE_PATH, source)
    a03a.register_disposable_database(source, tmp_path)
    before = a03a.file_snapshot(source)

    rehydrated = a03a.rehydrate_historical_copy(
        source,
        current,
        disposable_root=tmp_path,
        batch_size=3,
    )
    receipt = harness.run_shadow_prototype(
        current,
        disposable_root=tmp_path,
        batch_events=3,
        batch_bytes=BATCH_BYTES,
    )

    assert rehydrated["source_unchanged"] is True
    assert rehydrated["migration_claimed"] is False
    assert a03a.file_snapshot(source) == before
    assert receipt["ledger_unchanged"] is True
    assert receipt["recovery"]["classification"] == "NEW_ACTIVE_OLD_RETIRED"


def test_receipts_are_aggregate_only_and_do_not_disclose_payloads_or_paths(
    tmp_path: Path,
) -> None:
    path, _ = _synthetic(tmp_path, 9, label="private-receipt")
    receipt = harness.run_shadow_prototype(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
    )

    assert receipt["payloads_logged"] is False
    assert receipt["absolute_paths_logged"] is False
    forbidden_values = {
        str(path.resolve()).casefold(),
        str(tmp_path.resolve()).casefold(),
        "synthetic.metric.",
        "synthetic.source.",
        "claim_key",
        "claim_value",
    }
    for value in _strings(receipt):
        folded = value.casefold()
        assert all(forbidden not in folded for forbidden in forbidden_values)
    encoded = json.dumps(receipt, ensure_ascii=True, sort_keys=True)
    assert '"payload"' not in encoded.casefold()
    assert '"absolute_path"' not in encoded.casefold()


def test_sqlite_wal_reset_gate_is_explicit_and_fail_closed() -> None:
    assert harness.sqlite_wal_reset_gate("3.51.3")["wal_reset_fix"] == "confirmed"
    assert harness.sqlite_wal_reset_gate("3.44.6")["wal_reset_fix"] == "confirmed"
    assert harness.sqlite_wal_reset_gate("3.50.7")["wal_reset_fix"] == "confirmed"
    affected = harness.sqlite_wal_reset_gate("3.46.1")
    assert affected["wal_reset_fix"] == "unconfirmed"
    assert affected["live_eligibility"] is False
    malformed = harness.sqlite_wal_reset_gate("unknown")
    assert malformed["wal_reset_fix"] == "unconfirmed"
    assert malformed["live_eligibility"] is False


def test_verified_shadow_routes_later_writes_to_all_generations_before_cutover(
    tmp_path: Path,
) -> None:
    path, _ = _prepare_verified(tmp_path, label="routed-sync-tail")
    appended = harness.append_routed(
        path,
        "assertion_recorded",
        {
            "claim_key": "a03b.zero-tail",
            "claim_value": "new",
            "source": "experiment:a0_3b:test",
            "derivation": "experiment:a0_3b:test:v1",
        },
        disposable_root=tmp_path,
    )
    assert appended["committed"] is True
    assert appended["active_generation_id"] == "g1"
    assert appended["sync_generation_id"] == "g2"
    assert appended["routed_generation_count"] == 3
    assert appended["sync_chain_sha256"] is not None
    digests = [
        harness.stream_generation_digests(
            path,
            generation_id,
            disposable_root=tmp_path,
            batch_events=BATCH_EVENTS,
        )
        for generation_id in ("g1", "g2", "g3")
    ]
    assert digests[0]["projections"] == digests[1]["projections"] == digests[2]["projections"]
    assert digests[0]["sequences"] == digests[1]["sequences"] == digests[2]["sequences"]

    promoted = harness.cutover_shadow(path, disposable_root=tmp_path)
    assert promoted["outcome"] == "complete_new"
    assert promoted["synchronized_tail_event_count"] == 1
    assert promoted["unsynchronized_tail_event_count"] == 0


def test_active_generation_cannot_be_rebuilt_or_cleared_after_cutover(
    tmp_path: Path,
) -> None:
    path, _ = _prepare_verified(tmp_path, label="active-immutable")
    harness.cutover_shadow(path, disposable_root=tmp_path)
    before = harness.stream_generation_digests(
        path, "g2", disposable_root=tmp_path, batch_events=BATCH_EVENTS
    )
    with pytest.raises(harness.ShadowHarnessError, match="active/retired"):
        harness.build_shadow(
            path,
            disposable_root=tmp_path,
            batch_events=BATCH_EVENTS,
            batch_bytes=BATCH_BYTES,
        )
    after = harness.stream_generation_digests(
        path, "g2", disposable_root=tmp_path, batch_events=BATCH_EVENTS
    )
    assert after == before


def test_noncontiguous_sqlite_ids_are_streamed_by_successor_not_arithmetic(
    tmp_path: Path,
) -> None:
    path = tmp_path / "gapped.sqlite3"
    conn = db.connect(path)
    payloads = (
        json.dumps(
            {
                "claim_key": f"a03b.gap.{event_id}",
                "claim_value": event_id,
                "source": "experiment:a0_3b:test",
                "derivation": "experiment:a0_3b:test:v1",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        for event_id in (1, 3)
    )
    conn.executemany(
        "INSERT INTO event_log(id,event_type,payload,created_at,prev_seal,seal) "
        "VALUES (?,?,?,'2030-01-01T00:00:00.000000+00:00',NULL,NULL)",
        ((event_id, "assertion_recorded", payload) for event_id, payload in zip((1, 3), payloads)),
    )
    conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    a03a.replay_bounded_in_txn(conn, a03a.capture_fence(conn), 1)
    conn.commit()
    conn.close()
    a03a.register_disposable_database(path, tmp_path)

    receipt = harness.run_shadow_prototype(
        path,
        disposable_root=tmp_path,
        batch_events=1,
        batch_bytes=BATCH_BYTES,
    )
    assert receipt["ledger_unchanged"] is True
    assert receipt["verify"]["event_count"] == 2
    assert receipt["active_generation_id"] == "g2"


def test_invalid_cutover_metadata_never_advertises_reader_or_writer_ready(
    tmp_path: Path,
) -> None:
    path, _ = _synthetic(tmp_path, 5, label="ambiguous")
    harness.initialize_shadow(path, disposable_root=tmp_path)
    conn = sqlite3.connect(path)
    try:
        conn.execute("UPDATE a03b_generation SET state='retired' WHERE generation_id='g1'")
        conn.execute("UPDATE a03b_generation SET state='active' WHERE generation_id='g2'")
        conn.execute("UPDATE a03b_control SET active_generation_id='g2' WHERE singleton=1")
        conn.commit()
    finally:
        conn.close()
    recovered = harness.recover(path, disposable_root=tmp_path)
    assert recovered["classification"] == "INVALID_UNROUTED_TAIL"
    assert recovered["reader_ready"] is False
    assert recovered["writer_ready"] is False
    assert recovered["within_recovery_budget"] is False


def test_a_first_selects_bounded_direct_fence_with_no_sync_route(
    tmp_path: Path,
) -> None:
    path, _ = _synthetic(tmp_path, 17, label="a-first")
    harness.initialize_shadow(path, disposable_root=tmp_path)
    harness.build_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
    )

    receipt = harness.verify_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
        atomic_cutover=True,
    )
    admission = receipt["sync_admission"]
    cutover = receipt["cutover"]
    assert receipt["selected_final_sync_mode"] == "a_bounded_fence"
    assert receipt["sync_route_used"] is False
    assert admission["outcome"] == "complete_new"
    assert admission["selected_final_sync_mode"] == "a_bounded_fence"
    assert admission["sync_route_used"] is False
    assert admission["within_writer_block_budget"] is True
    assert admission["fence_seconds"] <= harness.WRITER_BLOCK_BUDGET_SECONDS
    assert admission["pointer_metadata_and_commit_seconds"] <= admission["fence_seconds"]
    assert admission["persistent_receipt_chains_recomputed"] is True
    assert admission["validated_receipt_count"] > 0
    assert admission["incremental_receipt_count_in_fence"] >= 0
    assert cutover["outcome"] == "complete_new"
    assert cutover["pointer_and_tail_same_fence"] is True
    assert cutover["unsynchronized_tail_event_count"] == 0
    assert receipt["write_transaction_max_seconds"]["pass"] is True
    status = harness.generation_status(path, disposable_root=tmp_path)
    assert status["active_generation_id"] == "g2"
    assert status["sync_generation_id"] is None
    assert harness.recover(path, disposable_root=tmp_path)["classification"] == (
        "NEW_ACTIVE_OLD_RETIRED"
    )


def test_b_routed_sync_is_selected_only_by_explicit_non_atomic_request(
    tmp_path: Path,
) -> None:
    path, prepared = _prepare_verified(tmp_path, label="explicit-b")
    verified = prepared["verified"]
    assert verified["selected_final_sync_mode"] == "b_routed_sync"
    assert verified["sync_route_used"] is True
    assert verified["cutover"] is None
    assert verified["sync_admission"]["outcome"] == "sync_armed"
    assert verified["sync_admission"]["selected_final_sync_mode"] == ("b_routed_sync")
    status = harness.generation_status(path, disposable_root=tmp_path)
    assert status["active_generation_id"] == "g1"
    assert status["sync_generation_id"] == "g2"

    cutover = harness.cutover_shadow(path, disposable_root=tmp_path)
    assert cutover["outcome"] == "complete_new"
    assert cutover["selected_final_sync_mode"] == "b_routed_sync"
    assert cutover["sync_route_used"] is True
    assert cutover["persistent_receipt_chains_recomputed"] is True
    assert cutover["validated_receipt_count"] > 0
    assert cutover["incremental_receipt_count_in_fence"] >= 0
    assert cutover["proof_prevalidation_seconds"] >= 0
    assert cutover["metadata_only_pointer_change"] is True


def test_continuous_writer_crosses_explicit_sync_route_and_atomic_cutover(
    tmp_path: Path,
) -> None:
    path, _ = _synthetic(tmp_path, 65, label="continuous-writer")
    harness.initialize_shadow(path, disposable_root=tmp_path)
    harness.build_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=8,
        batch_bytes=BATCH_BYTES,
    )
    stop = threading.Event()
    samples: list[dict[str, Any]] = []
    errors: list[BaseException] = []

    def writer() -> None:
        sequence = 0
        while not stop.wait(0.005):
            sequence += 1
            try:
                samples.append(
                    harness.append_routed(
                        path,
                        "assertion_recorded",
                        {
                            "claim_key": f"a03b.continuous.{sequence % 13}",
                            "claim_value": sequence,
                            "source": "experiment:a0_3b:test",
                            "derivation": "experiment:a0_3b:test:v1",
                        },
                        disposable_root=tmp_path,
                        timeout_seconds=2.0,
                    )
                )
            except BaseException as exc:  # surfaced in the main test thread
                errors.append(exc)
                stop.set()

    thread = threading.Thread(target=writer, name="a03b-continuous-writer")
    thread.start()
    try:
        deadline = time.monotonic() + 5.0
        while not samples and time.monotonic() < deadline:
            time.sleep(0.005)
        assert samples

        verified = harness.verify_shadow(
            path,
            disposable_root=tmp_path,
            batch_events=8,
            batch_bytes=BATCH_BYTES,
            atomic_cutover=False,
        )
        assert verified["sync_admission"]["outcome"] == "sync_armed"
        assert verified["sync_admission"]["sync_generation_id"] == "g2"
        assert verified["selected_final_sync_mode"] == "b_routed_sync"
        assert verified["sync_route_used"] is True

        deadline = time.monotonic() + 5.0
        while (
            not any(item["routed_generation_count"] == 3 for item in samples)
            and time.monotonic() < deadline
        ):
            time.sleep(0.005)
        assert any(
            item["active_generation_id"] == "g1"
            and item["sync_generation_id"] == "g2"
            and item["routed_generation_count"] == 3
            for item in samples
        )

        cutover = harness.cutover_shadow(path, disposable_root=tmp_path)
        assert cutover["outcome"] == "complete_new"
        assert cutover["unsynchronized_tail_event_count"] == 0
        assert cutover["metadata_only_pointer_change"] is True

        deadline = time.monotonic() + 5.0
        while (
            not any(item["active_generation_id"] == "g2" for item in samples)
            and time.monotonic() < deadline
        ):
            time.sleep(0.005)
        assert any(
            item["active_generation_id"] == "g2"
            and item["sync_generation_id"] is None
            and item["routed_generation_count"] == 1
            for item in samples
        )
    finally:
        stop.set()
        thread.join(timeout=5.0)
    assert not thread.is_alive()
    assert errors == []
    assert all(item["committed"] for item in samples)
    recovered = harness.recover(path, disposable_root=tmp_path)
    assert recovered["classification"] == "NEW_ACTIVE_OLD_RETIRED"
    assert recovered["reader_ready"] is True
    assert recovered["writer_ready"] is True


@pytest.mark.parametrize(
    "fault_phase",
    [
        "sync_admission_opened",
        "cutover_pointer_changed",
        "cutover_pre_commit",
        "sync_admission_pre_commit",
    ],
)
def test_integrated_atomic_cutover_precommit_fault_recovers_old_and_retries(
    tmp_path: Path, fault_phase: str
) -> None:
    path, _ = _synthetic(tmp_path, 17, label=f"integrated-{fault_phase}")
    harness.initialize_shadow(path, disposable_root=tmp_path)
    harness.build_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
    )

    def fault(phase: str, _evidence: Mapping[str, Any]) -> None:
        if phase == fault_phase:
            raise harness.InjectedFault(f"fault at {phase}")

    with pytest.raises(harness.InjectedFault, match=fault_phase):
        harness.verify_shadow(
            path,
            disposable_root=tmp_path,
            batch_events=BATCH_EVENTS,
            batch_bytes=BATCH_BYTES,
            atomic_cutover=True,
            fault=fault,
        )
    old = harness.recover(path, disposable_root=tmp_path)
    assert old["classification"] == "OLD_ACTIVE_SYNC_PREPARING"
    assert old["active_generation_id"] == "g1"
    assert old["retryable_now"] is True

    retried = harness.verify_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
        atomic_cutover=True,
    )
    assert retried["cutover"]["outcome"] == "complete_new"
    assert harness.recover(path, disposable_root=tmp_path)["classification"] == (
        "NEW_ACTIVE_OLD_RETIRED"
    )


@pytest.mark.parametrize("fault_phase", ["sync_admission_post_commit", "cutover_post_commit"])
def test_integrated_atomic_cutover_postcommit_fault_recovers_complete_new(
    tmp_path: Path, fault_phase: str
) -> None:
    path, _ = _synthetic(tmp_path, 17, label=f"integrated-{fault_phase}")
    harness.initialize_shadow(path, disposable_root=tmp_path)
    harness.build_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
    )

    def fault(phase: str, _evidence: Mapping[str, Any]) -> None:
        if phase == fault_phase:
            raise RuntimeError("telemetry failed after integrated commit")

    with pytest.raises(harness.PostCommitFault, match="after commit"):
        harness.verify_shadow(
            path,
            disposable_root=tmp_path,
            batch_events=BATCH_EVENTS,
            batch_bytes=BATCH_BYTES,
            atomic_cutover=True,
            fault=fault,
        )
    recovered = harness.recover(path, disposable_root=tmp_path)
    assert recovered["classification"] == "NEW_ACTIVE_OLD_RETIRED"
    assert recovered["active_generation_id"] == "g2"
    assert recovered["retryable_now"] is True


@pytest.mark.parametrize(
    "fault_phase",
    [
        "sync_admission_opened",
        "sync_admission_armed",
        "sync_admission_pre_commit",
    ],
)
def test_explicit_b_admission_precommit_fault_recovers_preparing_and_retries(
    tmp_path: Path, fault_phase: str
) -> None:
    path, _ = _synthetic(tmp_path, 17, label=f"b-admission-{fault_phase}")
    harness.initialize_shadow(path, disposable_root=tmp_path)
    harness.build_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
    )

    def fault(phase: str, _evidence: Mapping[str, Any]) -> None:
        if phase == fault_phase:
            raise harness.InjectedFault(f"fault at {phase}")

    with pytest.raises(harness.InjectedFault, match=fault_phase):
        harness.verify_shadow(
            path,
            disposable_root=tmp_path,
            batch_events=BATCH_EVENTS,
            batch_bytes=BATCH_BYTES,
            atomic_cutover=False,
            fault=fault,
        )
    recovered = harness.recover(path, disposable_root=tmp_path)
    assert recovered["classification"] == "OLD_ACTIVE_SYNC_PREPARING"
    assert recovered["retryable_now"] is True

    retry = harness.verify_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
        atomic_cutover=False,
    )
    assert retry["selected_final_sync_mode"] == "b_routed_sync"
    assert harness.cutover_shadow(path, disposable_root=tmp_path)["outcome"] == ("complete_new")


def test_explicit_b_admission_postcommit_fault_recovers_armed_and_retries(
    tmp_path: Path,
) -> None:
    path, _ = _synthetic(tmp_path, 17, label="b-admission-postcommit")
    harness.initialize_shadow(path, disposable_root=tmp_path)
    harness.build_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
    )

    def fault(phase: str, _evidence: Mapping[str, Any]) -> None:
        if phase == "sync_admission_post_commit":
            raise RuntimeError("telemetry failed after B admission commit")

    with pytest.raises(harness.PostCommitFault, match="after commit"):
        harness.verify_shadow(
            path,
            disposable_root=tmp_path,
            batch_events=BATCH_EVENTS,
            batch_bytes=BATCH_BYTES,
            atomic_cutover=False,
            fault=fault,
        )
    recovered = harness.recover(path, disposable_root=tmp_path)
    assert recovered["classification"] == "OLD_ACTIVE_SYNC_ARMED"
    assert recovered["retryable_now"] is True
    assert harness.cutover_shadow(path, disposable_root=tmp_path)["outcome"] == ("complete_new")


@pytest.mark.parametrize(
    ("fault_phase", "expected_exception", "message"),
    [
        ("sync_batch_opened", harness.InjectedFault, "sync_batch_opened"),
        ("sync_batch_pre_commit", harness.InjectedFault, "sync_batch_pre_commit"),
        ("sync_batch_post_commit", harness.PostCommitFault, "after commit"),
    ],
)
def test_sync_prepare_batch_fault_recovers_and_full_retry_succeeds(
    tmp_path: Path,
    fault_phase: str,
    expected_exception: type[BaseException],
    message: str,
) -> None:
    path, _ = _synthetic(tmp_path, 17, label=f"sync-batch-{fault_phase}")
    harness.initialize_shadow(path, disposable_root=tmp_path)
    harness.build_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
    )
    tail_added = False

    def fault(phase: str, _evidence: Mapping[str, Any]) -> None:
        nonlocal tail_added
        if phase == "validation_post_commit" and not tail_added:
            tail_added = True
            harness.append_routed(
                path,
                "assertion_recorded",
                {
                    "claim_key": f"a03b.sync-batch.{fault_phase}",
                    "claim_value": "tail",
                    "source": "experiment:a0_3b:test",
                    "derivation": "experiment:a0_3b:test:v1",
                },
                disposable_root=tmp_path,
            )
        elif phase == fault_phase:
            raise harness.InjectedFault(f"fault at {phase}")

    with pytest.raises(expected_exception, match=message):
        harness.verify_shadow(
            path,
            disposable_root=tmp_path,
            batch_events=BATCH_EVENTS,
            batch_bytes=BATCH_BYTES,
            atomic_cutover=True,
            fault=fault,
        )
    assert tail_added is True
    recovered = harness.recover(path, disposable_root=tmp_path)
    assert recovered["classification"] == "OLD_ACTIVE_SYNC_PREPARING"

    retry = harness.verify_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
        atomic_cutover=True,
    )
    assert retry["cutover"]["outcome"] == "complete_new"


@pytest.mark.parametrize(
    "fault_phase",
    ["validation_opened", "validation_digests_computed", "validation_pre_commit"],
)
def test_validation_precommit_fault_recovers_resumable_and_retries(
    tmp_path: Path, fault_phase: str
) -> None:
    path, _ = _synthetic(tmp_path, 17, label=f"validation-{fault_phase}")
    harness.initialize_shadow(path, disposable_root=tmp_path)
    harness.build_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
    )

    def fault(phase: str, _evidence: Mapping[str, Any]) -> None:
        if phase == fault_phase:
            raise harness.InjectedFault(f"fault at {phase}")

    with pytest.raises(harness.InjectedFault, match=fault_phase):
        harness.verify_shadow(
            path,
            disposable_root=tmp_path,
            batch_events=BATCH_EVENTS,
            batch_bytes=BATCH_BYTES,
            atomic_cutover=True,
            fault=fault,
        )
    recovered = harness.recover(path, disposable_root=tmp_path)
    assert recovered["classification"] == "OLD_ACTIVE_SHADOW_RESUMABLE"
    retry = harness.verify_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
        atomic_cutover=True,
    )
    assert retry["cutover"]["outcome"] == "complete_new"


def test_validation_postcommit_retry_reports_bounded_g3_purge_transactions(
    tmp_path: Path,
) -> None:
    path, _ = _synthetic(tmp_path, 257, label="bounded-g3-purge")
    harness.initialize_shadow(path, disposable_root=tmp_path)
    harness.build_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=32,
        batch_bytes=BATCH_BYTES,
    )

    def fault(phase: str, _evidence: Mapping[str, Any]) -> None:
        if phase == "validation_post_commit":
            raise RuntimeError("stop after durable G3 verification replay")

    with pytest.raises(harness.PostCommitFault, match="after commit"):
        harness.verify_shadow(
            path,
            disposable_root=tmp_path,
            batch_events=32,
            batch_bytes=BATCH_BYTES,
            atomic_cutover=True,
            fault=fault,
        )
    assert harness.recover(path, disposable_root=tmp_path)["classification"] == (
        "OLD_ACTIVE_SYNC_PREPARING"
    )

    retried = harness.verify_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=32,
        batch_bytes=BATCH_BYTES,
        atomic_cutover=True,
    )
    assert retried["g3_reset_strategy"] == ("bounded-table-and-metadata-delete-batches")
    assert retried["g3_bounded_reset_transaction_count"] > 1
    assert retried["g3_bounded_reset_max_transaction_seconds"] > 0
    assert (
        retried["g3_bounded_reset_max_transaction_seconds"]
        <= (retried["write_transaction_max_seconds"]["overall"])
    )
    assert retried["write_transaction_max_seconds"]["g3_second_replay"] <= (
        harness.WRITER_BLOCK_BUDGET_SECONDS
    )
    assert retried["write_transaction_max_seconds"]["pass"] is True


def test_build_postcommit_fault_preserves_old_and_retry_resumes_exactly(
    tmp_path: Path,
) -> None:
    path, _ = _synthetic(tmp_path, 9, label="build-postcommit")
    harness.initialize_shadow(path, disposable_root=tmp_path)
    fired = False

    def fault(phase: str, _evidence: Mapping[str, Any]) -> None:
        nonlocal fired
        if phase == "batch_post_commit" and not fired:
            fired = True
            raise RuntimeError("batch telemetry failed after commit")

    with pytest.raises(harness.PostCommitFault, match="after commit"):
        harness.build_shadow(
            path,
            disposable_root=tmp_path,
            batch_events=BATCH_EVENTS,
            batch_bytes=BATCH_BYTES,
            fault=fault,
        )
    recovered = harness.recover(path, disposable_root=tmp_path)
    assert recovered["classification"] == "OLD_ACTIVE_SHADOW_RESUMABLE"
    retry = harness.build_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
    )
    assert retry["processed_events"] == 5
    assert (
        _generation(harness.generation_status(path, disposable_root=tmp_path), "g2")[
            "built_event_count"
        ]
        == 9
    )


@pytest.mark.parametrize(
    ("fault_phase", "expected_exception", "expected_retry_events"),
    [
        ("catch_up_batch_opened", harness.InjectedFault, 1),
        ("catch_up_batch_pre_commit", harness.InjectedFault, 1),
        ("catch_up_batch_post_commit", harness.PostCommitFault, 0),
        ("catch_up_complete", harness.InjectedFault, 0),
    ],
)
def test_catchup_fault_boundaries_reopen_and_retry_to_the_same_tail(
    tmp_path: Path,
    fault_phase: str,
    expected_exception: type[BaseException],
    expected_retry_events: int,
) -> None:
    path, _ = _synthetic(tmp_path, 9, label=f"catchup-fault-{fault_phase}")
    harness.initialize_shadow(path, disposable_root=tmp_path)
    harness.build_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
    )
    appended = harness.append_routed(
        path,
        "assertion_recorded",
        {
            "claim_key": "a03b.catchup-fault",
            "claim_value": "tail",
            "source": "experiment:a0_3b:test",
            "derivation": "experiment:a0_3b:test:v1",
        },
        disposable_root=tmp_path,
    )

    def fault(phase: str, _evidence: Mapping[str, Any]) -> None:
        if phase == fault_phase:
            raise harness.InjectedFault(f"fault at {fault_phase}")

    with pytest.raises(expected_exception, match="fault|after commit"):
        harness.catch_up_shadow(
            path,
            disposable_root=tmp_path,
            batch_events=BATCH_EVENTS,
            batch_bytes=BATCH_BYTES,
            fault=fault,
        )
    reopened = harness.recover(path, disposable_root=tmp_path)
    assert reopened["classification"] == "OLD_ACTIVE_SHADOW_RESUMABLE"
    assert reopened["active_generation_id"] == "g1"
    retry = harness.catch_up_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
    )
    assert retry["processed_events"] == expected_retry_events
    assert retry["remaining_tail_gap"] == 0
    assert (
        _generation(harness.generation_status(path, disposable_root=tmp_path), "g2")[
            "built_through_event_id"
        ]
        == appended["event_id"]
    )


def test_final_fence_timer_excludes_prevalidation_delay(tmp_path: Path) -> None:
    path, _ = _synthetic(tmp_path, 17, label="fence-timer")
    harness.initialize_shadow(path, disposable_root=tmp_path)
    harness.build_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
    )
    delay_seconds = 0.2
    delayed = False

    def fault(phase: str, _evidence: Mapping[str, Any]) -> None:
        nonlocal delayed
        if phase == "validation_digests_computed" and not delayed:
            delayed = True
            time.sleep(delay_seconds)

    receipt = harness.verify_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
        atomic_cutover=True,
        fault=fault,
    )
    assert delayed is True
    assert receipt["duration_seconds"] >= delay_seconds
    assert receipt["cutover"]["final_fence_seconds"] < delay_seconds
    assert receipt["cutover"]["within_writer_block_budget"] is True


def test_post_cutover_routed_write_remains_complete_new_and_ready(
    tmp_path: Path,
) -> None:
    path, _ = _prepare_verified(tmp_path, label="post-cutover-write")
    cutover = harness.cutover_shadow(path, disposable_root=tmp_path)
    appended = harness.append_routed(
        path,
        "assertion_recorded",
        {
            "claim_key": "a03b.post-cutover",
            "claim_value": "new-active",
            "source": "experiment:a0_3b:test",
            "derivation": "experiment:a0_3b:test:v1",
        },
        disposable_root=tmp_path,
    )
    assert cutover["outcome"] == "complete_new"
    assert appended["active_generation_id"] == "g2"
    assert appended["sync_generation_id"] is None
    assert appended["routed_generation_count"] == 1

    recovered = harness.recover(path, disposable_root=tmp_path)
    assert recovered["classification"] == "NEW_ACTIVE_OLD_RETIRED"
    assert recovered["reader_ready"] is True
    assert recovered["writer_ready"] is True
    assert recovered["within_recovery_budget"] is True


def test_recovery_fails_closed_when_wal_mode_was_replaced_with_delete(
    tmp_path: Path,
) -> None:
    path, _ = _synthetic(tmp_path, 5, label="delete-journal")
    harness.initialize_shadow(path, disposable_root=tmp_path)
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        assert str(conn.execute("PRAGMA journal_mode=DELETE").fetchone()[0]).lower() == ("delete")
    finally:
        conn.close()

    recovered = harness.recover(path, disposable_root=tmp_path)
    assert recovered["classification"] == "INVALID_JOURNAL_MODE"
    assert recovered["extended_schema_valid"] is True
    assert recovered["reader_ready"] is False
    assert recovered["writer_ready"] is False
    assert recovered["within_recovery_budget"] is False


def test_parallel_builder_is_rejected_while_live_generation_lease_is_held(
    tmp_path: Path,
) -> None:
    path, _ = _synthetic(tmp_path, 17, label="parallel-builder")
    harness.initialize_shadow(path, disposable_root=tmp_path)
    lease_held = threading.Event()
    release = threading.Event()
    result: dict[str, Any] = {}
    paused = False

    def fault(phase: str, _evidence: Mapping[str, Any]) -> None:
        nonlocal paused
        if phase == "batch_post_commit" and not paused:
            paused = True
            lease_held.set()
            if not release.wait(timeout=10.0):
                raise TimeoutError("parallel builder lease barrier timed out")

    def first_builder() -> None:
        try:
            result["receipt"] = harness.build_shadow(
                path,
                disposable_root=tmp_path,
                batch_events=BATCH_EVENTS,
                batch_bytes=BATCH_BYTES,
                fault=fault,
            )
        except BaseException as exc:  # surfaced in the main test thread
            result["error"] = exc

    thread = threading.Thread(target=first_builder, name="a03b-first-builder")
    thread.start()
    assert lease_held.wait(timeout=10.0)
    try:
        during_lease = harness.recover(path, disposable_root=tmp_path)
        assert during_lease["classification"] == "OLD_ACTIVE_SHADOW_RESUMABLE"
        assert during_lease["live_operation_lease_count"] == 1
        assert during_lease["reader_ready"] is True
        assert during_lease["writer_ready"] is False
        assert during_lease["retryable_now"] is False
        assert during_lease["within_recovery_budget"] is False
        with pytest.raises(harness.ShadowHarnessError, match="active operation"):
            harness.build_shadow(
                path,
                disposable_root=tmp_path,
                batch_events=BATCH_EVENTS,
                batch_bytes=BATCH_BYTES,
            )
    finally:
        release.set()
        thread.join(timeout=10.0)
    assert not thread.is_alive()
    assert "error" not in result
    assert result["receipt"]["processed_events"] == 17


@pytest.mark.parametrize(
    ("tamper_sql", "expected_classification"),
    [
        (
            "UPDATE a03b_verification SET ledger_sha256=printf('%064d',0) WHERE generation_id='g2'",
            "INVALID_VERIFIED_BASE",
        ),
        (
            "UPDATE a03b_verification SET projection_digests_json='{}' WHERE generation_id='g2'",
            "INVALID_VERIFIED_BASE",
        ),
        (
            "UPDATE a03b_verification SET sequences_json='{}' WHERE generation_id='g3'",
            "INVALID_VERIFIED_BASE",
        ),
        (
            "UPDATE a03b_sync_session SET base_projection_digest_set_sha256="
            "printf('%064d',0) WHERE singleton=1",
            "INVALID_PERSISTENT_PROOF",
        ),
        (
            "UPDATE a03b_apply_receipt SET ledger_batch_sha256=printf('%064d',0) "
            "WHERE generation_id='g2' AND batch_no=(SELECT MIN(batch_no) "
            "FROM a03b_apply_receipt WHERE generation_id='g2')",
            "INVALID_PERSISTENT_PROOF",
        ),
        (
            "UPDATE a03b_apply_receipt SET receipt_sha256=printf('%064d',0) "
            "WHERE generation_id='g3' AND batch_no=(SELECT MAX(batch_no) "
            "FROM a03b_apply_receipt WHERE generation_id='g3')",
            "INVALID_PERSISTENT_PROOF",
        ),
        (
            "UPDATE a03b_sync_session SET sync_chain_sha256=printf('%064d',0) WHERE singleton=1",
            "INVALID_PERSISTENT_PROOF",
        ),
    ],
)
def test_verification_receipt_or_sync_metadata_tamper_blocks_cutover_and_recovery(
    tmp_path: Path, tamper_sql: str, expected_classification: str
) -> None:
    path, _ = _prepare_verified(tmp_path, label="verification-tamper")
    conn = sqlite3.connect(path)
    try:
        conn.execute(tamper_sql)
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(harness.CutoverNotReady, match="verified-base"):
        harness.cutover_shadow(path, disposable_root=tmp_path)
    recovered = harness.recover(path, disposable_root=tmp_path)
    assert recovered["classification"] == expected_classification
    assert recovered["reader_ready"] is False
    assert recovered["writer_ready"] is False
    assert recovered["within_recovery_budget"] is False


def test_unrouted_tail_blocks_reader_writer_cutover_and_recovery(tmp_path: Path) -> None:
    path, _ = _prepare_verified(tmp_path, label="unrouted-tail")
    conn = db.connect(path)
    try:
        ledger.append(
            conn,
            "assertion_recorded",
            {
                "claim_key": "a03b.unrouted-tail",
                "claim_value": "invalid",
                "source": "experiment:a0_3b:test",
                "derivation": "experiment:a0_3b:test:v1",
            },
        )
        conn.commit()
    finally:
        conn.close()
    raw = sqlite3.connect(path)
    try:
        before = int(raw.execute("SELECT COUNT(*) FROM event_log").fetchone()[0])
    finally:
        raw.close()

    with pytest.raises(harness.ShadowHarnessError, match="INVALID_UNROUTED_TAIL"):
        harness.cutover_shadow(path, disposable_root=tmp_path)
    with pytest.raises(harness.ShadowHarnessError, match="INVALID_UNROUTED_TAIL"):
        harness.active_reader(path, disposable_root=tmp_path)
    with pytest.raises(harness.ShadowHarnessError, match="INVALID_UNROUTED_TAIL"):
        harness.append_routed(
            path,
            "assertion_recorded",
            {
                "claim_key": "a03b.unrouted-tail.retry",
                "claim_value": "must-not-commit",
                "source": "experiment:a0_3b:test",
                "derivation": "experiment:a0_3b:test:v1",
            },
            disposable_root=tmp_path,
        )
    raw = sqlite3.connect(path)
    try:
        assert int(raw.execute("SELECT COUNT(*) FROM event_log").fetchone()[0]) == before
    finally:
        raw.close()
    recovered = harness.recover(path, disposable_root=tmp_path)
    assert recovered["classification"] == "INVALID_UNROUTED_TAIL"
    assert recovered["reader_ready"] is False
    assert recovered["writer_ready"] is False


@pytest.mark.parametrize(
    "tamper_sql",
    [
        "UPDATE a03b_generation SET role=CASE generation_id "
        "WHEN 'g2' THEN 'verifier' WHEN 'g3' THEN 'shadow' ELSE role END",
        "UPDATE a03b_generation SET state='building' WHERE generation_id='g2'",
    ],
)
def test_role_or_state_topology_tamper_rolls_back_routed_write_in_same_transaction(
    tmp_path: Path, tamper_sql: str
) -> None:
    path, _ = _prepare_verified(tmp_path, label="topology-tamper")
    conn = sqlite3.connect(path)
    try:
        conn.execute(tamper_sql)
        conn.commit()
        before = int(conn.execute("SELECT COUNT(*) FROM event_log").fetchone()[0])
    finally:
        conn.close()

    with pytest.raises(harness.ShadowHarnessError):
        harness.append_routed(
            path,
            "assertion_recorded",
            {
                "claim_key": "a03b.topology-tamper",
                "claim_value": "must-not-commit",
                "source": "experiment:a0_3b:test",
                "derivation": "experiment:a0_3b:test:v1",
            },
            disposable_root=tmp_path,
        )
    conn = sqlite3.connect(path)
    try:
        assert int(conn.execute("SELECT COUNT(*) FROM event_log").fetchone()[0]) == before
    finally:
        conn.close()
    with pytest.raises(harness.ShadowHarnessError):
        harness.active_reader(path, disposable_root=tmp_path)
    recovered = harness.recover(path, disposable_root=tmp_path)
    assert recovered["classification"].startswith("INVALID_")
    assert recovered["reader_ready"] is False
    assert recovered["writer_ready"] is False


@pytest.mark.parametrize(
    ("batch_events", "batch_bytes"),
    [
        (harness.MAX_BATCH_EVENTS + 1, BATCH_BYTES),
        (BATCH_EVENTS, harness.MAX_BATCH_BYTES + 1),
    ],
)
def test_batch_configuration_hard_caps_fail_before_any_shadow_progress(
    tmp_path: Path, batch_events: int, batch_bytes: int
) -> None:
    path, _ = _synthetic(tmp_path, 9, label="hard-batch-cap")
    harness.initialize_shadow(path, disposable_root=tmp_path)
    with pytest.raises(harness.ShadowHarnessError, match="hard cap"):
        harness.build_shadow(
            path,
            disposable_root=tmp_path,
            batch_events=batch_events,
            batch_bytes=batch_bytes,
        )
    status = harness.generation_status(path, disposable_root=tmp_path)
    assert _generation(status, "g2")["built_event_count"] == 0


def test_every_public_batched_api_rejects_over_cap_input_before_work(
    tmp_path: Path,
) -> None:
    path, _ = _synthetic(tmp_path, 5, label="all-public-caps")
    harness.initialize_shadow(path, disposable_root=tmp_path)
    over_events = harness.MAX_BATCH_EVENTS + 1

    with pytest.raises(harness.ShadowHarnessError, match="hard cap"):
        harness.catch_up_shadow(
            path,
            disposable_root=tmp_path,
            batch_events=over_events,
            batch_bytes=BATCH_BYTES,
        )
    with pytest.raises(harness.ShadowHarnessError, match="hard cap"):
        harness.stream_generation_digests(
            path,
            "g1",
            disposable_root=tmp_path,
            batch_events=over_events,
        )
    with pytest.raises(harness.ShadowHarnessError, match="hard cap"):
        harness.verify_shadow(
            path,
            disposable_root=tmp_path,
            batch_events=over_events,
            batch_bytes=BATCH_BYTES,
            atomic_cutover=True,
        )
    with pytest.raises(harness.ShadowHarnessError, match="hard cap"):
        harness.verify_shadow(
            path,
            disposable_root=tmp_path,
            batch_events=BATCH_EVENTS,
            batch_bytes=BATCH_BYTES,
            max_admission_tail_events=over_events,
            atomic_cutover=True,
        )
    with pytest.raises(harness.ShadowHarnessError, match="hard cap"):
        harness.cutover_shadow(
            path,
            disposable_root=tmp_path,
            max_tail_events=over_events,
        )
    with pytest.raises(harness.ShadowHarnessError, match="hard cap"):
        harness.run_concurrency_probe(
            path,
            disposable_root=tmp_path,
            batch_events=over_events,
            batch_bytes=BATCH_BYTES,
        )
    with pytest.raises(harness.ShadowHarnessError, match="hard cap"):
        harness.run_shadow_prototype(
            path,
            disposable_root=tmp_path,
            batch_events=over_events,
            batch_bytes=BATCH_BYTES,
        )
    with harness.active_reader(path, disposable_root=tmp_path) as reader:
        with pytest.raises(harness.ShadowHarnessError, match="hard cap"):
            reader.digest(over_events)
    with pytest.raises(harness.ShadowHarnessError, match="telemetry input"):
        harness.writer_latency_summary([{}] * (harness.MAX_WRITER_TELEMETRY_SAMPLES + 1))
    with pytest.raises(harness.ShadowHarnessError, match="round/gap"):
        harness.catch_up_shadow(
            path,
            disposable_root=tmp_path,
            batch_events=BATCH_EVENTS,
            batch_bytes=BATCH_BYTES,
            max_rounds=10_001,
        )


def test_writer_telemetry_truncation_forces_concurrency_gate_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, _ = _synthetic(tmp_path, 65, label="truncated-writer-evidence")
    harness.initialize_shadow(path, disposable_root=tmp_path)
    monkeypatch.setattr(harness, "MAX_WRITER_TELEMETRY_SAMPLES", 1)

    receipt = harness.run_concurrency_probe(
        path,
        disposable_root=tmp_path,
        writer_interval_seconds=0.001,
        short_reader_interval_seconds=0.002,
        batch_events=8,
        batch_bytes=BATCH_BYTES,
    )
    latency = receipt["writer_latency"]
    assert latency["total_sample_count"] > latency["sample_count"]
    assert latency["sample_count"] == 1
    assert latency["samples_truncated"] is True
    assert latency["dropped_sample_count"] > 0
    assert latency["starvation"] is True
    assert latency["within_max_block_budget"] is False
    assert receipt["writer_evidence_complete"] is False
    assert receipt["concurrency_gate_pass"] is False


def test_batch_aggregate_keeps_only_bounded_first_and_last_telemetry() -> None:
    aggregate = harness.BatchAggregate()
    for index in range(200):
        aggregate.add(
            harness.BatchMeasurement(
                generation_id="g2",
                phase="bounded-test",
                first_event_id=index,
                last_event_id=index,
                event_count=1,
                payload_bytes=64,
                transaction_seconds=index / 1_000_000,
                receipt_sha256=f"{index:064x}",
            )
        )
    samples = aggregate.receipt_samples()
    assert aggregate.batch_count == 200
    assert aggregate.processed_events == 200
    assert len(samples) == 2 * harness.BatchAggregate.SAMPLE_LIMIT
    assert [sample["first_event_id"] for sample in samples[:32]] == list(range(32))
    assert [sample["first_event_id"] for sample in samples[-32:]] == list(range(168, 200))


def test_cli_output_root_is_fresh_immediate_child_and_never_overwritten(
    tmp_path: Path,
) -> None:
    existing = tmp_path / "existing-output"
    existing.mkdir()
    sentinel = existing / "do-not-overwrite.txt"
    sentinel.write_text("owned", encoding="utf-8")

    with pytest.raises(FileExistsError, match="must be fresh"):
        a03b_cli._output_dir(existing, tmp_path)
    assert sentinel.read_text(encoding="utf-8") == "owned"

    nested_parent = tmp_path / "nested"
    nested_parent.mkdir()
    with pytest.raises(a03a.DisposableTargetError, match="immediate child"):
        a03b_cli._output_dir(nested_parent / "output", tmp_path)

    fresh = tmp_path / "fresh-output"
    output, root = a03b_cli._output_dir(fresh, tmp_path)
    assert output == fresh.resolve()
    assert root == tmp_path.resolve()
    assert output.is_dir()


@pytest.mark.parametrize(
    "phase",
    [
        "initialization_ddl_and_metadata",
        "operation_claim",
        "operation_release",
        "generation_prepare_metadata:g2",
        "generation_target_metadata:g2",
        "bounded_projection_purge",
        "bounded_metadata_purge",
        "bounded_sequence_purge",
        "projection_batch:g2:shadow_build",
        "projection_batch:g2:catch_up",
        "catch_up_state_transition",
        "verification_session_reset",
        "verification_state_transition",
        "verification_receipts_and_sync_session",
        "sync_pair_batch:sync_prepare",
        "a_bounded_admission_and_cutover",
        "b_sync_admission",
        "b_metadata_only_cutover",
        "routed_writer",
        "recovery_stale_lease_cleanup",
        "recovery_writer_readiness_probe",
    ],
)
def test_every_write_transaction_class_fails_its_gate_above_two_seconds(
    phase: str,
) -> None:
    collector = harness._WriteTxnCollector("phase-budget-regression")
    collector.attempted(phase)
    collector.opened(phase, 0.0)
    collector.finished(
        phase,
        committed=True,
        transaction_seconds=harness.WRITER_BLOCK_BUDGET_SECONDS + 0.001,
    )

    receipt = collector.receipt()
    assert receipt["exhaustive"] is True
    assert receipt["evidence_complete"] is True
    assert receipt["phase_max_transaction_seconds"][phase] > 2.0
    assert receipt["overall_max_transaction_seconds"] > 2.0
    assert receipt["pass"] is False


@pytest.mark.parametrize(
    ("scope", "specific_budget"),
    [
        ("initialize_shadow", "initialization_write_transactions"),
        ("build_shadow", "build_write_transactions"),
        ("catch_up_shadow", "catch_up_write_transactions"),
        ("verify_shadow", "verification_sync_and_cutover_write_transactions"),
        ("recover", "recovery"),
    ],
)
def test_prototype_budget_cannot_false_pass_a_slow_child_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scope: str,
    specific_budget: str,
) -> None:
    path, _ = _synthetic(tmp_path, 1, label=f"slow-{scope}")
    original_receipt = harness._WriteTxnCollector.receipt

    def receipt_with_slow_phase(
        collector: harness._WriteTxnCollector, *, exhaustive: bool = True
    ) -> dict[str, Any]:
        receipt = original_receipt(collector, exhaustive=exhaustive)
        if collector.scope != scope:
            return receipt
        slow = harness.WRITER_BLOCK_BUDGET_SECONDS + 0.001
        phase_stats = {phase: dict(values) for phase, values in receipt["phase_stats"].items()}
        phase = next(iter(phase_stats))
        phase_stats[phase]["max_transaction_seconds"] = slow
        return {
            **receipt,
            "phase_stats": phase_stats,
            "phase_max_transaction_seconds": {
                **receipt["phase_max_transaction_seconds"],
                phase: slow,
            },
            "overall_max_transaction_seconds": slow,
            "overall_max_seconds": slow,
            "pass": False,
        }

    monkeypatch.setattr(harness._WriteTxnCollector, "receipt", receipt_with_slow_phase)
    result = harness.run_shadow_prototype(
        path,
        disposable_root=tmp_path,
        batch_events=1,
        batch_bytes=BATCH_BYTES,
    )

    all_writes = result["budgets"]["all_experimental_write_transactions"]
    assert result["write_transactions"]["claim"] == ("all_experimental_write_transactions")
    assert all_writes["evidence_complete"] is True
    assert all_writes["measured_seconds"] > 2.0
    assert all_writes["pass"] is False
    assert result["budgets"][specific_budget]["pass"] is False
    assert result["budgets_pass"] is False


def test_prototype_sampler_is_active_before_initialization_and_keeps_its_highwater(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, _ = _synthetic(tmp_path, 1, label="sampler-before-init")
    active_samplers: list[harness._ResourceSampler] = []
    original_enter = harness._ResourceSampler.__enter__
    original_exit = harness._ResourceSampler.__exit__
    original_initialize = harness.initialize_shadow
    rss_sentinel = 100 * 1024 * 1024
    wal_sentinel = 100 * 1024 * 1024

    def enter(sampler: harness._ResourceSampler) -> harness._ResourceSampler:
        entered = original_enter(sampler)
        active_samplers.append(sampler)
        return entered

    def exit_sampler(
        sampler: harness._ResourceSampler,
        exc_type: Any,
        exc: Any,
        traceback: Any,
    ) -> None:
        try:
            original_exit(sampler, exc_type, exc, traceback)
        finally:
            active_samplers.remove(sampler)

    def initialize(*args: Any, **kwargs: Any) -> dict[str, Any]:
        assert len(active_samplers) == 1
        outer = active_samplers[0]
        outer.peak_rss_bytes = max(outer.peak_rss_bytes, rss_sentinel)
        outer.highwater["wal"] = max(outer.highwater["wal"], wal_sentinel)
        return original_initialize(*args, **kwargs)

    monkeypatch.setattr(harness._ResourceSampler, "__enter__", enter)
    monkeypatch.setattr(harness._ResourceSampler, "__exit__", exit_sampler)
    monkeypatch.setattr(harness, "initialize_shadow", initialize)

    result = harness.run_shadow_prototype(
        path,
        disposable_root=tmp_path,
        batch_events=1,
        batch_bytes=BATCH_BYTES,
    )
    assert result["peak_rss_bytes"] >= rss_sentinel
    assert result["storage_highwater_bytes"]["wal"] >= wal_sentinel
    assert not active_samplers


def test_all_108_projection_dml_guards_default_deny_a_foreign_connection_at_hstar(
    tmp_path: Path,
) -> None:
    candidate = golden.load_candidate()
    conn = golden.import_fixture(tmp_path / "guard-golden-import", candidate)
    path = golden.database_file(conn)
    conn.execute("BEGIN IMMEDIATE")
    a03a.replay_bounded_in_txn(conn, a03a.capture_fence(conn), 7)
    conn.commit()
    conn.close()
    a03a.register_disposable_database(path, tmp_path)
    harness.initialize_shadow(path, disposable_root=tmp_path)
    harness.build_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=7,
        batch_bytes=BATCH_BYTES,
    )
    verified = harness.verify_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=7,
        batch_bytes=BATCH_BYTES,
        atomic_cutover=False,
    )
    assert verified["sync_admission"]["outcome"] == "sync_armed"
    harness.append_routed(
        path,
        "assertion_recorded",
        {
            "claim_key": "a03b.guard.hstar",
            "claim_value": "routed",
            "source": "experiment:a0_3b:test",
            "derivation": "experiment:a0_3b:test:v1",
        },
        disposable_root=tmp_path,
    )

    def quoted(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    foreign = sqlite3.connect(path)
    try:
        triggers = foreign.execute(
            "SELECT name,tbl_name FROM sqlite_schema WHERE type='trigger' "
            "AND name GLOB 'a03b_g[123]__protect_*' ORDER BY name"
        ).fetchall()
        assert len(triggers) == 3 * len(harness.PROJECTION_TABLES) * 3 == 108
        before = {
            str(table): int(
                foreign.execute(f"SELECT COUNT(*) FROM {quoted(str(table))}").fetchone()[0]
            )
            for _, table in triggers
        }
        assert all(count > 0 for count in before.values())

        for name, raw_table in triggers:
            table = str(raw_table)
            action = str(name).split("__protect_", 1)[1].split("__", 1)[0]
            first_column = str(foreign.execute(f"PRAGMA table_info({quoted(table)})").fetchone()[1])
            if action == "insert":
                statement = f"INSERT INTO {quoted(table)} SELECT * FROM {quoted(table)} LIMIT 1"
            elif action == "update":
                statement = (
                    f"UPDATE {quoted(table)} SET {quoted(first_column)}="
                    f"{quoted(first_column)} WHERE {quoted(first_column)}=(SELECT "
                    f"{quoted(first_column)} FROM {quoted(table)} LIMIT 1)"
                )
            else:
                assert action == "delete"
                statement = (
                    f"DELETE FROM {quoted(table)} WHERE {quoted(first_column)}=(SELECT "
                    f"{quoted(first_column)} FROM {quoted(table)} LIMIT 1)"
                )
            with pytest.raises(
                sqlite3.DatabaseError,
                match="projection_write_allowed|unrouted projection write",
            ):
                foreign.execute(statement)
            foreign.rollback()

        after = {
            table: int(foreign.execute(f"SELECT COUNT(*) FROM {quoted(table)}").fetchone()[0])
            for table in before
        }
        assert after == before
    finally:
        foreign.close()

    assert harness.cutover_shadow(path, disposable_root=tmp_path)["outcome"] == "complete_new"
    assert harness.recover(path, disposable_root=tmp_path)["classification"] == (
        "NEW_ACTIVE_OLD_RETIRED"
    )


@pytest.mark.parametrize("mutation", ["drop", "replace"])
def test_projection_guard_inventory_tamper_fails_even_after_stored_hash_is_rebased(
    tmp_path: Path, mutation: str
) -> None:
    path, _ = _synthetic(tmp_path, 1, label=f"guard-{mutation}")
    harness.initialize_shadow(path, disposable_root=tmp_path)

    foreign = sqlite3.connect(path)
    try:
        name, table = foreign.execute(
            "SELECT name,tbl_name FROM sqlite_schema WHERE type='trigger' "
            "AND name GLOB 'a03b_g2__protect_insert__*' ORDER BY name LIMIT 1"
        ).fetchone()
        foreign.execute(f'DROP TRIGGER "{name}"')
        if mutation == "replace":
            foreign.execute(
                f'CREATE TRIGGER "{name}" BEFORE INSERT ON "{table}" '
                "BEGIN SELECT RAISE(ABORT,'changed guard'); END"
            )
        foreign.execute(
            "UPDATE a03b_control SET exact_schema_sha256=? WHERE singleton=1",
            (harness._schema_sha256(foreign),),
        )
        foreign.commit()
    finally:
        foreign.close()

    with pytest.raises(
        harness.SchemaInventoryError,
        match="projection write-guard inventory changed|projection write guard changed",
    ):
        harness.generation_status(path, disposable_root=tmp_path)
    recovered = harness.recover(path, disposable_root=tmp_path)
    assert recovered["classification"] == "INVALID_INVENTORY"
    assert recovered["reader_ready"] is False
    assert recovered["writer_ready"] is False


def test_foreign_sqlite_sequence_tamper_after_validation_stops_a_before_pointer(
    tmp_path: Path,
) -> None:
    path, _ = _synthetic(
        tmp_path,
        17,
        label="sequence-tamper-a",
    )
    harness.initialize_shadow(path, disposable_root=tmp_path)
    harness.build_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
    )
    tampered = False

    def fault(phase: str, _evidence: Mapping[str, Any]) -> None:
        nonlocal tampered
        if phase != "validation_post_commit" or tampered:
            return
        foreign = sqlite3.connect(path)
        try:
            physical, _ = _existing_relation_sequence(foreign, "g2")
            changed = foreign.execute(
                "UPDATE sqlite_sequence SET seq=seq+1000 WHERE name=?",
                (physical,),
            ).rowcount
            assert changed == 1
            foreign.commit()
        finally:
            foreign.close()
        tampered = True

    with pytest.raises(harness.ShadowHarnessError, match="INVALID_SEQUENCE_STATE"):
        harness.verify_shadow(
            path,
            disposable_root=tmp_path,
            batch_events=BATCH_EVENTS,
            batch_bytes=BATCH_BYTES,
            atomic_cutover=True,
            fault=fault,
        )
    assert tampered is True
    raw = sqlite3.connect(path)
    try:
        assert (
            raw.execute(
                "SELECT active_generation_id FROM a03b_control WHERE singleton=1"
            ).fetchone()[0]
            == "g1"
        )
    finally:
        raw.close()
    recovered = harness.recover(path, disposable_root=tmp_path)
    assert recovered["classification"].startswith("INVALID_")
    assert recovered["reader_ready"] is False
    assert recovered["writer_ready"] is False


def test_armed_b_sequence_tamper_blocks_digest_writer_cutover_and_recovery(
    tmp_path: Path,
) -> None:
    path, prepared = _prepare_verified(tmp_path, event_count=17, label="sequence-tamper-armed-b")
    assert prepared["verified"]["sync_admission"]["outcome"] == "sync_armed"
    foreign = sqlite3.connect(path)
    try:
        event_count = int(foreign.execute("SELECT COUNT(*) FROM event_log").fetchone()[0])
        stored_digest = str(
            foreign.execute(
                "SELECT sequence_digest_sha256 FROM a03b_generation WHERE generation_id='g2'"
            ).fetchone()[0]
        )
        physical, original_sequence = _existing_relation_sequence(foreign, "g2")
        foreign.execute("UPDATE sqlite_sequence SET seq=seq+1000 WHERE name=?", (physical,))
        foreign.commit()
    finally:
        foreign.close()

    with pytest.raises(harness.ShadowHarnessError, match="INVALID_SEQUENCE_STATE"):
        harness.stream_generation_digests(
            path, "g2", disposable_root=tmp_path, batch_events=BATCH_EVENTS
        )
    with pytest.raises(harness.ShadowHarnessError, match="INVALID_SEQUENCE_STATE"):
        harness.append_routed(
            path,
            "assertion_recorded",
            {
                "claim_key": "a03b.sequence.tamper",
                "claim_value": "must-not-append",
                "source": "experiment:a0_3b:test",
                "derivation": "experiment:a0_3b:test:v1",
            },
            disposable_root=tmp_path,
        )
    with pytest.raises(harness.ShadowHarnessError, match="INVALID_SEQUENCE_STATE"):
        harness.cutover_shadow(path, disposable_root=tmp_path)

    foreign = sqlite3.connect(path)
    try:
        assert (
            foreign.execute(
                "SELECT active_generation_id FROM a03b_control WHERE singleton=1"
            ).fetchone()[0]
            == "g1"
        )
        assert int(foreign.execute("SELECT COUNT(*) FROM event_log").fetchone()[0]) == event_count
        assert (
            str(
                foreign.execute(
                    "SELECT sequence_digest_sha256 FROM a03b_generation WHERE generation_id='g2'"
                ).fetchone()[0]
            )
            == stored_digest
        )
        assert (
            int(
                foreign.execute(
                    "SELECT seq FROM sqlite_sequence WHERE name=?", (physical,)
                ).fetchone()[0]
            )
            == original_sequence + 1000
        )
    finally:
        foreign.close()
    recovered = harness.recover(path, disposable_root=tmp_path)
    assert recovered["classification"].startswith("INVALID_")
    assert recovered["reader_ready"] is False
    assert recovered["writer_ready"] is False


@pytest.mark.parametrize("generation_id", ["g1", "g2", "g3"])
def test_postcut_sequence_tamper_in_any_generation_blocks_read_write_and_recovery(
    tmp_path: Path, generation_id: str
) -> None:
    path, _ = _synthetic(tmp_path, 9, label=f"postcut-sequence-{generation_id}")
    result = harness.run_shadow_prototype(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
    )
    assert result["active_generation_id"] == "g2"
    harness.append_routed(
        path,
        "assertion_recorded",
        {
            "claim_key": "a03b.sequence.legitimate",
            "claim_value": "post-cutover",
            "source": "experiment:a0_3b:test",
            "derivation": "experiment:a0_3b:test:v1",
        },
        disposable_root=tmp_path,
    )
    assert harness.recover(path, disposable_root=tmp_path)["classification"] == (
        "NEW_ACTIVE_OLD_RETIRED"
    )

    foreign = sqlite3.connect(path)
    try:
        event_count = int(foreign.execute("SELECT COUNT(*) FROM event_log").fetchone()[0])
        stored_digest = str(
            foreign.execute(
                "SELECT sequence_digest_sha256 FROM a03b_generation WHERE generation_id=?",
                (generation_id,),
            ).fetchone()[0]
        )
        physical, original_sequence = _existing_relation_sequence(foreign, generation_id)
        assert (
            foreign.execute(
                "UPDATE sqlite_sequence SET seq=seq+1000 WHERE name=?", (physical,)
            ).rowcount
            == 1
        )
        foreign.commit()
    finally:
        foreign.close()

    with pytest.raises(harness.ShadowHarnessError, match="INVALID_SEQUENCE_STATE"):
        harness.stream_generation_digests(
            path,
            generation_id,
            disposable_root=tmp_path,
            batch_events=BATCH_EVENTS,
        )
    with pytest.raises(harness.ShadowHarnessError, match="INVALID_SEQUENCE_STATE"):
        harness.active_reader(path, disposable_root=tmp_path)
    with pytest.raises(harness.ShadowHarnessError, match="INVALID_SEQUENCE_STATE"):
        harness.append_routed(
            path,
            "assertion_recorded",
            {
                "claim_key": "a03b.sequence.must-stop",
                "claim_value": generation_id,
                "source": "experiment:a0_3b:test",
                "derivation": "experiment:a0_3b:test:v1",
            },
            disposable_root=tmp_path,
        )
    recovered = harness.recover(path, disposable_root=tmp_path)
    assert recovered["classification"].startswith("INVALID_")
    assert recovered["reader_ready"] is False
    assert recovered["writer_ready"] is False

    foreign = sqlite3.connect(path)
    try:
        assert int(foreign.execute("SELECT COUNT(*) FROM event_log").fetchone()[0]) == event_count
        assert (
            str(
                foreign.execute(
                    "SELECT sequence_digest_sha256 FROM a03b_generation WHERE generation_id=?",
                    (generation_id,),
                ).fetchone()[0]
            )
            == stored_digest
        )
        assert (
            int(
                foreign.execute(
                    "SELECT seq FROM sqlite_sequence WHERE name=?", (physical,)
                ).fetchone()[0]
            )
            == original_sequence + 1000
        )
    finally:
        foreign.close()


@pytest.mark.parametrize(
    ("fault_phase", "expected_exception"),
    [
        ("g3_bounded_purge_opened", harness.InjectedFault),
        ("g3_bounded_purge_batch_pre_commit", harness.InjectedFault),
        ("g3_bounded_purge_batch_committed", harness.InjectedFault),
        ("g3_bounded_purge_complete", harness.InjectedFault),
        ("g3_second_replay_opened", harness.InjectedFault),
        ("g3_second_replay_batch_opened", harness.InjectedFault),
        ("g3_second_replay_batch_pre_commit", harness.InjectedFault),
        ("g3_second_replay_batch_post_commit", harness.PostCommitFault),
        ("g3_second_replay_complete", harness.InjectedFault),
    ],
)
def test_g3_purge_and_second_replay_fault_boundaries_reopen_and_retry(
    tmp_path: Path,
    fault_phase: str,
    expected_exception: type[BaseException],
) -> None:
    path, _ = _synthetic(tmp_path, 9, label=f"g3-fault-{fault_phase}")
    harness.initialize_shadow(path, disposable_root=tmp_path)
    harness.build_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
    )

    def fault(phase: str, _evidence: Mapping[str, Any]) -> None:
        if phase == fault_phase:
            raise harness.InjectedFault(f"fault at {fault_phase}")

    with pytest.raises(expected_exception, match="fault|after commit"):
        harness.verify_shadow(
            path,
            disposable_root=tmp_path,
            batch_events=BATCH_EVENTS,
            batch_bytes=BATCH_BYTES,
            atomic_cutover=True,
            fault=fault,
        )
    reopened = harness.recover(path, disposable_root=tmp_path)
    assert reopened["classification"] == "OLD_ACTIVE_SHADOW_RESUMABLE"
    assert reopened["active_generation_id"] == "g1"

    retry = harness.verify_shadow(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
        atomic_cutover=True,
    )
    assert retry["cutover"]["outcome"] == "complete_new"
    assert harness.recover(path, disposable_root=tmp_path)["classification"] == (
        "NEW_ACTIVE_OLD_RETIRED"
    )


def test_complete_prototype_reports_exhaustive_write_transaction_classes(
    tmp_path: Path,
) -> None:
    path, _ = _synthetic(tmp_path, 9, label="exhaustive-write-classes")
    result = harness.run_shadow_prototype(
        path,
        disposable_root=tmp_path,
        batch_events=BATCH_EVENTS,
        batch_bytes=BATCH_BYTES,
    )
    writes = result["write_transactions"]
    phases = set(writes["phase_stats"])
    assert {
        "initialization_ddl_and_metadata",
        "operation_claim",
        "operation_release",
        "generation_prepare_metadata:g2",
        "generation_prepare_metadata:g3",
        "generation_target_metadata:g2",
        "bounded_projection_purge",
        "bounded_metadata_purge",
        "bounded_sequence_purge",
        "projection_batch:g2:shadow_build",
        "projection_batch:g3:independent_replay",
        "catch_up_state_transition",
        "verification_session_reset",
        "verification_state_transition",
        "verification_receipts_and_sync_session",
        "a_bounded_admission_and_cutover",
        "recovery_writer_readiness_probe",
    } <= phases
    assert writes["claim"] == "all_experimental_write_transactions"
    assert writes["exhaustive"] is True
    assert writes["evidence_complete"] is True
    assert writes["attempt_count"] == (writes["transaction_count"] + writes["begin_error_count"])
    assert writes["transaction_count"] == (writes["committed_count"] + writes["rolled_back_count"])
    assert writes["open_transaction_count"] == 0
    assert writes["pass"] is True
    assert result["budgets"]["all_experimental_write_transactions"]["pass"] is True
    assert result["budgets_pass"] is True

    appended = harness.append_routed(
        path,
        "assertion_recorded",
        {
            "claim_key": "a03b.write-class.post-cutover",
            "claim_value": "recorded",
            "source": "experiment:a0_3b:test",
            "derivation": "experiment:a0_3b:test:v1",
        },
        disposable_root=tmp_path,
    )
    writer_writes = appended["write_transactions"]
    assert set(writer_writes["phase_stats"]) == {"routed_writer"}
    assert writer_writes["evidence_complete"] is True
    assert writer_writes["pass"] is True


def test_incomplete_write_evidence_never_claims_all_transactions() -> None:
    collector = harness._WriteTxnCollector("incomplete-evidence")
    collector.attempted("transaction_never_opened")

    merged = harness._merge_write_transaction_receipts("incomplete-merge", (collector.receipt(),))
    assert merged["evidence_complete"] is False
    assert merged["exhaustive"] is False
    assert merged["pass"] is False
    assert "claim" not in merged


def test_generation_connection_rewrite_cache_is_effective_and_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE a03b_g2__value_projection (value TEXT)")
    real_rewrite = harness._rewrite_projection_sql
    rewrite_calls = 0

    def observe_rewrite(sql: str, mapping: Mapping[str, str]) -> str:
        nonlocal rewrite_calls
        rewrite_calls += 1
        return real_rewrite(sql, mapping)

    monkeypatch.setattr(harness, "_rewrite_projection_sql", observe_rewrite)
    adapter = harness.GenerationConnection(conn, "g2")
    repeated = "SELECT COUNT(*) FROM value_projection"
    try:
        for _ in range(20):
            assert adapter.execute(repeated).fetchone()[0] == 0
        assert rewrite_calls == 1

        for value in range(harness._GENERATION_SQL_CACHE_LIMIT * 2):
            assert adapter.execute(f"SELECT {value + 1000}").fetchone()[0] == value + 1000
        assert len(adapter._rewrite_cache) == harness._GENERATION_SQL_CACHE_LIMIT

        before = rewrite_calls
        assert adapter.execute(repeated).fetchone()[0] == 0
        assert rewrite_calls == before
    finally:
        conn.close()
