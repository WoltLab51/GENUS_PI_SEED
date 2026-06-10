from __future__ import annotations

import json
import string

from genus import inquiries, projection, proposals


BELIEF_PATTERNS = (
    "was glaubst",
    "what do you believe",
    "beliefs",
    "glauben",
)
PROPOSAL_PATTERNS = (
    "was schlaegst",
    "was schlagst",
    "what do you propose",
    "proposals",
    "vorschlaege",
    "vorschlage",
)
INQUIRY_PATTERNS = (
    "was ist offen",
    "what is open",
    "inquiries",
    "questions",
    "fragen",
)
STATUS_PATTERNS = (
    "status",
    "summary",
    "zusammenfassung",
    "zustand",
)
SUPPORTED_PATTERNS = (
    'ask "was glaubst du"',
    'ask "status"',
    'ask "welche proposals"',
    'ask "was ist offen"',
)


def ask(conn, question: str) -> dict:
    normalized = _normalize(question)
    if _matches(normalized, BELIEF_PATTERNS):
        beliefs = projection.list_active_beliefs(conn)
        return {
            "kind": "active_beliefs",
            "question": question,
            "answer": f"{len(beliefs)} active belief(s)",
            "beliefs": beliefs,
        }
    if _matches(normalized, PROPOSAL_PATTERNS):
        rows = proposals.list_proposals(conn, include_all=False)
        return {
            "kind": "pending_proposals",
            "question": question,
            "answer": f"{len(rows)} pending proposal(s)",
            "proposals": rows,
        }
    if _matches(normalized, INQUIRY_PATTERNS):
        rows = inquiries.list_inquiries(conn, include_all=False)
        return {
            "kind": "open_inquiries",
            "question": question,
            "answer": f"{len(rows)} open inquiry/inquiries",
            "inquiries": rows,
        }
    if _matches(normalized, STATUS_PATTERNS):
        return {
            "kind": "status",
            "question": question,
            "answer": "current projection summary",
            "status": status(conn),
        }
    return {
        "kind": "unknown",
        "question": question,
        "answer": "unknown fixed query pattern",
        "supported": list(SUPPORTED_PATTERNS),
    }


def status(conn) -> dict:
    event_count = conn.execute("SELECT COUNT(*) AS count FROM event_log").fetchone()[
        "count"
    ]
    active_count = conn.execute(
        "SELECT COUNT(*) AS count FROM belief_projection WHERE state = ?",
        (projection.ACTIVE,),
    ).fetchone()["count"]
    superseded_count = conn.execute(
        "SELECT COUNT(*) AS count FROM belief_projection WHERE state = ?",
        (projection.SUPERSEDED,),
    ).fetchone()["count"]
    proposal_count = conn.execute(
        "SELECT COUNT(*) AS count FROM proposal_log WHERE state = 'pending'"
    ).fetchone()["count"]
    inquiry_count = conn.execute(
        "SELECT COUNT(*) AS count FROM inquiry_log WHERE state = 'open'"
    ).fetchone()["count"]
    return {
        "events": int(event_count),
        "active_beliefs": int(active_count),
        "superseded_beliefs": int(superseded_count),
        "pending_proposals": int(proposal_count),
        "open_inquiries": int(inquiry_count),
    }


def explain_belief(conn, belief_id: int) -> dict:
    row = projection.get_belief(conn, belief_id)
    belief = projection.belief_with_confidence(conn, row)
    supporting_ids = projection.json_list(row["supporting_events"])
    contradicting_ids = projection.json_list(row["contradicting_events"])
    return {
        "belief": belief,
        "created_by": _find_belief_creation_event(conn, belief_id),
        "supporting_evidence": [
            _event_with_observation(conn, event_id) for event_id in supporting_ids
        ],
        "contradicting_evidence": [
            _event_with_observation(conn, event_id) for event_id in contradicting_ids
        ],
        "transition_events": _find_belief_transition_events(conn, belief_id),
    }


def explain_proposal(conn, proposal_id: int) -> dict:
    proposal = _get_proposal(conn, proposal_id)
    source_belief_id = proposal["source_belief"]
    return {
        "proposal": dict(proposal),
        "proposal_event": _find_proposal_event(conn, proposal_id),
        "review_event": _find_proposal_review_event(conn, proposal_id),
        "source_event": _event_with_observation(conn, int(proposal["source_event"])),
        "source_belief": (
            explain_belief(conn, int(source_belief_id))
            if source_belief_id is not None
            else None
        ),
    }


def _normalize(value: str) -> str:
    lowered = value.casefold()
    translated = lowered.translate(str.maketrans("äöüß", "aous"))
    return translated.translate(str.maketrans("", "", string.punctuation)).strip()


def _matches(question: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in question for pattern in patterns)


def _get_event(conn, event_id: int) -> dict:
    row = conn.execute("SELECT * FROM event_log WHERE id = ?", (event_id,)).fetchone()
    if row is None:
        raise ValueError(f"event not found: {event_id}")
    return _event_dict(row)


def _event_with_observation(conn, event_id: int) -> dict:
    event = _get_event(conn, event_id)
    observation_id = event["payload"].get("observation_id")
    if observation_id is not None:
        event["observation"] = _get_event(conn, int(observation_id))
    return event


def _event_dict(row) -> dict:
    return {
        "id": row["id"],
        "event_type": row["event_type"],
        "payload": json.loads(row["payload"]),
        "created_at": row["created_at"],
    }


def _find_belief_creation_event(conn, belief_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT * FROM event_log
        WHERE (
            event_type = 'belief_created'
            AND json_extract(payload, '$.belief_id') = ?
        ) OR (
            event_type = 'belief_superseded'
            AND json_extract(payload, '$.new_belief_id') = ?
        )
        ORDER BY id
        LIMIT 1
        """,
        (belief_id, belief_id),
    ).fetchone()
    return _event_dict(row) if row is not None else None


def _find_belief_transition_events(conn, belief_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM event_log
        WHERE (
            event_type IN (
                'belief_created',
                'belief_confirmed',
                'belief_weakened',
                'contradiction_detected'
            )
            AND json_extract(payload, '$.belief_id') = ?
        ) OR (
            event_type = 'belief_superseded'
            AND (
                json_extract(payload, '$.old_belief_id') = ?
                OR json_extract(payload, '$.new_belief_id') = ?
            )
        )
        ORDER BY id
        """,
        (belief_id, belief_id, belief_id),
    ).fetchall()
    return [_event_dict(row) for row in rows]


def _find_proposal_event(conn, proposal_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT * FROM event_log
        WHERE event_type = 'proposal_created'
          AND json_extract(payload, '$.proposal_id') = ?
        ORDER BY id
        LIMIT 1
        """,
        (proposal_id,),
    ).fetchone()
    return _event_dict(row) if row is not None else None


def _find_proposal_review_event(conn, proposal_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT * FROM event_log
        WHERE event_type = 'proposal_reviewed'
          AND json_extract(payload, '$.proposal_id') = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (proposal_id,),
    ).fetchone()
    return _event_dict(row) if row is not None else None


def _get_proposal(conn, proposal_id: int):
    row = conn.execute(
        "SELECT * FROM proposal_log WHERE id = ?",
        (proposal_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"proposal not found: {proposal_id}")
    return row
