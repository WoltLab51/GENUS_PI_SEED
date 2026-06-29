import json
import sqlite3

from click.testing import CliRunner

from genus import cli, event_router, integrity, reactors, sensor, sources
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
    payload = json.dumps(
        {"claim_key": CLAIM, "claim_value": value, "source": source,
         "derivation": f"source:{source}"},
        sort_keys=True,
        separators=(",", ":"),
    )
    conn.execute(
        "INSERT INTO event_log (event_type, payload, created_at) VALUES ('assertion_recorded', ?, ?)",
        (payload, created_at),
    )
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


def test_source_trust_fast_path_for_relation_only_source():
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")  # no value claim
    assert sources._has_value_assertions(conn, "wikidata") is False
    assert sources.source_trust(conn, "wikidata") == sources.SOURCE_TRUST_SEED  # seed, no scan


def test_source_trust_unchanged_for_value_sources():
    conn = _fresh()
    reactors.observe_assertion(conn, "thing.temp", "20", "a")
    reactors.observe_assertion(conn, "thing.temp", "20", "b")  # agrees with a
    assert sources._has_value_assertions(conn, "a") is True
    assert sources.source_trust(conn, "a") == 1.0  # full computation still runs (earned trust)


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
