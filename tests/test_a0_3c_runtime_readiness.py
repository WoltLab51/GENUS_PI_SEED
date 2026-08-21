from __future__ import annotations

import copy
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

import pytest

from experiments.a0_3a import harness as a03a
from experiments.a0_3c import __main__ as cli
from experiments.a0_3c import harness
from tests import golden_ledger_support as golden


COMMIT = "1" * 40
ZERO = "0" * 64
CODE_ROOT = Path(__file__).resolve().parents[1]


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for key, item in value.items():
            yield key
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


def _target_identity() -> dict[str, Any]:
    value = harness.runtime_identity()
    fingerprint = value["runtime_fingerprint"]
    fingerprint.update(
        {
            "python_version": "3.13.15",
            "python_version_info": [3, 13, 15],
            "required_python_version_info": [3, 13, 15],
            "sqlite_version": "3.53.4",
            "sqlite_version_info": [3, 53, 4],
            "required_sqlite_version_info": [3, 53, 4],
            "sqlite_source_id": harness.REQUIRED_SQLITE_SOURCE_ID,
            "required_sqlite_source_id": harness.REQUIRED_SQLITE_SOURCE_ID,
            "wal_reset_fix_gate_pass": True,
            "exact_runtime_gate_pass": True,
            "target_series_match": True,
            "virtual_environment": True,
        }
    )
    value["environment"]["virtual_environment"] = True
    value["runtime_fingerprint_sha256"] = harness._sha256_json(fingerprint)
    value.pop("identity_sha256", None)
    value["identity_sha256"] = harness._sha256_json(value)
    return value


def _private_dir(path: Path) -> Path:
    path.mkdir()
    os.chmod(path, 0o700)
    return path


def _gate_files(tmp_path: Path, identity: Mapping[str, Any]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for index, gate in enumerate(sorted(harness.GATE_COMMANDS), start=1):
        receipt = harness.create_gate_receipt(
            gate=gate,
            candidate_commit=COMMIT,
            exit_status=0,
            stdout_sha256=f"{index:x}" * 64,
            stderr_sha256=ZERO,
            test_count=10 + index,
            identity=identity,
        )
        path = tmp_path / f"{gate}.json"
        harness.write_json_evidence(path, receipt)
        result[gate] = path
    return result


def _manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[dict[str, Any], dict[str, Any]]:
    identity = _target_identity()
    monkeypatch.setattr(
        harness, "runtime_identity", lambda *args, **kwargs: copy.deepcopy(identity)
    )
    manifest = harness.create_runtime_manifest(
        code_root=CODE_ROOT,
        candidate_commit=COMMIT,
        gate_receipt_paths=_gate_files(tmp_path, identity),
        identity=identity,
    )
    return manifest, identity


def _golden_source(tmp_path: Path) -> tuple[Path, Path, Path]:
    candidate = golden.load_candidate()
    import_root = tmp_path / "import"
    conn = golden.import_fixture(import_root, candidate)
    path = golden.database_file(conn)
    conn.execute("BEGIN IMMEDIATE")
    a03a.replay_bounded_in_txn(conn, a03a.capture_fence(conn), 7)
    conn.commit()
    conn.close()
    core_id = tmp_path / "core-id"
    core_id.write_text(candidate.anchor["core_id"] + "\n", encoding="utf-8")
    anchor_dir = CODE_ROOT / "tests" / "fixtures" / "golden_ledger_v1"
    return path, core_id, anchor_dir


def _acquire(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, Any], dict[str, Any], Path, Path]:
    manifest, _ = _manifest(tmp_path, monkeypatch)
    source, core_id, anchor_dir = _golden_source(tmp_path)
    source_before = source.read_bytes()
    root = _private_dir(tmp_path / "acquisition")
    receipt = harness.acquire_product_copies(
        source,
        disposable_root=root,
        core_id_file=core_id,
        anchor_dir=anchor_dir,
        manifest=manifest,
        code_root=CODE_ROOT,
        expected_candidate_commit=COMMIT,
    )
    assert source.read_bytes() == source_before
    return receipt, manifest, root, source


def test_runtime_identity_is_path_free_and_binds_loaded_binaries() -> None:
    identity = harness.runtime_identity()
    fingerprint = identity["runtime_fingerprint"]
    assert identity["schema"] == harness.RUNTIME_IDENTITY_SCHEMA
    assert identity["identity_sha256"] == harness._sha256_json(
        {key: item for key, item in identity.items() if key != "identity_sha256"}
    )
    assert identity["runtime_fingerprint_sha256"] == harness._sha256_json(fingerprint)
    assert len(fingerprint["compile_options_sha256"]) == 64
    assert fingerprint["python_binary"]["file_bytes"] > 0
    assert len(fingerprint["python_binary"]["file_sha256"]) == 64
    assert fingerprint["sqlite_extension"]["module_file_bytes"] > 0
    assert identity["paths_logged"] is False
    for value in _strings(identity):
        assert not value.startswith(("/", "\\\\"))
        assert not (len(value) > 2 and value[1:3] in {":\\", ":/"})


def test_local_runtime_does_not_silently_pass_exact_target() -> None:
    identity = harness.runtime_identity()
    fingerprint = identity["runtime_fingerprint"]
    expected = (
        tuple(fingerprint["python_version_info"]) == (3, 13, 15)
        and tuple(fingerprint["sqlite_version_info"]) == (3, 53, 4)
        and fingerprint["sqlite_source_id"] == harness.REQUIRED_SQLITE_SOURCE_ID
        and identity["environment"]["virtual_environment"] is True
    )
    assert fingerprint["exact_runtime_gate_pass"] is expected


def test_runtime_validator_rejects_minimum_only_runtime() -> None:
    identity = _target_identity()
    fingerprint = identity["runtime_fingerprint"]
    fingerprint["sqlite_version"] = "3.53.3"
    fingerprint["sqlite_version_info"] = [3, 53, 3]
    fingerprint["exact_runtime_gate_pass"] = False
    identity["runtime_fingerprint_sha256"] = harness._sha256_json(fingerprint)
    identity.pop("identity_sha256")
    identity["identity_sha256"] = harness._sha256_json(identity)
    with pytest.raises(harness.RuntimeManifestError, match="exact"):
        harness._validate_runtime_identity(identity, True)


def test_gate_commands_are_fixed_and_use_external_placeholder() -> None:
    assert set(harness.GATE_COMMANDS) == {
        "full_suite",
        "a0_2_golden",
        "a0_2_historical_sqlite",
    }
    for command in harness.GATE_COMMANDS.values():
        assert "{fresh_private_basetemp}" in command
        assert all(".a03c-gate-tmp" not in item for item in command)
    assert harness.GATE_ENVIRONMENT_CONTRACT["python_no_bytecode_flag"] is True
    assert set(harness.GATE_ENVIRONMENT_CONTRACT["removed"]) >= {
        "GENUS_DB_PATH",
        "GENUS_CORE_ID",
        "GENUS_PAUSE_FILE",
        "PYTHONPATH",
    }


def test_gate_output_is_hard_capped_during_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_MAX_GATE_OUTPUT_BYTES", 64)
    stdout = tmp_path / "stdout.bin"
    stderr = tmp_path / "stderr.bin"
    exit_status = cli._run_gate_bounded(
        [
            sys.executable,
            "-B",
            "-c",
            "import sys; sys.stdout.write('x' * 100000); sys.stdout.flush()",
        ],
        root=CODE_ROOT,
        gate_env=os.environ,
        stdout_path=stdout,
        stderr_path=stderr,
    )
    assert exit_status == 125
    assert stdout.stat().st_size == 64
    assert stderr.stat().st_size <= 64


def test_manifest_binds_runtime_code_config_and_real_green_gate_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, identity = _manifest(tmp_path, monkeypatch)
    assert manifest["runtime_identity"] == identity
    assert manifest["candidate_config"]["batch_events"] == 3_072
    assert manifest["a0_3b_code_sha256"] == harness.ACCEPTED_A03B_CODE_SHA256
    assert set(manifest["a0_3c_code_sha256"]) == {"package", "cli", "harness", "tests"}
    assert all(item["test_count"] > 0 for item in manifest["gate_evidence"].values())
    verified = harness.verify_runtime_manifest(
        manifest, code_root=CODE_ROOT, expected_candidate_commit=COMMIT, identity=identity
    )
    assert verified["outcome"] == "verified"


def test_manifest_rejects_red_gate_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _target_identity()
    monkeypatch.setattr(harness, "runtime_identity", lambda: copy.deepcopy(identity))
    gates = _gate_files(tmp_path, identity)
    red = harness.create_gate_receipt(
        gate="full_suite",
        candidate_commit=COMMIT,
        exit_status=1,
        stdout_sha256=ZERO,
        stderr_sha256=ZERO,
        test_count=1,
        identity=identity,
    )
    red_path = tmp_path / "red.json"
    harness.write_json_evidence(red_path, red)
    gates["full_suite"] = red_path
    with pytest.raises(harness.RuntimeManifestError, match="green"):
        harness.create_runtime_manifest(
            code_root=CODE_ROOT,
            candidate_commit=COMMIT,
            gate_receipt_paths=gates,
            identity=identity,
        )


def test_manifest_and_gate_tampering_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, identity = _manifest(tmp_path, monkeypatch)
    tampered = copy.deepcopy(manifest)
    tampered["candidate_config"]["batch_events"] = 4_096
    with pytest.raises(harness.RuntimeManifestError, match="digest"):
        harness.verify_runtime_manifest(tampered, code_root=CODE_ROOT, identity=identity)


def test_evidence_writer_is_exclusive_private_and_bounded(tmp_path: Path) -> None:
    target = tmp_path / "receipt.json"
    harness.write_json_evidence(target, {"safe": True})
    assert target.stat().st_nlink == 1
    if os.name == "posix":
        assert target.stat().st_mode & 0o777 == 0o600
    with pytest.raises(harness.RuntimeReadinessError, match="fresh"):
        harness.write_json_evidence(target, {"safe": True})
    with pytest.raises(harness.RuntimeReadinessError, match="byte cap"):
        harness.write_json_evidence(tmp_path / "large.json", {"value": "x" * 100}, limit=16)


def test_receipt_safety_rejects_paths_payload_fields_and_nonfinite() -> None:
    with pytest.raises(harness.RuntimeReadinessError, match="absolute path"):
        harness.assert_receipt_safe({"value": str(Path.cwd().resolve())})
    with pytest.raises(harness.RuntimeReadinessError, match="payload"):
        harness.assert_receipt_safe({"raw_payload": "secret"})
    with pytest.raises(harness.RuntimeReadinessError, match="non-finite"):
        harness.assert_receipt_safe({"value": float("nan")})


def test_acquisition_uses_two_private_siblings_and_leaves_source_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, _, root, source = _acquire(tmp_path, monkeypatch)
    before = source.read_bytes()
    assert receipt["schema"] == harness.ACQUISITION_RECEIPT_SCHEMA
    assert receipt["oracle"]["projection_count"] == 12
    assert receipt["oracle"]["sequence_count"] == 9
    assert receipt["source"]["uri_mode"] == "ro"
    assert receipt["source"]["query_only"] is True
    assert receipt["source"]["isolation_level"] is None
    assert receipt["safety"]["product_write_performed"] is False
    assert source.read_bytes() == before
    writer = root / harness.WRITER_FREE_DATABASE
    concurrent = root / harness.CONCURRENCY_DATABASE
    assert not writer.samefile(concurrent)
    assert writer.stat().st_nlink == concurrent.stat().st_nlink == 1
    assert (root / harness.PINNED_ANCHOR_FILE).read_bytes()
    assert receipt["anchor"]["bytes_identical"] is True


def test_acquisition_receipt_is_path_and_payload_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, _, root, source = _acquire(tmp_path, monkeypatch)
    forbidden = {str(root.resolve()).casefold(), str(source.resolve()).casefold(), "claim_value"}
    for value in _strings(receipt):
        folded = value.casefold()
        assert all(item not in folded for item in forbidden)


def test_acquisition_rejects_nonfresh_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, _ = _manifest(tmp_path, monkeypatch)
    source, core_id, anchor_dir = _golden_source(tmp_path)
    root = _private_dir(tmp_path / "not-fresh")
    (root / "unexpected").write_text("x", encoding="utf-8")
    with pytest.raises(harness.AcquisitionError, match="fresh"):
        harness.acquire_product_copies(
            source,
            disposable_root=root,
            core_id_file=core_id,
            anchor_dir=anchor_dir,
            manifest=manifest,
            code_root=CODE_ROOT,
        )


def test_acquisition_tampered_copy_is_rejected_before_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    acquisition, manifest, root, _ = _acquire(tmp_path, monkeypatch)
    with (root / harness.WRITER_FREE_DATABASE).open("ab") as stream:
        stream.write(b"tamper")
    with pytest.raises(harness.RunEvidenceError, match="changed"):
        harness.run_readiness_candidate(
            disposable_root=root,
            acquisition_receipt=acquisition,
            manifest=manifest,
            code_root=CODE_ROOT,
            run_sequence=1,
        )


def test_injected_prototype_fault_returns_red_reset_receipt_without_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    acquisition, manifest, root, _ = _acquire(tmp_path, monkeypatch)

    def fail(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("sensitive absolute /path and payload")

    receipt = harness.run_readiness_candidate(
        disposable_root=root,
        acquisition_receipt=acquisition,
        manifest=manifest,
        code_root=CODE_ROOT,
        run_sequence=1,
        writer_free_runner=fail,
    )
    assert receipt["outcome"] == "red"
    assert receipt["series_reset_required"] is True
    assert receipt["failure"] == {
        "phase": "writer_free",
        "exception_class": "RuntimeError",
        "message_logged": False,
    }
    assert "/path" not in json.dumps(receipt)


def test_real_candidate_run_on_golden_sibling_copies_is_green(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    acquisition, manifest, root, _ = _acquire(tmp_path, monkeypatch)
    receipt = harness.run_readiness_candidate(
        disposable_root=root,
        acquisition_receipt=acquisition,
        manifest=manifest,
        code_root=CODE_ROOT,
        run_sequence=1,
        expected_candidate_commit=COMMIT,
    )
    assert receipt["outcome"] == "green", json.dumps(
        {
            key: receipt[key]
            for key in (
                "failure",
                "writer_free",
                "writer_free_postcheck",
                "concurrency_initialization",
                "concurrency",
                "concurrency_recovery",
            )
        }
        | {
                "raw_phase_writes": {
                    phase: receipt["raw_evidence"]["concurrency"][phase][
                        "write_transactions"
                    ]
                    for phase in ("build", "catch_up")
                }
            },
        sort_keys=True,
    )
    assert receipt["gate_pass"] is True
    assert receipt["writer_free_postcheck"]["g1_g2_g3_equal_to_acquisition"] is True
    assert receipt["writer_free"]["final_sync_decision"]["gate_pass"] is True
    assert receipt["concurrency_initialization"]["gate_pass"] is True
    assert receipt["concurrency"]["final_sync_decision"]["gate_pass"] is True
    assert receipt["concurrency_recovery"]["gate_pass"] is True
    harness.assert_receipt_safe(receipt)


@pytest.fixture(scope="module")
def green_candidate_evidence(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    tmp_path = tmp_path_factory.mktemp("a03c-green-template")
    identity = _target_identity()
    manifest = harness.create_runtime_manifest(
        code_root=CODE_ROOT,
        candidate_commit=COMMIT,
        gate_receipt_paths=_gate_files(tmp_path, identity),
        identity=identity,
    )
    source, core_id, anchor_dir = _golden_source(tmp_path)
    acquisition_root = _private_dir(tmp_path / "acquisition")
    acquisition = harness.acquire_product_copies(
        source,
        disposable_root=acquisition_root,
        core_id_file=core_id,
        anchor_dir=anchor_dir,
        manifest=manifest,
        code_root=CODE_ROOT,
        expected_candidate_commit=COMMIT,
        identity=identity,
    )
    run = harness.run_readiness_candidate(
        disposable_root=acquisition_root,
        acquisition_receipt=acquisition,
        manifest=manifest,
        code_root=CODE_ROOT,
        run_sequence=1,
        expected_candidate_commit=COMMIT,
        identity=identity,
    )
    assert run["gate_pass"] is True
    return manifest, identity, acquisition, run


def _green_run(
    template: Mapping[str, Any],
    sequence: int,
    acquisition_sha256: str,
    *,
    acquired_at: datetime | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> dict[str, Any]:
    start = started_at or datetime(2026, 8, 18, 12, sequence, tzinfo=timezone.utc)
    acquired = acquired_at or start - timedelta(seconds=1)
    completed = completed_at or start + timedelta(seconds=1)
    body = copy.deepcopy(dict(template))
    body.pop("receipt_sha256", None)
    body.update({
        "run_sequence": sequence,
        "started_at_utc": start.isoformat().replace("+00:00", "Z"),
        "completed_at_utc": completed.isoformat().replace("+00:00", "Z"),
        "acquisition_acquired_at_utc": acquired.isoformat().replace("+00:00", "Z"),
        "acquisition_receipt_sha256": acquisition_sha256,
    })
    return harness._seal_receipt(body)


def _fresh_acquisition(template: Mapping[str, Any]) -> dict[str, Any]:
    body = copy.deepcopy(dict(template))
    body.pop("receipt_sha256", None)
    body["acquired_at_utc"] = datetime.now(timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")
    return harness._seal_receipt(body)


def _series_inputs(
    acquisition_template: Mapping[str, Any], run_template: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    acquisitions: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    for sequence in (1, 2, 3):
        acquired = datetime(2026, 8, 18, 12, sequence, tzinfo=timezone.utc) - timedelta(
            seconds=1
        )
        body = copy.deepcopy(dict(acquisition_template))
        body.pop("receipt_sha256", None)
        body["acquired_at_utc"] = acquired.isoformat().replace("+00:00", "Z")
        acquisition = harness._seal_receipt(body)
        acquisitions.append(acquisition)
        runs.append(
            _green_run(run_template, sequence, acquisition["receipt_sha256"])
        )
    return acquisitions, runs


def test_series_accepts_exact_three_fresh_ordered_green_runs(
    green_candidate_evidence: tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]
) -> None:
    manifest, identity, _, template = green_candidate_evidence
    receipt = harness.verify_run_series(
        [_green_run(template, index, f"{index:x}" * 64) for index in (1, 2, 3)],
        manifest=manifest,
        code_root=CODE_ROOT,
        expected_candidate_commit=COMMIT,
        identity=identity,
    )
    assert receipt["gate_pass"] is True
    assert receipt["consecutive_green_runs"] == 3
    assert receipt["runtime_identity_sha256"] == identity["runtime_fingerprint_sha256"]


def test_any_red_run_resets_series(
    green_candidate_evidence: tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]
) -> None:
    manifest, identity, _, template = green_candidate_evidence
    runs = [_green_run(template, index, f"{index:x}" * 64) for index in (1, 2, 3)]
    red = dict(runs[1])
    red.update({"outcome": "red", "gate_pass": False, "series_reset_required": True})
    runs[1] = harness._seal_receipt(red)
    receipt = harness.verify_run_series(
        runs, manifest=manifest, code_root=CODE_ROOT, identity=identity
    )
    assert receipt["gate_pass"] is False
    assert receipt["red_run_sequences"] == [2]
    assert receipt["consecutive_green_runs"] == 0


def test_series_rejects_reused_acquisition_and_tampered_receipt(
    green_candidate_evidence: tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]
) -> None:
    manifest, identity, _, template = green_candidate_evidence
    runs = [_green_run(template, index, f"{index:x}" * 64) for index in (1, 2, 3)]
    duplicate = dict(runs[1])
    duplicate["acquisition_receipt_sha256"] = runs[0]["acquisition_receipt_sha256"]
    runs[1] = harness._seal_receipt(duplicate)
    with pytest.raises(harness.SeriesEvidenceError, match="reuses"):
        harness.verify_run_series(
            runs, manifest=manifest, code_root=CODE_ROOT, identity=identity
        )
    tampered = [_green_run(template, index, f"{index:x}" * 64) for index in (1, 2, 3)]
    tampered[0]["batch_events"] = 4_096
    with pytest.raises(harness.RuntimeReadinessError, match="digest"):
        harness.verify_run_series(
            tampered, manifest=manifest, code_root=CODE_ROOT, identity=identity
        )


def test_series_requires_strict_timestamp_and_sequence_order(
    green_candidate_evidence: tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]
) -> None:
    manifest, identity, _, template = green_candidate_evidence
    runs = [_green_run(template, index, f"{index:x}" * 64) for index in (1, 2, 3)]
    moved = dict(runs[1])
    moved["started_at_utc"] = runs[0]["started_at_utc"]
    moved["acquisition_acquired_at_utc"] = runs[0]["acquisition_acquired_at_utc"]
    runs[1] = harness._seal_receipt(moved)
    with pytest.raises(harness.SeriesEvidenceError, match="strictly increasing"):
        harness.verify_run_series(
            runs, manifest=manifest, code_root=CODE_ROOT, identity=identity
        )


def test_append_only_journal_accepts_only_latest_three_green_epoch(
    tmp_path: Path,
    green_candidate_evidence: tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]],
) -> None:
    manifest, identity, acquisition_template, run_template = green_candidate_evidence
    series_root = _private_dir(tmp_path / "series")
    series_init = harness.initialize_series_journal(
        series_root,
        manifest=manifest,
        code_root=CODE_ROOT,
        expected_candidate_commit=COMMIT,
        identity=identity,
    )
    for sequence in (1, 2, 3):
        acquisition = _fresh_acquisition(acquisition_template)
        start = harness.reserve_series_attempt(
            series_root,
            series_init=series_init,
            acquisition_receipt=acquisition,
            requested_sequence=sequence,
            manifest=manifest,
            code_root=CODE_ROOT,
            expected_candidate_commit=COMMIT,
            identity=identity,
        )
        run_time = datetime.now(timezone.utc)
        run = _green_run(
            run_template,
            sequence,
            acquisition["receipt_sha256"],
            acquired_at=datetime.fromisoformat(
                acquisition["acquired_at_utc"].replace("Z", "+00:00")
            ),
            started_at=run_time,
            completed_at=run_time,
        )
        harness.finish_series_attempt(
            series_root,
            series_init=series_init,
            start_entry=start,
            manifest=manifest,
            run_receipt=run,
        )
    receipt = harness.verify_series_journal(
        series_root,
        series_init=series_init,
        manifest=manifest,
        code_root=CODE_ROOT,
        expected_candidate_commit=COMMIT,
        identity=identity,
    )
    assert receipt["gate_pass"] is True
    assert receipt["journal_entry_count"] == 6
    assert receipt["journal_attempt_count"] == 3
    assert receipt["journal_reset_count"] == 0
    assert receipt["all_attempts_bound"] is True


def test_open_and_red_attempts_are_bound_by_resets_before_sequence_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    green_candidate_evidence: tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]],
) -> None:
    manifest, identity, acquisition_template, run_template = green_candidate_evidence
    acquisitions, runs = _series_inputs(acquisition_template, run_template)
    series_root = _private_dir(tmp_path / "series")
    series_init = harness.initialize_series_journal(
        series_root, manifest=manifest, code_root=CODE_ROOT, identity=identity
    )
    first = harness.reserve_series_attempt(
        series_root,
        series_init=series_init,
        acquisition_receipt=acquisitions[0],
        requested_sequence=1,
        manifest=manifest,
        code_root=CODE_ROOT,
        identity=identity,
    )
    with pytest.raises(harness.SeriesEvidenceError, match="live process"):
        harness.reserve_series_attempt(
            series_root,
            series_init=series_init,
            acquisition_receipt=acquisitions[1],
            requested_sequence=1,
            manifest=manifest,
            code_root=CODE_ROOT,
            identity=identity,
        )
    monkeypatch.setattr(harness, "_process_still_matches", lambda _attempt: False)
    second = harness.reserve_series_attempt(
        series_root,
        series_init=series_init,
        acquisition_receipt=acquisitions[1],
        requested_sequence=1,
        manifest=manifest,
        code_root=CODE_ROOT,
        identity=identity,
    )
    assert first["epoch"] == 1 and second["epoch"] == 2
    finish = harness.finish_series_attempt(
        series_root,
        series_init=series_init,
        start_entry=second,
        manifest=manifest,
        exception_class="RuntimeError",
    )
    with pytest.raises(harness.SeriesEvidenceError, match="already used"):
        harness.reserve_series_attempt(
            series_root,
            series_init=series_init,
            acquisition_receipt=acquisitions[1],
            requested_sequence=1,
            manifest=manifest,
            code_root=CODE_ROOT,
            identity=identity,
        )
    third = harness.reserve_series_attempt(
        series_root,
        series_init=series_init,
        acquisition_receipt=acquisitions[2],
        requested_sequence=1,
        manifest=manifest,
        code_root=CODE_ROOT,
        identity=identity,
    )
    assert finish["exception_class"] == "RuntimeError"
    assert "message" not in finish
    assert third["epoch"] == 3 and third["sequence"] == 1
    _, _, _, entries = harness._journal_inventory(
        series_root, manifest=manifest, supplied_init=series_init
    )
    assert [entry["entry_type"] for entry in entries] == [
        "attempt_start", "reset", "attempt_start", "attempt_finish", "reset",
        "attempt_start",
    ]
    duplicate_attempt = copy.deepcopy(entries)
    duplicate_attempt[-1]["attempt_id"] = entries[0]["attempt_id"]
    with pytest.raises(harness.SeriesEvidenceError, match="reused"):
        harness._validate_journal_state(duplicate_attempt, manifest=manifest)
    duplicate_acquisition = copy.deepcopy(entries)
    duplicate_acquisition[-1]["acquisition_receipt_sha256"] = entries[0][
        "acquisition_receipt_sha256"
    ]
    with pytest.raises(harness.SeriesEvidenceError, match="reused"):
        harness._validate_journal_state(duplicate_acquisition, manifest=manifest)


def test_journal_rejects_run_created_before_attempt_start(
    tmp_path: Path,
    green_candidate_evidence: tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]],
) -> None:
    manifest, identity, acquisition_template, run_template = green_candidate_evidence
    acquisitions, runs = _series_inputs(acquisition_template, run_template)
    series_root = _private_dir(tmp_path / "series")
    series_init = harness.initialize_series_journal(
        series_root, manifest=manifest, code_root=CODE_ROOT, identity=identity
    )
    future = copy.deepcopy(acquisitions[0])
    future.pop("receipt_sha256")
    future["acquired_at_utc"] = (
        datetime.now(timezone.utc) + timedelta(days=1)
    ).isoformat(timespec="microseconds").replace("+00:00", "Z")
    future = harness._seal_receipt(future)
    with pytest.raises(harness.SeriesEvidenceError, match="future"):
        harness.reserve_series_attempt(
            series_root,
            series_init=series_init,
            acquisition_receipt=future,
            requested_sequence=1,
            manifest=manifest,
            code_root=CODE_ROOT,
            identity=identity,
        )
    _, _, _, empty_entries = harness._journal_inventory(
        series_root, manifest=manifest, supplied_init=series_init
    )
    assert empty_entries == []
    start = harness.reserve_series_attempt(
        series_root,
        series_init=series_init,
        acquisition_receipt=acquisitions[0],
        requested_sequence=1,
        manifest=manifest,
        code_root=CODE_ROOT,
        identity=identity,
    )
    with pytest.raises(harness.SeriesEvidenceError, match="run does not bind"):
        harness.finish_series_attempt(
            series_root,
            series_init=series_init,
            start_entry=start,
            manifest=manifest,
            run_receipt=runs[0],
        )
    _, _, _, entries = harness._journal_inventory(
        series_root, manifest=manifest, supplied_init=series_init
    )
    assert [entry["entry_type"] for entry in entries] == ["attempt_start"]


def test_runtime_fingerprint_is_path_independent_but_invocation_is_attested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, identity = _manifest(tmp_path, monkeypatch)
    alternate = copy.deepcopy(identity)
    alternate["invocation_identity"]["invoked_path_sha256"] = "f" * 64
    alternate["invocation_identity_sha256"] = harness._sha256_json(
        alternate["invocation_identity"]
    )
    alternate.pop("identity_sha256")
    alternate["identity_sha256"] = harness._sha256_json(alternate)
    assert harness._validate_runtime_identity(alternate, True) == identity[
        "runtime_fingerprint_sha256"
    ]
    verification = harness.verify_runtime_manifest(
        manifest, code_root=CODE_ROOT, identity=alternate
    )
    assert verification["runtime_identity_sha256"] == identity[
        "runtime_fingerprint_sha256"
    ]
    unattested = harness.runtime_identity(tmp_path / "not-the-runtime")
    assert unattested["invocation_identity"]["expected_invocation_attested"] is False
    contradictory = copy.deepcopy(identity)
    contradictory["runtime_fingerprint"]["virtual_environment"] = False
    contradictory["runtime_fingerprint_sha256"] = harness._sha256_json(
        contradictory["runtime_fingerprint"]
    )
    contradictory.pop("identity_sha256")
    contradictory["identity_sha256"] = harness._sha256_json(contradictory)
    with pytest.raises(harness.RuntimeManifestError, match="exact"):
        harness._validate_runtime_identity(contradictory, True)


def test_raw_evidence_resource_and_write_receipts_fail_closed_on_tamper(
    green_candidate_evidence: tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]],
) -> None:
    _, _, _, template = green_candidate_evidence
    assert harness._reconstruct_run_summaries(template)[
        "summary_reconstruction_pass"
    ] is True
    config = harness._reconstruct_run_summaries(template)["raw_candidate_config"]
    # Catch-up does not duplicate batch caps in its A0.3b receipt.  Its exact
    # shared build/catch-up/verify arguments are therefore proven by both build
    # witnesses plus the accepted A0.3b code hash and canonical A0.3c callsite.
    assert set(config["phase_bindings"]) == {
        "concurrency.build",
        "writer_free.build",
    }
    assert config["canonical_batch_callsite_binding"][
        "phases_receiving_same_batch_arguments"
    ] == ["build", "catch_up", "verify"]
    extra_raw = copy.deepcopy(template)
    extra_raw["raw_evidence"]["foreign"] = {}
    with pytest.raises(harness.RunEvidenceError, match="inventory"):
        harness._reconstruct_run_summaries(extra_raw)
    changed_summary = copy.deepcopy(template)
    changed_summary["writer_free"]["no_fallback"] = False
    with pytest.raises(harness.RunEvidenceError, match="reconstructed"):
        harness._reconstruct_run_summaries(changed_summary)
    wrong_batch = copy.deepcopy(template)
    wrong_batch["raw_evidence"]["writer_free"]["build"]["batch_events"] = 4_096
    wrong_batch["raw_evidence_sha256"] = {
        key: harness._sha256_json(value)
        for key, value in wrong_batch["raw_evidence"].items()
    }
    with pytest.raises(harness.RunEvidenceError, match="batch configuration"):
        harness._reconstruct_run_summaries(wrong_batch)
    wrong_interval = copy.deepcopy(template)
    wrong_interval["raw_evidence"]["concurrency"]["writer_handoff"][
        "think_time_seconds"
    ] = 0.123
    wrong_interval["raw_evidence_sha256"] = {
        key: harness._sha256_json(value)
        for key, value in wrong_interval["raw_evidence"].items()
    }
    with pytest.raises(harness.RunEvidenceError, match="writer interval"):
        harness._reconstruct_run_summaries(wrong_interval)
    injected_runner = copy.deepcopy(template)
    injected_runner["canonical_runners_used"] = False
    with pytest.raises(harness.RunEvidenceError, match="callsite configuration"):
        harness._reconstruct_run_summaries(injected_runner)
    resource = copy.deepcopy(template["resource_evidence"]["concurrency_recovery"])
    assert resource["sample_count"] >= 2
    assert resource["error_count"] == 0
    assert resource["peak_rss_bytes"] > 0
    assert resource["storage_highwater_bytes"]["wal"] >= 0
    resource["foreign"] = True
    assert harness._strict_resource_receipt(
        resource, expected_phase="concurrency_recovery"
    )["gate_pass"] is False
    writes = copy.deepcopy(template["raw_evidence"]["writer_free"]["write_transactions"])
    assert harness._strict_write_receipt(
        writes, expected_scope="run_shadow_prototype", require_claim=True
    )["gate_pass"] is True
    writes["attempt_count"] += 1
    assert harness._strict_write_receipt(
        writes, expected_scope="run_shadow_prototype", require_claim=True
    )["gate_pass"] is False


def test_admission_requires_no_sync_route_and_committed_complete_new(
    green_candidate_evidence: tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]],
) -> None:
    _, _, _, template = green_candidate_evidence
    raw = copy.deepcopy(template["raw_evidence"]["writer_free"])
    raw["verify"]["sync_admission"]["sync_route_used"] = True
    summary = harness._writer_free_summary(
        raw,
        template["acquisition_oracle"],
        template["resource_evidence"]["writer_free_outer"],
    )
    assert summary["no_fallback"] is False
    assert summary["gate_pass"] is False


def test_anchor_scan_is_streaming_and_hard_capped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, identity = _manifest(tmp_path, monkeypatch)
    source, core_id, fixture_anchor_dir = _golden_source(tmp_path)
    anchor_dir = tmp_path / "anchors"
    anchor_dir.mkdir()
    (anchor_dir / "anchor_v1.json").write_bytes(
        (fixture_anchor_dir / "anchor_v1.json").read_bytes()
    )
    (anchor_dir / "foreign.txt").write_text("bounded", encoding="utf-8")
    monkeypatch.setattr(harness, "MAX_ANCHOR_DIRECTORY_ENTRIES", 1)
    acquisition_root = _private_dir(tmp_path / "acquisition")
    with pytest.raises(harness.AcquisitionError, match="entry cap"):
        harness.acquire_product_copies(
            source,
            disposable_root=acquisition_root,
            core_id_file=core_id,
            anchor_dir=anchor_dir,
            manifest=manifest,
            code_root=CODE_ROOT,
            identity=identity,
        )


def test_journal_inventory_rejects_foreign_files(
    tmp_path: Path,
    green_candidate_evidence: tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]],
) -> None:
    manifest, identity, _, _ = green_candidate_evidence
    series_root = _private_dir(tmp_path / "series")
    series_init = harness.initialize_series_journal(
        series_root, manifest=manifest, code_root=CODE_ROOT, identity=identity
    )
    foreign = series_root / harness.SERIES_JOURNAL_DIR / "foreign.txt"
    foreign.write_text("must fail closed", encoding="utf-8")
    with pytest.raises(harness.SeriesEvidenceError, match="foreign"):
        harness._journal_inventory(
            series_root, manifest=manifest, supplied_init=series_init
        )


def test_cli_parser_has_only_fixed_contract_commands() -> None:
    parser = cli.build_parser()
    choices = parser._subparsers._group_actions[0].choices
    assert set(choices) == {
        "identity",
        "gate",
        "manifest-create",
        "manifest-verify",
        "acquire",
        "series-init",
        "run",
        "verify-series",
    }
    with pytest.raises(ValueError):
        parser.parse_args(["run", "--sequence", "4"])
    for command in choices.values():
        expected = next(
            action for action in command._actions if action.dest == "expected_invocation"
        )
        assert expected.required is True
