from __future__ import annotations

from genus import inquiries, ledger, projection, proposals


CPU_HIGH_THRESHOLD = 80.0
CPU_LOW_THRESHOLD = 60.0
MEMORY_HIGH_THRESHOLD = 85.0
MEMORY_LOW_THRESHOLD = 70.0
DISK_HIGH_THRESHOLD = 85.0
DISK_LOW_THRESHOLD = 60.0
TEMP_HIGH_THRESHOLD = 75.0
TEMP_LOW_THRESHOLD = 55.0
WINDOW_SIZE = 3
CPU_METRIC_KEY = "system.cpu_percent"
MEMORY_METRIC_KEY = "system.memory_percent"
DISK_METRIC_KEY = "system.disk_percent"
ACTIVITY_METRIC_KEY = "system.activity"
TEMPERATURE_METRIC_KEY = "system.temperature"
REPO_COMMITS_METRIC_KEY = "repo.commits_per_day"
REPO_LINES_METRIC_KEY = "repo.lines_changed_per_day"
REPO_CHURN_HEAVY_THRESHOLD = 300.0
CLAIM_KEY = "system.load"
HIGH_VALUE = "high"
NORMAL_VALUE = "normal"
CPU_DERIVATION = "rule:cpu_threshold_v1"
MEMORY_DERIVATION = "rule:memory_threshold_v1"
DISK_DERIVATION = "rule:disk_threshold_v1"
ACTIVITY_DERIVATION = "rule:activity_binary_v1"
TEMPERATURE_DERIVATION = "rule:temperature_threshold_v1"
REPO_ACTIVITY_DERIVATION = "rule:repo_activity_binary_v1"
REPO_CHURN_DERIVATION = "rule:repo_churn_binary_v1"

RULES = {
    CPU_METRIC_KEY: {
        "type": "threshold",
        "high_threshold": CPU_HIGH_THRESHOLD,
        "low_threshold": CPU_LOW_THRESHOLD,
        "claim_key": CLAIM_KEY,
        "derivation": CPU_DERIVATION,
        "contradiction_reason": "system.load high contradicted by sustained normal readings",
    },
    MEMORY_METRIC_KEY: {
        "type": "threshold",
        "high_threshold": MEMORY_HIGH_THRESHOLD,
        "low_threshold": MEMORY_LOW_THRESHOLD,
        "claim_key": "system.memory",
        "derivation": MEMORY_DERIVATION,
        "contradiction_reason": "system.memory high contradicted by sustained normal readings",
    },
    DISK_METRIC_KEY: {
        "type": "threshold",
        "high_threshold": DISK_HIGH_THRESHOLD,
        "low_threshold": DISK_LOW_THRESHOLD,
        "claim_key": "system.disk",
        "derivation": DISK_DERIVATION,
        "contradiction_reason": "system.disk high contradicted by sustained normal readings",
    },
    TEMPERATURE_METRIC_KEY: {
        "type": "threshold",
        "high_threshold": TEMP_HIGH_THRESHOLD,
        "low_threshold": TEMP_LOW_THRESHOLD,
        "claim_key": "system.temperature",
        "derivation": TEMPERATURE_DERIVATION,
        "contradiction_reason": "system.temperature high contradicted by sustained normal readings",
    },
    ACTIVITY_METRIC_KEY: {
        "type": "binary",
        "active_value": "active",
        "idle_value": "idle",
        "claim_key": "system.activity",
        "derivation": ACTIVITY_DERIVATION,
    },
    REPO_COMMITS_METRIC_KEY: {
        "type": "binary",
        "active_value": "active",
        "idle_value": "quiet",
        "claim_key": "repo.activity",
        "derivation": REPO_ACTIVITY_DERIVATION,
    },
    REPO_LINES_METRIC_KEY: {
        "type": "binary",
        "threshold": REPO_CHURN_HEAVY_THRESHOLD,
        "active_value": "heavy",
        "idle_value": "light",
        "claim_key": "repo.churn",
        "derivation": REPO_CHURN_DERIVATION,
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


def apply_disk_threshold(conn) -> list[str]:
    return apply_threshold(conn, DISK_METRIC_KEY)


def apply_activity_rule(conn) -> list[str]:
    return apply_threshold(conn, ACTIVITY_METRIC_KEY)


def apply_temperature_threshold(conn) -> list[str]:
    return apply_threshold(conn, TEMPERATURE_METRIC_KEY)


def apply_threshold(conn, metric_key: str) -> list[str]:
    rule = RULES[metric_key]
    if rule.get("type") == "binary":
        return apply_binary_rule(conn, metric_key, rule)

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
        inquiries.record_cause_inquiry_for_contradiction(
            conn,
            claim_key=claim_key,
            source_belief=int(high_belief["id"]),
            source_event=contradiction_event_id,
        )
        written.append("inquiry_created")
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

    return written


def apply_binary_rule(conn, metric_key: str, rule: dict) -> list[str]:
    window = _latest_evidence_window(conn, metric_key, n=1)
    if not window:
        return []

    latest = window[0]
    value = float(latest["metric_value"])
    event_id = int(latest["id"])
    claim_key = rule["claim_key"]
    derivation = rule["derivation"]
    threshold = rule.get("threshold", 1.0)
    new_value = rule["active_value"] if value >= threshold else rule["idle_value"]
    current = projection.active_belief(conn, claim_key)
    written: list[str] = []

    if current is None:
        belief_id = projection.next_belief_id(conn)
        belief_event_id = ledger.append(
            conn,
            "belief_created",
            {
                "belief_id": belief_id,
                "claim_key": claim_key,
                "claim_value": new_value,
                "derivation": derivation,
                "supporting_events": [event_id],
            },
        )
        projection.apply_belief_created(
            conn,
            {
                "belief_id": belief_id,
                "claim_key": claim_key,
                "claim_value": new_value,
                "derivation": derivation,
                "supporting_events": [event_id],
                "_event_created_at": ledger.event_created_at(conn, belief_event_id),
            },
        )
        written.append("belief_created")
    elif current["claim_value"] == new_value:
        confirmation_event_id = ledger.append(
            conn,
            "belief_confirmed",
            {
                "belief_id": int(current["id"]),
                "new_supporting_event": event_id,
            },
        )
        projection.apply_belief_confirmed(
            conn,
            {
                "belief_id": int(current["id"]),
                "new_supporting_event": event_id,
                "_event_created_at": ledger.event_created_at(conn, confirmation_event_id),
            },
        )
        written.append("belief_confirmed")
    else:
        new_belief_id = projection.next_belief_id(conn)
        superseded_payload = {
            "old_belief_id": int(current["id"]),
            "new_belief_id": new_belief_id,
            "claim_key": claim_key,
            "claim_value": new_value,
            "derivation": derivation,
            "supporting_events": [event_id],
            "reason": f"{metric_key}_changed_to_{new_value}",
        }
        superseded_event_id = ledger.append(conn, "belief_superseded", superseded_payload)
        superseded_payload["_event_created_at"] = ledger.event_created_at(
            conn, superseded_event_id
        )
        projection.apply_belief_superseded(conn, superseded_payload)
        written.append("belief_superseded")

    if metric_key == ACTIVITY_METRIC_KEY:
        written.extend(
            _check_activity_expectations(
                conn,
                evidence_id=event_id,
                observed_value=new_value,
            )
        )

    return written


def _latest_evidence_window(conn, metric_key: str = CPU_METRIC_KEY, n: int = WINDOW_SIZE):
    rows = conn.execute(
        """
        SELECT id, json_extract(payload, '$.metric_value') AS metric_value
        FROM event_log
        WHERE event_type = 'evidence_recorded'
          AND json_extract(payload, '$.metric_key') = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (metric_key, n),
    ).fetchall()
    evidence = []
    for row in reversed(rows):
        evidence.append(
            {
                "id": row["id"],
                "metric_value": row["metric_value"],
            }
        )
    return evidence


def _check_activity_expectations(
    conn,
    evidence_id: int,
    observed_value: str,
) -> list[str]:
    from genus import maturation

    hour_row = conn.execute(
        """
        SELECT CAST(strftime('%H', created_at) AS INTEGER) AS hour_utc
        FROM event_log
        WHERE id = ?
        """,
        (evidence_id,),
    ).fetchone()
    if hour_row is None or hour_row["hour_utc"] is None:
        return []

    current = projection.active_belief(conn, RULES[ACTIVITY_METRIC_KEY]["claim_key"])
    if current is None:
        return []

    written: list[str] = []
    for rule in maturation.active_expectations_for_hour(conn, int(hour_row["hour_utc"])):
        expected_value = rule["spec"]["expected_value"]
        if expected_value == observed_value:
            continue
        if _expectation_inquiry_exists(conn, evidence_id, rule["rule_key"]):
            continue
        inquiries.record_inquiry_created_event(
            conn,
            inquiry_id=inquiries.next_inquiry_id(conn),
            inquiry_type="ExpectationInquiry",
            claim_key=rule["subject_key"],
            source_belief=int(current["id"]),
            source_event=evidence_id,
            question_key="expectation.deviation",
            payload={
                "rule_key": rule["rule_key"],
                "rule_id": rule["id"],
                "hour_utc": rule["spec"]["hour_utc"],
                "expected": expected_value,
                "observed": observed_value,
                "evidence_id": evidence_id,
            },
        )
        written.append("inquiry_created")
    return written


def _expectation_inquiry_exists(conn, evidence_id: int, rule_key: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM event_log
        WHERE event_type = 'inquiry_created'
          AND json_extract(payload, '$.source_event') = ?
          AND json_extract(payload, '$.payload.rule_key') = ?
        LIMIT 1
        """,
        (evidence_id, rule_key),
    ).fetchone()
    return row is not None
