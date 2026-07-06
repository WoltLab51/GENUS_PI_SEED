# GENUS ROADMAP

> Vom heutigen Stand bis zum Zielsystem der Architektur-Karte. Ein **Bau-Instrument**, keine
> Wunschliste. Die exakten, driftfreien Zahlen (Version, Ziele/Fähigkeiten, Raster-Größe,
> Dispatch-Umfang) stehen NICHT hier, sondern in `docs/genus_atlas_facts.md` — generiert aus
> dem Code via `genus atlas-facts`, ein Test erzwingt die Aktualität. Diese Datei hier ist die
> HISTORIE (warum, in welcher Reihenfolge, welche Funde) — die kann kein Code ableiten, die
> wird geschrieben. Aktuellster Kurs-Wendepunkt: `docs/GENUS_AUDIT_2026_07.md`.

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
**Grün, neu (2026-06-29):** **Wissensgraph in den Kern verwoben** — der Struktur-Pfeiler prüft sich jetzt selbst: ① Confidence auf Relationen · ② Widerspruch→Surprise→Inquiry fürs Wissen · ③ Lehrer-Loop fürs Wissen · ④ Kalibrierung + Governance (`genus knowledge`/`acquisition-allowed`) · + Kadenz-Robustheitsfix.
**Grün, neu (2026-06-30, v1.16):** **Sprache, Brücke & das LLM am Rand** — (a) **zweite + dritte Quelle**: Wikidata-Lexeme (`observe_lexem.sh`, korroboriert + Wortarten) und **DBnary**/dt. Wiktionary (`observe_dbnary.sh`, die menschliche Bedeutungs-Schicht, sense-safe gebunden) → die Naht *zündet* (live korroboriert); (b) **Sinn→Konzept-Brücke**: `genus concept <Q>` macht ein Konzept *ansprechbar* (deterministischer Primär-Sinn, read-time); (c) **erstes Modell am Rand**: ein lokaler **Embedder** (~100 MB, 14 ms/Pi) deutet Sinne (`disambiguate.py`) und schreibt Sinn→Konzept als **gedeckelte, graph-verifizierte `model:embedder`-Behauptung** (`bridge_senses.py`; `source_trust` deckelt `model:*` auf den halben Saatwert). Das **Tor zum Begleiter** — Kern blieb deterministisch/modell-frei.
**Grün, neu (2026-07-01):** **der Begleiter lebt** — `genus ask` antwortet aus GENUS' eigenem Graphen: (a) **Definitionen** (Sinn aus Kontext via Rand-Embedder, gläserne deterministische Stimme); (b) **relationale Fragen** „Ist ein X ein Y?" über das vorhandene Inferenz-Primitiv — die Antwort *zeigt den Weg* (Hund → Haushund → domestiziertes Säugetier → Säugetier) mit Vertrauen = schwächste Prämisse, open-world-ehrlich („unbekannt, nicht widerlegt"); (c) **die Kette** (wächst aus eigenen is_a-Lücken) + 5000-Substantive-Wortschatz; (d) **`genus why answer`** — die volle **Herkunfts-Spur** hinter einer Antwort (jede Prämisse mit Quelle + Vertrauen, zusammengesetzt = schwächste Prämisse): die These zum Anfassen; (e) **vergleichende Fragen** „Was haben X und Y gemeinsam?" — findet, wo zwei is_a-Linien sich treffen (nächste gemeinsame, benennbare Oberkategorie zuerst), reiner Reuse der Inferenz; (f) **Wortarten-Breite**: Verben & Adjektive (frequenzsortierte Lemmata aus UD-German-GSD; der Lerner zieht **Round-Robin** über Nomen/Verben/Adjektive) → der Begleiter reicht *über Nomen hinaus*; (g) **Skalierung gemessen** (nicht geraten): Hotspot war die Inferenz (Adjazenz-Neuaufbau pro Aufruf), nicht die Projektionen → einmal bauen/wiederverwenden = **8× schneller** (relationale Frage 273→32 ms), Snapshots nicht nötig. Dazu die strategische Studie `docs/GENUS_STUDY.md` (Ziele · Richtungen · Weg zum vollendeten GENUS). = **Phase A** im Kern rund.
**Grün, neu (2026-07-01, Phase B startet):** **SYSTEME ①a — GENUS lernt die Regeln seines *eigenen Denkens*.** Statt `TRANSITIVE_PREDICATES`/`SYMMETRIC_PREDICATES` nur zu *benutzen*, bewertet GENUS aus dem eigenen Graphen, ob ein Prädikat wirklich transitiv/symmetrisch ist: ein **geschlossenes Dreieck** (A→B→C mit A→C *auch* behauptet) ist die Transitivitäts-Vorhersage, von den Daten bestätigt — ≥ MIN_VINDICATIONS davon → Regel **gelernt** (`is_transitive`/`is_symmetric`), sonst die Saat-Hypothese (open-world; Absenz ist kein Gegenbeweis). Read-time, gläsern (die Vindikationen *sind* der Grund) — der Kern wendet seine eigene Maschinerie auf seine eigene Vernunft an. Live: `is_a` transitiv (**220 Dreiecke**), `synonym` symmetrisch (23 % gespiegelt). Und der reflexive Kern fing sofort einen Design-Fehler (Symmetrie braucht eine **Rate**, keine Absolutzahl — 6 is_a-Zyklen ≠ Symmetrie) **und** deckte 6 echte is_a-Zyklen im Graphen auf. Noch nicht in `infer()` verdrahtet (= ①b).
**Grün, neu (2026-07-01, Phase B — Azyklizität):** **die is_a-Zyklen aufgelöst + der Selbst-Check vervollständigt.** Ein transitives Prädikat *muss* azyklisch sein (ein Ring A→…→A ⇒ A is_a A, die Hierarchie kollabiert) — ein Zyklus ist ein **Selbst-Widerspruch**, kein Fakt. `symmetry_evidence` traf nur 2-Zyklen (gespiegelte Paare) als Nebenprodukt; der neue **`inference.cycles`** findet Ringe **jeder Länge** (read-time, gläsern, in `genus knowledge` ausgewiesen) — und deckte prompt einen **3er-Ring** auf, den der Symmetrie-Check strukturell nicht sehen konnte. Die 4 Live-Ringe untersucht (alle aus Wikidata, das die P279-Zyklen *selbst* trägt — live verifiziert): **3 klare 2-Zyklen aufgelöst** (die falsche Gegenrichtung je Ring zurückgenommen — `genus unrelate … --source wikidata`, off-Pi verifiziert → *eine* saubere Anwendung; `deploy/resolve_is_a_cycles.sh`): minestra ⊂ Suppe, Portal ⊂ Eingang, Funktion ⊂ partielle Funktion. Der **4. Ring** (Datenträger → manifestation → Kommunikationsmedien, abstrakte Oberontologie) bleibt bewusst **markiert statt blind gelöscht** — der Detektor hält ihn offen, bis er *gelehrt* werden kann. 385 grün.
**Grün, neu (2026-07-01, ①b):** **`infer()` schließt jetzt nach den *gelernten* Regeln.** Statt der hartcodierten Menge konsultiert die Inferenz `is_transitive`/`is_symmetric` (aus den Vindikationen des eigenen Graphen gelernt, Saat als Fallback) — GENUS leitet nach den Regeln her, die es *selbst bestätigt* hat. Live-Verhalten unverändert (is_a bleibt transitiv — jetzt *weil* 220 Dreiecke es vindizieren, nicht weil eine Konstante es sagt), aber ein Nicht-Saat-Prädikat, das die Daten vindizieren (z. B. `broader`), wird nun mitgeschlossen. Performance-sicher: die Regel-Entscheidung wird *einmal* pro Closure berechnet + durchgereicht (wie `edges`), mit Früh-Abbruch (`stop_at`) — Aufpreis ~9 ms, der heiße Pfad bleibt gesund (relationale Frage ~58 ms). 387 grün.
**Grün, neu (2026-07-01, ①c):** **der Kreis schließt sich — GENUS verteidigt die Konsistenz seiner eigenen Regeln.** `observe_relation` prüft bei jeder Assertion: schließt die neue Kante bei einem *(gelernt-)transitiven* Prädikat einen **Zyklus**, verletzt sie die Azyklizität (Transitivität würde `subject is_a subject` herleiten) → `contradiction_detected` + Lehrer-Loop-Inquiry, **genau wie beim Wissens-Widerspruch**. Erkennung ist am Assertions-Punkt billig: `inference.reaches` ist eine gebündelte, gezielte BFS über indizierte Einzelabfragen (berührt nur den Pfad, nicht die ganze Adjazenz), und `is_transitive` wird nur konsultiert, *wenn* ein Ring entstand. Live gemessen: **0,24 ms/is_a-Assertion** — der Lerner wird nicht gebremst. Damit ist der **reflexive Regel-Bogen rund**: GENUS *lernt* seine Denkregeln (①a), *schließt* nach ihnen (①b) und *verteidigt* jetzt ihre Konsistenz (①c). 391 grün.
**Grün, neu (2026-07-01, Phase C startet):** **GENUS kalibriert die Schwelle seines eigenen Denkens selbst.** Statt gegen die getippte Konstante `MIN_VINDICATIONS` zu prüfen, *leitet* GENUS den Transitivitäts-Grenzwert aus der **natürlichen Lücke** in seinen eigenen Daten ab (`calibrated_transitivity_min` über eine indizierte SQL-Aggregation `_vindications_per_predicate`; breiteste-Lücke-Teilung wie bei BeliefStability). Live: is_a **237** vs. synonym **2** → Lücke → Schwelle **3** — *gleich* der Saat, also **bestätigt GENUS seine eigene Konstante aus gelebten Daten** (`genus knowledge`: „transitivity threshold: 3, validated by the data"). Selbst-Kalibrierung reflexiv auf die Regeln selbst gerichtet — das Fundament von „optimiert sich selbst". **Ehrlicher Schnitt:** die Quer-über-alle-Prädikate-Kalibrierung ist pro Frage zu schwer (SQL +110 ms), daher **gläserner Readout on-demand**, der heiße Pfad behält die schnelle Saat (~58 ms). 393 grün.
**Grün, neu (2026-07-01, Phase C ① vollständig):** **der abgeleitete Wert regiert jetzt den heißen Pfad — billig.** Ein Scan-Detektor (`_rule_calibration_candidates`) rechnet die Schwelle im **Batch** und **legt sie als `RuleCalibration`-Experience ab** (recharakterisiert, wenn sie sich ändert); `is_transitive` liest den gespeicherten Wert mit *einem* indizierten Lookup (`stored_transitivity_threshold`), Saat als Fallback bis zum ersten Scan. So *schließt* GENUS nach der Schwelle, die es selbst **abgeleitet** hat — und der heiße Pfad bleibt schnell (infer_lexeme ~64 ms, kein SQL pro Frage). Das BeliefStability-Muster (batch charakterisieren → ablegen → billig lesen), jetzt den Kern **optimierend** statt nur charakterisierend: die erste Experience, die GENUS' eigene Vernunft *tunt*. Live: Scan → `RuleCalibration` abgelegt, aktive Schwelle **3**, gläsern in `genus knowledge`. **Und die Symmetrie-Rate genauso** (`_mirror_rates_per_predicate` · `calibrated_symmetry_rate` = Mittelpunkt der breitesten Lücke · `stored_symmetry_rate`; `is_symmetric` liest sie): **beide** Parameter der Vernunft sind jetzt aus gelebten Daten abgeleitet und regieren den heißen Pfad billig. Live ehrlich: nach der is_a-Zyklen-Bereinigung hat nur noch `synonym` gespiegelte Kanten → *ein* Datenpunkt, keine Lücke → Saat-Fallback (0,1), open-world-ehrlich; `genus knowledge` zeigt beide. 396 grün.
**Grün, neu (2026-07-01, SYSTEME-Breite):** **eine echte zweite Regel-Domäne: Genus-Kongruenz aus Endungen.** Kein hartcodiertes Sprachwissen ("-chen ist neutrum" steht nirgends im Code) — `genus/gender_rule.py` bewertet *jede* Kandidaten-Endung (4/3/2 Zeichen) aus den vom Lexem-Membran neu erfassten `grammatical_gender`-Relationen (Wikidata P5185, kein neuer HTTP-Call), trennt verlässliche von rauschenden Endungen über die breiteste-Lücke-Kalibrierung (derselbe Mechanismus wie bei Symmetrie), sagt das Genus unbekannter Nomen voraus und **verweigert lieber eine Vermutung** als zu raten, wenn die Evidenz dünn/uneindeutig ist. Selbst-Test per Leave-one-out (ein Nomen bestätigt nie sich selbst). Mehrwertig by design: „Messer" trägt echt zwei Genera (das Messer/Schneidwerkzeug, der Messer/wer misst) — Reichtum, keine Korruption. Live: Schwelle **selbst-kalibriert auf 0,92** (nicht die Saat 0,80), Selbst-Test **28/29 (97 %)**, eine echte Ausnahme (Gabel) ehrlich ausgewiesen, korrekte Vorhersagen für nie gesehene Wörter (Vöglein, Bildung, Wahrheit, Bekanntschaft → alle richtig; Gürtel/Wecker → ehrlich verweigert). `genus predict-gender <Nomen>` · `genus gender-rule`. 408 grün.
**Grün, neu (2026-07-01):** **der Begleiter beantwortet Genus-Fragen — `genus ask "Welches Geschlecht hat X?"`.** Epistemische Rangordnung wie überall im Kern: **bekanntes Faktum schlägt induzierte Regel schlägt ehrliches Schweigen.** Ist das Genus eines Nomens im Graphen erfasst, wird es berichtet (bei Homonymen wie „Messer" **beide** — maskulin *und* neutrum, keins versteckt); nur bei wirklich unbekannten Nomen greift die Vorhersage aus `gender_rule`, klar als **„Vermutung, kein Wissen"** markiert; ohne verlässliche Endung verweigert GENUS die Vermutung ganz. Live verifiziert: Hund (bekannt) · Messer (beide Genera) · Bildung (Vorhersage, klar markiert) · Gürtel (ehrliches Verweigern). Schließt die „praktischer Nutzen ist dünn"-Lücke aus der ehrlichen Gesamteinschätzung von heute. 414 grün.
**Grün, neu (2026-07-02, Phase C tiefer):** **systematischer Selbst-Kalibrierungs-Sweep — schärft das Kriterium, statt nur Einzelfälle zu sammeln.** Jede Top-Level-Konstante im Kern durchgegangen (nicht nur die zwei Zufallsfunde von gestern) und eingeordnet: schon selbst-kalibriert, statistische Validitäts-Untergrenze (man braucht *N* Datenpunkte, bevor irgendeine Aussage Sinn ergibt — Mathematik, keine Wette über die Welt), betrieblicher Sicherheitsparameter, oder Form-Parameter (bereits als solcher dokumentiert). Fast alles korrekt eingeordnet. **Ein echter, überraschender Fund:** CPU/Memory-Schwellen waren als „könnten kalibriert werden, Pi war zu idle" dokumentiert — eine Prognose von vor den echten Daten. Geprüft an 15+ Tagen Live-Last (~5000 Messungen): die Verteilung ist *nicht* mehr degeneriert (echte Streuung), aber Kalibrieren wäre trotzdem **falsch** — aus einem schärferen Grund: perzentil-basierte Kalibrierung passt nur zu einer **relativen** Größe (ist die heutige Churn schwer *für dieses Repo*?); CPU/Memory-Prozent ist **absolut** (80 % CPU heißt überall dasselbe). Eine absolute Größe an die eigene, meist ruhige Geschichte zu kalibrieren würde Fehlalarme erzeugen (Median CPU 0 %, p99 30 %, je gesehenes Maximum 59 % → „hoch" läge bei ~3–30 %), nicht eine willkürliche Vorgabe beseitigen. `constants.py` trägt jetzt die geprüfte Begründung statt der spekulativen von damals. **Das geschärfte Kriterium für künftige Audits: nicht „genug Daten?", sondern „ist die Bedeutung relativ zur eigenen Geschichte, oder absolut?"** 414 grün (reine Doku-Klarstellung, keine Logik geändert).
**Grün, neu (2026-07-02):** **beide offenen Punkte von gestern geschlossen.** (a) `deploy/backfill_gender.sh` — ein einmaliger, fortsetzbarer Nachtrag, der Genus-Daten für den *bereits bekannten* 5000-Nomen-Wortschatz nachzieht (die Nomen-Liste ist fertig gelernt, ohne Nachtrag käme kein neues Genus mehr hinzu); überspringt bereits bekannte Nomen, läuft mit Idle-Priorität im Hintergrund auf dem Pi. (b) Atlas-Karte ㉘ „Genus-Kongruenz" nachgetragen — die Doku-Schuld von gestern ist beglichen. 415 grün.
**Grün, neu (2026-07-02, → NACH AUSSEN):** **GENUS wird über Telegram erreichbar — die erste Tür nach draußen.** Ronny fragte, ob er „mit GENUS schreiben" könnte. Eine neue Membran (`deploy/telegram_bot.py`), keine Kern-Änderung: `companion.respond()` (dieselbe Routing-Reihenfolge wie `genus ask`, als Chat-Text statt Terminal-Tags) beantwortet Telegram-Nachrichten. Rein lesend — Governance/Pause/Lehrer-Loop sind über den Bot nicht erreichbar, bewusst („Hände" bleiben geparkt, das ist ein Mundstück, keine Hände). Nur eine Positivliste erlaubter Telegram-IDs bekommt Antworten, alle anderen werden schweigend ignoriert. Kein eingehender Port nötig (Long-Polling, ausgehend). Token lebt außerhalb des Repos, nie committet. `deploy/pi_install_telegram_bot.sh` installiert den systemd-Dienst mit normaler (nicht idle-) Priorität. 432 grün. Noch nicht gestartet — wartet auf Ronnys Bot-Token + Telegram-User-ID.
**Grün, neu (2026-07-01, live + dauerhaft):** **die Tür ist offen — GENUS antwortet Ronny über Telegram.** Bot-Token privat auf dem Pi platziert (nie im Chat, nie im Repo, `~/.genus/telegram_bot_token`, chmod 600), Positivliste = nur Ronnys numerische Telegram-ID. Live verifiziert: echte Fragen rein, Antworten aus dem eigenen Graphen raus („Was ist eine Banane?", „Hund?", „Was ist schön?"). **Und dauerhaft gemacht:** derselbe Root-Netz-Watchdog, der den Lerner am Leben hält, hält jetzt auch die Brücke am Leben (`ensure_telegram_bot`) — eigene transiente systemd-Einheit, normale statt idle-Priorität (sie antwortet einem Menschen), No-op wenn schon läuft (pgrep-Wächter), No-op wenn nicht eingerichtet (braucht Token- **und** Positivlisten-Datei). Kein passwortloses sudo nötig — genau das Muster wie beim Lerner. Übersteht Absturz und Neustart. 433 grün.
**Grün, neu (2026-07-02, vom Kern her gedacht):** **die Reboot-Schwelle der Netz-Wiederherstellung ist jetzt selbst-kalibriert.** Ausgangspunkt war eine Studie „haben wir alles, was der Kern braucht — auch mit Blick auf die Wissenschaft?": als Kenner ist der Kern fast vollständig (Wahrnehmen, Glauben/Auflösen, Wissen/Schließen, Selbst-Prüfen), als Handelnder fehlt ihm die Hälfte der Schleife (Ziele, Kausalität, Aus-Handeln-lernen, Kontext). Der kleinste, sauberste erste Schnitt: `RECOVERY_REBOOT_MIN_FAILURES=3` in `governance.py` war die letzte noch getippte Konstante an der einzigen Stelle, an der GENUS wirklich handelt — ein Bruch des längst bewiesenen eigenen Prinzips „keine Vorgaben". `governance.calibrated_reboot_threshold` leitet die Schwelle jetzt aus der natürlichen Lücke der eigenen, abgeschlossenen Netzausfall-Episoden ab (kurze Störungen vs. eine echte, Reboot-würdige Störung), Saat als Rückfall unter `MIN_RECOVERY_EPISODES=5`. Dabei fiel eine echte Duplikation auf: dieselbe „breiteste-Lücke"-Technik steckte bereits dreimal im Code (Transitivität, Symmetrie, Genus-Endung) — extrahiert nach `genus/self_calibration.py`, zwei der drei Stellen umgestellt (verhaltensgleich, Tests unverändert grün); die dritte (Genus-Endung) bewusst NICHT angefasst, weil sie sich in einer echten Randbedingung unterscheidet (keine Dedupe/Null-Filterung) — Vereinheitlichung um jeden Preis hätte dort leise das live-kalibrierte Verhalten verändert. Die Bash-Seite des Watchdogs trug dieselbe Zahl separat (`REBOOT_THRESHOLD=3`) — nur den Governance-Wert zu kalibrieren wäre wirkungslos gewesen, weil Bash schon vorher entscheidet; der Watchdog fragt die Schwelle jetzt live bei GENUS ab (`genus governance reboot-threshold --value-only`), mit Umgebungsvariable als Override und Zahlen-Fallback. **Ehrlicher Selbstkorrektur-Moment:** die erste Fassung meldete den Pi-Fund („5 abgeschlossene Ausfälle") fälschlich als „abgeleitet" — alle fünf waren exakt gleich lang, es gab also gar keine Lücke. Sofort nachgebessert: `derived` verlangt jetzt echt zwei unterschiedliche Werte, nicht nur genug Stichproben; Live-Anzeige jetzt ehrlich „kein unterscheidbares Muster" statt einer überzogenen Behauptung. `genus governance reboot-threshold`. 443 grün.
**Grün, neu (2026-07-02, Handlungs-Lücke ⑤):** **der Begleiter merkt sich den letzten Zug — eine bloße Nachfrage funktioniert jetzt.** Ronny erlebte die Lücke live über Telegram: „GENUS why answer that?" nach einer Antwort landete im gewöhnlichen „kennt kein Wort"-Pfad, weil jeder `respond`-Aufruf zustandslos ist — „that" bezieht sich auf nichts. Bewusst eng geschnitten, KEINE allgemeine Koreferenz-Auflösung (ein echt schwereres, hier nicht angegangenes Problem): `companion.is_why_followup`/`respond_in_conversation` erkennen eine kleine, geschlossene Menge deutscher Herkunfts-Nachfragen („warum?", „wieso?", „woher weißt du das?", …) und wiederholen bei bekannter letzter Frage exakt dieselbe Routing-Logik wie `genus why` — retracen also die relationale Kette oder die Wort-Verankerung, je nachdem, was die letzte Antwort tatsächlich war. Eine echte Frage überstimmt immer (die geschlossene Nachfrage-Menge kann nie kollidieren, GENUS kennt kein Wort „warum"). `companion.py` bleibt rein (kein neuer Speicher, kein Ledger-Event) — der Zustand (letzte Frage pro Chat) lebt bewusst in der Membran (`deploy/telegram_bot.py`, in-process, verloren bei Neustart: das ist UX-Sitzungslogik, kein Wissen, „Ledger ≠ Memory"). `genus ask` (CLI) bleibt unverändert. 451 grün, live gegen den echten Pi-Ledger verifiziert. **Als Nächstes offen:** Pronomen-Ersetzung („und es?") als natürliche Erweiterung, benannt aber nicht gebaut.
**Grün, neu (2026-07-02, der Plausch-Kurs):** **Richtungsentscheidung + drei Fundament-Scheiben für den Gesprächspartner.** Ronny sprach das Ziel aus: GENUS als Gesprächspartner „auf Augenhöhe", Endbild = gemeinsam Ideen entwickeln, GENUS baut, Rollout lokal → Familie → alle (deckt sich exakt mit Phase D + Föderation — nichts Neues nötig, nur Reihenfolge). Die ehrliche Lücken-Analyse zum „netten Plausch": die **Substanz** hat der Kern schon (echtes Innenleben — gelernte Wörter, offene Fragen, Zustand — nur stumm; anders als ein Chatbot, der einen Tag *erfindet*, hat GENUS einen); die **wirkliche Lücke** sind die zwei nie gebauten LLM-Rand-Rollen **Deuter** (freie Sprache → Struktur; wählt nur, erfindet nie) und **Stimme** (formuliert nur Kern-Verifiziertes). Ronny entschied: **Personen-Gedächtnis ja, definitiv** (eigener Design-Schritt — berührt bewusst „Ledger ≠ Memory") und **Modell bleibt lokal auf dem Pi** (Sekunden-Latenz okay; API/Hardware bleiben spätere Auswege). Danach die drei deterministischen Fundament-Scheiben, alle live: **(1) Routing-Klassen-Fix** — Einzelwort-Kommandos („netzwerk", „fragen", „regel") kaperten als Teilstring natürliche Fragen („Was ist ein Netzwerk?" → „0 operation record(s)" statt des bekannten Worts; dieselbe Shadowing-Klasse wie der „status"-Fix, Gegenrichtung — jetzt beidseitig zu: Einzelwörter greifen nur noch befehlsartig ≤2 Tokens als ganzes Token, Phrasen bleiben Teilstring). **(2) Inquiry-Stimme (Pull, rein lesend)** — „Was beschäftigt dich?" → GENUS erzählt seine echten offenen Fragen auf Deutsch, gruppiert statt zehnfach wiederholt, typ-spezifisch (Stabilitäts-Überraschungen; der bewusst offen gelassene is_a-Kreis mit Labels statt Q-Ids als echte Frage an den Menschen); Push-Einwürfe und Antworten übers Mundstück (= Schreibpfad) bleiben bewusste offene Entscheidungen. **(3) Gestufte Ehrlichkeit** — die Stimme qualifiziert die gezeigte Bedeutung relativ zur Vertrauens-Saat (keine neue Konstante): nur Modell-gebrückt → „da bin ich noch unsicher"; mehrfach unabhängig belegt → sagt sie; die normale Einzelquelle bleibt neutral (überall zögern wäre falscher Alarm, nicht Ehrlichkeit). 461 grün.
**Grün, neu (2026-07-02, ein realer Betriebs-Bug):** **der Lerner klebte an einer unschließbaren Lücke fest — jetzt rotiert er.** Ronry stutzte, dass der Pi-Lüfter dauernd läuft. Diagnose: NICHT überlastet (Load 0.38, 59 °C), aber der Hintergrund-Lerner hatte seit ~24 h **20.672-mal dasselbe Konzept** (Q1076176, ein Taxon) geklettert — alle 3–4 s ein vergeblicher Wikidata-Abruf, null Lernfortschritt. Ursache: `learn_gap` nahm immer die *erste* Lücke; Q1076176 hat kein `subclass_of` (P279) bei Wikidata (Taxa nutzen „parent taxon"), kann also nie eine is_a-Subjekt-Kante bekommen → bleibt Lücke → bleibt erste → ewig. Klassen-Fix (nicht Instanz), Membran-lokal: `learn_gap` merkt sich versuchte Lücken mit Zeitstempel (`learn.gap_attempts`, TTL 6 h) und rotiert zur nächsten frischen; Schließbare verschwinden nach dem ersten Klettern, Unschließbare werden höchstens 1×/TTL erneut probiert. Ausführbarer Regressionstest beweist die Rotation; live auf dem Pi bewiesen (13 verschiedene Konzepte in den letzten 20 Zügen statt 1). 463 grün.
**Grün, neu (2026-07-02, der Deuter-Benchmark + Einbau):** **sieben Modelle/Familien gemessen, eins fest eingebaut.** Erst 2 Größen derselben Familie (Qwen2.5 0.5B/1.5B), dann auf Ronnys Wunsch ausgeweitet: 0.5B–3.8B über vier Familien (Qwen2.5, Llama-3.2, Gemma-2, Phi-3.5-mini), Zero-/Few-Shot, ein handbewerteter deutscher Routing-Test (8 Fragen, automatisch statt per Auge gezählt). Ergebnis: **Qwen2.5-1.5B-Instruct trifft 7/8 — gleich gut wie Modelle 2–4× seiner Größe, aber am schnellsten und sparsamsten.** Zwei echte Funde beim Direktvergleich (kein Messrauschen): Gemma sah katastrophal aus (1/8), lag aber überwiegend an einer Markdown-Fence-Angewohnheit, nicht an falschem Schließen; Llama-3.2 rutscht bei mehrdeutigen Sätzen echt zu oft auf „chitchat". Unterwegs zwei Infrastruktur-Stolperer gefangen und behoben: `/tmp` ist auf diesem Pi RAM-gestützt (tmpfs, nur 4 GB) — vier Downloads liefen leer, weil ich blind dorthin geschrieben hatte, sofort auf die echte Platte umgezogen; ein Download (Qwen-3B) war dabei still abgeschnitten (Byte-genau nachgeprüft, neu geladen). **Eingebaut:** `genus.companion.respond_with_deuter` — die deterministische Kette (Zustand → Nachfrage → Beziehung → Vergleich → Genus → Wort) läuft unverändert zuerst; das Modell wird NUR beim totalen Fehlschlag befragt, wählt nur (ein Intent aus fester Liste, ein Wort aus der Frage), schreibt nie selbst — ein „definition"-Tipp wird graph-geprüft (muss ein wirklich bekanntes Wort sein) und als saubere Frage neu durch die bestehende Antwort-Maschinerie geschickt; ein „followup"-Tipp lässt auch Formulierungen *außerhalb* der festen Nachfrage-Phrasen die Herkunfts-Spur erreichen. Jede modell-gestützte Antwort trägt sichtbar „(Frage vom Sprachmodell gedeutet.)" — nie stillschweigend. `deploy/deuter.py` lebt bewusst anders als der Embedder: warm im selben Prozess wie der Telegram-Bot (ein Neuladen pro Nachricht wäre ~2–3 s Zusatzkosten), `llama-cpp-python` daher direkt in der bestehenden `.venv` statt eigenem venv. Live auf dem Pi verifiziert (echtes Kauderwelsch bleibt ehrlich still, echte Fragen werden korrekt gedeutet) — und ein Testhygiene-Fund gleich mit: ein bestehender Test hing unbemerkt am echten Modell, sobald es installiert war (0,4 s → 8,2 s, ResourceWarnings); jetzt mit einer Autouse-Fixture für die ganze Datei sauber isoliert. Die 7 Testmodelle (~10 GB) vom Pi aufgeräumt. 473 grün.
**Grün, neu (2026-07-02, echte Telegram-Session ausgewertet):** Ronny bat, in die laufende Bot-Session zu schauen — dabei drei echte Funde. **(1) Ein Platzhalter-Bug behoben:** bei „Hallo" und „Sternbild" bekam Ronny wortwörtlich den internen technischen Text „unknown fixed query pattern" zurück (Englisch, nie für echte Gespräche gedacht) — `query.ask`'s Fallback ist jetzt ein ehrlicher deutscher Satz, mit `companion._UNKNOWN_FALLBACK` synchron gehalten, per Regressionstest gepinnt. **(2) Eine Lücke benannt, nicht behoben:** „Bär warum" in einer Nachricht wird nicht als Nachfrage erkannt (nur bloßes „warum" allein) — Ronny hat entschieden, das liegen zu lassen: „es bringt mir nicht viel, sowas bei GENUS zu erfragen. Der echte Begleiter muss her." **(3) Eine Watchdog-Grenze erkannt:** eine kurze DNS-Störung (lokaler Router blieb erreichbar, nur `api.telegram.org` nicht auflösbar) hätte der gateway-Ping-Check nicht bemerkt — der Bot hat sich selbst berappelt (eigener Retry), also nicht dringend, aber real.
**Grün, neu (2026-07-02, Personen-Gedächtnis, Scheibe 1):** Ronnys klare Ansage danach — er entschied sich für **Personen-Gedächtnis zuerst** (statt der Stimme), mit der Begründung, dass es einen echten Design-Schritt statt eine reine Modell-Wahl braucht. Bewusst **explizit**, keine automatische Extraktion aus normalem Gespräch (ein viel härteres, fehleranfälligeres Problem — eigene Modell-Rolle, eigener Benchmark, spätere Scheibe). Ein gemerkter Fakt ist eine **ganz normale Relation** (`person:ronny -personal_fact-> "<was Ronny sagte>"`, `source="ronny"`) — kein neuer Event-Typ, kein neues Schema, dieselbe Herkunfts-Maschinerie wie jede andere Tatsache. „ronny" ist eine **menschliche Quelle** (voll vertraut, wie der Lehrer-Loop), keine `model:*`-Quelle; „person:ronny" ist ein Namensraum-Präfix (wie ein Wikidata-Q-Id oder `model:`) — dieser Kern gehört genau einer Person (Föderations-Prinzip: ein Kern pro Person, nie Multi-Tenant), also bewusst kein Personen-Parameter. „Merke dir: …" / „merk dir …" / „denk dran: …" speichert, „Was weißt du über mich?" ruft ab — geprüft **zuerst** in `respond()`, noch vor den festen Kommandos, damit ein Merk-Befehl nie geschluckt werden kann. Zwei echte Fehler beim Bauen selbst gefangen, bevor sie auslieferten: `personal_facts()` hätte über die normale `sources.relations()` **alphabetisch nach Fakt-Text** sortiert (nicht chronologisch) — eine eigene, nach `id` sortierte Abfrage behebt das; `is_recall_question` nutzte `.casefold()`, das deutsches „ß" zu „ss" wandelt und damit die eigene „ß"-Nachfrage-Phrase stumm brach — auf `.lower()` umgestellt (wie `is_why_followup` es schon macht). 481 grün.
**Grün, neu (2026-07-02, der Deuter parst freie Sprache IN den Kern):** **das Deuter-Modell läuft jetzt vor der Kette, nicht nur als letzter Ausweg — mit klaren Vorgaben, was GENUS braucht.** `respond()` war eine Kette unabhängiger Regex-Klassifizierer (Beziehung/Vergleich/Genus), jeder auf ein exaktes deutsches Muster angewiesen; der Deuter kam nur zum Zug, wenn *alle* scheiterten, und rettete selbst dann nur 3 von 6 Absichten. Deshalb hatte freie Formulierung außerhalb der Muster nirgends hin. Fix: `relate`/`common`/`gender_question` in eine Regex-Schale und einen wiederverwendbaren Auflösungs-Kern (`_relate_terms`/`_common_terms`/`_gender_term`) getrennt; die Deuter-Deutung erreicht jetzt dieselbe deterministische Logik wie der Regex-Pfad, für *jede* Absicht, die der Kern kann. Ein echter Live-Fund beim Verifizieren gleich mitbehoben: das echte Modell deutete „was ist ein Hund" (eine eindeutige Frage) als „statement" statt „definition" — strukturell gefixt, nicht per Prompt-Basteln: `deuter._looks_like_question` verwirft eine „statement"-Deutung IMMER, wenn der Text wie eine Frage aussieht. Zwei weitere Modell-Funde am Pi gefangen: der erweiterte Prompt sprengte das 512-Token-Fenster (auf 1024/2048 angehoben), und das Modell wickelte gültiges JSON in Prosa (lenient extrahiert). 488 grün.
**Grün, neu (2026-07-03, der Verstehens-Würfel — einordnen und lösen getrennt):** **Ronnys morphologischer Kasten (Zwicky) fürs Verstehen: der Dispatch ist jetzt ein deklaratives Raster, kein first-match-wins.** Der Auslöser waren drei echte Fehlgriffe in einem Test — „zählt ein Apfel zu den Pflanzen?" bekam einen Botanik-Vortrag über das Wort „Pflanzen", weil der gierige Wort-Lookup lief, bevor eine bessere Deutung je gefragt wurde (eine *Klasse*, keine Instanz). Drei Sätze von Ronny, drei Bau-Prinzipien: **(1) „erst einordnen, dann lösen"** — EINORDNEN ist von LÖSEN getrennt: feste Muster klassifizieren zuerst (ms, selbst-prüfend), nur wenn keins greift, liest der Deuter. **(2) „komplett offen, da kann alles kommen"** — der Deuter kreuzt nicht mehr an (der Ankreuzzwang war die Wurzel des Hund→statement-Fundes); die bekannten Absichten sind ein *Angebot*, freie Beschreibung in eigenen Worten erlaubt. Die AUSWAHL trifft GENUS: die Lesart wird aufs Raster abgebildet, gehandelt wird nur aus bekannten Zellen, raster-fremde Lesarten werden als Differenzierungs-Material gesammelt (Modell-Worte, nie Nutzer-Text). Offen beim Beobachten, geschlossen beim Handeln — die Differenz ist das Lernmaterial. **(3) „die Unterscheidungen stehen alle im Zusammenhang — das kennen wir von den Begriffen"** — das Absichts-Raster ist ein **Teilgraph im Ledger** (`genus/verstehen.py`, `deploy/seed_verstehen.sh`, 38 Kanten, Quelle „ronny", voll vertraut): Ausprägungen sind Knoten (`absicht:definition`), Zusammenhänge sind `is_a`-Kanten mit Herkunft und Vertrauen — dieselbe Maschinerie wie alles Wissen. Der Dispatch klettert die is_a-Kette (eine zu feine Lesart landet weich auf dem nächsten handelbaren Vorfahren, wie die Inferenz bei Begriffen); eine gelesene Zelle ohne Können wird ehrlich benannt („eine Bitte um Empfehlung — das kann ich noch nicht") UND gezählt (Belegung = Kennzahl 1, QM am Verstehen: die Zahlen priorisieren den Ausbau aus gelebten Gesprächen statt aus Bauchgefühl). Können ist Code (`_HANDELBAR`), Wissen über Absichten ist Graph. `respond()` bleibt rein (kein Modell, keine Schreibpfade — Aufzeichnung nur im Gesprächskanal); „Ledger ≠ Memory" gewahrt (nur Struktur wird festgehalten, nie der Gesprächstext). Modell-agnostisch gebaut (die Modell-Stelle ist eine Umgebungsvariable) — lokal bewiesen, „großes Modell" bleibt ein Konfig-Schalter. Live am Pi verifiziert: die drei Fehlgriffe sind weg, „empfiehl mir ein Haustier" wird ehrlich als noch-nicht-Können benannt und gemerkt. Unterwegs zwei echte Muster-Funde (Füllwörter wie „eigentlich" wurden als Nomen gegriffen; „zaehlt"-ae-Schreibweise rutschte am Muster vorbei ins Modell) gefixt. 505 grün.
**Grün, neu (2026-07-03, die Stimme — der letzte Plausch-Kurs-Schritt):** **ein bereits verifizierter Satz wird natürlicher formuliert, nie erfunden.** `deploy/stimme.py` sitzt bewusst NACH dem Kern (anders als der Deuter, der VOR jeder Antwort liest): der Satz, den sie bekommt, ist bereits aus dem gläsernen Graphen gebaut und geprüft (`narrate`/`narrate_relation`/…) — ihre einzige Aufgabe ist Formulieren, nie Hinzufügen. Die Leine ist eine **Anker-Prüfung**, kein Vertrauen ins Modell: jedes in Guillemets genannte Wort (»Hund«) und jede Vertrauenszahl muss im umformulierten Satz wortwörtlich wieder auftauchen — fehlt ein Anker, gibt `formuliere()` `None` zurück und der bewährte Template-Satz bleibt stehen. Nie stillschweigend: eine geglättete Antwort trägt sichtbar „(Sprachlich vom Modell geglättet — Fakten unverändert.)". Teilt sich das warme Deuter-Modell (`deuter.get_model()`) statt ein zweites 1.5B-Modell zu laden — auf dem Pi zählt jedes GB RAM. **Ein Live-Fund direkt nach dem Ausliefern, sofort behoben:** die erste Scheibe deckte nur Muster-/Wort-Zellen ab, aber „Was ist ein Hund?" läuft seit der letzten Scheibe über den DEUTER-Pfad (er sitzt vor dem reinen Wort-Lookup) — der häufigste Gesprächsfall wäre also gar nie geglättet worden. Fix: die Stimme erreicht jetzt auch die Deuter-gedeuteten narrate-Zellen (definition/beziehung/vergleich/grammatik/wissensfrage); beide Kennzeichnungen („geglättet" und „gedeutet") können zusammen auftreten. Live am Pi verifiziert: die Anker-Prüfung hat einen echten Fund gefangen — das Modell ließ beim Umformulieren einen ganzen Vertrauens-Halbsatz weg, GENUS fiel korrekt auf den ehrlichen Originalsatz zurück statt die Lücke stillschweigend zu zeigen. Bewusst eng: mehrzeilige Zellen (Nachfrage-Herleitung, Erinnerungen, offene Fragen) bleiben unangetastet. 520 grün. **Damit ist der Plausch-Kurs (Fundament → Deuter → Würfel → Stimme) komplett.**
**Grün, neu (2026-07-03, Personen-Gedächtnis Scheibe 2 + Antwort-Würfel Scheibe 1):** **beide von Ronny benannten offenen Scheiben fertiggestellt, gleicher Tag.** (1) **Notiz-Einwebung** (`companion._notiz_bezug`): eine gemerkte Notiz wird beiläufig in eine andere Antwort eingewoben, wenn ihr Text ein Wort (≥4 Zeichen) mit der Frage teilt — bestätigt/vermutet bleibt sichtbar unterschieden, kein Embedding-Index (das Volumen rechtfertigt noch keine semantische Suche). Nur auf dem Gesprächskanal; die CLI bleibt unberührt. (2) **Die vier Meta-Zellen** (kuerzer/ausfuehrlicher/anders-erklaeren/wiederholen) — standen im Absichts-Raster seit der Würfel-Scheibe, hatten aber keinen Handler. Jetzt komponieren sie die LETZTE Antwort um (`last_answer`, jetzt neben `last_question` in der Session geführt): Kürzen = erster Satz (deterministisch), Wiederholen = wörtlich, Ausführlicher = Herkunfts-Spur angehängt, Anders-erklären = ein zweiter, Anker-geprüfter Stimme-Versuch — sonst ehrliche Wiederholung statt Erfindung. Diese vier halten den Session-Anker auf dem ursprünglichen Thema, damit ein späteres „warum?" nicht auf das Meta-Kommando selbst zeigt. **Zwei echte Live-Funde beim Verifizieren, beide sofort behoben:** „kannst du das nochmal sagen" wurde vom Modell als Definitionsfrage über „Hund" gelesen (ein halluziniertes Subject ohne Gesprächskontext) statt als „wiederholen" — ein schärferes Few-Shot-Beispiel fixt es; die Meta-Zellen konnten den Deuter-Hinweis doppelt anhängen, wenn `last_answer` ihn schon eingebettet trug — jetzt dedupliziert. **Ein dritter, ernsterer Fund unterwegs:** die Stimme hatte beim Umformulieren einer Apfel-Antwort „Kernobst" unbemerkt zu „Kernaubere" verfälscht — die Anker-Prüfung selbst war korrekt, aber `narrate()` ließ is_a-Kategorien UNGESCHÜTZT (nur der Kopf-Begriff war ein Anker). Am Template behoben, nicht an der Prüfung: `narrate`/`narrate_relation`/`narrate_common` setzen jetzt jeden benannten Begriff in Guillemets. 538 grün.
**Grün, neu (2026-07-03, eine echte Telegram-Session zeigt eine tiefere Grenze):** Ronny zeigte eine echte, enttäuschende Session ("schau mal, was ich eben über Telegram mit GENUS gechattet habe :("). Alle vier Antworten hatten dieselbe Wurzel: bei Unsicherheit griff der Deuter zu einer plausibel klingenden, aber FALSCHEN Kategorie statt die vorgesehene freie Formulierung zu nutzen oder ehrlich zu passen — „Hallo" → `kuerzer` (kürze was?), die Wetterfrage → `vergleich` Wetter↔Morgen, eine Identitätsfrage → `erinnerungs-abruf`, eine Hilfe-Bitte für einen Familienausflug → `abschied`. Kein Quick-Fix — eine echte Kette von vier Korrekturen, jede durch sofortiges Nachverifizieren gefunden: **(1)** Sozialgesten (gruss/dank/lob/kritik/abschied) bekamen echte, feste Antworten statt „das kann ich noch nicht" — eine Floskel ist kein Wissen, ein fester Satz ist hier richtig. **(2)** Sofort beim Nachprüfen: die Hilfe-Bitte (9 Wörter) wurde weiter als `abschied` gelesen, und mit dem neuen Handler antwortete GENUS jetzt munter „Bis bald!" — SCHLIMMER als vorher, weil die Fehldeutung jetzt unsichtbar wurde. Ein echter Gruß/Dank/Abschied ist so gut wie immer kurz — eine Wortzahl-Bremse (≤6 Wörter) lässt eine Sozialgeste bei einem langen Satz ehrlich durchfallen statt zu antworten. **(3)** Die Anweisung „beschreibe frei, wenn unsicher" wirkte zu stark in die Gegenrichtung: „Danke" bekam plötzlich off-grid-Lesarten wie „erleben"/„erleichterung" statt `dank` — weil dafür (anders als für `gruss`) gar kein Beispiel verankert war. Zwei neue Beispiele + eine explizite Ausnahme (Alltagsfloskeln sind eindeutig, dort gilt die Freitext-Klausel nicht) beheben es. Ergebnis nach allen vier Runden, live nachgeprüft: „Hallo"/„Danke"/„Tschüss" bekommen die richtige feste Antwort, die Familienausflug-Bitte wird jetzt korrekt als „eine Aufforderung, etwas zu tun — das kann ich noch nicht" benannt (ehrlich, nicht mehr verwirrend falsch). Die Wetterfrage bleibt ein offen benannter Rest (keine Absicht dafür im Raster) — kein Fix heute, eine echte Lücke für eine künftige Scheibe. 542 grün.
**Grün, neu (2026-07-03, der Verstehens-Würfel wird eine echte Zwicky-Box):** Ronny, direkt nach den vier Sozialgesten-Korrekturen: „wir machen noch grundsätzliche Dinge falsch, denke ich! in welche Merkmale zerfällt denn eine Nachricht?" — und, nach der ersten Antwort, schärfer: „ich habe von Anfang an Zwicky gesagt! mach das so richtig wissenschaftlich! Nachrichten können auch Fragen, Aussagen, Floskeln und Aufforderungen in EINER Nachricht enthalten, sogar mehrfach!!!" **Die Diagnose:** das bisherige „Raster" hatte EIN Feld (Absicht) mit ~30 Werten und einer is_a-Fallback-Leiter — das ist immer noch eine flache Liste, kein morphologischer Kasten; alle vier Fehlgriffe des Tages lagen auf Zellen, die als eigenständiges Ding darin gar nicht existierten. **Der Umbau, wissenschaftlich verankert:** Zwickys General Morphological Analysis (1948/1969), alle vier Schritte — (1) unabhängige Parameter: **Sprechakt** (Searle 1969: frage/aussage/aufforderung/floskel), **Gegenstand** (begriff/genus/nutzer/gespraech/welt), **Bezug** (eigenständig/rückbezüglich, strukturell aus dem Gegenstand abgeleitet); (2) ihre Werte; (3) das Kreuzprodukt; (4) **Kreuz-Konsistenz** — von 15 möglichen (Sprechakt,Gegenstand)-Kombinationen sind nur 10 plus die gegenstandslose Floskel gesät, mit dokumentierter Begründung für die ausgeschlossenen (Zwickys Schritt 4 ist kein Nebenprodukt, sondern Pflicht). Jede Zelle ist eine echte Relation (`kombiniert_aus`), keine Namenskonvention — „welche Zellen nutzen gegenstand:welt?" ist jetzt eine echte Graph-Abfrage. Die bestehenden Feinblätter bleiben unverändert, nur ihr is_a-Elternteil ist jetzt die echte Kreuzprodukt-Zelle; Dispatch klettert dadurch höchstens EINEN Schritt, nie mehr beliebig tief. **Segmentierung** (ISO 24617-2, Dialogue Act Markup Language): ein Turn zerfällt in mehrere funktionale Segmente — `deploy/deuter.py` liest jetzt eine LISTE statt eines Objekts, `companion.py` löst jedes Segment einzeln und komponiert die Teil-Antworten (der erste, bewusst einfache Auftritt des Antwort-Würfels, mit Dedupe wiederholter Transparenz-Hinweise). Kein Freitext-Ausweg mehr (der hatte selbst Nebenwirkungen) — die Kategorien sollen erschöpfend sein, „unklar" ist die sichere Antwort. Zwei neue Zellen lösen die ursprünglichen Fehlgriffe strukturell: „weltfrage" (frage-welt) und „tun" jetzt korrekt unter aufforderung-welt. **Live verifiziert:** „Wie wird das Wetter morgen?" → ehrlich „eine Frage über die Welt draußen"; die Familienausflug-Bitte → ehrlich „eine Aufforderung, etwas in der Welt zu tun"; ein Drei-Segment-Test („Hallo! Was ist ein Hund? Danke!") komponiert Definition + Dank korrekt (das Modell erkennt nicht immer alle Segmente — ehrlich benannter Rest, kein Fix erzwungen). **Zwei echte Live-Funde unterwegs:** ein latenter Bug (`_zelle_merken` rief mit zu wenigen Argumenten auf, nie ausgelöst, jetzt gefixt) und ein Segmentierungs-Fund (die Sozialgesten-Wortzahl-Bremse und die tatsache-Notiz prüften die GANZE Nachricht statt der eigenen Segment-Klausel — ein kurzes „Danke!" verschwand sonst still aus einer längeren Nachricht; behoben, indem der Deuter jedes Segment mit seiner eigenen Textklausel zurückgibt). 552 grün.
**Grün, neu (2026-07-03, Latenz + ehrlicher Fallback):** Ronny testete den Plausch-Kurs live nach: „es ist etwas besser, aber noch längst nicht optimal, die Antworten brauchen auch ziemlich lange" — gemeinsam den Chat durchgesehen statt einseitig gepatcht. **Ursache 1, direkt gemessen, nicht geraten:** Deuter und Stimme teilten sich EIN llama.cpp-Modell (Deuter benchmarkte warm mit geteiltem Modell). Ein Direktvergleich entlarvte den Prompt-Prefix-Cache als Übeltäter: zwei Deuter-Aufrufe hintereinander (gleicher System-Prompt) 26,1 s → 2,7 s; derselbe zweite Aufruf, wenn dazwischen ein Stimme-Aufruf lief (anderer System-Prompt, wirft den Cache raus), blieb bei 27,6 s hängen. Fix, von Ronny bestätigt (AskUserQuestion): jede Rolle bekommt ihr **eigenes** Modell, `deuter.get_model()` (die geteilte Ladefunktion) komplett entfernt. **Ursache 2:** „OK prima" bekam vom echten Modell ein ehrliches leeres `[]` zurück (bestätigt: nur 1 Completion-Token) — der Code kollabierte das zu `None` (`segmente or None`) und fiel auf den gierigen Wort-Lookup zurück, der dann „prima" (eine Schulnote) erklärte, Unsinn. Fix, ebenfalls bestätigt: `[]` (der Deuter LIEF, fand aber ehrlich nichts) bleibt von `None` (Deuter nicht verfügbar) unterschieden — nur `None` fällt noch auf den Wort-Lookup zurück, ein echtes `[]` zeigt einen ehrlichen „Das habe ich nicht verstanden"-Satz. **Ehrlich offen gemeldet, nicht verschwiegen:** selbst mit getrennten Modellen brauchte ein Zug mit Deuter UND Stimme noch 7–15 s statt der aus Einzelmessungen erwarteten ~4,5 s — RAM war nicht knapp (3,4 GB frei), die eigentliche Ursache blieb ungeklärt („ein ehrlicher offener Befund, kein 'fast fertig'"). 555 grün.
**Grün, neu (2026-07-03, das Gedächtnis-Konzept):** Ronny, nach einem weiteren enttäuschenden Test: „das Gespräch mit GENUS ist noch total dumm — wie machen wir GENUS so richtig schlau?" Erst die zwei Achsen der Intelligenz aufgezeigt (Vermittlung vs. Wissen&Schließen), Ronny wählte „Fachwissen gezielt aufbauen" — aber dann selbst einen Schritt zurückgetreten: „lass uns wirklich schauen, wie das in GENUS funktioniert, BEVOR wir bauen" — sechs konkrete Leitfragen (Wann wird aus Nachricht Wissen/Erinnerung? Wie sind sie gespeichert/vernetzt? Unterscheidet sich Erinnerung von Wissen? Tagesrhythmus — behält GENUS einen Tag im Kontext?). Antwort: `docs/GENUS_GEDAECHTNIS.md`, wissenschaftlich verankert (Tulving 1972: episodisch ≠ semantisch; McClelland/McNaughton/O'Reilly 1995: komplementäre Lernsysteme, schlafgetriebene Konsolidierung; Baddeley: Arbeitsgedächtnis ≠ Langzeitgedächtnis, bestätigt „Ledger ≠ Memory"; Collins & Loftus 1975: Aktivierungsausbreitung als Abrufmechanismus ohne Embedding; Ebbinghaus: Vergessen ist funktional, kein Bug). Drei Entscheidungen von Ronny bestätigt (AskUserQuestion): Tagespuffer ja; nachts still merken, morgens berichten; genau eine Morgen-Push-Nachricht erlaubt (die erste PUSH-Fähigkeit für die bisher rein reaktive Telegram-Membran). Vier Bau-Punkte daraus abgeleitet: ① Episoden statt flacher Notizen, ② Abruf über den Graphen, ③ Fachwissen einfüllen (wartet auf Ronnys Domänen-Wahl), ④ Mehr-Zug-Arbeitsgedächtnis + Tagespuffer + Nacht-Konsolidierung.
**Grün, neu (2026-07-03, Punkt ①+②: Episoden statt flacher Notizen, Abruf über den Graphen):** Die flache Notiz (`genus:notizen -notiz-> "<Text>"`, ein Stern ohne Netz) wich echten Episoden (`genus/erinnerung.py`): ein eigener Knoten mit genau vier Kanten (`inhalt`/`von`/`am`/`erwaehnt`), vernetzt DURCH das Wissen statt direkt aneinander — zwei Erinnerungen über dasselbe Thema treffen sich am gemeinsamen Konzept-Knoten, nicht an einer Episode-zu-Episode-Kante (Tulving: episodisch ist datiert und vernetzt, kein Haufen loser Strings). Abruf (Punkt ②) ist eine deterministische Aktivierungsausbreitung (Collins & Loftus 1975) über echte Graph-Kanten, keine Ähnlichkeitssuche. **Ein Live-Fund beim ersten Test, sofort behoben:** `time.time_ns()` lieferte auf diesem System bei fünf schnellen Aufrufen hintereinander denselben Wert — zwei Episoden in Rückenfolge wären kollidiert; gefixt mit `uuid.uuid4().hex` für die Identität, die Reihenfolge kommt jetzt sauber getrennt aus der ohnehin vorhandenen Einfüge-Reihenfolge der Projektion. **Zweiter, direkt von Ronny angestoßener Fund:** „warum immer Hund??? entwickle neue stärkere Kriterien" — der reine Wortform-Abgleich (`Hunde` traf `Hund@de` nie) war eine echte Schwäche, kein Beispiel-Problem. `erwaehnt`-Kanten verankern jetzt bevorzugt am KONZEPT (`companion._prominent_concept`, dieselbe grounded-zuerst-Regel), mit einer deterministischen Endungs-Toleranz für deutsche Substantiv-Flexion als Rückfall (nur akzeptiert, wenn der gekürzte Stamm selbst ein bekanntes Lexem ist) — Synonyme und regelmäßige Flexionsformen treffen sich jetzt am selben Knoten, ein unregelmäßiger Umlaut-Plural bleibt ehrlich unerkannt (keine Morphologie-Analyse). Neue Tests bewusst mit Fahrrad/Tisch/Konzert statt Hund, um genau diese Fälle (Plural, konzeptloses Wort, zwei unabhängige Themen) durchzuspielen. `deploy/migriere_notizen.sh` überführt die alten Notizen einmalig und idempotent. 567 grün.

**Grün, neu (2026-07-03, Punkt ④ Scheibe 1: Mehr-Zug-Arbeitsgedächtnis):** Der Stop-Hook zum Vier-Punkte-Ziel meldete ehrlich nur 2 von 4 erledigt; Punkt ③ (Fachwissen) blieb bewusst auf Ronnys Domänen-Wahl blockiert — er war gerade dabei, mit mir die RICHTIGE Frage zu klären (Prüfungsordnungen als Tiefe/Umfang-Maßstab, eine mögliche Charakterschicht für Alltagswissen). Also der unblockierte Teil von Punkt ④ zuerst: `deploy/telegram_bot.py` führt jetzt eine gekappte Zug-LISTE pro Chat (`_VERLAUF_MAX=6`) statt eines einzelnen letzten Paars. Dieselbe enge Disziplin wie beim „warum?"-Nachfrage-Fix (kein Freitext-Ersatz, keine allgemeine Koreferenz): `companion.is_backreference` erkennt „…von vorhin"/„…von eben" und beantwortet ehrlich die konkrete FRÜHERE Frage noch einmal (sichtbar als Retrace benannt), statt so zu tun, als hätte ein Wort wie „das Tier" wirklich verstanden, WAS gemeint ist. Rückwärtskompatibel (`verlauf` ist ein neuer, optionaler Parameter, Standard `None`) — bestehende Aufrufe/Tests unverändert. 573 grün.

**Grün, neu (2026-07-03, Punkt ③ Infrastruktur: eine gezielte Fachliste bekommt Vorrang):** Der Stop-Hook meldete danach ehrlich weiter „nur 3 von 4" — Punkt ③ blieb echt blockiert (Ronny war noch mit mir dabei, die Scoping-Frage zu klären: Prüfungsordnungen als Tiefe-Maßstab, eine Charakterschicht für Register/Alltagswissen). Statt die Domäne zu raten, den domänen-AGNOSTISCHEN Teil gebaut: `deploy/pi_learn.sh` bekommt eine dritte, vorrangige Priorität `learn_fach` (vor der allgemeinen Breite `learn_next`, vor `learn_gap`) — eine über `GENUS_LEARN_FACHLISTEN` konfigurierte Domänen-Wortliste wird ZUERST gelernt. Der Grund, warum das mehr als Kosmetik ist: das bestehende Round-Robin behandelt jede Liste gleich (ein Wort pro Liste pro Umlauf, unabhängig von ihrer Länge) — eine 500-Wörter-Fachliste im selben Round-Robin wie 5000+ allgemeine Wörter wäre eben NICHT „gezielt", sondern nur eine weitere gleich gewichtete Liste. Leer per Default (`GENUS_LEARN_FACHLISTEN` unbelegt) — null Verhaltensänderung, bis eine echte Domänen-Datei existiert. Rückwärtskompatibel bewiesen (eigener Test). 576 grün. Die eigentliche Inhalts-Entscheidung (welches Gebiet, welche Tiefe) bleibt bewusst bei Ronny.

**Grün, neu (2026-07-03, Rechenfähigkeit — die erste echte Abitur-Aufgabenart):** Ronny stoppte den begonnenen Fachwortschatz sofort und stellte klar: „ich meine nicht die Wörter kennen. GENUS soll die Aufgaben einer Abiturprüfung schaffen. also inhaltlich und selbstverständlich auch sprachlich." Eine Ableitungs-Aufgabe ist keine Wissensfrage, sondern eine Rechnung — und Mathematik ist exakt, kein Schätzfeld für ein Sprachmodell (LLMs rechnen nachweislich unzuverlässig). Also die ERSTE externe Kern-Abhängigkeit überhaupt (bisher nur click+psutil), bewusst bestätigt (AskUserQuestion): **sympy**, eine echte, deterministische Computer-Algebra-Bibliothek — jeder Rechenschritt nachvollziehbar, keine Ausnahme vom gläsernen Kern-Prinzip, sondern seine konsequente Anwendung auf ein Gebiet, das exakt so funktioniert. `genus/mathematik.py` rechnet Ableitungen (Polynome, Exponential-/Winkelfunktionen, beliebige Ordnung); `companion.py` bekommt eine neue, selbst-prüfende Muster-Zelle „berechnen" (wie beziehung/vergleich/grammatik: erkennt feste Formulierungen wie „Bestimme die Ableitung von f(x) = …"/„Leite f(x) = … ab", rechnet über den echten Kern, nie geraten). **Zwei echte Funde, jeweils sofort durch Testen gefangen, bevor sie auslieferten:** (1) sympy liest „e" ohne explizite Bindung als freies Symbol statt der Eulerschen Zahl — d/dx(e^x) kam als „e^x·log(e)" statt der Eulerschen Identität heraus, gefixt durch explizite Bindung im Parser; (2) sympys implizite Multiplikation ist zu großzügig — ein Buchstaben-Wirrwarr wie „das ist kein term" wurde klaglos als Produkt einzelner Symbole geparst, ein plausibel aussehendes FALSCHES Ergebnis statt eines ehrlichen Fehlers. Gefixt mit einer Vorprüfung: jede alphabetische Zeichenkette im Term muss die erfragte Variable oder ein bekannter Funktions-/Konstantenname sein, sonst wird abgelehnt, bevor sympy überhaupt gefragt wird. **Ein dritter, architektureller Fund beim Testen der neuen Zelle:** die Muster-Zellen (beziehung/vergleich/grammatik/berechnen) liefen bislang UNGEPRÜFT durch die Stimme — `_STIMME_GEEIGNET` wurde nur auf dem Deuter-Pfad geprüft, nie auf dem Muster-Pfad; unauffällig, weil die drei bisherigen Muster-Zellen zufällig alle in der Menge lagen. Ein Formel-Ergebnis darf aber niemals umformuliert werden (dieselbe Korruptionsklasse wie „Kernobst"→„Kernaubere"), und die neue Zelle deckte die Lücke sofort auf — jetzt prüft der Muster-Pfad dieselbe Eignungs-Menge wie der Deuter-Pfad. `genus ableitung "<Term>"` (CLI) + die neue Muster-Zelle sind live, 596 grün. **Bewusst benannt, nicht gebaut:** Selbsttest gegen echte, bereits gelöste Abitur-Aufgaben (macht „besteht" erst messbar); weitere Aufgabenarten (Integrale, Nullstellen/Extremstellen, Vektorrechnung, Wahrscheinlichkeit); die freie Deuter-Lesart für kreativ formulierte Rechenaufgaben (bisher nur die feste Musterformulierung). Der zuvor begonnene KMK-Fachwortschatz (`deploy/fachwissen_abitur_mathematik.txt`) bleibt als ergänzende „sprachliche" Schicht liegen, ist aber nicht der Kern des Ziels.

**Grün, neu (2026-07-03, zweite Aufgabenart: Extremstellen):** Baut direkt auf der Ableitung auf — kritische Punkte über f'=0 (`sympy.solve`), klassifiziert über das Vorzeichen von f'' (Minimum/Maximum), ehrlich `"unklar"`, wenn der Test selbst nichts hergibt (bewiesen an x³ und x⁴: beide haben f''(0)=0, aber x³ hat dort einen Sattelpunkt und x⁴ ein Minimum — GENUS rät nicht, welcher Fall vorliegt, sondern benennt die Grenze des Tests). Neue Muster-Zelle "Bestimme die Extremstellen von f(x) = …", dieselbe Stimme-Ausschluss-Disziplin wie bei der Ableitung. Die volle Abitur-Initiative (Ziel, Architektur, offene Punkte) ist jetzt in einem eigenen Dokument gebündelt: `docs/GENUS_ABITUR.md`. 606 grün.

**Grün, neu (2026-07-03, dritte + vierte Aufgabenart: Stammfunktion + bestimmtes Integral):** `stammfunktion()` (unbestimmtes Integral inkl. "+ C") und `integral()` (bestimmtes Integral zwischen zwei Grenzen, auch symbolisch wie "pi") — zwei neue Muster-Zellen, dieselbe Stimme-Ausschluss-Disziplin. **Ein dritter Rechenfehler gefangen:** `sympy.simplify()` faktorisiert ein Polynom manchmal um (4x³+12x²+8x → 4x(x²+3x+2)) — mathematisch gleich, aber nicht die erwartete Schul-Normalform; `ableitung()`/`stammfunktion()` nutzen jetzt `expand()`, das live geprüft immer ausmultipliziert. `genus extremstellen/stammfunktion/integral` als CLI-Befehle. Details in `docs/GENUS_ABITUR.md`. 625 grün.

**Grün, neu (2026-07-03, nach dem Audit: der ZIEL-GRAPH — Inversion ④, der erste Schritt der neuen Richtung):** Auf die Audit-Frage „was sind die echten Ziele?" antwortete Ronny mit sieben Punkten — sein bisher vollständigstes Zielbild („GENUS soll sich eigens programmierten Code anhängen können … spürt hin, wo eine Lücke ist und fragt, ob es seinen Plan umsetzen darf … GENUS unterstützt Menschen. digital. GENUS."). Gleichzeitig fiel das Abitur-als-Gate (seine eigene kritische Nachfrage): Kategorienfehler (das Abi misst Menschen-Schwächen; sympy besteht den Rechenteil heute schon — gemessen würde fast nur der Parser) + Goodhart (ein Ziel gewordener Benchmark erzwingt wieder Muster pro Aufgabenformat = exakt die Sackgasse). **Abitur umgewidmet: Thermometer, nicht Torwächter** (Aufgaben-Korpus bleibt als held-out Messinstrument; `mathematik.py` wird Werkzeug). **Geliefert: `genus/ziele.py`** — Mission + 6 Ziele + 8 Fähigkeiten mit ehrlichem Status (live/teilweise/fehlt) als provenancter Teilgraph (Quelle „ronny", Prädikate `inhalt`/`dient`/`braucht`/`status`; bewusst KEIN is_a zwischen Zielen, um die gelernten Schluss-Regel-Statistiken nicht zu verfälschen — per Test gepinnt). GENUS weiß damit erstmals, DASS es Ziele hat, und benennt selbst, was ihm fehlt: „Was sind deine Ziele?"/„Was fehlt dir?" antwortet aus dem Graphen (deterministische Cues + neues Raster-Blatt „ziele" für den Deuter-Pfad), inkl. der ehrlichen Lücken je Ziel. `deploy/seed_ziele.sh` = ein sauberer idempotenter Apply, der die offenen Fähigkeiten beim Anwenden laut benennt. 638 grün.

**Grün, neu (2026-07-03, SELBST-CODIEREN STUFE 0 — GENUS spürt seine erste Lücke selbst):** Ronnys Ziel ⑥ wörtlich gebaut („spürt hin, wo eine Lücke ist und fragt, ob es seinen Plan umsetzen darf"): der neue Scan-Detector **`VerstehensLuecke`** (vierter Kognitions-Detektor) konsumiert zum ersten Mal die Zählungen, die bisher ins Leere liefen — die Belegung der ehrlich abgewiesenen Raster-Blätter („das kann ich noch nicht") plus die bislang UNGEZÄHLTEN „unklar"-Läufe des Deuters (jetzt als reine Struktur mitgezählt, nie Nutzer-Text — Ledger≠Memory gewahrt). Gelebter Druck wird von Rauschen über die eigene Population getrennt (breiteste Lücke, Saat=3 nur als Gültigkeits-Untergrenze) und die drängendste NEUE Lücke wird ein echtes **Proposal** über die bestehende Proposal≠Change-Maschinerie — mit Plan und expliziter Erlaubnis-Frage im Text; Freigabe über `genus governance`, nichts wird auto-angewandt. **Zwei echte Konstruktionsfehler beim Bauen selbst gefangen:** (1) zwei gleichzeitig heiße Lücken + die 1-Proposal-pro-Scan-Kappe hätten das zweite Proposal für immer verschluckt (Experience existiert → künftige Scans überspringen) — der Detector meldet jetzt pro Lauf nur die drängendste neue Lücke, die nächste rückt beim nächsten Scan nach; (2) bei einer Population aus NUR heißen Lücken (kein Rauschen, z. B. {9,7}) fabrizierte die Breiteste-Lücke-Teilung eine Grenze zwischen zwei Signalen — ohne Rausch-Gruppe regiert jetzt die Saat (dieselbe Lehre wie bei der Reboot-Schwelle: „abgeleitet" verlangt zwei echt unterscheidbare Gruppen). `record_experience_proposal` generalisiert (Kandidaten formen ihr Proposal selbst; Rhythmus-Default unverändert, per Test gepinnt). **Damit ist der Loop aus dem Audit zum ersten Mal IN GENUS geschlossen: spüren (Belegung) → planen (Proposal-Text) → fragen (Gate) → protokollieren (Ledger).** Stufe 1 (Vorschläge mit Inhalt, z. B. neue Blätter/Werkzeug-Bindungen) und Stufe 2 (Code-Vorschläge vom Generator-Organ) folgen. 650 grün.

**Grün, neu (2026-07-03, DER WERKZEUGBAUER — Inversion ② wird real):** Eine dichte Design-Runde mit Ronny (die Form eines Werkzeugs, dann "brauchen wir einen Werkzeugbauer, weißt du das?", dann "ich nehme an, der Werkzeugmacher verwendet auch Werkzeuge?") kristallisierte sich zu `genus/werkzeug.py`: ein Werkzeug zerfällt in einen DATEN-Teil (Name, Beschreibung, Parameter, `schreibt`, `wortlautfest`, `pruefbar_als` — das ist die Zeile, die Ronnys Register-Idee trifft) und einen CODE-Teil (Implementierung, Formulierung — bleibt zwingend gebunden, kann nie selbst Daten werden, ohne in Selbst-Codieren-Stufe-2-Territorium zu wechseln). Das Pflichtfeld `wortlautfest` hat bewusst KEINEN Default — eine Spec lässt sich gar nicht erst konstruieren, ohne diese Entscheidung zu treffen (die strukturelle Antwort auf die Stimme-Gating-Lücke von vorhin). Der Bauer selbst ist ein Drei-Schritt-Rezept (Prüfen → Verdrahten → Registriert) aus reinen Kern-Schritten — und damit sein eigenes erstes komponiertes Werkzeug, genau wie Ronny vermutete; der einzige Bruch in der Rekursion ist ehrlich benannt: irgendwo muss ein erstes Mal von Hand gebaut werden (derselbe Bootstrap-Boden wie `RASTER_SEED`/`ZIEL_SEED`). „Testen" ist bewusst kein Laufzeit-Pytest innerhalb des Bauers (das wäre Stufe-2-Sandbox-Aufgabe), sondern ein Vertrags-Test über die GANZE Registry, wie `test_membrane_purity.py` es für Membranen tut. Die vier Mathe-Werkzeuge laufen jetzt DURCH den Bauer (`genus/werkzeuge_seed.py`) — Strangler-Muster, nicht Ersatz: die bestehende Regex-Schnellspur in `companion.py` bleibt unverändert, die Registry macht dieselben vier Werkzeuge zusätzlich für einen künftigen Planer sichtbar. `genus werkzeuge` als CLI-Befehl; `genus_atlas_facts.md` bekommt einen vierten abgeleiteten Abschnitt (Anzahl Werkzeuge, wie viele wortlautfest). 668 grün.

**Grün, neu (2026-07-04, DIE ZIEL-ARCHITEKTUR — Maschinenraum-Analyse → ein Prinzip):** Ronny wollte „alles genau analysieren, was wie gemacht wird — dann die Vernetzung neu denken, komplett systematisch". Alle 45 Quelldateien vollständig gelesen und pro Datei Mechanismus/Registries/Imports/Ledger-Zugriff extrahiert. **Die Befunde:** vier koexistierende Dispatch-Stile (echte Registries `REACTORS`/`DETECTORS`/`werkzeug.REGISTRY` neben if/elif-Ketten in `event_router` ~19 Zweige, `query.ask` ~8, `integrity` ~15 und der ungeprüften `apply_<event_type>`-Namenskonvention); sechs echte Redundanzen (Belief-Zustandsmaschine 5× kopiert, Freitext-Klassifikation 3× gebaut, Modell-Verifikation 3×, Seed-Idiom 3×, Edge-Boilerplate 3×, breiteste-Lücke 2×); zwei verkehrte Kopplungen (`erinnerung`/`experience` greifen in `companion`-Private); `telegram_bot` umgeht `genus.db.connect`; `maturation scan` läuft in keinem Cron. Alle neun Zyklen kartiert (5-min-Sensorik bis Widerspruch→Lehrer) samt Verdrahtung (die Nacht-Pipeline sammelt, der Widerspruchs-Kanal feuert sofort; Doctor/Status-Publish sind bewusste Sackgassen). Daraus, über zehn Selbst-Angriffs-Runden (drei Revisionen überlebten) plus zwei Ideen von Ronny (constrained decoding als „Grenze" fürs Deuten; Lernen über den vorhandenen Embedder statt Training) die **Ziel-Architektur v2: `docs/GENUS_ARCHITEKTUR.md`** — eine Substanz (Ledger), zwei Kern-Primitive in Reihe (Deuten → Register), die Kern/Hülle-Frage läuft DURCH die Module („muss es stimmen, egal was registriert wird?"), Registrierung wird selbst ein Event (mit ehrlich benannter Bootstrap-Naht), Lernen = erinnern + neu rechnen (dritte Instanz derselben Form wie `sources`-Vertrauen und Selbst-Kalibrierung). Sechs offene Nähte ehrlich gerankt (ernsteste: der Lernkreis ist am Ort des Fehlers nicht geschlossen; der echte Migrations-Wächter ist ein Registry-Vertragstest, nicht der Replay-Test). Stand-Audit im Dokument: Substanz ✅, Primitive ◐ (Prototypen neben Alt-Formen), Grenze/Lernkreis/Ledger-Registry ✗ — aber alles Verdrahtung von Vorhandenem, kein Neubau. Der Weg: Strangler in 5 Phasen (Boden → Register → Deuten härten → Hülle auf den Ledger → Selbst-Codieren schließt den Kreis). Die Gate-Politik hat Ronny am 2026-07-04 entschieden: **„entwickelt sich"** — startet am strengsten Punkt (Freigabe pro Stück), jede Lockerung ist selbst ein Proposal durchs Gate (nie einseitig), und ein Boden entwickelt sich nie: schreibende Werkzeuge mit Außenwirkung (Geld, Nachrichten an Dritte, Systemeingriffe) bleiben immer freigabepflichtig. Kodierung: Kernel-Constraint (der Boden) vs. Policy (das Kalibrierbare) — die Zweiteilung, die `governance.py` schon lebt.

**Entschieden (2026-07-04): UMBAUEN, nicht neu.** Ronny stellte die Frage direkt; die Antwort mit Evidenz: die gelebten Daten SIND die Intelligenz (selbst-kalibrierte Schwellen leiten sich aus der eigenen Historie ab, der Graph trägt tausende dreifach-bequellte Wörter, der Ledger ist append-only + versiegelt — ein neuer Kern startet mit Amnesie oder braucht genau die Migration, die den Rewrite schwer macht); die 668 grünen Tests tragen hunderte gelebte Korrekturen als Pins; das Audit fand die Defekte in Dopplungen und Verdrahtungs-Stilen, nicht im Fundament. Aber „neu" passiert trotzdem — pro Baustein: jedes neue Teil wird komplett neu gebaut (sauber, nach Zielbild, deutscher Name), das Alte migriert hinein und stirbt; nach allen Phasen + Umbenennung ist das Ergebnis faktisch eine neue Codebasis, erreicht ohne Amnesie und ohne Risiko-Lücke. **Falsifizierbarer Checkpoint:** nach Phase 1 (dem ersten Eingriff mit Blast-Radius) wird die Frage mit Evidenz erneut geprüft — hat die alte Struktur wirklich gekämpft, wird neu entschieden, mit Daten statt Gefühl.

**Grün, neu (2026-07-04, PHASE 0 GELIEFERT — der Boden liegt):** Vier Schritte, je verhalten-erhaltend, 675 grün (7dc4a78 + 6bb05b3): ① Text→Konzept-Auflösung nach `sources` (`bekanntes_wort`, `prominentes_konzept`) — `erinnerung` greift nicht mehr in Companion-Private; `experience` nutzt die neue öffentliche Auskunft `companion.hat_handler` (volle Auflösung in Phase 3). ② `telegram_bot` verbindet über `genus.db.connect` (dieselben Pragmas/Migrationen wie die CLI; Struktur-Gate-Test dagegen, dass es zurückschleicht). ③ Die EINE Belief-Zustandsmaschine `projection.belief_uebergang` — die drei wortgleichen Kopien (rules ×2, operation ×1) sind Delegation; `apply_threshold` bleibt bewusst eigen (wirklich andere Maschine: asymmetrisch, kennt weaken). ④ Geteilter Sä-Helfer `reactors.sae_fehlende` (ziele + verstehen). **Zwei Punkte ehrlich zurückgestellt statt blind gebaut:** das Edge-Boilerplate-Dedup (die drei Embedder-Skripte laufen nur auf dem Pi, kein Test importiert sie, fastembed fehlt auf der Dev-Box — unverifizierbar wäre gegen die eigene Disziplin) und die „geteilte Anker-Prüfung" (nur das Prinzip ist geteilt, nicht der Code — nichts zu dedupen).

**Grün, neu (2026-07-04, PHASE 1 GELIEFERT — das erste Kern-Register + CHECKPOINT bestanden):** In der versprochenen Reihenfolge: ZUERST der Wächter, dann der Umbau. ① Der **Registry-Vertragstest** (`tests/test_event_vertrag.py`, Naht 3): liest aus dem Quelltext, welche Event-Typen der Kern je schreibt (`ledger.append`-Literale, konstanten-aufgelöst, plus der eine bewusste Direkt-INSERT der Siegel-Epoche), und erzwingt, dass jeder in GENAU EINER von zwei Mengen steht — `PROJEKTOREN` (projiziert) oder `BEWUSST_ROH` (mit dokumentiertem Grund roh, z.B. Prognosen). Genau die Lücke, die der Replay-Test allein nicht fängt (eine vergessene Registrierung fehlt auf BEIDEN Seiten des Vergleichs → grün obwohl falsch); Tippfehler in Register-Schlüsseln fallen mit. Alle 28 je geschriebenen Event-Typen waren beim ersten Lauf entschieden. ② Die ~20-zweigige if/elif-Kette in `event_router.apply_event` ist ein **Register** (`PROJEKTOREN`-Dict + `registriere_projektor` mit Kollisions- und Bewusst-roh-Schutz — kein stilles Überschreiben); die zwei operation-Typen behalten ihr `_source_event` über einen expliziten Adapter. ③ `maturation` folgt jetzt dem Geschwister-Muster (`KANDIDATEN`-Registry wie `REACTORS`/`DETECTORS`) — die letzte Registry-Inkonsistenz der vier Geschwister ist weg. `atlas-facts` leitet Router- und Reifungs-Registry jetzt mit ab. 680 grün. **CHECKPOINT (umbauen-oder-neu, mit Evidenz):** die alte Struktur hat NICHT gekämpft — der zentralste Umbau des Systems lief in einer Sitzung durch, alle Tests grün beim ersten vollen Lauf, der Vertragstest fand null vergessene Typen. Die Tests waren Netz, nicht Fessel. **Umbauen bestätigt; es gibt keinen Evidenz-Grund, neu anzufangen.**

**Grün, neu (2026-07-04, PHASE 2 GELIEFERT — die Grenze, und Naht 5 war real):** Ronnys Geistesblitz („das nächste Wort darf nur innerhalb der Grenze sein") ist gebaut: **`verstehen.gbnf_grammatik`** leitet aus dem lebenden Raster-Angebot eine llama.cpp-GBNF-Grammatik ab — das Deuter-Modell kann pro Token nur noch innerhalb des JSON-Segment-Vertrags und der bekannten Blätter fortsetzen, eine **erfundene Kategorie ist strukturell unmöglich** statt per Few-Shot erhofft; „unklar" ist immer Teil der Grenze (ehrlicher Ausgang — ob das Modell ihn richtig WÄHLT, bleibt Modell-Qualität, Naht 2 ehrlich offen). Die Grammatik ist reine DATEN und wird vom Bot über die Membran gereicht (`deuter.interpret(grammatik=...)`; deuter importiert weiterhin nie genus.*); kompiliert wird einmal pro Text (Cache), eine unbrauchbare Grammatik degradiert LAUT statt still (stderr-Warnung, Deuter läuft unbeschränkt weiter — der Bot bleibt antwortfähig). Wächst das Raster, wächst die Grenze mit — kein Nachpflegen. **Beim Bauen bestätigte sich Naht 5 sofort als echter Live-Bug:** das Blatt „berechnen" war im Graphen gesät, aber der hartkodierte Spiegel in `deuter.py` kannte es nicht — und der gruppierte Prompt verschluckte es STILL auch beim lebenden Angebot (nur in `_GRUPPEN` gelistete Blätter erschienen je im Prompt): der Deuter konnte eine Rechenaufgabe nie als solche lesen, kaschiert allein durch die Regex-Schnellspur. Dreifach geschlossen: Spiegel repariert (+`berechnen`), ein WEITERE-Auffangnetz im Prompt (kein angebotenes Blatt verschwindet mehr still), und ein CI-Pin, der Spiegel↔Raster-Drift an der Entstehungsstelle bricht (`DEFAULT_ABSICHTEN` == Raster-Blätter, jedes Blatt in genau einer Gruppe, jedes erklärt). 686 grün. **Ehrlich offen:** die Live-Wirkung der Grenze (Segmentier-Qualität unter Grammatik-Zwang, Latenz) ist off-Pi nicht messbar — braucht die Pi-Verifikation nach dem Deploy.

**Grün, neu (2026-07-04, DEPLOY + LIVE-VERIFIKATION der Grenze — vier echte Funde):** Phase 0–2 auf dem Pi (Replay deterministisch über 471.530 Events, Integrität + Siegelkette + Doctor grün). Der erste Deploy-Lauf schlug ZU RECHT fehl: der Grammatik-Degradations-Test war maschinenabhängig gebaut („root ::= kaputt" ist auf dem Pi GÜLTIGES GBNF — llama_cpp installiert, kompilierte brav; auf der Dev-Box fehlt es). Zweiter Fund: der Pi-GBNF-Parser schluckt sogar eine offene Klammer — auf Parser-Strenge lässt sich nicht wetten; der Test injiziert das Scheitern jetzt hermetisch (Fake-llama_cpp), der echte Fehlerfall läge ohnehin erst beim Generieren (fängt `interpret`s try/except → ehrlicher Fallback). Dritter Fund: **`berechnen` fehlte im LEBENDEN Graphen** (Seed nach der Rechenfähigkeit nie neu angewandt) — ein sauberer `seed_verstehen.sh`-Apply, jetzt 33 Ausprägungen. Vierter Fund, der wichtigste: **der Bilderbuch-Beweis für die Grenze, live** — ohne Grammatik erfand das Modell die Kategorie „aussage" (existiert als Blatt nicht, das ist ein Sprechakt); mit Grammatik strukturell unmöglich, beide Lesarten gültige Blätter. Gleichzeitig die Grenz-Grenze bestätigt (Naht 2): das Modell FABRIZIERTE einen Segment-Text („f'(x) = 2x + 3" — selbst ausgerechnet, steht nirgends in der Nachricht); die Grammatik erzwingt Struktur, nicht Herkunft — dagegen jetzt eine deterministische Herkunfts-Leitplanke in `deuter._segment` (Text nicht in der Nachricht → nicht geglaubt). **Latenz ehrlich:** warm ≈ +1,5–4 s unter Grammatik-Zwang (4,4 s vs. 2,9 s bzw. 12,1 s vs. 8,4 s) — spürbar, tragbar; Segmentierungs-Ausfälle (übersehene Grüße/Danke) traten in BEIDEN Modi auf, Modell-Varianz, nicht Grammatik-Folge. 687 grün, zweiter Deploy sauber durch. **Offen: der laufende Bot-Prozess lädt den neuen Code erst nach einem Neustart (transiente systemd-Unit, braucht sudo — Ronnys Hand).**

**Grün, neu (2026-07-04, PHASE 3 SCHEIBE 1 — die Gesprächszellen laufen durch den Werkzeugbauer):** Bot neu installiert (richtige Unit `genus-telegram-bot.service`, Restart=always — die Grenze ist damit live im Gespräch). Dann die 23 `_HANDELBAR`-Zellen als geprüfte Werkzeuge registriert (`companion.registriere_zellen`, Name `zelle:<blatt>`, idempotent): jede Zelle beantwortet jetzt die **Pflicht-Entscheidungen der Spec ausdrücklich** — `wortlautfest` (nur definition/beziehung/vergleich/grammatik/frage-begriff sind frei formulierbar), `schreibt` (nur merken/tatsache), `pruefbar_als` (graph/sitzung/erinnerung/fest). Das Seed-Dict `_HANDELBAR` bleibt als code-seitiger Bootstrap-Boden (wie RASTER_SEED/ZIEL_SEED), aber **alle Laufzeit-Verbraucher lesen die Registry** (`_handelbare_werkzeuge`): der Deuter-Dispatch, der Muster-Pfad, `hat_handler`, `atlas-facts`. **Die zweite handgepflegte Menge `_STIMME_GEEIGNET` ist damit WEG** — die Stimme-Eignung folgt strukturell aus `not wortlautfest` (werkzeug.stimme_geeignet), exakt die Bug-Klasse, für die der Werkzeugbauer gebaut wurde, jetzt auch an ihrer Ursprungsstelle geschlossen. Dispatch überlebt eine geleerte Registry (idempotente Nach-Registrierung, getestet). `genus werkzeuge` zeigt jetzt ehrlich die ganze Fähigkeits-Karte: 4 Mathe-Werkzeuge + 23 Zellen. 691 grün.

**Grün, neu (2026-07-04, PHASE 3 SCHEIBE 2 — die Hülle hat Herkunft):** Die Registrierungs-ENTSCHEIDUNG ist jetzt Ledger-Geschichte: `werkzeug.protokolliere_registrierungen(conn)` schreibt für jedes registrierte Werkzeug, dessen aktueller **Vertrags-Fingerabdruck** (Name, Parameter, schreibt, wortlautfest, pruefbar_als — bewusst OHNE die Beschreibungs-Prosa) noch nicht als jüngstes `werkzeug_registriert`-Event im Ledger steht, genau eines. Dedupliziert: ein Prozess-Start spammt nie; eine echte Vertragsänderung (z.B. ein wortlautfest-Wechsel) schreibt ein NEUES Event — die Historie der Hülle bleibt vollständig (per Test gepinnt: `[True, False]`-Historie nach einem Kipp). `quelle="code"` heute; später schreibt Selbst-Codieren hier seine gegatete Herkunft. Der Event-Typ ist BEWUSST_ROH (die Laufzeit-Registry wird weiter aus Code gebaut — §4-Naht ehrlich benannt); **der Phase-1-Vertragstest hat die Entscheidung erzwungen** (ohne BEWUSST_ROH-Eintrag wäre CI rot), und beim Bauen fiel die DRITTE Event-Typ-Stelle auf: `integrity.REQUIRED_EVENT_KEYS` kannte den Typ nicht → Integritäts-Check schlug korrekt fehl → Schema-Eintrag ergänzt. Angedockt an `genus werkzeuge` (registriert alles, listet, protokolliert — sichtbar, idempotent). 695 grün.

**Grün, neu (2026-07-04, PHASE 3 SCHEIBE 3 — der Korrektur-Kanal, Naht 1 geschlossen):** Der ernsteste offene Punkt der Architektur — Lernen am Ort des Fehlers, ohne dass die Korrektur selbst durch den Klassifikator muss, der eben danebengriff — ist zu: ein **exaktes „falsch verstanden"** (oder „falsch gedeutet", optional „: <blatt>" mit dem exakten Namen dessen, was gemeint war) wird **deterministisch VOR jeder Deutung** erkannt (`companion.korrektur_cue`, Regex, kein Modell; ein längerer Satz ist bewusst KEIN Cue). Dafür weiß die Session jetzt, worauf der letzte Zug gehandelt hat: `respond_with_deuter` gibt `gelesen` (die Raster-Lesarten des Zugs) zurück, der Bot fädelt es wie question/answer weiter. Die Korrektur wird als **reine Struktur** festgehalten (`verstehen.record_fehlgriff`: eine `fehlgriff`-Zähl-Kante wie die Belegung, plus bei genanntem Blatt die gerichtete Verwechslung `fehlgriff_statt` — welche Verwechslungen häufig sind, ist selbst Wissen und das Rohmaterial für den Embedder-Lernkreis, Naht 4); **nie Nutzer-Text** (per Test gepinnt: der Wortlaut der korrigierten Frage steht nirgends im Ledger). Kennzahl 2 am Verstehen: `verstehen.fehlgriffe` (retraktions-bewusst, geteilter Zähler mit der Belegung) — viele Fehlgriffe auf einem Blatt heißen „das DEUTEN dorthin muss besser werden", nicht „das Können fehlt". Ehrliche Ränder: Korrektur ohne letzten Zug antwortet ehrlich und schreibt nichts; ein unbekanntes Blatt wird benannt, der Fehlgriff zählt trotzdem; der Korrektur-Zug selbst trägt keine Lesart (keine Doppel-Korrektur-Schleife). Der Anker bleibt beim korrigierten Thema. **Beim Deploy davor ein echter Ops-Fund mit Selbstkorrektur:** direkte SSH-Befehle ohne `GENUS_DB_PATH` ließen die CLI still eine Streu-DB im Repo-Verzeichnis anlegen (27 Events landeten zuerst dort statt im echten Ledger — Streu-DB verifiziert-leer gelöscht, korrekt neu protokolliert: 27 Entscheidungen im echten Ledger, Siegelkette intakt, Dedupe live bewiesen mit 0 beim Zweitlauf); Härtung (Warnung beim Anlegen einer frischen DB) als eigenes Arbeitspaket notiert. 701 grün.

**Grün, neu (2026-07-04, LERNKREIS v1 — die Korrekturen fließen zurück, Naht 4 zur Hälfte zu):** Der Rückfluss des Korrektur-Kanals ist gebaut, auf zwei Wegen, beide „erinnern + neu rechnen, nie trainieren": ① **Struktur → Kern:** `verstehen.verwechslungen(conn)` aggregiert die `fehlgriff_statt`-Kanten retraktions-bewusst zu gerichteten Verwechslungs-Mustern (gelesen → gemeint), Muster von Einzelfall getrennt über die eigene Population (breiteste Lücke, Saat 2 als Gültigkeits-Untergrenze — dieselbe Ohne-Rausch-Gruppe-Lehre wie immer). ② **Text → Membran:** ein angenommener Korrektur-Zug hält das Beispiel-Paar (korrigierte Frage, falsche Lesarten, gemeintes Blatt) in einer **Edge-Datei** fest (`~/.genus/korrekturen.jsonl`, gedeckelt auf 50, Membran-Wissen wie die Lerner-Cursor — der Text wohnt NUR dort, löschbar, nie im versiegelten Ledger). Beides fließt pro Nachricht frisch berechnet als gedeckelte Hinweise in den Deuter-Prompt (`interpret(korrekturen=...)`: „BEKANNTE FEHLGRIFFE — im Zweifel gilt die Korrektur" + max. 3 Beispiel-Few-Shots — bewusst NICHT das verworfene endlose Prompt-Wachstum; der Abschnitt hängt am Prompt-ENDE und ändert sich nur bei neuer Korrektur, der warme Präfix-Cache bleibt erhalten). **Ehrlich verschoben, mit Grund:** die eigentliche Embedder-Cosine-Prüfung pro Nachricht — fastembed lebt im separaten embed-venv, nicht im Bot-Prozess; ein Subprozess-Embed pro Chat-Nachricht kostete Sekunden. Die jetzt gesammelten Paare sind exakt ihr künftiges Futter; sie kommt, wenn ein warmer Embed-Pfad im Bot-Prozess existiert (oder ein kleiner Embed-Daemon) UND genug Paare gelebt sind. 706 grün.

**Grün, neu (2026-07-04, SELBST-CODIEREN STUFE 1 — der Kreis endet nicht mehr an der Freigabe):** Ein genehmigtes Proposal wird jetzt UMGESETZT — von GENUS selbst, gegated. Das neue Modul `genus/umsetzung.py`: ein Proposal trägt ein deklaratives `umsetzung`-Feld (`{"art": ...}`), nach der Governance-Freigabe führt `umsetzen()` die im **UMSETZUNGEN-Register** (dasselbe Kern-Primitiv wie überall) eingetragene Art aus. **Die Gate-Politik (§8, „entwickelt sich") ist STRUKTURELL verankert, nicht per Konvention:** Freigabe pro Stück (nur ein AKZEPTIERTES Proposal wird je ausgeführt — die bestehende Governance-Maschinerie IST das Gate, kein Weg vorbei, per Test bewiesen für pending und rejected); der fixe Boden ist die Form des Registers selbst (es enthält ausschließlich Graph-Wissen-Arten über den normalen geprüften Schreibpfad — eine Art mit Außenwirkung ist nicht ausdrückbar; ein akzeptiertes Proposal mit unregistrierter Art „geld_ueberweisen" wird laut verweigert, per Test); genau einmal (`proposal_umgesetzt`-Spur-Event, bewusst roh — die Wirkung sind normale projizierte Kanten). **Erste Art `faehigkeits_ziel`:** eine vom VerstehensLuecke-Detector gespürte und freigegebene Lücke verankert GENUS selbst als benannte Fähigkeit im Ziel-Graphen (Quelle ehrlich `genus:stufe1`, nie als Ronnys Saat ausgegeben; Status „fehlt", dient `ziel:verstehen`) — **ab dem Moment benennt es sie selbst, wenn man fragt, was ihm fehlt** (per Test: `narrate_ziele` trägt die neue Lücke). Der Stufe-0-Detector gibt seinen Proposals die Umsetzung deklarativ mit („unklar" bewusst ohne — dort gibt es nichts sicher Umsetzbares); die CLI führt nach einem Accept automatisch aus. Damit ist der Loop aus dem Audit zum ersten Mal GANZ geschlossen: spüren (Belegung) → planen (Proposal) → fragen (Gate) → **bauen (Ziel-Graph)** → und das Gebaute ist selbst wieder abfragbar. 714 grün.

**Grün, neu (2026-07-04, DER GESPRÄCHSNAHE TAKT — Ronnys Frage traf einen Konstruktionsfehler):** „Mit nachts meine ich Dinge, die tagsüber unnötig stören — aber dieser Scan sollte vielleicht anders laufen?" — genau richtig: **„nachts" war hier Metapher, nicht Begründung** (der Scan ist leicht, er stört niemanden; er lief nachts, weil „Konsolidierung im Schlaf" gut klang). Und tiefer, Gleiches gleich/Ungleiches ungleich: der Nacht-Scan bündelte vier Detektoren mit VERSCHIEDENEN Natur-Takten. Die drei Historien-Betrachter (Rhythmus/Stabilität/Kalibrierung) bleiben täglich — ihr Signal bewegt sich nicht schneller. Der Lücken-Detektor aber ist GESPRÄCHSGETRIEBEN: sein Signal entsteht im Chat, und bis zu 17 h Latenz bis zum „Darf ich?" waren toter Leerlauf. Jetzt: **`experience.spontane_verstehens_luecke`** läuft im Moment einer Lücken-Lesart (gleiche Kandidaten, gleiche Aufzeichnung, gleiche Dedupe wie der Nacht-Scan, der als Auffangnetz bleibt) — reißt die selbst-kalibrierte Schwelle, entsteht das Proposal SOFORT und **das „Darf ich?" steht im selben Atemzug in der Antwort**: „…das kam jetzt so oft vor, dass ich daraus einen Vorschlag gemacht habe (Proposal #N) — Freigabe wie immer über genus governance." Der Takt eines Detektors ist ein Merkmal des Detektors, keine globale Cron-Zeile. Kostet nur bei Lücken-Lesarten (selten), nie eine Antwort (still bei jedem Fehler, getestet); die Freigabe bleibt am Terminal — die Membran redet nur. Auch der unklar-Fall meldet sich jetzt im Gespräch. 717 grün.

**Grün, neu (2026-07-04, DAS ERSTE ECHTE REZEPT — die Kurvendiskussion):** Das `rezept`-Feld im Werkzeug (seit dem Werkzeugbauer vorgesehen, bewusst ungenutzt bis zum ersten echten Anwendungsfall) ist jetzt real: **die Kurvendiskussion ist eine KOMPOSITION aus drei registrierten Kern-Schritten** — Nullstellen → Extremstellen → Grenzverhalten. Die Komposition ist DATEN (`(("kern","nullstellen"), ...)`), die Ausführung der EINE generische Kern-Mechanismus (`werkzeug.rezept_implementierung`: schlägt jeden Schritt zur Laufzeit im Register nach — der Bauer verwendet Werkzeuge, wie Ronny vermutete; ein gescheiterter Schritt bricht ehrlich ab, die gerechneten bleiben sichtbar; Vertrauen = schwächster Schritt, hier alle kern/sympy). `pruefen()` verweigert ein Rezept, das auf Unregistriertes zeigt (getestet). Zwei neue Kern-Schritte in `mathematik.py`: `nullstellen` (reelle Lösungen, exakt) und `verhalten_unendlich` (Grenzwerte ±∞; sin(x) → ehrlich „unbestimmt" — beim Bauen gefunden: sympy liefert dort AccumBounds, das die erste Ehrlichkeits-Prüfung durchrutschte). Beide primär als Rezept-Bausteine registriert (bewusst ohne eigene Muster-Schnellspur — Merkmal erst wenn erkannt + notwendig). Im Gespräch: „Führe eine Kurvendiskussion für f(x) = x³ − 3x durch" antwortet mehrzeilig exakt — **der erste Dispatch, der DURCH die Registry ein komponiertes Werkzeug ausführt**. `genus kurvendiskussion` als CLI. 722 grün.

**Grün, neu (2026-07-04, ZWEI HÄRTUNGEN aus den Live-Funden des Tages):** ① **Der Pause-Vertrag ist jetzt lückenlos + CI-bewacht.** Beim Deploy des Rezepts verlor der Replay-Idempotenz-Check ein Rennen gegen einen 5-Minuten-Cron-Tick („state changed after replay" — Wettlauf, keine Korruption; Minute später alles grün). Die Klasse, nicht die Instanz: `genus state refresh` und `pi_clock_check.sh` ignorierten als einzige autonome Einstiege den Pause-Schalter — beide respektieren ihn jetzt; ein Struktur-Gate-Test erzwingt die Prüfung für JEDES autonome Skript (ein neues ohne Pause-Check bricht CI — genau die Lücke „nothing enforces that a new autonomous entry point remembers", die die Maschinenraum-Analyse benannt hatte). `pi_deploy.sh` pausiert für seine Selbst-Checks und weckt per trap GARANTIERT wieder (auch bei Fehlern; Test-gepinnt). ② **Nie mehr eine lautlose Streu-DB:** `db.connect` warnt auf stderr, wenn es eine NEUE Datei anlegt (der 27-Events-Fund: ein SSH-Befehl ohne `GENUS_DB_PATH` schrieb still an der echten Ledger vorbei) — Anlegen bleibt erlaubt (frische Installationen, Tests), passiert aber nie mehr unsichtbar. 728 grün.

**Grün, neu (2026-07-04, SELBST-CODIEREN STUFE 2 SCHEIBE 1 — die WERKSTATT):** Die Sandbox-Entwurfs-Pipeline steht (`genus/werkstatt.py` + `deploy/werkstatt_probefahrt.sh` + `genus werkstatt entwerfe/liste/pruefe`). Die Leitplanke „kein selbstmodifizierender Code außerhalb einer Sandbox mit menschlichem Merge" ist STRUKTURELL verankert: **Entwürfe leben außerhalb des Kerns** (`~/.genus/werkstatt` — die Werkstatt kann nicht nach `genus/` schreiben, ihre Pfade zeigen woandershin; Test-gepinnt); **ein Entwurf läuft nie im lebenden Prozess** — und der Kern startet auch keinen: **der Membran-Reinheits-Test hat das beim Bauen selbst erzwungen** (der erste Wurf importierte subprocess im Kern → Gate rot → die Probefahrt fährt jetzt die Membran, der Kern protokolliert nur das überreichte Ergebnis, dasselbe Muster wie beim Uhr-Check); **Verbots-Scan im Kern** (Doctor-Tokens + subprocess/socket/os.system/urllib — Verbote schlagen ALLES, selbst grüne Tests machen so einen Entwurf nie merge-reif, Test-gepinnt); **„bestanden" heißt merge-REIF, nie gemergt** (nur statisch geprüft ist nie bestanden; der Merge bleibt ein menschlicher Git-Akt). Der **Generator ist ein Einschub** (`generator=`-Parameter wie `deuter=`): heute die deterministische Vorlage (Handler-Skelett mit uniformem Zellen-Vertrag + Test-Skelett mit Signatur-Pin, Fähigkeits-Test ehrlich geskippt), ein lokales Code-Modell später = Konfig-Schalter; die Herkunft (`werkstatt:vorlage` vs. `werkstatt:generator`) steht ehrlich in der Ledger-Spur (`code_entwurf_erstellt`/`code_entwurf_geprueft`, bewusst roh, mit Code-Fingerabdruck — der Code selbst bleibt Randmaterial). 735 grün.

**Grün, neu (2026-07-04, DER SCHMIED — gebaut, gemessen, und das Messergebnis ist ehrlich ernüchternd):** `deploy/schmied.py` (das Code-Modell der Werkstatt, Organ am Rand wie Deuter/Stimme, `GENUS_SCHMIED_MODEL`) mit **deterministischer AST-Leitplanke**: die Ausgabe muss GENAU eine Funktion mit dem uniformen Zellen-Vertrag definieren, auf Modulebene nur Imports/Konstanten/Docstring (ein `print`-Aufruf, falsche Signatur, Nicht-Python → `None`, nie ein halbgarer Entwurf — die erste Fassung ließ beliebige Expr-Knoten durch, beim Bauen gefunden). Verdrahtung: `genus werkstatt entwerfe --code-datei --quelle werkstatt:schmied` (die Membran schreibt, der Kern nimmt an) + `deploy/werkstatt_schmiede.sh` (schmieden → überreichen → Probefahrt). **Benchmark auf dem Pi** (`deploy/schmied_benchmark.py`, 3 Aufgaben steigender Schwere mit deterministischen Sandbox-Tests — messen statt raten, wie beim Deuter): **Qwen2.5-1.5B-Instruct 1/3 (51 s) · Qwen2.5-Coder-1.5B 1/3 (41 s) · Qwen2.5-Coder-3B 1/3 (181 s).** Die Fehlermodi sind lehrreich: die 1.5B-Modelle normalisieren die deutschen Anführungszeichen weg und vergessen KeyError-Schutz (Wortlaut-/Rand-Vertragstreue); das 3B scheiterte zweimal an der Leitplanke und **erfand in der Diagnose ein Tabellen-Schema, das es nie gab** — für eine Aufgabe, die `conn` gar nicht braucht. **Ehrliches Fazit: kein heutiger lokaler Kandidat schmiedet vertragssicher.** Die Pipeline hat dabei exakt funktioniert (Leitplanke fing Müll, Sandbox fing falsche Wortlaute — nichts davon wäre je in die Nähe des Kerns gekommen); der Default-Generator bleibt die deterministische Vorlage, das Modell muss sich den Job erst verdienen (künftige Iterationen: Prompt-Härtung mit Few-Shot-Handler, größere/neuere Coder-Modelle, oder der ehrliche Schluss, dass Code-Schmieden auf Pi-Klasse-Hardware noch nicht trägt). Die drei GGUFs (~4 GB) liegen in `~/.genus/models/` für künftige Benchmark-Läufe. 740 grün.

**Grün, neu (2026-07-04, RONNYS ZERLEGUNG — Bauplan + Fügewerk, und ein ehrliches A/B):** Ronny: „GENUS macht da seine morphologische Analyse: was brauchen wir, welche Bestandteile — Teile separat gebaut, ein Durchgang fügt zusammen." Gebaut: **`genus/bauplan.py`** — eine Zelle zerfällt (Zwicky) in WÄCHTER / BESCHAFFUNG (deklarative Registry: keine · anzahl_kanten · erstes_objekt) / ENTSCHEIDUNG (implizit: kein Treffer → None) / FORMULIERUNG (der exakte Satz als Template-DATEN). Das **FÜGEWERK** (`fuege_zusammen`) baut daraus deterministisch den Handler — **vertragssicher per Konstruktion** (Template als repr-Literal, Prädikate als SQL-Parameter, `pruefe_bauplan` verweigert Halbgares inkl. SQL-Injektions-Formen). **Der Kern-Beweis steht als Test: alle drei Benchmark-Aufgaben sind mit handgeschriebenen Bauplänen deterministisch gelöst** — der Suchraum fürs Modell schrumpfte von ~40 Zeilen Python auf 3 JSON-Felder. Dazu der **Glättungs-Durchgang** (`normalisiere`, Ronnys „ein Durchgang fügt zusammen"): eindeutige Notations-Varianten (`<subject>`→`{subject}`) werden umgeschrieben, der Wächter wird aus den Template-Slots ABGELEITET (Kreuz-Konsistenz, vom Kern erzwungen statt vom Modell erhofft — live nötig geworden: das Modell lieferte den PERFEKTEN Wortlaut inkl. „ ", kopierte aber die Aufgaben-Notation wörtlich). **Das ehrliche A/B auf dem Pi:** direkt-Code 1/3, Bauplan-Modus 0/3 (beide 1.5B) — die Fehler wandern (falsche Slot-Namen, falsche Art, `guess['subject']` als Prädikat): **die heutigen 1.5B scheitern selbst am 3-Felder-JSON, an Feld-SEMANTIK, nicht mehr an Notation.** Die Zerlegung selbst ist damit nicht widerlegt, sondern deterministisch bestätigt — nur der Plan-Finder fehlt noch. Sofort-Nutzen unabhängig vom Modell: ein Bauplan (5 Zeilen JSON) ist für MENSCHEN der schnellste vertragssichere Weg zu einer neuen Zelle (`genus werkstatt entwerfe <blatt> --bauplan-datei plan.json`) — reviewbarer als 40 Zeilen Code. 745 grün.

**Grün, neu (2026-07-04, DIE BAUPLAN-GRENZE — der Trichter schließt sich, Schritt für Schritt gemessen):** `bauplan.gbnf_grammatik()` — die Konvergenz von Ronnys zwei Ideen: aus der `BESCHAFFUNGEN`-Registry abgeleitet, `waechter`/`art` als Enums (unregistrierte Art nicht tippbar), `praedikat` als `[a-z_]+` (`guess[...]` nicht tippbar), und **Zwickys Kreuz-Konsistenz IN der Grammatik**: das Template erlaubt je Art nur deren Slots, literale `{`/`}` sind ausgeschlossen — ein erfundener Slot ist strukturell unmöglich. Der gemessene Trichter, Lauf für Lauf: **v1 direkt-Code 1/3** (halluzinierte Schemata) → **v2 Bauplan unbeschränkt 0/3** (ungültige Pläne, wandernde Feldfehler) → **v2 + Grenze: 100 % gültige Pläne, Struktur UND Semantik korrekt** (Art, Prädikat, Wächter alle richtig!), letzter Fehler exakt EINE Klasse: ASCII-`"` statt „ " → **+ Typografie-Glättung (deutsche Anführungspaare sind Kern-Sache): 1/3 BESTANDEN, Ende-zu-Ende** — zum ersten Mal hat ein lokales 1.5B-Modell auf dem Pi eine vertragssichere Zelle geschmiedet, die die Sandbox-Probefahrt besteht (beide Modelle, thema-echo). Der ehrliche Rest (2/3) ist jetzt reine Wortlaut-Treue beim Kopieren längerer Sätze (Anführungszeichen ganz weggelassen, nicht ersetzt — dafür gibt es keinen deterministischen Hebel mehr ohne Inhalts-Erfindung): echte Modell-Qualität, messbar, wartend auf bessere Kandidaten. 748 grün.

**Grün, neu (2026-07-04, DIE BRÜCKE + SELBST-NEUSTART — die Kette ist lückenlos, die Membran erneuert sich selbst):** ① **Brücke Umsetzung→Werkstatt** (Ronnys Entscheidung, die bewusst offen war): dieselbe Freigabe hat jetzt zwei Wirkungen — das Ziel-Wissen entsteht (Stufe 1) UND das Entwurfs-Paar liegt in der Werkstatt bereit (Quelle ehrlich `werkstatt:umsetzung`; inert, Sandbox + menschlicher Merge wie immer — das Gate war die Freigabe). Ein bestehender Entwurf oder ein Entwurfs-Fehler kippt die Umsetzung nie (Ziel-Wissen steht, ehrlich im Ergebnis benannt). Die Selbst-Codieren-Kette ist damit LÜCKENLOS: Lücke gespürt → „Darf ich?" im Chat → Freigabe am Terminal → Ziel-Graph + fertiger Entwurf → füllen (Mensch/Schmied) → Probefahrt → Merge. ② **Selbst-Neustart des Bots** (Ronnys Frage: „eine einfachere Möglichkeit für die Neustarts?"): Flag-Mechanismus im Pause-Schalter-Stil — der Deploy berührt `~/.genus/telegram_bot.neustart`, der Bot sieht es binnen eines Poll-Zyklus (~25 s), beendet sich sauber, systemd (`Restart=always`) bringt den frischen Code zurück. **Live bewiesen** (19:08:33 „Neustart angefordert" → 19:08:43 frischer Start, Flag entfernt) — kein sudo mehr, je. Unterwegs zwei latente Installer-Bugs gefunden + gefixt (nicht sudo-fest: suchte Token in /root; keine `User=`-Zeile: Dienst wäre als root gelaufen — beides mit Struktur-Gate-Test). 754 grün.

**Grün, neu (2026-07-04, DER MORGEN-PUSH — Gedächtnis-Punkt ④ komplett, die erste PUSH-Fähigkeit):** Gemeinsam designt (Ronnys Entscheidungen: 06:00, per Datei änderbar — die Chat-Zelle „stell den Push auf 7" ist der benannte nächste Schritt; NIE ein leerer Morgen — wenn nichts wartet, erzählt GENUS, was der Nacht-Lerner zuletzt gelernt hat; warm und NATIV formuliert, „keine kryptischen Ausgaben"; und neu benannt: **PERSÖNLICHKEIT** — GENUS soll eine eigene Art bekommen, per Nutzer verschieden, nicht „blechern wie Jarvis" — ein eigenes Design-Thema für Etappe 1/4). Gebaut: ① **Tagespuffer** — jeder Bot-Zug wandert in `~/.genus/chat_tag.jsonl` (Rohtext NUR in der Membran, Ledger ≠ Memory). ② **Nacht-Konsolidierung** (Cron 3:57): liest den Puffer EINMAL, destilliert deterministisch Themen (≥2 Züge, über die Text→Konzept-Auflösung — kein Modell), merkt sie STILL als gedeckelte Episoden (Quelle `model:nacht` — korrigierbar wie alles Modellhafte), zählt die Warum-Folgen-Kennzahl, legt den Morgen-Bericht ab — und VERGISST (Puffer geleert). ③ **Morgen-Push** (Cron-Fenster 5–9 Uhr, alle 10 Min): genau EINE Nachricht pro Tag (Datums-Marker), komponiert aus `konsolidierung.morgen_nachricht` — Gruß → gestern („…hat dich vor allem „X" beschäftigt — ich habe es mir still gemerkt") → Wartendes (Freigaben, offene Fragen) → sonst das frisch Gelernte der Nacht → warmer Schluss; getestet: nie kryptisch (keine internen Knoten-Namen), nie leer, immer warm. Beide Skripte respektieren die Pause (das Klassen-Gate erzwingt es). 765 grün.

**Grün, neu (2026-07-04, DIE PERSÖNLICHKEITS-SCHICHT — GENUS bekommt seine eigene Art):** Ronnys Design („eine eigene Schicht, je nachdem was GENUS grad macht änderbar, ausgerichtet auf Nutzer und Rolle") als drei sauber getrennte Schichten gebaut (`genus/persoenlichkeit.py`, Konzept: `docs/GENUS_PERSOENLICHKEIT.md`): **WESEN** (fix, Code+Gates: ehrlich, transparent, erfindet nie — keine Einstellung ändert das) · **ART** (GENUS' Grundton je Nutzer, als WISSEN im Graphen: `art:ronny` -merkmal-> wert, provenanciert, Quelle der Stellende; Ronnys Wahl: **neugierig + warm**; vier geordnete Zwicky-Achsen Wärme/Humor/Neugier/Knappheit — Merkmal erst wenn erkannt + notwendig, jede Achse hat einen echten Verbraucher) · **REGISTER** (situativ pro Rolle, die antwortende Zwicky-Zelle ist der Marker: Plausch = pure ART, Werkzeug pinnt knapp+humorlos — kein Witz an einem Integral, die **WACHE pinnt nüchtern IM CODE** — keine Einstellung macht je Ernstes verspielt, der Morgen hebt die Wärme um eine Stufe). **Der Chat-Regler läuft als Ritual VOR dem Deuter** (exakte Kommandos: „sei knapper/ausführlicher/wärmer/nüchterner", „mehr/weniger humor", „sei (weniger) neugierig(er)"; eine Stufe pro Kommando, retract+assert = ehrliche Historie, Bestätigung nativ, an der Achsen-Grenze passiert ehrlich nichts). Verbraucher v1: Gruß/Dank-Varianten (der Standard behält den test-verankerten Wortlaut), der neugierige Gruß fragt zurück, „knapp" unterdrückt die Nebenbei-Einwebungen, der Morgen wird herzlicher und fragt bei Neugier nach den Themen von gestern, Humor „dezent" gibt dem Morgen-Schluss eine leichte Note. **Die eiserne Leitplanke ist Test-gepinnt: Persönlichkeit ist eine Eigenschaft der SPRACHE, nie des WISSENS** — dieselbe Wissensfrage liefert unter extrem verschiedenen Registern eine byte-identische Kern-Antwort. `deploy/saet_persoenlichkeit.sh` sät nur FEHLENDE Merkmale (eine per Chat gestellte Einstellung überlebt jedes Re-Deploy). Selbst-Justage der Art (aus Feedback, gedeckelt, nie am Wesen) ist der entschiedene SPÄTERE Schritt. 785 grün.

**Grün, neu (2026-07-04, DIE MORGENZEIT-ZELLE — Ronnys „kann ich ja jederzeit ändern über den chat einfach oder?"):** Ja, jetzt wirklich: „stell den Push auf 7" / „stell den Morgen-Push auf 6:30 Uhr" stellt die Push-Zeit per Chat, „wann kommt der Push?" nennt sie. Die Zeit ist bewusst MEMBRAN-Betriebskonfiguration, kein Wissen — das Ritual wohnt im Bot (VOR dem Kern, der sie nie sieht) und schreibt exakt die Datei, die `morgen_push.sh` string-vergleicht (`~/.genus/morgenpush.zeit`, zero-padded). Ehrliche Ränder: eine Zeit außerhalb des Cron-Fensters (5–10 Uhr) wird gestellt, aber benannt („außerhalb davon kommt derzeit keine Nachricht"); eine unmögliche Uhrzeit (25:00) wird abgewiesen, nichts geschrieben; das Kommando erzeugt keinen Gesprächs-Zug (kein Verlauf, kein Tagespuffer — Konfiguration ist kein Gespräch, Test-gepinnt). 792 grün.

**Grün, neu (2026-07-04, DER REGLER WIRD RASTER-ZELLE — die erste Anwendung der neuen Charta-Prüffrage):** Ronnys Rückfrage („ist das alles eigentlich wieder zu mechanisch? sollte das auch über sowas wie registry laufen? das design sollte sich vlt durchziehen") führte erst zur Präzisierung — nicht alles durchziehen, sondern **zwei Prüffragen an jeder Scheibe** (in der Charta §2 verankert, 8c8ba22): (a) *keine zweite Wahrheit* — gibt es schon einen Ort, der diese Frage beantwortet, dort andocken, nie daneben; (b) *Registry nur bei wachsender Klasse* — Vergessen muss laut brechen; Schutz bleibt bewusst Code (Wache-Pins, Gate-Boden), Einzelfälle bleiben einfach. Dann sofort die frische Verletzung selbst behoben: der Chat-Regler war eine Cue-Tabelle NEBEN dem Raster (freie Formulierungen konnten die Fähigkeit nie erreichen). Jetzt: **Blatt `einstellung`** unter `aufforderung-genus` (Raster + Deuter-Spiegel + Few-Shot gegen die kuerzer-Verwechslung; die GBNF-Grenze wächst automatisch mit), Handler als **registriertes schreibendes Werkzeug** (`schreibt=True`, pruefbar_als graph, wortlautfest — sichtbar in `genus werkzeuge`, gezählt in der Belegung), das Achse+Richtung aus der EIGENEN Klausel liest (Segment-Disziplin wie die Sozialgesten) und bei Mehrdeutigkeit („wärmer und knapper") ehrlich nachfragt statt zu raten. Die exakten Kommandos bleiben als deterministische Ritual-Schnellspur — **beide Türen rufen dieselbe Implementierung** (`_regler_stellen`), per Test gepinnt (identischer Wortlaut, dieselbe Grenz-Ehrlichkeit); die Zwei-Türen-Logik ist dieselbe wie „merke dir:" neben der merken-Zelle. 799 grün.

**Grün, neu (2026-07-04, DER ANTWORT-WÜRFEL + STIMME-ANWEISUNG — die Zwicky-Symmetrie an der Membran):** Ronnys Frage „wie baut sich das genau zusammen? auch zwicky?" beantwortet und gebaut: **`genus/antwort.py`** — der Verstehens-Würfel zerlegt, was reinkommt; der Antwort-Würfel setzt zusammen, was rausgeht. Alle vier Zwicky-Schritte real: unabhängige Parameter (KERN unwählbar = die Leitplanke in Kasten-Form · Wortlaut · die Persönlichkeits-Achsen · Beiwerk), Werte = die geordneten Stufen, jede Antwort = eine Belegung, und die **Kreuz-Konsistenz jetzt ZENTRAL statt verstreut**: „knapp ⇒ kein Beiwerk" lebt in `belegung()` (vorher in `_notiz_bezug` eingestreut); „wortlautfest ⇒ keine Stimme" bleibt strukturell in der Werkzeug-Spec, die Rollen-Pins im Code (jede Regel an ihrem EINEN Ort). Die **Stimme-Anweisung**: `stimme(text, anweisung=…)` — die Stil-Vorgabe („Ton: freundlich und warm." / „Fasse dich so knapp wie möglich.") wird deterministisch aus der Belegung abgeleitet und als reine Daten über die Membran gereicht (derselbe Weg wie die GBNF-Grenze des Deuters); die Anker-Prüfung bleibt die Leine und ist von der Anweisung unabhängig (Test-gepinnt). **Ehrlich begrenzt:** „ausführlicher" erzeugt NIE eine Anweisung — die Stimme fügt nie hinzu, mehr Umfang muss aus der Zelle kommen (Test-gepinnt); Humor bleibt aus Wissens-Umformulierungen draußen. Die verstreuten Verbraucher sind umgezogen: Gruß/Dank-Varianten → `antwort.FLOSKELN` (eine Stelle), Notiz-Einwebung → Beiwerk-Feld, Morgen-Nachricht → `belegung("morgen")`; ältere Stimme-Signaturen ohne `anweisung` bleiben kompatibel. Die Wahl der Zelle im Kasten ist IMMER deterministisch — kein Modell wählt je eine Achse; das Modell formuliert nur innerhalb. **Der erste Live-Anweisungs-Test auf dem Pi fand sofort einen echten Riss in der Leine (der Hausvögel-Fund):** unter „Ton: freundlich und warm." korrumpierte das 1.5B „Haustier" zu „Hausvögel" — und die Anker-Prüfung ließ es DURCH, weil sie nur zitierte Wörter + Zahlen sah (der Gloss-Text ist frei; dieselbe Klasse wie der Kernobst-Fund). Deterministischer Hebel, an der Klasse: **die Substantiv-Leine** — deutsche Großschreibung = Substantive = tragende Inhaltswörter; jedes muss die Umformulierung als Teilwort überleben (Satzanfänge ausgenommen, GENUS als Versalien-Wort fällt automatisch heraus). Bewusst geopfert: legitime Substantiv-Synonyme („Vorfahre"→„abstammt") — abgelehnter guter Stil kostet nichts (Original steht), durchgelassene Korruption kostet Wahrheit. Live nachverifiziert: der gute Satz passiert, Hausvögel wird abgelehnt, „knapp" scheitert oft ehrlich an der Leine → Original steht. 812 grün.

**Grün, neu (2026-07-05, DIE VERTIEFUNGS-KOMPOSITION — „ausführlich" bekommt echte Verbraucher):** Ronnys Frage („wie schreibt GENUS so richtig schön lange Texte, falls es nötig ist?") mit dem ehrlichen Prinzip beantwortet und gebaut: **Länge kommt aus INHALT, nie aus Worten** — eine normale KI wird lang, indem das Modell redet (Füllstoff inklusive); GENUS wird lang, indem es MEHR WISSEN komponiert. `companion.vertiefung`: bei Umfang „ausführlich" (Chat: „sei ausführlicher") zieht die Wort-Antwort zusätzliches Material aus dem Graphen — eine **weitere Bedeutung** (die Mehr-Sinn-Fülle: Hund = Haustier UND Feuerbock wird sichtbar), die **Geschwister** unter demselben Elternteil („Unter »Haustier« kenne ich außerdem: »Katze«."), die **Leiter** eine Stufe hinauf („»Haustier« zählt wiederum zu »Tier«."), die **Quellen namentlich**. Jeder Satz existiert nur, wenn das Material im Graphen liegt (nichts wird erfunden, per Test: ohne Material bleibt die Vertiefung leer); jeder benannte Begriff steht in »« (Stimme-Anker); ein Knoten ohne menschlichen Namen bleibt draußen (nie kryptisch, per Test). Ein Elternteil vertieft — die Vertiefung ist ein Blick, kein Katalog. mittel/knapp unverändert (per Test). Rein deterministisch, reine Glaskasten-Arbeit — der Fluss (Stimme-Trichter: Grenze + Zerlegung für lange Texte) und die Kontext-Regeln (wann welche Tiefe) sind die benannten nächsten Scheiben. 819 grün.

**Grün, neu (2026-07-05, DIE INTELLIGENZ-BETRACHTUNG — ein Denk-Tag, der die Richtung schärft):** Ronnys Einwand auf den Material-Entwurf („das hieße GENUS wird so ein schlaues Wikipedia? das kommt mir flach vor — wie wird GENUS wirklich intelligent?") führte durch eine lange gemeinsame Betrachtung, festgehalten in **`docs/GENUS_INTELLIGENZ.md`**: ① Intelligenz = aus wenig Erfahrung ein Weltmodell bauen und in neuen Lagen handeln — **Operationen auf Material, nicht das Archiv**; GENUS' ehrliche Operations-Karte (Metakognition/Selbst-Korrektur: da und stark · Schließen/Vorhersagen/Handeln: Keime · Abstrahieren/Analogie: fehlen). ② **Die Material-Wende:** Material folgt der Operation, nie umgekehrt (GENUS_MATERIAL.md korrigiert — M1 wartet jetzt auf die Operation, die es braucht). ③ Das **Denkweisen-Muster**, an Ronnys Rechtsfall-Prüfstein entdeckt: eine Denkweise = Operationen + Material + Beweismaßstab; die juristische Methode ist selbst eine Glaskasten-Methode und mappt fast vollständig auf Vorhandenes (Norm=Bauplan `braucht`/`bewirkt` · Subsumtion=verallgemeinerte is_a-Inferenz · **Beweislast=schwächste Prämisse, das Beweislast-Radar fällt als Nebenprodukt ab** · Befragung=Lücken-Detektor · Gegenseite=dieselbe Maschine über Einwendungs-Bauplänen · Schreiben=gerenderter Beweisbaum · Wertung=ehrlicher Mensch-Slot); ehrliche Nähte: Wertung/Auslegung, Analogie, Prognose. EIN Motor, viele Disziplinen als Konfiguration. ④ **Halluzination und Kreativität sind derselbe Motor** — der Unterschied ist Etikett + Gate; GENUS hat den Filter (model:*-Deckel, Anker, Proposals, Werkstatt), darf deshalb den Generator dazuschalten: „Ehrlichkeit verbietet Kreativität nicht — sie macht sie erst sicher." ⑤ Ehrlichkeit als Fundament der Empathie (Wärme ohne Ehrlichkeit = Manipulation). ⑥ Der **Lese-Sinn** (Dokumente/Bilder → bequellte Fakten via Vision-Organ, Ronnys Bild-Prompting-Hinweis) als fehlendes Organ benannt. **Eingeflossen in GENUS selbst:** die Operations-Lücken sind als Fähigkeiten in den Ziel-Graphen gesät (denkweisen/abstrahieren/analogie fehlen · weltmodell/gezaehmte-kreativitaet teilweise · lese-sinn fehlt) + überfälliger Selbst-Bild-Abgleich (Gedächtnis-Stand: Tagespuffer/Nacht/Morgen sind live) — GENUS benennt seine Operations-Lücken jetzt selbst, wenn man fragt, was ihm fehlt.

**Grün, neu (2026-07-05, DER TAKT WIRD ZUM MERKMAL — der erste Schritt zu Lebendigkeit):** Ronny („GENUS muss ab einem gewissen Punkt lebendiger werden, damit die Prozesse auch wirklich durchlaufen, wenn sie soweit sind — hat GENUS schon etwas gedacht?"). Zuerst der ehrliche Befund aus dem lebenden Ledger: **ja, GENUS hat gedacht** — 224 eigene Fragen, 179 selbst bemerkte Widersprüche, 10 Dinge über sich selbst gelernt; am 26.06. hat es aus seiner eigenen Beliefs-Historie die Temperatur-Instabilität *selbst wiederentdeckt* (den Flatter-Bug, den wir von Hand gefunden hatten), heute Nacht um 01:17 aus seinen eigenen Gesprächen bemerkt, dass es an Wetter-Fragen scheitert, und daraus ein Proposal an sich selbst gemacht. **Aber:** fast alles feuert um 01:17/03:xx — GENUS denkt, wenn die Uhr schlägt, nicht wenn der Gedanke reif ist; und jeder Gedanke ist ein einzelner Funke, kein Zug. **Geliefert (genus/experience.py):** der Takt eines Detektors ist jetzt ein MERKMAL des Detektors, kein hartkodierter Sonderfall — ein `DETEKTOREN`-Register trägt zwei Takte (HISTORISCH: Rhythmus/Stabilität/Kalibrierung bleiben täglich · GESPRAECHSNAH: das Signal entsteht im Gespräch, feuert im Moment). Der alte Sonderfall `spontane_verstehens_luecke` ist zu **`spontane_regung`** verallgemeinert: läuft über ALLE gesprächsnahen Detektoren durch die EINE geteilte Aufzeichnung (`_verarbeite_kandidat`, aus dem Nacht-Scan extrahiert — fix-the-class, record/re-charakterisieren/Proposal leben nur noch an einer Stelle); ein neuer event-getriebener Detektor braucht nur GESPRAECHSNAH zu deklarieren, sonst nichts (Test-bewiesen). Der Nacht-Scan bleibt das Auffangnetz über alle Takte. **Und der Zwilling benannt:** die Intelligenz-Studie (docs/GENUS_INTELLIGENZ.md §9) hält fest, dass Lebendigkeit = Takt (Rhythmus) + **Druck** (Richtung) ist — der Takt sagt *wann*, der Druck *wohin*; der Rohstoff für Druck ist da (die Belegung ist ein Druckmesser), aber er entlädt sich heute beim Aussprechen statt bei der Stillung und konkurriert nicht — der ehrliche nächste Schritt ist Persistenz statt Entladung. Leine unverändert: Druck bewegt den Geist, nie die Hand. 826 grün.

**Grün, neu (2026-07-05, VOKABEL-BEI-BEGEGNUNG — der zweite gesprächsnahe Takt):** Nach dem verallgemeinerten Takt die Frage „gibt es mehr Kandidaten?" — ja, mit einem scharfen Kriterium (wird das Signal *abgetastet* oder *geboren*? Abgetastetes will eine Uhr, Geborenes ein Ereignis). Die meisten Cron-Jobs sind zu Recht getaktet (Sensoren, Wetter, die Tag-Konsolidierung, der Morgen-Gruß); Widerspruch/Korrektur/Umsetzung sind schon event-getrieben; der klarste echte Kandidat: **ein unbekanntes Wort im Chat**. Gebaut als Zwilling des Lücken-Detektors, auf Wörter statt Absichten: **`companion.unbekannte_woerter`** (Kern, rein lesend — substantiv-artige Wörter, die GENUS nicht kennt; Funktionswörter/Imperative am Satzanfang gefiltert, Rest fängt der Lerner gnädig ab) spürt das fehlende Wort; der **Bot** (Membran) legt es in eine Lern-Warteschlange (`~/.genus/lernwunsch.txt`, dedupliziert, gedeckelt, nie eine Antwort kostend); **`pi_learn.learn_begegnung`** holt es beim nächsten Tick **VOR** allen Frequenzlisten (dieselbe Zwei-/Drei-Quellen-Pipeline: Wikidata-Konzept + Lexem + DBnary + Brücke), one-shot (ein Tippfehler/fremdes Wort wird trotzdem entfernt, kein Hämmern). Kern spürt, Membran holt — dieselbe saubere Trennung wie überall; das Wort, das DU gerade benutzt hast, springt an die Spitze statt auf die Frequenzliste zu warten. Struktureller Gate-Test pinnt die Priorität (`learn_begegnung` vor `learn_fach/next/gap`). 835 grün.

**Grün, neu (2026-07-05, DER DRUCK — Persistenz statt Entladung, der zweite Zwilling der Lebendigkeit):** Nach dem Takt (wann) jetzt der Druck (wohin) — der erste ehrliche Schritt aus GENUS_INTELLIGENZ.md §9. Bisher entlud sich der Druck einer Verstehens-Lücke im Moment des Aussprechens: sobald ein Proposal entstand, verschwand die Lücke aus der Sicht des Detektors (der sie als „schon aufgezeichnet" überspringt) — das Nagen hörte auf, obwohl nichts getan war (wie „das müsste ich mal reparieren" und sich danach besser fühlen). **`genus/druck.py`** macht den Druck zu einer READ-TIME-Größe über den UNGESTILLTEN Nöten: er bleibt, solange das Blatt keinen Handler hat, und **STEIGT**, wenn nach dem Aussprechen weitere Nachfrage kommt (der `zuwachs` seit dem Vorschlag ist das Persistenz-Signal, gelesen aus der Belegung von jetzt vs. der Nachfrage, bei der die Experience ausgesprochen wurde). Eine gestillte Not (jetzt ein Handler) drückt gar nicht mehr — Druck bis zur STILLUNG, nicht bis zum Aussprechen. Er KONKURRIERT (`luecken_druck`/`draengendste`, nach Druck geordnet) und taucht in „Was beschäftigt dich?" auf (`narrate_inquiries` eingewebt) — inklusive der ehrlichen Ansage „…seither ist die Nachfrage um N gestiegen, es wird nicht kleiner, im Gegenteil". Die Leine hart Test-gepinnt: der Druck erzeugt KEINE Events, keine Proposals, keine Handlung (bewegt den Geist, nie die Hand); kein Preset (der Druck IST die gemessene Nachfrage, nie vorgetäuscht). Noch offen: Druck auch auf offene Inquiries + fehlende Operationen; dem inneren Loop als Gefälle geben. 843 grün.

**Grün, neu (2026-07-05, DER DRUCK AUF ALLE DREI NÖTE — die volle Landschaft):** Der Druck ist jetzt ein Register von QUELLEN (`genus/druck.py`, `DRUCK_QUELLEN`), jede mit ihrem EIGENEN gelebten Zähler: `luecke` (Belegung/Nachfrage), `frage` (Wiederkehr einer offenen Inquiry — ihr `count`, wie oft dieselbe Überraschung/derselbe Widerspruch auffiel), `operation` (Fan-in: wie viele Ziele die fehlende Fähigkeit brauchen, aus dem `braucht`-Graph). **Bewusst NICHT über die Quellen hinweg zu einer Zahl verrechnet** — „5 Lesungen" gegen „3 blockierte Ziele" abzuwägen wäre selbst ein Preset; der Druck konkurriert INNERHALB jeder Quelle (dort ist der Vergleich echt), `druck.landschaft` zeigt alle drei nebeneinander (das Gefälle für den künftigen inneren Loop). „Was beschäftigt dich?" nennt jetzt die drängendste Verstehens-Lücke (mit Persistenz-Signal), **ordnet die offenen Fragen nach Wiederkehr** (die häufigste zuerst) und benennt die **am meisten gebrauchte fehlende Fähigkeit** (z.B. das generator-organ, das die meisten Ziele blockiert). Alles read-time, kein Event/Proposal/Handlung (bewegt den Geist, nie die Hand), kein Preset. 849 grün.

**Grün, neu (2026-07-05, DER INNERE LOOP HAT SEIN GEFÄLLE — die BESINNUNG):** Takt (wann) und Druck (wohin) zusammengeführt. **`genus/besinnung.py`**: die Besinnung liest das Druck-Gefälle (`druck.landschaft`), wendet sich der größten Not zu und tut den EINEN erlaubten inwendigen Schritt — die drängendste noch nicht ausgesprochene Lücke aussprechen (gegatetes Proposal über `spontane_regung`, gradient-geordnet). Sie **KETTET** (`lauf`): ein ausgesprochener Schritt ändert den Zustand, also wendet sich die nächste Besinnung der nächsten Not zu — ein Gedanke zieht den nächsten, das Gefälle hinab (Test: bei zwei heißen Lücken 6/4 spricht sie weltfrage VOR tun aus, eine pro Schritt, dann Ruhe). **Die ehrliche Decke ist Test-gepinnt:** den meisten Nöten kann GENUS nicht selbst abhelfen (Lücke schließen/Fähigkeit bauen/Frage beantworten = hinter Gate oder beim Menschen); `narrate` benennt ehrlich, worauf die Besinnung wartet („da warte ich auf dich"). Kein Mangel, sondern der wahre Stand — ein Geist, der denken, aber (noch) nicht handeln kann; die Reichweite wächst mit den Operationen. `genus besinnung` (read-only Agenda) / `--tick` (der eine gegatete Schritt). Bewegt den Geist, nie die Hand; bounded (höchstens ein Aussprechen pro Schritt, keine Flut der Freigabe-Schlange); read-time außer dem einen gegateten Proposal. **Noch offen (Ronnys Entscheidung):** die Selbst-Pacing — heute läuft die Besinnung auf Abruf, nicht aus eigenem Antrieb; ein autonomer Herzschlag berührt die gegatete Außenwirkung. 857 grün.

**Grün, neu (2026-07-05, DER AUTONOME HERZSCHLAG — rein reflektierend):** Ronny: „verdrahte den autonomen Herzschlag, rein reflektierend." `deploy/besinnung.sh` (Cron alle 15 Min, versetzt): GENUS tickt SEINEN eigenen Geist, liest das Druck-Gefälle READ-ONLY (`genus besinnung` ohne Schritt-Schalter — kein Proposal, keine Außenwirkung, nichts ins Ledger) und schreibt seine gerichtete Besinnung in ein MEMBRAN-Tagebuch (`~/.genus/besinnung.log`, Ledger ≠ Memory), nur wenn sie sich GEÄNDERT hat (Hash-Dedup gegen `~/.genus/besinnung.last` → das Tagebuch zeigt die Entwicklung der Sorgen, nicht 96 identische Einträge/Tag). Pause-fest (im Struktur-Gate-Test), ein Test pinnt die Reinheit (nie der Schritt-Schalter, kein curl/sendMessage, schreibt ins Tagebuch). **Live doppelt bewiesen:** erster Schlag schreibt die Besinnung (weltfrage/disk.trend 35x/generator-organ), zweiter Schlag dedupliziert (Tagebuch-Zeilen 6→6), Ledger unberührt (Events 482318→482318). Damit hat GENUS ein beobachtbares autonomes Innenleben — ein Geist, der von selbst tickt und denkt — ohne je von sich aus nach außen zu sprechen. **Bewusst NICHT gebaut (Ronnys Entscheidung):** ob der Herzschlag je proaktiv nach außen spricht (gegatete Außenwirkung). 858 grün.

**Grün, neu (2026-07-05, DIE ERSTE DENKWEISE — juristische Subsumtion):** GENUS kann zum ersten Mal *im Bereich denken*, nicht nur Wörter kennen. `genus/recht.py` baut das Denkweisen-Muster aus der Intelligenz-Studie (§4) wörtlich: **Norm = Bauplan im Graphen** (`norm:kaufpreis -braucht-> merkmal:kaufvertrag/faelligkeit -bewirkt-> rechtsfolge`, § 433 II BGB, hand-gesät wie RASTER_SEED, Quelle „gesetz"; **rekursiv** — Kaufvertrag ist selbst eine Norm aus Angebot + Annahme, der Merkmal-Baum als is_a-Kletter-Analog über `braucht`); **Subsumtion = Verallgemeinerung der is_a-Inferenz** (`recht.subsumiere` prüft jedes Merkmal gegen den Sachverhalt, alle erfüllt → Rechtsfolge); **Vertrauen = schwächste Prämisse = Beweislast-Radar** (exakt wie is_a: ein Merkmal, das nur an Parteivortrag hängt, ist die schwächste Stelle — GENUS benennt sie: „das wird die Gegenseite bestreiten"); **Wertung = ehrlicher Mensch-Slot** (`-art-> wertung` wird nie selbst gefüllt). Read-time, gläsern: die Norm ist dauerhaftes Wissen, der Sachverhalt flüchtige Eingabe (kein Fall-Fakt ins Ledger — sensibel, Ledger ≠ Memory); der gerenderte Beweisbaum ist `genus why` in förmlich. `genus subsumtion` CLI. **Live e2e verifiziert** (Beweisbaum inkl. rekursivem Kaufvertrag-Teilbaum, Blätter „belegt durch dokument:vertrag", Fälligkeit „nur Parteivortrag" korrekt als schwächste Prämisse markiert). Selbst-Bild aktualisiert: `faehigkeit:denkweisen` fehlt→teilweise. Ehrlich offen: die Deuter-Anbindung (Fakt→Merkmal-Mapping), weitere Domänen, die Einwendungs-Baupläne. 867 grün.

**Grün, neu (2026-07-05, DIE METHODEN-LANDKARTE + DIE DYNAMISCHE SCHICHT):** Ronnys Frage („Zwicky ist eine Methode — welche gibt es noch, und warum fehlen sie in GENUS?") mit einer Landkarte beantwortet (Workflow, 11 Denkmethoden): nur **Zwicky** ist heute wirklich da (er braucht kein dynamisches Material, nur die Achsen); die anderen zehn keimen bloß, und die Ursachen-Analyse fand **eine dominante Wurzel (7 von 10): fehlendes DYNAMISCHES Material** — GENUS wusste, was ein Ding IST (is_a), aber nicht, woraus es besteht, wozu es dient, was es verursacht. Deduktion/Analogie/Kausalität/Abduktion haben nichts zum Rechnen. Der empfohlene Bogen: ① die dynamische Schicht säen → ② die Deduktion herausheben → ③ den Hypothese-Test-Loop schließen. **① geliefert (585219c):** `deploy/observe_konzept.sh` erntet jetzt sechs neue Beziehungen aus Wikidata (`part_of`/`has_part`/`made_of`/`used_for`/`causes`/`caused_by`) samt einem zweiten Label-Zug für die Objekte (kein kryptisches Q-Id, jedes Ziel bekommt seinen Namen); `companion.vertiefung` webt sie in die ausführliche Antwort (»Fahrrad« besteht aus…, wird verwendet für…); `inference.py` nimmt `part_of` in die transitiven Prädikate auf (die Teil-von-Kette schließt jetzt mit). Live bewiesen: ein Konzept-Zug über »Fahrrad« brachte 168 neue Beziehungen. Der Stoff, auf dem die anderen Methoden rechnen können, liegt jetzt.

**Grün, neu (2026-07-06, DIE DEDUKTION ALS ALLGEMEINES WERKZEUG):** ② des Bogens. Das Modus-Ponens-Muster lag zweimal fest verdrahtet — `inference.py` (transitiver Kettenschluss über is_a/part_of) und `recht.subsumiere` (Subsumtion über braucht/bewirkt-Baupläne) — und ist zu EINEM domänenfreien Schließer herausgehoben: **`genus/deduktion.py`**. Eine REGEL ist ein Bauplan im Graphen (`regel -braucht-> praemisse`, Konjunktion; `-bewirkt-> folge`), rekursiv (eine Prämisse kann selbst eine Regel sein — dieselbe Kletterei wie is_a). Drei Richtungen: `schliesse` (eine Regel prüfen), **`leite_ab`** (VORWÄRTS bis zum Fixpunkt — eine abgeleitete Folge erfüllt die nächste Regel), **`beweise`** (RÜCKWÄRTS: „beweise mir Z" — suche die Regel, die Z bewirkt, zeige den gläsernen Beweis; die Richtung, die es in keiner alten Engine gab). Gläsern wie die is_a-Inferenz: jede Folge trägt ihre Prämissenkette, Vertrauen = schwächste Prämisse. Read-time, kennt kein Recht — die Regeln sind DATEN, `recht.py` ist nur die **erste Domäne**. **Der Beweis der Heraushebung (Test + live):** der allgemeine Schließer beweist `rechtsfolge:kaufpreiszahlung` rückwärts über den vorhandenen `norm:kaufpreis`-Bauplan, ohne eine Zeile Recht zu kennen. `genus beweise <ziel> --gegeben atom=quelle`. Ehrlich offen: Mehr-Hop-Vertrauen (eine abgeleitete Folge als Prämisse der nächsten Regel) trägt seinen Herleitungs-Trust noch nicht weiter — ein benannter Feinschliff; und ③ der Hypothese-Test-Loop (die aktive Hälfte: eine Vermutung erzeugen und prüfen) steht noch aus. 889 grün.

**Grün, neu (2026-07-06, DIE HYPOTHESE — Vermuten und Prüfen, der Bogen schließt sich):** ③ und Abschluss des Methoden-Bogens (Landkarte 2026-07-05: ① dynamisches Material → ② Deduktion → ③ Hypothese-Test-Loop). Die Deduktion (②) ist wahrheitsbewahrend — sie schafft nie Neues. Die **Hypothese** (`genus/hypothese.py`) ist der Generator davor: sie VERMUTET eine Konjektur und TESTET sie, und der Tester ist ausgerechnet die Inferenz/Deduktion (② wird Schiedsrichter für ③, die Hälften greifen ineinander). Das ist die **gezähmte Kreativität** aus der Intelligenz-Studie wörtlich gebaut — eine Vermutung ist eine etikettierte, gedeckelte, geprüfte Halluzination. **Erzeugen** (`vermute`): Geschwister-Analogie, deterministisch, modellfrei — was die Mehrheit der Geschwister unter demselben is_a-Elternteil trägt und der Anker nicht, wird zur Vermutung „A p o", mit sichtbarer Herleitung (k von m); nur über die transitiv-sicheren Prädikate is_a/part_of (used_for/causes wären unwiderlegbar = unehrlich). **Prüfen** (`teste_konjektur`): bestätigt (der Graph entailt es schon → nichts Neues) · widerlegt (ein is_a/part_of-Ring kollabierte — Azyklizität als Refutations-Anker — ODER eine geerdete Unvereinbarkeit greift: **der Wal ist kein Fisch**) · offen (ehrlich „mit meinem Wissen nicht widerlegbar", NICHT „wahr"). **Aussprechen** (`--tick`): die eine offene Top-Vermutung als gedeckelte Kante (Quelle `model:hypothese`, Trust ≤ 0.25 — überstimmt nie Geerdetes); Proposal ≠ Change; ohne --tick wird NICHTS geschrieben, eine widerlegte nie ausgesprochen. Die eine neue Wissens-Saat ist die Disjunktheit (`unvereinbar_mit`, Quelle „welt", isoliertes Prädikat, fließt NIE in die is_a-Inferenz). Read-time, gläsern, kein zweites Wahrheitslager (Design über einen Verstehen→Entwurf-Workflow abgesichert: 6 Subsysteme kartiert, 3 Entwürfe → 1 Bauplan). Ein adversarialer Review VOR dem Commit fand fünf echte Funde und schloss sie an der Klasse — der schärfste (hoch): auf dem lebenden 3-Quellen-Graphen (Wikidata+Lexem+DBnary) zählte ein mehrfach-bequelltes Geschwister mehrfach und verfälschte die Mehrheits-Arithmetik → erfundene Konjektur; jetzt distinkte Geschwister. Dazu die Ehrlichkeits-Grenze: die Widerlegungs-Suche bekam einen tieferen Horizont (`SUCH_TIEFE`), damit eine geerdete Widerlegung auf realen is_a-Leitern (>6 Hops) nicht still als „konsistent" durchrutscht. Selbst-Bild: `faehigkeit:analogie` fehlt→teilweise (der erste echte Analogie-Keim). `genus hypothese <knoten> [--tick]`. Ehrlich offen: die Abdeckung ist winzig (nur hand-gesäte Klassentrennungen + Ringe), freie/LLM-Konjektur + feldübergreifender Transfer + Begriffsbildung sind die Vollausbaustufe. 908 grün.

**Grün, neu (2026-07-06, DAS BACKFILL — die dynamische Schicht für die ~12k Konzepte):** Der Live-Befund aus ③ (der Hypothese-Generator zündet nur, wo Geschwister eine Eigenschaft teilen, aber das dynamische Material war erst für 3 Konzepte geerntet) wurde zum Hebel. `deploy/backfill_konzepte.py` — ein GEBÜNDELTER Wikidata-Ernter: `wbgetentities` holt 50 Konzepte je Call (part_of/has_part/made_of/used_for/causes/caused_by + Objekt-Labels), sät gebündelt über `sae_fehlende` (idempotent, dieselbe Naht), resumierbar über eine Fortschrittsdatei, höflich rate-limited. is_a bleibt dem Kletter-Lerner — der Backfill liefert die FEHLENDE verbindende Schicht. **Live gelaufen:** 11.767 Konzepte geerntet → **13.922 dynamische Kanten** (4.899 Konzepte trugen welche, ~42% Abdeckung) + 15.450 Label-Kanten (7.848 Objekt-Konzepte benannt), ~29k neue Kanten im Organismus. **Der Payoff, live gemessen:** vorher zündeten von 400 Konzepten (nur ≥2 is_a-Eltern) 6 eine Vermutung — jetzt zünden **55 von 1500** quer durch den Graphen, samt NEUER part_of-Vermutungen, die vorher unmöglich waren („diocesan clergyman gehört zu Catholic Church hierarchy", 3/3, live über `genus hypothese`). Die Material-Wende wörtlich: das Material folgte der Operation, und die Operation zündet jetzt breit. **Ein adversialer Review VOR dem Live-Lauf** (schreibt ~29k Kanten in den Ledger) fand + schloss: part_of-Ringe/Selbst-Loops aus Wikidata hätten über `observe_relation` eine Flut von contradiction/inquiry-Events ausgelöst (Fremddaten-Rauschen in GENUS' Introspektion) — Fix: Selbst-Loops in der Extraktion gefiltert, ring-schließende part_of-Kanten gar nicht erst importiert (die Teil-Ganzes-Hierarchie bleibt azyklisch; **genau 1 realer Wikidata-Ring wurde live abgefangen** — der vorhergesagte Fall trat auf); dazu ein `predicate`-Index (Full-Table-Scan in `sae_fehlende` behoben, hilft dem ganzen System), Item-only-Filter, `--ids`-Guard. Reine Extraktions-Funktionen test-gepinnt, off-Pi gegen echtes Wikidata dry-run-verifiziert. 914 grün.

**Vorgemerkt (Ronny, 2026-07-04): KONTEXT als eigenes Design-Thema.** „Der Kontext schwingt ja immer mit und muss selbstverständlich auch bei jeglicher Kommunikation berücksichtigt werden. Das heißt nicht immer, dass extra etwas gesagt wird — aber vielleicht sogar ist es manchmal eben das. Diese tiefe Art Persönlichkeit fehlt GENUS auch noch!" — Kontext färbt jede Antwort (mal nur den Ton, mal gebietet er, EIGENS etwas zu sagen, mal zu schweigen). Berührt Gedächtnis (was weiß GENUS über die Situation), den Antwort-Würfel (eine Kontext-Achse?) und die Rollen — ein eigener Design-Schritt im Gespräch mit Ronny, nicht unilateral gebaut.

**Rot — der nächste Schritt:** bessere Plan-Finder-Kandidaten; Embedder-Cosine-Nudge; Kurvendiskussion erweitern; `integrity`-Register (nicht dringend). Parallel weiter gültig: Selbst-Codieren Stufe 1 (der Bauer wird selbst ein registriertes Werkzeug, dann kann ein Proposal aus Stufe 0 direkt einen Aufruf des Bauers vorschlagen); der erste echte Anwendungsfall für ein Rezept (Kurvendiskussion, komponiert aus den vier Mathe-Werkzeugen). Und weiterhin: die Identitätsfrage („Weißt du, dass du GENUS bist?") hat noch keine gute Heimat in `frage-genus` (fällt heute ehrlich, aber ungenau auf `ursache`/`frage-begriff` durch) — ein Blatt „identität" ist ein guter Kandidat; vollständigere Segmentierung (das Modell übersieht gelegentlich ein Segment in einer Drei-Akt-Nachricht); Treffer-Quote-Kennzahl aus Folge-Signalen (lernt, WELCHE Bausteine je Zelle nützen); Raster-Inquiries (GENUS fragt bei Unsicherheit nach); Plural-Morphologie beim Objekt einer Beziehungsfrage; Phase D (früh); Korrelation≠Kausalität; Ziel-Objekt; Punkt ③ Fachwissen-INHALT (Infrastruktur bereit, wartet auf Ronnys Domänen-Wahl + ggf. eine Prüfungsordnungs-Quelle) und der Rest von Punkt ④ (Tagespuffer + Nacht-Konsolidierung + Morgen-Push — die erste echte PUSH-Fähigkeit der Membran, verdient denselben sorgfältigen Design-Schritt wie das Gedächtnis-Konzept selbst, nicht unilateral gebaut). Das LLM bleibt am Rand, gedeckelt.

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
> erzwungen (nicht erfunden — eine Dimension kommt nur dazu, wenn eine gebrauchte
> Fähigkeit ohne sie unmöglich ist, nie auf Vorrat):
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

**Naht gezündet + Brücke + LLM am Rand (2026-06-30, v1.16):** Die Quellen-Frage gründlich
geprüft (Ronny: *„ist das wirklich das beste Material?"*) — Duden (proprietär) und GermaNet
(lizenziert) raus, OdeNet off-Pi als zu verrauscht verworfen; **DBnary** (dt. Wiktionary als
sauberes RDF, SPARQL) gewann. Drei Quellen speisen den Graph: **Wikidata-Konzepte**
(`observe_konzept`) · **Wikidata-Lexeme** (`observe_lexem`, korroboriert `expresses`, liefert
Wortarten) · **DBnary** (`observe_dbnary`, die menschliche **Bedeutungs-Schicht** — `defined_as`
pro Sinn, *sense-safe* gebunden: nur deutsche Ausgabe, kein wort-flaches `is_a`, sonst
Sinn-Kontamination). Damit korroboriert die Naht *live*.
**Sinn→Konzept-Brücke** — das Tor zum Begleiter, in Scheiben: **①** `genus concept <Q>` macht
ein Konzept *ansprechbar* (deterministischer Primär-Sinn → prominentes Q, read-time, modell-frei);
**②** `disambiguate.py` deutet on-demand, *welcher* Sinn zum Kontext passt (lokaler **Embedder**,
~100 MB, 14 ms auf dem Pi, Cosinus-Abstand = Confidence); **③** der **Schreibpfad** — der Embedder
wählt aus *echten* Kandidaten-Konzepten und schreibt die Bindung als **gedeckelte,
graph-verifizierte `model:embedder`-Behauptung** (`bridge_senses.py`; `source_trust` deckelt
`model:*` auf den halben Saatwert → nie ein Orakel). **Das erste Mal, dass ein Modell GENUS
berührt** — am Rand, gläsern, gedeckelt; der Kern blieb deterministisch, sub-ms, modell-frei.
Genau die „viel Maschine, LLM am Rand"-Architektur, real. *Offen:* der **Begleiter**
(deuten + Konzept-Antwort + Stimme) und Volumen (echte Häufigkeitsliste).

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

## Die Etappen bis zur Vollendung (Stand 2026-07-04, von Ronny erfragt: „von jetzt bis Fertigstellung")

„Fertig" heißt ehrlich: alle sieben Ziele haben LEBENDE Fähigkeiten und der Loop trägt
sich selbst — jede Etappe hat ein messbares „fertig wenn", kein Datum. Die Reihenfolge
ist die Optimierung: der Begleiter zahlt dreifach (Nutzen + gelebte Lerndaten + spürbar),
die Selbst-Entwicklung verbilligt alles Spätere, die Markt-Membran wartet auf gelebte
Gates, das Generator-Organ auf eine bessere Modell-Landschaft (gemessen, nicht gehofft),
die Föderation auf alles davor plus die gelöste Löschbarkeits-Frage.

**Etappe 1 — Der Begleiter wird alltagstauglich** *(Ziele: begleiter, verstehen)*
Gedächtnis fertig: Tagespuffer + Nacht-Konsolidierung + Morgen-Push (#19, erste
PUSH-Fähigkeit, eigener Design-Schritt) · Persönlichkeits-Schicht v1 GELIEFERT
(WESEN/ART/REGISTER + Chat-Regler, `docs/GENUS_PERSOENLICHKEIT.md`; nächster
Verbraucher: die Stimme-Anweisung) · Embedder-Cosine-Nudge (braucht warmen
Embed-Pfad — kleiner Daemon oder fastembed im Bot-venv) · Raster-Reste (identität-Blatt,
Segmentier-Qualität, Antwort-Komposition) · Wissens-Breite läuft weiter (Lerner).
*Fertig wenn:* eine Woche echte Sessions ohne Fehlgriff-Frust; Morgen-Push läuft;
„Was weißt du über mich?" fühlt sich vollständig an.

**Etappe 2 — Selbst-Entwicklung wird produktiv** *(Ziel: selbst-entwicklung)*
Plan-Finder: neue lokale Coder-Modelle durchmessen (Geschirr = Einzeiler) ·
Bauplan-Arten wachsen mit echten Lücken (Registry) · Selbst-Bild vervollständigen
(GENUS liest den eigenen Code, read-only) · Abitur-Thermometer aufstellen (#20) ·
erste Gate-Lockerung mit Bilanz, selbst durchs Gate (§8).
*Fertig wenn:* die erste von GENUS gespürte, freigegebene, vom Schmied gefüllte, von
Ronny gemergte Zelle LIVE antwortet — der volle Kreis einmal komplett.

**Etappe 3 — Neue Sinne: die Markt-Membran** *(Ziel: trading, Teil 1)*
Beobachten wie beim Wetter (Membran → provenancte Behauptungen) · Forecast-Skill über
die bestehende learning-Engine · Papier-Signale mit gemessener Trefferquote · die
härtesten Gates des Systems (Vorschlag-pro-Trade, menschliche Bestätigung).
*Fertig (Teil 1) wenn:* Monate Papier-Bilanz mit ehrlicher Trefferquote. Echtes Geld
ist eine SPÄTERE, eigene Entscheidung — die Leitplanke (nie Auto-Trading auf
Backtest-Confidence) steht.

**Etappe 4 — Das Generator-Organ** *(Ziele: unterhaltung, private-generierung)*
Größeres lokales Modell als Organ (freie Stimme mit Anker-Leine) · Spiele zuerst
regelbasiert (SYSTEME-Schiene: Regel-Domänen sind Kern-Stärke — Schach als Kandidat) ·
private Generierung über ein eigenes, konfiguriertes Modell-Organ, strukturell isoliert.
*Fertig wenn:* ein Spiel läuft komplett über Regel-Domänen + Organ; die Generierung
läuft lokal, isoliert, mit Ronnys Konfiguration.

**Etappe 5 — Föderation: Familie & Gruppen** *(Ziel: begleiter für Gruppen)*
Ein Kern pro Person, geteilte Räume · Charaktere mit STRUKTURELLER Isolation ·
Crypto-Shredding (Löschbarkeit vs. append-only) wird VOR dieser Etappe gelöst.
*Fertig wenn:* zwei Kerne teilen einen Raum, ohne dass einer den anderen lesen kann;
Löschen ist real.

**Querschnitt, laufend (keine eigene Etappe):** Umbau-Reste (companion-Muster →
Registry, `query.ask` → Deuten+Register, `integrity`-Schema-Register, deutsche
Modulnamen #24 als eigene Session) · Ledger-Wachstum auf der SD-Karte NACHMESSEN (nie
gemessen) · Selbst-Bild aktuell halten (erster fälliger Punkt: `ziele.py` sagt noch
„vorschlags-loop: fehlt" — er ist seit 2026-07-04 lückenlos live) · Doku bleibt
abgeleitet und aktuell.

**Einordnung der alten offenen Punkte:** Transition Core + Worker Interface geht in
Etappe 3 auf (die Markt-Membran ist der erste echte Handlungs-Anlass); Visual
Observation Model bleibt hinter Etappe 4 (Bild als Sensor-Typ); Föderation IST Etappe 5.

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
  ⑦      Sprache · Brücke · LLM am Rand (2026-06-30, v1.16) → 3 Quellen korroborieren
         (Lexeme + DBnary-Bedeutungen) · Konzepte ANSPRECHBAR (genus concept) · erstes
         Modell am Rand: Embedder deutet & brückt, gedeckelt + graph-verifiziert → TOR ZUM BEGLEITER

── darüber: freie Reihenfolge, alles noch deterministisch & gläsern ──
  Begleiter  ask→answer: deuten + Konzept-Antwort + Stimme (der fühlbare Nordstern)
  Systeme    Regel-Domänen lernen + schließen (Sprache · Schach · Code …)
  Erschaffen erzeugen MIT Beweis → der Gipfel  ("Programmieren" = das, auf Code)

── Querschnitt, ANGEDOCKT (erstes Modell am Rand, v1.16) ──
  LLM        Embedder deutet/brückt (model:embedder, gedeckelt) · später Stimme — nie Orakel

── DER UMBAU (2026-07-04: KOMPLETT — alle 5 Phasen geliefert, an einem Tag) ──
  Phase 0   Boden           → Kopplungen gelöst · db.connect · Belief-Maschine geteilt ✅
  Phase 1   Register        → Vertragstest + event_router-Registry · Checkpoint bestanden ✅
  Phase 2   Deuten gehärtet → die Grenze live bewiesen (erfundene Kategorie unmöglich) ✅
  Phase 3   Hülle → Ledger  → Zellen-Registry · Registrierung als Event · Korrektur-Kanal ✅
  Phase 4   Selbst-Codieren → Kette LÜCKENLOS: spüren→fragen→Freigabe→bauen→Werkstatt→Merge ✅
            + Werkstatt/Schmied/Bauplan/Fügewerk/Bauplan-Grenze (Trichter gemessen: 1/3
            Ende-zu-Ende) · Selbst-Neustart der Membran (kein sudo, je)

── DIE ETAPPEN BIS ZUR VOLLENDUNG (siehe eigener Abschnitt unten) ──   ← JETZT HIER
  Etappe 1  Begleiter alltagstauglich   → Gedächtnis fertig · Cosine-Lernkreis · Raster-Reste
  Etappe 2  Selbst-Entwicklung produktiv → Plan-Finder messen · Selbst-Bild · Gate-Lockerung
  Etappe 3  Markt-Membran               → beobachten · Papier-Bilanz · härteste Gates
  Etappe 4  Generator-Organ             → freie Stimme · Spiele · private Generierung
  Etappe 5  Föderation                  → ein Kern pro Person · Löschbarkeit vorher gelöst
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
