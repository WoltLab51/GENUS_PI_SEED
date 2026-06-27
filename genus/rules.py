from __future__ import annotations

import json
import math

from genus import inquiries, ledger, projection, proposals
from genus.proposal_types import ACTIVITY_EXPECTATION_RULE
# The fixed thresholds are the preset budget — collected in one visible place.
from genus.constants import (
    CPU_HIGH_THRESHOLD,
    CPU_LOW_THRESHOLD,
    MEMORY_HIGH_THRESHOLD,
    MEMORY_LOW_THRESHOLD,
    DISK_HIGH_THRESHOLD,
    DISK_LOW_THRESHOLD,
    TEMP_HIGH_THRESHOLD,
    TEMP_LOW_THRESHOLD,
)


WINDOW_SIZE = 3
CPU_METRIC_KEY = "system.cpu_percent"
MEMORY_METRIC_KEY = "system.memory_percent"
DISK_METRIC_KEY = "system.disk_percent"
ACTIVITY_METRIC_KEY = "system.activity"
TEMPERATURE_METRIC_KEY = "system.temperature"
REPO_COMMITS_METRIC_KEY = "repo.commits_per_day"
REPO_LINES_METRIC_KEY = "repo.lines_changed_per_day"
# No imposed magnitude for "heavy": it is judged against this core's own lived
# churn distribution. These two are *form*, not magnitude — "heavy = top
# quartile" and "judge only after a week of own history", not "heavy = N lines".
REPO_CHURN_PERCENTILE = 75
REPO_CHURN_MIN_SAMPLES = 7
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
DISK_TREND_DERIVATION = "rule:disk_trend_v1"
# TREND_WINDOW is form — the horizon the trend is asked over, not a magnitude.
# The threshold for "a real move" is NOT preset: it is this core's own scatter.
TREND_WINDOW = 24
TREND_RISING = "rising"
TREND_STABLE = "stable"
TREND_FALLING = "falling"
WEATHER_TEMP_METRIC_KEY = "weather.temp_outside"
WEATHER_TREND_DERIVATION = "rule:weather_trend_v1"
THERMAL_CORRELATION_DERIVATION = "rule:thermal_correlation_v1"
# Form, not magnitude: "high = top quartile of this core's own readings", judged
# only after a week of own history. What counts as hot/busy is never preset.
THERMAL_PERCENTILE = 75
THERMAL_MIN_SAMPLES = 7
THERMAL_ANOMALOUS = "anomalous"
THERMAL_NORMAL = "normal"

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
        "calibration": {
            "metric": REPO_LINES_METRIC_KEY,
            "percentile": REPO_CHURN_PERCENTILE,
            "min_samples": REPO_CHURN_MIN_SAMPLES,
        },
        "active_value": "heavy",
        "idle_value": "light",
        "claim_key": "repo.churn",
        "derivation": REPO_CHURN_DERIVATION,
    },
}

# A metric may feed more than one belief: TREND_RULES run alongside RULES and
# read the same evidence stream to judge direction over a window, a belief type
# beyond high/normal and binary. A metric can appear in both registries.
TREND_RULES = {
    DISK_METRIC_KEY: {
        "claim_key": "disk.trend",
        "derivation": DISK_TREND_DERIVATION,
        "window": TREND_WINDOW,
    },
    # First external material: outside temperature, fetched by the membrane.
    # Self-calibrated like disk.trend (epsilon = own scatter), so the daily swing
    # is filtered and only a sustained multi-day warming/cooling reads as a trend.
    WEATHER_TEMP_METRIC_KEY: {
        "claim_key": "weather.trend",
        "derivation": WEATHER_TREND_DERIVATION,
        "window": TREND_WINDOW,
    },
}

# Cross-metric: temperature read against CPU. "anomalous" = temperature high
# while CPU is not — both "high" thresholds are this core's own percentiles,
# never imposed. Trains the correlation form the Grundausbildung asks for.
CORRELATION_RULES = {
    TEMPERATURE_METRIC_KEY: {
        "claim_key": "system.thermal",
        "anomalous_value": THERMAL_ANOMALOUS,
        "normal_value": THERMAL_NORMAL,
        "derivation": THERMAL_CORRELATION_DERIVATION,
        "primary": {
            "metric": TEMPERATURE_METRIC_KEY,
            "percentile": THERMAL_PERCENTILE,
            "min_samples": THERMAL_MIN_SAMPLES,
        },
        "secondary": {
            "metric": CPU_METRIC_KEY,
            "percentile": THERMAL_PERCENTILE,
            "min_samples": THERMAL_MIN_SAMPLES,
        },
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
    rule = RULES.get(metric_key)
    if rule is None:
        # Not every metric carries a threshold/binary rule. Some feed only a
        # trend or correlation (weather.temp_outside is the first such metric);
        # those passes handle them. Nothing to judge here.
        return []
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
    calibration = rule.get("calibration")
    if calibration is not None:
        # No imposed magnitude: "heavy" is judged against this core's own lived
        # distribution, computed at read time from prior evidence.
        threshold = _calibrated_threshold(conn, calibration, event_id)
        if threshold is None:
            # Not enough lived history yet to know what is heavy — withhold.
            return []
        new_value = rule["active_value"] if value > threshold else rule["idle_value"]
    else:
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


def apply_trend(conn, metric_key: str) -> list[str]:
    rule = TREND_RULES.get(metric_key)
    if rule is None:
        return []

    window = _latest_evidence_window(conn, metric_key, n=rule["window"])
    if len(window) < rule["window"]:
        # A trend needs a full window before it judges direction.
        return []

    values = [float(row["metric_value"]) for row in window]
    event_ids = [int(row["id"]) for row in window]
    net = values[-1] - values[0]
    # No imposed magnitude: a move counts as a trend only when it is larger than
    # this core's own scatter over the window. A quiet disk notices a small
    # drift; a noisy one needs a bigger move to call it a trend.
    epsilon = _stddev(values)
    if net > epsilon:
        new_value = TREND_RISING
    elif net < -epsilon:
        new_value = TREND_FALLING
    else:
        new_value = TREND_STABLE

    return _record_value_belief(
        conn, rule["claim_key"], rule["derivation"], new_value, event_ids
    )


def apply_correlation(conn, metric_key: str) -> list[str]:
    rule = CORRELATION_RULES.get(metric_key)
    if rule is None:
        return []

    primary_window = _latest_evidence_window(conn, rule["primary"]["metric"], n=1)
    secondary_window = _latest_evidence_window(conn, rule["secondary"]["metric"], n=1)
    if not primary_window or not secondary_window:
        return []

    primary_value = float(primary_window[0]["metric_value"])
    primary_event = int(primary_window[0]["id"])
    secondary_value = float(secondary_window[0]["metric_value"])
    secondary_event = int(secondary_window[0]["id"])

    primary_threshold = _calibrated_threshold(conn, rule["primary"], primary_event)
    secondary_values = _prior_distribution(
        conn, rule["secondary"]["metric"], secondary_event
    )
    if primary_threshold is None or len(secondary_values) < rule["secondary"]["min_samples"]:
        # Not enough lived history yet to know what "high" is — withhold.
        return []
    # Premise of meaning: the correlation only says something if the driver
    # (secondary) actually has a high regime to be decoupled from. With no spread
    # — e.g. an always-idle CPU whose p75 == p25 — "secondary not high" is
    # vacuously true and the verdict would be noise. Withhold rather than cry
    # wolf. (The p75<=p25 test is revisable implementation; the principle is not.)
    if _percentile(secondary_values, 75) <= _percentile(secondary_values, 25):
        return []

    secondary_threshold = _percentile(secondary_values, rule["secondary"]["percentile"])
    primary_high = primary_value > primary_threshold
    secondary_high = secondary_value > secondary_threshold
    new_value = (
        rule["anomalous_value"]
        if primary_high and not secondary_high
        else rule["normal_value"]
    )
    return _record_value_belief(
        conn,
        rule["claim_key"],
        rule["derivation"],
        new_value,
        [secondary_event, primary_event],
    )


# Observation-reactor registry: each reactor reacts to one new observation and
# returns the belief-event types it wrote. process_observation iterates this, so a
# new rule type is added by registering its reactor here, not by hand-writing
# another pass — mirroring the cognition DETECTORS registry. The two registries
# (per-observation reactors here, per-scan detectors in experience.py) are the one
# uniform module pattern, for the eye and the mind.
REACTORS = (apply_threshold, apply_trend, apply_correlation)


def _record_value_belief(
    conn,
    claim_key: str,
    derivation: str,
    new_value: str,
    supporting_events: list[int],
) -> list[str]:
    latest_event = supporting_events[-1]
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
                "supporting_events": supporting_events,
            },
        )
        projection.apply_belief_created(
            conn,
            {
                "belief_id": belief_id,
                "claim_key": claim_key,
                "claim_value": new_value,
                "derivation": derivation,
                "supporting_events": supporting_events,
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
                "new_supporting_event": latest_event,
            },
        )
        projection.apply_belief_confirmed(
            conn,
            {
                "belief_id": int(current["id"]),
                "new_supporting_event": latest_event,
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
            "supporting_events": supporting_events,
            "reason": f"{claim_key}_changed_to_{new_value}",
        }
        superseded_event_id = ledger.append(conn, "belief_superseded", superseded_payload)
        superseded_payload["_event_created_at"] = ledger.event_created_at(
            conn, superseded_event_id
        )
        projection.apply_belief_superseded(conn, superseded_payload)
        written.append("belief_superseded")

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


# Recency bound on the self-calibration scan: percentiles use the most recent
# CALIBRATION_WINDOW prior values, not all of history. This keeps the scan
# O(window) and lets "high"/"heavy" track current conditions instead of being
# anchored to ancient readings. A structural recency bound, not an epistemic preset.
CALIBRATION_WINDOW = 2000


def _prior_distribution(conn, metric_key: str, before_event_id: int) -> list[float]:
    """Sorted recent prior evidence values for a metric — causal (only events
    before this one), bounded to a recency window, the shared basis for read-time,
    replay-stable self-calibration."""
    rows = conn.execute(
        """
        SELECT json_extract(payload, '$.metric_value') AS metric_value
        FROM event_log
        WHERE event_type = 'evidence_recorded'
          AND json_extract(payload, '$.metric_key') = ?
          AND id < ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (metric_key, before_event_id, CALIBRATION_WINDOW),
    ).fetchall()
    return sorted(float(row["metric_value"]) for row in rows)


def _calibrated_threshold(conn, calibration: dict, before_event_id: int):
    """This core's own threshold, learned from its lived ledger — never imposed.

    Returns the chosen percentile of prior evidence for the calibration metric,
    or None when there is not yet enough history to judge. Read-time and causal,
    so the recorded belief stays deterministic and replay-stable.
    """
    values = _prior_distribution(conn, calibration["metric"], before_event_id)
    if len(values) < calibration["min_samples"]:
        return None
    return _percentile(values, calibration["percentile"])


def _percentile(sorted_values: list[float], percentile: float) -> float:
    rank = math.ceil(percentile / 100.0 * len(sorted_values))
    index = min(max(rank, 1), len(sorted_values)) - 1
    return sorted_values[index]


def _stddev(values: list[float]) -> float:
    n = len(values)
    if n == 0:
        return 0.0
    mean = sum(values) / n
    return math.sqrt(sum((value - mean) ** 2 for value in values) / n)


def _check_activity_expectations(
    conn,
    evidence_id: int,
    observed_value: str,
) -> list[str]:
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
    # Read the active expectation rules directly from the shared rule_projection
    # read-model — no import of the maturation module that produced them.
    rules_for_hour = conn.execute(
        """
        SELECT id, rule_key, subject_key, spec
        FROM rule_projection
        WHERE status = 'active' AND rule_type = ?
          AND CAST(json_extract(spec, '$.hour_utc') AS INTEGER) = ?
        ORDER BY id
        """,
        (ACTIVITY_EXPECTATION_RULE, int(hour_row["hour_utc"])),
    ).fetchall()
    for rule in rules_for_hour:
        spec = json.loads(rule["spec"])
        expected_value = spec["expected_value"]
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
                "hour_utc": spec["hour_utc"],
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
