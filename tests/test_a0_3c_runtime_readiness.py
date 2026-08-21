from __future__ import annotations

import copy
import json
import os
import stat
import subprocess
import sys
import types
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
    contract = harness.GATE_ENVIRONMENT_CONTRACT
    assert contract["schema"] == "genus-a0-3c-gate-environment-v2"
    assert contract["base_environment"] == "empty"
    assert contract["python_argv"] == ["-B"]
    assert contract["account"] == {
        "source": "pwd.getpwuid(os.geteuid())",
        "require_real_effective_uid_match": True,
        "allow_root": False,
        "mapping": {
            "LOGNAME": "pw_name",
            "USER": "pw_name",
        },
    }
    assert contract["scratch_directories"] == {
        "HOME": {"relative_path": "gate-home", "mode": "0700"},
        "TMPDIR": {"relative_path": "gate-tmp", "mode": "0700"},
    }
    assert contract["cwd"] == "verified_code_root"
    assert contract["subprocess_umask"] == "0077"
    assert contract["set"] == {
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        "PYTHONHASHSEED": "0",
        "PYTHONIOENCODING": "utf-8:strict",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONUTF8": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "TZ": "UTC0",
    }
    assert contract["git"]["executable"] == "/usr/bin/git"
    assert contract["git"]["argv_prefix"] == [
        "--no-optional-locks",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.hooksPath=/dev/null",
    ]


def test_gate_environment_uses_getpwuid_and_no_ambient_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ambient = {
        "BASH_ENV": "/tmp/injected-bash-env",
        "ENV": "/tmp/injected-sh-env",
        "SHELLOPTS": "xtrace:verbose",
        "BASHOPTS": "expand_aliases:sourcepath",
        "CDPATH": "/tmp/injected-cdpath",
        "GENUS_A03C_SYSTEMCTL": "/tmp/injected-systemctl",
        "GENUS_DB_PATH": "/live/product.sqlite3",
        "LD_PRELOAD": "/tmp/injected-loader.so",
        "PYTHONHOME": "/tmp/injected-python",
        "PYTHONPATH": "/tmp/injected-modules",
        "PYTEST_ADDOPTS": "--ignore=tests",
        "PYTEST_PLUGINS": "injected_plugin",
        "PATH": "/tmp/injected-bin",
        "HOME": "/tmp/injected-home",
        "LOGNAME": "injected-logname",
        "USER": "injected-user",
        "LANG": "injected-locale",
        "LC_ALL": "injected-locale",
        "TZ": "injected-timezone",
        "TMPDIR": "/tmp/injected-tmp",
        "GIT_DIR": "/tmp/injected-git-dir",
        "GIT_WORK_TREE": "/tmp/injected-work-tree",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "core.fsmonitor",
        "GIT_CONFIG_VALUE_0": "/tmp/injected-fsmonitor",
    }
    for key, value in ambient.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(harness.os, "getuid", lambda: 1234, raising=False)
    monkeypatch.setattr(harness.os, "geteuid", lambda: 1234, raising=False)
    monkeypatch.setitem(
        sys.modules,
        "pwd",
        types.SimpleNamespace(
            getpwuid=lambda uid: types.SimpleNamespace(
                pw_uid=uid,
                pw_name="gate-user",
            )
        ),
    )

    environment = harness.gate_environment(
        home="/evidence/gate-home", tmpdir="/evidence/gate-tmp"
    )

    assert environment == {
        **harness.GATE_ENVIRONMENT_CONTRACT["set"],
        "HOME": "/evidence/gate-home",
        "TMPDIR": "/evidence/gate-tmp",
        "LOGNAME": "gate-user",
        "USER": "gate-user",
    }
    fixed_keys = {
        "PATH",
        "HOME",
        "TMPDIR",
        "LOGNAME",
        "USER",
        "LANG",
        "LC_ALL",
        "TZ",
    }
    assert set(environment).isdisjoint(set(ambient) - fixed_keys)
    assert all("injected" not in value for value in environment.values())


@pytest.mark.parametrize(
    ("user", "home", "tmpdir"),
    [
        ("", "/evidence/home", "/evidence/tmp"),
        ("gate\nuser", "/evidence/home", "/evidence/tmp"),
        ("gate-user", "relative/home", "/evidence/tmp"),
        ("gate-user", "/evidence/../tmp", "/evidence/tmp"),
        ("gate-user", "/evidence/same", "/evidence/same"),
    ],
)
def test_gate_environment_rejects_unsafe_account_values(
    monkeypatch: pytest.MonkeyPatch, user: str, home: str, tmpdir: str
) -> None:
    monkeypatch.setattr(harness, "_posix_account", lambda: user)
    with pytest.raises(harness.RuntimeReadinessError):
        harness.gate_environment(home=home, tmpdir=tmpdir)


@pytest.mark.parametrize(("uid", "effective_uid"), [(0, 0), (1000, 0), (1000, 1001)])
def test_gate_account_rejects_root_or_identity_transitions(
    monkeypatch: pytest.MonkeyPatch, uid: int, effective_uid: int
) -> None:
    monkeypatch.setattr(harness.os, "getuid", lambda: uid, raising=False)
    monkeypatch.setattr(harness.os, "geteuid", lambda: effective_uid, raising=False)
    with pytest.raises(harness.RuntimeReadinessError, match="non-root"):
        harness._posix_account()


def test_git_attestation_environment_and_command_ignore_ambient_injection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_KEY_0",
        "GIT_CONFIG_VALUE_0",
    ):
        monkeypatch.setenv(key, f"injected-{key}")
    gate = {
        **harness.GATE_ENVIRONMENT_CONTRACT["set"],
        "HOME": "/evidence/gate-home",
        "TMPDIR": "/evidence/gate-tmp",
        "LOGNAME": "gate-user",
        "USER": "gate-user",
    }

    environment = harness.git_environment(gate)
    command = cli._git_command(CODE_ROOT, "status", "--porcelain=v1")

    assert environment == {
        "HOME": "/evidence/gate-home",
        "TMPDIR": "/evidence/gate-tmp",
        "PATH": "/usr/bin:/bin",
        "LANG": "C",
        "LC_ALL": "C",
        "TZ": "UTC0",
        **harness.GATE_ENVIRONMENT_CONTRACT["git"]["set"],
    }
    assert not any(key.startswith("injected-") for key in environment.values())
    assert not any(key.startswith("GIT_DIR") for key in environment)
    assert command == [
        "/usr/bin/git",
        "--no-optional-locks",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.hooksPath=/dev/null",
        "--git-dir",
        str(CODE_ROOT / ".git"),
        "--work-tree",
        str(CODE_ROOT),
        "status",
        "--porcelain=v1",
    ]


def test_git_head_and_clean_check_pass_only_the_isolated_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], dict[str, Any]]] = []
    isolated = harness.git_environment()

    def fake_run(command: list[str], **kwargs: Any):
        calls.append((command, kwargs))
        stdout = f"{COMMIT}\n".encode("ascii") if "rev-parse" in command else b""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr=b"")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    monkeypatch.setenv("GIT_DIR", "/tmp/ambient-repository")
    monkeypatch.setenv("PATH", "/tmp/fake-bin")

    assert cli._git_head(CODE_ROOT) == COMMIT
    cli._require_clean_git(CODE_ROOT)

    assert len(calls) == 2
    for command, kwargs in calls:
        assert command[0] == "/usr/bin/git"
        assert kwargs["cwd"] == CODE_ROOT
        assert kwargs["env"] == isolated
        assert "GIT_DIR" not in kwargs["env"]
        assert kwargs["env"]["PATH"] == "/usr/bin:/bin"


def test_cmd_gate_passes_the_exact_built_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    home = scratch / "gate-home"
    temporary = scratch / "gate-tmp"
    expected_environment = {"BOUND_GATE_ENV": "exact"}
    expected_git_environment = {"BOUND_GIT_ENV": "exact"}
    captured: dict[str, Any] = {}
    clean_calls: list[dict[str, str]] = []

    monkeypatch.setenv("BASH_ENV", "/tmp/ambient-injection")
    monkeypatch.setattr(cli, "_code_root", lambda path: CODE_ROOT)
    monkeypatch.setattr(cli, "_require_external", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        cli, "_gate_scratch_directories", lambda path: (home, temporary)
    )
    monkeypatch.setattr(
        harness,
        "gate_environment",
        lambda **kwargs: dict(expected_environment),
    )
    monkeypatch.setattr(
        harness,
        "git_environment",
        lambda gate=None: dict(expected_git_environment),
    )
    monkeypatch.setattr(
        cli,
        "_require_clean_git",
        lambda root, git_env=None: clean_calls.append(dict(git_env or {})),
    )
    monkeypatch.setattr(cli, "_git_head", lambda root, git_env=None: COMMIT)
    monkeypatch.setattr(cli, "_attested_identity", lambda args: _target_identity())
    monkeypatch.setattr(harness, "_validate_runtime_identity", lambda *args: ZERO)
    monkeypatch.setattr(cli, "_print_result", lambda value: None)

    def fake_gate_run(command: list[str], **kwargs: Any) -> int:
        captured["command"] = command
        captured["environment"] = dict(kwargs["gate_env"])
        kwargs["stdout_path"].write_bytes(b"1 passed\n")
        kwargs["stderr_path"].write_bytes(b"")
        return 0

    monkeypatch.setattr(cli, "_run_gate_bounded", fake_gate_run)
    args = types.SimpleNamespace(
        code_root=CODE_ROOT,
        scratch_root=scratch,
        receipt=tmp_path / "gate-receipt.json",
        candidate_commit=COMMIT,
        expected_invocation=None,
        gate="full_suite",
    )

    assert cli._cmd_gate(args) == 0
    assert captured["environment"] == expected_environment
    assert "BASH_ENV" not in captured["environment"]
    assert captured["command"][:2] == [sys.executable, "-B"]
    assert clean_calls == [expected_git_environment, expected_git_environment]


@pytest.mark.skipif(os.name != "posix", reason="validates POSIX ownership and umask")
def test_gate_scratch_and_child_umask_are_private(tmp_path: Path) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir(mode=0o700)
    os.chmod(scratch, 0o700)

    home, temporary = cli._gate_scratch_directories(scratch)
    environment = harness.gate_environment(home=home, tmpdir=temporary)
    child_file = temporary / "child-created"
    stdout = scratch / "stdout.bin"
    stderr = scratch / "stderr.bin"
    status_code = cli._run_gate_bounded(
        [
            sys.executable,
            "-c",
            "import pathlib,sys; pathlib.Path(sys.argv[1]).touch(mode=0o666)",
            str(child_file),
        ],
        root=CODE_ROOT,
        gate_env=environment,
        stdout_path=stdout,
        stderr_path=stderr,
    )

    assert status_code == 0
    assert home.parent == scratch and temporary.parent == scratch
    assert home.name == "gate-home" and temporary.name == "gate-tmp"
    assert stat.S_IMODE(home.stat().st_mode) == 0o700
    assert stat.S_IMODE(temporary.stat().st_mode) == 0o700
    assert stat.S_IMODE(child_file.stat().st_mode) == 0o600


@pytest.mark.skipif(
    os.name != "posix" or not Path("/usr/bin/git").is_file(),
    reason="validates canonical POSIX Git behavior",
)
def test_git_clean_check_disables_configured_fsmonitor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    canary = tmp_path / "fsmonitor-ran"
    monitor = tmp_path / "fsmonitor"
    repository.mkdir()
    monitor.write_text(
        f"#!/bin/sh\n: > {canary}\nexit 0\n",
        encoding="utf-8",
    )
    monitor.chmod(0o700)
    subprocess.run(["/usr/bin/git", "init", "-q", str(repository)], check=True)
    subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(repository),
            "config",
            "core.fsmonitor",
            str(monitor),
        ],
        check=True,
    )
    monkeypatch.setenv("GIT_DIR", str(CODE_ROOT / ".git"))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.fsmonitor")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(monitor))

    cli._require_clean_git(repository)

    assert not canary.exists()


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
    assert manifest["candidate_config"]["long_reader_snapshot_scope"] == (
        "cutover_pre_commit_through_post_commit"
    )
    assert manifest["candidate_config"]["bulk_replay_wal_pinned"] is False
    assert manifest["a0_3b_code_sha256"] == (
        harness.A03C_REQUIRED_A03B_CANDIDATE_SHA256
    )
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


def test_a03c_rejects_the_human_accepted_pre_wal_fix_a03b_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_by_path = {
        str((CODE_ROOT / relative).resolve()): (
            harness.HUMAN_ACCEPTED_A03B_BASELINE_SHA256[role]
        )
        for role, relative in harness._A03B_FILES.items()
    }
    assert harness.HUMAN_ACCEPTED_A03B_BASELINE_SHA256 != (
        harness.A03C_REQUIRED_A03B_CANDIDATE_SHA256
    )
    monkeypatch.setattr(
        harness,
        "_canonical_source_sha256",
        lambda path: baseline_by_path[str(path.resolve())],
    )

    with pytest.raises(harness.RuntimeManifestError, match="required A0.3c candidate"):
        harness.a03b_code_hashes(CODE_ROOT)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("long_reader_snapshot_scope", "bulk_replay_through_post_commit"),
        ("bulk_replay_wal_pinned", True),
    ],
)
def test_manifest_rejects_resealed_reader_scope_config_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    key: str,
    value: Any,
) -> None:
    manifest, identity = _manifest(tmp_path, monkeypatch)
    tampered = copy.deepcopy(manifest)
    tampered["candidate_config"][key] = value
    tampered["manifest_sha256"] = harness._sha256_json(
        {item: content for item, content in tampered.items() if item != "manifest_sha256"}
    )

    with pytest.raises(harness.RuntimeManifestError, match="candidate configuration"):
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
    assert receipt["concurrency"]["reader_inventory_exact"] is True
    assert receipt["concurrency"]["reader_evidence_reconstructed"] is True
    assert receipt["concurrency"]["reader_snapshot_scope_bound"] is True
    assert receipt["concurrency"]["long_reader_snapshot_scope"] == (
        "cutover_pre_commit_through_post_commit"
    )
    assert receipt["concurrency"]["bulk_replay_wal_pinned"] is False
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


def _final_series_layout(
    tmp_path: Path,
    evidence: tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]],
) -> tuple[Path, Path, Path, dict[str, Any], Path, dict[str, Any]]:
    manifest, identity, acquisition_template, run_template = evidence
    evidence_root = _private_dir(tmp_path / "series-evidence")
    series_parent = _private_dir(evidence_root / "readiness-id")
    journal_root = _private_dir(series_parent / "journal-root")
    series_init = harness.initialize_series_journal(
        journal_root,
        manifest=manifest,
        code_root=CODE_ROOT,
        expected_candidate_commit=COMMIT,
        identity=identity,
    )
    for sequence in (1, 2, 3):
        acquisition = _fresh_acquisition(acquisition_template)
        start = harness.reserve_series_attempt(
            journal_root,
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
            journal_root,
            series_init=series_init,
            start_entry=start,
            manifest=manifest,
            run_receipt=run,
        )
    receipt = harness.verify_series_journal(
        journal_root,
        series_init=series_init,
        manifest=manifest,
        code_root=CODE_ROOT,
        expected_candidate_commit=COMMIT,
        identity=identity,
    )
    final_receipt = series_parent / "final-series.json"
    harness.write_json_evidence(final_receipt, receipt)
    return evidence_root, series_parent, journal_root, series_init, final_receipt, receipt


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


def test_final_series_chain_replays_canonical_private_journal(
    tmp_path: Path,
    green_candidate_evidence: tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]],
) -> None:
    manifest, identity, _, _ = green_candidate_evidence
    evidence_root, _, _, _, final_receipt, receipt = _final_series_layout(
        tmp_path, green_candidate_evidence
    )
    verified = harness.verify_final_series_receipt_chain(
        final_receipt,
        series_evidence_root=evidence_root,
        manifest=manifest,
        code_root=CODE_ROOT,
        expected_candidate_commit=COMMIT,
        identity=identity,
    )
    assert verified["file_sha256"] == harness._stable_file_bytes(
        final_receipt, harness.MAX_RECEIPT_BYTES
    )[1]["sha256"]
    assert verified["journal_chain_tip_sha256"] == receipt["journal_chain_tip_sha256"]
    assert verified["gate_pass"] is True


def test_final_series_chain_rejects_self_sealed_stale_aggregate(
    tmp_path: Path,
    green_candidate_evidence: tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]],
) -> None:
    manifest, identity, _, _ = green_candidate_evidence
    evidence_root, _, _, _, final_receipt, receipt = _final_series_layout(
        tmp_path, green_candidate_evidence
    )
    stale = dict(receipt)
    stale.pop("receipt_sha256")
    stale["journal_chain_tip_sha256"] = "f" * 64
    final_receipt.unlink()
    harness.write_json_evidence(final_receipt, harness._seal_receipt(stale))
    with pytest.raises(harness.SeriesEvidenceError, match="journal replay"):
        harness.verify_final_series_receipt_chain(
            final_receipt,
            series_evidence_root=evidence_root,
            manifest=manifest,
            code_root=CODE_ROOT,
            expected_candidate_commit=COMMIT,
            identity=identity,
        )


def test_final_series_chain_parses_the_exact_pinned_receipt_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    green_candidate_evidence: tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]],
) -> None:
    manifest, identity, _, _ = green_candidate_evidence
    evidence_root, _, _, _, final_receipt, valid = _final_series_layout(
        tmp_path, green_candidate_evidence
    )
    stale = dict(valid)
    stale.pop("receipt_sha256")
    stale["journal_chain_tip_sha256"] = "f" * 64
    final_receipt.unlink()
    harness.write_json_evidence(final_receipt, harness._seal_receipt(stale))
    original_read = harness.read_json_evidence

    def split_read(path: Path | str, **kwargs: Any) -> dict[str, Any]:
        if Path(path) == final_receipt:
            return copy.deepcopy(valid)
        return original_read(path, **kwargs)

    monkeypatch.setattr(harness, "read_json_evidence", split_read)
    with pytest.raises(harness.SeriesEvidenceError, match="journal replay"):
        harness.verify_final_series_receipt_chain(
            final_receipt,
            series_evidence_root=evidence_root,
            manifest=manifest,
            code_root=CODE_ROOT,
            expected_candidate_commit=COMMIT,
            identity=identity,
        )


def test_final_series_chain_binds_replay_to_pinned_journal_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    green_candidate_evidence: tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]],
) -> None:
    manifest, identity, _, _ = green_candidate_evidence
    evidence_root, _, journal_root, _, final_receipt, valid = _final_series_layout(
        tmp_path, green_candidate_evidence
    )
    entry_path = journal_root / harness.SERIES_JOURNAL_DIR / "00000001.json"
    entry = harness.read_json_evidence(entry_path)
    entry.pop("receipt_sha256")
    entry["created_at_utc"] = "2026-08-18T00:00:00Z"
    entry_path.unlink()
    harness.write_json_evidence(entry_path, harness._seal_receipt(entry))
    monkeypatch.setattr(
        harness,
        "verify_series_journal",
        lambda *args, **kwargs: copy.deepcopy(valid),
    )
    with pytest.raises(harness.SeriesEvidenceError, match="pinned evidence inventory"):
        harness.verify_final_series_receipt_chain(
            final_receipt,
            series_evidence_root=evidence_root,
            manifest=manifest,
            code_root=CODE_ROOT,
            expected_candidate_commit=COMMIT,
            identity=identity,
        )


def test_final_series_chain_rejects_tampered_journal_entry(
    tmp_path: Path,
    green_candidate_evidence: tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]],
) -> None:
    manifest, identity, _, _ = green_candidate_evidence
    evidence_root, _, journal_root, _, final_receipt, _ = _final_series_layout(
        tmp_path, green_candidate_evidence
    )
    entry_path = journal_root / harness.SERIES_JOURNAL_DIR / "00000001.json"
    entry = harness.read_json_evidence(entry_path)
    entry.pop("receipt_sha256")
    entry["candidate_commit"] = "2" * 40
    entry_path.unlink()
    harness.write_json_evidence(entry_path, harness._seal_receipt(entry))
    with pytest.raises(harness.SeriesEvidenceError):
        harness.verify_final_series_receipt_chain(
            final_receipt,
            series_evidence_root=evidence_root,
            manifest=manifest,
            code_root=CODE_ROOT,
            expected_candidate_commit=COMMIT,
            identity=identity,
        )


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
    assert config["long_reader_snapshot_scope"] == (
        "cutover_pre_commit_through_post_commit"
    )
    assert config["bulk_replay_wal_pinned"] is False
    assert config["reader_inventory_exact"] is True
    assert config["reader_evidence_reconstructed"] is True
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


def _reseal_concurrency_tamper(
    receipt: dict[str, Any],
) -> dict[str, Any]:
    raw_concurrency = receipt["raw_evidence"]["concurrency"]
    summary = harness._concurrency_summary(
        raw_concurrency, receipt["resource_evidence"]["concurrency_outer"]
    )
    receipt["concurrency"] = summary
    receipt["raw_evidence_sha256"]["concurrency"] = harness._sha256_json(
        raw_concurrency
    )
    body = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    receipt["receipt_sha256"] = harness._sha256_json(body)
    assert harness._verify_receipt_digest(receipt, "resealed concurrency tamper") == (
        receipt["receipt_sha256"]
    )
    return summary


@pytest.mark.parametrize(
    ("field", "value", "remove", "expected_error", "inventory_exact"),
    [
        ("long_reader_snapshot_scope", None, True, "reader inventory", False),
        (
            "long_reader_snapshot_scope",
            "bulk_replay_through_post_commit",
            False,
            "snapshot scope",
            True,
        ),
        ("bulk_replay_wal_pinned", None, True, "reader inventory", False),
        ("bulk_replay_wal_pinned", True, False, "snapshot scope", True),
    ],
)
def test_concurrency_receipt_fails_closed_on_reader_scope_tamper(
    green_candidate_evidence: tuple[
        dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]
    ],
    field: str,
    value: Any,
    remove: bool,
    expected_error: str,
    inventory_exact: bool,
) -> None:
    _, _, _, template = green_candidate_evidence
    tampered = copy.deepcopy(template)
    raw_concurrency = tampered["raw_evidence"]["concurrency"]
    if remove:
        raw_concurrency["reader"].pop(field)
    else:
        raw_concurrency["reader"][field] = value
    summary = _reseal_concurrency_tamper(tampered)
    assert summary["reader_inventory_exact"] is inventory_exact
    assert summary["reader_evidence_reconstructed"] is False
    assert summary["reader_snapshot_scope_bound"] is False
    assert summary["gate_pass"] is False

    with pytest.raises(harness.RunEvidenceError, match=expected_error):
        harness._reconstruct_run_summaries(tampered)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("long_reader_before", "g2"),
        ("long_reader_after", "g2"),
        ("fresh_reader_after", "g1"),
        ("generations_seen", []),
        ("generations_seen", ["g2", "g1"]),
        ("generations_seen", ["g1", "g1"]),
        ("generations_seen", ["g3"]),
        ("generations_seen", "g1"),
        ("short_transaction_count", True),
        ("short_transaction_count", 0),
        ("retained_sample_count", 0),
        ("samples_truncated", True),
        ("failures", ["InjectedFault"]),
        ("failure_count", False),
        ("failure_samples_truncated", True),
        ("reader_thread_alive_after_join", True),
        ("writer_thread_alive_after_join", True),
        ("coherent_old_or_new_only", 1),
    ],
)
def test_concurrency_reader_evidence_rejects_resealed_tamper(
    green_candidate_evidence: tuple[
        dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]
    ],
    field: str,
    value: Any,
) -> None:
    _, _, _, template = green_candidate_evidence
    tampered = copy.deepcopy(template)
    tampered["raw_evidence"]["concurrency"]["reader"][field] = value
    summary = _reseal_concurrency_tamper(tampered)
    assert summary["reader_inventory_exact"] is True
    assert summary["reader_evidence_reconstructed"] is False
    assert summary["gate_pass"] is False

    with pytest.raises(harness.RunEvidenceError, match="reader evidence"):
        harness._reconstruct_run_summaries(tampered)


def test_concurrency_reader_inventory_rejects_resealed_extra_key(
    green_candidate_evidence: tuple[
        dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]
    ],
) -> None:
    _, _, _, template = green_candidate_evidence
    tampered = copy.deepcopy(template)
    tampered["raw_evidence"]["concurrency"]["reader"]["foreign"] = False
    summary = _reseal_concurrency_tamper(tampered)
    assert summary["reader_inventory_exact"] is False
    assert summary["reader_evidence_reconstructed"] is False
    assert summary["gate_pass"] is False

    with pytest.raises(harness.RunEvidenceError, match="reader inventory"):
        harness._reconstruct_run_summaries(tampered)


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
