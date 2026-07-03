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
     "entscheidet nie (Organ, nicht Orakel).", "fehlt"),
    ("faehigkeit:vorschlags-loop",
     "Lücke spüren → Plan als Proposal → Gate (Tests, Replay, Mensch) → Ledger. "
     "Proposal≠Change existiert; der Konsument, der aus eigenen Fehlgriffen Vorschläge macht, "
     "fehlt.", "fehlt"),
    ("faehigkeit:werkzeugkasten",
     "Kern-Fähigkeiten als planbare Werkzeuge (Mathe exakt: live als Muster; Graph-Abfragen: "
     "live als Muster; als frei planbares Tool-Set: fehlt).", "teilweise"),
    ("faehigkeit:gedaechtnis",
     "Episoden + Abruf über den Graphen + Mehr-Zug-Arbeitsgedächtnis: live. Tagespuffer, "
     "Nacht-Konsolidierung, Morgen-Bericht: fehlen.", "teilweise"),
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
)


def seed_ziele(conn) -> int:
    """Sät Mission, Ziele, Fähigkeiten und ihre Kanten -- idempotent wie seed_raster:
    vorhandene Kanten werden übersprungen, zurückgegeben wird die Zahl NEU gesäter Kanten."""
    from genus import reactors

    vorhanden = {
        (r["subject"], r["predicate"], r["object"])
        for pred in (INHALT, DIENT, BRAUCHT, STATUS)
        for r in sources.relations(conn, predicate=pred)
    }
    neu = 0

    def sow(s: str, p: str, o: str) -> None:
        nonlocal neu
        if (s, p, o) not in vorhanden:
            reactors.observe_relation(conn, s, p, o, SEED_SOURCE)
            neu += 1

    for ziel_id, inhalt in ZIEL_SEED:
        sow(ziel_id, INHALT, inhalt)
        if ziel_id != MISSION:
            sow(ziel_id, DIENT, MISSION)
    for f_id, inhalt, status in FAEHIGKEIT_SEED:
        sow(f_id, INHALT, inhalt)
        sow(f_id, STATUS, status)
    for ziel_id, f_id in ZIEL_BRAUCHT:
        sow(ziel_id, BRAUCHT, f_id)
    return neu


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
