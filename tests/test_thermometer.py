"""Das Thermometer (Skill-Dashboard ④): Sensor für den Menschen, kein Optimierungsziel.
Die Tests prüfen die zwei Leitplanken strukturell: read-only (kein einziges Event) und
Generalisierung als Kennzahl (die Planer-Absichten, nicht die Handler-Zahl)."""
import json
import sqlite3

from click.testing import CliRunner

from genus import cli, companion, reactors, thermometer, verstehen
from genus.db import init_schema


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    verstehen.seed_raster(conn)
    return conn


def _zaehlwerk_datei(tmp_path, monkeypatch, zeilen):
    pfad = tmp_path / "zaehlwerk.jsonl"
    pfad.write_text("\n".join(json.dumps(z) for z in zeilen) + "\n", encoding="utf-8")
    monkeypatch.setenv("GENUS_PLANER_ZAEHLWERK", str(pfad))


def test_stand_ist_strikt_read_only(tmp_path, monkeypatch):
    # DIE Goodhart-Leitplanke, strukturell: das Thermometer misst, es schreibt NIE --
    # kein einziges neues Event im Ledger durch einen vollen stand()-Lauf.
    _zaehlwerk_datei(tmp_path, monkeypatch, [{"absicht": "beziehung", "ereignis": "treffer"}])
    conn = _conn()
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    vorher = conn.execute("SELECT COUNT(*) n FROM event_log").fetchone()["n"]
    thermometer.stand(conn)
    nachher = conn.execute("SELECT COUNT(*) n FROM event_log").fetchone()["n"]
    assert nachher == vorher


def test_planer_quote_wird_aus_dem_zaehlwerk_berechnet(tmp_path, monkeypatch):
    _zaehlwerk_datei(tmp_path, monkeypatch, [
        {"absicht": "beziehung", "ereignis": "treffer"},
        {"absicht": "beziehung", "ereignis": "treffer"},
        {"absicht": "beziehung", "ereignis": "treffer"},
        {"absicht": "beziehung", "ereignis": "rueckfall"},
        {"absicht": "ort", "ereignis": "treffer"},
    ])
    s = thermometer.stand(_conn())
    assert s["planer"]["beziehung"]["treffer"] == 3
    assert s["planer"]["beziehung"]["quote"] == 0.75
    assert s["planer"]["ort"]["quote"] == 1.0


def test_generalisierung_zaehlt_die_planer_absichten_nicht_die_handler(tmp_path, monkeypatch):
    # die Doktrin-Kennzahl: sie wächst nur durch eine neue Absicht auf der EINEN Mechanik
    # (ABSICHT_SAAT) -- eine neue Sonder-Zelle/Handler erhöht sie nicht
    from genus.werkzeuge_auskunft import ABSICHT_SAAT
    _zaehlwerk_datei(tmp_path, monkeypatch, [
        {"absicht": "beziehung", "ereignis": "treffer"},
        {"absicht": "beziehung", "ereignis": "rueckfall"},
    ])
    s = thermometer.stand(_conn())
    g = s["generalisierung"]
    assert g["absichten_auf_planer"] == sorted(ABSICHT_SAAT)
    assert "ort" in g["absichten_auf_planer"]              # die vierte Absicht zählt
    assert g["verkehr_ueber_planer"] == 0.5
    assert g["blaetter_handelbar"] <= g["blaetter_gesaet"]


def test_verstehen_belegung_und_unklar_erscheinen(tmp_path, monkeypatch):
    _zaehlwerk_datei(tmp_path, monkeypatch, [])
    conn = _conn()
    verstehen.record_reading(conn, "beziehung", "muster")
    verstehen.record_reading(conn, "beziehung", "model:deuter")
    verstehen.record_reading(conn, "unklar", "model:deuter")
    s = thermometer.stand(conn)
    assert s["verstehen"]["blaetter"]["beziehung"]["gelesen"] == {"muster": 1, "model:deuter": 1}
    assert s["verstehen"]["unklar"] == {"model:deuter": 1}


def test_luecken_nennen_blaetter_ohne_handler_ehrlich(tmp_path, monkeypatch):
    _zaehlwerk_datei(tmp_path, monkeypatch, [])
    s = thermometer.stand(_conn())
    ohne = s["luecken"]["blaetter_ohne_handler"]
    assert "tun" in ohne                   # eine ehrlich benannte Lücke
    assert "faehigkeiten" not in ohne      # seit Proposal #15 gebaut -- GENUS' eigener Wunsch
    assert "beziehung" not in ohne         # handelbar -> keine Lücke
    assert "unklar" not in ohne            # kein Blatt, sondern der blinde Fleck selbst


def test_skills_cli_rendert_das_thermometer(tmp_path, monkeypatch):
    _zaehlwerk_datei(tmp_path, monkeypatch, [
        {"absicht": "ort", "ereignis": "treffer"},
    ])
    conn = _conn()
    monkeypatch.setattr(cli, "get_conn", lambda: conn)
    result = CliRunner().invoke(cli.main, ["skills"])
    assert result.exit_code == 0, result.output
    assert "Sensor, kein Ziel" in result.output
    assert "GENERALISIERUNG" in result.output
    assert "ort" in result.output
    assert "LÜCKEN" in result.output
