import sqlite3

from genus import gender_rule, reactors
from genus.db import init_schema


def _fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def _gender(conn, noun, gender, source="wikidata-lexemes"):
    reactors.observe_relation(conn, f"{noun}@de", "grammatical_gender", gender, source)


def _seed_reliable_and_noisy(conn):
    # -chen: near-categorical neuter cue (real German grammar) -> reliable
    for noun in ("Mädchen", "Kaninchen", "Häuschen", "Brötchen", "Kätzchen"):
        _gender(conn, noun, "neutrum")
    # -el: genuinely mixed in German (Löffel masc, Gabel fem, ...) -> noisy, an even 50/50 split
    for noun, g in [("Löffel", "maskulin"), ("Onkel", "maskulin"), ("Sessel", "maskulin"),
                    ("Gabel", "feminin"), ("Kachel", "feminin"), ("Nadel", "feminin")]:
        _gender(conn, noun, g)
    return conn


def test_suffix_evidence_aggregates_across_nouns():
    conn = _seed_reliable_and_noisy(_fresh())
    ev = gender_rule.suffix_evidence(conn)
    assert ev[("chen", 4)]["neutrum"] == 5           # all 5 -chen nouns vote neuter
    assert set(ev[("el", 2)].keys()) == {"maskulin", "feminin"}  # -el is genuinely mixed


def test_calibrated_reliability_cut_finds_the_gap_between_reliable_and_noisy():
    conn = _seed_reliable_and_noisy(_fresh())
    cut = gender_rule.calibrated_reliability_cut(conn)
    assert cut != gender_rule.MIN_RELIABILITY          # DERIVED from the data, not the constant
    assert 0.60 < cut < 1.0                            # sits between noisy (~60%) and reliable (100%)


def test_predict_gender_trusts_the_reliable_suffix():
    conn = _seed_reliable_and_noisy(_fresh())
    r = gender_rule.predict_gender(conn, "Vögelchen@de")   # unseen noun, -chen suffix
    assert r["found"] and r["gender"] == "neutrum" and r["suffix"] == "chen"


def test_predict_gender_withholds_on_a_noisy_suffix():
    conn = _seed_reliable_and_noisy(_fresh())
    r = gender_rule.predict_gender(conn, "Wachtel@de")     # -el, but too noisy to trust
    assert r["found"] is False                             # open-world: withholds, doesn't guess


def test_predict_gender_prefers_the_longer_more_specific_suffix():
    conn = _fresh()
    # "-el" alone is noisy (mixed), but the more specific "-ndel" happens to be all feminine here
    for noun, g in [("Kachel", "feminin"), ("Nadel", "feminin"), ("Löffel", "maskulin")]:
        _gender(conn, noun, g)
    for noun in ("Kandel", "Mandel", "Sandel"):
        _gender(conn, noun, "feminin")
    r = gender_rule.predict_gender(conn, "Bandel@de")
    assert r["found"] and r["suffix"] == "ndel" and r["gender"] == "feminin"  # 4-char cue, not 2-char "-el"


def test_gender_is_multi_valued_for_homonyms_like_messer():
    conn = _fresh()
    _gender(conn, "Messer", "neutrum")     # das Messer -- the knife
    _gender(conn, "Messer", "maskulin")    # der Messer -- one who measures (rare agent noun)
    counts = gender_rule._gender_counts(conn)["Messer@de"]
    assert counts == {"neutrum": 1, "maskulin": 1}         # both recorded, neither overwrites the other


def test_self_test_leaveoneout_does_not_let_a_noun_confirm_itself():
    conn = _fresh()
    # exactly MIN_SUPPORT (3) nouns share a suffix -- removing any one leaves only 2, below
    # MIN_SUPPORT, so the rule can never fire FOR that noun using only the other two
    for noun in ("Mädchen", "Kaninchen", "Häuschen"):
        _gender(conn, noun, "neutrum")
    result = gender_rule.self_test(conn)
    assert result["checked"] == 0              # honest: not enough OTHER evidence to test any of them


def test_self_test_reports_a_real_exception():
    conn = _fresh()
    # 4 "-chen" nouns neuter (rule fires confidently) + 1 genuine exception with a different gender
    for noun in ("Mädchen", "Kaninchen", "Häuschen", "Brötchen"):
        _gender(conn, noun, "neutrum")
    _gender(conn, "Bärchen", "maskulin")   # a constructed exception to the -chen rule
    result = gender_rule.self_test(conn)
    assert result["accuracy"] is not None and result["accuracy"] < 1.0
    exc = next(e for e in result["exceptions"] if e["noun"] == "Bärchen@de")
    assert exc["predicted"] == "neutrum" and exc["actual"] == ["maskulin"]


def test_self_test_reports_perfect_accuracy_when_the_rule_holds_throughout():
    conn = _fresh()
    for noun in ("Mädchen", "Kaninchen", "Häuschen", "Brötchen", "Kätzchen"):
        _gender(conn, noun, "neutrum")
    result = gender_rule.self_test(conn)
    assert result["checked"] > 0 and result["accuracy"] == 1.0 and result["exceptions"] == []


def test_predict_gender_cli(monkeypatch):
    from click.testing import CliRunner
    from genus import cli
    conn = _seed_reliable_and_noisy(_fresh())
    monkeypatch.setattr(cli, "get_conn", lambda: conn)
    result = CliRunner().invoke(cli.main, ["predict-gender", "Vögelchen"])
    assert result.exit_code == 0, result.output
    assert "neutrum" in result.output and "chen" in result.output


def test_gender_rule_report_cli(monkeypatch):
    from click.testing import CliRunner
    from genus import cli
    conn = _fresh()
    for noun in ("Mädchen", "Kaninchen", "Häuschen", "Brötchen"):
        _gender(conn, noun, "neutrum")
    _gender(conn, "Bärchen", "maskulin")
    monkeypatch.setattr(cli, "get_conn", lambda: conn)
    result = CliRunner().invoke(cli.main, ["gender-rule"])
    assert result.exit_code == 0, result.output
    assert "Bärchen" in result.output and "Ausnahmen" in result.output


def test_companion_gender_question_reports_known_fact_over_guessing():
    from genus import companion
    conn = _fresh()
    _gender(conn, "Hund", "maskulin")
    r = companion.gender_question(conn, "Welches Geschlecht hat Hund?")
    assert r["gender_q"] and r["known"] == ["maskulin"]
    s = companion.narrate_gender(r)
    assert "maskulin" in s and "bekannt" in s and "vermutet" not in s


def test_companion_gender_question_shows_both_genders_of_a_homonym():
    from genus import companion
    conn = _fresh()
    _gender(conn, "Messer", "neutrum")
    _gender(conn, "Messer", "maskulin")
    r = companion.gender_question(conn, "Welches Geschlecht hat Messer?")
    assert r["known"] == ["maskulin", "neutrum"]           # both recorded senses, neither hidden


def test_companion_gender_question_falls_back_to_a_labelled_prediction():
    from genus import companion
    conn = _seed_reliable_and_noisy(_fresh())
    r = companion.gender_question(conn, "Welches Geschlecht hat Vögelchen?")   # unseen, -chen
    assert r["gender_q"] and not r["known"] and r["prediction"]["gender"] == "neutrum"
    s = companion.narrate_gender(r)
    assert "vermutet" in s and "Vermutung, kein Wissen" in s     # clearly labelled, not stated as fact


def test_companion_gender_question_withholds_honestly_when_unsure():
    from genus import companion
    conn = _fresh()
    r = companion.gender_question(conn, "Welches Geschlecht hat Quuxikon?")
    assert r["gender_q"] and not r["known"] and r["prediction"] is None
    assert "rät nicht" in companion.narrate_gender(r)


def test_gender_question_not_triggered_by_an_unrelated_question():
    from genus import companion
    conn = _fresh()
    assert companion.gender_question(conn, "Was ist ein Hund?")["gender_q"] is False


def test_ask_cli_routes_gender_question(monkeypatch):
    from click.testing import CliRunner
    from genus import cli
    conn = _fresh()
    _gender(conn, "Hund", "maskulin")
    monkeypatch.setattr(cli, "get_conn", lambda: conn)
    monkeypatch.setattr(cli, "get_diagnostic_conn", lambda: conn)
    result = CliRunner().invoke(cli.main, ["ask", "Welches", "Geschlecht", "hat", "Hund?"])
    assert result.exit_code == 0, result.output
    assert "maskulin" in result.output


def test_respond_routes_state_query_as_plain_text():
    from genus import companion
    conn = _fresh()
    s = companion.respond(conn, "status")
    assert "projection summary" in s and "[ASK]" not in s and "[BLF]" not in s  # plain, no CLI tags


def test_respond_routes_relational_question():
    from genus import companion
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Säugetier@de", "expresses", "Q_s", "wikidata")
    reactors.observe_relation(conn, "Q144", "is_a", "Q_s", "wikidata")
    s = companion.respond(conn, "Ist ein Hund ein Säugetier?")
    assert "Ja." in s and "Säugetier" in s


def test_respond_routes_gender_question():
    from genus import companion
    conn = _fresh()
    _gender(conn, "Hund", "maskulin")
    assert "maskulin" in companion.respond(conn, "Welches Geschlecht hat Hund?")


def test_respond_routes_word_definition_with_concept_hint():
    from genus import companion
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier, Vorfahre der Wolf", "dbnary")
    s = companion.respond(conn, "Was ist ein Hund?")
    assert "Wolf" in s and "genus concept Q144" in s


def test_respond_falls_back_to_help_when_nothing_matches():
    from genus import companion
    conn = _fresh()
    s = companion.respond(conn, "Quuxikon Blarg?")
    assert "GENUS nicht einordnen" in s  # the query.ask help text, honest German -- never a raw
                                          # internal placeholder leaking to a real conversation
