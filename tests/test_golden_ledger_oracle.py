"""A0.2 Golden Ledger tests — CANDIDATE — PENDING HUMAN REVIEW.

The static fixture and Oracle are the authority under human review.  Runtime
replay is only compared against those files and never used to generate them.
"""

from __future__ import annotations

import json
import unicodedata
from datetime import datetime

import pytest

from genus import (
    anchor,
    confidence,
    event_router,
    integrity,
    ledger,
    maturation,
    projection,
    proposals,
    sealing,
)
from tests import golden_ledger_support as golden


@pytest.fixture
def candidate() -> golden.CandidateBundle:
    return golden.load_candidate()


def _canonical_payload(payload: dict) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _tamperable_event_id(
    conn,
    *,
    minimum: int,
    maximum: int,
) -> int:
    rows = conn.execute(
        """
        SELECT id, event_type
        FROM event_log
        WHERE id BETWEEN ? AND ?
        ORDER BY id
        """,
        (minimum, maximum),
    ).fetchall()
    excluded = {
        "ledger_epoch_opened",
        "response_outcome_recorded",
        "response_feedback_recorded",
    }
    for row in rows:
        if row["event_type"] not in excluded:
            return int(row["id"])
    raise AssertionError("candidate needs a structurally tamperable event in this range")


def _events_of_type(
    candidate: golden.CandidateBundle,
    event_type: str,
) -> list[dict]:
    return [
        event for event in candidate.events if event["event_type"] == event_type
    ]


def _one_event(events: list[dict], description: str) -> dict:
    assert len(events) == 1, f"expected exactly one {description}, got {len(events)}"
    return events[0]


def _assert_emitted_events_match_fixture(
    conn,
    candidate: golden.CandidateBundle,
    *,
    first_id: int,
    last_id: int,
) -> None:
    """Compare producer-stable event semantics, not the runtime wall clock.

    ``ledger.append`` obtains ``created_at`` from SQLite's current clock and the seal
    deliberately does not include that timestamp.  The static fixture timestamps are
    therefore checked separately as historical data; this helper compares the current
    producer's type, payload, chain link, and seal only.
    """
    actual = conn.execute(
        """
        SELECT id, event_type, payload, prev_seal, seal
        FROM event_log
        WHERE id BETWEEN ? AND ?
        ORDER BY id
        """,
        (first_id, last_id),
    ).fetchall()
    expected = [
        event
        for event in candidate.events
        if first_id <= event["id"] <= last_id
    ]
    assert [int(row["id"]) for row in actual] == list(
        range(first_id, last_id + 1)
    )
    assert [event["id"] for event in expected] == list(
        range(first_id, last_id + 1)
    )
    for row, event in zip(actual, expected, strict=True):
        assert row["event_type"] == event["event_type"]
        assert json.loads(row["payload"]) == event["payload"]
        assert row["prev_seal"] == event["prev_seal"]
        assert row["seal"] == event["seal"]


def test_static_artifacts_match_exact_contract(candidate: golden.CandidateBundle) -> None:
    assert golden.CANDIDATE_NOTICE == "CANDIDATE — PENDING HUMAN REVIEW"
    assert golden.CANDIDATE_STATUS == "candidate_pending_human_review"

    golden.assert_artifact_schemas(candidate)

    assert candidate.oracle["provenance"]["baseline_commit"] == golden.BASELINE_COMMIT
    assert candidate.oracle["provenance"]["baseline_commit"] == (
        "1a102979b3a53d68207a86147005e137e6b0a5db"
    )
    assert set(candidate.oracle["expected_projections"]) == set(
        golden.PROJECTION_TABLES
    )


def test_source_bytes_and_semantic_stream_are_distinct_and_bound(
    candidate: golden.CandidateBundle,
) -> None:
    fixture_digest = golden.sha256_hex(candidate.events_bytes)
    records = golden.event_stream_records_from_fixture(candidate.events)
    stream_digest = golden.event_stream_sha256(records)

    assert fixture_digest == candidate.manifest["digests"]["fixture_sha256"]
    assert stream_digest == candidate.manifest["digests"]["event_stream_sha256"]
    assert fixture_digest != stream_digest
    assert records == sorted(records, key=lambda record: record["id"])
    assert set(records[0]) == {
        "created_at",
        "event_type",
        "id",
        "payload_text",
        "prev_seal",
        "seal",
    }


def test_unicode_source_exercises_all_nfc_and_ascii_escape_domains(
    candidate: golden.CandidateBundle,
) -> None:
    source = "synthetic.source-café"
    assert unicodedata.normalize("NFC", source) == source
    assert unicodedata.normalize("NFD", source) != source

    source_event = _one_event(
        [
            event
            for event in candidate.events
            if event["payload"].get("source") == source
        ],
        "event carrying the Unicode source",
    )
    assert source_event["event_type"] == "assertion_recorded"

    literal_utf8 = source.encode("utf-8")
    escaped_ascii = json.dumps(source, ensure_ascii=True)[1:-1].encode("ascii")
    assert literal_utf8 in candidate.events_bytes
    assert unicodedata.normalize("NFD", source).encode("utf-8") not in (
        candidate.events_bytes
    )

    records = golden.event_stream_records_from_fixture(candidate.events)
    stream_record = _one_event(
        [record for record in records if record["id"] == source_event["id"]],
        "event-stream record for the Unicode source",
    )
    assert stream_record["payload_text"].isascii()
    assert escaped_ascii.decode("ascii") in stream_record["payload_text"]

    assert candidate.oracle_bytes.isascii()
    assert literal_utf8 not in candidate.oracle_bytes
    assert escaped_ascii in candidate.oracle_bytes

    projected = _one_event(
        [
            row
            for row in candidate.oracle["expected_projections"]["value_projection"][
                "rows"
            ]
            if row["event_id"] == source_event["id"]
        ],
        "projected value for the Unicode source",
    )
    assert projected["source"] == source


def test_direct_historical_import_builds_independent_actual_receipt(
    candidate: golden.CandidateBundle,
    tmp_path,
) -> None:
    before = golden.bundle_bytes_snapshot(candidate)
    conn = golden.import_fixture(tmp_path, candidate)
    try:
        source_records = golden.event_stream_records_from_fixture(candidate.events)
        imported_records = golden.event_stream_records_from_db(conn)
        assert imported_records == source_records

        event_router.replay(conn)
        snapshot = golden.projection_snapshot(conn, candidate.oracle)
        actual_receipt = golden.compute_actual_receipt(candidate, conn, snapshot)

        assert actual_receipt == candidate.receipt
    finally:
        conn.close()
    golden.assert_bundle_unchanged(candidate, before)


def test_replay_twice_matches_all_twelve_static_projections_without_new_events(
    candidate: golden.CandidateBundle,
    tmp_path,
) -> None:
    conn = golden.import_fixture(tmp_path, candidate)
    try:
        events_before = golden.event_stream_records_from_db(conn)
        summary_first = event_router.replay(conn)
        first = golden.projection_snapshot(conn, candidate.oracle)
        events_after_first = golden.event_stream_records_from_db(conn)

        golden.assert_snapshot_matches_oracle(first, candidate.oracle)
        assert events_after_first == events_before
        assert set(first.rows) == set(golden.PROJECTION_TABLES)

        summary_second = event_router.replay(conn)
        second = golden.projection_snapshot(conn, candidate.oracle)
        events_after_second = golden.event_stream_records_from_db(conn)

        golden.assert_snapshot_matches_oracle(second, candidate.oracle)
        assert summary_second == summary_first
        assert second == first
        assert events_after_second == events_before
    finally:
        conn.close()


def test_integrity_seal_epoch_and_current_head_match_static_oracle(
    candidate: golden.CandidateBundle,
    tmp_path,
) -> None:
    conn = golden.import_fixture(tmp_path, candidate)
    try:
        event_router.replay(conn)
        events_before = golden.event_stream_records_from_db(conn)

        assert sealing.verify_chain(conn) == []
        result = integrity.check(conn)
        assert {
            "ok": result["ok"],
            "issues": result["issues"],
        } == candidate.oracle["expected"]["integrity"]

        epoch = sealing.epoch_event(conn)
        assert epoch is not None
        epoch_payload = json.loads(epoch["payload"])
        assert int(epoch["id"]) == candidate.oracle["expected"]["epoch"]["event_id"]
        assert epoch_payload["algo"] == candidate.oracle["expected"]["epoch"]["algo"]
        assert epoch_payload["prefix_count"] == (
            candidate.oracle["expected"]["legacy_prefix"]["event_count"]
        )
        assert epoch_payload["prefix_max_id"] == (
            candidate.oracle["expected"]["legacy_prefix"]["max_event_id"]
        )
        assert epoch_payload["genesis_digest"] == (
            candidate.oracle["expected"]["legacy_prefix"]["genesis_digest"]
        )

        head = sealing.head(conn)
        assert head is not None
        assert {
            "event_id": int(head["id"]),
            "event_type": head["event_type"],
            "created_at": head["created_at"],
            "seal": head["seal"],
        } == candidate.oracle["expected"]["head"]
        assert golden.event_stream_records_from_db(conn) == events_before
    finally:
        conn.close()


def test_belief_read_models_use_only_fixed_time_and_half_life(
    candidate: golden.CandidateBundle,
    tmp_path,
) -> None:
    conn = golden.import_fixture(tmp_path, candidate)
    try:
        event_router.replay(conn)
        model = candidate.oracle["expected_read_models"]["belief_epistemic_state_v1"]
        as_of = datetime.fromisoformat(model["as_of"].replace("Z", "+00:00"))

        for case in model["cases"]:
            belief = conn.execute(
                "SELECT * FROM belief_projection WHERE id = ?",
                (case["belief_id"],),
            ).fetchone()
            assert belief is not None
            assert belief["state"] == "active"
            assert json.loads(belief["supporting_events"]) == (
                case["supporting_event_ids"]
            )
            assert json.loads(belief["contradicting_events"]) == (
                case["contradicting_event_ids"]
            )
            assert all(
                datetime.fromisoformat(belief[column].replace("Z", "+00:00"))
                == as_of
                for column in ("created_at", "last_updated_at")
            )

            supporting_times = golden.event_times(
                conn,
                case["supporting_event_ids"],
            )
            contradicting_times = golden.event_times(
                conn,
                case["contradicting_event_ids"],
            )
            all_times = supporting_times + contradicting_times
            assert all(
                datetime.fromisoformat(value.replace("Z", "+00:00")) == as_of
                for value in all_times
            )

            actual_confidence = confidence.calculate_confidence(
                supporting_times,
                contradicting_times,
                claim_key=belief["claim_key"],
                now=as_of,
                halflife_seconds=model["halflife_seconds"],
            )
            assert round(actual_confidence, 3) == case["expected_confidence"]
            assert projection.epistemic_state(
                actual_confidence,
                bool(case["contradicting_event_ids"]),
            ) == case["expected_epistemic_state"]
    finally:
        conn.close()


def test_belief_evidence_lineage_is_claim_coherent_and_source_independent(
    candidate: golden.CandidateBundle,
) -> None:
    by_id = {event["id"]: event for event in candidate.events}
    model = candidate.oracle["expected_read_models"]["belief_epistemic_state_v1"]

    for case in model["cases"]:
        belief_event = _one_event(
            [
                event
                for event in _events_of_type(candidate, "belief_created")
                if event["payload"]["belief_id"] == case["belief_id"]
            ],
            f"belief_created event for belief {case['belief_id']}",
        )
        belief = belief_event["payload"]
        assert belief["supporting_events"] == case["supporting_event_ids"]

        supporting = [by_id[event_id] for event_id in case["supporting_event_ids"]]
        assert all(event["event_type"] == "assertion_recorded" for event in supporting)
        assert all(
            event["payload"]["claim_key"] == belief["claim_key"]
            and event["payload"]["claim_value"] == belief["claim_value"]
            for event in supporting
        )
        supporting_sources = [event["payload"]["source"] for event in supporting]
        assert len(supporting_sources) == len(set(supporting_sources))

        contradicting = [
            by_id[event_id] for event_id in case["contradicting_event_ids"]
        ]
        assert all(
            event["event_type"] == "assertion_recorded" for event in contradicting
        )
        assert all(
            event["payload"]["claim_key"] == belief["claim_key"]
            and event["payload"]["claim_value"] != belief["claim_value"]
            for event in contradicting
        )
        contradicting_values = {
            event["payload"]["claim_value"] for event in contradicting
        }
        if contradicting:
            assert len(contradicting_values) == 1
        contradicting_sources = [
            event["payload"]["source"] for event in contradicting
        ]
        assert len(contradicting_sources) == len(set(contradicting_sources))
        all_sources = supporting_sources + contradicting_sources
        assert len(all_sources) == len(set(all_sources))

        weakened = [
            event
            for event in _events_of_type(candidate, "belief_weakened")
            if event["payload"]["belief_id"] == case["belief_id"]
        ]
        assert [
            event["payload"]["contradicting_event"] for event in weakened
        ] == case["contradicting_event_ids"]


def test_activity_daily_rhythm_support_is_linked_observation_evidence(
    candidate: golden.CandidateBundle,
) -> None:
    by_id = {event["id"]: event for event in candidate.events}
    experience_event = _one_event(
        [
            event
            for event in _events_of_type(candidate, "experience_recorded")
            if event["payload"]["experience_type"] == "ActivityDailyRhythm"
        ],
        "ActivityDailyRhythm experience",
    )
    experience_payload = experience_event["payload"]
    activity_events = [
        event for event in candidate.events if 11 <= event["id"] <= 20
    ]
    assert [event["id"] for event in activity_events] == list(range(11, 21))
    assert [event["event_type"] for event in activity_events] == [
        "observation_created",
        "evidence_recorded",
    ] * 5

    evidence_events = [
        event
        for event in candidate.events
        if event["event_type"] == "evidence_recorded"
        and event["payload"].get("metric_key") == "system.activity"
    ]
    assert [event["id"] for event in evidence_events] == [12, 14, 16, 18, 20]

    classified: list[tuple[int, int, str]] = []
    for evidence in evidence_events:
        observation_id = evidence["payload"]["observation_id"]
        observation = by_id[observation_id]
        assert observation_id == evidence["id"] - 1
        assert observation["event_type"] == "observation_created"
        assert observation["payload"]["raw_value"] == (
            evidence["payload"]["metric_value"]
        )
        assert observation["payload"].get("metric_key") == "system.activity"
        assert observation["created_at"] == evidence["created_at"]

        hour_utc = datetime.fromisoformat(evidence["created_at"]).hour
        activity_value = (
            "active"
            if float(evidence["payload"]["metric_value"]) >= 1.0
            else "idle"
        )
        classified.append((evidence["id"], hour_utc, activity_value))

    assert classified == [
        (12, 0, "active"),
        (14, 0, "active"),
        (16, 0, "active"),
        (18, 2, "idle"),
        (20, 2, "idle"),
    ]

    values = sorted({value for _, _, value in classified})
    contrasting_hours: dict[str, list[dict]] = {}
    for value in values:
        global_count = sum(1 for _, _, item_value in classified if item_value == value)
        hours: list[dict] = []
        for hour in sorted({item_hour for _, item_hour, _ in classified}):
            bucket = [item for item in classified if item[1] == hour]
            supporting = [
                event_id
                for event_id, _, item_value in bucket
                if item_value == value
            ]
            count = len(supporting)
            bucket_ratio = count / len(bucket)
            global_ratio = global_count / len(classified)
            contrast = bucket_ratio - global_ratio
            if count < 3 or bucket_ratio < 0.75 or contrast < 0.25:
                continue
            hours.append(
                {
                    "hour_utc": hour,
                    "count": count,
                    "bucket_ratio": round(bucket_ratio, 3),
                    "global_ratio": round(global_ratio, 3),
                    "contrast": round(contrast, 3),
                    "supporting_events": supporting,
                }
            )
        if hours:
            contrasting_hours[value] = hours

    assert contrasting_hours == {
        "active": [
            {
                "hour_utc": 0,
                "count": 3,
                "bucket_ratio": 1.0,
                "global_ratio": 0.6,
                "contrast": 0.4,
                "supporting_events": [12, 14, 16],
            }
        ]
    }
    active_hours = contrasting_hours["active"]
    expected_pattern = {
        "bucket": "hour_of_day_utc",
        "value": "active",
        "hours_utc": [item["hour_utc"] for item in active_hours],
        "count": sum(item["count"] for item in active_hours),
        "contrasting_hours": active_hours,
    }
    assert experience_payload == {
        "experience_id": 1,
        "experience_key": "activity_daily_rhythm:system.activity:active",
        "experience_type": "ActivityDailyRhythm",
        "subject_key": "system.activity",
        "pattern": expected_pattern,
        "supporting_events": [12, 14, 16],
        "derivation": "rule:activity_daily_rhythm_v1",
        "summary": (
            "system.activity is disproportionately active during UTC hour(s) "
            "00:00 (3 contrasting observations)"
        ),
    }


def test_rule_lifecycle_matches_current_governed_producer_path(
    candidate: golden.CandidateBundle,
) -> None:
    activity_experience = _one_event(
        [
            event
            for event in _events_of_type(candidate, "experience_recorded")
            if event["payload"]["experience_type"] == "ActivityDailyRhythm"
        ],
        "ActivityDailyRhythm experience",
    )
    rule_event = _one_event(
        _events_of_type(candidate, "rule_proposed"),
        "rule_proposed event",
    )
    proposal_event = _one_event(
        [
            event
            for event in _events_of_type(candidate, "proposal_created")
            if event["payload"]["proposal_type"] == "RuleProposal"
        ],
        "RuleProposal proposal_created event",
    )

    rule = rule_event["payload"]
    proposal = proposal_event["payload"]
    proposal_id = proposal["proposal_id"]
    static_span = [
        event for event in candidate.events if 22 <= event["id"] <= 33
    ]
    assert [event["id"] for event in static_span] == list(range(22, 34))
    static_times = [datetime.fromisoformat(event["created_at"]) for event in static_span]
    assert all(
        earlier < later
        for earlier, later in zip(static_times, static_times[1:])
    )
    assert activity_experience["id"] == 21
    assert [rule_event["id"], proposal_event["id"]] == [22, 23]
    assert rule["source_experience"] == activity_experience["payload"]["experience_id"]
    assert rule["rule_type"] == "activity_expectation_v1"
    assert proposal["source_event"] == rule_event["id"]
    assert proposal["claim_key"] == rule["subject_key"]
    assert proposal["claim_value"] == rule["rule_type"]
    assert proposal["source_belief"] is None
    assert {
        key: proposal["payload"][key]
        for key in (
            "rule_key",
            "rule_type",
            "spec",
            "source_experience",
            "derivation",
        )
    } == {
        key: rule[key]
        for key in (
            "rule_key",
            "rule_type",
            "spec",
            "source_experience",
            "derivation",
        )
    }

    decisions = _events_of_type(candidate, "governance_decision")
    assert len(decisions) == 2
    review_decision = _one_event(
        [
            event
            for event in decisions
            if event["payload"]["action"] == "proposal.review"
            and event["payload"]["target_id"] == proposal_id
        ],
        "proposal.review governance decision",
    )
    activation_decision = _one_event(
        [
            event
            for event in decisions
            if event["payload"]["action"] == "rule.activate"
            and event["payload"]["target_id"] == proposal_id
        ],
        "rule.activate governance decision",
    )
    assert all(
        event["payload"]["decision"] == "allowed"
        and event["payload"]["override"] is False
        and event["payload"]["target_type"] == "proposal"
        for event in (review_decision, activation_decision)
    )
    review_decision_id = review_decision["payload"]["decision_id"]
    activation_decision_id = activation_decision["payload"]["decision_id"]
    assert review_decision_id < activation_decision_id

    constraints = _events_of_type(candidate, "constraint_checked")
    review_constraints = [
        event
        for event in constraints
        if event["payload"]["decision_id"] == review_decision_id
    ]
    activation_constraints = [
        event
        for event in constraints
        if event["payload"]["decision_id"] == activation_decision_id
    ]
    assert [event["payload"]["constraint_key"] for event in review_constraints] == [
        "kernel:terminal_review_v1",
        "kernel:valid_decision_v1",
    ]
    assert [
        event["payload"]["constraint_key"] for event in activation_constraints
    ] == [
        "kernel:rule_source_accepted_v1",
        "kernel:rule_single_activation_v1",
    ]
    assert constraints == review_constraints + activation_constraints
    for event in review_constraints:
        assert {
            key: event["payload"][key]
            for key in ("action", "target_type", "target_id", "result")
        } == {
            "action": "proposal.review",
            "target_type": "proposal",
            "target_id": proposal_id,
            "result": "pass",
        }
    for event in activation_constraints:
        assert {
            key: event["payload"][key]
            for key in ("action", "target_type", "target_id", "result")
        } == {
            "action": "rule.activate",
            "target_type": "proposal",
            "target_id": proposal_id,
            "result": "pass",
        }

    policy_event = _one_event(
        _events_of_type(candidate, "policy_evaluated"),
        "proposal review policy evaluation",
    )
    assert {
        key: policy_event["payload"][key]
        for key in (
            "decision_id",
            "action",
            "target_type",
            "target_id",
            "policy_key",
            "result",
        )
    } == {
        "decision_id": review_decision_id,
        "action": "proposal.review",
        "target_type": "proposal",
        "target_id": proposal_id,
        "policy_key": "policy:pressure_guard_v1",
        "result": "pass",
    }
    assert review_decision["payload"]["policy_results"] == [
        {
            key: policy_event["payload"][key]
            for key in ("policy_key", "result", "reason")
        }
    ]
    assert activation_decision["payload"]["policy_results"] == []

    reviewed_event = _one_event(
        [
            event
            for event in _events_of_type(candidate, "proposal_reviewed")
            if event["payload"]["proposal_id"] == proposal_id
        ],
        "accepted RuleProposal review",
    )
    assert reviewed_event["payload"]["decision"] == "accepted"
    activated_event = _one_event(
        _events_of_type(candidate, "rule_activated"),
        "rule_activated event",
    )
    activated = activated_event["payload"]
    assert activated["source_proposal"] == proposal_id
    assert {
        key: activated[key]
        for key in ("rule_key", "rule_type", "subject_key", "spec", "derivation")
    } == {
        key: rule[key]
        for key in ("rule_key", "rule_type", "subject_key", "spec", "derivation")
    }

    lifecycle = [
        rule_event,
        proposal_event,
        *review_constraints,
        policy_event,
        review_decision,
        reviewed_event,
        *activation_constraints,
        activation_decision,
        activated_event,
    ]
    assert [event["id"] for event in lifecycle] == sorted(
        event["id"] for event in lifecycle
    )
    assert [event["event_type"] for event in lifecycle] == [
        "rule_proposed",
        "proposal_created",
        "constraint_checked",
        "constraint_checked",
        "policy_evaluated",
        "governance_decision",
        "proposal_reviewed",
        "constraint_checked",
        "constraint_checked",
        "governance_decision",
        "rule_activated",
    ]
    assert [rule_event["id"], proposal_event["id"]] == list(range(22, 24))
    assert [
        *[event["id"] for event in review_constraints],
        policy_event["id"],
        review_decision["id"],
        reviewed_event["id"],
    ] == list(range(25, 30))
    assert [
        *[event["id"] for event in activation_constraints],
        activation_decision["id"],
        activated_event["id"],
    ] == list(range(30, 34))


def test_rule_lifecycle_is_reachable_through_current_producers(
    candidate: golden.CandidateBundle,
    tmp_path,
) -> None:
    conn = golden.import_fixture(tmp_path, candidate)
    try:
        golden.drop_append_only_guards(conn, tmp_root=tmp_path)
        for table in event_router.REPLAY_PROJEKTIONSTABELLEN:
            conn.execute(f'DELETE FROM "{table}"')
        conn.execute("DELETE FROM event_log WHERE id >= 22")
        event_router.replay(conn)
        updated = conn.execute(
            "UPDATE sqlite_sequence SET seq = 21 WHERE name = 'event_log'"
        )
        assert updated.rowcount == 1

        proposed = maturation.scan(conn)
        assert len(proposed) == 1
        assert proposed[0]["rule_event_id"] == 22
        assert proposed[0]["proposal_event_id"] == 23
        proposal_id = proposed[0]["proposal_id"]
        _assert_emitted_events_match_fixture(
            conn,
            candidate,
            first_id=22,
            last_id=23,
        )

        static_belief = candidate.events[23]
        assert static_belief["id"] == 24
        assert static_belief["event_type"] == "belief_created"
        belief_payload = dict(static_belief["payload"])
        belief_event_id = ledger.append(conn, "belief_created", belief_payload)
        assert belief_event_id == 24
        belief_payload["_event_created_at"] = ledger.event_created_at(
            conn,
            belief_event_id,
        )
        projection.apply_belief_created(conn, belief_payload)
        _assert_emitted_events_match_fixture(
            conn,
            candidate,
            first_id=24,
            last_id=24,
        )

        review = proposals.review_proposal_governed(
            conn,
            proposal_id,
            proposals.ACCEPTED,
            note="Synthetic review complete.",
        )
        assert review["decision"] == "allowed"
        assert review["review_event_id"] == 29
        _assert_emitted_events_match_fixture(
            conn,
            candidate,
            first_id=25,
            last_id=29,
        )

        activation = maturation.activate_rule(conn, proposal_id)
        assert activation["decision"] == "allowed"
        assert activation["rule_event_id"] == 33
        _assert_emitted_events_match_fixture(
            conn,
            candidate,
            first_id=30,
            last_id=33,
        )
    finally:
        conn.close()


def test_historical_anchor_and_all_three_negative_cases_match_static_oracle(
    candidate: golden.CandidateBundle,
    tmp_path,
) -> None:
    conn = golden.import_fixture(tmp_path, candidate)
    try:
        assert (
            anchor.canonical_json(candidate.anchor) + "\n"
        ).encode("utf-8") == candidate.anchor_bytes
        actual = golden.anchor_case_results(conn, candidate.anchor)
        assert actual == candidate.oracle["expected_anchor_v1"]["cases"]
    finally:
        conn.close()


def test_tamper_legacy_prefix_is_detected_by_genesis_and_event_digest(
    candidate: golden.CandidateBundle,
    tmp_path,
) -> None:
    conn = golden.import_fixture(tmp_path, candidate)
    try:
        prefix_max = candidate.manifest["epoch"]["prefix_max_id"]
        target = _tamperable_event_id(conn, minimum=1, maximum=prefix_max)
        row = conn.execute(
            "SELECT payload FROM event_log WHERE id = ?",
            (target,),
        ).fetchone()
        payload = json.loads(row["payload"])
        payload["tamper_marker"] = "legacy-prefix"

        golden.drop_append_only_guards(conn, tmp_root=tmp_path)
        conn.execute(
            "UPDATE event_log SET payload = ? WHERE id = ?",
            (_canonical_payload(payload), target),
        )

        assert any(
            "genesis digest mismatch" in issue
            for issue in sealing.verify_chain(conn)
        )
        assert golden.event_stream_sha256(
            golden.event_stream_records_from_db(conn)
        ) != candidate.oracle["source_bindings"]["event_stream_sha256"]
        assert integrity.check(conn)["ok"] is False
    finally:
        conn.close()


def test_tamper_tail_truncation_is_detected_by_count_head_and_receipt_binding(
    candidate: golden.CandidateBundle,
    tmp_path,
) -> None:
    conn = golden.import_fixture(tmp_path, candidate)
    try:
        current_head = candidate.manifest["head"]["event_id"]
        assert current_head > candidate.manifest["epoch"]["event_id"]
        golden.drop_append_only_guards(conn, tmp_root=tmp_path)
        conn.execute("DELETE FROM event_log WHERE id = ?", (current_head,))
        conn.commit()

        count = int(
            conn.execute("SELECT COUNT(*) AS count FROM event_log").fetchone()["count"]
        )
        head = sealing.head(conn)
        assert count != candidate.manifest["counts"]["event_count"]
        assert head is not None and int(head["id"]) != current_head
        assert golden.event_stream_sha256(
            golden.event_stream_records_from_db(conn)
        ) != candidate.oracle["source_bindings"]["event_stream_sha256"]

        event_router.replay(conn)
        snapshot = golden.projection_snapshot(conn, candidate.oracle)
        with pytest.raises(
            golden.CandidateContractError,
            match="source and imported event streams differ",
        ):
            golden.compute_actual_receipt(candidate, conn, snapshot)
    finally:
        conn.close()


def test_tamper_sealed_payload_is_detected(
    candidate: golden.CandidateBundle,
    tmp_path,
) -> None:
    conn = golden.import_fixture(tmp_path, candidate)
    try:
        epoch_id = candidate.manifest["epoch"]["event_id"]
        target = _tamperable_event_id(
            conn,
            minimum=epoch_id + 1,
            maximum=candidate.manifest["head"]["event_id"],
        )
        row = conn.execute(
            "SELECT payload FROM event_log WHERE id = ?",
            (target,),
        ).fetchone()
        payload = json.loads(row["payload"])
        payload["tamper_marker"] = "sealed-payload"

        golden.drop_append_only_guards(conn, tmp_root=tmp_path)
        conn.execute(
            "UPDATE event_log SET payload = ? WHERE id = ?",
            (_canonical_payload(payload), target),
        )

        assert any("seal mismatch" in issue for issue in sealing.verify_chain(conn))
        assert golden.event_stream_sha256(
            golden.event_stream_records_from_db(conn)
        ) != candidate.oracle["source_bindings"]["event_stream_sha256"]
    finally:
        conn.close()


def test_tamper_first_true_tail_prev_seal_reports_exact_link_mismatch(
    candidate: golden.CandidateBundle,
    tmp_path,
) -> None:
    conn = golden.import_fixture(tmp_path, candidate)
    try:
        target = candidate.manifest["epoch"]["event_id"] + 1
        row = conn.execute(
            "SELECT prev_seal FROM event_log WHERE id = ?",
            (target,),
        ).fetchone()
        assert row is not None
        replacement = "0" * 64 if row["prev_seal"] != "0" * 64 else "1" * 64

        golden.drop_append_only_guards(conn, tmp_root=tmp_path)
        conn.execute(
            "UPDATE event_log SET prev_seal = ? WHERE id = ?",
            (replacement, target),
        )

        assert sealing.verify_chain(conn) == [f"event {target} prev_seal mismatch"]
        assert golden.event_stream_sha256(
            golden.event_stream_records_from_db(conn)
        ) != candidate.oracle["source_bindings"]["event_stream_sha256"]
    finally:
        conn.close()


def test_tamper_seal_is_detected_by_chain_and_anchor(
    candidate: golden.CandidateBundle,
    tmp_path,
) -> None:
    conn = golden.import_fixture(tmp_path, candidate)
    try:
        head_id = candidate.manifest["head"]["event_id"]
        replacement = (
            "0" * 64
            if candidate.manifest["head"]["seal"] != "0" * 64
            else "1" * 64
        )
        golden.drop_append_only_guards(conn, tmp_root=tmp_path)
        conn.execute(
            "UPDATE event_log SET seal = ? WHERE id = ?",
            (replacement, head_id),
        )

        assert any("seal mismatch" in issue for issue in sealing.verify_chain(conn))
        assert anchor.verify_anchor(
            conn,
            candidate.anchor,
            core_id="golden-ledger-v1",
        )
    finally:
        conn.close()


def test_tamper_oracle_is_detected_in_memory_without_changing_fixture(
    candidate: golden.CandidateBundle,
) -> None:
    before = golden.bundle_bytes_snapshot(candidate)
    tampered = golden.tampered_oracle_bytes(candidate)

    assert tampered != candidate.oracle_bytes
    assert golden.sha256_hex(tampered) != (
        candidate.manifest["digests"]["oracle_sha256"]
    )
    assert golden.sha256_hex(tampered) != (
        candidate.receipt["digests"]["oracle_sha256"]
    )
    golden.assert_bundle_unchanged(candidate, before)


def test_fixture_bytes_remain_immutable_and_db_stays_under_tmp_path(
    candidate: golden.CandidateBundle,
    tmp_path,
) -> None:
    before = golden.bundle_bytes_snapshot(candidate)
    conn = golden.import_fixture(tmp_path, candidate)
    database_path = golden.database_file(conn)
    try:
        event_router.replay(conn)
        snapshot = golden.projection_snapshot(conn, candidate.oracle)
        golden.compute_actual_receipt(candidate, conn, snapshot)
    finally:
        conn.close()

    assert database_path.parent == tmp_path.resolve()
    assert {path.name for path in candidate.root.iterdir()} == set(
        golden.ARTIFACT_NAMES
    )
    golden.assert_bundle_unchanged(candidate, before)
