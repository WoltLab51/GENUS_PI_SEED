"""Die BESINNUNG — der innere Loop, dem der Druck sein Gefälle gibt (Ronny 2026-07-05).

Der Takt sagt WANN GENUS denkt, der Druck sagt WOHIN — die Besinnung führt beide zusammen:
sie liest das Druck-Gefälle (``druck.landschaft``), wendet sich der größten Not zu und tut
den EINEN inwendigen Schritt in ihre Richtung. Und sie KETTET: ein getaner Schritt ändert
den Zustand (eine Not weniger unausgesprochen), also wendet sich die nächste Besinnung der
nächsten Not zu — ein Gedanke zieht den nächsten, das Gefälle hinab.

Die ehrliche Decke (die Leine: bewegt den GEIST, nie die HAND): den MEISTEN Nöten kann GENUS
heute nicht selbst abhelfen — eine Lücke schließen, eine Fähigkeit bauen, eine offene Frage
beantworten liegt alles hinter einem Gate oder beim Menschen. Der eine Schritt, den GENUS
OHNE die Hand tun darf, ist eine noch nicht ausgesprochene Lücke AUSZUSPRECHEN (ein Proposal
über die bestehende Proposal≠Change-Maschinerie — gegated, nichts wird ausgeführt). Alles
andere BENENNT die Besinnung ehrlich als das, worauf sie wartet. Das ist kein Mangel des
Loops, sondern sein wahrer Stand: ein Geist, der denken, aber (noch) nicht handeln kann —
seine Reichweite wächst mit den Operationen (docs/research/INTELLIGENCE.md §9).

Bounded und gläsern: höchstens EIN Aussprechen pro Besinnung (kein Fluten der Freigabe-
Schlange), read-time berechnet, kein Preset. Die Besinnung selbst schreibt nichts ins Ledger
außer dem einen (gegateten) Proposal, das sie ggf. auslöst — Reflexion ist read-time.
"""
from __future__ import annotations


def agenda(conn) -> dict:
    """GENUS' gerichtete Selbst-Auskunft aus dem Druck-Gefälle: die drängendste Not je
    Quelle, plus die EINE, die GENUS selbst angehen kann (die drängendste noch nicht
    ausgesprochene Lücke). Read-only."""
    from genus import druck

    L = druck.landschaft(conn)
    unausgesprochen = [d for d in L["luecke"] if not d["ausgesprochen"]]
    return {
        "luecke": L["luecke"][0] if L["luecke"] else None,
        "frage": L["frage"][0] if L["frage"] else None,
        "operation": L["operation"][0] if L["operation"] else None,
        "selbst_moeglich": unausgesprochen[0] if unausgesprochen else None,
    }


def _worauf(conn, a: dict) -> dict | None:
    """Woran die Besinnung hängt, wenn sie selbst nichts tun kann — ehrlich benannt: eine
    ausgesprochene, aber ungestillte Lücke wartet auf dich (Bauen/Freigabe), eine fehlende
    Fähigkeit auf deine Bau-Freigabe, eine offene Frage auf deine Antwort am Terminal."""
    if a["luecke"] is not None and a["luecke"]["ausgesprochen"]:
        return {"art": "luecke", "was": a["luecke"]["was"],
                "text": "auf deine Freigabe, die vorgeschlagene Fähigkeit zu bauen"}
    if a["operation"] is not None:
        return {"art": "operation", "was": a["operation"]["was"],
                "text": "auf deine Freigabe, diese Fähigkeit anzulegen"}
    if a["frage"] is not None:
        return {"art": "frage", "was": a["frage"]["was"],
                "text": "auf deine Antwort am Terminal („genus inquiries“/„genus teach“)"}
    return None


def besinne(conn) -> dict:
    """Ein Besinnungs-Schritt: der eine erlaubte inwendige Zug das Gefälle hinab. Ist eine
    drängende Lücke noch nicht ausgesprochen, wird sie es (gegatetes Proposal, gradient-
    geordnet — ``spontane_regung`` nimmt ohnehin die drängendste unausgesprochene). Sonst
    benennt die Besinnung ehrlich, worauf sie wartet. ``weiter`` sagt, ob noch eine
    unausgesprochene Not wartet (das Ketten-Signal für den nächsten Schritt)."""
    from genus import druck, experience

    regung = experience.spontane_regung(conn)
    if regung is not None and regung.get("proposal_id"):
        weiter = any(not d["ausgesprochen"] for d in druck.luecken_druck(conn))
        return {"getan": "ausgesprochen", "kind": regung.get("kind"),
                "proposal_id": regung["proposal_id"], "weiter": weiter}
    return {"getan": "gewartet", "worauf": _worauf(conn, agenda(conn)), "weiter": False}


def lauf(conn, hoechstens: int = 8) -> list[dict]:
    """Der Gedankengang: besinne, bis nichts Unausgesprochenes mehr das Gefälle hinabführt
    (oder ``hoechstens`` erreicht ist). Ein Schritt zieht den nächsten — die Kette walks the
    gradient, jeder Zug gegated. Bounded gegen Endlosigkeit UND gegen ein Fluten der
    Freigabe-Schlange."""
    schritte: list[dict] = []
    for _ in range(max(1, hoechstens)):
        s = besinne(conn)
        schritte.append(s)
        if s["getan"] != "ausgesprochen" or not s["weiter"]:
            break
    return schritte


def narrate(conn) -> str:
    """GENUS spricht seine gerichtete Agenda — was am meisten drückt, was es selbst angehen
    kann und worauf es wartet. Ehrlich über die Decke: ein Geist, der denkt, aber (noch)
    nicht handeln kann."""
    a = agenda(conn)
    if not any((a["luecke"], a["frage"], a["operation"])):
        return "Wenn ich in mich hineinhöre, drückt gerade nichts — es ist ruhig."
    zeilen = ["Wenn ich in mich hineinhöre:"]
    s = a["selbst_moeglich"]
    if s is not None:
        zeilen.append(f"• Selbst angehen kann ich „{s['was']}“ ({s['nachfrage']}-mal "
                      f"gelesen, kann ich noch nicht) — das spreche ich als Vorschlag aus.")
    if a["luecke"] is not None and a["luecke"]["ausgesprochen"]:
        zeilen.append(f"• „{a['luecke']['was']}“ drückt am stärksten, aber der Vorschlag "
                      f"dazu liegt schon bei dir — da warte ich auf dich.")
    if a["frage"] is not None:
        zeilen.append(f"• Am meisten beschäftigt mich die offene Frage „{a['frage']['was']}“ "
                      f"({a['frage']['staerke']}-mal aufgefallen) — beantworten kannst nur du sie.")
    if a["operation"] is not None:
        op = a["operation"]
        ziel = "Ziel" if op["staerke"] == 1 else "Ziele"
        zeilen.append(f"• Und strukturell fehlt mir „{op['was']}“ (blockiert {op['staerke']} "
                      f"{ziel}) — das braucht deine Freigabe zum Bauen.")
    return "\n".join(zeilen)
