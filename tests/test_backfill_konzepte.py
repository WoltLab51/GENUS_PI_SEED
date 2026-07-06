"""Backfill der dynamischen Schicht (Ronny 2026-07-06). Pinnt die reinen Extraktions-Funktionen
von deploy/backfill_konzepte.py gegen synthetische wbgetentities-Antworten — genau die Ränder,
die der adversariale Review benannt hat: nur Item-Ziele, kein Selbst-Loop, korrektes Prädikat-
Mapping, Label-Sprachvorzug."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("backfill_konzepte", ROOT / "deploy" / "backfill_konzepte.py")
bf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bf)


def _item(pid, obj_qid):
    return {pid: [{"mainsnak": {"datavalue": {"value": {"id": obj_qid}, "type": "wikibase-entityid"}}}]}


def test_extrahiere_kanten_mappt_die_dynamischen_praedikate(conn=None):
    ent = {"Q1": {"claims": {**_item("P361", "Q2"), **_item("P527", "Q3"), **_item("P366", "Q4")}}}
    tripel, objids = bf.extrahiere_kanten(ent)
    assert ("Q1", "part_of", "Q2") in tripel
    assert ("Q1", "has_part", "Q3") in tripel
    assert ("Q1", "used_for", "Q4") in tripel
    assert objids == {"Q2", "Q3", "Q4"}


def test_tiefung_erntet_is_a_hinzu():
    # Der Default lässt is_a (P279) weg (Kletter-Lerner); die Tiefung nimmt es HINZU, um die
    # Inseln zu platzieren. Dieselbe Antwort, zwei Prädikat-Maps -> unterschiedliche Ausbeute.
    ent = {"Q1": {"claims": {**_item("P279", "Q5"), **_item("P361", "Q2")}}}
    ohne, _ = bf.extrahiere_kanten(ent)                          # Default: nur dynamisch
    mit, _ = bf.extrahiere_kanten(ent, bf.PROP_MAP_TIEFUNG)      # Tiefung: is_a dazu
    assert ("Q1", "is_a", "Q5") not in ohne and ("Q1", "part_of", "Q2") in ohne
    assert ("Q1", "is_a", "Q5") in mit and ("Q1", "part_of", "Q2") in mit


def test_extrahiere_kanten_nimmt_nur_item_ziele():
    # ein Quantity/String/Koordinaten-Wert hat kein value.id -> keine Müll-Kante, kein Absturz
    ent = {"Q1": {"claims": {
        "P361": [{"mainsnak": {"datavalue": {"value": {"amount": "+5"}, "type": "quantity"}}}],
        "P366": [{"mainsnak": {"datavalue": {"value": "freitext", "type": "string"}}}],
        "P527": [{"mainsnak": {"snaktype": "novalue"}}],          # gar kein datavalue
    }}}
    tripel, objids = bf.extrahiere_kanten(ent)
    assert tripel == [] and objids == set()


def test_extrahiere_kanten_filtert_selbst_loop_und_nicht_items():
    # X part_of X (Selbst-Loop, nie legitim) und ein Property/Lexem-Ziel werden verworfen
    ent = {"Q1": {"claims": {
        **_item("P361", "Q1"),                                    # Selbst-Loop
        "P527": [{"mainsnak": {"datavalue": {"value": {"id": "P279"}, "type": "wikibase-entityid"}}}],  # Property
        **_item("P186", "Q9"),                                    # echt -> bleibt
    }}}
    tripel, objids = bf.extrahiere_kanten(ent)
    assert tripel == [("Q1", "made_of", "Q9")] and objids == {"Q9"}


def test_extrahiere_labels_bevorzugt_deutsch_dann_englisch():
    ent = {
        "Q2": {"labels": {"de": {"value": "Rad"}, "en": {"value": "wheel"}}},
        "Q3": {"labels": {"en": {"value": "hub"}}},               # kein de -> en
        "Q4": {"labels": {}},                                     # kein Label -> nichts
    }
    out = bf.extrahiere_labels(ent)
    assert ("Rad@de", "label", "Q2") in out and ("Rad@de", "expresses", "Q2") in out
    assert ("hub@en", "label", "Q3") in out
    assert not any(o == "Q4" for _, _, o in out)                  # ein namenloses Ziel bleibt draußen
    assert not any(s.startswith("wheel@") for s, _, _ in out)     # de gewann, en nicht zusätzlich
