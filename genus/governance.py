from __future__ import annotations

import json
from datetime import datetime, timezone

from genus import ledger, self_calibration, state
from genus.proposal_types import RULE_PROPOSAL


ACTION_PROPOSAL_REVIEW = "proposal.review"
ACTION_RULE_ACTIVATE = "rule.activate"
ACTION_OPERATION_RECOVERY = "operation.recovery"
TARGET_PROPOSAL = "proposal"
TARGET_OPERATION_RECOVERY = "operation_recovery"
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
CONSTRAINT_RULE_SOURCE_ACCEPTED = "kernel:rule_source_accepted_v1"
CONSTRAINT_RULE_SINGLE_ACTIVATION = "kernel:rule_single_activation_v1"
CONSTRAINT_OPERATION_RECOVERY_ACTION = "kernel:operation_recovery_action_v1"
POLICY_PRESSURE_GUARD = "policy:pressure_guard_v1"
POLICY_REBOOT_AFTER_FAILURES = "policy:reboot_after_failures_v1"
POLICY_REBOOT_COOLDOWN = "policy:reboot_cooldown_v1"
RECOVERY_RESTART_NETWORK = "restart_network"
RECOVERY_REBOOT = "reboot"
RECOVERY_ACTIONS = {RECOVERY_RESTART_NETWORK, RECOVERY_REBOOT}
# The SEED for how many consecutive gateway failures justify a reboot -- no longer the last word:
# calibrated_reboot_threshold() derives the real cut from GENUS's own recovery history once there
# is enough of it (MIN_RECOVERY_EPISODES), the same self-calibration already applied to the
# reasoning rules (transitivity/symmetry). This is the one place GENUS truly ACTS on the world;
# until now it was the only threshold in the core still typed in by hand.
RECOVERY_REBOOT_MIN_FAILURES = 3
MIN_RECOVERY_EPISODES = 5
# How long to wait between successive reboots -- a fixed safety margin against a reboot-loop,
# not a "what's typical for this Pi" question, so it deliberately stays a constant (per the
# relative-vs-absolute criterion in [[self-calibration-no-presets]]).
RECOVERY_REBOOT_COOLDOWN_SECONDS = 3600


def evaluate_proposal_review(
    conn,
    proposal_id: int,
    decision: str,
    override: bool = False,
) -> dict:
    decision_id = next_decision_id(conn)
    constraint_results = _evaluate_kernel_constraints(conn, proposal_id, decision)
    for result in constraint_results:
        _record_constraint_checked(
            conn,
            decision_id,
            ACTION_PROPOSAL_REVIEW,
            TARGET_PROPOSAL,
            proposal_id,
            result,
        )

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
            action=ACTION_PROPOSAL_REVIEW,
            target_type=TARGET_PROPOSAL,
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
        _record_policy_evaluated(
            conn,
            decision_id,
            ACTION_PROPOSAL_REVIEW,
            TARGET_PROPOSAL,
            proposal_id,
            result,
        )

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
        action=ACTION_PROPOSAL_REVIEW,
        target_type=TARGET_PROPOSAL,
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


def evaluate_rule_activation(
    conn,
    proposal_id: int,
    override: bool = False,
) -> dict:
    decision_id = next_decision_id(conn)
    constraint_results = _evaluate_rule_activation_constraints(conn, proposal_id)
    for result in constraint_results:
        _record_constraint_checked(
            conn,
            decision_id,
            ACTION_RULE_ACTIVATE,
            TARGET_PROPOSAL,
            proposal_id,
            result,
        )

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
            action=ACTION_RULE_ACTIVATE,
            target_type=TARGET_PROPOSAL,
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

    _record_governance_decision(
        conn,
        decision_id=decision_id,
        decision=ALLOWED,
        override=override,
        policy_results=[],
        reason="governance checks passed",
        action=ACTION_RULE_ACTIVATE,
        target_type=TARGET_PROPOSAL,
        target_id=proposal_id,
    )
    return {
        "decision_id": decision_id,
        "decision": ALLOWED,
        "kernel": False,
        "blocked_by": None,
        "reason": "governance checks passed",
        "override": override,
        "policy_results": [],
        "constraint_results": constraint_results,
    }


def evaluate_operation_recovery(
    conn,
    recovery_id: int,
    action: str,
    failures: int,
    override: bool = False,
) -> dict:
    decision_id = next_decision_id(conn)
    constraint_results = _evaluate_operation_recovery_constraints(action)
    for result in constraint_results:
        _record_constraint_checked(
            conn,
            decision_id,
            ACTION_OPERATION_RECOVERY,
            TARGET_OPERATION_RECOVERY,
            recovery_id,
            result,
        )

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
            action=ACTION_OPERATION_RECOVERY,
            target_type=TARGET_OPERATION_RECOVERY,
            target_id=recovery_id,
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

    policy_results = _evaluate_operation_recovery_policies(conn, action, failures)
    for result in policy_results:
        _record_policy_evaluated(
            conn,
            decision_id,
            ACTION_OPERATION_RECOVERY,
            TARGET_OPERATION_RECOVERY,
            recovery_id,
            result,
        )

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
        action=ACTION_OPERATION_RECOVERY,
        target_type=TARGET_OPERATION_RECOVERY,
        target_id=recovery_id,
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


def _evaluate_rule_activation_constraints(conn, proposal_id: int) -> list[dict]:
    proposal = conn.execute(
        "SELECT proposal_type, state, payload FROM proposal_log WHERE id = ?",
        (proposal_id,),
    ).fetchone()
    rule_key = None
    if proposal is None:
        source_result = VIOLATION
        source_reason = "proposal not found"
    elif proposal["proposal_type"] != RULE_PROPOSAL:
        source_result = VIOLATION
        source_reason = "proposal is not a RuleProposal"
    elif proposal["state"] != ACCEPTED:
        source_result = VIOLATION
        source_reason = "RuleProposal must be accepted before activation"
    else:
        payload = json.loads(proposal["payload"])
        rule_key = payload.get("rule_key")
        source_result = PASS
        source_reason = "RuleProposal is accepted"

    if rule_key is None and proposal is not None:
        try:
            rule_key = json.loads(proposal["payload"]).get("rule_key")
        except json.JSONDecodeError:
            rule_key = None

    if not rule_key:
        activation_result = VIOLATION
        activation_reason = "rule_key unavailable"
    elif _rule_activated(conn, rule_key):
        activation_result = VIOLATION
        activation_reason = "rule_key already activated"
    else:
        activation_result = PASS
        activation_reason = "rule_key is not activated"

    return [
        {
            "constraint_key": CONSTRAINT_RULE_SOURCE_ACCEPTED,
            "result": source_result,
            "reason": source_reason,
        },
        {
            "constraint_key": CONSTRAINT_RULE_SINGLE_ACTIVATION,
            "result": activation_result,
            "reason": activation_reason,
        },
    ]


def _evaluate_operation_recovery_constraints(action: str) -> list[dict]:
    if action in RECOVERY_ACTIONS:
        result = PASS
        reason = "recovery action is valid"
    else:
        result = VIOLATION
        reason = "recovery action must be restart_network or reboot"
    return [
        {
            "constraint_key": CONSTRAINT_OPERATION_RECOVERY_ACTION,
            "result": result,
            "reason": reason,
        }
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


def _evaluate_operation_recovery_policies(
    conn,
    action: str,
    failures: int,
) -> list[dict]:
    if action != RECOVERY_REBOOT:
        threshold_result = PASS
        threshold_reason = "reboot guard only applies to reboot recovery"
    else:
        threshold = calibrated_reboot_threshold(conn)
        if int(failures) >= threshold:
            threshold_result = PASS
            threshold_reason = "network failure threshold reached"
        else:
            threshold_result = POLICY_BLOCK
            threshold_reason = (
                "reboot recovery requires at least "
                f"{threshold} consecutive failures"
            )
    cooldown_result = _evaluate_reboot_cooldown(conn, action)
    return [
        {
            "policy_key": POLICY_REBOOT_AFTER_FAILURES,
            "result": threshold_result,
            "reason": threshold_reason,
        },
        cooldown_result,
    ]


def calibrated_reboot_threshold(conn) -> int:
    """How many consecutive gateway failures GENUS requires before allowing reboot recovery,
    learned from the natural gap in GENUS's own outage history instead of the typed-in
    RECOVERY_REBOOT_MIN_FAILURES. Most outage episodes are short (a blip, or restart_network
    already fixed it); a real outage that needed the harsher remedy sits far above them -- the
    widest gap between completed episode lengths is the cut. Falls back to the seed when there
    are too few completed episodes to show a real pattern (an idle, stable Pi rightly keeps the
    seed). Read on demand: recovery attempts are rare, so there is no hot-path cost to justify a
    stored/batched calibration like the reasoning rules (see [[self-calibration-no-presets]])."""
    return reboot_threshold_report(conn)["threshold"]


def reboot_threshold_report(conn) -> dict:
    """Glass-box readout behind calibrated_reboot_threshold: the active value, how many completed
    outage episodes it's derived from, and whether it's actually derived or still the seed."""
    lengths = _recovery_episode_lengths(conn)
    derived = len(lengths) >= MIN_RECOVERY_EPISODES
    threshold = (
        self_calibration.widest_gap_count_threshold(lengths, RECOVERY_REBOOT_MIN_FAILURES)
        if derived else RECOVERY_REBOOT_MIN_FAILURES
    )
    return {"threshold": threshold, "episodes": len(lengths), "derived": derived}


def _recovery_episode_lengths(conn) -> list[int]:
    """Length (consecutive failed checks) of every COMPLETED network-outage episode -- a run of
    failed network.gateway checks followed by an ok check. An episode still failing at the most
    recent check is excluded (unresolved, its true length isn't known yet) -- open-world, like
    every other calibration in the core."""
    rows = conn.execute(
        """
        SELECT json_extract(payload, '$.status') AS status,
               json_extract(payload, '$.payload.failures') AS failures
        FROM event_log
        WHERE event_type = 'operation_check_recorded'
          AND json_extract(payload, '$.check_key') = 'network.gateway'
        ORDER BY id ASC
        """
    ).fetchall()
    lengths: list[int] = []
    run_max = 0
    for row in rows:
        if row["status"] == "fail":
            run_max = max(run_max, int(row["failures"] or 0))
        elif run_max > 0:
            lengths.append(run_max)
            run_max = 0
    return lengths


def _evaluate_reboot_cooldown(conn, action: str) -> dict:
    if action != RECOVERY_REBOOT:
        return {
            "policy_key": POLICY_REBOOT_COOLDOWN,
            "result": PASS,
            "reason": "reboot cooldown only applies to reboot recovery",
        }

    recent = _latest_reboot_recovery_attempt(conn)
    if recent is None:
        return {
            "policy_key": POLICY_REBOOT_COOLDOWN,
            "result": PASS,
            "reason": "no prior reboot recovery attempt recorded",
        }

    last_reboot_at = _parse_event_time(recent["created_at"])
    elapsed_seconds = (_utc_now() - last_reboot_at).total_seconds()
    if elapsed_seconds >= RECOVERY_REBOOT_COOLDOWN_SECONDS:
        return {
            "policy_key": POLICY_REBOOT_COOLDOWN,
            "result": PASS,
            "reason": "reboot cooldown elapsed",
        }

    remaining = int(RECOVERY_REBOOT_COOLDOWN_SECONDS - elapsed_seconds)
    return {
        "policy_key": POLICY_REBOOT_COOLDOWN,
        "result": POLICY_BLOCK,
        "reason": f"reboot recovery cooldown active for {remaining} more second(s)",
    }


def _latest_reboot_recovery_attempt(conn):
    return conn.execute(
        """
        SELECT id, created_at
        FROM event_log
        WHERE event_type = 'operation_recovery_attempted'
          AND json_extract(payload, '$.action') = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (RECOVERY_REBOOT,),
    ).fetchone()


def _parse_event_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _record_constraint_checked(
    conn,
    decision_id: int,
    action: str,
    target_type: str,
    target_id: int,
    result: dict,
) -> int:
    return ledger.append(
        conn,
        "constraint_checked",
        {
            "decision_id": decision_id,
            "constraint_key": result["constraint_key"],
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "result": result["result"],
            "reason": result["reason"],
        },
    )


def _record_policy_evaluated(
    conn,
    decision_id: int,
    action: str,
    target_type: str,
    target_id: int,
    result: dict,
) -> int:
    return ledger.append(
        conn,
        "policy_evaluated",
        {
            "decision_id": decision_id,
            "policy_key": result["policy_key"],
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
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
    action: str,
    target_type: str,
    target_id: int,
) -> int:
    payload = {
        "decision_id": decision_id,
        "action": action,
        "target_type": target_type,
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


def _rule_activated(conn, rule_key: str) -> bool:
    projection_row = conn.execute(
        "SELECT 1 FROM rule_projection WHERE rule_key = ? LIMIT 1",
        (rule_key,),
    ).fetchone()
    if projection_row is not None:
        return True
    event_row = conn.execute(
        """
        SELECT 1
        FROM event_log
        WHERE event_type = 'rule_activated'
          AND json_extract(payload, '$.rule_key') = ?
        LIMIT 1
        """,
        (rule_key,),
    ).fetchone()
    return event_row is not None


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


# --- Acquisition gate: lightweight, read-time governance for the autonomous learner -------
# The engine above is deliberative -- it logs a decision per review. Autonomous knowledge
# acquisition runs in a hot loop (potentially 100k words), so its governance is a read-time
# gate that records nothing: it just answers "may the learner acquire from this source now?"
ACQUISITION_ALLOWED = "allowed"
ACQUISITION_PAUSED = "GENUS is paused"
ACQUISITION_UNTRUSTED = "source trust below seed"


def acquisition_allowed(conn, source: str) -> dict:
    """May the autonomous learner acquire knowledge from ``source`` right now?

    Glass-box and self-calibrating: blocked while GENUS is paused (the control plane), or
    when the source has proven *less* trustworthy than a fresh one -- its read-time
    ``source_trust`` has fallen below the seed. No preset rate or allow-list; the gate reads
    the live ledger. Records nothing (safe to call in the learner's hot loop).
    """
    from genus import control, sources

    if control.is_paused():
        return {"allowed": False, "reason": ACQUISITION_PAUSED}
    if sources.source_trust(conn, source) < sources.SOURCE_TRUST_SEED:
        return {"allowed": False, "reason": ACQUISITION_UNTRUSTED}
    return {"allowed": True, "reason": ACQUISITION_ALLOWED}
