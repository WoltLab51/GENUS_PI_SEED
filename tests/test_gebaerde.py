"""Die Gebärden-Schnellspur (Proposal #14): eine reine Emoji-Nachricht wird gläsern und
modellfrei auf ein Floskel-Blatt gelesen -- die Antwort auf die vom Fehlgriff-Konsumenten
selbst erspürte Emoji-Lücke ("Nachrichten, die ich gar nicht deuten konnte")."""
import sqlite3

from genus import companion, gebaerde, reactors, sources, verstehen
from genus.db import init_schema

# Emoji als Codepoints, damit im Quelltext keine unsichtbaren/heiklen Literale stehen.
DAUMEN_HOCH = "\U0001F44D"
DAUMEN_RUNTER = "\U0001F44E"
BETENDE_HAENDE = "\U0001F64F"
WINKEN = "\U0001F44B"
HERZ = "❤"
SCHLAFEND = "\U0001F634"           # bewusst NICHT in der Liste -- zweideutig
HAUTTON_MITTEL = "\U0001F3FD"
VARIANTEN_SELEKTOR = chr(0xFE0F)


def _fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


# --- der Reader selbst (reine Funktion, keine conn) ------------------------------------

def _absichten(nachricht):
    gelesen = gebaerde.lies(nachricht)
    return None if gelesen is None else [s["absicht"] for s in gelesen]


def test_eindeutige_gesten_werden_auf_ihr_floskel_blatt_gelesen():
    assert _absichten(DAUMEN_HOCH) == ["lob"]
    assert _absichten(BETENDE_HAENDE) == ["dank"]
    assert _absichten(WINKEN) == ["gruss"]
    assert _absichten(DAUMEN_RUNTER) == ["kritik"]


def test_wiederholte_geste_ist_eine_geste():
    assert _absichten(DAUMEN_HOCH * 3) == ["lob"]


def test_mehrere_verschiedene_gesten_in_reihenfolge():
    assert _absichten(BETENDE_HAENDE + HERZ) == ["dank", "lob"]


def test_gemischter_text_bleibt_sache_des_modells():
    # Buchstaben/Ziffern -> None: das kann das Modell gut, das Emoji ist dort ohnehin redundant
    assert gebaerde.lies("danke " + BETENDE_HAENDE) is None
    assert gebaerde.lies("2 " + DAUMEN_HOCH) is None


def test_unbekanntes_emoji_faellt_ehrlich_durch():
    # keine erzwungene Kategorie (kein Ankreuzzwang) -- lieber None und ehrlich weiterreichen
    assert gebaerde.lies(SCHLAFEND) is None


def test_modifikatoren_veraendern_die_geste_nicht():
    assert _absichten(DAUMEN_HOCH + HAUTTON_MITTEL) == ["lob"]
    assert _absichten(HERZ + VARIANTEN_SELEKTOR) == ["lob"]


def test_leere_oder_reine_whitespace_nachricht_ist_keine_geste():
    assert gebaerde.lies("") is None
    assert gebaerde.lies("   ") is None
    assert gebaerde.lies(None) is None


# --- die Schnellspur im Dispatch (respond_with_deuter) ---------------------------------

def test_emoji_nachricht_wird_ohne_modell_warm_beantwortet():
    conn = _fresh()
    aufrufe = []
    deuter = lambda q: aufrufe.append(q) or []   # das Modell DARF hier nie laufen
    result = companion.respond_with_deuter(conn, DAUMEN_HOCH, deuter=deuter)
    assert aufrufe == []                          # die Gebärde griff vor dem Modell
    assert result["text"] != companion._NICHT_VERSTANDEN
    assert result["gelesen"] == ["lob"]
    # ehrlich: KEIN "vom Sprachmodell gedeutet" -- es hat kein Modell gedeutet
    assert "Sprachmodell" not in result["text"]


def test_dank_geste_landet_in_der_dank_zelle():
    conn = _fresh()
    result = companion.respond_with_deuter(conn, BETENDE_HAENDE, deuter=lambda q: [])
    assert result["gelesen"] == ["dank"]
    assert result["text"] != companion._NICHT_VERSTANDEN


def test_belegung_traegt_die_ehrliche_herkunft_gebaerde():
    conn = _fresh()
    companion.respond_with_deuter(conn, DAUMEN_HOCH, deuter=lambda q: [])
    quellen = {
        r["object"]
        for r in sources.relations(conn, subject=verstehen.node("lob"),
                                    predicate=verstehen.READING_PREDICATE)
    }
    assert "gebaerde" in quellen           # die Belegung ist als Gebärde vermerkt, nicht als Modell
    assert "model:deuter" not in quellen


def test_gemischte_nachricht_geht_weiter_an_den_deuter():
    conn = _fresh()
    aufrufe = []
    deuter = lambda q: aufrufe.append(q) or []
    companion.respond_with_deuter(conn, "danke dir " + BETENDE_HAENDE, deuter=deuter)
    assert aufrufe == ["danke dir " + BETENDE_HAENDE]   # kein reines Emoji -> das Modell liest
