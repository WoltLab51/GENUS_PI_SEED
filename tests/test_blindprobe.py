"""Die Blind-Probe (deploy/blindprobe.py): die selbst-kalibrierte Handlungs-Schwelle je
Gestalt/Klasse. Die Schwellen-LOGIK wird deterministisch mit Fake-Messwerten geprüft (ob das
Modell gut wiegt, ist eine Modell-Frage und läuft live am Pi)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy"))
import blindprobe  # noqa: E402


def _e(name, gestalt, ok, margin, klasse="x"):
    return {"name": name, "klasse": klasse, "gestalt": gestalt, "ok": ok, "margin": margin,
            "gewaehlt": name}


def test_schwelle_ohne_fehlgriff_ist_der_kleinste_richtige_margin():
    erg = [_e("a", "form", True, 1.2), _e("b", "form", True, 0.4), _e("c", "form", True, 3.0)]
    s = blindprobe._schwelle(erg)
    assert s["schwelle"] == 0.4 and s["regel"] == "min-richtig" and s["treffer"] == 3


def test_schwelle_mit_fehlgriff_liegt_knapp_ueber_dem_groessten_fehlgriff():
    # ein selbstbewusst-falscher Fehlgriff (margin 4.9) muss die Schwelle nach oben drücken
    erg = [_e("gut", "inhalt", True, 5.4), _e("boese", "inhalt", False, 4.9),
           _e("knapp", "inhalt", True, 2.0)]
    s = blindprobe._schwelle(erg)
    assert s["schwelle"] > 4.9 and s["regel"] == "ueber-max-fehlgriff"
    # nur die richtige Wägung über 4.9 überlebt -> Präzision 1.0 auf dem Gemessenen
    assert s["schwelle"] <= 5.4


def test_schwelle_none_wenn_kein_richtiger_ueber_allen_fehlgriffen_liegt():
    # alle Fehlgriffe wiegen schwerer als jede richtige -> es gibt keinen sicheren Bereich
    erg = [_e("gut", "inhalt", True, 1.0), _e("boese", "inhalt", False, 3.0)]
    s = blindprobe._schwelle(erg)
    assert s["schwelle"] is None and s["regel"] == "kein-sicherer-bereich"


def test_schwelle_none_wenn_nichts_richtig():
    erg = [_e("boese", "inhalt", False, 3.0)]
    assert blindprobe._schwelle(erg)["schwelle"] is None


def test_kalibriere_gruppiert_nach_gestalt_und_klasse():
    erg = [_e("m1", "form", True, 1.0, klasse="morphologie"),
           _e("m2", "form", True, 2.0, klasse="morphologie"),
           _e("i1", "inhalt", True, 5.0, klasse="wsd"),
           _e("i2", "inhalt", False, 0.5, klasse="wsd")]
    kal = blindprobe.kalibriere(erg)
    assert set(kal["gestalten"]) == {"form", "inhalt"}
    assert set(kal["klassen"]) == {"morphologie", "wsd"}
    assert kal["gestalten"]["form"]["schwelle"] == 1.0             # kein Fehlgriff -> min richtig
    assert kal["gestalten"]["inhalt"]["schwelle"] > 0.5            # über dem Fehlgriff


def test_messe_ohne_modell_ist_none():
    # kein Modell injiziert und keins auf der Platte -> None (keine leere Kalibrierung)
    alt = blindprobe.waage.MODEL_PATH
    blindprobe.waage.MODEL_PATH = "/gibt/es/nicht.gguf"
    blindprobe.waage._model = None
    try:
        assert blindprobe.messe(proben=[{"name": "x", "klasse": "x", "gestalt": "form",
                                         "kontext": "a ", "kandidaten": ["b", "c"],
                                         "erwartet": "b"}]) is None
    finally:
        blindprobe.waage.MODEL_PATH = alt


def test_schreibe_und_lese_kalibrierung(tmp_path):
    kal = {"gestalten": {"form": {"schwelle": 0.4, "n": 14, "treffer": 14, "regel": "min-richtig"}}}
    pfad = tmp_path / "waage_kalibrierung.json"
    blindprobe.schreibe_kalibrierung(kal, str(pfad))
    gelesen = json.loads(pfad.read_text(encoding="utf-8"))
    assert gelesen["gestalten"]["form"]["schwelle"] == 0.4


def test_die_proben_datei_ist_wohlgeformt_und_vollstaendig():
    proben = blindprobe.lade_proben()
    assert len(proben) >= 50
    for p in proben:
        assert p["erwartet"] in p["kandidaten"]            # Integrität: erwartet ist wählbar
        assert p["gestalt"] in ("form", "stil", "inhalt")
        assert p["kontext"] is not None and len(p["kandidaten"]) >= 2
