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
