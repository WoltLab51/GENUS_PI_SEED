"""Die dritte DENKWEISE: HYPOTHESE — Vermuten und Prüfen (Ronny 2026-07-06: „mach ③ den
Hypothese-Test-Loop"). Der aktive Halbkreis, der den Methoden-Bogen schließt.

Die Deduktion (genus/deduktion.py, ②) ist WAHRHEITSBEWAHREND: aus Regeln + Fakten folgt
Sicheres — aber nie etwas NEUES; sie entfaltet nur, was schon impliziert ist. Die Hypothese ist
der Generator davor: sie VERMUTET (eine plausible, unbewiesene Konjektur) und TESTET sie dann —
und der Tester ist ausgerechnet die Inferenz/Deduktion, sodass die beiden Hälften ineinander
greifen. Das ist zugleich die „gezähmte Kreativität" aus der Intelligenz-Studie (§4 ④): eine
Vermutung ist eine ETIKETTIERTE, GEDECKELTE, GEPRÜFTE Halluzination — Ehrlichkeit verbietet
Kreativität nicht, sie macht sie erst sicher.

  Erzeugen (vermute)   = Geschwister-Analogie, DETERMINISTISCH aus dem Graphen, KEIN Modell:
                         was die Mehrheit der Geschwister unter demselben is_a-Elternteil trägt
                         und der Anker A nicht, wird zur Konjektur „A p o". Die Herleitung
                         (k von m Geschwistern) ist im narrate sichtbar — kein verstecktes Preset.
  Prüfen (teste)       = der read-time Test über genus/inference.py — KEIN zweiter Schließer:
                         BESTÄTIGT (der Graph entailt es schon) · WIDERLEGT (ein is_a/part_of-Ring
                         würde kollabieren · eine geerdete Unvereinbarkeit greift — der Wal ist
                         kein Fisch · ODER eine causes-Vermutung kehrt eine bekannte Kausalrichtung
                         um, denn caused_by ist die Inverse) · OFFEN (ehrlich „mit meinem Wissen
                         nicht widerlegbar" — das ist NICHT dasselbe wie „wahr"). Prädikate ohne
                         ehrliche Widerlegung (used_for) bleiben bewusst DRAUSSEN.
  Aussprechen (--tick) = die EINE offene Top-Vermutung als gedeckelte Kante (Quelle
                         model:hypothese, Trust ≤ 0.25 — überstimmt NIE Geerdetes). Proposal ≠
                         Change: sie liegt vor, wiegt aber fast nichts; der Mensch bestätigt/verwirft.

Alles read-time und gläsern wie die Subsumtion: die zu prüfende Konjektur ist FLÜCHTIG, die
Vermutungs-Funktionen (vermute/teste_konjektur/vermute_und_teste/narrate) schreiben NICHTS. Die
EINZIGEN Schreibvorgänge sind (a) das geerdete Disjunktheits-WELTWISSEN (`unvereinbar_mit`, gesät
wie die Norm, Quelle „welt", idempotent — Bootstrap-Wissen, KEINE Vermutung) und (b) auf
ausdrücklichen `--tick` die eine gedeckelte Vermutung. Der ehrliche Invariant: **ohne --tick wird
keine VERMUTUNG geschrieben und nie nach außen gehandelt** (bewegt den Geist, nie die Hand).
`unvereinbar_mit` ist ein ISOLIERTES Prädikat — es fließt NIE in die is_a-Inferenz (sonst leitet
der Schließer Unsinn ab), nur der Refutations-Test liest es (in beiden Richtungen, weil es
symmetrisch gemeint ist).
"""
from __future__ import annotations

from genus import inference, sources

UNVEREINBAR = "unvereinbar_mit"      # symmetrisch gemeint, ISOLIERT — nie in die is_a-Inferenz
INHALT = "inhalt"
IS_A = "is_a"
PART_OF = "part_of"
CAUSES = "causes"
CAUSED_BY = "caused_by"               # die INVERSE von causes: A caused_by B  ==  B causes A
# Ein Prädikat darf nur dann zur Konjektur, wenn eine Vermutung über es ehrlich WIDERLEGBAR ist
# (sonst ist „offen" vakuum — eine unwiderlegbare Vermutung ist unehrlich, die ehrliche Decke):
#   is_a/part_of  -- transitiv & STRENG azyklisch (ein Ring ist ein echter Widerspruch) + is_a
#                    zusätzlich über Klassen-Disjunktheit (unvereinbar_mit).
#   causes/caused_by -- über die INVERSE: „A verursacht B" ist widerlegt, wenn der Graph die
#                    Gegenrichtung kennt (B verursacht A) — du kehrst eine bekannte Kausalrichtung
#                    um. Echtes, nicht-triviales Widerlegen ohne riskante Saat (Ronny 2026-07-06).
# BEWUSST DRAUSSEN: used_for (P366) hat KEINE Inverse und keine saubere Azyklizität; es ehrlich
# widerlegbar zu machen bräuchte eine Typ-Disjunktheits-Saat, die echte Wikidata-Kanten
# fehlwiderlegen würde. „Draußen lassen" ist hier die ehrlichere Antwort als eine Scheinprüfung.
KAUSAL_PRAEDIKATE = (CAUSES, CAUSED_BY)
ANALOGIE_PRAEDIKATE = (IS_A, PART_OF, CAUSES, CAUSED_BY)

MODEL_QUELLE = "model:hypothese"     # Präfix model: -> Trust automatisch auf 0.25 gedeckelt
WELT_QUELLE = "welt"                 # geerdetes Disjunktheits-Weltwissen, KEIN Modell-Rateschluss

# der eine Quasi-Parameter, gläsern als gelebte Schwelle benannt (kein verstecktes Preset):
MIN_GESCHWISTER = 2   # unter 2 Geschwistern ist „die anderen tun das auch" keine Analogie

# Die Widerlegungs-Suche braucht einen TIEFEREN Horizont als die alltägliche Inferenz
# (inference.MAX_DEPTH=6, eine Sicherheitsschranke): auf den realen Wikidata-Leitern liegt die
# disjunkte Ober-Klasse (Säugetier über dem Wal) oft mehr als 6 is_a-Hops entfernt. Ein zu flacher
# Horizont wäre HIER unehrlich — eine verpasste Widerlegung würde als „nicht widerlegbar" verkauft
# (eine Übertreibung), während eine verpasste Bestätigung nur konservativ „offen" bleibt. Darum
# suchen Bestätigung UND Widerlegung tief genug für reale Taxonomien, aber endlich (Schranke).
SUCH_TIEFE = 32

# Die minimale Disjunktheits-Saat (hand-gesät wie NORM_SEED, Quelle welt) — der Wal-Prüfstein.
# Bewusst winzig: v1 widerlegt genau die geerdeten Klassentrennungen (+ is_a/part_of-Zyklen),
# sonst bleibt es ehrlich OFFEN. Eine ehrliche Decke ist mehr wert als breite, unwiderlegbare
# Vermutung. Auf dem lebenden Wikidata-Graphen sind die Klassen Q-ids; diese symbolische Saat
# dokumentiert den Mechanismus und trägt die Off-Pi-Tests — die realen Q-id-Paare kommen bei
# Bedarf über denselben Sä-Helfer dazu (teach/seed, Quelle welt).
UNVEREINBAR_SEED: tuple[tuple[str, str, str], ...] = (
    # symbolisch — dokumentiert den Mechanismus und trägt die Off-Pi-Tests
    ("konzept:fisch", UNVEREINBAR, "konzept:saeugetier"),
    ("konzept:fisch", INHALT, "Fisch — eine eigene Tierklasse, unvereinbar mit Säugetier"),
    ("konzept:saeugetier", INHALT, "Säugetier — eine eigene Tierklasse, unvereinbar mit Fisch"),
    # real (Wikidata Q152 Fisch ⊥ Q7377 Säugetier) — damit die Widerlegung auf dem lebenden
    # Graphen greift (ein Hauspferd erreicht Q7377, kann also kein Q152 sein). So universell
    # wie das Gesetz in NORM_SEED; weitere reale Klassentrennungen kommen über denselben Helfer.
    ("Q152", UNVEREINBAR, "Q7377"),
)


def seed_hypothesen(conn) -> int:
    """Sät das Disjunktheits-Weltwissen — idempotent über den geteilten Sä-Helfer (wie recht)."""
    from genus import reactors

    return reactors.sae_fehlende(conn, [(s, p, o) for s, p, o in UNVEREINBAR_SEED], WELT_QUELLE)


# --- gläserne Helfer ----------------------------------------------------------------------

def _objekte(conn, subjekt: str, praedikat: str) -> list[str]:
    return [r["object"] for r in sources.relations(conn, subject=subjekt, predicate=praedikat)]


def _name(conn, knoten: str) -> str:
    """Menschlicher Name eines Knotens (Q726 -> „Pferd", Hund@de -> „Hund"), sonst unverändert."""
    anzeige = sources.display(conn, knoten)
    if anzeige.endswith(")") and "(" in anzeige:
        return anzeige[anzeige.rfind("(") + 1:-1]     # „Q726 (Pferd)" -> „Pferd"
    if "@" in anzeige:
        return anzeige.split("@", 1)[0]               # „Hund@de" -> „Hund"
    return anzeige


def _profil(conn, X: str) -> set[tuple[str, str]]:
    """Eigenschafts-Profil von X: die Menge ``(praedikat, objekt)`` — NUR über die transitiv-
    sicheren Analogie-Prädikate (:data:`ANALOGIE_PRAEDIKATE`)."""
    return {(p, o) for p in ANALOGIE_PRAEDIKATE for o in _objekte(conn, X, p)}


def _geschwister(conn, A: str) -> dict[str, list[str]]:
    """Das Rohmaterial der Analogie: je is_a-Elternteil P von A die anderen Kinder von P (ohne A).
    Die Kinder werden als DISTINKTE Knoten geführt: auf dem lebenden Graphen ist jede is_a-Kante
    mehrfach bequellt (Wikidata + Lexem + DBnary), ein Geschwister erschiene sonst einmal PRO
    Quelle und würde die Mehrheits-Arithmetik in :func:`vermute` verfälschen (eine erfundene
    Mehrheit). Deduplizieren = je Geschwister genau eine Stimme."""
    ergebnis: dict[str, list[str]] = {}
    for P in set(_objekte(conn, A, IS_A)):
        kinder = sorted({r["subject"] for r in sources.relations(conn, predicate=IS_A, object=P)
                         if r["subject"] != A})
        if kinder:
            ergebnis[P] = kinder
    return ergebnis


# --- Erzeugen: die Vermutung --------------------------------------------------------------

def vermute(conn, A: str, hoechstens: int = 20) -> list[dict]:
    """Erzeugt Konjekturen für den Anker ``A`` per Geschwister-Analogie — deterministisch,
    gläsern, modellfrei. Ein Merkmal ``(p, o)``, das die MEHRHEIT der Geschwister unter einem
    gemeinsamen is_a-Elternteil P trägt (k von m, ``k*2 > m``, ``m >= MIN_GESCHWISTER``) und A
    NICHT, wird zur Vermutung „A p o" mit sichtbarer Herleitung. Stabil geordnet (Stärke k/m
    absteigend, dann lexikografisch) — voll replaybar, kein Zufall. Read-time, erzeugt nichts."""
    eigen = _profil(conn, A)
    beste: dict[tuple[str, str], dict] = {}     # (p, o) -> stärkste Herleitung über alle Eltern
    for P, geschwister in _geschwister(conn, A).items():
        m = len(geschwister)
        if m < MIN_GESCHWISTER:
            continue
        traeger: dict[tuple[str, str], list[str]] = {}
        for G in geschwister:
            for merkmal in _profil(conn, G):
                traeger.setdefault(merkmal, []).append(G)
        for merkmal, wer in traeger.items():
            if merkmal in eigen or merkmal[1] == A:     # A trägt es schon / entartet -> nichts
                continue
            k = len(wer)
            if k * 2 <= m:                              # keine echte Mehrheit -> zu schwach
                continue
            staerke = k / m
            vorher = beste.get(merkmal)
            if vorher is None or staerke > vorher["staerke"]:
                beste[merkmal] = {"ueber": P, "k": k, "m": m, "geschwister": wer,
                                  "staerke": staerke}
    vermutungen = [{
        "subjekt": A, "praedikat": p, "objekt": o, "strategie": "geschwister_analogie",
        "staerke": round(h["staerke"], 3),
        "herleitung": {"muster": "geschwister_analogie", "ueber": h["ueber"],
                       "k": h["k"], "m": h["m"], "geschwister": h["geschwister"]},
    } for (p, o), h in beste.items()]
    vermutungen.sort(key=lambda v: (-v["staerke"], v["praedikat"], v["objekt"]))
    return vermutungen[:hoechstens]


# --- Prüfen: der Test (die Inferenz ist der Schiedsrichter, kein zweiter Schließer) -------

def _unvereinbar(conn, subjekt: str, objekt: str) -> dict | None:
    """Der Wal-Refutations-Kern: erreicht der Konjektur-Träger ``subjekt`` via is_a eine Klasse X,
    die mit einer Klasse Y unvereinbar ist, die der Konjektur-Gegenstand ``objekt`` via is_a
    erreicht? Dann ist „subjekt is_a objekt" ausgeschlossen. Beide Richtungen der symmetrisch
    gemeinten ``unvereinbar_mit``-Kante werden EXPLIZIT gelesen (is_symmetric lernt dieses
    isolierte Prädikat nicht). Gibt die Widerlegungs-Kette zurück oder ``None``."""
    for r in sources.relations(conn, predicate=UNVEREINBAR):
        for x, y in ((r["subject"], r["object"]), (r["object"], r["subject"])):
            if inference.reaches(conn, subjekt, x, IS_A, max_depth=SUCH_TIEFE) and \
               inference.reaches(conn, objekt, y, IS_A, max_depth=SUCH_TIEFE):
                return {"subjekt_ist": x, "objekt_ist": y, "quelle": r["source"]}
    return None


def _kausal_nachfolger(conn, knoten: str) -> set[str]:
    """Was ``knoten`` (direkt) verursacht — die vereinte gerichtete Kausalrelation: die
    ``causes``-Ziele PLUS die Knoten, die ``knoten`` als ``caused_by`` nennen (X caused_by knoten
    == knoten causes X). So zählt beide Schreibweisen als eine Kausalrichtung."""
    ziele = set(_objekte(conn, knoten, CAUSES))
    for r in sources.relations(conn, predicate=CAUSED_BY, object=knoten):
        ziele.add(r["subject"])
    return ziele


def _kausal_erreicht(conn, von: str, nach: str, max_depth: int = SUCH_TIEFE) -> bool:
    """Erreicht ``von`` das Ziel ``nach`` über die vereinte KAUSALKETTE (causes + caused_by-
    Inverse)? Ein tiefen-gedeckelter BFS — die transitive Verallgemeinerung der direkten
    Gegenrichtung: eine Kausalkette B→…→A macht „A verursacht B" zum Ring, egal wie lang."""
    if von == nach:
        return True
    gesehen, front = {von}, [von]
    for _ in range(max_depth):
        neu = []
        for n in front:
            for o in _kausal_nachfolger(conn, n):
                if o == nach:
                    return True
                if o not in gesehen:
                    gesehen.add(o)
                    neu.append(o)
        if not neu:
            break
        front = neu
    return False


def _kausal_urteil(conn, subjekt: str, praedikat: str, objekt: str) -> str | None:
    """Kausal-Urteil über die INVERSE + die transitive KAUSALKETTE. Die Vermutung ist eine
    gerichtete Kausalkante ``ursache → wirkung`` (bei caused_by getauscht). BESTÄTIGT, wenn die
    Kante direkt (in einer der beiden Schreibweisen) steht; WIDERLEGT, wenn die ``wirkung`` die
    ``ursache`` über eine KAUSALKETTE erreicht — dann schlösse die Vermutung einen Kausal-Ring
    (du kehrst den bekannten Kausal-Fluss um). Das ist meist ein echter Widerspruch, selten ein
    wahrer Rückkopplungs-Kreis (Wetter↔Klima); darum benennt narrate die Rest-Unsicherheit
    ehrlich. Read-time; ``None``, wenn der Graph zur Richtung nichts sagt (dann bleibt es offen)."""
    ursache, wirkung = (subjekt, objekt) if praedikat == CAUSES else (objekt, subjekt)

    def steht(s, p, o):
        return bool(sources.relations(conn, subject=s, predicate=p, object=o))

    if steht(ursache, CAUSES, wirkung) or steht(wirkung, CAUSED_BY, ursache):
        return "bestaetigt"                        # die Kante steht direkt -> nichts Neues
    if _kausal_erreicht(conn, wirkung, ursache):   # Gegenrichtung (transitiv) bekannt -> Ring
        return "widerlegt"
    return None


def teste_konjektur(conn, subjekt: str, praedikat: str, objekt: str) -> dict:
    """DER Tester (read-time, erzeugt nichts — spiegelt recht.subsumiere: rechnet, gibt ein dict).
    Prüft „subjekt praedikat objekt" gegen den Graphen mit der Inferenz als Schiedsrichter:
      bestaetigt  der Graph enthält/entailt es schon (direkt/transitiv, oder kausal via Inverse);
      widerlegt   ein is_a/part_of-Ring würde kollabieren · eine geerdete Unvereinbarkeit greift ·
                  ODER eine causes/caused_by-Vermutung kehrt eine bekannte Kausalrichtung um;
      offen       weder noch — ehrlich unbewiesen (open-world), NICHT „wahr".
    Über ein Prädikat ohne ehrliche Widerlegung (z.B. used_for) ist ``widerlegbar`` False."""
    transitiv = inference.is_transitive(conn, praedikat)
    direkt = bool(sources.relations(conn, subject=subjekt, predicate=praedikat, object=objekt))
    # Bestätigung UND Zyklus-Widerlegung suchen tief (SUCH_TIEFE), nicht mit dem flachen
    # Alltags-Horizont — sonst rutscht auf realen Leitern eine echte Widerlegung still auf „offen".
    entailt = direkt or (transitiv
                         and inference.reaches(conn, subjekt, objekt, praedikat, max_depth=SUCH_TIEFE))
    schliesst_ring = transitiv and inference.reaches(conn, objekt, subjekt, praedikat,
                                                     max_depth=SUCH_TIEFE)
    # Klassen-Disjunktheit widerlegt nur eine KLASSEN-Zugehörigkeit (is_a), nicht ein part_of:
    # ein Metallteil kann Teil eines Holzstuhls sein (Metall/Holz unvereinbar, part_of trotzdem).
    unvereinbar = _unvereinbar(conn, subjekt, objekt) if praedikat == IS_A else None
    # Kausal: die INVERSE (caused_by) macht causes ehrlich widerlegbar (Gegenrichtung bekannt).
    kausal = _kausal_urteil(conn, subjekt, praedikat, objekt) if praedikat in KAUSAL_PRAEDIKATE else None

    if entailt or kausal == "bestaetigt":
        urteil = "bestaetigt"
    elif schliesst_ring or unvereinbar is not None or kausal == "widerlegt":
        urteil = "widerlegt"
    else:
        urteil = "offen"

    # Vertrauen einer BESTÄTIGTEN transitiven Konjektur = schwächste Prämisse der Inferenz-Kette
    # (NICHT der Modell-Deckel: sie folgt deduktiv, stammt nicht vom Modell).
    vertrauen, chain = None, None
    if entailt and not direkt:
        for d in inference.infer(conn, subjekt, praedikat, max_depth=SUCH_TIEFE):
            if d["object"] == objekt:
                vertrauen, chain = d["trust"], d["chain"]
                break
    return {"subjekt": subjekt, "praedikat": praedikat, "objekt": objekt, "urteil": urteil,
            "transitiv": transitiv, "direkt": direkt, "entailt": entailt,
            "schliesst_ring": schliesst_ring, "unvereinbar_kette": unvereinbar, "kausal": kausal,
            "widerlegbar": transitiv or praedikat == IS_A or praedikat in KAUSAL_PRAEDIKATE,
            "vertrauen": vertrauen, "chain": chain}


def vermute_und_teste(conn, A: str) -> dict | None:
    """Der eine Zug: erzeugt + testet Vermutungen für ``A`` und gibt die EINE bemerkenswerteste
    zurück — die stärkste OFFENE (aussprechbar), oder wenn keine offen ist die stärkste
    WIDERLEGTE (eine gelernte Grenze, Popper). Bestätigte (schon im Graphen) werden verworfen,
    sie sind nichts Neues. ``None``, wenn ``A`` gar keine testbare Vermutung trägt. Genau EIN
    Kandidat pro Aufruf (keine Flut). Read-time."""
    getestet = []
    for v in vermute(conn, A):
        e = teste_konjektur(conn, v["subjekt"], v["praedikat"], v["objekt"])
        e.update({"strategie": v["strategie"], "staerke": v["staerke"],
                  "herleitung": v["herleitung"]})
        getestet.append(e)
    offen = [e for e in getestet if e["urteil"] == "offen"]
    if offen:
        return offen[0]                                   # schon nach Stärke geordnet
    widerlegt = [e for e in getestet if e["urteil"] == "widerlegt"]
    return widerlegt[0] if widerlegt else None


# --- Aussprechen: die eine gedeckelte, gegatete Emission -----------------------------------

def emit_vermutung(conn, e: dict) -> int:
    """Spricht die (OFFENE) Vermutung als gedeckelte Kante aus — Quelle model:hypothese (Trust
    ≤ 0.25, überstimmt nie Geerdetes), idempotent über den Sä-Helfer (kein Duplikat bei erneutem
    Tick). Proposal ≠ Change: die Kante liegt vor, wiegt aber fast nichts; der Mensch bestätigt
    (teach_relation) oder verwirft (retract_relation). Gibt 1 zurück, wenn NEU ausgesprochen,
    sonst 0. Eine nicht-offene Vermutung wird NIE ausgesprochen."""
    if e["urteil"] != "offen":
        return 0
    from genus import reactors

    return reactors.sae_fehlende(conn, [(e["subjekt"], e["praedikat"], e["objekt"])], MODEL_QUELLE)


# --- Gläserner Beweis ----------------------------------------------------------------------

def narrate_hypothese(conn, e: dict) -> str:
    """Der gläserne Beweis der Vermutung: Konjektur → Herleitung (k von m Geschwistern) → Test +
    Urteil (bei widerlegt die Kette samt Quelle) → ehrliche Einordnung. Deutsch, deterministisch,
    modellfrei — im Ton von recht.narrate_subsumtion / deduktion.narrate."""
    A, Z = _name(conn, e["subjekt"]), _name(conn, e["objekt"])
    verb = {IS_A: "ist ein", PART_OF: "gehört zu", CAUSES: "verursacht",
            CAUSED_BY: "wird verursacht von"}.get(e["praedikat"], "gehört zu")
    zeilen = [f"Vermutung: {A} {verb} »{Z}«."]
    h = e.get("herleitung")
    if h and h.get("muster") == "geschwister_analogie":
        P = _name(conn, h["ueber"])
        zeilen.append(f"Warum: {h['k']} von {h['m']} Geschwistern unter »{P}« tun das, {A} bisher "
                      f"nicht — eine Analogie (Stärke {e.get('staerke')}).")
    if e["urteil"] == "bestaetigt":
        wie = (f" (Vertrauen {e['vertrauen']}, schwächste Prämisse)" if e.get("vertrauen") is not None
               else "")
        zeilen.append(f"Test: schon BESTÄTIGT — der Graph leitet es bereits ab{wie}. Nichts Neues.")
    elif e["urteil"] == "widerlegt":
        u = e.get("unvereinbar_kette")
        if e.get("kausal") == "widerlegt":
            # WELCHE Seite der Graph als Ursache kennt, hängt vom Prädikat ab: bei „A verursacht B"
            # (causes) steht die Gegenrichtung, also ist B (=Z) die bekannte Ursache; bei „A wird
            # verursacht von B" (caused_by) steht A als Ursache. Sonst lügt der Beweistext (Review).
            ursache = Z if e["praedikat"] == CAUSES else A
            zeilen.append(f"Test: WIDERLEGT — der Graph kennt bereits die GEGENrichtung (»{ursache}« "
                          f"steht als Ursache, nicht als Wirkung). Eine bekannte Kausalrichtung "
                          f"umzukehren ist meist falsch (nur selten ein echter Rückkopplungs-Kreis).")
        elif u:
            xi, yi = _name(conn, u["subjekt_ist"]), _name(conn, u["objekt_ist"])
            zeilen.append(f"Test: WIDERLEGT. {A} ist ein »{xi}«, und »{xi}« ist unvereinbar mit "
                          f"»{yi}« (Quelle: {u['quelle']}). Die Analogie war verführerisch, aber "
                          f"falsch — eine gelernte Grenze.")
        else:
            zeilen.append(f"Test: WIDERLEGT — {A} {verb} »{Z}« würde einen Widerspruch schließen "
                          f"(»{Z}« zählt bereits zu »{A}«). Eine gelernte Grenze.")
        zeilen.append("Ich schreibe nichts — eine Widerlegung ist Erkenntnis, keine Behauptung.")
    else:  # offen
        if e.get("widerlegbar"):
            zeilen.append("Test: mit meinem Wissen nicht widerlegbar — ich finde keinen Widerspruch, "
                          "aber eine offene Vermutung ist damit nicht wahr, nur ungeprüft.")
        else:
            zeilen.append(f"Test: über »{e['praedikat']}« kann ich weder beweisen noch widerlegen "
                          f"— offen, und mit meinen Mitteln ehrlich unprüfbar.")
    return "\n".join(zeilen)
