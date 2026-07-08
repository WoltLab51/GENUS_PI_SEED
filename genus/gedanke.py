"""Der proaktive GEDANKE (Ronny 2026-07-08: „solche Vorschläge sollten kommen, wenn GENUS es parat
hat, nicht erst am nächsten Morgen" — und „der Morgengruß soll ein schöner Gruß sein").

GENUS schickt dir das WICHTIGE, sobald es das hat, statt es bis zum Morgen aufzustauen. „Nur das
Wichtige" (Ronnys Wahl): Entscheidungs-Vorschläge (``action_required``) und die Begriffs-Fragen, die
GENUS sich SELBST bildet (:data:`inquiries.ABSTRAKTION_INQUIRY_TYPE`). Betriebs-Rauschen und innere
Widersprüche bleiben draußen (nur auf Nachfrage, „Was beschäftigt dich?").

Der Weg ist die erste HAND (:mod:`genus.hand`): ein Gedanke wird eine bestätigte Nachricht-Hand,
fällig JETZT (Ronnys Wahl „immer sofort, auch nachts"); der Membran-Cron sendet sie binnen ~2 min.
Auto-bestätigt unter Ronnys STEHENDER Erlaubnis (dieser Auftrag ist die Politik, kein Einzel-OK) —
gedeckelt durch den Anti-Weglauf der Hand (:data:`hand.MAX_OFFENE`) und IDEMPOTENT: ein Gedanke wird
nur EINMAL zur Hand (Dedup über die Hand-Quelle ``gedanke:<schlüssel>``), auch nachdem sie gesendet
ist. Wird der Vorschlag entschieden / die Frage beantwortet, taucht er nicht mehr auf.
"""
from __future__ import annotations

import json

from genus import hand, inquiries, konsolidierung, proposals
from genus.hypothese import _name

QUELLE = "gedanke:"


def _abstraktion_text(conn, inquiry: dict) -> str:
    roh = inquiry["payload"]
    p = json.loads(roh) if isinstance(roh, str) else (roh or {})
    eltern = _name(conn, p["elternteil"]) if p.get("elternteil") else "einem Muster"
    if p.get("art") == "wachstum":
        kand = ", ".join(_name(conn, k) for k in (p.get("kandidaten") or [])[:5]) or "etwas"
        return (f"Mir ist ein Gedanke gekommen zu einem Begriff, den ich selbst gebildet habe: "
                f"Sollte auch {kand} zu den »{eltern}« gehören, die ich gruppiert habe?")
    return (f"Ein Begriff, den ich selbst unter »{eltern}« gebildet habe, trägt seine Mitglieder "
            f"nicht mehr zusammen — magst du mal draufschauen?")


def wichtige_gedanken(conn) -> list[dict]:
    """Die Gedanken, die eine proaktive Nachricht verdienen -- ``{schluessel, text}``: die
    Entscheidungs-Vorschläge (``action_required``, über :func:`konsolidierung.triagiere_proposals`)
    und die offenen selbst gebildeten Begriffs-Fragen (:data:`inquiries.ABSTRAKTION_INQUIRY_TYPE`)."""
    gedanken: list[dict] = []
    dringend, _betrieb = konsolidierung.triagiere_proposals(proposals.list_proposals(conn))
    for pr in dringend:
        beschreibung = (konsolidierung._proposal_payload(pr).get("description") or "").strip()
        text = (f"Ich möchte etwas mit dir klären (Vorschlag #{pr['id']}): {beschreibung}"
                if beschreibung else
                f"Vorschlag #{pr['id']} wartet auf deine Entscheidung (über „genus governance“).")
        gedanken.append({"schluessel": f"proposal:{pr['id']}", "text": text})
    for inq in inquiries.list_inquiries(conn, include_all=False):
        if inq["inquiry_type"] == inquiries.ABSTRAKTION_INQUIRY_TYPE:
            gedanken.append({"schluessel": f"inquiry:{inq['id']}",
                             "text": _abstraktion_text(conn, inq)})
    return gedanken


def push(conn) -> list[int]:
    """Reconcile: für jeden wichtigen Gedanken, der noch NICHT als Hand vorliegt, eine bestätigte
    Nachricht-Hand anlegen (fällig jetzt). Idempotent über die Quelle; verweigert die Hand den
    Vorschlag (z.B. Anti-Weglauf-Deckel), wird still übersprungen. Gibt die neuen ``hand_id``s."""
    schon = hand.quellen(conn)
    neu: list[int] = []
    for g in wichtige_gedanken(conn):
        quelle = QUELLE + g["schluessel"]
        if quelle in schon:
            continue
        v = hand.vorschlagen(conn, "nachricht", g["text"], None, quelle=quelle)
        if not v.get("vorgeschlagen"):
            continue
        hand.bestaetigen(conn, v["hand_id"])
        neu.append(v["hand_id"])
    return neu
