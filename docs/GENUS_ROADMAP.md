# GENUS ROADMAP

> Vom heutigen Stand (v1.1) bis zum Zielsystem der Architektur-Karte.
> Ein **Bau-Instrument**, keine Wunschliste.

---

## Wie diese Roadmap benutzt wird

**Die eine Regel:** Es wird immer nur der **nächste offene Schritt** gebaut.
Nie zwei gleichzeitig, nie einer übersprungen. Codex bekommt genau einen
Eintrag als Spec — erst wenn dessen *Definition of Done* vollständig grün ist,
wird der nächste geöffnet.

**Das Gate vor jedem Schritt — die Wachstumsregel.** Jeder Schritt muss vor
dem Bauen fünf Fragen mit Ja beantworten:

1. Welches Event hält den Input oder die Transition fest?
2. Ist der Zustand aus `event_log` rebuildbar?
3. Lässt Replay `event_log` unverändert?
4. Wird Confidence berechnet statt gespeichert?
5. Vermeidet der Schritt LLM-, Web-, Worker- und HTTP-Abhängigkeiten —
   sofern nicht eine Version es ausdrücklich erlaubt?

Frage 5 wird erst in der **Model Era** (ab v2.0) bewusst gelockert.

---

## Die zwei Prinzipien, die die Reihenfolge bestimmen

**1. Material vor Maschinerie.** Kein Verarbeitungs-Core, bevor es Input gibt,
der ihn rechtfertigt. Sonst baust du leere Cores — korrekt und getestet, aber
ohne Inhalt.

**2. Beobachtbarkeit neben Maschinerie.** Baue nichts, das du nicht sofort
inspizieren kannst. Deshalb kommt die Query-Schicht früh — sie ist die
Inspektionslampe für alles, was danach kommt.

Daraus ergeben sich **zwei Achsen**: Material wird *breiter*
(Habitat → Arbeit → Sprache), Maschinerie wird *tiefer*
(Lifecycle → Experience → State → Governance → Maturation). Maschinerie wird
immer auf dem *einfachsten* Material zuerst bewiesen.

---

## Wo wir stehen (v1.1)

**Grün:** Observation · Evidence · Belief · Ledger · CPU/Memory-Sensor ·
Disk/Activity/Temperature-Sensor · CLI · Query · Replay · Integrity ·
append-only Trigger · Proposal Review · Inquiry Resolve · Experience Core ·
State Core · Governance v1 · Maturation v1 · CI · Ledger Audit · Ledger Sealing
**Gelb:** externer Anchor fehlt
**Rot:** alles Übrige der Karte

---

# Phase 1 — Deterministischer Kern (kein LLM)

---

## v0.6 — Habitat vervollständigen · *mehr Material*

**Status:** umgesetzt. CPU, Memory, Disk, Activity und Temperature sind lokale,
offline Sensoren. Activity ist die erste binäre Regel-Art ohne Window. Disk und
Temperature nutzen in v0.6 bewusst noch Threshold/Revision; echter Trend bzw.
echte CPU-Temperatur-Korrelation bleiben spätere Vertiefungen, sobald Query und
Experience sichtbar machen können, was daran gelernt wurde.

**Warum jetzt:** Mit zwei Metriken (CPU, Memory) gibt es kaum Muster zu lernen
und kaum Zustand zu aggregieren. Erst mehr Sensoren machen die spätere
Maschinerie nicht-leer. Material ist die Grundlage von allem Weiteren.

**Hängt ab von:** nichts (Reactor-Pattern existiert)

**Neue Sensoren:**
- `system.disk_percent` — Trend + plötzliche Sprünge (Backups, Downloads)
- `system.activity` — aktiv/idle, der musterreichste Sensor (Tagesrhythmus)
- optional: `system.process_count`, `system.temperature`

**Scope:**
- je Sensor: `read_*` in `sensor.py`, ein `RULES`-Eintrag, ein `observe-*`
  Kommando — kein neuer Architektur-Aufwand
- **Achtung `activity`:** binär/zeitlich, nicht high/normal. Der Wert liegt im
  Muster über Stunden, nicht im Moment. Wahrscheinlich braucht es hier eine
  zweite Regel-Art neben dem Schwellwert-Schema. Das ist gewollt — echtes
  Material, das die Architektur fordert.

**Definition of Done:**
- [ ] mind. 2 neue Sensoren, je eigener Belief-Typ
- [ ] alle deterministisch, Replay-stabil, Integrity grün
- [ ] grep leer (kein LLM/HTTP)
- [ ] Wachstumsregel ✓

---

## v0.7 — Query-Schicht · *GENUS spricht aus seinem Zustand*

**Status:** umgesetzt. `ask`, `explain belief` und `why proposal` lesen aus
Projektionen und Ledger, schreiben keine Events und zeigen Herkunftsketten für
Beliefs und Proposals.

**Warum jetzt:** Sobald Material da ist, baust du die Lampe, mit der du jeden
folgenden Core inspizierst. GENUS beantwortet "was glaubst du, und warum?"
aus Projektionen und Ledger — rein deterministisch, **schreibt nichts**. Das
ist der erste Moment, in dem GENUS sich lebendig anfühlt, lange vor dem LLM.

**Hängt ab von:** Material (v0.6)

**Neue Events:** keine — Query ist read-only

**Scope:**
- `genus ask "<frage>"` → strukturierte Antwort aus aktuellem Zustand
  (anfangs feste Frage-Muster, kein freier Text)
- `genus explain belief <id>` → Belief + stützende/widersprechende Evidence
- `genus why proposal <id>` → die Kette, die zum Proposal führte
- alles aus bestehenden Tabellen, in Sätze gegossen

**Definition of Done:**
- [ ] Query schreibt nachweislich kein Event (read-only)
- [ ] explain/why zeigen vollständige, korrekte Herkunftsketten
- [ ] Antworten stimmen mit Ledger überein
- [ ] Wachstumsregel ✓

---

## v0.8 — Proposal/Inquiry Lifecycle · *erster Governance-Akt*

**Status:** umgesetzt. `proposal_reviewed` und `inquiry_resolved` sind
event-backed, terminal und replay-stabil. Akzeptierte Proposals führen nichts
aus; `Proposal ≠ Change` bleibt als Test bewiesen.

**Warum jetzt:** Mit Query siehst du jetzt, wie sich offene Proposals und
Inquiries stauen — das Schließen wird sichtbar nötig. Der Moment, in dem ein
Mensch ein Proposal als *reviewed* markiert, ist der erste echte
Governance-Akt und bereitet die spätere Governance-Schicht vor.

**Hängt ab von:** nichts Hartes (Query macht den Bedarf sichtbar)

**Neue Events:** `proposal_reviewed`, `inquiry_resolved`

**Scope:**
- `genus proposals review <id> [--accept|--reject]`
- `genus inquiries resolve <id> --answer <text>` (setzt `resolved_at`)
- beide event-backed, beide Zustände reine Projektion, Replay-stabil

**Definition of Done:**
- [ ] beide Events im Contract + Integrity
- [ ] Lebenszyklen ändern sich korrekt über CLI
- [ ] Replay rekonstruiert beide identisch
- [ ] Wachstumsregel ✓

---

## v0.9 — Experience Core · *erstes Lernen*

**Status:** umgesetzt. `experience_recorded` ist im Contract und in Integrity.
`experience_log` ist eine rebuildbare Projektion. Der erste Detector erkennt
kontrastierende `system.activity`-Stunden statt bloßer Cron-Häufungen und
erzeugt pro Scan höchstens einen review-only `ExperienceProposal`.

**Bekannte Schuld:** Experiences haben noch keinen Lebenszyklus. Ein späterer
Schritt muss `experience_confirmed`/`experience_invalidated` oder eine
gleichwertige Relevanz-Mechanik einführen, damit alte Erfahrungen nicht
epistemisch einfrieren.

**Warum jetzt:** Jetzt gibt es Material (Muster sind da) *und* Query (du kannst
sie sehen). Zeitliche Verdichtung über den Ledger: aus "Disk um 14:03 hoch"
wird "Disk füllt sich immer mittwochs". Rein deterministisch, SQL über
Zeitfenster.

**Hängt ab von:** Material (v0.6), Query (v0.7, zum Sichtbarmachen)

**Neue Events:** `experience_recorded`

**Scope:**
- Aggregation über `event_log`: Häufungen nach Tageszeit/Wochentag,
  wiederkehrende Belief-Kombinationen
- `ExperienceRecord` als Projektion, `genus experience show`
- ein wiederkehrendes Muster kann einen Proposal erzeugen

**Definition of Done:**
- [x] `experience_recorded` im Contract + Integrity
- [x] mind. ein Muster-Typ erkannt, Replay-stabil
- [x] über Query inspizierbar
- [x] Wachstumsregel ✓

---

## v0.10 — State Core · *Gesamtzustand aus vielen Beliefs*

**Status:** umgesetzt. `state_changed` ist im Contract und in Integrity.
`state_projection` ist eine rebuildbare Projektion. Der erste StateVector
leitet `system.pressure` aus aktiven Activity- und Ressourcen-Beliefs ab und
ist über `genus state show`, `genus explain state` und Query inspizierbar.
Im Dauerbetrieb wird State bewusst per `genus state refresh` nach den Sensoren
aktualisiert; `observe-all` bleibt reine Beobachtung.

**Warum jetzt:** Mit 4–5 Belief-Typen ist Aggregation endlich nicht-trivial.
Mehrere Beliefs → ein `StateVector` (z.B. `aktiv + CPU hoch + Disk wächst`
→ `pressure=elevated`). Fundament, das Governance im nächsten Schritt braucht.

**Hängt ab von:** Material (v0.6), Belief Core

**Neue Events:** `state_changed`

**Scope:**
- StateVector aus aktiven Beliefs abgeleitet, nicht als Wahrheit gespeichert
- `genus state show`, über Query erklärbar

**Definition of Done:**
- [x] `state_changed` im Contract + Integrity
- [x] State aus Beliefs abgeleitet, Replay-stabil
- [x] Wachstumsregel ✓

---

## v0.11 — Governance v1 · *Policy + Constraint greifen*

**Status:** umgesetzt. Proposal-Reviews laufen durch eine Governance-Schicht.
Kernel-Constraints blockieren ungültige oder nicht-pending Reviews und sind
nicht overridebar. `policy:pressure_guard_v1` blockiert Accept-Reviews bei
`system.pressure=elevated`, außer der Mensch setzt explizit `--override`.
Jede Entscheidung ist event-backed und über `genus governance list` sowie
`genus why decision` inspizierbar.

**Warum jetzt:** Jetzt existiert ein Zustand zum Bewerten und genug
Proposal-Vielfalt zum Regeln. Governance kann zum ersten Mal wirklich
eingreifen statt nur dokumentiert zu sein — der Querschnitt der Karte bekommt
seinen Anker.

**Hängt ab von:** State Core (v0.10), Lifecycle (v0.8)

**Neue Events:** `policy_evaluated`, `constraint_checked`, `governance_decision`

**Scope:**
- **Code-definierte Policy:** in v0.11 bewusst kein DB-Policy-Store; Policies
  sind deterministische Code-Konstanten und später migrierbar
- **Constraint Enforcement:** ein Proposal bei hohem State-Druck darf nicht
  ohne explizites menschliches Override akzeptiert werden
- **Constitutional Kernel:** kleiner Satz harter Regeln (pending target,
  gültige Entscheidung), nicht overridebar
- jede Entscheidung im Ledger → Audit & Trace wird grün

**Definition of Done:**
- [x] mind. eine durchgesetzte Policy, nachweislich blockierend/erlaubend
- [x] jede Entscheidung im Ledger nachvollziehbar, über Query erklärbar
- [x] Replay-stabil, Integrity grün
- [x] Wachstumsregel ✓

*Hinweis: **Transition Core** ("welche Veränderung wäre möglich") wird hier
bewusst ausgelassen. Für ein System, das nur beobachtet und vorschlägt, ist
Transition vestigial — sinnvoll erst, wenn GENUS handeln kann (Worker, Model
Era). Es bleibt auf der Karte, aber nicht im 1.0-Pfad.*

---

## v1.0 — Maturation v1 · *Erfahrung wird Regel · Kern grün*

**Status:** umgesetzt. Eine bestätigte `ActivityDailyRhythm`-Experience kann
eine `activity_expectation_v1`-Regel vorschlagen. Die Regel wird erst nach zwei
getrennten menschlichen Toren wirksam: `proposal_reviewed` akzeptiert den
`RuleProposal`, `rule_activated` aktiviert ihn über einen zweiten Governance-
Entscheid. Die Wirkung bleibt bewusst klein: Abweichungen erzeugen nur
`ExpectationInquiry`, keine Belief-Änderung und keine Aktion.

**Bekannte Schuld:** Regeln haben in v1.0 keinen Deaktivierungs- oder
Revisions-Lifecycle. Das gehört mit dem Experience-Lifecycle in eine spätere
Maturation+-Schicht. Weitere Regel-Arten wie Threshold-Tuning sind ebenfalls
spätere Arbeit.

**Warum das die 1.0 ist:** Der deterministische Stoffwechsel läuft Ende zu
Ende: wahrnehmen → belegen → glauben → Zustand → regeln → vorschlagen →
lernen. Schlussstein:

**Aus Erfahrung wird Regel.** Ein Experience-Muster, das oft genug auftritt
und vom Menschen bestätigt wird, wird zu einer neuen deterministischen Regel.
GENUS kompiliert seine eigene Erfahrung zu auditierbarem Code — autonomer,
ohne unkontrollierbarer zu werden.

**Hängt ab von:** Experience (v0.9), Governance (v0.11)

**Neue Events:** `rule_proposed`, `rule_activated`

**Definition of Done:**
- [x] wiederkehrendes Muster erzeugt `rule_proposed`
- [x] menschliche Freigabe aktiviert die Regel (`rule_activated`)
- [x] aktivierte Regel wirkt deterministisch im nächsten Zyklus
- [x] ganze Pipeline Replay-stabil
- [x] **Kern-Pipeline der Karte ist grün**
- [x] Wachstumsregel ✓

---

## v1.0.1 — Ledger Audit + CI · *Kern absichern*

**Status:** umgesetzt. GitHub Actions führt Tests, Replay, Integrity und die
Import-Greps aus. `GENUS_LEDGER_AUDIT.md` dokumentiert die aktuelle Grenze:
append-only und replay-stabil, aber noch nicht manipulations-evident gegen
vollen lokalen DB-Zugriff. Ein Negativtest stellt sicher, dass kaputte
Event-Payloads `integrity.check()` scheitern lassen.

**Warum hier:** Nach dem geschlossenen v1.0-Kreis wird nicht sofort größer
gebaut, sondern das grüne Fundament reproduzierbar abgesichert.

**Definition of Done:**
- [x] CI läuft für `main` und Pull Requests
- [x] Audit-Report beschreibt Bedrohungsmodell und v1.1-Sealing-Pfad
- [x] Negativtest für kaputtes Event im Integrity-Check
- [x] Wachstumsregel ✓

---

## v1.1 — Ledger Sealing · *lokale Tamper Detection*

**Status:** umgesetzt. `genus ledger seal-init` öffnet eine versiegelte Epoche
per `ledger_epoch_opened` und Genesis-Digest über den Legacy-Prefix. Danach
schreibt `ledger.append()` `prev_seal` und `seal` direkt beim Insert. Integrity
prüft Prefix-Digest, Chain-Kontinuität und Seal-Gültigkeit. `genus ledger head`
macht den aktuellen Kopf exportierbar.

**Ehrliche Grenze:** Ohne externen Anchor erkennt GENUS versehentliche
Korruption und nicht nachversiegelte Manipulation. Ein adaptiver lokaler
Angreifer mit voller DB-Kontrolle kann History ändern und lokal neu versiegeln.
Tail-Truncation ist lokal ebenfalls nicht beweisbar. Externe Anchors sind daher
ein eigener späterer Schritt.

**Definition of Done:**
- [x] `ledger_epoch_opened` im Contract + Integrity
- [x] bestehende Events bleiben unberührt
- [x] neue Events nach Epoch tragen `prev_seal` und `seal`
- [x] lazy Tampering wird erkannt
- [x] adaptive lokale Re-Sealing-Grenze ist getestet und dokumentiert
- [x] `genus ledger head` exportiert den Chain-Head
- [x] Wachstumsregel ✓

---

# Phase 2 — Mehr Material, noch deterministisch

---

## v1.x — Struktur-Material · *GENUS beobachtet deine Arbeit*

**Warum hier:** Die ganze Maschinerie (Experience, State, Governance,
Maturation) existiert schon. Jetzt fütterst du nur eine neue Materialquelle
ein — kein Umbau nötig. GENUS beobachtet *dich*, nicht nur die Maschine.

**Neue Sensoren (deterministisch):**
- Repo: Commits/Tag, oft gemeinsam geänderte Dateien (versteckte Kopplung),
  offene Issues, Test-Coverage über Zeit
- Dateiaktivität: welche Ordner ändern sich wann, in welchem Rhythmus

**Neue Events:** nur neue Observation-/Evidence-Quellen, keine neuen Typen

---

# Phase 3 — Model Era (ab hier mit LLM)

> Wachstumsregel Frage 5 wird **bewusst und kontrolliert** gelockert. Der
> Punkt, an dem `Model Output ≠ Knowledge` praktisch greifen muss.

**Der Model-Vertrag (für alle Schritte ab v2.0):**
- Modell-Output betritt GENUS **nur als Evidence**, nie direkt als Belief
- trägt `derivation: model:<name>`, gedeckelte Confidence
- Governance gated jeden Modell-Beitrag
- der deterministische Kern bleibt ohne Modell voll funktionsfähig

## v2.0 — Meaning Engine · *erstes Modell-Organ, echtes Gespräch*

Sprache → Evidence. Du sagst etwas, GENUS interpretiert es als Beobachtung.
Jetzt versteht GENUS *dich* — die Query-Schicht aus v0.7 wird zum echten
Dialog. Erst hier, weil Sprache am weitesten von "roh und eindeutig" entfernt
ist.

**Neue Events:** `meaning_extracted` (immer `derivation: model:*`)

## v2.x — und weiter

- **Belief-Graph / Memory-Tiefe** — Beliefs vernetzen, wenn ein Proposal es braucht
- **Transition Core + Worker Interface** — wenn GENUS handeln soll (eigener Replay-Vertrag)
- **Visual Observation Model** — Bild als Sensor-Typ → Evidence (siehe `GENUS_VISUAL_THINKING.md`)
- **Maturation+ / Monitoring / Habitat-Pi** — der Rest der Karte, einer nach dem anderen

---

## Reihenfolge auf einen Blick

```
DETERMINISTISCH (kein LLM)
  v0.6   Habitat              → mehr Material
  v0.7   Query                → GENUS spricht aus seinem Zustand
  v0.8   Lifecycle            → erster Governance-Akt
  v0.9   Experience           → erstes Lernen
  v0.10  State                → Gesamtzustand
  v0.11  Governance           → Policy + Constraint greifen
  v1.0   Maturation           → Erfahrung wird Regel · KARTE-KERN GRÜN

MEHR MATERIAL (noch deterministisch)
  v1.x   Struktur-Material    → GENUS beobachtet deine Arbeit

MODEL ERA (mit LLM, eigener Vertrag)
  v2.0   Meaning Engine       → echtes Gespräch
  v2.x   Graph · Transition · Worker · Visual · Rest der Karte
```

---

## Harte Leitplanken — was auf keinem Schritt passieren darf

Diese gelten über alle Versionen, ohne Ausnahme:

- **Proposals werden niemals automatisch ausgeführt.** `Proposal ≠ Change`
  bleibt für immer hart — besonders, wenn GENUS einmal Code vorschlägt.
- **Charaktere brauchen strukturelle Isolation, nicht Policy-Versprechen.**
  Ein NSFW- und ein Kinder-Charakter auf demselben Speicher heißt: ein
  einziger Governance-Bug erreicht ein Kind. Föderation (ein Kern pro
  Charakter, getrennte Datenbanken) ist die Richtung — bindend spätestens
  bei den Charakteren.
- **Kein automatisiertes Trading mit echtem Geld auf Basis von
  Backtest-Confidence.** Niemals.
- **Keine Beobachtung von Familienmitgliedern ohne deren Wissen und ohne
  Löschkonzept.** Der Löschung-vs-Append-only-Konflikt muss *vor* der
  Familienphase gelöst sein (Richtung: Crypto-Shredding).
- **Kein selbstmodifizierender Code außerhalb einer Sandbox mit menschlichem
  Merge.**
- **Kein Kind emotional an einen Charakter binden, der verschwinden oder sich
  ändern kann** — Abhängigkeit ist bei Begleiter-Charakteren für Kinder die
  ernsteste Verantwortung der ganzen Liste.

Und eine Projekt-Regel, die das Bauen schützt: **keine neuen
Konzeptdokumente zwischen zwei Builds.** Bestehende Dokumente pflegen: ja.
Neue erst nach dem nächsten gemergten Roadmap-Schritt.

---

*Die Karte ist das Zielsystem. Diese Roadmap ist der Weg dorthin —
ein bewiesener Schritt nach dem anderen, Material vor Maschinerie,
nichts ohne Inspektion.* 🧬
