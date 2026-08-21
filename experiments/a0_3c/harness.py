"""Fail-closed A0.3c runtime and copy-only readiness harness."""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import re
import sqlite3
import stat
import sys
import threading
import _sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import psutil

from experiments.a0_3a import harness as a03a
from experiments.a0_3b import harness as a03b
from genus import anchor, schema_detection, sealing


RUNTIME_IDENTITY_SCHEMA = "genus-a0-3c-runtime-identity-v1"
RUNTIME_MANIFEST_SCHEMA = "genus-a0-3c-runtime-manifest-v1"
MANIFEST_VERIFICATION_SCHEMA = "genus-a0-3c-manifest-verification-v1"
GATE_RECEIPT_SCHEMA = "genus-a0-3c-gate-receipt-v1"
ACQUISITION_RECEIPT_SCHEMA = "genus-a0-3c-acquisition-v1"
RUN_RECEIPT_SCHEMA = "genus-a0-3c-readiness-run-v1"
SERIES_RECEIPT_SCHEMA = "genus-a0-3c-readiness-series-v1"
SERIES_INIT_SCHEMA = "genus-a0-3c-series-init-v1"
JOURNAL_ENTRY_SCHEMA = "genus-a0-3c-series-journal-entry-v1"

MINIMUM_SQLITE_VERSION = (3, 51, 3)
TARGET_SQLITE_SERIES = (3, 53)
REQUIRED_PYTHON_VERSION = (3, 13, 15)
REQUIRED_SQLITE_VERSION = (3, 53, 4)
REQUIRED_SQLITE_SOURCE_ID = (
    "2026-07-24 19:02:57 "
    "bf7c7f30031888f4e796e429ab3978879485813aaca6f641c7b33e4e09459bcc"
)
REQUIRED_BATCH_EVENTS = 3_072
REQUIRED_BATCH_BYTES = a03b.DEFAULT_BATCH_BYTES
REQUIRED_WRITER_INTERVAL_SECONDS = 0.005
REQUIRED_READER_INTERVAL_SECONDS = 0.003
REQUIRED_CONSECUTIVE_RUNS = 3
REQUIRED_FINAL_SYNC_DECISION_REASON = (
    "bounded admission tail and pointer CAS completed in one fence"
)
MAX_MANIFEST_BYTES = 128 * 1024
MAX_RECEIPT_BYTES = 32 * 1024 * 1024
MAX_CODE_FILE_BYTES = 4 * 1024 * 1024
MAX_RUNTIME_MODULE_BYTES = 64 * 1024 * 1024
MAX_JSON_DEPTH = 32
MAX_JSON_ITEMS = 2_000_000
WRITER_FREE_DATABASE = "writer-free.sqlite3"
CONCURRENCY_DATABASE = "concurrency.sqlite3"
PINNED_ANCHOR_FILE = "pinned-anchor.json"
MAX_ANCHOR_BYTES = 65_536
MAX_CORE_ID_BYTES = 512
MAX_ANCHOR_DIRECTORY_ENTRIES = 1_024
MAX_ANCHOR_CANDIDATES = 256
MAX_JOURNAL_ENTRIES = 4_096
SERIES_INIT_FILE = "series-init.json"
SERIES_JOURNAL_DIR = "journal"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")
_JOURNAL_FILE = re.compile(r"^(\d{8})\.json$")
_ZERO_SHA256 = "0" * 64
_A03B_FILES = {
    "package": Path("experiments/a0_3b/__init__.py"),
    "cli": Path("experiments/a0_3b/__main__.py"),
    "harness": Path("experiments/a0_3b/harness.py"),
    "tests": Path("tests/test_a0_3b_shadow_cutover.py"),
}
_A03C_FILES = {
    "package": Path("experiments/a0_3c/__init__.py"),
    "cli": Path("experiments/a0_3c/__main__.py"),
    "harness": Path("experiments/a0_3c/harness.py"),
    "tests": Path("tests/test_a0_3c_runtime_readiness.py"),
}
ACCEPTED_A03B_CODE_SHA256 = {
    "package": "c8fdd59854fa9822867aadf602ce2a9a2e5c2bf64e0d3f30930521a6ffaee871",
    "cli": "612e28134dfd3b9ab029628a824de93b29c4637892a23921ae3f783a9e99890e",
    "harness": "f8e31096637eaaf5abc44a77f10b0f09eb362ad3f4ea7c9d4e3f1d2cc895b579",
    "tests": "e90a10c87a599de6e1fc0bd9a5cabd56ad9d9cb7536ea41eb2e228a0ce37fcc6",
}
_WRITER_FREE_BUDGET_KEYS = {
    "peak_rss",
    "wal_highwater",
    "initialization_write_transactions",
    "build_write_transactions",
    "catch_up_write_transactions",
    "verification_sync_and_cutover_write_transactions",
    "rebuild",
    "final_fence",
    "all_experimental_write_transactions",
    "recovery",
}
_RAW_EVIDENCE_KEYS = {
    "writer_free",
    "concurrency_initialization",
    "concurrency",
    "concurrency_recovery",
}
_RESOURCE_EVIDENCE_KEYS = {
    "writer_free_outer",
    "concurrency_initialization",
    "concurrency_outer",
    "concurrency_recovery",
}
GATE_COMMANDS = {
    "full_suite": (
        "-m", "pytest", "-q", "-p", "no:cacheprovider",
        "--basetemp", "{fresh_private_basetemp}",
    ),
    "a0_2_golden": (
        "-m", "pytest", "-q", "-p", "no:cacheprovider",
        "tests/test_golden_ledger_oracle.py",
        "--basetemp", "{fresh_private_basetemp}",
    ),
    "a0_2_historical_sqlite": (
        "-m", "pytest", "-q", "-p", "no:cacheprovider",
        "tests/test_historical_sqlite_fixture.py",
        "--basetemp", "{fresh_private_basetemp}",
    ),
}
GATE_ENVIRONMENT_CONTRACT = {
    "python_no_bytecode_flag": True,
    "set": {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    },
    "removed": [
        "GENUS_CORE_ID",
        "GENUS_DB_PATH",
        "GENUS_PAUSE_FILE",
        "PYTEST_ADDOPTS",
        "PYTEST_PLUGINS",
        "PYTHONPATH",
    ],
    "stdin": "devnull",
}


class RuntimeReadinessError(RuntimeError):
    """An A0.3c fail-closed invariant was violated."""


class RuntimeManifestError(RuntimeReadinessError):
    """The pinned runtime manifest is malformed or no longer exact."""


class AcquisitionError(RuntimeReadinessError):
    """A copy acquisition could not be proven safe and exact."""


class RunEvidenceError(RuntimeReadinessError):
    """One readiness run has incomplete evidence."""


class SeriesEvidenceError(RuntimeReadinessError):
    """The three-run series is inconsistent."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise SeriesEvidenceError("receipt timestamp is not canonical UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise SeriesEvidenceError("receipt timestamp is malformed") from exc
    if parsed.tzinfo != timezone.utc:
        raise SeriesEvidenceError("receipt timestamp is not UTC")
    return parsed


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _seal_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    body = {key: item for key, item in value.items() if key != "receipt_sha256"}
    return {**body, "receipt_sha256": _sha256_json(body)}


def _verify_receipt_digest(value: Mapping[str, Any], label: str) -> str:
    digest = value.get("receipt_sha256")
    body = {key: item for key, item in value.items() if key != "receipt_sha256"}
    if not isinstance(digest, str) or not _HEX64.fullmatch(digest):
        raise RuntimeReadinessError(f"{label} receipt digest is malformed")
    if digest != _sha256_json(body):
        raise RuntimeReadinessError(f"{label} receipt digest differs")
    return digest


def _walk_json(value: Any, depth: int = 0) -> int:
    if depth > MAX_JSON_DEPTH:
        raise RuntimeReadinessError("JSON evidence exceeds its depth cap")
    if value is None or isinstance(value, (bool, int, str)):
        return 1
    if isinstance(value, float):
        if not math.isfinite(value):
            raise RuntimeReadinessError("JSON evidence contains a non-finite number")
        return 1
    if isinstance(value, Mapping):
        total = 1
        for key, item in value.items():
            if not isinstance(key, str):
                raise RuntimeReadinessError("JSON object key is not text")
            total += _walk_json(item, depth + 1)
        if total > MAX_JSON_ITEMS:
            raise RuntimeReadinessError("JSON evidence exceeds its item cap")
        return total
    if isinstance(value, (list, tuple)):
        total = 1 + sum(_walk_json(item, depth + 1) for item in value)
        if total > MAX_JSON_ITEMS:
            raise RuntimeReadinessError("JSON evidence exceeds its item cap")
        return total
    raise RuntimeReadinessError("JSON evidence contains an unsupported type")


def assert_receipt_safe(value: Any) -> None:
    """Reject absolute paths, raw payload fields and non-JSON values."""
    _walk_json(value)

    def visit(item: Any) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                normalized_key = key.casefold()
                if "payload" in normalized_key:
                    payload_attestation = normalized_key in {
                        "payload_logged",
                        "payloads_logged",
                    }
                    payload_measurement = normalized_key.endswith("payload_bytes")
                    if payload_attestation and child is not False:
                        raise RuntimeReadinessError(
                            "receipt does not attest payload exclusion"
                        )
                    if payload_measurement and (
                        isinstance(child, bool)
                        or not isinstance(child, int)
                        or child < 0
                    ):
                        raise RuntimeReadinessError(
                            "receipt payload byte measurement is malformed"
                        )
                    if not payload_attestation and not payload_measurement:
                        raise RuntimeReadinessError(
                            "receipt has a payload-bearing field"
                        )
                visit(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child)
        elif isinstance(item, str) and (
            item.startswith("/") or item.startswith("\\\\") or _WINDOWS_ABSOLUTE.match(item)
        ):
            raise RuntimeReadinessError("receipt contains an absolute path")

    visit(value)


def _stable_file_bytes(path: Path | str, limit: int) -> tuple[bytes, dict[str, Any]]:
    target = Path(path).expanduser()
    if target.is_symlink() or not target.is_file():
        raise RuntimeReadinessError("evidence is not a regular non-symlink file")
    before = target.stat(follow_symlinks=False)
    if before.st_size > limit:
        raise RuntimeReadinessError("evidence exceeds its byte cap")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(target, flags)
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise RuntimeReadinessError("evidence identity changed before read")
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(fd, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        opened_after = os.fstat(fd)
    finally:
        os.close(fd)
    data = b"".join(chunks)
    after = target.stat(follow_symlinks=False)
    def stamp(item: os.stat_result) -> tuple[int, ...]:
        common = (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
        if os.name != "posix":
            return common
        return common + (item.st_mode, item.st_uid, item.st_gid, item.st_nlink)
    if stamp(before) != stamp(opened) or stamp(before) != stamp(opened_after) or stamp(before) != stamp(after):
        raise RuntimeReadinessError("evidence changed during bounded read")
    if len(data) != before.st_size or len(data) > limit:
        raise RuntimeReadinessError("evidence read was not exact and bounded")
    return data, {
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "mode": f"{stat.S_IMODE(before.st_mode):04o}",
        "uid": int(before.st_uid),
        "links": int(before.st_nlink),
        "device": int(before.st_dev),
        "inode": int(before.st_ino),
    }


def _decode_json_evidence(data: bytes) -> dict[str, Any]:
    """Decode one already-pinned byte snapshot as strict evidence JSON."""

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in items:
            if key in result:
                raise RuntimeReadinessError("duplicate JSON object key")
            result[key] = item
        return result

    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeReadinessError("evidence is not strict UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeReadinessError("evidence root is not an object")
    assert_receipt_safe(value)
    return value


def read_json_evidence(
    path: Path | str, *, limit: int = MAX_RECEIPT_BYTES, require_private: bool = True
) -> dict[str, Any]:
    data, evidence = _stable_file_bytes(path, limit)
    if evidence["links"] != 1 or (
        os.name == "posix"
        and require_private
        and (evidence["mode"] != "0600" or evidence["uid"] != os.geteuid())
    ):
        raise RuntimeReadinessError("evidence is not private and single-linked")
    return _decode_json_evidence(data)


def write_json_evidence(
    path: Path | str, value: Mapping[str, Any], *, limit: int = MAX_RECEIPT_BYTES
) -> dict[str, Any]:
    assert_receipt_safe(value)
    encoded = json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    if len(encoded) > limit:
        raise RuntimeReadinessError("evidence exceeds its byte cap")
    target = Path(path).expanduser()
    if target.exists() or target.is_symlink():
        raise RuntimeReadinessError("evidence target must be fresh")
    parent = target.parent.resolve(strict=True)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(parent / target.name, flags, 0o600)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        view = memoryview(encoded)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise RuntimeReadinessError("evidence write made no progress")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    evidence = _stable_file_bytes(parent / target.name, limit)[1]
    if evidence["links"] != 1 or (os.name == "posix" and evidence["mode"] != "0600"):
        raise RuntimeReadinessError("written evidence is not private and single-linked")
    return {"sha256": evidence["sha256"], "bytes": evidence["bytes"]}


def _path_binding(path: Path | str) -> str:
    resolved = os.path.normcase(os.path.realpath(os.fspath(path)))
    return hashlib.sha256(os.fsencode(resolved)).hexdigest()


def _canonical_source_sha256(path: Path) -> str:
    """Hash Git-canonical LF source bytes on LF and CRLF checkouts alike."""
    data = _stable_file_bytes(path, MAX_CODE_FILE_BYTES)[0]
    canonical = data.replace(b"\r\n", b"\n")
    if b"\r" in canonical:
        raise RuntimeManifestError("source contains a non-canonical carriage return")
    return hashlib.sha256(canonical).hexdigest()


def _lexical_path_binding(path: Path | str) -> str:
    lexical = os.path.normcase(os.path.abspath(os.fspath(path)))
    return hashlib.sha256(os.fsencode(lexical)).hexdigest()


def runtime_identity(
    expected_invocation_path: Path | str | None = None,
) -> dict[str, Any]:
    """Bind runtime content canonically and invocation paths separately."""
    sqlite_info = tuple(int(item) for item in sqlite3.sqlite_version_info)
    if tuple(int(part) for part in sqlite3.sqlite_version.split(".")) != sqlite_info:
        raise RuntimeReadinessError("SQLite string and tuple versions disagree")
    probe = sqlite3.connect(":memory:", isolation_level=None)
    try:
        sqlite_source_id = str(probe.execute("SELECT sqlite_source_id()").fetchone()[0])
        compile_options = sorted(str(row[0]) for row in probe.execute("PRAGMA compile_options"))
    finally:
        probe.close()
    module_path = Path(_sqlite3.__file__).resolve(strict=True)
    module_data, _ = _stable_file_bytes(module_path, MAX_RUNTIME_MODULE_BYTES)
    executable_path = Path(sys.executable).resolve(strict=True)
    executable_data, _ = _stable_file_bytes(executable_path, MAX_RUNTIME_MODULE_BYTES)
    base_executable_path = Path(
        getattr(sys, "_base_executable", sys.executable)
    ).resolve(strict=True)
    base_executable_data, _ = _stable_file_bytes(
        base_executable_path, MAX_RUNTIME_MODULE_BYTES
    )
    python_info = tuple(int(item) for item in sys.version_info[:3])
    virtual_environment = sys.prefix != sys.base_prefix
    exact_runtime_gate = bool(
        python_info == REQUIRED_PYTHON_VERSION
        and sqlite_info == REQUIRED_SQLITE_VERSION
        and sqlite_source_id == REQUIRED_SQLITE_SOURCE_ID
        and virtual_environment
    )
    fingerprint: dict[str, Any] = {
        "schema": "genus-a0-3-c-runtime-fingerprint-v1",
        "implementation": sys.implementation.name,
        "python_version": platform.python_version(),
        "python_version_info": list(sys.version_info[:3]),
        "required_python_version_info": list(REQUIRED_PYTHON_VERSION),
        "sqlite_version": sqlite3.sqlite_version,
        "sqlite_version_info": list(sqlite_info),
        "minimum_sqlite_version_info": list(MINIMUM_SQLITE_VERSION),
        "required_sqlite_version_info": list(REQUIRED_SQLITE_VERSION),
        "sqlite_source_id": sqlite_source_id,
        "required_sqlite_source_id": REQUIRED_SQLITE_SOURCE_ID,
        "compile_options_count": len(compile_options),
        "compile_options_sha256": _sha256_json(compile_options),
        "sqlite_extension": {
            "module_label": module_path.name,
            "module_file_sha256": hashlib.sha256(module_data).hexdigest(),
            "module_file_bytes": len(module_data),
        },
        "python_binary": {
            "label": executable_path.name,
            "file_sha256": hashlib.sha256(executable_data).hexdigest(),
            "file_bytes": len(executable_data),
        },
        "base_python_binary": {
            "label": base_executable_path.name,
            "file_sha256": hashlib.sha256(base_executable_data).hexdigest(),
            "file_bytes": len(base_executable_data),
        },
        "target_sqlite_series": list(TARGET_SQLITE_SERIES),
        "wal_reset_fix_gate_pass": sqlite_info >= MINIMUM_SQLITE_VERSION,
        "exact_runtime_gate_pass": exact_runtime_gate,
        "target_series_match": sqlite_info[:2] == TARGET_SQLITE_SERIES,
        "platform_system": platform.system(),
        "platform_machine": platform.machine(),
        "virtual_environment": virtual_environment,
    }
    fingerprint_sha256 = _sha256_json(fingerprint)
    expected_supplied = expected_invocation_path is not None
    lexical_match = False
    same_file = False
    expected_binding = None
    if expected_invocation_path is not None:
        expected_binding = _lexical_path_binding(expected_invocation_path)
        lexical_match = expected_binding == _lexical_path_binding(sys.executable)
        try:
            same_file = os.path.samefile(expected_invocation_path, sys.executable)
        except (FileNotFoundError, OSError):
            same_file = False
    invocation: dict[str, Any] = {
        "schema": "genus-a0-3-c-runtime-invocation-v1",
        "executable_label": Path(sys.executable).name,
        "invoked_path_sha256": _lexical_path_binding(sys.executable),
        "resolved_executable_path_sha256": _path_binding(sys.executable),
        "resolved_base_executable_path_sha256": _path_binding(base_executable_path),
        "prefix_path_sha256": _path_binding(sys.prefix),
        "base_prefix_path_sha256": _path_binding(sys.base_prefix),
        "expected_invocation_path_supplied": expected_supplied,
        "expected_invocation_path_sha256": expected_binding,
        "expected_invocation_lexical_match": lexical_match,
        "expected_invocation_same_file": same_file,
        "expected_invocation_attested": bool(
            expected_supplied and lexical_match and same_file
        ),
    }
    invocation_sha256 = _sha256_json(invocation)
    body: dict[str, Any] = {
        "schema": RUNTIME_IDENTITY_SCHEMA,
        "runtime_fingerprint": fingerprint,
        "runtime_fingerprint_sha256": fingerprint_sha256,
        "invocation_identity": invocation,
        "invocation_identity_sha256": invocation_sha256,
        "environment": {
            "prefix_path_sha256": _path_binding(sys.prefix),
            "base_prefix_path_sha256": _path_binding(sys.base_prefix),
            "virtual_environment": virtual_environment,
        },
        "paths_logged": False,
        "payloads_logged": False,
    }
    body["identity_sha256"] = _sha256_json(body)
    assert_receipt_safe(body)
    return body


def _validate_runtime_identity(identity: Mapping[str, Any], require_gate: bool) -> str:
    if identity.get("schema") != RUNTIME_IDENTITY_SCHEMA:
        raise RuntimeManifestError("runtime identity schema differs")
    unsigned = {key: item for key, item in identity.items() if key != "identity_sha256"}
    digest = identity.get("identity_sha256")
    if not isinstance(digest, str) or digest != _sha256_json(unsigned):
        raise RuntimeManifestError("runtime identity digest differs")
    fingerprint = identity.get("runtime_fingerprint")
    invocation = identity.get("invocation_identity")
    if not isinstance(fingerprint, Mapping) or not isinstance(invocation, Mapping):
        raise RuntimeManifestError("runtime fingerprint or invocation identity is missing")
    fingerprint_digest = identity.get("runtime_fingerprint_sha256")
    invocation_digest = identity.get("invocation_identity_sha256")
    if (
        fingerprint.get("schema") != "genus-a0-3-c-runtime-fingerprint-v1"
        or not isinstance(fingerprint_digest, str)
        or fingerprint_digest != _sha256_json(fingerprint)
        or invocation.get("schema") != "genus-a0-3-c-runtime-invocation-v1"
        or not isinstance(invocation_digest, str)
        or invocation_digest != _sha256_json(invocation)
    ):
        raise RuntimeManifestError("runtime fingerprint or invocation digest differs")
    version = fingerprint.get("sqlite_version_info")
    python_version = fingerprint.get("python_version_info")
    environment = identity.get("environment")
    if not isinstance(version, list) or any(not isinstance(item, int) for item in version):
        raise RuntimeManifestError("runtime SQLite tuple is malformed")
    if (
        not isinstance(python_version, list)
        or any(not isinstance(item, int) for item in python_version)
        or not isinstance(environment, Mapping)
    ):
        raise RuntimeManifestError("runtime Python tuple or environment is malformed")
    minimum_gate = tuple(version) >= MINIMUM_SQLITE_VERSION
    exact_gate = bool(
        python_version == list(REQUIRED_PYTHON_VERSION)
        and fingerprint.get("python_version")
        == ".".join(str(item) for item in python_version)
        and version == list(REQUIRED_SQLITE_VERSION)
        and fingerprint.get("sqlite_version")
        == ".".join(str(item) for item in version)
        and fingerprint.get("minimum_sqlite_version_info")
        == list(MINIMUM_SQLITE_VERSION)
        and fingerprint.get("sqlite_source_id") == REQUIRED_SQLITE_SOURCE_ID
        and fingerprint.get("required_sqlite_source_id") == REQUIRED_SQLITE_SOURCE_ID
        and fingerprint.get("required_python_version_info") == list(REQUIRED_PYTHON_VERSION)
        and fingerprint.get("required_sqlite_version_info") == list(REQUIRED_SQLITE_VERSION)
        and _HEX64.fullmatch(str(fingerprint.get("compile_options_sha256"))) is not None
        and isinstance(fingerprint.get("compile_options_count"), int)
        and fingerprint.get("compile_options_count", 0) > 0
        and isinstance(fingerprint.get("sqlite_extension"), Mapping)
        and _HEX64.fullmatch(str(fingerprint["sqlite_extension"].get("module_file_sha256"))) is not None
        and isinstance(fingerprint["sqlite_extension"].get("module_file_bytes"), int)
        and fingerprint["sqlite_extension"].get("module_file_bytes", 0) > 0
        and isinstance(fingerprint.get("python_binary"), Mapping)
        and _HEX64.fullmatch(str(fingerprint["python_binary"].get("file_sha256"))) is not None
        and isinstance(fingerprint["python_binary"].get("file_bytes"), int)
        and fingerprint["python_binary"].get("file_bytes", 0) > 0
        and isinstance(fingerprint.get("base_python_binary"), Mapping)
        and _HEX64.fullmatch(str(fingerprint["base_python_binary"].get("file_sha256"))) is not None
        and isinstance(fingerprint["base_python_binary"].get("file_bytes"), int)
        and fingerprint["base_python_binary"].get("file_bytes", 0) > 0
        and fingerprint.get("implementation") == "cpython"
        and fingerprint.get("target_sqlite_series") == list(TARGET_SQLITE_SERIES)
        and fingerprint.get("target_series_match")
        is (tuple(version[:2]) == TARGET_SQLITE_SERIES)
        and fingerprint.get("virtual_environment") is True
        and environment.get("virtual_environment") is True
        and fingerprint.get("virtual_environment")
        is environment.get("virtual_environment")
    )
    if fingerprint.get("wal_reset_fix_gate_pass") is not minimum_gate:
        raise RuntimeManifestError("runtime minimum SQLite gate is inconsistent")
    if fingerprint.get("exact_runtime_gate_pass") is not exact_gate:
        raise RuntimeManifestError("runtime exact gate is inconsistent")
    if require_gate and not exact_gate:
        raise RuntimeManifestError("exact Python/SQLite runtime gate did not pass")
    return str(fingerprint_digest)


def gate_command_argv(gate: str) -> tuple[str, ...]:
    """Return one fixed, path-relative gate command (without the Python executable)."""
    try:
        return GATE_COMMANDS[gate]
    except KeyError as exc:
        raise RuntimeManifestError("unknown A0.3c gate") from exc


def create_gate_receipt(
    *,
    gate: str,
    candidate_commit: str,
    exit_status: int,
    stdout_sha256: str,
    stderr_sha256: str,
    test_count: int,
    identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind one execution of a predefined gate without retaining test output."""
    command = gate_command_argv(gate)
    commit = candidate_commit.casefold()
    if not _COMMIT.fullmatch(commit):
        raise RuntimeManifestError("gate candidate commit is malformed")
    if not _HEX64.fullmatch(stdout_sha256) or not _HEX64.fullmatch(stderr_sha256):
        raise RuntimeManifestError("gate output digest is malformed")
    if isinstance(test_count, bool) or test_count < 0:
        raise RuntimeManifestError("gate test count must be non-negative")
    current = dict(identity) if identity is not None else runtime_identity()
    identity_digest = _validate_runtime_identity(current, True)
    passed = exit_status == 0 and test_count > 0
    body: dict[str, Any] = {
        "schema": GATE_RECEIPT_SCHEMA,
        "gate": gate,
        "command_contract_sha256": _sha256_json(list(command)),
        "environment_contract_sha256": _sha256_json(GATE_ENVIRONMENT_CONTRACT),
        "candidate_commit": commit,
        "runtime_identity_sha256": identity_digest,
        "exit_status": exit_status,
        "test_count": test_count,
        "stdout_sha256": stdout_sha256,
        "stderr_sha256": stderr_sha256,
        "pass": passed,
        "outcome": "green" if passed else "red",
        "paths_logged": False,
        "payloads_logged": False,
    }
    receipt = _seal_receipt(body)
    assert_receipt_safe(receipt)
    return receipt


def _load_green_gate_receipt(
    path: Path | str,
    *,
    expected_gate: str,
    candidate_commit: str,
    runtime_identity_sha256: str,
) -> dict[str, Any]:
    receipt = read_json_evidence(path, limit=MAX_RECEIPT_BYTES, require_private=True)
    file_stat = _stable_file_bytes(path, MAX_RECEIPT_BYTES)[1]
    if receipt.get("schema") != GATE_RECEIPT_SCHEMA:
        raise RuntimeManifestError("gate receipt schema differs")
    receipt_digest = _verify_receipt_digest(receipt, f"gate {expected_gate}")
    command = gate_command_argv(expected_gate)
    if (
        receipt.get("gate") != expected_gate
        or receipt.get("command_contract_sha256") != _sha256_json(list(command))
        or receipt.get("environment_contract_sha256")
        != _sha256_json(GATE_ENVIRONMENT_CONTRACT)
        or receipt.get("candidate_commit") != candidate_commit
        or receipt.get("runtime_identity_sha256") != runtime_identity_sha256
        or receipt.get("exit_status") != 0
        or receipt.get("pass") is not True
        or receipt.get("outcome") != "green"
        or not isinstance(receipt.get("test_count"), int)
        or receipt.get("test_count", 0) < 1
    ):
        raise RuntimeManifestError("gate receipt is not an exact green candidate gate")
    return {
        "gate": expected_gate,
        "receipt_sha256": receipt_digest,
        "file_sha256": file_stat["sha256"],
        "file_bytes": file_stat["bytes"],
        "command_contract_sha256": receipt["command_contract_sha256"],
        "environment_contract_sha256": receipt["environment_contract_sha256"],
        "test_count": receipt["test_count"],
    }


def a03b_code_hashes(code_root: Path | str) -> dict[str, str]:
    raw = Path(code_root).expanduser()
    if raw.is_symlink():
        raise RuntimeManifestError("code root must not be a symlink")
    root = raw.resolve(strict=True)
    result: dict[str, str] = {}
    for role, relative in sorted(_A03B_FILES.items()):
        target = root / relative
        if target.is_symlink() or not target.is_file():
            raise RuntimeManifestError(f"A0.3b {role} is not a regular file")
        result[role] = _canonical_source_sha256(target)
    if result != ACCEPTED_A03B_CODE_SHA256:
        raise RuntimeManifestError("A0.3b code differs from accepted hashes")
    return result


def a03c_code_hashes(code_root: Path | str) -> dict[str, str]:
    """Bind the complete A0.3c candidate that is actually executing."""
    raw = Path(code_root).expanduser()
    if raw.is_symlink():
        raise RuntimeManifestError("code root must not be a symlink")
    root = raw.resolve(strict=True)
    result: dict[str, str] = {}
    for role, relative in sorted(_A03C_FILES.items()):
        target = root / relative
        if target.is_symlink() or not target.is_file():
            raise RuntimeManifestError(f"A0.3c {role} is not a regular file")
        result[role] = _canonical_source_sha256(target)
    return result


def required_candidate_config() -> dict[str, Any]:
    return {
        "topology": "option-c-same-file-generation-pointer",
        "final_sync_mode": "a_bounded_fence",
        "batch_events": REQUIRED_BATCH_EVENTS,
        "batch_bytes": REQUIRED_BATCH_BYTES,
        "writer_interval_seconds": REQUIRED_WRITER_INTERVAL_SECONDS,
        "short_reader_interval_seconds": REQUIRED_READER_INTERVAL_SECONDS,
        "projection_count": 12,
        "sequence_count": 9,
        "budgets": {
            "writer_block_seconds": a03b.WRITER_BLOCK_BUDGET_SECONDS,
            "recovery_seconds": a03b.RECOVERY_BUDGET_SECONDS,
            "rebuild_seconds": a03b.REBUILD_BUDGET_SECONDS,
            "rss_bytes": a03b.RSS_BUDGET_BYTES,
            "wal_bytes": a03b.WAL_BUDGET_BYTES,
        },
    }


def create_runtime_manifest(
    *,
    code_root: Path | str,
    candidate_commit: str,
    gate_receipt_paths: Mapping[str, Path | str],
    identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    commit = candidate_commit.casefold()
    required = {"full_suite", "a0_2_golden", "a0_2_historical_sqlite"}
    gate_paths = dict(gate_receipt_paths)
    if not _COMMIT.fullmatch(commit):
        raise RuntimeManifestError("candidate commit must be forty lowercase hex digits")
    if set(gate_paths) != required:
        raise RuntimeManifestError("three exact green gate receipt files are required")
    pinned = dict(identity) if identity is not None else runtime_identity()
    identity_digest = _validate_runtime_identity(pinned, True)
    gates = {
        gate: _load_green_gate_receipt(
            gate_paths[gate],
            expected_gate=gate,
            candidate_commit=commit,
            runtime_identity_sha256=identity_digest,
        )
        for gate in sorted(required)
    }
    body: dict[str, Any] = {
        "schema": RUNTIME_MANIFEST_SCHEMA,
        "candidate_commit": commit,
        "runtime_identity": pinned,
        "runtime_identity_sha256": identity_digest,
        "runtime_fingerprint": dict(pinned["runtime_fingerprint"]),
        "candidate_invocation_identity_sha256": pinned[
            "invocation_identity_sha256"
        ],
        "a0_3b_code_sha256": a03b_code_hashes(code_root),
        "a0_3c_code_sha256": a03c_code_hashes(code_root),
        "candidate_config": required_candidate_config(),
        "gate_evidence": gates,
        "retuning_allowed_within_series": False,
        "product_activation_authorized": False,
        "paths_logged": False,
        "payloads_logged": False,
    }
    body["manifest_sha256"] = _sha256_json(body)
    assert_receipt_safe(body)
    return body


def verify_runtime_manifest(
    manifest: Mapping[str, Any],
    *,
    code_root: Path | str,
    expected_candidate_commit: str | None = None,
    identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if manifest.get("schema") != RUNTIME_MANIFEST_SCHEMA:
        raise RuntimeManifestError("runtime manifest schema differs")
    unsigned = {key: item for key, item in manifest.items() if key != "manifest_sha256"}
    digest = manifest.get("manifest_sha256")
    if not isinstance(digest, str) or digest != _sha256_json(unsigned):
        raise RuntimeManifestError("runtime manifest digest differs")
    commit = manifest.get("candidate_commit")
    if not isinstance(commit, str) or not _COMMIT.fullmatch(commit):
        raise RuntimeManifestError("candidate commit is malformed")
    if expected_candidate_commit is not None and commit != expected_candidate_commit.casefold():
        raise RuntimeManifestError("candidate commit differs from expected pin")
    pinned = manifest.get("runtime_identity")
    if not isinstance(pinned, Mapping):
        raise RuntimeManifestError("runtime identity is missing")
    pinned_digest = _validate_runtime_identity(pinned, True)
    current = dict(identity) if identity is not None else runtime_identity()
    current_digest = _validate_runtime_identity(current, True)
    if (
        current_digest != pinned_digest
        or current.get("runtime_fingerprint") != pinned.get("runtime_fingerprint")
        or manifest.get("runtime_fingerprint") != pinned.get("runtime_fingerprint")
    ):
        raise RuntimeManifestError("current runtime differs from manifest")
    required = {"full_suite", "a0_2_golden", "a0_2_historical_sqlite"}
    gates = manifest.get("gate_evidence")
    if manifest.get("runtime_identity_sha256") != pinned_digest:
        raise RuntimeManifestError("runtime identity binding differs")
    if (
        manifest.get("candidate_invocation_identity_sha256")
        != pinned.get("invocation_identity_sha256")
        or manifest.get("runtime_fingerprint") != pinned.get("runtime_fingerprint")
    ):
        raise RuntimeManifestError("candidate invocation/fingerprint binding differs")
    if manifest.get("a0_3b_code_sha256") != a03b_code_hashes(code_root):
        raise RuntimeManifestError("A0.3b code binding differs")
    if manifest.get("a0_3c_code_sha256") != a03c_code_hashes(code_root):
        raise RuntimeManifestError("A0.3c code binding differs")
    if manifest.get("candidate_config") != required_candidate_config():
        raise RuntimeManifestError("candidate configuration differs")
    if not isinstance(gates, Mapping) or set(gates) != required or any(
        not isinstance(value, Mapping)
        or value.get("gate") != gate
        or not _HEX64.fullmatch(str(value.get("receipt_sha256")))
        or not _HEX64.fullmatch(str(value.get("file_sha256")))
        or value.get("command_contract_sha256") != _sha256_json(list(gate_command_argv(gate)))
        or value.get("environment_contract_sha256")
        != _sha256_json(GATE_ENVIRONMENT_CONTRACT)
        or not isinstance(value.get("test_count"), int)
        or value.get("test_count", 0) < 1
        for gate, value in gates.items()
    ):
        raise RuntimeManifestError("test-gate evidence is incomplete")
    if manifest.get("retuning_allowed_within_series") is not False or manifest.get("product_activation_authorized") is not False:
        raise RuntimeManifestError("manifest weakens a fail-closed gate")
    return _seal_receipt({
        "schema": MANIFEST_VERIFICATION_SCHEMA,
        "outcome": "verified",
        "manifest_sha256": digest,
        "candidate_commit": commit,
        "runtime_identity_sha256": pinned_digest,
        "current_invocation_identity_sha256": current[
            "invocation_identity_sha256"
        ],
        "expected_invocation_attested": current["invocation_identity"].get(
            "expected_invocation_attested"
        ),
        "candidate_config_sha256": _sha256_json(required_candidate_config()),
        "a0_3b_code_sha256": dict(manifest["a0_3b_code_sha256"]),
        "a0_3c_code_sha256": dict(manifest["a0_3c_code_sha256"]),
        "gate_evidence": {key: dict(value) for key, value in gates.items()},
        "wal_reset_fix_gate_pass": True,
        "paths_logged": False,
        "payloads_logged": False,
    })


class _ReadTrace:
    """Record SQL statement classes only; never retain text or parameters."""

    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()
        self.invalid = False

    def __call__(self, statement: str) -> None:
        token = statement.lstrip().split(None, 1)
        statement_class = token[0].upper().rstrip(";") if token else "EMPTY"
        self.counts[statement_class] += 1
        if statement_class not in {"PRAGMA", "SELECT"}:
            self.invalid = True

    def receipt(self) -> dict[str, Any]:
        if self.invalid or not set(self.counts).issubset({"PRAGMA", "SELECT"}):
            raise AcquisitionError("read trace contains a write-capable statement")
        return {
            "statement_classes": sorted(self.counts),
            "statement_class_counts": dict(sorted(self.counts.items())),
            "only_select_or_pragma": True,
            "sql_text_logged": False,
        }


class _StrictResourceSampler:
    """Outer sampler whose errors and zero RSS fail readiness closed."""

    SCHEMA = "genus-a0-3-c-resource-sample-v1"

    def __init__(self, path: Path, phase: str, interval_seconds: float = 0.02):
        self.path = path
        self.phase = phase
        self.interval_seconds = interval_seconds
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.peak_rss_bytes = 0
        self.highwater = {"database": 0, "wal": 0, "shm": 0, "journal": 0}
        self.samples = 0
        self.error_counts: Counter[str] = Counter()
        self.thread_alive_after_join = False

    def _sample(self) -> None:
        with self.lock:
            try:
                rss = int(psutil.Process(os.getpid()).memory_info().rss)
            except (psutil.Error, OSError):
                self.error_counts["rss"] += 1
                rss = 0
            self.peak_rss_bytes = max(self.peak_rss_bytes, rss)
            for key, suffix in (
                ("database", ""),
                ("wal", "-wal"),
                ("shm", "-shm"),
                ("journal", "-journal"),
            ):
                try:
                    size = int(Path(f"{self.path}{suffix}").stat().st_size)
                except FileNotFoundError:
                    if key == "database":
                        self.error_counts["database_missing"] += 1
                    size = 0
                except OSError:
                    self.error_counts[f"{key}_stat"] += 1
                    size = 0
                self.highwater[key] = max(self.highwater[key], size)
            self.samples += 1

    def _loop(self) -> None:
        try:
            while not self.stop.wait(self.interval_seconds):
                self._sample()
        except BaseException:
            with self.lock:
                self.error_counts["sampler_loop"] += 1

    def __enter__(self) -> "_StrictResourceSampler":
        self._sample()
        self.thread.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.stop.set()
        self.thread.join(timeout=max(1.0, self.interval_seconds * 4))
        self.thread_alive_after_join = self.thread.is_alive()
        if self.thread_alive_after_join:
            with self.lock:
                self.error_counts["thread_join"] += 1
        self._sample()

    def receipt(self) -> dict[str, Any]:
        with self.lock:
            errors = dict(sorted(self.error_counts.items()))
            error_count = sum(errors.values())
            gate = bool(
                self.samples >= 2
                and error_count == 0
                and self.peak_rss_bytes > 0
                and not self.thread_alive_after_join
                and self.peak_rss_bytes <= a03b.RSS_BUDGET_BYTES
                and self.highwater["wal"] <= a03b.WAL_BUDGET_BYTES
            )
            return {
                "schema": self.SCHEMA,
                "phase": self.phase,
                "sample_count": self.samples,
                "error_count": error_count,
                "error_counts": errors,
                "peak_rss_bytes": self.peak_rss_bytes,
                "storage_highwater_bytes": dict(self.highwater),
                "thread_alive_after_join": self.thread_alive_after_join,
                "rss_nonzero": self.peak_rss_bytes > 0,
                "gate_pass": gate,
            }


def _strict_write_receipt(
    receipt: Mapping[str, Any], *, expected_scope: str, require_claim: bool = False
) -> dict[str, Any]:
    count_keys = (
        "attempt_count",
        "transaction_count",
        "committed_count",
        "rolled_back_count",
        "begin_error_count",
    )
    exact_keys = {
        "schema", "scope", "exhaustive", "evidence_complete",
        *count_keys, "open_transaction_count", "phase_stats",
        "phase_max_transaction_seconds", "overall_max_transaction_seconds",
        "overall_max_seconds", "max_lock_wait_seconds", "limit_seconds", "pass",
    }
    if require_claim:
        exact_keys.add("claim")

    def count(value: Any) -> bool:
        return not isinstance(value, bool) and isinstance(value, int) and value >= 0

    phase_stats = receipt.get("phase_stats")
    phase_totals = {key: 0 for key in count_keys}
    phase_max: dict[str, float] = {}
    lock_max = 0.0
    phases_valid = isinstance(phase_stats, Mapping)
    if phases_valid:
        expected_keys = {*count_keys, "max_transaction_seconds", "max_lock_wait_seconds"}
        for phase, raw in phase_stats.items():
            if (
                not isinstance(phase, str)
                or not isinstance(raw, Mapping)
                or set(raw) != expected_keys
                or not all(count(raw.get(key)) for key in count_keys)
            ):
                phases_valid = False
                break
            transaction_max = raw.get("max_transaction_seconds")
            phase_lock_max = raw.get("max_lock_wait_seconds")
            if any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0
                for value in (transaction_max, phase_lock_max)
            ):
                phases_valid = False
                break
            if (
                raw["attempt_count"]
                != raw["transaction_count"] + raw["begin_error_count"]
                or raw["transaction_count"]
                != raw["committed_count"] + raw["rolled_back_count"]
            ):
                phases_valid = False
                break
            for key in count_keys:
                phase_totals[key] += int(raw[key])
            phase_max[phase] = float(transaction_max)
            lock_max = max(lock_max, float(phase_lock_max))
    numeric_keys = (
        "overall_max_transaction_seconds",
        "overall_max_seconds",
        "max_lock_wait_seconds",
        "limit_seconds",
    )
    numerics_valid = all(
        not isinstance(receipt.get(key), bool)
        and isinstance(receipt.get(key), (int, float))
        and math.isfinite(float(receipt[key]))
        and float(receipt[key]) >= 0
        for key in numeric_keys
    )
    outer_counts_valid = all(count(receipt.get(key)) for key in count_keys)
    expected_max = max(phase_max.values(), default=0.0)
    arithmetic = bool(
        outer_counts_valid
        and receipt.get("attempt_count")
        == receipt.get("transaction_count", 0) + receipt.get("begin_error_count", 0)
        and receipt.get("transaction_count")
        == receipt.get("committed_count", 0) + receipt.get("rolled_back_count", 0)
        and phases_valid
        and all(receipt.get(key) == phase_totals[key] for key in count_keys)
        and receipt.get("phase_max_transaction_seconds") == phase_max
        and numerics_valid
        and float(receipt["overall_max_transaction_seconds"]) == expected_max
        and float(receipt["overall_max_seconds"]) == expected_max
        and float(receipt["max_lock_wait_seconds"]) == lock_max
    )
    gate = bool(
        set(receipt) == exact_keys
        and receipt.get("schema") == a03b.WRITE_TRANSACTION_RECEIPT_SCHEMA
        and receipt.get("scope") == expected_scope
        and receipt.get("exhaustive") is True
        and receipt.get("evidence_complete") is True
        and receipt.get("open_transaction_count") == 0
        and (not require_claim or receipt.get("claim") == "all_experimental_write_transactions")
        and receipt.get("begin_error_count") == 0
        and receipt.get("limit_seconds") == a03b.WRITER_BLOCK_BUDGET_SECONDS
        and receipt.get("pass") is True
        and arithmetic
        and expected_max <= a03b.WRITER_BLOCK_BUDGET_SECONDS
    )
    return {
        "schema": receipt.get("schema"),
        "scope": receipt.get("scope"),
        "exhaustive": receipt.get("exhaustive"),
        "arithmetic_pass": arithmetic,
        "transaction_count": receipt.get("transaction_count"),
        "overall_max_transaction_seconds": receipt.get(
            "overall_max_transaction_seconds"
        ),
        "gate_pass": gate,
    }


def _strict_resource_receipt(
    receipt: Mapping[str, Any], *, expected_phase: str
) -> dict[str, Any]:
    errors = receipt.get("error_counts")
    storage = receipt.get("storage_highwater_bytes")
    error_sum = (
        sum(errors.values())
        if isinstance(errors, Mapping)
        and all(
            isinstance(key, str)
            and not isinstance(value, bool)
            and isinstance(value, int)
            and value >= 0
            for key, value in errors.items()
        )
        else -1
    )
    storage_valid = bool(
        isinstance(storage, Mapping)
        and set(storage) == {"database", "wal", "shm", "journal"}
        and all(
            not isinstance(value, bool) and isinstance(value, int) and value >= 0
            for value in storage.values()
        )
    )
    expected_gate = bool(
        set(receipt) == {
            "schema", "phase", "sample_count", "error_count", "error_counts",
            "peak_rss_bytes", "storage_highwater_bytes",
            "thread_alive_after_join", "rss_nonzero", "gate_pass",
        }
        and receipt.get("schema") == _StrictResourceSampler.SCHEMA
        and receipt.get("phase") == expected_phase
        and isinstance(receipt.get("sample_count"), int)
        and not isinstance(receipt.get("sample_count"), bool)
        and receipt.get("sample_count", 0) >= 2
        and error_sum == 0
        and receipt.get("error_count") == 0
        and isinstance(receipt.get("peak_rss_bytes"), int)
        and not isinstance(receipt.get("peak_rss_bytes"), bool)
        and 0 < receipt.get("peak_rss_bytes", 0) <= a03b.RSS_BUDGET_BYTES
        and storage_valid
        and storage.get("wal", a03b.WAL_BUDGET_BYTES + 1)
        <= a03b.WAL_BUDGET_BYTES
        and receipt.get("thread_alive_after_join") is False
        and receipt.get("rss_nonzero") is True
    )
    return {
        "phase": receipt.get("phase"),
        "sample_count": receipt.get("sample_count"),
        "error_count": receipt.get("error_count"),
        "peak_rss_bytes": receipt.get("peak_rss_bytes"),
        "wal_highwater_bytes": storage.get("wal") if storage_valid else None,
        "gate_pass": expected_gate and receipt.get("gate_pass") is True,
    }


def _missing_resource_receipt(phase: str) -> dict[str, Any]:
    return {
        "schema": _StrictResourceSampler.SCHEMA,
        "phase": phase,
        "sample_count": 0,
        "error_count": 1,
        "error_counts": {"phase_not_started": 1},
        "peak_rss_bytes": 0,
        "storage_highwater_bytes": {
            "database": 0,
            "wal": 0,
            "shm": 0,
            "journal": 0,
        },
        "thread_alive_after_join": False,
        "rss_nonzero": False,
        "gate_pass": False,
    }


def _private_root(raw: Path | str, *, require_empty: bool) -> tuple[Path, dict[str, Any]]:
    path = Path(raw).expanduser()
    if path.is_symlink():
        raise AcquisitionError("disposable root must not be a symlink")
    try:
        root = path.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise AcquisitionError("disposable root does not exist") from exc
    if not root.is_dir():
        raise AcquisitionError("disposable root is not a directory")
    value = root.stat(follow_symlinks=False)
    if os.name == "posix" and (
        int(value.st_uid) != int(os.geteuid()) or stat.S_IMODE(value.st_mode) != 0o700
    ):
        raise AcquisitionError("disposable root must be owned by the user and mode 0700")
    entries = list(root.iterdir())
    if len(entries) > 16:
        raise AcquisitionError("disposable root exceeds the entry cap")
    if require_empty and entries:
        raise AcquisitionError("acquisition requires a fresh empty root")
    return root, {
        "owner_is_effective_user": True,
        "mode_0700_posix": True if os.name == "posix" else None,
        "posix_enforced": os.name == "posix",
        "device": int(value.st_dev),
        "inode": int(value.st_ino),
        "fresh_empty": require_empty,
    }


def _private_file(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise AcquisitionError(f"{label} is not a regular non-symlink file")
    value = path.stat(follow_symlinks=False)
    mode = stat.S_IMODE(value.st_mode)
    if value.st_nlink != 1 or (os.name == "posix" and mode != 0o600):
        raise AcquisitionError(f"{label} is not private and single-linked")
    return {
        "mode": f"{mode:04o}",
        "mode_0600_posix": True if os.name == "posix" else None,
        "links": int(value.st_nlink),
        "bytes": int(value.st_size),
        "device": int(value.st_dev),
        "inode": int(value.st_ino),
    }


def _source_file(raw: Path | str, root: Path) -> tuple[Path, os.stat_result]:
    path = Path(raw).expanduser()
    if path.is_symlink():
        raise AcquisitionError("product database must not be a symlink")
    source = path.resolve(strict=True)
    if not source.is_file() or source == root or root in source.parents:
        raise AcquisitionError("product database is not a regular file outside the root")
    value = source.stat(follow_symlinks=False)
    if value.st_nlink != 1:
        raise AcquisitionError("product database must not be hardlinked")
    return source, value


def _open_readonly(path: Path) -> tuple[sqlite3.Connection, _ReadTrace]:
    conn = sqlite3.connect(
        path.as_uri() + "?mode=ro", uri=True, isolation_level=None, timeout=5.0
    )
    conn.row_factory = sqlite3.Row
    trace = _ReadTrace()
    conn.set_trace_callback(trace)
    conn.execute("PRAGMA query_only=ON")
    if int(conn.execute("PRAGMA query_only").fetchone()[0]) != 1:
        conn.close()
        raise AcquisitionError("query_only could not be enabled")
    return conn, trace


def _close_readonly(conn: sqlite3.Connection, trace: _ReadTrace) -> dict[str, Any]:
    try:
        if conn.in_transaction or conn.total_changes != 0:
            raise AcquisitionError("read-only connection reports a write or transaction")
        trace_receipt = trace.receipt()
    finally:
        conn.set_trace_callback(None)
        conn.close()
    return {
        "uri_mode": "ro",
        "isolation_level": None,
        "query_only": True,
        "total_changes": 0,
        "active_transaction": False,
        "trace": trace_receipt,
    }


def _identity_stat(path: Path, fd: int, identity: tuple[int, int]) -> os.stat_result:
    if path.is_symlink() or not path.is_file():
        raise AcquisitionError("copy pathname is not a regular file")
    for value in (path.stat(follow_symlinks=False), os.fstat(fd)):
        if (int(value.st_dev), int(value.st_ino)) != identity:
            raise AcquisitionError("copy pathname identity changed")
        if value.st_nlink != 1 or (os.name == "posix" and stat.S_IMODE(value.st_mode) != 0o600):
            raise AcquisitionError("copy is not private and single-linked")
    return path.stat(follow_symlinks=False)


def _linux_matching_fds(identity: tuple[int, int], guard_fd: int) -> int | None:
    if not sys.platform.startswith("linux"):
        return None
    directory = Path("/proc/self/fd")
    if not directory.is_dir():
        raise AcquisitionError("Linux fd identity proof is unavailable")
    matches = 0
    for entry in directory.iterdir():
        try:
            descriptor = int(entry.name)
            if descriptor == guard_fd:
                continue
            value = entry.stat()
        except (FileNotFoundError, OSError, ValueError):
            continue
        if (int(value.st_dev), int(value.st_ino)) == identity:
            matches += 1
    return matches


def _backup(source: sqlite3.Connection, source_path: Path, target: Path) -> dict[str, Any]:
    sidecars = [Path(f"{target}{suffix}") for suffix in ("-wal", "-shm", "-journal")]
    if target.exists() or target.is_symlink() or any(item.exists() for item in sidecars):
        raise AcquisitionError("Backup API target is not fresh")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(target, flags, 0o600)
    identity = (int(os.fstat(fd).st_dev), int(os.fstat(fd).st_ino))
    destination: sqlite3.Connection | None = None
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        _identity_stat(target, fd, identity)
        before_sqlite_fds = _linux_matching_fds(identity, fd)
        if before_sqlite_fds not in (None, 0):
            raise AcquisitionError("copy has an unexplained descriptor before SQLite open")
        destination = sqlite3.connect(
            target.as_uri() + "?mode=rw", uri=True, isolation_level=None, timeout=5.0
        )
        _identity_stat(target, fd, identity)
        after_open_fds = _linux_matching_fds(identity, fd)
        if after_open_fds not in (None, 1):
            raise AcquisitionError("SQLite destination descriptor identity is unproven")
        source_stat = source_path.stat(follow_symlinks=False)
        if (int(source_stat.st_dev), int(source_stat.st_ino)) == identity:
            raise AcquisitionError("source and destination are the same inode")
        if destination.total_changes or destination.in_transaction:
            raise AcquisitionError("fresh backup destination is not pristine")
        source.backup(destination, pages=1_024, sleep=0.01)
        if destination.total_changes or destination.in_transaction:
            raise AcquisitionError("Backup API destination reports SQL DML")
        _identity_stat(target, fd, identity)
        after_backup_fds = _linux_matching_fds(identity, fd)
        if after_backup_fds not in (None, 1):
            raise AcquisitionError("SQLite destination descriptor changed during backup")
        os.fsync(fd)
    finally:
        if destination is not None:
            destination.close()
        final = _identity_stat(target, fd, identity)
        os.close(fd)
    if final.st_size < 512 or any(item.exists() or item.is_symlink() for item in sidecars):
        raise AcquisitionError("Backup API did not leave one complete sidecar-free database")
    return {
        "method": "sqlite3.Connection.backup",
        "pages_per_step": 1_024,
        "sleep_seconds": 0.01,
        "destination_precreated_exclusive": True,
        "destination_mode": "0600",
        "destination_nlink_one": True,
        "destination_device": identity[0],
        "destination_inode": identity[1],
        "sqlite_fd_zero_before_open_linux": True if before_sqlite_fds is not None else None,
        "sqlite_fd_exactly_one_after_open_linux": True if after_open_fds is not None else None,
        "sqlite_fd_exactly_one_after_backup_linux": True if after_backup_fds is not None else None,
        "guard_path_identity_stable": True,
        "database_bytes": int(final.st_size),
        "sidecars_absent": True,
    }


def _sequence_state(conn: sqlite3.Connection) -> dict[str, int]:
    result: dict[str, int] = {}
    for table in a03b.SEQUENCE_TABLES:
        row = conn.execute("SELECT seq FROM sqlite_sequence WHERE name=?", (table,)).fetchone()
        result[table] = 0 if row is None else int(row[0])
    if len(result) != 9:
        raise AcquisitionError("sequence oracle is not exactly nine")
    return result


def _capture_fence_readonly(conn: sqlite3.Connection) -> a03a.ReplayFence:
    count, min_id, head_id = conn.execute(
        "SELECT COUNT(*), MIN(id), MAX(id) FROM event_log"
    ).fetchone()
    epoch = conn.execute(
        "SELECT id FROM event_log WHERE event_type=? ORDER BY id LIMIT 1",
        (sealing.EPOCH_EVENT,),
    ).fetchone()
    head_seal = None
    if head_id is not None:
        row = conn.execute("SELECT seal FROM event_log WHERE id=?", (int(head_id),)).fetchone()
        if row is None:
            raise AcquisitionError("fixed ledger head disappeared")
        head_seal = row[0]
    return a03a.ReplayFence(
        head_id=None if head_id is None else int(head_id),
        event_count=int(count),
        min_id=None if min_id is None else int(min_id),
        epoch_event_id=None if epoch is None else int(epoch[0]),
        head_seal=head_seal,
    )


def _read_core_id(path: Path | str, root: Path) -> tuple[str, dict[str, Any], str]:
    raw = Path(path).expanduser()
    if raw.is_symlink():
        raise AcquisitionError("core-id file must not be a symlink")
    resolved = raw.resolve(strict=True)
    if not resolved.is_file() or resolved == root or root in resolved.parents:
        raise AcquisitionError("core-id file must be a regular file outside the root")
    data, file_stat = _stable_file_bytes(resolved, MAX_CORE_ID_BYTES)
    if file_stat["links"] != 1:
        raise AcquisitionError("core-id file must not be hardlinked")
    try:
        normalized = anchor.normalize_core_id(data.decode("utf-8"))
    except UnicodeError as exc:
        raise AcquisitionError("core-id file is not UTF-8") from exc
    return normalized, file_stat, hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _verify_anchor_bounded(
    conn: sqlite3.Connection,
    artifact: Mapping[str, Any],
    *,
    full_fence: a03a.ReplayFence,
    expected_core_id: str,
) -> list[str]:
    issues = list(anchor.validate_anchor(dict(artifact)))
    if issues:
        return issues
    if artifact.get("core_id") != expected_core_id:
        return ["anchor core id differs"]
    head_id = int(artifact["head_event_id"])
    if full_fence.head_id is None or head_id > full_fence.head_id:
        return ["anchor head is newer than the copied ledger"]
    if int(artifact["epoch_event_id"]) != full_fence.epoch_event_id:
        issues.append("anchor epoch differs")
    row = conn.execute(
        "SELECT event_type,created_at,seal FROM event_log WHERE id=?", (head_id,)
    ).fetchone()
    if row is None:
        return issues + ["anchor head is absent"]
    if row[0] != artifact["head_event_type"] or row[1] != artifact["head_created_at"] or row[2] != artifact["head"]:
        issues.append("anchor head tuple differs")
    prefix_count = int(
        conn.execute("SELECT COUNT(*) FROM event_log WHERE id<=?", (head_id,)).fetchone()[0]
    )
    if prefix_count != int(artifact["event_count"]):
        issues.append("anchor event count differs")
    anchored_fence = a03a.ReplayFence(
        head_id=head_id,
        event_count=int(artifact["event_count"]),
        min_id=full_fence.min_id,
        epoch_event_id=full_fence.epoch_event_id,
        head_seal=str(artifact["head"]),
    )
    issues.extend(a03a.verify_chain_bounded(conn, anchored_fence, REQUIRED_BATCH_EVENTS))
    return issues


def _select_anchor(
    conn: sqlite3.Connection,
    anchor_dir: Path | str,
    *,
    full_fence: a03a.ReplayFence,
    expected_core_id: str,
    root: Path,
) -> tuple[bytes, dict[str, Any], dict[str, Any], dict[str, Any]]:
    raw = Path(anchor_dir).expanduser()
    if raw.is_symlink():
        raise AcquisitionError("anchor directory must not be a symlink")
    directory = raw.resolve(strict=True)
    if not directory.is_dir() or directory == root or root in directory.parents:
        raise AcquisitionError("anchor directory must be outside the disposable root")
    candidates: list[
        tuple[tuple[int, str, str], bytes, dict[str, Any], dict[str, Any]]
    ] = []
    entry_count = 0
    json_file_count = 0
    with os.scandir(directory) as entries:
        for entry in entries:
            entry_count += 1
            if entry_count > MAX_ANCHOR_DIRECTORY_ENTRIES:
                raise AcquisitionError("anchor directory exceeds its entry cap")
            if not entry.name.casefold().endswith(".json"):
                continue
            try:
                if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                    continue
                json_file_count += 1
                if json_file_count > MAX_ANCHOR_CANDIDATES:
                    raise AcquisitionError("anchor directory exceeds its candidate cap")
                candidate = Path(entry.path)
                data, file_stat = _stable_file_bytes(candidate, MAX_ANCHOR_BYTES)
                if file_stat["links"] != 1:
                    continue
                artifact = json.loads(data.decode("utf-8"))
                if not isinstance(artifact, dict) or anchor.validate_anchor(artifact):
                    continue
                if artifact.get("core_id") != expected_core_id:
                    continue
                rank = (
                    int(artifact["head_event_id"]),
                    str(artifact["created_at"]),
                    entry.name,
                )
                candidates.append((rank, data, artifact, file_stat))
            except AcquisitionError:
                raise
            except (
                OSError,
                UnicodeError,
                ValueError,
                json.JSONDecodeError,
                RuntimeReadinessError,
            ):
                continue
    for _, data, artifact, file_stat in sorted(candidates, key=lambda item: item[0], reverse=True):
        if not _verify_anchor_bounded(
            conn, artifact, full_fence=full_fence, expected_core_id=expected_core_id
        ):
            return data, artifact, file_stat, {
                "streaming_scan": True,
                "entry_count": entry_count,
                "json_file_count": json_file_count,
                "valid_core_candidate_count": len(candidates),
                "entry_cap": MAX_ANCHOR_DIRECTORY_ENTRIES,
                "candidate_cap": MAX_ANCHOR_CANDIDATES,
            }
    raise AcquisitionError("no existing anchor is valid for the copied fixed head")


def _write_private_bytes(path: Path, data: bytes) -> dict[str, Any]:
    if path.exists() or path.is_symlink():
        raise AcquisitionError("pinned anchor target must be fresh")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise AcquisitionError("pinned anchor write made no progress")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    file_stat = _stable_file_bytes(path, MAX_ANCHOR_BYTES)[1]
    if file_stat["links"] != 1 or (os.name == "posix" and file_stat["mode"] != "0600"):
        raise AcquisitionError("pinned anchor is not private and single-linked")
    return file_stat


def _copy_oracle(conn: sqlite3.Connection) -> dict[str, Any]:
    detection = schema_detection.detect_schema(conn)
    if detection.status != "current" or detection.schema_id != "current":
        raise AcquisitionError("copy does not have the current schema")
    if [str(row[0]) for row in conn.execute("PRAGMA quick_check(1)")] != ["ok"]:
        raise AcquisitionError("copy quick_check failed")
    fence = _capture_fence_readonly(conn)
    ledger = a03a.stream_ledger_binding(conn, fence, REQUIRED_BATCH_EVENTS)
    projections = a03a.stream_projection_digests(conn, REQUIRED_BATCH_EVENTS)
    if a03a.verify_chain_bounded(conn, fence, REQUIRED_BATCH_EVENTS):
        raise AcquisitionError("copy seal verification failed")
    if _capture_fence_readonly(conn) != fence:
        raise AcquisitionError("copy head changed during bounded verification")
    digests = projections.get("digests")
    if not isinstance(digests, Mapping) or set(digests) != set(a03b.PROJECTION_TABLES) or len(digests) != 12:
        raise AcquisitionError("projection oracle is not exactly twelve")
    sequences = _sequence_state(conn)
    oracle = {
        "schema_detection": {
            "status": detection.status,
            "schema_id": detection.schema_id,
            "fingerprint": detection.fingerprint,
        },
        "quick_check": "ok",
        "ledger": ledger,
        "projections": projections,
        "projection_count": 12,
        "sequences": sequences,
        "sequence_count": 9,
        "sequence_digest_schema": a03b.SEQUENCE_DIGEST_SCHEMA,
        "sequence_digest_sha256": _sha256_json(sequences),
        "seal": {"bounded": True, "batch_events": REQUIRED_BATCH_EVENTS, "valid": True},
    }
    oracle["oracle_sha256"] = _sha256_json(oracle)
    return oracle


def _snapshot_readonly(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    conn, trace = _open_readonly(path)
    try:
        oracle = _copy_oracle(conn)
        read = _close_readonly(conn, trace)
        conn = None
    finally:
        if conn is not None:
            conn.close()
    return oracle, read


def _register_copy(path: Path, root: Path, source: Path) -> dict[str, Any]:
    previous = os.environ.get("GENUS_DB_PATH")
    os.environ["GENUS_DB_PATH"] = str(source)
    try:
        marker = a03a.register_disposable_database(path, root)
        evidence = a03a.validate_disposable_target(path, root).receipt()
    finally:
        if previous is None:
            os.environ.pop("GENUS_DB_PATH", None)
        else:
            os.environ["GENUS_DB_PATH"] = previous
    os.chmod(marker, 0o600)
    return {
        "schema": evidence["schema"],
        "validated": True,
        "marker_sha256": evidence["marker_sha256"],
        "strict_containment": evidence["strict_containment"],
        "product_path_match": False,
        "root_contains_product_path": False,
        "private_file": _private_file(marker, "disposable marker"),
        "absolute_paths_logged": False,
    }


def acquire_product_copies(
    source_database: Path | str,
    *,
    disposable_root: Path | str,
    core_id_file: Path | str,
    anchor_dir: Path | str,
    manifest: Mapping[str, Any],
    code_root: Path | str,
    expected_candidate_commit: str | None = None,
    identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Acquire two exact siblings while opening the product only mode=ro."""
    manifest_check = verify_runtime_manifest(
        manifest, code_root=code_root, expected_candidate_commit=expected_candidate_commit,
        identity=identity,
    )
    root, root_receipt = _private_root(disposable_root, require_empty=True)
    source, before = _source_file(source_database, root)
    expected_core_id, core_id_stat, core_id_sha256 = _read_core_id(core_id_file, root)
    writer_free = root / WRITER_FREE_DATABASE
    concurrency = root / CONCURRENCY_DATABASE
    source_conn, source_trace = _open_readonly(source)
    try:
        writer_backup = _backup(source_conn, source, writer_free)
        source_read = _close_readonly(source_conn, source_trace)
        source_conn = None
    finally:
        if source_conn is not None:
            source_conn.close()
    after = source.stat(follow_symlinks=False)
    source_stamp = lambda value: (
        int(value.st_dev),
        int(value.st_ino),
        int(value.st_nlink),
        stat.S_IMODE(value.st_mode),
        int(value.st_size),
        int(value.st_mtime_ns),
    )
    if source_stamp(before) != source_stamp(after):
        raise AcquisitionError("product database identity or stat changed during acquisition")
    writer_conn, writer_trace = _open_readonly(writer_free)
    try:
        oracle = _copy_oracle(writer_conn)
        (
            anchor_bytes,
            anchor_artifact,
            source_anchor_stat,
            anchor_scan,
        ) = _select_anchor(
            writer_conn,
            anchor_dir,
            full_fence=_capture_fence_readonly(writer_conn),
            expected_core_id=expected_core_id,
            root=root,
        )
        concurrency_backup = _backup(writer_conn, writer_free, concurrency)
        writer_read = _close_readonly(writer_conn, writer_trace)
        writer_conn = None
    finally:
        if writer_conn is not None:
            writer_conn.close()
    concurrency_oracle, concurrency_read = _snapshot_readonly(concurrency)
    if concurrency_oracle != oracle:
        raise AcquisitionError("sibling copies have different bounded oracles")
    writer_private = _private_file(writer_free, "writer-free copy")
    concurrency_private = _private_file(concurrency, "concurrency copy")
    if (writer_private["device"], writer_private["inode"]) == (concurrency_private["device"], concurrency_private["inode"]):
        raise AcquisitionError("sibling copies are the same inode")
    pinned_anchor = root / PINNED_ANCHOR_FILE
    pinned_anchor_stat = _write_private_bytes(pinned_anchor, anchor_bytes)
    if pinned_anchor_stat["sha256"] != source_anchor_stat["sha256"]:
        raise AcquisitionError("pinned anchor bytes differ from the selected anchor")
    body = {
        "schema": ACQUISITION_RECEIPT_SCHEMA,
        "outcome": "acquired",
        "acquired_at_utc": _utc_now(),
        "manifest_sha256": manifest["manifest_sha256"],
        "candidate_commit": manifest["candidate_commit"],
        "runtime_identity_sha256": manifest["runtime_identity_sha256"],
        "candidate_config_sha256": manifest_check["candidate_config_sha256"],
        "a0_3b_code_sha256": dict(manifest["a0_3b_code_sha256"]),
        "a0_3c_code_sha256": dict(manifest["a0_3c_code_sha256"]),
        "batch_events": REQUIRED_BATCH_EVENTS,
        "batch_bytes": REQUIRED_BATCH_BYTES,
        "root": root_receipt,
        "source": {
            **source_read,
            "identity_and_stat_stable": True,
            "mode": f"{stat.S_IMODE(before.st_mode):04o}",
            "links": int(before.st_nlink),
            "bytes": int(before.st_size),
            "single_linked": True,
            "product_write_performed": False,
        },
        "core_id": {
            "file_stat": core_id_stat,
            "normalized_sha256": core_id_sha256,
            "normalized_bytes": len(expected_core_id.encode("utf-8")),
            "clear_value_logged": False,
            "anchor_exact_match": True,
        },
        "anchor": {
            "source_stat": source_anchor_stat,
            "selection_scan": anchor_scan,
            "pinned_stat": pinned_anchor_stat,
            "bytes_identical": True,
            "bounded_verification": True,
            "valid": True,
            "epoch_event_id": anchor_artifact["epoch_event_id"],
            "head_event_id": anchor_artifact["head_event_id"],
            "head_seal": anchor_artifact["head"],
        },
        "oracle": oracle,
        "copies": {
            "writer_free": {
                "backup": writer_backup,
                "private_file": writer_private,
                "bounded_read": writer_read,
                "marker": _register_copy(writer_free, root, source),
                "oracle_sha256": oracle["oracle_sha256"],
            },
            "concurrency": {
                "backup": concurrency_backup,
                "private_file": concurrency_private,
                "bounded_read": concurrency_read,
                "marker": _register_copy(concurrency, root, source),
                "oracle_sha256": oracle["oracle_sha256"],
            },
        },
        "safety": {
            "source_outside_disposable_root": True,
            "source_opened_mode_ro": True,
            "source_query_only": True,
            "source_autocommit": True,
            "source_total_changes_zero": True,
            "sibling_inodes_distinct": True,
            "copies_populated_only_by_backup_api": True,
            "bounded_scans": True,
            "symlinks_and_hardlinks_rejected": True,
            "product_write_performed": False,
            "product_activation_authorized": False,
            "paths_logged": False,
            "payloads_logged": False,
        },
    }
    receipt = _seal_receipt(body)
    assert_receipt_safe(receipt)
    return receipt


def _require_acquisition(
    receipt: Mapping[str, Any], *, manifest: Mapping[str, Any], root: Path
) -> tuple[dict[str, Any], Path, Path, str]:
    if receipt.get("schema") != ACQUISITION_RECEIPT_SCHEMA or receipt.get("outcome") != "acquired":
        raise RunEvidenceError("acquisition receipt schema or outcome differs")
    _verify_receipt_digest(receipt, "acquisition")
    if receipt.get("manifest_sha256") != manifest.get("manifest_sha256"):
        raise RunEvidenceError("acquisition manifest binding differs")
    if (
        receipt.get("candidate_commit") != manifest.get("candidate_commit")
        or receipt.get("runtime_identity_sha256")
        != manifest.get("runtime_identity_sha256")
        or receipt.get("a0_3b_code_sha256") != manifest.get("a0_3b_code_sha256")
        or receipt.get("a0_3c_code_sha256") != manifest.get("a0_3c_code_sha256")
        or receipt.get("candidate_config_sha256")
        != _sha256_json(required_candidate_config())
        or receipt.get("batch_events") != REQUIRED_BATCH_EVENTS
        or receipt.get("batch_bytes") != REQUIRED_BATCH_BYTES
    ):
        raise RunEvidenceError("acquisition candidate/runtime/config binding differs")
    _parse_utc(receipt.get("acquired_at_utc"))
    oracle = receipt.get("oracle")
    if not isinstance(oracle, dict):
        raise RunEvidenceError("acquisition oracle is missing")
    oracle_body = {key: item for key, item in oracle.items() if key != "oracle_sha256"}
    if oracle.get("oracle_sha256") != _sha256_json(oracle_body):
        raise RunEvidenceError("acquisition oracle digest differs")
    if oracle.get("projection_count") != 12 or oracle.get("sequence_count") != 9:
        raise RunEvidenceError("acquisition oracle cardinality differs")
    copies = receipt.get("copies")
    if not isinstance(copies, Mapping):
        raise RunEvidenceError("acquisition copy inventory is missing")
    writer_free = root / WRITER_FREE_DATABASE
    concurrency = root / CONCURRENCY_DATABASE
    for role, path in (("writer_free", writer_free), ("concurrency", concurrency)):
        item = copies.get(role)
        if not isinstance(item, Mapping):
            raise RunEvidenceError(f"{role} acquisition evidence is missing")
        if _private_file(path, role) != item.get("private_file"):
            raise RunEvidenceError(f"{role} copy identity or stat changed")
        a03a.validate_disposable_target(path, root)
        current, _ = _snapshot_readonly(path)
        if current != oracle:
            raise RunEvidenceError(f"{role} copy differs from acquisition oracle")
    if writer_free.samefile(concurrency):
        raise RunEvidenceError("acquisition sibling copies became one file")
    anchor_receipt = receipt.get("anchor")
    core_receipt = receipt.get("core_id")
    if not isinstance(anchor_receipt, Mapping) or not isinstance(core_receipt, Mapping):
        raise RunEvidenceError("acquisition anchor/core binding is missing")
    pinned = root / PINNED_ANCHOR_FILE
    pinned_data, pinned_stat = _stable_file_bytes(pinned, MAX_ANCHOR_BYTES)
    if pinned_stat != anchor_receipt.get("pinned_stat"):
        raise RunEvidenceError("pinned anchor bytes or identity changed")
    try:
        artifact = json.loads(pinned_data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RunEvidenceError("pinned anchor is invalid JSON") from exc
    if not isinstance(artifact, dict) or anchor.validate_anchor(artifact):
        raise RunEvidenceError("pinned anchor contract is invalid")
    normalized = anchor.normalize_core_id(str(artifact.get("core_id", "")))
    if hashlib.sha256(normalized.encode("utf-8")).hexdigest() != core_receipt.get("normalized_sha256"):
        raise RunEvidenceError("pinned anchor core binding differs")
    if artifact.get("head") != anchor_receipt.get("head_seal"):
        raise RunEvidenceError("pinned anchor head binding differs")
    for path in (writer_free, concurrency):
        conn, trace = _open_readonly(path)
        try:
            issues = _verify_anchor_bounded(
                conn,
                artifact,
                full_fence=_capture_fence_readonly(conn),
                expected_core_id=normalized,
            )
            _close_readonly(conn, trace)
            conn = None
        finally:
            if conn is not None:
                conn.close()
        if issues:
            raise RunEvidenceError("pinned anchor no longer verifies against a copy")
    return dict(oracle), writer_free, concurrency, str(pinned_stat["sha256"])


def _postcheck_writer_free(
    path: Path, *, oracle: Mapping[str, Any], pinned_anchor: Path
) -> dict[str, Any]:
    pinned_data, pinned_stat = _stable_file_bytes(pinned_anchor, MAX_ANCHOR_BYTES)
    try:
        artifact = json.loads(pinned_data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RunEvidenceError("pinned anchor is unreadable during postcheck") from exc
    if not isinstance(artifact, dict) or anchor.validate_anchor(artifact):
        raise RunEvidenceError("pinned anchor is invalid during postcheck")
    expected_core = anchor.normalize_core_id(str(artifact["core_id"]))
    conn, trace = _open_readonly(path)
    try:
        exact_schema_sha256 = a03b._validate_extended_schema(conn)
        topology = a03b._topology_snapshot(conn, verify_event_count=True)
        active = topology["active"]
        if topology.get("kind") != "new_active" or active.generation_id != "g2" or active.state != "active":
            raise RunEvidenceError("writer-free topology is not active G2")
        generations = {
            generation: a03b._stream_generation_digests_conn(
                conn, generation, REQUIRED_BATCH_EVENTS
            )
            for generation in ("g1", "g2", "g3")
        }
        for generation, digest in generations.items():
            if digest.get("projections") != oracle["projections"]:
                raise RunEvidenceError(f"{generation} projections differ from acquisition")
            if digest.get("sequences") != oracle["sequences"]:
                raise RunEvidenceError(f"{generation} sequences differ from acquisition")
        fence = _capture_fence_readonly(conn)
        ledger = a03a.stream_ledger_binding(conn, fence, REQUIRED_BATCH_EVENTS)
        if ledger != oracle["ledger"]:
            raise RunEvidenceError("writer-free ledger differs from acquisition")
        if a03a.verify_chain_bounded(conn, fence, REQUIRED_BATCH_EVENTS):
            raise RunEvidenceError("writer-free ledger seal verification failed")
        if _capture_fence_readonly(conn) != fence:
            raise RunEvidenceError("writer-free ledger head changed during postcheck")
        if _verify_anchor_bounded(
            conn, artifact, full_fence=fence, expected_core_id=expected_core
        ):
            raise RunEvidenceError("pinned anchor failed the writer-free postcheck")
        if [str(row[0]) for row in conn.execute("PRAGMA quick_check(1)")] != ["ok"]:
            raise RunEvidenceError("writer-free quick_check failed")
        read_receipt = _close_readonly(conn, trace)
        conn = None
    finally:
        if conn is not None:
            conn.close()
    generation_hashes = {
        generation: _sha256_json(value) for generation, value in generations.items()
    }
    return {
        "exact_extended_schema_sha256": exact_schema_sha256,
        "topology": "new_active",
        "active_generation_id": "g2",
        "generation_digest_sha256": generation_hashes,
        "g1_g2_g3_equal_to_acquisition": True,
        "all_twelve_projection_digests_match": True,
        "all_nine_sequences_match": True,
        "ledger_unchanged": True,
        "seal_valid": True,
        "pinned_anchor_sha256": pinned_stat["sha256"],
        "pinned_anchor_valid": True,
        "quick_check": "ok",
        "read_only": read_receipt,
        "gate_pass": True,
    }


def _writer_free_summary(
    receipt: Mapping[str, Any],
    oracle: Mapping[str, Any],
    resources: Mapping[str, Any],
) -> dict[str, Any]:
    verify = receipt.get("verify") if isinstance(receipt.get("verify"), Mapping) else {}
    cutover = receipt.get("cutover") if isinstance(receipt.get("cutover"), Mapping) else {}
    recovery = receipt.get("recovery") if isinstance(receipt.get("recovery"), Mapping) else {}
    active = receipt.get("active_projection_digests")
    active = active if isinstance(active, Mapping) else {}
    projections = active.get("projections") if isinstance(active.get("projections"), Mapping) else {}
    sequences = active.get("sequences") if isinstance(active.get("sequences"), Mapping) else {}
    budgets = receipt.get("budgets") if isinstance(receipt.get("budgets"), Mapping) else {}
    admission = (
        verify.get("sync_admission")
        if isinstance(verify.get("sync_admission"), Mapping)
        else {}
    )
    projection_match = projections.get("digests") == oracle["projections"]["digests"]
    sequence_match = dict(sequences) == oracle["sequences"]
    ledger_bound = bool(
        receipt.get("ledger_before") == receipt.get("ledger_after")
        and receipt.get("ledger_unchanged") is True
        and isinstance(receipt.get("ledger_before"), Mapping)
        and receipt["ledger_before"].get("binding") == oracle["ledger"]
    )
    no_fallback = bool(
        receipt.get("selected_final_sync_mode") == "a_bounded_fence"
        and receipt.get("sync_route_used") is False
        and verify.get("selected_final_sync_mode") == "a_bounded_fence"
        and verify.get("sync_route_used") is False
        and cutover.get("selected_final_sync_mode") == "a_bounded_fence"
        and cutover.get("sync_route_used") is False
        and cutover.get("outcome") == "complete_new"
        and cutover.get("committed") is True
        and admission.get("selected_final_sync_mode") == "a_bounded_fence"
        and admission.get("sync_route_used") is False
        and admission.get("committed") is True
        and admission.get("outcome") == "complete_new"
        and verify.get("decision_reason") == REQUIRED_FINAL_SYNC_DECISION_REASON
        and admission.get("decision_reason") == REQUIRED_FINAL_SYNC_DECISION_REASON
        and cutover.get("decision_reason") == REQUIRED_FINAL_SYNC_DECISION_REASON
    )
    recovery_pass = bool(
        recovery.get("classification") == "NEW_ACTIVE_OLD_RETIRED"
        and recovery.get("reader_ready") is True
        and recovery.get("writer_ready") is True
        and recovery.get("within_recovery_budget") is True
        and recovery.get("persistent_receipt_chains_recomputed") is True
    )
    budget_inventory_exact = set(budgets) == _WRITER_FREE_BUDGET_KEYS
    budgets_pass = budget_inventory_exact and all(
        isinstance(item, Mapping) and item.get("pass") is True for item in budgets.values()
    )
    writes = receipt.get("write_transactions")
    writes = writes if isinstance(writes, Mapping) else {}
    strict_writes = _strict_write_receipt(
        writes, expected_scope="run_shadow_prototype", require_claim=True
    )
    strict_resources = _strict_resource_receipt(
        resources, expected_phase="writer_free_outer"
    )
    exhaustive_writes = bool(
        writes.get("claim") == "all_experimental_write_transactions"
        and writes.get("exhaustive") is True
        and writes.get("evidence_complete") is True
        and writes.get("open_transaction_count") == 0
        and writes.get("pass") is True
        and writes.get("attempt_count")
        == writes.get("transaction_count", 0) + writes.get("begin_error_count", 0)
        and writes.get("transaction_count")
        == writes.get("committed_count", 0) + writes.get("rolled_back_count", 0)
        and strict_writes["gate_pass"] is True
    )
    storage = receipt.get("storage_highwater_bytes")
    numeric_budgets = bool(
        isinstance(receipt.get("peak_rss_bytes"), int)
        and receipt["peak_rss_bytes"] <= a03b.RSS_BUDGET_BYTES
        and isinstance(storage, Mapping)
        and isinstance(storage.get("wal"), int)
        and storage["wal"] <= a03b.WAL_BUDGET_BYTES
        and isinstance(receipt.get("build"), Mapping)
        and receipt["build"].get("duration_seconds", a03b.REBUILD_BUDGET_SECONDS + 1)
        <= a03b.REBUILD_BUDGET_SECONDS
        and isinstance(cutover.get("final_fence_seconds"), (int, float))
        and cutover["final_fence_seconds"] <= a03b.WRITER_BLOCK_BUDGET_SECONDS
        and isinstance(writes.get("overall_max_transaction_seconds"), (int, float))
        and writes["overall_max_transaction_seconds"] <= a03b.WRITER_BLOCK_BUDGET_SECONDS
        and isinstance(recovery.get("duration_seconds"), (int, float))
        and recovery["duration_seconds"] <= a03b.RECOVERY_BUDGET_SECONDS
    )
    gate = bool(
        receipt.get("budgets_pass") is True
        and budgets_pass
        and verify.get("all_twelve_match") is True
        and verify.get("all_nine_sequences_match") is True
        and projection_match
        and sequence_match
        and ledger_bound
        and no_fallback
        and recovery_pass
        and receipt.get("schema") == a03b.RECEIPT_SCHEMA
        and exhaustive_writes
        and numeric_budgets
        and strict_resources["gate_pass"] is True
    )
    return {
        "receipt_schema": receipt.get("schema"),
        "receipt_sha256": _sha256_json(receipt),
        "projection_count": len(projections.get("digests", {})),
        "all_twelve_projection_digests_match": projection_match and len(projections.get("digests", {})) == 12,
        "projection_digest_set_sha256": projections.get("digest_set_sha256"),
        "sequence_count": len(sequences),
        "all_nine_sequences_match": sequence_match and len(sequences) == 9,
        "sequence_digest_sha256": active.get("sequence_digest_sha256"),
        "ledger_before_after_unchanged_and_acquisition_bound": ledger_bound,
        "recovery_classification": recovery.get("classification"),
        "recovery_seconds": recovery.get("duration_seconds"),
        "recovery_pass": recovery_pass,
        "selected_final_sync_mode": receipt.get("selected_final_sync_mode"),
        "fallback_used": receipt.get("sync_route_used") is True,
        "no_fallback": no_fallback,
        "final_sync_decision": {
            "selected_final_sync_mode": receipt.get("selected_final_sync_mode"),
            "fallback_used": receipt.get("sync_route_used") is True,
            "decision_reason": verify.get("decision_reason"),
            "writer_free_verify_admission_cutover_agree": bool(
                verify.get("selected_final_sync_mode") == "a_bounded_fence"
                and admission.get("selected_final_sync_mode") == "a_bounded_fence"
                and cutover.get("selected_final_sync_mode") == "a_bounded_fence"
                and verify.get("decision_reason") == REQUIRED_FINAL_SYNC_DECISION_REASON
                and admission.get("decision_reason") == REQUIRED_FINAL_SYNC_DECISION_REASON
                and cutover.get("decision_reason") == REQUIRED_FINAL_SYNC_DECISION_REASON
            ),
            "gate_pass": no_fallback,
        },
        "build_seconds": receipt["build"].get("duration_seconds") if isinstance(receipt.get("build"), Mapping) else None,
        "all_experimental_write_max_seconds": writes.get("overall_max_transaction_seconds"),
        "final_fence_seconds": cutover.get("final_fence_seconds"),
        "peak_rss_bytes": receipt.get("peak_rss_bytes"),
        "wal_highwater_bytes": storage.get("wal") if isinstance(storage, Mapping) else None,
        "budget_inventory_exact": budget_inventory_exact,
        "all_experimental_write_evidence_exhaustive": exhaustive_writes,
        "write_receipt_validation": strict_writes,
        "outer_resources": strict_resources,
        "numeric_budgets_pass": numeric_budgets,
        "budgets_pass": budgets_pass,
        "gate_pass": gate,
    }


def _concurrency_summary(
    receipt: Mapping[str, Any], resources_receipt: Mapping[str, Any]
) -> dict[str, Any]:
    verify = receipt.get("verify") if isinstance(receipt.get("verify"), Mapping) else {}
    cutover = receipt.get("cutover") if isinstance(receipt.get("cutover"), Mapping) else {}
    latency = receipt.get("writer_latency") if isinstance(receipt.get("writer_latency"), Mapping) else {}
    reader = receipt.get("reader") if isinstance(receipt.get("reader"), Mapping) else {}
    build = receipt.get("build") if isinstance(receipt.get("build"), Mapping) else {}
    catchup = receipt.get("catch_up") if isinstance(receipt.get("catch_up"), Mapping) else {}
    admission = verify.get("sync_admission") if isinstance(verify.get("sync_admission"), Mapping) else {}
    write_max = verify.get("write_transaction_max_seconds")
    write_max = write_max if isinstance(write_max, Mapping) else {}
    phase_values = [
        build.get("max_write_transaction_seconds"),
        catchup.get("max_write_transaction_seconds"),
        write_max.get("overall"),
        admission.get("fence_seconds"),
        cutover.get("final_fence_seconds"),
        latency.get("max_seconds"),
    ]
    complete = all(isinstance(value, (int, float)) for value in phase_values)
    overall_write_max = max((float(value) for value in phase_values if isinstance(value, (int, float))), default=None)
    no_fallback = bool(
        verify.get("selected_final_sync_mode") == "a_bounded_fence"
        and verify.get("sync_route_used") is False
        and admission.get("selected_final_sync_mode") == "a_bounded_fence"
        and admission.get("sync_route_used") is False
        and admission.get("committed") is True
        and admission.get("outcome") == "complete_new"
        and cutover.get("selected_final_sync_mode") == "a_bounded_fence"
        and cutover.get("sync_route_used") is False
        and cutover.get("outcome") == "complete_new"
        and cutover.get("committed") is True
        and admission.get("decision_reason") == REQUIRED_FINAL_SYNC_DECISION_REASON
        and cutover.get("decision_reason") == REQUIRED_FINAL_SYNC_DECISION_REASON
    )
    rates = bool(
        isinstance(latency.get("observed_attempt_rate_per_second"), (int, float))
        and latency["observed_attempt_rate_per_second"] > 0
        and isinstance(latency.get("committed_arrival_rate_per_second"), (int, float))
        and latency["committed_arrival_rate_per_second"] > 0
        and isinstance(catchup.get("catch_up_rate_events_per_second"), (int, float))
        and catchup["catch_up_rate_events_per_second"] >= 0
        and isinstance(catchup.get("event_arrival_rate_events_per_second"), (int, float))
        and catchup["event_arrival_rate_events_per_second"] >= 0
    )
    writer_clean = bool(
        receipt.get("writer_evidence_complete") is True
        and latency.get("sample_count", 0) > 0
        and latency.get("committed_count") == latency.get("sample_count")
        and latency.get("timeouts") == 0
        and latency.get("errors") == 0
        and latency.get("starvation") is False
        and latency.get("samples_truncated") is False
        and latency.get("dropped_sample_count") == 0
        and latency.get("within_max_block_budget") is True
        and rates
    )
    reader_clean = bool(
        reader.get("short_transaction_count", 0) > 0
        and reader.get("evidence_complete") is True
        and reader.get("samples_truncated") is False
        and reader.get("failure_count") == 0
        and reader.get("failure_samples_truncated") is False
        and reader.get("reader_thread_alive_after_join") is False
        and reader.get("writer_thread_alive_after_join") is False
        and reader.get("coherent_old_or_new_only") is True
    )
    storage = receipt.get("storage_highwater_bytes")
    handoff = receipt.get("writer_handoff")
    handoff = handoff if isinstance(handoff, Mapping) else {}
    handoff_pass = bool(
        handoff.get("pass") is True
        and handoff.get("timeouts") == 0
        and handoff.get("requested") == handoff.get("completed")
        and handoff.get("completed") == handoff.get("expected_from_committed_batches")
        and handoff.get("exactly_one_commit_per_slot") is True
        and handoff.get("outside_transactions") is True
    )
    phase_write_receipts = {
        "build": (
            build.get("write_transactions")
            if isinstance(build.get("write_transactions"), Mapping)
            else {}
        ),
        "catch_up": (
            catchup.get("write_transactions")
            if isinstance(catchup.get("write_transactions"), Mapping)
            else {}
        ),
    }

    write_receipt_validation = {
        role: _strict_write_receipt(
            phase_write_receipts[role], expected_scope=scope
        )
        for role, scope in {
            "build": "build_shadow",
            "catch_up": "catch_up_shadow",
        }.items()
    }
    bounded_phase_writes = all(
        item["gate_pass"] is True for item in write_receipt_validation.values()
    )
    strict_outer_resources = _strict_resource_receipt(
        resources_receipt, expected_phase="concurrency_outer"
    )
    verification_write_aggregate = bool(
        write_max.get("pass") is True
        and isinstance(write_max.get("overall"), (int, float))
        and write_max["overall"] <= a03b.WRITER_BLOCK_BUDGET_SECONDS
        and admission.get("within_writer_block_budget") is True
        and cutover.get("within_writer_block_budget") is True
    )
    phase_latency = receipt.get("writer_latency_by_phase")
    phase_latency = phase_latency if isinstance(phase_latency, Mapping) else {}
    phase_evidence = bool(
        isinstance(phase_latency.get("g1_only"), Mapping)
        and phase_latency["g1_only"].get("committed_count", 0) > 0
        and isinstance(phase_latency.get("g2_only"), Mapping)
        and phase_latency["g2_only"].get("committed_count", 0) > 0
        and isinstance(phase_latency.get("sync_triple"), Mapping)
        and phase_latency["sync_triple"].get("committed_count") == 0
    )
    exhaustive_write_evidence = bool(
        bounded_phase_writes
        and verification_write_aggregate
        and writer_clean
        and handoff_pass
        and phase_evidence
        and receipt.get("writer_evidence_complete") is True
    )
    resources = bool(
        receipt.get("peak_rss_bytes", a03b.RSS_BUDGET_BYTES + 1) <= a03b.RSS_BUDGET_BYTES
        and isinstance(storage, Mapping)
        and storage.get("wal", a03b.WAL_BUDGET_BYTES + 1) <= a03b.WAL_BUDGET_BYTES
        and build.get("duration_seconds", a03b.REBUILD_BUDGET_SECONDS + 1) <= a03b.REBUILD_BUDGET_SECONDS
        and complete
        and overall_write_max is not None
        and overall_write_max <= a03b.WRITER_BLOCK_BUDGET_SECONDS
        and cutover.get("final_fence_seconds", a03b.WRITER_BLOCK_BUDGET_SECONDS + 1) <= a03b.WRITER_BLOCK_BUDGET_SECONDS
    )
    gate = bool(
        receipt.get("concurrency_gate_pass") is True
        and verify.get("all_twelve_match") is True
        and verify.get("all_nine_sequences_match") is True
        and writer_clean and reader_clean and resources and no_fallback
        and receipt.get("schema") == a03b.RECEIPT_SCHEMA
        and exhaustive_write_evidence
        and strict_outer_resources["gate_pass"] is True
    )
    return {
        "receipt_schema": receipt.get("schema"),
        "receipt_sha256": _sha256_json(receipt),
        "all_twelve_projection_digests_match": verify.get("all_twelve_match") is True,
        "all_nine_sequences_match": verify.get("all_nine_sequences_match") is True,
        "selected_final_sync_mode": verify.get("selected_final_sync_mode"),
        "fallback_used": verify.get("sync_route_used") is True,
        "no_fallback": no_fallback,
        "final_sync_decision": {
            "selected_final_sync_mode": verify.get("selected_final_sync_mode"),
            "fallback_used": verify.get("sync_route_used") is True,
            "decision_reason": admission.get("decision_reason"),
            "verify_admission_cutover_agree": bool(
                verify.get("selected_final_sync_mode") == "a_bounded_fence"
                and admission.get("selected_final_sync_mode") == "a_bounded_fence"
                and cutover.get("selected_final_sync_mode") == "a_bounded_fence"
                and admission.get("decision_reason") == REQUIRED_FINAL_SYNC_DECISION_REASON
                and cutover.get("decision_reason") == REQUIRED_FINAL_SYNC_DECISION_REASON
            ),
            "gate_pass": no_fallback,
        },
        "writer": {
            "sample_count": latency.get("sample_count"),
            "committed_count": latency.get("committed_count"),
            "timeouts": latency.get("timeouts"),
            "errors": latency.get("errors"),
            "starvation": latency.get("starvation"),
            "max_seconds": latency.get("max_seconds"),
            "p50_seconds": latency.get("p50_seconds"),
            "p95_seconds": latency.get("p95_seconds"),
            "p99_seconds": latency.get("p99_seconds"),
            "observed_attempt_rate_per_second": latency.get("observed_attempt_rate_per_second"),
            "committed_arrival_rate_per_second": latency.get("committed_arrival_rate_per_second"),
            "evidence_complete": writer_clean,
        },
        "rates": {
            "catch_up_events_per_second": catchup.get("catch_up_rate_events_per_second"),
            "event_arrival_per_second": catchup.get("event_arrival_rate_events_per_second"),
            "positive_and_complete": rates,
        },
        "reader_old_or_new_only": reader_clean,
        "all_experimental_write_max_seconds": overall_write_max,
        "final_fence_seconds": cutover.get("final_fence_seconds"),
        "peak_rss_bytes": receipt.get("peak_rss_bytes"),
        "wal_highwater_bytes": storage.get("wal") if isinstance(storage, Mapping) else None,
        "build_seconds": build.get("duration_seconds"),
        "resource_budgets_pass": resources,
        "writer_handoff_pass": handoff_pass,
        "bounded_phase_write_receipts_pass": bounded_phase_writes,
        "write_receipt_validation": write_receipt_validation,
        "outer_resources": strict_outer_resources,
        "verification_write_aggregate_pass": verification_write_aggregate,
        "writer_phase_evidence_complete": phase_evidence,
        "all_experimental_write_evidence_exhaustive": exhaustive_write_evidence,
        "gate_pass": gate,
    }


def _initialization_summary(
    receipt: Mapping[str, Any], resources: Mapping[str, Any]
) -> dict[str, Any]:
    writes = receipt.get("write_transactions")
    writes = writes if isinstance(writes, Mapping) else {}
    strict_writes = _strict_write_receipt(
        writes, expected_scope="initialize_shadow"
    )
    strict_resources = _strict_resource_receipt(
        resources, expected_phase="concurrency_initialization"
    )
    gate = bool(
        receipt.get("schema") == a03b.METADATA_SCHEMA
        and receipt.get("already_initialized") is False
        and strict_writes["gate_pass"] is True
        and strict_resources["gate_pass"] is True
    )
    return {
        "receipt_schema": receipt.get("schema"),
        "receipt_sha256": _sha256_json(receipt),
        "write_transactions_pass": strict_writes["gate_pass"],
        "write_receipt_validation": strict_writes,
        "max_write_transaction_seconds": writes.get("overall_max_transaction_seconds"),
        "peak_rss_bytes": strict_resources["peak_rss_bytes"],
        "wal_highwater_bytes": strict_resources["wal_highwater_bytes"],
        "outer_resources": strict_resources,
        "resource_budgets_pass": strict_resources["gate_pass"],
        "gate_pass": gate,
    }


def _recovery_summary(
    receipt: Mapping[str, Any], resources: Mapping[str, Any]
) -> dict[str, Any]:
    writes = receipt.get("write_transactions")
    writes = writes if isinstance(writes, Mapping) else {}
    strict_writes = _strict_write_receipt(writes, expected_scope="recover")
    strict_resources = _strict_resource_receipt(
        resources, expected_phase="concurrency_recovery"
    )
    gate = bool(
        receipt.get("schema") == a03b.RECEIPT_SCHEMA
        and receipt.get("classification") == "NEW_ACTIVE_OLD_RETIRED"
        and receipt.get("reader_ready") is True
        and receipt.get("writer_ready") is True
        and receipt.get("within_recovery_budget") is True
        and receipt.get("persistent_receipt_chains_recomputed") is True
        and isinstance(receipt.get("duration_seconds"), (int, float))
        and receipt["duration_seconds"] <= a03b.RECOVERY_BUDGET_SECONDS
        and strict_writes["gate_pass"] is True
        and strict_resources["gate_pass"] is True
    )
    return {
        "receipt_schema": receipt.get("schema"),
        "receipt_sha256": _sha256_json(receipt),
        "classification": receipt.get("classification"),
        "duration_seconds": receipt.get("duration_seconds"),
        "write_transactions_pass": strict_writes["gate_pass"],
        "write_receipt_validation": strict_writes,
        "max_write_transaction_seconds": writes.get("overall_max_transaction_seconds"),
        "peak_rss_bytes": strict_resources["peak_rss_bytes"],
        "wal_highwater_bytes": strict_resources["wal_highwater_bytes"],
        "outer_resources": strict_resources,
        "resource_gate_pass": strict_resources["gate_pass"],
        "gate_pass": gate,
    }


def _raw_candidate_config_receipt(
    run: Mapping[str, Any], raw: Mapping[str, Any]
) -> dict[str, Any]:
    code_hashes = run.get("a0_3b_code_sha256")
    if (
        code_hashes != ACCEPTED_A03B_CODE_SHA256
        or run.get("candidate_config_sha256")
        != _sha256_json(required_candidate_config())
        or run.get("batch_events") != REQUIRED_BATCH_EVENTS
        or run.get("batch_bytes") != REQUIRED_BATCH_BYTES
        or run.get("writer_interval_seconds")
        != REQUIRED_WRITER_INTERVAL_SECONDS
        or run.get("short_reader_interval_seconds")
        != REQUIRED_READER_INTERVAL_SECONDS
        or run.get("canonical_runners_used") is not True
    ):
        raise RunEvidenceError("candidate callsite configuration differs")
    phase_bindings: dict[str, dict[str, int]] = {}
    for role in ("writer_free", "concurrency"):
        receipt = raw.get(role)
        if not isinstance(receipt, Mapping):
            raise RunEvidenceError("raw candidate config role is missing")
        # A0.3b's catch-up receipt deliberately does not duplicate its input caps.
        # The accepted A0.3b code hash proves each canonical entry point forwards
        # the same arguments to build, catch-up, and verify; the build receipt is
        # the observable value witness for that shared callsite configuration.
        build = receipt.get("build")
        if (
            not isinstance(build, Mapping)
            or build.get("batch_events") != REQUIRED_BATCH_EVENTS
            or build.get("batch_bytes") != REQUIRED_BATCH_BYTES
        ):
            raise RunEvidenceError("raw candidate batch configuration differs")
        phase_bindings[f"{role}.build"] = {
            "batch_events": REQUIRED_BATCH_EVENTS,
            "batch_bytes": REQUIRED_BATCH_BYTES,
        }
    concurrency = raw["concurrency"]
    handoff = concurrency.get("writer_handoff")
    if (
        not isinstance(handoff, Mapping)
        or handoff.get("think_time_seconds") != REQUIRED_WRITER_INTERVAL_SECONDS
    ):
        raise RunEvidenceError("raw writer interval configuration differs")
    body = {
        "phase_bindings": phase_bindings,
        "canonical_batch_callsite_binding": {
            "a0_3b_harness_sha256": code_hashes["harness"],
            "entry_points": ["run_concurrency_probe", "run_shadow_prototype"],
            "phases_receiving_same_batch_arguments": [
                "build",
                "catch_up",
                "verify",
            ],
        },
        "writer_interval_seconds": REQUIRED_WRITER_INTERVAL_SECONDS,
        "short_reader_interval_seconds": REQUIRED_READER_INTERVAL_SECONDS,
        "candidate_config_sha256": _sha256_json(required_candidate_config()),
        "gate_pass": True,
    }
    return {**body, "receipt_sha256": _sha256_json(body)}


def _reconstruct_run_summaries(run: Mapping[str, Any]) -> dict[str, Any]:
    raw = run.get("raw_evidence")
    raw_hashes = run.get("raw_evidence_sha256")
    resources = run.get("resource_evidence")
    oracle = run.get("acquisition_oracle")
    if (
        not isinstance(raw, Mapping)
        or set(raw) != _RAW_EVIDENCE_KEYS
        or not all(isinstance(raw[key], Mapping) for key in _RAW_EVIDENCE_KEYS)
        or not isinstance(raw_hashes, Mapping)
        or set(raw_hashes) != _RAW_EVIDENCE_KEYS
        or not isinstance(resources, Mapping)
        or set(resources) != _RESOURCE_EVIDENCE_KEYS
        or not all(
            isinstance(resources[key], Mapping) for key in _RESOURCE_EVIDENCE_KEYS
        )
        or not isinstance(oracle, Mapping)
    ):
        raise RunEvidenceError("run raw/resource evidence inventory differs")
    oracle_body = {key: value for key, value in oracle.items() if key != "oracle_sha256"}
    if (
        oracle.get("oracle_sha256") != _sha256_json(oracle_body)
        or run.get("acquisition_oracle_sha256") != oracle.get("oracle_sha256")
        or oracle.get("projection_count") != 12
        or oracle.get("sequence_count") != 9
    ):
        raise RunEvidenceError("run acquisition oracle binding differs")
    expected_raw_hashes = {
        key: _sha256_json(raw[key]) for key in sorted(_RAW_EVIDENCE_KEYS)
    }
    if dict(raw_hashes) != expected_raw_hashes:
        raise RunEvidenceError("run raw evidence hash binding differs")
    raw_candidate_config = _raw_candidate_config_receipt(run, raw)
    if (
        raw["writer_free"].get("schema") != a03b.RECEIPT_SCHEMA
        or raw["writer_free"].get("topology")
        != "option-c-same-file-generation-pointer"
        or raw["concurrency_initialization"].get("schema")
        != a03b.METADATA_SCHEMA
        or raw["concurrency_initialization"].get("already_initialized") is not False
        or raw["concurrency"].get("schema") != a03b.RECEIPT_SCHEMA
        or raw["concurrency"].get("operation") != "concurrency_probe"
        or raw["concurrency_recovery"].get("schema") != a03b.RECEIPT_SCHEMA
        or raw["concurrency_recovery"].get("classification")
        != "NEW_ACTIVE_OLD_RETIRED"
    ):
        raise RunEvidenceError("run raw evidence schema/operation differs")
    expected = {
        "writer_free": _writer_free_summary(
            raw["writer_free"], oracle, resources["writer_free_outer"]
        ),
        "concurrency_initialization": _initialization_summary(
            raw["concurrency_initialization"],
            resources["concurrency_initialization"],
        ),
        "concurrency": _concurrency_summary(
            raw["concurrency"], resources["concurrency_outer"]
        ),
        "concurrency_recovery": _recovery_summary(
            raw["concurrency_recovery"], resources["concurrency_recovery"]
        ),
    }
    if any(run.get(key) != summary for key, summary in expected.items()):
        raise RunEvidenceError("run summary is not reconstructed from raw evidence")
    resource_hashes = {
        key: _sha256_json(resources[key])
        for key in sorted(_RESOURCE_EVIDENCE_KEYS)
    }
    return {
        "raw_inventory_exact": True,
        "resource_inventory_exact": True,
        "summary_reconstruction_pass": True,
        "raw_evidence_sha256": expected_raw_hashes,
        "resource_evidence_sha256": resource_hashes,
        "raw_candidate_config": raw_candidate_config,
    }


def run_readiness_candidate(
    *,
    disposable_root: Path | str,
    acquisition_receipt: Mapping[str, Any],
    manifest: Mapping[str, Any],
    code_root: Path | str,
    run_sequence: int,
    expected_candidate_commit: str | None = None,
    identity: Mapping[str, Any] | None = None,
    writer_free_runner: Callable[..., dict[str, Any]] | None = None,
    concurrency_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run one fixed candidate on the two acquired copies, never the product."""
    if isinstance(run_sequence, bool) or run_sequence not in {1, 2, 3}:
        raise RunEvidenceError("run sequence must be exactly 1, 2, or 3")
    started_at_utc = _utc_now()
    manifest_check = verify_runtime_manifest(
        manifest, code_root=code_root, expected_candidate_commit=expected_candidate_commit,
        identity=identity,
    )
    root, _ = _private_root(disposable_root, require_empty=False)
    oracle, writer_free, concurrency, pinned_anchor_sha256 = _require_acquisition(
        acquisition_receipt, manifest=manifest, root=root
    )
    writer_free_result: dict[str, Any] | None = None
    writer_free_postcheck: dict[str, Any] | None = None
    initialization_result: dict[str, Any] | None = None
    concurrency_result: dict[str, Any] | None = None
    recovery_result: dict[str, Any] | None = None
    writer_sampler: _StrictResourceSampler | None = None
    initialization_sampler: _StrictResourceSampler | None = None
    concurrency_sampler: _StrictResourceSampler | None = None
    recovery_sampler: _StrictResourceSampler | None = None
    failure: dict[str, Any] | None = None
    canonical_runners_used = writer_free_runner is None and concurrency_runner is None
    try:
        writer_sampler = _StrictResourceSampler(writer_free, "writer_free_outer")
        with writer_sampler:
            writer_free_result = (writer_free_runner or a03b.run_shadow_prototype)(
                writer_free,
                disposable_root=root,
                batch_events=REQUIRED_BATCH_EVENTS,
                batch_bytes=REQUIRED_BATCH_BYTES,
            )
            writer_free_postcheck = _postcheck_writer_free(
                writer_free,
                oracle=oracle,
                pinned_anchor=root / PINNED_ANCHOR_FILE,
            )
        concurrency_sampler = _StrictResourceSampler(
            concurrency, "concurrency_outer"
        )
        with concurrency_sampler:
            initialization_sampler = _StrictResourceSampler(
                concurrency, "concurrency_initialization"
            )
            with initialization_sampler:
                initialization_result = a03b.initialize_shadow(
                    concurrency, disposable_root=root
                )
            concurrency_result = (concurrency_runner or a03b.run_concurrency_probe)(
                concurrency,
                disposable_root=root,
                writer_interval_seconds=REQUIRED_WRITER_INTERVAL_SECONDS,
                batch_events=REQUIRED_BATCH_EVENTS,
                batch_bytes=REQUIRED_BATCH_BYTES,
                short_reader_interval_seconds=REQUIRED_READER_INTERVAL_SECONDS,
            )
            recovery_sampler = _StrictResourceSampler(
                concurrency, "concurrency_recovery"
            )
            with recovery_sampler:
                recovery_result = a03b.recover(concurrency, disposable_root=root)
    except Exception as exc:
        failure = {
            "phase": (
                "writer_free"
                if writer_free_result is None
                else "writer_free_postcheck"
                if writer_free_postcheck is None
                else "concurrency_initialization"
                if initialization_result is None
                else "concurrency"
                if concurrency_result is None
                else "recovery"
            ),
            "exception_class": type(exc).__name__,
            "message_logged": False,
        }
    resource_evidence = {
        "writer_free_outer": (
            writer_sampler.receipt()
            if writer_sampler is not None
            else _missing_resource_receipt("writer_free_outer")
        ),
        "concurrency_initialization": (
            initialization_sampler.receipt()
            if initialization_sampler is not None
            else _missing_resource_receipt("concurrency_initialization")
        ),
        "concurrency_outer": (
            concurrency_sampler.receipt()
            if concurrency_sampler is not None
            else _missing_resource_receipt("concurrency_outer")
        ),
        "concurrency_recovery": (
            recovery_sampler.receipt()
            if recovery_sampler is not None
            else _missing_resource_receipt("concurrency_recovery")
        ),
    }
    writer_summary = (
        _writer_free_summary(
            writer_free_result, oracle, resource_evidence["writer_free_outer"]
        )
        if writer_free_result is not None
        else {"gate_pass": False}
    )
    initialization_summary = (
        _initialization_summary(
            initialization_result, resource_evidence["concurrency_initialization"]
        )
        if initialization_result is not None
        else {"gate_pass": False}
    )
    concurrency_summary = (
        _concurrency_summary(
            concurrency_result, resource_evidence["concurrency_outer"]
        )
        if concurrency_result is not None
        else {"gate_pass": False}
    )
    recovery_summary = (
        _recovery_summary(
            recovery_result, resource_evidence["concurrency_recovery"]
        )
        if recovery_result is not None
        else {"gate_pass": False}
    )
    gate = bool(
        failure is None
        and canonical_runners_used
        and writer_summary.get("gate_pass") is True
        and isinstance(writer_free_postcheck, Mapping)
        and writer_free_postcheck.get("gate_pass") is True
        and initialization_summary.get("gate_pass") is True
        and concurrency_summary.get("gate_pass") is True
        and recovery_summary.get("gate_pass") is True
        and all(
            item.get("gate_pass") is True for item in resource_evidence.values()
        )
    )
    completed_at_utc = _utc_now()
    acquisition_time = _parse_utc(acquisition_receipt.get("acquired_at_utc"))
    if not acquisition_time <= _parse_utc(started_at_utc) <= _parse_utc(completed_at_utc):
        raise RunEvidenceError("acquisition/run UTC ordering is inconsistent")
    raw_evidence = {
        "writer_free": writer_free_result,
        "concurrency_initialization": initialization_result,
        "concurrency": concurrency_result,
        "concurrency_recovery": recovery_result,
    }
    body: dict[str, Any] = {
        "schema": RUN_RECEIPT_SCHEMA,
        "outcome": "green" if gate else "red",
        "started_at_utc": started_at_utc,
        "completed_at_utc": completed_at_utc,
        "acquisition_acquired_at_utc": acquisition_receipt.get("acquired_at_utc"),
        "run_sequence": run_sequence,
        "manifest_sha256": manifest["manifest_sha256"],
        "candidate_commit": manifest["candidate_commit"],
        "runtime_identity_sha256": manifest["runtime_identity_sha256"],
        "candidate_config_sha256": manifest_check["candidate_config_sha256"],
        "a0_3b_code_sha256": dict(manifest["a0_3b_code_sha256"]),
        "a0_3c_code_sha256": dict(manifest["a0_3c_code_sha256"]),
        "batch_events": REQUIRED_BATCH_EVENTS,
        "batch_bytes": REQUIRED_BATCH_BYTES,
        "writer_interval_seconds": REQUIRED_WRITER_INTERVAL_SECONDS,
        "short_reader_interval_seconds": REQUIRED_READER_INTERVAL_SECONDS,
        "canonical_runners_used": canonical_runners_used,
        "acquisition_receipt_sha256": acquisition_receipt["receipt_sha256"],
        "acquisition_oracle_sha256": oracle["oracle_sha256"],
        "acquisition_oracle": oracle,
        "pinned_anchor_sha256": pinned_anchor_sha256,
        "writer_free": writer_summary,
        "writer_free_postcheck": writer_free_postcheck,
        "concurrency_initialization": initialization_summary,
        "concurrency": concurrency_summary,
        "concurrency_recovery": recovery_summary,
        "raw_evidence": raw_evidence,
        "resource_evidence": resource_evidence,
        "raw_evidence_sha256": {
            key: _sha256_json(value) if value is not None else None
            for key, value in raw_evidence.items()
        },
        "failure": failure,
        "gate_pass": gate,
        "series_reset_required": not gate,
        "safety": {
            "product_database_opened_by_run": False,
            "only_acquired_sibling_copies_written": True,
            "product_activation_authorized": False,
            "retuning_performed": False,
            "paths_logged": False,
            "payloads_logged": False,
        },
    }
    body["raw_reconstruction"] = (
        _reconstruct_run_summaries(body)
        if gate
        else {
            "raw_inventory_exact": set(raw_evidence) == _RAW_EVIDENCE_KEYS,
            "resource_inventory_exact": set(resource_evidence)
            == _RESOURCE_EVIDENCE_KEYS,
            "summary_reconstruction_pass": False,
        }
    )
    receipt = _seal_receipt(body)
    assert_receipt_safe(receipt)
    return receipt


def initialize_series_journal(
    series_root: Path | str,
    *,
    manifest: Mapping[str, Any],
    code_root: Path | str,
    expected_candidate_commit: str | None = None,
    identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Initialize one fresh, private append-only attempt journal."""
    manifest_check = verify_runtime_manifest(
        manifest,
        code_root=code_root,
        expected_candidate_commit=expected_candidate_commit,
        identity=identity,
    )
    root, root_stat = _private_root(series_root, require_empty=True)
    journal = root / SERIES_JOURNAL_DIR
    os.mkdir(journal, mode=0o700)
    if hasattr(os, "chmod"):
        os.chmod(journal, 0o700)
    journal_stat = journal.stat(follow_symlinks=False)
    body = {
        "schema": SERIES_INIT_SCHEMA,
        "created_at_utc": _utc_now(),
        "manifest_sha256": manifest["manifest_sha256"],
        "candidate_commit": manifest["candidate_commit"],
        "runtime_identity_sha256": manifest["runtime_identity_sha256"],
        "candidate_config_sha256": manifest_check["candidate_config_sha256"],
        "a0_3b_code_sha256": dict(manifest["a0_3b_code_sha256"]),
        "a0_3c_code_sha256": dict(manifest["a0_3c_code_sha256"]),
        "batch_events": REQUIRED_BATCH_EVENTS,
        "batch_bytes": REQUIRED_BATCH_BYTES,
        "root_device": root_stat["device"],
        "root_inode": root_stat["inode"],
        "journal_device": int(journal_stat.st_dev),
        "journal_inode": int(journal_stat.st_ino),
        "first_epoch": 1,
        "first_sequence": 1,
        "paths_logged": False,
        "payloads_logged": False,
    }
    receipt = _seal_receipt(body)
    write_json_evidence(root / SERIES_INIT_FILE, receipt)
    return receipt


def _append_journal_entry(
    journal: Path,
    *,
    index: int,
    previous_sha256: str,
    series_init_sha256: str,
    entry_type: str,
    fields: Mapping[str, Any],
) -> dict[str, Any]:
    if index < 1 or index > MAX_JOURNAL_ENTRIES:
        raise SeriesEvidenceError("journal entry cap exceeded")
    created_at_utc = _utc_now()
    if index > 1:
        previous_entry = read_json_evidence(
            journal / f"{index - 1:08d}.json", require_private=True
        )
        previous_created = _parse_utc(previous_entry.get("created_at_utc"))
        current_created = _parse_utc(created_at_utc)
        if current_created <= previous_created:
            created_at_utc = (
                previous_created + datetime.resolution
            ).isoformat(timespec="microseconds").replace("+00:00", "Z")
    body = {
        "schema": JOURNAL_ENTRY_SCHEMA,
        "index": index,
        "previous_entry_sha256": previous_sha256,
        "series_init_sha256": series_init_sha256,
        "entry_type": entry_type,
        "created_at_utc": created_at_utc,
        **dict(fields),
        "paths_logged": False,
        "payloads_logged": False,
    }
    receipt = _seal_receipt(body)
    write_json_evidence(journal / f"{index:08d}.json", receipt)
    return receipt


def _journal_inventory(
    series_root: Path | str,
    *,
    manifest: Mapping[str, Any],
    supplied_init: Mapping[str, Any] | None = None,
) -> tuple[Path, Path, dict[str, Any], list[dict[str, Any]]]:
    root, root_stat = _private_root(series_root, require_empty=False)
    root_entries = {item.name: item for item in root.iterdir()}
    if set(root_entries) != {SERIES_INIT_FILE, SERIES_JOURNAL_DIR}:
        raise SeriesEvidenceError("series root inventory is not exact")
    init_path = root_entries[SERIES_INIT_FILE]
    journal = root_entries[SERIES_JOURNAL_DIR]
    if init_path.is_symlink() or journal.is_symlink() or not journal.is_dir():
        raise SeriesEvidenceError("series journal paths are not regular")
    init = read_json_evidence(init_path, require_private=True)
    init_sha = _verify_receipt_digest(init, "series init")
    if supplied_init is not None and dict(supplied_init) != init:
        raise SeriesEvidenceError("supplied series init differs from pinned root init")
    journal_stat = journal.stat(follow_symlinks=False)
    expected_init = {
        "schema": SERIES_INIT_SCHEMA,
        "manifest_sha256": manifest.get("manifest_sha256"),
        "candidate_commit": manifest.get("candidate_commit"),
        "runtime_identity_sha256": manifest.get("runtime_identity_sha256"),
        "candidate_config_sha256": _sha256_json(required_candidate_config()),
        "a0_3b_code_sha256": manifest.get("a0_3b_code_sha256"),
        "a0_3c_code_sha256": manifest.get("a0_3c_code_sha256"),
        "batch_events": REQUIRED_BATCH_EVENTS,
        "batch_bytes": REQUIRED_BATCH_BYTES,
        "root_device": root_stat["device"],
        "root_inode": root_stat["inode"],
        "journal_device": int(journal_stat.st_dev),
        "journal_inode": int(journal_stat.st_ino),
        "first_epoch": 1,
        "first_sequence": 1,
    }
    if any(init.get(key) != value for key, value in expected_init.items()):
        raise SeriesEvidenceError("series init pin differs")
    if os.name == "posix" and stat.S_IMODE(journal_stat.st_mode) != 0o700:
        raise SeriesEvidenceError("series journal directory is not mode 0700")
    paths: list[tuple[int, Path]] = []
    with os.scandir(journal) as scan:
        for count, item in enumerate(scan, start=1):
            if count > MAX_JOURNAL_ENTRIES:
                raise SeriesEvidenceError("journal entry cap exceeded")
            match = _JOURNAL_FILE.fullmatch(item.name)
            if (
                match is None
                or item.is_symlink()
                or not item.is_file(follow_symlinks=False)
            ):
                raise SeriesEvidenceError("journal contains a foreign entry")
            paths.append((int(match.group(1)), Path(item.path)))
    paths.sort()
    if [index for index, _ in paths] != list(range(1, len(paths) + 1)):
        raise SeriesEvidenceError("journal indices are not contiguous")
    entries: list[dict[str, Any]] = []
    previous = _ZERO_SHA256
    for index, path in paths:
        entry = read_json_evidence(path, require_private=True)
        digest = _verify_receipt_digest(entry, f"journal entry {index}")
        if (
            entry.get("schema") != JOURNAL_ENTRY_SCHEMA
            or entry.get("index") != index
            or entry.get("previous_entry_sha256") != previous
            or entry.get("series_init_sha256") != init_sha
        ):
            raise SeriesEvidenceError("journal chain binding differs")
        previous = digest
        entries.append(entry)
    return root, journal, init, entries


_JOURNAL_COMMON_KEYS = {
    "schema", "index", "previous_entry_sha256", "series_init_sha256",
    "entry_type", "created_at_utc", "paths_logged", "payloads_logged",
    "receipt_sha256",
}
_JOURNAL_START_KEYS = {
    "epoch", "sequence", "attempt_id", "acquisition_receipt_sha256",
    "acquisition_acquired_at_utc", "process_id", "process_create_time",
}
_JOURNAL_FINISH_KEYS = {
    "epoch", "sequence", "attempt_id", "start_entry_sha256", "outcome",
    "run_receipt", "exception_class",
}
_JOURNAL_RESET_KEYS = {
    "closed_epoch", "new_epoch", "reset_for_entry_sha256", "reason",
}


def _validate_journal_state(
    entries: Sequence[Mapping[str, Any]], *, manifest: Mapping[str, Any]
) -> dict[str, Any]:
    epoch = 1
    sequence = 1
    open_attempt: Mapping[str, Any] | None = None
    pending_red: Mapping[str, Any] | None = None
    attempts = finishes = resets = abandoned_resets = 0
    attempt_ids: set[str] = set()
    acquisition_ids: set[str] = set()
    previous_created: datetime | None = None
    validation_time = datetime.now(timezone.utc)
    for entry in entries:
        entry_type = entry.get("entry_type")
        created = _parse_utc(entry.get("created_at_utc"))
        if created > validation_time:
            raise SeriesEvidenceError("journal timestamp is in the future")
        if previous_created is not None and not previous_created < created:
            raise SeriesEvidenceError("journal timestamps are not strictly increasing")
        previous_created = created
        if entry.get("paths_logged") is not False or entry.get("payloads_logged") is not False:
            raise SeriesEvidenceError("journal entry weakens logging safety")
        if entry_type == "attempt_start":
            if set(entry) != _JOURNAL_COMMON_KEYS | _JOURNAL_START_KEYS:
                raise SeriesEvidenceError("attempt-start schema is not exact")
            if open_attempt is not None or pending_red is not None or sequence > 3:
                raise SeriesEvidenceError("attempt-start violates journal state")
            if entry.get("epoch") != epoch or entry.get("sequence") != sequence:
                raise SeriesEvidenceError("attempt-start epoch or sequence differs")
            attempt_id = str(entry.get("attempt_id"))
            acquisition_id = str(entry.get("acquisition_receipt_sha256"))
            if not _HEX64.fullmatch(attempt_id) or not _HEX64.fullmatch(acquisition_id):
                raise SeriesEvidenceError("attempt-start binding is malformed")
            if attempt_id in attempt_ids or acquisition_id in acquisition_ids:
                raise SeriesEvidenceError("attempt or acquisition is reused")
            acquisition_created = _parse_utc(
                entry.get("acquisition_acquired_at_utc")
            )
            if acquisition_created > created:
                raise SeriesEvidenceError("attempt starts before its acquisition")
            if (
                not isinstance(entry.get("process_id"), int)
                or entry.get("process_id", 0) < 1
                or not isinstance(entry.get("process_create_time"), (int, float))
                or isinstance(entry.get("process_create_time"), bool)
                or entry.get("process_create_time", 0) <= 0
            ):
                raise SeriesEvidenceError("attempt-start process identity is malformed")
            open_attempt = entry
            attempt_ids.add(attempt_id)
            acquisition_ids.add(acquisition_id)
            attempts += 1
        elif entry_type == "attempt_finish":
            if set(entry) != _JOURNAL_COMMON_KEYS | _JOURNAL_FINISH_KEYS:
                raise SeriesEvidenceError("attempt-finish schema is not exact")
            if open_attempt is None or pending_red is not None:
                raise SeriesEvidenceError("attempt-finish has no open attempt")
            if any(
                entry.get(key) != open_attempt.get(key)
                for key in ("epoch", "sequence", "attempt_id")
            ) or entry.get("start_entry_sha256") != open_attempt.get("receipt_sha256"):
                raise SeriesEvidenceError("attempt-finish does not bind its start")
            run = entry.get("run_receipt")
            exception_class = entry.get("exception_class")
            if isinstance(run, Mapping):
                _verify_receipt_digest(run, "journal run")
                expected_outcome = "green" if run.get("gate_pass") is True else "red"
                acquisition_created = _parse_utc(
                    open_attempt.get("acquisition_acquired_at_utc")
                )
                start_created = _parse_utc(open_attempt.get("created_at_utc"))
                run_started = _parse_utc(run.get("started_at_utc"))
                run_completed = _parse_utc(run.get("completed_at_utc"))
                if (
                    run.get("schema") != RUN_RECEIPT_SCHEMA
                    or run.get("manifest_sha256") != manifest.get("manifest_sha256")
                    or run.get("run_sequence") != sequence
                    or run.get("acquisition_receipt_sha256")
                    != open_attempt.get("acquisition_receipt_sha256")
                    or run.get("acquisition_acquired_at_utc")
                    != open_attempt.get("acquisition_acquired_at_utc")
                    or not acquisition_created
                    <= start_created
                    <= run_started
                    <= run_completed
                    <= created
                    or entry.get("outcome") != expected_outcome
                    or exception_class is not None
                ):
                    raise SeriesEvidenceError("attempt-finish run binding differs")
            elif (
                run is not None
                or entry.get("outcome") != "red"
                or not isinstance(exception_class, str)
                or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", exception_class) is None
            ):
                raise SeriesEvidenceError("attempt-finish exception evidence is malformed")
            open_attempt = None
            finishes += 1
            if entry.get("outcome") == "green":
                sequence += 1
            else:
                pending_red = entry
        elif entry_type == "reset":
            if set(entry) != _JOURNAL_COMMON_KEYS | _JOURNAL_RESET_KEYS:
                raise SeriesEvidenceError("reset schema is not exact")
            target = open_attempt if open_attempt is not None else pending_red
            reason = "abandoned_open_attempt" if open_attempt is not None else "red_finish"
            if (
                target is None
                or entry.get("closed_epoch") != epoch
                or entry.get("new_epoch") != epoch + 1
                or entry.get("reset_for_entry_sha256") != target.get("receipt_sha256")
                or entry.get("reason") != reason
            ):
                raise SeriesEvidenceError("reset does not bind the failed epoch")
            epoch += 1
            sequence = 1
            open_attempt = None
            pending_red = None
            resets += 1
            abandoned_resets += reason == "abandoned_open_attempt"
        else:
            raise SeriesEvidenceError("journal entry type is foreign")
    return {
        "epoch": epoch,
        "next_sequence": sequence,
        "open_attempt": open_attempt,
        "pending_red": pending_red,
        "attempt_count": attempts,
        "finish_count": finishes,
        "reset_count": resets,
        "abandoned_reset_count": abandoned_resets,
    }


def _process_still_matches(attempt: Mapping[str, Any]) -> bool:
    try:
        process = psutil.Process(int(attempt["process_id"]))
        return bool(
            process.is_running()
            and process.status() != psutil.STATUS_ZOMBIE
            and abs(float(process.create_time()) - float(attempt["process_create_time"]))
            < 0.001
        )
    except (psutil.Error, KeyError, TypeError, ValueError):
        return False


def reserve_series_attempt(
    series_root: Path | str,
    *,
    series_init: Mapping[str, Any],
    acquisition_receipt: Mapping[str, Any],
    requested_sequence: int,
    manifest: Mapping[str, Any],
    code_root: Path | str,
    expected_candidate_commit: str | None = None,
    identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Reserve an attempt before the long run, resetting failed epochs first."""
    verify_runtime_manifest(
        manifest,
        code_root=code_root,
        expected_candidate_commit=expected_candidate_commit,
        identity=identity,
    )
    acquisition_sha = _verify_receipt_digest(acquisition_receipt, "acquisition")
    if (
        acquisition_receipt.get("schema") != ACQUISITION_RECEIPT_SCHEMA
        or acquisition_receipt.get("outcome") != "acquired"
        or acquisition_receipt.get("manifest_sha256") != manifest.get("manifest_sha256")
    ):
        raise SeriesEvidenceError("attempt acquisition binding differs")
    acquisition_created = _parse_utc(acquisition_receipt.get("acquired_at_utc"))
    if acquisition_created > datetime.now(timezone.utc):
        raise SeriesEvidenceError("attempt acquisition timestamp is in the future")
    root, journal, init, entries = _journal_inventory(
        series_root, manifest=manifest, supplied_init=series_init
    )
    del root
    state = _validate_journal_state(entries, manifest=manifest)
    if any(
        entry.get("entry_type") == "attempt_start"
        and entry.get("acquisition_receipt_sha256") == acquisition_sha
        for entry in entries
    ):
        raise SeriesEvidenceError("attempt acquisition was already used")
    open_attempt = state["open_attempt"]
    if open_attempt is not None and _process_still_matches(open_attempt):
        raise SeriesEvidenceError("a matching live process still owns the open attempt")
    reset_target = open_attempt or state["pending_red"]
    if reset_target is not None:
        reason = "abandoned_open_attempt" if open_attempt is not None else "red_finish"
        previous = entries[-1]["receipt_sha256"] if entries else _ZERO_SHA256
        _append_journal_entry(
            journal,
            index=len(entries) + 1,
            previous_sha256=previous,
            series_init_sha256=init["receipt_sha256"],
            entry_type="reset",
            fields={
                "closed_epoch": state["epoch"],
                "new_epoch": state["epoch"] + 1,
                "reset_for_entry_sha256": reset_target["receipt_sha256"],
                "reason": reason,
            },
        )
        _, journal, init, entries = _journal_inventory(
            series_root, manifest=manifest, supplied_init=series_init
        )
        state = _validate_journal_state(entries, manifest=manifest)
    if requested_sequence != state["next_sequence"] or requested_sequence not in {1, 2, 3}:
        raise SeriesEvidenceError("requested run sequence differs from journal state")
    process = psutil.Process(os.getpid())
    previous_attempt_ids = {
        str(entry.get("attempt_id"))
        for entry in entries
        if entry.get("entry_type") == "attempt_start"
    }
    while True:
        attempt_id = hashlib.sha256(
            _canonical_bytes(
                {
                    "series_init_sha256": init["receipt_sha256"],
                    "acquisition_receipt_sha256": acquisition_sha,
                    "index": len(entries) + 1,
                    "nonce_sha256": hashlib.sha256(os.urandom(32)).hexdigest(),
                }
            )
        ).hexdigest()
        if attempt_id not in previous_attempt_ids:
            break
    previous = entries[-1]["receipt_sha256"] if entries else _ZERO_SHA256
    start = _append_journal_entry(
        journal,
        index=len(entries) + 1,
        previous_sha256=previous,
        series_init_sha256=init["receipt_sha256"],
        entry_type="attempt_start",
        fields={
            "epoch": state["epoch"],
            "sequence": requested_sequence,
            "attempt_id": attempt_id,
            "acquisition_receipt_sha256": acquisition_sha,
            "acquisition_acquired_at_utc": acquisition_receipt["acquired_at_utc"],
            "process_id": os.getpid(),
            "process_create_time": float(process.create_time()),
        },
    )
    _validate_journal_state([*entries, start], manifest=manifest)
    return start


def finish_series_attempt(
    series_root: Path | str,
    *,
    series_init: Mapping[str, Any],
    start_entry: Mapping[str, Any],
    manifest: Mapping[str, Any],
    run_receipt: Mapping[str, Any] | None = None,
    exception_class: str | None = None,
) -> dict[str, Any]:
    """Append the only valid terminal record for the currently open attempt."""
    _, journal, init, entries = _journal_inventory(
        series_root, manifest=manifest, supplied_init=series_init
    )
    state = _validate_journal_state(entries, manifest=manifest)
    open_attempt = state["open_attempt"]
    if open_attempt is None or dict(open_attempt) != dict(start_entry):
        raise SeriesEvidenceError("attempt finish does not own the open journal tail")
    if (run_receipt is None) == (exception_class is None):
        raise SeriesEvidenceError("attempt finish requires exactly one result kind")
    if run_receipt is not None:
        _verify_receipt_digest(run_receipt, "attempt run")
        outcome = "green" if run_receipt.get("gate_pass") is True else "red"
        acquisition_created = _parse_utc(
            open_attempt.get("acquisition_acquired_at_utc")
        )
        start_created = _parse_utc(open_attempt.get("created_at_utc"))
        run_started = _parse_utc(run_receipt.get("started_at_utc"))
        run_completed = _parse_utc(run_receipt.get("completed_at_utc"))
        if (
            run_receipt.get("schema") != RUN_RECEIPT_SCHEMA
            or run_receipt.get("manifest_sha256") != manifest.get("manifest_sha256")
            or run_receipt.get("run_sequence") != open_attempt.get("sequence")
            or run_receipt.get("acquisition_receipt_sha256")
            != open_attempt.get("acquisition_receipt_sha256")
            or run_receipt.get("acquisition_acquired_at_utc")
            != open_attempt.get("acquisition_acquired_at_utc")
            or not acquisition_created
            <= start_created
            <= run_started
            <= run_completed
            <= datetime.now(timezone.utc)
        ):
            raise SeriesEvidenceError("attempt run does not bind the open start")
        embedded_run: Mapping[str, Any] | None = dict(run_receipt)
        type_only: str | None = None
    else:
        if (
            not isinstance(exception_class, str)
            or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", exception_class) is None
        ):
            raise SeriesEvidenceError("attempt exception class is malformed")
        outcome = "red"
        embedded_run = None
        type_only = exception_class
    finish = _append_journal_entry(
        journal,
        index=len(entries) + 1,
        previous_sha256=entries[-1]["receipt_sha256"],
        series_init_sha256=init["receipt_sha256"],
        entry_type="attempt_finish",
        fields={
            "epoch": open_attempt["epoch"],
            "sequence": open_attempt["sequence"],
            "attempt_id": open_attempt["attempt_id"],
            "start_entry_sha256": open_attempt["receipt_sha256"],
            "outcome": outcome,
            "run_receipt": embedded_run,
            "exception_class": type_only,
        },
    )
    _validate_journal_state([*entries, finish], manifest=manifest)
    return finish


def verify_series_journal(
    series_root: Path | str,
    *,
    series_init: Mapping[str, Any],
    manifest: Mapping[str, Any],
    code_root: Path | str,
    expected_candidate_commit: str | None = None,
    identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify the complete chain and only accept the latest three-green epoch."""
    verify_runtime_manifest(
        manifest,
        code_root=code_root,
        expected_candidate_commit=expected_candidate_commit,
        identity=identity,
    )
    _, _, init, entries = _journal_inventory(
        series_root, manifest=manifest, supplied_init=series_init
    )
    state = _validate_journal_state(entries, manifest=manifest)
    if state["open_attempt"] is not None or state["pending_red"] is not None:
        raise SeriesEvidenceError("latest journal epoch is unfinished or red")
    latest_starts = [
        entry
        for entry in entries
        if entry.get("entry_type") == "attempt_start"
        and entry.get("epoch") == state["epoch"]
    ]
    latest_finishes = [
        entry
        for entry in entries
        if entry.get("entry_type") == "attempt_finish"
        and entry.get("epoch") == state["epoch"]
    ]
    if (
        len(latest_starts) != REQUIRED_CONSECUTIVE_RUNS
        or len(latest_finishes) != REQUIRED_CONSECUTIVE_RUNS
        or [entry.get("sequence") for entry in latest_starts] != [1, 2, 3]
        or [entry.get("sequence") for entry in latest_finishes] != [1, 2, 3]
        or any(entry.get("outcome") != "green" for entry in latest_finishes)
    ):
        raise SeriesEvidenceError("latest epoch is not exactly three green attempts")
    runs = [entry.get("run_receipt") for entry in latest_finishes]
    if any(not isinstance(run, Mapping) for run in runs):
        raise SeriesEvidenceError("latest epoch omits an embedded run")
    verified = verify_run_series(
        runs,  # type: ignore[arg-type]
        manifest=manifest,
        code_root=code_root,
        expected_candidate_commit=expected_candidate_commit,
        identity=identity,
    )
    body = {key: value for key, value in verified.items() if key != "receipt_sha256"}
    body.update(
        {
            "series_init_sha256": init["receipt_sha256"],
            "journal_entry_count": len(entries),
            "journal_entry_sha256": [entry["receipt_sha256"] for entry in entries],
            "journal_chain_tip_sha256": (
                entries[-1]["receipt_sha256"] if entries else _ZERO_SHA256
            ),
            "journal_attempt_count": state["attempt_count"],
            "journal_finish_count": state["finish_count"],
            "journal_reset_count": state["reset_count"],
            "latest_epoch": state["epoch"],
            "all_attempts_bound": state["attempt_count"]
            == state["finish_count"] + state["abandoned_reset_count"],
            "latest_epoch_exact_three_green": True,
        }
    )
    if body["all_attempts_bound"] is not True:
        raise SeriesEvidenceError("journal leaves an attempt unbound")
    receipt = _seal_receipt(body)
    assert_receipt_safe(receipt)
    return receipt


def verify_final_series_receipt_chain(
    final_receipt: Path | str,
    *,
    series_evidence_root: Path | str,
    manifest: Mapping[str, Any],
    code_root: Path | str,
    expected_candidate_commit: str | None = None,
    identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Replay the canonical journal and bind it to its persisted aggregate."""

    def private_dir(raw: Path, label: str) -> Path:
        if raw.is_symlink():
            raise SeriesEvidenceError(f"{label} must not be a symlink")
        try:
            resolved = raw.resolve(strict=True)
            info = raw.stat(follow_symlinks=False)
        except (FileNotFoundError, OSError) as exc:
            raise SeriesEvidenceError(f"{label} is missing") from exc
        if resolved != raw or not stat.S_ISDIR(info.st_mode):
            raise SeriesEvidenceError(f"{label} is not a canonical directory")
        if os.name == "posix" and (
            int(info.st_uid) != int(os.geteuid())
            or stat.S_IMODE(info.st_mode) != 0o700
        ):
            raise SeriesEvidenceError(f"{label} must be user-owned mode 0700")
        return resolved

    base_raw = Path(series_evidence_root).expanduser().absolute()
    base = private_dir(base_raw, "series evidence root")
    supplied_raw = Path(final_receipt).expanduser().absolute()
    if supplied_raw.name != "final-series.json" or supplied_raw.parent.parent != base:
        raise SeriesEvidenceError("final series receipt layout differs")
    parent = private_dir(supplied_raw.parent, "series parent")
    if parent.parent != base:
        raise SeriesEvidenceError("series parent is not directly below its fixed root")
    supplied_path = parent / "final-series.json"
    if supplied_path != supplied_raw or supplied_path.is_symlink():
        raise SeriesEvidenceError("final series receipt is not canonical")
    supplied_info = supplied_path.stat(follow_symlinks=False)
    if (
        not stat.S_ISREG(supplied_info.st_mode)
        or supplied_info.st_nlink != 1
        or (
            os.name == "posix"
            and (
                int(supplied_info.st_uid) != int(os.geteuid())
                or stat.S_IMODE(supplied_info.st_mode) != 0o600
            )
        )
    ):
        raise SeriesEvidenceError("final series receipt must be user-owned mode 0600 and single-linked")
    journal_root = private_dir(parent / "journal-root", "series journal root")
    init_path = journal_root / SERIES_INIT_FILE
    if init_path.is_symlink() or not init_path.is_file():
        raise SeriesEvidenceError("internal series init is not a regular file")
    init_info = init_path.stat(follow_symlinks=False)
    if (
        init_info.st_nlink != 1
        or (
            os.name == "posix"
            and (
                int(init_info.st_uid) != int(os.geteuid())
                or stat.S_IMODE(init_info.st_mode) != 0o600
            )
        )
    ):
        raise SeriesEvidenceError("internal series init must be user-owned mode 0600 and single-linked")
    journal_dir = private_dir(journal_root / SERIES_JOURNAL_DIR, "series journal directory")

    def evidence_snapshot() -> tuple[
        dict[str, tuple[Any, ...]], str, str, list[str]
    ]:
        checked_dirs = (
            private_dir(base_raw, "series evidence root"),
            private_dir(parent, "series parent"),
            private_dir(journal_root, "series journal root"),
            private_dir(journal_dir, "series journal directory"),
        )
        journal_files = sorted(
            journal_dir.iterdir(), key=lambda item: os.fsencode(item.name)
        )
        if len(journal_files) > MAX_JOURNAL_ENTRIES:
            raise SeriesEvidenceError("journal entry cap exceeded")
        indexed: list[tuple[int, Path]] = []
        for entry in journal_files:
            match = _JOURNAL_FILE.fullmatch(entry.name)
            if match is None:
                raise SeriesEvidenceError("journal contains a foreign entry")
            indexed.append((int(match.group(1)), entry))
        if [index for index, _ in indexed] != list(range(1, len(indexed) + 1)):
            raise SeriesEvidenceError("journal indices are not contiguous")
        files = [supplied_path, init_path, *(entry for _, entry in indexed)]
        snapshot: dict[str, tuple[Any, ...]] = {}
        pinned_bytes: dict[str, bytes] = {}
        for directory in checked_dirs:
            info = directory.stat(follow_symlinks=False)
            snapshot[str(directory)] = (
                int(info.st_dev), int(info.st_ino), int(info.st_uid), int(info.st_mode),
                int(info.st_nlink), int(info.st_size), int(info.st_mtime_ns),
            )
        for entry in files:
            data, evidence = _stable_file_bytes(entry, MAX_RECEIPT_BYTES)
            if (
                entry.is_symlink()
                or evidence["links"] != 1
                or (
                    os.name == "posix"
                    and (
                        evidence["uid"] != int(os.geteuid())
                        or evidence["mode"] != "0600"
                    )
                )
            ):
                raise SeriesEvidenceError("series evidence file privacy differs")
            snapshot[str(entry)] = (
                evidence["device"], evidence["inode"], evidence["uid"],
                evidence["mode"], evidence["links"], evidence["bytes"],
                evidence["sha256"],
            )
            pinned_bytes[str(entry)] = data
        pinned_init = _decode_json_evidence(pinned_bytes[str(init_path)])
        init_digest = _verify_receipt_digest(pinned_init, "pinned series init")
        entry_digests = [
            _verify_receipt_digest(
                _decode_json_evidence(pinned_bytes[str(entry)]),
                f"pinned journal entry {index}",
            )
            for index, entry in indexed
        ]
        return snapshot, snapshot[str(supplied_path)][-1], init_digest, entry_digests

    privacy_before, pinned_final_hash, pinned_init_digest, pinned_entry_digests = (
        evidence_snapshot()
    )
    before_bytes, before_stat = _stable_file_bytes(supplied_path, MAX_RECEIPT_BYTES)
    if before_stat["sha256"] != pinned_final_hash:
        raise SeriesEvidenceError("final series receipt differs from pinned evidence snapshot")
    supplied = _decode_json_evidence(before_bytes)
    supplied_digest = _verify_receipt_digest(supplied, "final series")
    _parse_utc(supplied.get("verified_at_utc"))
    series_init = read_json_evidence(
        init_path, limit=MAX_RECEIPT_BYTES, require_private=True
    )
    replayed = verify_series_journal(
        journal_root,
        series_init=series_init,
        manifest=manifest,
        code_root=code_root,
        expected_candidate_commit=expected_candidate_commit,
        identity=identity,
    )
    if (
        replayed.get("series_init_sha256") != pinned_init_digest
        or replayed.get("journal_entry_sha256") != pinned_entry_digests
    ):
        raise SeriesEvidenceError("journal replay differs from pinned evidence inventory")
    time_dependent = {"verified_at_utc", "receipt_sha256"}
    supplied_static = {
        key: value for key, value in supplied.items() if key not in time_dependent
    }
    replayed_static = {
        key: value for key, value in replayed.items() if key not in time_dependent
    }
    if supplied_static != replayed_static:
        raise SeriesEvidenceError("final series receipt differs from journal replay")
    after_bytes, after_stat = _stable_file_bytes(supplied_path, MAX_RECEIPT_BYTES)
    privacy_after, final_hash_after, init_digest_after, entry_digests_after = (
        evidence_snapshot()
    )
    if (
        before_bytes != after_bytes
        or before_stat != after_stat
        or after_stat["sha256"] != final_hash_after
        or privacy_before != privacy_after
        or pinned_init_digest != init_digest_after
        or pinned_entry_digests != entry_digests_after
    ):
        raise SeriesEvidenceError("final series receipt changed during chain replay")
    return {
        "resolved_path": str(supplied_path),
        "file_sha256": before_stat["sha256"],
        "receipt_sha256": supplied_digest,
        "manifest_sha256": replayed["manifest_sha256"],
        "candidate_commit": replayed["candidate_commit"],
        "runtime_identity_sha256": replayed["runtime_identity_sha256"],
        "consecutive_green_runs": replayed["consecutive_green_runs"],
        "gate_pass": replayed["gate_pass"],
        "journal_chain_tip_sha256": replayed["journal_chain_tip_sha256"],
    }


def verify_run_series(
    run_receipts: Sequence[Mapping[str, Any]],
    *, manifest: Mapping[str, Any], code_root: Path | str,
    expected_candidate_commit: str | None = None,
    identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify exactly three fresh, consecutive, untuned candidate runs."""
    manifest_check = verify_runtime_manifest(
        manifest, code_root=code_root, expected_candidate_commit=expected_candidate_commit,
        identity=identity,
    )
    if len(run_receipts) != REQUIRED_CONSECUTIVE_RUNS:
        raise SeriesEvidenceError("series must contain exactly three run receipts")
    run_digests: list[str] = []
    acquisitions: list[str] = []
    acquisition_times: list[datetime] = []
    started_times: list[datetime] = []
    completed_times: list[datetime] = []
    red: list[int] = []
    common = {
        "manifest_sha256": manifest["manifest_sha256"],
        "candidate_commit": manifest["candidate_commit"],
        "runtime_identity_sha256": manifest["runtime_identity_sha256"],
        "candidate_config_sha256": manifest_check["candidate_config_sha256"],
        "a0_3b_code_sha256": manifest["a0_3b_code_sha256"],
        "a0_3c_code_sha256": manifest["a0_3c_code_sha256"],
        "batch_events": REQUIRED_BATCH_EVENTS,
        "batch_bytes": REQUIRED_BATCH_BYTES,
        "writer_interval_seconds": REQUIRED_WRITER_INTERVAL_SECONDS,
        "short_reader_interval_seconds": REQUIRED_READER_INTERVAL_SECONDS,
        "canonical_runners_used": True,
    }
    for sequence, receipt in enumerate(run_receipts, start=1):
        if receipt.get("schema") != RUN_RECEIPT_SCHEMA:
            raise SeriesEvidenceError("series contains a foreign receipt")
        run_digests.append(_verify_receipt_digest(receipt, f"run {sequence}"))
        if receipt.get("run_sequence") != sequence:
            raise SeriesEvidenceError("run sequence is not exactly 1, 2, 3")
        for key, expected in common.items():
            if receipt.get(key) != expected:
                raise SeriesEvidenceError(f"run changes the {key} pin")
        acquisition = receipt.get("acquisition_receipt_sha256")
        if not isinstance(acquisition, str) or not _HEX64.fullmatch(acquisition):
            raise SeriesEvidenceError("run acquisition binding is malformed")
        acquisitions.append(acquisition)
        acquisition_time = _parse_utc(receipt.get("acquisition_acquired_at_utc"))
        started_time = _parse_utc(receipt.get("started_at_utc"))
        completed_time = _parse_utc(receipt.get("completed_at_utc"))
        if not acquisition_time <= started_time <= completed_time:
            raise SeriesEvidenceError("run timestamps are internally unordered")
        acquisition_times.append(acquisition_time)
        started_times.append(started_time)
        completed_times.append(completed_time)
        writer = receipt.get("writer_free")
        postcheck = receipt.get("writer_free_postcheck")
        initialization = receipt.get("concurrency_initialization")
        concurrency = receipt.get("concurrency")
        concurrency_writer = concurrency.get("writer") if isinstance(concurrency, Mapping) else None
        writer_decision = writer.get("final_sync_decision") if isinstance(writer, Mapping) else None
        concurrency_decision = (
            concurrency.get("final_sync_decision")
            if isinstance(concurrency, Mapping)
            else None
        )
        safety = receipt.get("safety")
        reconstruction: Mapping[str, Any] | None = None
        if receipt.get("gate_pass") is True:
            try:
                reconstruction = _reconstruct_run_summaries(receipt)
            except RuntimeReadinessError as exc:
                raise SeriesEvidenceError(
                    "green run raw evidence cannot reconstruct its summaries"
                ) from exc
        details_green = bool(
            isinstance(writer, Mapping)
            and writer.get("gate_pass") is True
            and writer.get("all_twelve_projection_digests_match") is True
            and writer.get("all_nine_sequences_match") is True
            and writer.get("ledger_before_after_unchanged_and_acquisition_bound") is True
            and writer.get("no_fallback") is True
            and isinstance(writer_decision, Mapping)
            and writer_decision.get("gate_pass") is True
            and writer_decision.get("decision_reason")
            == REQUIRED_FINAL_SYNC_DECISION_REASON
            and writer_decision.get("writer_free_verify_admission_cutover_agree")
            is True
            and writer.get("all_experimental_write_evidence_exhaustive") is True
            and writer.get("numeric_budgets_pass") is True
            and isinstance(postcheck, Mapping)
            and postcheck.get("gate_pass") is True
            and isinstance(initialization, Mapping)
            and initialization.get("gate_pass") is True
            and isinstance(concurrency, Mapping)
            and concurrency.get("gate_pass") is True
            and concurrency.get("all_twelve_projection_digests_match") is True
            and concurrency.get("all_nine_sequences_match") is True
            and concurrency.get("no_fallback") is True
            and isinstance(concurrency_decision, Mapping)
            and concurrency_decision.get("gate_pass") is True
            and concurrency_decision.get("decision_reason")
            == REQUIRED_FINAL_SYNC_DECISION_REASON
            and concurrency_decision.get("verify_admission_cutover_agree") is True
            and isinstance(concurrency_writer, Mapping)
            and concurrency_writer.get("timeouts") == 0
            and concurrency_writer.get("errors") == 0
            and concurrency_writer.get("starvation") is False
            and concurrency_writer.get("evidence_complete") is True
            and concurrency.get("all_experimental_write_evidence_exhaustive") is True
            and concurrency.get("writer_handoff_pass") is True
            and isinstance(receipt.get("concurrency_recovery"), Mapping)
            and receipt["concurrency_recovery"].get("gate_pass") is True
            and isinstance(receipt.get("raw_evidence"), Mapping)
            and isinstance(receipt.get("raw_evidence_sha256"), Mapping)
            and all(
                value is not None
                and receipt["raw_evidence_sha256"].get(key) == _sha256_json(value)
                for key, value in receipt["raw_evidence"].items()
            )
            and isinstance(safety, Mapping)
            and safety.get("product_database_opened_by_run") is False
            and safety.get("only_acquired_sibling_copies_written") is True
            and safety.get("product_activation_authorized") is False
            and safety.get("retuning_performed") is False
            and isinstance(reconstruction, Mapping)
            and receipt.get("raw_reconstruction") == reconstruction
            and reconstruction.get("summary_reconstruction_pass") is True
        )
        if receipt.get("gate_pass") is not True or receipt.get("outcome") != "green" or not details_green:
            red.append(sequence)
        if receipt.get("series_reset_required") is not (receipt.get("gate_pass") is not True):
            raise SeriesEvidenceError("run reset flag is inconsistent")
    if len(set(run_digests)) != 3 or len(set(acquisitions)) != 3:
        raise SeriesEvidenceError("series reuses a run or acquisition receipt")
    if not all(left < right for left, right in zip(started_times, started_times[1:])):
        raise SeriesEvidenceError("run start timestamps are not strictly increasing")
    if not all(
        completed < next_acquisition
        for completed, next_acquisition in zip(
            completed_times, acquisition_times[1:]
        )
    ):
        raise SeriesEvidenceError(
            "fresh acquisition/run intervals are not strictly consecutive"
        )
    gate = not red
    receipt = _seal_receipt({
        "schema": SERIES_RECEIPT_SCHEMA,
        "outcome": "green" if gate else "reset_required",
        "verified_at_utc": _utc_now(),
        "manifest_sha256": manifest["manifest_sha256"],
        "candidate_commit": manifest["candidate_commit"],
        "runtime_identity_sha256": manifest["runtime_identity_sha256"],
        "candidate_config_sha256": manifest_check["candidate_config_sha256"],
        "batch_events": REQUIRED_BATCH_EVENTS,
        "batch_bytes": REQUIRED_BATCH_BYTES,
        "required_consecutive_runs": 3,
        "run_receipt_sha256": run_digests,
        "acquisition_receipt_sha256": acquisitions,
        "fresh_acquisition_per_run": True,
        "identical_candidate_runtime_config": True,
        "retuning_between_runs": False,
        "red_run_sequences": red,
        "consecutive_green_runs": 3 if gate else 0,
        "series_reset_required": not gate,
        "gate_pass": gate,
        "product_activation_authorized": False,
        "separate_human_live_go_required": True,
        "paths_logged": False,
        "payloads_logged": False,
    })
    assert_receipt_safe(receipt)
    return receipt
