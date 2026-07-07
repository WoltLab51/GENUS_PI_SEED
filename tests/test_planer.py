"""Der PLANER (Ronny 2026-07-07): der Bauplan-Finder als Schluss. Aus einem Abnahme-Vertrag
schliesst GENUS sich selbst einen Bauplan zusammen -- deterministisch, KEIN LLM. Der Beweis:
er entdeckt die drei Benchmark-Baupläne allein aus ihren Beispielfällen wieder, und er gibt
ehrlich None, wo seine Bausteine nicht reichen."""
from genus import bauplan, planer
from genus.abnahme import Abnahmefall, Abnahmevertrag


def _v(blatt, faelle):
    return Abnahmevertrag(blatt, tuple(faelle))


def test_findet_erstes_objekt_bauplan():
    v = _v("erste-verbindung", [
        Abnahmefall({"subject": "Dackel"}, (("Dackel", "is_a", "Hund", "q"),),
                    erwartet="„Dackel“ ist ein Hund."),
        Abnahmefall({"subject": "Nirgendwo"}, (), erwartet=None),
    ])
    plan = planer.finde_bauplan(v)
    assert plan is not None
    assert plan["beschaffung"] == {"art": "erstes_objekt", "praedikat": "is_a"}
    assert plan["formulierung"] == "„{subject}“ ist ein {wert}."
    assert plan["waechter"] == "subject"
    assert bauplan.pruefe_bauplan(plan) == []


def test_findet_keine_bauplan_thema_echo():
    v = _v("thema-echo", [
        Abnahmefall({"subject": "Klima"}, (), erwartet="„Klima“ ist mir als Thema bekannt."),
        Abnahmefall({}, (), erwartet=None),   # kein subject -> None (Waechter)
    ])
    plan = planer.finde_bauplan(v)
    assert plan is not None and plan["beschaffung"]["art"] == "keine"
    assert plan["formulierung"] == "„{subject}“ ist mir als Thema bekannt."


def test_findet_anzahl_kanten_bauplan():
    v = _v("verbindungs-zahl", [
        Abnahmefall({"subject": "Hund"},
                    (("Hund", "is_a", "Tier", "q"), ("Hund", "part_of", "Rudel", "q")),
                    erwartet="Zu „Hund“ kenne ich 2 Verbindung(en)."),
        Abnahmefall({"subject": "Leer"}, (), erwartet=None),   # 0 Kanten -> None
    ])
    plan = planer.finde_bauplan(v)
    assert plan is not None and plan["beschaffung"]["art"] == "anzahl_kanten"
    assert plan["formulierung"] == "Zu „{subject}“ kenne ich {anzahl} Verbindung(en)."


def test_der_passt_nicht_fall_zwingt_den_richtigen_baustein():
    # ohne den None-Fall wuerde "keine" faelschlich passen (es antwortet immer). Der Passt-nicht-
    # Fall (Nirgendwo -> None) ZWINGT den Finder zum erstes_objekt-Baustein statt zum simplen echo.
    v = _v("erste-verbindung", [
        Abnahmefall({"subject": "Dackel"}, (("Dackel", "is_a", "Hund", "q"),),
                    erwartet="„Dackel“ ist ein Hund."),
        Abnahmefall({"subject": "Nirgendwo"}, (), erwartet=None),
    ])
    assert planer.finde_bauplan(v)["beschaffung"]["art"] == "erstes_objekt"


def test_gibt_none_wenn_die_vokabel_nicht_reicht():
    # zwei Treffer mit unterschiedlichem, NICHT graph-ableitbarem Inhalt -> kein einzelner
    # Baustein + Template traegt beide; der Planer gibt ehrlich None (raet nicht)
    v = _v("unbaubar", [
        Abnahmefall({"subject": "A"}, (), erwartet="A ist rot."),
        Abnahmefall({"subject": "B"}, (), erwartet="B ist blau."),
        Abnahmefall({}, (), erwartet=None),
    ])
    assert planer.finde_bauplan(v) is None
    assert "reicht (noch) nicht" in planer.narrate(None)


def test_lose_klammer_stuerzt_nicht_ab_sondern_gibt_none():
    # Review-Fund: eine unpaarige { / } im erwarteten Satz erzeugte ein kaputtes Format-Template
    # und einen ungefangenen ValueError bis in die CLI. Jetzt: ehrliches None, kein Absturz.
    v = _v("mit-klammer", [
        Abnahmefall({"subject": "Hund"}, (), erwartet="Hund hat Merkmal } offen."),
        Abnahmefall({}, (), erwartet=None),
    ])
    assert planer.finde_bauplan(v) is None
    assert "reicht (noch) nicht" in planer.narrate(None)


def test_ascii_anfuehrungszeichen_werden_nicht_still_verfehlt():
    # Review-Fund: schreibt der Autor ASCII-"..." (in JSON idiomatisch), schrieb normalisiere sie
    # auf Guillemets um -> der Plan reproduzierte den Satz nicht mehr -> falsches None. Jetzt bleibt
    # die Formulierung Wort fuer Wort wie im Vertrag; der Bauplan wird gefunden.
    v = _v("erste-verbindung", [
        Abnahmefall({"subject": "Dackel"}, (("Dackel", "is_a", "Hund", "q"),),
                    erwartet='"Dackel" ist ein Hund.'),   # ASCII-Quotes
        Abnahmefall({"subject": "Nirgendwo"}, (), erwartet=None),
    ])
    plan = planer.finde_bauplan(v)
    assert plan is not None and plan["beschaffung"]["art"] == "erstes_objekt"
    assert plan["formulierung"] == '"{subject}" ist ein {wert}.'   # ASCII bleibt ASCII


def test_ohne_treffer_kein_bauplan():
    v = _v("nur-none", [Abnahmefall({"subject": "X"}, (), erwartet=None)])
    assert planer.finde_bauplan(v) is None


def test_gefundener_bauplan_fuegt_sich_zu_vertragssicherem_code():
    # der Kreis: der geschlossene Bauplan ist fuegbar (fuege_zusammen wirft nicht) und liefert
    # eine echte Zelle -- der Sandbox-Beweis am gefuegten Code liegt in test_werkstatt.py
    v = _v("erste-verbindung", [
        Abnahmefall({"subject": "Dackel"}, (("Dackel", "is_a", "Hund", "q"),),
                    erwartet="„Dackel“ ist ein Hund."),
        Abnahmefall({"subject": "Nirgendwo"}, (), erwartet=None),
    ])
    plan = planer.finde_bauplan(v)
    code = bauplan.fuege_zusammen("erste-verbindung", plan)
    assert "def zelle_erste_verbindung(conn, guess" in code
    assert "„{subject}“ ist ein {wert}." in code
    assert "zusammengeschlossen" in planer.narrate(plan)
