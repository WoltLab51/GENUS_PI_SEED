"""Die FORMWAHL: deutsche Wortformen für die eigene Stimme, mit VORFAHRT.

Die gläserne Stimme umging Formen bisher durch Phrasierung („es zählt zu »Haustier«" statt
„es ist ein »Haustier«"), weil ein Artikel eine Genus-Entscheidung braucht, die kein Template
raten darf. Dieses Modul trifft sie — aber nie durch Raten, sondern über eine Kette mit
Vorfahrt (Gegründetes schlägt Regel schlägt Modell, die Doktrin des Schreibpfads gilt auch
beim Sprechen):

  ① GEGRÜNDET: die ``grammatical_gender``-Kanten des Ledgers (wikidata-lexemes u.a.).
     Tragen die belegten Genera verschiedene Artikel (der/die See), ist das ENDGÜLTIG
     mehrdeutig — kein späteres Glied darf gegründete Mehrdeutigkeit überstimmen.
  ② GEGRÜNDETER KOMPOSITUM-KOPF: ist das Nomen ein belegter Unterbegriff und endet auf
     dessen geerdete deutsche Form (``Wohngebäude`` → ``Gebäude``), erbt es deren Artikel.
     Das ist eine Graph- plus Morphologie-Ableitung, kein bloßes Endungsraten.
  ③ EIGENE REGEL: :func:`genus.gender_rule.predict_gender` — GENUS' selbst gelernte,
     selbst-kalibrierte Suffix-Regel (leave-one-out-geprüft).
  ④ GEWOGEN: ein injiziertes Organ (die Waage, deploy/waage.py) — das Modell LIEST nur,
     welche Form schwerer wiegt; es ist per Blind-Probe kalibriert und handelt nur über
     seiner gemessenen Schwelle. Injiziert wie ``stimme``/``deuter``: ohne Organ bleibt die
     Kette rein deterministisch (CLI-Weg), die Membran reicht es herein.
  ⑤ Ohne Entscheidung: ``None`` — der Aufrufer behält seine alte, formfreie Phrasierung.

Die Artikel-Frage ist bewusst die SICHERSTE Form-Entscheidung: beide Kandidaten tragen
dasselbe Nomen (fakten-identisch), ein Fehlgriff wäre ein Grammatik-, nie ein Faktenfehler —
und maskulin/neutrum teilen sich im Nominativ ohnehin „ein" (nur feminin unterscheidet sich).
"""
from __future__ import annotations

from genus import gender_rule, sources, zaehlwerk

# Nominativ nach Kopula („es ist ein/eine X"): maskulin und neutrum teilen sich „ein" --
# die Entscheidung ist binär, obwohl das Genus dreiwertig ist.
ARTIKEL_EIN = {"maskulin": "ein", "neutrum": "ein", "feminin": "eine"}


def _tragfaehig(conn, relation: dict, cache: dict[str, float]) -> bool:
    quelle = relation["source"]
    if quelle not in cache:
        cache[quelle] = sources.source_trust(conn, quelle)
    return cache[quelle] >= sources.SOURCE_TRUST_SEED


def _kompositum_artikel(conn, nomen: str) -> tuple[bool, str | None]:
    """``(Kopf gefunden, eindeutiger Artikel)`` für einen graph-geerdeten Kompositum-Kopf.

    Nur ein tatsächlicher ``is_a``-Elternbegriff des ausgedrückten Konzepts darf Kopf sein,
    und seine deutsche Form muss ein echtes, kürzeres Wortende des Nomens bilden. Dadurch ist
    ``Wohngebäude`` → ``Gebäude`` tragfähig, während eine zufällige gleiche Endung eines
    beliebigen Lexems nie genügt. Widersprechen sich geerdete Köpfe, ist das Ergebnis bewusst
    offen und kein schwächeres Glied darf darüber hinweggehen.
    """
    lexem = f"{nomen}@de"
    nomen_fold = nomen.casefold()
    artikel: set[str] = set()
    gefunden = False
    vertrauen: dict[str, float] = {}
    for ausdrueckt in sources.relations(conn, subject=lexem, predicate="expresses"):
        if not _tragfaehig(conn, ausdrueckt, vertrauen):
            continue
        for eltern in sources.relations(conn, subject=ausdrueckt["object"], predicate="is_a"):
            if not _tragfaehig(conn, eltern, vertrauen):
                continue
            for form in sources.relations(conn, predicate="expresses", object=eltern["object"]):
                if (not form["subject"].endswith("@de")
                        or not _tragfaehig(conn, form, vertrauen)):
                    continue
                kopf = form["subject"].removesuffix("@de")
                if len(kopf) >= len(nomen) or not nomen_fold.endswith(kopf.casefold()):
                    continue
                genera = {
                    r["object"] for r in sources.relations(
                        conn, subject=form["subject"], predicate="grammatical_gender")
                    if _tragfaehig(conn, r, vertrauen)
                }
                if not genera:
                    continue
                gefunden = True
                kopf_artikel = {ARTIKEL_EIN[g] for g in genera if g in ARTIKEL_EIN}
                if len(kopf_artikel) != 1:
                    return True, None
                artikel.update(kopf_artikel)
    if not gefunden or len(artikel) != 1:
        return gefunden, None
    return True, artikel.pop()


def artikel_ein(conn, nomen: str, waage=None) -> dict | None:
    """Der unbestimmte Artikel (Nominativ) für ``nomen`` — ``{"artikel", "weg"}`` oder ``None``.

    ``waage`` (optional): das injizierte Wiege-Organ ``(nomen) -> "ein" | "eine" | None``
    (deploy-seitig, per Blind-Probe geschwellt). Jeder getroffene Weg wird gezählt
    (Zählwerk, in-Prozess — der reine Antwortpfad schreibt nie ins Ledger)."""
    # ① gegründet: belegte Genus-Kanten des Ledgers
    vertrauen: dict[str, float] = {}
    genera = {
        r["object"] for r in sources.relations(
            conn, subject=f"{nomen}@de", predicate="grammatical_gender")
        if _tragfaehig(conn, r, vertrauen)
    }
    if genera:
        artikel = {ARTIKEL_EIN[g] for g in genera if g in ARTIKEL_EIN}
        if len(artikel) == 1:
            zaehlwerk.zaehle("formwahl", "gegruendet")
            return {"artikel": artikel.pop(), "weg": "gegruendet"}
        # gegründete Mehrdeutigkeit (der/die See) ist eine ANTWORT, kein Loch: kein
        # Regel-/Modell-Glied darf sie überstimmen (model:* überstimmt nie Gegründetes)
        zaehlwerk.zaehle("formwahl", "mehrdeutig")
        return None
    # ② ein graph-geerdeter Kompositum-Kopf schlägt die statistische Endungsregel. Live-Fund:
    # „Wohngebäude" endete wie viele Feminina auf -e, ist aber als Unterbegriff von „Gebäude"
    # belegt; dessen Neutrum muss gewinnen.
    kopf_gefunden, kopf_artikel = _kompositum_artikel(conn, nomen)
    if kopf_gefunden:
        if kopf_artikel is not None:
            zaehlwerk.zaehle("formwahl", "kompositum")
            return {"artikel": kopf_artikel, "weg": "kompositum"}
        zaehlwerk.zaehle("formwahl", "mehrdeutig")
        return None
    # ③ die eigene, selbst-kalibrierte Suffix-Regel
    p = gender_rule.predict_gender(conn, f"{nomen}@de")
    if p.get("found"):
        a = ARTIKEL_EIN.get(p["gender"])
        if a is not None:
            zaehlwerk.zaehle("formwahl", "regel")
            return {"artikel": a, "weg": "regel"}
        return None
    # ④ die Waage (nur wenn injiziert; sie selbst handelt nur über ihrer Blind-Proben-Schwelle)
    if waage is not None:
        a = waage(nomen)
        if a in ("ein", "eine"):
            zaehlwerk.zaehle("formwahl", "gewogen")
            return {"artikel": a, "weg": "gewogen"}
    zaehlwerk.zaehle("formwahl", "offen")
    return None
