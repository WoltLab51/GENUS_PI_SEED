"""Privacy-sparse, replayable response outcomes and explicit feedback links.

The response id is deliberately not a second generated identifier: it is the
``event_log.id`` of ``response_outcome_recorded``.  The payload therefore carries
only structural facts that are useful for quality measurement.  Question text,
answer text, slots and transport/user identifiers never cross this boundary.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping

from genus import ledger


OUTCOME_EVENT = "response_outcome_recorded"
FEEDBACK_EVENT = "response_feedback_recorded"

OUTCOMES = frozenset({"answered", "invalid_slots", "understood_unknown", "fallback"})
CHANNELS = frozenset({"telegram"})
ANSWER_MODES = frozenset({"core", "voice", "edge_ritual", "feedback_ack", "error"})
FEEDBACK_SIGNALS = frozenset({"positive", "negative", "intent_correction"})
FEEDBACK_SOURCES = frozenset({"owner_explicit"})

OUTCOME_PAYLOAD_KEYS = frozenset(
    {"channel", "outcome", "readings", "answer_mode", "feedback_eligible"}
)
FEEDBACK_PAYLOAD_KEYS = frozenset(
    {"response_id", "signal", "corrected_intent", "source"}
)

MAX_READINGS = 32
_INTENT_TOKEN = re.compile(r"^[a-z0-9äöüß][a-z0-9äöüß_-]{0,63}$")


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _intent_issue(value: object, field: str) -> str | None:
    if not isinstance(value, str) or _INTENT_TOKEN.fullmatch(value) is None:
        return f"{field} must be a lowercase structural intent token"
    return None


def outcome_payload_issues(payload: Mapping[str, object]) -> list[str]:
    """Return every violation of the exact, content-free outcome payload."""
    issues: list[str] = []
    keys = set(payload)
    if keys != OUTCOME_PAYLOAD_KEYS:
        missing = sorted(OUTCOME_PAYLOAD_KEYS - keys)
        extra = sorted(keys - OUTCOME_PAYLOAD_KEYS)
        if missing:
            issues.append(f"missing keys: {', '.join(missing)}")
        if extra:
            issues.append(f"privacy contract forbids extra keys: {', '.join(extra)}")

    channel = payload.get("channel")
    if channel not in CHANNELS:
        issues.append(f"channel must be one of {sorted(CHANNELS)}")
    outcome = payload.get("outcome")
    if outcome not in OUTCOMES:
        issues.append(f"outcome must be one of {sorted(OUTCOMES)}")
    answer_mode = payload.get("answer_mode")
    if answer_mode not in ANSWER_MODES:
        issues.append(f"answer_mode must be one of {sorted(ANSWER_MODES)}")

    eligible = payload.get("feedback_eligible")
    if not isinstance(eligible, bool):
        issues.append("feedback_eligible must be boolean")
    elif answer_mode in {"feedback_ack", "error"} and eligible:
        issues.append(f"answer_mode {answer_mode} must not be feedback eligible")

    readings = payload.get("readings")
    if not isinstance(readings, list):
        issues.append("readings must be a list")
    else:
        if len(readings) > MAX_READINGS:
            issues.append(f"readings must contain at most {MAX_READINGS} intents")
        if len(readings) != len(set(_hashable_or_repr(value) for value in readings)):
            issues.append("readings must not contain duplicates")
        for index, reading in enumerate(readings):
            issue = _intent_issue(reading, f"readings[{index}]")
            if issue:
                issues.append(issue)
    return issues


def _hashable_or_repr(value: object) -> object:
    try:
        hash(value)
    except TypeError:
        return repr(value)
    return value


def feedback_payload_issues(payload: Mapping[str, object]) -> list[str]:
    """Return every structural violation of an explicit feedback link payload."""
    issues: list[str] = []
    keys = set(payload)
    if keys != FEEDBACK_PAYLOAD_KEYS:
        missing = sorted(FEEDBACK_PAYLOAD_KEYS - keys)
        extra = sorted(keys - FEEDBACK_PAYLOAD_KEYS)
        if missing:
            issues.append(f"missing keys: {', '.join(missing)}")
        if extra:
            issues.append(f"privacy contract forbids extra keys: {', '.join(extra)}")

    response_id = payload.get("response_id")
    if not _is_int(response_id) or int(response_id) <= 0:
        issues.append("response_id must be a positive integer")

    signal = payload.get("signal")
    if signal not in FEEDBACK_SIGNALS:
        issues.append(f"signal must be one of {sorted(FEEDBACK_SIGNALS)}")
    if payload.get("source") not in FEEDBACK_SOURCES:
        issues.append(f"source must be one of {sorted(FEEDBACK_SOURCES)}")

    corrected = payload.get("corrected_intent")
    if corrected is not None:
        issue = _intent_issue(corrected, "corrected_intent")
        if issue:
            issues.append(issue)
        if signal != "intent_correction":
            issues.append("corrected_intent is only valid for intent_correction")
    return issues


def _require_valid(issues: list[str]) -> None:
    if issues:
        raise ValueError("; ".join(issues))


def record_outcome(
    conn,
    *,
    channel: str,
    outcome: str,
    readings: list[str],
    answer_mode: str,
    feedback_eligible: bool,
) -> int:
    """Append and project one delivered response; return its stable response id."""
    payload = {
        "channel": channel,
        "outcome": outcome,
        "readings": readings,
        "answer_mode": answer_mode,
        "feedback_eligible": feedback_eligible,
    }
    _require_valid(outcome_payload_issues(payload))
    try:
        response_id = ledger.append(conn, OUTCOME_EVENT, payload)
        payload["_event_id"] = response_id
        payload["_event_created_at"] = ledger.event_created_at(conn, response_id)
        apply_response_outcome_recorded(conn, payload)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return response_id


def record_feedback(
    conn,
    *,
    response_id: int,
    signal: str,
    corrected_intent: str | None = None,
    source: str = "owner_explicit",
) -> int:
    """Append explicit feedback linked to an earlier eligible response.

    The lookup and append share one SQLite writer gate, so eligibility cannot
    change between validation and persistence.  Multiple explicit signals may
    refer to one response; each remains a separate historical observation.
    """
    payload = {
        "response_id": response_id,
        "signal": signal,
        "corrected_intent": corrected_intent,
        "source": source,
    }
    _require_valid(feedback_payload_issues(payload))
    try:
        if not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE")
        response = conn.execute(
            """
            SELECT feedback_eligible
            FROM response_outcome_log
            WHERE response_id = ?
            """,
            (response_id,),
        ).fetchone()
        if response is None:
            raise ValueError(f"unknown response_id: {response_id}")
        if not bool(response["feedback_eligible"]):
            raise ValueError(f"response_id {response_id} is not feedback eligible")

        feedback_event_id = ledger.append(conn, FEEDBACK_EVENT, payload)
        payload["_event_id"] = feedback_event_id
        payload["_event_created_at"] = ledger.event_created_at(conn, feedback_event_id)
        apply_response_feedback_recorded(conn, payload)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return feedback_event_id


def apply_response_outcome_recorded(conn, payload: Mapping[str, object]) -> None:
    """Project one outcome using only the event id/time supplied by the router."""
    conn.execute(
        """
        INSERT INTO response_outcome_log
            (response_id, channel, outcome, readings, answer_mode,
             feedback_eligible, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(payload["_event_id"]),
            payload["channel"],
            payload["outcome"],
            json.dumps(payload["readings"], ensure_ascii=False, separators=(",", ":")),
            payload["answer_mode"],
            int(bool(payload["feedback_eligible"])),
            payload["_event_created_at"],
        ),
    )


def apply_response_feedback_recorded(conn, payload: Mapping[str, object]) -> None:
    """Project one immutable link from explicit feedback to its response."""
    conn.execute(
        """
        INSERT INTO response_feedback_log
            (feedback_event_id, response_id, signal, corrected_intent, source, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            int(payload["_event_id"]),
            int(payload["response_id"]),
            payload["signal"],
            payload["corrected_intent"],
            payload["source"],
            payload["_event_created_at"],
        ),
    )
