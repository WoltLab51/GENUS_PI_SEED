"""Der Registry-Vertragstest -- der echte Wächter der Router-Migration (Naht 3,
docs/GENUS_ARCHITEKTUR.md §8).

Der Replay-Determinismus-Test (test_integrity) fängt eine VERPFUSCHTE Migration: weicht
das Register vom alten Verhalten ab, wird er rot. Aber eine später VERGESSENE
Registrierung fehlt auf beiden Seiten des Vergleichs -- beide einig, grün, obwohl falsch.
Dieser Test schließt genau die Lücke: er liest aus dem QUELLTEXT, welche Event-Typen
irgendwo im Kern je geschrieben werden (``ledger.append``-Literale, konstanten-aufgelöst,
plus der eine bewusste Direkt-INSERT der Siegel-Epoche), und erzwingt, dass jeder davon
in GENAU EINER der beiden Router-Mengen steht: ``PROJEKTOREN`` (projiziert) oder
``BEWUSST_ROH`` (mit Absicht und dokumentiertem Grund roh). Ein neuer Event-Typ ohne
diese Entscheidung bricht CI -- und ein Tippfehler in einem Register-Schlüssel auch
(er entspräche keinem je geschriebenen Typ).
"""
import re
from pathlib import Path

import pytest

from genus import event_router, integrity

ROOT = Path(__file__).resolve().parents[1]

_LITERAL = re.compile(r'ledger\.append\(\s*conn,\s*"([a-z_]+)"')
_KONSTANTE = re.compile(r"ledger\.append\(\s*conn,\s*([A-Z][A-Z_]*)\b")


def _geschriebene_event_typen() -> set[str]:
    typen: set[str] = set()
    for py in sorted((ROOT / "genus").glob("*.py")):
        text = py.read_text(encoding="utf-8")
        typen.update(_LITERAL.findall(text))
        for name in _KONSTANTE.findall(text):
            wert = re.search(rf'^{name} = "([a-z_]+)"', text, re.MULTILINE)
            assert wert is not None, (
                f"{py.name}: ledger.append mit Konstante {name}, deren Wert dieser Test "
                f"nicht auflösen kann -- Konstante im selben Modul als NAME = \"...\" definieren"
            )
            typen.add(wert.group(1))
    # Der eine bewusste Weg an ledger.append vorbei: sealing.open_epoch schreibt den
    # Epochen-Marker direkt (die Versiegelung IST der Mechanismus unter dem Ledger).
    typen.add("ledger_epoch_opened")
    return typen


def test_jeder_geschriebene_event_typ_ist_entschieden():
    geschrieben = _geschriebene_event_typen()
    projiziert = set(event_router.PROJEKTOREN)
    roh = set(event_router.BEWUSST_ROH)

    assert not (projiziert & roh), (
        f"Event-Typen in BEIDEN Mengen (eine Entscheidung, nicht zwei): {projiziert & roh}"
    )
    unentschieden = geschrieben - projiziert - roh
    assert not unentschieden, (
        f"Event-Typen ohne Entscheidung (projiziert oder bewusst roh?): {unentschieden} "
        f"-- in event_router.PROJEKTOREN registrieren ODER mit Grund in BEWUSST_ROH aufnehmen"
    )
    tote_schluessel = (projiziert | roh) - geschrieben
    assert not tote_schluessel, (
        f"Register-Schlüssel, die kein Code je schreibt (Tippfehler oder tot): {tote_schluessel}"
    )


def test_jeder_geschriebene_event_typ_ist_dem_integritaets_vertrag_bekannt():
    # Die ZWEITE Registrierung, die ein neuer Event-Typ braucht: integrity.check kennzeichnet
    # JEDEN Typ ohne Eintrag in REQUIRED_EVENT_KEYS als „unknown event_type" -> [FAIL] integrity.
    # Router-Entscheidung UND Integritäts-Vertrag sind getrennte Register; die hand_*-Typen waren
    # im Router entschieden, aber nicht hier -> genus doctor wäre auf dem echten Ledger rot geworden,
    # sobald die erste Hand existiert. Dieser Wächter schließt genau diese zweite Lücke.
    geschrieben = _geschriebene_event_typen()
    bekannt = set(integrity.REQUIRED_EVENT_KEYS)
    fehlend = geschrieben - bekannt
    assert not fehlend, (
        "Event-Typen, die geschrieben werden, aber integrity.REQUIRED_EVENT_KEYS nicht kennt "
        f"(integrity.check wiese sie als 'unknown event_type' ab -> doctor rot): {fehlend}"
    )


def test_registrierung_ist_die_eine_tuer():
    def fake_projektor(conn, payload):   # pragma: no cover - nie aufgerufen
        pass

    # idempotent für dieselbe Funktion
    event_router.registriere_projektor("test_nur_hier", fake_projektor)
    try:
        event_router.registriere_projektor("test_nur_hier", fake_projektor)
        # ein ABWEICHENDER Eintrag für einen belegten Typ schlägt laut fehl
        with pytest.raises(ValueError, match="schon registriert"):
            event_router.registriere_projektor("test_nur_hier", lambda conn, payload: None)
    finally:
        del event_router.PROJEKTOREN["test_nur_hier"]

    # ein bewusst-roher Typ lässt sich nicht nebenbei projizieren
    with pytest.raises(ValueError, match="bewusst-roh"):
        event_router.registriere_projektor("forecast_made", fake_projektor)


def test_apply_event_schlaegt_im_register_nach(conn):
    gesehen: list[str] = []
    event_router.PROJEKTOREN["test_register_typ"] = (
        lambda c, payload: gesehen.append(payload["wert"])
    )
    try:
        conn.execute(
            "INSERT INTO event_log (event_type, payload) VALUES (?, ?)",
            ("test_register_typ", '{"wert": "angekommen"}'),
        )
        row = conn.execute(
            "SELECT * FROM event_log WHERE event_type = 'test_register_typ'"
        ).fetchone()
        event_router.apply_event(conn, row)
        assert gesehen == ["angekommen"]
    finally:
        del event_router.PROJEKTOREN["test_register_typ"]


def test_unbekannter_typ_bleibt_still(conn):
    # exakt das alte Verhalten der Kette: kein Zweig -> kein Effekt (die bewusst-rohen
    # Typen laufen beim Replay hier durch und dürfen nichts tun)
    conn.execute(
        "INSERT INTO event_log (event_type, payload) VALUES (?, ?)",
        ("voellig_unbekannter_typ", "{}"),
    )
    row = conn.execute(
        "SELECT * FROM event_log WHERE event_type = 'voellig_unbekannter_typ'"
    ).fetchone()
    event_router.apply_event(conn, row)   # darf schlicht nicht werfen
