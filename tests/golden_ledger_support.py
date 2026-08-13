"""Test-only support for the A0.2 Golden Ledger candidate.

Every artifact remains **CANDIDATE — PENDING HUMAN REVIEW**.  This module has
no blessing, generation, or update path for the static Oracle.  Runtime code is
only a system under test whose output is compared with the reviewed files.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from genus import anchor, db, event_router


CANDIDATE_NOTICE = "CANDIDATE — PENDING HUMAN REVIEW"
CANDIDATE_STATUS = "candidate_pending_human_review"
BASELINE_COMMIT = "1a102979b3a53d68207a86147005e137e6b0a5db"
FIXTURE_SCHEMA = "genus-golden-ledger-fixture-v1"
EVENT_STREAM_DIGEST_SCHEMA = "genus-golden-ledger-event-stream-digest-v1"
PROJECTION_ROWS_SCHEMA = "genus-golden-ledger-projection-rows-v1"
PROJECTION_DIGEST_SCHEMA = "genus-golden-ledger-projection-digest-v1"
PROJECTION_DIGEST_SET_SCHEMA = "genus-golden-ledger-projection-digest-set-v1"
BUNDLE_DIGEST_SCHEMA = "genus-golden-ledger-bundle-digest-v1"
READ_MODEL_SCHEMA = "genus-golden-ledger-belief-epistemic-read-model-v1"

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "golden_ledger_v1"
ARTIFACT_NAMES = (
    "events.jsonl",
    "manifest.json",
    "oracle.json",
    "import_receipt.json",
    "anchor_v1.json",
    "README.md",
    "ORACLE_REVIEW.md",
)

PROJECTION_TABLES = (
    "response_feedback_log",
    "response_outcome_log",
    "rule_projection",
    "governance_log",
    "operation_log",
    "inquiry_log",
    "proposal_log",
    "experience_log",
    "state_projection",
    "belief_projection",
    "relation_projection",
    "value_projection",
)

JSON_COLUMNS: dict[str, frozenset[str]] = {
    "response_feedback_log": frozenset(),
    "response_outcome_log": frozenset({"readings"}),
    "rule_projection": frozenset({"spec"}),
    "governance_log": frozenset({"policy_results"}),
    "operation_log": frozenset({"payload"}),
    "inquiry_log": frozenset({"payload"}),
    "proposal_log": frozenset({"payload"}),
    "experience_log": frozenset({"pattern", "supporting_events"}),
    "state_projection": frozenset({"supporting_beliefs", "components"}),
    "belief_projection": frozenset({"supporting_events", "contradicting_events"}),
    "relation_projection": frozenset(),
    "value_projection": frozenset(),
}

GOVERNING_DOCUMENTS = [
    "docs/ARCHITECTURE.md",
    "docs/EVENT_CONTRACT.md",
    "docs/QUALITY.md",
    "docs/SECURITY_MODEL.md",
    "docs/decisions/ADR-0006-GOLDEN-LEDGER-ORACLE.md",
    "docs/decisions/ADR-0009-HUMAN-OWNED-CRITICAL-LANE.md",
    "docs/decisions/ADR-0010-HUMAN-SUPERVISED-MODEL-ASSISTANCE-A0.md",
    "docs/decisions/ADR-0011-GOLDEN-LEDGER-CANONICALIZATION-AND-BELIEF-COVERAGE.md",
    "docs/reviews/A0_2_GOLDEN_LEDGER_ENTRY_CONTRACT.md",
    "docs/reviews/A0_2_GOLDEN_LEDGER_ARTIFACT_SCHEMA.md",
]

README_SECTIONS = [
    "Purpose",
    "Artifact Inventory",
    "Corpus Design",
    "Legacy Prefix and Seal Epoch",
    "Oracle Independence",
    "Canonicalization and Digests",
    "Import Receipt",
    "Anchor v1 Boundary",
    "Human Review",
    "Change Procedure",
    "Non-Goals",
]

REVIEW_SECTIONS = [
    "1. Corpus and Privacy",
    "2. Event Contract",
    "3. Legacy Prefix and Genesis Digest",
    "4. Seal Epoch and Tail",
    "5. Projection Oracle",
    "6. Belief Lifecycle and Read-Time Epistemics",
    "7. Canonicalization and Digests",
    "8. Anchor v1 and Negative Cases",
    "9. Final Decision",
]

_EVENT_KEYS = {"id", "event_type", "payload", "created_at", "prev_seal", "seal"}
_EVENT_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class CandidateContractError(AssertionError):
    """A static candidate or its disposable derivative violates the contract."""


@dataclass(frozen=True)
class CandidateBundle:
    root: Path
    events_bytes: bytes
    events: tuple[dict[str, Any], ...]
    manifest_bytes: bytes
    manifest: dict[str, Any]
    oracle_bytes: bytes
    oracle: dict[str, Any]
    receipt_bytes: bytes
    receipt: dict[str, Any]
    anchor_bytes: bytes
    anchor: dict[str, Any]
    readme_bytes: bytes
    review_bytes: bytes


@dataclass(frozen=True)
class ProjectionSnapshot:
    rows: dict[str, list[dict[str, Any]]]
    digests: dict[str, str]
    digest_set_sha256: str


def _fail(message: str) -> None:
    raise CandidateContractError(message)


def _expect(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


def _expect_keys(value: Any, keys: set[str], path: str) -> None:
    _expect(isinstance(value, dict), f"{path} must be an object")
    actual = set(value)
    _expect(actual == keys, f"{path} keys differ: expected {sorted(keys)}, got {sorted(actual)}")


def _expect_hex(value: Any, path: str) -> None:
    _expect(isinstance(value, str) and _HEX64.fullmatch(value) is not None, f"{path} must be lowercase sha256 hex")


def _expect_int(value: Any, path: str, *, minimum: int = 0) -> None:
    _expect(
        isinstance(value, int) and not isinstance(value, bool) and value >= minimum,
        f"{path} must be an integer >= {minimum}",
    )


def _reject_constant(token: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {token}")


def _loads_strict(text: str, path: str) -> Any:
    try:
        return json.loads(text, parse_constant=_reject_constant)
    except (json.JSONDecodeError, ValueError) as exc:
        raise CandidateContractError(f"{path} is not strict JSON: {exc}") from exc


def normalize_json_value(value: Any) -> Any:
    """Return the contract's recursive NFC/finite/-0.0 JSON normalization."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            _fail("non-finite JSON number is forbidden")
        return 0.0 if value == 0.0 else value
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [normalize_json_value(item) for item in value]
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            _expect(isinstance(key, str), "JSON object keys must be strings")
            normalized_key = unicodedata.normalize("NFC", key)
            _expect(normalized_key not in normalized, "NFC normalization collides object keys")
            normalized[normalized_key] = normalize_json_value(item)
        return normalized
    _fail(f"unsupported JSON value type: {type(value).__name__}")


def canonical_json_file_bytes(value: Any) -> bytes:
    normalized = normalize_json_value(value)
    return (
        json.dumps(normalized, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def canonical_anchor_bytes(value: Mapping[str, Any]) -> bytes:
    normalized = normalize_json_value(dict(value))
    return (
        json.dumps(
            normalized,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _canonical_payload_text(payload: Mapping[str, Any], *, ensure_ascii: bool) -> str:
    normalized = normalize_json_value(dict(payload))
    return json.dumps(
        normalized,
        ensure_ascii=ensure_ascii,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_event_line(event: Mapping[str, Any]) -> bytes:
    normalized = normalize_json_value(dict(event))
    return (
        json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_event(event: Any, path: str) -> dict[str, Any]:
    _expect_keys(event, _EVENT_KEYS, path)
    _expect_int(event["id"], f"{path}.id", minimum=1)
    _expect(isinstance(event["event_type"], str) and bool(event["event_type"]), f"{path}.event_type must be non-empty text")
    _expect(isinstance(event["payload"], dict), f"{path}.payload must be an object")
    created_at = event["created_at"]
    _expect(isinstance(created_at, str) and _EVENT_TIMESTAMP.fullmatch(created_at) is not None, f"{path}.created_at has the wrong fixture form")
    try:
        parsed = datetime.fromisoformat(created_at)
    except ValueError as exc:
        raise CandidateContractError(f"{path}.created_at is invalid") from exc
    _expect(parsed.utcoffset() == timezone.utc.utcoffset(parsed), f"{path}.created_at must be UTC")
    for field in ("prev_seal", "seal"):
        value = event[field]
        _expect(value is None or (isinstance(value, str) and _HEX64.fullmatch(value) is not None), f"{path}.{field} must be null or lowercase sha256 hex")
    return event


def _parse_events(raw: bytes) -> tuple[dict[str, Any], ...]:
    _expect(not raw.startswith(b"\xef\xbb\xbf"), "events.jsonl must not have a BOM")
    _expect(b"\r" not in raw, "events.jsonl must use LF line endings")
    _expect(raw.endswith(b"\n"), "events.jsonl must have one final LF")
    _expect(not raw.endswith(b"\n\n"), "events.jsonl must have exactly one final LF")
    body = raw[:-1]
    _expect(bool(body), "events.jsonl must not be empty")
    raw_lines = body.split(b"\n")
    _expect(all(raw_lines), "events.jsonl must not contain blank lines")

    events: list[dict[str, Any]] = []
    for index, raw_line in enumerate(raw_lines, start=1):
        try:
            text = raw_line.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CandidateContractError(f"events.jsonl line {index} is not UTF-8") from exc
        value = _loads_strict(text, f"events.jsonl line {index}")
        event = _validate_event(value, f"events[{index - 1}]")
        _expect(
            canonical_event_line(event) == raw_line + b"\n",
            f"events.jsonl line {index} is not canonical",
        )
        events.append(event)

    ids = [event["id"] for event in events]
    _expect(ids == list(range(1, len(events) + 1)), "fixture event ids must be contiguous from 1 in file order")
    epoch_ids = [event["id"] for event in events if event["event_type"] == "ledger_epoch_opened"]
    _expect(len(epoch_ids) == 1, "fixture must contain exactly one ledger_epoch_opened event")
    epoch_id = epoch_ids[0]
    _expect(epoch_id > 1, "fixture needs a non-empty legacy prefix")
    _expect(epoch_id < len(events), "fixture needs a non-empty sealed tail")
    for event in events:
        if event["id"] < epoch_id:
            _expect(event["prev_seal"] is None and event["seal"] is None, "legacy prefix events must be unsealed")
        else:
            _expect(event["prev_seal"] is not None and event["seal"] is not None, "epoch and tail events must be sealed")
    return tuple(events)


def _load_object(raw: bytes, name: str) -> dict[str, Any]:
    _expect(not raw.startswith(b"\xef\xbb\xbf"), f"{name} must not have a BOM")
    _expect(b"\r" not in raw, f"{name} must use LF line endings")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CandidateContractError(f"{name} is not UTF-8") from exc
    value = _loads_strict(text, name)
    _expect(isinstance(value, dict), f"{name} must contain an object")
    return value


def _validate_markdown_bytes(raw: bytes, name: str) -> str:
    _expect(not raw.startswith(b"\xef\xbb\xbf"), f"{name} must not have a BOM")
    _expect(b"\r" not in raw, f"{name} must use LF line endings")
    _expect(raw.endswith(b"\n"), f"{name} must end with LF")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CandidateContractError(f"{name} is not UTF-8") from exc


def load_candidate(root: Path = FIXTURE_ROOT) -> CandidateBundle:
    root = root.resolve()
    _expect(root.is_dir(), f"candidate directory is missing: {root}")
    entries = {path.name for path in root.iterdir()}
    _expect(entries == set(ARTIFACT_NAMES), f"candidate inventory differs: {sorted(entries)}")
    for name in ARTIFACT_NAMES:
        path = root / name
        _expect(path.is_file() and not path.is_symlink(), f"candidate artifact must be a regular file: {name}")

    raw = {name: (root / name).read_bytes() for name in ARTIFACT_NAMES}
    events = _parse_events(raw["events.jsonl"])
    manifest = _load_object(raw["manifest.json"], "manifest.json")
    oracle = _load_object(raw["oracle.json"], "oracle.json")
    receipt = _load_object(raw["import_receipt.json"], "import_receipt.json")
    anchor_value = _load_object(raw["anchor_v1.json"], "anchor_v1.json")

    _expect(raw["manifest.json"] == canonical_json_file_bytes(manifest), "manifest.json bytes are not canonical")
    _expect(raw["oracle.json"] == canonical_json_file_bytes(oracle), "oracle.json bytes are not canonical")
    _expect(raw["import_receipt.json"] == canonical_json_file_bytes(receipt), "import_receipt.json bytes are not canonical")
    _expect(raw["anchor_v1.json"] == canonical_anchor_bytes(anchor_value), "anchor_v1.json bytes are not canonical")
    _validate_markdown_bytes(raw["README.md"], "README.md")
    _validate_markdown_bytes(raw["ORACLE_REVIEW.md"], "ORACLE_REVIEW.md")

    return CandidateBundle(
        root=root,
        events_bytes=raw["events.jsonl"],
        events=events,
        manifest_bytes=raw["manifest.json"],
        manifest=manifest,
        oracle_bytes=raw["oracle.json"],
        oracle=oracle,
        receipt_bytes=raw["import_receipt.json"],
        receipt=receipt,
        anchor_bytes=raw["anchor_v1.json"],
        anchor=anchor_value,
        readme_bytes=raw["README.md"],
        review_bytes=raw["ORACLE_REVIEW.md"],
    )


def event_stream_records_from_fixture(events: tuple[dict[str, Any], ...] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "created_at": event["created_at"],
            "event_type": event["event_type"],
            "id": int(event["id"]),
            "payload_text": _canonical_payload_text(event["payload"], ensure_ascii=True),
            "prev_seal": event["prev_seal"],
            "seal": event["seal"],
        }
        for event in sorted(events, key=lambda item: int(item["id"]))
    ]


def event_stream_records_from_db(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    records = []
    rows = conn.execute(
        "SELECT id, event_type, payload, created_at, prev_seal, seal FROM event_log ORDER BY id"
    ).fetchall()
    for row in rows:
        payload = _loads_strict(row["payload"], f"event_log[{row['id']}].payload")
        _expect(isinstance(payload, dict), f"event_log[{row['id']}].payload must be an object")
        expected_storage = _canonical_payload_text(payload, ensure_ascii=False)
        _expect(row["payload"] == expected_storage, f"event_log[{row['id']}].payload is not canonical")
        records.append(
            {
                "created_at": row["created_at"],
                "event_type": row["event_type"],
                "id": int(row["id"]),
                "payload_text": _canonical_payload_text(payload, ensure_ascii=True),
                "prev_seal": row["prev_seal"],
                "seal": row["seal"],
            }
        )
    return records


def event_stream_sha256(records: list[dict[str, Any]]) -> str:
    ordered = sorted(records, key=lambda item: int(item["id"]))
    encoded = json.dumps(
        normalize_json_value(ordered),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256_hex(encoded)


def projection_rows_sha256(rows: list[dict[str, Any]]) -> str:
    encoded = json.dumps(
        normalize_json_value(rows),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256_hex(encoded)


def projection_digest_set_sha256(digests: Mapping[str, str]) -> str:
    _expect(set(digests) == set(PROJECTION_TABLES), "projection digest set must name exactly twelve tables")
    for table, digest in digests.items():
        _expect_hex(digest, f"projection digests.{table}")
    encoded = json.dumps(
        dict(digests),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_hex(encoded)


def bundle_sha256(components: Mapping[str, Any]) -> str:
    expected_keys = {
        "anchor_v1_sha256",
        "event_stream_sha256",
        "fixture_schema_version",
        "fixture_sha256",
        "manifest_sha256",
        "oracle_sha256",
        "projection_digest_set_sha256",
    }
    _expect_keys(components, expected_keys, "bundle digest input")
    encoded = json.dumps(
        normalize_json_value(dict(components)),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256_hex(encoded)


def _projection_sort_component(value: Any) -> tuple[int, Any]:
    if value is None:
        return (0, "")
    if isinstance(value, bool):
        return (1, int(value))
    if isinstance(value, int):
        return (2, value)
    if isinstance(value, float):
        return (3, value)
    if isinstance(value, str):
        return (4, value)
    return (
        5,
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    )


def _projection_sort_key(row: Mapping[str, Any], sort_by: list[str]) -> tuple[tuple[int, Any], ...]:
    return tuple(_projection_sort_component(row[column]) for column in sort_by)


def _normalize_projection_value(table: str, column: str, value: Any) -> Any:
    if isinstance(value, (bytes, bytearray, memoryview)):
        _fail(f"SQLite BLOB is forbidden in {table}.{column}")
    if column in JSON_COLUMNS[table]:
        _expect(isinstance(value, str), f"{table}.{column} must contain JSON text")
        parsed = _loads_strict(value, f"{table}.{column}")
        return json.dumps(
            normalize_json_value(parsed),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    return normalize_json_value(value)


def _validate_projection_spec(table: str, spec: Any) -> None:
    _expect_keys(spec, {"columns", "sort_by", "rows", "sha256"}, f"oracle.expected_projections.{table}")
    columns = spec["columns"]
    sort_by = spec["sort_by"]
    rows = spec["rows"]
    _expect(isinstance(columns, list) and columns and all(isinstance(item, str) for item in columns), f"{table}.columns must be non-empty text list")
    _expect(len(columns) == len(set(columns)), f"{table}.columns must be unique")
    _expect(isinstance(sort_by, list) and sort_by and all(isinstance(item, str) for item in sort_by), f"{table}.sort_by must be non-empty text list")
    _expect(len(sort_by) == len(set(sort_by)), f"{table}.sort_by must be unique")
    _expect(set(sort_by) <= set(columns), f"{table}.sort_by must be a subset of columns")
    _expect(isinstance(rows, list), f"{table}.rows must be a list")

    normalized_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        _expect_keys(row, set(columns), f"{table}.rows[{index}]")
        normalized = {
            column: _normalize_projection_value(table, column, row[column])
            for column in columns
        }
        _expect(normalized == row, f"{table}.rows[{index}] is not normalized")
        normalized_rows.append(normalized)
    ordered = sorted(normalized_rows, key=lambda row: _projection_sort_key(row, sort_by))
    _expect(ordered == normalized_rows, f"{table}.rows are not sorted by sort_by")
    keys = [_projection_sort_key(row, sort_by) for row in normalized_rows]
    _expect(len(keys) == len(set(keys)), f"{table}.sort_by is not a unique total key")
    _expect_hex(spec["sha256"], f"{table}.sha256")
    _expect(projection_rows_sha256(rows) == spec["sha256"], f"{table}.sha256 does not bind static rows")


def _assert_manifest_schema(manifest: dict[str, Any]) -> None:
    _expect_keys(
        manifest,
        {"schema", "format_version", "status", "fixture_schema_version", "canonicalization", "files", "counts", "epoch", "head", "digests"},
        "manifest",
    )
    _expect(manifest["schema"] == "genus-golden-ledger-manifest-v1", "manifest schema differs")
    _expect(manifest["format_version"] == 1, "manifest format_version differs")
    _expect(manifest["status"] == CANDIDATE_STATUS, "manifest candidate status differs")
    _expect(manifest["fixture_schema_version"] == FIXTURE_SCHEMA, "manifest fixture schema differs")
    _expect_keys(manifest["canonicalization"], {"event_stream_digest_schema", "projection_digest_schema", "projection_digest_set_schema", "bundle_digest_schema"}, "manifest.canonicalization")
    _expect(
        manifest["canonicalization"]
        == {
            "event_stream_digest_schema": EVENT_STREAM_DIGEST_SCHEMA,
            "projection_digest_schema": PROJECTION_DIGEST_SCHEMA,
            "projection_digest_set_schema": PROJECTION_DIGEST_SET_SCHEMA,
            "bundle_digest_schema": BUNDLE_DIGEST_SCHEMA,
        },
        "manifest canonicalization values differ",
    )
    _expect_keys(manifest["files"], {"events", "oracle", "import_receipt", "anchor_v1", "readme", "human_review"}, "manifest.files")
    _expect(
        manifest["files"]
        == {
            "events": "events.jsonl",
            "oracle": "oracle.json",
            "import_receipt": "import_receipt.json",
            "anchor_v1": "anchor_v1.json",
            "readme": "README.md",
            "human_review": "ORACLE_REVIEW.md",
        },
        "manifest filenames differ",
    )
    _expect_keys(manifest["counts"], {"event_count", "legacy_prefix_event_count", "sealed_tail_event_count", "projection_target_count"}, "manifest.counts")
    for field in ("event_count", "legacy_prefix_event_count", "sealed_tail_event_count", "projection_target_count"):
        _expect_int(manifest["counts"][field], f"manifest.counts.{field}")
    _expect(manifest["counts"]["projection_target_count"] == 12, "manifest projection target count must be 12")
    _expect(manifest["counts"]["event_count"] == manifest["counts"]["legacy_prefix_event_count"] + 1 + manifest["counts"]["sealed_tail_event_count"], "manifest event count decomposition differs")
    _expect_keys(manifest["epoch"], {"event_id", "prefix_count", "prefix_max_id", "genesis_digest", "algo"}, "manifest.epoch")
    for field in ("event_id", "prefix_count", "prefix_max_id"):
        _expect_int(manifest["epoch"][field], f"manifest.epoch.{field}")
    _expect_hex(manifest["epoch"]["genesis_digest"], "manifest.epoch.genesis_digest")
    _expect(manifest["epoch"]["algo"] == "sha256-chain-v1", "manifest epoch algo differs")
    _expect_keys(manifest["head"], {"event_id", "event_type", "created_at", "seal"}, "manifest.head")
    _expect_int(manifest["head"]["event_id"], "manifest.head.event_id", minimum=1)
    _expect_hex(manifest["head"]["seal"], "manifest.head.seal")
    _expect_keys(manifest["digests"], {"fixture_sha256", "event_stream_sha256", "oracle_sha256", "anchor_v1_sha256", "projection_digest_set_sha256"}, "manifest.digests")
    for field, value in manifest["digests"].items():
        _expect_hex(value, f"manifest.digests.{field}")


def _assert_oracle_schema(oracle: dict[str, Any]) -> None:
    _expect_keys(
        oracle,
        {"schema", "format_version", "status", "fixture_schema_version", "provenance", "source_bindings", "canonicalization", "expected", "expected_projections", "expected_read_models", "expected_anchor_v1", "projection_digest_set_sha256"},
        "oracle",
    )
    _expect(oracle["schema"] == "genus-golden-ledger-replay-oracle-v1", "oracle schema differs")
    _expect(oracle["format_version"] == 1, "oracle format_version differs")
    _expect(oracle["status"] == CANDIDATE_STATUS, "oracle candidate status differs")
    _expect(oracle["fixture_schema_version"] == FIXTURE_SCHEMA, "oracle fixture schema differs")

    provenance = oracle["provenance"]
    _expect_keys(provenance, {"repository", "baseline_commit", "derivation", "governing_documents", "roles"}, "oracle.provenance")
    _expect(provenance["repository"] == "WoltLab51/GENUS_PI_SEED", "oracle provenance repository differs")
    _expect(provenance["baseline_commit"] == BASELINE_COMMIT, "oracle baseline commit differs from captured clean baseline")
    _expect(provenance["derivation"] == "a0_2:human_supervised_golden_ledger_candidate:v1", "oracle derivation differs")
    _expect(provenance["governing_documents"] == GOVERNING_DOCUMENTS, "oracle governing document order differs")
    _expect_keys(provenance["roles"], {"canonicalization_digest_contract_owner", "corpus_owner", "human_implementer_committer", "non_authoritative_model_assistant", "oracle_reviewer", "privacy_reviewer"}, "oracle.provenance.roles")
    _expect(
        provenance["roles"]
        == {
            "canonicalization_digest_contract_owner": "Ronny",
            "corpus_owner": "Ronny",
            "human_implementer_committer": "Ronny",
            "non_authoritative_model_assistant": "Codex",
            "oracle_reviewer": "Ronny",
            "privacy_reviewer": "Ronny",
        },
        "oracle provenance roles differ",
    )

    _expect_keys(oracle["source_bindings"], {"events_file", "fixture_sha256", "event_stream_digest_schema", "event_stream_sha256"}, "oracle.source_bindings")
    _expect(oracle["source_bindings"]["events_file"] == "events.jsonl", "oracle events filename differs")
    _expect(oracle["source_bindings"]["event_stream_digest_schema"] == EVENT_STREAM_DIGEST_SCHEMA, "oracle event-stream schema differs")
    _expect_hex(oracle["source_bindings"]["fixture_sha256"], "oracle source fixture digest")
    _expect_hex(oracle["source_bindings"]["event_stream_sha256"], "oracle source event-stream digest")

    _expect_keys(oracle["canonicalization"], {"projection_rows_schema", "projection_digest_schema", "projection_digest_set_schema", "read_model_schema"}, "oracle.canonicalization")
    _expect(
        oracle["canonicalization"]
        == {
            "projection_rows_schema": PROJECTION_ROWS_SCHEMA,
            "projection_digest_schema": PROJECTION_DIGEST_SCHEMA,
            "projection_digest_set_schema": PROJECTION_DIGEST_SET_SCHEMA,
            "read_model_schema": READ_MODEL_SCHEMA,
        },
        "oracle canonicalization values differ",
    )

    expected = oracle["expected"]
    _expect_keys(expected, {"event_count", "legacy_prefix", "epoch", "head", "integrity"}, "oracle.expected")
    _expect_int(expected["event_count"], "oracle.expected.event_count")
    _expect_keys(expected["legacy_prefix"], {"event_count", "max_event_id", "genesis_digest"}, "oracle.expected.legacy_prefix")
    _expect_int(expected["legacy_prefix"]["event_count"], "oracle expected legacy count")
    _expect_int(expected["legacy_prefix"]["max_event_id"], "oracle expected legacy max id")
    _expect_hex(expected["legacy_prefix"]["genesis_digest"], "oracle expected genesis digest")
    _expect_keys(expected["epoch"], {"event_id", "algo"}, "oracle.expected.epoch")
    _expect_int(expected["epoch"]["event_id"], "oracle expected epoch id", minimum=1)
    _expect(expected["epoch"]["algo"] == "sha256-chain-v1", "oracle expected epoch algo differs")
    _expect_keys(expected["head"], {"event_id", "event_type", "created_at", "seal"}, "oracle.expected.head")
    _expect_int(expected["head"]["event_id"], "oracle expected head id", minimum=1)
    _expect_hex(expected["head"]["seal"], "oracle expected head seal")
    _expect_keys(expected["integrity"], {"ok", "issues"}, "oracle.expected.integrity")
    _expect(expected["integrity"] == {"ok": True, "issues": []}, "valid oracle integrity result differs")

    projections = oracle["expected_projections"]
    _expect_keys(projections, set(PROJECTION_TABLES), "oracle.expected_projections")
    for table in PROJECTION_TABLES:
        _validate_projection_spec(table, projections[table])
    digest_map = {table: projections[table]["sha256"] for table in PROJECTION_TABLES}
    _expect_hex(oracle["projection_digest_set_sha256"], "oracle projection digest set")
    _expect(projection_digest_set_sha256(digest_map) == oracle["projection_digest_set_sha256"], "oracle projection digest set does not bind static row digests")

    _expect_keys(oracle["expected_read_models"], {"belief_epistemic_state_v1"}, "oracle.expected_read_models")
    model = oracle["expected_read_models"]["belief_epistemic_state_v1"]
    _expect_keys(model, {"as_of", "halflife_seconds", "cases"}, "oracle expected belief read model")
    _expect(model["as_of"] == "2026-01-01T00:00:00.000Z", "belief read-model as_of differs")
    _expect(
        type(model["halflife_seconds"]) is float
        and model["halflife_seconds"] == 3600.0,
        "belief read-model half-life must be the exact JSON number 3600.0",
    )
    _expect(isinstance(model["cases"], list), "belief read-model cases must be a list")
    seen_states: set[str] = set()
    seen_beliefs: set[int] = set()
    for index, case in enumerate(model["cases"]):
        _expect_keys(case, {"belief_id", "supporting_event_ids", "contradicting_event_ids", "expected_confidence", "expected_epistemic_state"}, f"belief read-model case {index}")
        _expect_int(case["belief_id"], f"belief read-model case {index}.belief_id", minimum=1)
        _expect(case["belief_id"] not in seen_beliefs, "belief read-model belief ids must be unique")
        seen_beliefs.add(case["belief_id"])
        _expect(isinstance(case["supporting_event_ids"], list) and all(isinstance(item, int) and not isinstance(item, bool) for item in case["supporting_event_ids"]), "supporting event ids must be integers")
        _expect(isinstance(case["contradicting_event_ids"], list) and all(isinstance(item, int) and not isinstance(item, bool) for item in case["contradicting_event_ids"]), "contradicting event ids must be integers")
        state = case["expected_epistemic_state"]
        seen_states.add(state)
        if state == "supported":
            _expect(len(case["supporting_event_ids"]) == 2 and len(case["contradicting_event_ids"]) == 0 and case["expected_confidence"] == 0.667, "supported read-model case differs")
        elif state == "contested":
            _expect(len(case["supporting_event_ids"]) == 1 and len(case["contradicting_event_ids"]) == 2 and case["expected_confidence"] == 0.250, "contested read-model case differs")
        else:
            _fail(f"unsupported Golden read-model state: {state}")
    _expect(seen_states == {"supported", "contested"}, "read model must cover supported and contested")

    anchor_expected = oracle["expected_anchor_v1"]
    _expect_keys(anchor_expected, {"artifact_file", "verification_core_id", "cases"}, "oracle.expected_anchor_v1")
    _expect(anchor_expected["artifact_file"] == "anchor_v1.json", "expected anchor filename differs")
    _expect(anchor_expected["verification_core_id"] == "golden-ledger-v1", "expected anchor core id differs")
    _expect_keys(anchor_expected["cases"], {"historical_head_with_later_tail", "wrong_head_event_id", "wrong_head_seal", "wrong_core_id"}, "oracle.expected_anchor_v1.cases")
    _expect(
        anchor_expected["cases"]
        == {
            "historical_head_with_later_tail": {"accepted": True},
            "wrong_head_event_id": {"accepted": False},
            "wrong_head_seal": {"accepted": False},
            "wrong_core_id": {"accepted": False},
        },
        "expected anchor case results differ",
    )


def _assert_receipt_schema(receipt: dict[str, Any]) -> None:
    _expect_keys(receipt, {"schema", "format_version", "status", "fixture_schema_version", "event_stream_digest_schema", "source_files", "counts", "digests", "bundle_digest_schema", "bundle_sha256"}, "import receipt")
    _expect(receipt["schema"] == "genus-golden-ledger-import-receipt-v1", "receipt schema differs")
    _expect(receipt["format_version"] == 1, "receipt format_version differs")
    _expect(receipt["status"] == CANDIDATE_STATUS, "receipt candidate status differs")
    _expect(receipt["fixture_schema_version"] == FIXTURE_SCHEMA, "receipt fixture schema differs")
    _expect(receipt["event_stream_digest_schema"] == EVENT_STREAM_DIGEST_SCHEMA, "receipt event-stream schema differs")
    _expect(receipt["bundle_digest_schema"] == BUNDLE_DIGEST_SCHEMA, "receipt bundle schema differs")
    _expect_keys(receipt["source_files"], {"events", "manifest", "oracle", "anchor_v1"}, "receipt.source_files")
    _expect(receipt["source_files"] == {"events": "events.jsonl", "manifest": "manifest.json", "oracle": "oracle.json", "anchor_v1": "anchor_v1.json"}, "receipt source filenames differ")
    _expect_keys(receipt["counts"], {"expected_event_count", "imported_event_count"}, "receipt.counts")
    _expect_int(receipt["counts"]["expected_event_count"], "receipt expected event count")
    _expect_int(receipt["counts"]["imported_event_count"], "receipt imported event count")
    _expect_keys(receipt["digests"], {"fixture_sha256", "event_stream_sha256", "manifest_sha256", "oracle_sha256", "anchor_v1_sha256", "projection_digest_set_sha256"}, "receipt.digests")
    for field, value in receipt["digests"].items():
        _expect_hex(value, f"receipt.digests.{field}")
    _expect_hex(receipt["bundle_sha256"], "receipt.bundle_sha256")


def _assert_anchor_schema(artifact: dict[str, Any]) -> None:
    _expect_keys(artifact, {"algo", "core_id", "created_at", "derivation", "epoch_event_id", "event_count", "head", "head_created_at", "head_event_id", "head_event_type", "schema", "signature"}, "anchor")
    _expect(artifact["schema"] == "genus-ledger-anchor-v1", "anchor schema differs")
    _expect(artifact["algo"] == "sha256-chain-v1", "anchor algo differs")
    _expect(artifact["core_id"] == "golden-ledger-v1", "anchor core id differs")
    _expect(artifact["derivation"] == "ledger_anchor:v1", "anchor derivation differs")
    _expect(artifact["signature"] is None, "anchor signature must be null")
    for field in ("epoch_event_id", "event_count", "head_event_id"):
        _expect_int(artifact[field], f"anchor.{field}")
    _expect_hex(artifact["head"], "anchor.head")
    _expect(anchor.validate_anchor(artifact) == [], "runtime anchor validation rejects static artifact")


def _assert_markdown_contract(bundle: CandidateBundle) -> None:
    readme = bundle.readme_bytes.decode("utf-8")
    readme_lines = readme.splitlines()
    _expect(readme_lines[:2] == ["# Golden Ledger v1", f"> Status: {CANDIDATE_NOTICE}"], "README heading/status differs")
    readme_sections = [line[3:] for line in readme_lines if line.startswith("## ")]
    _expect(readme_sections == README_SECTIONS, "README section order differs")

    review = bundle.review_bytes.decode("utf-8")
    review_lines = review.splitlines()
    _expect(
        review_lines[:5]
        == [
            "# A0.2 Golden Ledger Oracle Review",
            f"> Status: {CANDIDATE_NOTICE}",
            "> Reviewer: Ronny",
            "> Review date:",
            "> Baseline commit:",
        ],
        "ORACLE_REVIEW heading block differs",
    )
    review_sections = [line[3:] for line in review_lines if line.startswith("## ")]
    _expect(review_sections == REVIEW_SECTIONS, "ORACLE_REVIEW section order differs")
    checkbox_marks = re.findall(r"^- \[([^\]])\]", review, flags=re.MULTILINE)
    _expect(len(checkbox_marks) == 35, "ORACLE_REVIEW must contain exactly 35 review checkboxes")
    _expect(
        all(mark == " " for mark in checkbox_marks),
        "all 35 ORACLE_REVIEW checkboxes must remain open",
    )
    _expect(
        review_lines[-3:]
        == [
            "- [ ] Accept candidate",
            "- [ ] Reject candidate",
            "- [ ] Request changes",
        ],
        "ORACLE_REVIEW must end with exactly the three open decisions",
    )


def assert_artifact_schemas(bundle: CandidateBundle) -> None:
    """Validate every static schema, byte form, digest and cross-binding."""
    _assert_manifest_schema(bundle.manifest)
    _assert_oracle_schema(bundle.oracle)
    _assert_receipt_schema(bundle.receipt)
    _assert_anchor_schema(bundle.anchor)
    _assert_markdown_contract(bundle)

    manifest = bundle.manifest
    oracle = bundle.oracle
    receipt = bundle.receipt
    events = list(bundle.events)
    fixture_digest = sha256_hex(bundle.events_bytes)
    stream_digest = event_stream_sha256(event_stream_records_from_fixture(events))
    oracle_digest = sha256_hex(bundle.oracle_bytes)
    manifest_digest = sha256_hex(bundle.manifest_bytes)
    anchor_digest = sha256_hex(bundle.anchor_bytes)
    projection_set = oracle["projection_digest_set_sha256"]

    _expect(manifest["digests"]["fixture_sha256"] == fixture_digest, "manifest fixture digest differs")
    _expect(oracle["source_bindings"]["fixture_sha256"] == fixture_digest, "oracle fixture digest differs")
    _expect(receipt["digests"]["fixture_sha256"] == fixture_digest, "receipt fixture digest differs")
    _expect(manifest["digests"]["event_stream_sha256"] == stream_digest, "manifest event-stream digest differs")
    _expect(oracle["source_bindings"]["event_stream_sha256"] == stream_digest, "oracle event-stream digest differs")
    _expect(receipt["digests"]["event_stream_sha256"] == stream_digest, "receipt event-stream digest differs")
    _expect(manifest["digests"]["oracle_sha256"] == oracle_digest, "manifest oracle digest differs")
    _expect(receipt["digests"]["oracle_sha256"] == oracle_digest, "receipt oracle digest differs")
    _expect(manifest["digests"]["anchor_v1_sha256"] == anchor_digest, "manifest anchor digest differs")
    _expect(receipt["digests"]["anchor_v1_sha256"] == anchor_digest, "receipt anchor digest differs")
    _expect(receipt["digests"]["manifest_sha256"] == manifest_digest, "receipt manifest digest differs")
    _expect(manifest["digests"]["projection_digest_set_sha256"] == projection_set, "manifest projection digest set differs")
    _expect(receipt["digests"]["projection_digest_set_sha256"] == projection_set, "receipt projection digest set differs")

    event_count = len(events)
    epoch_event = next(event for event in events if event["event_type"] == "ledger_epoch_opened")
    epoch_id = epoch_event["id"]
    epoch_payload = epoch_event["payload"]
    head_event = events[-1]
    _expect(manifest["counts"]["event_count"] == event_count, "manifest event count differs from fixture")
    _expect(manifest["counts"]["legacy_prefix_event_count"] == epoch_id - 1, "manifest legacy count differs")
    _expect(manifest["counts"]["sealed_tail_event_count"] == event_count - epoch_id, "manifest tail count differs")
    _expect(manifest["epoch"] == {"event_id": epoch_id, "prefix_count": epoch_payload["prefix_count"], "prefix_max_id": epoch_payload["prefix_max_id"], "genesis_digest": epoch_payload["genesis_digest"], "algo": epoch_payload["algo"]}, "manifest epoch differs from fixture")
    expected_head = {"event_id": head_event["id"], "event_type": head_event["event_type"], "created_at": head_event["created_at"], "seal": head_event["seal"]}
    _expect(manifest["head"] == expected_head, "manifest head differs from fixture")
    _expect(oracle["expected"]["head"] == expected_head, "oracle head differs from fixture")
    _expect(oracle["expected"]["event_count"] == event_count, "oracle event count differs")
    _expect(receipt["counts"] == {"expected_event_count": event_count, "imported_event_count": event_count}, "static receipt counts differ")
    _expect(manifest["epoch"]["prefix_count"] == manifest["counts"]["legacy_prefix_event_count"], "manifest prefix counts differ")
    _expect(manifest["epoch"]["prefix_max_id"] == epoch_id - 1, "manifest prefix max id differs")
    _expect(oracle["expected"]["legacy_prefix"] == {"event_count": epoch_id - 1, "max_event_id": epoch_id - 1, "genesis_digest": epoch_payload["genesis_digest"]}, "oracle legacy prefix differs")
    _expect(oracle["expected"]["epoch"] == {"event_id": epoch_id, "algo": epoch_payload["algo"]}, "oracle epoch differs")

    anchor_artifact = bundle.anchor
    _expect(anchor_artifact["epoch_event_id"] == epoch_id, "anchor epoch id differs")
    anchored = [event for event in events if event["id"] == anchor_artifact["head_event_id"]]
    _expect(len(anchored) == 1, "anchor historical head is absent")
    anchored_head = anchored[0]
    _expect(anchor_artifact["head_event_id"] < head_event["id"], "anchor must have a later fixture tail")
    _expect(anchor_artifact["event_count"] == len([event for event in events if event["id"] <= anchor_artifact["head_event_id"]]), "anchor event_count differs from historical boundary")
    _expect(anchor_artifact["head_event_type"] == anchored_head["event_type"], "anchor head type differs")
    _expect(anchor_artifact["head_created_at"] == anchored_head["created_at"], "anchor head time differs")
    _expect(anchor_artifact["head"] == anchored_head["seal"], "anchor head seal differs")
    _expect(anchor_artifact["head_event_id"] == 41, "anchor must bind historical head event 41")
    _expect(head_event["id"] == 42, "fixture must retain event 42 as the later anchor tail")
    anchor_created = datetime.fromisoformat(anchor_artifact["created_at"].replace("Z", "+00:00"))
    head_created = datetime.fromisoformat(anchor_artifact["head_created_at"].replace("Z", "+00:00"))
    later_tail_created = datetime.fromisoformat(head_event["created_at"].replace("Z", "+00:00"))
    _expect(
        head_created < anchor_created < later_tail_created,
        "anchor created_at must be strictly between historical head 41 and later tail 42",
    )

    bundle_components = {
        "anchor_v1_sha256": anchor_digest,
        "event_stream_sha256": stream_digest,
        "fixture_schema_version": FIXTURE_SCHEMA,
        "fixture_sha256": fixture_digest,
        "manifest_sha256": manifest_digest,
        "oracle_sha256": oracle_digest,
        "projection_digest_set_sha256": projection_set,
    }
    _expect(bundle_sha256(bundle_components) == receipt["bundle_sha256"], "static receipt bundle digest differs")


def bundle_bytes_snapshot(bundle: CandidateBundle) -> dict[str, bytes]:
    return {name: (bundle.root / name).read_bytes() for name in ARTIFACT_NAMES}


def assert_bundle_unchanged(bundle: CandidateBundle, before: Mapping[str, bytes]) -> None:
    entries = {path.name for path in bundle.root.iterdir()}
    _expect(entries == set(ARTIFACT_NAMES), "candidate inventory changed during the test")
    after = {name: (bundle.root / name).read_bytes() for name in ARTIFACT_NAMES}
    _expect(after == dict(before), "candidate bytes changed during the test")


def import_fixture(tmp_path: Path, bundle: CandidateBundle) -> sqlite3.Connection:
    """Directly import static historical rows into a fresh Current-Schema DB."""
    tmp_root = tmp_path.resolve()
    tmp_root.mkdir(parents=True, exist_ok=True)
    database_path = (tmp_root / "golden-ledger-v1.sqlite3").resolve()
    _expect(database_path.parent == tmp_root, "temporary database escaped tmp_path")
    _expect(not database_path.exists(), "temporary database must start absent")
    conn = db.connect(database_path)
    try:
        conn.executemany(
            """
            INSERT INTO event_log
                (id, event_type, payload, created_at, prev_seal, seal)
            VALUES
                (:id, :event_type, :payload, :created_at, :prev_seal, :seal)
            """,
            [
                {
                    "id": event["id"],
                    "event_type": event["event_type"],
                    "payload": _canonical_payload_text(event["payload"], ensure_ascii=False),
                    "created_at": event["created_at"],
                    "prev_seal": event["prev_seal"],
                    "seal": event["seal"],
                }
                for event in bundle.events
            ],
        )
        conn.commit()
        _expect(event_stream_records_from_db(conn) == event_stream_records_from_fixture(bundle.events), "direct import changed the semantic event stream")
        return conn
    except Exception:
        conn.close()
        raise


def _quote_identifier(value: str) -> str:
    _expect(_IDENTIFIER.fullmatch(value) is not None, f"unsafe SQLite identifier: {value}")
    return f'"{value}"'


def projection_snapshot(conn: sqlite3.Connection, oracle: Mapping[str, Any]) -> ProjectionSnapshot:
    expected = oracle["expected_projections"]
    _expect(set(expected) == set(PROJECTION_TABLES), "oracle projection names differ from contract")
    _expect(set(event_router.REPLAY_PROJEKTIONSTABELLEN) == set(PROJECTION_TABLES), "runtime replay target names drifted")
    router_targets = set().union(*event_router.PROJEKTIONSZIELE.values())
    _expect(router_targets == set(PROJECTION_TABLES), "runtime projector target names drifted")
    _expect(set(JSON_COLUMNS) == set(PROJECTION_TABLES), "JSON column map is incomplete")

    all_rows: dict[str, list[dict[str, Any]]] = {}
    digests: dict[str, str] = {}
    for table in PROJECTION_TABLES:
        spec = expected[table]
        columns = list(spec["columns"])
        sort_by = list(spec["sort_by"])
        actual_columns = [
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({_quote_identifier(table)})").fetchall()
        ]
        _expect(set(actual_columns) == set(columns) and len(actual_columns) == len(columns), f"{table} schema differs from oracle columns")
        selected = ", ".join(_quote_identifier(column) for column in columns)
        raw_rows = conn.execute(f"SELECT {selected} FROM {_quote_identifier(table)}").fetchall()
        normalized_rows = [
            {
                column: _normalize_projection_value(table, column, row[column])
                for column in columns
            }
            for row in raw_rows
        ]
        normalized_rows.sort(key=lambda row: _projection_sort_key(row, sort_by))
        keys = [_projection_sort_key(row, sort_by) for row in normalized_rows]
        _expect(len(keys) == len(set(keys)), f"{table}.sort_by is not unique for runtime rows")
        all_rows[table] = normalized_rows
        digests[table] = projection_rows_sha256(normalized_rows)
    return ProjectionSnapshot(
        rows=all_rows,
        digests=digests,
        digest_set_sha256=projection_digest_set_sha256(digests),
    )


def assert_snapshot_matches_oracle(snapshot: ProjectionSnapshot, oracle: Mapping[str, Any]) -> None:
    expected = oracle["expected_projections"]
    for table in PROJECTION_TABLES:
        _expect(snapshot.rows[table] == expected[table]["rows"], f"runtime rows differ from static oracle for {table}")
        _expect(snapshot.digests[table] == expected[table]["sha256"], f"runtime digest differs from static oracle for {table}")
    _expect(snapshot.digest_set_sha256 == oracle["projection_digest_set_sha256"], "runtime projection digest set differs from static oracle")


def compute_actual_receipt(
    bundle: CandidateBundle,
    conn: sqlite3.Connection,
    snapshot: ProjectionSnapshot,
) -> dict[str, Any]:
    """Build an independent in-memory receipt; never read expected receipt values."""
    source_stream = event_stream_sha256(event_stream_records_from_fixture(bundle.events))
    imported_stream = event_stream_sha256(event_stream_records_from_db(conn))
    _expect(source_stream == imported_stream, "source and imported event streams differ")
    imported_count = int(conn.execute("SELECT COUNT(*) AS count FROM event_log").fetchone()["count"])
    digests = {
        "fixture_sha256": sha256_hex(bundle.events_bytes),
        "event_stream_sha256": imported_stream,
        "manifest_sha256": sha256_hex(bundle.manifest_bytes),
        "oracle_sha256": sha256_hex(bundle.oracle_bytes),
        "anchor_v1_sha256": sha256_hex(bundle.anchor_bytes),
        "projection_digest_set_sha256": snapshot.digest_set_sha256,
    }
    components = {
        "anchor_v1_sha256": digests["anchor_v1_sha256"],
        "event_stream_sha256": digests["event_stream_sha256"],
        "fixture_schema_version": FIXTURE_SCHEMA,
        "fixture_sha256": digests["fixture_sha256"],
        "manifest_sha256": digests["manifest_sha256"],
        "oracle_sha256": digests["oracle_sha256"],
        "projection_digest_set_sha256": digests["projection_digest_set_sha256"],
    }
    return {
        "schema": "genus-golden-ledger-import-receipt-v1",
        "format_version": 1,
        "status": CANDIDATE_STATUS,
        "fixture_schema_version": FIXTURE_SCHEMA,
        "event_stream_digest_schema": EVENT_STREAM_DIGEST_SCHEMA,
        "source_files": {
            "events": "events.jsonl",
            "manifest": "manifest.json",
            "oracle": "oracle.json",
            "anchor_v1": "anchor_v1.json",
        },
        "counts": {
            "expected_event_count": bundle.manifest["counts"]["event_count"],
            "imported_event_count": imported_count,
        },
        "digests": digests,
        "bundle_digest_schema": BUNDLE_DIGEST_SCHEMA,
        "bundle_sha256": bundle_sha256(components),
    }


def database_file(conn: sqlite3.Connection) -> Path:
    row = conn.execute("SELECT file FROM pragma_database_list WHERE name = 'main'").fetchone()
    _expect(row is not None and bool(row["file"]), "disposable test DB must be file-backed")
    return Path(row["file"]).resolve()


def drop_append_only_guards(
    conn: sqlite3.Connection,
    *,
    tmp_root: Path,
) -> None:
    """Unlock only a proven disposable DB for negative tamper tests."""
    resolved_root = tmp_root.resolve()
    path = database_file(conn)
    try:
        path.relative_to(resolved_root)
    except ValueError as exc:
        raise CandidateContractError(f"refusing to unlock non-temporary DB: {path}") from exc
    conn.execute("DROP TRIGGER prevent_event_log_update")
    conn.execute("DROP TRIGGER prevent_event_log_delete")


def anchor_case_results(conn: sqlite3.Connection, artifact: Mapping[str, Any]) -> dict[str, dict[str, bool]]:
    candidate = dict(artifact)
    max_id = int(conn.execute("SELECT MAX(id) AS id FROM event_log").fetchone()["id"])
    _expect(max_id > candidate["head_event_id"], "historical anchor case requires a later tail")
    core_id = "golden-ledger-v1"

    adjacent = conn.execute(
        """
        SELECT id FROM event_log
        WHERE id != ? AND id <= ?
        ORDER BY ABS(id - ?), id
        LIMIT 1
        """,
        (candidate["head_event_id"], candidate["event_count"], candidate["head_event_id"]),
    ).fetchone()
    _expect(adjacent is not None, "wrong-head-id case needs another historical event")
    wrong_id = copy.deepcopy(candidate)
    wrong_id["head_event_id"] = int(adjacent["id"])

    wrong_seal = copy.deepcopy(candidate)
    wrong_seal["head"] = "0" * 64 if candidate["head"] != "0" * 64 else "1" * 64

    return {
        "historical_head_with_later_tail": {
            "accepted": anchor.verify_anchor(conn, candidate, core_id=core_id) == []
        },
        "wrong_head_event_id": {
            "accepted": anchor.verify_anchor(conn, wrong_id, core_id=core_id) == []
        },
        "wrong_head_seal": {
            "accepted": anchor.verify_anchor(conn, wrong_seal, core_id=core_id) == []
        },
        "wrong_core_id": {
            "accepted": anchor.verify_anchor(conn, candidate, core_id="wrong-golden-ledger-v1") == []
        },
    }


def event_times(conn: sqlite3.Connection, event_ids: list[int]) -> list[str]:
    if not event_ids:
        return []
    placeholders = ",".join("?" for _ in event_ids)
    rows = conn.execute(
        f"SELECT id, created_at FROM event_log WHERE id IN ({placeholders}) ORDER BY id",
        event_ids,
    ).fetchall()
    _expect(len(rows) == len(set(event_ids)), "read-model evidence references missing events")
    by_id = {int(row["id"]): row["created_at"] for row in rows}
    return [by_id[event_id] for event_id in event_ids]


def tampered_oracle_bytes(bundle: CandidateBundle) -> bytes:
    """Return an in-memory negative case without touching the static Oracle."""
    value = copy.deepcopy(bundle.oracle)
    value["expected"]["integrity"]["ok"] = False
    return canonical_json_file_bytes(value)
