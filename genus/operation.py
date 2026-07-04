from __future__ import annotations

import json

from genus import governance, ledger, projection, proposals


CHECK_EVENT = "operation_check_recorded"
RECOVERY_ATTEMPT_EVENT = "operation_recovery_attempted"
RECOVERY_RESULT_EVENT = "operation_recovery_result"
DERIVATION_CHECK = "operation_check:v1"
DERIVATION_RECOVERY = "operation_recovery:v1"
PROPOSAL_TYPE = "OperationProposal"
CHECK_NETWORK_GATEWAY = "network.gateway"
CLAIM_NETWORK = "system.network"
HEALTHY = "healthy"
UNSTABLE = "unstable"
CHECK_CLOCK_SYNC = "clock.sync"
CLAIM_CLOCK = "system.clock"
CLOCK_TARGET = "ntp"
SYNCHRONIZED = "synchronized"
UNSYNCHRONIZED = "unsynchronized"
STATUS_OK = "ok"
STATUS_FAIL = "fail"
RECOVERY_ATTEMPTED = "attempted"
RECOVERY_SUCCEEDED = "succeeded"
RECOVERY_FAILED = "failed"
RECOVERY_SCHEDULED = "scheduled"
ACTION_RESTART_NETWORK = "restart_network"
ACTION_REBOOT = "reboot"
RECOVERY_ACTIONS = {ACTION_RESTART_NETWORK, ACTION_REBOOT}
RECOVERY_RESULTS = {RECOVERY_SUCCEEDED, RECOVERY_FAILED, RECOVERY_SCHEDULED}


def record_network_check(
    conn,
    status: str,
    target: str,
    failures: int = 0,
    action: str | None = None,
    detail: str = "",
) -> dict:
    if status not in {STATUS_OK, STATUS_FAIL}:
        raise ValueError("status must be ok or fail")
    if action is not None and action not in RECOVERY_ACTIONS:
        raise ValueError("unsupported recovery action")
    if status == STATUS_OK and action is not None:
        raise ValueError("recovery action requires a failed check")

    payload = {
        "failures": int(failures),
        "detail": detail,
    }
    check_event_id = record_check_event(
        conn,
        check_key=CHECK_NETWORK_GATEWAY,
        status=status,
        target=target,
        payload=payload,
    )
    belief_result = _record_network_belief(conn, check_event_id, status)

    recovery_result = None
    if status == STATUS_FAIL and action is not None:
        recovery_result = record_recovery_attempt(
            conn,
            check_key=CHECK_NETWORK_GATEWAY,
            action=action,
            target=target,
            failures=int(failures),
            reason=f"{CHECK_NETWORK_GATEWAY} failed {int(failures)} time(s)",
        )

    return {
        "check_event_id": check_event_id,
        "belief": belief_result,
        "recovery": recovery_result,
    }


def record_clock_check(
    conn,
    status: str,
    target: str = CLOCK_TARGET,
    detail: str = "",
) -> dict:
    if status not in {STATUS_OK, STATUS_FAIL}:
        raise ValueError("status must be ok or fail")

    check_event_id = record_check_event(
        conn,
        check_key=CHECK_CLOCK_SYNC,
        status=status,
        target=target,
        payload={"detail": detail},
    )
    belief_result = _record_clock_belief(conn, check_event_id, status)

    return {
        "check_event_id": check_event_id,
        "belief": belief_result,
    }


def record_check_event(
    conn,
    check_key: str,
    status: str,
    target: str,
    payload: dict,
    operation_id: int | None = None,
) -> int:
    if not target:
        raise ValueError("target must not be empty")
    operation_id = operation_id or next_operation_id(conn)
    event_payload = {
        "operation_id": operation_id,
        "check_key": check_key,
        "status": status,
        "target": target,
        "payload": payload,
        "derivation": DERIVATION_CHECK,
    }
    event_id = ledger.append(conn, CHECK_EVENT, event_payload)
    event_payload["_event_created_at"] = ledger.event_created_at(conn, event_id)
    event_payload["_source_event"] = event_id
    apply_operation_check_recorded(conn, event_payload)
    return event_id


def record_recovery_attempt(
    conn,
    check_key: str,
    action: str,
    target: str,
    failures: int,
    reason: str,
) -> dict:
    if action not in RECOVERY_ACTIONS:
        raise ValueError("unsupported recovery action")
    recovery_id = next_operation_id(conn)
    verdict = governance.evaluate_operation_recovery(
        conn,
        recovery_id=recovery_id,
        action=action,
        failures=int(failures),
        override=False,
    )
    if verdict["decision"] == governance.BLOCKED:
        return {
            "recovery_id": recovery_id,
            "attempt_event_id": None,
            "verdict": verdict,
        }

    event_payload = {
        "recovery_id": recovery_id,
        "check_key": check_key,
        "action": action,
        "target": target,
        "failures": int(failures),
        "reason": reason,
        "derivation": DERIVATION_RECOVERY,
    }
    event_id = ledger.append(conn, RECOVERY_ATTEMPT_EVENT, event_payload)
    event_payload["_event_created_at"] = ledger.event_created_at(conn, event_id)
    event_payload["_source_event"] = event_id
    apply_operation_recovery_attempted(conn, event_payload)
    return {
        "recovery_id": recovery_id,
        "attempt_event_id": event_id,
        "verdict": verdict,
    }


def record_recovery_result(
    conn,
    recovery_id: int,
    result: str,
    detail: str = "",
) -> int:
    if result not in RECOVERY_RESULTS:
        raise ValueError("result must be succeeded, failed, or scheduled")
    row = get_operation(conn, recovery_id)
    payload = json.loads(row["payload"])
    event_payload = {
        "recovery_id": int(recovery_id),
        "result": result,
        "action": payload.get("action", ""),
        "target": row["target"],
        "detail": detail,
        "derivation": DERIVATION_RECOVERY,
    }
    event_id = ledger.append(conn, RECOVERY_RESULT_EVENT, event_payload)
    event_payload["_event_created_at"] = ledger.event_created_at(conn, event_id)
    apply_operation_recovery_result(conn, event_payload)
    return event_id


def apply_operation_check_recorded(conn, payload: dict) -> int:
    return _insert_operation(
        conn,
        operation_id=int(payload["operation_id"]),
        operation_type="check",
        check_key=payload["check_key"],
        status=payload["status"],
        target=payload["target"],
        payload=dict(payload["payload"]),
        derivation=payload["derivation"],
        source_event=payload.get("_source_event"),
        created_at=payload.get("_event_created_at"),
    )


def apply_operation_recovery_attempted(conn, payload: dict) -> int:
    return _insert_operation(
        conn,
        operation_id=int(payload["recovery_id"]),
        operation_type="recovery",
        check_key=payload["check_key"],
        status=RECOVERY_ATTEMPTED,
        target=payload["target"],
        payload={
            "action": payload["action"],
            "failures": int(payload["failures"]),
            "reason": payload["reason"],
        },
        derivation=payload["derivation"],
        source_event=payload.get("_source_event"),
        created_at=payload.get("_event_created_at"),
    )


def apply_operation_recovery_result(conn, payload: dict) -> None:
    row = get_operation(conn, int(payload["recovery_id"]))
    existing_payload = json.loads(row["payload"])
    existing_payload["result"] = payload["result"]
    existing_payload["detail"] = payload["detail"]
    conn.execute(
        """
        UPDATE operation_log
        SET status = ?,
            payload = ?,
            last_updated_at = COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        WHERE id = ?
        """,
        (
            payload["result"],
            _json(existing_payload),
            payload.get("_event_created_at"),
            int(payload["recovery_id"]),
        ),
    )


def get_operation(conn, operation_id: int):
    row = conn.execute(
        "SELECT * FROM operation_log WHERE id = ?",
        (operation_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"operation not found: {operation_id}")
    return row


def list_operations(conn, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM operation_log ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    result = []
    for row in reversed(rows):
        item = dict(row)
        item["payload"] = json.loads(row["payload"])
        result.append(item)
    return result


def next_operation_id(conn) -> int:
    row = conn.execute(
        "SELECT seq FROM sqlite_sequence WHERE name = 'operation_log'"
    ).fetchone()
    if row is not None:
        return int(row["seq"]) + 1
    row = conn.execute("SELECT COALESCE(MAX(id), 0) AS max_id FROM operation_log").fetchone()
    return int(row["max_id"]) + 1


def _record_network_belief(conn, check_event_id: int, status: str) -> dict:
    claim_value = HEALTHY if status == STATUS_OK else UNSTABLE
    belief_result, transitioned = _record_operation_belief(
        conn, check_event_id, CLAIM_NETWORK, claim_value
    )
    if transitioned and claim_value == UNSTABLE:
        _record_network_proposal(conn, belief_result["belief_id"], check_event_id)
    return belief_result


def _record_clock_belief(conn, check_event_id: int, status: str) -> dict:
    claim_value = SYNCHRONIZED if status == STATUS_OK else UNSYNCHRONIZED
    belief_result, transitioned = _record_operation_belief(
        conn, check_event_id, CLAIM_CLOCK, claim_value
    )
    if transitioned and claim_value == UNSYNCHRONIZED:
        _record_clock_proposal(conn, belief_result["belief_id"], check_event_id)
    return belief_result


def _record_operation_belief(
    conn,
    check_event_id: int,
    claim_key: str,
    claim_value: str,
) -> tuple[dict, bool]:
    """Create, confirm, or supersede an operation belief from one check event.

    Returns the belief result and whether the belief freshly took ``claim_value``
    (created or superseded). A ``belief_confirmed`` is not a fresh transition, so
    a caller that raises a proposal on a bad value raises it once per episode,
    not on every repeated check.
    """
    # Phase 0 der Ziel-Architektur: die eine geteilte Zustandsmaschine statt einer
    # eigenen Kopie -- erstellen/bestätigen/ablösen wohnt jetzt in projection.
    result = projection.belief_uebergang(
        conn,
        claim_key=claim_key,
        claim_value=claim_value,
        derivation=DERIVATION_CHECK,
        supporting_events=[check_event_id],
    )
    fresh = result.pop("fresh")
    return result, fresh


def _record_network_proposal(conn, belief_id: int, source_event: int) -> int:
    return proposals.record_proposal_created_event(
        conn,
        proposal_id=proposals.next_proposal_id(conn),
        proposal_type=PROPOSAL_TYPE,
        claim_key=CLAIM_NETWORK,
        claim_value=UNSTABLE,
        source_belief=belief_id,
        source_event=source_event,
        payload={
            "description": "Network gateway checks failed. Review Pi connectivity.",
            "observed_pattern": f"{CLAIM_NETWORK}: {UNSTABLE}",
            "action_required": False,
            "review_recommended": True,
        },
    )


def _record_clock_proposal(conn, belief_id: int, source_event: int) -> int:
    return proposals.record_proposal_created_event(
        conn,
        proposal_id=proposals.next_proposal_id(conn),
        proposal_type=PROPOSAL_TYPE,
        claim_key=CLAIM_CLOCK,
        claim_value=UNSYNCHRONIZED,
        source_belief=belief_id,
        source_event=source_event,
        payload={
            "description": (
                "System clock is not NTP-synchronized. Check the Pi time source; "
                "without an RTC battery, timestamps may be unreliable after a power loss."
            ),
            "observed_pattern": f"{CLAIM_CLOCK}: {UNSYNCHRONIZED}",
            "action_required": False,
            "review_recommended": True,
        },
    )


def _insert_operation(
    conn,
    operation_id: int,
    operation_type: str,
    check_key: str,
    status: str,
    target: str,
    payload: dict,
    derivation: str,
    source_event: int | None,
    created_at: str | None,
) -> int:
    if not derivation:
        raise ValueError("derivation must not be empty")
    conn.execute(
        """
        INSERT INTO operation_log
            (id, operation_type, check_key, status, target, payload,
             derivation, source_event, created_at, last_updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')))
        """,
        (
            operation_id,
            operation_type,
            check_key,
            status,
            target,
            _json(payload),
            derivation,
            source_event,
            created_at,
            created_at,
        ),
    )
    return operation_id


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
