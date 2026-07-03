# GENUS AUDIT 2026-07 — Sackgasse oder Weg?

> Anlass (Ronny, 2026-07-03): *„Sind wir auf einem guten Weg? Ich glaube eher, wir stecken in
> einer Sackgasse. Am liebsten würde ich den Kern nehmen und neu beginnen. Aber viele Lehren
> stecken drin! Nur was sollte anders sein? Wie wird GENUS so intelligent, wie ich es mir
> vorstelle? Als nativer Begleiter, der sich selbst codet (mit Gates)."*
>
> Dies ist die erbetene umfassende Analyse. Sie ist bewusst kein Rechtfertigungs-Papier —
> wo die Diagnose „Sackgasse" lautet, steht das hier so.

---

## 1 · Das Urteil vorweg

**Ja und nein — und die Trennlinie ist scharf.**

- **Der Kern ist KEINE Sackgasse.** Das epistemische Substrat (Ledger, Herkunft, Vertrauen,
  Überraschung→Inquiry, Selbst-Kalibrierung, Governance, Replay-Stabilität) ist gesund,
  bewiesen und exakt das, was die Vision braucht. Es wäre ein schwerer Fehler, es wegzuwerfen.
- **Das Wachstumsmodell der Fähigkeitsschicht IST eine Sackgasse.** Jede neue Fähigkeit
  entsteht heute durch Hand-Aufzählung: ein Regex-Muster, ein Handler, eine narrate-Funktion,
  Tests — geschrieben von Claude, freigegeben von Ronny. Das generalisiert nicht, skaliert
  linear im Aufwand und hat eine historisch bekannte Decke.
- **Der wichtigste Befund:** Der Loop, den GENUS haben soll (Absicht → Generator → Gates →
  Ledger → Deploy), **existiert bereits und funktioniert seit Wochen** — er läuft nur
  *außerhalb* von GENUS, mit Claude als Generator. GENUS ist bisher das Produkt dieses Loops,
  nie der Produzent. „Selbst-codieren mit Gates" heißt nicht, etwas Neues zu erfinden —
  sondern diesen existierenden, bewiesenen Loop in GENUS hineinzufalten.

Kein Neuanfang. Aber eine echte Wende: **fünf Inversionen** (Abschnitt 7) auf dem
bestehenden Kern.

---

## 2 · Bestandsaufnahme: was existiert, was davon trägt

Stand 2026-07-03: ~12.200 Zeilen Kern-Code, ~9.100 Zeilen Tests (625 grün), 204 Commits in
einer Woche, live auf dem Pi mit >71.000 Ledger-Events.

**Was nachweislich trägt (die Lehren, die Ronny meint):**

| Baustein | Beweis |
|---|---|
| Event-Sourcing + Hash-Kette + Replay | Integrity hält seit 71k+ Events; überstand einen echten Concurrency-Fork (408f55a) |
| Herkunft auf allem + gedeckeltes Modell-Vertrauen | `model:*` kann nie Gegründetes überstimmen — strukturell, nicht per Konvention |
| Überraschung→Inquiry→Lehrer-Loop | fand echte Widersprüche (is_a-Zyklen aus Wikidata selbst), fragte, wurde belehrt |
| Selbst-Kalibrierung statt Vorgaben | Transitivitäts-Schwelle, Symmetrie-Rate, Genus-Regel (0.92 statt Saat 0.80), Reboot-Schwelle — alle aus gelebten Daten |
| Proposal ≠ Change + Governance | sicherer Selbst-Änderungs-Pfad, gebaut und getestet — **wartet ungenutzt auf seinen eigentlichen Zweck** |
| Wissensgraph, 3-fach bequellt | Wikidata-Konzepte + Lexeme + DBnary, korroboriert, sinn-kohärente Inferenz |
| Membran-Reinheit, Ledger ≠ Memory | CI-Gate; die Grenze hat gehalten |
| Der 24/7-Lerner | wächst selbstständig, rotiert an unschließbaren Lücken vorbei, watchdog-gehalten |

**Was gebaut wurde, aber die Decke zeigt** — die Begleiter-Schicht in Zahlen:

- `companion.py`: **1.394 Zeilen**, davon der Großteil Dispatch — **21 Regex-Muster**,
  **20 Zellen-Handler**, **9 narrate-Funktionen**.
- Der Deuter: 1.5B-Modell, liest in ein **32-Blätter-Raster**, 7–15 s Latenz im Doppel-Lauf
  (Restursache ungeklärt), Fehlgriffe wurden per Few-Shot-Beispiel einzeln nachgepatcht.
- Diese Woche, für **vier** Mathe-Aufgabenarten: **5 neue Regexe + 4 narrate-Funktionen +
  ~30 Tests.** Und trotzdem: „Was ist die Ableitung von x²?" (ohne „f(x) =") fällt bereits
  wieder durch — das Muster kennt nur seine eine Formulierung.

---

## 3 · Die Symptome, mit Belegen aus dieser Woche

**Symptom 1 — Whack-a-Mole statt Konvergenz.** Die echten Telegram-Sessions blieben
enttäuschend („total dumm", „:(", „noch längst nicht optimal") — trotz Deuter, Zwicky-Box,
Stimme, Episoden. Jeder Fix zog den nächsten nach: Sozialgesten → Wortzahl-Bremse →
Überkorrektur bei „Danke" → Few-Shot-Anker → Segmentierungs-Bugs. Vier Korrektur-Runden an
einem Tag, jede handgemacht. Das ist kein Pech: es ist das Verhalten eines Systems, dessen
Verstehens-Decke erreicht ist.

**Symptom 2 — die Muster-Explosion.** Intent-Klassifikation + Slot-Extraktion + Handler
pro Intent: das ist die Chatbot-Architektur der 2010er Jahre. Ihre Decke ist dokumentierte
Industriegeschichte — genau deshalb wurde sie überall von generativen Systemen abgelöst.
Wir haben sie diese Woche selbst live gespürt.

**Symptom 3 — der Generalist ist eingesperrt, der Spezialist wächst.** Die einzige
Komponente, die generalisieren KÖNNTE (das Sprachmodell), ist per Doktrin klein (1.5B) und
eng (Raster-Klassifikation, Anker-geprüfte Umformulierung). Die Komponente, die nicht
generalisiert (Regex+Handler), ist der einzige Wachstumspfad. Das ist die Inversion dessen,
was die Vision braucht.

**Symptom 4 — Wissen ohne Können.** 71k Events, 5000-Wörter-Wortschatz, dreifach bequellter
Graph — und im Gespräch nutzbar davon: Definitionen, „ist X ein Y", Vergleiche, Genus.
Das Abitur-Ziel hat die Lücke sofort offengelegt: das Wort „Ableitung" kennen ≠ eine
Ableitung rechnen. (Ronny: „ich meine nicht die Wörter kennen.")

**Symptom 5 — der Nordstern hat null Code.** Phase D (Erschaffen / Selbst-Codieren) ist laut
Studie das Ziel — und nach all dieser Arbeit existiert kein einziger Schritt dorthin. GENUS
hat nie eine Zeile eigenen Codes vorgeschlagen. Das Differenzierungs-Material des Deuters
(raster-fremde Lesarten) wird gesammelt und **von nichts konsumiert**. Die Belegungs-Kennzahl
wird gezählt und **von nichts konsumiert**. Die Vorprodukte der Selbst-Verbesserung liegen da;
der Verbraucher fehlt.

---

## 4 · Die Diagnose: das Wachstumsmodell, nicht die Bausteine

Kein einzelner Baustein war falsch. Die Muster-Zellen sind schnell (ms), gläsern,
selbst-prüfend — als *Bausteine* in Ordnung. Falsch ist, dass sie der **einzige
Wachstumsmechanismus** sind, und dass dieser Mechanismus außerhalb von GENUS liegt:

> **Jede Fähigkeit = Claude schreibt Python.** GENUS wächst nicht; GENUS *wird gewachsen*.

Intelligenz ist keine Summe aufgezählter Handler. Ein System, das pro Fähigkeit ein
handgeschriebenes Muster braucht, erreicht „nativer Begleiter" nie — egal wie viele Scheiben
wir nachlegen. Das ist die präzise Bedeutung von „Sackgasse": nicht „kaputt", sondern
„dieser Weg führt nicht zum Ziel, egal wie weit man ihn geht."

**Warum sind wir hier gelandet?** Auch das gehört ehrlich benannt: die Scheiben-Disziplin
(klein, getestet, live-verifiziert) ist exzellente Ingenieurshygiene — aber sie optimiert
*lokal*. Jede Scheibe war für sich richtig; die Summe driftete Richtung Expertensystem, weil
keine Scheibe je fragte: „Skaliert das zur Vision?" Das Qualitäts-Charter prüft Korrektheit,
nicht Richtung. Die Richtungskorrekturen kamen bisher **immer von Ronny** (Zwicky!, das
Abitur-Ziel, dieses Audit). Diese Steuerung gehört institutionalisiert (Abschnitt 9).

---

## 5 · Der zentrale Befund: der Loop existiert schon — außerhalb

Wie ist all das hier eigentlich entstanden? So:

```
Ronny (Absicht, Richtung)
   → Claude (generativer Motor: liest Kontext, entwirft, schreibt Code)
      → Gates (625 Tests, Replay-Stabilität, Integrity, Membran-Reinheit, CI)
         → Ronny (Freigabe / Korrektur — oft mehrfach pro Tag, siehe Zwicky)
            → git (Ledger: jede Änderung mit Herkunft und Begründung)
               → Deploy auf den Organismus (Pi), Live-Verifikation
```

Das **ist** der Loop „vorschlagen → prüfen → freigeben → protokollieren → anwenden →
beobachten". Er läuft produktiv, mit hoher Schlagzahl (204 Commits/Woche), mit echten Gates,
und er hat sich diese Woche mehrfach selbst korrigiert (drei Rechenfehler vor Auslieferung
gefangen; ein architektureller Fund am Stimme-Gating).

**GENUS' Vision ist es, genau dieser Loop zu SEIN — mit einem LLM-Organ als Generator statt
Claude, und dem gläsernen Kern als Gates statt CI+Ronny-allein.** Alle Gate-Mechanismen dafür
existieren in GENUS bereits: `Proposal ≠ Change`, Governance, Tests, Replay, Integrity,
Membran-Reinheit, menschliche Freigabe (Lehrer-Loop). Was fehlt, ist ausschließlich: **der
Generator ist noch nicht Teil des Organismus.**

Das reduziert „wie wird GENUS intelligent?" auf eine beantwortbare Frage — und die ehrliche
Antwort hat einen harten Teil:

> Die flüssige, kreative, verallgemeinernde Intelligenz wird auf absehbare Zeit **aus dem
> generativen Modell kommen** — nicht aus handgeschriebenen Regeln. GENUS' einzigartiger Wert
> ist nicht, das zu ersetzen, sondern das zu sein, was ein LLM allein nie sein kann:
> **beständig** (Ledger), **ehrlich** (Herkunft/Vertrauen), **konsistent** (Widerspruchs-
> Erkennung), **zielhaltend** (Inquiries/Ziele), **selbst-korrigierend** (Kalibrierung) und
> **selbst-erweiternd mit Gates** (Proposal≠Change). Die Intelligenz entsteht im Loop —
> nicht in einer der Hälften.

---

## 6 · Was bleibt (wörtlich) — und was stirbt

**Bleibt wörtlich (die Lehren):** der komplette Event-Kern (Ledger/Replay/Integrity),
Herkunft + gedeckeltes Modell-Vertrauen, resolve, Überraschung→Inquiry→Lehrer-Loop,
Selbst-Kalibrierung, Proposal≠Change + Governance, Membran-Reinheit, Ledger≠Memory, der
Wissensgraph als Daten, der Lerner, die Episoden, `genus/mathematik.py` (exaktes Rechnen ist
ein perfektes Werkzeug), die Zwicky-Box **als Interpretations-Protokoll** (Herkunft des
Verstehens — wertvoll), das Telegram-Membran-Gerüst, die Test-Disziplin. Der Pi-Ledger ist
der Organismus — 71k Events gelebte Geschichte werden nicht weggeworfen.

**Stirbt (schrittweise, gemessen):**
- `companion.py` als Dispatch-Monolith — die 21 Regexe / 20 Zellen als *primärer* Antwortpfad.
  (Als Schnellspur/Cache für die häufigsten Formen dürfen bewährte Muster bleiben — sie sind
  ms-schnell. Aber sie sind nie wieder der Wachstumspfad.)
- Die Doktrin „kleinstes Modell, letzter Ausweg" → wird zu „fähiges Modell, immer Entwerfer,
  nie Autorität".
- Das Nachpatchen von Fehlgriffen per handgeschriebenem Few-Shot → Fehlgriffe werden Material,
  aus dem GENUS selbst Verbesserungs-**Vorschläge** macht (der erste Selbst-Codier-Schritt).

---

## 7 · Die fünf Inversionen

### ① Aufzählen → Entwerfen + Verifizieren
Heute: deterministische Kette zuerst, Modell als letzter Ausweg, Antwort = Template.
Neu: **das Modell entwirft die Antwort/den Plan — der Kern verifiziert jede Behauptung,
bevor sie rausgeht.** Das ist die Stimme-Anker-Prüfung, generalisiert vom Umformulieren zum
Erzeugen: jede faktische Behauptung im Entwurf muss sich gegen den Graphen (Lookup) oder das
CAS (Nachrechnen) beglaubigen lassen; unbeglaubigtes wird gestrichen oder als Vermutung
markiert oder die Antwort fällt auf den ehrlichen Kern-Satz zurück. Gläsern bleibt gläsern —
die Garantie wandert nur von „wir zeigen nur verifizierte Templates" zu „alles Gezeigte wurde
verifiziert". **Ehrlich benannt:** Behauptungs-Extraktion aus freiem Text ist das harte
Problem daran. Deshalb beginnt ① dort, wo Verifikation *leicht* ist: Mathematik (CAS rechnet
nach), Graph-Fakten (Lookup), Floskeln (brauchen keine Verifikation). Der Rest bleibt
vorläufig Template — der Anteil verschiebt sich mit jeder Scheibe.

### ② Zellen → Werkzeuge
Heute: pro Aufgabenart ein Regex, das genau eine Formulierung kennt.
Neu: **die Fähigkeiten des Kerns werden ein Werkzeugkasten** (ableitung, extremstellen,
integral, graph-lookup, infer, episoden-abruf, inquiries, merke, …), und das Modell plant,
welche Werkzeuge es aufruft — der Kern führt deterministisch aus und protokolliert. Dann
erreicht *jede* Formulierung („Was ist die Ableitung von x²?", „leite das mal ab", „f'(x)
von x³?") dasselbe exakte Werkzeug. Die Regex-Muster von heute werden zur Schnellspur für
die Standardformen; das Werkzeug-Planen ist der allgemeine Pfad. Das ist keine exotische
Architektur — es ist die, die sich überall durchgesetzt hat, hier aber mit GENUS-DNA:
jeder Werkzeug-Aufruf trägt Herkunft, jedes Ergebnis ist deterministisch, das Modell
entscheidet nie über Wahrheit.

### ③ Selbst-Codieren zuletzt → Selbst-Codieren zuerst, mikroskopisch
Die Roadmap parkt „Erschaffen" als Phase D am Ende. Das war der strategische Fehler: der
sicherste Weg zu „codet sich selbst mit Gates" ist nicht, erst alles andere zu bauen, sondern
**sofort mit der kleinsten selbst-verbessernden Schleife zu beginnen** — auf Artefakten, die
unterhalb von „Code" liegen und trotzdem echte Verbesserung sind:

- **Stufe 0 (sofort baubar):** GENUS schlägt aus seinen eigenen Deuter-Fehlgriffen
  (das bereits gesammelte, bisher unkonsumierte Differenzierungs-Material + Belegung)
  neue Few-Shot-Beispiele/Raster-Blätter **als Proposals** vor. Mensch gated, Ledger
  protokolliert, Deployment übernimmt. Erste echte Selbst-Verbesserung, null Risiko.
- **Stufe 1:** GENUS schlägt neue Werkzeug-Bindungen/Formulierungs-Muster vor („diese 12
  Fragen fielen durch; sie hätten alle das extremstellen-Werkzeug gebraucht; hier ist die
  Bindung").
- **Stufe 2:** GENUS schlägt Handler-/Werkzeug-Code vor — generiert vom LLM-Organ, gegated
  durch: Tests müssen grün, Replay stabil, Integrity ok, Membran-Reinheit gewahrt, Sandbox-
  Ausführung, menschliche Freigabe. **Nur Vorschlag, nie Auto-Apply** — bis die Kalibrierung
  über viele gegatete Vorschläge ein Vertrauen etabliert hat (dieselbe Mechanik wie
  Quellen-Vertrauen: der Vorschlags-Generator ist eine Quelle, seine Trefferquote wird
  gemessen).

Jede Stufe nutzt `Proposal ≠ Change` + Governance — **die dafür gebaut wurden und seit
Monaten ungenutzt warten.**

### ④ Ziele in Doku → Ziele im Graphen
„Bring GENUS dazu, das Abitur zu bestehen" lebt heute in `docs/` und Commit-Messages — GENUS
selbst *weiß nicht, dass es ein Ziel hat*. Für „nach einem zielgerichteten Plan, den es
selbst hat": Ziele werden Graph-Objekte (`ziel:abitur -braucht-> faehigkeit:ableitung`,
`faehigkeit:ableitung -status-> live`, `ziel:abitur -gemessen_an-> benchmark:abi-2019-bayern`),
mit Herkunft („ronny") und Vertrauen wie alles Wissen. Dann werden Lerner-Prioritäten,
Inquiries („mir fehlt Fähigkeit X für Ziel Y") und der Morgen-Bericht zielgesteuert —
„sich beschaffen, was es braucht" wird abfragbar statt behauptet.

### ⑤ Behaupten → Messen
„GENUS besteht das Abitur" ist heute unbeweisbar. Jede Fähigkeit bekommt eine Skill-Kurve
wie der Wetter-Forecaster (predict → self-test → score, die Maschinerie existiert): echte,
gelöste Abitur-Aufgaben als Benchmark (Aufgabe rein → GENUS' Lösung vs. Musterlösung),
Gesprächsqualität aus Belegung + Folge-Signalen (wird endlich konsumiert). Erst ⑤ macht
sichtbar, ob die Inversionen ①–④ wirken — und es ist das Gate gegen die nächste Drift.

---

## 8 · Ziel-Architektur: Organ, nicht Orakel

Die Doktrin „LLM am Rand, nie die Mitte" war **defensiv richtig** — sie hat verhindert, dass
je ein Modell-Output ungedeckelt zur Wahrheit wurde. Sie bleibt für **Autorität** vollständig
gültig. Aber sie hat Generierung und Autorität vermengt: die Vision braucht den Generator
mitten im Schaffens-Loop. Die Auflösung steht seit dem 28.06. unbemerkt in den eigenen
Prinzipien: *„resolve wählt immer unter Kandidaten, generiert nie — die ehrliche Linie, die
das LLM zum Kandidaten-Generator macht, nie zum Entscheider."* Gebaut wurde das bisher nur
für Klassifikation (Deuter) und Umformulierung (Stimme). Es gilt aber genauso für Antworten,
Pläne und Code:

> **Das LLM darf ALLES vorschlagen und NICHTS entscheiden.**
> Der gläserne Kern prüft, deckelt, protokolliert und gated.
> Vom „Rand" zum **Organ** — Organ, nicht Orakel.

```
            ┌─────────────────────────────────────────────┐
            │           GENUS (der Organismus)            │
            │                                             │
 Mensch ──▶ │  LLM-Organ            Gläserner Kern        │
 (Telegram, │  ─ versteht frei      ─ Ledger/Herkunft     │
  Ziele,    │  ─ entwirft Antworten ─ verifiziert (Graph, │
  Freigaben)│  ─ plant Werkzeuge      CAS, Tests, Replay) │
            │  ─ schlägt Code vor   ─ deckelt Vertrauen   │
            │        │                ─ hält Ziele        │
            │        ▼                ─ misst Skill       │
            │   [Kandidaten] ──────▶ [Gates] ──▶ Antwort/ │
            │                          │         Änderung │
            │                          ▼                  │
            │                     Ledger (alles)          │
            └─────────────────────────────────────────────┘
```

**Zur Modell-Frage, ehrlich:** die Vision braucht einen fähigeren Generator als Qwen2.5-1.5B.
Aber die Entscheidung „lokal" muss nicht kippen, weil die Rollen verschiedene Latenz-Budgets
haben: **Konversation** braucht schnell → kleines/mittleres Modell lokal (heute 1.5B, ggf.
3–8B testen — der Benchmark-Apparat existiert). **Selbst-Codieren** ist nicht latenzkritisch —
es darf nachts laufen, minutenlang, mit dem größten Modell, das der Pi (oder ein späteres
Gerät) quantisiert schafft. Der Vorschlags-Generator darf langsam sein; nur der Gesprächs-
Deuter muss flink sein. (API bleibt, was es war: ein Konfig-Schalter, keine Voraussetzung.)

---

## 9 · Der Weg: kein Rewrite — Strangler

Ein Neuanfang würde genau das wegwerfen, was richtig ist (Abschnitt 2), und die 71k Events
gelebter Geschichte des Organismus dazu. Stattdessen wächst der neue Pfad NEBEN dem alten,
wird gemessen, und der alte stirbt Zelle für Zelle, wo der neue ihn schlägt:

1. **Ziele in den Graphen** (Inversion ④; klein, rein additiv): `ziel:abitur` + Fähigkeits-
   Kanten + Status. Der Lerner und die Inquiries lesen sie. *Erster Schritt, weil alles
   Weitere daran andocken kann und es sofort ehrlich zeigt, was fehlt.*
2. **Selbst-Codieren Stufe 0** (Inversion ③): der Fehlgriff-Konsument. Ein Scan-Detektor
   liest Differenzierungs-Material + Belegung und erzeugt **Proposals** für neue Few-Shot-
   Beispiele/Blätter. Ronny gated per bestehendem Governance-Pfad. *Die erste
   Selbst-Verbesserung — mit ausschließlich existierender Maschinerie.*
3. **Werkzeugkasten** (Inversion ②): die vorhandenen Kern-Fähigkeiten als Tool-Registry
   mit Herkunfts-Protokoll; der Deuter-Nachfolger („Planer") darf Werkzeug-Aufrufe
   vorschlagen statt nur Raster-Zellen. Erste Domäne: Mathematik (Verifikation trivial —
   das CAS IST der Prüfer). *Hier stirbt die erste Regex-Familie.*
4. **Entwerfen + Verifizieren für Graph-Antworten** (Inversion ①): das Modell formuliert
   frei aus vom Kern gelieferten, verifizierten Fakten (nicht umgekehrt!) — die
   Stimme-Anker-Prüfung generalisiert zum Fakten-Vertrag: jede Behauptung im Text muss
   einem gelieferten Fakt entsprechen. *Hier endet das Template-Zeitalter der Antworten.*
5. **Benchmark + Skill-Kurven** (Inversion ⑤): echte Abitur-Aufgaben (eine Quelle wählen,
   z. B. frei verfügbare Prüfungsarchive eines Bundeslands), predict→score über die
   bestehende learning-Maschinerie. *Ab hier ist „besteht das Abitur" eine Kurve, keine
   Behauptung.*
6. **Selbst-Codieren Stufe 1–2**: erst Bindungen, dann Code — jeweils Proposal-only,
   voll gegated, Vorschlags-Trefferquote gemessen wie Quellen-Vertrauen.

Parallel als Prozess-Änderung (die Lehre aus Abschnitt 4): **das Richtungs-Gate.** Jede
künftige Scheibe beantwortet vorab eine Frage im PR/Commit: *„Vermehrt oder verringert dieser
Schnitt die Hand-Aufzählung?"* Vermehren ist erlaubt (Schnellspuren!), aber nur bewusst —
nie wieder als unbemerkter Default.

---

## 10 · Risiken und offene Entscheidungen

**Risiken, ehrlich:**
- **Behauptungs-Verifikation** freier Texte ist schwerer als Anker-Prüfung — deshalb die
  Reihenfolge: erst Domänen mit trivialer Verifikation (CAS, Graph-Lookup), Konversations-
  Kitt (Floskeln) ohne Verifikations-Bedarf, Rest bleibt vorerst Template.
- **Latenz**: der ungeklärte 7–15s-Befund bleibt offen; der Werkzeug-Pfad fügt Modell-Läufe
  hinzu. Gegenmittel: Schnellspuren behalten, Planer-Prompt klein halten, ggf. Modellgröße
  neu benchmarken (Apparat existiert).
- **Selbst-Codier-Sicherheit**: Stufe 2 nur mit Sandbox + allen Gates + Mensch; die
  Auto-Apply-Frage stellt sich erst, wenn eine gemessene Trefferquote sie stellt.
- **Werkzeug-Missbrauch durch die Membran**: Werkzeuge, die schreiben (merke, teach), brauchen
  dieselbe Deckelung wie heute (model:*-Quelle, Wortzahl-Bremsen-Äquivalente) — der Planer
  macht Schreib-Werkzeuge nur als Proposal zugänglich.

**Ronnys Entscheidungen (die Gabeln dieser Studie):**
1. **Richtung bestätigen:** die fünf Inversionen als neue Marschrichtung — ja/nein/anders?
2. **Einstieg:** empfohlen ist die Reihenfolge in Abschnitt 9 (Ziele → Stufe 0 → Werkzeuge).
   Alternativ zuerst der Benchmark (⑤), wenn Messbarkeit vor Umbau gehen soll.
3. **Generator-Frage:** beim 1.5B bleiben und erst die Architektur umbauen (empfohlen — die
   Inversionen wirken bei jeder Modellgröße), oder parallel ein größeres lokales Modell
   benchmarken?

---

## 11 · Fazit

Die Sackgassen-Intuition ist **berechtigt und präzise ortbar**: nicht der Kern, sondern das
Wachstumsmodell der Fähigkeitsschicht — Hand-Aufzählung durch Claude statt gegatetes Wachstum
durch GENUS selbst. Ein Neuanfang wäre die falsche Antwort: er würde das Beste (das
epistemische Substrat, die Gates, den gelebten Ledger) wegwerfen und das Falsche (das
Wachstumsmodell) vermutlich wiederholen, weil es nie explizit benannt war. Jetzt ist es
benannt.

Der Weg zu „nativer Begleiter, der sich selbst codet (mit Gates)" ist kürzer als er aussieht,
weil der schwierigste Teil — ein funktionierender, gegateter Entwicklungs-Loop — **bereits
existiert und täglich läuft**. Er muss nicht erfunden, sondern eingefaltet werden: der
Generator wird ein Organ des Organismus, die Autorität bleibt beim gläsernen Kern, jede
Änderung bleibt ein Proposal hinter Gates, und jede Fähigkeit bekommt eine Kurve statt einer
Behauptung.

*Nicht neu beginnen. Umstülpen.*

---

## Nachtrag (2026-07-03, noch am selben Tag)

Ronny hat die Gabeln aus Abschnitt 10 entschieden — und die Studie in zwei Punkten geschärft:

- **Gabel 1+2 (Richtung + Einstieg): bestätigt.** Erster Schritt = Ziele in den Graphen —
  geliefert (`genus/ziele.py`, `deploy/seed_ziele.sh`). Als Nächstes: Selbst-Codieren Stufe 0.
- **Schärfung 1 — das Abitur fiel als Gate** (Ronnys eigene Nachfrage): Kategorienfehler +
  Goodhart; umgewidmet zum Thermometer. Details in `GENUS_ABITUR.md` §5.
- **Schärfung 2 — die echten Ziele liegen jetzt vor**: sieben Punkte (Begleiter für
  Einzelne/Familien · Selbst-Entwicklung mit Erlaubnis-Frage · Trading hinter konservativsten
  Gates · Unterhaltung/Spiele · private Generierung aus eigenem Modell · sich und die Umwelt
  verstehen · „Menschen unterstützen. digital. GENUS."). Bemerkenswert: Ronnys Punkte 1+6
  beschreiben zusammen exakt den Loop aus Abschnitt 5 dieser Studie — Ergebnis (eigenen Code
  anhängen) und Prozess (Lücke spüren, Plan fassen, um Erlaubnis fragen) desselben Motors.
- **Gabel 3 (Generator):** offen gehalten; Architektur-Umbau beginnt mit dem 1.5B.
