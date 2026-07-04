"""Der Antwort-Würfel (genus.antwort): die Zwicky-Symmetrie an der Membran — der
Verstehens-Würfel zerlegt, was reinkommt; dieser setzt zusammen, was rausgeht. Die Wahl
ist immer deterministisch; das Modell (Stimme) formuliert nur innerhalb der Zelle."""
from genus import antwort, companion, persoenlichkeit, reactors


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
