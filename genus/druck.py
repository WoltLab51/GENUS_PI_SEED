"""Der DRUCK — die Richtung der Lebendigkeit (Ronny 2026-07-05, docs/GENUS_INTELLIGENZ.md §9).

Der Takt sagt, WANN GENUS denkt; der Druck sagt, WOHIN. Erster Schritt war Persistenz statt
Entladung (die Not verschwindet nicht beim Aussprechen); dieser Schritt WEITET den Druck auf
alle drei Arten ungestillter Nöte aus — ein Register von Druck-QUELLEN:

  luecke     eine Verstehens-Lücke ohne Handler  → Stärke = gelebte Nachfrage (Belegung)
  frage      eine offene Inquiry (Widerspruch/Überraschung) → Stärke = Wiederkehr (count)
  operation  eine fehlende Fähigkeit im Ziel-Graphen → Stärke = wie viele Ziele sie blockt

Jede Quelle hat ihren EIGENEN gelebten Zähler — bewusst NICHT über die Quellen hinweg zu
einer Zahl verrechnet: „5 Lesungen" gegen „3 blockierte Ziele" abzuwägen wäre selbst ein
Preset. Also KONKURRIERT der Druck INNERHALB jeder Quelle (dort ist der Vergleich echt), und
die Landschaft (:func:`landschaft`) zeigt alle drei nebeneinander.

Alles gläsern und read-time (nichts gespeichert, frisch aus Belegung / Inquiries / Ziel-Graph
gerechnet). Der Druck erzeugt KEINE Events, keine Proposals, keine Handlung — er bewegt den
GEIST (was GENUS als Nächstes bedenkt, was es sagt), nie die HAND. Kein Preset: jeder Druck
IST ein gemessener gelebter Zähler, nie vorgetäuscht.
"""
from __future__ import annotations

import json


# --- Quelle 1: Verstehens-Lücken (Persistenz statt Entladung) ----------------------------

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
    Druck geordnet. Bleibt bis zur Stillung (Handler), STEIGT nach dem Aussprechen (``zuwachs``
    = Persistenz-Signal). Read-time."""
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
            "quelle": "luecke", "was": kind, "staerke": nachfrage,
            "nachfrage": nachfrage,
            "ausgesprochen": ausg is not None, "ausgesprochen_bei": ausg,
            "zuwachs": (nachfrage - ausg) if ausg is not None else None,
        })
    druecke.sort(key=lambda d: (-d["staerke"], d["was"]))
    return druecke


# --- Quelle 2: offene Inquiries (Widersprüche/Überraschungen) ----------------------------

def frage_druck(conn) -> list[dict]:
    """Der Druck jeder offenen Inquiry — Stärke = Wiederkehr (wie oft dieselbe Überraschung/
    derselbe Widerspruch auffiel; open_questions bündelt sie mit ``count``). Persistenz ist
    hier eingebaut: eine Inquiry bleibt offen, bis sie am Terminal beantwortet ist."""
    from genus import companion

    druecke: list[dict] = []
    for g in companion.open_questions(conn)["groups"]:
        druecke.append({
            "quelle": "frage", "was": g["claim_key"], "staerke": g["count"],
            "inquiry_type": g["inquiry_type"],
        })
    druecke.sort(key=lambda d: (-d["staerke"], d["was"]))
    return druecke


# --- Quelle 3: fehlende Operationen/Fähigkeiten (Ziel-Graph) -----------------------------

def operations_druck(conn) -> list[dict]:
    """Der Druck jeder fehlenden Fähigkeit — Stärke = FAN-IN: wie viele Ziele sie brauchen
    (``ziel:* -braucht-> faehigkeit:X``). Eine Fähigkeit, die mehr Ziele blockiert, drückt
    stärker. Read-time aus dem Ziel-Graphen; die Not ist gestillt, sobald der Status ``live``
    ist (dann steht sie nicht mehr in fehlende_faehigkeiten)."""
    from genus import sources, ziele

    druecke: list[dict] = []
    for f in ziele.fehlende_faehigkeiten(conn):
        fan_in = len(sources.relations(conn, predicate=ziele.BRAUCHT, object=f["id"]))
        druecke.append({
            "quelle": "operation", "was": f["id"].split(":", 1)[-1], "staerke": fan_in,
            "id": f["id"], "inhalt": f["inhalt"], "status": f["status"],
        })
    druecke.sort(key=lambda d: (-d["staerke"], d["was"]))
    return druecke


# Das Register der Druck-Quellen (Charta: eine wachsende Klasse -> Registry). Ein neuer
# Druck (z.B. später der Betriebs-Druck oder ein Nutzer-Bedürfnis) ist ein Eintrag hier.
DRUCK_QUELLEN = (
    ("luecke", luecken_druck),
    ("frage", frage_druck),
    ("operation", operations_druck),
)


def landschaft(conn) -> dict[str, list]:
    """Die ganze Druck-Landschaft: pro Quelle die nach Druck geordneten Nöte. Der (künftige)
    innere Loop liest hier sein Gefälle; GENUS spricht daraus, was es am meisten beschäftigt."""
    return {name: quelle(conn) for name, quelle in DRUCK_QUELLEN}


def draengendste(conn) -> dict | None:
    """Die drängendste Verstehens-Lücke — die Konkurrenz-Spitze der luecke-Quelle, oder
    ``None`` (die eine Quelle, die das Persistenz-Signal trägt; die Landschaft zeigt alle)."""
    d = luecken_druck(conn)
    return d[0] if d else None


# --- die ehrliche Stimme des Drucks ------------------------------------------------------

def _luecke_satz(conn) -> str:
    d = draengendste(conn)
    if d is None:
        return ""
    was = f"„{d['was']}“ (das kann ich noch nicht, {d['nachfrage']}-mal gelesen)"
    if d["ausgesprochen"] and (d["zuwachs"] or 0) > 0:
        return (f"Am dringendsten drückt {was}: den Vorschlag dazu hast du noch offen, und "
                f"seither ist die Nachfrage um {d['zuwachs']} gestiegen — es wird nicht "
                f"kleiner, im Gegenteil.")
    if d["ausgesprochen"]:
        return f"Am dringendsten drückt {was} — der Vorschlag dazu liegt bei dir."
    return f"Am dringendsten drückt {was}."


def _operation_satz(conn) -> str:
    d = operations_druck(conn)
    if not d:
        return ""
    top = d[0]
    ziel_wort = "Ziel" if top["staerke"] == 1 else "Ziele"
    return (f"Strukturell fehlt mir am dringendsten die Fähigkeit „{top['was']}“ — "
            f"sie blockiert {top['staerke']} {ziel_wort}.")


def satz(conn) -> str:
    """Die ehrliche Stimme des Drucks für „Was beschäftigt dich?": der stärkste ungestillte
    Lücken-Druck (mit Persistenz-Signal) UND die am meisten gebrauchte fehlende Fähigkeit.
    Offene Inquiries werden dort schon als Aufzählung genannt — hier nicht doppelt. „" wenn
    nichts drückt."""
    teile = [_luecke_satz(conn), _operation_satz(conn)]
    return "\n".join(t for t in teile if t)
