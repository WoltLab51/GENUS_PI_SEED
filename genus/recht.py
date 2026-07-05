"""Die erste DENKWEISE: juristische Subsumtion (Ronny 2026-07-05, docs/GENUS_INTELLIGENZ.md §4).

Eine Denkweise = ein Satz Operationen + ihr Material + ihr Beweismaßstab. Die juristische
Methode ist selbst eine Glaskasten-Methode (erfunden, damit Denken auditierbar wird), darum
passt sie GENUS im Wesen. Die Abbildung auf Vorhandenes:

  Norm (Anspruchsgrundlage)   = ein BAUPLAN im Graphen: `norm:X -braucht-> merkmal:A`,
                                `-braucht-> merkmal:B`, `-bewirkt-> rechtsfolge:Y`. Rekursiv:
                                ein Merkmal kann selbst eine Norm sein (Kaufvertrag = Angebot
                                + Annahme) -- dieselbe Kletterei wie is_a, nur über `braucht`.
  Sachverhalt                 = welche Merkmale der konkrete Fall erfüllt, JE MIT QUELLE
                                (deine Aussage = Parteivortrag; ein Dokument = Urkunde, härter).
  Subsumtion (Justizsyllogismus) = die VERALLGEMEINERUNG der is_a-Inferenz: prüfe jedes
                                Merkmal gegen den Sachverhalt; sind alle erfüllt, folgt die
                                Rechtsfolge -- als abgeleitete Aussage mit voller
                                Prämissenkette. VERTRAUEN = SCHWÄCHSTE PRÄMISSE (genau wie bei
                                is_a) -- und das ist zugleich das BEWEISLAST-RADAR: die Zeile,
                                die nur an deiner Aussage hängt, wird die Gegenseite bestreiten.
  Wertung ("angemessen")      = ein ehrlicher MENSCH-SLOT (Merkmal mit `-art-> wertung`):
                                die Deduktion endet, GENUS füllt ihn NIE selbst, es benennt
                                ihn als das, was menschliches Urteil (oder einen Anwalt) braucht.

Alles read-time und gläsern: die NORM ist dauerhaftes Wissen (gesät wie das Raster/die Ziele),
der SACHVERHALT ist flüchtige Eingabe (kein Fall-Fakt wird ins Ledger gesät -- ein Rechtsfall
ist sensibel; Ledger ≠ Memory). Die Subsumtion erzeugt nichts, sie RECHNET -- und ihr Ergebnis
ist der gerenderte Beweisbaum. Kein Anwalt: bei echter Unsicherheit sagt GENUS das.
"""
from __future__ import annotations

from genus import sources

NORM_PREFIX = "norm:"
MERKMAL_PREFIX = "merkmal:"
BRAUCHT = "braucht"          # norm/merkmal -braucht-> merkmal (die Tatbestandsmerkmale)
BEWIRKT = "bewirkt"          # norm -bewirkt-> rechtsfolge
INHALT = "inhalt"            # menschlicher Wortlaut (wie bei Zielen/Episoden)
ART = "art"                  # merkmal -art-> wertung  (der Mensch-Slot)
WERTUNG = "wertung"

SEED_SOURCE = "gesetz"       # Bootstrap-Boden: die Norm IST Gesetz (hand-gesät wie RASTER_SEED)

# Die erste Anspruchsgrundlage: Kaufpreiszahlungsanspruch (§ 433 Abs. 2 BGB) -- der häufigste
# Alltagsfall. Rekursiv: „Kaufvertrag" ist selbst eine Norm (Angebot + Annahme), damit der
# Merkmal-Baum von Anfang an echt zweistufig ist (der is_a-Kletter-Analog über `braucht`).
NORM_SEED: tuple[tuple[str, str, str], ...] = (
    ("norm:kaufpreis", INHALT, "Anspruch auf Zahlung des Kaufpreises (§ 433 Abs. 2 BGB)"),
    ("norm:kaufpreis", BRAUCHT, "merkmal:kaufvertrag"),
    ("norm:kaufpreis", BRAUCHT, "merkmal:faelligkeit"),
    ("norm:kaufpreis", BEWIRKT, "rechtsfolge:kaufpreiszahlung"),
    ("rechtsfolge:kaufpreiszahlung", INHALT,
     "der Verkäufer kann vom Käufer Zahlung des Kaufpreises verlangen"),
    # das zusammengesetzte Merkmal „Kaufvertrag" als Unter-Norm (Rekursion)
    ("merkmal:kaufvertrag", INHALT, "ein wirksamer Kaufvertrag (Angebot und Annahme)"),
    ("merkmal:kaufvertrag", BRAUCHT, "merkmal:angebot"),
    ("merkmal:kaufvertrag", BRAUCHT, "merkmal:annahme"),
    ("merkmal:angebot", INHALT, "ein Angebot über den Kauf (Ware und Preis bestimmt)"),
    ("merkmal:annahme", INHALT, "die Annahme dieses Angebots durch die andere Partei"),
    ("merkmal:faelligkeit", INHALT,
     "der Kaufpreis ist fällig (keine Stundung, kein Zurückbehaltungsrecht)"),
)


def seed_normen(conn) -> int:
    """Sät die Anspruchsnormen als Bauplan -- idempotent über den geteilten Sä-Helfer."""
    from genus import reactors

    return reactors.sae_fehlende(conn, [(s, p, o) for s, p, o in NORM_SEED], SEED_SOURCE)


def _objekte(conn, subjekt: str, praedikat: str) -> list[str]:
    return [r["object"] for r in sources.relations(conn, subject=subjekt, predicate=praedikat)]


def _inhalt(conn, knoten: str) -> str:
    o = _objekte(conn, knoten, INHALT)
    return o[0] if o else knoten


def _ist_wertung(conn, merkmal: str) -> bool:
    return WERTUNG in _objekte(conn, merkmal, ART)


def _evidenz_art(quelle: str) -> str:
    """Beweisrechtlich: eine Urkunde ist härter als Parteivortrag. Strukturelle Natur des
    Beweises, kein Schwellwert -- eine ``dokument:*``-Quelle belegt, eine Partei behauptet."""
    return "urkunde" if quelle.split(":", 1)[0] in ("dokument", "urkunde", "zeuge") else "parteivortrag"


_SCHWAECHE = {"urkunde": 0, "abgeleitet": 1, "parteivortrag": 2}   # größer = schwächer belegt


def _pruefe_merkmal(conn, merkmal: str, sachverhalt: dict[str, str]) -> dict:
    """Ein Tatbestandsmerkmal gegen den Sachverhalt: direkt erfüllt (eine Quelle im
    Sachverhalt), abgeleitet erfüllt (ein zusammengesetztes Merkmal, dessen Unter-Merkmale
    alle erfüllt sind -- Rekursion) oder offen. Ein Wertungs-Merkmal wird NIE selbst
    gefüllt -- es ist ein Mensch-Slot."""
    inhalt = _inhalt(conn, merkmal)
    if _ist_wertung(conn, merkmal):
        return {"merkmal": merkmal, "inhalt": inhalt, "erfuellt": False, "art": "wertung",
                "quelle": None, "trust": None,
                "hinweis": "braucht menschliches Urteil (oder einen Anwalt) — das entscheide nicht ich"}
    unter = _objekte(conn, merkmal, BRAUCHT)
    if unter:                                    # zusammengesetztes Merkmal -> Unter-Norm, rekursiv
        sub = subsumiere(conn, merkmal, sachverhalt)
        return {"merkmal": merkmal, "inhalt": inhalt, "erfuellt": sub["erfuellt"],
                "art": "abgeleitet", "quelle": None, "trust": sub["vertrauen"], "unter": sub}
    if merkmal in sachverhalt:                   # direkt erfüllt, mit Quelle
        quelle = sachverhalt[merkmal]
        return {"merkmal": merkmal, "inhalt": inhalt, "erfuellt": True,
                "art": _evidenz_art(quelle), "quelle": quelle,
                "trust": round(sources.source_trust(conn, quelle), 3)}
    return {"merkmal": merkmal, "inhalt": inhalt, "erfuellt": False, "art": "offen",
            "quelle": None, "trust": None}


def subsumiere(conn, norm: str, sachverhalt: dict[str, str]) -> dict:
    """Der Justizsyllogismus: prüft jedes Merkmal der ``norm`` gegen den ``sachverhalt``
    (Merkmal -> Quelle). Sind ALLE erfüllt, folgt die Rechtsfolge. Vertrauen = schwächste
    Prämisse (die Verallgemeinerung der is_a-Inferenz); die schwächste Stelle ist zugleich
    das Beweislast-Radar. Read-time, erzeugt nichts."""
    merkmale = [_pruefe_merkmal(conn, m, sachverhalt)
                for m in _objekte(conn, norm, BRAUCHT)]
    erfuellt = bool(merkmale) and all(m["erfuellt"] for m in merkmale)
    belegte = [m for m in merkmale if m["erfuellt"] and m["trust"] is not None]
    vertrauen = min((m["trust"] for m in belegte), default=None)
    # die schwächste Prämisse: am schwächsten belegtes erfülltes Merkmal (Beweislast-Radar)
    schwaechste = None
    if erfuellt and belegte:
        schwaechste = min(belegte, key=lambda m: (-_SCHWAECHE.get(m["art"], 1),
                                                  m["trust"]))  # schwächste Art, dann kleinstes Vertrauen
    rf = _objekte(conn, norm, BEWIRKT)
    return {
        "norm": norm, "inhalt": _inhalt(conn, norm),
        "rechtsfolge": rf[0] if rf else None,
        "rechtsfolge_inhalt": _inhalt(conn, rf[0]) if rf else None,
        "erfuellt": erfuellt,
        "merkmale": merkmale,
        "offen": [m for m in merkmale if not m["erfuellt"]],
        "vertrauen": vertrauen,
        "schwaechste": schwaechste,
    }


# --- Deuter-Anbindung: freier Text → Merkmale (das Modell liest, der Kern rechnet) -------
#
# Die Arbeitsteilung wie beim Intent-Deuter: das MODELL liest die fuzzy Fakten in Struktur
# (welche Merkmale die Schilderung erfüllt, und WOMIT belegt), der KERN rechnet die Subsumtion
# (die Logik bleibt exakt). Das Modell entscheidet NIE, ob der Anspruch besteht -- nur, welche
# Merkmale die Fakten berühren; alles, was es liest, ist Deutung (gedeckelte Quelle), vom
# Menschen zu bestätigen ("korrigiere mich"), und an der GRENZE gehalten (gbnf_sachverhalt:
# nur bekannte Merkmale, nur die drei Beweis-Arten -- ein erfundenes Merkmal ist unmöglich).

EVIDENZ_ARTEN = ("urkunde", "parteivortrag", "offen")
_EVIDENZ_QUELLE = {"urkunde": "dokument:genannt", "parteivortrag": "aussage"}


def blatt_merkmale(conn, norm: str) -> list[dict]:
    """Die BLATT-Merkmale einer Norm (rekursiv): die, die direkte Fakten brauchen (kein
    Unter-Merkmal, keine Wertung) -- genau das, was das Modell aus der Schilderung lesen
    soll. Jedes mit ``id`` und ``inhalt`` (für den Prompt)."""
    blaetter: list[dict] = []
    for m in _objekte(conn, norm, BRAUCHT):
        if _ist_wertung(conn, m):
            continue                                 # Wertung ist nie modell-lesbar (Mensch-Slot)
        if _objekte(conn, m, BRAUCHT):
            blaetter += blatt_merkmale(conn, m)       # zusammengesetzt -> hinabsteigen
        else:
            blaetter.append({"id": m, "inhalt": _inhalt(conn, m)})
    return blaetter


def gbnf_sachverhalt(blatt_ids) -> str:
    """Die GRENZE für das Fakt→Merkmal-Lesen: ein JSON-Objekt, dessen Schlüssel nur die
    bekannten Blatt-Merkmale und dessen Werte nur die drei Beweis-Arten sein können -- ein
    erfundenes Merkmal oder eine erfundene Beweisart ist strukturell unmöglich (dieselbe
    Grenze wie beim Raster-Deuter)."""
    schluessel = " | ".join(f'"\\"{m}\\""' for m in blatt_ids) or '"\\"\\""'
    evidenz = " | ".join(f'"\\"{e}\\""' for e in EVIDENZ_ARTEN)
    return "\n".join([
        'root ::= "{" ws "}" | "{" ws eintrag (ws "," ws eintrag)* ws "}"',
        'eintrag ::= schluessel ws ":" ws evidenz',
        f"schluessel ::= {schluessel}",
        f"evidenz ::= {evidenz}",
        'ws ::= [ \\t\\n\\r]*',
    ])


def subsumiere_frei(conn, norm: str, text: str, deuter) -> dict:
    """Subsumtion aus einer FREIEN Schilderung: der (injizierte) ``deuter`` liest den Text in
    ``{merkmal: evidenz}`` (evidenz ∈ EVIDENZ_ARTEN), der Kern übersetzt die Beweis-Art in
    eine Quelle und rechnet die Subsumtion deterministisch. Gibt das Subsumtions-Ergebnis
    plus die gelesene Deutung zurück -- read-time, nichts wird gesät. ``deuter`` ist
    dependency-injected wie beim Intent-Deuter (Membran ruft das Modell; Test einen Fake)."""
    blaetter = blatt_merkmale(conn, norm)
    gelesen = deuter(text, blaetter) or {}
    bekannt = {b["id"] for b in blaetter}
    sachverhalt: dict[str, str] = {}
    for merkmal, evidenz in gelesen.items():
        if merkmal in bekannt and evidenz in _EVIDENZ_QUELLE:   # "offen"/Unbekanntes fällt raus
            sachverhalt[merkmal] = _EVIDENZ_QUELLE[evidenz]
    return {"ergebnis": subsumiere(conn, norm, sachverhalt),
            "gelesen": gelesen, "sachverhalt": sachverhalt}


def narrate_frei(conn, frei: dict) -> str:
    """Der Beweisbaum aus freier Schilderung -- mit dem ehrlichen Rahmen, dass das Lesen der
    Fakten eine DEUTUNG des Modells ist (bestätigbar/korrigierbar), während die Subsumtion
    darüber deterministisch bleibt."""
    kopf = ("So lese ich deinen Fall (das ist meine Deutung — sag mir, wo ich falsch liege):")
    return kopf + "\n" + narrate_subsumtion(conn, frei["ergebnis"]) + (
        "\n(Ich bin kein Anwalt; das Lesen der Fakten kann ich falsch verstanden haben, "
        "das rechtliche Prüfen darüber ist exakt.)")


def _merkmal_zeilen(m: dict, tiefe: int = 0) -> list[str]:
    """Eine Merkmal-Zeile, und -- bei einem zusammengesetzten Merkmal -- der eingerückte
    Unter-Baum darunter (der gerenderte Merkmal-Baum, so tief wie die Rekursion reicht)."""
    pre = "  " * tiefe + "• "
    if m["erfuellt"]:
        if m["art"] == "urkunde":
            beleg = f"belegt durch {m['quelle']}"
        elif m["art"] == "abgeleitet":
            beleg = "erfüllt aus den Unter-Voraussetzungen"
        else:
            beleg = "nur Parteivortrag (deine Aussage)"
        zeile = f"{pre}{m['inhalt']} — erfüllt, {beleg}"
    elif m["art"] == "wertung":
        zeile = f"{pre}{m['inhalt']} — {m['hinweis']}"
    else:
        zeile = f"{pre}{m['inhalt']} — NICHT belegt"
    zeilen = [zeile]
    if m.get("unter"):
        for sub in m["unter"]["merkmale"]:
            zeilen += _merkmal_zeilen(sub, tiefe + 1)
    return zeilen


def narrate_subsumtion(conn, e: dict) -> str:
    """Der gerenderte Beweisbaum: Sachverhalt-Prüfung → Würdigung → Ergebnis, mit dem
    ehrlichen Beweislast-Hinweis auf die schwächste Stelle. `genus why` in förmlich."""
    zeilen = [f"Anspruch: {e['rechtsfolge_inhalt'] or e['inhalt']} ({e['inhalt']}).",
              "Voraussetzungen:"]
    for m in e["merkmale"]:
        zeilen += _merkmal_zeilen(m)
    if e["erfuellt"]:
        zeilen.append("→ Alle Voraussetzungen sind erfüllt: der Anspruch besteht.")
        s = e["schwaechste"]
        if s is not None and s["art"] == "parteivortrag":
            zeilen.append(f"Schwächste Stelle (Beweislast): „{s['inhalt']}“ hängt nur an deiner "
                          f"Aussage — genau das wird die Gegenseite bestreiten. Dafür bräuchtest "
                          f"du einen Beleg (Dokument, Zeuge).")
    else:
        offen = e["offen"]
        wertung = [m for m in offen if m["art"] == "wertung"]
        namen = ", ".join(f"„{m['inhalt']}“" for m in offen if m["art"] != "wertung")
        if namen:
            zeilen.append(f"→ Der Anspruch besteht (noch) NICHT: es fehlt {namen}.")
        if wertung:
            zeilen.append("→ Eine Voraussetzung verlangt eine Wertung, die ich nicht treffe — "
                          "das braucht menschliches Urteil oder einen Anwalt.")
    return "\n".join(zeilen)
