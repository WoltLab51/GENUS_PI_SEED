# GENUS ROADMAP

> Vom heutigen Stand (v1.14 — der Geist ist erwacht, GENUS lernt 24/7) bis zum Zielsystem der
> Architektur-Karte. Ein **Bau-Instrument**, keine Wunschliste.

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

Frage 5 wird erst beim **LLM-Querschnitt** (unten) bewusst gelockert — und auch dort
nur für den *offenen Schwanz*; verifizierbares Erschaffen bleibt deterministisch.

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

## Die Form — drei Schichten in einem gläsernen Kern (statt linearer Phasen)

Lange dachten wir in linearen Phasen, die auf eine „Model Era" zulaufen. Das war
schief: **verifizierbares Erschaffen ist deterministisch** — ein Beweiser, ein
Code-Synthesizer braucht kein Modell. Der gläserne, deterministische Kern endet also
*nicht* vor dem LLM; er **wächst durch drei Schichten bis zum Erschaffen**:

1. **WISSEN** — beobachten → glauben → … → Wissen mit *Herkunft, Vertrauen,
   Struktur*. (Gebaut bis zum Sensor-Wissen; ⑤ unten *vollendet* es: Wissen aus
   *jeder* Quelle.)
2. **SYSTEME** — regelgeführte Domänen *lernen* und darüber *schließen* (Sprache,
   Schach, Code …). Setzt Struktur aus Schicht 1 voraus.
3. **ERSCHAFFEN** — *erzeugen mit Beweis*: der „vorhersagen→testen"-Loop,
   verallgemeinert zu „erzeugen→verifizieren". Der Gipfel — **immer noch
   deterministisch, gläsern**.

Das **LLM ist keine Phase und kein Ziel.** Es ist ein **Querschnitt**: eine
gedeckelte Quelle/Stimme für den *offenen Schwanz* (Fluss, Idiom, das Ungeprüfbare),
die *jederzeit* andocken kann — nie Orakel, immer gegen das eigene Wissen geprüft.

Folgen für die Reihenfolge:
- **Über „Wissen" ist die Reihenfolge frei** — Domänen (Sprache/Schach/Code) und der
  LLM-Andock-Zeitpunkt sind wählbar, kein starrer Marsch.
- **„Programmieren" ist keine eigene Stufe** — es ist *Erschaffen, auf Code
  angewandt*. **„Begleiter"** ist keine Stufe — es ist *wie* GENUS genutzt wird.

(Die folgenden v0.6–v1.14-Schritte sind die *gebaute Geschichte* dieser Form — vor
allem das Wachsen der Wissens-Schicht. Was kommt, steht weiter unten *nach Schichten*,
nicht als nummerierte Phasen.)

---

## Wo wir stehen (v1.14 — Geist erwacht, lernt 24/7, Kern rund)

**Grün — deterministischer Kern + Material:** Observation · Evidence · Belief · Ledger · CPU/Memory-Sensor ·
Disk/Activity/Temperature-Sensor · CLI · Query · Replay · Integrity ·
append-only Trigger · Proposal Review · Inquiry Resolve · Experience Core ·
State Core · Governance v1 · Maturation v1 · CI · Ledger Audit · Ledger Sealing ·
External Ledger Anchors · Self-Operation Evidence · Self-Healing Governance ·
Confidence Decay v2 · Clock-Sync Self-Check · Struktur-Material (repo.commits_per_day, repo.lines_changed_per_day) · Disk-Trend (disk.trend) · Korrelation (system.thermal, self-kalibriert) · Self-Kalibrierung (repo.churn-Schwelle + disk.trend-ε aus eigener Verteilung) · Externes Material (weather.temp_outside → weather.trend, erster Internet-Sensor über die Membran)

**Grün — der Geist erwacht (Selbst-Reflexion, NICHT in der alten Roadmap geplant — gewachsen):**
BeliefStability (GENUS reflektiert über die Stabilität *eigener* Beliefs) ·
Surprise-Loop (StabilityInquiry bei Erwartungsbruch) · Experience-Re-Charakterisierung
(Selbst-Wissen bleibt aktuell) · gelernte Halbwertszeit (letztes Preset geschlossen) ·
gebundenes Evidenz-Fenster (Tier-0 zu) · DB-Härtung (WAL, busy_timeout) ·
Volatilität-als-Ausreißer (Selbst-Sicht geschärft, aus gelebten Pi-Daten) ·
azyklischer Modul-Cluster · cli-Entflechtung · Preset-Budget ehrlich reklassifiziert ·
Visual Atlas (22 Bilder) + generierte, drift-feste atlas-facts

**Grün — weiß über sein eigenes Wissen + lernt 24/7 (wissenschaftlich fundiert):**
`genus calibration` (Bayes — sind die „stabil"-Urteile belegt? live 4/4) ·
`genus surprisal` (Shannon — Bits, die ein Flip trägt) ·
`genus learning` (die Lernprogramm-Engine: Vorhersage → Selbst-Test → benoten →
Forecast-Skill, läuft 24/7 auf den Crons; vier Pfade: Wetter, Pi-Temperatur, disk, repo-Rhythmus) ·
SPC als verkörpert erkannt, TMS auf die Inferenz-Schicht vertagt. Alle read-time, rohe
Fakten, Replay-stabil, Kern bleibt modell-frei.

**Gelb:** Maturation-Pfad gebaut, aber schläft (idle Pi hat keinen Aktivitäts-Rhythmus, `active_rules=0`) · cli-Split nur teilweise
**Grün, neu (2026-06-28):** **Schicht WISSEN vollendet** — Herkunft · Vertrauen (read-time) · `resolve` regiert alle Konsumenten · Widerspruch→Surprise-Loop · Lehrer-Loop · Struktur (Relationen).
**Grün, neu (2026-06-29):** **Wissensgraph in den Kern verwoben** — der Struktur-Pfeiler prüft sich jetzt selbst: ① Confidence auf Relationen · ② Widerspruch→Surprise→Inquiry fürs Wissen · ③ Lehrer-Loop fürs Wissen · ④ Kalibrierung + Governance (`genus knowledge`/`acquisition-allowed`) · + Kadenz-Robustheitsfix. *Live-Befund:* der Graph ist 100 % einquellig → Confidence am Saatwert, Naht scharfgestellt-nicht-ausgelöst → die **zweite Quelle** ist der Zündschlüssel.
**Rot — der nächste Schritt:** **Schicht SYSTEME** — Regel-Domänen lernen + schließen; danach Erschaffen; das LLM dockt als gedeckelte Quelle an, wann es gebraucht wird

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

## v1.2 — External Ledger Anchors · *extern bezeugbarer Head*

**Status:** umgesetzt. `genus ledger anchor create` exportiert ein kanonisches
Offline-JSON-Artefakt für den aktuellen Seal-Head. Das Artefakt enthält
`core_id`, `head_event_id`, `head_created_at` und den Seal-Head. Es schreibt
kein Event und verändert die DB nicht. `genus ledger anchor verify` prüft den
verankerten Punkt gegen die lokale Chain.

**Ehrliche Grenze:** Ein Anchor schützt den Prefix bis zu seinem
`head_event_id`. Events danach sind gültige lokale Historie, aber erst ab einem
späteren Anchor extern bezeugt. Deshalb ist die Anchor-Kadenz ein
Sicherheitsparameter.

**Definition of Done:**
- [x] Anchor-Erzeugung ist read-only
- [x] `core_id` ist Pflicht über `--core-id` oder `GENUS_CORE_ID`
- [x] Verify erkennt Rewrites vor oder am Anchor-Head
- [x] Verify bleibt grün für adaptive Änderungen nur nach dem Anchor
- [x] CI erzeugt und verifiziert ein Offline-Anchor-Artefakt
- [x] Wachstumsregel ✓

---

## v1.3 — Self-Operation Evidence · *GENUS beobachtet seinen Betrieb*

**Status:** umgesetzt. GENUS kann deterministische Betriebschecks als eigene
Events schreiben. Der erste Check ist `network.gateway`: erreichbar oder nicht
erreichbar. Daraus entsteht der normale Belief `system.network=healthy` oder
`system.network=unstable`.

**Neue Events:** `operation_check_recorded`

**Neue Projektion:** `operation_log`

**Definition of Done:**
- [x] Netzwerk-Checks sind event-backed
- [x] `operation_log` ist Replay-stabil
- [x] `system.network` ist ein normaler Belief ohne gespeicherte Confidence
- [x] `genus operation list` und `genus ask "betrieb"` lesen den Zustand
- [x] Wachstumsregel ✓

---

## v1.4 — Self-Healing Governance · *Reparatur nur mit Policy*

**Status:** umgesetzt. Ein systemd-Timer kann auf dem Pi das Default-Gateway
prüfen und bei Ausfall eine Recovery anstoßen. GENUS entscheidet vorher, ob die
Recovery nach Kernel-Constraint und Policy erlaubt ist.

**Policy:** `restart_network` ist nach einem fehlgeschlagenen Gateway-Check
erlaubt. `reboot` ist erst nach mindestens drei aufeinanderfolgenden
Fehlschlägen und außerhalb des Governance-Cooldown-Fensters erlaubt.

**Neue Events:** `operation_recovery_attempted`, `operation_recovery_result`

**Definition of Done:**
- [x] Recovery wird als `operation.recovery` durch Governance bewertet
- [x] Reboot ist bis zur Fehler-Schwelle blockiert
- [x] Reboot-Wiederholung wird durch Governance-Cooldown blockiert
- [x] Recovery-Ergebnis wird event-backed dokumentiert
- [x] systemd-Timer und Windows-Installer liegen in `deploy/`
- [x] volle Testsuite grün
- [x] Wachstumsregel ✓

---

## v1.5 — Confidence Decay v2 · *alte Evidenz wird leichter*

**Status:** umgesetzt. Confidence wird weiterhin ausschließlich zur Lesezeit
berechnet, aber nicht mehr aus rohen Counts plus jüngstem Evidence-Alter. Jede
stützende und widersprechende Evidence zählt jetzt zeitgewichtet:
`2^(-age / H)`.

**Warum:** Lang bestätigte Beliefs sollen nicht nur wegen alter Akkumulation
klebrig werden. Ein frischer Widerspruch muss sichtbar Gewicht haben, ohne die
Ledger-Historie zu löschen.

**Definition of Done:**
- [x] keine Schema-Änderung, keine gespeicherte Confidence
- [x] Halbwertszeiten liegen zentral in `confidence.py`
- [x] Projektion übergibt Einzel-Zeitstempel aller Evidence-Events
- [x] Sättigung, frischer Widerspruch und alter Evidence-Zerfall getestet
- [x] Recovery-/Cooldown-Pfade bleiben unabhängig von Confidence
- [x] Wachstumsregel ✓

---

# Phase 2 — Mehr Material, noch deterministisch

---

## v1.x — Struktur-Material · *GENUS beobachtet deine Arbeit*

**Status:** zwei Sensoren umgesetzt — `repo.commits_per_day` (Anwesenheit) und
`repo.lines_changed_per_day` (Intensität). Weitere (Datei-Kopplung, offene
Issues, Coverage, Dateiaktivität) sind bewusst je *eigene* spätere Schritte.

**Warum hier:** Die ganze Maschinerie (Experience, State, Governance,
Maturation) existiert schon. Jetzt fütterst du nur eine neue Materialquelle
ein — kein Umbau nötig. GENUS beobachtet *dich*, nicht nur die Maschine.

**Hängt ab von:** Material-/Reactor-Pattern (existiert), Query (zum
Sichtbarmachen).

**Membran-Grenze:** Der Kern darf kein `git`/subprocess. Wie bei `network`/
`clock` misst die Membran (`deploy/observe_repo_from_x1.sh` auf dem X1) und
reicht über `genus observe-repo` nur die **Zahl** in den Pi-Kern. Bewusste
Entscheidung: gemessen wird auf dem **X1** (dein echter Arbeits-Rhythmus), nicht
auf dem Pi (das wäre nur die Pull-/Deploy-Kadenz). Damit speist erstmals ein
*zweites Gerät* Observations in den Kern — die Provenance hält fest, woher.

**Privacy-Grenze (Wächter-Regel):** ausschließlich **Zähler & Rhythmen**, nie
Inhalte. `git log` wird sofort in `wc -l` gepiped; nur die Zahl verlässt den X1.
Keine Commit-Messages, keine Diffs, keine Dateinamen.

**Abwesenheit ≠ Ruhe:** Läuft der X1 nicht, läuft die Membran nicht → *keine*
Observation → der Belief altert nur (Konfidenz zerfällt). Ein echter Lauf mit
0 Commits ist dagegen eine beobachtete Ruhe (`quiet`). Der Kern leitet Ruhe
*nie* aus Stille ab.

**Neue Sensoren:**
- `repo.commits_per_day` — Commits der letzten 24 h, binär:
  `repo.activity = active` (≥1) / `quiet` (0).
- `repo.lines_changed_per_day` — Summe geänderter Zeilen (24 h), binär:
  `repo.churn = heavy` / `light`. **Keine Vorgabe-Schwelle:** „heavy" wird zur
  Lesezeit aus der *eigenen* Churn-Verteilung des Pi bestimmt (Perzentil über
  bisherige Evidenz) und enthält sich, bis genug eigene Geschichte da ist.
Beide Halbwertszeit 1 Tag (träge Klasse). Der binäre Regel-Typ wurde dafür um
eine optionale Schwelle erweitert (Default 1.0 → bestehende Sensoren unverändert).
**Neue Events:** keine neuen Typen — `observation_created` + `evidence_recorded`,
Belief über `RULES` (gespiegelt von `system.activity`). `observe-repo` schreibt
beide Beobachtungen in einem Aufruf; eine Membran, ein geplanter Task.

**Definition of Done:**
- [x] beide Sensoren deterministisch, Replay-stabil, Integrity grün
- [x] `repo.activity` und `repo.churn` als Beliefs, Confidence berechnet (1 Tag)
- [x] Provenance (`measured_on`) im `observation_created`-Event
- [x] Membran misst `git`, Kern bleibt rein (grep leer, kein subprocess in `genus/`)
- [x] nur Zähler, keine Inhalte/Dateinamen
- [x] Wachstumsregel ✓

---

# Schicht WISSEN — vollenden · ⑤ Knowledge &amp; Source-Trust (deterministisch)

> Der Schritt, der die **Wissens-Schicht des Kerns vollendet**: von „weiß, was es
> gemessen hat" zu „weiß Dinge aus *jeder* Quelle, mit Herkunft" — **ohne Modell**.
> *Kein* „Eintritt in eine Model Era", sondern Kern-Vollendung. Das Fundament für
> Systeme, Sprache und Erschaffen. Aus dem Gespräch vom 2026-06-27/28 destilliert.

**Die Einsicht.** Ein LLM weiß durch Interpolation: keine Herkunft, nicht prüfbar,
kann halluzinieren, man *muss* ihm glauben. GENUS weiß durch *Aufzeichnung*.
„GENUS weiß X" muss heißen: es gibt eine herkunftsbehaftete, replaybare Kette, die
X mit einer Konfidenz behauptet. Damit wird auch *zweifelhaftes* Material sicher
konsumierbar — GENUS glaubt nie einer Quelle, es zeichnet auf, *welche* Quelle
*was* behauptet, und **lernt, wem zu trauen ist**.

**Was neu ist (drei deterministische Bausteine):**

- **Behauptung verallgemeinert.** Ein Belief ist heute schon Herkunft + Evidenz +
  Konfidenz. Verallgemeinere ihn zur *Behauptung aus einer Quelle*: jede trägt
  `source:<name>`, einen Zeitstempel und eine quellen-gedeckelte Confidence.
- **Quellen-Vertrauen, gelernt.** Jede Quelle bekommt eine Reputation — *nicht*
  vorgegeben, sondern aus ihrer Bilanz gelernt: wie oft stimmte sie mit anderen
  Quellen / mit direkter Beobachtung überein, wie oft widersprach sie. Self-
  kalibriert, wie churn und Volatilität. Eine neue Quelle startet gedeckelt und
  verdient (oder verliert) Vertrauen.
- **Widerspruch erster Klasse.** Widersprechende Evidenz gibt es schon pro Belief;
  hier wird *Quelle gegen Quelle* zum eigenen Signal: ein Widerspruch senkt
  Vertrauen und kann eine Inquiry auslösen — der Surprise-Loop, auf Wissen
  angewandt.

**Membran-Grenze:** Wie bei Wetter — der Abruf (Datensatz, Almanach-Rechnung wie
Sonnenauf-/untergang, fragwürdige Web-Zahl) passiert *außerhalb*; nur
`(claim, source, value)` betritt den Kern. Kein HTTP/LLM in `genus/`.

**Warum es den Kern *vollendet*:** Das heutige Belief-System ist nur der *Sonderfall*
„Quelle = eigener Sensor". Diese Schicht verallgemeinert ihn — und macht damit das
LLM zu *einer weiteren gedeckelten Quelle* statt einem Sonderorgan: der „Model-Vertrag"
(unten, Querschnitt) wird zum **Spezialfall** des Quellen-Vertrauens. Ohne diese
Schicht wäre ein LLM ein Sonderfall ohne Rahmen; mit ihr ist es nur der
unzuverlässigste Zeuge unter vielen. Genau das adressiert „GENUS muss kein LLM
fragen": es weiß aus eigenem, herkunftsbehaftetem Bestand.

**Bezug zu „GENUS programmiert":** Programmieren ist großteils *Wissen + Regeln +
Historie* („diese API verhält sich so", „diese Änderung tat damals X"). Diese
Schicht hält genau das — und GENUS kennt seine *eigene* Codebasis + jede Änderung
schon (der Ledger). `Proposal ≠ Change` ist bereits die Form sicherer
Selbst-Veränderung (siehe Leitplanken). Der Weg dorthin führt *durch* diese
Schicht, nicht an ihr vorbei.

**Events:** `assertion_recorded` (`derivation: source:*`, quellen-gedeckelte
Confidence) · `contradiction_detected` erweitert (Quelle gegen Quelle / gegen
Beobachtung). **Kein** `source_trust_updated`-Event — *Vertrauen ist read-time*
berechnet wie Konfidenz und Halbwertszeit, nie gespeichert (eine Korrektur an der
ersten Skizze).

**Skelett — die tragenden Verträge (verbindlich, 2026-06-28):**
1. **Darstellung** — Behauptung = (claim, value, `source`), *append-only*: neues
   `assertion_recorded`; alte `evidence_recorded` bleiben unangetastet (Sonderfall
   `source:sensor`). Kein Reshapen bestehender Events → Replay alter Events stabil.
2. **Event-Contract** — `assertion_recorded` ist *projektionsrelevant* (speist Beliefs,
   anders als die rohen forecast-Events); `contradiction_detected` um Quelle-gegen-Quelle
   erweitert; Integrity-Keys registriert; replay-stabil (Trust/Auswahl read-time).
3. **Trust = read-time** — `source_trust(conn, source)` als Query (Übereinstimmungs-Bilanz,
   self-kalibriert wie Confidence/Halbwertszeit), **kein** `source_trust_updated`-Event;
   neue Quelle gedeckelt (Seed-Fallback, kein Preset).
4. **Membran** — Abruf in `deploy/`; nur `(claim, source, value)` betritt den Kern über
   einen `observe_assertion`-Reactor; `tests/test_membrane_purity.py` erzwingt die Reinheit.
5. **Der Knackpunkt — gelöst:** die Projektion hält *Kandidaten* (`claim_key × source`);
   der aktive Belief ist eine **read-time-Auswahl per einsteckbarem Kriterium** (heute:
   Quellen-Vertrauen; Confidence = Decay ∧ Trust-Cap, beides read-time, nichts gespeichert).
   **Eine Quelle ≡ heutiges Verhalten** (Regressionstest pinnt es), *bevor* Quelle B
   dazukommt. Dieselbe Form trägt später ein Bewertungs-Kriterium (Schach) — das Kriterium
   ist tauschbar.

*Bewusst draußen (erlaubt, nicht jetzt):* Relationen/Graph · Lehrer-Loop (du als hoch-
vertraute Quelle) · LLM als Quelle (Querschnitt) · Bewertungs-Kriterium (Schach, SYSTEME)
· Merkmal-Erkennung (nie geraten). Das Skelett *erlaubt* sie (eine Quelle kann Mensch oder
`model:*` sein), baut sie aber nicht.

**Erster Schritt (kleinste solide Scheibe) — „zwei Quellen, eine Behauptung".**
Gebaut in zwei Teil-Schnitten (1a verhaltens-erhaltend, 1b neues Verhalten); Stand 2026-06-28:
- [x] Evidenz verallgemeinert zur **Behauptung mit `source`** (Sensor-Messung trägt ihre
  Quelle; neues `assertion_recorded` für Nicht-Sensor-Quellen), replay-stabil, Contract erweitert. *(1a/1b)*
- [x] Eine **zweite Quelle** für eine bestehende Behauptung (`observe_assertion`,
  read-time `consensus`) — zwei Quellen behaupten dasselbe. *(1b)*
- [x] `source_trust(conn, source)` **read-time**: Übereinstimmungs-Bilanz, self-kalibrierte
  Toleranz, keine Vorgabe; neue Quelle am Saat-Deckel. CLI: `genus sources`. *(1a/1b)*
- [x] Widerspruch Quelle-gegen-Quelle (Divergenz > self-kalibrierter Toleranz, nur unter
  *lebenden* Kandidaten): **erkannt** (`resolve.contradiction`), **senkt Vertrauen**
  automatisch, *und* **regiert** den Surprise-Loop — `observe_assertion` emittiert ein
  **claim-verankertes** `contradiction_detected` + eine `SourceContradiction`-Inquiry
  (einmal pro offener Episode). `contradiction_detected` ist nun belief- *oder*
  claim-verankert (Contract gelockert, rückwärtskompatibel); Inquiry mit `source_belief =
  NULL` (Schema erlaubte es). Der Keim des Lehrer-Loops.
- [~] Belief = trust-gewichteter Konsens, read-time: als **`consensus`-Sicht** geliefert
  (Auswahl per einsteckbarem Kriterium). Sie zur *kanonischen* `active_belief` zu erheben
  berührt alle Belief-Konsumenten → eigener Schnitt (1c).
- [x] Membran rein (`test_membrane_purity`) · Replay-stabil · Integrity grün · 279 Tests.
- [x] Wachstumsregel ✓ — Frage 5 bleibt erfüllt (noch kein Modell).

*Gefüttert (1c):* ein zweiter, unabhängiger Wetter-Anbieter (**wttr.in**) speist über
`deploy/observe_weather_second.sh` + `genus observe-assertion` *denselben* Claim
`weather.temp_outside` (stündlicher Cron) — Konsens & Widerspruch werden auf dem Pi real.
**`resolve(claim)` — die allgemeine Form (gebaut):** „gegeben ein Claim, was ist sein
*aktueller* Wert?" Kandidaten = letzte Behauptung je Quelle; gewählt wird per **Trust ×
Frische** (read-time, self-kalibrierte Kadenz als Halbwertszeit). Eine veraltete Quelle
*verblasst* (löst die Rezenz-Lücke: der eingefrorene `sensor`-Kandidat zählt nicht mehr
und kann keinen Falschalarm auslösen); Widerspruch wird nur unter *lebenden* Kandidaten
geprüft. CLI: `genus resolve <claim>`. Dieselbe Form trägt später ein Bewertungs-Kriterium
(Schach) und Erdung (Bedeutung) — `resolve` *wählt* immer unter Kandidaten, *erzeugt* sie nie.

*Erster Konsument verdrahtet:* die **Korrelations-Belief** (`apply_correlation`, ein
Punkt-Konsument) liest jetzt den *aufgelösten* Wert statt des rohen Sensors — der Sensor
ist dort nur noch *eine Quelle unter Peers*. Verhaltens-erhaltend (eine Quelle → resolve =
letzter Wert); mit mehreren regiert die Auflösung. `resolve(claim)` filtert per Claim in
SQL, damit der Reactor-Aufruf nicht den ganzen Strom scannt.

*Die Auflösung regiert jetzt **alles**:* auch die **Fenster**-Konsumenten
(`apply_threshold`/`apply_trend`) lesen über `sources.resolved_window` — die letzten n
Werte, beschränkt auf *lebende* Quellen (eine veraltete kann die Bahn nicht verschmutzen;
lebender Widerspruch ist separat geflaggt). Und **Forecasting** lernt über *alle* Quellen
(`assertions`) und benotet gegen den **aufgelösten** Wert (`resolve`). `apply_binary_rule`
(Punkt) läuft ebenfalls über `resolve`; das tote `_latest_evidence_window` ist entfernt.
Verhaltens-erhaltend (Einzel-/lebende Quelle → wie zuvor); der Sensor ist in der *ganzen*
Belief- und Lern-Schicht ein Peer.

**Lehrer-Loop — gebaut.** `genus teach <claim> <value>` (`reactors.teach`): deine Antwort
betritt als gewöhnliche `human`-Behauptung — *kein* Preset-Trust. Sie regiert *natürlich*:
die zerstrittenen Maschinen-Quellen haben ihr Vertrauen gegenseitig auf ~0 gedrückt, also
schlägt das Saat-Vertrauen des Menschen sie, `resolve` wählt den gelehrten Wert, und das
Vertrauen kalibriert sich nach (die Quelle, die mit dir übereinstimmte, verdient Vertrauen
zurück). Offene `SourceContradiction`-Inquiries für den Claim werden gelöst — GENUS fragte,
du antwortest.

**Struktur — gebaut.** `genus relate <s> <p> <o>` / `genus relations [s]`
(`reactors.observe_relation`, `sources.relations`): vernetztes Wissen als
`(Subjekt, Prädikat, Objekt)`-Tripel mit Herkunft (`relation_asserted`, Roh-Fakt,
replay-stabil), abfragbar als Graph. Dieselbe Quellen-Vertrauen-Logik gilt. *Wissen
halten* ist damit strukturiert; es *nutzen* (Inferenz, Cross-Consistency) ist die nächste
**Schicht** (SYSTEME), nicht mehr WISSEN.

> ✅ **Das *Wert-/Quellen*-Wissen ist vollendet** (2026-06-28): Herkunft · Vertrauen
> (read-time, self-kalibriert) · Auflösung (regiert alle Konsumenten) ·
> Widerspruch→Surprise-Loop · Lehrer-Loop.
>
> ⚠️ **Ehrliche Korrektur (2026-06-28, im Gespräch erkannt):** „WISSEN vollendet" war
> voreilig. Der **Struktur**-Pfeiler ist erst ein Substrat (flache Tripel, keine
> Relevanz/Inferenz). Und zwei *notwendige* Dimensionen fehlen, von echtem Bedarf
> erzwungen (nicht erfunden — siehe [[representation-dimensions-as-merkmale]]):
> **Kontext** (wo ein Claim gilt — Welt/Gespräch/Strang; Relevanz lebt darin) und
> **Modalität** (Fakt vs *Ziel/Absicht* — ein Handlungsstrang = Kontext + Ziel).
> *Vollständigkeits-Test:* eine Schicht ist fertig, wenn keine *gebrauchte* Fähigkeit an
> einer fehlenden Dimension scheitert — Gespräch/Stränge scheitern noch.

## Nächster Zwischenstand — Wissens-Akquise (strukturierte Quellen → Hirn)

> Ronnys Ziel (2026-06-28): GENUS *eignet sich* Wissen an — saugt **strukturiertes**
> Wissen aus dem Internet (Fakten, Mathe, Geo, Sprachen, Wortbedeutungen) und füllt sein
> Hirn; weiß, *wann* etwas Relevanz hat, und *setzt es ein*. **Viel Maschine, LLM am Rand.**

**Warum das ohne LLM geht:** das Internet ist großteils *schon strukturiert* —
**Wikidata** (Tripel!), **WordNet/Wiktionary** (Wort-Sinne + Relationen, genau „Bedeutung
in Beziehung x"), **GeoNames/REST-APIs** (Geo), formale Mathe-Bibliotheken,
Grammatik-Tabellen. Aufnehmen = *parsen* (Membran), nicht *interpretieren*. Das LLM braucht
es nur für den *unstrukturierten Schwanz* (freier Text → Struktur) und die Stimme.

**Der Bogen (jedes Stück deterministisch, bekannt):**
```
strukturierte Quellen (Wikidata/WordNet/GeoNames/…)
  → Membran-Parser → relation_asserted (Herkunft, Trust)
  → indizierte Relations-Projektion (Skala — das eigene event→projection-Muster,
     wie belief_projection; der heutige read-time-Voll-Scan reicht nur für Tausende)
  → Kontext + Relevanz (was holen, wann nutzen)
  → resolve über Sinne (Wortbedeutung im Kontext = Kandidaten aus WordNet, Kriterium Kontext)
  → LLM NUR für den unstrukturierten Schwanz + Stimme
```

**Erste Scheibe — GEBAUT (2026-06-28):** *strukturierte Wortbedeutung* über die Membran ins
Hirn (`deploy/observe_word.sh`) — genau dein „Bedeutung in Beziehung x". Eine freie,
no-auth Wörterbuch-API liefert Wortsinn als *Struktur* (Wortart, Synonyme, Antonyme); der
Parser macht daraus Tripel wie `run -[is_a]-> verb` · `run -[synonym]-> execute`, die als
`relation_asserted` (Quelle `dictionaryapi`, Herkunft) in den Graph gehen. Deterministisch,
**kein LLM**. `genus relations run` zeigt das gelernte Wort-Wissen.
*Danach:* Skala (indizierte Relations-Projektion) · mehr Quellen (Wikidata, GeoNames) ·
Kontext/Relevanz (welcher Sinn wann) · `resolve` über Sinne.

**Inferenz + Deutsch + die Sinn-Erkenntnis (2026-06-29):**
- **Inferenz** (`genus infer`, `genus/inference.py`) — der erste Schluss-Primitiv: gebundene,
  rückverfolgbare transitive/symmetrische Hülle über den Graph; abgeleitete Kanten werden
  *nicht gespeichert* (Begründungskette statt Herkunft), Trust = schwächste Prämisse.
- **Deutscher Grundwortschatz** (`deploy/observe_wort.sh`, OpenThesaurus) + der Lücke-Loop
  klettert die `is_a`-Hierarchie (`genus gaps --predicate is_a`, `GENUS_ACQUIRE_SCRIPT`).
- **Erzwungene Erkenntnis aus echten Daten:** der primäre-Sinn-Trick + transitive Hülle
  erzeugte **Sinn-Kontamination** (`Hund is_a Bevölkerung`). Bedeutung lebt im *Sinn*, nicht
  im Wort → die **Sinn-Dimension wurde erzwungen**, nicht am Reißbrett gewählt.

**Zwei-Schichten-Modell — die mehrsprachige Form (gebaut, 2026-06-29):**
```
WORT / Lexem  "form@lang"  --expresses-->  KONZEPT (sprach-neutral)
                                            KONZEPT --is_a--> KONZEPT   (Hierarchie + Schließen)
```
- Sprache sitzt am **Wort** (`Hund@de`, `dog@en`), Bedeutung + Hierarchie am **Konzept**
  (latein-verschlüsselt für Naturarten: `Canis → Mammalia → Animalia`).
- `genus infer Hund is_a --lang de` bildet Wort→Konzept ab, schließt **sinn-kohärent**
  (keine Kontamination — jede Kette bleibt in *einer* Sinn-Linie) und rendert die Antwort
  zurück ins Deutsche. **Ein** Konzept-Graph dient *jeder* Sprache → Englisch/Französisch
  docken durch `expresses`-Kanten an, Übersetzung + cross-linguales Schließen fallen gratis ab.
- **Lehnwörter** trennscharf: eine Form, Lexeme in mehreren Sprachen (`Community@de` +
  `Community@en`), *ein* Konzept — kein Konflikt. (`sources.senses`/`lexicalize`/`split_lexeme`.)
- *Erst Deutsch, dann en/fr, irgendwann alle* — die Konzepte sind neutral, das Schließen
  wird *einmal* gelernt und gilt überall. Die Sprache ist im Schlüssel getragen (auf eine
  Spalte promotbar, wenn eine Fähigkeit es verlangt).
- *Danach:* die Quelle umstellen (Wikidata/Wikispecies → saubere latein-verankerte
  Taxonomie statt vernakulärer Mehrdeutigkeit) · `expresses`-Akquise statt Wort-`is_a`.

**Wissensgraph in den Kern verwoben — der Graph prüft sich selbst (2026-06-29):** Der
**Struktur**-Pfeiler war ein Substrat (flache Tripel), das *neben* den epistemischen
Schleifen des Kerns lief — er nutzte Wahrheit/Projektion/Vertrauen/Rücknahme, aber nicht
Confidence, Widerspruch→Surprise→Lehrer, Governance/Kalibrierung. Vier Scheiben weben ihn
ein (alle read-time, kein Schema, kein Replay):
- **① Confidence auf Relationen** (`sources.relation_confidence`, `genus confidence`) —
  Noisy-OR über die Quellen einer Tripel: eine Relation wird *geglaubt mit einer Zahl*
  (Vertrauen × Korroboration), nicht nur „da". Die `resolve`-Idee für die Wissensseite.
- **② Widerspruch→Surprise→Inquiry fürs Wissen** (`sources.relation_contradiction`,
  `FUNCTIONAL_PREDICATES`) — für funktionale Prädikate spiegelt `observe_relation` jetzt
  `observe_assertion`: konkurrierende Objekte → `contradiction_detected` +
  `SourceContradiction`-Inquiry (Key `subject|predicate`). GENUS **flaggt faule Aufnahmen
  selbst**.
- **③ Lehrer-Loop fürs Wissen** (`reactors.teach_relation`, `genus teach-relation`) —
  Mensch/LLM setzt die richtige Relation; bei funktionalem Prädikat werden konkurrierende
  Objekte zurückgenommen, die Inquiry gelöst. Spiegelt `teach`.
- **④ Kalibrierung + Governance** (`sources.characterize_knowledge`/`genus knowledge`;
  `governance.acquisition_allowed`/`genus governance acquisition-allowed`) — GENUS weiß,
  *wie sicher* es weiß (Confidence-Verteilung, unkorroborierte/widersprochene Relationen);
  der Lerner ist read-time gegated (Pause + self-kalibrierter Quellen-Vertrauens-Boden,
  ungeloggt für den Hotloop).
- *Bonus, unterwegs gefunden:* **Kadenz-Robustheit** — die self-kalibrierte Frische-
  Halbwertszeit nahm den Median der Lücken (nur `>0` gefiltert); ein Same-Millisekunde-Burst
  erzeugte eine Millisekunden-„Kadenz", die einen gleichzeitigen Sensor fälschlich
  „veraltete" und echte Wert-Widersprüche intermittierend verbarg. Sub-Runden-Jitter
  (`< _MIN_CADENCE_SECONDS`) wird nun als Schreib-Jitter ignoriert, nicht als Rhythmus.
- **Ehrlicher Live-Befund (Pi, 2026-06-29):** `genus knowledge` zeigt **5321 Relationen,
  alle Confidence 0,50, alle einquellig (Wikidata), 0 Widersprüche** — die Maschinerie ist
  *scharfgestellt, nicht ausgelöst*: ohne eine *zweite unabhängige Quelle* gibt es nichts zu
  korroborieren und nichts zu widersprechen. Damit ist die zweite Quelle (Wiktionary/Lexeme
  — auch jenseits der Substantive) nicht nur Breite, sondern der **Zündschlüssel** der ganzen
  Naht.

---

# Schicht SYSTEME — Regel-Domänen lernen + schließen (deterministisch)

> Vom *Signal* zum *System*. Setzt die Struktur aus Schicht WISSEN voraus.

GENUS lernt regelgeführte Domänen, in denen es sich *selbst prüfen* kann (der
Lernprogramm-Loop, auf Regeln statt auf Vorhersagen). Und es **schließt**: leitet
neue, beweisbare Tripel aus bekannten ab.

- **Lernprogramme für prüfbare Domänen** — der regelmäßige Kern *einer* Sprache,
  Mathe, Spiele, Code. Selbst-Test gegen Grundwahrheit (parst es? legal? Tests grün?).
- **Inferenz** — gebundenes, deterministisches Schließen über den Graph (rückverfolgbar).
- Domänen sind **frei wählbar und parallel** — keine feste Reihenfolge.

# Schicht ERSCHAFFEN — verifizierbare Generativität (deterministisch · der Gipfel)

> Erzeugen **mit Beweis**. Der „vorhersagen→testen"-Loop, verallgemeinert zu
> „erzeugen→verifizieren". Setzt ein gemeistertes System voraus.

Wo es einen Prüfstein gibt, *erschafft* GENUS Neues, das korrekt ist: neue Beweise,
neue Sätze, neuen Code (läuft? Tests grün?). Über **Komponieren + Suchen + Verifizieren**
— alles deterministisch, geerdet, mit Herkunft. „**Programmieren**" ist genau das, auf
die Code-Domäne angewandt (governt, Mensch-merge — siehe Leitplanken).

---

# Querschnitt — das LLM als gedeckelte Quelle (kein Phase, kein Ziel)

> Wachstumsregel Frage 5 wird **bewusst und kontrolliert** gelockert — *nur* für den
> *offenen Schwanz* (Fluss, Idiom, das Ungeprüfbare). Verifizierbares Erschaffen
> bleibt deterministisch im Kern; das LLM ist ein **Werkzeug am Rand**, das jederzeit
> andocken kann, nie das Ziel.

**Der Model-Vertrag (für jeden Modell-Beitrag):**
- Modell-Output betritt GENUS **nur als Behauptung einer (niedrig-vertrauten) Quelle**,
  nie direkt als Belief — der Spezialfall des Quellen-Vertrauens aus Schicht WISSEN.
- trägt `derivation: model:<name>`, gedeckelte Confidence; Governance gated jeden Beitrag.
- der deterministische Kern bleibt **ohne Modell voll funktionsfähig**.

Seine zwei ehrlichen Jobs: **dolmetschen** (fuzzy Sprache → Struktur, die „Meaning
Engine" — `meaning_extracted`, immer `derivation: model:*`) und **Stimme** für flüssige
Ausgabe. *GENUS weiß und erdet; das LLM dolmetscht und spricht* — jede Äußerung gegen
das eigene Wissen geprüft.

## Noch offen auf der Karte (einzuordnen, nicht linear)

- **Transition Core + Worker Interface** — wenn GENUS *handeln* soll (eigener Replay-Vertrag).
- **Visual Observation Model** — Bild als Sensor-Typ → Behauptung (siehe `GENUS_VISUAL_THINKING.md`).
- **Föderation / Begleiter** — *wie* GENUS genutzt wird (ein Kern pro Charakter, getrennte DBs).

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
  v1.1   Ledger Sealing       → lokale Hash-Kette
  v1.2   External Anchors     → externer Head-Zeuge
  v1.3   Self-Operation       → GENUS beobachtet seinen Betrieb
  v1.4   Self-Healing         → Reparatur nur mit Governance
  v1.5   Confidence Decay     → alte Evidence wird leichter

MEHR MATERIAL (noch deterministisch)
  v1.6   Struktur-Material    → GENUS beobachtet deine Arbeit (repo)
  v1.7   Externes Material    → Wetter über die Membran

DER GEIST ERWACHT (Selbst-Reflexion, deterministisch · ungeplant gewachsen)
  v1.8   BeliefStability      → erste Reflexion über eigene Beliefs
  v1.9   Surprise-Loop        → Inquiry bei Erwartungsbruch
  v1.10  Evidenz-Fenster      → Tier-0 geschlossen
  v1.11  Gelernte Halbwertszeit → das letzte Preset geschlossen
  v1.12  Re-Charakterisierung → Selbst-Wissen aktuell · DB-Härtung
  v1.13  Volatilität-als-Ausreißer → Selbst-Sicht geschärft
  v1.14  Selbst-Reflexion + 24/7-Lernen → Kalibrierung · Surprisal · Forecast-Skill

── Schicht WISSEN ── VOLLENDET ✅ (2026-06-28, deterministisch)
  ⑤      Wissen & Quellen-Vertrauen → weiß aus JEDER Quelle, mit Herkunft · resolve
         regiert alles · Widerspruch→Surprise · Lehrer-Loop · Struktur (Relationen)
  ⑥      Wissensgraph verwoben (2026-06-29) → der Graph PRÜFT SICH SELBST: Confidence ·
         Widerspruch→Surprise→Inquiry · Lehrer-Loop · Kalibrierung+Governance fürs Wissen
         (Zündschlüssel offen: eine zweite unabhängige Quelle)

── darüber: freie Reihenfolge, alles noch deterministisch & gläsern ──   ← JETZT HIER
  Systeme    Regel-Domänen lernen + schließen (Sprache · Schach · Code …)
  Erschaffen erzeugen MIT Beweis → der Gipfel  ("Programmieren" = das, auf Code)

── Querschnitt, jederzeit andockbar (kein Phase, kein Ziel) ──
  LLM        gedeckelte Quelle & Stimme für den offenen Schwanz — nie Orakel
```

---

## Harte Leitplanken — was auf keinem Schritt passieren darf

> *Wie* wir bauen, damit diese Leitplanken halten: [GENUS_QUALITY.md](GENUS_QUALITY.md)
> — die Qualitäts-Charta (Plan-Disziplin + Bau-Gates, an jeder Scheibe abgehakt).

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
Neue erst nach dem nächsten gemergten Roadmap-Schritt. Skizzen dürfen in
`docs/parked/` liegen, sind dort aber ausdrücklich nicht kanonisch und kein
Build-Input.

---

*Die Karte ist das Zielsystem. Diese Roadmap ist der Weg dorthin —
ein bewiesener Schritt nach dem anderen, Material vor Maschinerie,
nichts ohne Inspektion.* 🧬
