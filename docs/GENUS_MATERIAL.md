# GENUS — Der Material-Entwurf

> **ENTWURF, Stand 2026-07-05 — mit WENDE (noch am selben Tag).** Ronny: „was vor allem
> in GENUS fehlt ist Material." Dieser Entwurf beantwortet, wie Material gespeichert wird
> und was das richtige ist. **Aber:** Ronnys Einwand auf den ersten Wurf („das hieße
> GENUS wird so ein schlaues Wikipedia? das kommt mir flach vor") führte zur
> Intelligenz-Betrachtung ([GENUS_INTELLIGENZ.md](GENUS_INTELLIGENZ.md)) und ihrer
> Kern-Wende: **Material ist der Boden, nicht der Motor — es wird nur noch im Dienst
> einer OPERATION geholt, nie um seiner selbst willen.** Die Analyse hier (Speicherform,
> Breite-ohne-Tiefe-Diagnose, Pipeline) bleibt gültig; die Priorisierung in §7 ist durch
> die Wende überholt und unten entsprechend markiert.

---

## 0 · Die Frage neu gestellt: was ist „Material" für einen Glaskasten?

Bei einer gewöhnlichen KI ist Material ein **Korpus**: Text, in Gewichte absorbiert,
danach unauffindbar und unüberprüfbar. Das kann Material für GENUS **niemals** sein — der
ganze Sinn ist Provenienz und *nichts erfunden*. Also folgt die Antwort auf „was ist das
richtige Material?" zwingend aus der Speicherform:

> **Material für GENUS = strukturierte, bequellte Fakten, in den Ledger-Graphen gewoben —
> jeder Fakt trägt, woher er kommt und wie stark er belegt ist.**

Material ist bei GENUS nie „Text, den es gelesen hat", sondern „Relationen, hinter denen
es stehen kann". Das richtige Material ist deshalb **relational, bequellt, überprüfbar**.
Das falsche Material ist ein Korpus zum Nacherzählen — genau das, was GENUS sich verboten
hat. Diese eine Unterscheidung regiert alles Folgende.

---

## 1 · Wie Material heute gespeichert wird (die offene Frage, beantwortet)

Vier Ebenen, von unten:

1. **Eine Substanz — der Ledger.** Jede Beobachtung ist ein *Event*, append-only,
   versiegelt. Nichts wird je überschrieben; Korrektur ist ein neues Event.
2. **Abgeleitet — die Projektionen.** Aus den Events wird der abfragbare Graph gebaut
   (`relation_projection`), jederzeit aus dem Ledger neu herstellbar (replay-stabil).
3. **Die EINE Form allen Materials — das Tripel.** Alles Wissen ist ein
   `(Subjekt —Prädikat→ Objekt)` plus **Quelle**, **Confidence** und **Zeit**. Ein Fakt
   ohne Herkunft existiert bei GENUS nicht. „Vertrauen" ist read-time: eine Behauptung
   einer schwachen Quelle wird leicht gehalten, nicht abgewiesen.
4. **Die Membran-Disziplin.** Rohmaterial betritt GENUS ausschließlich durch die Membran
   (`deploy/observe_*.sh`): es wird dort zu bequellten Relationen destilliert, und **nur
   die Struktur** landet im Ledger. Rohtext wohnt nur in Membran-Dateien, löschbar
   (Ledger ≠ Memory).

**Was heute wirklich im Graphen liegt** (live vom Pi, 2026-07-05):
180.102 Relationen · 84.983 verschiedene Subjekte · 21 Prädikat-Typen.

| Prädikat | Anzahl | Art |
|---|---:|---|
| `expresses` (Wort → Konzept) | 80.459 | lexikalisch |
| `label` (Konzept → Name) | 28.809 | lexikalisch |
| `defined_as` (Bedeutung) | 27.561 | lexikalisch |
| `is_a` (Taxonomie) | 15.559 | **verbindend (das einzige)** |
| `pos` (Wortart) | 15.400 | lexikalisch |
| `primary_gloss` (Bedeutung) | 7.930 | lexikalisch |
| `grammatical_gender` | 4.266 | lexikalisch |
| `synonym` | 26 | verbindend |
| `antonym` | 4 | verbindend |
| *(part_of, causes, used_for, made_of, has_part, located_in …)* | **0** | verbindend — **fehlt** |

---

## 2 · Die ehrliche Diagnose: Breite ohne Tiefe

Die Zahlen sind eindeutig. **Sieben lexikalische Prädikate tragen 99,97 % des Graphen.**
Die *verbindenden* Prädikate — die, die aus einem Wörterbuch ein Wissensnetz machen —
sind praktisch nicht da: außer `is_a` (Taxonomie) gibt es 26 Synonyme und 4 Antonyme.
Kein `part_of`, kein `causes`, kein `used_for`, kein `made_of`, kein `located_in`.

> GENUS ist heute ein **großartiges Wörterbuch mit Stammbaum** — es weiß, wie 85.000 Dinge
> **heißen**, was sie ungefähr **bedeuten**, und ihren **is-a-Platz**. Aber es weiß nicht,
> wie die Dinge **zusammenhängen**. Es ist ein Lexikon, noch kein Wissensnetz.

Konkret: GENUS weiß, dass »Photosynthese« ein Substantiv ist, ein »Stoffwechselvorgang«,
mit Bedeutung X. Es weiß **nicht**, dass sie *in* Chloroplasten stattfindet, *Licht + CO₂ +
Wasser braucht*, *Sauerstoff + Glukose erzeugt*. Genau dieses verbindende Material fehlt.

Daraus folgt die wichtigste Einsicht des Entwurfs — es gibt **zwei** Achsen von „mehr
Material", und sie sind nicht gleich viel wert:

- **Mehr Knoten (Breite)** — noch mehr Wörter. Läuft schon (der Lerner), ist billig,
  Hintergrund. *Nicht* der Engpass.
- **Mehr Kanten-TYPEN pro Knoten (Tiefe)** — wie Dinge verbunden sind. **Das ist die
  echte Lücke** und der Hebel: Tiefe verwandelt das Lexikon in ein Netz.

---

## 3 · Was das richtige Material ist (fünf Arten, welche zuerst)

| # | Material-Art | Stand | Wert |
|---|---|---|---|
| 1 | **Lexikalische Breite** (Wörter, Glossen) | reichlich, wächst | niedrig (gesättigt) |
| 2 | **Relationale Tiefe** (Kanten-Typen) | fast leer | **höchster Hebel** |
| 3 | **Fachwissen** (tiefe Domäne) | leer (Punkt ③) | höchster Nutzen, braucht Wahl |
| 4 | **Persönliches** (über dich) | wächst durchs Reden | wächst von selbst |
| 5 | **Selbst/Erfahrung** (Betrieb) | fließt | fließt |

**Der Schlüssel bei #2:** die Quelle ist **schon da**. Wikidata ist ein
sprachneutraler Konzept-Graph mit *hunderten* Eigenschaften — GENUS erntet Wikidata heute
(`deploy/observe_konzept.sh`), aber **nur P279** (subclass_of → `is_a`). Dieselbe Quelle,
dieselbe Provenienz-Disziplin, kein neues Vertrauens-Risiko — nur mehr Properties ernten:

- P361 *part of* → `part_of` · P527 *has part(s)* → `has_part`
- P366 *has use* → `used_for` · P186 *made from material* → `made_of`
- P276 *location* → `located_in` · P1552 *has quality* → `hat_eigenschaft`

Jede wird eine gewöhnliche bequellte Kante. Der Suchraum ist bekannt (die Property-Liste
ist Daten), der Weg ist erprobt (is_a kam genau so). **Tiefe fast zum Nulltarif.**

**#3 (Fachwissen)** ist der höchste Nutzen für „GENUS als Helfer", braucht aber zwei
Dinge, die #2 nicht braucht: **deine Domänen-Wahl** und eine **strukturierte Quelle**
dafür. Deshalb kommt #2 zuerst (kann sofort, ohne Entscheidung), #3 danach (bewusst).

---

## 4 · Wie neues Material landet (die Pipeline, wiederverwendet)

Kein Neubau — dieselbe Form wie beim Wort-Material:

```
Membran (deploy/observe_*.sh)  →  destilliert zu bequellten Tripeln
   →  Event im Ledger (Struktur, nie Rohtext)  →  Projektion (Graph)
   →  der Selbst-Check greift automatisch
```

Für **Tiefe (#2):** `observe_konzept.sh` um eine gewählte Property-Liste erweitern; jede
Property → ein Prädikat, jede Aussage → eine bequellte Kante. Der **Graph-Selbst-Check
skaliert mit**: mehr Kanten-Typen = mehr Widerspruchs-Fläche, und die vorhandene Maschine
(Widerspruch → Surprise → Inquiry → Lehrer-Loop) macht daraus **mehr Selbst-Befragung** —
ein Merkmal, kein Fehler.

Für **Fachwissen (#3):** eine kuratierte, strukturierte Quelle (Domänen-Ontologie oder
geprüfter Datensatz), durch die Membran mit **kalibriertem Quellen-Vertrauen**.

---

## 5 · Warum es zählt — Material ist stromaufwärts von allem

Material ist die Substanz, aus der jede spätere Fähigkeit schöpft:

- Die **Vertiefung** (das gerade gebaute „ausführlich") komponiert aus dem, was im Graphen
  liegt — **automatisch**. Heute zieht sie Geschwister + Leiter (die is_a-Kanten). Mit
  `part_of`/`used_for`/`located_in` würde dieselbe Funktion, **ohne eine Zeile mehr Code**,
  sagen können *was ein Hund hat, wofür er da ist, wo er lebt*. Tiefe im Graph = Tiefe in
  der Antwort, geschenkt.
- Der **Deuter** erdet gegen den Graphen — je reicher, desto seltener „das weiß ich nicht".
- Die **Stimme** spricht nur, was verifiziert ist — mehr Material, mehr zu sprechen.

Und der Bezug zu deinem „Feintuning kommt eh noch": Feintuning (Ausdruck, Ton, wann etwas
sagen) **zahlt sich nur aus, wenn es reiches Material zu formulieren gibt.** Erst die
Substanz, dann ihr Schliff — dein Instinkt, bestätigt.

---

## 6 · Leitplanken (was NICHT passieren darf)

- **Nie ein Korpus zum Nacherzählen.** Alles betritt GENUS als bequellte Relation, sonst
  gar nicht. Ein Modell darf Material *finden helfen*, nie *sein*.
- **Quellen-Vertrauen kalibriert**, nicht binär: eine neue, laute Quelle wird leicht
  gehalten und über Widersprüche selbst nachjustiert — nicht verbannt, nicht blind geglaubt.
- **Ledger-Wachstum messen — jetzt dringend.** Der Ledger ist heute 227 MB auf der
  SD-Karte (der nie gemessene Punkt). Ein großer Tiefen-Ingest vervielfacht die Kanten;
  das muss **vorher** gemessen werden, nicht hinterher entdeckt.
- **Die Domänen-Wahl ist deine** (siehe §8) — kein Fachwissen ohne deine Richtung.

---

## 7 · Der phasenweise Plan (die Material-Etappen)

> **WENDE (2026-07-05, siehe Kopfnote):** Diese Etappen laufen nicht mehr selbständig los.
> Regel: **erst die Operation wählen, dann ihr Material holen.** M1 wird ausgelöst, wenn
> eine Schließ-Operation die Kanten braucht (z. B. Teil-Ganzes-Inferenz oder die
> Subsumtion der ersten Denkweise) — nicht vorher. M2 bleibt davon unberührt fällig.

- **M1 — Relationale Tiefe aus Wikidata-Properties. GESTARTET (2026-07-05).** Der
  Konzept-Ernter (`deploy/observe_konzept.sh`) zieht jetzt neben P279→is_a auch die
  DYNAMISCHE Schicht: `part_of`/`has_part` (P361/P527), `made_of` (P186), `used_for` (P366),
  `causes`/`caused_by` (P1542/P828) — als bequellte Kanten, mit einem Sammel-Call für die
  Ziel-Labels (sonst kryptisch). Die Vertiefung nennt sie im „ausführlich"-Umfang
  („besteht aus", „wird verwendet für", „verursacht"); `inference.py` behandelt `part_of`
  schon als transitiv, die Deduktion konsumiert also die Teil-Ganzes-Kanten sofort. Ausgelöst
  durch zwei unabhängig konvergierende Analysen (Material-Wende + Methoden-Landkarte:
  „fast alle Denkweisen hungern nach genau diesem Material").
- **M2 — Ledger-Wachstum messen** (vor jedem großen Ingest). Der nie gemessene Punkt,
  jetzt fällig.
- **M3 — Fachwissen einer gewählten Domäne.** Braucht deine Domänen-Wahl + eine
  strukturierte Quelle. Höchster Helfer-Nutzen.
- **M4 — nichts zu bauen:** Vertiefung, Deuter, companion konsumieren den reicheren
  Graphen von selbst.
- **Querschnitt:** der Selbst-Check skaliert mit; Quellen-Vertrauen bleibt kalibriert.

---

## 8 · Die eine Entscheidung, die deine ist

M1 und M2 brauchen **keine** Entscheidung — ich kann dort anfangen, sobald du den Entwurf
gutheißt. Die eine offene Wahl ist **die Domäne für M3**: Wo soll GENUS *tief* werden?

- **Dein Fach / deine Arbeit** — GENUS wird dort zum echten Helfer.
- **Ein Interessengebiet / Hobby** — reichhaltige, freudige Domäne.
- **Der Abitur-Korpus als Test-Domäne** — misst Tiefe an held-out Aufgaben (das
  umgewidmete Thermometer), ohne Goodhart, weil es nicht das Ziel ist, sondern der Prüfstein.
- **Bewusst später** — erst M1/M2 leben lassen, dann aus dem Gefühl entscheiden.

*Das ist der Entwurf. Kein Code ist gebaut — der nächste Schritt ist deine Reaktion.*
