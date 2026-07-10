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


def test_functional_predicate_contradiction_raises_inquiry(monkeypatch):
    monkeypatch.setattr(sources, "FUNCTIONAL_PREDICATES", {"label"})   # a functional predicate
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "label", "Q144", "wikidata")
    r = reactors.observe_relation(conn, "Hund@de", "label", "Q999", "other")  # disagrees on the label
    types = [e["event_type"] for e in r["events"]]
    assert "contradiction_detected" in types and "inquiry_created" in types
    assert reactors._open_source_contradiction(conn, "Hund@de|label")
    assert sources.relation_contradiction(conn, "Hund@de", "label")["contradiction"] is True


def test_label_not_functional_by_default_no_false_contradiction():
    conn = _fresh()  # a word labels many concepts (homonymy) -> no contradiction by default
    reactors.observe_relation(conn, "Bank@de", "label", "Q_bench", "wikidata")
    r = reactors.observe_relation(conn, "Bank@de", "label", "Q_money", "wikidata-lexemes")
    assert "contradiction_detected" not in [e["event_type"] for e in r["events"]]
    assert sources.relation_contradiction(conn, "Bank@de", "label")["contradiction"] is False


def test_nonfunctional_predicate_allows_many_objects():
    conn = _fresh()
    reactors.observe_relation(conn, "Hund", "is_a", "Säugetier", "wikidata")
    r = reactors.observe_relation(conn, "Hund", "is_a", "Haustier", "wikidata")  # 2nd parent, fine
    assert "contradiction_detected" not in [e["event_type"] for e in r["events"]]
    assert sources.relation_contradiction(conn, "Hund", "is_a")["contradiction"] is False


def test_teach_relation_settles_inquiry_and_corrects_functional(monkeypatch):
    monkeypatch.setattr(sources, "FUNCTIONAL_PREDICATES", {"label"})
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
    monkeypatch.setattr(sources, "FUNCTIONAL_PREDICATES", {"label"})
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


def test_characterize_knowledge_counts_open_contradictions(monkeypatch):
    monkeypatch.setattr(sources, "FUNCTIONAL_PREDICATES", {"label"})
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


def test_companion_answers_verb_at_word_level():
    from genus import companion
    conn = _fresh()  # a verb has glosses + pos but usually no concept node
    reactors.observe_relation(conn, "laufen@de", "primary_gloss", "sich auf den Beinen fortbewegen", "dbnary")
    reactors.observe_relation(conn, "laufen@de", "pos", "verb", "wikidata-lexemes")
    a = companion.answer(conn, "Was bedeutet laufen?")
    assert a["found"] and a["concept"] is None
    assert any("Beinen" in m for m in a["meaning"]) and "verb" in a["pos"]


def test_companion_narrate_is_fluent_and_glassbox():
    from genus import companion
    a = {"found": True, "word": "Hund", "label": "Haushund", "concept": "Q144",
         "pos": ["noun"], "meaning": ["Haustier, dessen Vorfahre der Wolf ist"],
         "is_a": ["Q39201 (Heimtier)", "Q57814795 (domestiziertes Säugetier)"],
         "languages": ["chien", "dog"]}
    s = companion.narrate(a)
    assert s.startswith("Unter »Hund« (Substantiv)") and "Haustier" in s
    # jeder benannte Begriff in Guillemets -- der Stimme-Anker-Schutz (live gefunden: ohne den
    # Schutz wurde "Kernobst" beim Umformulieren unbemerkt zu "Kernaubere")
    assert "»Heimtier« und »domestiziertes Säugetier«" in s and "Q39201" not in s   # labels, no Q-id
    assert "»chien«" in s


def test_companion_narrate_drops_unnameable_parents():
    from genus import companion  # a verb's is_a often includes concepts with no label -> no raw Q-id
    a = {"found": True, "word": "laufen", "label": "laufen", "concept": "Q105674",
         "pos": ["verb"], "meaning": ["sich schnell fortbewegen"],
         "is_a": ["Q106170525", "Q219067 (Fortbewegung)", "Q2535935"], "languages": []}
    s = companion.narrate(a)
    assert "Fortbewegung" in s                       # the one nameable parent is spoken
    assert "Q106170525" not in s and "Q2535935" not in s   # the bare Q-ids are dropped


def test_ask_state_query_wins_over_learned_word(monkeypatch):
    conn = _fresh()  # "Status" is a learned word, but the state query must take precedence
    reactors.observe_relation(conn, "Status@de", "expresses", "Q_status", "wikidata")
    reactors.observe_relation(conn, "Status@de", "primary_gloss", "Art und Weise, wie etwas ist", "dbnary")
    monkeypatch.setattr(cli, "get_conn", lambda: conn)
    result = CliRunner().invoke(cli.main, ["ask", "status"])
    assert result.exit_code == 0, result.output
    assert "Art und Weise" not in result.output   # not the word gloss -> the state answer instead


def _isa_graph():
    conn = _fresh()  # Hund -> Haustier -> Säugetier at concept level; Reptil is known but unconnected
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Haustier@de", "expresses", "Q_pet", "wikidata")
    reactors.observe_relation(conn, "Säugetier@de", "expresses", "Q_mammal", "wikidata")
    reactors.observe_relation(conn, "Reptil@de", "expresses", "Q_reptile", "wikidata")
    reactors.observe_relation(conn, "Q144", "is_a", "Q_pet", "wikidata")
    reactors.observe_relation(conn, "Q_pet", "is_a", "Q_mammal", "wikidata")
    return conn


def test_relate_yes_transitive_shows_the_way():
    from genus import companion
    conn = _isa_graph()
    r = companion.relate(conn, "Ist ein Hund ein Säugetier?")
    assert r["relational"] and r["verdict"] == "yes" and r["target"] == "Q_mammal"
    assert len(r["chain"]) >= 2                       # expresses + is_a hops, glass-box
    s = companion.narrate_relation(conn, r)
    assert s.startswith("Ja.") and "Säugetier" in s and "→" in s   # the path is shown


def test_relate_direct_parent_shows_no_multistep_path():
    from genus import companion
    conn = _isa_graph()
    r = companion.relate(conn, "Ist ein Hund ein Haustier?")
    assert r["verdict"] == "yes" and r["target"] == "Q_pet"
    assert "→" not in companion.narrate_relation(conn, r)          # one hop, no way to trace out


def test_relate_no_path_withholds_not_denies():
    from genus import companion
    conn = _isa_graph()   # both concepts known, but no is_a connection between them
    r = companion.relate(conn, "Ist ein Hund ein Reptil?")
    assert r["relational"] and r["verdict"] == "no_path"
    assert "nicht widerlegt" in companion.narrate_relation(conn, r)  # open-world honesty


def test_relate_unknown_terms_fall_through():
    from genus import companion
    conn = _isa_graph()
    assert companion.relate(conn, "Ist ein Quux ein Blarg?")["relational"] is False


def test_relate_is_case_lenient():
    from genus import companion
    conn = _isa_graph()
    assert companion.relate(conn, "ist ein hund ein säugetier?")["verdict"] == "yes"


def _kausal_graph():
    conn = _fresh()  # Feuer->Rauch->Smog (causes); Grippe verursacht Fieber (numerische Q-ids wie live)
    for w, q in (("Feuer", "Q901"), ("Rauch", "Q902"), ("Smog", "Q903"),
                 ("Fieber", "Q904"), ("Grippe", "Q905")):
        reactors.observe_relation(conn, f"{w}@de", "expresses", q, "wikidata")
    reactors.observe_relation(conn, "Q901", "causes", "Q902", "wikidata")
    reactors.observe_relation(conn, "Q902", "causes", "Q903", "wikidata")
    reactors.observe_relation(conn, "Q905", "causes", "Q904", "wikidata")
    return conn


def test_kausal_ja_direkt():
    from genus import companion
    conn = _kausal_graph()
    r = companion.relate_kausal(conn, "Verursacht Feuer Rauch?")
    assert r["kausal_q"] and r["art"] == "ja"
    assert companion.narrate_kausal(conn, r) == "Ja. »Feuer« verursacht »Rauch«."


def test_kausal_ja_transitiv_zeigt_den_weg():
    from genus import companion
    conn = _kausal_graph()   # Feuer -> Rauch -> Smog: mediierte Kausation, der Weg wird gezeigt
    r = companion.relate_kausal(conn, "Verursacht Feuer Smog?")
    assert r["art"] == "ja"
    s = companion.narrate_kausal(conn, r)
    assert "Kausalkette" in s and "→" in s and "»Rauch«" in s


def test_kausal_was_verursacht_listet_ursachen():
    from genus import companion
    conn = _kausal_graph()
    r = companion.relate_kausal(conn, "Was verursacht Fieber?")
    assert r["art"] == "ursachen" and "Grippe" in r["ursachen"]
    assert "»Grippe«" in companion.narrate_kausal(conn, r)


def test_kausal_unbekannt_haelt_zurueck_statt_zu_verneinen():
    from genus import companion
    conn = _kausal_graph()   # „Rauch verursacht Feuer?" -> kein Pfad (Fluss geht Feuer->Rauch)
    r = companion.relate_kausal(conn, "Verursacht Rauch Feuer?")
    assert r["art"] == "unbekannt"
    assert "kenne ich nicht" in companion.narrate_kausal(conn, r)   # open-world, kein „nein"


def test_kausal_unbekannte_begriffe_fallen_durch():
    from genus import companion
    conn = _kausal_graph()
    assert companion.relate_kausal(conn, "Verursacht Quux Blarg?")["kausal_q"] is False


def test_kausal_synonym_ist_keine_erfundene_kausation():
    # X und Y lösen auf DASSELBE Konzept auf (Synonyme) -> keine „Ja"-Aussage aus dem Identitäts-
    # Kurzschluss (Review-Fund HOCH: sonst „Ja, Feuer verursacht Flamme" mit NULL causes-Kanten)
    from genus import companion
    conn = _kausal_graph()
    reactors.observe_relation(conn, "Flamme@de", "expresses", "Q901", "wikidata")   # Synonym von Feuer
    r = companion.relate_kausal(conn, "Verursacht Feuer Flamme?")
    assert r["art"] == "unbekannt"
    assert "kenne ich nicht" in companion.narrate_kausal(conn, r)


def test_kausal_ohne_bekannte_ursache_antwortet_ehrlich():
    # „Was verursacht Feuer?" — nichts verursacht Feuer -> ehrliche Nicht-Antwort auf die KAUSAL-
    # Frage (kanal-sicher: im Bot führt Durchfallen zu „nicht verstanden", nicht zur Definition)
    from genus import companion
    conn = _kausal_graph()
    r = companion.relate_kausal(conn, "Was verursacht Feuer?")
    assert r["kausal_q"] is True and r["art"] == "ursachen" and r["ursachen"] == []
    assert "kenne ich nicht" in companion.narrate_kausal(conn, r)


# --- Voice 1 („warm & direkt"): „Rahmen frei, Kern fest" (Antwort-Seele, Scheibe 1) --------
#
# Der warme Ton wird über eine Belegung mit Wärme ≥ „warm" gewählt (der Antwort-Würfel steuert).
# Der Fakt-Kern -- die Begriffe in »«, die Vertrauens-Zahl, die Richtung Subjekt→Objekt -- steht
# in beiden Tönen wortgleich und deterministisch platziert; ohne Belegung bleibt der nüchterne
# Wortlaut byte-genau wie zuvor (CLI/why).

_WARM = {"waerme": "warm"}


def test_narrate_relation_ohne_belegung_bleibt_byte_genau_wie_zuvor():
    from genus import companion
    conn = _isa_graph()
    r = companion.relate(conn, "Ist ein Hund ein Haustier?")
    assert companion.narrate_relation(conn, r) == (
        "Ja. »Hund« zählt zu »Haustier«. "
        "(Vertrauen 0.50 — aus dem Wissensgraphen hergeleitet, nicht behauptet.)")


def test_narrate_relation_warm_ist_voice_eins_mit_festem_kern():
    from genus import companion
    conn = _isa_graph()
    r = companion.relate(conn, "Ist ein Hund ein Haustier?")
    warm = companion.narrate_relation(conn, r, _WARM)
    assert warm.startswith("Ja, klar —")                 # der warme Rahmen
    assert "»Hund« zählt zu »Haustier«" in warm          # der Kern
    assert "0.50" in warm                                # die Vertrauens-Zahl überlebt wortgleich
    assert "Wissensnetz" in warm and "nicht behauptet" in warm


def test_narrate_relation_warm_richtung_kann_nicht_kippen():
    # „Kern fest": das Subjekt steht IMMER vor dem Objekt -- deterministisch platziert, keine Umkehr
    from genus import companion
    conn = _isa_graph()
    r = companion.relate(conn, "Ist ein Hund ein Haustier?")
    warm = companion.narrate_relation(conn, r, _WARM)
    assert warm.index("»Hund«") < warm.index("»Haustier«")


def test_narrate_relation_warm_niedriges_vertrauen_bleibt_ehrlich():
    # gestufte Ehrlichkeit: „ziemlich sicher" steht nie über einem schwachen Vertrauen
    from genus import companion
    conn = _isa_graph()
    r = companion.relate(conn, "Ist ein Hund ein Haustier?")
    r["trust"] = 0.30
    warm = companion.narrate_relation(conn, r, _WARM)
    assert "Ganz sicher bin ich mir da nicht" in warm and "0.30" in warm


def test_narrate_kausal_warm_und_plain_teilen_den_kern():
    from genus import companion
    conn = _kausal_graph()
    r = companion.relate_kausal(conn, "Was verursacht Fieber?")
    assert companion.narrate_kausal(conn, r) == "Als Ursache von »Fieber« kenne ich: »Grippe«."
    warm = companion.narrate_kausal(conn, r, _WARM)
    assert warm.startswith("Klar, dazu kenne ich etwas")
    assert "»Fieber«" in warm and "»Grippe«" in warm


def test_konversation_waermt_beziehung_der_reine_respond_bleibt_nuechtern():
    # der Gesprächs-Einstieg (respond_with_deuter) trägt Voice 1; der CLI-nahe respond() bleibt plain
    from genus import companion
    conn = _isa_graph()
    warm = companion.respond_with_deuter(conn, "Ist ein Hund ein Haustier?")["text"]
    plain = companion.respond(conn, "Ist ein Hund ein Haustier?")
    assert warm.startswith("Ja, klar —") and plain.startswith("Ja. »Hund«")
    assert "»Hund« zählt zu »Haustier«" in warm and "»Hund« zählt zu »Haustier«" in plain


def test_beziehung_ist_wortlautfest_die_stimme_dreht_nicht_um():
    # gerichtete Relations-/Kausal-Aussagen („A verursacht B") dürfen NICHT vom Modell umformuliert
    # werden -- die Substantiv-Leine prüft Vorkommen, nicht Richtung (live-Fund: Stimme kehrte um)
    from genus import companion, werkzeug
    companion.registriere_zellen()
    assert werkzeug.stimme_geeignet(f"{companion.ZELLE_PREFIX}beziehung") is False


def test_muster_antwort_routet_die_kausal_frage():
    from genus import companion
    conn = _kausal_graph()
    text, zelle = companion._muster_antwort(conn, "Verursacht Feuer Rauch?")
    assert "verursacht" in text and zelle == "beziehung"


# --- P3.1: die freie Kausalfrage über den Deuter (das „ursache"-Blatt hat jetzt einen Handler) ---

def test_deuter_ursache_blatt_erreicht_die_kausal_faehigkeit():
    # das „ursache"-Blatt bekam früher keinen Handler und kletterte zur Zelle frage-begriff ->
    # es gab die DEFINITION von X statt seiner URSACHEN (eine andere Frage). Jetzt führt eine als
    # „ursache" gelesene Frage zur gebauten Kausal-Fähigkeit -- die Ursachen, nicht die Definition.
    from genus import companion
    conn = _kausal_graph()
    guess = {"absicht": "ursache", "subject": "Fieber", "object": None}
    a = companion._deuter_antwort(conn, guess, "Wodurch entsteht Fieber?", None)
    assert a is not None and a["kind"] == "ursache"
    assert "»Grippe«" in a["text"] and "Ursache" in a["text"]


def test_deuter_beziehung_blatt_traegt_auch_die_gerichtete_kausation():
    # „Führt X zu Y?": beide Begriffe bekannt, KEINE is_a-Kante -> _relate_terms gibt
    # relational=True/verdict=no_path. Dieser Fall darf NICHT von der is_a-Zurückhaltung
    # geschluckt werden (sonst „zählt nicht nachweislich zu" statt der echten Kausalkette).
    from genus import companion
    conn = _kausal_graph()
    guess = {"absicht": "beziehung", "subject": "Feuer", "object": "Smog"}
    a = companion._deuter_antwort(conn, guess, "Führt Feuer zu Smog?", None)
    assert a is not None and a["kind"] == "beziehung"
    assert "Kausalkette" in a["text"] and "»Rauch«" in a["text"]


def test_zelle_beziehung_is_a_ja_schlaegt_kausal_und_no_path_bleibt_ehrlich():
    # Reihenfolge is_a-Ja > Kausal-Ja > ehrliche is_a-Zurückhaltung: eine echte is_a-Einordnung
    # gewinnt; und wo weder is_a-ja noch belegte Kausation besteht (Rauch->Feuer: kein Pfad),
    # bleibt die ehrliche is_a-Zurückhaltung erhalten -- der Kausal-Zweig verschluckt sie nicht.
    from genus import companion
    conn = _kausal_graph()
    reactors.observe_relation(conn, "Q902", "is_a", "Q903", "wikidata")   # Rauch is_a Smog (künstlich)
    ja = companion._zelle_beziehung(conn, {"subject": "Rauch", "object": "Smog"},
                                    "Zählt Rauch zu Smog?", None, None)
    assert ja is not None and "→" not in ja                              # is_a-Ja, kein Kausalpfad
    ehrlich = companion._zelle_beziehung(conn, {"subject": "Rauch", "object": "Feuer"},
                                         "Führt Rauch zu Feuer?", None, None)
    assert ehrlich is not None and "nicht widerlegt" in ehrlich          # ehrliche Zurückhaltung


def test_zelle_ursache_ohne_bekanntes_subjekt_klettert_ehrlich():
    # unauflösbares subject -> _zelle_ursache gibt None, damit der Dispatch ehrlich weiterklettert
    # (statt eine Kausal-Antwort über einen unbekannten Begriff zu erfinden)
    from genus import companion
    conn = _kausal_graph()
    a = companion._zelle_ursache(conn, {"subject": "Quux", "object": None},
                                 "Was verursacht Quux?", None, None)
    assert a is None


def test_ursache_und_beziehung_sind_wortlautfest():
    # beide Kausal-Zellen sind gerichtet -> sie dürfen NICHT der Stimme angeboten werden
    from genus import companion, werkzeug
    companion.registriere_zellen()
    assert werkzeug.stimme_geeignet(f"{companion.ZELLE_PREFIX}ursache") is False
    assert werkzeug.stimme_geeignet(f"{companion.ZELLE_PREFIX}beziehung") is False


def test_ask_cli_routes_relational_question(monkeypatch):
    conn = _isa_graph()  # a relational question reaches the inference route, not the word lookup
    monkeypatch.setattr(cli, "get_conn", lambda: conn)
    result = CliRunner().invoke(cli.main, ["ask", "Ist", "ein", "Hund", "ein", "Säugetier?"])
    assert result.exit_code == 0, result.output
    assert "Ja." in result.output and "Säugetier" in result.output


def _kinship_graph():
    conn = _fresh()  # Hund & Katze meet at Säugetier (→ Tier); Auto is unrelated
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q_hund", "wikidata")
    reactors.observe_relation(conn, "Katze@de", "expresses", "Q_katze", "wikidata")
    reactors.observe_relation(conn, "Säugetier@de", "expresses", "Q_saeug", "wikidata")
    reactors.observe_relation(conn, "Tier@de", "expresses", "Q_tier", "wikidata")
    reactors.observe_relation(conn, "Auto@de", "expresses", "Q_auto", "wikidata")
    reactors.observe_relation(conn, "Q_hund", "is_a", "Q_saeug", "wikidata")
    reactors.observe_relation(conn, "Q_katze", "is_a", "Q_saeug", "wikidata")
    reactors.observe_relation(conn, "Q_saeug", "is_a", "Q_tier", "wikidata")
    return conn


def test_common_finds_closest_shared_ancestor():
    from genus import companion
    conn = _kinship_graph()
    r = companion.common(conn, "Was haben ein Hund und eine Katze gemeinsam?")
    assert r["common"] and r["found"] and r["shared"][0] == "Q_saeug"   # Säugetier is closest
    s = companion.narrate_common(conn, r)
    assert "Säugetier" in s and "Tier" in s                             # closest, then the farther one


def test_common_skips_unnameable_ancestors():
    from genus import companion
    conn = _kinship_graph()  # insert a wordless concept between Säugetier and Tier
    reactors.observe_relation(conn, "Q_saeug", "is_a", "Q_nolabel", "wikidata")
    reactors.observe_relation(conn, "Q_nolabel", "is_a", "Q_tier", "wikidata")
    r = companion.common(conn, "Was haben ein Hund und eine Katze gemeinsam?")
    assert "Q_nolabel" not in r["shared"]                       # no raw Q-id reaches a human
    assert "Q_saeug" in r["shared"] and "Q_tier" in r["shared"]  # the nameable ones stay


def test_common_none_when_unrelated():
    from genus import companion
    conn = _kinship_graph()
    r = companion.common(conn, "Was haben ein Hund und ein Auto gemeinsam?")
    assert r["common"] and r["found"] is False
    assert "keine gemeinsame" in companion.narrate_common(conn, r)


def test_narrate_common_warm_ist_voice_eins_mit_festem_kern():
    # vergleich „mitgenommen" (Antwort-Seele, gleiche Mechanik wie beziehung/ursache)
    from genus import companion
    conn = _kinship_graph()
    r = companion.common(conn, "Was haben ein Hund und eine Katze gemeinsam?")
    plain = companion.narrate_common(conn, r)
    warm = companion.narrate_common(conn, r, _WARM)
    assert plain.startswith("»Hund« und »Katze« haben gemeinsam:")   # nüchtern, byte-genau wie zuvor
    assert "ja, die haben was gemeinsam" in warm                      # der warme Rahmen (Voice 1)
    assert "beide zählen zu" in warm and "Säugetier" in warm          # der Fakt-Kern steht
    assert "»Hund«" in warm and "»Katze«" in warm


def test_common_not_triggered_by_plain_question():
    from genus import companion
    conn = _kinship_graph()
    assert companion.common(conn, "Was ist ein Hund?")["common"] is False


def test_ask_cli_routes_comparative(monkeypatch):
    conn = _kinship_graph()
    monkeypatch.setattr(cli, "get_conn", lambda: conn)
    result = CliRunner().invoke(cli.main, ["ask", "Was", "haben", "Hund", "und", "Katze", "gemeinsam?"])
    assert result.exit_code == 0, result.output
    assert "gemeinsam" in result.output and "Säugetier" in result.output


def test_why_relation_lays_open_every_premise():
    from genus import companion
    conn = _isa_graph()
    t = companion.trace(conn, "Ist ein Hund ein Säugetier?")
    assert t["kind"] == "relation" and t["verdict"] == "yes"
    text = "\n".join(companion.render_trace(conn, t))
    assert "expresses" in text and "is_a" in text          # every hop laid open
    assert "wikidata" in text                               # the source is named
    assert "schwächste Prämisse" in text                   # composed trust = weakest premise


def test_why_word_shows_grounding_sources():
    from genus import companion
    conn = _isa_graph()
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier, Vorfahre der Wolf", "dbnary")
    t = companion.trace(conn, "Was ist ein Hund?")
    assert t["kind"] == "word"
    text = "\n".join(companion.render_trace(conn, t))
    assert "dbnary" in text and "Wolf" in text              # the meaning and where it came from
    assert "expresses" in text and "is_a" in text           # grounding + hierarchy provenance


def test_why_no_path_has_nothing_to_show():
    from genus import companion
    conn = _isa_graph()
    text = "\n".join(companion.render_trace(conn, companion.trace(conn, "Ist ein Hund ein Reptil?")))
    assert "Nichts zu belegen" in text


def test_why_unknown_is_honest():
    from genus import companion
    conn = _isa_graph()
    t = companion.trace(conn, "Was ist ein Quux?")
    assert t["kind"] == "none" and "kennt kein Wort" in "\n".join(companion.render_trace(conn, t))


def test_why_cli_traces_a_relation(monkeypatch):
    conn = _isa_graph()
    monkeypatch.setattr(cli, "get_conn", lambda: conn)
    result = CliRunner().invoke(cli.main, ["why", "answer", "Ist", "ein", "Hund", "ein", "Säugetier?"])
    assert result.exit_code == 0, result.output
    assert "[WHY]" in result.output and "Säugetier" in result.output and "Vertrauen" in result.output


def test_werkzeuge_cli_lists_all_registered_werkzeuge_with_flags():
    result = CliRunner().invoke(cli.main, ["werkzeuge"])
    assert result.exit_code == 0, result.output
    assert "ableitung(" in result.output and "wortlautfest" in result.output
    assert "prüfbar_als=sympy" in result.output


def test_ableitung_cli_computes_exactly():
    result = CliRunner().invoke(cli.main, ["ableitung", "3x^2 + 2x"])
    assert result.exit_code == 0, result.output
    assert "[MATH]" in result.output and "6*x + 2" in result.output


def test_ableitung_cli_honestly_fails_on_gibberish():
    result = CliRunner().invoke(cli.main, ["ableitung", "quatsch mit soße"])
    assert result.exit_code == 1
    assert "kein bekanntes Symbol" in result.output


def test_ableitung_cli_respects_variable_and_ordnung_options():
    result = CliRunner().invoke(cli.main, ["ableitung", "x^3 - 3x", "--ordnung", "2"])
    assert result.exit_code == 0, result.output
    assert "f''(x)" in result.output and "6*x" in result.output


def test_extremstellen_cli_reports_both_points():
    result = CliRunner().invoke(cli.main, ["extremstellen", "x^3 - 3x"])
    assert result.exit_code == 0, result.output
    assert "Maximum bei x = -1" in result.output and "Minimum bei x = 1" in result.output


def test_stammfunktion_cli_shows_the_integration_constant():
    result = CliRunner().invoke(cli.main, ["stammfunktion", "3x^2 + 2x"])
    assert result.exit_code == 0, result.output
    assert "x**3 + x**2 + C" in result.output


def test_integral_cli_computes_between_bounds():
    result = CliRunner().invoke(cli.main, ["integral", "x^2", "0", "3"])
    assert result.exit_code == 0, result.output
    assert "= 9" in result.output


def test_integral_cli_honestly_fails_on_an_unreadable_bound():
    result = CliRunner().invoke(cli.main, ["integral", "x^2", "0", "quatsch"])
    assert result.exit_code == 1
    assert "kein bekanntes Symbol" in result.output


def test_why_followup_recognizes_the_closed_set_of_cue_phrases():
    from genus import companion
    for phrase in ("warum?", "Warum", "wieso??", "  weshalb ", "Woher weißt du das?",
                   "woher kommt das", "Woher hast du das?"):
        assert companion.is_why_followup(phrase), phrase
    for phrase in ("warum ist ein Hund ein Säugetier?", "Was ist ein Hund?", ""):
        assert not companion.is_why_followup(phrase), phrase


def test_is_backreference_recognizes_von_vorhin_and_von_eben():
    from genus import companion
    for phrase in ("was frisst das Tier von vorhin", "und was meintest du von eben",
                   "VON VORHIN nochmal"):
        assert companion.is_backreference(phrase), phrase
    for phrase in ("Was ist ein Fahrrad?", "warum?", "ich habe Angst davor", ""):
        assert not companion.is_backreference(phrase), phrase


def test_backreference_reanswers_the_earlier_question_not_the_last_one():
    # Mehr-Zug-Arbeitsgedächtnis (Punkt 4): "von vorhin" reicht über die letzte Runde hinaus --
    # last_question/last_answer sind ein Gruss (kein bekanntes Wort), verlauf[0] trägt Fahrrad
    from genus import companion
    conn = _fahrrad_graph()
    reactors.observe_relation(conn, "Fahrrad@de", "primary_gloss", "ein Zweirad zum Fahren", "dbnary")
    verlauf = [{"question": "Was ist ein Fahrrad?", "answer": "ein Zweirad zum Fahren."}]
    result = companion.respond_with_deuter(
        conn, "was war das nochmal von vorhin?", last_question="Hallo!", last_answer="Hallo!",
        verlauf=verlauf,
    )
    assert "Zweirad" in result["text"]
    assert "frühere Frage" in result["text"] and "Was ist ein Fahrrad?" in result["text"]
    assert result["question"] == "Was ist ein Fahrrad?"   # anchor moves to the retraced topic


def test_backreference_without_any_resolvable_earlier_turn_falls_through():
    from genus import companion
    conn = _fahrrad_graph()
    verlauf = [{"question": "Hallo!", "answer": "Hallo, was kann ich für dich tun?"}]
    result = companion.respond_with_deuter(
        conn, "und das von vorhin?", last_question="Danke!", last_answer="Gern!", verlauf=verlauf,
    )
    assert "frühere Frage" not in result["text"]   # nothing in verlauf had a known word -- honest fallthrough


def test_backreference_is_a_noop_without_verlauf_or_without_the_cue():
    from genus import companion
    conn = _fahrrad_graph()
    reactors.observe_relation(conn, "Fahrrad@de", "primary_gloss", "ein Zweirad zum Fahren", "dbnary")
    baseline = companion.respond_with_deuter(conn, "Was ist ein Fahrrad?")
    with_empty_verlauf = companion.respond_with_deuter(conn, "Was ist ein Fahrrad?", verlauf=[])
    assert baseline == with_empty_verlauf


def test_conversation_retraces_the_previous_relational_answer():
    from genus import companion
    conn = _isa_graph()
    first = companion.respond_in_conversation(conn, "Ist ein Hund ein Säugetier?")
    # Voice 1 (Scheibe 1): der Rahmen ist warm, der Fakt-Kern steht wortgleich
    assert "»Hund« zählt zu »Säugetier«" in first["text"] and first["question"] == "Ist ein Hund ein Säugetier?"

    followup = companion.respond_in_conversation(conn, "warum?", last_question=first["question"])
    assert "Herleitung" in followup["text"] and "Vertrauen" in followup["text"]
    assert "wikidata" in followup["text"]                    # the same sourced chain, retraced
    assert followup["question"] == first["question"]         # still anchored on the same topic


def test_conversation_retraces_the_previous_word_answer():
    from genus import companion
    conn = _isa_graph()
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier, Vorfahre der Wolf", "dbnary")
    first = companion.respond_in_conversation(conn, "Was ist ein Hund?")
    assert "Hund" in first["text"]

    followup = companion.respond_in_conversation(conn, "Woher weißt du das?", last_question=first["question"])
    assert "dbnary" in followup["text"] and "Wolf" in followup["text"]   # the grounding, not a re-explanation


def test_natural_question_reaches_the_word_not_the_command_table():
    from genus import companion  # the "Was ist ein Netzwerk?" shadowing bug, end-to-end
    conn = _fresh()
    reactors.observe_relation(conn, "Netzwerk@de", "expresses", "Q1301371", "wikidata")
    reactors.observe_relation(conn, "Netzwerk@de", "primary_gloss", "Verbund verbundener Systeme", "dbnary")
    text = companion.respond(conn, "Was ist ein Netzwerk?")
    assert "Verbund" in text
    assert "operation record" not in text


def test_companion_tells_its_open_questions_in_german():
    from genus import companion, inquiries
    conn = _fresh()
    # two stability surprises on the SAME claim (must group to one spoken line with a count)
    for i in (1, 2):
        inquiries.record_inquiry_created_event(
            conn, inquiry_id=i, inquiry_type="StabilityInquiry", claim_key="weather.trend",
            source_belief=None, source_event=1, question_key="stability.unexpected_flip",
            payload={"expected": "stable", "observed": "flipped"},
        )
    # and the real flagged is_a ring, with labelled concepts (label edge = Wort@de -label-> Q)
    reactors.observe_relation(conn, "Datenträger@de", "label", "Q101", "wikidata")
    reactors.observe_relation(conn, "Medien@de", "label", "Q202", "wikidata")
    inquiries.record_inquiry_created_event(
        conn, inquiry_id=3, inquiry_type="SourceContradiction", claim_key="Q101|is_a|Q202|acyclic",
        source_belief=None, source_event=1, question_key="source.contradiction",
        payload={"kind": "acyclicity_violation", "subject": "Q101", "object": "Q202", "predicate": "is_a"},
    )

    text = companion.respond(conn, "Was beschäftigt dich gerade?")

    assert "Mich beschäftigen gerade 2 Dinge" in text
    assert "weather.trend" in text and "2-mal" in text          # grouped, not two lines
    assert "Kreis" in text and "Datenträger" in text and "Medien" in text
    assert "Q101" not in text                                    # labels, never raw Q-ids
    assert "genus teach" in text                                 # the honest read-only note


def test_companion_with_nothing_open_says_so():
    from genus import companion
    conn = _fresh()
    assert "nichts Offenes" in companion.respond(conn, "Hast du Fragen?")


def test_voice_hedges_a_weakly_backed_meaning():
    from genus import companion  # meaning carried only by the capped model bridge (0.25 < seed)
    conn = _fresh()
    reactors.observe_relation(conn, "Blub@de", "primary_gloss", "eine Testbedeutung", "model:embedder")
    a = companion.answer(conn, "Was ist ein Blub?")
    assert a["meaning_confidence"] < 0.5
    assert "unsicher" in companion.narrate(a)


def test_voice_names_independent_corroboration():
    from genus import companion  # two independent sources carry the same gloss (0.75 > seed)
    conn = _fresh()
    reactors.observe_relation(conn, "Blub@de", "primary_gloss", "eine Testbedeutung", "dbnary")
    reactors.observe_relation(conn, "Blub@de", "primary_gloss", "eine Testbedeutung", "wikidata-lexemes")
    a = companion.answer(conn, "Was ist ein Blub?")
    assert a["meaning_sources"] == 2
    assert "mehrfach unabhängig belegt" in companion.narrate(a)


def test_voice_stays_neutral_for_an_ordinary_single_source():
    from genus import companion  # one seed-trust source = the normal case, no crying wolf
    conn = _fresh()
    reactors.observe_relation(conn, "Blub@de", "primary_gloss", "eine Testbedeutung", "dbnary")
    s = companion.narrate(companion.answer(conn, "Was ist ein Blub?"))
    assert "unsicher" not in s and "mehrfach" not in s


def test_followup_without_a_previous_question_falls_through_honestly():
    from genus import companion
    conn = _isa_graph()
    result = companion.respond_in_conversation(conn, "warum?", last_question=None)
    assert result["question"] == "warum?"
    assert result["text"] == companion.respond(conn, "warum?")   # no state to retrace -> ordinary routing
    assert "Herleitung" not in result["text"]                    # never mislabeled as a trace


def test_a_real_question_is_never_mistaken_for_a_followup():
    from genus import companion
    conn = _isa_graph()
    result = companion.respond_in_conversation(conn, "Was ist ein Hund?", last_question="Ist ein Hund ein Säugetier?")
    assert "Herleitung" not in result["text"]          # routed through respond(), not the why-trace
    assert result["question"] == "Was ist ein Hund?"   # a real question always overrides, never a stale one


def test_stimme_rephrases_a_deterministic_word_answer():
    from genus import companion
    conn = _isa_graph()
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier, Vorfahre der Wolf", "dbnary")
    stimme = lambda satz: "»Hund« ist laut GENUS ein Haustier, das vom Wolf abstammt."
    result = companion.respond_with_deuter(conn, "Was ist ein Hund?", stimme=stimme)
    assert result["text"].startswith("»Hund« ist laut GENUS")
    assert "Sprachlich vom Modell geglättet" in result["text"]


def test_stimme_laesst_gerichtete_relation_wortlautfest():
    # eine GERICHTETE Relations-Antwort wird NICHT vom Modell umformuliert (Richtungs-Umkehr-Schutz,
    # live-Fund 2026-07-06): selbst eine angebotene Stimme greift nicht, das Template steht.
    from genus import companion
    conn = _isa_graph()
    stimme = lambda satz: "»Säugetier« gehört laut GENUS zu »Hund«."   # das Modell KÖNNTE umkehren
    result = companion.respond_with_deuter(conn, "Ist ein Hund ein Säugetier?", stimme=stimme)
    assert "»Säugetier« gehört laut GENUS zu »Hund«" not in result["text"]   # die Umkehrung greift NIE
    assert "geglättet" not in result["text"]                                # wortlautfest -> keine Stimme
    assert "»Hund« zählt zu »Säugetier«" in result["text"]                   # der Fakt-Kern (Richtung!) steht


def test_stimme_none_or_failed_rephrase_keeps_the_original_template():
    from genus import companion
    conn = _isa_graph()
    baseline = companion.respond_with_deuter(conn, "Ist ein Hund ein Säugetier?")
    for stimme in (None, lambda satz: None):
        result = companion.respond_with_deuter(conn, "Ist ein Hund ein Säugetier?", stimme=stimme)
        assert result == baseline
        assert "geglättet" not in result["text"]


def test_stimme_also_reaches_the_deuter_driven_definition_cell():
    # live fund (2026-07-03): "Was ist ein Hund?" runs through the DEUTER path now (it sits
    # before the plain word reading), not through _wort_antwort directly -- Stimme must reach
    # it there too, or the single most common conversational pattern never gets rephrased
    from genus import companion
    conn = _isa_graph()
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier, Vorfahre der Wolf", "dbnary")
    deuter = lambda q: {"absicht": "definition", "subject": "Hund"}
    stimme = lambda satz: "»Hund« ist laut GENUS ein Haustier, das vom Wolf abstammt."
    result = companion.respond_with_deuter(conn, "was ist eigentlich ein wuffwuff", deuter=deuter, stimme=stimme)
    assert result["text"].startswith("»Hund« ist laut GENUS")
    assert "Sprachlich vom Modell geglättet" in result["text"]
    assert "Sprachmodell gedeutet" in result["text"]   # both disclosures survive, never silent


def test_stimme_is_not_consulted_for_rituals_or_the_honest_fallback():
    # the first slice is deliberately scoped to Muster/Wort cells -- memory, recall, and the
    # honest "nichts erkannt" fallback are left exactly as they are (no value in rephrasing a
    # short, already-clear sentence, and less surface for a faithfulness slip)
    from genus import companion
    conn = _isa_graph()
    calls = []
    stimme = lambda satz: (calls.append(satz) or None)
    companion.respond_with_deuter(conn, "Merke dir: ich mag Kaffee", stimme=stimme)
    companion.respond_with_deuter(conn, "asdf ganz unklare frage", stimme=stimme)
    assert calls == []


def _fahrrad_graph():
    conn = _fresh()
    reactors.observe_relation(conn, "Fahrrad@de", "expresses", "Q_fahrrad", "wikidata")
    return conn


def test_notiz_bezug_finds_a_confirmed_note_sharing_a_word_with_the_question():
    from genus import companion, erinnerung
    conn = _fahrrad_graph()
    erinnerung.merke(conn, "mein Fahrrad hat einen Platten", quelle="ronny")
    aside = companion._notiz_bezug(conn, "Was ist ein Fahrrad?")
    assert aside is not None and "Platten" in aside and "Nebenbei" in aside


def test_notiz_bezug_marks_a_suggested_note_as_unconfirmed():
    from genus import companion, erinnerung
    conn = _fahrrad_graph()
    erinnerung.merke(conn, "mein Fahrrad hat einen Platten", quelle=erinnerung.STATEMENT_SOURCE)
    aside = companion._notiz_bezug(conn, "Was ist ein Fahrrad?")
    assert aside is not None and "noch unbestätigt" in aside


def test_notiz_bezug_prefers_a_confirmed_note_over_a_suggested_one():
    from genus import companion, erinnerung
    conn = _fahrrad_graph()
    erinnerung.merke(conn, "ich hatte mal ein altes Fahrrad", quelle=erinnerung.STATEMENT_SOURCE)
    erinnerung.merke(conn, "mein Fahrrad hat einen Platten", quelle="ronny")   # told later -- confirmed wins
    aside = companion._notiz_bezug(conn, "Was ist ein Fahrrad?")
    assert "Platten" in aside and "noch unbestätigt" not in aside


def test_notiz_bezug_ignores_short_words_and_unrelated_notes():
    from genus import companion, erinnerung
    conn = _fahrrad_graph()
    erinnerung.merke(conn, "ich mag Kaffee", quelle="ronny")
    assert companion._notiz_bezug(conn, "Was ist ein Fahrrad?") is None   # no shared concept
    assert companion._notiz_bezug(conn, "Wie ist das Wetter?") is None


def test_notiz_bezug_returns_none_without_any_notes():
    from genus import companion
    conn = _isa_graph()
    assert companion._notiz_bezug(conn, "Was ist ein Hund?") is None


def test_respond_with_deuter_weaves_a_note_into_a_word_answer_on_the_bot_path():
    from genus import companion, erinnerung
    conn = _fahrrad_graph()
    reactors.observe_relation(conn, "Fahrrad@de", "primary_gloss", "ein Zweirad zum Fahren", "dbnary")
    erinnerung.merke(conn, "mein Fahrrad hat einen Platten", quelle="ronny")
    result = companion.respond_with_deuter(conn, "Was ist ein Fahrrad?", deuter=lambda q: None)
    assert "Zweirad" in result["text"] and "Nebenbei" in result["text"] and "Platten" in result["text"]


def test_note_weaving_is_off_for_the_cli_path_deuter_none():
    # respond_with_deuter(deuter=None) must exactly reproduce respond_in_conversation --
    # the CLI never gets a beiläufig-personalised answer, only the explicit recall command does
    from genus import companion, erinnerung
    conn = _fahrrad_graph()
    reactors.observe_relation(conn, "Fahrrad@de", "primary_gloss", "ein Zweirad zum Fahren", "dbnary")
    erinnerung.merke(conn, "mein Fahrrad hat einen Platten", quelle="ronny")
    result = companion.respond_with_deuter(conn, "Was ist ein Fahrrad?")
    assert "Nebenbei" not in result["text"]
    assert result == companion.respond_in_conversation(conn, "Was ist ein Fahrrad?")


def test_note_weaving_is_not_applied_to_remember_or_recall_or_the_honest_fallback():
    # weaving a note right next to recording/recalling notes would be circular/confusing
    from genus import companion, erinnerung
    conn = _fahrrad_graph()
    erinnerung.merke(conn, "mein Fahrrad hat einen Platten", quelle="ronny")
    gemerkt = companion.respond_with_deuter(conn, "Merke dir: ich mag auch Zugfahren", deuter=lambda q: None)
    assert "Nebenbei" not in gemerkt["text"]
    abgerufen = companion.respond_with_deuter(conn, "Was weißt du über mich?", deuter=lambda q: None)
    assert "Nebenbei" not in abgerufen["text"]
    unklar = companion.respond_with_deuter(conn, "asdf ganz unklare frage", deuter=lambda q: None)
    assert "Nebenbei" not in unklar["text"]


def test_gender_pattern_skips_filler_words_instead_of_grabbing_them():
    # live (2026-07-02): "welchen Artikel hat eigentlich Tisch?" grabbed "eigentlich" as the
    # noun and answered from the "-ich" suffix rule -- fillers are now skipped in the patterns
    from genus import companion
    conn = _fresh()
    reactors.observe_relation(conn, "Tisch@de", "grammatical_gender", "maskulin", "wikidata-lexemes")
    r = companion.gender_question(conn, "Welchen Artikel hat eigentlich Tisch?")
    assert r["gender_q"] and r["noun"] == "Tisch" and r["known"] == ["maskulin"]


def test_ableitung_frage_recognizes_bestimme_and_berechne_and_leite_ab():
    from genus import companion
    for text, erwartet in [
        ("Bestimme die Ableitung von f(x) = 3x^2 + 2x", "6*x + 2"),
        ("Berechne die zweite Ableitung von f(x) = x^3 - 3x", "6*x"),
        ("Leite f(x) = sin(x) ab", "cos(x)"),
        ("Wie lautet die Ableitung von f(t) = 2t^2 + 5?", "4*t"),
    ]:
        r = companion.ableitung_frage(text)
        assert r["berechnung_q"] and r["ok"] and r["ableitung"] == erwartet, text


def test_ableitung_frage_is_false_for_an_unrelated_question():
    from genus import companion
    assert companion.ableitung_frage("Was ist ein Fahrrad?") == {"berechnung_q": False}


def test_narrate_ableitung_shows_the_exact_result_with_the_right_number_of_strokes():
    from genus import companion
    r = companion.ableitung_frage("Berechne die zweite Ableitung von f(x) = x^3 - 3x")
    text = companion.narrate_ableitung(r)
    assert "f''(x) = 6*x" in text and "exakt berechnet" in text


def test_narrate_ableitung_is_honest_about_an_unreadable_term():
    from genus import companion
    r = companion.ableitung_frage("Bestimme die Ableitung von f(x) = quatsch mit soße")
    text = companion.narrate_ableitung(r)
    assert "kann ich nicht ausrechnen" in text


def test_ableitung_is_reached_through_the_muster_dispatch():
    from genus import companion
    conn = _fresh()
    result = companion.respond_with_deuter(conn, "Bestimme die Ableitung von f(x) = 3x^2 + 2x")
    assert "6*x + 2" in result["text"]


def test_ableitung_answer_is_never_offered_to_the_stimme():
    # ein Formel-Ergebnis darf nie umformuliert werden -- viel zu hohes Korruptionsrisiko
    # (dieselbe Klasse wie "Kernobst" -> "Kernaubere"), deshalb bewusst nicht in
    # _STIMME_GEEIGNET; hier direkt bewiesen: eine Stimme, die IMMER etwas anderes zurückgibt,
    # darf trotzdem nie zum Zug kommen
    from genus import companion
    conn = _fresh()
    calls = []
    stimme = lambda satz: (calls.append(satz) or "VERFÄLSCHT")
    result = companion.respond_with_deuter(
        conn, "Bestimme die Ableitung von f(x) = 3x^2 + 2x", deuter=lambda q: None, stimme=stimme)
    assert calls == [] and "6*x + 2" in result["text"] and "VERFÄLSCHT" not in result["text"]


def test_extremstellen_frage_recognizes_the_fixed_formulation():
    from genus import companion
    r = companion.extremstellen_frage("Bestimme die Extremstellen von f(x) = x^3 - 3x")
    assert r["berechnung_q"] and r["ok"]
    assert r["punkte"] == [
        {"x": "-1", "y": "2", "art": "Maximum"}, {"x": "1", "y": "-2", "art": "Minimum"},
    ]


def test_extremstellen_frage_is_false_for_an_unrelated_question():
    from genus import companion
    assert companion.extremstellen_frage("Was ist ein Fahrrad?") == {"berechnung_q": False}


def test_narrate_extremstellen_names_both_points_with_their_kind():
    from genus import companion
    r = companion.extremstellen_frage("Bestimme die Extremstellen von f(x) = x^3 - 3x")
    text = companion.narrate_extremstellen(r)
    assert "Maximum bei x = -1" in text and "Minimum bei x = 1" in text


def test_narrate_extremstellen_is_honest_when_there_are_none():
    from genus import companion
    r = companion.extremstellen_frage("Bestimme die Extremstellen von f(x) = 7")
    text = companion.narrate_extremstellen(r)
    assert "keine Extremstellen" in text


def test_extremstellen_is_reached_through_the_muster_dispatch_and_never_offered_to_the_stimme():
    from genus import companion
    conn = _fresh()
    calls = []
    stimme = lambda satz: (calls.append(satz) or "VERFÄLSCHT")
    result = companion.respond_with_deuter(
        conn, "Bestimme die Extremstellen von f(x) = x^3 - 3x", deuter=lambda q: None, stimme=stimme)
    assert calls == [] and "Maximum bei x = -1" in result["text"] and "VERFÄLSCHT" not in result["text"]


def test_stammfunktion_frage_recognizes_the_fixed_formulation():
    from genus import companion
    r = companion.stammfunktion_frage("Bestimme eine Stammfunktion von f(x) = 3x^2 + 2x")
    assert r["berechnung_q"] and r["ok"] and r["stammfunktion"] == "x**3 + x**2 + C"


def test_stammfunktion_frage_is_false_for_an_unrelated_question():
    from genus import companion
    assert companion.stammfunktion_frage("Was ist ein Fahrrad?") == {"berechnung_q": False}


def test_narrate_stammfunktion_shows_the_integration_constant():
    from genus import companion
    r = companion.stammfunktion_frage("Bestimme eine Stammfunktion von f(x) = x^2")
    assert "F(x) = x**3/3 + C" in companion.narrate_stammfunktion(r)


def test_integral_frage_recognizes_in_den_grenzen_von_and_zwischen():
    from genus import companion
    for text, erwartet in [
        ("Berechne das Integral von f(x) = x^2 in den Grenzen von 0 bis 3", "9"),
        ("Berechne das Integral von f(x) = sin(x) zwischen 0 und pi", "2"),
    ]:
        r = companion.integral_frage(text)
        assert r["berechnung_q"] and r["ok"] and r["integral"] == erwartet, text


def test_integral_frage_is_false_for_an_unrelated_question():
    from genus import companion
    assert companion.integral_frage("Was ist ein Fahrrad?") == {"berechnung_q": False}


def test_narrate_integral_shows_both_bounds_and_the_result():
    from genus import companion
    r = companion.integral_frage("Berechne das Integral von f(x) = x^2 in den Grenzen von 0 bis 3")
    text = companion.narrate_integral(r)
    assert "0 bis 3" in text and "ist 9" in text


def test_integral_and_stammfunktion_are_reached_through_muster_and_never_offered_to_stimme():
    from genus import companion
    conn = _fresh()
    calls = []
    stimme = lambda satz: (calls.append(satz) or "VERFÄLSCHT")
    r1 = companion.respond_with_deuter(
        conn, "Bestimme eine Stammfunktion von f(x) = x^2", deuter=lambda q: None, stimme=stimme)
    r2 = companion.respond_with_deuter(
        conn, "Berechne das Integral von f(x) = x^2 in den Grenzen von 0 bis 3",
        deuter=lambda q: None, stimme=stimme)
    assert calls == []
    assert "x**3/3 + C" in r1["text"] and "ist 9" in r2["text"]
    assert "VERFÄLSCHT" not in r1["text"] and "VERFÄLSCHT" not in r2["text"]


def test_zaehlt_zu_is_a_deterministic_relation_pattern():
    # "Zählt X zu den Y?" -- one of the live misfires -- is now a fixed pattern (ms, no model)
    from genus import companion
    conn = _fresh()
    reactors.observe_relation(conn, "Apfel@de", "expresses", "Q_apfel", "wikidata")
    reactors.observe_relation(conn, "Pflanzen@de", "expresses", "Q_pflanze", "wikidata")
    reactors.observe_relation(conn, "Q_apfel", "is_a", "Q_pflanze", "wikidata")
    r = companion.relate(conn, "Zählt ein Apfel eigentlich zu den Pflanzen?")
    assert r["relational"] and r["verdict"] == "yes"
    # the ae spelling (no umlaut key on the phone) must hit the same fixed pattern -- caught
    # live: "zaehlt ..." slipped past z[äa]hlt into the model instead of staying deterministic
    r2 = companion.relate(conn, "zaehlt ein Apfel eigentlich zu den Pflanzen")
    assert r2["relational"] and r2["verdict"] == "yes"


def test_common_pattern_skips_filler_words():
    from genus import companion
    conn = _kinship_graph()
    r = companion.common(conn, "Was haben Hund und Katze eigentlich gemeinsam?")
    assert r["common"] and r["found"]


def test_deuter_none_reproduces_the_conversation_default():
    from genus import companion
    conn = _isa_graph()
    a = companion.respond_with_deuter(conn, "Quuxikon?")
    b = companion.respond_in_conversation(conn, "Quuxikon?")
    assert a == b   # deuter=None must be a byte-for-byte no-op, safe for every existing caller


def test_deuter_is_never_consulted_when_the_deterministic_chain_already_answered():
    from genus import companion
    conn = _isa_graph()
    calls = []
    deuter = lambda q: (calls.append(q) or {"absicht": "definition", "subject": "Hund"})
    companion.respond_with_deuter(conn, "Ist ein Hund ein Säugetier?", deuter=deuter)
    assert calls == []   # the relational answer already succeeded -- the model must stay idle


def test_deuter_resolves_a_freeform_question_the_deterministic_chain_missed():
    from genus import companion
    conn = _isa_graph()   # already has Hund@de -expresses-> Q144
    deuter = lambda q: {"absicht": "definition", "subject": "Hund"}
    # a phrasing the rigid extractor can't parse a subject out of on its own
    result = companion.respond_with_deuter(conn, "so ne allgemeine frage zu dem thema wuffwuff", deuter=deuter)
    assert "Hund" in result["text"]
    assert "Sprachmodell gedeutet" in result["text"]   # glass-box: never silently model-assisted


def test_deuter_guess_is_graph_verified_not_trusted_blindly():
    # das Modell nennt ein Wort, das GENUS nicht kennt -- kein Rückfall auf den gierigen
    # Wort-Lookup mehr (Ronnys Entscheidung 2026-07-03): der Deuter LIEF und die Lesart löste
    # sich nicht auf, also ein ehrliches "nicht verstanden" statt einer erfundenen Antwort
    from genus import companion
    conn = _isa_graph()
    deuter = lambda q: {"absicht": "definition", "subject": "Erfundenwort"}   # GENUS knows no such word
    result = companion.respond_with_deuter(conn, "asdf ganz unklare frage", deuter=deuter)
    assert result["text"] == companion._NICHT_VERSTANDEN


def test_deuter_followup_reaches_the_trace_outside_the_fixed_cue_phrases():
    from genus import companion
    conn = _isa_graph()
    first = companion.respond_in_conversation(conn, "Ist ein Hund ein Säugetier?")
    deuter = lambda q: {"absicht": "warum-herkunft", "subject": None}
    # a phrasing NOT in the small fixed _WHY_FOLLOWUP set -- deterministic is_why_followup misses it
    followup = companion.respond_with_deuter(
        conn, "kannst du mir das nochmal genauer herleiten", last_question=first["question"], deuter=deuter,
    )
    assert "Herleitung" in followup["text"] and "Sprachmodell gedeutet" in followup["text"]


def test_deuter_explicit_empty_list_is_honest_not_understood():
    # live gefunden: "OK prima" bekam vom echten Modell wortwörtlich "[]" zurück -- das Modell
    # LIEF und sagte ehrlich "keine Segmente passen". Das ist ein staerkeres Signal als
    # "kein Deuter da" und darf nicht beim gierigen Wort-Lookup landen.
    from genus import companion
    conn = _isa_graph()
    result = companion.respond_with_deuter(conn, "OK prima", deuter=lambda q: [])
    assert result["text"] == companion._NICHT_VERSTANDEN


def test_deuter_none_still_falls_back_to_word_lookup():
    # der Unterschied zur leeren Liste: deuter(question) selbst gibt None (Modell fehlt,
    # Ausnahme, kaputtes JSON) -- dann bleibt der Wort-Lookup ein legitimer letzter Versuch
    from genus import companion
    conn = _isa_graph()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    baseline = companion.respond_in_conversation(conn, "Was ist ein Hund?")
    result = companion.respond_with_deuter(conn, "Was ist ein Hund?", deuter=lambda q: None)
    assert result == baseline


def test_deuter_unactionable_readings_fail_safe_honestly():
    # ein Deuter-LAUF (auch eine Liste mit nur unklaren/nicht auflösbaren Lesarten) endet jetzt
    # ehrlich bei "nicht verstanden", nicht beim gierigen Wort-Lookup -- außer der Deuter selbst
    # lief GAR NICHT (gibt None zurück), dann bleibt der Wort-Lookup der legitime letzte Versuch
    from genus import companion
    conn = _isa_graph()
    for guess in ({"absicht": "beziehung", "subject": "Hund"},   # no object -> can't be safely re-asked
                  {"absicht": "unklar", "subject": None},        # model honestly can't place it
                  {"absicht": "", "subject": None}):
        result = companion.respond_with_deuter(conn, "asdf ganz unklare frage", deuter=lambda q, g=guess: g)
        assert result["text"] == companion._NICHT_VERSTANDEN
    baseline = companion.respond_in_conversation(conn, "asdf ganz unklare frage")
    kein_lauf = companion.respond_with_deuter(conn, "asdf ganz unklare frage", deuter=lambda q: None)
    assert kein_lauf == baseline   # der Deuter lief gar nicht -- Wort-Lookup bleibt der Ausweg


def test_deuter_known_but_unhandled_cell_is_named_honestly_and_counted():
    # the big-raster principle: open when OBSERVING, closed when ACTING. A cell GENUS can read
    # but not act on is named honestly (not "kein Wort bekannt") and its Belegung is counted --
    # these counts prioritise what gets built next, from lived conversations
    from genus import companion, verstehen
    conn = _isa_graph()
    verstehen.seed_raster(conn)
    deuter = lambda q: {"absicht": "empfehlungsfrage", "subject": "Haustier"}
    result = companion.respond_with_deuter(conn, "kannst du mir ein Haustier empfehlen", deuter=deuter)
    assert "Bitte um Empfehlung" in result["text"] and "noch nicht" in result["text"]
    assert verstehen.belegung(conn, "empfehlungsfrage")["gesamt"] == 1


def test_deuter_unknown_leaf_changes_nothing_no_freetext_escape_anymore():
    # Zwickys Kategorien sollen erschöpfend sein -- kein Freitext-Ausweg mehr (der hatte selbst
    # Nebenwirkungen, live gefunden: "Danke" wich auf "erleben" aus). Ein Blatt außerhalb der
    # gesäten Liste (Modell-Fehler oder Halluzination) ändert ehrlich nichts, fail safe --
    # honestly "nicht verstanden", nie der gierige Wort-Lookup (der Deuter LIEF ja).
    from genus import companion, verstehen
    conn = _isa_graph()
    verstehen.seed_raster(conn)
    deuter = lambda q: {"absicht": "bitte um ein gedicht", "subject": None}
    result = companion.respond_with_deuter(conn, "asdf ganz unklare frage", deuter=deuter)
    assert result["text"] == companion._NICHT_VERSTANDEN


def test_deuter_reading_climbs_the_is_a_chain_to_the_nearest_actionable_cell():
    # the soft landing: "eigenschaft" has no handler of its own, but its Zelle frage-begriff
    # does -- a too-fine reading falls SOFT onto the cell instead of hard onto the fallback,
    # exactly like inference climbs concept is_a (now exactly one step: Blatt -> Zelle)
    from genus import companion, verstehen
    conn = _isa_graph()
    verstehen.seed_raster(conn)
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier, Vorfahre der Wolf", "dbnary")
    deuter = lambda q: {"absicht": "eigenschaft", "subject": "Hund"}
    result = companion.respond_with_deuter(conn, "wie schnell rennt so ein wuffwuff", deuter=deuter)
    assert "Wolf" in result["text"]                        # what IS known about the subject
    assert "kann ich noch nicht" in result["text"]         # the honest limit, named
    assert verstehen.belegung(conn, "eigenschaft")["gesamt"] == 1   # counted as the FINE cell


# --- Antwort-Würfel, Scheibe 1: die Meta-Zellen (kuerzer/ausfuehrlicher/anders/wiederholen) --

def test_kuerzer_truncates_to_the_first_sentence():
    from genus import companion
    conn = _isa_graph()
    voll = "Unter »Hund« versteht GENUS: Haustier. Es zählt zu Heimtier. (Vertrauen 0.50.)"
    deuter = lambda q: {"absicht": "kuerzer"}
    result = companion.respond_with_deuter(conn, "kürzer bitte", last_answer=voll, deuter=deuter)
    assert result["text"].startswith("Unter »Hund« versteht GENUS: Haustier.")
    assert "Heimtier" not in result["text"] and "Vertrauen" not in result["text"]


def test_kuerzer_without_a_prior_answer_fails_safe_honestly():
    # kein last_answer -- die Zelle kann nichts kürzen, und weil der Deuter aktiv LIEF und
    # ehrlich nichts fand, zeigt GENUS jetzt ein "nicht verstanden" statt eines gierigen
    # Wort-Lookups (Ronnys Entscheidung nach der zweiten enttäuschenden Session)
    from genus import companion
    conn = _isa_graph()
    deuter = lambda q: {"absicht": "kuerzer"}
    result = companion.respond_with_deuter(conn, "kürzer bitte", deuter=deuter)   # no last_answer
    assert result["text"] == companion._NICHT_VERSTANDEN   # never fabricates a shortened answer


def test_ausfuehrlicher_appends_the_provenance_trace():
    from genus import companion
    conn = _isa_graph()
    deuter = lambda q: {"absicht": "ausfuehrlicher"}
    result = companion.respond_with_deuter(
        conn, "ausführlicher bitte", last_question="Ist ein Hund ein Säugetier?",
        last_answer="Ja. »Hund« zählt zu »Säugetier«.", deuter=deuter,
    )
    assert result["text"].startswith("Ja. »Hund« zählt zu »Säugetier«.")
    assert "Herleitung" in result["text"] and "wikidata" in result["text"]


def test_anders_erklaeren_uses_the_stimme_for_a_genuinely_different_phrasing():
    from genus import companion
    conn = _isa_graph()
    deuter = lambda q: {"absicht": "anders-erklaeren"}
    stimme = lambda satz: "GENUS meint: »Hund« ist ein Haustier."
    result = companion.respond_with_deuter(
        conn, "kannst du das anders sagen", last_answer="Unter »Hund« versteht GENUS: Haustier.",
        deuter=deuter, stimme=stimme,
    )
    assert result["text"].startswith("GENUS meint: »Hund« ist ein Haustier.")


def test_anders_erklaeren_without_a_working_stimme_repeats_honestly():
    from genus import companion
    conn = _isa_graph()
    deuter = lambda q: {"absicht": "anders-erklaeren"}
    result = companion.respond_with_deuter(
        conn, "kannst du das anders sagen", last_answer="Unter »Hund« versteht GENUS: Haustier.",
        deuter=deuter,   # kein stimme
    )
    assert result["text"].startswith(
        "Ich kann es nur so sagen, wie ich es weiß: Unter »Hund« versteht GENUS: Haustier.")


def test_wiederholen_repeats_the_last_answer_verbatim():
    from genus import companion
    conn = _isa_graph()
    deuter = lambda q: {"absicht": "wiederholen"}
    result = companion.respond_with_deuter(
        conn, "nochmal bitte", last_answer="Unter »Hund« versteht GENUS: Haustier.", deuter=deuter,
    )
    assert result["text"].startswith("Nochmal: Unter »Hund« versteht GENUS: Haustier.")


def test_wiederholen_does_not_duplicate_a_marker_already_in_the_last_answer():
    # live fund (2026-07-03): "Nochmal" on an already Deuter-tagged last_answer produced the
    # marker TWICE (once embedded in last_answer, once freshly appended) -- deduped now
    from genus import companion
    conn = _isa_graph()
    deuter = lambda q: {"absicht": "wiederholen"}
    getaggt = "Unter »Hund« versteht GENUS: Haustier." + companion._DEUTED
    result = companion.respond_with_deuter(conn, "nochmal bitte", last_answer=getaggt, deuter=deuter)
    assert result["text"].count("Frage vom Sprachmodell gedeutet") == 1


def test_meta_zellen_keep_the_session_anchored_on_the_original_topic():
    # a "kürzer"/"nochmal" turn must not become the new last_question -- a later "warum?" should
    # still retrace the ORIGINAL topic, not the meta-command
    from genus import companion
    conn = _isa_graph()
    deuter = lambda q: {"absicht": "wiederholen"}
    result = companion.respond_with_deuter(
        conn, "nochmal bitte", last_question="Ist ein Hund ein Säugetier?",
        last_answer="Ja. »Hund« zählt zu »Säugetier«.", deuter=deuter,
    )
    assert result["question"] == "Ist ein Hund ein Säugetier?"


# --- Sozialgesten -- live gefunden: "Hallo" landete beim generischen "kann ich nicht" ------

def test_gruss_gets_a_friendly_reply_not_the_honest_gap_message():
    from genus import companion
    conn = _isa_graph()
    deuter = lambda q: {"absicht": "gruss"}
    result = companion.respond_with_deuter(conn, "Hallo", deuter=deuter)
    assert "kann ich noch nicht" not in result["text"]
    assert "Hallo" in result["text"]


def test_dank_lob_kritik_abschied_get_deterministic_replies():
    from genus import companion
    conn = _isa_graph()
    for absicht, erwartet in [("dank", "Gern geschehen"), ("lob", "Danke"),
                               ("kritik", "Rückmeldung"), ("abschied", "Bis bald")]:
        deuter = lambda q, a=absicht: {"absicht": a}
        result = companion.respond_with_deuter(conn, "irgendein Text", deuter=deuter)
        assert erwartet in result["text"], (absicht, result["text"])


def test_sozialgesten_are_counted_as_belegung_but_never_store_the_message_text():
    # eine Lese-Zelle wird wie jede andere gezählt (Belegung/QM), aber der Nutzertext selbst
    # ("Hallo, wie schön dich zu treffen") landet nie im Ledger -- nur die Struktur (Absicht+Quelle)
    from genus import companion, verstehen
    conn = _isa_graph()
    verstehen.seed_raster(conn)
    deuter = lambda q: {"absicht": "gruss"}
    companion.respond_with_deuter(conn, "Hallo, wie schön dich zu treffen!", deuter=deuter)
    assert verstehen.belegung(conn, "gruss")["gesamt"] == 1
    for row in conn.execute("SELECT payload FROM event_log").fetchall():
        assert "wie schön dich zu treffen" not in row["payload"]


def test_sozialgesten_refuse_a_long_sentence_even_if_the_model_reads_one():
    # live gefunden direkt beim Nachverifizieren: eine Hilfe-Bitte für einen Familienausflug
    # wurde als "abschied" gelesen -- ein selbstsicheres "Bis bald!" darauf ist SCHLIMMER als
    # die ehrliche Lücken-Meldung, weil es die Fehldeutung unsichtbar macht. Ein echter Gruß/
    # Dank/Abschied ist so gut wie immer kurz; ein langer Satz in dieser Zelle ist fast sicher
    # ein Fehlgriff -- die Wortzahl-Bremse lässt ihn dann ehrlich durchfallen statt zu antworten.
    from genus import companion
    conn = _isa_graph()
    lang = "Ich möchte einen Familienausflug planen. Kannst du mir helfen?"
    deuter = lambda q: {"absicht": "abschied", "subject": None}
    result = companion.respond_with_deuter(conn, lang, deuter=deuter)
    assert "Bis bald" not in result["text"]
    assert result["text"] == companion._NICHT_VERSTANDEN   # fällt ehrlich durch, nicht falsch


# --- Segmentierung (ISO 24617-2): eine Nachricht kann mehrere Sprechhandlungen enthalten ----

def test_deuter_segments_are_resolved_independently_and_composed():
    # Ronny: "Nachrichten können auch Fragen, Aussagen, Floskeln und Aufforderungen in einer
    # Nachricht enthalten, sogar mehrfach!" -- eine Liste von Segmenten, jedes einzeln gelöst,
    # zu EINER Antwort komponiert
    from genus import companion
    conn = _isa_graph()
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier, Vorfahre der Wolf", "dbnary")
    deuter = lambda q: [
        {"absicht": "gruss"},
        {"absicht": "definition", "subject": "Hund"},
        {"absicht": "dank"},
    ]
    result = companion.respond_with_deuter(conn, "Hallo! Was ist ein Hund? Danke!", deuter=deuter)
    assert "Hallo!" in result["text"]
    assert "Wolf" in result["text"]
    assert "Gern geschehen" in result["text"]


def test_deuter_composition_deduplicates_the_repeated_disclosure_tag():
    # jedes Segment traegt seinen eigenen "(Frage vom Sprachmodell gedeutet.)"-Hinweis --
    # zusammengesetzt soll er nur EINMAL erscheinen, nicht dreimal hintereinander
    from genus import companion
    conn = _isa_graph()
    deuter = lambda q: [{"absicht": "gruss"}, {"absicht": "dank"}, {"absicht": "abschied"}]
    result = companion.respond_with_deuter(conn, "Hallo, danke, tschüss", deuter=deuter)
    assert result["text"].count("Frage vom Sprachmodell gedeutet") == 1


def test_sozialgeste_word_limit_judges_the_segments_own_text_not_the_whole_message():
    # live gefunden: "Danke dir!" als eigenes, kurzes Segment innerhalb einer langen Nachricht
    # ("Hallo! Was ist ein Hund? Danke dir!") verschwand stillschweigend aus der komponierten
    # Antwort, weil die Wortzahl-Bremse die GANZE Nachricht prüfte statt der eigenen Klausel
    from genus import companion
    conn = _isa_graph()
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier, Vorfahre der Wolf", "dbnary")
    lange_nachricht = "Hallo! Was ist ein Hund? Danke dir schonmal ganz herzlich dafür!"
    deuter = lambda q: [
        {"text": "Hallo!", "absicht": "gruss"},
        {"text": "Was ist ein Hund?", "absicht": "definition", "subject": "Hund"},
        {"text": "Danke dir schonmal ganz herzlich dafür!", "absicht": "dank"},
    ]
    result = companion.respond_with_deuter(conn, lange_nachricht, deuter=deuter)
    assert "Hallo!" in result["text"]
    assert "Wolf" in result["text"]
    assert "Gern geschehen" in result["text"]   # das kurze Dank-SEGMENT durfte nicht durchfallen


def test_tatsache_remembers_only_its_own_segment_not_the_whole_message():
    # dieselbe Klasse: eine Notiz soll die KLAUSEL enthalten, nicht Gruß+Frage+Dank mit
    from genus import companion, erinnerung
    conn = _isa_graph()
    deuter = lambda q: [{"text": "ich war auf einem Konzert", "absicht": "tatsache"}]
    companion.respond_with_deuter(
        conn, "Übrigens, ich war auf einem Konzert, das nur nebenbei", deuter=deuter)
    assert erinnerung.vermutete_episoden(conn) == ["ich war auf einem Konzert"]


def test_deuter_a_segment_that_fails_does_not_block_the_others():
    # ein Segment, das an nichts andockt (unklar/unbekannt), liefert einfach nichts bei -- die
    # anderen Segmente antworten trotzdem
    from genus import companion
    conn = _isa_graph()
    deuter = lambda q: [{"absicht": "gruss"}, {"absicht": "unklar"}, {"absicht": "dank"}]
    result = companion.respond_with_deuter(conn, "Hallo, ???, danke", deuter=deuter)
    assert "Hallo" in result["text"] and "Gern geschehen" in result["text"]


def test_deuter_bare_dict_still_works_single_segment_backward_compatible():
    # ein Aufrufer/Test, der noch ein bare dict liefert (statt einer Liste), wird grosszügig
    # als Ein-Segment-Liste behandelt
    from genus import companion
    conn = _isa_graph()
    deuter = lambda q: {"absicht": "gruss"}
    result = companion.respond_with_deuter(conn, "Hallo", deuter=deuter)
    assert "kann ich noch nicht" not in result["text"]


def test_weltfrage_wird_von_der_eigenen_sinnes_zelle_beantwortet():
    # der eigentliche Auslöser der ganzen Zwicky-Box: "Wie wird das Wetter morgen?" wurde vorher
    # als "vergleich" zwischen Wetter und Morgen fehlgedeutet -- jetzt hat weltfrage eine EIGENE
    # Zelle, und seit P4 sogar einen SINN. Ohne Messwert (hier kein Wetter geseedet) antwortet
    # sie ehrlich, statt zu erfinden, und benennt, was der Sinn noch nicht erreicht.
    from genus import companion
    conn = _isa_graph()
    deuter = lambda q: [{"absicht": "weltfrage"}]
    result = companion.respond_with_deuter(conn, "Wie wird das Wetter morgen?", deuter=deuter)
    assert "erreicht die Welt im Moment nicht" in result["text"]   # ehrlich, kein Fehlgriff
    assert "spaeter noch einmal" in result["text"]


def test_tun_is_an_honest_named_gap_for_real_world_help_requests():
    # der zweite Auslöser: eine Hilfe-Bitte für einen Familienausflug wurde als "abschied"
    # fehlgedeutet ("Bis bald!") -- jetzt eine eigene, ehrliche Zelle für Aufforderungen in
    # der Welt
    from genus import companion
    conn = _isa_graph()
    deuter = lambda q: [{"absicht": "tun", "subject": "Familienausflug"}]
    result = companion.respond_with_deuter(
        conn, "Ich möchte einen Familienausflug planen. Kannst du mir helfen?", deuter=deuter)
    assert "Aufforderung, etwas in der Welt zu tun" in result["text"]
    assert "Bis bald" not in result["text"]


def test_zelle_merken_no_longer_crashes_on_a_deuter_read_remember_request():
    # ein latenter Bug: _zelle_merken rief _zelle_tatsache mit zu wenigen Argumenten auf
    # (fehlte last_answer/stimme) -- ein TypeError, der nur nie live ausgelöst wurde
    from genus import companion
    conn = _isa_graph()
    deuter = lambda q: [{"absicht": "merken"}]
    result = companion.respond_with_deuter(conn, "ich hab zwei Hunde, merk dir das", deuter=deuter)
    assert "notiert" in result["text"]


def test_deuter_relation_guess_with_both_terms_resolves_via_the_graph():
    # the Deuter now runs on free phrasing the fixed _REL_PATTERNS regex can't parse -- the
    # extracted subject/object still go through the exact same graph reasoning (_relate_terms)
    from genus import companion
    conn = _isa_graph()
    deuter = lambda q: {"absicht": "beziehung", "subject": "Hund", "object": "Säugetier"}
    result = companion.respond_with_deuter(conn, "gehoert sowas wie ein wuffwuff eigentlich dahin", deuter=deuter)
    assert "»Hund« zählt zu »Säugetier«" in result["text"]
    assert "Sprachmodell gedeutet" in result["text"]


def test_deuter_reading_outranks_the_greedy_word_lookup():
    # the live bug class (2026-07-02): "zählt ein Apfel zu den Pflanzen?" got a botany lecture
    # about the word "Pflanzen" because the greedy word lookup ran before the Deuter was ever
    # consulted. In the Würfel order the Deuter reads first; the word reading is the LAST resort.
    from genus import companion
    conn = _fresh()
    reactors.observe_relation(conn, "Apfel@de", "expresses", "Q_apfel", "wikidata")
    reactors.observe_relation(conn, "Pflanzen@de", "expresses", "Q_pflanze", "wikidata")
    reactors.observe_relation(conn, "Q_apfel", "is_a", "Q_pflanze", "wikidata")
    deuter = lambda q: {"absicht": "beziehung", "subject": "Apfel", "object": "Pflanzen"}
    result = companion.respond_with_deuter(
        conn, "gehört der Apfel nicht irgendwie zu den Pflanzen", deuter=deuter)
    assert "»Apfel« zählt zu »Pflanzen«" in result["text"]   # the relation -- NOT a lecture on "Pflanzen"
    assert "Sprachmodell gedeutet" in result["text"]


def test_deuter_comparative_guess_with_both_terms_resolves_via_the_graph():
    from genus import companion
    conn = _kinship_graph()
    deuter = lambda q: {"absicht": "vergleich", "subject": "Hund", "object": "Katze"}
    result = companion.respond_with_deuter(conn, "was ist da eigentlich aehnlich bei den beiden", deuter=deuter)
    assert "Säugetier" in result["text"] and "Sprachmodell gedeutet" in result["text"]


def test_deuter_gender_guess_resolves_when_the_noun_is_known():
    from genus import companion
    conn = _isa_graph()
    reactors.observe_relation(conn, "Hund@de", "grammatical_gender", "maskulin", "wikidata-lexemes")
    deuter = lambda q: {"absicht": "grammatik", "subject": "Hund"}
    result = companion.respond_with_deuter(conn, "was fuer ein wort ist das denn grammatikalisch", deuter=deuter)
    assert "maskulin" in result["text"] and "Sprachmodell gedeutet" in result["text"]


def test_deuter_gender_guess_with_unresolvable_noun_stays_honest():
    # unlike the regex-triggered gender_question (an unambiguous pattern match commits to the
    # "I don't know" answer), an unresolvable MODEL guess never manufactures an answer -- it
    # fails safe to an honest "nicht verstanden" (the Deuter DID run, just found nothing usable)
    from genus import companion
    conn = _isa_graph()
    deuter = lambda q: {"absicht": "grammatik", "subject": "Erfundenwort"}
    result = companion.respond_with_deuter(conn, "was fuer ein wort ist das denn grammatikalisch", deuter=deuter)
    assert result["text"] == companion._NICHT_VERSTANDEN


def test_remember_command_recognizes_the_cue_phrases_and_extracts_the_fact():
    from genus import companion
    for question, expected in [
        ("Merke dir: ich habe zwei Hunde", "ich habe zwei Hunde"),
        ("merk dir ich mag Kaffee", "ich mag Kaffee"),
        ("Denk dran: mein Geburtstag ist im Mai.", "mein Geburtstag ist im Mai"),
        ("notiere dir, ich wohne in Berlin", "ich wohne in Berlin"),
    ]:
        assert companion.remember_command(question) == expected
    for question in ("Was ist ein Hund?", "erinnerst du dich an mich", ""):
        assert companion.remember_command(question) is None


def test_remember_and_recall_round_trip():
    from genus import erinnerung
    conn = _isa_graph()
    assert erinnerung.bestaetigte_episoden(conn) == []
    # "Zebra" sorts AFTER "Apfel" alphabetically but was told FIRST -- pins insertion order,
    # not sources.relations()'s alphabetical-by-object order (a real bug caught locally)
    erinnerung.merke(conn, "Zebra mag ich am liebsten im Zoo", quelle="ronny")
    erinnerung.merke(conn, "Apfelsaft trinke ich jeden Morgen", quelle="ronny")
    assert erinnerung.bestaetigte_episoden(conn) == [
        "Zebra mag ich am liebsten im Zoo", "Apfelsaft trinke ich jeden Morgen",
    ]


def test_remembering_is_not_hardcoded_to_be_about_ronny():
    # regression, caught live on the Pi (Ronny's own reaction was a 😂): "Merk dir dass du
    # GENUS heisst" is a fact about GENUS, not about Ronny -- slice 1 filed EVERYTHING as "a
    # fact about Ronny" regardless of content, so recalling it read back nonsensically. The
    # notebook is now general -- it just knows WHO TOLD it, never WHAT/WHOM a note is about.
    from genus import erinnerung
    conn = _isa_graph()
    erinnerung.merke(conn, "dass du GENUS heißt und Ronny dich erschaffen hat", quelle="ronny")
    assert erinnerung.bestaetigte_episoden(conn) == ["dass du GENUS heißt und Ronny dich erschaffen hat"]


def test_recall_question_is_recognized_by_exact_match_not_substring():
    from genus import companion
    for q in ("Was weißt du über mich?", "was weisst du von mir", "Kennst du mich?",
              "Was weißt du?", "was hast du dir gemerkt"):
        assert companion.is_recall_question(q)
    assert not companion.is_recall_question("Was ist ein Hund?")
    # regression: a substring check on the bare "was weißt du" cue would have hijacked this
    # ordinary word question (real risk once "was weißt du" itself became a valid cue)
    assert not companion.is_recall_question("Was weißt du über Hunde?")


def test_narrate_notes_shows_confirmed_and_suggested_tiers_separately():
    from genus import companion
    assert "noch nichts" in companion.narrate_notes([], [])
    assert "Einzige" in companion.narrate_notes(["ich mag Kaffee"], [])
    many = companion.narrate_notes(["A", "B"], [])
    assert "A" in many and "B" in many and "Das weiß ich sicher" in many
    mixed = companion.narrate_notes(["A"], ["B"])
    assert "A" in mixed and "B" in mixed
    assert "noch nicht bestätigt" in mixed   # a suggestion is never presented as a fact


def test_remembering_is_a_human_source_with_full_trust_not_capped():
    from genus import erinnerung, sources
    conn = _isa_graph()
    erinnerung.merke(conn, "ich mag Kaffee", quelle="ronny")
    assert sources.source_trust(conn, "ronny") >= sources.SOURCE_TRUST_SEED  # never model-capped


def test_a_deuter_suggested_statement_is_capped_and_marked_unconfirmed():
    from genus import companion, erinnerung
    conn = _isa_graph()
    deuter = lambda q: {"absicht": "tatsache", "subject": "Konzert"}
    result = companion.respond_with_deuter(conn, "ich war gestern auf einem Konzert", deuter=deuter)
    assert "notiert" in result["text"] and "unsicher" in result["text"]
    assert erinnerung.vermutete_episoden(conn) == ["ich war gestern auf einem Konzert"]
    assert erinnerung.bestaetigte_episoden(conn) == []   # never conflated with a real "Merke dir"
    assert sources.source_trust(conn, erinnerung.STATEMENT_SOURCE) <= sources.MODEL_TRUST_SEED


def test_respond_remembers_and_recalls_end_to_end():
    from genus import companion
    conn = _isa_graph()
    gemerkt = companion.respond(conn, "Merke dir: ich habe zwei Hunde")
    assert "Gemerkt" in gemerkt and "zwei Hunde" in gemerkt
    erinnerung = companion.respond(conn, "Was weißt du über mich?")
    assert "zwei Hunde" in erinnerung


def test_remember_command_always_takes_priority_over_other_routing():
    from genus import companion
    conn = _isa_graph()
    # the fact text itself contains "status" -- a fixed state-pattern word -- and must NOT be
    # hijacked by query.ask's command matching (the routing-shadowing class from earlier)
    result = companion.respond(conn, "Merke dir: mein Status-Update ist fertig")
    assert "Gemerkt" in result and "Status-Update" in result


# --- Phase 0 der Ziel-Architektur: das Geteilte wandert nach unten -------------------


def test_phase0_wortauskunft_wohnt_in_sources_grounded_zuerst():
    # Die Text->Konzept-Aufloesung ist geteiltes Wissen (sources), keine Companion-
    # Interna mehr -- erinnerung greift nie wieder in private Attribute einer hoeheren
    # Schicht. Grounded-zuerst: die wikidata-Kante gewinnt vor anderen Quellen.
    conn = _fresh()
    reactors.observe_relation(conn, "Fahrrad@de", "expresses", "Q99999", "dbnary")
    reactors.observe_relation(conn, "Fahrrad@de", "expresses", "Q11442", "wikidata")
    assert sources.bekanntes_wort(conn, "Fahrrad")
    assert not sources.bekanntes_wort(conn, "Nebelkraehe")
    assert sources.prominentes_konzept(conn, "Fahrrad") == "Q11442"
    conn.close()


def test_phase0_wort_mit_nur_glosse_ist_bekannt_aber_ohne_konzept():
    conn = _fresh()
    reactors.observe_relation(
        conn, "flanieren@de", "defined_as", "gemächlich spazieren gehen", "dbnary"
    )
    assert sources.bekanntes_wort(conn, "flanieren")
    assert sources.prominentes_konzept(conn, "flanieren") is None
    conn.close()


def test_phase0_wortgraph_delegiert_an_sources():
    # Strangler: die alten privaten Companion-Helfer bleiben duenne Delegation -- eine Logik,
    # ein Zuhause. Seit der Modularisierung (Schritt ③) wohnen sie in der Lese-Grundlage
    # genus.wortgraph (companion re-exportiert nur, was externe Aufrufer brauchen).
    from genus import wortgraph

    conn = _fresh()
    reactors.observe_relation(conn, "Tisch@de", "expresses", "Q14748", "wikidata")
    assert wortgraph._known(conn, "Tisch") == sources.bekanntes_wort(conn, "Tisch")
    assert wortgraph._prominent_concept(conn, "Tisch") == sources.prominentes_konzept(
        conn, "Tisch"
    )
    conn.close()


def test_phase0_hat_handler_entspricht_der_alten_luecken_logik():
    # Die oeffentliche Faehigkeits-Auskunft (companion.hat_handler) ersetzt den privaten
    # _HANDELBAR-Zugriff des VerstehensLuecke-Detectors -- exakt dieselbe Logik: das
    # Blatt selbst oder seine Zwicky-Zelle (ein is_a-Schritt) traegt eine Zelle. Seit
    # Phase 3 liest hat_handler die Werkzeug-Registry; das Seed-Dict bleibt die
    # inhaltliche Referenz (die Registry spiegelt es geprueft wider).
    from genus import companion, verstehen

    conn = _fresh()
    verstehen.seed_raster(conn)
    zellen = companion._handelbare_werkzeuge()
    assert set(zellen) == set(companion._HANDELBAR)
    for leaf, _zelle in verstehen.RASTER_SEED:
        erwartet = (
            leaf in zellen
            or (verstehen.zelle_of(conn, leaf) or "") in zellen
        )
        assert companion.hat_handler(conn, leaf) == erwartet, leaf
    assert not companion.hat_handler(conn, "voellig-unbekanntes-blatt")
    conn.close()
