"""Die freigelegten AUSKUNFT-PRIMITIVE + der erste komponierte Antwort-Plan (Tool-Planer ③,
Schritt 1 -- rein deterministisch, kein Modell).

Der schöne Befund der Modularisierung: ``auskunft.relate``/``common``/``relate_kausal`` sind
längst KOMPOSITIONEN derselben wenigen Graph-Primitive (ein Wort zu seinem Konzept auflösen, die
is_a-Oberbegriffe klettern, prüfen wo zwei Linien sich treffen) -- nur fest verdrahtet. Hier
werden diese Primitive als geprüfte, einzeln verifizierbare WERKZEUGE sichtbar gemacht, und
``relate`` als DATEN-Plan über ihnen nachgebaut. Der Beweis (tests/test_werkplan.py): der
komponierte Plan liefert Zeichen für Zeichen dasselbe wie das heutige ``_relate_terms`` -- die
Komposition ist schon da, sie wird nur explizit und frei rekombinierbar.

„Ein Werkzeug" ist hier bewusst grob genug, dass jedes für sich zuverlässig + prüfbar ist, und
fein genug, dass ihre Kombination neue Antworten ergibt (Ronnys Granularitäts-Frage). Die
Primitive sind rein lesend; conn wird ihnen vom Ausführer injiziert (die reine Schnittmengen-
Prüfung ``verbindung`` bekommt es nicht).
"""
from __future__ import annotations

from genus import auskunft, inference, werkplan, werkzeug, wortgraph
# (auskunft auf Modul-Ebene ist zyklusfrei: auskunft importiert werkzeuge_auskunft
# seinerseits nur funktions-lokal -- die Richtung Werkzeuge -> Netz ist die stabile.)


# --- die Primitive (dünne, geprüfte Hüllen über wortgraph/inference) ----------------------

def konzept_form(conn, wort):
    """Die geschriebene/großgeschriebene Form von ``wort``, die GENUS als Konzept kennt."""
    return {"form": wortgraph._concept_form(conn, wort)}


def konzepte_von(conn, wort):
    """Alle Konzepte, die ein Wort ausdrückt, plus die bekannte Form (die Objekt-Seite)."""
    konzepte, form = wortgraph._concepts_of(conn, wort)
    return {"konzepte": konzepte, "form": form}


def oberbegriffe(conn, form):
    """Die transitiven is_a-Oberbegriffe einer Form (mit Kette + Vertrauen je Vorfahr) -- das
    Kern-Inferenz-Primitiv. Leere Form -> keine Vorfahren (kein sinnloser Aufruf)."""
    if form is None:
        return {"oberbegriffe": []}
    return {"oberbegriffe": inference.infer_lexeme(conn, form, "is_a", "de")}


def ortsbegriffe(conn, form):
    """Die transitiven ``located_in``-Oberorte einer Form (Stadt -> Bundesland -> Deutschland,
    mit Kette + Vertrauen) -- das Geo-Zwilling von :func:`oberbegriffe`. Dieselbe Inferenz,
    nur das Prädikat wechselt; ``verbindung`` prüft die Linie danach prädikat-agnostisch.
    Liefert bewusst denselben Schlüssel ``oberbegriffe`` wie is_a, damit ``verbindung``
    unverändert konsumiert -- welches der beiden Primitive der Plan wählt, entscheidet die
    Fälle-Verifikation (die Geo-Fälle tragen nur mit located_in)."""
    if form is None:
        return {"oberbegriffe": []}
    return {"oberbegriffe": inference.infer_lexeme(conn, form, "located_in", "de")}


def gemeinsame_kategorien(conn, x_form, y_form):
    """Wo treffen sich die is_a-Linien zweier Formen -- die nächste gemeinsame, BENENNBARE
    Oberkategorie zuerst (die klassische LCA-Frage als EIN kohärenter Graph-Schritt).
    Das Urteil einer Vergleichsfrage; spiegelt das Herz von ``auskunft._common_terms``."""
    if x_form is None or y_form is None:
        return {"common": False}
    dx = auskunft._ancestor_depths(conn, x_form)
    dy = auskunft._ancestor_depths(conn, y_form)
    ordered = sorted(set(dx) & set(dy), key=lambda c: dx[c] + dy[c])
    shared = [c for c in ordered if wortgraph._label(conn, c) != c]
    return {"common": True, "found": bool(shared), "x": x_form, "y": y_form, "shared": shared}


def ursachen_im_graph(conn, form, konzepte):
    """Die bekannten Ursachen der Konzepte einer Form (``s causes X`` ∪ ``X caused_by o``),
    benannt und sortiert -- das Urteil der Ursachen-Frage; spiegelt das Herz von
    ``auskunft._ursachen_von``. Leere Ursachen bleiben ehrlich ``kausal_q=True`` (die
    Kausal-FRAGE wurde gestellt; „kenne keine Ursache" ist die responsive Antwort)."""
    from genus import sources

    if form is None:
        return {"kausal_q": False}
    ursachen: set[str] = set()
    for q in sorted(konzepte):
        for r in sources.relations(conn, predicate="causes", object=q):
            ursachen.add(r["subject"])
        for r in sources.relations(conn, subject=q, predicate="caused_by"):
            ursachen.add(r["object"])
    return {"kausal_q": True, "art": "ursachen", "subjekt": form,
            "ursachen": sorted({wortgraph._label(conn, u) for u in ursachen})}


def verbindung(subjekt_form, objekt_form, oberbegriffe, ziel_konzepte):
    """Findet, ob eine der is_a-Linien des Subjekts ein Ziel-Konzept trifft, und den KÜRZESTEN
    Weg dorthin -- rein (kein conn). Dasselbe Urteil wie das Herz von ``_relate_terms``:
    ``relational: False`` wenn Subjekt/Ziel nicht auflösbar; sonst ``yes`` mit Weg + Vertrauen
    (schwächste Prämisse, aus dem Graphen hergeleitet) oder ``no_path`` (unbekannt, nicht
    widerlegt)."""
    if subjekt_form is None or not ziel_konzepte:
        return {"relational": False}
    treffer = [a for a in oberbegriffe if a["object"] in ziel_konzepte]
    if treffer:
        best = min(treffer, key=lambda a: len(a["chain"]))
        return {"relational": True, "verdict": "yes", "subject": subjekt_form,
                "object": objekt_form, "target": best["object"], "trust": best["trust"],
                "chain": best["chain"]}
    return {"relational": True, "verdict": "no_path", "subject": subjekt_form, "object": objekt_form}


def registriere_auskunft_werkzeuge() -> None:
    """Meldet die vier Auskunft-Primitive beim Werkzeugbauer an (idempotent -- verdrahten
    ersetzt per Name). pruefbar_als='graph', rein lesend, nicht wortlautfest (abgeleitete
    Fakten, keine wörtlich zu schützenden Fremdtexte)."""
    werkzeug.verdrahten(werkzeug.Werkzeug(
        name="konzept_form",
        beschreibung="Ein Wort zu der Form auflösen, die GENUS als Konzept kennt (Subjekt-Seite).",
        parameter={"wort": werkzeug.Parameter("Text", pflicht=True)},
        schreibt=False, wortlautfest=False, pruefbar_als="graph",
        liefert={"form": "Wort"},
        implementierung=konzept_form,
    ))
    werkzeug.verdrahten(werkzeug.Werkzeug(
        name="konzepte_von",
        beschreibung="Alle Konzepte, die ein Wort ausdrückt, plus die bekannte Form (Objekt-Seite).",
        parameter={"wort": werkzeug.Parameter("Text", pflicht=True)},
        schreibt=False, wortlautfest=False, pruefbar_als="graph",
        liefert={"konzepte": "Menge", "form": "Wort"},
        implementierung=konzepte_von,
    ))
    werkzeug.verdrahten(werkzeug.Werkzeug(
        name="oberbegriffe",
        beschreibung="Die transitiven is_a-Oberbegriffe einer Form, mit Kette und Vertrauen.",
        parameter={"form": werkzeug.Parameter("Wort", pflicht=True)},
        schreibt=False, wortlautfest=False, pruefbar_als="graph",
        liefert={"oberbegriffe": "Liste"},
        implementierung=oberbegriffe,
    ))
    werkzeug.verdrahten(werkzeug.Werkzeug(
        name="ortsbegriffe",
        beschreibung="Die transitiven located_in-Oberorte einer Form (Stadt→Land→Deutschland).",
        parameter={"form": werkzeug.Parameter("Wort", pflicht=True)},
        schreibt=False, wortlautfest=False, pruefbar_als="graph",
        liefert={"oberbegriffe": "Liste"},
        implementierung=ortsbegriffe,
    ))
    werkzeug.verdrahten(werkzeug.Werkzeug(
        name="gemeinsame_kategorien",
        beschreibung=("Wo treffen sich die is_a-Linien zweier Formen -- nächste gemeinsame, "
                      "benennbare Oberkategorie zuerst (das Urteil einer Vergleichsfrage)."),
        parameter={
            "x_form": werkzeug.Parameter("Wort"),
            "y_form": werkzeug.Parameter("Wort"),
        },
        schreibt=False, wortlautfest=False, pruefbar_als="graph",
        liefert={"common": "Wahrheit", "found": "Wahrheit", "x": "Wort", "y": "Wort",
                 "shared": "Liste"},
        implementierung=gemeinsame_kategorien,
    ))
    werkzeug.verdrahten(werkzeug.Werkzeug(
        name="ursachen_im_graph",
        beschreibung=("Die bekannten Ursachen der Konzepte einer Form (causes/caused_by), "
                      "benannt und sortiert (das Urteil der Ursachen-Frage)."),
        parameter={
            "form": werkzeug.Parameter("Wort"),
            "konzepte": werkzeug.Parameter("Menge"),
        },
        schreibt=False, wortlautfest=False, pruefbar_als="graph",
        liefert={"kausal_q": "Wahrheit", "art": "Text", "subjekt": "Wort", "ursachen": "Liste"},
        implementierung=ursachen_im_graph,
    ))
    werkzeug.verdrahten(werkzeug.Werkzeug(
        name="verbindung",
        beschreibung=("Findet, ob eine is_a-Linie des Subjekts ein Ziel-Konzept trifft (kürzester "
                      "Weg, mit Vertrauen) -- das Urteil einer Beziehungsfrage."),
        parameter={
            "subjekt_form": werkzeug.Parameter("Wort"),
            "objekt_form": werkzeug.Parameter("Wort"),
            "oberbegriffe": werkzeug.Parameter("Liste"),
            "ziel_konzepte": werkzeug.Parameter("Menge"),
        },
        schreibt=False, wortlautfest=False, pruefbar_als="graph",
        liefert={"relational": "Wahrheit", "verdict": "Text", "subject": "Wort", "object": "Wort", "target": "Text", "trust": "Zahl", "chain": "Liste"},
        implementierung=verbindung,
    ))


# --- der erste komponierte Antwort-Plan: eine Beziehungsfrage („Ist ein X ein Y?") --------
#
# Genau die Kette von _relate_terms, jetzt als DATEN: X -> Form; Y -> Konzepte+Form; Form ->
# Oberbegriffe; (Form, Konzepte, Oberbegriffe) -> Verbindung. Die Ausgabe von „xf" fließt in
# „vf", die Ausgaben von „xf"/„yk"/„vf" in „erg" -- echter Datenfluss, kein linear geteilter Input.
BEZIEHUNG_PLAN = werkplan.Werkplan(
    eingaben=("x_tok", "y_tok"),
    schritte=(
        werkplan.Schritt("xf", "konzept_form", (("wort", ("in", "x_tok")),)),
        werkplan.Schritt("yk", "konzepte_von", (("wort", ("in", "y_tok")),)),
        werkplan.Schritt("vf", "oberbegriffe", (("form", ("aus", "xf", "form")),)),
        werkplan.Schritt("erg", "verbindung", (
            ("subjekt_form", ("aus", "xf", "form")),
            ("objekt_form", ("aus", "yk", "form")),
            ("oberbegriffe", ("aus", "vf", "oberbegriffe")),
            ("ziel_konzepte", ("aus", "yk", "konzepte")),
        )),
    ),
    ergebnis="erg",
)


def relate_komponiert(conn, x_tok: str, y_tok: str) -> dict:
    """``_relate_terms`` als komponierter Plan über der Registry -- beweisbar identisch zum
    fest verdrahteten Original (der Zweck dieses Schritts). Stellt die Primitive sicher und
    führt den Plan aus."""
    registriere_auskunft_werkzeuge()
    return werkplan.fuehre_aus(conn, BEZIEHUNG_PLAN, x_tok=x_tok, y_tok=y_tok)[BEZIEHUNG_PLAN.ergebnis]


# --- Scheibe C: der Planer wird PRIMÄRPFAD (Absicht -> Ziel + Fälle als DATEN) ------------
#
# Jede verdrahtete Absicht trägt ihr Ziel-Werkzeug und ihre Planfälle als Saat-Daten (wie
# RASTER_SEED/ZIEL_SEED); der Plan wird daraus EINMAL pro Prozess DEDUZIERT (deterministisch,
# ~0,4 s) und dann gecacht -- jede Nachricht zahlt nur die ms der Ausführung. Scheitert
# irgendetwas (keine Kette, Ausführungsfehler), fällt es GEZÄHLT auf das alte, handgebaute
# Netz zurück -- der Nutzer merkt nichts, das Zählwerk alles. Der Richtungs-/Vertauschungs-
# Fall ist Pflichtteil jeder Saat: Typen allein können x/y nicht unterscheiden.
_HUND_TIER_GRAPH = (
    ("Hund@de", "expresses", "Q144", "wikidata"),
    ("Q144", "is_a", "Q_haustier", "wikidata"),
    ("Haustier@de", "expresses", "Q_haustier", "wikidata"),
    ("Q_haustier", "is_a", "Q_tier", "wikidata"),
    ("Tier@de", "expresses", "Q_tier", "wikidata"),
)
_OBST_GRAPH = (
    ("Apfel@de", "expresses", "Q89", "wikidata"),
    ("Birne@de", "expresses", "Q434", "wikidata"),
    ("Q89", "is_a", "Q13184", "wikidata"),
    ("Q434", "is_a", "Q13184", "wikidata"),
    ("Kernobst@de", "expresses", "Q13184", "wikidata"),
    ("Q13184", "is_a", "Q1364", "wikidata"),
    ("Obst@de", "expresses", "Q1364", "wikidata"),
)
_KAUSAL_GRAPH = (
    ("Bakterie@de", "expresses", "Q901", "wikidata"),
    ("Infektion@de", "expresses", "Q902", "wikidata"),
    ("Q901", "causes", "Q902", "wikidata"),
)

BEZIEHUNG_FAELLE = (
    werkplan.Planfall(graph=_HUND_TIER_GRAPH,
                      eingaben={"x_tok": "Hund", "y_tok": "Tier"},
                      erwartet={"verdict": "yes", "subject": "Hund", "object": "Tier",
                                "target": "Q_tier"}),
    werkplan.Planfall(graph=_HUND_TIER_GRAPH,
                      eingaben={"x_tok": "Tier", "y_tok": "Hund"},
                      erwartet={"verdict": "no_path"}),
)
VERGLEICH_FAELLE = (
    # x/y stehen EXAKT im erwartet -> der vertauschte Kandidat stirbt an diesem Fall
    werkplan.Planfall(graph=_OBST_GRAPH,
                      eingaben={"x_tok": "Apfel", "y_tok": "Birne"},
                      erwartet={"common": True, "found": True, "x": "Apfel", "y": "Birne",
                                "shared": ["Q13184", "Q1364"]}),
    werkplan.Planfall(graph=_OBST_GRAPH,
                      eingaben={"x_tok": "Apfel", "y_tok": "Xyzzy"},
                      erwartet={"common": False}),
)
URSACHE_FAELLE = (
    werkplan.Planfall(graph=_KAUSAL_GRAPH,
                      eingaben={"x_tok": "Infektion"},
                      erwartet={"kausal_q": True, "art": "ursachen", "subjekt": "Infektion",
                                "ursachen": ["Bakterie"]}),
    # der RICHTUNGS-Fall: nichts verursacht die Bakterie -- eine umgedrehte Lesung stirbt hier
    werkplan.Planfall(graph=_KAUSAL_GRAPH,
                      eingaben={"x_tok": "Bakterie"},
                      erwartet={"kausal_q": True, "ursachen": []}),
)

# Die Ortsfrage („Ist Kassel in Hessen?") -- dasselbe Ziel wie beziehung (verbindung), nur die
# Linie klettert located_in statt is_a. Die Fälle tragen NUR mit ortsbegriffe (keine is_a-Kante
# im Graphen), sodass die Verifikation den located_in-Zweig wählt. Richtungs-Fall Pflicht.
_ORT_GRAPH = (
    ("Kassel@de", "expresses", "Q_kassel", "kuratiert"),
    ("Q_kassel", "located_in", "Q_hessen", "kuratiert"),
    ("Hessen@de", "expresses", "Q_hessen", "kuratiert"),
    ("Q_hessen", "located_in", "Q_de", "kuratiert"),
    ("Deutschland@de", "expresses", "Q_de", "kuratiert"),
)
ORT_FAELLE = (
    werkplan.Planfall(graph=_ORT_GRAPH,
                      eingaben={"x_tok": "Kassel", "y_tok": "Hessen"},
                      erwartet={"verdict": "yes", "subject": "Kassel", "object": "Hessen",
                                "target": "Q_hessen"}),
    # Richtung: Hessen liegt NICHT in Kassel -- der vertauschte Plan stirbt hier
    werkplan.Planfall(graph=_ORT_GRAPH,
                      eingaben={"x_tok": "Hessen", "y_tok": "Kassel"},
                      erwartet={"verdict": "no_path"}),
)

# Absicht -> (Ziel-Werkzeug, Plan-Eingaben, Fälle): die EINE Saat-Tabelle des Primärpfads.
ABSICHT_SAAT = {
    "beziehung": ("verbindung", {"x_tok": "Text", "y_tok": "Text"}, BEZIEHUNG_FAELLE),
    "vergleich": ("gemeinsame_kategorien", {"x_tok": "Text", "y_tok": "Text"}, VERGLEICH_FAELLE),
    "ursache": ("ursachen_im_graph", {"x_tok": "Text"}, URSACHE_FAELLE),
    "ort": ("verbindung", {"x_tok": "Text", "y_tok": "Text"}, ORT_FAELLE),
}

_PLAN_CACHE: dict[str, object] = {}


def plan_fuer(absicht: str):
    """Der DEDUZIERTE Plan einer Absicht -- einmal pro Prozess geschlossen (Suche über die
    Registry, verifiziert gegen die Saat-Fälle), dann gecacht. ``None``, wenn die Suche
    ehrlich keine Kette findet (dann trägt das Netz allein)."""
    if absicht not in _PLAN_CACHE:
        registriere_auskunft_werkzeuge()
        ziel, eingaben, faelle = ABSICHT_SAAT[absicht]
        _PLAN_CACHE[absicht] = werkplan.finde_werkplan(ziel, eingaben, faelle)["plan"]
    return _PLAN_CACHE[absicht]


def _geplant(absicht: str, netz, conn, **eingaben) -> dict:
    """Die EINE Primärpfad-Mechanik: der selbst-deduzierte Plan antwortet; JEDES Scheitern
    (keine Kette, Ausführungsfehler) fällt gezählt auf das handgebaute ``netz`` zurück.
    Drop-in-gleich zum Netz (testbewiesen je Absicht); beide Wege rein lesend."""
    from genus import zaehlwerk

    try:
        plan = plan_fuer(absicht)
        if plan is not None:
            registriere_auskunft_werkzeuge()   # Registry kann geleert worden sein (Tests/Neustart)
            ergebnis = werkplan.fuehre_aus(conn, plan, **eingaben)[plan.ergebnis]
            zaehlwerk.zaehle(absicht, "treffer")
            return ergebnis
    except Exception:
        pass   # jedes Scheitern fällt ehrlich (und gezählt) auf das Netz
    zaehlwerk.zaehle(absicht, "rueckfall")
    return netz()


def relate_geplant(conn, x_tok: str, y_tok: str) -> dict:
    """Die Beziehungsfrage, Planer zuerst (Netz: :func:`auskunft._relate_terms`)."""
    return _geplant("beziehung", lambda: auskunft._relate_terms(conn, x_tok, y_tok),
                    conn, x_tok=x_tok, y_tok=y_tok)


def vergleich_geplant(conn, x_tok: str, y_tok: str) -> dict:
    """Die Vergleichsfrage, Planer zuerst (Netz: :func:`auskunft._common_terms`)."""
    return _geplant("vergleich", lambda: auskunft._common_terms(conn, x_tok, y_tok),
                    conn, x_tok=x_tok, y_tok=y_tok)


def ursachen_geplant(conn, x_tok: str) -> dict:
    """Die Ursachen-Frage, Planer zuerst (Netz: :func:`auskunft._ursachen_von`)."""
    return _geplant("ursache", lambda: auskunft._ursachen_von(conn, x_tok),
                    conn, x_tok=x_tok)


def _ort_netz(conn, x_tok: str, y_tok: str) -> dict:
    """Das handgebaute Rückfall-Netz der Ortsfrage: dieselben Primitive wie der Plan, nur
    located_in statt is_a -- rein lesend, drop-in-gleich zum deduzierten Plan."""
    xf = konzept_form(conn, x_tok)["form"]
    yk = konzepte_von(conn, y_tok)
    ob = ortsbegriffe(conn, xf)["oberbegriffe"]
    return verbindung(xf, yk["form"], ob, yk["konzepte"])


def ort_geplant(conn, x_tok: str, y_tok: str) -> dict:
    """Die Ortsfrage („Ist X in Y?"), Planer zuerst (Netz: :func:`_ort_netz`, located_in)."""
    return _geplant("ort", lambda: _ort_netz(conn, x_tok, y_tok), conn, x_tok=x_tok, y_tok=y_tok)
