"""Der Verstehens-Würfel als WISSEN: das Absichts-Raster lebt als Teilgraph im Ledger.

Ronnys Einsicht (2026-07-03): "die Unterscheidungen stehen ja alle im Zusammenhang. das kennen
wir von den Begriffen." Das Raster der Gesprächs-Absichten ist keine Konfigurationsliste im
Code -- es ist Wissen, in exakt derselben Form wie alles andere Wissen hier: Ausprägungen sind
Knoten (``absicht:definition``), ihre Zusammenhänge sind gewöhnliche, herkunfts-tragende
``is_a``-Relationen, gesät mit Quelle "ronny" (Mensch, voll vertraut -- wie der Lehrer-Loop).
Damit erbt das Verstehen die komplette vorhandene Maschinerie umsonst: Herkunft und Vertrauen
je Kante, Read-time-Konfidenz, Widerspruch->Inquiry, und später Governance für vom Scan
VORGESCHLAGENE neue Unterscheidungen (gedeckelt, bis bestätigt).

Zwei Radien, eine Disziplin: fürs LESEN ist das Raster von Anfang an groß (beobachten kostet
nichts und kann nichts verderben); GEHANDELT wird nur aus Zellen, für die im Companion ein
deterministischer Kern existiert -- Können ist Code, Wissen über Absichten ist Graph. Eine
gelesene Zelle ohne Können ist kein Fehler, sondern ein benannter Sammelplatz: GENUS sagt
ehrlich, WAS es noch nicht kann, und die Belegungszahlen priorisieren den Ausbau aus gelebten
Gesprächen statt aus Bauchgefühl.

Kennzahlen (QM am Verstehen): die erste ist die Belegung -- wie oft eine Zelle gelesen wurde,
je Herkunft (festes Muster vs. Deuter). Sie wird read-time aus dem Event-Log gezählt, nichts
Neues gespeichert. Weitere (Treffer-Quote aus Folge-Signalen, Stabilität) folgen, wenn die
Daten da sind -- selbst-kalibriert, keine Presets.

Ledger != Memory bleibt gewahrt: für eine BEKANNTE Zelle wird nur Struktur festgehalten
(Zelle + Herkunft der Lesart), nie Gesprächstext. Nur eine raster-FREMDE freie Lesart wird
mit den eigenen Worten des Modells notiert (Quelle ``model:*``, automatisch gedeckelt) --
denn genau sie ist das Lernmaterial, aus dem neue Ausprägungen erkannt werden.
"""
from __future__ import annotations

from genus import sources

SEED_SOURCE = "ronny"
READING_PREDICATE = "gelesen"          # (absicht:X, gelesen, <quelle>) -- Struktur, kein Text
FREE_READING_PREDICATE = "gelesen_als" # (absicht:unklar, gelesen_als, <Modell-Worte>)
FREE_READING_SOURCE = "model:deuter"

# Ronnys Saat-Tabelle (2026-07-03), Merkmal 1 · Absicht: (Ausprägung, Elternteil).
# Bewusst ASCII-Schlüssel (das Modell muss sie exakt zurückgeben können); die Wurzel ist
# "aeusserung". Merkmal 2-4 (Gegenstand, Bezug, Form) bleiben vorerst implizit im Dispatch
# (subject-Term, last_question) -- eigene Teilgraphen erst, wenn eine Fähigkeit sie braucht.
RASTER_SEED: tuple[tuple[str, str], ...] = (
    ("wissensfrage", "aeusserung"),
    ("definition", "wissensfrage"),
    ("beziehung", "wissensfrage"),
    ("vergleich", "wissensfrage"),
    ("eigenschaft", "wissensfrage"),
    ("ursache", "wissensfrage"),
    ("menge", "wissensfrage"),
    ("grammatik", "wissensfrage"),
    ("genus-auskunft", "aeusserung"),
    ("zustand", "genus-auskunft"),
    ("offene-fragen", "genus-auskunft"),
    ("faehigkeiten", "genus-auskunft"),
    ("erinnerungs-abruf", "aeusserung"),
    ("aufforderung", "aeusserung"),
    ("merken", "aufforderung"),
    ("lernen", "aufforderung"),
    ("tun", "aufforderung"),
    ("mitteilung", "aeusserung"),
    ("tatsache", "mitteilung"),
    ("meinung", "mitteilung"),
    ("korrektur", "mitteilung"),
    ("empfehlungsfrage", "aeusserung"),
    ("sozialgeste", "aeusserung"),
    ("gruss", "sozialgeste"),
    ("dank", "sozialgeste"),
    ("lob", "sozialgeste"),
    ("kritik", "sozialgeste"),
    ("abschied", "sozialgeste"),
    ("meta", "aeusserung"),
    ("kuerzer", "meta"),
    ("ausfuehrlicher", "meta"),
    ("anders-erklaeren", "meta"),
    ("wiederholen", "meta"),
    ("nachfrage", "aeusserung"),
    ("warum-herkunft", "nachfrage"),
    ("vertiefung", "nachfrage"),
    ("bezug", "nachfrage"),
    ("unklar", "aeusserung"),
)


def node(kind: str) -> str:
    return f"absicht:{kind}"


def seed_raster(conn) -> int:
    """Sow the Absichts-Raster into the ledger as ordinary is_a relations, source "ronny".
    Idempotent: an edge already in the graph is skipped (the ledger is append-only, so a
    naive re-run would pile up duplicate events). Returns how many NEW edges were sown."""
    from genus import reactors  # local: keeps this module's import surface a leaf

    existing = {
        (r["subject"], r["object"])
        for r in sources.relations(conn, predicate="is_a")
        if r["subject"].startswith("absicht:")
    }
    sown = 0
    for kind, parent in RASTER_SEED:
        edge = (node(kind), node(parent))
        if edge in existing:
            continue
        reactors.observe_relation(conn, edge[0], "is_a", edge[1], SEED_SOURCE)
        sown += 1
    return sown


def kinds(conn) -> set[str]:
    """Every Ausprägung the graph knows (child OR parent side of a sown edge), bare keys."""
    result: set[str] = set()
    for r in sources.relations(conn, predicate="is_a"):
        for side in (r["subject"], r["object"]):
            if side.startswith("absicht:"):
                result.add(side.split(":", 1)[1])
    return result


def leaf_kinds(conn) -> list[str]:
    """The Ausprägungen with no children -- what the Deuter is offered to choose from (a
    parent like "wissensfrage" is a fallback landing, not a reading the model should pick)."""
    all_kinds = kinds(conn)
    parents_of_something = {
        r["object"].split(":", 1)[1]
        for r in sources.relations(conn, predicate="is_a")
        if r["object"].startswith("absicht:") and r["subject"].startswith("absicht:")
    }
    return sorted(all_kinds - parents_of_something)


def parents(conn, kind: str) -> list[str]:
    """The is_a ancestors of an Ausprägung, closest first -- the dispatch climbs this chain
    when the read cell itself has no handler (a too-fine or slightly-off reading falls SOFT
    onto the nearest actionable ancestor, exactly like inference climbs concept is_a)."""
    chain: list[str] = []
    current, seen = node(kind), {node(kind)}
    while True:
        ups = [r["object"] for r in sources.relations(conn, subject=current, predicate="is_a")
               if r["object"].startswith("absicht:") and r["object"] not in seen]
        if not ups:
            return chain
        current = ups[0]
        seen.add(current)
        chain.append(current.split(":", 1)[1])


def record_reading(conn, kind: str, quelle: str) -> None:
    """One Einordnung, recorded as pure structure: (absicht:X, gelesen, quelle). The event
    itself is the tally mark; counting happens read-time (:func:`belegung`). ``quelle`` is
    "muster" (a fixed pattern read it, GENUS's own deterministic observation) or
    "model:deuter" (the edge model read it -- automatically trust-capped like every model
    source). Never any conversation text."""
    from genus import reactors

    reactors.observe_relation(conn, node(kind), READING_PREDICATE, quelle, quelle)


def record_free_reading(conn, reading: str) -> None:
    """An off-grid reading in the model's OWN words -- the differentiation material for new
    Ausprägungen, collected under absicht:unklar, capped model source. The user's words are
    never stored; only what the model said the intent was."""
    from genus import reactors

    reactors.observe_relation(conn, node("unklar"), FREE_READING_PREDICATE, reading,
                              FREE_READING_SOURCE)


def free_readings(conn) -> list[str]:
    """The collected off-grid readings -- what the scan (later slice) will differentiate over."""
    return [r["object"] for r in sources.relations(
        conn, subject=node("unklar"), predicate=FREE_READING_PREDICATE)]


def belegung(conn, kind: str) -> dict:
    """Kennzahl 1 (QM am Verstehen): how often this cell was read, per Herkunft -- counted
    read-time from the event log (every recorded reading is one relation_asserted event),
    nothing new stored.

    Retraction-aware: a reading is an ordinary relation, so a mis-count (e.g. a verification
    run that wrote into the live ledger) is corrected the ordinary way -- ``reactors.
    retract_relation(node(kind), READING_PREDICATE, quelle, source=quelle)`` -- and the count
    nets asserted minus retracted per Herkunft. Reading the raw event_log (not the projection,
    which collapses the UNIQUE (s,p,o,source) tuple to one row and would lose the tally) is
    what makes a real COUNT possible; netting the retractions is what keeps it CORRECTABLE."""
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
