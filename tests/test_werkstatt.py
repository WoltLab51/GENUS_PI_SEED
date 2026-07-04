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


# --- Scheibe 2: der Schmied (Code-Modell als Einschub) + die AST-Leitplanke -----------


def _schmied():
    import importlib
    sys.path.insert(0, str(ROOT / "deploy"))
    return importlib.import_module("schmied")


GUTER_CODE = (
    "def zelle_weltfrage(conn, guess, question, last_question, last_answer, stimme=None):\n"
    "    return None\n"
)


def test_ast_leitplanke_nimmt_den_vertrag_an():
    schmied = _schmied()
    assert schmied._ast_leitplanke(GUTER_CODE, "weltfrage") == GUTER_CODE


def test_ast_leitplanke_verwirft_falsche_signatur_und_beiwerk():
    schmied = _schmied()
    # falsche Parameter
    assert schmied._ast_leitplanke(
        "def zelle_weltfrage(conn, frage):\n    return None\n", "weltfrage") is None
    # falscher Funktionsname
    assert schmied._ast_leitplanke(GUTER_CODE, "anderes-blatt") is None
    # Code auf Modulebene (ein Aufruf) -- nie ein halbgarer Entwurf
    assert schmied._ast_leitplanke(GUTER_CODE + "print('hallo')\n", "weltfrage") is None
    # gar kein Python
    assert schmied._ast_leitplanke("das ist kein code {", "weltfrage") is None


def test_schmiede_zieht_codeblock_und_prueft(monkeypatch):
    schmied = _schmied()

    class _FakeModell:
        def create_chat_completion(self, messages, max_tokens=None, temperature=None):
            return {"choices": [{"message": {"content":
                "Hier ist der Code:\n```python\n" + GUTER_CODE + "```\nViel Erfolg!"}}]}

    monkeypatch.setattr(schmied, "MODEL_PATH", __file__)
    monkeypatch.setattr(schmied, "_get_model", lambda: _FakeModell())
    assert schmied.schmiede("weltfrage") == GUTER_CODE


def test_schmiede_gibt_none_bei_leitplanken_bruch(monkeypatch):
    schmied = _schmied()

    class _FakeModell:
        def create_chat_completion(self, messages, max_tokens=None, temperature=None):
            return {"choices": [{"message": {"content":
                "```python\nimport os\nos.system('rm -rf /')\n```"}}]}

    monkeypatch.setattr(schmied, "MODEL_PATH", __file__)
    monkeypatch.setattr(schmied, "_get_model", lambda: _FakeModell())
    assert schmied.schmiede("weltfrage") is None


def test_kern_nimmt_membran_code_mit_ehrlicher_herkunft_an(conn, tmp_path):
    code_datei = tmp_path / "geschmiedet.py"
    code_datei.write_text(GUTER_CODE, encoding="utf-8")
    from click.testing import CliRunner
    from genus import cli

    result = CliRunner().invoke(
        cli.main, ["werkstatt", "entwerfe", "weltfrage",
                   "--code-datei", str(code_datei), "--quelle", "werkstatt:schmied"],
    )
    assert result.exit_code == 0 and "werkstatt:schmied" in result.output
    handler = werkstatt.verzeichnis() / "zelle_weltfrage.py"
    assert handler.read_text(encoding="utf-8") == GUTER_CODE


# --- Ronnys morphologische Zerlegung: Bauplan + Fügewerk ------------------------------
# Die drei Benchmark-Aufgaben, an denen die Modelle als CODE-Schreiber scheiterten,
# sind mit einem handgeschriebenen BAUPLAN deterministisch loesbar -- das Fuegewerk
# traegt; das Modell muss nur noch den Plan finden.

from genus import bauplan as bauplan_modul

BENCHMARK_BAUPLAENE = {
    "thema-echo": {
        "waechter": "subject",
        "beschaffung": {"art": "keine"},
        "formulierung": "„{subject}“ ist mir als Thema bekannt.",
    },
    "verbindungs-zahl": {
        "waechter": "subject",
        "beschaffung": {"art": "anzahl_kanten"},
        "formulierung": "Zu „{subject}“ kenne ich {anzahl} Verbindung(en).",
    },
    "erste-verbindung": {
        "waechter": "subject",
        "beschaffung": {"art": "erstes_objekt", "praedikat": "is_a"},
        "formulierung": "„{subject}“ ist ein {wert}.",
    },
}


def test_pruefe_bauplan_verweigert_halbgares():
    p = bauplan_modul.pruefe_bauplan
    assert p({"waechter": "zauber", "beschaffung": {"art": "keine"},
              "formulierung": "x"}) != []
    assert p({"waechter": "subject", "beschaffung": {"art": "gibt-es-nicht"},
              "formulierung": "x"}) != []
    # erstes_objekt braucht ein Praedikat; boese Praedikat-Formen fallen durch
    assert p({"waechter": "subject", "beschaffung": {"art": "erstes_objekt"},
              "formulierung": "{wert}"}) != []
    assert p({"waechter": "subject",
              "beschaffung": {"art": "erstes_objekt", "praedikat": "x; DROP TABLE"},
              "formulierung": "{wert}"}) != []
    # ein Slot, den die Beschaffung nicht liefert
    assert p({"waechter": "subject", "beschaffung": {"art": "keine"},
              "formulierung": "{anzahl}"}) != []
    # und alle drei Benchmark-Bauplaene sind sauber
    for plan in BENCHMARK_BAUPLAENE.values():
        assert p(plan) == [], plan


def test_fuegewerk_loest_alle_drei_benchmark_aufgaben_deterministisch(tmp_path):
    # exakt die Sandbox-Tests des Benchmarks -- aber der Code kommt aus dem Fuegewerk,
    # nicht aus einem Modell: vertragssicher per Konstruktion.
    sys.path.insert(0, str(ROOT / "deploy"))
    import importlib
    benchmark = importlib.import_module("schmied_benchmark")

    for aufgabe in benchmark.AUFGABEN:
        plan = BENCHMARK_BAUPLAENE[aufgabe["blatt"]]
        code = bauplan_modul.fuege_zusammen(aufgabe["blatt"], plan)
        assert benchmark._pruefe(code, aufgabe), aufgabe["blatt"]


def test_gefuegter_code_besteht_auch_die_schmied_leitplanke():
    schmied = _schmied()
    for blatt, plan in BENCHMARK_BAUPLAENE.items():
        code = bauplan_modul.fuege_zusammen(blatt, plan)
        assert schmied._ast_leitplanke(code, blatt) == code, blatt


def test_cli_fuegt_bauplan_zum_entwurf(conn, tmp_path):
    import json as _json
    from click.testing import CliRunner
    from genus import cli

    plan_datei = tmp_path / "plan.json"
    plan_datei.write_text(_json.dumps(BENCHMARK_BAUPLAENE["thema-echo"]),
                          encoding="utf-8")
    result = CliRunner().invoke(
        cli.main, ["werkstatt", "entwerfe", "thema-echo",
                   "--bauplan-datei", str(plan_datei)],
    )
    assert result.exit_code == 0 and "werkstatt:bauplan" in result.output
    code = (werkstatt.verzeichnis() / "zelle_thema_echo.py").read_text(encoding="utf-8")
    assert "„{subject}“ ist mir als Thema bekannt." in code


def test_glaettung_normalisiert_notation_und_leitet_den_waechter_ab():
    # Live im A/B gefunden: das Modell kopierte "<subject>" aus der Aufgabe woertlich
    # und waehlte einen inkonsistenten Waechter -- beides glaettet der Fuege-Durchgang
    # deterministisch (Zwickys Kreuz-Konsistenz: {subject} im Template => Waechter subject).
    roh = {
        "waechter": "keiner",
        "beschaffung": {"art": "keine"},
        "formulierung": "„<subject>“ ist mir als Thema bekannt.",
    }
    glatt = bauplan_modul.normalisiere(roh)
    assert glatt["formulierung"] == "„{subject}“ ist mir als Thema bekannt."
    assert glatt["waechter"] == "subject"
    # und der geglaettete Plan fuegt sich zu Code, der die Benchmark-Tests besteht
    sys.path.insert(0, str(ROOT / "deploy"))
    import importlib
    benchmark = importlib.import_module("schmied_benchmark")
    code = bauplan_modul.fuege_zusammen("thema-echo", roh)
    assert benchmark._pruefe(code, benchmark.AUFGABEN[0])
