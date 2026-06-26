from __future__ import annotations

import json
from collections import Counter, defaultdict

from genus import inquiries, ledger, proposals


ACTIVITY_METRIC_KEY = "system.activity"
DERIVATION = "rule:activity_daily_rhythm_v1"
EXPERIENCE_TYPE = "ActivityDailyRhythm"
PROPOSAL_TYPE = "ExperienceProposal"
MIN_SUPPORT = 3
MIN_BUCKET_RATIO = 0.75
MIN_GLOBAL_CONTRAST = 0.25
MAX_PROPOSALS_PER_SCAN = 1

# BeliefStability: the first experience about GENUS's own cognition rather than a
# sensor metric. It measures how volatile each belief is from its lifecycle.
BELIEF_STABILITY_TYPE = "BeliefStability"
BELIEF_STABILITY_DERIVATION = "rule:belief_stability_v1"
MIN_LIFECYCLE_UPDATES = 10  # premise of meaning: enough lifecycle to judge volatility

# Closing the expect-then-be-surprised loop: a belief characterized as stable
# that subsequently flips is a violated expectation.
STABILITY_INQUIRY_TYPE = "StabilityInquiry"
STABILITY_QUESTION_KEY = "stability.unexpected_flip"


def scan(conn) -> list[dict]:
    # The mind grows by registering detectors, not by rewriting scan. Each is a
    # pure function conn -> candidates, mirroring how RULES/TREND_RULES/
    # CORRELATION_RULES make the eye's growth structural.
    recorded: list[dict] = []
    proposals_created = 0
    for detector in DETECTORS:
        for candidate in detector(conn):
            existing = _active_experience(conn, candidate["experience_key"])
            if existing is not None:
                # The experience already exists; re-characterize it in place if its
                # characterization changed (a belief that was stable now reads
                # volatile), else leave it. Keeps self-knowledge current.
                event_id = _maybe_recharacterize(conn, existing, candidate)
                if event_id is not None:
                    recorded.append(
                        {"experience_event_id": event_id, "recharacterized": True, **candidate}
                    )
                continue
            experience_event_id = record_experience_event(conn, candidate)
            proposal_event_id = None
            if candidate.get("proposable") and proposals_created < MAX_PROPOSALS_PER_SCAN:
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
    _raise_stability_surprises(conn)
    return recorded


def _active_experience(conn, experience_key: str):
    # experience_key is UNIQUE, so there is at most one row.
    return conn.execute(
        "SELECT * FROM experience_log WHERE experience_key = ?",
        (experience_key,),
    ).fetchone()


def _maybe_recharacterize(conn, existing, candidate: dict):
    # Re-characterize when the candidate's characterization differs from what is
    # recorded. Candidates without a 'characterization' (e.g. the activity rhythm)
    # never re-characterize, preserving the record-once behaviour. Returns the
    # event id if it re-recorded, else None.
    new_char = candidate.get("characterization")
    if new_char is None:
        return None
    old_char = json.loads(existing["pattern"]).get("classification")
    if new_char == old_char:
        return None
    return record_experience_recharacterized_event(conn, int(existing["id"]), candidate)


def record_experience_recharacterized_event(conn, experience_id: int, candidate: dict) -> int:
    payload = {
        "experience_id": experience_id,
        "experience_key": candidate["experience_key"],
        "pattern": candidate["pattern"],
        "supporting_events": candidate["supporting_events"],
        "summary": candidate["summary"],
        "reason": f"{candidate['subject_key']}_recharacterized",
    }
    event_id = ledger.append(conn, "experience_recharacterized", payload)
    payload["_event_created_at"] = ledger.event_created_at(conn, event_id)
    apply_experience_recharacterized(conn, payload)
    return event_id


def apply_experience_recharacterized(conn, payload: dict) -> None:
    # Update the existing experience in place (experience_key stays unique). The
    # full history of characterizations remains in event_log; the projection holds
    # the current one. Replay re-applies this deterministically.
    conn.execute(
        """
        UPDATE experience_log
        SET pattern = ?, supporting_events = ?, summary = ?
        WHERE id = ?
        """,
        (
            json.dumps(payload["pattern"], sort_keys=True, separators=(",", ":")),
            json.dumps(payload["supporting_events"], sort_keys=True, separators=(",", ":")),
            payload["summary"],
            int(payload["experience_id"]),
        ),
    )


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
                "proposable": True,
            }
        )
    return candidates


def _format_hours(hours: list[int]) -> str:
    return ", ".join(f"{hour:02d}:00" for hour in hours)


def _belief_stability_candidates(conn) -> list[dict]:
    # GENUS reflects on its own beliefs: how volatile is each, measured from its
    # lifecycle in the ledger. flip_rate = supersessions / (confirmations +
    # supersessions). A rock-stable belief flips ~never; a volatile one flips
    # often. This is the first experience whose subject is GENUS's own cognition.
    rows = conn.execute(
        """
        SELECT id, event_type, payload
        FROM event_log
        WHERE event_type IN ('belief_created', 'belief_confirmed', 'belief_superseded')
        ORDER BY id
        """
    ).fetchall()
    if not rows:
        return []

    id_to_key: dict[int, str] = {}
    confirms: dict[str, int] = defaultdict(int)
    flips: dict[str, int] = defaultdict(int)
    events: dict[str, list[int]] = defaultdict(list)

    for row in rows:
        payload = json.loads(row["payload"])
        event_id = int(row["id"])
        if row["event_type"] == "belief_created":
            key = payload["claim_key"]
            id_to_key[int(payload["belief_id"])] = key
            events[key].append(event_id)
        elif row["event_type"] == "belief_superseded":
            key = payload["claim_key"]
            id_to_key[int(payload["new_belief_id"])] = key
            flips[key] += 1
            events[key].append(event_id)
        else:  # belief_confirmed carries belief_id only; map it to its claim_key
            key = id_to_key.get(int(payload["belief_id"]))
            if key is None:
                continue
            confirms[key] += 1
            events[key].append(event_id)

    # Flip-rate per belief that has enough lifecycle to judge (premise of meaning).
    rates: dict[str, float] = {}
    for key in set(confirms) | set(flips):
        updates = confirms[key] + flips[key]
        if updates < MIN_LIFECYCLE_UPDATES:
            continue
        rates[key] = flips[key] / updates

    # A relative "volatile/stable" verdict needs a spread to judge against. With
    # fewer than two qualifying beliefs or no spread, withhold (premise of meaning).
    if len(rates) < 2:
        return []
    ordered = sorted(rates.values())
    if ordered[-1] <= ordered[0]:
        return []
    median = _median(ordered)

    candidates = []
    for key in sorted(rates):
        rate = rates[key]
        updates = confirms[key] + flips[key]
        classification = "volatile" if rate > median else "stable"
        candidates.append(
            {
                "experience_key": f"belief_stability:{key}",
                "experience_type": BELIEF_STABILITY_TYPE,
                "subject_key": key,
                "pattern": {
                    "flip_rate": round(rate, 3),
                    "confirmations": confirms[key],
                    "supersessions": flips[key],
                    "updates": updates,
                    "classification": classification,
                    "population_median": round(median, 3),
                },
                "supporting_events": events[key],
                "derivation": BELIEF_STABILITY_DERIVATION,
                "summary": (
                    f"{key} is {classification} (flip-rate {rate:.2f} over "
                    f"{updates} lifecycle updates; GENUS-median {median:.2f})"
                ),
                "proposable": False,
                # re-characterize the experience if this verdict later changes
                "characterization": classification,
            }
        )
    return candidates


def _raise_stability_surprises(conn) -> list[int]:
    # Close the expect-then-be-surprised loop. A belief GENUS characterized as
    # stable that flips AFTER that characterization is a violated expectation:
    # raise one StabilityInquiry per such flip. A volatile belief flipping is no
    # surprise, so only 'stable' experiences are watched. The frozen experience is
    # the expectation; a later belief_superseded for the same claim is the
    # falsification. One inquiry per flip event (deduped by source_event), so the
    # detection is idempotent and replay re-applies the inquiry_created events.
    raised: list[int] = []
    stable = conn.execute(
        """
        SELECT subject_key, supporting_events
        FROM experience_log
        WHERE experience_type = ?
          AND json_extract(pattern, '$.classification') = 'stable'
        """,
        (BELIEF_STABILITY_TYPE,),
    ).fetchall()
    for row in stable:
        claim_key = row["subject_key"]
        supporting = json.loads(row["supporting_events"])
        as_of = max(supporting) if supporting else 0
        flips = conn.execute(
            """
            SELECT id, payload
            FROM event_log
            WHERE event_type = 'belief_superseded'
              AND json_extract(payload, '$.claim_key') = ?
              AND id > ?
            ORDER BY id
            """,
            (claim_key, as_of),
        ).fetchall()
        for flip in flips:
            flip_id = int(flip["id"])
            if _stability_inquiry_exists(conn, flip_id):
                continue
            payload = json.loads(flip["payload"])
            inquiries.record_inquiry_created_event(
                conn,
                inquiry_id=inquiries.next_inquiry_id(conn),
                inquiry_type=STABILITY_INQUIRY_TYPE,
                claim_key=claim_key,
                source_belief=int(payload["new_belief_id"]),
                source_event=flip_id,
                question_key=STABILITY_QUESTION_KEY,
                payload={
                    "expected": "stable",
                    "observed": "flipped",
                    "changed_to": payload.get("claim_value"),
                    "review_recommended": True,
                },
            )
            raised.append(flip_id)
    return raised


def _stability_inquiry_exists(conn, source_event: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM inquiry_log WHERE inquiry_type = ? AND source_event = ? LIMIT 1",
        (STABILITY_INQUIRY_TYPE, source_event),
    ).fetchone()
    return row is not None


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


# Cognition detector registry: each is a pure function conn -> candidates.
DETECTORS = (_activity_daily_rhythm_candidates, _belief_stability_candidates)
