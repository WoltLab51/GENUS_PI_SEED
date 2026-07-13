"""Das THERMOMETER (Skill-Dashboard ④, Wachstums-Doktrin 2026-07-08): GENUS als Messmaschine
der eigenen Fähigkeitsentwicklung -- der fehlende Sensor des geschlossenen Kreislaufs
(Lücke → Plan → Werkzeug vorschlagen → testen → Mensch gibt frei → LIVE MESSEN → kalibrieren).

Zwei Leitplanken, fest eingebaut (Ronnys Guardrails, nicht Prosa):

THERMOMETER, KEIN ZIEL (Goodhart): jede Zahl hier ist ein SENSOR für den Kreislauf, nie ein
Optimierungsziel. Nichts in GENUS liest diese Zahlen, um sich daran auszurichten -- sie werden
einem Menschen gezeigt (CLI ``genus skills``), der daraus Prioritäten macht. Das Modul ist
strikt read-only (kein einziger Schreibpfad), damit das strukturell so bleibt.

GENERALISIERUNG, NICHT SPEZIALFÄLLE: die eine Zahl, die wachsen soll, ist die Zahl der
Absichten auf der EINEN Planer-Mechanik (``ABSICHT_SAAT``) samt ihrem Anteil am echten
Live-Verkehr -- sie wächst nur durch echte Verallgemeinerung (eine neue Absicht auf derselben
Mechanik) und ist gegen die Spezialfall-Falle immun: eine neue Sonder-Zelle, ein neues
Regex-Muster, ein neuer Handler erhöhen sie NICHT.

Alle Quellen sind bestehende Sensoren, nichts wird neu erhoben: das Planer-Zählwerk
(genus.zaehlwerk, JSONL am Membran-Rand), die Verstehens-Belegung/Fehlgriffe (genus.verstehen,
Kennzahlen im Graphen, retraktions-bewusst), der Ziel-Graph (genus.ziele, „was fehlt dir?"),
die Werkzeug-Registry (handelbare Zellen) und die offenen Proposals (das Gate).
"""
from __future__ import annotations


def _planer(zaehlung: dict) -> dict:
    """Je Absicht: treffer/rueckfall/anker_frei + Trefferquote (Plan trug / Plan+Netz gesamt).
    Die Quote misst, ob die EINE Mechanik den echten Verkehr trägt -- nicht, ob GENUS
    „gut" ist (ein Rückfall ist eine ehrliche, gezählte Degradation, keine falsche Antwort)."""
    absichten: dict[str, dict] = {}
    for schluessel, n in zaehlung.items():
        absicht, _, ereignis = schluessel.partition(":")
        absichten.setdefault(absicht, {})[ereignis] = n
    for werte in absichten.values():
        getragen = werte.get("treffer", 0)
        gesamt = getragen + werte.get("rueckfall", 0)
        werte["quote"] = round(getragen / gesamt, 3) if gesamt else None
    return absichten


def _verstehen(conn) -> dict:
    """Je gesätem Blatt: Belegung je Herkunft (muster/model:deuter/gebaerde) und Fehlgriffe --
    die QM-Kennzahlen am Verstehen, plus „unklar" (die gezählten blinden Flecken)."""
    from genus import verstehen

    blaetter: dict[str, dict] = {}
    for kind in verstehen.leaf_kinds(conn):
        bel = verstehen.belegung(conn, kind)
        feh = verstehen.fehlgriffe(conn, kind)
        gelesen = bel.get("je_quelle", {}) if isinstance(bel, dict) else {}
        fehlgriffe = sum((feh.get("je_quelle", {}) or {}).values()) if isinstance(feh, dict) else 0
        if gelesen or fehlgriffe:
            blaetter[kind] = {"gelesen": gelesen, "fehlgriffe": fehlgriffe}
    unklar = verstehen.belegung(conn, "unklar")
    return {
        "blaetter": blaetter,
        "unklar": (unklar.get("je_quelle", {}) if isinstance(unklar, dict) else {}),
        "verwechslungen": verstehen.verwechslungen(conn),
    }


def _generalisierung(conn, planer: dict) -> dict:
    """Die Doktrin-Kennzahl: wie viel läuft über die EINE Mechanik? ``absichten`` = die
    Planer-Absichten (wächst nur durch Verallgemeinerung); ``verkehr_ueber_planer`` = Anteil
    des gezählten Live-Verkehrs, den der deduzierte Plan trug (treffer / alle Ereignisse)."""
    from genus import companion, verstehen
    from genus.werkzeuge_auskunft import ABSICHT_SAAT

    treffer = sum(w.get("treffer", 0) for w in planer.values())
    gesamt = sum(n for w in planer.values() for n in w.values() if isinstance(n, int))
    blaetter = verstehen.leaf_kinds(conn)
    handelbar = [b for b in blaetter if companion.hat_handler(conn, b)]
    return {
        "absichten_auf_planer": sorted(ABSICHT_SAAT),
        "verkehr_ueber_planer": round(treffer / gesamt, 3) if gesamt else None,
        "blaetter_gesaet": len(blaetter),
        "blaetter_handelbar": len(handelbar),
    }


def _luecken(conn) -> dict:
    """Die ehrlich benannten Lücken, aus drei bestehenden Sensoren: Raster-Blätter ohne
    Handler (gelesen ≠ gekonnt), fehlende Fähigkeiten aus dem Ziel-Graphen („was fehlt
    dir?") und offene Proposals am Gate (der Kreislauf wartet auf den Menschen)."""
    from genus import companion, proposals, verstehen, ziele

    ohne_handler = sorted(
        b for b in verstehen.leaf_kinds(conn)
        if b != "unklar" and not companion.hat_handler(conn, b)
    )
    fehlende = [
        {"id": f["id"], "status": f["status"]} for f in ziele.fehlende_faehigkeiten(conn)
    ]
    try:
        offene = len(proposals.list_proposals(conn))
    except Exception:
        offene = 0   # ein frisches Ledger ohne proposal_log liest sich als „keine offenen"
    return {"blaetter_ohne_handler": ohne_handler, "faehigkeiten_nicht_live": fehlende,
            "offene_proposals": offene}


def betriebsstand(conn) -> dict:
    """Bounded operating subset without the ledger-heavy understanding scan.

    The 24/48/72-hour operating profile needs only generalisation and gap
    indicators.  Keeping this public helper separate prevents read-only
    background diagnostics from accidentally invoking ``_verstehen``'s repeated
    whole-ledger scans.
    """
    from genus import zaehlwerk

    planer = _planer(zaehlwerk.stand())
    return {
        "generalisierung": _generalisierung(conn, planer),
        "luecken": _luecken(conn),
    }


def stand(conn) -> dict:
    """Der ganze Thermometer-Stand als EIN Dict -- rein lesend, deterministisch, kein Modell.
    Struktur: planer (Quoten je Absicht) / verstehen (Belegung, Fehlgriffe, unklar) /
    generalisierung (die Doktrin-Kennzahl) / luecken (ehrlich benannt)."""
    from genus import zaehlwerk

    planer = _planer(zaehlwerk.stand())
    return {
        "planer": planer,
        "verstehen": _verstehen(conn),
        "generalisierung": _generalisierung(conn, planer),
        "luecken": _luecken(conn),
    }
