"""Der ABNAHME-VERTRAG (Ronny 2026-07-07): die dritte, Verhaltens-Sperrklinke des Selbst-
Codier-Gatters. Ein Baustein wird »bewährt«, indem er einen forger-UNABHÄNGIGEN
Erwartungssatz besteht -- eine return-None-Attrappe fällt durch, wo sie früher als merge-reif
galt (das prüft der Ende-zu-Ende-Teil in test_werkstatt.py)."""
import pytest

from genus import abnahme
from genus.abnahme import Abnahmefall, Abnahmevertrag


def _vertrag_erste_verbindung():
    return Abnahmevertrag(
        blatt="erste-verbindung",
        faelle=(
            Abnahmefall(guess={"subject": "Dackel"},
                        graph=(("Dackel", "is_a", "Hund", "test"),),
                        erwartet="„Dackel“ ist ein Hund."),
            Abnahmefall(guess={"subject": "Nirgendwo"}, graph=(), erwartet=None),
        ),
    )


def test_pruefe_vertrag_verlangt_beide_belege():
    # ohne Treffer-Fall: unbewiesen, dass die Zelle je antwortet
    nur_none = Abnahmevertrag("x", (Abnahmefall({"subject": "a"}, erwartet=None),))
    assert any("Treffer" in m for m in abnahme.pruefe_vertrag(nur_none))
    # ohne None-Fall: unbewiesen, dass sie ehrlich schweigt
    nur_satz = Abnahmevertrag("x", (Abnahmefall({"subject": "a"}, erwartet="da."),))
    assert any("Passt-nicht" in m for m in abnahme.pruefe_vertrag(nur_satz))
    # beide Belege da -> fügbar
    assert abnahme.pruefe_vertrag(_vertrag_erste_verbindung()) == []


def test_pruefe_vertrag_leer_ist_kein_beweis():
    assert abnahme.pruefe_vertrag(Abnahmevertrag("x", ())) != []


def test_pruefe_vertrag_faengt_kaputte_kante():
    v = Abnahmevertrag("x", (
        Abnahmefall({"subject": "a"}, (("a", "is_a"),), erwartet="da."),   # 2 statt 4 Felder
        Abnahmefall({"subject": "b"}, erwartet=None),
    ))
    assert any("Kante" in m for m in abnahme.pruefe_vertrag(v))


def test_baue_test_ist_deterministisch_und_traegt_die_marke():
    a = abnahme.baue_test(_vertrag_erste_verbindung())
    b = abnahme.baue_test(_vertrag_erste_verbindung())
    assert a == b                              # byte-gleich -> stabiler Fingerabdruck
    assert abnahme.MARKER in a                 # protokolliere_pruefung erkennt daran VERHALTEN
    assert "def test_abnahme_fall_0" in a and "def test_abnahme_fall_1" in a
    assert "pytest.skip" not in a              # kein Skip mehr -- echtes Verhalten wird geprüft
    assert 'zelle_erste_verbindung(conn,' in a


def test_baue_test_wirft_bei_unpruefbarem_vertrag():
    with pytest.raises(ValueError):
        abnahme.baue_test(Abnahmevertrag("x", ()))


def test_aus_json_uebersetzt_treu():
    daten = {"blatt": "erste-verbindung", "faelle": [
        {"guess": {"subject": "Dackel"}, "graph": [["Dackel", "is_a", "Hund", "test"]],
         "erwartet": "„Dackel“ ist ein Hund."},
        {"guess": {"subject": "Nirgendwo"}, "erwartet": None},
    ]}
    v = abnahme.aus_json(daten)
    assert v.blatt == "erste-verbindung" and len(v.faelle) == 2
    assert v.faelle[0].graph == (("Dackel", "is_a", "Hund", "test"),)
    assert v.faelle[1].erwartet is None
    assert abnahme.pruefe_vertrag(v) == []
