"""Klassen-Waechter fuer die Zeilenenden byte-verglichener Artefakte.

Live-Fund 2026-08-20: `test_alltagsprobe.py::test_generated_answer_quality_report_is_byte_exact`
scheiterte auf jedem Windows-Checkout mit `core.autocrlf=true`. Der Test vergleicht
`docs/generated/ANTWORTQUALITAET.md` byteweise gegen einen frischen LF-Render; die
.gitattributes deckte damals aber nur `tests/fixtures/golden_ledger_v1/*` ab, also
materialisierte git die Datei mit CRLF. Der Fehler sagt nichts ueber den Code aus --
er ist reine Checkout-Kosmetik und verdeckt echte Regressionen.

Die Klasse ist: *jedes committete Artefakt, dessen Bytes ein Test behauptet, muss auf
jeder Plattform mit LF im Arbeitsbaum landen.* Dieser Waechter leitet die Menge aus den
Wahrheitsquellen ab (die Support-Module und `git ls-files`), nicht aus einer gepflegten
Liste -- ein neu hinzugefuegtes generiertes Artefakt ist damit automatisch abgedeckt.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tests import golden_ledger_support as golden
from tests import historical_sqlite_support as historical


ROOT = Path(__file__).resolve().parents[1]


def _git(*args: str) -> str:
    git = shutil.which("git")
    if git is None:
        pytest.skip("kein git verfuegbar")
    fertig = subprocess.run([git, *args], cwd=ROOT, capture_output=True, text=True)
    if fertig.returncode != 0:
        pytest.skip("kein git-Checkout")
    return fertig.stdout


def _attribute(pfade: list[str]) -> dict[str, dict[str, str]]:
    """Effektive text/eol-Attribute -- egal, welche .gitattributes sie liefert."""
    roh = _git("check-attr", "-z", "text", "eol", "--", *pfade)
    felder = roh.split("\0")
    ergebnis: dict[str, dict[str, str]] = {}
    for pfad, attribut, wert in zip(felder[0::3], felder[1::3], felder[2::3]):
        ergebnis.setdefault(pfad, {})[attribut] = wert
    return ergebnis


def _relativ(pfad: Path) -> str:
    return pfad.resolve().relative_to(ROOT).as_posix()


def _byte_verglichene_textartefakte() -> list[str]:
    # 1. Alles unter docs/generated/ ist deterministische Projektion des Codes und wird
    #    gegen einen frischen Render geprueft (ANTWORTQUALITAET.md byteweise).
    generiert = [zeile for zeile in _git("ls-files", "--", "docs/generated").splitlines() if zeile]
    # 2. Die Golden-Ledger-Artefakte -- golden_ledger_support liest sie als Bytes ein.
    golden_artefakte = [
        _relativ(golden.FIXTURE_ROOT / name) for name in golden.ARTIFACT_NAMES
    ]
    # 3. Die historische SQLite-Fixture; die .sqlite3 selbst ist bewusst binaer (siehe unten).
    historisch = [
        _relativ(pfad)
        for pfad in (
            historical.EVENTS_PATH,
            historical.SCHEMA_PATH,
            historical.MANIFEST_PATH,
            historical.REVIEW_PATH,
            historical.README_PATH,
        )
    ]
    return sorted(set(generiert + golden_artefakte + historisch))


def test_byte_verglichene_artefakte_sind_als_lf_deklariert():
    pfade = _byte_verglichene_textartefakte()
    # das Muster greift wirklich: der Ausloeser des Fundes ist enthalten
    assert "docs/generated/ANTWORTQUALITAET.md" in pfade
    assert "tests/fixtures/golden_ledger_v1/events.jsonl" in pfade
    assert len(pfade) >= 15

    attribute = _attribute(pfade)
    for pfad in pfade:
        assert attribute.get(pfad, {}).get("eol") == "lf", (
            f"{pfad} wird byteweise verglichen, traegt aber kein `text eol=lf` "
            f"(effektiv: {attribute.get(pfad)}) -> auf einem Windows-Checkout mit "
            f"core.autocrlf=true materialisiert git CRLF und der Byte-Vergleich scheitert"
        )


def test_byte_verglichene_artefakte_liegen_im_arbeitsbaum_als_lf():
    # Der Attributtest oben faellt auf jeder Plattform; dieser hier reproduziert den
    # eigentlichen Fund und faellt genau dort, wo er weh tut -- im echten Arbeitsbaum.
    for pfad in _byte_verglichene_textartefakte():
        datei = ROOT / pfad
        if not datei.exists():
            continue
        assert b"\r" not in datei.read_bytes(), (
            f"{pfad} liegt im Arbeitsbaum mit CR -- ein neu gesetztes eol-Attribut wirkt erst "
            f"beim naechsten Auschecken, vorhandene Dateien bleiben unveraendert liegen. "
            f"Gezielt neu materialisieren: `rm {pfad} && git checkout -- {pfad}`"
        )


def test_binaere_fixture_bleibt_von_der_textnormalisierung_ausgenommen():
    # Die Kehrseite derselben Klasse: eine als Text behandelte SQLite-Datei wuerde von der
    # CRLF-Normalisierung zerstoert. Sie muss ausdruecklich `binary` (text: unset) sein.
    pfad = _relativ(historical.DATABASE_PATH)
    attribute = _attribute([pfad])
    assert attribute.get(pfad, {}).get("text") == "unset", (
        f"{pfad} ist eine SQLite-Datei und muss `binary` deklariert sein "
        f"(effektiv: {attribute.get(pfad)}) -> sonst beschaedigt git sie beim Checkout"
    )
