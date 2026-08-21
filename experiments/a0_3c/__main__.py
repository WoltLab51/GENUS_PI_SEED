"""Command line interface for the copy-only A0.3c readiness harness."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Mapping

from . import harness


_PASSED = re.compile(rb"(?<!\d)(\d+) passed(?:[,\s]|$)")
_MAX_GATE_OUTPUT_BYTES = 64 * 1024 * 1024
_GATE_TIMEOUT_SECONDS = 3_600


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


def _code_root(path: Path) -> Path:
    if path.is_symlink():
        raise harness.RuntimeManifestError("code root must not be a symlink")
    root = path.resolve(strict=True)
    if not root.is_dir():
        raise harness.RuntimeManifestError("code root is not a directory")
    return root


def _git_head(root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=root,
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=30,
    )
    value = completed.stdout.decode("ascii", errors="strict").strip().casefold()
    if completed.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise harness.RuntimeManifestError("code root has no exact Git HEAD")
    return value


def _require_clean_git(root: Path) -> None:
    completed = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=root,
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=30,
    )
    if completed.returncode != 0 or completed.stdout:
        raise harness.RuntimeManifestError("Git worktree is not exactly clean")


def _require_external(path: Path, root: Path, label: str, *, existing: bool) -> Path:
    resolved = path.resolve(strict=existing) if existing else path.parent.resolve(strict=True) / path.name
    if resolved == root or root in resolved.parents:
        raise harness.RuntimeReadinessError(f"{label} must be outside the code root")
    return resolved


def _read_manifest(path: Path) -> dict[str, Any]:
    return harness.read_json_evidence(
        path, limit=harness.MAX_MANIFEST_BYTES, require_private=True
    )


def _strict_receipt_under_root(path: Path, root: Path) -> Path:
    if path.exists() or path.is_symlink():
        raise harness.RuntimeReadinessError("receipt target must be fresh")
    parent = path.parent.resolve(strict=True)
    target = parent / path.name
    try:
        relative = target.relative_to(root.resolve(strict=True))
    except ValueError as exc:
        raise harness.RuntimeReadinessError("receipt target is outside disposable root") from exc
    if not relative.parts:
        raise harness.RuntimeReadinessError("receipt target is not strictly below root")
    return target


def _existing_under_root(path: Path, root: Path, label: str) -> Path:
    if path.is_symlink():
        raise harness.RuntimeReadinessError(f"{label} must not be a symlink")
    target = path.resolve(strict=True)
    try:
        relative = target.relative_to(root.resolve(strict=True))
    except ValueError as exc:
        raise harness.RuntimeReadinessError(
            f"{label} is outside its disposable root"
        ) from exc
    if not relative.parts or not target.is_file():
        raise harness.RuntimeReadinessError(f"{label} is not a regular child file")
    return target


def _print_result(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True))


def _attested_identity(args: argparse.Namespace) -> dict[str, Any]:
    expected = getattr(args, "expected_invocation", None)
    identity = harness.runtime_identity(expected)
    if (
        expected is not None
        and identity["invocation_identity"].get("expected_invocation_attested")
        is not True
    ):
        raise harness.RuntimeManifestError("runtime invocation attestation failed")
    return identity


def _cmd_identity(args: argparse.Namespace) -> int:
    identity = _attested_identity(args)
    harness.write_json_evidence(
        args.receipt, identity, limit=harness.MAX_RECEIPT_BYTES
    )
    _print_result(
        {
            "receipt": Path(args.receipt).name,
            "exact_runtime_gate_pass": identity["runtime_fingerprint"][
                "exact_runtime_gate_pass"
            ],
            "identity_sha256": identity["identity_sha256"],
        }
    )
    return 0 if identity["runtime_fingerprint"]["exact_runtime_gate_pass"] else 2


def _exclusive_output(path: Path):
    if path.exists() or path.is_symlink():
        raise harness.RuntimeReadinessError("gate output target must be fresh")
    stream = path.open("xb")
    os.chmod(path, 0o600)
    return stream


def _run_gate_bounded(
    command: list[str],
    *,
    root: Path,
    gate_env: Mapping[str, str],
    stdout_path: Path,
    stderr_path: Path,
) -> int:
    """Run one gate with concurrently drained, hard-capped output streams."""
    overflow = threading.Event()
    pump_errors: list[str] = []
    with _exclusive_output(stdout_path) as stdout_file, _exclusive_output(
        stderr_path
    ) as stderr_file:
        process = subprocess.Popen(
            command,
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=dict(gate_env),
        )

        def pump(source: Any, target: Any) -> None:
            remaining = _MAX_GATE_OUTPUT_BYTES
            try:
                while True:
                    chunk = source.read(65_536)
                    if not chunk:
                        break
                    accepted = chunk[:remaining]
                    if accepted:
                        target.write(accepted)
                        remaining -= len(accepted)
                    if len(accepted) != len(chunk):
                        overflow.set()
                        try:
                            process.kill()
                        except OSError:
                            pass
            except Exception as exc:
                pump_errors.append(type(exc).__name__)
                try:
                    process.kill()
                except OSError:
                    pass
            finally:
                source.close()

        assert process.stdout is not None and process.stderr is not None
        threads = [
            threading.Thread(
                target=pump, args=(process.stdout, stdout_file), daemon=True
            ),
            threading.Thread(
                target=pump, args=(process.stderr, stderr_file), daemon=True
            ),
        ]
        for thread in threads:
            thread.start()
        try:
            exit_status = int(process.wait(timeout=_GATE_TIMEOUT_SECONDS))
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=30)
            exit_status = 124
        for thread in threads:
            thread.join(timeout=30)
        if any(thread.is_alive() for thread in threads) or pump_errors:
            raise harness.RuntimeReadinessError("gate output capture failed closed")
        stdout_file.flush()
        stderr_file.flush()
        if overflow.is_set():
            exit_status = 125
    return exit_status


def _cmd_gate(args: argparse.Namespace) -> int:
    root = _code_root(args.code_root)
    _require_clean_git(root)
    candidate = _git_head(root)
    if candidate != args.candidate_commit.casefold():
        raise harness.RuntimeManifestError("gate candidate commit differs from Git HEAD")
    identity = _attested_identity(args)
    harness._validate_runtime_identity(identity, True)
    scratch, _ = harness._private_root(args.scratch_root, require_empty=True)
    _require_external(scratch, root, "gate scratch root", existing=True)
    _require_external(args.receipt, root, "gate receipt", existing=False)
    basetemp = scratch / "pytest-basetemp"
    stdout_path = scratch / "stdout.bin"
    stderr_path = scratch / "stderr.bin"
    template = harness.gate_command_argv(args.gate)
    command = [
        sys.executable,
        "-B",
        *(str(basetemp) if item == "{fresh_private_basetemp}" else item for item in template),
    ]
    gate_env = os.environ.copy()
    for key in harness.GATE_ENVIRONMENT_CONTRACT["removed"]:
        gate_env.pop(key, None)
    gate_env.update(harness.GATE_ENVIRONMENT_CONTRACT["set"])
    exit_status = _run_gate_bounded(
        command,
        root=root,
        gate_env=gate_env,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )
    stdout_data, stdout_stat = harness._stable_file_bytes(
        stdout_path, _MAX_GATE_OUTPUT_BYTES
    )
    _, stderr_stat = harness._stable_file_bytes(stderr_path, _MAX_GATE_OUTPUT_BYTES)
    matches = [int(item) for item in _PASSED.findall(stdout_data)]
    test_count = matches[-1] if matches else 0
    receipt = harness.create_gate_receipt(
        gate=args.gate,
        candidate_commit=candidate,
        exit_status=exit_status,
        stdout_sha256=stdout_stat["sha256"],
        stderr_sha256=stderr_stat["sha256"],
        test_count=test_count,
        identity=identity,
    )
    harness.write_json_evidence(args.receipt, receipt)
    _require_clean_git(root)
    _print_result(
        {
            "receipt": Path(args.receipt).name,
            "gate": args.gate,
            "test_count": test_count,
            "pass": receipt["pass"],
        }
    )
    return 0 if receipt["pass"] else 2


def _cmd_manifest_create(args: argparse.Namespace) -> int:
    root = _code_root(args.code_root)
    _require_clean_git(root)
    _require_external(args.receipt, root, "manifest receipt", existing=False)
    for gate_receipt in (
        args.full_suite_receipt,
        args.a0_2_golden_receipt,
        args.a0_2_historical_sqlite_receipt,
    ):
        _require_external(gate_receipt, root, "gate receipt", existing=True)
    candidate = _git_head(root)
    if candidate != args.candidate_commit.casefold():
        raise harness.RuntimeManifestError("manifest candidate differs from Git HEAD")
    identity = _attested_identity(args)
    manifest = harness.create_runtime_manifest(
        code_root=root,
        candidate_commit=candidate,
        gate_receipt_paths={
            "full_suite": args.full_suite_receipt,
            "a0_2_golden": args.a0_2_golden_receipt,
            "a0_2_historical_sqlite": args.a0_2_historical_sqlite_receipt,
        },
        identity=identity,
    )
    harness.write_json_evidence(
        args.receipt, manifest, limit=harness.MAX_MANIFEST_BYTES
    )
    _require_clean_git(root)
    _print_result(
        {
            "receipt": Path(args.receipt).name,
            "manifest_sha256": manifest["manifest_sha256"],
            "candidate_commit": candidate,
        }
    )
    return 0


def _cmd_manifest_verify(args: argparse.Namespace) -> int:
    root = _code_root(args.code_root)
    _require_clean_git(root)
    _require_external(args.manifest, root, "manifest", existing=True)
    _require_external(args.receipt, root, "manifest verification receipt", existing=False)
    manifest = _read_manifest(args.manifest)
    identity = _attested_identity(args)
    verification = harness.verify_runtime_manifest(
        manifest, code_root=root, expected_candidate_commit=_git_head(root),
        identity=identity,
    )
    harness.write_json_evidence(args.receipt, verification)
    _require_clean_git(root)
    _print_result(
        {
            "receipt": Path(args.receipt).name,
            "manifest_sha256": verification["manifest_sha256"],
            "outcome": "verified",
        }
    )
    return 0


def _cmd_acquire(args: argparse.Namespace) -> int:
    root = _code_root(args.code_root)
    _require_clean_git(root)
    disposable_root, _ = harness._private_root(args.root, require_empty=True)
    _require_external(disposable_root, root, "acquisition root", existing=True)
    _require_external(args.manifest, root, "manifest", existing=True)
    _require_external(args.source, root, "product database", existing=True)
    _require_external(args.core_id_file, root, "core-id file", existing=True)
    _require_external(args.anchor_dir, root, "anchor directory", existing=True)
    target = _strict_receipt_under_root(args.receipt, disposable_root)
    manifest = _read_manifest(args.manifest)
    identity = _attested_identity(args)
    receipt = harness.acquire_product_copies(
        args.source,
        disposable_root=disposable_root,
        core_id_file=args.core_id_file,
        anchor_dir=args.anchor_dir,
        manifest=manifest,
        code_root=root,
        expected_candidate_commit=_git_head(root),
        identity=identity,
    )
    harness.write_json_evidence(target, receipt)
    _require_clean_git(root)
    _print_result(
        {
            "receipt": target.name,
            "outcome": receipt["outcome"],
            "oracle_sha256": receipt["oracle"]["oracle_sha256"],
        }
    )
    return 0


def _cmd_series_init(args: argparse.Namespace) -> int:
    root = _code_root(args.code_root)
    _require_clean_git(root)
    series_root, _ = harness._private_root(args.root, require_empty=True)
    _require_external(series_root, root, "series root", existing=True)
    _require_external(args.manifest, root, "manifest", existing=True)
    _require_external(args.receipt, root, "series init receipt", existing=False)
    _require_external(args.receipt, series_root, "series init receipt", existing=False)
    manifest = _read_manifest(args.manifest)
    identity = _attested_identity(args)
    receipt = harness.initialize_series_journal(
        series_root,
        manifest=manifest,
        code_root=root,
        expected_candidate_commit=_git_head(root),
        identity=identity,
    )
    harness.write_json_evidence(args.receipt, receipt)
    _require_clean_git(root)
    _print_result(
        {
            "receipt": Path(args.receipt).name,
            "series_init_sha256": receipt["receipt_sha256"],
            "outcome": "initialized",
        }
    )
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    root = _code_root(args.code_root)
    _require_clean_git(root)
    disposable_root, _ = harness._private_root(args.root, require_empty=False)
    _require_external(disposable_root, root, "run root", existing=True)
    series_root, _ = harness._private_root(args.series_root, require_empty=False)
    _require_external(series_root, root, "series root", existing=True)
    _require_external(args.manifest, root, "manifest", existing=True)
    target = _strict_receipt_under_root(args.receipt, disposable_root)
    manifest = _read_manifest(args.manifest)
    series_init = harness.read_json_evidence(
        _existing_under_root(args.series_init, series_root, "series init")
    )
    acquisition = harness.read_json_evidence(
        _existing_under_root(args.acquisition, disposable_root, "acquisition receipt")
    )
    identity = _attested_identity(args)
    expected_commit = _git_head(root)
    start = harness.reserve_series_attempt(
        series_root,
        series_init=series_init,
        acquisition_receipt=acquisition,
        requested_sequence=args.sequence,
        manifest=manifest,
        code_root=root,
        expected_candidate_commit=expected_commit,
        identity=identity,
    )
    try:
        receipt = harness.run_readiness_candidate(
            disposable_root=disposable_root,
            acquisition_receipt=acquisition,
            manifest=manifest,
            code_root=root,
            run_sequence=args.sequence,
            expected_candidate_commit=expected_commit,
            identity=identity,
        )
    except Exception as exc:
        harness.finish_series_attempt(
            series_root,
            series_init=series_init,
            start_entry=start,
            manifest=manifest,
            exception_class=type(exc).__name__,
        )
        raise
    harness.finish_series_attempt(
        series_root,
        series_init=series_init,
        start_entry=start,
        manifest=manifest,
        run_receipt=receipt,
    )
    harness.write_json_evidence(target, receipt)
    _require_clean_git(root)
    _print_result(
        {
            "receipt": target.name,
            "run_sequence": receipt["run_sequence"],
            "gate_pass": receipt["gate_pass"],
        }
    )
    return 0 if receipt["gate_pass"] else 2


def _cmd_verify_series(args: argparse.Namespace) -> int:
    root = _code_root(args.code_root)
    _require_clean_git(root)
    _require_external(args.manifest, root, "manifest", existing=True)
    _require_external(args.receipt, root, "series receipt", existing=False)
    series_root, _ = harness._private_root(args.series_root, require_empty=False)
    _require_external(series_root, root, "series root", existing=True)
    _require_external(args.receipt, series_root, "series receipt", existing=False)
    manifest = _read_manifest(args.manifest)
    series_init = harness.read_json_evidence(
        _existing_under_root(args.series_init, series_root, "series init")
    )
    identity = _attested_identity(args)
    receipt = harness.verify_series_journal(
        series_root,
        series_init=series_init,
        manifest=manifest,
        code_root=root,
        expected_candidate_commit=_git_head(root),
        identity=identity,
    )
    harness.write_json_evidence(args.receipt, receipt)
    _require_clean_git(root)
    _print_result(
        {
            "receipt": Path(args.receipt).name,
            "consecutive_green_runs": receipt["consecutive_green_runs"],
            "gate_pass": receipt["gate_pass"],
        }
    )
    return 0 if receipt["gate_pass"] else 2


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    identity = sub.add_parser("identity")
    identity.add_argument("--receipt", type=Path, required=True)
    identity.add_argument("--expected-invocation", type=Path, required=True)
    identity.set_defaults(handler=_cmd_identity)

    gate = sub.add_parser("gate")
    gate.add_argument("--gate", choices=sorted(harness.GATE_COMMANDS), required=True)
    gate.add_argument("--candidate-commit", required=True)
    gate.add_argument("--scratch-root", type=Path, required=True)
    gate.add_argument("--receipt", type=Path, required=True)
    gate.add_argument("--code-root", type=Path, default=Path("."))
    gate.add_argument("--expected-invocation", type=Path, required=True)
    gate.set_defaults(handler=_cmd_gate)

    create = sub.add_parser("manifest-create")
    create.add_argument("--candidate-commit", required=True)
    create.add_argument("--full-suite-receipt", type=Path, required=True)
    create.add_argument("--a0-2-golden-receipt", type=Path, required=True)
    create.add_argument("--a0-2-historical-sqlite-receipt", type=Path, required=True)
    create.add_argument("--receipt", type=Path, required=True)
    create.add_argument("--code-root", type=Path, default=Path("."))
    create.add_argument("--expected-invocation", type=Path, required=True)
    create.set_defaults(handler=_cmd_manifest_create)

    verify = sub.add_parser("manifest-verify")
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--receipt", type=Path, required=True)
    verify.add_argument("--code-root", type=Path, default=Path("."))
    verify.add_argument("--expected-invocation", type=Path, required=True)
    verify.set_defaults(handler=_cmd_manifest_verify)

    acquire = sub.add_parser("acquire")
    acquire.add_argument("--source", type=Path, required=True)
    acquire.add_argument("--root", type=Path, required=True)
    acquire.add_argument("--core-id-file", type=Path, required=True)
    acquire.add_argument("--anchor-dir", type=Path, required=True)
    acquire.add_argument("--manifest", type=Path, required=True)
    acquire.add_argument("--receipt", type=Path, required=True)
    acquire.add_argument("--code-root", type=Path, default=Path("."))
    acquire.add_argument("--expected-invocation", type=Path, required=True)
    acquire.set_defaults(handler=_cmd_acquire)

    series_init = sub.add_parser("series-init")
    series_init.add_argument("--root", type=Path, required=True)
    series_init.add_argument("--manifest", type=Path, required=True)
    series_init.add_argument("--receipt", type=Path, required=True)
    series_init.add_argument("--code-root", type=Path, default=Path("."))
    series_init.add_argument("--expected-invocation", type=Path, required=True)
    series_init.set_defaults(handler=_cmd_series_init)

    run = sub.add_parser("run")
    run.add_argument("--root", type=Path, required=True)
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--acquisition", type=Path, required=True)
    run.add_argument("--series-root", type=Path, required=True)
    run.add_argument("--series-init", type=Path, required=True)
    run.add_argument("--sequence", type=int, choices=(1, 2, 3), required=True)
    run.add_argument("--receipt", type=Path, required=True)
    run.add_argument("--code-root", type=Path, default=Path("."))
    run.add_argument("--expected-invocation", type=Path, required=True)
    run.set_defaults(handler=_cmd_run)

    series = sub.add_parser("verify-series")
    series.add_argument("--manifest", type=Path, required=True)
    series.add_argument("--series-root", type=Path, required=True)
    series.add_argument("--series-init", type=Path, required=True)
    series.add_argument("--receipt", type=Path, required=True)
    series.add_argument("--code-root", type=Path, default=Path("."))
    series.add_argument("--expected-invocation", type=Path, required=True)
    series.set_defaults(handler=_cmd_verify_series)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        return int(args.handler(args))
    except Exception as exc:
        print(type(exc).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
