"""Tool-Planer ③, Schritt 1 (rein deterministisch): der WERKPLAN-Mechanismus + der Beweis,
dass eine bekannte Antwort (die Beziehungsfrage ``relate``) als komponierter Plan über der
Werkzeug-Registry Zeichen für Zeichen dasselbe liefert wie das heutige, fest verdrahtete
``_relate_terms``. Die Komposition ist schon da -- hier wird sie nur explizit und frei
rekombinierbar. Plus die Grammatik-Prüfung (Organ, kein Orakel: nur Gültiges läuft)."""
from genus import auskunft, reactors, werkplan, werkzeug, werkzeuge_auskunft


def _hierarchie(conn):
    # Hund -> Q144 -> Q_haustier -> Q_tier ; Katze -> Q_haustier (eine echte is_a-Leiter)
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Q144", "is_a", "Q_haustier", "wikidata")
    reactors.observe_relation(conn, "Haustier@de", "expresses", "Q_haustier", "wikidata")
    reactors.observe_relation(conn, "Q_haustier", "is_a", "Q_tier", "wikidata")
    reactors.observe_relation(conn, "Tier@de", "expresses", "Q_tier", "wikidata")
    reactors.observe_relation(conn, "Q_katze", "is_a", "Q_haustier", "wikidata")
    reactors.observe_relation(conn, "Katze@de", "expresses", "Q_katze", "wikidata")


# --- der Beweis: komponierter Plan == fest verdrahtetes Original --------------------------

def test_relate_komponiert_gleicht_dem_original_ja(conn):
    _hierarchie(conn)
    komp = werkzeuge_auskunft.relate_komponiert(conn, "Hund", "Tier")
    orig = auskunft._relate_terms(conn, "Hund", "Tier")
    assert komp == orig
    assert komp["verdict"] == "yes" and komp["target"] == "Q_tier"   # echte transitive Kette


def test_relate_komponiert_gleicht_dem_original_kein_pfad(conn):
    _hierarchie(conn)
    komp = werkzeuge_auskunft.relate_komponiert(conn, "Hund", "Katze")   # keine is_a-Linie
    orig = auskunft._relate_terms(conn, "Hund", "Katze")
    assert komp == orig and komp["verdict"] == "no_path"


def test_relate_komponiert_gleicht_dem_original_unbekannt(conn):
    _hierarchie(conn)
    # unbekanntes Subjekt UND unbekanntes Objekt -- beide Male {relational: False}, identisch
    for x, y in (("Xyzzy", "Tier"), ("Hund", "Xyzzy")):
        assert (werkzeuge_auskunft.relate_komponiert(conn, x, y)
                == auskunft._relate_terms(conn, x, y) == {"relational": False})


def test_die_komponierte_antwort_bleibt_narrierbar(conn):
    # das komponierte Ergebnis trägt genau die Felder, die die Stimme braucht -> gläsern bleibt gläsern
    _hierarchie(conn)
    komp = werkzeuge_auskunft.relate_komponiert(conn, "Hund", "Tier")
    assert auskunft.narrate_relation(conn, komp) == auskunft.narrate_relation(
        conn, auskunft._relate_terms(conn, "Hund", "Tier"))


# --- die Grammatik-Prüfung (die erste Leine: nur Gültiges läuft) --------------------------

def test_der_beziehungsplan_ist_wohlgeformt(conn):
    werkzeuge_auskunft.registriere_auskunft_werkzeuge()
    assert werkplan.pruefe_plan(werkzeuge_auskunft.BEZIEHUNG_PLAN) == []


def test_pruefer_faengt_unregistriertes_werkzeug():
    plan = werkplan.Werkplan(
        eingaben=("a",),
        schritte=(werkplan.Schritt("x", "gibt_es_nicht", (("wort", ("in", "a")),)),),
        ergebnis="x",
    )
    fehler = werkplan.pruefe_plan(plan)
    assert any("nicht registriert" in f for f in fehler)


def test_pruefer_faengt_vorwaerts_verweis():
    werkzeuge_auskunft.registriere_auskunft_werkzeuge()
    # „erg" verweist auf „vf", das ERST DANACH kommt -> kein Rückwärts-Verweis -> abgelehnt
    plan = werkplan.Werkplan(
        eingaben=("x_tok",),
        schritte=(
            werkplan.Schritt("erg", "oberbegriffe", (("form", ("aus", "vf", "form")),)),
            werkplan.Schritt("vf", "konzept_form", (("wort", ("in", "x_tok")),)),
        ),
        ergebnis="erg",
    )
    fehler = werkplan.pruefe_plan(plan)
    assert any("noch) nicht berechnet" in f for f in fehler)


def test_pruefer_faengt_griff_in_nicht_geliefertes_feld():
    # Scheibe A: seit Werkzeug.liefert prüft die Grammatik auch, ob ein ("aus",...)-Verweis
    # ein Feld greift, das der Quell-Schritt WIRKLICH liefert -- ein Tippfehler im Feldnamen
    # ist jetzt ein Grammatik-Fehler, kein Laufzeit-KeyError mehr.
    werkzeuge_auskunft.registriere_auskunft_werkzeuge()
    plan = werkplan.Werkplan(
        eingaben=("x_tok",),
        schritte=(
            werkplan.Schritt("xf", "konzept_form", (("wort", ("in", "x_tok")),)),
            werkplan.Schritt("vf", "oberbegriffe", (("form", ("aus", "xf", "vorm")),)),  # Tippfehler
        ),
        ergebnis="vf",
    )
    fehler = werkplan.pruefe_plan(plan)
    assert any("vorm" in f and "liefert nur" in f for f in fehler)


def test_pruefer_faengt_typ_bruch():
    # ...und ob der Typ des gelieferten Felds zum konsumierenden Parameter passt: oberbegriffe
    # erwartet form: "Wort", konzepte_von.konzepte liefert "Menge" -> Grammatik-Fehler.
    werkzeuge_auskunft.registriere_auskunft_werkzeuge()
    plan = werkplan.Werkplan(
        eingaben=("x_tok",),
        schritte=(
            werkplan.Schritt("yk", "konzepte_von", (("wort", ("in", "x_tok")),)),
            werkplan.Schritt("vf", "oberbegriffe", (("form", ("aus", "yk", "konzepte")),)),
        ),
        ergebnis="vf",
    )
    fehler = werkplan.pruefe_plan(plan)
    assert any("erwartet Typ" in f and "Wort" in f and "Menge" in f for f in fehler)


def test_zellen_sind_ausdruecklich_terminal():
    # eine Gesprächszelle liefert einen fertigen Satz (str), keine Nutzlast-Felder -- die
    # bewusst leere liefert-Deklaration macht den Griff in ihre "Felder" zum Grammatik-Fehler.
    from genus import companion
    companion.registriere_zellen()
    zelle = f"{companion.ZELLE_PREFIX}definition"
    plan = werkplan.Werkplan(
        eingaben=("frage",),
        schritte=(
            werkplan.Schritt("z", zelle, (("question", ("in", "frage")),)),
            werkplan.Schritt("vf", "oberbegriffe", (("form", ("aus", "z", "text")),)),
        ),
        ergebnis="vf",
    )
    werkzeuge_auskunft.registriere_auskunft_werkzeuge()
    fehler = werkplan.pruefe_plan(plan)
    assert any("terminal" in f for f in fehler)


def test_ausfuehrer_verweigert_malformten_plan(conn):
    plan = werkplan.Werkplan(
        eingaben=("a",),
        schritte=(werkplan.Schritt("x", "gibt_es_nicht", (("wort", ("in", "a")),)),),
        ergebnis="x",
    )
    try:
        werkplan.fuehre_aus(conn, plan, a="Hund")
        assert False, "malformter Plan haette abgelehnt werden muessen"
    except ValueError as e:
        assert "Grammatik" in str(e)
