from __future__ import annotations

import json

from genus import experience, ledger, proposals
from genus.proposal_types import ACTIVITY_EXPECTATION_RULE, RULE_PROPOSAL


RULE_TYPE = ACTIVITY_EXPECTATION_RULE
DERIVATION = "maturation:activity_expectation_v1"
PROPOSAL_TYPE = RULE_PROPOSAL
ACTIVE = "active"


def scan(conn) -> list[dict]:
    proposed: list[dict] = []
    for kandidaten_quelle in KANDIDATEN:
        for candidate in kandidaten_quelle(conn):
            if rule_exists(conn, candidate["rule_key"]):
                continue
            rule_event_id = record_rule_proposed_event(conn, candidate)
            proposal_id, proposal_event_id = record_rule_proposal(
                conn,
                candidate,
                rule_event_id,
            )
            proposed.append(
                {
                    "rule_event_id": rule_event_id,
                    "proposal_event_id": proposal_event_id,
                    "proposal_id": proposal_id,
                    **candidate,
                }
            )
    return proposed


def activate_rule(conn, proposal_id: int, override: bool = False) -> dict:
    from genus import governance

    verdict = governance.evaluate_rule_activation(conn, proposal_id, override)
    if verdict["decision"] == governance.BLOCKED:
        return verdict

    proposal = proposals.get_proposal(conn, proposal_id)
    payload = json.loads(proposal["payload"])
    rule_id = next_rule_id(conn)
    event_payload = {
        "rule_id": rule_id,
        "rule_key": payload["rule_key"],
        "rule_type": payload["rule_type"],
        "subject_key": proposal["claim_key"],
        "spec": payload["spec"],
        "source_proposal": proposal_id,
        "derivation": payload.get("derivation", DERIVATION),
    }
    event_id = ledger.append(conn, "rule_activated", event_payload)
    event_payload["_event_created_at"] = ledger.event_created_at(conn, event_id)
    apply_rule_activated(conn, event_payload)
    verdict["rule_event_id"] = event_id
    verdict["rule_id"] = rule_id
    verdict["rule_key"] = payload["rule_key"]
    return verdict


def record_rule_proposed_event(conn, candidate: dict) -> int:
    event_payload = {
        "rule_key": candidate["rule_key"],
        "rule_type": candidate["rule_type"],
        "subject_key": candidate["subject_key"],
        "spec": candidate["spec"],
        "source_experience": candidate["source_experience"],
        "derivation": candidate["derivation"],
        "summary": candidate["summary"],
    }
    return ledger.append(conn, "rule_proposed", event_payload)


def record_rule_proposal(conn, candidate: dict, rule_event_id: int) -> tuple[int, int]:
    proposal_id = proposals.next_proposal_id(conn)
    event_id = proposals.record_proposal_created_event(
        conn,
        proposal_id=proposal_id,
        proposal_type=PROPOSAL_TYPE,
        claim_key=candidate["subject_key"],
        claim_value=RULE_TYPE,
        source_belief=None,
        source_event=rule_event_id,
        payload={
            "description": (
                "Activate rule: expect activity="
                f"{candidate['spec']['expected_value']} around "
                f"{candidate['spec']['hour_utc']:02d}:00 UTC, learned from "
                f"experience #{candidate['source_experience']}"
            ),
            "rule_key": candidate["rule_key"],
            "rule_type": candidate["rule_type"],
            "spec": candidate["spec"],
            "source_experience": candidate["source_experience"],
            "derivation": candidate["derivation"],
            "action_required": False,
            "review_recommended": True,
        },
    )
    return proposal_id, event_id


def apply_rule_activated(conn, payload: dict) -> int:
    conn.execute(
        """
        INSERT INTO rule_projection
            (id, rule_key, rule_type, subject_key, spec, status,
             source_proposal, derivation, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?,
                COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')))
        """,
        (
            int(payload["rule_id"]),
            payload["rule_key"],
            payload["rule_type"],
            payload["subject_key"],
            _json(payload["spec"]),
            ACTIVE,
            int(payload["source_proposal"]),
            payload["derivation"],
            payload.get("_event_created_at"),
        ),
    )
    return int(payload["rule_id"])


def list_rules(conn, active_only: bool = True) -> list[dict]:
    if active_only:
        rows = conn.execute(
            """
            SELECT * FROM rule_projection
            WHERE status = ?
            ORDER BY id
            """,
            (ACTIVE,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT * FROM rule_projection
            ORDER BY CASE WHEN status = 'active' THEN 0 ELSE 1 END, id
            """
        ).fetchall()
    return [rule_dict(row) for row in rows]


def get_rule(conn, rule_id: int):
    row = conn.execute(
        "SELECT * FROM rule_projection WHERE id = ?",
        (rule_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"rule not found: {rule_id}")
    return row


def rule_exists(conn, rule_key: str) -> bool:
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
        WHERE event_type IN ('rule_proposed', 'rule_activated')
          AND json_extract(payload, '$.rule_key') = ?
        LIMIT 1
        """,
        (rule_key,),
    ).fetchone()
    return event_row is not None


def next_rule_id(conn) -> int:
    row = conn.execute(
        "SELECT seq FROM sqlite_sequence WHERE name = 'rule_projection'"
    ).fetchone()
    if row is not None:
        return int(row["seq"]) + 1
    row = conn.execute(
        "SELECT COALESCE(MAX(id), 0) AS max_id FROM rule_projection"
    ).fetchone()
    return int(row["max_id"]) + 1


def rule_dict(row) -> dict:
    data = dict(row)
    data["spec"] = json.loads(row["spec"])
    return data


def _activity_expectation_candidates(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM experience_log
        WHERE experience_type = ?
          AND subject_key = ?
        ORDER BY id
        """,
        (experience.EXPERIENCE_TYPE, experience.ACTIVITY_METRIC_KEY),
    ).fetchall()
    candidates: list[dict] = []
    for row in rows:
        data = experience.experience_dict(row)
        pattern = data["pattern"]
        expected_value = pattern["value"]
        for hour in pattern["hours_utc"]:
            hour_int = int(hour)
            rule_key = (
                f"activity_expectation:{data['subject_key']}:"
                f"{hour_int:02d}:{expected_value}"
            )
            spec = {
                "hour_utc": hour_int,
                "expected_value": expected_value,
            }
            candidates.append(
                {
                    "rule_key": rule_key,
                    "rule_type": RULE_TYPE,
                    "subject_key": data["subject_key"],
                    "spec": spec,
                    "source_experience": int(data["id"]),
                    "derivation": DERIVATION,
                    "summary": (
                        f"Expect {data['subject_key']}={expected_value} "
                        f"during UTC hour {hour_int:02d}:00"
                    ),
                }
            )
    return candidates


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


# Kandidaten-Registry: jede Quelle ist eine reine Funktion conn -> list[candidate] --
# dasselbe Muster wie rules.REACTORS (pro Beobachtung) und experience.DETECTORS (pro
# Scan), Phase 1 der Ziel-Architektur: eine neue Reifungs-Art wird REGISTRIERT, nicht
# in scan() hineingeschrieben. Bisher war maturation das eine Geschwister-Modul ohne
# diese Form (ein hart verdrahteter Aufruf mitten in scan).
KANDIDATEN = (_activity_expectation_candidates,)
