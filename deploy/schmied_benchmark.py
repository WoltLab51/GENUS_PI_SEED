"""Schmied-Benchmark: welches lokale Code-Modell schmiedet? Messen statt raten — dieselbe
Disziplin wie beim Deuter-Benchmark (7 Modelle/4 Familien, Qwen2.5-1.5B gewann dort).

Drei Aufgaben steigender Schwere, jede mit DETERMINISTISCHEN Sandbox-Tests (pytest im
Subprozess, wie die echte Probefahrt). Eine Aufgabe zählt nur, wenn der Entwurf die
AST-Leitplanke des Schmieds besteht UND seine Tests grün laufen. Ergebnis pro Modell:
bestanden/gesamt + Dauer. Standalone (kein genus-Import — Edge-Skript).

Usage:  .venv/bin/python deploy/schmied_benchmark.py <model.gguf> [weitere.gguf ...]
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import schmied  # noqa: E402

AUFGABEN = [
    {
        "blatt": "thema-echo",
        "beschreibung": (
            "Wenn guess['subject'] ein nicht-leerer String ist, gib genau den Satz "
            "'„<subject>“ ist mir als Thema bekannt.' zurück (mit deutschen "
            "Anführungszeichen „ und “). Sonst gib None zurück. conn wird nicht benutzt."
        ),
        "test": (
            "from zelle_thema_echo import zelle_thema_echo\n"
            "\n"
            "def test_mit_subject():\n"
            "    s = zelle_thema_echo(None, {'subject': 'Hund'}, 'egal', None, None)\n"
            "    assert s == '„Hund“ ist mir als Thema bekannt.'\n"
            "\n"
            "def test_ohne_subject_ehrlich_none():\n"
            "    assert zelle_thema_echo(None, {'subject': None}, 'egal', None, None) is None\n"
            "    assert zelle_thema_echo(None, {}, 'egal', None, None) is None\n"
        ),
    },
    {
        "blatt": "verbindungs-zahl",
        "beschreibung": (
            "Zähle in der Tabelle relation_projection (Spalten: subject, predicate, "
            "object) die Zeilen, deren subject gleich guess['subject'] ist. Bei Anzahl "
            "n > 0 gib genau 'Zu „<subject>“ kenne ich <n> Verbindung(en).' zurück, "
            "bei 0 oder fehlendem subject gib None zurück."
        ),
        "test": (
            "import sqlite3\n"
            "from zelle_verbindungs_zahl import zelle_verbindungs_zahl\n"
            "\n"
            "def _conn():\n"
            "    c = sqlite3.connect(':memory:')\n"
            "    c.row_factory = sqlite3.Row\n"
            "    c.execute('CREATE TABLE relation_projection "
            "(subject TEXT, predicate TEXT, object TEXT)')\n"
            "    c.executemany('INSERT INTO relation_projection VALUES (?,?,?)',\n"
            "                  [('Q144','is_a','Q_pet'), ('Q144','label','Hund'),\n"
            "                   ('Q42','is_a','Q5')])\n"
            "    return c\n"
            "\n"
            "def test_zaehlt():\n"
            "    s = zelle_verbindungs_zahl(_conn(), {'subject': 'Q144'}, 'egal', None, None)\n"
            "    assert s == 'Zu „Q144“ kenne ich 2 Verbindung(en).'\n"
            "\n"
            "def test_unbekannt_ehrlich_none():\n"
            "    assert zelle_verbindungs_zahl(_conn(), {'subject': 'Q999'}, 'egal', "
            "None, None) is None\n"
        ),
    },
    {
        "blatt": "erste-verbindung",
        "beschreibung": (
            "Suche in relation_projection (subject, predicate, object) die Zeilen mit "
            "subject gleich guess['subject'] und predicate gleich 'is_a', alphabetisch "
            "nach object sortiert. Gibt es welche, gib genau '„<subject>“ ist ein "
            "<erstes object>.' zurück; sonst None. Fehlt guess['subject'], gib None."
        ),
        "test": (
            "import sqlite3\n"
            "from zelle_erste_verbindung import zelle_erste_verbindung\n"
            "\n"
            "def _conn():\n"
            "    c = sqlite3.connect(':memory:')\n"
            "    c.row_factory = sqlite3.Row\n"
            "    c.execute('CREATE TABLE relation_projection "
            "(subject TEXT, predicate TEXT, object TEXT)')\n"
            "    c.executemany('INSERT INTO relation_projection VALUES (?,?,?)',\n"
            "                  [('Hund','is_a','Tier'), ('Hund','is_a','Haustier'),\n"
            "                   ('Hund','label','Hund')])\n"
            "    return c\n"
            "\n"
            "def test_erste_alphabetisch():\n"
            "    s = zelle_erste_verbindung(_conn(), {'subject': 'Hund'}, 'egal', None, None)\n"
            "    assert s == '„Hund“ ist ein Haustier.'\n"
            "\n"
            "def test_ohne_treffer_none():\n"
            "    assert zelle_erste_verbindung(_conn(), {'subject': 'Katze'}, 'egal', "
            "None, None) is None\n"
        ),
    },
]


def _pruefe(code: str, aufgabe: dict) -> bool:
    name = aufgabe["blatt"].replace("-", "_")
    with tempfile.TemporaryDirectory() as sandbox:
        (Path(sandbox) / f"zelle_{name}.py").write_text(code, encoding="utf-8")
        testdatei = Path(sandbox) / f"test_zelle_{name}.py"
        testdatei.write_text(aufgabe["test"], encoding="utf-8")
        lauf = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(testdatei)],
            cwd=sandbox, capture_output=True, text=True, timeout=120,
        )
        return lauf.returncode == 0


def benchmark(modelle: list[str], modus: str = "code") -> None:
    """``modus="code"``: das Modell schreibt den Handler direkt (Schmied v1).
    ``modus="bauplan"``: das Modell füllt nur den morphologischen Bauplan, das
    deterministische Fügewerk (genus/bauplan.py) baut den Code (Ronnys Zerlegung,
    Schmied v2) -- der A/B-Vergleich derselben Aufgaben und Modelle."""
    if modus == "bauplan":
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from genus import bauplan as fuegewerk
    for modell in modelle:
        schmied.MODEL_PATH = modell
        schmied._model = None   # frisches, warmes Modell pro Kandidat
        name = Path(modell).name
        bestanden = 0
        start = time.time()
        for aufgabe in AUFGABEN:
            if modus == "bauplan":
                plan = schmied.schmiede_bauplan(aufgabe["blatt"], aufgabe["beschreibung"])
                if plan is None:
                    print(f"[BENCH:{modus}] {name}  {aufgabe['blatt']:<20} kein JSON")
                    continue
                try:
                    code = fuegewerk.fuege_zusammen(aufgabe["blatt"], plan)
                except ValueError as exc:
                    print(f"[BENCH:{modus}] {name}  {aufgabe['blatt']:<20} "
                          f"Bauplan ungültig ({str(exc).splitlines()[1][:60]})")
                    continue
            else:
                code = schmied.schmiede(aufgabe["blatt"], aufgabe["beschreibung"])
                if code is None:
                    print(f"[BENCH:{modus}] {name}  {aufgabe['blatt']:<20} "
                          f"LEITPLANKE (kein Entwurf)")
                    continue
            ok = _pruefe(code, aufgabe)
            bestanden += ok
            print(f"[BENCH:{modus}] {name}  {aufgabe['blatt']:<20} "
                  f"{'BESTANDEN' if ok else 'tests rot'}")
        dauer = time.time() - start
        print(f"[BENCH:{modus}] {name}  => {bestanden}/{len(AUFGABEN)} in {dauer:.0f}s")


if __name__ == "__main__":
    argumente = sys.argv[1:]
    modus = "code"
    if argumente and argumente[0] == "--bauplan":
        modus = "bauplan"
        argumente = argumente[1:]
    if not argumente:
        print(__doc__)
        sys.exit(2)
    benchmark(argumente, modus)
