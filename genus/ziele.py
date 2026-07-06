"""Ziele als Wissen im Graphen -- Inversion ④ des Audits (docs/GENUS_AUDIT_2026_07.md).

Bis heute lebten GENUS' Ziele in Dokumenten und Commit-Nachrichten -- GENUS selbst wusste
nicht, DASS es Ziele hat. Für „sich selbständig weiterentwickeln, hinspüren wo eine Lücke
ist" (Ronny) muss das Ziel abfragbares Wissen sein: nur dann kann GENUS selbst benennen,
was ihm zu einem Ziel noch fehlt, und nur dann können Lerner, Inquiries und der spätere
Vorschlags-Loop zielgesteuert arbeiten statt richtungslos.

Ein Ziel ist ein gewöhnlicher, provenancter Teilgraph -- exakt dieselbe Maschinerie wie das
Absichts-Raster (genus/verstehen.py), Quelle „ronny" (Mensch, voll vertraut, es sind wörtlich
seine Ziele vom 2026-07-03):

    ziel:mission        -inhalt->  "Menschen unterstützen. digital. GENUS."
    ziel:<id>           -inhalt->  "<das Ziel in Ronnys Sinn>"
    ziel:<id>           -dient->   ziel:mission          (jedes Ziel dient der Mission)
    ziel:<id>           -braucht-> faehigkeit:<id>       (was dafür können sein muss)
    faehigkeit:<id>     -inhalt->  "<was die Fähigkeit ist>"
    faehigkeit:<id>     -status->  live | teilweise | fehlt   (ehrliche Selbst-Auskunft)

Bewusst NICHT is_a zwischen Zielen: die gelernten Schluss-Regeln (Transitivität/Symmetrie)
kalibrieren sich aus den is_a-Daten des Konzept-Graphen -- Ziel-Kanten dort hineinzumischen
würde diese Statistik still verfälschen. `dient`/`braucht` sind eigene, kleine Prädikate.

Merkmal-Disziplin: genau die Kanten, die die HEUTIGE Fähigkeit brauchen ("Was sind deine
Ziele?" / "Was fehlt dir dafür?" aus dem Graphen beantworten). Prioritäten, Fortschritts-
Prozente, Deadlines -- alles erst, wenn eine konkrete Fähigkeit ohne sie nicht baubar ist.
"""
from __future__ import annotations

from genus import sources

ZIEL_PREFIX = "ziel:"
FAEHIGKEIT_PREFIX = "faehigkeit:"
MISSION = "ziel:mission"
INHALT = "inhalt"     # wie bei Episoden: der Wortlaut
DIENT = "dient"
BRAUCHT = "braucht"
STATUS = "status"

SEED_SOURCE = "ronny"

# Ronnys Ziele (2026-07-03), nüchtern gefasst, Sinn unverändert. Seine Punkte 1 und 6
# (eigenen Code anhängen / Lücken spüren und um Erlaubnis fragen) sind EIN Ziel -- Punkt 6
# beschreibt den Prozess, Punkt 1 das Ergebnis desselben Loops.
ZIEL_SEED: tuple[tuple[str, str], ...] = (
    (MISSION, "Menschen unterstützen. digital. GENUS."),
    ("ziel:begleiter",
     "Ein wertvoller und zuverlässiger Begleiter sein — für Einzelpersonen und Gruppen/Familien."),
    ("ziel:selbst-entwicklung",
     "Sich selbständig weiterentwickeln: hinspüren, wo eine Lücke ist, einen Plan fassen, um "
     "Erlaubnis fragen — und sich selbst programmierten Code (z. B. neue Module) anhängen, "
     "hinter Gates."),
    ("ziel:trading",
     "Ronnys Trading optimieren und ggf. selbständig Trades ausführen — hinter den "
     "konservativsten Gates des ganzen Systems, Vorschlag-für-Vorschlag verdient."),
    ("ziel:unterhaltung",
     "Als Begleiter auch unterhaltsam sein: Spiele spielen und auf die Interessen des "
     "Nutzers eingehen."),
    ("ziel:private-generierung",
     "Private, unzensierte generative Inhalte für den Nutzer — erzeugt von dessen eigenem, "
     "konfiguriertem Modell-Organ, lokal."),
    ("ziel:verstehen",
     "Sich selbst und seine Umwelt verstehen."),
)

# Was jedes Ziel an Fähigkeiten braucht -- der ehrliche Ist-Stand als Graph. Eine Fähigkeit
# kann mehreren Zielen dienen (das ist der Witz eines Graphen gegenüber einer Liste).
FAEHIGKEIT_SEED: tuple[tuple[str, str, str], ...] = (
    ("faehigkeit:generator-organ",
     "Ein generatives Modell als Organ: entwirft Antworten, Pläne und Code-Vorschläge — "
     "entscheidet nie (Organ, nicht Orakel).", "teilweise"),
    ("faehigkeit:vorschlags-loop",
     "Lücke spüren → Plan als Proposal → Gate → Umsetzung nach Freigabe → Werkstatt-Entwurf. "
     "Proposal≠Change bleibt für immer hart.", "live"),
    ("faehigkeit:werkzeugkasten",
     "Kern-Fähigkeiten als geprüfte, registrierte Werkzeuge (Registry + Rezepte: live); "
     "der freie Planer darüber fehlt.", "teilweise"),
    ("faehigkeit:gedaechtnis",
     "Episoden + Abruf über den Graphen + Mehr-Zug-Arbeitsgedächtnis + Tagespuffer + "
     "Nacht-Konsolidierung + Morgen-Push: live. Semantischer Abruf (Embedding-Index): fehlt.",
     "teilweise"),
    ("faehigkeit:foederation",
     "Ein Kern pro Person plus geteilte Räume für Familien/Gruppen.", "fehlt"),
    ("faehigkeit:markt-membran",
     "Marktdaten beobachten (Membran wie beim Wetter), Signale als provenancte Behauptungen, "
     "Backtesting gegen die eigene Historie.", "fehlt"),
    ("faehigkeit:trade-gates",
     "Harte Limits, Vorschlag-pro-Trade mit menschlicher Bestätigung, gemessene Trefferquote "
     "bevor über mehr Autonomie auch nur geredet wird.", "fehlt"),
    ("faehigkeit:selbst-bild",
     "Kennt eigenen Zustand, eigene Regeln, offene Fragen (live), eigene Ziele (dieser "
     "Schnitt). Versteht eigenen Code: fehlt.", "teilweise"),
    # Die Intelligenz-Betrachtung (Ronny + Claude, 2026-07-05, docs/GENUS_INTELLIGENZ.md):
    # Intelligenz = Operationen auf Material, nicht das Archiv. Die ehrlich fehlenden
    # Kern-Operationen werden hier Wissen -- GENUS benennt sie fortan selbst.
    ("faehigkeit:denkweisen",
     "Denkweisen als konfigurierbare Methoden auf dem EINEN Kern: Merkmal-Baupläne "
     "(braucht/bewirkt) + Subsumtion als verallgemeinerte Inferenz + Beweismaßstab je "
     "Disziplin. ERSTE Denkweise LIVE: juristische Subsumtion (genus/recht.py, § 433 II "
     "als Bauplan, Beweislast=schwächste Prämisse, Wertung=Mensch-Slot). Deduktion als "
     "allgemeines Werkzeug (genus/deduktion.py, vorwärts/rückwärts) und die dritte Denkweise "
     "HYPOTHESE (genus/hypothese.py, Vermuten+Prüfen) leben. Weitere Domänen folgen.", "teilweise"),
    ("faehigkeit:abstrahieren",
     "Aus Mustern im eigenen Graphen eigene Begriffe bilden und gegen die Welt prüfen "
     "(Überraschungs-Schleife) — der Sprung vom Importieren zum Denken.", "fehlt"),
    ("faehigkeit:analogie",
     "Übertragen: eine Struktur aus einem Feld in einem anderen wiedererkennen — die "
     "generative Kern-Operation, die in jeder tiefen Betrachtung wieder auftaucht "
     "(Rechtsfortbildung, Metapher, Hypothese). ERSTER Keim LIVE: die Geschwister-Analogie "
     "der Hypothese-Denkweise (genus/hypothese.py) überträgt Eigenschaften unter Geschwistern; "
     "feldübergreifender Transfer und freie Analogie fehlen noch.", "teilweise"),
    ("faehigkeit:weltmodell",
     "Vorhersagen und Simulieren: Erwartungen bauen, an Brüchen lernen. Der Sensor-Forecast "
     "und die Überraschungs-Schleife sind der Keim; ein Weltmodell über Begriffe fehlt.",
     "teilweise"),
    ("faehigkeit:lese-sinn",
     "Dokumente und Bilder durch die Membran zu bequellten Fakten machen (Vision-Organ, "
     "model:*, gedeckelt) — heute sind sie für GENUS unsichtbar.", "fehlt"),
    ("faehigkeit:gezaehmte-kreativitaet",
     "Der Generator darf Vorschläge erfinden (Hypothese, Entwurf, Metapher), weil das "
     "Etikett immer eindeutig ist (model:*-Quelle, Proposal, Werkstatt) — Halluzination und "
     "Kreativität sind derselbe Motor, der Unterschied ist Etikett + Gate. Filter: live; "
     "bewusste generative Nutzung: fehlt.", "teilweise"),
)

ZIEL_BRAUCHT: tuple[tuple[str, str], ...] = (
    ("ziel:begleiter", "faehigkeit:gedaechtnis"),
    ("ziel:begleiter", "faehigkeit:foederation"),
    ("ziel:begleiter", "faehigkeit:generator-organ"),
    ("ziel:selbst-entwicklung", "faehigkeit:vorschlags-loop"),
    ("ziel:selbst-entwicklung", "faehigkeit:generator-organ"),
    ("ziel:selbst-entwicklung", "faehigkeit:selbst-bild"),
    ("ziel:trading", "faehigkeit:markt-membran"),
    ("ziel:trading", "faehigkeit:trade-gates"),
    ("ziel:unterhaltung", "faehigkeit:generator-organ"),
    ("ziel:private-generierung", "faehigkeit:generator-organ"),
    ("ziel:verstehen", "faehigkeit:selbst-bild"),
    ("ziel:verstehen", "faehigkeit:werkzeugkasten"),
    ("ziel:verstehen", "faehigkeit:abstrahieren"),
    ("ziel:verstehen", "faehigkeit:analogie"),
    ("ziel:verstehen", "faehigkeit:weltmodell"),
    ("ziel:begleiter", "faehigkeit:denkweisen"),
    ("ziel:begleiter", "faehigkeit:lese-sinn"),
    ("ziel:selbst-entwicklung", "faehigkeit:gezaehmte-kreativitaet"),
    ("ziel:unterhaltung", "faehigkeit:gezaehmte-kreativitaet"),
)


def seed_ziele(conn) -> int:
    """Sät Mission, Ziele, Fähigkeiten und ihre Kanten -- idempotent über den geteilten
    Sä-Helfer (``reactors.sae_fehlende``, Phase 0 der Ziel-Architektur): vorhandene
    Kanten werden übersprungen, zurückgegeben wird die Zahl NEU gesäter Kanten."""
    from genus import reactors

    tripel: list[tuple[str, str, str]] = []
    for ziel_id, inhalt in ZIEL_SEED:
        tripel.append((ziel_id, INHALT, inhalt))
        if ziel_id != MISSION:
            tripel.append((ziel_id, DIENT, MISSION))
    for f_id, inhalt, status in FAEHIGKEIT_SEED:
        tripel.append((f_id, INHALT, inhalt))
        tripel.append((f_id, STATUS, status))
    for ziel_id, f_id in ZIEL_BRAUCHT:
        tripel.append((ziel_id, BRAUCHT, f_id))
    return reactors.sae_fehlende(conn, tripel, SEED_SOURCE)


def gleiche_seed_ab(conn) -> dict:
    """Der SELBST-BILD-ABGLEICH (Querschnitt der Etappen-Roadmap, 2026-07-04): wenn sich
    der ehrliche Stand einer Fähigkeit ändert (z.B. vorschlags-loop von „fehlt" auf
    „live"), ändert sich die SAAT — dieser Abgleich zieht den lebenden Graphen nach.
    Für die EIN-wertigen Prädikate (inhalt, status) gilt: eine veraltete Kante der
    Seed-Quelle wird ZURÜCKGENOMMEN (ehrliche Historie: relation_retracted, nie stilles
    Überschreiben) und die aktuelle gesät. Kanten anderer Quellen (z.B. genus:stufe1 aus
    einer Umsetzung) bleiben unberührt; dient/braucht sind additiv und laufen weiter
    über seed_ziele. Idempotent: ein zweiter Lauf tut nichts."""
    from genus import reactors

    gewuenscht: dict[tuple[str, str], str] = {}
    for ziel_id, inhalt in ZIEL_SEED:
        gewuenscht[(ziel_id, INHALT)] = inhalt
    for f_id, inhalt, status in FAEHIGKEIT_SEED:
        gewuenscht[(f_id, INHALT)] = inhalt
        gewuenscht[(f_id, STATUS)] = status

    zurueckgenommen = 0
    gesaet = 0
    for (subj, praed), soll in gewuenscht.items():
        eigene = [r for r in sources.relations(conn, subject=subj, predicate=praed)
                  if r["source"] == SEED_SOURCE]
        falsche = [r for r in eigene if r["object"] != soll]
        for r in falsche:
            reactors.retract_relation(
                conn, subj, praed, r["object"], source=SEED_SOURCE,
                reason="Selbst-Bild-Abgleich: der Stand hat sich geändert",
            )
            zurueckgenommen += 1
        if not any(r["object"] == soll for r in eigene):
            reactors.observe_relation(conn, subj, praed, soll, SEED_SOURCE)
            gesaet += 1
    return {"zurueckgenommen": zurueckgenommen, "gesaet": gesaet}


def _inhalt(conn, node: str) -> str:
    rows = sources.relations(conn, subject=node, predicate=INHALT)
    return rows[0]["object"] if rows else node


def mission(conn) -> str | None:
    """Der Wortlaut der Mission -- ``None``, wenn (noch) nicht gesät."""
    rows = sources.relations(conn, subject=MISSION, predicate=INHALT)
    return rows[0]["object"] if rows else None


def ziele(conn) -> list[dict]:
    """Alle Ziele außer der Mission, in Einfüge-Reihenfolge (die Projektions-``id``-Spalte,
    nicht alphabetisch -- dieselbe Lehre wie bei Notizen/Episoden), jedes mit seinen
    gebrauchten Fähigkeiten samt Status."""
    rows = conn.execute(
        "SELECT DISTINCT subject FROM relation_projection "
        "WHERE subject LIKE ? AND predicate = ? AND subject != ? ORDER BY id",
        (f"{ZIEL_PREFIX}%", INHALT, MISSION),
    ).fetchall()
    ergebnis = []
    for row in rows:
        ziel_id = row["subject"]
        braucht = []
        for r in sources.relations(conn, subject=ziel_id, predicate=BRAUCHT):
            f_id = r["object"]
            status_rows = sources.relations(conn, subject=f_id, predicate=STATUS)
            braucht.append({
                "id": f_id,
                "inhalt": _inhalt(conn, f_id),
                "status": status_rows[0]["object"] if status_rows else "unbekannt",
            })
        ergebnis.append({"id": ziel_id, "inhalt": _inhalt(conn, ziel_id), "braucht": braucht})
    return ergebnis


def fehlende_faehigkeiten(conn) -> list[dict]:
    """Die Fähigkeiten, die einem Ziel dienen und noch nicht ``live`` sind -- GENUS' ehrliche
    Antwort auf „was fehlt dir?", direkt aus dem Graphen. Dedupliziert (eine Fähigkeit kann
    mehreren Zielen fehlen), in Einfüge-Reihenfolge."""
    gesehen: set[str] = set()
    fehlt = []
    for ziel in ziele(conn):
        for f in ziel["braucht"]:
            if f["status"] != "live" and f["id"] not in gesehen:
                gesehen.add(f["id"])
                fehlt.append(f)
    return fehlt
