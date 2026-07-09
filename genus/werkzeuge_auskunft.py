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

from genus import inference, werkplan, werkzeug, wortgraph


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
# Die Absicht „beziehung" trägt ihr Ziel-Werkzeug und ihre Planfälle als Saat-Daten (wie
# RASTER_SEED/ZIEL_SEED); der Plan wird daraus EINMAL pro Prozess DEDUZIERT (deterministisch,
# ~0,4 s) und dann gecacht -- jede Nachricht zahlt nur die ms der Ausführung. Scheitert
# irgendetwas (keine Kette, Ausführungsfehler), fällt es GEZÄHLT auf das alte, handgebaute
# Netz (auskunft._relate_terms) zurück -- der Nutzer merkt nichts, das Zählwerk alles.
# Der Richtungs-Fall ist Pflichtteil der Saat: er tötet den vertauschten Kandidaten.
BEZIEHUNG_FAELLE = (
    werkplan.Planfall(
        graph=(("Hund@de", "expresses", "Q144", "wikidata"),
               ("Q144", "is_a", "Q_haustier", "wikidata"),
               ("Haustier@de", "expresses", "Q_haustier", "wikidata"),
               ("Q_haustier", "is_a", "Q_tier", "wikidata"),
               ("Tier@de", "expresses", "Q_tier", "wikidata")),
        eingaben={"x_tok": "Hund", "y_tok": "Tier"},
        erwartet={"verdict": "yes", "subject": "Hund", "object": "Tier", "target": "Q_tier"},
    ),
    werkplan.Planfall(
        graph=(("Hund@de", "expresses", "Q144", "wikidata"),
               ("Q144", "is_a", "Q_haustier", "wikidata"),
               ("Haustier@de", "expresses", "Q_haustier", "wikidata"),
               ("Q_haustier", "is_a", "Q_tier", "wikidata"),
               ("Tier@de", "expresses", "Q_tier", "wikidata")),
        eingaben={"x_tok": "Tier", "y_tok": "Hund"},
        erwartet={"verdict": "no_path"},
    ),
)

_PLAN_CACHE: dict[str, object] = {}


def beziehungs_plan():
    """Der DEDUZIERTE Beziehungs-Plan -- einmal pro Prozess geschlossen (Suche über die
    Registry, verifiziert gegen BEZIEHUNG_FAELLE), dann gecacht. ``None``, wenn die Suche
    ehrlich keine Kette findet (dann trägt das Netz allein)."""
    if "beziehung" not in _PLAN_CACHE:
        registriere_auskunft_werkzeuge()
        fund = werkplan.finde_werkplan(
            "verbindung", {"x_tok": "Text", "y_tok": "Text"}, BEZIEHUNG_FAELLE)
        _PLAN_CACHE["beziehung"] = fund["plan"]
    return _PLAN_CACHE["beziehung"]


def relate_geplant(conn, x_tok: str, y_tok: str) -> dict:
    """Die Beziehungsfrage, PLANER ZUERST: der selbst-deduzierte Plan antwortet; scheitert
    er (keine Kette gefunden, Ausführungsfehler), fällt es GEZÄHLT auf das handgebaute Netz
    (:func:`auskunft._relate_terms`) zurück. Drop-in-gleich zum Netz (die Gleichheit ist
    testbewiesen); beide Wege rein lesend."""
    from genus import zaehlwerk

    try:
        plan = beziehungs_plan()
        if plan is not None:
            registriere_auskunft_werkzeuge()   # Registry kann geleert worden sein (Tests/Neustart)
            ergebnis = werkplan.fuehre_aus(conn, plan, x_tok=x_tok, y_tok=y_tok)[plan.ergebnis]
            zaehlwerk.zaehle("beziehung", "treffer")
            return ergebnis
    except Exception:
        pass   # jedes Scheitern fällt ehrlich (und gezählt) auf das Netz
    zaehlwerk.zaehle("beziehung", "rueckfall")
    from genus import auskunft
    return auskunft._relate_terms(conn, x_tok, y_tok)
