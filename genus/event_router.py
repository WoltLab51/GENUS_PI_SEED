from __future__ import annotations

import json

from genus import (
    experience,
    governance,
    inquiries,
    maturation,
    operation,
    projection,
    proposals,
    state,
)


def replay(conn) -> dict:
    events = conn.execute("SELECT * FROM event_log ORDER BY id").fetchall()
    conn.execute("DELETE FROM rule_projection")
    conn.execute("DELETE FROM governance_log")
    conn.execute("DELETE FROM operation_log")
    conn.execute("DELETE FROM inquiry_log")
    conn.execute("DELETE FROM proposal_log")
    conn.execute("DELETE FROM experience_log")
    conn.execute("DELETE FROM state_projection")
    conn.execute("DELETE FROM belief_projection")
    conn.execute(
        """
        DELETE FROM sqlite_sequence
        WHERE name IN (
            'rule_projection',
            'governance_log',
            'operation_log',
            'inquiry_log',
            'proposal_log',
            'experience_log',
            'state_projection',
            'belief_projection'
        )
        """
    )

    for event in events:
        apply_event(conn, event)

    active_count = conn.execute(
        "SELECT COUNT(*) AS count FROM belief_projection WHERE state = 'active'"
    ).fetchone()["count"]
    proposal_count = conn.execute("SELECT COUNT(*) AS count FROM proposal_log").fetchone()[
        "count"
    ]
    inquiry_count = conn.execute("SELECT COUNT(*) AS count FROM inquiry_log").fetchone()[
        "count"
    ]
    experience_count = conn.execute(
        "SELECT COUNT(*) AS count FROM experience_log"
    ).fetchone()["count"]
    state_count = conn.execute(
        "SELECT COUNT(*) AS count FROM state_projection WHERE status = 'active'"
    ).fetchone()["count"]
    governance_count = conn.execute(
        "SELECT COUNT(*) AS count FROM governance_log"
    ).fetchone()["count"]
    operation_count = conn.execute(
        "SELECT COUNT(*) AS count FROM operation_log"
    ).fetchone()["count"]
    active_rule_count = conn.execute(
        "SELECT COUNT(*) AS count FROM rule_projection WHERE status = 'active'"
    ).fetchone()["count"]
    conn.commit()
    return {
        "events": len(events),
        "active_beliefs": int(active_count),
        "proposals": int(proposal_count),
        "inquiries": int(inquiry_count),
        "experiences": int(experience_count),
        "active_states": int(state_count),
        "governance_decisions": int(governance_count),
        "operations": int(operation_count),
        "active_rules": int(active_rule_count),
    }


def apply_event(conn, event) -> None:
    payload = json.loads(event["payload"])
    payload["_event_created_at"] = event["created_at"]
    event_type = event["event_type"]
    if event_type == "belief_created":
        projection.apply_belief_created(conn, payload)
    elif event_type == "belief_confirmed":
        projection.apply_belief_confirmed(conn, payload)
    elif event_type == "belief_weakened":
        projection.apply_belief_weakened(conn, payload)
    elif event_type == "belief_superseded":
        projection.apply_belief_superseded(conn, payload)
    elif event_type == "proposal_created":
        proposals.apply_proposal_created(conn, payload)
    elif event_type == "proposal_reviewed":
        proposals.apply_proposal_reviewed(conn, payload)
    elif event_type == "experience_recorded":
        experience.apply_experience_recorded(conn, payload)
    elif event_type == "experience_recharacterized":
        experience.apply_experience_recharacterized(conn, payload)
    elif event_type == "state_changed":
        state.apply_state_changed(conn, payload)
    elif event_type == "governance_decision":
        governance.apply_governance_decision(conn, payload)
    elif event_type == "operation_check_recorded":
        payload["_source_event"] = event["id"]
        operation.apply_operation_check_recorded(conn, payload)
    elif event_type == "operation_recovery_attempted":
        payload["_source_event"] = event["id"]
        operation.apply_operation_recovery_attempted(conn, payload)
    elif event_type == "operation_recovery_result":
        operation.apply_operation_recovery_result(conn, payload)
    elif event_type == "rule_activated":
        maturation.apply_rule_activated(conn, payload)
    elif event_type == "inquiry_created":
        inquiries.apply_inquiry_created(conn, payload)
    elif event_type == "inquiry_resolved":
        inquiries.apply_inquiry_resolved(conn, payload)
