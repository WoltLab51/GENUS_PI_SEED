"""Der Antwort-Würfel (genus.antwort): die Zwicky-Symmetrie an der Membran — der
Verstehens-Würfel zerlegt, was reinkommt; dieser setzt zusammen, was rausgeht. Die Wahl
ist immer deterministisch; das Modell (Stimme) formuliert nur innerhalb der Zelle."""
import pytest

from genus import antwort, companion, persoenlichkeit, reactors, verstehen


# --- der isolierte Antwortvertrag: Claims -> Frame -> treuer Text -------------------------

def _frame(frage: str, intent: str = "definition", knappheit: str = "mittel"):
    return antwort.dialograhmen(
        frage,
        intent=intent,
        belegung={
            "waerme": "warm",
            "knappheit": knappheit,
            "beiwerk_notiz": True,
            "beiwerk_rueckfrage": True,
        },
    )


def test_answer_text_bleibt_ein_echter_string_und_traegt_seinen_draft():
    claim = antwort.Claim("Hund", "defined_as", "ein Haustier")
    draft = antwort.AnswerDraft(
        kind="definition",
        resolution="answered",
        focus=("Hund", "defined_as", "ein Haustier"),
        claims=(claim,),
        fallback_text="Unter »Hund« versteht GENUS: ein Haustier.",
        anchors=("Hund",),
    )
    text = antwort.AnswerText(draft.fallback_text, draft)
    assert isinstance(text, str)
    assert text == draft.fallback_text and "Haustier" in text
    assert " ".join([text, "Gut."]).endswith("Gut.")
    assert text.draft is draft


def test_definition_entwurf_traegt_claims_quellen_und_natuerlichen_fallback(conn):
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "ein Haustier", "dbnary")
    reactors.observe_relation(conn, "Q144", "is_a", "Q_haustier", "wikidata")
    reactors.observe_relation(conn, "Haustier@de", "expresses", "Q_haustier", "wikidata")

    material = companion.answer(conn, "Was ist ein Hund?")
    fallback = companion.narrate(material)
    draft = antwort.entwurf_definition(material, fallback, reading_source="model:deuter")

    bedeutung = next(c for c in draft.claims if c.predicate == "defined_as")
    eltern = [c for c in draft.claims if c.predicate == "is_a"]
    assert bedeutung.object == "ein Haustier"
    assert {e.source for e in bedeutung.evidence} == {"dbnary"}
    assert eltern and eltern[0].object == "Haustier"
    assert {e.source for e in eltern[0].evidence} == {"wikidata"}
    assert draft.reading_source == "model:deuter"

    text = antwort.rendere(draft, _frame("Was ist ein Hund?"))
    assert isinstance(text, antwort.AnswerText) and text.draft is draft
    assert text.startswith("»Hund« bedeutet hier: ein Haustier.")
    assert "zählt »Hund« zu »Haustier«" in text


def test_definition_renderer_zeigt_schwache_bedeutung_ohne_sie_aufzublasen():
    material = {
        "found": True,
        "word": "Quux",
        "meaning": ["ein kaum belegter Begriff"],
        "meaning_confidence": 0.2,
        "meaning_evidence": [{
            "subject": "Quux@de",
            "predicate": "primary_gloss",
            "object": "ein kaum belegter Begriff",
            "source": "model:bridge",
            "trust": 0.2,
        }],
        "is_a": [],
    }
    draft = antwort.entwurf_definition(
        material, "Unter »Quux« versteht GENUS: ein kaum belegter Begriff."
    )
    text = antwort.rendere(draft, _frame("Was ist Quux?"))
    assert "noch vorsichtig" in text and "schwach belegt" in text
    assert "model:bridge" not in text   # Quellenname erst bei ausdrücklicher Ausführlichkeit

    knapp = antwort.rendere(draft, _frame("Was ist Quux?", knappheit="knapp"))
    assert "schwach belegt" in knapp   # Knappheit darf Ehrlichkeit nie wegkürzen.


def test_definition_renderer_nutzt_dieselbe_bereinigte_sprechglosse_wie_narrate(conn):
    reactors.observe_relation(
        conn, "Ferien@de", "primary_gloss", "ohne Plural: arbeitsfreie Tage", "dbnary"
    )
    material = companion.answer(conn, "Was ist Ferien?")
    fallback = companion.narrate(material)
    draft = antwort.entwurf_definition(material, fallback)
    text = antwort.rendere(draft, _frame("Was ist Ferien?"))
    assert material["spoken_meaning"] == ["arbeitsfreie Tage"]
    assert "arbeitsfreie Tage" in text and "ohne Plural" not in text


def test_definition_renderer_begrenzt_standardantwort_auf_zwei_eltern():
    material = {
        "found": True,
        "word": "Hund",
        "meaning": ["ein Haustier"],
        "spoken_meaning": ["ein Haustier"],
        "is_a": ["Säugetier", "Tier", "Lebewesen", "Organismus"],
        "languages": ["dog", "chien"],
        "pos": ["noun"],
    }
    basis = companion.narrate(material)
    fallback = basis + " Ein bewahrter, graphgestützter Zusatz."
    draft = antwort.entwurf_definition(material, fallback)

    text = antwort.rendere(draft, _frame("Was ist ein Hund?"))

    for bestandteil in (
        "Substantiv", "ein Haustier", "Säugetier", "Tier",
        "Ein bewahrter, graphgestützter Zusatz.",
    ):
        assert bestandteil in text
    assert "Lebewesen" not in text and "Organismus" not in text
    assert "dog" not in text and "chien" not in text


def test_definition_renderer_faellt_zurueck_wenn_ein_claim_verloren_geht(monkeypatch):
    material = {
        "found": True,
        "word": "Hund",
        "meaning": ["ein Haustier"],
        "is_a": ["Säugetier"],
        "languages": ["dog"],
        "pos": ["noun"],
    }
    fallback = companion.narrate(material)
    draft = antwort.entwurf_definition(material, fallback)
    monkeypatch.setattr(
        antwort, "_rendere_definition", lambda d, f: "»Hund« bedeutet hier: ein Haustier.",
    )

    assert antwort.rendere(draft, _frame("Was ist ein Hund?")) == fallback


def test_beziehungs_entwurf_bewahrt_richtung_pfad_und_vertrauen(conn):
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Säugetier@de", "expresses", "Q7377", "wikidata")
    reactors.observe_relation(conn, "Q144", "is_a", "Q7377", "wikidata")
    result = companion.relate(conn, "Ist ein Hund ein Säugetier?")
    fallback = companion.narrate_relation(conn, result)
    draft = antwort.entwurf_beziehung(result, fallback)

    assert draft.verbatim_core == "»Hund« zählt zu »Säugetier«"
    assert draft.claims[0].confidence == result["trust"]
    assert {e.source for e in draft.claims[0].evidence} == {"wikidata"}
    text = antwort.rendere(draft, _frame("Ist ein Hund ein Säugetier?", "beziehung"))
    assert draft.verbatim_core in text
    assert f"{result['trust']:.2f}" not in text   # ab 0.5 bleibt die Routineantwort direkt


def test_schwache_beziehung_verschweigt_unsicherheit_und_vertrauenszahl_nie():
    result = {
        "relational": True,
        "verdict": "yes",
        "subject": "Hund",
        "object": "Säugetier",
        "trust": 0.2,
        "chain": [{
            "subject": "Q144",
            "predicate": "is_a",
            "object": "Q7377",
            "source": "model:bridge",
            "trust": 0.2,
        }],
    }
    fallback = "Ja. »Hund« zählt zu »Säugetier«. (Vertrauen 0.20.)"
    draft = antwort.entwurf_beziehung(result, fallback)

    text = antwort.rendere(draft, _frame("Ist ein Hund ein Säugetier?", "beziehung"))

    assert draft.verbatim_core in text
    assert "unsicher" in text and "schwach" in text
    assert "0.20" in text


def test_mehrstufige_beziehung_bewahrt_die_vollstaendige_herleitung(conn):
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q_hund", "wikidata")
    reactors.observe_relation(conn, "Säugetier@de", "expresses", "Q_saeuger", "wikidata")
    reactors.observe_relation(conn, "Tier@de", "expresses", "Q_tier", "wikidata")
    reactors.observe_relation(conn, "Q_hund", "is_a", "Q_saeuger", "wikidata")
    reactors.observe_relation(conn, "Q_saeuger", "is_a", "Q_tier", "wikidata")
    result = companion.relate(conn, "Ist ein Hund ein Tier?")
    fallback = companion.narrate_relation(conn, result, {"waerme": "warm"})
    draft = antwort.entwurf_beziehung(result, fallback)

    text = antwort.rendere(draft, _frame("Ist ein Hund ein Tier?", "beziehung"))

    assert text == fallback
    assert "Hund" in text and "Säugetier" in text and "Tier" in text


def test_no_path_ist_understood_unknown_und_nie_ein_negativer_claim():
    result = {
        "relational": True,
        "verdict": "no_path",
        "subject": "Rauch",
        "object": "Feuer",
    }
    fallback = ("Nach allem, was GENUS weiß, nicht: es findet keine is_a-Verbindung von "
                "»Rauch« zu »Feuer«. (Das heißt: unbekannt, nicht widerlegt.)")
    draft = antwort.entwurf_beziehung(result, fallback)
    assert draft.resolution == "understood_unknown" and draft.claims == ()
    text = antwort.rendere(draft, _frame("Zählt Rauch zu Feuer?", "beziehung"))
    assert "unbekannt, nicht widerlegt" in text
    assert text.index("Rauch") < text.index("Feuer")


def test_unknown_mit_claim_wird_vom_vertrag_abgelehnt():
    with pytest.raises(ValueError, match="keinen negativen Claim"):
        antwort.AnswerDraft(
            kind="beziehung",
            resolution="understood_unknown",
            focus=("Rauch", "is_a", "Feuer"),
            claims=(antwort.Claim("Rauch", "is_a", "Feuer"),),
            fallback_text="Unbekannt.",
        )


def test_renderer_faellt_bei_ankerbruch_auf_den_bewaehrten_text(monkeypatch):
    result = {
        "relational": True,
        "verdict": "yes",
        "subject": "Hund",
        "object": "Tier",
        "trust": 0.5,
        "chain": [{
            "subject": "Q144", "predicate": "is_a", "object": "Q_tier",
            "source": "wikidata",
        }],
    }
    fallback = "Ja. »Hund« zählt zu »Tier«."
    draft = antwort.entwurf_beziehung(result, fallback)
    monkeypatch.setattr(antwort, "_rendere_beziehung", lambda d, f: "Ja. Tier umfasst Hund.")
    text = antwort.rendere(draft, _frame("Ist ein Hund ein Tier?", "beziehung"))
    assert text == fallback and text.draft is draft


def test_dialograhmen_enthaelt_nur_entschiedene_registerdaten():
    frame = antwort.dialograhmen(
        "Und warum?",
        anchor_question="Ist ein Hund ein Tier?",
        intent="warum-herkunft",
        belegung={
            "waerme": "herzlich",
            "knappheit": "knapp",
            "beiwerk_notiz": False,
            "beiwerk_rueckfrage": False,
        },
        is_followup=True,
        previous_response_id=41,
    )
    assert frame.continues_anchor and frame.is_followup
    assert frame.waerme == "herzlich" and frame.knappheit == "knapp"
    assert not frame.allow_note and not frame.allow_followup
    assert frame.previous_response_id == 41
    assert not hasattr(frame, "last_answer")
    assert not hasattr(frame, "question") and not hasattr(frame, "anchor_question")


def test_pos_allein_ist_keine_beantwortete_definition():
    material = {
        "found": True,
        "word": "Quux",
        "meaning": [],
        "is_a": [],
        "languages": [],
        "pos": ["noun"],
    }
    fallback = "»Quux« (Substantiv) kennt GENUS, aber eine Bedeutung ist noch nicht erschlossen."

    draft = antwort.entwurf_definition(material, fallback)

    assert draft.resolution == "understood_unknown" and draft.claims == ()
    assert antwort.rendere(draft, _frame("Was ist Quux?")) == fallback


def test_segment_outcome_verliert_einen_unaufgeloesten_teil_nicht(conn):
    verstehen.seed_raster(conn)

    result = companion.respond_with_deuter(
        conn,
        "Hallo, ist Hund?",
        deuter=lambda q: [
            {"absicht": "gruss", "subject": None, "object": None},
            {"absicht": "beziehung", "subject": "Hund", "object": None},
        ],
        renderer=antwort.rendere,
    )

    assert "Hallo" in result["text"]
    assert result["outcome"] == "invalid_slots"

    nur_luecke = companion.respond_with_deuter(
        conn,
        "Ist Hund?",
        deuter=lambda q: {"absicht": "beziehung", "subject": "Hund", "object": None},
        renderer=antwort.rendere,
    )
    assert nur_luecke["outcome"] == "invalid_slots"
    assert nur_luecke["gelesen"] == ["beziehung"]


# --- die Belegung: Register + Kreuz-Konsistenz an EINER Stelle ---------------------------

def test_belegung_traegt_die_kreuz_konsistenz_knapp_kein_beiwerk(conn):
    bel = antwort.belegung(conn, "plausch")
    assert bel["beiwerk_notiz"] and bel["beiwerk_rueckfrage"]   # Saat: mittel + neugierig
    persoenlichkeit.stelle(conn, "knappheit", -1)   # mittel -> knapp
    bel = antwort.belegung(conn, "plausch")
    assert not bel["beiwerk_notiz"] and not bel["beiwerk_rueckfrage"]


def test_belegung_der_wache_ist_nuechtern_und_ohne_beiwerk_rueckfrage(conn):
    bel = antwort.belegung(conn, "wache")
    assert bel["waerme"] == "nuechtern" and bel["beiwerk_rueckfrage"] is False


# --- die Anweisung: deterministisch gewählt, ehrlich begrenzt ----------------------------

def test_anweisung_leitet_ton_und_straffung_aus_der_belegung_ab(conn):
    assert antwort.anweisung(antwort.belegung(conn, "plausch")) == "Ton: freundlich und warm."
    persoenlichkeit.stelle(conn, "waerme", -1)   # warm -> neutral
    persoenlichkeit.stelle(conn, "knappheit", -1)
    anw = antwort.anweisung(antwort.belegung(conn, "plausch"))
    assert anw == "Fasse dich so knapp wie möglich."   # neutral hat keinen Ton-Teil


def test_anweisung_ist_bei_neutraler_belegung_none():
    assert antwort.anweisung({"waerme": "neutral", "knappheit": "mittel"}) is None


def test_anweisung_verlangt_nie_ausfuehrlichkeit_die_stimme_fuegt_nie_hinzu(conn):
    # Ehrlichkeits-Pin: mehr Umfang muss aus der ZELLE kommen (mehr Inhalt), nie aus der
    # Stimme (die darf nur umformulieren) -- "ausführlich" erzeugt keine Anweisung.
    persoenlichkeit.stelle(conn, "knappheit", +1)   # mittel -> ausfuehrlich
    anw = antwort.anweisung(antwort.belegung(conn, "plausch")) or ""
    assert "ausführlich" not in anw and "länger" not in anw


# --- die Floskeln: eine Stelle für die Wärme-Varianten -----------------------------------

def test_floskel_gruss_folgt_waerme_und_beiwerk(conn):
    assert antwort.floskel(conn, "gruss") == (
        "Hallo! Schön, dass du da bist. Was beschäftigt dich gerade?")
    persoenlichkeit.stelle(conn, "knappheit", -1)   # knapp ⇒ keine Rückfrage (Beiwerk)
    assert "beschäftigt" not in antwort.floskel(conn, "gruss")


def test_floskel_dank_standard_bleibt_der_verankerte_wortlaut(conn):
    assert "Gern geschehen" in antwort.floskel(conn, "dank")


# --- die Stimme bekommt die Anweisung als Daten ------------------------------------------

def test_stimme_erhaelt_die_anweisung_des_wuerfels(conn):
    empfangen = {}

    def stimme(text, anweisung=None):
        empfangen["anweisung"] = anweisung
        return text.replace("zählt zu", "gehört zu")

    text = companion._stimme_versucht(conn, "»Hund« zählt zu »Säugetier«.", stimme)
    assert empfangen["anweisung"] == "Ton: freundlich und warm."
    assert "gehört zu" in text and companion._STIMME_TAG in text


def test_eine_stimme_ohne_anweisungs_parameter_bleibt_kompatibel(conn):
    # ältere Membran / Test-Fakes mit (text)-Signatur: der Aufruf fällt auf die alte Form
    aufrufe = []

    def alte_stimme(text):
        aufrufe.append(text)
        return None   # Anker-Prüfung „gescheitert" -> Original bleibt

    text = companion._stimme_versucht(conn, "»Hund« zählt zu »Säugetier«.", alte_stimme)
    assert text == "»Hund« zählt zu »Säugetier«."
    assert aufrufe == ["»Hund« zählt zu »Säugetier«."]


def test_deploy_stimme_traegt_die_anweisung_in_den_system_prompt():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy"))
    import stimme as stimme_modul

    class FakeModel:
        def __init__(self):
            self.system = None

        def create_chat_completion(self, messages, max_tokens=None, temperature=None):
            self.system = messages[0]["content"]
            return {"choices": [{"message": {"content": "Ein »Hund« gehört zu »Säugetier«."}}]}

    fake = FakeModel()
    ergebnis = stimme_modul.formuliere("»Hund« zählt zu »Säugetier«.", model=fake,
                                       anweisung="Ton: freundlich und warm.")
    assert "Ton: freundlich und warm." in fake.system
    assert ergebnis == "Ein »Hund« gehört zu »Säugetier«."
    # die Anker-Leine ist von der Anweisung unabhängig: fehlender Anker -> None
    fake2 = FakeModel()
    fake2.create_chat_completion = lambda messages, max_tokens=None, temperature=None: {
        "choices": [{"message": {"content": "Ein Hund gehört zu Tieren."}}]}
    assert stimme_modul.formuliere("»Hund« zählt zu »Säugetier«.", model=fake2,
                                   anweisung="Ton: herzlich und zugewandt.") is None


def _stimme_modul():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy"))
    import stimme as stimme_modul
    return stimme_modul


def _fake_stimme(rueckgabe):
    class FakeModel:
        def create_chat_completion(self, messages, max_tokens=None, temperature=None):
            return {"choices": [{"message": {"content": rueckgabe}}]}
    return FakeModel()


def test_formuliere_verwirft_eine_richtungsumkehr_und_haelt_gleiche_reihenfolge():
    # Antwort-Seele Scheibe 2: der reihenfolge-bewusste Anker. Eine Umformulierung, die die
    # zitierten Begriffe VERTAUSCHT (Richtung gekippt), wird verworfen (None -> Aufrufer nimmt
    # den Voice-1-Satz); eine, die die Reihenfolge WAHRT, darf durch.
    sm = _stimme_modul()
    satz = "Ja, klar — »Hund« zählt zu »Haustier«. Da bin ich mir ziemlich sicher (0.85)."
    # Umkehr: »Haustier« steht jetzt vor »Hund« -- alle Anker VORHANDEN, aber Reihenfolge gebrochen
    umkehr = "»Haustier« umfasst »Hund«, da bin ich ziemlich sicher (0.85)."
    assert sm.formuliere(satz, model=_fake_stimme(umkehr)) is None
    # gleiche Reihenfolge, natürlicher formuliert -> akzeptiert
    natuerlich = "Ja klar, ein »Hund« ist ein »Haustier« — da bin ich ziemlich sicher (0.85)."
    assert sm.formuliere(satz, model=_fake_stimme(natuerlich)) == natuerlich


def test_reihenfolge_haelt_ist_die_leine_gegen_umkehr():
    sm = _stimme_modul()
    assert sm._reihenfolge_haelt("erst »A« dann »B«", ["A", "B"]) is True
    assert sm._reihenfolge_haelt("erst »B« dann »A«", ["A", "B"]) is False
    assert sm._reihenfolge_haelt("nur »A« da", ["A", "B"]) is False   # fehlt ganz


def test_formuliere_haelt_die_verbatim_insel_gegen_verb_umkehr():
    # Antwort-Seele Scheibe 2 (Approach A): der gerichtete Kern-Satz ist eine VERBATIM-INSEL.
    # Der Reihenfolge-Anker allein liesse eine Verb-Umkehr bei GLEICHER Wortstellung durch
    # („»Hund« umfasst »Haustier«"); die Insel faengt sie, weil der Kern nicht mehr woertlich
    # dasteht -> None -> Voice-1-Fallback. Bleibt der Kern woertlich, darf der Rahmen frei sein.
    sm = _stimme_modul()
    satz = "Ja, klar — »Hund« zählt zu »Haustier«. Da bin ich mir ziemlich sicher (0.85)."
    kern = "»Hund« zählt zu »Haustier«"
    gekippt = "Also »Hund« umfasst »Haustier«, da bin ich ziemlich sicher (0.85)."
    assert sm.formuliere(satz, model=_fake_stimme(gekippt), kern=kern) is None
    frei_gerahmt = "Na klar: »Hund« zählt zu »Haustier«. Da bin ich ziemlich sicher (0.85)!"
    assert sm.formuliere(satz, model=_fake_stimme(frei_gerahmt), kern=kern) == frei_gerahmt


def test_stimme_substantiv_leine_faengt_den_hausvoegel_fund():
    # live gefunden beim ERSTEN Anweisungs-Test auf dem Pi: das 1.5B machte unter
    # "Ton: freundlich und warm." aus "Haustier" ein "Hausvögel" -- die Anker-Prüfung
    # (nur zitierte Wörter + Zahlen) ließ es durch, weil "Hund" im Text überlebte.
    # Deutsche Großschreibung = Substantive = die tragende zweite Leine.
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy"))
    import stimme as stimme_modul

    satz = "Unter »Hund« versteht GENUS: Haustier, dessen Vorfahre der Wolf ist."

    def fake(inhalt):
        class M:
            def create_chat_completion(self, messages, max_tokens=None, temperature=None):
                return {"choices": [{"message": {"content": inhalt}}]}
        return M()

    kaputt = "Hausvögel, die Vorfahre aus Wolfgruppen stammen, sind die Vorfahren von Hund."
    assert stimme_modul.formuliere(satz, model=fake(kaputt),
                                   anweisung="Ton: freundlich und warm.") is None
    gut = "Ein Haustier, dessen Vorfahre der Wolf ist, ist ein Hund."
    assert stimme_modul.formuliere(satz, model=fake(gut)) == gut
    # Satzanfänge ("Unter") und Versalien ("GENUS") zählen bewusst nicht als Substantiv-Anker
    worte = stimme_modul._inhaltsworte(satz)
    assert "Unter" not in worte and "GENUS" not in worte
    assert worte == ["Hund", "Haustier", "Vorfahre", "Wolf"]


def test_stimme_wortidentische_rueckgabe_ist_keine_glaettung():
    # live gesehen: das Modell gibt manchmal exakt den Eingabesatz zurück -- das darf
    # nie den "geglättet"-Tag tragen (nichts wurde geglättet), also ehrlich None
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy"))
    import stimme as stimme_modul

    satz = "Unter »Hund« versteht GENUS: Haustier, dessen Vorfahre der Wolf ist."

    class M:
        def create_chat_completion(self, messages, max_tokens=None, temperature=None):
            return {"choices": [{"message": {"content": satz}}]}

    assert stimme_modul.formuliere(satz, model=M()) is None


# --- Vokabel-bei-Begegnung: der Kern spürt das unbekannte Wort (rein lesend) -------------

def test_unbekannte_woerter_meldet_ein_wort_das_genus_nicht_kennt(conn):
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "ein Haustier", "dbnary")
    # „Fernweh" kennt GENUS nicht, „Hund" schon
    woerter = companion.unbekannte_woerter(conn, "Was hat ein Hund mit Fernweh zu tun?")
    assert woerter == ["Fernweh"]


def test_unbekannte_woerter_filtert_funktionswoerter_am_satzanfang(conn):
    # „Was/Wie/Der" am Satzanfang sind keine Vokabeln -- die Membran-Quelle nicht behelligen
    assert companion.unbekannte_woerter(conn, "Was ist das?") == []
    assert companion.unbekannte_woerter(conn, "Wie geht es dir?") == []


def test_unbekannte_woerter_faengt_ein_substantiv_am_satzanfang(conn):
    # ein echtes Substantiv am Satzanfang bleibt lernenswert (kein Funktionswort)
    assert companion.unbekannte_woerter(conn, "Fernweh überkommt mich.") == ["Fernweh"]


def test_unbekannte_woerter_dedupliziert_reihenerhaltend(conn):
    woerter = companion.unbekannte_woerter(conn, "Zugvogel, ach der Zugvogel und der Wanderfalke!")
    assert woerter == ["Zugvogel", "Wanderfalke"]


def test_unbekannte_woerter_meldet_bekanntes_nie(conn):
    reactors.observe_relation(conn, "Apfel@de", "expresses", "Q_apfel", "wikidata")
    reactors.observe_relation(conn, "Apfel@de", "primary_gloss", "eine Frucht", "dbnary")
    assert companion.unbekannte_woerter(conn, "Der Apfel ist reif.") == []


# --- die Vertiefungs-Komposition: Länge aus Inhalt, nie aus Worten -----------------------

def _reiches_wissen(conn):
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss",
                              "Haustier, dessen Vorfahre der Wolf ist", "dbnary")
    reactors.observe_relation(conn, "Q144", "is_a", "Q_haustier", "wikidata")
    reactors.observe_relation(conn, "Haustier@de", "expresses", "Q_haustier", "wikidata")
    reactors.observe_relation(conn, "Q_katze", "is_a", "Q_haustier", "wikidata")
    reactors.observe_relation(conn, "Katze@de", "expresses", "Q_katze", "wikidata")
    reactors.observe_relation(conn, "Q_haustier", "is_a", "Q_tier", "wikidata")
    reactors.observe_relation(conn, "Tier@de", "expresses", "Q_tier", "wikidata")


def test_ausfuehrlich_zieht_mehr_material_aus_dem_graphen(conn):
    _reiches_wissen(conn)
    persoenlichkeit.stelle(conn, "knappheit", +1)   # mittel -> ausfuehrlich
    text = companion.respond(conn, "Was ist ein Hund?")
    assert "Unter »Haustier« kenne ich außerdem: »Katze«." in text
    assert "»Haustier« zählt wiederum zu »Tier«." in text
    assert "Meine Quellen zu »Hund«: dbnary, wikidata." in text


def test_ausfuehrlich_nennt_eine_zweite_bedeutung_wenn_es_eine_gibt(conn):
    # die Mehr-Sinn-Fülle (Hund = Haustier UND Feuerbock UND Förderwagen) wird bei
    # „ausführlich" sichtbar -- der Kern-Satz trägt die eine, die Vertiefung die andere
    _reiches_wissen(conn)
    reactors.observe_relation(conn, "Hund@de", "primary_gloss",
                              "Feuerbock am offenen Kamin", "dbnary")
    persoenlichkeit.stelle(conn, "knappheit", +1)
    text = companion.respond(conn, "Was ist ein Hund?")
    assert "weitere Bedeutung" in text
    assert "Feuerbock" in text and "Haustier, dessen Vorfahre" in text


def test_mittel_und_knapp_bleiben_bei_der_heutigen_antwort(conn):
    _reiches_wissen(conn)
    mittel = companion.respond(conn, "Was ist ein Hund?")
    assert "Katze" not in mittel and "Meine Quellen" not in mittel
    persoenlichkeit.stelle(conn, "knappheit", -1)
    knapp = companion.respond(conn, "Was ist ein Hund?")
    assert "Katze" not in knapp and "Meine Quellen" not in knapp


def test_vertiefung_ohne_material_bleibt_ehrlich_leer(conn):
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "ein Haustier", "wikidata")
    a = companion.answer(conn, "Was ist ein Hund?")
    assert companion.vertiefung(conn, a) == []   # eine Quelle, keine Eltern: nichts erfunden


def test_vertiefung_nennt_nie_einen_kryptischen_knoten(conn):
    # ein Elternteil ohne menschlichen Namen (blanker Q-Knoten) bleibt draußen
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Q144", "label", "Hund@de", "wikidata")
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "ein Haustier", "dbnary")
    reactors.observe_relation(conn, "Q144", "is_a", "Q999999", "wikidata")
    a = companion.answer(conn, "Was ist ein Hund?")
    assert all("Q999999" not in satz for satz in companion.vertiefung(conn, a))


def test_vertiefung_zeigt_die_dynamische_schicht(conn):
    # die neue verbindende Schicht (Methoden-Landkarte 2026-07-05): Teil-Ganzes/Kausal/Zweck
    reactors.observe_relation(conn, "Fahrrad@de", "expresses", "Q_fahrrad", "wikidata")
    reactors.observe_relation(conn, "Fahrrad@de", "primary_gloss", "ein Zweirad", "dbnary")
    reactors.observe_relation(conn, "Q_fahrrad", "has_part", "Q_rad", "wikidata")
    reactors.observe_relation(conn, "Rad@de", "expresses", "Q_rad", "wikidata")
    reactors.observe_relation(conn, "Q_fahrrad", "used_for", "Q_fortbewegung", "wikidata")
    reactors.observe_relation(conn, "Fortbewegung@de", "expresses", "Q_fortbewegung", "wikidata")
    reactors.observe_relation(conn, "Q_fahrrad", "made_of", "Q_metall", "wikidata")
    reactors.observe_relation(conn, "Metall@de", "expresses", "Q_metall", "wikidata")
    saetze = companion.vertiefung(conn, companion.answer(conn, "Was ist ein Fahrrad?"))
    text = " ".join(saetze)
    assert "Zu »Fahrrad« gehören: »Rad«." in text
    assert "»Fahrrad« wird verwendet für »Fortbewegung«." in text
    assert "»Fahrrad« besteht aus »Metall«." in text


def test_dynamische_schicht_nennt_nie_einen_kryptischen_knoten(conn):
    reactors.observe_relation(conn, "Fahrrad@de", "expresses", "Q_fahrrad", "wikidata")
    reactors.observe_relation(conn, "Fahrrad@de", "primary_gloss", "ein Zweirad", "dbnary")
    reactors.observe_relation(conn, "Q_fahrrad", "causes", "Q999999", "wikidata")  # kein Label
    saetze = companion.vertiefung(conn, companion.answer(conn, "Was ist ein Fahrrad?"))
    assert not any("Q999999" in s for s in saetze)
    assert not any("verursacht" in s for s in saetze)   # kein benanntes Ziel -> kein Satz


def test_dynamische_schicht_nur_bei_ausfuehrlich(conn):
    reactors.observe_relation(conn, "Fahrrad@de", "expresses", "Q_fahrrad", "wikidata")
    reactors.observe_relation(conn, "Fahrrad@de", "primary_gloss", "ein Zweirad", "dbnary")
    reactors.observe_relation(conn, "Q_fahrrad", "has_part", "Q_rad", "wikidata")
    reactors.observe_relation(conn, "Rad@de", "expresses", "Q_rad", "wikidata")
    mittel = companion.respond(conn, "Was ist ein Fahrrad?")
    assert "gehören" not in mittel   # dynamische Schicht steckt in der Vertiefung (ausführlich)


def test_vertiefung_setzt_jeden_benannten_begriff_in_anker_guillemets(conn):
    _reiches_wissen(conn)
    a = companion.answer(conn, "Was ist ein Hund?")
    saetze = companion.vertiefung(conn, a)
    # jeder strukturell benannte Begriff (Geschwister, Leiter) ist ein Stimme-Anker
    assert any("»Katze«" in s for s in saetze)
    assert any("»Tier«" in s for s in saetze)
    assert not any("Katze" in s and "»Katze«" not in s for s in saetze)


# --- das konkrete BEISPIEL (instance_of, Antwort-Komposition 2026-07-07) -----------------

def test_vertiefung_nennt_ein_konkretes_beispiel(conn):
    # die stärkste noch fehlende Substanz-Zutat: ein benanntes Beispiel, rückwärts aus einer
    # echten instance_of-Kante gelesen (X instance_of Vulkan) -- macht die Definition greifbar
    reactors.observe_relation(conn, "Vulkan@de", "expresses", "Q_vulkan", "wikidata")
    reactors.observe_relation(conn, "Vulkan@de", "primary_gloss",
                              "eine Öffnung in der Erdkruste", "dbnary")
    reactors.observe_relation(conn, "Q_vesuv", "instance_of", "Q_vulkan", "wikidata")
    reactors.observe_relation(conn, "Vesuv@de", "expresses", "Q_vesuv", "wikidata")
    saetze = companion.vertiefung(conn, companion.answer(conn, "Was ist ein Vulkan?"))
    assert "Ein Beispiel dafür ist »Vesuv«." in saetze


def test_beispiel_wird_nie_erfunden(conn):
    # ohne instance_of-Kante kein Beispiel; eine unbenannte Instanz bleibt stumm (kein Q-Knoten)
    reactors.observe_relation(conn, "Fluss@de", "expresses", "Q_fluss", "wikidata")
    reactors.observe_relation(conn, "Fluss@de", "primary_gloss", "ein Gewässer", "dbnary")
    ohne = companion.vertiefung(conn, companion.answer(conn, "Was ist ein Fluss?"))
    assert not any("Beispiel" in s for s in ohne)
    reactors.observe_relation(conn, "Q999777", "instance_of", "Q_fluss", "wikidata")  # kein Label
    stumm = companion.vertiefung(conn, companion.answer(conn, "Was ist ein Fluss?"))
    assert not any("Beispiel" in s or "Q999777" in s for s in stumm)


def test_instance_of_macht_die_instanz_nicht_zum_unterbegriff(conn):
    # SICHERHEIT: instance_of ist NICHT is_a. „Ist ein Vesuv ein Berg?" darf NICHT ja ergeben,
    # obwohl Vesuv instance_of Vulkan und Vulkan is_a Berg -- die Instanz ist kein Unterbegriff,
    # instance_of läuft nie in die is_a-Inferenz.
    for w, q in (("Vesuv", "Q_vesuv"), ("Vulkan", "Q_vulkan"), ("Berg", "Q_berg")):
        reactors.observe_relation(conn, f"{w}@de", "expresses", q, "wikidata")
    reactors.observe_relation(conn, "Q_vesuv", "instance_of", "Q_vulkan", "wikidata")
    reactors.observe_relation(conn, "Q_vulkan", "is_a", "Q_berg", "wikidata")
    r = companion._relate_terms(conn, "Vesuv", "Berg")
    assert r["relational"] and r["verdict"] == "no_path"   # kein is_a-Weg über instance_of


# --- die ANTIZIPATION: das proaktive Anschluss-Angebot (2026-07-08) ----------------------

def _saee_vulkan(conn, ausbruch_beantwortbar: bool):
    """Vulkan (ein beantwortbares Konzept) verursacht einen Ausbruch (benannt); der Ausbruch
    ist NUR dann selbst erklärbar, wenn ``ausbruch_beantwortbar`` -- das prüft die Treue-Leine."""
    reactors.observe_relation(conn, "Vulkan@de", "expresses", "Q_vulkan", "wikidata")
    reactors.observe_relation(conn, "Vulkan@de", "primary_gloss",
                              "eine Öffnung in der Erdkruste", "dbnary")
    reactors.observe_relation(conn, "Q_vulkan", "causes", "Q_ausbruch", "wikidata")
    reactors.observe_relation(conn, "Ausbruch@de", "expresses", "Q_ausbruch", "wikidata")
    if ausbruch_beantwortbar:
        reactors.observe_relation(conn, "Ausbruch@de", "primary_gloss",
                                  "eine Entladung von Magma", "dbnary")


def test_antizipation_bietet_die_verifizierte_anschlussfrage(conn):
    # nach einer Konzept-Antwort EIN graph-verifiziertes Angebot; die Anschlussfrage wandert
    # als result["anschluss"] mit (der Aufrufer fädelt sie für das nächste „ja")
    _saee_vulkan(conn, ausbruch_beantwortbar=True)
    result = companion.respond_with_deuter(conn, "Was ist ein Vulkan?", deuter=lambda q: None)
    assert "Wenn du magst, erkläre ich dir noch, was »Ausbruch« ist." in result["text"]
    assert result["anschluss"] == "Was ist Ausbruch?"


def test_antizipation_bietet_nichts_unbeantwortbares(conn):
    # TREUE vor Freundlichkeit: der Ausbruch ist benannt, aber GENUS kann ihn nicht erklären
    # (keine Bedeutung, kein is_a) -> kein Angebot, das ins Leere liefe
    _saee_vulkan(conn, ausbruch_beantwortbar=False)
    result = companion.respond_with_deuter(conn, "Was ist ein Vulkan?", deuter=lambda q: None)
    assert "Wenn du magst" not in result["text"] and result.get("anschluss") is None


def test_antizipation_ja_loest_genau_das_angebot_ein(conn):
    # ein knappes „ja" im nächsten Zug beantwortet die verifizierte Anschlussfrage -- VOR jeder
    # Deutung (nie durch den Klassifikator), und ohne eine neue Angebots-Kette zu öffnen
    _saee_vulkan(conn, ausbruch_beantwortbar=True)
    result = companion.respond_with_deuter(conn, "ja", deuter=lambda q: None,
                                           letzter_anschluss="Was ist Ausbruch?")
    assert "Ausbruch" in result["text"] and "Entladung von Magma" in result["text"]
    assert result["question"] == "Was ist Ausbruch?"
    assert result.get("anschluss") is None   # ein Blick, kein Sog: keine Kette


def test_antizipation_echte_frage_ist_kein_ja(conn):
    # eine echte neue Frage darf NIE als Zustimmung durchgehen, auch wenn ein Angebot aussteht
    _saee_vulkan(conn, ausbruch_beantwortbar=True)
    assert not companion._ist_zustimmung("Was ist ein Berg?")
    assert companion._ist_zustimmung("ja") and companion._ist_zustimmung("Gerne!")


def test_antizipation_schweigt_bei_knappheit(conn):
    # Kreuz-Konsistenz (Rollen-Pin/Regler): knapp ⇒ kein Beiwerk, obwohl das Material da wäre
    _saee_vulkan(conn, ausbruch_beantwortbar=True)
    persoenlichkeit.stelle(conn, "knappheit", -1)   # mittel -> knapp
    result = companion.respond_with_deuter(conn, "Was ist ein Vulkan?", deuter=lambda q: None)
    assert "Wenn du magst" not in result["text"] and result.get("anschluss") is None


def test_antizipation_nur_auf_dem_gespraechspfad(conn):
    # ohne Deuter (CLI-Stimme, nüchtern) kein Angebot -- die Antizipation ist eine Gesprächs-Geste
    _saee_vulkan(conn, ausbruch_beantwortbar=True)
    result = companion.respond_with_deuter(conn, "Was ist ein Vulkan?")
    assert "Wenn du magst" not in result["text"] and result.get("anschluss") is None


def test_antizipation_verifiziert_gegen_das_gemeinte_konzept(conn):
    # Review-Fund: die Frage muss sich GENAU aufs Kanten-Ziel-Konzept zurückführen. Löst das
    # nachgeparste Label auf ein ANDERES Konzept auf (Mehrwort-Zerfall / Homonym), gibt es kein
    # Angebot -- sonst beantwortete das spätere „ja" ein anderes Konzept als angeboten.
    reactors.observe_relation(conn, "Ausbruch@de", "expresses", "Q_ausbruch", "wikidata")
    reactors.observe_relation(conn, "Ausbruch@de", "primary_gloss", "eine Entladung", "dbnary")
    assert companion._erklaerbar_und_eindeutig(conn, "Was ist Ausbruch?", "Q_ausbruch")
    assert not companion._erklaerbar_und_eindeutig(conn, "Was ist Ausbruch?", "Q_ein_anderes")


def test_antizipation_bietet_nichts_mit_nur_blankem_elternknoten(conn):
    # Review-Fund (Treue): is_a existiert, aber der einzige Elternteil ist ein blanker Q-Knoten,
    # den narrate() gar nicht ausspricht -> die Leine muss das als „nicht erklärbar" werten (sonst
    # liefe das Angebot in „eine Bedeutung ist noch nicht erschlossen")
    reactors.observe_relation(conn, "Vulkan@de", "expresses", "Q_vulkan", "wikidata")
    reactors.observe_relation(conn, "Vulkan@de", "primary_gloss", "eine Öffnung", "dbnary")
    reactors.observe_relation(conn, "Q_vulkan", "causes", "Q_ausbruch", "wikidata")
    reactors.observe_relation(conn, "Ausbruch@de", "expresses", "Q_ausbruch", "wikidata")
    reactors.observe_relation(conn, "Q_ausbruch", "is_a", "Q999999", "wikidata")  # blank, kein Label
    result = companion.respond_with_deuter(conn, "Was ist ein Vulkan?", deuter=lambda q: None)
    assert "Wenn du magst" not in result["text"] and result.get("anschluss") is None


def test_antizipation_bietet_nichts_mit_nur_benannten_eltern(conn):
    # Live-Fund Haus -> Madschlis: ein Name plus Oberklassen ist noch keine erklärbare Bedeutung.
    reactors.observe_relation(conn, "Haus@de", "expresses", "Q_haus", "wikidata")
    reactors.observe_relation(conn, "Haus@de", "primary_gloss", "ein Gebäude", "dbnary")
    reactors.observe_relation(conn, "Q_haus", "causes", "Q_madschlis", "wikidata")
    reactors.observe_relation(conn, "Madschlis@de", "expresses", "Q_madschlis", "wikidata")
    reactors.observe_relation(conn, "Q_madschlis", "is_a", "Q_gremium", "wikidata")
    reactors.observe_relation(conn, "Gremium@de", "label", "Q_gremium", "wikidata")

    result = companion.respond_with_deuter(conn, "Was ist ein Haus?", deuter=lambda _q: None)

    assert "Madschlis" not in result["text"] and result.get("anschluss") is None


# --- die umgezogenen Verbraucher bleiben verhaltensgleich --------------------------------

def test_gruss_und_dank_lesen_jetzt_aus_dem_wuerfel(conn):
    gruss = companion._zelle_gruss(conn, {"text": "Hallo"}, "Hallo", None, None)
    assert gruss == antwort.floskel(conn, "gruss")
    dank = companion._zelle_dank(conn, {"text": "Danke"}, "Danke", None, None)
    assert dank == antwort.floskel(conn, "dank")


def test_notiz_beiwerk_folgt_der_wuerfel_belegung(conn):
    from genus import erinnerung
    reactors.observe_relation(conn, "Fahrrad@de", "expresses", "Q_fahrrad", "wikidata")
    erinnerung.merke(conn, "mein Fahrrad hat einen Platten", quelle="ronny")
    assert companion._notiz_bezug(conn, "Was ist ein Fahrrad?") is not None
    persoenlichkeit.stelle(conn, "knappheit", -1)
    assert companion._notiz_bezug(conn, "Was ist ein Fahrrad?") is None
