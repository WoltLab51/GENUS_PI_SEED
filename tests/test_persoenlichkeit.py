"""Die Persönlichkeits-Schicht (Ronnys Design 2026-07-04): WESEN fix im Code, ART als
Wissen im Graphen (träge, per Chat stellbar), REGISTER situativ pro Rolle. Die eiserne
Leitplanke: Persönlichkeit ist eine Eigenschaft der SPRACHE, nie des WISSENS."""
import pytest

from genus import companion, erinnerung, persoenlichkeit, reactors, sources


# --- ART: Saat, Lesen, Stellen ----------------------------------------------------------

def test_art_faellt_ohne_saat_auf_den_grundton(conn):
    assert persoenlichkeit.art(conn) == persoenlichkeit.ART_SEED


def test_saet_art_ist_idempotent(conn):
    assert persoenlichkeit.saet_art(conn) == len(persoenlichkeit.MERKMALE)
    assert persoenlichkeit.saet_art(conn) == 0


def test_saet_art_ueberschreibt_nie_eine_gestellte_einstellung(conn):
    # Re-Deploy-Sicherheit: „sei knapper" überlebt jede neue Saat
    persoenlichkeit.stelle(conn, "knappheit", -1)   # mittel -> knapp
    persoenlichkeit.saet_art(conn)
    assert persoenlichkeit.art(conn)["knappheit"] == "knapp"


def test_stelle_bewegt_genau_eine_stufe_und_traegt_die_nutzer_quelle(conn):
    res = persoenlichkeit.stelle(conn, "waerme", +1)   # warm -> herzlich
    assert res == {"gestellt": True, "merkmal": "waerme", "wert": "herzlich"}
    rows = sources.relations(conn, subject="art:ronny", predicate="waerme")
    assert len(rows) == 1   # die alte Kante ist zurückgenommen, nicht gestapelt
    assert rows[0]["object"] == "herzlich" and rows[0]["source"] == "ronny"


def test_stelle_ist_an_der_grenze_ehrlich(conn):
    persoenlichkeit.stelle(conn, "waerme", +1)          # warm -> herzlich
    res = persoenlichkeit.stelle(conn, "waerme", +1)    # herzlich ist das Ende
    assert res["gestellt"] is False and res["wert"] == "herzlich"


def test_stelle_weist_ein_unbekanntes_merkmal_ab(conn):
    res = persoenlichkeit.stelle(conn, "lautstaerke", +1)
    assert res["gestellt"] is False


# --- REGISTER: Rollen-Pins leben im Code (Wesens-Schutz) --------------------------------

def test_wache_pinnt_nuechtern_egal_was_gestellt_ist(conn):
    persoenlichkeit.stelle(conn, "waerme", +1)   # herzlich
    reg = persoenlichkeit.register(conn, "wache")
    assert reg["waerme"] == "nuechtern" and reg["humor"] == "aus" and reg["neugier"] == "aus"


def test_werkzeug_pinnt_knapp_und_witzlos(conn):
    persoenlichkeit.stelle(conn, "knappheit", +1)   # ausfuehrlich
    reg = persoenlichkeit.register(conn, "werkzeug")
    assert reg["knappheit"] == "knapp" and reg["humor"] == "aus"


def test_morgen_hebt_die_waerme_um_eine_stufe_und_bleibt_am_rand_stehen(conn):
    assert persoenlichkeit.register(conn, "morgen")["waerme"] == "herzlich"   # warm +1
    persoenlichkeit.stelle(conn, "waerme", +1)   # schon herzlich
    assert persoenlichkeit.register(conn, "morgen")["waerme"] == "herzlich"


# --- der Chat-Regler (Ritual, exakte Kommandos) -----------------------------------------

def test_regler_kommando_stellt_und_bestaetigt_nativ(conn):
    text = companion._ritual_antwort(conn, "sei knapper")
    assert "Knappheit" in text and "„knapp“" in text and "Quelle: du" in text
    assert persoenlichkeit.art(conn)["knappheit"] == "knapp"


def test_regler_ist_satzzeichen_tolerant(conn):
    text = companion._ritual_antwort(conn, "Sei wärmer!")
    assert "Wärme" in text and persoenlichkeit.art(conn)["waerme"] == "herzlich"


def test_regler_ist_an_der_grenze_ehrlich(conn):
    text = companion._ritual_antwort(conn, "weniger humor")   # steht schon auf aus
    assert "steht schon" in text and "weiter geht es" in text


def test_regler_laeuft_vor_dem_deuter_eine_klare_anweisung_braucht_keine_deutung(conn):
    def deuter(q):
        raise AssertionError("der Deuter darf ein Regler-Kommando nie sehen")
    result = companion.respond_with_deuter(conn, "sei nüchterner", deuter=deuter)
    assert "Wärme" in result["text"]
    assert persoenlichkeit.art(conn)["waerme"] == "neutral"


def test_eine_gewoehnliche_frage_ist_kein_regler_kommando(conn):
    assert companion._regler_antwort(conn, "Was ist ein Hund?") is None


# --- die Verbraucher: Persönlichkeit wirkt an der Sprache -------------------------------

def _stufe_runter(conn, merkmal, male):
    for _ in range(male):
        persoenlichkeit.stelle(conn, merkmal, -1)


def test_gruss_variiert_mit_der_waerme_und_fragt_bei_neugier(conn):
    guess = {"text": "Hallo"}
    warm = companion._zelle_gruss(conn, guess, "Hallo", None, None)
    assert "Schön, dass du da bist" in warm and "Was beschäftigt dich gerade?" in warm
    _stufe_runter(conn, "waerme", 2)   # warm -> nuechtern
    persoenlichkeit.stelle(conn, "neugier", -1)
    nuechtern = companion._zelle_gruss(conn, guess, "Hallo", None, None)
    assert nuechtern.startswith("Hallo.") and "beschäftigt" not in nuechtern


def test_dank_behaelt_am_standard_den_verankerten_wortlaut(conn):
    text = companion._zelle_dank(conn, {"text": "Danke"}, "Danke", None, None)
    assert "Gern geschehen" in text


def test_knapp_unterdrueckt_die_beilaeufige_notiz_einwebung(conn):
    reactors.observe_relation(conn, "Fahrrad@de", "expresses", "Q_fahrrad", "wikidata")
    erinnerung.merke(conn, "mein Fahrrad hat einen Platten", quelle="ronny")
    assert companion._notiz_bezug(conn, "Was ist ein Fahrrad?") is not None
    persoenlichkeit.stelle(conn, "knappheit", -1)   # mittel -> knapp
    assert companion._notiz_bezug(conn, "Was ist ein Fahrrad?") is None


def test_morgen_nachricht_wird_bei_humor_dezent_leicht(conn):
    from genus import konsolidierung
    persoenlichkeit.stelle(conn, "humor", +1)   # aus -> dezent
    text = konsolidierung.morgen_nachricht(conn, None)
    assert "einer muss es ja tun" in text


def test_morgen_nachricht_fragt_bei_neugier_nach_den_themen(conn):
    from genus import konsolidierung
    bericht = {"themen": [{"konzept": "Q1", "label": "Hund", "anzahl": 3}],
               "warum_folgen": 0, "episoden": [], "zuege": 5}
    text = konsolidierung.morgen_nachricht(conn, bericht)
    assert "Magst du mir heute mehr davon erzählen?" in text


# --- der Umbau: der Regler ist eine Raster-Zelle (Charta: keine zweite Wahrheit) --------

def test_einstellung_ist_ein_blatt_im_raster_unter_aufforderung_genus(conn):
    from genus import verstehen
    verstehen.seed_raster(conn)
    eltern = [r["object"] for r in sources.relations(
        conn, subject="absicht:einstellung", predicate="is_a")]
    assert eltern == ["zelle:aufforderung-genus"]


def test_regler_deute_liest_achse_und_richtung_aus_freier_formulierung():
    assert companion._regler_deute("könntest du dich generell etwas kürzer fassen?") == ("knappheit", -1)
    assert companion._regler_deute("etwas mehr Humor bitte") == ("humor", +1)
    assert companion._regler_deute("bitte weniger humor") == ("humor", -1)
    assert companion._regler_deute("antworte ruhig etwas herzlicher") == ("waerme", +1)
    assert companion._regler_deute("bleib sachlicher") == ("waerme", -1)


def test_regler_deute_faellt_bei_mehrdeutigem_oder_leerem_ehrlich_durch():
    assert companion._regler_deute("sei wärmer und knapper") is None   # zwei Achsen -> nie raten
    assert companion._regler_deute("stell dich anders ein") is None


def test_einstellungs_zelle_stellt_ueber_den_deuter_pfad(conn):
    deuter = lambda q: [{"absicht": "einstellung",
                         "text": "könntest du dich generell etwas kürzer fassen?"}]
    result = companion.respond_with_deuter(
        conn, "könntest du dich generell etwas kürzer fassen?", deuter=deuter)
    assert "Knappheit" in result["text"] and "„knapp“" in result["text"]
    assert persoenlichkeit.art(conn)["knappheit"] == "knapp"


def test_einstellungs_zelle_fragt_bei_unklarer_richtung_ehrlich_nach(conn):
    deuter = lambda q: [{"absicht": "einstellung", "text": "stell dich mal anders ein"}]
    result = companion.respond_with_deuter(conn, "stell dich mal anders ein", deuter=deuter)
    assert "Richtung" in result["text"] and "Wärme" in result["text"]
    assert persoenlichkeit.art(conn) == persoenlichkeit.ART_SEED   # nichts geraten


def test_beide_tueren_fuehren_zur_selben_wahrheit(conn):
    # Ritual-Schnellspur und Raster-Zelle teilen Implementierung UND Wortlaut
    ritual = companion._ritual_antwort(conn, "sei knapper")
    zelle = companion._zelle_einstellung(
        conn, {"text": "sei doch bitte etwas knapper"}, "sei doch bitte etwas knapper",
        None, None)
    assert "Knappheit" in ritual and "steht schon" not in ritual
    assert zelle == "Knappheit steht schon auf „knapp“ — weiter geht es in diese Richtung nicht."


def test_einstellung_ist_ein_registriertes_schreibendes_werkzeug():
    from genus import werkzeug
    spec = companion._handelbare_werkzeuge()["einstellung"]
    assert spec.schreibt is True
    assert werkzeug.stimme_geeignet(f"{companion.ZELLE_PREFIX}einstellung") is False


def test_leitplanke_persoenlichkeit_aendert_nie_das_wissen(conn):
    # dieselbe Wissensfrage, extrem verschiedene Register -- der Fakten-Kern der Antwort
    # ist byte-identisch (nur Beiläufiges/Soziales darf variieren)
    reactors.observe_relation(conn, "Hund@de", "primary_gloss", "Haustier, Vorfahre der Wolf", "dbnary")
    deuter = lambda q: {"absicht": "definition", "subject": "Hund"}
    vorher = companion.respond_with_deuter(conn, "Was ist ein Hund?", deuter=deuter)["text"]
    _stufe_runter(conn, "waerme", 2)
    persoenlichkeit.stelle(conn, "neugier", -1)
    persoenlichkeit.stelle(conn, "humor", +1)
    nachher = companion.respond_with_deuter(conn, "Was ist ein Hund?", deuter=deuter)["text"]
    assert vorher == nachher
