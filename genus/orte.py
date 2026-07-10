"""Der Orte-Seed (Antwort-Seele / Planer-Absicht „ort", Scheibe ①): eine kleine, KURATIERTE
Grundierung der deutschen Verwaltungsgeografie, damit „Ist Kassel in Hessen?" überhaupt
beantwortbar wird.

WARUM kuratiert statt roh erworben: der allgemeine Wikidata-Erwerber (deploy/observe_konzept.sh)
zieht `part_of` (P361), aber NICHT `located_in` (P131) / `country` (P17) -- deshalb kannte der
Graph zwar Ortsnamen, aber keine nutzbare Enthaltungs-Struktur. Und die rohen P131/P17-Werte sind
verrauscht (historische Staaten: Preußen, Weimar, DDR … stehen gleichberechtigt neben dem
heutigen). Für ein klares „ort" ist die AKTUELLE Hierarchie Stadt→Bundesland→Deutschland das
Richtige. Die Struktur (welche Stadt in welchem Land liegt) ist stabiles Allgemeinwissen; die
Q-IDs stammen von Wikidata (jede einzeln gegen ihr Label/ihre Beschreibung geprüft). Herkunft
ehrlich „kuratiert" -- die direkte Stadt→Land-Kante ist unsere Vereinfachung, nicht Wikidatas
mehrstufige (und historisch verrauschte) P131-Kette.

Der Seed sät `located_in` als eigenes Prädikat (nicht `part_of`, das schon für allgemeine
Teil-Ganzes-Relationen belegt und verrauscht ist) über den normalen, geprüften Schreibpfad
(reactors.sae_fehlende: Herkunft, Widerspruchs-/Zyklus-Check, idempotent). Die Absicht „ort"
(Scheibe ②) liest ihn dann wie beziehung, nur mit predicate=`located_in`.
"""
from __future__ import annotations

LOCATED_IN = "located_in"
QUELLE = "kuratiert"
DEUTSCHLAND = "Q183"   # der Wurzelknoten (hat selbst kein located_in)

# (Name, Q-ID) -- jedes located_in Deutschland. Q-IDs gegen Wikidata-Label geprüft (16 Länder).
BUNDESLAENDER: tuple[tuple[str, str], ...] = (
    ("Baden-Württemberg", "Q985"), ("Bayern", "Q980"), ("Berlin", "Q64"),
    ("Brandenburg", "Q1208"), ("Bremen", "Q1209"), ("Hamburg", "Q1055"),
    ("Hessen", "Q1199"), ("Mecklenburg-Vorpommern", "Q1196"), ("Niedersachsen", "Q1197"),
    ("Nordrhein-Westfalen", "Q1198"), ("Rheinland-Pfalz", "Q1200"), ("Saarland", "Q1201"),
    ("Sachsen", "Q1202"), ("Sachsen-Anhalt", "Q1206"), ("Schleswig-Holstein", "Q1194"),
    ("Thüringen", "Q1205"),
)

# (Name, Q-ID, Bundesland-Q-ID) -- jede Stadt located_in ihr Bundesland. Q-IDs gegen Wikidata-
# Beschreibung geprüft (jede Beschreibung nennt das erwartete Land). Berlin/Hamburg/Bremen sind
# Stadtstaaten (Stadt = Land) und stehen schon oben.
STAEDTE: tuple[tuple[str, str, str], ...] = (
    ("Kassel", "Q2865", "Q1199"), ("Frankfurt am Main", "Q1794", "Q1199"),
    ("Wiesbaden", "Q1721", "Q1199"), ("Darmstadt", "Q2973", "Q1199"),
    ("München", "Q1726", "Q980"), ("Nürnberg", "Q2090", "Q980"), ("Augsburg", "Q2749", "Q980"),
    ("Stuttgart", "Q1022", "Q985"), ("Mannheim", "Q2119", "Q985"),
    ("Karlsruhe", "Q1040", "Q985"), ("Freiburg im Breisgau", "Q2833", "Q985"),
    ("Köln", "Q365", "Q1198"), ("Düsseldorf", "Q1718", "Q1198"),
    ("Dortmund", "Q1295", "Q1198"), ("Essen", "Q2066", "Q1198"),
    ("Hannover", "Q1715", "Q1197"), ("Braunschweig", "Q2773", "Q1197"),
    ("Dresden", "Q1731", "Q1202"), ("Leipzig", "Q2079", "Q1202"), ("Chemnitz", "Q2795", "Q1202"),
    ("Magdeburg", "Q1733", "Q1206"), ("Halle (Saale)", "Q2814", "Q1206"),
    ("Erfurt", "Q1729", "Q1205"), ("Jena", "Q3150", "Q1205"),
    ("Kiel", "Q1707", "Q1194"), ("Lübeck", "Q2843", "Q1194"),
    ("Mainz", "Q1720", "Q1200"), ("Koblenz", "Q3104", "Q1200"),
    ("Rostock", "Q2861", "Q1196"), ("Potsdam", "Q1711", "Q1208"),
    ("Saarbrücken", "Q1724", "Q1201"),
)

# Kurzformen, die Leute sagen -> dieselbe Q-ID (zusätzliche expresses-Kante, kein neuer Knoten).
ALIASE: tuple[tuple[str, str], ...] = (
    ("Frankfurt", "Q1794"), ("Freiburg", "Q2833"), ("Halle", "Q2814"),
)


def _tripel() -> list[tuple[str, str, str]]:
    """Alle zu säenden (subject, predicate, object)-Tripel -- rein aus den Tabellen oben."""
    tripel: list[tuple[str, str, str]] = []

    def benenne(name: str, qid: str) -> None:
        # label + expresses in derselben Richtung wie der Wikidata-Erwerber (wort@de -> Q),
        # damit Auflösung (expresses) und Anzeige (label/lexicalize) identisch funktionieren
        tripel.append((f"{name}@de", "label", qid))
        tripel.append((f"{name}@de", "expresses", qid))

    benenne("Deutschland", DEUTSCHLAND)
    for name, qid in BUNDESLAENDER:
        benenne(name, qid)
        tripel.append((qid, LOCATED_IN, DEUTSCHLAND))
    for name, qid, land in STAEDTE:
        benenne(name, qid)
        tripel.append((qid, LOCATED_IN, land))
    for name, qid in ALIASE:
        tripel.append((f"{name}@de", "expresses", qid))
    return tripel


def seed_orte(conn) -> int:
    """Sät die kuratierte Geo-Grundierung idempotent (nur Fehlendes) über den geprüften
    Schreibpfad. Gibt die Zahl NEU gesäter Kanten zurück."""
    from genus import reactors

    return reactors.sae_fehlende(conn, _tripel(), QUELLE)
