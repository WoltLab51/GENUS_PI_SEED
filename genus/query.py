from __future__ import annotations

import json
import math
import string

from genus import (
    db,
    experience,
    governance,
    inquiries,
    maturation,
    operation,
    projection,
    proposals,
    state,
)


BELIEF_PATTERNS = (
    "was glaubst",
    "what do you believe",
    "beliefs",
    "glauben",
)
PROPOSAL_PATTERNS = (
    "was schlaegst",
    "was schlagst",
    "what do you propose",
    "proposals",
    "vorschlaege",
    "vorschlage",
)
INQUIRY_PATTERNS = (
    "was ist offen",
    "what is open",
    "inquiries",
    "questions",
    "fragen",
)
EXPERIENCE_PATTERNS = (
    "experience",
    "experiences",
    "erfahrung",
    "muster",
    "pattern",
    "rhythmus",
)
STATE_PATTERNS = (
    "state",
    "state vector",
    "gesamtzustand",
    "zustand",
    "pressure",
    "druck",
)
GOVERNANCE_PATTERNS = (
    "governance",
    "entscheidungen",
    "decisions",
    "decision",
    "policy",
    "policies",
)
RULE_PATTERNS = (
    "rules",
    "rule",
    "regeln",
    "regel",
)
OPERATION_PATTERNS = (
    "operation",
    "operations",
    "betrieb",
    "watchdog",
    "netzwerk",
    "network",
)
STATUS_PATTERNS = (
    "status",
    "summary",
    "zusammenfassung",
)
SUPPORTED_PATTERNS = (
    'ask "was glaubst du"',
    'ask "status"',
    'ask "welche proposals"',
    'ask "was ist offen"',
    'ask "welche muster"',
    'ask "zustand"',
    'ask "governance"',
    'ask "regeln"',
    'ask "betrieb"',
)


def ask(conn, question: str) -> dict:
    normalized = _normalize(question)
    if _matches(normalized, BELIEF_PATTERNS):
        beliefs = projection.list_active_beliefs(conn)
        return {
            "kind": "active_beliefs",
            "question": question,
            "answer": f"{len(beliefs)} active belief(s)",
            "beliefs": beliefs,
        }
    if _matches(normalized, PROPOSAL_PATTERNS):
        rows = proposals.list_proposals(conn, include_all=False)
        return {
            "kind": "pending_proposals",
            "question": question,
            "answer": f"{len(rows)} pending proposal(s)",
            "proposals": rows,
        }
    if _matches(normalized, INQUIRY_PATTERNS):
        rows = inquiries.list_inquiries(conn, include_all=False)
        return {
            "kind": "open_inquiries",
            "question": question,
            "answer": f"{len(rows)} open inquiry/inquiries",
            "inquiries": rows,
        }
    if _matches(normalized, EXPERIENCE_PATTERNS):
        rows = experience.list_experiences(conn)
        return {
            "kind": "experiences",
            "question": question,
            "answer": f"{len(rows)} experience(s)",
            "experiences": rows,
        }
    if _matches(normalized, STATE_PATTERNS):
        rows = state.list_active_states(conn)
        return {
            "kind": "states",
            "question": question,
            "answer": f"{len(rows)} active state(s)",
            "states": rows,
        }
    if _matches(normalized, GOVERNANCE_PATTERNS):
        rows = governance.list_decisions(conn)
        return {
            "kind": "governance_decisions",
            "question": question,
            "answer": f"{len(rows)} governance decision(s)",
            "governance_decisions": rows,
        }
    if _matches(normalized, RULE_PATTERNS):
        rows = maturation.list_rules(conn)
        return {
            "kind": "rules",
            "question": question,
            "answer": f"{len(rows)} active rule(s)",
            "rules": rows,
        }
    if _matches(normalized, OPERATION_PATTERNS):
        rows = operation.list_operations(conn)
        return {
            "kind": "operations",
            "question": question,
            "answer": f"{len(rows)} operation record(s)",
            "operations": rows,
        }
    if _matches(normalized, STATUS_PATTERNS):
        return {
            "kind": "status",
            "question": question,
            "answer": "current projection summary",
            "status": status(conn),
        }
    return {
        "kind": "unknown",
        "question": question,
        "answer": "Das kann GENUS nicht einordnen — kein bekannter Befehl, kein gelerntes Wort.",
        "supported": list(SUPPORTED_PATTERNS),
    }


def calibration(conn) -> dict:
    # Read-time honesty check: are GENUS's own stability judgments borne out? A
    # belief it characterised "stable" is a high-confidence prediction ("this will
    # not flip"); the held-rate is that prediction's empirical accuracy, and the
    # mean flip-rate gap is whether the judgment actually separates stable from
    # volatile. Aggregated from existing experiences + stability surprises -- no new
    # state, computed read-time like every other magnitude. The seed of "does GENUS
    # know that it knows" (Bayesian calibration, applied to its self-characterisation).
    rows = conn.execute(
        "SELECT subject_key, pattern FROM experience_log WHERE experience_type = ?",
        (experience.BELIEF_STABILITY_TYPE,),
    ).fetchall()
    stable: dict[str, float] = {}
    volatile: dict[str, float] = {}
    for row in rows:
        pattern = json.loads(row["pattern"])
        bucket = stable if pattern.get("classification") == "stable" else volatile
        bucket[row["subject_key"]] = float(pattern.get("flip_rate", 0.0))
    surprised = {
        row["claim_key"]
        for row in conn.execute(
            "SELECT DISTINCT claim_key FROM inquiry_log WHERE inquiry_type = ?",
            (experience.STABILITY_INQUIRY_TYPE,),
        ).fetchall()
    }
    betrayed = sorted(key for key in stable if key in surprised)
    stable_n = len(stable)
    return {
        "stable_count": stable_n,
        "volatile_count": len(volatile),
        "betrayed": betrayed,
        "stable_judgment_accuracy": (
            (stable_n - len(betrayed)) / stable_n if stable_n else None
        ),
        "stable_mean_flip_rate": (sum(stable.values()) / stable_n if stable_n else None),
        "volatile_mean_flip_rate": (
            sum(volatile.values()) / len(volatile) if volatile else None
        ),
    }


def surprisal(conn) -> list[dict]:
    # Information-theoretic surprise (Shannon): how many bits would a flip of each
    # belief carry? surprisal = -log2(p_flip), with p_flip Laplace-smoothed from the
    # belief's own lifecycle ((flips + 0.5) / (updates + 1)) so a never-flipping
    # belief has a finite, large surprise potential. A rock-stable belief flipping is
    # shocking (many bits); a volatile one flipping is expected (few). Lets GENUS rank
    # where a surprise would teach it the most -- the seed of "learn the
    # high-information thing first". Read-time, from existing experiences.
    rows = conn.execute(
        "SELECT subject_key, pattern FROM experience_log WHERE experience_type = ?",
        (experience.BELIEF_STABILITY_TYPE,),
    ).fetchall()
    out = []
    for row in rows:
        pattern = json.loads(row["pattern"])
        updates = int(pattern.get("updates", 0))
        flips = int(pattern.get("supersessions", 0))
        p_flip = (flips + 0.5) / (updates + 1)
        out.append(
            {
                "subject_key": row["subject_key"],
                "classification": pattern.get("classification"),
                "flip_rate": float(pattern.get("flip_rate", 0.0)),
                "updates": updates,
                "surprise_bits": -math.log2(p_flip),
            }
        )
    out.sort(key=lambda r: r["surprise_bits"], reverse=True)
    return out


def status(conn) -> dict:
    event_count = conn.execute("SELECT COUNT(*) AS count FROM event_log").fetchone()[
        "count"
    ]
    metrics = db.ledger_metrics(conn, event_count=int(event_count))
    active_beliefs = projection.list_active_beliefs(conn)
    active_count = len(active_beliefs)
    epistemic_counts = {
        state: sum(1 for belief in active_beliefs if belief["epistemic_state"] == state)
        for state in (projection.SUPPORTED, projection.CONTESTED, projection.UNCERTAIN)
    }
    superseded_count = conn.execute(
        "SELECT COUNT(*) AS count FROM belief_projection WHERE state = ?",
        (projection.SUPERSEDED,),
    ).fetchone()["count"]
    proposal_count = conn.execute(
        "SELECT COUNT(*) AS count FROM proposal_log WHERE state = 'pending'"
    ).fetchone()["count"]
    inquiry_count = conn.execute(
        "SELECT COUNT(*) AS count FROM inquiry_log WHERE state = 'open'"
    ).fetchone()["count"]
    inquiry_claim_count = conn.execute(
        """SELECT COUNT(*) AS count FROM (
               SELECT inquiry_type, claim_key FROM inquiry_log
               WHERE state = 'open' GROUP BY inquiry_type, claim_key
           )"""
    ).fetchone()["count"]
    experience_count = conn.execute(
        "SELECT COUNT(*) AS count FROM experience_log"
    ).fetchone()["count"]
    active_state_count = conn.execute(
        "SELECT COUNT(*) AS count FROM state_projection WHERE status = 'active'"
    ).fetchone()["count"]
    governance_count = conn.execute(
        "SELECT COUNT(*) AS count FROM governance_log"
    ).fetchone()["count"]
    active_rule_count = conn.execute(
        "SELECT COUNT(*) AS count FROM rule_projection WHERE status = 'active'"
    ).fetchone()["count"]
    operation_count = conn.execute(
        "SELECT COUNT(*) AS count FROM operation_log"
    ).fetchone()["count"]
    return {
        "events": int(event_count),
        "active_beliefs": int(active_count),
        "supported_beliefs": epistemic_counts[projection.SUPPORTED],
        "contested_beliefs": epistemic_counts[projection.CONTESTED],
        "uncertain_beliefs": epistemic_counts[projection.UNCERTAIN],
        "superseded_beliefs": int(superseded_count),
        "pending_proposals": int(proposal_count),
        "open_inquiries": int(inquiry_count),
        "open_inquiry_claims": int(inquiry_claim_count),
        "experiences": int(experience_count),
        "active_states": int(active_state_count),
        "governance_decisions": int(governance_count),
        "operations": int(operation_count),
        "active_rules": int(active_rule_count),
        "ledger_storage_bytes": metrics["storage_bytes"],
        "ledger_main_bytes": metrics["main_bytes"],
        "ledger_wal_bytes": metrics["wal_bytes"],
        "ledger_free_bytes": metrics["free_bytes"],
        "ledger_bytes_per_event": metrics["bytes_per_event"],
        "ledger_events_24h": metrics["events_24h"],
        "ledger_events_7d": metrics["events_7d"],
        "ledger_estimated_daily_growth_bytes": metrics[
            "estimated_daily_growth_bytes"
        ],
    }


def explain_belief(conn, belief_id: int) -> dict:
    row = projection.get_belief(conn, belief_id)
    belief = projection.belief_with_confidence(conn, row)
    supporting_ids = projection.json_list(row["supporting_events"])
    contradicting_ids = projection.json_list(row["contradicting_events"])
    return {
        "belief": belief,
        "created_by": _find_belief_creation_event(conn, belief_id),
        "supporting_evidence": [
            _event_with_observation(conn, event_id) for event_id in supporting_ids
        ],
        "contradicting_evidence": [
            _event_with_observation(conn, event_id) for event_id in contradicting_ids
        ],
        "transition_events": _find_belief_transition_events(conn, belief_id),
    }


def explain_proposal(conn, proposal_id: int) -> dict:
    proposal = _get_proposal(conn, proposal_id)
    source_belief_id = proposal["source_belief"]
    source_event = _event_with_observation(conn, int(proposal["source_event"]))
    source_experience_id = (
        source_event["payload"].get("source_experience")
        if source_event["event_type"] == "rule_proposed"
        else None
    )
    return {
        "proposal": dict(proposal),
        "proposal_event": _find_proposal_event(conn, proposal_id),
        "review_event": _find_proposal_review_event(conn, proposal_id),
        "source_event": source_event,
        "source_belief": (
            explain_belief(conn, int(source_belief_id))
            if source_belief_id is not None
            else None
        ),
        "source_experience": (
            explain_experience(conn, int(source_experience_id))
            if source_experience_id is not None
            else None
        ),
    }


def explain_experience(conn, experience_id: int) -> dict:
    row = experience.get_experience(conn, experience_id)
    data = experience.experience_dict(row)
    supporting_ids = data["supporting_events"]
    return {
        "experience": data,
        "experience_event": _find_experience_event(conn, experience_id),
        "supporting_evidence": [
            _event_with_observation(conn, event_id) for event_id in supporting_ids
        ],
        "proposals": _find_experience_proposals(conn, experience_id),
    }


def explain_state(conn, state_id: int) -> dict:
    row = state.get_state(conn, state_id)
    data = state.state_dict(row)
    supporting_ids = data["supporting_beliefs"]
    return {
        "state": data,
        "state_event": _find_state_event(conn, state_id),
        "supporting_beliefs": [
            projection.belief_with_confidence(
                conn,
                projection.get_belief(conn, belief_id),
            )
            for belief_id in supporting_ids
        ],
    }


def explain_decision(conn, decision_id: int) -> dict:
    row = governance.get_decision(conn, decision_id)
    return {
        "decision": governance.decision_dict(row),
        "governance_event": _find_governance_decision_event(conn, decision_id),
        "constraint_events": _find_governance_audit_events(
            conn,
            decision_id,
            "constraint_checked",
        ),
        "policy_events": _find_governance_audit_events(
            conn,
            decision_id,
            "policy_evaluated",
        ),
    }


def explain_rule(conn, rule_id: int) -> dict:
    row = maturation.get_rule(conn, rule_id)
    rule = maturation.rule_dict(row)
    source_proposal = _get_proposal(conn, int(rule["source_proposal"]))
    rule_event = _find_rule_activated_event(conn, rule_id)
    rule_proposed_event = _event_with_observation(conn, int(source_proposal["source_event"]))
    source_experience_id = rule_proposed_event["payload"].get("source_experience")
    return {
        "rule": rule,
        "rule_event": rule_event,
        "source_proposal": dict(source_proposal),
        "rule_proposed_event": rule_proposed_event,
        "source_experience": (
            explain_experience(conn, int(source_experience_id))
            if source_experience_id is not None
            else None
        ),
    }


def _normalize(value: str) -> str:
    lowered = value.casefold()
    translated = lowered.translate(str.maketrans("äöüß", "aous"))
    return translated.translate(str.maketrans("", "", string.punctuation)).strip()


def _matches(question: str, patterns: tuple[str, ...]) -> bool:
    """Fixed patterns are terse COMMANDS, not conversation. A multi-word phrase ("was ist
    offen") is specific enough to match anywhere in the question; a single word ("status",
    "netzwerk", "fragen") matches only when the question itself is command-like -- at most two
    tokens, with the pattern as a whole token. Plain substring matching hijacked natural
    questions ("Was ist ein Netzwerk?" got the operations count instead of the word the
    companion knows) -- the same shadowing class as the learned word "Status" once hiding the
    status command, now closed from both directions."""
    tokens = question.split()
    for pattern in patterns:
        if " " in pattern:
            if pattern in question:
                return True
        elif len(tokens) <= 2 and pattern in tokens:
            return True
    return False


def _get_event(conn, event_id: int) -> dict:
    row = conn.execute("SELECT * FROM event_log WHERE id = ?", (event_id,)).fetchone()
    if row is None:
        raise ValueError(f"event not found: {event_id}")
    return _event_dict(row)


def _event_with_observation(conn, event_id: int) -> dict:
    event = _get_event(conn, event_id)
    observation_id = event["payload"].get("observation_id")
    if observation_id is not None:
        event["observation"] = _get_event(conn, int(observation_id))
    return event


def _event_dict(row) -> dict:
    return {
        "id": row["id"],
        "event_type": row["event_type"],
        "payload": json.loads(row["payload"]),
        "created_at": row["created_at"],
    }


def _find_belief_creation_event(conn, belief_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT * FROM event_log
        WHERE (
            event_type = 'belief_created'
            AND json_extract(payload, '$.belief_id') = ?
        ) OR (
            event_type = 'belief_superseded'
            AND json_extract(payload, '$.new_belief_id') = ?
        )
        ORDER BY id
        LIMIT 1
        """,
        (belief_id, belief_id),
    ).fetchone()
    return _event_dict(row) if row is not None else None


def _find_belief_transition_events(conn, belief_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM event_log
        WHERE (
            event_type IN (
                'belief_created',
                'belief_confirmed',
                'belief_weakened',
                'contradiction_detected'
            )
            AND json_extract(payload, '$.belief_id') = ?
        ) OR (
            event_type = 'belief_superseded'
            AND (
                json_extract(payload, '$.old_belief_id') = ?
                OR json_extract(payload, '$.new_belief_id') = ?
            )
        )
        ORDER BY id
        """,
        (belief_id, belief_id, belief_id),
    ).fetchall()
    return [_event_dict(row) for row in rows]


def _find_proposal_event(conn, proposal_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT * FROM event_log
        WHERE event_type = 'proposal_created'
          AND json_extract(payload, '$.proposal_id') = ?
        ORDER BY id
        LIMIT 1
        """,
        (proposal_id,),
    ).fetchone()
    return _event_dict(row) if row is not None else None


def _find_proposal_review_event(conn, proposal_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT * FROM event_log
        WHERE event_type = 'proposal_reviewed'
          AND json_extract(payload, '$.proposal_id') = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (proposal_id,),
    ).fetchone()
    return _event_dict(row) if row is not None else None


def _find_experience_event(conn, experience_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT * FROM event_log
        WHERE event_type = 'experience_recorded'
          AND json_extract(payload, '$.experience_id') = ?
        ORDER BY id
        LIMIT 1
        """,
        (experience_id,),
    ).fetchone()
    return _event_dict(row) if row is not None else None


def _find_experience_proposals(conn, experience_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM proposal_log
        WHERE json_extract(payload, '$.experience_id') = ?
        ORDER BY id
        """,
        (experience_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _find_state_event(conn, state_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT * FROM event_log
        WHERE event_type = 'state_changed'
          AND json_extract(payload, '$.state_id') = ?
        ORDER BY id
        LIMIT 1
        """,
        (state_id,),
    ).fetchone()
    return _event_dict(row) if row is not None else None


def _find_governance_decision_event(conn, decision_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT * FROM event_log
        WHERE event_type = 'governance_decision'
          AND json_extract(payload, '$.decision_id') = ?
        ORDER BY id
        LIMIT 1
        """,
        (decision_id,),
    ).fetchone()
    return _event_dict(row) if row is not None else None


def _find_governance_audit_events(
    conn,
    decision_id: int,
    event_type: str,
) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM event_log
        WHERE event_type = ?
          AND json_extract(payload, '$.decision_id') = ?
        ORDER BY id
        """,
        (event_type, decision_id),
    ).fetchall()
    return [_event_dict(row) for row in rows]


def _find_rule_activated_event(conn, rule_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT * FROM event_log
        WHERE event_type = 'rule_activated'
          AND json_extract(payload, '$.rule_id') = ?
        ORDER BY id
        LIMIT 1
        """,
        (rule_id,),
    ).fetchone()
    return _event_dict(row) if row is not None else None


def _get_proposal(conn, proposal_id: int):
    row = conn.execute(
        "SELECT * FROM proposal_log WHERE id = ?",
        (proposal_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"proposal not found: {proposal_id}")
    return row
