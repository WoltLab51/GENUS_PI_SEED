"""Der Verstehens-Würfel als echte Zwicky-Box: drei unabhängige Parameter, kein flaches Raster.

Ronny (2026-07-03, nach einer echten enttäuschenden Session): "wir machen noch grundsätzliche
Dinge falsch, denke ich! in welche Merkmale zerfällt denn eine Nachricht?" -- und, schärfer:
"ich habe von Anfang an Zwicky gesagt! mach das so richtig wissenschaftlich!" Die vorige
Fassung dieses Moduls hatte EIN Raster ("Absicht") mit ~30 Werten und einer is_a-Fallback-
Leiter -- das ist immer noch eine LISTE, kein morphologischer Kasten. Zwickys General
Morphological Analysis (1948/1969) hat vier Schritte: (1) unabhängige Parameter finden,
(2) ihre Werte aufzählen, (3) das Kreuzprodukt bilden, (4) KREUZ-KONSISTENZ prüfen -- welche
Kombinationen sind überhaupt sinnvoll. Schritt 4 fehlte komplett; die Live-Fehlgriffe von
heute (Wetterfrage->vergleich, Hilfe-Bitte->abschied) lagen alle auf Zellen, die es als
eigenständiges Ding in der flachen Liste gar nicht gab.

Drei Parameter, aus etablierter Wissenschaft, nicht ad-hoc erfunden:
- **Sprechakt** (Searle 1969, Sprechakttheorie): frage, aussage, aufforderung, floskel --
  WAS für ein sprachlicher Zug ist das.
- **Gegenstand**: begriff (ein Wort/Konzept im eigenen Graphen), genus (GENUS selbst),
  nutzer (die Person), gespraech (das laufende Gespräch, rückbezüglich), welt (draußen,
  ungespeichert) -- WORUM geht es.
- **Bezug**: eigenständig oder rückbezüglich auf den letzten Zug. Heute strukturell aus dem
  Gegenstand abgeleitet (gespraech ⇒ rückbezüglich, sonst eigenständig) -- ein echtes,
  gesätes Merkmal, aber noch nicht unabhängig GEBRAUCHT (erkannt für später, z.B. Ellipsen
  wie "und die Katze?"; nicht spekulativ vorgebaut, siehe representation-dimensions-as-Merkmale).

Kreuz-Konsistenz (Zwickys Schritt 4, kein Nebenprodukt): von 3×5=15 möglichen (Sprechakt,
Gegenstand)-Kombinationen plus der gegenstandslosen Floskel sind nur 11 tatsächlich gesät --
`ZELLEN` unten. Ausgeschlossen, mit Begründung: aussage-genus/aussage-gespraech (eine
"Behauptung über GENUS/das Gespräch" ist keine natürliche eigene Sprechhandlung -- das wäre
eher Lob oder eine Meta-Frage), aufforderung-begriff/aufforderung-nutzer (eine Aufforderung
braucht ein Ziel, das handeln kann -- ein bloßer Begriff kann nicht "aufgefordert" werden,
und GENUS kann nicht den Nutzer auffordern, die Richtung ist falsch herum), aussage-welt
(eine reale, aber heute unbelegte Zelle -- kein Blatt/Vokabular existiert dafür, erst säen
wenn ein echter Fall auftritt).

Jede Zelle ist eine echte Kombination, keine Namenskonvention: `zelle:X -kombiniert_aus->
sprechakt:Y`, `-kombiniert_aus-> gegenstand:Z`, `-kombiniert_aus-> bezug:W` -- drei gewöhnliche,
herkunftstragende Relationen (Quelle "ronny"), so dass "welche Zellen nutzen gegenstand:welt?"
eine echte Graph-Abfrage ist, nicht Implementierungsdetail. Die bestehenden Feinblätter
(definition, beziehung, gruss, kuerzer, ...) bleiben unverändert -- nur ihr is_a-Elternteil ist
jetzt die echte Kreuzprodukt-Zelle statt eines Ad-hoc-Sammelbegriffs ("wissensfrage",
"mitteilung", "meta"). Der Dispatch klettert dadurch höchstens EINEN Schritt (Blatt -> Zelle),
nicht mehr beliebig tief.

Segmentierung (ISO 24617-2, Dialogue Act Markup Language): ein Turn zerfällt in mehrere
funktionale Segmente, jedes mit eigenem Dialogakt -- "Hallo! Was ist ein Hund? Danke!" sind
DREI Segmente, nicht eins. Das ist NICHT hier in verstehen.py verankert (die Segmentierung
selbst passiert im Deuter, deploy/deuter.py gibt eine LISTE von Lesarten zurück) -- dieses
Modul bleibt, was es war: das Raster als Wissen, jetzt nur mit der richtigen Form.

Zwei Radien, eine Disziplin, unverändert: fürs LESEN ist das Raster von Anfang an vollständig
(Kreuz-Konsistenz IST die vollständige, geprüfte Form); GEHANDELT wird nur aus Zellen, für die
im Companion ein deterministischer Kern existiert. Belegung (Kennzahl 1, QM am Verstehen)
bleibt unverändert: wie oft ein Blatt gelesen wurde, je Herkunft, retraktions-bewusst gezählt.
"""
from __future__ import annotations

from genus import sources

SEED_SOURCE = "ronny"
READING_PREDICATE = "gelesen"        # (absicht:X, gelesen, <quelle>) -- Struktur, kein Text
KOMBINIERT_AUS = "kombiniert_aus"    # (zelle:X, kombiniert_aus, sprechakt:Y/gegenstand:Z/bezug:W)

SPRECHAKTE: tuple[str, ...] = ("frage", "aussage", "aufforderung", "floskel")
GEGENSTAENDE: tuple[str, ...] = ("begriff", "genus", "nutzer", "gespraech", "welt")
BEZUEGE: tuple[str, ...] = ("eigenstaendig", "rueckbezueglich")

# Kreuz-Konsistenz-Tabelle (Zwickys Schritt 4): (Sprechakt, Gegenstand) -> Zellenname.
# Gegenstand=None für die gegenstandslose Floskel (ein Gruß ist über nichts).
ZELLEN: dict[tuple[str, str | None], str] = {
    ("frage", "begriff"): "frage-begriff",
    ("frage", "genus"): "frage-genus",
    ("frage", "nutzer"): "frage-nutzer",
    ("frage", "gespraech"): "frage-gespraech",
    ("frage", "welt"): "frage-welt",
    ("aussage", "begriff"): "aussage-begriff",
    ("aussage", "nutzer"): "aussage-nutzer",
    ("aufforderung", "genus"): "aufforderung-genus",
    ("aufforderung", "gespraech"): "aufforderung-gespraech",
    ("aufforderung", "welt"): "aufforderung-welt",
    ("floskel", None): "floskel",
}

# Bezug ist strukturell vom Gegenstand abgeleitet (siehe Moduldoc) -- kein eigenes Deuter-Feld.
_BEZUG_VON_GEGENSTAND = {"gespraech": "rueckbezueglich"}


def _bezug_fuer(gegenstand: str | None) -> str:
    return _BEZUG_VON_GEGENSTAND.get(gegenstand, "eigenstaendig")


def node(kind: str) -> str:
    """Ein Feinblatt (Ausprägung) -- unverändert seit der vorigen Fassung."""
    return f"absicht:{kind}"


def zelle_node(zelle: str) -> str:
    return f"zelle:{zelle}"


def sprechakt_node(s: str) -> str:
    return f"sprechakt:{s}"


def gegenstand_node(g: str) -> str:
    return f"gegenstand:{g}"


def bezug_node(b: str) -> str:
    return f"bezug:{b}"


# Feinblätter: (Blatt, Zelle) -- dieselben Namen/Handler wie vorher, jetzt unter den echten
# Kreuzprodukt-Zellen. "bezug" (der alte Blattname für einen Pronomen-Anschluss wie "und er?")
# wurde in "anschlussfrage" umbenannt -- Kollision mit dem neuen Achsennamen "Bezug" vermieden.
RASTER_SEED: tuple[tuple[str, str], ...] = (
    ("definition", "frage-begriff"), ("beziehung", "frage-begriff"), ("vergleich", "frage-begriff"),
    ("grammatik", "frage-begriff"), ("eigenschaft", "frage-begriff"), ("ursache", "frage-begriff"),
    ("menge", "frage-begriff"),
    ("zustand", "frage-genus"), ("offene-fragen", "frage-genus"), ("faehigkeiten", "frage-genus"),
    ("empfehlungsfrage", "frage-genus"), ("ziele", "frage-genus"),
    ("erinnerungs-abruf", "frage-nutzer"),
    ("warum-herkunft", "frage-gespraech"), ("vertiefung", "frage-gespraech"),
    ("anschlussfrage", "frage-gespraech"),
    ("weltfrage", "frage-welt"),
    ("korrektur", "aussage-begriff"),
    ("tatsache", "aussage-nutzer"), ("merken", "aussage-nutzer"), ("meinung", "aussage-nutzer"),
    ("lernen", "aufforderung-genus"), ("berechnen", "aufforderung-genus"),
    ("kuerzer", "aufforderung-gespraech"), ("ausfuehrlicher", "aufforderung-gespraech"),
    ("anders-erklaeren", "aufforderung-gespraech"), ("wiederholen", "aufforderung-gespraech"),
    ("tun", "aufforderung-welt"),
    ("gruss", "floskel"), ("dank", "floskel"), ("lob", "floskel"), ("kritik", "floskel"),
    ("abschied", "floskel"),
)


def seed_raster(conn) -> int:
    """Sät die komplette Zwicky-Box: jede Zelle kombiniert_aus ihrem Sprechakt (+Gegenstand,
    +Bezug), jedes Feinblatt is_a seiner Zelle. Idempotent über den geteilten Sä-Helfer
    (``reactors.sae_fehlende``, Phase 0 der Ziel-Architektur): eine schon vorhandene
    Kante wird übersprungen. Gibt die Zahl neu gesäter Kanten zurück."""
    from genus import reactors

    tripel: list[tuple[str, str, str]] = []
    for (sprechakt, gegenstand), zelle in ZELLEN.items():
        zn = zelle_node(zelle)
        tripel.append((zn, KOMBINIERT_AUS, sprechakt_node(sprechakt)))
        tripel.append((zn, KOMBINIERT_AUS, bezug_node(_bezug_fuer(gegenstand))))
        if gegenstand is not None:
            tripel.append((zn, KOMBINIERT_AUS, gegenstand_node(gegenstand)))
    for leaf, zelle in RASTER_SEED:
        tripel.append((node(leaf), "is_a", zelle_node(zelle)))
    return reactors.sae_fehlende(conn, tripel, SEED_SOURCE)


def kinds(conn) -> set[str]:
    """Jedes gesäte Feinblatt (Ausprägung) -- was der Deuter pro Segment lesen kann."""
    return {
        r["subject"].split(":", 1)[1]
        for r in sources.relations(conn, predicate="is_a")
        if r["subject"].startswith("absicht:")
    }


def leaf_kinds(conn) -> list[str]:
    """Alle Feinblätter -- in der neuen Struktur ist jedes absicht:*-Blatt schon ein echtes
    Blatt (die Eltern sind jetzt zelle:*, ein anderer Namensraum), keine weitere Filterung nötig."""
    return sorted(kinds(conn))


def zelle_of(conn, kind: str) -> str | None:
    """Die Kreuzprodukt-Zelle eines Feinblatts (sein is_a-Elternteil) -- der EINE weiche
    Landeplatz, falls das Blatt selbst keinen Handler hat. Anders als die vorige mehrstufige
    is_a-Kletterei ist das jetzt genau EIN Schritt: Blatt -> Zelle, nie tiefer (die Zelle IST
    schon die gröbste sinnvolle Einheit -- "irgendeine Frage" ohne Gegenstand wäre keine
    handelbare Stufe mehr). ``None`` wenn das Blatt nicht gesät/unbekannt ist."""
    for r in sources.relations(conn, subject=node(kind), predicate="is_a"):
        if r["object"].startswith("zelle:"):
            return r["object"].split(":", 1)[1]
    return None


def zellen_von(conn, sprechakt: str | None = None, gegenstand: str | None = None) -> list[str]:
    """Alle gesäten Zellen, optional gefiltert nach Sprechakt und/oder Gegenstand -- eine
    ECHTE Graph-Abfrage über die Kreuz-Konsistenz-Tabelle (z.B. "welche Zellen nutzen
    gegenstand:welt?"), nicht nur Python-Introspektion von ``ZELLEN``."""
    kandidaten = {r["subject"] for r in sources.relations(conn, predicate=KOMBINIERT_AUS)}
    if sprechakt is not None:
        kandidaten &= {r["subject"] for r in sources.relations(
            conn, predicate=KOMBINIERT_AUS, object=sprechakt_node(sprechakt))}
    if gegenstand is not None:
        kandidaten &= {r["subject"] for r in sources.relations(
            conn, predicate=KOMBINIERT_AUS, object=gegenstand_node(gegenstand))}
    return sorted(z.split(":", 1)[1] for z in kandidaten if z.startswith("zelle:"))


def record_reading(conn, kind: str, quelle: str) -> None:
    """Eine Einordnung, als reine Struktur festgehalten: (absicht:X, gelesen, quelle).
    Unverändert seit der vorigen Fassung -- ``quelle`` ist "muster" oder "model:deuter"."""
    from genus import reactors

    reactors.observe_relation(conn, node(kind), READING_PREDICATE, quelle, quelle)


def belegung(conn, kind: str) -> dict:
    """Kennzahl 1 (QM am Verstehen), unverändert: wie oft dieses Blatt gelesen wurde, je
    Herkunft, retraktions-bewusst gezählt (siehe frühere Fassung für die volle Begründung)."""
    counts: dict[str, int] = {}
    for event_type, delta in (("relation_asserted", 1), ("relation_retracted", -1)):
        for row in conn.execute(
            """
            SELECT json_extract(payload, '$.object') AS quelle, COUNT(*) AS n
            FROM event_log
            WHERE event_type = ?
              AND json_extract(payload, '$.subject') = ?
              AND json_extract(payload, '$.predicate') = ?
            GROUP BY quelle
            """,
            (event_type, node(kind), READING_PREDICATE),
        ).fetchall():
            counts[row["quelle"]] = counts.get(row["quelle"], 0) + delta * row["n"]
    je_quelle = {q: n for q, n in counts.items() if n > 0}
    return {"kind": kind, "gesamt": sum(je_quelle.values()), "je_quelle": je_quelle}
