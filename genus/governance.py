from __future__ import annotations

import json

from genus import ledger, state


ACTION_PROPOSAL_REVIEW = "proposal.review"
TARGET_PROPOSAL = "proposal"
ALLOWED = "allowed"
BLOCKED = "blocked"
PASS = "pass"
POLICY_BLOCK = "block"
VIOLATION = "violation"
ACCEPTED = "accepted"
REJECTED = "rejected"
PENDING = "pending"
DECISIONS = {ACCEPTED, REJECTED}
CONSTRAINT_TERMINAL_REVIEW = "kernel:terminal_review_v1"
CONSTRAINT_VALID_DECISION = "kernel:valid_decision_v1"
POLICY_PRESSURE_GUARD = "policy:pressure_guard_v1"
KERNEL_CONSTRAINTS = (CONSTRAINT_TERMINAL_REVIEW, CONSTRAINT_VALID_DECISION)
POLICIES = (POLICY_PRESSURE_GUARD,)


def evaluate_proposal_review(
    conn,
    proposal_id: int,
    decision: str,
    override: bool = False,
) -> dict:
    decision_id = next_decision_id(conn)
    constraint_results = _evaluate_kernel_constraints(conn, proposal_id, decision)
    for result in constraint_results:
        _record_constraint_checked(conn, decision_id, proposal_id, result)

    violations = [result for result in constraint_results if result["result"] == VIOLATION]
    if violations:
        reason = violations[0]["reason"]
        _record_governance_decision(
            conn,
            decision_id=decision_id,
            decision=BLOCKED,
            override=override,
            policy_results=[],
            reason=reason,
            target_id=proposal_id,
        )
        return {
            "decision_id": decision_id,
            "decision": BLOCKED,
            "kernel": True,
            "blocked_by": violations[0]["constraint_key"],
            "reason": reason,
            "override": override,
            "policy_results": [],
            "constraint_results": constraint_results,
        }

    policy_results = _evaluate_policies(conn, proposal_id, decision)
    for result in policy_results:
        _record_policy_evaluated(conn, decision_id, proposal_id, result)

    blocked_policies = [
        result for result in policy_results if result["result"] == POLICY_BLOCK
    ]
    if blocked_policies and not override:
        verdict = BLOCKED
        reason = blocked_policies[0]["reason"]
        blocked_by = blocked_policies[0]["policy_key"]
    else:
        verdict = ALLOWED
        blocked_by = blocked_policies[0]["policy_key"] if blocked_policies else None
        reason = (
            f"override accepted for {blocked_by}"
            if blocked_policies and override
            else "governance checks passed"
        )

    _record_governance_decision(
        conn,
        decision_id=decision_id,
        decision=verdict,
        override=override,
        policy_results=policy_results,
        reason=reason,
        target_id=proposal_id,
    )
    return {
        "decision_id": decision_id,
        "decision": verdict,
        "kernel": False,
        "blocked_by": blocked_by,
        "reason": reason,
        "override": override,
        "policy_results": policy_results,
        "constraint_results": constraint_results,
    }


def apply_governance_decision(conn, payload: dict) -> int:
    conn.execute(
        """
        INSERT INTO governance_log
            (id, action, target_type, target_id, decision, override,
             policy_results, reason, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?,
                COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')))
        """,
        (
            int(payload["decision_id"]),
            payload["action"],
            payload["target_type"],
            int(payload["target_id"]),
            payload["decision"],
            1 if payload["override"] else 0,
            _json(payload["policy_results"]),
            payload["reason"],
            payload.get("_event_created_at"),
        ),
    )
    return int(payload["decision_id"])


def list_decisions(conn, target_type: str | None = None, target_id: int | None = None):
    if target_type is not None and target_id is not None:
        rows = conn.execute(
            """
            SELECT * FROM governance_log
            WHERE target_type = ? AND target_id = ?
            ORDER BY id
            """,
            (target_type, target_id),
        ).fetchall()
    elif target_type is not None:
        rows = conn.execute(
            "SELECT * FROM governance_log WHERE target_type = ? ORDER BY id",
            (target_type,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM governance_log ORDER BY id").fetchall()
    return [decision_dict(row) for row in rows]


def get_decision(conn, decision_id: int):
    row = conn.execute(
        "SELECT * FROM governance_log WHERE id = ?",
        (decision_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"governance decision not found: {decision_id}")
    return row


def decision_dict(row) -> dict:
    data = dict(row)
    data["override"] = bool(data["override"])
    data["policy_results"] = json.loads(row["policy_results"])
    return data


def next_decision_id(conn) -> int:
    row = conn.execute(
        "SELECT seq FROM sqlite_sequence WHERE name = 'governance_log'"
    ).fetchone()
    if row is not None:
        return int(row["seq"]) + 1
    row = conn.execute(
        "SELECT COALESCE(MAX(id), 0) AS max_id FROM governance_log"
    ).fetchone()
    return int(row["max_id"]) + 1


def _evaluate_kernel_constraints(conn, proposal_id: int, decision: str) -> list[dict]:
    proposal = conn.execute(
        "SELECT state FROM proposal_log WHERE id = ?",
        (proposal_id,),
    ).fetchone()
    if proposal is None:
        terminal_result = VIOLATION
        terminal_reason = "proposal not found"
    elif proposal["state"] != PENDING:
        terminal_result = VIOLATION
        terminal_reason = "proposal review is terminal"
    else:
        terminal_result = PASS
        terminal_reason = "proposal is pending"

    if decision in DECISIONS:
        decision_result = PASS
        decision_reason = "decision is valid"
    else:
        decision_result = VIOLATION
        decision_reason = "decision must be accepted or rejected"

    return [
        {
            "constraint_key": CONSTRAINT_TERMINAL_REVIEW,
            "result": terminal_result,
            "reason": terminal_reason,
        },
        {
            "constraint_key": CONSTRAINT_VALID_DECISION,
            "result": decision_result,
            "reason": decision_reason,
        },
    ]


def _evaluate_policies(conn, proposal_id: int, decision: str) -> list[dict]:
    active_pressure = state.active_state(conn, state.STATE_KEY)
    if decision != ACCEPTED:
        result = PASS
        reason = "pressure guard only applies to accepted reviews"
    elif active_pressure is not None and active_pressure["state_value"] == state.ELEVATED:
        result = POLICY_BLOCK
        reason = (
            "accepting proposals while system.pressure=elevated requires --override"
        )
    else:
        result = PASS
        reason = "system.pressure is not elevated"
    return [
        {
            "policy_key": POLICY_PRESSURE_GUARD,
            "result": result,
            "reason": reason,
        }
    ]


def _record_constraint_checked(
    conn,
    decision_id: int,
    proposal_id: int,
    result: dict,
) -> int:
    return ledger.append(
        conn,
        "constraint_checked",
        {
            "decision_id": decision_id,
            "constraint_key": result["constraint_key"],
            "action": ACTION_PROPOSAL_REVIEW,
            "target_type": TARGET_PROPOSAL,
            "target_id": proposal_id,
            "result": result["result"],
            "reason": result["reason"],
        },
    )


def _record_policy_evaluated(
    conn,
    decision_id: int,
    proposal_id: int,
    result: dict,
) -> int:
    return ledger.append(
        conn,
        "policy_evaluated",
        {
            "decision_id": decision_id,
            "policy_key": result["policy_key"],
            "action": ACTION_PROPOSAL_REVIEW,
            "target_type": TARGET_PROPOSAL,
            "target_id": proposal_id,
            "result": result["result"],
            "reason": result["reason"],
        },
    )


def _record_governance_decision(
    conn,
    decision_id: int,
    decision: str,
    override: bool,
    policy_results: list[dict],
    reason: str,
    target_id: int,
) -> int:
    payload = {
        "decision_id": decision_id,
        "action": ACTION_PROPOSAL_REVIEW,
        "target_type": TARGET_PROPOSAL,
        "target_id": target_id,
        "decision": decision,
        "override": bool(override),
        "policy_results": policy_results,
        "reason": reason,
    }
    event_id = ledger.append(conn, "governance_decision", payload)
    payload["_event_created_at"] = ledger.event_created_at(conn, event_id)
    apply_governance_decision(conn, payload)
    return event_id


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
