"""Die Werkstatt (Selbst-Codieren Stufe 2, Scheibe 1): Entwürfe entstehen außerhalb des
Kerns, werden deterministisch (Verbots-Scan) und in der Sandbox (Membran-Probefahrt)
geprüft — Teil der Hülle wird ein Entwurf NUR durch einen menschlichen Git-Merge."""
import subprocess
import sys
from pathlib import Path

import pytest

from genus import werkstatt

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _werkstatt_im_tmp(monkeypatch, tmp_path):
    monkeypatch.setenv("GENUS_WERKSTATT", str(tmp_path / "werkstatt"))


def test_entwurf_entsteht_ausserhalb_des_kerns(conn):
    ergebnis = werkstatt.entwerfe_zelle(conn, "weltfrage")
    assert ergebnis["erstellt"] is True
    handler = Path(ergebnis["handler"])
    assert handler.exists() and Path(ergebnis["test"]).exists()
    # NIE unter genus/ -- die Werkstatt kann den Kern nicht anfassen
    assert ROOT / "genus" not in handler.parents
    code = handler.read_text(encoding="utf-8")
    assert "def zelle_weltfrage(conn, guess, question, last_question" in code
    assert "return None" in code   # das ehrliche Skelett
    # die Entscheidungs-Spur liegt im Ledger, mit Fingerabdruck
    row = conn.execute(
        "SELECT payload FROM event_log WHERE event_type = 'code_entwurf_erstellt'"
    ).fetchone()
    assert row is not None and "fingerabdruck" in row["payload"]


def test_entwurf_wird_nie_ueberschrieben(conn):
    assert werkstatt.entwerfe_zelle(conn, "weltfrage")["erstellt"] is True
    zweiter = werkstatt.entwerfe_zelle(conn, "weltfrage")
    assert zweiter["erstellt"] is False and "menschliche Entscheidung" in zweiter["grund"]


def test_verbots_scan_faengt_ausbruchs_bausteine(conn):
    werkstatt.entwerfe_zelle(conn, "weltfrage")
    handler = werkstatt.verzeichnis() / "zelle_weltfrage.py"
    handler.write_text(
        handler.read_text(encoding="utf-8")
        + "\nimport requests\nimport subprocess\n", encoding="utf-8",
    )
    ergebnis = werkstatt.protokolliere_pruefung(conn, "weltfrage", tests_exit=0)
    assert "requests" in ergebnis["verbote"] and "subprocess" in ergebnis["verbote"]
    # Verbote schlagen ALLES: selbst gruene Tests machen den Entwurf nie merge-reif
    assert ergebnis["bestanden"] is False


def test_probefahrt_ergebnis_wird_ueberreicht_und_protokolliert(conn):
    # Die Membran faehrt die Sandbox-Tests wirklich (hier direkt, wie
    # deploy/werkstatt_probefahrt.sh es tut) und ueberreicht nur das Ergebnis.
    werkstatt.entwerfe_zelle(conn, "weltfrage")
    testdatei = werkstatt.verzeichnis() / "test_zelle_weltfrage.py"
    lauf = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(testdatei)],
        cwd=str(werkstatt.verzeichnis()), capture_output=True, text=True, timeout=120,
    )
    assert lauf.returncode == 0   # Signatur-Pin gruen, Faehigkeits-Test ehrlich geskippt
    ergebnis = werkstatt.protokolliere_pruefung(conn, "weltfrage", tests_exit=lauf.returncode)
    assert ergebnis["bestanden"] is True   # merge-REIF -- gemergt wird nur menschlich


def test_nur_statische_pruefung_ist_nie_bestanden(conn):
    werkstatt.entwerfe_zelle(conn, "weltfrage")
    ergebnis = werkstatt.protokolliere_pruefung(conn, "weltfrage")   # ohne Probefahrt
    assert ergebnis["verbote"] == [] and ergebnis["tests_exit"] is None
    assert ergebnis["bestanden"] is False   # ohne Probefahrt keine Merge-Reife


def test_generator_ist_einschub_und_wird_ehrlich_benannt(conn):
    ergebnis = werkstatt.entwerfe_zelle(
        conn, "weltfrage",
        generator=lambda blatt: (
            "def zelle_weltfrage(conn, guess, question, last_question, "
            "last_answer, stimme=None):\n    return 'Modell-Entwurf'\n"
        ),
    )
    assert ergebnis["quelle"] == "werkstatt:generator"
    row = conn.execute(
        "SELECT payload FROM event_log WHERE event_type = 'code_entwurf_erstellt'"
    ).fetchone()
    assert "werkstatt:generator" in row["payload"]


def test_pruefung_ohne_entwurf_bleibt_ehrlich(conn):
    ergebnis = werkstatt.protokolliere_pruefung(conn, "gibt-es-nicht")
    assert ergebnis["gefunden"] is False
