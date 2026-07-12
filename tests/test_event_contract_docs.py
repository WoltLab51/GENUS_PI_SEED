"""Drift guard between the canonical event documentation and the live registries."""

from __future__ import annotations

import re
from pathlib import Path

from genus import event_router, integrity


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "EVENT_CONTRACT.md"
SCHEMA_BLOCK = re.compile(
    r"<!-- EVENT_SCHEMA:START -->(.*?)<!-- EVENT_SCHEMA:END -->",
    re.DOTALL,
)
SCHEMA_ROW = re.compile(
    r"^\| `(?P<event_type>[a-z_]+)` \| (?P<keys>.*?) \| "
    r"`(?P<route>projected|raw)` \|",
    re.MULTILINE,
)
BACKTICK_VALUE = re.compile(r"`([^`]+)`")


def _documented_schema() -> dict[str, tuple[set[str], str]]:
    text = CONTRACT.read_text(encoding="utf-8")
    block_match = SCHEMA_BLOCK.search(text)
    assert block_match is not None, "EVENT_CONTRACT.md needs one machine-readable schema block"

    schema: dict[str, tuple[set[str], str]] = {}
    for match in SCHEMA_ROW.finditer(block_match.group(1)):
        event_type = match.group("event_type")
        assert event_type not in schema, f"event type documented twice: {event_type}"
        keys = set(BACKTICK_VALUE.findall(match.group("keys")))
        schema[event_type] = (keys, match.group("route"))
    assert schema, "EVENT_CONTRACT.md schema block contains no event rows"
    return schema


def test_documented_event_types_and_required_keys_match_integrity_contract():
    documented = {
        event_type: keys
        for event_type, (keys, _route) in _documented_schema().items()
    }

    assert documented == integrity.REQUIRED_EVENT_KEYS, (
        "docs/EVENT_CONTRACT.md drifted from integrity.REQUIRED_EVENT_KEYS; "
        "document every event type with exactly its enforced required payload keys"
    )


def test_documented_routes_match_event_router():
    documented = {
        event_type: route
        for event_type, (_keys, route) in _documented_schema().items()
    }
    projected = set(event_router.PROJEKTOREN)
    raw = set(event_router.BEWUSST_ROH)

    assert projected.isdisjoint(raw), "an event type cannot be both projected and raw"
    expected = {event_type: "projected" for event_type in projected}
    expected.update({event_type: "raw" for event_type in raw})

    assert documented == expected, (
        "docs/EVENT_CONTRACT.md route drifted from event_router; document each event "
        "as exactly one of projected or raw"
    )
