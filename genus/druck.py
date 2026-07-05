"""Der DRUCK — die Richtung der Lebendigkeit (Ronny 2026-07-05, docs/GENUS_INTELLIGENZ.md §9).

Der Takt sagt, WANN GENUS denkt; der Druck sagt, WOHIN. Erster ehrlicher Schritt:
**Persistenz statt Entladung.**

Bisher entlud sich der Druck einer Verstehens-Lücke im Moment des Aussprechens: sobald ein
Proposal entstand, verschwand die Lücke aus der Sicht des Detektors (der sie als „schon
aufgezeichnet" überspringt) — das Nagen hörte auf, obwohl nichts getan war. Wie ein Mensch,
der „das müsste ich mal reparieren" sagt und sich danach besser fühlt, ohne es zu reparieren.

Jetzt ist der Druck eine READ-TIME-Größe über den UNGESTILLTEN Nöten:
- er BLEIBT, solange die Not besteht (das Blatt hat noch keinen Handler);
- er STEIGT, wenn nach dem Aussprechen weitere Nachfrage kommt (der Zuwachs seit dem
  Vorschlag ist das Persistenz-Signal — die Not wird nicht kleiner, sondern größer);
- eine GESTILLTE Not (das Blatt hat jetzt einen Handler) drückt gar nicht mehr — Druck
  bis zur Stillung, nicht bis zum Aussprechen.

Gläsern: nichts gespeichert (read-time wie Confidence/Trust), frisch gerechnet aus der
Belegung und der einen ausgesprochenen Experience. Der Druck erzeugt KEINE Events, KEINE
Proposals, KEINE Handlung — er bewegt den GEIST (was GENUS als Nächstes bedenkt, was es
sagt), nie die HAND. Und er KONKURRIERT: die Nöte sind nach Druck geordnet, die drängendste
zuerst. Kein Preset: der Druck IST die gelebte Nachfrage, gemessen, nie vorgetäuscht.
"""
from __future__ import annotations

import json


def _ausgesprochen_bei(conn, kind: str) -> int | None:
    """Die Nachfrage im Moment, als die Lücke ausgesprochen wurde (das Proposal entstand) —
    aus der aufgezeichneten Experience. ``None``, wenn sie noch nie ausgesprochen wurde."""
    row = conn.execute(
        "SELECT pattern FROM experience_log WHERE experience_key = ?",
        (f"verstehens_luecke:{kind}",),
    ).fetchone()
    if row is None:
        return None
    try:
        return int(json.loads(row["pattern"]).get("demand"))
    except (ValueError, TypeError):
        return None


def luecken_druck(conn) -> list[dict]:
    """Der Druck jeder UNGESTILLTEN Verstehens-Lücke (kein Handler, Nachfrage > 0), nach
    Druck geordnet (die drängendste zuerst — Konkurrenz). Pro Lücke: die aktuelle
    ``nachfrage``, ob sie schon ``ausgesprochen`` wurde (und bei welcher Nachfrage,
    ``ausgesprochen_bei``), und der ``zuwachs`` seither (das Persistenz-Signal, ``None``
    wenn noch nicht ausgesprochen). Read-time, nichts gespeichert."""
    from genus import companion, verstehen

    druecke: list[dict] = []
    for kind in verstehen.leaf_kinds(conn):
        if companion.hat_handler(conn, kind):
            continue                                   # gestillt -> kein Druck
        nachfrage = verstehen.belegung(conn, kind).get("gesamt", 0)
        if nachfrage <= 0:
            continue
        ausg = _ausgesprochen_bei(conn, kind)
        druecke.append({
            "kind": kind,
            "nachfrage": nachfrage,
            "ausgesprochen": ausg is not None,
            "ausgesprochen_bei": ausg,
            "zuwachs": (nachfrage - ausg) if ausg is not None else None,
        })
    druecke.sort(key=lambda d: (-d["nachfrage"], d["kind"]))
    return druecke


def draengendste(conn) -> dict | None:
    """Die Not, die am stärksten drückt — die Konkurrenz-Spitze, oder ``None``."""
    d = luecken_druck(conn)
    return d[0] if d else None


def satz(conn) -> str:
    """Eine ehrliche Zeile über den stärksten ungestillten Druck — „" wenn nichts drückt.
    Ein ausgesprochener, aber SEITHER GEWACHSENER Druck wird als solcher benannt (das
    Persistenz-Signal): der Vorschlag liegt, und die Not ist trotzdem größer geworden."""
    d = draengendste(conn)
    if d is None:
        return ""
    was = f"„{d['kind']}“ (das kann ich noch nicht, {d['nachfrage']}-mal gelesen)"
    if d["ausgesprochen"] and (d["zuwachs"] or 0) > 0:
        return (f"Am dringendsten drückt {was}: den Vorschlag dazu hast du noch offen, und "
                f"seither ist die Nachfrage um {d['zuwachs']} gestiegen — es wird nicht "
                f"kleiner, im Gegenteil.")
    if d["ausgesprochen"]:
        return f"Am dringendsten drückt {was} — der Vorschlag dazu liegt bei dir."
    return f"Am dringendsten drückt {was}."
