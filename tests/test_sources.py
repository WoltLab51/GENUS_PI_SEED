import json
import sqlite3

from click.testing import CliRunner

from genus import cli, event_router, integrity, projection, reactors, sensor, sources
from genus.db import init_schema

CLAIM = "weather.temp_outside"


def _fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def _observe(conn, temp):
    return reactors.observe_weather_reading(conn, sensor.mock_weather(temp))


def test_source_flows_from_observation_into_the_assertion_stream():
    conn = _fresh()
    _observe(conn, 18.0)
    stream = sources.assertions(conn, CLAIM)
    assert stream, "expected at least one assertion"
    assert all(row["source"] == "mock" for row in stream)
    assert stream[-1]["value"] == 18.0
    conn.close()


def test_lone_source_is_held_at_the_seed():
    conn = _fresh()
    for temp in (18.0, 19.0, 18.5):
        _observe(conn, temp)
    # only one source has spoken -> nothing to agree/disagree with -> unproven seed,
    # never a confident 1.0.
    assert sources.source_trust(conn, "mock") == sources.SOURCE_TRUST_SEED
    conn.close()


def test_threading_source_is_behaviour_preserving_and_replays_clean():
    conn = _fresh()
    for temp in (18.0, 18.0, 19.0):
        _observe(conn, temp)
    # integrity.check replays into a fresh db and compares projections: this proves the
    # belief lifecycle is unchanged by the added source provenance, and replay-stable.
    assert integrity.check(conn)["ok"] is True
    assert sources.assertions(conn, CLAIM)
    conn.close()


def _assert_source(conn, value, source):
    return reactors.observe_assertion(conn, CLAIM, value, source)


def test_two_agreeing_sources_earn_trust_with_no_contradiction():
    conn = _fresh()
    for temp in (18.0, 18.0, 18.0):
        _observe(conn, temp)  # sensor source "mock"
    _assert_source(conn, 18.0, "provider-b")  # a second source, agreeing
    assert sources.source_trust(conn, "mock") == 1.0
    assert sources.source_trust(conn, "provider-b") == 1.0
    result = sources.resolve(conn, CLAIM)
    assert set(result["candidates"]) == {"mock", "provider-b"}
    assert result["contradiction"] is False
    conn.close()


def test_two_disagreeing_sources_lose_trust_and_flag_contradiction():
    conn = _fresh()
    for temp in (18.0, 18.0, 18.0):
        _observe(conn, temp)
    _assert_source(conn, 30.0, "provider-b")  # far outside the claim's own spread
    assert sources.source_trust(conn, "mock") == 0.0
    assert sources.source_trust(conn, "provider-b") == 0.0
    result = sources.resolve(conn, CLAIM)
    assert result["contradiction"] is True
    conn.close()


def _inject_assertion(conn, value, source, created_at):
    body = {"claim_key": CLAIM, "claim_value": value, "source": source,
            "derivation": f"source:{source}"}
    cur = conn.execute(
        "INSERT INTO event_log (event_type, payload, created_at) VALUES ('assertion_recorded', ?, ?)",
        (json.dumps(body, sort_keys=True, separators=(",", ":")), created_at),
    )
    projection.apply_assertion_recorded(  # keep the indexed value view in sync, like the reactor
        conn, {**body, "_event_id": cur.lastrowid, "_event_created_at": created_at})
    conn.commit()


def test_single_source_resolves_to_itself_behaviour_preserving():
    conn = _fresh()
    _observe(conn, 18.0)
    result = sources.resolve(conn, CLAIM)
    assert result["value"] == 18.0
    assert result["chosen_source"] == "mock"
    assert result["candidates"]["mock"]["live"] is True
    assert result["contradiction"] is False
    conn.close()


def test_a_stale_source_does_not_drag_a_live_sources_trust():
    conn = _fresh()
    # hourly cadence: two fresh sources that agree + one stale, wildly-off source
    _inject_assertion(conn, 18.0, "A", "2026-06-28T10:00:00.000Z")
    _inject_assertion(conn, 18.0, "A", "2026-06-28T11:00:00.000Z")
    _inject_assertion(conn, 18.1, "B", "2026-06-28T11:00:30.000Z")
    _inject_assertion(conn, 99.0, "stale", "2026-06-28T02:00:00.000Z")
    # A and B agree and are live; the faded ghost must NOT pull their trust down
    assert sources.source_trust(conn, "A") == 1.0
    assert sources.source_trust(conn, "B") == 1.0
    conn.close()


def test_a_stale_source_fades_and_raises_no_false_contradiction():
    conn = _fresh()
    # an hourly cadence with two fresh sources that agree
    _inject_assertion(conn, 18.0, "open-meteo", "2026-06-28T10:00:00.000Z")
    _inject_assertion(conn, 18.2, "open-meteo", "2026-06-28T11:00:00.000Z")
    _inject_assertion(conn, 18.1, "wttr", "2026-06-28T11:00:30.000Z")
    # a third source spoke once, long ago, with a wildly different value
    _inject_assertion(conn, 40.0, "old", "2026-06-28T02:00:00.000Z")

    result = sources.resolve(conn, CLAIM)
    # ~9h stale against an hourly cadence -> faded, so it neither wins nor raises alarm
    assert result["candidates"]["old"]["live"] is False
    assert result["chosen_source"] in {"open-meteo", "wttr"}
    assert result["contradiction"] is False
    conn.close()


def test_cadence_ignores_subsecond_jitter():
    # A burst of near-simultaneous writes has no measurable cadence -> None (nothing fades),
    # so sub-second timestamp jitter can never make a concurrent source look stale. Without
    # this, same-millisecond bursts yielded a millisecond "cadence" that intermittently hid a
    # genuine contradiction (the flake).
    burst = [{"created_at": "2026-06-28T11:00:00.001Z"},
             {"created_at": "2026-06-28T11:00:00.002Z"},
             {"created_at": "2026-06-28T11:00:00.004Z"}]
    assert sources._cadence_halflife(burst) is None
    # a real (>= 1s) rhythm is still measured exactly
    rhythm = [{"created_at": "2026-06-28T11:00:00.000Z"},
              {"created_at": "2026-06-28T11:00:30.000Z"},
              {"created_at": "2026-06-28T11:01:00.000Z"}]
    assert sources._cadence_halflife(rhythm) == 30.0


def test_disagreeing_live_sources_raise_a_claim_anchored_inquiry():
    conn = _fresh()
    for temp in (18.0, 18.0, 18.0):
        _observe(conn, temp)  # source "mock"
    result = reactors.observe_assertion(conn, CLAIM, 30.0, "provider-b")
    types = [event["event_type"] for event in result["events"]]
    assert "contradiction_detected" in types
    assert "inquiry_created" in types
    rows = conn.execute(
        "SELECT inquiry_type, source_belief FROM inquiry_log WHERE state = 'open'"
    ).fetchall()
    # claim-anchored: a SourceContradiction inquiry with no belief behind it
    assert any(
        row["inquiry_type"] == "SourceContradiction" and row["source_belief"] is None
        for row in rows
    )
    conn.close()


def test_source_contradiction_fires_once_per_open_episode():
    conn = _fresh()
    for temp in (18.0, 18.0, 18.0):
        _observe(conn, temp)
    reactors.observe_assertion(conn, CLAIM, 30.0, "provider-b")
    second = reactors.observe_assertion(conn, CLAIM, 31.0, "provider-b")  # still disagrees
    assert "inquiry_created" not in [event["event_type"] for event in second["events"]]
    count = conn.execute(
        "SELECT COUNT(*) AS c FROM inquiry_log WHERE inquiry_type = 'SourceContradiction'"
    ).fetchone()["c"]
    assert count == 1
    conn.close()


def test_agreeing_sources_raise_no_contradiction_inquiry():
    conn = _fresh()
    for temp in (18.0, 18.0):
        _observe(conn, temp)
    result = reactors.observe_assertion(conn, CLAIM, 18.0, "provider-b")
    assert "inquiry_created" not in [event["event_type"] for event in result["events"]]
    conn.close()


def test_source_contradiction_events_replay_clean():
    conn = _fresh()
    for temp in (18.0, 18.0, 18.0):
        _observe(conn, temp)
    reactors.observe_assertion(conn, CLAIM, 30.0, "provider-b")
    assert integrity.check(conn)["ok"] is True
    conn.close()


def test_teach_records_a_human_source_settles_and_governs():
    conn = _fresh()
    for temp in (18.0, 18.0, 18.0):
        _observe(conn, temp)  # source "mock" ~18
    reactors.observe_assertion(conn, CLAIM, 30.0, "provider-b")  # disagree -> inquiry
    result = reactors.teach(conn, CLAIM, 18.5, "human")
    assert result["resolved_inquiries"]               # the inquiry was settled
    assert "human" in sources.sources(conn)           # the teacher is now a source
    open_count = conn.execute(
        "SELECT COUNT(*) AS c FROM inquiry_log "
        "WHERE state = 'open' AND inquiry_type = 'SourceContradiction'"
    ).fetchone()["c"]
    assert open_count == 0
    # the teacher governs: its seed trust outranks the distrusted machine sources
    assert sources.resolve(conn, CLAIM)["chosen_source"] == "human"
    conn.close()


def test_teach_events_replay_clean():
    conn = _fresh()
    for temp in (18.0, 18.0, 18.0):
        _observe(conn, temp)
    reactors.observe_assertion(conn, CLAIM, 30.0, "provider-b")
    reactors.teach(conn, CLAIM, 18.5, "human")
    assert integrity.check(conn)["ok"] is True
    conn.close()


def test_resolved_window_drops_a_faded_source_keeps_the_live_trajectory():
    conn = _fresh()
    _inject_assertion(conn, 10.0, "live", "2026-06-28T10:00:00.000Z")
    _inject_assertion(conn, 11.0, "live", "2026-06-28T11:00:00.000Z")
    _inject_assertion(conn, 12.0, "live", "2026-06-28T12:00:00.000Z")
    _inject_assertion(conn, 99.0, "old", "2026-06-28T02:00:00.000Z")  # stale outlier
    values = [row["metric_value"] for row in sources.resolved_window(conn, CLAIM, 3)]
    assert 99.0 not in values             # the faded source never enters the window
    assert values == [10.0, 11.0, 12.0]   # chronological, live trajectory only
    conn.close()


def test_resolved_window_single_source_is_behaviour_preserving():
    conn = _fresh()
    for temp in (18.0, 19.0, 20.0):
        _observe(conn, temp)
    values = [row["metric_value"] for row in sources.resolved_window(conn, CLAIM, 3)]
    assert values == [18.0, 19.0, 20.0]
    conn.close()


def test_observe_relation_holds_a_triple_in_the_graph():
    conn = _fresh()
    reactors.observe_relation(conn, "system.thermal", "correlates_with", "system.load", "experience")
    reactors.observe_relation(conn, "system.thermal", "measured_by", "cpu_thermal", "sensor")
    assert len(sources.relations(conn)) == 2
    subject = sources.relations(conn, subject="system.thermal")
    assert {(t["predicate"], t["object"]) for t in subject} == {
        ("correlates_with", "system.load"),
        ("measured_by", "cpu_thermal"),
    }
    conn.close()


def test_relation_asserted_replays_clean():
    conn = _fresh()
    reactors.observe_relation(conn, "a", "relates_to", "b", "human")
    assert integrity.check(conn)["ok"] is True
    conn.close()


def test_gaps_are_referenced_but_unknown_words():
    conn = _fresh()
    reactors.observe_relation(conn, "run", "synonym", "execute", "dict")
    reactors.observe_relation(conn, "run", "is_a", "verb", "dict")
    g = sources.gaps(conn)
    assert "execute" in g   # referenced via synonym, not yet a subject -> a gap
    assert "verb" not in g  # is_a objects (parts of speech) are not word gaps
    # once GENUS learns "execute", it is no longer a gap
    reactors.observe_relation(conn, "execute", "synonym", "run", "dict")
    assert "execute" not in sources.gaps(conn)
    conn.close()


def test_gaps_can_follow_the_is_a_hierarchy():
    conn = _fresh()
    reactors.observe_relation(conn, "dog", "is_a", "mammal", "src")
    reactors.observe_relation(conn, "dog", "synonym", "pooch", "src")
    assert "pooch" in sources.gaps(conn)                        # default follows synonyms
    assert "mammal" not in sources.gaps(conn)                   # is_a not followed by default
    assert "mammal" in sources.gaps(conn, predicates=("is_a",))  # climb the hierarchy
    conn.close()


def test_display_renders_concepts_with_a_readable_label():
    conn = _fresh()
    reactors.observe_relation(conn, "Pferd@de", "expresses", "Q726", "wikidata")
    reactors.observe_relation(conn, "horse@en", "expresses", "Q726", "wikidata")
    assert sources.display(conn, "Q726") == "Q726 (Pferd)"               # de preferred
    assert sources.display(conn, "Q726", langs=("en",)) == "Q726 (horse)"
    assert sources.display(conn, "Pferd@de") == "Pferd@de"               # a lexeme labels itself
    assert sources.display(conn, "Q999") == "Q999"                       # nothing lexicalizes it
    conn.close()


def test_display_prefers_the_canonical_label_over_an_alias():
    conn = _fresh()
    reactors.observe_relation(conn, "Pferd@de", "label", "Q726", "wikidata")     # canonical
    reactors.observe_relation(conn, "Pferd@de", "expresses", "Q726", "wikidata")
    reactors.observe_relation(conn, "Gaul@de", "expresses", "Q726", "wikidata")  # alias only
    assert sources.display(conn, "Q726") == "Q726 (Pferd)"   # not the alphabetically-first "Gaul"
    assert sources.senses(conn, "Gaul", "de") == ["Q726"]    # alias still resolves to the concept
    conn.close()


def test_source_trust_seed_for_relation_only_source():
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")  # no value claim
    assert sources.source_trust(conn, "wikidata") == sources.SOURCE_TRUST_SEED  # seed, indexed


def test_value_projection_indexes_assertions_and_trust():
    conn = _fresh()
    reactors.observe_assertion(conn, "thing.temp", "20", "a")
    reactors.observe_assertion(conn, "thing.temp", "20", "b")  # agrees with a
    assert {r["source"] for r in sources.assertions(conn, "thing.temp")} == {"a", "b"}
    assert sources.source_trust(conn, "a") == 1.0  # full agreement computation still runs


def test_value_projection_rebuilds_identically_on_replay():
    conn = _fresh()
    reactors.observe_assertion(conn, "thing.temp", "21", "a")
    before = [tuple(r) for r in conn.execute(
        "SELECT event_id, claim_key, value, source FROM value_projection ORDER BY event_id")]
    event_router.replay(conn)
    after = [tuple(r) for r in conn.execute(
        "SELECT event_id, claim_key, value, source FROM value_projection ORDER BY event_id")]
    assert before == after and len(before) == 1


def test_relation_confidence_rises_with_corroboration():
    conn = _fresh()
    reactors.observe_relation(conn, "Hund", "is_a", "Säugetier", "wikidata")
    one = sources.relation_confidence(conn, "Hund", "is_a", "Säugetier")
    reactors.observe_relation(conn, "Hund", "is_a", "Säugetier", "curated")
    two = sources.relation_confidence(conn, "Hund", "is_a", "Säugetier")
    assert one["n_sources"] == 1 and two["n_sources"] == 2
    assert two["confidence"] > one["confidence"]      # corroboration raises confidence
    assert two["confidence"] == 0.75                  # noisy-OR of two seed-trust (0.5) sources
    assert sources.relation_confidence(conn, "Hund", "is_a", "Pflanze")["confidence"] == 0.0


def test_confidence_cli_shows_corroborated_value(monkeypatch):
    conn = _fresh()
    reactors.observe_relation(conn, "Hund", "is_a", "Säugetier", "wikidata")
    reactors.observe_relation(conn, "Hund", "is_a", "Säugetier", "curated")
    monkeypatch.setattr(cli, "get_conn", lambda: conn)
    result = CliRunner().invoke(cli.main, ["confidence", "Hund", "is_a", "Säugetier"])
    assert result.exit_code == 0, result.output
    assert "confidence 0.75" in result.output


def test_functional_predicate_contradiction_raises_inquiry():
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "label", "Q144", "wikidata")
    r = reactors.observe_relation(conn, "Hund@de", "label", "Q999", "other")  # disagrees on the label
    types = [e["event_type"] for e in r["events"]]
    assert "contradiction_detected" in types and "inquiry_created" in types
    assert reactors._open_source_contradiction(conn, "Hund@de|label")
    assert sources.relation_contradiction(conn, "Hund@de", "label")["contradiction"] is True


def test_nonfunctional_predicate_allows_many_objects():
    conn = _fresh()
    reactors.observe_relation(conn, "Hund", "is_a", "Säugetier", "wikidata")
    r = reactors.observe_relation(conn, "Hund", "is_a", "Haustier", "wikidata")  # 2nd parent, fine
    assert "contradiction_detected" not in [e["event_type"] for e in r["events"]]
    assert sources.relation_contradiction(conn, "Hund", "is_a")["contradiction"] is False


def test_teach_relation_settles_inquiry_and_corrects_functional():
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "label", "Q999", "wikidata")  # wrong
    reactors.observe_relation(conn, "Hund@de", "label", "Q144", "other")     # right -> raises inquiry
    assert reactors._open_source_contradiction(conn, "Hund@de|label")
    result = reactors.teach_relation(conn, "Hund@de", "label", "Q144", "human")
    assert result["resolved_inquiries"]                       # the inquiry is settled
    assert "Q999" in result["retracted_objects"]              # the wrong object is taken back
    objs = {r["object"] for r in sources.relations(conn, subject="Hund@de", predicate="label")}
    assert objs == {"Q144"}                                   # only the taught object remains
    assert not reactors._open_source_contradiction(conn, "Hund@de|label")


def test_teach_relation_nonfunctional_adds_without_retract():
    conn = _fresh()
    reactors.observe_relation(conn, "Hund", "is_a", "Säugetier", "wikidata")
    result = reactors.teach_relation(conn, "Hund", "is_a", "Haustier", "human")
    assert result["retracted_objects"] == []                  # non-functional: nothing dropped
    objs = {r["object"] for r in sources.relations(conn, subject="Hund", predicate="is_a")}
    assert objs == {"Säugetier", "Haustier"}                  # both parents kept


def test_teach_relation_cli(monkeypatch):
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "label", "Q999", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "label", "Q144", "other")
    monkeypatch.setattr(cli, "get_conn", lambda: conn)
    result = CliRunner().invoke(cli.main, ["teach-relation", "Hund@de", "label", "Q144"])
    assert result.exit_code == 0, result.output
    assert "settled 1 inquiry" in result.output


def test_retract_relation_removes_edge_and_survives_replay():
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q37575615", "wikidata")  # wrong (surname)
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")        # right (dog)
    reactors.retract_relation(conn, "Hund@de", "expresses", "Q37575615", "wikidata")
    assert {r["object"] for r in sources.relations(conn, subject="Hund@de")} == {"Q144"}
    event_router.replay(conn)  # the retraction must be replay-stable
    assert {r["object"] for r in sources.relations(conn, subject="Hund@de")} == {"Q144"}
    conn.close()


def test_retract_relation_without_source_removes_all_copies():
    conn = _fresh()
    reactors.observe_relation(conn, "x", "is_a", "y", "a")
    reactors.observe_relation(conn, "x", "is_a", "y", "b")
    reactors.retract_relation(conn, "x", "is_a", "y")  # no source -> every copy
    assert sources.relations(conn, subject="x") == []
    conn.close()


def test_relations_project_and_rebuild_from_the_log():
    conn = _fresh()
    reactors.observe_relation(conn, "run", "is_a", "verb", "dict")
    reactors.observe_relation(conn, "run", "synonym", "execute", "dict")
    # served from the indexed relation_projection (not an event scan)
    assert len(sources.relations(conn, subject="run")) == 2
    # and the projection rebuilds deterministically from the event log (the scale view)
    event_router.replay(conn)
    assert len(sources.relations(conn, subject="run")) == 2
    assert integrity.check(conn)["ok"] is True
    conn.close()


def test_relations_cli_runs(monkeypatch):
    conn = _fresh()
    reactors.observe_relation(conn, "system.thermal", "correlates_with", "system.load", "experience")
    monkeypatch.setattr(cli, "get_conn", lambda: conn)
    result = CliRunner().invoke(cli.main, ["relations"])
    assert result.exit_code == 0, result.output
    assert "correlates_with" in result.output


def test_resolve_cli_runs(monkeypatch):
    conn = _fresh()
    for temp in (18.0, 18.0):
        _observe(conn, temp)
    _assert_source(conn, 18.0, "wttr.in")
    monkeypatch.setattr(cli, "get_conn", lambda: conn)
    result = CliRunner().invoke(cli.main, ["resolve", CLAIM])
    assert result.exit_code == 0, result.output
    assert "[RSV]" in result.output
    assert "weight" in result.output


def test_assertion_recorded_passes_integrity_and_replays_clean():
    conn = _fresh()
    _observe(conn, 18.0)
    _assert_source(conn, 18.0, "provider-b")
    assert integrity.check(conn)["ok"] is True
    conn.close()


def test_observe_assertion_cli_records_a_source(monkeypatch):
    conn = _fresh()
    monkeypatch.setattr(cli, "get_conn", lambda: conn)
    result = CliRunner().invoke(
        cli.main,
        ["observe-assertion", "--claim-key", CLAIM, "--value", "18.5", "--source", "wttr.in"],
    )
    # the command closes its own connection, so assert on its output, not the conn
    assert result.exit_code == 0, result.output
    assert "[ASR]" in result.output
    assert "wttr.in" in result.output


def test_sources_cli_runs(monkeypatch):
    conn = _fresh()
    for temp in (18.0, 18.0):
        _observe(conn, temp)
    _assert_source(conn, 18.0, "provider-b")
    monkeypatch.setattr(cli, "get_conn", lambda: conn)
    result = CliRunner().invoke(cli.main, ["sources"])
    assert result.exit_code == 0, result.output
    assert "trust" in result.output
    assert "provider-b" in result.output


def test_characterize_knowledge_reports_epistemic_state():
    conn = _fresh()
    reactors.observe_relation(conn, "Hund", "is_a", "Säugetier", "wikidata")
    reactors.observe_relation(conn, "Hund", "is_a", "Säugetier", "curated")    # corroborated
    reactors.observe_relation(conn, "Katze", "is_a", "Säugetier", "wikidata")  # single source
    k = sources.characterize_knowledge(conn)
    assert k["n_relations"] == 2
    assert k["n_uncorroborated"] == 1                  # only Katze rests on one source
    assert 0.0 < k["mean_confidence"] <= 1.0
    assert k["weakest"][0]["subject"] == "Katze"       # least confident surfaced first


def test_characterize_knowledge_counts_open_contradictions():
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "label", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "label", "Q999", "other")  # raises a relation contradiction
    assert sources.characterize_knowledge(conn)["open_contradictions"] == 1


def test_knowledge_cli(monkeypatch):
    conn = _fresh()
    reactors.observe_relation(conn, "Hund", "is_a", "Säugetier", "wikidata")
    monkeypatch.setattr(cli, "get_conn", lambda: conn)
    result = CliRunner().invoke(cli.main, ["knowledge"])
    assert result.exit_code == 0, result.output
    assert "1 relation(s)" in result.output


def test_acquisition_allowed_for_fresh_source():
    from genus import governance
    conn = _fresh()
    assert governance.acquisition_allowed(conn, "wikidata")["allowed"] is True


def test_acquisition_blocked_when_paused():
    from genus import control, governance
    conn = _fresh()
    control.pause("test")
    try:
        verdict = governance.acquisition_allowed(conn, "wikidata")
        assert verdict["allowed"] is False and "paused" in verdict["reason"]
    finally:
        control.resume()


def test_acquisition_blocked_for_untrusted_source(monkeypatch):
    from genus import governance
    conn = _fresh()
    monkeypatch.setattr(sources, "source_trust", lambda c, s: 0.1)  # below seed (0.5)
    verdict = governance.acquisition_allowed(conn, "shady")
    assert verdict["allowed"] is False and "trust" in verdict["reason"]


def test_governance_acquisition_allowed_cli(monkeypatch):
    conn = _fresh()
    monkeypatch.setattr(cli, "get_conn", lambda: conn)
    result = CliRunner().invoke(cli.main, ["governance", "acquisition-allowed", "wikidata"])
    assert result.exit_code == 0, result.output
    assert "allowed" in result.output


def test_concept_meaning_bridges_primary_gloss():
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier, Vorfahre der Wolf", "dbnary")
    reactors.observe_relation(conn, "Q144", "is_a", "Q_mammal", "wikidata")
    c = sources.concept_meaning(conn, "Q144")
    assert "Hund@de" in c["words"] and c["prominent"] == ["Hund@de"]
    assert any("Wolf" in g for g in c["meaning"])      # the concept now carries its meaning
    assert "Q_mammal" in c["is_a"]


def test_concept_meaning_uses_prominent_word_only():
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")            # prominent
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier", "dbnary")
    reactors.observe_relation(conn, "Köter@de", "expresses", "Q144", "wikidata-lexemes")   # secondary
    reactors.observe_relation(conn, "Köter@de", "primary_gloss", "abwertend für Hund", "dbnary")
    c = sources.concept_meaning(conn, "Q144")
    assert c["prominent"] == ["Hund@de"]               # only the Wikidata-prominent word lends meaning
    assert c["meaning"] == ["Haustier"]


def test_concept_cli(monkeypatch):
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier, Vorfahre der Wolf", "dbnary")
    monkeypatch.setattr(cli, "get_conn", lambda: conn)
    result = CliRunner().invoke(cli.main, ["concept", "Q144"])
    assert result.exit_code == 0, result.output
    assert "bedeutet" in result.output and "Wolf" in result.output


def test_model_source_trust_capped_below_seed():
    conn = _fresh()
    assert sources.MODEL_TRUST_SEED < sources.SOURCE_TRUST_SEED
    assert sources.source_trust(conn, "model:embedder") == sources.MODEL_TRUST_SEED  # capped
    assert sources.source_trust(conn, "wikidata") == sources.SOURCE_TRUST_SEED        # grounded stays


def test_model_relation_held_more_lightly_than_grounded():
    conn = _fresh()
    reactors.observe_relation(conn, "x", "is_a", "y", "model:embedder")
    reactors.observe_relation(conn, "a", "is_a", "b", "wikidata")
    model_only = sources.relation_confidence(conn, "x", "is_a", "y")["confidence"]
    grounded = sources.relation_confidence(conn, "a", "is_a", "b")["confidence"]
    assert model_only == sources.MODEL_TRUST_SEED and model_only < grounded


def test_model_cannot_outrank_grounded_even_when_agreeing(monkeypatch):
    conn = _fresh()
    monkeypatch.setattr(sources, "_trust", lambda by_claim, source: 0.9)  # pretend high agreement
    reactors.observe_assertion(conn, "thing.x", "1", "model:llm")
    assert sources.source_trust(conn, "model:llm") == sources.MODEL_TRUST_SEED  # still capped


def test_concept_meaning_includes_model_bound_gloss():
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Q144", "defined_as", "ein Haustier (Embedder-gebunden)", "model:embedder")
    c = sources.concept_meaning(conn, "Q144")
    assert any("Embedder" in g for g in c["meaning"])   # the model's matched gloss surfaces


def test_companion_answers_about_known_word():
    from genus import companion
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier, Vorfahre der Wolf", "dbnary")
    reactors.observe_relation(conn, "Q144", "is_a", "Q_mammal", "wikidata")
    a = companion.answer(conn, "Was ist eigentlich ein Hund?")
    assert a["found"] and a["word"] == "Hund" and a["concept"] == "Q144"
    assert any("Wolf" in m for m in a["meaning"])


def test_companion_unknown_word_falls_through():
    from genus import companion
    conn = _fresh()
    assert companion.answer(conn, "Was ist ein Quux?")["found"] is False


def test_companion_picks_last_known_content_word():
    from genus import companion
    conn = _fresh()
    reactors.observe_relation(conn, "Wort@de", "expresses", "Q_word", "wikidata")
    reactors.observe_relation(conn, "laufen@de", "expresses", "Q_run", "wikidata")
    a = companion.answer(conn, "Was bedeutet das Wort laufen?")  # asked word comes last
    assert a["word"] == "laufen"


def test_ask_cli_routes_to_companion(monkeypatch):
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier, Vorfahre der Wolf", "dbnary")
    monkeypatch.setattr(cli, "get_conn", lambda: conn)
    result = CliRunner().invoke(cli.main, ["ask", "Was", "ist", "ein", "Hund?"])
    assert result.exit_code == 0, result.output
    assert "Wolf" in result.output and "Hund" in result.output
