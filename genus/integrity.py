from __future__ import annotations

import json
import sqlite3

from genus import event_router
from genus.db import init_schema


REQUIRED_EVENT_KEYS = {
    "observation_created": {"source", "raw_value", "unit"},
    "evidence_recorded": {"observation_id", "metric_key", "metric_value"},
    "belief_created": {
        "belief_id",
        "claim_key",
        "claim_value",
        "derivation",
        "supporting_events",
    },
    "belief_confirmed": {"belief_id", "new_supporting_event"},
    "belief_weakened": {"belief_id", "contradicting_event"},
    "belief_superseded": {
        "old_belief_id",
        "new_belief_id",
        "claim_key",
        "claim_value",
        "derivation",
        "supporting_events",
        "reason",
    },
    "contradiction_detected": {"belief_id", "reason"},
    "proposal_created": {
        "proposal_id",
        "proposal_type",
        "claim_key",
        "claim_value",
        "source_belief",
        "source_event",
        "payload",
        "reason",
    },
    "proposal_reviewed": {"proposal_id", "decision", "note"},
    "experience_recorded": {
        "experience_id",
        "experience_key",
        "experience_type",
        "subject_key",
        "pattern",
        "supporting_events",
        "derivation",
        "summary",
    },
    "state_changed": {
        "state_id",
        "state_key",
        "state_value",
        "previous_state_id",
        "derivation",
        "supporting_beliefs",
        "components",
        "reason",
    },
    "policy_evaluated": {
        "decision_id",
        "policy_key",
        "action",
        "target_type",
        "target_id",
        "result",
        "reason",
    },
    "constraint_checked": {
        "decision_id",
        "constraint_key",
        "action",
        "target_type",
        "target_id",
        "result",
        "reason",
    },
    "governance_decision": {
        "decision_id",
        "action",
        "target_type",
        "target_id",
        "decision",
        "override",
        "policy_results",
        "reason",
    },
    "inquiry_created": {
        "inquiry_id",
        "inquiry_type",
        "claim_key",
        "source_belief",
        "source_event",
        "question_key",
        "payload",
        "state",
    },
    "inquiry_resolved": {"inquiry_id", "answer"},
}


def check(conn) -> dict:
    issues = []
    issues.extend(validate_schema(conn))
    issues.extend(validate_event_contract(conn))

    event_log_before = snapshot_event_log(conn)
    projection_before = snapshot_projections(conn)
    replay_conn = replay_connection_from_events(event_log_before)
    replay_summary = event_router.replay(replay_conn)
    event_log_after = snapshot_event_log(conn)
    projection_after = snapshot_projections(replay_conn)
    replay_conn.close()

    if event_log_after != event_log_before:
        issues.append("event_log changed during replay")
    if projection_after != projection_before:
        issues.append("projection state changed after replay")

    return {
        "ok": not issues,
        "issues": issues,
        "events": len(event_log_after),
        "active_beliefs": replay_summary["active_beliefs"],
        "proposals": replay_summary["proposals"],
        "inquiries": replay_summary["inquiries"],
        "experiences": replay_summary["experiences"],
        "active_states": replay_summary["active_states"],
        "governance_decisions": replay_summary["governance_decisions"],
    }


def replay_connection_from_events(events: list[dict]) -> sqlite3.Connection:
    replay_conn = sqlite3.connect(":memory:")
    replay_conn.row_factory = sqlite3.Row
    init_schema(replay_conn)
    replay_conn.executemany(
        """
        INSERT INTO event_log (id, event_type, payload, created_at)
        VALUES (:id, :event_type, :payload, :created_at)
        """,
        events,
    )
    replay_conn.commit()
    return replay_conn


def validate_schema(conn) -> list[str]:
    issues = []
    belief_columns = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(belief_projection)").fetchall()
    ]
    proposal_columns = [
        row["name"] for row in conn.execute("PRAGMA table_info(proposal_log)").fetchall()
    ]
    inquiry_columns = [
        row["name"] for row in conn.execute("PRAGMA table_info(inquiry_log)").fetchall()
    ]
    experience_columns = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(experience_log)").fetchall()
    ]
    state_columns = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(state_projection)").fetchall()
    ]
    governance_columns = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(governance_log)").fetchall()
    ]
    if "confidence" in belief_columns:
        issues.append("belief_projection must not store confidence")
    if not {"decision", "reviewed_at"}.issubset(proposal_columns):
        issues.append("proposal_log missing lifecycle columns")
    if "answer" not in inquiry_columns:
        issues.append("inquiry_log missing answer column")
    if not {
        "experience_key",
        "experience_type",
        "subject_key",
        "pattern",
        "supporting_events",
        "derivation",
        "summary",
    }.issubset(experience_columns):
        issues.append("experience_log missing required columns")
    if "confidence" in experience_columns:
        issues.append("experience_log must not store confidence")
    if not {
        "state_key",
        "state_value",
        "status",
        "derivation",
        "supporting_beliefs",
        "components",
        "reason",
    }.issubset(state_columns):
        issues.append("state_projection missing required columns")
    if "confidence" in state_columns:
        issues.append("state_projection must not store confidence")
    if not {
        "action",
        "target_type",
        "target_id",
        "decision",
        "override",
        "policy_results",
        "reason",
    }.issubset(governance_columns):
        issues.append("governance_log missing required columns")
    if "confidence" in governance_columns:
        issues.append("governance_log must not store confidence")

    empty_derivations = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM belief_projection
        WHERE derivation IS NULL OR TRIM(derivation) = ''
        """
    ).fetchone()["count"]
    if empty_derivations:
        issues.append("belief_projection contains empty derivation")
    empty_experience_derivations = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM experience_log
        WHERE derivation IS NULL OR TRIM(derivation) = ''
        """
    ).fetchone()["count"]
    if empty_experience_derivations:
        issues.append("experience_log contains empty derivation")
    empty_state_derivations = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM state_projection
        WHERE derivation IS NULL OR TRIM(derivation) = ''
        """
    ).fetchone()["count"]
    if empty_state_derivations:
        issues.append("state_projection contains empty derivation")
    return issues


def validate_event_contract(conn) -> list[str]:
    issues = []
    rows = conn.execute("SELECT id, event_type, payload FROM event_log ORDER BY id").fetchall()
    ids = [row["id"] for row in rows]
    if ids and ids != list(range(ids[0], ids[-1] + 1)):
        issues.append("event_log ids are not contiguous")
    reviewed_proposals = set()
    resolved_inquiries = set()

    for row in rows:
        event_type = row["event_type"]
        try:
            payload = json.loads(row["payload"])
        except json.JSONDecodeError:
            issues.append(f"event {row['id']} payload is not valid JSON")
            continue

        required = REQUIRED_EVENT_KEYS.get(event_type)
        if required is None:
            issues.append(f"event {row['id']} has unknown event_type {event_type}")
            continue

        missing = sorted(required - set(payload))
        if missing:
            issues.append(
                f"event {row['id']} {event_type} missing keys: {', '.join(missing)}"
            )

        if event_type in {"belief_created", "belief_superseded"} and not payload.get(
            "derivation"
        ):
            issues.append(f"event {row['id']} {event_type} has empty derivation")
        if event_type == "experience_recorded" and not payload.get("derivation"):
            issues.append(f"event {row['id']} experience_recorded has empty derivation")
        if event_type == "state_changed" and not payload.get("derivation"):
            issues.append(f"event {row['id']} state_changed has empty derivation")
        if event_type == "constraint_checked":
            if payload["result"] not in {"pass", "violation"}:
                issues.append(f"event {row['id']} constraint_checked has invalid result")
        if event_type == "policy_evaluated":
            if payload["result"] not in {"pass", "block"}:
                issues.append(f"event {row['id']} policy_evaluated has invalid result")
        if event_type == "governance_decision":
            if payload["decision"] not in {"allowed", "blocked"}:
                issues.append(f"event {row['id']} governance_decision has invalid decision")
            if payload["action"] != "proposal.review":
                issues.append(f"event {row['id']} governance_decision has invalid action")
        if event_type == "proposal_reviewed":
            proposal_id = payload["proposal_id"]
            if payload["decision"] not in {"accepted", "rejected"}:
                issues.append(f"event {row['id']} proposal_reviewed has invalid decision")
            if proposal_id in reviewed_proposals:
                issues.append(f"proposal {proposal_id} reviewed more than once")
            reviewed_proposals.add(proposal_id)
        if event_type == "inquiry_resolved":
            inquiry_id = payload["inquiry_id"]
            if not str(payload["answer"]).strip():
                issues.append(f"event {row['id']} inquiry_resolved has empty answer")
            if inquiry_id in resolved_inquiries:
                issues.append(f"inquiry {inquiry_id} resolved more than once")
            resolved_inquiries.add(inquiry_id)
    return issues


def snapshot_event_log(conn) -> list[dict]:
    return [
        {
            "id": row["id"],
            "event_type": row["event_type"],
            "payload": row["payload"],
            "created_at": row["created_at"],
        }
        for row in conn.execute(
            "SELECT id, event_type, payload, created_at FROM event_log ORDER BY id"
        ).fetchall()
    ]


def snapshot_projections(conn) -> dict:
    beliefs = [
        dict(row)
        for row in conn.execute(
            """
            SELECT id, claim_key, claim_value, state, derivation,
                   supporting_events, contradicting_events,
                   created_at, last_updated_at, superseded_by
            FROM belief_projection
            ORDER BY id
            """
        ).fetchall()
    ]
    proposals = [
        dict(row)
        for row in conn.execute(
            """
            SELECT id, proposal_type, claim_key, claim_value, source_belief,
                   source_event, payload, state, decision, reviewed_at, created_at
            FROM proposal_log
            ORDER BY id
            """
        ).fetchall()
    ]
    inquiries = [
        dict(row)
        for row in conn.execute(
            """
            SELECT id, inquiry_type, claim_key, source_belief, source_event,
                   question_key, payload, state, answer, created_at, resolved_at
            FROM inquiry_log
            ORDER BY id
            """
        ).fetchall()
    ]
    experiences = [
        dict(row)
        for row in conn.execute(
            """
            SELECT id, experience_key, experience_type, subject_key, pattern,
                   supporting_events, derivation, summary, created_at
            FROM experience_log
            ORDER BY id
            """
        ).fetchall()
    ]
    states = [
        dict(row)
        for row in conn.execute(
            """
            SELECT id, state_key, state_value, status, derivation,
                   supporting_beliefs, components, reason,
                   created_at, last_updated_at, superseded_by
            FROM state_projection
            ORDER BY id
            """
        ).fetchall()
    ]
    governance = [
        dict(row)
        for row in conn.execute(
            """
            SELECT id, action, target_type, target_id, decision, override,
                   policy_results, reason, created_at
            FROM governance_log
            ORDER BY id
            """
        ).fetchall()
    ]
    return {
        "beliefs": beliefs,
        "proposals": proposals,
        "inquiries": inquiries,
        "experiences": experiences,
        "states": states,
        "governance": governance,
    }
