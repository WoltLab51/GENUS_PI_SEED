import sqlite3
import sys
from pathlib import Path

import pytest

from genus import reactors
from genus.db import init_schema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy"))
import telegram_bot  # noqa: E402  (deploy/ script, imported directly for its pure logic)
import deuter  # noqa: E402
import stimme  # noqa: E402


class _FakeModel:
    """A minimal stand-in for llama_cpp.Llama's chat-completion surface -- no real model,
    no GGUF file, just the one method deuter.py/stimme.py actually call."""

    def __init__(self, reply: str):
        self.reply = reply
        self.calls: list = []

    def create_chat_completion(self, messages, max_tokens=None, temperature=None):
        self.calls.append(messages)
        return {"choices": [{"message": {"content": self.reply}}]}


@pytest.fixture(autouse=True)
def _no_real_deuter_model(monkeypatch):
    """Every test here must behave the same regardless of whether a Deuter model happens to be
    installed on the machine running them (the deployed Pi has one; a fresh dev/CI box doesn't)
    -- force "not installed" by default, so a session-based test can't silently start loading
    the real 1.5B model just because a chat_id's message falls through to the fallback sentinel.
    Tests that specifically exercise the wiring monkeypatch ``deuter.interpret``/``get_model``
    (and ``stimme.formuliere``), which override this."""
    monkeypatch.setattr(deuter, "MODEL_PATH", "/nonexistent/path/model.gguf")
    monkeypatch.setattr(stimme, "MODEL_PATH", "/nonexistent/path/model.gguf")


@pytest.fixture(autouse=True)
def _korrektur_datei_im_tmp(monkeypatch, tmp_path):
    """Die Lernkreis-Edge-Datei darf in Tests NIE ins echte ~/.genus schreiben."""
    monkeypatch.setattr(telegram_bot, "KORREKTUR_DATEI",
                        str(tmp_path / "korrekturen.jsonl"))


def _fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def _msg(update_id, sender_id, text, chat_id=None):
    return {
        "update_id": update_id,
        "message": {"from": {"id": sender_id}, "chat": {"id": chat_id or sender_id}, "text": text},
    }


def test_unauthorized_sender_is_ignored():
    conn = _fresh()
    result = telegram_bot.handle_update(conn, _msg(1, 999, "Was ist ein Hund?"), allowed={42})
    assert result is None


def test_authorized_sender_gets_answered_via_companion_respond():
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier, Vorfahre der Wolf", "dbnary")
    result = telegram_bot.handle_update(conn, _msg(1, 42, "Was ist ein Hund?"), allowed={42})
    assert result is not None
    chat_id, answer = result
    assert chat_id == 42 and "Wolf" in answer


def test_update_without_text_is_ignored():
    conn = _fresh()
    update = {"update_id": 1, "message": {"from": {"id": 42}, "chat": {"id": 42}}}  # no "text" (e.g. a photo)
    assert telegram_bot.handle_update(conn, update, allowed={42}) is None


def test_update_without_message_is_ignored():
    conn = _fresh()
    assert telegram_bot.handle_update(conn, {"update_id": 1}, allowed={42}) is None


def test_a_bug_in_answering_is_caught_not_raised(monkeypatch):
    conn = _fresh()
    from genus import companion
    monkeypatch.setattr(companion, "respond", lambda c, q: (_ for _ in ()).throw(RuntimeError("boom")))
    chat_id, answer = telegram_bot.handle_update(conn, _msg(1, 42, "irgendwas"), allowed={42})
    assert chat_id == 42 and "schiefgelaufen" in answer   # graceful, never crashes the loop


def test_sessions_let_a_bare_followup_retrace_the_previous_answer():
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Haustier@de", "expresses", "Q_pet", "wikidata")
    reactors.observe_relation(conn, "Q144", "is_a", "Q_pet", "wikidata")
    sessions: dict = {}

    telegram_bot.handle_update(conn, _msg(1, 42, "Ist ein Hund ein Haustier?"), allowed={42}, sessions=sessions)
    chat_id, answer = telegram_bot.handle_update(conn, _msg(2, 42, "warum?"), allowed={42}, sessions=sessions)

    assert chat_id == 42
    assert "Herleitung" in answer and "wikidata" in answer   # retraced, not "kein Wort bekannt"


def test_session_threads_last_answer_into_the_meta_zellen(monkeypatch):
    # Antwort-Würfel Scheibe 1: a follow-up like "kürzer" needs the PREVIOUS answer, not just
    # the previous question -- the session must carry both across turns
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier, Vorfahre der Wolf", "dbnary")
    lesarten = {"Was ist ein Hund?": {"absicht": "definition", "subject": "Hund"},
                "nochmal bitte": {"absicht": "wiederholen"}}
    monkeypatch.setattr(deuter, "interpret",
                        lambda q, absichten=None, grammatik=None, korrekturen=None: lesarten[q])
    sessions: dict = {}

    telegram_bot.handle_update(conn, _msg(1, 42, "Was ist ein Hund?"), allowed={42}, sessions=sessions)
    chat_id, answer = telegram_bot.handle_update(conn, _msg(2, 42, "nochmal bitte"), allowed={42}, sessions=sessions)

    assert chat_id == 42
    assert answer.startswith("Nochmal: ") and "Wolf" in answer


def test_sessions_are_kept_separate_per_chat():
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier, Vorfahre der Wolf", "dbnary")
    sessions: dict = {}

    telegram_bot.handle_update(conn, _msg(1, 42, "Was ist ein Hund?"), allowed={42}, sessions=sessions)
    # a DIFFERENT chat asks a bare followup with no history of its own -- must not see chat 42's question
    _, answer = telegram_bot.handle_update(
        conn, _msg(2, 42, "warum?", chat_id=99), allowed={42}, sessions=sessions,
    )
    assert "Herleitung" not in answer   # chat 99 has no prior turn -> ordinary routing, not a stale trace


def test_sessions_resolve_a_von_vorhin_backreference_across_two_turns():
    # Mehr-Zug-Arbeitsgedächtnis: Runde 3 fragt "von vorhin" -- muss Runde 1 (Fahrrad) treffen,
    # nicht die dazwischenliegende Runde 2 (ein Gruss ohne bekanntes Wort)
    conn = _fresh()
    reactors.observe_relation(conn, "Fahrrad@de", "expresses", "Q_fahrrad", "wikidata")
    reactors.observe_relation(conn, "Fahrrad@de", "primary_gloss", "ein Zweirad zum Fahren", "dbnary")
    sessions: dict = {}

    telegram_bot.handle_update(conn, _msg(1, 42, "Was ist ein Fahrrad?"), allowed={42}, sessions=sessions)
    telegram_bot.handle_update(conn, _msg(2, 42, "Hallo!"), allowed={42}, sessions=sessions)
    chat_id, answer = telegram_bot.handle_update(
        conn, _msg(3, 42, "was war das von vorhin?"), allowed={42}, sessions=sessions)

    assert chat_id == 42
    assert "Zweirad" in answer and "Was ist ein Fahrrad?" in answer


def test_session_turn_history_is_capped_not_unbounded():
    conn = _fresh()
    reactors.observe_relation(conn, "Fahrrad@de", "expresses", "Q_fahrrad", "wikidata")
    reactors.observe_relation(conn, "Fahrrad@de", "primary_gloss", "ein Zweirad zum Fahren", "dbnary")
    sessions: dict = {}
    for i in range(telegram_bot._VERLAUF_MAX + 4):
        telegram_bot.handle_update(conn, _msg(i, 42, f"Runde {i}"), allowed={42}, sessions=sessions)
    assert len(sessions[42]) == telegram_bot._VERLAUF_MAX


def test_without_sessions_behaves_exactly_as_before():
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier, Vorfahre der Wolf", "dbnary")
    result = telegram_bot.handle_update(conn, _msg(1, 42, "Was ist ein Hund?"), allowed={42})   # no sessions
    assert result is not None and "Wolf" in result[1]


def test_bot_is_wired_to_the_deuter_as_a_last_resort(monkeypatch):
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier, Vorfahre der Wolf", "dbnary")
    monkeypatch.setattr(deuter, "interpret",
                        lambda q, absichten=None, grammatik=None, korrekturen=None: {"absicht": "definition",
                                                                   "subject": "Hund"})

    chat_id, answer = telegram_bot.handle_update(
        conn, _msg(1, 42, "so ne frage zu dem wuffwuff thema"), allowed={42}, sessions={},
    )
    assert chat_id == 42
    assert "Wolf" in answer and "Sprachmodell gedeutet" in answer


def test_bot_stays_honest_when_the_deuter_is_not_installed():
    # the autouse fixture above already forces "not installed" for every test in this file
    conn = _fresh()
    chat_id, answer = telegram_bot.handle_update(
        conn, _msg(1, 42, "voellig unverstaendliche anfrage"), allowed={42}, sessions={},
    )
    assert chat_id == 42
    assert "schiefgelaufen" not in answer   # no crash, just the ordinary honest fallback


def test_deuter_never_calls_a_real_question_a_statement():
    # live-caught 2026-07-02: "was ist ein Hund" (an unambiguous question) came back from the
    # real model as {"intent": "statement", ...} -- a structural, deterministic veto, not a
    # prompt tweak: ANY "statement" verdict for text that looks like a question is retried as
    # "definition" instead, regardless of what the model said.
    assert deuter._looks_like_question("was ist ein Hund")
    assert deuter._looks_like_question("Ist das so?")
    assert deuter._looks_like_question("kannst du mir das erklären")
    assert not deuter._looks_like_question("ich habe zwei Hunde")
    assert not deuter._looks_like_question("mein Geburtstag ist im Mai")


def test_deuter_interpret_distinguishes_explicit_empty_from_hard_failure(monkeypatch):
    # live gefunden: "OK prima" bekam wortwörtlich "[]" vom echten Modell zurück -- eine
    # erfolgreich geparste, aber LEERE Liste ist ein anderes Signal als "Modell/JSON kaputt"
    monkeypatch.setattr(deuter, "MODEL_PATH", __file__)   # eine echt existierende Datei genügt
    monkeypatch.setattr(deuter, "_get_model", lambda: _FakeModel("[]"))
    assert deuter.interpret("OK prima") == []

    monkeypatch.setattr(deuter, "_get_model", lambda: _FakeModel("das ist kein JSON"))
    assert deuter.interpret("kaputte antwort") is None


def test_stimme_anchors_extracts_every_quoted_word_and_number():
    satz = "Unter »Hund« versteht GENUS: Haustier. (Vertrauen 0.50 — hergeleitet.)"
    assert stimme._anchors(satz) == ["Hund", "0.50"]


def test_stimme_formuliere_returns_the_rephrase_when_every_anchor_survives():
    satz = "Unter »Hund« versteht GENUS: Haustier, dessen Vorfahre der Wolf ist."
    model = _FakeModel("»Hund« ist laut GENUS ein Haustier, das vom Wolf abstammt.")
    result = stimme.formuliere(satz, model=model)
    assert result == model.reply
    assert model.calls and model.calls[0][1]["content"] == satz   # the original, unmodified


def test_stimme_formuliere_fails_safe_when_an_anchor_goes_missing():
    # the model dropped the quoted word entirely -- a faithfulness violation, not a style choice
    satz = "Unter »Hund« versteht GENUS: Haustier."
    model = _FakeModel("Ein Tier, das gerne bellt.")
    assert stimme.formuliere(satz, model=model) is None


def test_stimme_catches_a_corrupted_category_name_when_it_is_a_quoted_anchor():
    # live fund (2026-07-03): companion.narrate() left is_a-category names UNQUOTED, so a
    # rephrase could silently corrupt one ("Kernobst" -> "Kernaubere") without the anchor
    # check ever noticing -- only the headword was protected. Fixed at the source (companion
    # now quotes every named category), which this pins from the Stimme's side: once quoted,
    # a corrupted category name is exactly the kind of anchor loss formuliere() must catch.
    satz = "Unter »Apfel« versteht GENUS: Frucht; es zählt zu »Kernobst« und »Obst«."
    model = _FakeModel("»Apfel« ist laut GENUS eine Frucht aus der Familie der Kernaubere.")
    assert stimme.formuliere(satz, model=model) is None


def test_stimme_formuliere_fails_safe_when_a_number_is_altered():
    satz = "Ja. »Apfel« zählt zu »Pflanzen«. (Vertrauen 0.50 — hergeleitet.)"
    model = _FakeModel("»Apfel« gehört laut GENUS zu »Pflanzen«. (Vertrauen 0.95 — hergeleitet.)")
    assert stimme.formuliere(satz, model=model) is None   # the model must not invent confidence


def test_stimme_formuliere_returns_none_without_a_model_and_none_installed():
    # the autouse fixture forces stimme.MODEL_PATH to a nonexistent path
    assert stimme.formuliere("Unter »Hund« versteht GENUS: Haustier.") is None


def test_bot_gives_deuter_and_stimme_each_their_own_model(monkeypatch):
    # live gemessen (2026-07-03): ein geteiltes Modell verwarf bei jedem Stimme-Aufruf den
    # Prompt-Cache des Deuter (anderer System-Prompt) -- der NÄCHSTE Deuter-Aufruf brauchte dann
    # 26s statt 3s. Jetzt bekommt jede Rolle ihr eigenes warmes Modell; der Bot ruft
    # stimme.formuliere direkt auf (ohne ein model= von deuter.get_model() durchzureichen --
    # die Funktion existiert seit diesem Fix gar nicht mehr).
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier, Vorfahre der Wolf", "dbnary")
    assert not hasattr(deuter, "get_model")
    seen_models = []

    def spy(satz, model=None):
        seen_models.append(model)
        return "»Hund« ist laut GENUS ein Haustier, das vom Wolf abstammt."
    monkeypatch.setattr(stimme, "formuliere", spy)

    chat_id, answer = telegram_bot.handle_update(
        conn, _msg(1, 42, "Was ist ein Hund?"), allowed={42}, sessions={},
    )
    assert seen_models == [None]   # kein geteiltes Modell durchgereicht -- stimme lädt ihr eigenes
    assert "Sprachlich vom Modell geglättet" in answer


def test_bot_falls_back_to_the_template_when_no_model_is_installed():
    # the autouse fixture forces "not installed" -- stimme must never be consulted, and the
    # plain deterministic answer must reach the user unmarked
    conn = _fresh()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier, Vorfahre der Wolf", "dbnary")
    chat_id, answer = telegram_bot.handle_update(
        conn, _msg(1, 42, "Was ist ein Hund?"), allowed={42}, sessions={},
    )
    assert "Wolf" in answer and "geglättet" not in answer


def test_allowed_ids_parses_comma_separated_list(monkeypatch):
    monkeypatch.setenv("GENUS_TELEGRAM_ALLOWED_IDS", "111, 222 ,333")
    assert telegram_bot._allowed_ids() == {111, 222, 333}


def test_allowed_ids_skips_malformed_entries(monkeypatch):
    monkeypatch.setenv("GENUS_TELEGRAM_ALLOWED_IDS", "111,notanumber,222")
    assert telegram_bot._allowed_ids() == {111, 222}


def test_allowed_ids_empty_by_default(monkeypatch):
    monkeypatch.delenv("GENUS_TELEGRAM_ALLOWED_IDS", raising=False)
    assert telegram_bot._allowed_ids() == set()


def test_main_refuses_to_start_without_a_token(monkeypatch, tmp_path):
    monkeypatch.delenv("GENUS_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setattr(telegram_bot, "TOKEN_FILE", str(tmp_path / "no_such_token_file"))
    assert telegram_bot.main() == 1


def test_main_refuses_to_start_with_an_empty_allowlist(monkeypatch):
    monkeypatch.setenv("GENUS_TELEGRAM_BOT_TOKEN", "fake-token-for-test")
    monkeypatch.delenv("GENUS_TELEGRAM_ALLOWED_IDS", raising=False)
    assert telegram_bot.main() == 1


def test_bot_verbindet_ueber_genus_db_connect_nicht_roh():
    # Phase 0 der Ziel-Architektur: der Bot bekommt dieselben Pragmas (WAL, busy_timeout)
    # und Spalten-Migrationen wie die CLI. Ein roher sqlite3.connect in main() hiess:
    # dieser eine Zugang konnte sich auf einer frischen/unmigrierten DB anders verhalten
    # als jeder andere. Struktur-Gate wie test_membrane_purity: der Quelltext selbst
    # wird geprueft, damit die Abweichung nicht zurueckschleichen kann.
    quelle = (ROOT / "deploy" / "telegram_bot.py").read_text(encoding="utf-8")
    assert "db.connect(" in quelle
    assert "sqlite3.connect(" not in quelle


# --- Phase 2 der Ziel-Architektur: die GRENZE (constrained decoding) + Naht 5 ---------


def test_deuter_spiegel_driftet_nie_vom_raster(conn):
    # Naht 5: der hartkodierte Spiegel (DEFAULT_ABSICHTEN/_GRUPPEN/_ERKLAERUNGEN) konnte
    # vom gesaeten Raster wegdriften -- LIVE SO PASSIERT: "berechnen" war gesaet, aber im
    # Spiegel unbekannt und wurde vom gruppierten Prompt still verschluckt. Dieser Pin
    # bricht CI an der Stelle, wo die Drift entsteht (eine Code-Aenderung an nur einer
    # der beiden Seiten).
    from genus import verstehen

    raster_blaetter = {leaf for leaf, _ in verstehen.RASTER_SEED}
    assert set(deuter.DEFAULT_ABSICHTEN) == raster_blaetter | {"unklar"}
    # jedes Blatt hat eine Erklaerung und einen Platz in genau einer Prompt-Gruppe
    gruppiert = [b for _, blaetter in deuter._GRUPPEN for b in blaetter]
    assert sorted(gruppiert) == sorted(set(gruppiert)), "ein Blatt in zwei Gruppen"
    assert set(gruppiert) == raster_blaetter
    assert set(deuter._ERKLAERUNGEN) == raster_blaetter | {"unklar"}


def test_system_prompt_verschluckt_kein_angebotenes_blatt_mehr():
    # Das Auffangnetz: ein im Graphen gesaetes Blatt ohne Gruppen-Zuordnung im Spiegel
    # erscheint trotzdem im Prompt (unter WEITERE) statt still zu verschwinden.
    prompt = deuter._system_prompt(("definition", "voellig-neues-blatt"))
    assert "voellig-neues-blatt" in prompt
    assert "WEITERE" in prompt


def test_gbnf_grammatik_kompiliert_die_blaetter_als_grenze():
    from genus import verstehen

    grammatik = verstehen.gbnf_grammatik(("definition", "dank"))
    assert grammatik.startswith("root ::=")
    # jedes Blatt ist eine einkompilierte Alternative, unklar immer dabei
    assert '"\\"definition\\""' in grammatik
    assert '"\\"dank\\""' in grammatik
    assert '"\\"unklar\\""' in grammatik
    # der Segment-Vertrag (die vier Schluessel in fester Reihenfolge) steht drin
    for schluessel in ("text", "absicht", "subject", "object"):
        assert f'\\"{schluessel}\\"' in grammatik
    # ohne Angebot: das RASTER_SEED ist die Grenze
    voll = verstehen.gbnf_grammatik(None)
    assert '"\\"berechnen\\""' in voll


class _FakeModelMitKwargs(_FakeModel):
    def __init__(self, reply: str):
        super().__init__(reply)
        self.kwargs: list[dict] = []

    def create_chat_completion(self, messages, max_tokens=None, temperature=None, **kwargs):
        self.kwargs.append(kwargs)
        return super().create_chat_completion(messages, max_tokens, temperature)


def test_interpret_reicht_die_grenze_ans_modell_durch(monkeypatch):
    fake = _FakeModelMitKwargs('[{"text": "hi", "absicht": "gruss", "subject": null, '
                               '"object": null}]')
    monkeypatch.setattr(deuter, "MODEL_PATH", __file__)
    monkeypatch.setattr(deuter, "_get_model", lambda: fake)
    monkeypatch.setattr(deuter, "_gbnf", lambda text: f"KOMPILIERT:{len(text)}")

    ergebnis = deuter.interpret("hi", grammatik="root ::= irgendwas")
    assert ergebnis and ergebnis[0]["absicht"] == "gruss"
    assert fake.kwargs == [{"grammar": f"KOMPILIERT:{len('root ::= irgendwas')}"}]


def test_unbrauchbare_grammatik_degradiert_ehrlich_statt_zu_schweigen(monkeypatch, capsys):
    # _gbnf kann nicht kompilieren -> lauter stderr-Hinweis, aber der Deuter laeuft
    # UNBESCHRAENKT weiter (der Bot bleibt antwortfaehig; der Verlust der Garantie
    # passiert nie still). ZWEI Pi-Deploy-Funde stecken in diesem Test: (1) "root ::=
    # kaputt" war auf dem Pi GUELTIGES GBNF (llama_cpp installiert; der Test lief nur
    # auf der Dev-Box gruen); (2) der Pi-Parser schluckt sogar eine offene Klammer --
    # auf Parser-Strenge laesst sich nicht wetten. Also wird das Scheitern hermetisch
    # INJIZIERT: ein Fake-llama_cpp, dessen from_string wirft -- deterministisch auf
    # jeder Maschine, und es testet exakt unseren except-Pfad. (Der echte Fehlerfall
    # auf dem Pi laege ohnehin erst beim Generieren -- den faengt interprets
    # try/except -> None -> ehrlicher Wort-Lookup-Fallback.)
    import types

    kaputtes_llama = types.ModuleType("llama_cpp")

    class _KaputteGrammatik:
        @staticmethod
        def from_string(text, verbose=False):
            raise ValueError("injiziert: kompiliert nie")

    kaputtes_llama.LlamaGrammar = _KaputteGrammatik
    monkeypatch.setitem(sys.modules, "llama_cpp", kaputtes_llama)

    fake = _FakeModelMitKwargs('[{"text": "hi", "absicht": "gruss", "subject": null, '
                               '"object": null}]')
    monkeypatch.setattr(deuter, "MODEL_PATH", __file__)
    monkeypatch.setattr(deuter, "_get_model", lambda: fake)
    deuter._grammatik_cache.clear()

    ergebnis = deuter.interpret("hi", grammatik="root ::= irrelevant")
    assert ergebnis and ergebnis[0]["absicht"] == "gruss"
    assert fake.kwargs == [{}]   # keine Grammatik durchgereicht
    assert "UNBESCHRÄNKT" in capsys.readouterr().err
    deuter._grammatik_cache.clear()


def test_bot_leitet_die_grenze_aus_dem_lebenden_raster_ab(monkeypatch):
    conn = _fresh()
    from genus import verstehen
    verstehen.seed_raster(conn)
    empfangen: dict = {}

    def fake_interpret(q, absichten=None, grammatik=None, korrekturen=None):
        empfangen["absichten"] = absichten
        empfangen["grammatik"] = grammatik
        return [{"text": q, "absicht": "gruss", "subject": None, "object": None}]

    monkeypatch.setattr(deuter, "interpret", fake_interpret)
    telegram_bot.handle_update(conn, _msg(1, 42, "Hallo!"), allowed={42}, sessions={})

    assert empfangen["grammatik"] is not None and empfangen["grammatik"].startswith("root ::=")
    # die Grenze kommt aus demselben lebenden Angebot wie der Prompt
    assert '"\\"berechnen\\""' in empfangen["grammatik"]


def test_fabrizierter_segment_text_wird_nicht_geglaubt(monkeypatch):
    # Live-Fund (Pi, 2026-07-04): das Modell meldete ein Segment mit dem Text
    # "f'(x) = 2x + 3" -- selbst ausgerechnet, steht nirgends in der Nachricht. Die
    # Grammatik erzwingt Struktur, nicht Herkunft; die prueft der deterministische
    # Segment-Filter: fabrizierter Text -> die ganze Nachricht ist die ehrliche Klausel.
    fake = _FakeModelMitKwargs(
        '[{"text": "f\'(x) = 2x + 3", "absicht": "berechnen", "subject": null, '
        '"object": null}]'
    )
    monkeypatch.setattr(deuter, "MODEL_PATH", __file__)
    monkeypatch.setattr(deuter, "_get_model", lambda: fake)

    nachricht = "Bestimme die Ableitung von f(x) = x^2 + 3x"
    ergebnis = deuter.interpret(nachricht)
    assert ergebnis and ergebnis[0]["absicht"] == "berechnen"
    assert ergebnis[0]["text"] == nachricht   # nicht der fabrizierte Text

    # ein ECHTER Teil-Text der Nachricht bleibt dagegen unangetastet
    fake2 = _FakeModelMitKwargs(
        '[{"text": "Danke!", "absicht": "dank", "subject": null, "object": null}]'
    )
    monkeypatch.setattr(deuter, "_get_model", lambda: fake2)
    ergebnis2 = deuter.interpret("Was ist ein Hund? Danke!")
    assert ergebnis2 and ergebnis2[0]["text"] == "Danke!"


# --- Phase 3 Scheibe 3: der enge Korrektur-Kanal (Naht 1) -----------------------------


def test_korrektur_cue_ist_exakt_und_deutungsfrei():
    from genus import companion

    assert companion.korrektur_cue("falsch verstanden") == (True, None)
    assert companion.korrektur_cue("Falsch gedeutet!") == (True, None)
    assert companion.korrektur_cue("falsch verstanden: beziehung") == (True, "beziehung")
    # ein laengerer Satz ist KEIN Cue -- er muesste sonst durch genau den Klassifikator,
    # der eben danebengriff (zirkulaer, Naht 1)
    assert companion.korrektur_cue("das hast du falsch verstanden, glaube ich") == (False, None)
    assert companion.korrektur_cue("Was ist ein Hund?") == (False, None)


def test_korrektur_haelt_fehlgriff_als_struktur_fest_nie_text():
    from genus import companion, verstehen

    conn = _fresh()
    verstehen.seed_raster(conn)
    result = companion.respond_with_deuter(
        conn, "falsch verstanden", last_question="Wie wird das Wetter morgen?",
        letzte_lesarten=["abschied"],
    )
    assert "abschied" in result["text"] and "gemerkt" in result["text"]
    assert result["question"] == "Wie wird das Wetter morgen?"   # Anker bleibt beim Thema
    assert verstehen.fehlgriffe(conn, "abschied")["gesamt"] == 1
    # Ledger≠Memory: der Wortlaut der korrigierten Frage steht NIRGENDS im Ledger
    rows = conn.execute("SELECT payload FROM event_log").fetchall()
    assert all("Wetter morgen" not in r["payload"] for r in rows)


def test_korrektur_mit_blattnamen_haelt_die_verwechslung_fest():
    from genus import companion, sources, verstehen

    conn = _fresh()
    verstehen.seed_raster(conn)
    result = companion.respond_with_deuter(
        conn, "falsch verstanden: weltfrage", letzte_lesarten=["abschied"],
    )
    assert "weltfrage" in result["text"]
    kanten = sources.relations(conn, subject="absicht:abschied",
                               predicate=verstehen.FEHLGRIFF_STATT)
    assert [k["object"] for k in kanten] == ["absicht:weltfrage"]


def test_korrektur_mit_unbekanntem_blatt_bleibt_ehrlich():
    from genus import companion, verstehen

    conn = _fresh()
    verstehen.seed_raster(conn)
    result = companion.respond_with_deuter(
        conn, "falsch verstanden: quatschblatt", letzte_lesarten=["dank"],
    )
    assert "kenne ich allerdings nicht" in result["text"]
    assert verstehen.fehlgriffe(conn, "dank")["gesamt"] == 1   # der Fehlgriff zaehlt trotzdem


def test_korrektur_ohne_letzte_deutung_antwortet_ehrlich_und_schreibt_nichts():
    from genus import companion

    conn = _fresh()
    vorher = conn.execute("SELECT COUNT(*) AS n FROM event_log").fetchone()["n"]
    result = companion.respond_with_deuter(conn, "falsch verstanden")
    assert "keine letzte Deutung" in result["text"]
    nachher = conn.execute("SELECT COUNT(*) AS n FROM event_log").fetchone()["n"]
    assert nachher == vorher


def test_bot_faedelt_gelesen_durch_die_session_ende_zu_ende(monkeypatch):
    # Zug 1: der Deuter greift daneben (liest eine Wetterfrage als "abschied").
    # Zug 2: das exakte "falsch verstanden" korrigiert -- Ende zu Ende ueber die Session.
    from genus import verstehen

    conn = _fresh()
    verstehen.seed_raster(conn)
    monkeypatch.setattr(deuter, "interpret",
                        lambda q, absichten=None, grammatik=None, korrekturen=None:
                        [{"text": q, "absicht": "abschied", "subject": None, "object": None}])
    sessions: dict = {}

    telegram_bot.handle_update(conn, _msg(1, 42, "Wie wird das Wetter morgen?"),
                               allowed={42}, sessions=sessions)
    assert sessions[42][-1]["gelesen"] == ["abschied"]
    chat_id, answer = telegram_bot.handle_update(conn, _msg(2, 42, "falsch verstanden"),
                                                 allowed={42}, sessions=sessions)
    assert chat_id == 42 and "abschied" in answer
    assert verstehen.fehlgriffe(conn, "abschied")["gesamt"] == 1
    # der Korrektur-Zug selbst traegt keine Lesart -- eine Doppel-Korrektur laeuft nie im Kreis
    assert sessions[42][-1]["gelesen"] == []


# --- Lernkreis v1 (Naht 4): Verwechslungs-Wissen + Korrektur-Beispiele ----------------


def test_verwechslungen_trennen_muster_von_einzelfall():
    from genus import verstehen

    conn = _fresh()
    verstehen.seed_raster(conn)
    # zweimal dieselbe Verwechslung = Muster; einmal eine andere = Einzelfall
    verstehen.record_fehlgriff(conn, "abschied", "weltfrage")
    verstehen.record_fehlgriff(conn, "abschied", "weltfrage")
    verstehen.record_fehlgriff(conn, "gruss", "dank")
    v = verstehen.verwechslungen(conn)
    assert v == [{"gelesen": "abschied", "gemeint": "weltfrage", "n": 2}]
    # eine einzelne Korrektur allein bleibt unter der Gueltigkeits-Saat
    conn2 = _fresh()
    verstehen.record_fehlgriff(conn2, "gruss", "dank")
    assert verstehen.verwechslungen(conn2) == []


def test_deuter_prompt_traegt_den_lernkreis_rueckfluss():
    prompt = deuter._system_prompt(None, [
        {"gelesen": "abschied", "gemeint": "weltfrage"},
        {"gelesen": "abschied", "gemeint": "weltfrage",
         "beispiel": "Wie wird das Wetter morgen?"},
    ])
    assert "BEKANNTE FEHLGRIFFE" in prompt
    assert 'lies im Zweifel "weltfrage" statt "abschied"' in prompt
    assert "Wie wird das Wetter morgen? -> weltfrage" in prompt
    # ohne Korrekturen: kein Abschnitt (der Prompt-Praefix bleibt exakt wie vorher)
    assert "BEKANNTE FEHLGRIFFE" not in deuter._system_prompt(None)


def test_merke_korrektur_datei_bleibt_gedeckelt():
    import json as _json

    for i in range(telegram_bot._KORREKTUR_MAX + 7):
        telegram_bot._merke_korrektur(f"Frage {i}", ["abschied"], "weltfrage")
    zeilen = open(telegram_bot.KORREKTUR_DATEI, encoding="utf-8").read().splitlines()
    assert len(zeilen) == telegram_bot._KORREKTUR_MAX
    assert _json.loads(zeilen[-1])["text"] == f"Frage {telegram_bot._KORREKTUR_MAX + 6}"


def test_korrektur_zug_landet_als_beispiel_in_der_edge_datei(monkeypatch):
    import json as _json
    from genus import verstehen

    conn = _fresh()
    verstehen.seed_raster(conn)
    monkeypatch.setattr(deuter, "interpret",
                        lambda q, absichten=None, grammatik=None, korrekturen=None:
                        [{"text": q, "absicht": "abschied", "subject": None, "object": None}])
    sessions: dict = {}
    telegram_bot.handle_update(conn, _msg(1, 42, "Wie wird das Wetter morgen?"),
                               allowed={42}, sessions=sessions)
    telegram_bot.handle_update(conn, _msg(2, 42, "falsch verstanden: weltfrage"),
                               allowed={42}, sessions=sessions)
    zeilen = open(telegram_bot.KORREKTUR_DATEI, encoding="utf-8").read().splitlines()
    eintrag = _json.loads(zeilen[-1])
    assert eintrag == {"text": "Wie wird das Wetter morgen?",
                       "falsch": ["abschied"], "richtig": "weltfrage"}


def test_naechste_nachricht_bekommt_den_rueckfluss_in_den_deuter(monkeypatch):
    from genus import verstehen

    conn = _fresh()
    verstehen.seed_raster(conn)
    # gelebte Historie: zweimal korrigierte Verwechslung im Graphen + ein Beispiel in der Datei
    verstehen.record_fehlgriff(conn, "abschied", "weltfrage")
    verstehen.record_fehlgriff(conn, "abschied", "weltfrage")
    telegram_bot._merke_korrektur("Wie wird das Wetter morgen?", ["abschied"], "weltfrage")
    empfangen: dict = {}

    def fake_interpret(q, absichten=None, grammatik=None, korrekturen=None):
        empfangen["korrekturen"] = korrekturen
        return [{"text": q, "absicht": "gruss", "subject": None, "object": None}]

    monkeypatch.setattr(deuter, "interpret", fake_interpret)
    telegram_bot.handle_update(conn, _msg(1, 42, "Hallo!"), allowed={42}, sessions={})

    k = empfangen["korrekturen"]
    assert {"gelesen": "abschied", "gemeint": "weltfrage"} in k
    assert any(e.get("beispiel") == "Wie wird das Wetter morgen?" for e in k)


# --- der Selbst-Neustart: kein sudo mehr für Deploys (Ronny, 2026-07-04) --------------


def test_neustart_flag_zaehlt_nur_wenn_frischer_als_der_prozess(monkeypatch, tmp_path):
    import os as _os
    import time as _time

    flag = tmp_path / "telegram_bot.neustart"
    monkeypatch.setattr(telegram_bot, "NEUSTART_DATEI", str(flag))
    jetzt = _time.time()
    # kein Flag -> kein Neustart
    assert telegram_bot._neustart_angefordert(jetzt) is False
    # ein ALTES Flag (Ueberbleibsel von vor dem Start) -> kein Neustart, keine Schleife
    flag.write_text("", encoding="utf-8")
    _os.utime(flag, (jetzt - 100, jetzt - 100))
    assert telegram_bot._neustart_angefordert(jetzt) is False
    # ein frisches Flag (Deploy NACH Prozess-Start) -> Neustart
    _os.utime(flag, (jetzt + 5, jetzt + 5))
    assert telegram_bot._neustart_angefordert(jetzt) is True


def test_deploy_beruehrt_das_neustart_flag():
    # Struktur-Gate: der Deploy fordert den Bot-Neustart automatisch an -- die Aera
    # "sudo systemctl restart" nach jedem Deploy ist vorbei.
    text = (ROOT / "deploy" / "pi_deploy.sh").read_text(encoding="utf-8")
    assert "telegram_bot.neustart" in text
