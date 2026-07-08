"""faehigkeit:abstrahieren, Scheibe 1 — der Sprung vom IMPORTIEREN zum DENKEN, rein lesend.

GENUS schaut in seinen EIGENEN Graphen und findet Gruppen von Geschwistern (Kindern desselben
is_a-Elternteils), die ein noch UNBENANNTES Merkmal-Bündel teilen — der Keim eines neuen Begriffs.
Das Rohmaterial ist dasselbe wie in :func:`genus.hypothese.vermute` (die Träger-Map „welches
Geschwister trägt welches Merkmal"), nur ANDERSHERUM gelesen: nicht „was fehlt EINEM Anker",
sondern „was teilt eine GANZE Gruppe, ohne dass es dafür schon einen Namen gibt".

Der Ehrlichkeits-Test (docs/GENUS_INTELLIGENZ.md: ein Begriff ist eine VERDICHTUNG — kürzer als die
Fakten und MÄCHTIGER; §9d: „man darf nur dort vermuten, wo man auch falsch liegen kann"): eine
Bündel-Definition ist über ihre eigene Auswahl TAUTOLOGISCH. Darum zählt ein Kandidat NUR, wenn die
Gruppe eine WEITERE geteilte Eigenschaft VORHERSAGT, auf die nicht ausgewählt wurde — die
Überraschung, die aus einer Willkür-Schnittmenge einen echten Begriff macht. Und nur, wenn es für
die Gruppe noch KEINEN feineren benannten Oberbegriff gibt (sonst ist der Begriff schon da).

Scheibe 1 SCHREIBT NICHTS und ruft KEIN Modell: sie macht das Muster nur sichtbar (gläsern, mit der
Mitglieder-Liste als Begründung). Das PRÄGEN eines echten Knotens (gedeckelt, Quelle
``model:abstraktion``, nur auf ``--tick``, Mensch bestätigt/verwirft — 1:1 gespiegelt von
:func:`genus.hypothese.emit_vermutung`) und der Durchlauf durch :func:`genus.hypothese.teste_konjektur`
ist bewusst Scheibe 2.
"""
from __future__ import annotations

from genus import sources
from genus.hypothese import IS_A, _name, _objekte

# Das Bündel wird über die DYNAMISCHE (verbindende) Schicht gebildet -- was die Dinge TUN, woraus
# sie bestehen, wozu sie dienen -- NICHT über is_a: das gruppiert sie schon (der Elternteil P). Ein
# geteiltes weiteres is_a wäre selbst ein benannter Oberbegriff (den fängt die Schon-benannt-Prüfung).
MERKMAL_PRAEDIKATE = ("part_of", "has_part", "made_of", "used_for", "causes", "caused_by")

# Gelebte Schwellen, gläsern benannt (wie hypothese.MIN_GESCHWISTER=2), kein verstecktes Preset:
MIN_MITGLIEDER = 3   # unter 3 gemeinsamen Dingen ist es ein Zufall zu zweit, kein Begriff.
MIN_MERKMALE = 3     # ein Begriff braucht ein BÜNDEL von >=3 UNTERSCHEIDENDEN Merkmalen: zwei würden
                     # genügen, die Gruppe zu benennen -- dass sie ALLE drei (oder mehr) teilen, ist
                     # die Überraschung/Verdichtung (docs/GENUS_INTELLIGENZ.md), kein Tautologie-Paar.

# Ein Naben-Knoten (»Objekt«, »Entität«) hat Tausende Kinder -- zu grob für einen scharfen
# unbenannten Begriff und teuer im Paar-Durchlauf. entdecke() überspringt solche Naben; ihre
# feineren Unter-Elternteile tragen die echten Muster. Ehrlich benannte Deckung, kein Fehlen.
MAX_KINDER_JE_ELTERNTEIL = 200

# Zwei Kandidaten, deren Mitglieder sich zu >= der Hälfte (des kleineren) decken, sind DERSELBE
# Begriff, nur anders geschnitten -- den stärkeren behalten, den anderen unterdrücken. Der erste
# Live-Lauf zeigte 5 fast gleiche „gemeinsame Buchstaben"-Scheiben (verschiedene Alphabet-Teilmengen
# desselben Kerns); ehrliche Verdichtung heißt: EINEN Begriff zeigen, nicht fünf Schatten davon.
UEBERLAPPUNG = 0.5


def _merkmale(conn, X: str) -> set[tuple[str, str]]:
    """Das dynamische Merkmal-Profil von X: ``(praedikat, objekt)`` über :data:`MERKMAL_PRAEDIKATE`."""
    return {(p, o) for p in MERKMAL_PRAEDIKATE for o in _objekte(conn, X, p)}


def _kinder(conn, P: str) -> list[str]:
    """Die Kinder von P (Knoten mit ``is_a P``), distinkt -- je Kind eine Stimme (der Graph ist
    mehrfach bequellt, wie in hypothese._geschwister)."""
    return sorted({r["subject"] for r in sources.relations(conn, predicate=IS_A, object=P)})


def _schon_benannt(conn, mitglieder: list[str], P: str) -> str | None:
    """Gibt es schon einen menschlich BENANNTEN, feineren is_a-Elternteil Q ≠ P (selbst ``is_a P``),
    dessen Kinder GENAU die Mitglieder sind? Dann trägt exakt diese Gruppe bereits den Namen Q --
    kein neuer Begriff. Das ``==`` ist entscheidend (Review-Fund): teilen alle Mitglieder ein Q,
    das aber NOCH WEITERE Kinder hat, benennt Q nur eine gröbere Obergruppe, nicht diesen feineren
    Begriff -- dann ist er sehr wohl neu. Flache Prüfung (direkte Eltern); Scheibe 1 schreibt nichts,
    ein übersehener tieferer Name fällt bei der menschlichen Sicht auf. Gibt Q zurück oder ``None``."""
    mitgl = set(mitglieder)
    gemeinsame: set[str] | None = None
    for m in mitglieder:
        eltern = {o for o in _objekte(conn, m, IS_A) if o != P}
        gemeinsame = eltern if gemeinsame is None else (gemeinsame & eltern)
        if not gemeinsame:
            return None
    for Q in sorted(gemeinsame or ()):
        if P not in _objekte(conn, Q, IS_A) or _name(conn, Q) == Q:   # Q muss feiner als P UND benannt sein
            continue
        kinder_Q = {r["subject"] for r in sources.relations(conn, predicate=IS_A, object=Q)}
        if kinder_Q == mitgl:                     # Q benennt GENAU diese Gruppe (kein echter Superset)
            return Q
    return None


def verdichte(conn, P: str) -> list[dict]:
    """Findet Begriffs-Kandidaten unter dem is_a-Elternteil ``P``: Teilmengen der Kinder, die ein
    noch UNBENANNTES Merkmal-Bündel teilen UND eine weitere, nicht ausgewählte Eigenschaft
    VORHERSAGEN (die Überraschung gegen die Tautologie). Read-time, modellfrei, schreibt nichts.
    Rückgabe: Kandidaten, stark (viele Mitglieder, viel Überraschung) zuerst."""
    kinder = _kinder(conn, P)
    n = len(kinder)
    if n < MIN_MITGLIEDER:
        return []
    profil = {k: _merkmale(conn, k) for k in kinder}
    traeger: dict[tuple[str, str], set[str]] = {}
    for k in kinder:
        for merkmal in profil[k]:
            traeger.setdefault(merkmal, set()).add(k)
    # UNTERSCHEIDENDE Merkmale: von >=2, aber NICHT von ALLEN Kindern getragen. Ein Merkmal, das
    # ALLE Kinder tragen, gehört zum »P-Sein« und unterscheidet die Untergruppe von nichts -- es
    # als Überraschung zu zählen wäre eine Schein-Verdichtung (Review-Fund 1).
    diskr = {m: wer for m, wer in traeger.items() if 2 <= len(wer) < n}
    if not diskr:
        return []
    sig = {k: frozenset(m for m, wer in diskr.items() if k in wer) for k in kinder}

    # Für jedes Kind den REICHSTEN Begriff, dem es angehört: die Hülle seiner Signatur (formale
    # Begriffsanalyse) -- extent = alle mit >= diesem Bündel, intent = Schnitt ihrer Signaturen, bis
    # stabil. So wird die maximale Gruppe {A,B,C}, die ein 3er-Bündel teilt, wirklich erreicht --
    # anders als ein Merkmal-PAAR als Definition, das einen Randgänger mit hereinzöge (Review-Fund 2).
    kandidaten: dict[frozenset, dict] = {}
    for k in kinder:
        intent = sig[k]
        if len(intent) < MIN_MERKMALE:
            continue
        while True:
            extent = frozenset(x for x in kinder if intent <= sig[x])
            neu = frozenset.intersection(*(sig[x] for x in extent))
            if neu == intent:
                break
            intent = neu
        if len(extent) < MIN_MITGLIEDER or len(intent) < MIN_MERKMALE or extent in kandidaten:
            continue
        if _schon_benannt(conn, sorted(extent), P):
            continue
        # Definition = die 2 allgemeinsten (von den meisten getragenen) Merkmale; die übrigen sind
        # die Überraschung: dass die Gruppe AUCH diese teilt, folgt nicht aus der Definition.
        geordnet = sorted(intent, key=lambda m: (-len(diskr[m]), m))
        vorhergesagt = sorted(set(intent) - set(geordnet[:2]))
        kandidaten[extent] = {
            "elternteil": P,
            "mitglieder": sorted(extent),
            "definition": sorted(geordnet[:2]),
            "buendel": sorted(intent),
            "vorhergesagt": vorhergesagt,
        }
    ergebnis = list(kandidaten.values())
    ergebnis.sort(key=lambda c: (-len(c["mitglieder"]), -len(c["vorhergesagt"]),
                                 str(c["mitglieder"])))
    return ergebnis


def entdecke(conn, hoechstens: int = 10) -> list[dict]:
    """Scannt den ganzen Graphen: alle is_a-Elternteile mit genug Kindern, sammelt Begriffs-
    Kandidaten und ordnet sie stark zuerst. Die Mitglieder-Schwelle wird über die gefundene
    Population SELBST-KALIBRIERT (weiteste natürliche Lücke, Boden :data:`MIN_MITGLIEDER`) --
    kein Preset. Read-time, schreibt nichts."""
    # Nur Elternteile mit genug (aber nicht zu vielen) Kindern -- EINE Aggregat-Abfrage statt den
    # ganzen Graphen abzugehen (dasselbe Direkt-SQL-Idiom wie inference.py). Naben-Knoten mit
    # Tausenden Kindern fallen bewusst raus (siehe MAX_KINDER_JE_ELTERNTEIL).
    eltern = [r["object"] for r in conn.execute(
        "SELECT object, COUNT(DISTINCT subject) AS n FROM relation_projection "
        "WHERE predicate = ? GROUP BY object HAVING n >= ? AND n <= ? "
        "ORDER BY n DESC, object",
        (IS_A, MIN_MITGLIEDER, MAX_KINDER_JE_ELTERNTEIL),
    ).fetchall()]
    alle: list[dict] = []
    for P in eltern:
        alle.extend(verdichte(conn, P))
    # Stärke = viele Mitglieder + viel Überraschung; :data:`MIN_MITGLIEDER` ist der gläserne Boden
    # (absolut, wie hypothese.MIN_GESCHWISTER). BEWUSST KEIN globaler selbst-kalibrierter Schnitt
    # über die Mitgliederzahlen: der erste Live-Lauf zeigte, dass ein einzelner Riesen-Cluster
    # (26 Biochemie-Aktivitäten) sonst die weiteste Lücke setzt und ALLE kleineren, oft
    # bedeutsameren Kandidaten unterdrückt. Kalibrierung vergleicht mit der eigenen Historie --
    # hier würden Kandidaten aus UNVERWANDTEN Elternteilen verglichen, das ist der falsche Maßstab.
    alle.sort(key=lambda c: (-len(c["mitglieder"]), -len(c["vorhergesagt"]), str(c["mitglieder"])))
    # Überlappungs-Dedup: derselbe Begriff, anders geschnitten, taucht nicht mehrfach auf --
    # den stärkeren (zuerst gereihten) behalten, stark überlappende Schatten unterdrücken.
    behalten: list[dict] = []
    for c in alle:
        cm = set(c["mitglieder"])
        if any(len(cm & set(k["mitglieder"])) >= UEBERLAPPUNG * min(len(cm), len(k["mitglieder"]))
               for k in behalten):
            continue
        behalten.append(c)
        if len(behalten) >= hoechstens:
            break
    return behalten


def _merkmal_text(conn, merkmal: tuple[str, str]) -> str:
    p, o = merkmal
    verb = {"part_of": "Teil von", "has_part": "hat Teil", "made_of": "besteht aus",
            "used_for": "dient zu", "causes": "verursacht",
            "caused_by": "wird verursacht von"}.get(p, p)
    return f"{verb} »{_name(conn, o)}«"


def _merkmal_liste(conn, merkmale: list[tuple[str, str]]) -> str:
    """Merkmale als Text, nach ANZEIGE dedupliziert -- auf dem lebenden Graphen rendern zwei
    verschiedene Objekte manchmal gleich (z.B. »4-)«); doppelt anzuzeigen wäre nur verwirrend."""
    gesehen: set[str] = set()
    texte: list[str] = []
    for m in merkmale:
        t = _merkmal_text(conn, m)
        if t not in gesehen:
            gesehen.add(t)
            texte.append(t)
    return "; ".join(texte)


def narrate(conn, kandidat: dict) -> str:
    """Der gläserne Begriffs-Vorschlag: welche Mitglieder, welches Bündel, die Überraschung
    (was die Gruppe JENSEITS der Definition teilt) und die ehrliche Einordnung (kein Name da,
    ich schreibe nichts). Deutsch, deterministisch, modellfrei -- im Ton von hypothese.narrate."""
    P = _name(conn, kandidat["elternteil"])
    namen = [_name(conn, m) for m in kandidat["mitglieder"]]
    n = len(namen)
    gezeigt = ", ".join(namen[:8]) + ("" if n <= 8 else f" … (+{n - 8})")
    zeilen = [f"Begriffs-Kandidat unter »{P}«: {n} Dinge teilen ein noch unbenanntes Muster.",
              f"Mitglieder: {gezeigt}.",
              "Gemeinsam: " + _merkmal_liste(conn, kandidat["buendel"]) + "."]
    if kandidat["vorhergesagt"]:
        zeilen.append("Überraschung (nicht ausgewählt, aber alle teilen es auch): "
                      + _merkmal_liste(conn, kandidat["vorhergesagt"]) + ".")
    zeilen.append("Für diese Gruppe gibt es noch keinen Namen — genau das macht sie zu einem "
                  "Begriffs-Kandidaten. Ich schreibe nichts; ich zeige nur, was ich sehe.")
    return "\n".join(zeilen)
