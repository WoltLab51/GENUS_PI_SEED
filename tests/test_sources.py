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
    assert "Heimtier und domestiziertes Säugetier" in s and "Q39201" not in s   # labels, no Q-id
    assert "chien" in s


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


def test_why_followup_recognizes_the_closed_set_of_cue_phrases():
    from genus import companion
    for phrase in ("warum?", "Warum", "wieso??", "  weshalb ", "Woher weißt du das?",
                   "woher kommt das", "Woher hast du das?"):
        assert companion.is_why_followup(phrase), phrase
    for phrase in ("warum ist ein Hund ein Säugetier?", "Was ist ein Hund?", ""):
        assert not companion.is_why_followup(phrase), phrase


def test_conversation_retraces_the_previous_relational_answer():
    from genus import companion
    conn = _isa_graph()
    first = companion.respond_in_conversation(conn, "Ist ein Hund ein Säugetier?")
    assert "Ja." in first["text"] and first["question"] == "Ist ein Hund ein Säugetier?"

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


def test_gender_pattern_skips_filler_words_instead_of_grabbing_them():
    # live (2026-07-02): "welchen Artikel hat eigentlich Tisch?" grabbed "eigentlich" as the
    # noun and answered from the "-ich" suffix rule -- fillers are now skipped in the patterns
    from genus import companion
    conn = _fresh()
    reactors.observe_relation(conn, "Tisch@de", "grammatical_gender", "maskulin", "wikidata-lexemes")
    r = companion.gender_question(conn, "Welchen Artikel hat eigentlich Tisch?")
    assert r["gender_q"] and r["noun"] == "Tisch" and r["known"] == ["maskulin"]


def test_zaehlt_zu_is_a_deterministic_relation_pattern():
    # "Zählt X zu den Y?" -- one of the live misfires -- is now a fixed pattern (ms, no model)
    from genus import companion
    conn = _fresh()
    reactors.observe_relation(conn, "Apfel@de", "expresses", "Q_apfel", "wikidata")
    reactors.observe_relation(conn, "Pflanzen@de", "expresses", "Q_pflanze", "wikidata")
    reactors.observe_relation(conn, "Q_apfel", "is_a", "Q_pflanze", "wikidata")
    r = companion.relate(conn, "Zählt ein Apfel eigentlich zu den Pflanzen?")
    assert r["relational"] and r["verdict"] == "yes"


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
    from genus import companion
    conn = _isa_graph()
    deuter = lambda q: {"absicht": "definition", "subject": "Erfundenwort"}   # GENUS knows no such word
    baseline = companion.respond_in_conversation(conn, "asdf ganz unklare frage")
    result = companion.respond_with_deuter(conn, "asdf ganz unklare frage", deuter=deuter)
    assert result == baseline   # the model's guess is not a real word -- stays honest, unchanged


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


def test_deuter_unactionable_readings_fail_safe_to_the_baseline():
    from genus import companion
    conn = _isa_graph()
    baseline = companion.respond_in_conversation(conn, "asdf ganz unklare frage")
    for guess in ({"absicht": "beziehung", "subject": "Hund"},   # no object -> can't be safely re-asked
                  {"absicht": "unklar", "subject": None},        # model honestly can't place it
                  {"absicht": "", "subject": None},
                  None):
        result = companion.respond_with_deuter(conn, "asdf ganz unklare frage", deuter=lambda q, g=guess: g)
        assert result == baseline


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


def test_deuter_offgrid_reading_is_collected_as_differentiation_material():
    # "da kann alles kommen": a reading OUTSIDE the raster changes no answer (fail safe), but
    # the model's OWN words are collected under absicht:unklar -- the material from which the
    # scan will later recognize missing Ausprägungen. The user's words are never stored.
    from genus import companion, verstehen
    conn = _isa_graph()
    verstehen.seed_raster(conn)
    baseline = companion.respond_in_conversation(conn, "asdf ganz unklare frage")
    deuter = lambda q: {"absicht": "bitte um ein gedicht", "subject": None}
    result = companion.respond_with_deuter(conn, "asdf ganz unklare frage", deuter=deuter)
    assert result == baseline
    assert verstehen.free_readings(conn) == ["bitte um ein gedicht"]


def test_deuter_reading_climbs_the_is_a_chain_to_the_nearest_actionable_cell():
    # the soft landing: "eigenschaft" has no handler of its own, but is_a wissensfrage does --
    # a too-fine reading falls SOFT onto the ancestor instead of hard onto the fallback,
    # exactly like inference climbs concept is_a
    from genus import companion, verstehen
    conn = _isa_graph()
    verstehen.seed_raster(conn)
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier, Vorfahre der Wolf", "dbnary")
    deuter = lambda q: {"absicht": "eigenschaft", "subject": "Hund"}
    result = companion.respond_with_deuter(conn, "wie schnell rennt so ein wuffwuff", deuter=deuter)
    assert "Wolf" in result["text"]                        # what IS known about the subject
    assert "kann ich noch nicht" in result["text"]         # the honest limit, named
    assert verstehen.belegung(conn, "eigenschaft")["gesamt"] == 1   # counted as the FINE cell


def test_deuter_relation_guess_with_both_terms_resolves_via_the_graph():
    # the Deuter now runs on free phrasing the fixed _REL_PATTERNS regex can't parse -- the
    # extracted subject/object still go through the exact same graph reasoning (_relate_terms)
    from genus import companion
    conn = _isa_graph()
    deuter = lambda q: {"absicht": "beziehung", "subject": "Hund", "object": "Säugetier"}
    result = companion.respond_with_deuter(conn, "gehoert sowas wie ein wuffwuff eigentlich dahin", deuter=deuter)
    assert result["text"].startswith("Ja.") and "Säugetier" in result["text"]
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
    assert result["text"].startswith("Ja.")            # the relation -- NOT a lecture on "Pflanzen"
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
    # "I don't know" answer), an unresolvable MODEL guess just leaves the honest fallback in
    # place -- a wrong guess can never manufacture an answer, it can only fail safe
    from genus import companion
    conn = _isa_graph()
    deuter = lambda q: {"absicht": "grammatik", "subject": "Erfundenwort"}
    baseline = companion.respond_in_conversation(conn, "was fuer ein wort ist das denn grammatikalisch")
    result = companion.respond_with_deuter(conn, "was fuer ein wort ist das denn grammatikalisch", deuter=deuter)
    assert result == baseline


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
    from genus import companion
    conn = _isa_graph()
    assert companion.confirmed_notes(conn) == []
    # "Zebra" sorts AFTER "Apfel" alphabetically but was told FIRST -- pins insertion order,
    # not sources.relations()'s alphabetical-by-object order (a real bug caught locally)
    companion.remember(conn, "Zebra mag ich am liebsten im Zoo")
    companion.remember(conn, "Apfelsaft trinke ich jeden Morgen")
    assert companion.confirmed_notes(conn) == [
        "Zebra mag ich am liebsten im Zoo", "Apfelsaft trinke ich jeden Morgen",
    ]


def test_remembering_is_not_hardcoded_to_be_about_ronny():
    # regression, caught live on the Pi (Ronny's own reaction was a 😂): "Merk dir dass du
    # GENUS heisst" is a fact about GENUS, not about Ronny -- slice 1 filed EVERYTHING as "a
    # fact about Ronny" regardless of content, so recalling it read back nonsensically. The
    # notebook is now general -- it just knows WHO TOLD it, never WHAT/WHOM a note is about.
    from genus import companion
    conn = _isa_graph()
    companion.remember(conn, "dass du GENUS heißt und Ronny dich erschaffen hat")
    assert companion.confirmed_notes(conn) == ["dass du GENUS heißt und Ronny dich erschaffen hat"]


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
    from genus import companion, sources
    conn = _isa_graph()
    companion.remember(conn, "ich mag Kaffee")
    assert sources.source_trust(conn, "ronny") >= sources.SOURCE_TRUST_SEED  # never model-capped


def test_a_deuter_suggested_statement_is_capped_and_marked_unconfirmed():
    from genus import companion, sources
    conn = _isa_graph()
    deuter = lambda q: {"absicht": "tatsache", "subject": "Hund"}
    result = companion.respond_with_deuter(conn, "ich habe zwei Hunde", deuter=deuter)
    assert "notiert" in result["text"] and "unsicher" in result["text"]
    assert companion.suggested_notes(conn) == ["ich habe zwei Hunde"]
    assert companion.confirmed_notes(conn) == []   # never conflated with a real "Merke dir"
    assert sources.source_trust(conn, companion.STATEMENT_SOURCE) <= sources.MODEL_TRUST_SEED


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
