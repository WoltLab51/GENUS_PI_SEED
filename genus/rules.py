from __future__ import annotations

import json

from genus import ledger, projection, proposals


HIGH_THRESHOLD = 80.0
LOW_THRESHOLD = 60.0
WINDOW_SIZE = 3
METRIC_KEY = "system.cpu_percent"
CLAIM_KEY = "system.load"
HIGH_VALUE = "high"
NORMAL_VALUE = "normal"
DERIVATION = "rule:cpu_threshold_v1"


def apply_cpu_threshold(conn) -> list[str]:
    window = _latest_evidence_window(conn)
    if len(window) < WINDOW_SIZE:
        return []

    values = [float(row["metric_value"]) for row in window]
    event_ids = [int(row["id"]) for row in window]
    latest_event = event_ids[-1]
    written: list[str] = []

    high_belief = projection.active_belief(conn, CLAIM_KEY, HIGH_VALUE)
    any_active = projection.active_belief(conn, CLAIM_KEY)

    if all(value > HIGH_THRESHOLD for value in values):
        if high_belief is None:
            belief_id = projection.next_belief_id(conn)
            belief_event_id = ledger.append(
                conn,
                "belief_created",
                {
                    "belief_id": belief_id,
                    "claim_key": CLAIM_KEY,
                    "claim_value": HIGH_VALUE,
                    "derivation": DERIVATION,
                    "supporting_events": event_ids,
                },
            )
            projection.apply_belief_created(
                conn,
                {
                    "belief_id": belief_id,
                    "claim_key": CLAIM_KEY,
                    "claim_value": HIGH_VALUE,
                    "derivation": DERIVATION,
                    "supporting_events": event_ids,
                    "_event_created_at": ledger.event_created_at(conn, belief_event_id),
                },
            )
            written.append("belief_created")
            proposals.record_resource_proposal_for_sustained_high(
                conn,
                trigger_belief_id=belief_id,
                trigger_event_id=belief_event_id,
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

    elif all(value < LOW_THRESHOLD for value in values) and high_belief is not None:
        new_belief_id = projection.next_belief_id(conn)
        superseded_payload = {
            "old_belief_id": int(high_belief["id"]),
            "new_belief_id": new_belief_id,
            "claim_key": CLAIM_KEY,
            "claim_value": NORMAL_VALUE,
            "derivation": DERIVATION,
            "supporting_events": event_ids,
            "reason": "cpu_load_below_low_threshold",
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
                "reason": "system.load high contradicted by sustained normal readings",
            },
        )
        written.append("contradiction_detected")
        proposals.record_resource_proposal_for_contradiction(
            conn,
            trigger_belief_id=int(high_belief["id"]),
            trigger_event_id=contradiction_event_id,
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


def _latest_evidence_window(conn):
    rows = conn.execute(
        """
        SELECT id, payload
        FROM event_log
        WHERE event_type = 'evidence_recorded'
        ORDER BY id DESC
        LIMIT ?
        """,
        (WINDOW_SIZE,),
    ).fetchall()
    evidence = []
    for row in reversed(rows):
        payload = json.loads(row["payload"])
        if payload.get("metric_key") == METRIC_KEY:
            evidence.append(
                {
                    "id": row["id"],
                    "metric_value": payload["metric_value"],
                }
            )
    return evidence
