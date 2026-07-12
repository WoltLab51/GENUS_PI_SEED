"""Die HÄNDE (P4, Ronny 2026-07-08: „geben wir GENUS Hände"). Der erste Weg, auf dem GENUS die
Welt nicht nur LIEST, sondern VERÄNDERT — und deshalb der am härtesten gegatete.

Die Asymmetrie (aktueller Vertrag: docs/ARCHITECTURE.md §8; historische Herkunft:
docs/history/TARGET_ARCHITECTURE_2026-07-04.md §8): ein SINN liest (im Zweifel nur falsch — der Kern
fängt es ab); eine HAND wirkt (oft unumkehrbar). Darum das eiserne Gate:

- HARTER KERN-CONSTRAINT, nicht übersteuerbar: eine Außenhandlung wird NUR ausgeführt, wenn ein
  frisches, aktions-genaues menschliches OK vorliegt (Status FREIGEGEBEN) — und GENAU EINMAL. Es
  gibt keinen ``override``-Parameter; die Bestätigung IST das Gate. §8 war bisher Prosa — hier
  wird es zum ersten Mal im Code erzwungen.
- FIXER BODEN (wie ``umsetzung.UMSETZUNGEN``): nur Arten, deren Wirkung eine NACHRICHT AN RONNY
  ist, lassen sich hier überhaupt ausdrücken. Eine Art mit Geld-, Fremd- oder Systemwirkung kann
  hier gar nicht entstehen — der Boden ist die Form dieses Moduls, keine vergessbare Laufzeitprüfung.
- ANTI-WEGLAUF: höchstens :data:`MAX_OFFENE` offene Hände; darüber verweigert GENUS neue Vorschläge
  (kein Modell und kein Fehlgriff kann eine Flut erzeugen).
- VOLLE PRÜF-SPUR: Vorschlag, Bestätigung/Ablehnung und Ausführung sind je ein Ledger-Ereignis.

Der Kern SENDET NIE selbst (Membran-Reinheit: kein HTTP im Kern): :func:`faellige` gibt die
freigegebenen, fälligen Aktionen; die Membran sendet jede und ruft :func:`markiere_ausgefuehrt`.
Der Zustand lebt rein im Ledger (Ereignis-Projektion, read-time) — kein Nebentisch, replay-stabil.
"""
from __future__ import annotations

import contextlib
import datetime
import json

from genus import ledger

HAND_VORGESCHLAGEN = "hand_vorgeschlagen"
HAND_BESTAETIGT = "hand_bestaetigt"
HAND_AUSGEFUEHRT = "hand_ausgefuehrt"
HAND_ABGELEHNT = "hand_abgelehnt"

VORGESCHLAGEN = "vorgeschlagen"
FREIGEGEBEN = "freigegeben"
AUSGEFUEHRT = "ausgefuehrt"
ABGELEHNT = "abgelehnt"

# Der fixe Boden: die einzige heute ausdrückbare Hand-Art ist eine Nachricht an Ronny. Jede
# weitere Art (und erst recht eine mit Geld-/Fremd-/Systemwirkung) ist eine bewusste, spätere
# Entscheidung — sie existiert bis dahin gar nicht.
ARTEN = frozenset({"nachricht"})
MAX_OFFENE = 20   # Anti-Weglauf: so viele offene (vorgeschlagene+freigegebene) Hände höchstens

# Herzschlag-Wächter: eine freigegebene, fällige Hand, die LÄNGER als so viele Minuten
# unversendet bleibt, heißt der Membran-Sende-Tick (hand_ausfuehren.sh, alle 2 min) steht still —
# denn im gesunden Fall leert ihn ein Tick binnen ~2 min. FESTE Schwelle: sie leitet sich aus dem
# bekannten Cron-Takt ab (mehrere verpasste Ticks = eindeutig kaputt), NICHT aus GENUS' eigener
# Historie — also absolut, nicht selbst-kalibriert (self-calibration-no-presets: eine ruhige
# eigene Verteilung würde sonst Fehlalarme erzeugen). 10 min = ~5 verpasste Ticks, kein Fehlalarm.
UEBERFAELLIG_MIN = 10


@contextlib.contextmanager
def _schreib_lock(conn):
    """``BEGIN IMMEDIATE`` mit GARANTIERTEM Rollback bei jeder Ausnahme. Die geteilte,
    langlebige Verbindung (Bot + Crons schreiben dasselbe Ledger) darf nie in einer offenen
    Transaktion hängenbleiben — sonst scheitert der nächste Ledger-Schreib mit „cannot start a
    transaction within a transaction", und ein vorübergehender Lock beim HANDELN würde das REDEN
    mitvergiften. Die fachlichen Ablehnungen unten rollen selbst zurück und kehren normal zurück
    (kein Fehler); dieser Wächter fängt nur das Unerwartete (Lock nach Timeout, Platten-I/O)
    und reicht es sauber weiter — die Verbindung bleibt danach benutzbar."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.rollback()
        raise


def _hand_ereignisse(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT id, event_type, payload FROM event_log "
        "WHERE event_type LIKE 'hand\\_%' ESCAPE '\\' ORDER BY id"
    ).fetchall()
    return [dict(r) for r in rows]


def _zustand(conn) -> dict[int, dict]:
    """Rekonstruiert jede Hand aus ihren Ereignissen -- reine Projektion, read-time. Die hand_id
    ist die Ereignis-Id des Vorschlags (eindeutig); Folge-Ereignisse verweisen darauf."""
    haende: dict[int, dict] = {}
    for e in _hand_ereignisse(conn):
        p = json.loads(e["payload"])
        if not isinstance(p, dict):   # ein gefaelschtes/kaputtes Ereignis darf das Gate NIE lahmlegen
            continue
        if e["event_type"] == HAND_VORGESCHLAGEN:
            haende[e["id"]] = {
                "hand_id": e["id"], "art": p.get("art"), "inhalt": p.get("inhalt"),
                "faellig_um": p.get("faellig_um"), "quelle": p.get("quelle"),
                "status": VORGESCHLAGEN,
            }
            continue
        h = haende.get(p.get("hand_id"))
        if h is None:
            continue
        if e["event_type"] == HAND_BESTAETIGT and h["status"] == VORGESCHLAGEN:
            h["status"] = FREIGEGEBEN
        elif e["event_type"] == HAND_ABGELEHNT and h["status"] == VORGESCHLAGEN:
            h["status"] = ABGELEHNT
        elif e["event_type"] == HAND_AUSGEFUEHRT and h["status"] == FREIGEGEBEN:
            h["status"] = AUSGEFUEHRT
    return haende


def hand(conn, hand_id: int) -> dict | None:
    return _zustand(conn).get(hand_id)


def offene(conn) -> list[dict]:
    """Alle noch nicht abgeschlossenen Hände (vorgeschlagen oder freigegeben-aber-nicht-gesendet)."""
    return [h for h in _zustand(conn).values()
            if h["status"] in (VORGESCHLAGEN, FREIGEGEBEN)]


def quellen(conn) -> set[str]:
    """Alle je vergebenen Hand-Quellen über ALLE Zustände (auch ausgeführte) -- der Dedup-Griff für
    eine proaktive Nachricht: ein Gedanke wird nur EINMAL zur Hand, auch nachdem sie längst gesendet ist."""
    return {h.get("quelle") for h in _zustand(conn).values()}


def vorschlagen(conn, art: str, inhalt: str, faellig_um: str | None = None,
                quelle: str = "genus") -> dict:
    """Eine Außenhandlung VORSCHLAGEN — sie wird noch NICHT ausgeführt, sondern wartet auf ein
    aktions-genaues menschliches OK (:func:`bestaetigen`). Verweigert eine unbekannte Art (fixer
    Boden), leeren Inhalt und zu viele offene Hände (Anti-Weglauf)."""
    if art not in ARTEN:
        return {"vorgeschlagen": False, "grund": f"Hand-Art „{art}“ ist nicht erlaubt."}
    if not str(inhalt).strip():
        return {"vorgeschlagen": False, "grund": "Eine Hand ohne Inhalt gibt es nicht."}
    with _schreib_lock(conn):   # Zählen + Anhängen atomar: der Anti-Weglauf-Deckel hält
        if len(offene(conn)) >= MAX_OFFENE:            # auch bei gleichzeitigen Vorschlägen
            conn.rollback()
            return {"vorgeschlagen": False,
                    "grund": f"Zu viele offene Hände (≥ {MAX_OFFENE}) — erst abarbeiten."}
        eid = ledger.append(conn, HAND_VORGESCHLAGEN,
                            {"art": art, "inhalt": str(inhalt), "faellig_um": faellig_um,
                             "quelle": quelle})
        conn.commit()
        return {"vorgeschlagen": True, "hand_id": eid}


def bestaetigen(conn, hand_id: int) -> dict:
    """Das aktions-genaue menschliche OK: die Hand wird FREIGEGEBEN. Nur ein Vorschlag lässt sich
    bestätigen (nicht doppelt, nicht nach Ablehnung/Ausführung)."""
    with _schreib_lock(conn):   # atomar gegen ein gleichzeitiges ablehnen derselben Hand
        h = _zustand(conn).get(hand_id)
        if h is None:
            conn.rollback()
            return {"bestaetigt": False, "grund": "Unbekannte Hand."}
        if h["status"] != VORGESCHLAGEN:
            conn.rollback()
            return {"bestaetigt": False, "grund": f"Hand ist „{h['status']}“, nicht „{VORGESCHLAGEN}“."}
        ledger.append(conn, HAND_BESTAETIGT, {"hand_id": hand_id})
        conn.commit()
        return {"bestaetigt": True, "hand_id": hand_id}


def ablehnen(conn, hand_id: int) -> dict:
    """Ein Vorschlag wird verworfen — nichts wird je ausgeführt."""
    with _schreib_lock(conn):   # atomar gegen ein gleichzeitiges bestaetigen derselben Hand
        h = _zustand(conn).get(hand_id)
        if h is None or h["status"] != VORGESCHLAGEN:
            conn.rollback()
            return {"abgelehnt": False}
        ledger.append(conn, HAND_ABGELEHNT, {"hand_id": hand_id})
        conn.commit()
        return {"abgelehnt": True, "hand_id": hand_id}


def faellige(conn, jetzt_iso: str) -> list[dict]:
    """Die FREIGEGEBENEN, jetzt fälligen, noch nicht ausgeführten Hände — was die Membran gerade
    ausführen (senden) darf. ``jetzt_iso`` reicht die Membran herein (der Kern liest keine
    Wanduhr für einen Schreib-Entscheid — Replay-Stabilität)."""
    faellig = []
    for h in _zustand(conn).values():
        if h["status"] != FREIGEGEBEN:
            continue
        fa = h.get("faellig_um")
        if fa is None or str(fa) <= str(jetzt_iso):
            faellig.append(h)
    return faellig


def ueberfaellige(conn, jetzt_iso: str, minuten: int = UEBERFAELLIG_MIN) -> list[dict]:
    """Die FREIGEGEBENEN Hände, die schon LÄNGER als ``minuten`` fällig sind und immer noch nicht
    ausgeführt — ein Zeichen, dass der Membran-Sende-Tick (der die Fälligen leeren sollte) STILL
    STEHT (der Herzschlag-Wächter). Reine read-time-Projektion; ``jetzt_iso`` reicht die Membran /
    das Diagnose-Kommando herein (der Kern liest keine Wanduhr). Anders als :func:`faellige` lässt
    dies das normale Sendefenster in Ruhe: eine gerade eben fällige Hand ist noch kein Stillstand.
    Eine Hand ohne ``faellig_um`` ist hier nicht messbar (keine Fälligkeit) und zählt nicht.

    Braucht — anders als der reine lexikografische Vergleich in :func:`faellige` — echte
    Zeit-Arithmetik (``jetzt - minuten``); ein unparsbarer Zeitstempel wird still übersprungen,
    statt den Wächter abstürzen zu lassen."""
    try:
        grenze = datetime.datetime.fromisoformat(str(jetzt_iso)) - datetime.timedelta(minutes=minuten)
    except ValueError:
        return []
    spaet = []
    for h in _zustand(conn).values():
        if h["status"] != FREIGEGEBEN:
            continue
        fa = h.get("faellig_um")
        if fa is None:
            continue
        try:
            # Der Vergleich MUSS im Wächter liegen: ein unparsbares faellig_um (ValueError) ODER
            # ein zeitzonen-behafteter Stempel gegen unsere naive Uhr (TypeError bei aware≠naiv)
            # überspringt die Hand still, statt den Wächter — und damit die Morgen-Nachricht,
            # die ihn NICHT umschließt — abstürzen zu lassen.
            if datetime.datetime.fromisoformat(str(fa)) <= grenze:
                spaet.append(h)
        except (ValueError, TypeError):
            continue
    return spaet


def markiere_ausgefuehrt(conn, hand_id: int, ergebnis: str = "gesendet") -> dict:
    """DER HARTE KERN-CONSTRAINT (§8): eine Außenhandlung wird nur als ausgeführt vermerkt, wenn
    sie FREIGEGEBEN ist (ein menschliches OK liegt vor) — und GENAU EINMAL. Kein ``override``:
    die Bestätigung ist das Gate, es gibt keinen Weg daran vorbei. Die Membran ruft dies NACH
    dem tatsächlichen Senden; ohne vorherige Freigabe darf gar nicht erst gesendet werden
    (:func:`faellige` gibt nur Freigegebene aus).

    ATOMAR: Lesen des Zustands + Prüfung + Anhängen laufen unter EINEM Schreib-Lock
    (``BEGIN IMMEDIATE``), damit zwei gleichzeitige Membran-/Cron-Läufe nicht beide dieselbe Hand
    ausführen (der zweite wartet auf den Lock, liest dann den frischen Zustand AUSGEFUEHRT und
    verweigert) -- exakt-einmal auch nebenläufig."""
    with _schreib_lock(conn):
        h = _zustand(conn).get(hand_id)
        if h is None:
            conn.rollback()
            return {"ausgefuehrt": False, "grund": "Unbekannte Hand."}
        if h["status"] == AUSGEFUEHRT:
            conn.rollback()
            return {"ausgefuehrt": False, "grund": "Schon ausgeführt (genau einmal, nie doppelt)."}
        if h["status"] != FREIGEGEBEN:
            conn.rollback()
            return {"ausgefuehrt": False,
                    "grund": f"NICHT freigegeben (Status „{h['status']}“) — ohne Bestätigung "
                             f"keine Außenhandlung."}
        ledger.append(conn, HAND_AUSGEFUEHRT, {"hand_id": hand_id, "ergebnis": str(ergebnis)})
        conn.commit()
        return {"ausgefuehrt": True, "hand_id": hand_id}
