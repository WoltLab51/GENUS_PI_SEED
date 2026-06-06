from __future__ import annotations

import json

from genus import ledger, projection, proposals


CPU_HIGH_THRESHOLD = 80.0
CPU_LOW_THRESHOLD = 60.0
MEMORY_HIGH_THRESHOLD = 85.0
MEMORY_LOW_THRESHOLD = 70.0
WINDOW_SIZE = 3
CPU_METRIC_KEY = "system.cpu_percent"
MEMORY_METRIC_KEY = "system.memory_percent"
METRIC_KEY = CPU_METRIC_KEY
CLAIM_KEY = "system.load"
HIGH_VALUE = "high"
NORMAL_VALUE = "normal"
CPU_DERIVATION = "rule:cpu_threshold_v1"
MEMORY_DERIVATION = "rule:memory_threshold_v1"
DERIVATION = CPU_DERIVATION

HIGH_THRESHOLD = CPU_HIGH_THRESHOLD
LOW_THRESHOLD = CPU_LOW_THRESHOLD

RULES = {
    CPU_METRIC_KEY: {
        "high_threshold": CPU_HIGH_THRESHOLD,
        "low_threshold": CPU_LOW_THRESHOLD,
        "claim_key": CLAIM_KEY,
        "derivation": CPU_DERIVATION,
        "contradiction_reason": "system.load high contradicted by sustained normal readings",
    },
    MEMORY_METRIC_KEY: {
        "high_threshold": MEMORY_HIGH_THRESHOLD,
        "low_threshold": MEMORY_LOW_THRESHOLD,
        "claim_key": "system.memory",
        "derivation": MEMORY_DERIVATION,
        "contradiction_reason": "system.memory high contradicted by sustained normal readings",
    },
}


def apply_thresholds(conn) -> list[str]:
    written: list[str] = []
    for metric_key in RULES:
        written.extend(apply_threshold(conn, metric_key))
    return written


def apply_cpu_threshold(conn) -> list[str]:
    return apply_threshold(conn, CPU_METRIC_KEY)


def apply_memory_threshold(conn) -> list[str]:
    return apply_threshold(conn, MEMORY_METRIC_KEY)


def apply_threshold(conn, metric_key: str) -> list[str]:
    rule = RULES[metric_key]
    window = _latest_evidence_window(conn, metric_key)
    if len(window) < WINDOW_SIZE:
        return []

    values = [float(row["metric_value"]) for row in window]
    event_ids = [int(row["id"]) for row in window]
    latest_event = event_ids[-1]
    written: list[str] = []

    claim_key = rule["claim_key"]
    derivation = rule["derivation"]
    high_belief = projection.active_belief(conn, claim_key, HIGH_VALUE)
    any_active = projection.active_belief(conn, claim_key)

    if all(value > rule["high_threshold"] for value in values):
        if high_belief is None:
            belief_id = projection.next_belief_id(conn)
            belief_event_id = ledger.append(
                conn,
                "belief_created",
                {
                    "belief_id": belief_id,
                    "claim_key": claim_key,
                    "claim_value": HIGH_VALUE,
                    "derivation": derivation,
                    "supporting_events": event_ids,
                },
            )
            projection.apply_belief_created(
                conn,
                {
                    "belief_id": belief_id,
                    "claim_key": claim_key,
                    "claim_value": HIGH_VALUE,
                    "derivation": derivation,
                    "supporting_events": event_ids,
                    "_event_created_at": ledger.event_created_at(conn, belief_event_id),
                },
            )
            written.append("belief_created")
            proposals.record_resource_proposal_for_sustained_high(
                conn,
                trigger_belief_id=belief_id,
                trigger_event_id=belief_event_id,
                claim_key=claim_key,
            )
            written.append("proposal_created")
        else:
            event_id = ledger.append(
                conn,
                "belief_confirmed",
                {
                    "belief_id": int(high_belief["id"]),
                    "new_supporting_event": latest_event,
                },
            )
            projection.apply_belief_confirmed(
                conn,
                {
                    "belief_id": int(high_belief["id"]),
                    "new_supporting_event": latest_event,
                    "_event_created_at": ledger.event_created_at(conn, event_id),
                },
            )
            written.append("belief_confirmed")
            assert event_id > 0

    elif all(value < rule["low_threshold"] for value in values) and high_belief is not None:
        new_belief_id = projection.next_belief_id(conn)
        superseded_payload = {
            "old_belief_id": int(high_belief["id"]),
            "new_belief_id": new_belief_id,
            "claim_key": claim_key,
            "claim_value": NORMAL_VALUE,
            "derivation": derivation,
            "supporting_events": event_ids,
            "reason": f"{metric_key}_below_low_threshold",
        }
        superseded_event_id = ledger.append(conn, "belief_superseded", superseded_payload)
        superseded_payload["_event_created_at"] = ledger.event_created_at(
            conn, superseded_event_id
        )
        projection.apply_belief_superseded(conn, superseded_payload)
        written.append("belief_superseded")

        contradiction_event_id = ledger.append(
            conn,
            "contradiction_detected",
            {
                "belief_id": int(high_belief["id"]),
                "reason": rule["contradiction_reason"],
            },
        )
        written.append("contradiction_detected")
        proposals.record_resource_proposal_for_contradiction(
            conn,
            trigger_belief_id=int(high_belief["id"]),
            trigger_event_id=contradiction_event_id,
            claim_key=claim_key,
        )
        written.append("proposal_created")

    elif any_active is not None:
        event_id = ledger.append(
            conn,
            "belief_weakened",
            {
                "belief_id": int(any_active["id"]),
                "contradicting_event": latest_event,
            },
        )
        projection.apply_belief_weakened(
            conn,
            {
                "belief_id": int(any_active["id"]),
                "contradicting_event": latest_event,
                "_event_created_at": ledger.event_created_at(conn, event_id),
            },
        )
        written.append("belief_weakened")
        assert event_id > 0

    conn.commit()
    return written


def _latest_evidence_window(conn, metric_key: str = METRIC_KEY):
    rows = conn.execute(
        """
        SELECT id, payload
        FROM event_log
        WHERE event_type = 'evidence_recorded'
        ORDER BY id DESC
        """,
    ).fetchall()
    evidence = []
    for row in reversed(rows):
        payload = json.loads(row["payload"])
        if payload.get("metric_key") == metric_key:
            evidence.append(
                {
                    "id": row["id"],
                    "metric_value": payload["metric_value"],
                }
            )
    evidence = evidence[-WINDOW_SIZE:]
    return evidence
