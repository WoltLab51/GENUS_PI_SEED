"""Selbst-Codieren Stufe 1: ein genehmigtes Proposal wird UMGESETZT — der Kreis
„spüren → vorschlagen → fragen → BAUEN" endet nicht mehr an der Freigabe.

Was GENUS heute sicher selbst bauen kann, ist GRAPH-WISSEN (Hüllen-Daten, nie Code —
Code bleibt Stufe 2). Ein Proposal trägt dafür ein deklaratives ``umsetzung``-Feld
(``{"art": ..., ...}``); nach der Governance-Freigabe führt :func:`umsetzen` die
registrierte Umsetzungs-Art aus. Das Register (``UMSETZUNGEN``) ist dasselbe
Kern-Primitiv wie überall: registrieren → nachschlagen — eine neue Art wird
registriert, nicht in eine if-Kette geschrieben.

Die Gate-Politik (aktueller Vertrag: docs/ARCHITECTURE.md §8; historische Herkunft:
docs/history/TARGET_ARCHITECTURE_2026-07-04.md §8, Ronnys „entwickelt sich") ist hier
STRUKTURELL verankert, nicht per Konvention:
- Freigabe pro Stück: :func:`umsetzen` weigert sich bei allem außer einem
  AKZEPTIERTEN Proposal — die menschliche Freigabe über die bestehende
  Governance-Maschinerie IST das Gate, es gibt keinen Weg daran vorbei.
- Der fixe Boden: das Register enthält ausschließlich Arten, die Graph-Wissen
  säen (über den normalen, geprüften Schreibpfad). Eine Art mit Außenwirkung
  (Geld, Nachrichten, System) kann hier nicht einmal ausgedrückt werden.
- Idempotenz: eine schon umgesetzte Freigabe wird nie doppelt ausgeführt
  (``proposal_umgesetzt``-Event als Ausführungs-Spur, bewusst roh — die Wirkung
  selbst sind ganz normale, projizierte relation_asserted-Events).

Erste registrierte Art: ``faehigkeits_ziel`` — die vom VerstehensLuecke-Detector
gespürte und von Ronny freigegebene Lücke wird eine benannte Fähigkeit im
Ziel-Graphen (Status „fehlt", dient ``ziel:verstehen``). Ab dem Moment benennt
GENUS sie selbst, wenn man es fragt, was ihm fehlt.
"""
from __future__ import annotations

import json
from typing import Callable

from genus import ledger, proposals, ziele

UMSETZUNG_EVENT = "proposal_umgesetzt"
STUFE1_SOURCE = "genus:stufe1"   # ehrliche Herkunft: von GENUS selbst gesät, nach Freigabe


def _setze_faehigkeits_ziel(conn, umsetzung: dict) -> dict:
    """Art „faehigkeits_ziel": sät die freigegebene Lücke als Fähigkeit in den
    Ziel-Graphen — über den normalen Schreibpfad (sae_fehlende: Herkunft, Prüfungen),
    mit eigener Quelle (nie als Ronnys Saat ausgegeben)."""
    from genus import reactors

    blatt = umsetzung["blatt"]
    beschreibung = umsetzung.get(
        "beschreibung",
        f"Eine Fähigkeit für die Verstehens-Lesart „{blatt}“ — von GENUS selbst "
        f"erspürt (Belegung) und nach Freigabe hier verankert.",
    )
    knoten = f"{ziele.FAEHIGKEIT_PREFIX}{blatt}"
    neu = reactors.sae_fehlende(conn, [
        (knoten, ziele.INHALT, beschreibung),
        (knoten, ziele.STATUS, "fehlt"),
        ("ziel:verstehen", ziele.BRAUCHT, knoten),
    ], STUFE1_SOURCE)
    # Die BRÜCKE zur Werkstatt (Ronny, 2026-07-04): dieselbe Freigabe legt auch das
    # Entwurfs-Paar bereit -- inert (läuft nie von allein), Verbots-Scan + Sandbox-
    # Probefahrt + menschlicher Merge wie bei jedem Entwurf; das Gate war die Freigabe
    # eben. Ein Scheitern hier kippt die Umsetzung NICHT (das Ziel-Wissen steht) --
    # es wird ehrlich im Ergebnis benannt, der Entwurf lässt sich von Hand nachholen.
    try:
        from genus import werkstatt
        entwurf = werkstatt.entwerfe_zelle(conn, blatt, quelle="werkstatt:umsetzung")
    except Exception as exc:
        entwurf = {"erstellt": False, "grund": f"Entwurf gescheitert: {exc}"}
    return {"faehigkeit": knoten, "neue_kanten": neu, "entwurf": entwurf}


# Das Umsetzungs-Register: Art -> reine Funktion (conn, umsetzung) -> Ergebnis-Dict.
# Ausschließlich Graph-Wissen-Arten -- der fixe Boden der Gate-Politik ist die Form
# dieses Registers selbst, keine Laufzeit-Prüfung, die man vergessen könnte.
UMSETZUNGEN: dict[str, Callable] = {
    "faehigkeits_ziel": _setze_faehigkeits_ziel,
}


def bereits_umgesetzt(conn, proposal_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM event_log WHERE event_type = ? "
        "AND json_extract(payload, '$.proposal_id') = ? LIMIT 1",
        (UMSETZUNG_EVENT, proposal_id),
    ).fetchone()
    return row is not None


def umsetzen(conn, proposal_id: int) -> dict:
    """Führt die Umsetzung eines AKZEPTIERTEN Proposals aus — genau einmal.

    Rückgabe: ``{"umgesetzt": True, "ergebnis": ...}`` bei Erfolg;
    ``{"umgesetzt": False, "grund": ...}`` wenn es (noch) nichts umzusetzen gibt —
    kein Fehler: die meisten Proposals tragen (noch) kein umsetzung-Feld, eine
    Ablehnung setzt nie um, eine zweite Freigabe führt nie doppelt aus."""
    proposal = proposals.get_proposal(conn, proposal_id)
    if proposal["state"] != proposals.ACCEPTED:
        return {"umgesetzt": False, "grund": f"Proposal ist {proposal['state']}, "
                                             f"nicht {proposals.ACCEPTED} — das Gate zuerst"}
    payload = json.loads(proposal["payload"])
    umsetzung = payload.get("umsetzung")
    if not isinstance(umsetzung, dict) or "art" not in umsetzung:
        return {"umgesetzt": False, "grund": "Proposal trägt keine Umsetzung"}
    if bereits_umgesetzt(conn, proposal_id):
        return {"umgesetzt": False, "grund": "schon umgesetzt (genau einmal, nie doppelt)"}
    art = umsetzung["art"]
    ausfuehrung = UMSETZUNGEN.get(art)
    if ausfuehrung is None:
        return {"umgesetzt": False,
                "grund": f"Umsetzungs-Art „{art}“ ist nicht registriert — nichts "
                         f"Unregistriertes wird je ausgeführt"}
    ergebnis = ausfuehrung(conn, umsetzung)
    ledger.append(conn, UMSETZUNG_EVENT, {
        "proposal_id": proposal_id,
        "art": art,
        "ergebnis": ergebnis,
    })
    conn.commit()
    return {"umgesetzt": True, "art": art, "ergebnis": ergebnis}
