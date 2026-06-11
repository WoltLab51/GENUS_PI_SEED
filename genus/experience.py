from __future__ import annotations

import json
from collections import Counter, defaultdict

from genus import ledger, proposals


ACTIVITY_METRIC_KEY = "system.activity"
DERIVATION = "rule:activity_daily_rhythm_v1"
EXPERIENCE_TYPE = "ActivityDailyRhythm"
PROPOSAL_TYPE = "ExperienceProposal"
MIN_SUPPORT = 3
MIN_BUCKET_RATIO = 0.75
MIN_GLOBAL_CONTRAST = 0.25
MAX_PROPOSALS_PER_SCAN = 1


def scan(conn) -> list[dict]:
    recorded: list[dict] = []
    proposals_created = 0
    for candidate in _activity_daily_rhythm_candidates(conn):
        if experience_exists(conn, candidate["experience_key"]):
            continue
        experience_event_id = record_experience_event(conn, candidate)
        proposal_event_id = None
        if proposals_created < MAX_PROPOSALS_PER_SCAN:
            proposal_event_id = record_experience_proposal(
                conn,
                candidate,
                experience_event_id,
            )
            proposals_created += 1
        recorded.append(
            {
                "experience_event_id": experience_event_id,
                "proposal_event_id": proposal_event_id,
                **candidate,
            }
        )
    return recorded


def record_experience_event(conn, candidate: dict) -> int:
    experience_id = next_experience_id(conn)
    candidate["experience_id"] = experience_id
    event_payload = {
        "experience_id": experience_id,
        "experience_key": candidate["experience_key"],
        "experience_type": candidate["experience_type"],
        "subject_key": candidate["subject_key"],
        "pattern": candidate["pattern"],
        "supporting_events": candidate["supporting_events"],
        "derivation": candidate["derivation"],
        "summary": candidate["summary"],
    }
    event_id = ledger.append(conn, "experience_recorded", event_payload)
    event_payload["_event_created_at"] = ledger.event_created_at(conn, event_id)
    apply_experience_recorded(conn, event_payload)
    return event_id


def record_experience_proposal(conn, candidate: dict, experience_event_id: int) -> int:
    return proposals.record_proposal_created_event(
        conn,
        proposal_id=proposals.next_proposal_id(conn),
        proposal_type=PROPOSAL_TYPE,
        claim_key=candidate["subject_key"],
        claim_value="daily_rhythm",
        source_belief=None,
        source_event=experience_event_id,
        payload={
            "description": (
                f"Recurring experience detected: {candidate['summary']}. "
                "Review whether this rhythm is expected."
            ),
            "observed_pattern": candidate["experience_key"],
            "experience_id": candidate["experience_id"],
            "experience_key": candidate["experience_key"],
            "experience_type": candidate["experience_type"],
            "action_required": False,
            "review_recommended": True,
        },
    )


def apply_experience_recorded(conn, payload: dict) -> int:
    serialized_pattern = json.dumps(
        payload["pattern"], sort_keys=True, separators=(",", ":")
    )
    serialized_supporting = json.dumps(
        payload["supporting_events"], sort_keys=True, separators=(",", ":")
    )
    conn.execute(
        """
        INSERT INTO experience_log
            (id, experience_key, experience_type, subject_key, pattern,
             supporting_events, derivation, summary, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?,
                COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')))
        """,
        (
            int(payload["experience_id"]),
            payload["experience_key"],
            payload["experience_type"],
            payload["subject_key"],
            serialized_pattern,
            serialized_supporting,
            payload["derivation"],
            payload["summary"],
            payload.get("_event_created_at"),
        ),
    )
    return int(payload["experience_id"])


def list_experiences(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM experience_log ORDER BY id").fetchall()
    return [experience_dict(row) for row in rows]


def get_experience(conn, experience_id: int):
    row = conn.execute(
        "SELECT * FROM experience_log WHERE id = ?",
        (experience_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"experience not found: {experience_id}")
    return row


def experience_dict(row) -> dict:
    data = dict(row)
    data["pattern"] = json.loads(row["pattern"])
    data["supporting_events"] = json.loads(row["supporting_events"])
    return data


def experience_exists(conn, experience_key: str) -> bool:
    projection_row = conn.execute(
        "SELECT 1 FROM experience_log WHERE experience_key = ? LIMIT 1",
        (experience_key,),
    ).fetchone()
    if projection_row is not None:
        return True
    event_row = conn.execute(
        """
        SELECT 1
        FROM event_log
        WHERE event_type = 'experience_recorded'
          AND json_extract(payload, '$.experience_key') = ?
        LIMIT 1
        """,
        (experience_key,),
    ).fetchone()
    return event_row is not None


def next_experience_id(conn) -> int:
    row = conn.execute(
        "SELECT seq FROM sqlite_sequence WHERE name = 'experience_log'"
    ).fetchone()
    if row is not None:
        return int(row["seq"]) + 1
    row = conn.execute(
        "SELECT COALESCE(MAX(id), 0) AS max_id FROM experience_log"
    ).fetchone()
    return int(row["max_id"]) + 1


def _activity_daily_rhythm_candidates(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            id,
            CAST(strftime('%H', created_at) AS INTEGER) AS hour_utc,
            CASE
                WHEN CAST(json_extract(payload, '$.metric_value') AS REAL) >= 1.0
                THEN 'active'
                ELSE 'idle'
            END AS activity_value
        FROM event_log
        WHERE event_type = 'evidence_recorded'
          AND json_extract(payload, '$.metric_key') = ?
        ORDER BY id
        """,
        (ACTIVITY_METRIC_KEY,),
    ).fetchall()
    if not rows:
        return []

    global_counts: Counter[str] = Counter()
    hourly_counts: dict[int, Counter[str]] = defaultdict(Counter)
    hourly_events: dict[tuple[int, str], list[int]] = defaultdict(list)
    for row in rows:
        value = row["activity_value"]
        hour = int(row["hour_utc"])
        global_counts[value] += 1
        hourly_counts[hour][value] += 1
        hourly_events[(hour, value)].append(int(row["id"]))

    total_observations = sum(global_counts.values())
    contrasting_hours: dict[str, list[dict]] = defaultdict(list)
    for hour in sorted(hourly_counts):
        hour_total = sum(hourly_counts[hour].values())
        for value, count in hourly_counts[hour].items():
            if count < MIN_SUPPORT:
                continue
            bucket_ratio = count / hour_total
            global_ratio = global_counts[value] / total_observations
            contrast = bucket_ratio - global_ratio
            if bucket_ratio < MIN_BUCKET_RATIO or contrast < MIN_GLOBAL_CONTRAST:
                continue
            contrasting_hours[value].append(
                {
                    "hour_utc": hour,
                    "count": count,
                    "bucket_ratio": round(bucket_ratio, 3),
                    "global_ratio": round(global_ratio, 3),
                    "contrast": round(contrast, 3),
                    "supporting_events": hourly_events[(hour, value)],
                }
            )

    candidates = []
    for value in sorted(contrasting_hours):
        hours = contrasting_hours[value]
        supporting_events = [
            event_id
            for hour_data in hours
            for event_id in hour_data["supporting_events"]
        ]
        total_count = sum(hour_data["count"] for hour_data in hours)
        hours_utc = [hour_data["hour_utc"] for hour_data in hours]
        experience_key = f"activity_daily_rhythm:{ACTIVITY_METRIC_KEY}:{value}"
        pattern = {
            "bucket": "hour_of_day_utc",
            "value": value,
            "hours_utc": hours_utc,
            "count": total_count,
            "contrasting_hours": hours,
        }
        candidates.append(
            {
                "experience_key": experience_key,
                "experience_type": EXPERIENCE_TYPE,
                "subject_key": ACTIVITY_METRIC_KEY,
                "pattern": pattern,
                "supporting_events": supporting_events,
                "derivation": DERIVATION,
                "summary": (
                    f"{ACTIVITY_METRIC_KEY} is disproportionately {value} "
                    f"during UTC hour(s) {_format_hours(hours_utc)} "
                    f"({total_count} contrasting observations)"
                ),
            }
        )
    return candidates


def _format_hours(hours: list[int]) -> str:
    return ", ".join(f"{hour:02d}:00" for hour in hours)
