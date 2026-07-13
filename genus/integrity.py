from __future__ import annotations

import json
import sqlite3

from genus import event_router, response_outcomes, sealing
from genus.db import init_schema


REQUIRED_EVENT_KEYS = {
    "observation_created": {"source", "raw_value", "unit"},
    "evidence_recorded": {"observation_id", "metric_key", "metric_value"},
    "assertion_recorded": {"claim_key", "claim_value", "source", "derivation"},
    "relation_asserted": {"subject", "predicate", "object", "source", "derivation"},
    "relation_retracted": {"subject", "predicate", "object", "source", "reason"},
    "belief_created": {
        "belief_id",
        "claim_key",
        "claim_value",
        "derivation",
        "supporting_events",
    },
    "belief_confirmed": {"belief_id", "new_supporting_event"},
    "belief_weakened": {"belief_id", "contradicting_event"},
    "belief_superseded": {
        "old_belief_id",
        "new_belief_id",
        "claim_key",
        "claim_value",
        "derivation",
        "supporting_events",
        "reason",
    },
    "contradiction_detected": {"reason"},
    "proposal_created": {
        "proposal_id",
        "proposal_type",
        "claim_key",
        "claim_value",
        "source_belief",
        "source_event",
        "payload",
        "reason",
    },
    "proposal_reviewed": {"proposal_id", "decision", "note"},
    "experience_recorded": {
        "experience_id",
        "experience_key",
        "experience_type",
        "subject_key",
        "pattern",
        "supporting_events",
        "derivation",
        "summary",
    },
    "experience_recharacterized": {
        "experience_id",
        "experience_key",
        "pattern",
        "supporting_events",
        "summary",
        "reason",
    },
    "state_changed": {
        "state_id",
        "state_key",
        "state_value",
        "previous_state_id",
        "derivation",
        "supporting_beliefs",
        "components",
        "reason",
    },
    "rule_proposed": {
        "rule_key",
        "rule_type",
        "subject_key",
        "spec",
        "source_experience",
        "derivation",
        "summary",
    },
    "rule_activated": {
        "rule_id",
        "rule_key",
        "rule_type",
        "subject_key",
        "spec",
        "source_proposal",
        "derivation",
    },
    "policy_evaluated": {
        "decision_id",
        "policy_key",
        "action",
        "target_type",
        "target_id",
        "result",
        "reason",
    },
    "constraint_checked": {
        "decision_id",
        "constraint_key",
        "action",
        "target_type",
        "target_id",
        "result",
        "reason",
    },
    "governance_decision": {
        "decision_id",
        "action",
        "target_type",
        "target_id",
        "decision",
        "override",
        "policy_results",
        "reason",
    },
    "operation_check_recorded": {
        "operation_id",
        "check_key",
        "status",
        "target",
        "payload",
        "derivation",
    },
    "operation_recovery_attempted": {
        "recovery_id",
        "check_key",
        "action",
        "target",
        "failures",
        "reason",
        "derivation",
    },
    "operation_recovery_result": {
        "recovery_id",
        "result",
        "action",
        "target",
        "detail",
        "derivation",
    },
    "inquiry_created": {
        "inquiry_id",
        "inquiry_type",
        "claim_key",
        "source_belief",
        "source_event",
        "question_key",
        "payload",
        "state",
    },
    "inquiry_resolved": {"inquiry_id", "answer"},
    "inquiries_reconciled": {"inquiry_ids", "answer"},
    response_outcomes.OUTCOME_EVENT: set(response_outcomes.OUTCOME_PAYLOAD_KEYS),
    response_outcomes.FEEDBACK_EVENT: set(response_outcomes.FEEDBACK_PAYLOAD_KEYS),
    "forecast_made": {"metric_key", "predicted_value", "method", "support"},
    "forecast_scored": {
        "forecast_event",
        "metric_key",
        "predicted_value",
        "actual_value",
        "error",
    },
    "ledger_epoch_opened": {
        "algo",
        "genesis_digest",
        "prefix_max_id",
        "prefix_count",
    },
    "werkzeug_registriert": {
        "name",
        "parameter",
        "schreibt",
        "wortlautfest",
        "pruefbar_als",
        "quelle",
    },
    "proposal_umgesetzt": {
        "proposal_id",
        "art",
        "ergebnis",
    },
    "code_entwurf_erstellt": {
        "blatt",
        "pfad",
        "fingerabdruck",
        "quelle",
    },
    "code_entwurf_geprueft": {
        "blatt",
        "pfad",
        "fingerabdruck",
        "verbote",
        "tests_exit",
        "bestanden",
    },
    # Die erste HAND (P4): Vorschlag → menschliches OK → genau-einmal-Ausführung. Bewusst rohe
    # Marker (event_router.BEWUSST_ROH) — der Zustand ist eine read-time-Projektion, kein Nebentisch;
    # hier stehen sie, weil jeder je geschriebene Typ auch dem Integritäts-Vertrag bekannt sein muss.
    "hand_vorgeschlagen": {"art", "inhalt", "faellig_um", "quelle"},
    "hand_bestaetigt": {"hand_id"},
    "hand_ausgefuehrt": {"hand_id", "ergebnis"},
    "hand_abgelehnt": {"hand_id"},
}


def _projection_summary(events: list[dict], projections: dict) -> dict:
    """Keep the diagnostic result shaped even when an invalid event blocks replay."""
    return {
        "events": len(events),
        "active_beliefs": sum(
            1 for row in projections["beliefs"] if row["state"] == "active"
        ),
        "proposals": len(projections["proposals"]),
        "inquiries": len(projections["inquiries"]),
        "experiences": len(projections["experiences"]),
        "active_states": sum(
            1 for row in projections["states"] if row["status"] == "active"
        ),
        "governance_decisions": len(projections["governance"]),
        "operations": len(projections["operations"]),
        "active_rules": sum(
            1 for row in projections["rules"] if row["status"] == "active"
        ),
        "response_outcomes": len(projections["response_outcomes"]),
        "response_feedback": len(projections["response_feedback"]),
    }


def check(conn) -> dict:
    issues = []
    schema_issues = validate_schema(conn)
    event_issues = validate_event_contract(conn)
    issues.extend(schema_issues)
    issues.extend(event_issues)
    issues.extend(sealing.verify_chain(conn))

    # Take a CONSISTENT point-in-time snapshot of events + projections in one read
    # transaction (a stable WAL snapshot), so concurrent autonomous writers -- the learner,
    # cron ticks -- cannot make this check spuriously fail. The ledger is append-only, so a
    # fresh replay of exactly those events must reproduce exactly those projections; new
    # events appended *during* the check are simply not part of this snapshot.
    in_txn = conn.in_transaction
    if not in_txn:
        conn.execute("BEGIN")
    try:
        event_log_snapshot = snapshot_event_log(conn)
        projection_before = snapshot_projections(conn)
    finally:
        if not in_txn:
            conn.execute("COMMIT")

    replay_summary = _projection_summary(event_log_snapshot, projection_before)
    # A structurally invalid event must make the check red, never crash the
    # diagnostic through a projector/FK exception.  Once the event contract is
    # valid, replay still runs and any unexpected projector failure is reported
    # as its own integrity issue rather than escaping.
    if not event_issues:
        replay_conn = None
        try:
            replay_conn = replay_connection_from_events(event_log_snapshot)
            replay_summary = event_router.replay(replay_conn)
            projection_after = snapshot_projections(replay_conn)
        except Exception as exc:  # diagnostic boundary: report, never hide a red ledger
            issues.append(f"projection replay failed ({type(exc).__name__})")
        else:
            if projection_after != projection_before:
                issues.append("projection state changed after replay")
        finally:
            if replay_conn is not None:
                replay_conn.close()

    return {
        "ok": not issues,
        "issues": issues,
        "events": len(event_log_snapshot),
        "active_beliefs": replay_summary["active_beliefs"],
        "proposals": replay_summary["proposals"],
        "inquiries": replay_summary["inquiries"],
        "experiences": replay_summary["experiences"],
        "active_states": replay_summary["active_states"],
        "governance_decisions": replay_summary["governance_decisions"],
        "operations": replay_summary["operations"],
        "active_rules": replay_summary["active_rules"],
        "response_outcomes": replay_summary["response_outcomes"],
        "response_feedback": replay_summary["response_feedback"],
    }


def replay_connection_from_events(events: list[dict]) -> sqlite3.Connection:
    replay_conn = sqlite3.connect(":memory:")
    replay_conn.row_factory = sqlite3.Row
    init_schema(replay_conn)
    replay_conn.executemany(
        """
        INSERT INTO event_log
            (id, event_type, payload, created_at, prev_seal, seal)
        VALUES
            (:id, :event_type, :payload, :created_at, :prev_seal, :seal)
        """,
        events,
    )
    replay_conn.commit()
    return replay_conn


def validate_schema(conn) -> list[str]:
    issues = []
    event_columns = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(event_log)").fetchall()
    ]
    belief_columns = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(belief_projection)").fetchall()
    ]
    proposal_columns = [
        row["name"] for row in conn.execute("PRAGMA table_info(proposal_log)").fetchall()
    ]
    inquiry_columns = [
        row["name"] for row in conn.execute("PRAGMA table_info(inquiry_log)").fetchall()
    ]
    experience_columns = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(experience_log)").fetchall()
    ]
    state_columns = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(state_projection)").fetchall()
    ]
    governance_columns = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(governance_log)").fetchall()
    ]
    operation_columns = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(operation_log)").fetchall()
    ]
    rule_columns = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(rule_projection)").fetchall()
    ]
    response_outcome_columns = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(response_outcome_log)").fetchall()
    ]
    response_feedback_columns = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(response_feedback_log)").fetchall()
    ]
    if not {"prev_seal", "seal"}.issubset(event_columns):
        issues.append("event_log missing sealing columns")
    if "confidence" in belief_columns:
        issues.append("belief_projection must not store confidence")
    if not {"decision", "reviewed_at"}.issubset(proposal_columns):
        issues.append("proposal_log missing lifecycle columns")
    if "answer" not in inquiry_columns:
        issues.append("inquiry_log missing answer column")
    if not {
        "experience_key",
        "experience_type",
        "subject_key",
        "pattern",
        "supporting_events",
        "derivation",
        "summary",
    }.issubset(experience_columns):
        issues.append("experience_log missing required columns")
    if "confidence" in experience_columns:
        issues.append("experience_log must not store confidence")
    if not {
        "state_key",
        "state_value",
        "status",
        "derivation",
        "supporting_beliefs",
        "components",
        "reason",
    }.issubset(state_columns):
        issues.append("state_projection missing required columns")
    if "confidence" in state_columns:
        issues.append("state_projection must not store confidence")
    if not {
        "action",
        "target_type",
        "target_id",
        "decision",
        "override",
        "policy_results",
        "reason",
    }.issubset(governance_columns):
        issues.append("governance_log missing required columns")
    if "confidence" in governance_columns:
        issues.append("governance_log must not store confidence")
    if not {
        "operation_type",
        "check_key",
        "status",
        "target",
        "payload",
        "derivation",
        "source_event",
        "last_updated_at",
    }.issubset(operation_columns):
        issues.append("operation_log missing required columns")
    if "confidence" in operation_columns:
        issues.append("operation_log must not store confidence")
    if not {
        "rule_key",
        "rule_type",
        "subject_key",
        "spec",
        "status",
        "source_proposal",
        "derivation",
    }.issubset(rule_columns):
        issues.append("rule_projection missing required columns")
    if "confidence" in rule_columns:
        issues.append("rule_projection must not store confidence")

    expected_outcome_columns = {
        "response_id",
        "channel",
        "outcome",
        "readings",
        "answer_mode",
        "feedback_eligible",
        "created_at",
    }
    expected_feedback_columns = {
        "feedback_event_id",
        "response_id",
        "signal",
        "corrected_intent",
        "source",
        "created_at",
    }
    if set(response_outcome_columns) != expected_outcome_columns:
        issues.append("response_outcome_log violates its exact privacy-safe schema")
    if set(response_feedback_columns) != expected_feedback_columns:
        issues.append("response_feedback_log violates its exact privacy-safe schema")
    outcome_table_row = conn.execute(
        "SELECT sql FROM sqlite_schema WHERE type = 'table' AND name = 'response_outcome_log'"
    ).fetchone()
    outcome_table_sql = (
        " ".join(str(outcome_table_row["sql"]).casefold().split())
        if outcome_table_row is not None
        else ""
    )
    if "check (feedback_eligible in (0, 1))" not in outcome_table_sql:
        issues.append("response_outcome_log must constrain feedback_eligible to 0/1")

    outcome_foreign_keys = {
        (row["from"], row["table"], row["to"])
        for row in conn.execute("PRAGMA foreign_key_list(response_outcome_log)").fetchall()
    }
    feedback_foreign_keys = {
        (row["from"], row["table"], row["to"])
        for row in conn.execute("PRAGMA foreign_key_list(response_feedback_log)").fetchall()
    }
    if ("response_id", "event_log", "id") not in outcome_foreign_keys:
        issues.append("response_outcome_log must link response_id to event_log.id")
    if not {
        ("feedback_event_id", "event_log", "id"),
        ("response_id", "response_outcome_log", "response_id"),
    }.issubset(feedback_foreign_keys):
        issues.append("response_feedback_log has an incomplete response/event link")

    empty_derivations = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM belief_projection
        WHERE derivation IS NULL OR TRIM(derivation) = ''
        """
    ).fetchone()["count"]
    if empty_derivations:
        issues.append("belief_projection contains empty derivation")
    empty_experience_derivations = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM experience_log
        WHERE derivation IS NULL OR TRIM(derivation) = ''
        """
    ).fetchone()["count"]
    if empty_experience_derivations:
        issues.append("experience_log contains empty derivation")
    empty_state_derivations = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM state_projection
        WHERE derivation IS NULL OR TRIM(derivation) = ''
        """
    ).fetchone()["count"]
    if empty_state_derivations:
        issues.append("state_projection contains empty derivation")
    empty_rule_derivations = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM rule_projection
        WHERE derivation IS NULL OR TRIM(derivation) = ''
        """
    ).fetchone()["count"]
    if empty_rule_derivations:
        issues.append("rule_projection contains empty derivation")
    empty_operation_derivations = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM operation_log
        WHERE derivation IS NULL OR TRIM(derivation) = ''
        """
    ).fetchone()["count"]
    if empty_operation_derivations:
        issues.append("operation_log contains empty derivation")
    return issues


def validate_event_contract(conn) -> list[str]:
    issues = []
    rows = conn.execute("SELECT id, event_type, payload FROM event_log ORDER BY id").fetchall()
    ids = [row["id"] for row in rows]
    if ids and ids != list(range(ids[0], ids[-1] + 1)):
        issues.append("event_log ids are not contiguous")
    reviewed_proposals = set()
    resolved_inquiries = set()
    activated_rule_keys = set()
    response_eligibility: dict[int, bool] = {}

    for row in rows:
        event_type = row["event_type"]
        try:
            payload = json.loads(row["payload"])
        except json.JSONDecodeError:
            issues.append(f"event {row['id']} payload is not valid JSON")
            continue
        if not isinstance(payload, dict):
            issues.append(f"event {row['id']} payload must be a JSON object")
            continue

        required = REQUIRED_EVENT_KEYS.get(event_type)
        if required is None:
            issues.append(f"event {row['id']} has unknown event_type {event_type}")
            continue

        missing = sorted(required - set(payload))
        if missing:
            issues.append(
                f"event {row['id']} {event_type} missing keys: {', '.join(missing)}"
            )

        if event_type == response_outcomes.OUTCOME_EVENT:
            payload_issues = response_outcomes.outcome_payload_issues(payload)
            issues.extend(
                f"event {row['id']} {event_type} {issue}" for issue in payload_issues
            )
            if not payload_issues:
                response_eligibility[int(row["id"])] = bool(payload["feedback_eligible"])
            continue

        if event_type == response_outcomes.FEEDBACK_EVENT:
            payload_issues = response_outcomes.feedback_payload_issues(payload)
            issues.extend(
                f"event {row['id']} {event_type} {issue}" for issue in payload_issues
            )
            if not payload_issues:
                response_id = int(payload["response_id"])
                eligible = response_eligibility.get(response_id)
                if eligible is None:
                    issues.append(
                        f"event {row['id']} {event_type} response_id {response_id} "
                        "does not reference an earlier valid response outcome"
                    )
                elif not eligible:
                    issues.append(
                        f"event {row['id']} {event_type} response_id {response_id} "
                        "is not feedback eligible"
                    )
            continue

        if event_type in {"belief_created", "belief_superseded"} and not payload.get(
            "derivation"
        ):
            issues.append(f"event {row['id']} {event_type} has empty derivation")
        if event_type == "contradiction_detected" and not (
            payload.get("belief_id") or payload.get("claim_key")
        ):
            # A contradiction must anchor to something: a belief (belief-vs-evidence) or
            # a claim (source-vs-source, which may have no belief).
            issues.append(
                f"event {row['id']} contradiction_detected needs belief_id or claim_key"
            )
        if event_type == "experience_recorded" and not payload.get("derivation"):
            issues.append(f"event {row['id']} experience_recorded has empty derivation")
        if event_type == "state_changed" and not payload.get("derivation"):
            issues.append(f"event {row['id']} state_changed has empty derivation")
        if event_type == "rule_proposed" and not payload.get("derivation"):
            issues.append(f"event {row['id']} rule_proposed has empty derivation")
        if event_type == "rule_activated":
            if not payload.get("derivation"):
                issues.append(f"event {row['id']} rule_activated has empty derivation")
            rule_key = payload["rule_key"]
            if rule_key in activated_rule_keys:
                issues.append(f"rule {rule_key} activated more than once")
            activated_rule_keys.add(rule_key)
        if event_type == "constraint_checked":
            if payload["result"] not in {"pass", "violation"}:
                issues.append(f"event {row['id']} constraint_checked has invalid result")
        if event_type == "policy_evaluated":
            if payload["result"] not in {"pass", "block"}:
                issues.append(f"event {row['id']} policy_evaluated has invalid result")
        if event_type == "governance_decision":
            if payload["decision"] not in {"allowed", "blocked"}:
                issues.append(f"event {row['id']} governance_decision has invalid decision")
            if payload["action"] not in {
                "proposal.review",
                "rule.activate",
                "operation.recovery",
            }:
                issues.append(f"event {row['id']} governance_decision has invalid action")
            if payload["target_type"] not in {"proposal", "operation_recovery"}:
                issues.append(
                    f"event {row['id']} governance_decision has invalid target_type"
                )
        if event_type == "operation_check_recorded":
            if payload["status"] not in {"ok", "fail"}:
                issues.append(
                    f"event {row['id']} operation_check_recorded has invalid status"
                )
            if not payload.get("derivation"):
                issues.append(
                    f"event {row['id']} operation_check_recorded has empty derivation"
                )
            if not payload.get("target"):
                issues.append(
                    f"event {row['id']} operation_check_recorded has empty target"
                )
        if event_type == "operation_recovery_attempted":
            if payload["action"] not in {"restart_network", "reboot"}:
                issues.append(
                    f"event {row['id']} operation_recovery_attempted has invalid action"
                )
            if not payload.get("derivation"):
                issues.append(
                    f"event {row['id']} operation_recovery_attempted has empty derivation"
                )
        if event_type == "operation_recovery_result":
            if payload["result"] not in {"succeeded", "failed", "scheduled"}:
                issues.append(
                    f"event {row['id']} operation_recovery_result has invalid result"
                )
            if not payload.get("derivation"):
                issues.append(
                    f"event {row['id']} operation_recovery_result has empty derivation"
                )
        if event_type == "ledger_epoch_opened":
            if required is not None and not missing:
                if payload["algo"] != sealing.ALGO:
                    issues.append(
                        f"event {row['id']} ledger_epoch_opened has invalid algo"
                    )
                if not isinstance(payload["genesis_digest"], str):
                    issues.append(
                        f"event {row['id']} ledger_epoch_opened has invalid genesis_digest"
                    )
                try:
                    prefix_count = int(payload["prefix_count"])
                    prefix_max_id = int(payload["prefix_max_id"])
                except (TypeError, ValueError):
                    issues.append(
                        f"event {row['id']} ledger_epoch_opened has invalid prefix values"
                    )
                else:
                    if prefix_count < 0:
                        issues.append(
                            f"event {row['id']} ledger_epoch_opened has invalid prefix_count"
                        )
                    if prefix_max_id < 0:
                        issues.append(
                            f"event {row['id']} ledger_epoch_opened has invalid prefix_max_id"
                        )
        if event_type == "proposal_reviewed":
            proposal_id = payload["proposal_id"]
            if payload["decision"] not in {"accepted", "rejected"}:
                issues.append(f"event {row['id']} proposal_reviewed has invalid decision")
            if proposal_id in reviewed_proposals:
                issues.append(f"proposal {proposal_id} reviewed more than once")
            reviewed_proposals.add(proposal_id)
        if event_type == "inquiry_resolved":
            inquiry_id = payload["inquiry_id"]
            if not str(payload["answer"]).strip():
                issues.append(f"event {row['id']} inquiry_resolved has empty answer")
            if inquiry_id in resolved_inquiries:
                issues.append(f"inquiry {inquiry_id} resolved more than once")
            resolved_inquiries.add(inquiry_id)
        if event_type == "inquiries_reconciled":
            inquiry_ids = payload["inquiry_ids"]
            if not isinstance(inquiry_ids, list) or not inquiry_ids:
                issues.append(f"event {row['id']} inquiries_reconciled has no inquiry ids")
                continue
            if not str(payload["answer"]).strip():
                issues.append(f"event {row['id']} inquiries_reconciled has empty answer")
            if len(inquiry_ids) != len(set(inquiry_ids)):
                issues.append(f"event {row['id']} inquiries_reconciled has duplicate inquiry ids")
            for inquiry_id in inquiry_ids:
                if inquiry_id in resolved_inquiries:
                    issues.append(f"inquiry {inquiry_id} resolved more than once")
                resolved_inquiries.add(inquiry_id)
    return issues


def snapshot_event_log(conn) -> list[dict]:
    return [
        {
            "id": row["id"],
            "event_type": row["event_type"],
            "payload": row["payload"],
            "created_at": row["created_at"],
            "prev_seal": row["prev_seal"],
            "seal": row["seal"],
        }
        for row in conn.execute(
            """
            SELECT id, event_type, payload, created_at, prev_seal, seal
            FROM event_log
            ORDER BY id
            """
        ).fetchall()
    ]


# Der Snapshot benennt seine Tabellen ausdrücklich, damit Router-Ziele, Replay-Clear-Liste
# und Integritätsvergleich maschinenlesbar gegeneinander geprüft werden können.
SNAPSHOT_PROJEKTIONSTABELLEN: dict[str, str] = {
    "beliefs": "belief_projection",
    "proposals": "proposal_log",
    "inquiries": "inquiry_log",
    "experiences": "experience_log",
    "states": "state_projection",
    "governance": "governance_log",
    "operations": "operation_log",
    "rules": "rule_projection",
    "relations": "relation_projection",
    "values": "value_projection",
    "response_outcomes": "response_outcome_log",
    "response_feedback": "response_feedback_log",
}


def snapshot_projections(conn) -> dict:
    beliefs = [
        dict(row)
        for row in conn.execute(
            """
            SELECT id, claim_key, claim_value, state, derivation,
                   supporting_events, contradicting_events,
                   created_at, last_updated_at, superseded_by
            FROM belief_projection
            ORDER BY id
            """
        ).fetchall()
    ]
    proposals = [
        dict(row)
        for row in conn.execute(
            """
            SELECT id, proposal_type, claim_key, claim_value, source_belief,
                   source_event, payload, state, decision, reviewed_at, created_at
            FROM proposal_log
            ORDER BY id
            """
        ).fetchall()
    ]
    inquiries = [
        dict(row)
        for row in conn.execute(
            """
            SELECT id, inquiry_type, claim_key, source_belief, source_event,
                   question_key, payload, state, answer, created_at, resolved_at
            FROM inquiry_log
            ORDER BY id
            """
        ).fetchall()
    ]
    experiences = [
        dict(row)
        for row in conn.execute(
            """
            SELECT id, experience_key, experience_type, subject_key, pattern,
                   supporting_events, derivation, summary, created_at
            FROM experience_log
            ORDER BY id
            """
        ).fetchall()
    ]
    states = [
        dict(row)
        for row in conn.execute(
            """
            SELECT id, state_key, state_value, status, derivation,
                   supporting_beliefs, components, reason,
                   created_at, last_updated_at, superseded_by
            FROM state_projection
            ORDER BY id
            """
        ).fetchall()
    ]
    governance = [
        dict(row)
        for row in conn.execute(
            """
            SELECT id, action, target_type, target_id, decision, override,
                   policy_results, reason, created_at
            FROM governance_log
            ORDER BY id
            """
        ).fetchall()
    ]
    operations = [
        dict(row)
        for row in conn.execute(
            """
            SELECT id, operation_type, check_key, status, target, payload,
                   derivation, source_event, created_at, last_updated_at
            FROM operation_log
            ORDER BY id
            """
        ).fetchall()
    ]
    rules = [
        dict(row)
        for row in conn.execute(
            """
            SELECT id, rule_key, rule_type, subject_key, spec, status,
                   source_proposal, derivation, created_at
            FROM rule_projection
            ORDER BY id
            """
        ).fetchall()
    ]
    relations = [
        dict(row)
        for row in conn.execute(
            """
            SELECT id, subject, predicate, object, source, derivation,
                   created_at, last_updated_at
            FROM relation_projection
            ORDER BY id
            """
        ).fetchall()
    ]
    values = [
        dict(row)
        for row in conn.execute(
            "SELECT event_id, claim_key, value, source, created_at "
            "FROM value_projection ORDER BY event_id"
        ).fetchall()
    ]
    response_outcomes_rows = [
        dict(row)
        for row in conn.execute(
            """
            SELECT response_id, channel, outcome, readings, answer_mode,
                   feedback_eligible, created_at
            FROM response_outcome_log
            ORDER BY response_id
            """
        ).fetchall()
    ]
    response_feedback_rows = [
        dict(row)
        for row in conn.execute(
            """
            SELECT feedback_event_id, response_id, signal, corrected_intent,
                   source, created_at
            FROM response_feedback_log
            ORDER BY feedback_event_id
            """
        ).fetchall()
    ]
    return {
        "beliefs": beliefs,
        "proposals": proposals,
        "inquiries": inquiries,
        "experiences": experiences,
        "states": states,
        "governance": governance,
        "operations": operations,
        "rules": rules,
        "relations": relations,
        "values": values,
        "response_outcomes": response_outcomes_rows,
        "response_feedback": response_feedback_rows,
    }
