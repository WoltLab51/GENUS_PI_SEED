"""Selbst-Codieren Stufe 2, Scheibe 1: die WERKSTATT — wo Code-Entwürfe entstehen,
geprüft werden und auf den menschlichen Merge warten.

Die Leitplanke (docs/GENUS_ROADMAP.md) ist hier Gesetz, nicht Konvention: **kein
selbstmodifizierender Code außerhalb einer Sandbox mit menschlichem Merge.** Strukturell
verankert:

- Entwürfe leben in einem eigenen Verzeichnis AUSSERHALB des Kerns (``~/.genus/werkstatt``,
  ``GENUS_WERKSTATT``). Die Werkstatt schreibt nie nach ``genus/`` — sie KANN es nicht,
  ihre Pfade zeigen woandershin. Teil der Hülle wird ein Entwurf ausschließlich durch
  einen menschlichen Git-Merge.
- Ein Entwurf läuft nie im lebenden Prozess — und der Kern startet auch keinen: die
  PROBEFAHRT (Sandbox-pytest im Subprozess) fährt die Membran
  (``deploy/werkstatt_probefahrt.sh``), der Kern protokolliert nur das überreichte
  Ergebnis — dasselbe Muster wie beim Uhr-Check (die Membran misst, der Kern records).
  Der Membran-Reinheits-Test hat genau das erzwungen: subprocess ist im Kern verboten.
- Vor jeder Protokollierung läuft der deterministische VERBOTS-SCAN im Kern: dieselben
  Modell-/Netz-Tokens, die der Doctor im Kern verbietet, plus die Prozess-/Netz-
  Grundbausteine, mit denen ein Entwurf aus der Sandbox ausbrechen könnte. Ein Entwurf
  mit Verboten kann nie „bestanden" werden, egal was seine Tests sagen.
- Der GENERATOR ist ein austauschbarer Einschub (``generator=``-Parameter, wie ``deuter=``
  im Companion): heute eine deterministische VORLAGE (Handler-Skelett mit dem uniformen
  Zellen-Vertrag + Test-Skelett mit Signatur-Pin), später ein lokales Code-Modell — ein
  Konfig-Schalter, kein Umbau. Das Organ darf ALLES vorschlagen und NICHTS entscheiden;
  die Werkstatt IST die entscheidende Struktur.
- Die ENTSCHEIDUNGS-SPUR liegt im Ledger (``code_entwurf_erstellt`` /
  ``code_entwurf_geprueft``, bewusst roh, mit Code-Fingerabdruck) — der Code selbst bleibt
  Randmaterial wie Modellgewichte und Korrektur-Beispiele: löschbar, nicht versiegelt.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from genus import abnahme, doctor, ledger

ENTWURF_EVENT = "code_entwurf_erstellt"
PRUEFUNG_EVENT = "code_entwurf_geprueft"

# Dieselben Verbote wie im Kern (doctor), plus die Grundbausteine, mit denen ein Entwurf
# aus der Sandbox ausbrechen könnte. Die Tokens kommen zur Laufzeit aus doctor (dort
# geteilt geschrieben, damit der Doctor-Scan sich nicht selbst auslöst).
_VERBOTENE_TOKENS = (
    doctor.FORBIDDEN_MODEL_TOKENS
    + doctor.FORBIDDEN_NETWORK_TOKENS
    + ("sub" + "process", "sock" + "et", "os." + "system", "ur" + "llib")
)


def verzeichnis() -> Path:
    """Wo die Entwürfe wohnen -- außerhalb des Repos, neben dem Ledger."""
    explicit = os.environ.get("GENUS_WERKSTATT")
    if explicit:
        return Path(explicit)
    return Path(os.path.expanduser("~")) / ".genus" / "werkstatt"


def _fingerabdruck(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _vorlage_handler(blatt: str) -> str:
    """Der deterministische Default-Generator: ein ehrliches Handler-Skelett mit dem
    uniformen Zellen-Vertrag. Ein Modell-Generator ersetzt genau diese Funktion."""
    name = blatt.replace("-", "_")
    return (
        f'"""Entwurf: Gesprächszelle „{blatt}“ — erzeugt von GENUS\' Werkstatt (Stufe 2).\n'
        f"\n"
        f"Dieser Entwurf läuft NIE automatisch: er lebt außerhalb des Kerns, wird in der\n"
        f"Werkstatt geprüft (Verbots-Scan + Sandbox-Probefahrt) und wird erst durch einen\n"
        f"menschlichen Git-Merge Teil der Hülle.\n"
        f'"""\n'
        f"\n"
        f"\n"
        f"def zelle_{name}(conn, guess, question, last_question, last_answer, stimme=None):\n"
        f"    # Der Zellen-Vertrag: liest nur aus dem Graphen (conn), erfindet nie Fakten,\n"
        f"    # gibt einen deutschen Antwortsatz zurück -- oder None (ehrliches Passen).\n"
        f"    # TODO (Generator oder Mensch): die eigentliche Fähigkeit.\n"
        f"    return None\n"
    )


def _vorlage_test(blatt: str) -> str:
    name = blatt.replace("-", "_")
    return (
        f'"""Sandbox-Tests für den Entwurf „{blatt}“ -- laufen NUR in der Werkstatt\n'
        f"(deploy/werkstatt_probefahrt.sh), nie im lebenden Prozess.\"\"\"\n"
        f"import inspect\n"
        f"\n"
        f"import pytest\n"
        f"\n"
        f"from zelle_{name} import zelle_{name}\n"
        f"\n"
        f"\n"
        f"def test_vertrag_signatur():\n"
        f"    # der uniforme Zellen-Vertrag (wie werkzeug.pruefen ihn prüfen wird)\n"
        f"    parameter = list(inspect.signature(zelle_{name}).parameters)\n"
        f'    assert parameter == ["conn", "guess", "question", "last_question",\n'
        f'                         "last_answer", "stimme"]\n'
        f"\n"
        f"\n"
        f"def test_faehigkeit():\n"
        f"    # TODO (Generator oder Mensch): der eigentliche Fähigkeits-Test.\n"
        f'    pytest.skip("Entwurf: Fähigkeit noch nicht gebaut")\n'
    )


def entwerfe_zelle(conn, blatt: str, generator=None, quelle: str | None = None,
                   vertrag=None) -> dict:
    """Erzeugt ein Entwurfs-Paar (Handler + Sandbox-Test) für ein Raster-Blatt und
    protokolliert die Entscheidung im Ledger. Weigert sich, einen bestehenden Entwurf
    zu überschreiben (ein Entwurf ist Arbeitsstand -- Löschen ist eine menschliche,
    bewusste Handlung im Dateisystem). ``generator``: ``(blatt) -> code`` für den
    Handler-Teil; Default ist die deterministische Vorlage. ``quelle`` überschreibt die
    Herkunfts-Angabe in der Ledger-Spur (z.B. ``werkstatt:schmied``, wenn die Membran
    den Code eines Code-Modells überreicht).

    ``vertrag`` (:class:`genus.abnahme.Abnahmevertrag`, optional): der forger-UNABHÄNGIGE
    Erwartungssatz. Ist einer da, wird statt des geskippten Vorlage-Tests ein echter
    VERHALTENS-Test erzeugt (``abnahme.baue_test``) -- erst der macht „bestanden" zu einer
    Aussage über Korrektheit. Ein nicht prüfbarer Vertrag lässt gar nichts entstehen."""
    name = blatt.replace("-", "_")
    ziel = verzeichnis()
    handler_pfad = ziel / f"zelle_{name}.py"
    test_pfad = ziel / f"test_zelle_{name}.py"
    if handler_pfad.exists() or test_pfad.exists():
        return {"erstellt": False,
                "grund": f"Entwurf für „{blatt}“ existiert schon ({handler_pfad}) — "
                         f"Überschreiben ist eine menschliche Entscheidung."}
    if vertrag is not None:
        maengel = abnahme.pruefe_vertrag(vertrag)
        if maengel:
            return {"erstellt": False,
                    "grund": "Abnahme-Vertrag nicht prüfbar:\n" + "\n".join(maengel)}
        test_code = abnahme.baue_test(vertrag)
    else:
        test_code = _vorlage_test(blatt)
    ziel.mkdir(parents=True, exist_ok=True)
    erzeuger = generator or _vorlage_handler
    handler_code = erzeuger(blatt)
    handler_pfad.write_text(handler_code, encoding="utf-8")
    test_pfad.write_text(test_code, encoding="utf-8")
    if quelle is None:
        quelle = "werkstatt:vorlage" if generator is None else "werkstatt:generator"
    ledger.append(conn, ENTWURF_EVENT, {
        "blatt": blatt,
        "pfad": str(handler_pfad),
        "fingerabdruck": _fingerabdruck(handler_code),
        "test_fingerabdruck": _fingerabdruck(test_code),
        "quelle": quelle,
        "abnahme": vertrag is not None,
    })
    conn.commit()
    return {"erstellt": True, "handler": str(handler_pfad), "test": str(test_pfad),
            "quelle": quelle, "abnahme": vertrag is not None}


def liste() -> list[dict]:
    """Alle Entwürfe in der Werkstatt (Handler-Dateien), mit Fingerabdruck."""
    ziel = verzeichnis()
    if not ziel.is_dir():
        return []
    eintraege = []
    for pfad in sorted(ziel.glob("zelle_*.py")):
        code = pfad.read_text(encoding="utf-8")
        eintraege.append({
            "blatt": pfad.stem[len("zelle_"):].replace("_", "-"),
            "pfad": str(pfad),
            "fingerabdruck": _fingerabdruck(code),
        })
    return eintraege


def _verbots_scan(code: str) -> list[str]:
    return sorted({token for token in _VERBOTENE_TOKENS if token in code})


def _letzter_entwurf(conn, blatt: str) -> dict | None:
    """Der jüngste Entwurfs-Eintrag für ein Blatt aus dem VERSIEGELTEN Ledger -- die
    fälschungssichere Quelle für „lag beim Entwurf ein Abnahme-Vertrag vor, und welchen
    Test-Fingerabdruck hatte er". Der Werkstatt-Ordner ist löschbares Randmaterial; der
    Ledger nicht (append-only, gesiegelt) -- darum wird die Verhaltens-Klinke HIER verankert,
    nicht an einer Marke in der mutierbaren Datei (Review-Fund 2026-07-07)."""
    row = conn.execute(
        "SELECT payload FROM event_log WHERE event_type = ? "
        "AND json_extract(payload, '$.blatt') = ? ORDER BY id DESC LIMIT 1",
        (ENTWURF_EVENT, blatt),
    ).fetchone()
    return json.loads(row[0]) if row else None


def protokolliere_pruefung(conn, blatt: str, tests_exit: int | None = None) -> dict:
    """Die Prüfung eines Entwurfs, als Entscheidungs-Spur protokolliert. Der VERBOTS-SCAN
    läuft immer hier im Kern (deterministisch, zum Zeitpunkt der Protokollierung, gegen
    den aktuellen Datei-Stand). ``tests_exit`` ist das Ergebnis der Sandbox-PROBEFAHRT,
    die die Membran gefahren hat (``deploy/werkstatt_probefahrt.sh``) -- ``None`` heißt:
    noch nicht probegefahren, nur statisch geprüft. „Bestanden" (merge-REIF, nie gemergt:
    der Merge bleibt menschlich) verlangt jetzt DREI Klinken: keine Verbote, tests_exit == 0
    UND einen Abnahme-Vertrag (der Test prueft wirklich VERHALTEN, nicht nur die Signatur)."""
    name = blatt.replace("-", "_")
    handler_pfad = verzeichnis() / f"zelle_{name}.py"
    if not handler_pfad.exists():
        return {"gefunden": False,
                "grund": f"kein Entwurf für „{blatt}“ in {verzeichnis()}"}
    code = handler_pfad.read_text(encoding="utf-8")
    verbote = _verbots_scan(code)
    # die dritte, VERHALTENS-Klinke (Ronny 2026-07-07) muss BINDEND sein, nicht bloss eine Marke:
    # ein Substring in der Datei ist faelschbar (Review-Fund HOCH -- ein untergeschobener Skip-Test
    # mit der Marke kaeme sonst durch). Der Anker ist der versiegelte Ledger-Eintrag des Entwurfs:
    # (a) beim Entwurf lag ein echter Abnahme-Vertrag vor UND (b) die Test-Datei ist BYTE-genau
    # noch die damals erzeugte (Fingerabdruck-Abgleich gegen das Ledger). Ohne Entwurfs-Eintrag
    # oder bei veraenderter Test-Datei traegt tests_exit==0 keine Verhaltens-Aussage -> kein bestanden.
    test_pfad = verzeichnis() / f"test_zelle_{name}.py"
    test_code = test_pfad.read_text(encoding="utf-8") if test_pfad.exists() else ""
    entwurf = _letzter_entwurf(conn, blatt)
    abnahme_vorhanden = bool(
        entwurf and entwurf.get("abnahme")
        and entwurf.get("test_fingerabdruck") == _fingerabdruck(test_code)
    )
    bestanden = not verbote and tests_exit == 0 and abnahme_vorhanden
    ledger.append(conn, PRUEFUNG_EVENT, {
        "blatt": blatt,
        "pfad": str(handler_pfad),
        "fingerabdruck": _fingerabdruck(code),
        "verbote": verbote,
        "tests_exit": tests_exit,
        "abnahme": abnahme_vorhanden,
        "bestanden": bestanden,
    })
    conn.commit()
    return {"gefunden": True, "blatt": blatt, "verbote": verbote,
            "tests_exit": tests_exit, "abnahme": abnahme_vorhanden, "bestanden": bestanden}
