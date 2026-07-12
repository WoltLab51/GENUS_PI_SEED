"""GENUS' lesbares Selbstbild -- eine Projektion vorhandener, belegter Zustände.

Das Modul erfindet keine Persona und ruft für eine Chat-Antwort auch keinen Live-Sensor auf.
Es komponiert ausschließlich aus drei bereits vorhandenen Wahrheitsflächen:

* laufender Code (Name und Version),
* Zielgraph (Mission und Status der Fähigkeit ``selbst-bild``),
* aktive Belief-/State-Projektionen (das beobachtete Habitat).

Damit ist „Wer bist du?“ keine festgeschriebene Werbebotschaft und „Kennst du dein Habitat?“
kein Hostname-Raten. Ändert sich der Graph oder der beobachtete Zustand, ändert sich die
Antwort. Was nicht bequellt ist, bleibt ausdrücklich unbekannt.
"""
from __future__ import annotations

import genus
from genus import projection, sources, state, ziele


SELBST_FAEHIGKEIT = "faehigkeit:selbst-bild"

# Reine Anzeigesprache. Welche Werte tatsächlich gelten, kommt ausschließlich aus den
# Projektionen. Die Allowlist verhindert zugleich, dass beliebige interne Claim-Namen oder
# künftig personenbezogene Schlüssel versehentlich in einer Selbstauskunft landen.
_HABITAT_ANZEIGE = {
    "disk.trend": "Datenträgertrend",
    "repo.activity": "Repository-Aktivität",
    "repo.churn": "Repository-Änderungsdichte",
    "system.activity": "Aktivität",
    "system.clock": "Uhr",
    "system.disk": "Datenträger",
    "system.load": "Systemlast",
    "system.memory": "Arbeitsspeicher",
    "system.network": "Netzwerk",
    "system.temperature": "Temperatur",
    "system.thermal": "Thermik",
    "weather.trend": "Wettertrend",
}

_WERT_ANZEIGE = {
    "active": "aktiv",
    "anomalous": "auffällig",
    "elevated": "erhöht",
    "falling": "fallend",
    "healthy": "gesund",
    "high": "hoch",
    "idle": "ruhig",
    "latent": "latent",
    "light": "gering",
    "low": "niedrig",
    "nominal": "nominal",
    "normal": "normal",
    "rising": "steigend",
    "stable": "stabil",
    "synchronized": "synchronisiert",
    "unknown": "unbekannt",
    "unstable": "instabil",
    "unsynchronized": "nicht synchronisiert",
}

_EPISTEMISCH = {
    projection.SUPPORTED: "belegt",
    projection.CONTESTED: "umstritten",
    projection.UNCERTAIN: "unsicher",
}


def _zielwert(conn, node: str, predicate: str) -> dict:
    rows = sources.relations(conn, subject=node, predicate=predicate)
    kandidaten = [{"wert": r["object"], "quelle": r["source"]} for r in rows]
    werte = {k["wert"] for k in kandidaten}
    return {
        "wert": next(iter(werte)) if len(werte) == 1 else None,
        "kandidaten": kandidaten,
        "konflikt": len(werte) > 1,
    }


def stand(conn) -> dict:
    """Strukturierte, rein lesende Selbstsicht; geeignet für Tests und andere Oberflächen."""
    habitat = []
    for belief in projection.list_active_beliefs(conn):
        key = belief["claim_key"]
        if key not in _HABITAT_ANZEIGE:
            continue
        habitat.append({
            "claim_key": key,
            "anzeige": _HABITAT_ANZEIGE[key],
            "wert": belief["claim_value"],
            "wert_anzeige": _WERT_ANZEIGE.get(belief["claim_value"], belief["claim_value"]),
            "epistemisch": belief["epistemic_state"],
            "epistemisch_anzeige": _EPISTEMISCH[belief["epistemic_state"]],
            "ableitung": belief["derivation"],
        })

    mission = _zielwert(conn, ziele.MISSION, ziele.INHALT)
    selbst_status = _zielwert(conn, SELBST_FAEHIGKEIT, ziele.STATUS)
    selbst_beschreibung = _zielwert(conn, SELBST_FAEHIGKEIT, ziele.INHALT)
    druck = state.active_state(conn)
    return {
        "name": "GENUS",
        "version": genus.__version__,
        "mission": mission["wert"],
        "mission_kandidaten": mission["kandidaten"],
        "mission_konflikt": mission["konflikt"],
        "selbstbild_status": selbst_status["wert"],
        "selbstbild_status_kandidaten": selbst_status["kandidaten"],
        "selbstbild_status_konflikt": selbst_status["konflikt"],
        "selbstbild_beschreibung": selbst_beschreibung["wert"],
        "selbstbild_beschreibung_kandidaten": selbst_beschreibung["kandidaten"],
        "selbstbild_beschreibung_konflikt": selbst_beschreibung["konflikt"],
        "habitat": habitat,
        "systemzustand": ({
            "state_key": druck["state_key"],
            "wert": druck["state_value"],
            "wert_anzeige": _WERT_ANZEIGE.get(druck["state_value"], druck["state_value"]),
            "ableitung": druck["derivation"],
        } if druck is not None else None),
    }


def _identitaets_bericht(s: dict) -> str:
    teile = [
        f"Ich bin {s['name']} {s['version']}: ein lokaler, ereignisbasierter Erkenntniskern."
    ]
    if s["mission_konflikt"]:
        teile.append("Mein Zielgraph enthält widersprüchliche Mission-Lesarten: "
                     + _kandidaten_text(s["mission_kandidaten"]) + ".")
    elif s["mission"]:
        teile.append(f"Meine im Zielgraphen verankerte Mission lautet: {s['mission']}")
    else:
        teile.append("Meine Mission ist noch nicht in meinem Zielgraphen angekommen.")
    if s["selbstbild_status_konflikt"]:
        teile.append("Der Status meines Selbstbilds ist im Zielgraphen widersprüchlich: "
                     + _kandidaten_text(s["selbstbild_status_kandidaten"]) + ".")
    elif s["selbstbild_status"] or s["selbstbild_beschreibung"]:
        status = s["selbstbild_status"] or "unbekannt"
        if s["selbstbild_beschreibung_konflikt"]:
            beschreibung = ("widersprüchliche Beschreibungen: "
                            + _kandidaten_text(s["selbstbild_beschreibung_kandidaten"]))
        else:
            beschreibung = s["selbstbild_beschreibung"] or "keine Beschreibung bequellt"
        teile.append(f"Mein Zielgraph bewertet mein Selbstbild als {status}: {beschreibung}")
    else:
        teile.append("Eine eigene Selbstbild-Fähigkeit ist in meinem Zielgraphen noch nicht bequellt.")
    return " ".join(teile)


def _kandidaten_text(kandidaten: list[dict]) -> str:
    return "; ".join(f"{k['wert']} (Quelle: {k['quelle']})" for k in kandidaten)


def _habitat_bericht(s: dict) -> str:
    habitat = s["habitat"]
    if not habitat and s["systemzustand"] is None:
        return (
            "Mein Habitat ist noch nicht ausreichend beobachtet: Im Ledger liegen aktuell keine "
            "aktiven Habitat-Zustände. Einen Hostnamen, physischen Ort oder laufende Dienste rate "
            "ich nicht."
        )

    belegt = [h for h in habitat if h["epistemisch"] == projection.SUPPORTED]
    offen = [h for h in habitat if h["epistemisch"] != projection.SUPPORTED]
    teile = [
        "Teilweise. Ich kenne mein Habitat über beobachtete Zustände im Ledger, nicht über "
        "einen geratenen Hostnamen oder Ortsnamen."
    ]
    if belegt:
        teile.append("Belegt sind: " + "; ".join(
            f"{h['anzeige']}: {h['wert_anzeige']}" for h in belegt
        ) + ".")
    if offen:
        teile.append("Unsicher oder umstritten bleiben: " + "; ".join(
            f"{h['anzeige']}: {h['wert_anzeige']} ({h['epistemisch_anzeige']})" for h in offen
        ) + ".")
    if s["systemzustand"] is not None:
        teile.append(
            "Mein abgeleiteter Systemzustand ist: Systemdruck "
            f"{s['systemzustand']['wert_anzeige']}."
        )
    teile.append("Nicht bequellt sind physischer Standort, Host-Topologie und laufende Dienste.")
    return " ".join(teile)


def bericht(conn, aspekt: str | None = None) -> str:
    """Eine deutschsprachige Selbstauskunft.

    ``aspekt`` kommt als semantischer Slot aus dem Deuter (z. B. ``Habitat`` oder
    ``Identität``), nie aus einem Phrasen-Regex. Ohne Facette entsteht das Gesamtbild.
    """
    s = stand(conn)
    norm = (aspekt or "").casefold()
    if any(w in norm for w in ("habitat", "umwelt", "umgebung", "zuhause")):
        return _habitat_bericht(s)
    if any(w in norm for w in ("identität", "identitaet", "wer", "name")):
        return _identitaets_bericht(s)
    return _identitaets_bericht(s) + "\n" + _habitat_bericht(s)
