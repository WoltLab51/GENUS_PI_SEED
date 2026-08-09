# A0 Decision Packet

> **Status:** decision required · datierter Report, keine angenommene Entscheidung
> **Decision Owner:** Ronny
> **Snapshot:** 2026-08-09 (Europe/Berlin)
> **Geprüfter Commit:** `cd22fc42cab9d5a693336f47ffea7aaf53782d2f`
> **Evidenzbasis:** [A0 Foundation Audit](2026-08-09-a0-foundation-audit.md)
> **Build-Autorität:** keine

## 1. Ausgangspunkt, Snapshot und Autorität

Dieses Packet bereitet die menschlichen Entscheidungen vor, die A0 erst
implementierbar machen. Es ist weder ADR noch Roadmap, Freigabe, ChangeSpec oder
Implementierungsauftrag. Keine Empfehlung ist angenommen; nur Ronny darf die
Checkboxen in Abschnitt 11 entscheiden. Erst angenommene ADRs dürfen danach
`docs/ROADMAP.md` und `docs/NOW.md` binden.

### Vergleich mit dem Audit-Snapshot

- **Bestätigter Repo-Befund:** Der Audit prüfte den lokalen Stand
  `cadcda834a5d8e61be357f90b0db11c284ea9a9a`. Er wurde anschließend unverändert
  als Dokumentationscommit `cd22fc42cab9d5a693336f47ffea7aaf53782d2f`
  (`docs: add A0 foundation audit`) eingefroren.
- **Bestätigter Repo-Befund:** Der Commit-Unterschied `cadcda8..cd22fc4`
  besteht ausschließlich aus dem Auditreport und seinem einen Index-Link: 946
  Dokumentationszeilen in zwei Dateien. Runtime, Schema, Tests und Deploypfade
  änderten sich zwischen Auditbasis und Decision-Packet-Basis nicht.
- **Bestätigter Repo-Befund:** Der Worktree war zu Beginn dieses Packets auf
  `cd22fc4` sauber.
- **Schlussfolgerung:** Die technischen Auditbefunde gelten für denselben
  Runtime-Stand weiter; dieses Packet darf sie als Evidenz verwenden, ohne sie
  neu als Tatsachen zu erfinden.

### Getrennter Status-Repository-Zeitpunkt

Der Audit-Snapshot belegt, dass `GENUS_PI_STATUS/main` am Abfragezeitpunkt
ungeschützt war. Unmittelbar vor Beginn dieses Packets wurde auf ausdrückliche
menschliche Anweisung eine davon getrennte Minimalhärtung vorgenommen und
read-only verifiziert:

- Branch Protection ist aktiv;
- `allow_force_pushes=false`;
- `allow_deletions=false`;
- keine erforderlichen Reviews oder Statuschecks;
- keine Push-Restriktionen und kein Branch-Lock;
- der vorhandene schreibende Deploy Key blieb unverändert.

Diese Änderung gehört **nicht** zum historischen Auditbefund und wurde nicht
durch dieses Decision Packet vorgenommen. Sie lässt normale Fast-Forward-
Status-Pushes zu. Sie verhindert aber nicht, dass ein normaler neuer Commit alte
Anchor-Dateien ändert oder löscht, und schafft weder Signaturen noch
pfadbegrenzte Publisher-Rechte. GitHub bleibt deshalb Transportfläche, kein
alleiniger Vertrauenszeuge.

### Kanonische Grenze

`docs/README.md` klassifiziert Reports ausdrücklich als nicht buildsteuernd.
`docs/CHARTER.md` hält menschliche Freigabe und Widerrufbarkeit fest.
`docs/ARCHITECTURE.md`, `docs/EVENT_CONTRACT.md`, `docs/SECURITY_MODEL.md` und
`docs/QUALITY.md` besitzen die dauerhaften Verträge. ADR-0002 und ADR-0004
verbieten, dass ein Generator seine eigene Abnahme, seinen Merge oder kritische
Autorität definiert.

Die aktuelle `docs/ROADMAP.md` nennt weiterhin H1.2 als aktive Baulinie. Dieses
Packet ändert das nicht. Es schlägt für eine spätere menschliche Annahme vor,
dass eine A0-Implementierung dann der einzige mergefähige kritische
GENUS_PI_SEED-Produktpfad sein muss.

## 2. Entscheidungsformat

Jedes Teilpaket trennt strikt:

1. **bestätigter Repo-Befund** — ausschließlich Audit-/Kanon-Evidenz;
2. **Schlussfolgerung** — aus dem Befund abgeleitete notwendige Grenze;
3. **Optionen** — reale Alternativen einschließlich des Status quo;
4. **Empfehlung zur menschlichen Prüfung** — noch nicht angenommen;
5. **Nachteile und offene Risiken** — auch der Empfehlung;
6. **menschliche Entscheidung** — Parameter, die Ronny festlegen muss;
7. **spätere ADR-Zuordnung** — vorgeschlagen, noch keine Datei;
8. **noch nicht erlaubte Implementierung** — explizite Stopplinie.

Bewertungen sind ordinal und keine Scheingenauigkeit:

- `gut`: unterstützt das Kriterium unmittelbar;
- `bedingt`: möglich, aber nur mit Zusatzvertrag oder noch fehlender Evidenz;
- `schwach`: löst das Kriterium nicht belastbar;
- `UNKNOWN`: muss experimentell geklärt werden.

## 3. A0.1 — Schema Evolution

### Entscheidungsfrage

> Wie soll GENUS Schemaänderungen künftig erkennen, planen, ausführen,
> verifizieren und bei Fehlern stoppen, ohne dass ein normaler `connect()`- oder
> Startup-Pfad die Produktdatenbank implizit verändert?

### Bestätigter Repo-Befund

- `genus/db.py:16-29,141-170` ruft beim normalen Datei-Connect
  `init_schema()` auf, führt `schema.sql`, fünf ad-hoc `_ensure_column()`-
  Ergänzungen und einen Commit aus.
- Eine persistierte DB-Schemaversion, `schema_migrations`, nummerierte
  Migrationen, `genus db status`, `genus db migrate`, Dry-Run und technischer
  Recovery-Vertrag fehlen.
- `connect_readonly()` ist bereits ein strikt nicht migrierender
  Diagnosebaustein (`genus/db.py:32-57`).
- Zwei synthetische Tests prüfen einzelne Spaltenergänzungen, aber keine
  vollständige historische Altversion, Migration plus Replay oder Fehlerfolge.
- Produktpfade einschließlich Status-Export können heute den schreibenden
  Connect erreichen. Der Audit belegt keine konkrete produktive Korruption.

### Schlussfolgerung

Schemaerkennung, Schemaänderung und Dienststart benötigen getrennte
Autoritäten. Ein Startup darf weder eine unbekannte Altform still interpretieren
noch eine teilweise Migration fortsetzen. Die Schemaentscheidung muss mit
Ledger-, Replay-, Seal- und Recovery-Invarianten gekoppelt werden, ohne einen
Schemafehler durch Reseal zu verdecken.

### Optionen

| Option | Beschreibung | Hauptvorteil | Hauptnachteil |
|---|---|---|---|
| **A — Status quo** | `_ensure_column()`/`init_schema()` bleiben im normalen Connect. | kleinster Bedienaufwand | stille DDL, keine Version/Provenienz, unklarer Zwischenzustand |
| **B — versioniert, aber automatisch** | Explizite Schema-Version und nummerierte Migrationen; Startup migriert weiterhin automatisch. | nachvollziehbarere Schritte bei einfacher Bedienung | jeder Dienststart bleibt verändernde Autorität; Crash/Verfügbarkeit und Rolloutkopplung bleiben kritisch |
| **C — versioniert und manuell** | Read-only Versionsprüfung, Fail-Closed bei falscher/unklarer Version; ausschließlich expliziter human-owned Runner darf migrieren. | klare Autorität, testbarer Plan, Recovery vor Veränderung | mehr Betriebsdisziplin, Wartungsfenster und mögliche Startverweigerung |

### Bewertungsmatrix

| Kriterium | A | B | C |
|---|---|---|---|
| Nachvollziehbarkeit | schwach | gut | gut |
| Crash-Risiko | hoch/unklar | bedingt: Migration am Dienststart | am besten begrenzbar; konkrete DDL-Atomizität bleibt zu testen |
| Wiederholbarkeit | ad hoc | gut bei idempotenten Schritten | gut bei idempotenten Schritten und explizitem Plan |
| Testbarkeit | einzelne Altspalten | nummerierte Schritte testbar | Schritte, Plan, Verweigerung und Recovery getrennt testbar |
| Recovery | kein Vertrag | mit Startup und Dienstfehler gekoppelt | Backup/Restore und `recovery_required` vor Start erzwingbar |
| Bedienbarkeit auf dem Pi | bequem, aber unsichtbar | bequem, aber riskanter Start | zusätzlicher Befehl/Wartungsablauf, dafür erklärbar |
| Wirkung auf normale Dienste | dürfen Schema ändern | dürfen Schema ändern | prüfen nur und verweigern bei Inkompatibilität |
| Ledger-/Replay-Invarianten | nicht systematisch gegatet | nachträglich integrierbar | Vor-/Nachgates und Golden Oracle verbindlich koppelbar |

### Empfehlung zur menschlichen Prüfung

**Option C.** Normales `connect()` verändert kein bestehendes Schema. Eine
explizite Version und ein kanonischer Schema-Fingerprint werden read-only durch
`genus db status` geprüft. Bei alter, neuer, unbekannter oder teilweise
migrierter Version verweigert der Produktdienst den Start. Nur ein explizites
`genus db migrate` darf nach menschlicher Freigabe nummerierte, idempotente
Migrationen ausführen — zunächst ausschließlich gegen DB-Kopien.

Als Ausführungsklasse sollte zusätzlich entschieden werden: Forward-only
In-place-Migrationen sind nur für nachweislich atomare, nicht destruktive
Schritte zulässig; destruktive, Ledger-/Seal-nahe oder nicht beweisbar atomare
Schritte verwenden Copy → Transform → Verify → atomaren Cutover. Rückkehr
erfolgt über das verifizierte Backup, nicht über ein gefährliches historisches
`down`.

Vor einer späteren Produktmigration: Writer-Stopp, konsistentes DB/WAL/SHM-
Backup samt Digest, Restore-Probe, letzter gültiger Anchor, Integrity/Seal-
Baseline, freier Speicher und menschliche Freigabe. Danach: Schema-
Nachbedingungen, Golden Replay zweimal, alle Projektionsdigests, unverändertes
Event-Log, Integrity, Seal und Anchor-Verifikation.

### Nachteile und offene Risiken

- Fail-Closed kann Verfügbarkeit kosten, wenn Deploy und Migration falsch
  koordiniert sind.
- Copy/Cutover benötigt erheblichen freien Speicher und eine definierte
  fsync-/Rename-/WAL-Grenze auf dem Pi.
- Eine Versionsnummer allein kann falsche Struktur behaupten; ein kanonischer
  Schema-Fingerprint und Nachbedingungen bleiben nötig.
- SQLite-DDL-, Kill- und Recovery-Verhalten je Migrationsklasse ist noch
  **UNKNOWN** und muss mit Fehler-Injection geprüft werden.
- Unterstützte Altversionen und die maximale akzeptierte Downtime sind noch
  menschlich festzulegen.

### Menschlich zu entscheiden

- heutige Basisschemaversion und offiziell unterstützte Altversionen;
- Versionsträger, Schema-Fingerprint und Felder des Migrationsjournals;
- Schwelle für verpflichtendes Copy/Cutover;
- Operator, Approver und Freigabeartefakt;
- Startup-Matrix für aktuell/alt/neu/unbekannt/teilweise migriert;
- Downtime-, Platz- und Recovery-Budget;
- ausdrückliches Verbot von Event-/Seal-Umschreibung durch Schema-Migration.

### Spätere ADR-Zuordnung

**ADR-0005 — Explicit Schema Evolution and Migration Boundary**

### Noch nicht erlaubt

Keine `schema_migrations`-Tabelle, keine Version, kein neuer CLI-Befehl, keine
Änderung an `connect()`, kein Runner und keine Migration gegen eine Produkt-DB.

## 4. A0.2 — Golden Ledger und unabhängiges Orakel

### Entscheidungsfrage

> Wie beweist GENUS in CI, dass historisch gewachsene Ledger nach Code- und
> Schemaänderungen dieselbe fachliche Gegenwart rekonstruieren?

### Bestätigter Repo-Befund

- CI replayt eine frisch erzeugte temporäre DB und öffnet erst danach die
  Seal-Epoche (`.github/workflows/ci.yml:45-88`).
- Standardtests verwenden frische temporäre oder In-Memory-DBs
  (`tests/conftest.py:26-44`).
- Einzeltests belegen Legacy-Präfix-Tamper, versiegelten Replay, Lifecycle,
  Governance und Idempotenz verteilt; keine Fixture vereinigt diese Fälle.
- Es gibt kein unabhängig versioniertes Orakel mit erwarteten Digests aller
  zwölf Projektionen und keinen Alt-Schema→Migration→Replay-Nachweis.
- Die CLI-Replay-Aufnahme lässt vier Replayziele aus; der vollständige
  Integrity-Snapshot kennt alle zwölf.

### Schlussfolgerung

Eine Implementierung darf nicht zugleich Testmaterial und erwartete Wahrheit
erzeugen. Der Golden-Vertrag muss die historische Eingabe statisch binden und
die erwartete fachliche Gegenwart unabhängig kanonisieren. Er muss vor oder
spätestens gemeinsam mit dem Migrationsrahmen feststehen.

### Grundoptionen

| Option | Beschreibung | Urteil |
|---|---|---|
| **A — nur frische CI-DBs** | heutige Testform bleibt alleinige Evidenz | schnell, aber kein Legacy-/Genesis-/Migrationsbeweis |
| **B — runtime-generiertes Golden** | aktuelle Producer/Projektoren erzeugen Fixture und Erwartung | reproduzierbar, aber Fehler und Erwartung können gemeinsam driften |
| **C — handgeprüfte historische Fixture + unabhängiges Orakel** | synthetische statische Historie und separat freigegebene Erwartungen | stärkste kleine Beweisbasis; zusätzlicher Review-/Pflegevertrag |

### Mögliche Repräsentationen

| Form | Stärke | Grenze |
|---|---|---|
| Statische SQLite-Fixture | bewahrt alte Schemaform, IDs, Zeitstempel, Payloads und Seals exakt; direkt für Migration nutzbar | binär und allein schlecht reviewbar; SQLite-/Toolversionen müssen kontrolliert werden |
| JSONL-Eventfixture mit deterministischem Import | gut diff- und reviewbar; Events leicht additiv versionierbar | bildet Altschema/Indizes/Trigger nicht vollständig ab; Importer kann mit dem Code unter Test driften |
| Fixture + signiertes Manifest | starke externe Bindung von Corpus und Oracle | Signatur- und Key-Custody-Vertrag existiert noch nicht; darf ADR-0008 nicht vorwegnehmen |

### Empfehlung zur menschlichen Prüfung

**Option C.** Kleinste belastbare Variante für A0:

1. eine statische, datenschutzfreie SQLite-Fixture als exaktes ausführbares
   Alt-Schema-/Ledger-Artefakt;
2. ein menschenlesbarer deterministischer SQL-Export als Reviewbegleiter und
   Wiederherstellungsbeleg;
3. ein separates versioniertes, zunächst digestgebundenes und handgeprüftes
   Manifest/Orakel. Eine spätere Signatur darf nach ADR-0008 additiv hinzukommen,
   ist aber keine Vorbedingung für das erste Golden Ledger.

Genau eine Darstellung ist normativ; Derivate tragen Digests und müssen
deterministisch daraus entstehen. JSONL allein ist für die erste
Migrationsfixture zu schwach, weil es die historische Schemaform nicht bindet.

### Pflichtinhalt der Fixture

- mehrere unversiegelte Legacy-/Prä-Epochen-Events;
- nichtleerer Legacy-Präfix;
- korrektes `ledger_epoch_opened` und Genesis-Digest über diesen Präfix;
- versiegelter Tail;
- projizierte und bewusst rohe Eventtypen;
- `supported`, `contested` und `superseded` Beliefs;
- Relation, Inquiry, Experience, Proposal und Governance;
- mindestens ein terminaler Lebenszyklus;
- prüfbarer historischer Anchor;
- ausschließlich erfundene, datenschutzfreie Inhalte.

### Pflichtinhalt des unabhängigen Orakels

- normalisierte erwartete Daten jeder der zwölf Projektionen;
- stabiler Digest je Projektion und ein Gesamtdigest;
- erwartete Eventzahl, IDs und Reihenfolge;
- Präfix-, Genesis-, Epoch-, Head- und Seal-Erwartung;
- erwartete Integrity- und Anchor-Ergebnisse;
- zweimaliger Replay mit identischem Ergebnis und null neuen Events;
- negative Tamper-Fälle für Präfix, Tail, Payload, Seal und Oracle;
- später: jede unterstützte Altversion erreicht nach Migration dasselbe Orakel.

Kanonisierung muss Tabellen-/Spaltenreihenfolge, SQLite-Typen, `NULL`, Text,
Zeit, JSON-Normalisierung, Floatdarstellung und Digestalgorithmus explizit
definieren. Oracle-Änderungen sind eigene menschengeprüfte Änderungen; ein
Runtime-Patch darf seine Goldens nicht beiläufig „aktualisieren“.

### Nachteile und offene Risiken

- Eine einzelne Fixture kann falsche Vollständigkeit suggerieren; Coverage-
  Matrix und spätere additive Corpus-Versionen bleiben nötig.
- Binärfixture, SQL-Export und Manifest können auseinanderdriften; nur eine
  normative Quelle und Derivatprüfungen verhindern das.
- Plattformabhängige SQLite-/Float-/JSON-Darstellung kann Digests instabil
  machen.
- Die unabhängige Ersterzeugung der erwarteten Projektionen benötigt einen
  benannten Menschen und eine nachvollziehbare zweite Berechnung.
- Datenschutzfreiheit muss positiv geprüft werden; „aus Produktion anonymisiert“
  ist nicht gleich synthetisch.

### Menschlich zu entscheiden

- Corpus Owner, Datenschutzprüfer und Oracle-Prüfer;
- normative Darstellung und erlaubte Derivate;
- Kanonisierungs- und Digestvertrag;
- Freigabeschwelle für Oracle-Änderungen;
- unterstützte Schema-/Eventära und Coverage-Matrix;
- ob/ab wann ein nach ADR-0008 signiertes Manifest erforderlich wird.

### Spätere ADR-Zuordnung

**ADR-0006 — Golden Ledger and Independent Replay Oracle**

### Noch nicht erlaubt

Keine Fixture, kein Oracle, kein Importer, keine Golden-Aktualisierung, keine
Migration und keine Schlüssel-/Signaturerzeugung.

## 5. A0.3 — Bounded Replay und Integrity

### Entscheidungsfrage

> Wie kann GENUS Ledger mit mehr als einer Million Events replayen und prüfen,
> ohne den vollständigen Ledger in den RAM zu laden oder bei einem Abbruch eine
> unklare sichtbare Gegenwart zu hinterlassen?

### Bestätigter Repo-Befund

- `event_router.replay()` lädt alle Events per `fetchall()` in RAM, leert zwölf
  Projektionsziele und baut sie neu auf (`genus/event_router.py:197-272`).
- Der CLI-Pfad hält `BEGIN IMMEDIATE` durch Replay und Vergleich; ein
  Writer-Gate ist getestet. Das Bild paralleler Leser ist nur **INFERRED**.
- Kill/Stromausfall, Reopen/Retry, Peak RAM, WAL und Pi-Laufzeit sind
  **UNKNOWN**.
- Der tiefe Replay-API-Pfad besitzt keinen eigenen vollständigen
  Transaktions-/Rollbackvertrag.
- Integrity materialisiert ebenfalls das gesamte Event-Log in Python und in
  einer zweiten In-Memory-DB.
- Der Deploypfad multipliziert Vollreplays; es gibt keine Benchmarks oder
  Budgets für die öffentliche Größenordnung von mehr als einer Million Events.

### Schlussfolgerung

„Batch“ allein löst nur Peak RAM. A0.3 braucht zugleich einen festen
Eingangs-Head, explizite Transaktionsownership, eine atomare Sichtbarkeitsgrenze,
bounded Integrity, Abbruch-/Retry-Vertrag und messbare Pi-Budgets. Welche
Sichtbarkeitsarchitektur genügt, darf ohne Reader-/Kill-Experiment nicht als
Tatsache festgeschrieben werden.

### Optionen

| Option | Beschreibung | Hauptstärke | Hauptgrenze |
|---|---|---|---|
| **A — heutiges `fetchall()`** | Vollständige resident gehaltene Liste, heutige Projektionstabellen | geringste Änderung | O(N) RAM, kein Fortschritt/Budget, Integrity bleibt doppelt unbeschränkt |
| **B — Cursor/Batch in einer Transaktion** | fester Head, begrenzte Iteration, heutige Tabellen, ein atomarer Commit | kleine Architekturänderung, Leser sollten alten Stand behalten | lange Writer-Sperre/WAL/Crash-Verhalten auf Pi noch UNKNOWN |
| **C — Shadow-Projektionen** | neue versionierte Projektionstabellen aufbauen, prüfen, atomar umschalten | klare Alt/Neu-Sicht, guter Fehlerrückzug | Schema-/Routing-/FK-Komplexität und doppelter Speicher |
| **D — separate temporäre DB/Kopie** | Ledger/Projektionen außerhalb der Live-DB replayen, danach geprüft übernehmen | starke Isolation und gute Migrationsprüfung | sichere Übernahme zurück ist selbst ein komplexer Cutover; hoher Speicher/I/O |

### Bewertungsmatrix

| Kriterium | A | B | C | D |
|---|---|---|---|---|
| Peak RAM | schwach | gut | gut | gut bei Streaming |
| Laufzeit | heutiger Referenzwert fehlt | voraussichtlich günstig | Zusatzarbeit | höchste I/O-Tendenz |
| WAL-Wachstum | UNKNOWN | potenziell groß, zu messen | abhängig vom Aufbau/Cutover | Live-WAL klein, Kopier-I/O groß |
| Leser während Replay | **INFERRED:** alter Commit | **INFERRED:** alter Commit | klare Zielsemantik, noch zu testen | Live-Leser unberührt bis Übernahme |
| Writer während Replay | getestetes Gate | langes Gate | Capture/Cutover-Gates nötig | Capture/Cutover-Gates nötig |
| Crash-Verhalten | UNKNOWN | UNKNOWN | alte Version sollte erhaltbar sein, Beweis fehlt | Live-Stand bleibt bis Übernahme, Cutover bleibt kritisch |
| Wiederholbarkeit | fachlich vorhanden, unvollständiger CLI-Snapshot | gut mit festem Head | gut mit Versions-ID | gut auf verworfener Kopie |
| Komplexität | niedrig | mittel | hoch | hoch |
| Pi-Eignung | bei >1M unbelegt | Kandidat, messpflichtig | speicher-/schemaintensiv | platz-/I/O-intensiv |
| Recovery | CLI-Ausnahme-Rollback, Kill UNKNOWN | Rollback/Retry zu beweisen | Shadow verwerfen/Alt aktiv lassen | Kopie verwerfen; Übernahme separat |
| Messbarkeit | heute kein Budget | gut instrumentierbar | gut instrumentierbar | gut instrumentierbar |

### Empfehlung zur menschlichen Prüfung

Keine endgültige Wahl B/C ohne Experimente. Empfohlen wird eine
**evidenzgegatede Strategie**:

1. Unabhängig von der Topologie festlegen: kein Voll-`fetchall`, fester
   `head_id`, Keyset-/Cursor-Iteration, konfigurierbare Batch-Größe,
   Fortschritt, null Ledgerwrites und derselbe bounded Stream für Integrity.
2. Option B als kleinsten Prototyp ausschließlich gegen die Golden Fixture und
   synthetische Größenklassen messen.
3. Option B nur wählen, wenn Reader-, Kill-, WAL-, Lock- und Pi-Budgets die
   vollständige Transaktion nachweislich tragen.
4. Andernfalls Option C als Live-Strategie wählen. Option D bleibt bevorzugter
   Validierungsweg für Migrationen und forensische Kopien, nicht automatisch der
   Live-Cutover.

Das ist keine Vertagung der Sicherheitsinvarianten. Vertagt wird nur die
Topologie, weil der Audit die entscheidenden Laufzeiteigenschaften ausdrücklich
nicht beweist.

### Pflicht-Experimente

- 10.000, 100.000 und 1.000.000 Events;
- realistische Payload-Größen und Mischung projizierter/roher Typen;
- 0-/1-Event- und exakte Batchgrenzen;
- Laufzeit, Peak RSS, Hauptdatei und WAL-Hochwasser;
- Writer-Lock-Dauer und Fortschrittskosten;
- paralleler read-only Leser: nur vollständiges Alt oder vollständig Neues;
- konkurrierender Writer gemäß festgelegtem Gate;
- injizierter Projector-Fehler;
- kontrollierter Prozessabbruch/Kill, Reopen und Retry;
- zweiter Replay ohne Drift über alle zwölf Projektionsdigests;
- exakter Vorher-/Nachher-Vergleich des Event-Logs: null neue/geänderte Events;
- dieselben Messungen für Integrity und die relevante Deploysequenz;
- Pi-spezifische Abnahme mit vorab beschlossenen Zeit-/RAM-/WAL-/Lockbudgets.

### Nachteile und offene Risiken

- Die bedingte Empfehlung verzögert die endgültige Tabellenstrategie bis nach
  Messung.
- Option B kann bei großem WAL oder langer Sperre praktisch ausscheiden.
- Option C erhöht Schema-, Foreign-Key-, Speicher- und Cutover-Komplexität.
- Fortschritt innerhalb einer atomaren Transaktion darf keinen falschen
  öffentlich sichtbaren Zwischenstand suggerieren.
- Ein synthetischer Millionentest approximiert Payload- und Hardwareverhalten;
  eine getrennte Pi-Abnahme bleibt nötig.

### Menschlich zu entscheiden

- harte Invarianten (bounded, fixed head, no-write, atomic visibility);
- ob die B→C-Entscheidung experimentgegated bleiben darf;
- Batch-Default und konfigurierbarer Bereich;
- Zeit-, Peak-RAM-, WAL- und Lockbudgets auf dem Pi;
- Verhalten konkurrierender Writer und maximale Wartungsdauer;
- Shadow-/Cutover-Schwelle und Recovery-Artefakte;
- welche redundanten Deploy-Replays entfallen dürfen.

### Spätere ADR-Zuordnung

**ADR-0007 — Bounded Replay and Integrity Verification**

### Noch nicht erlaubt

Keine Replay-Batches, Cursoränderung, Shadow-Tabelle, temporäre Übernahme,
Integrity-Änderung, Benchmark-Gate oder Deployänderung.

## 6. A0.4 — Anchors, Key Custody und Ledger Repair

### Getrennte Entscheidungsfragen

1. Wo darf der private Anchor-Signaturschlüssel liegen?
2. Wer darf eine Signatur auslösen?
3. Wie funktionieren Rotation, Widerruf, Verlust und Notbetrieb?
4. Welche GitHub-Fläche ist Transport/Archiv und welche Instanz ist
   Vertrauenszeuge?
5. Unter welchen Bedingungen darf ein Reseal überhaupt stattfinden?
6. Soll langfristig ein erklärbares Multi-Epoch-Protokoll entstehen?

Diese Fragen teilen einen Trust Boundary, dürfen aber nicht zu einer
„Kryptografie-und-Reparatur“-Megaentscheidung verschmolzen werden.

### Bestätigter Repo-Befund

- `sealing.reseal()` entfernt temporär die UPDATE-/DELETE-Schutztrigger und
  überschreibt `prev_seal`/`seal` aller Post-Präfix-Zeilen. Es erzeugt keinen
  historischen Reseal-/Maintenance-Beleg.
- `--force` erlaubt Reseal trotz intakter Kette; Grund, Operator, Approver,
  Backup, letzter Anchor und Bereich sind keine technischen Pflichtgates. Der
  CLI committet vor der abschließenden Seal-Prüfung.
- `epoch_event()` und Verifier verwenden die erste Epoche; eine weitere
  erklärbare Repair-Epoche wird nicht unterstützt.
- Anchor v1 schreibt und verlangt `signature=null`; Signaturprüfung, Key-ID,
  Rotation und Widerruf fehlen.
- Der Pi erzeugt und veröffentlicht Status/Anchor selbst; derselbe
  repository-weite Deploy Key besitzt weiterhin Schreibrecht.
- Anchor-Dateinamen sind pro Core/Head/Hash, aber nicht pro Ausstellung oder
  Signaturschlüssel eindeutig; eine Same-Head-Ausgabe kann denselben Pfad
  überschreiben.
- Ein Anchor bezeugt nur den Präfix bis zu seinem Head. Adaptive Änderung nach
  diesem Head lässt den alten Anchor für seinen Präfix gültig.

### Schlussfolgerung

Ledger-Produktion, Signaturautorität und öffentliche Verwahrung müssen getrennte
Vertrauensdomänen sein. Branch Protection schützt die Ref-Historie, ersetzt aber
weder append-only Dateiregeln noch eine Signatur. Reseal ist keine normale
Reparatur, und ein Event in der danach selbst neu versiegelten Kette kann den
Vorgang nicht unabhängig bezeugen.

### Key-Custody-Optionen

| Option | Beschreibung | Stärke | Grenze |
|---|---|---|---|
| **A — Signaturschlüssel auf dem Pi** | Pi erzeugt Candidate und Signatur. | einfachster Automatismus | kompromittierter Pi kontrolliert Wahrheit und Zeugen; verletzt harte Zielgrenze |
| **B — verschlüsselter Workstation-Key** | separater Rechner; manuell entsperrter exportierbarer Software-Key | praktikabler Start, einfache Sicherung | Workstation-/Passphrase-Kompromittierung; Schlüssel kopierbar |
| **C — Hardware-Token** | Signatur auf separater Vertrauensstation mit PIN/Touch | Private Key nicht exportierbar; klare Bedienfreigabe | Geräteverlust, Treiber-/Algorithmus-Support und Recovery nötig |
| **D — getrennter Online-Key plus Offline-Recovery-Key** | Routine-Signer außerhalb des Pi; zweiter Schlüssel offline verwahrt | expliziter Notfall-/Rotationspfad | mehr Schlüsselrollen; Online-Key bleibt kompromittierbar, wenn er als Softwaredienst läuft |

### Harte Zielgrenzen

- Ein Signatur-Private-Key liegt niemals auf dem Pi.
- Der Pi erzeugt höchstens kanonische unsigned Anchor Candidates.
- Öffentliche Prüfschlüssel und Trust-Manifeste dürfen verteilt werden.
- Eine separate menschlich kontrollierte Vertrauensstation prüft und signiert.
- Key-ID und Algorithmus sind Teil des Anchor-Vertrags.
- Rotation, Widerruf und Verlust sind versionierte historische Vorgänge.
- Schlüsselverlust führt nicht zum Umschreiben alter Geschichte.
- Unsigned Anchors sind keine unabhängige kryptografische Bezeugung.
- Eine heutige Signatur über einen alten v1-Anchor ist eine heutige
  retrospektive Bezeugung, keine rückdatierte historische Signatur.
- Keine Eigenkryptografie; Algorithmus und Bibliothek folgen einem gesonderten
  menschlichen Security-Review.

### Empfehlung zur menschlichen Prüfung: Key Custody

**Option C als Routine-Primärschlüssel plus der Offline-Recovery-Anteil von
Option D.** Hardware-/Bibliothekskompatibilität muss vor Annahme praktisch
geprüft werden. Option B ist nur als ausdrücklich befristete Übergangslösung mit
Enddatum, Rotation und offline verwahrtem Recovery-Pfad vertretbar. Option A ist
mit der erforderlichen Trennung unvereinbar.

Eine Signatur darf nur nach menschlichem Auslösen oder einer ausdrücklich
entschiedenen Mehrpersonenregel entstehen. Der Signierplatz prüft mindestens
Candidate-Schema, Core/Epoche, monotone Head-Entwicklung, Vorgängeranchor,
Integrity-/Seal-Receipt und gegebenenfalls Repair-Manifest. Bei Ausfall bleiben
Candidates `PENDING/UNTRUSTED`; sie werden nicht als extern bezeugt bezeichnet.

### Anchor-v2-Vertrag zur Entscheidung

Empfohlen wird ein versioniertes v2-Envelope statt einer stillen Erweiterung
von v1 oder einer lose gekoppelten `.sig`-Datei. Die genaue Struktur ist noch
nicht beschlossen; erforderlich sind mindestens:

```text
genus-ledger-anchor-v2
  statement:
    core_id
    epoch_id
    head_event_id
    head
    event_count
    created_at
    predecessor_anchor_digest
    repair_manifest_digest?
  signatures[]:
    key_id
    algorithm
    signed_at
    signature
```

Signiert werden domain-separierte kanonische Bytes des `statement`, nicht ein
Objekt mit eigener Signatur. Zu entscheiden sind Kanonisierung, Domain
Separation, Algorithmus, Key-ID-Format, Ein-/Mehrsignatur, Legacy-v1-Verhalten,
Anchor-Kadenz und genaue Aussage. `created_at`/`signed_at` sind ohne externen
Zeitstempeldienst keine vertrauenswürdige Zeitbehauptung.

### GitHub als Transport- und Archivfläche

Die bereits separat aktivierte Force-/Delete-Sperre ist eine sinnvolle
kurzfristige Härtung, aber nicht hinreichend. Als weitere, noch nicht
implementierte Ziele gelten:

- vorhandene Anchor-Dateien dürfen in späteren Commits nicht geändert oder
  gelöscht werden;
- jede Ausstellung erhält einen eindeutigen append-orientierten Pfad;
- ein Required Check prüft alte Anchor-Digests, Candidate-/Signaturschema,
  Trust-Manifest und Monotonie;
- normale neue Status-Snapshots bleiben zulässig;
- der Pi besitzt keine Bypass- oder Signaturautorität;
- bevorzugte Zielarchitektur ist eine signer-owned Witness-Fläche oder ein
  unabhängiger Mirror; GitHub allein ist nicht die Signaturautorität.

GitHub Deploy Keys besitzen keine Pfadrechte. Solange der Pi-Key repo-weit
schreiben darf, kann er per normalem Fast-Forward-Commit Status- und
Anchor-Dateien ändern. Kryptografisch gültige Signaturen müssen solche Dateien
unterscheidbar machen; ein unabhängiger Witness muss Löschung/Ersetzung erkennen.

### Kurzfristige menschliche Reseal-Zeremonie

Default-Empfehlung: **kein Production-Reseal**, solange Golden Ledger,
Recovery-Gates und externe Signatur nicht beschlossen und abgenommen sind. Eine
ausdrücklich freigegebene Verfügbarkeitsnotlage folgt mindestens dieser
Zeremonie:

1. alle Writer stoppen;
2. DB, WAL und SHM unverändert kopieren und hashen;
3. letzten gültigen externen Anchor und seinen ursprünglichen Ort sichern;
4. Backup auf getrenntem Medium verifizieren und Restore-Probe ausführen;
5. dokumentierten Schaden/technischen Grund, Incident-ID, Operator,
   unabhängigen Approver und betroffenen Eventbereich festhalten;
6. alten Head, erste untrusted Position und erwartete Anchor-Auswirkung fixieren;
7. ausdrückliche menschliche Freigabe erteilen;
8. Reseal ausschließlich im Wartungsfenster auf der Arbeitskopie ausführen;
9. Trigger, Seal, Integrity und Golden Replay vor Freigabe prüfen;
10. neuen Head und externen Wartungsbeleg erzeugen;
11. auf separater Vertrauensstation signieren;
12. neuen ausstellungs-eindeutigen Anchor append-only veröffentlichen;
13. alte Anchors und Originalabbild unverändert erhalten;
14. bei jedem Fehler pausiert bleiben und auf den gesicherten Zustand
    zurückgehen.

Ein `ledger_resealed`-Event in derselben neu versiegelten Kette wäre allein kein
kryptografischer Beweis: Der Akteur, der die Kette neu berechnet, könnte dieses
Event und seine Position ebenfalls neu berechnen. Beweiskraft entsteht erst aus
vorherigem Anchor/Backup, externem Wartungsbeleg und Signatur einer getrennten
Autorität.

### Langfristige Multi-Epoch-Richtung

Der aktuelle Code ist Single-Epoch. Multi-Epoch ist eine neue
Protokollversion, kein kleiner Patch. Empfohlene Richtung ist eine explizite
Repair-Transition:

- beschädigte Epoche und alte Anchors bleiben historisch sichtbar;
- letzte vertrauenswürdige Eventposition und letzter gültiger Anchor werden
  benannt;
- erste untrusted/beschädigte Position und beobachteter beschädigter Head
  werden gebunden;
- Incident-/Repair-Manifest, Grund und menschliche Freigabe tragen Digests;
- eine neue Epoche bindet Vorgänger, Schadensgrenze, Repair-Artefakt,
  Algorithmus und zulässige Prüfschlüssel;
- der Verifier erklärt je Epoche mindestens `valid`, `broken`,
  `untrusted_tail`, `repair_transition_valid` oder `unsupported`;
- bei semantisch nicht reparierbarer Historie beginnt eine neue
  Ledger-Generation, deren Lineage auf die unverändert quarantänisierte alte
  Generation verweist.

### Nachteile und offene Risiken

- Hardware-Token und Recovery erhöhen Bedien-, Geräte- und
  Langzeitkompatibilitätsaufwand.
- Signatur schützt nicht automatisch Verfügbarkeit, Vertraulichkeit oder einen
  vertrauenswürdigen Zeitpunkt.
- Ein signer-owned Witness-Repo schafft zusätzliche Infrastruktur und
  Berechtigungen.
- Multi-Epoch erweitert Event-/Seal-/Anchor-Vertrag, Verifier, Golden Corpus,
  Migration und Incident-Runbook zugleich.
- Anchor-Kadenz, maximaler unanchored Tail und Widerrufsfenster sind noch offen.
- Der tatsächliche heutige Speicherort des Status-Private-Keys bleibt
  **UNKNOWN**; er wird in diesem Packet nicht geprüft oder verändert.

### Menschlich zu entscheiden

- Primär- und Recovery-Custody samt Besitzern und Orten;
- Signaturauslöser und gegebenenfalls Mehrpersonenregel;
- Algorithmus/Bibliothek nach Hardware-/Langzeitprüfung;
- Anchor-v2-Kanonisierung, Aussage, Kadenz und Legacy-v1-Status;
- Rotation, Widerruf, Verlust und rückwirkendes Unsicherheitsfenster;
- Witness-Topologie und notwendige GitHub-/Append-only-Checks;
- Reseal-Default, Ausnahmegrund und Approval-Schwelle;
- Repair-Transition gegenüber neuer Ledger-Generation;
- Aufbewahrungsdauer von DB/WAL/SHM, alten Anchors und Repair-Belegen.

### Spätere ADR-Zuordnung

**ADR-0008 — External Anchor Trust, Key Custody and Ledger Repair**

### Noch nicht erlaubt

Keine Anchor-v2-Datei, Signatur, Schlüssel-/Token-Erzeugung, Rotation,
Widerruf, Reseal-Gates, Multi-Epoch-Änderung, Witness-Repo-Änderung oder weitere
GitHub-Einstellung.

## 7. Human-owned critical lane

A0 berührt Schema, Ledger, Replay, Sealing, Anchors, Integrity und kritische
Governance. Für die spätere Implementierung ist dieser Scope verbindlich
**human-owned critical lane**:

- kein GENUS-generierter Modellpatch;
- keine automatische Coding-Membran und keine kritischen Dateien im
  Modellscope;
- keine selbstdefinierte Abnahme;
- kein automatischer Commit, Merge, Push oder Deploy;
- der Mensch besitzt Patchhoheit, unabhängiges Review, Freigabe, Merge,
  Key-Ceremony und Laufzeitabnahme.

Das verbietet keine KI-Unterstützung beim Denken. KI darf Analyse, Threat
Modeling, Testfalldesign, Gegenbeispiele, Dokumentationsentwürfe, Review und
Diff-Erklärung unterstützen. Sie ist weder verantwortlicher Autor der
kritischen Implementierung noch Freigeber. Diese Grenze folgt der Risikostufe
`critical` in `docs/design/SELF_CODING.md` und der monotonen Autorität aus
ADR-0004.

## 8. Isolated non-production learning lane

Für den Scope dieses Packets gilt als vorgeschlagene Planungsgrenze:

- **Produktlinie:** Sobald A0 durch ADRs und Roadmap aktiviert wird, ist es der
  einzige mergefähige aktive Veränderungspfad im kritischen
  `GENUS_PI_SEED`-Kern.
- **Isolierte Lernlinie:** Der Entwickler-Loop darf parallel nur in
  synthetischen Repositories, isolierten Worktrees, `GENUS_EGG`, `GENUS_CORE`
  oder nicht produktiv gemergten Übungsaufgaben lernen.

Harte Grenzen:

- kein konkurrierender `GENUS_PI_SEED`-Produktmerge;
- keine Rechteausweitung;
- keine kritischen Dateien im Modellscope;
- keine Produktdaten;
- keine automatische Aktivierung.

Die Begriffe sind **human-owned critical lane + isolated non-production
learning lane**. Das ist kein zweiter aktiver Produktpfad. Weil die aktuelle
Roadmap noch H1.2 als aktiv nennt, wird diese vorgeschlagene A0-Grenze erst nach
Ronnys Entscheidung, angenommenen ADRs und einer gesonderten Roadmap-Änderung
operativ verbindlich.

## 9. Technische Abhängigkeitsreihenfolge

Die Reihenfolge folgt Beweisabhängigkeiten, nicht den Nummern der ADRs:

1. **Menschliche Entscheidungen und vorgeschlagene ADRs 0005–0008.** Ohne
   Version, Oracle-Governance, Replay-Invarianten und Key-Custody ist kein
   verändernder Scope bestimmt.
2. **Golden Ledger und unabhängiges Orakel.** Es muss vor einem produktiv
   nutzbaren Migration Runner und vor der endgültigen Replay-Topologie bestehen;
   sonst definieren Transformation/Optimierung ihre eigene Erwartung.
3. **Read-only Schemaerkennung.** Version/Fingerprint/Kompatibilitätsstatus kann
   als erste nichtmutierende Scheibe entstehen und hilft, Golden-Altformen
   explizit zu klassifizieren. Sie autorisiert noch keine Migration.
4. **Bounded Replay-/Integrity-Prototyp gegen Fixture und Größenklassen.** Erst
   Messung entscheidet zwischen einer atomaren Batch-Transaktion und Shadow-
   Projektionen.
5. **Migration Runner ausschließlich gegen Kopien.** Abnahmefolge:
   Alt-Schemafixture → explizite Migration → gewählter bounded Replay → zweiter
   Replay → Golden Oracle/Integrity/Seal/Anchor; keine Produktmigration.
6. **Key-Custody- und Anchor-v2-Vertrag.** Custody, Algorithmus, Trust-Manifest,
   Rotation/Widerruf und signierte Bytes müssen vor Signaturcode entschieden
   sein. Dieser Entscheidungsstrang kann organisatorisch parallel zu 2–5
   vorbereitet werden, öffnet aber keinen zweiten Produktmerge.
7. **Status-/Witness-Härtung.** Force-/Delete-Sperre ist bereits separat aktiv.
   Append-only Pfade, Checks, Publisher-Minimierung und Witness-Trennung hängen
   vom Anchor-v2-Vertrag ab.
8. **Signierte Anchors und Recovery-Drill.** Erst nach getrenntem Signierer,
   Verifier, Legacy-Regel, Rotation/Widerruf und öffentlicher Prüfung.
9. **Kurzfristige Reseal-Zeremonie.** Nur als eigener menschlich freigegebener
   Incident-Pfad nach Golden/Backup/Signatur; kein Routinebetrieb.
10. **Multi-Epoch-Protokoll.** Zuletzt, weil es Ledger-, Seal-, Anchor-,
    Integrity-, Migration- und Recovery-Vertrag gemeinsam versioniert und die
    gebrochene Geschichte erhalten muss.

### Warum diese Reihenfolge

- Golden Ledger muss vor einem vertrauenswürdigen Migration Runner stehen;
  Framework-Gerüst und Corpus-Design dürfen gemeinsam entstehen, aber der Runner
  ist ohne Orakel nicht abnahmefähig.
- Das Oracle steht vor der endgültigen Replay-Optimierung, weil Batch- und
  Cutover-Varianten alle zwölf Projektionen semantisch vergleichen müssen.
- Read-only Schemaerkennung ist unabhängig von produktiver DDL und kann früh
  gebaut werden.
- Anchor v2 benötigt zuerst Key-Custody-, Kanonisierungs- und
  Widerrufsentscheidungen; ein Signaturfeld allein wäre kein Trust-Vertrag.
- Minimaler Ref-Schutz ist unabhängig und bereits erfolgt; Dateinamens-/Witness-
  Härtung benötigt den Anchor-v2-Vertrag.
- Reseal/Multi-Epoch kommen spät, weil sie Beweis und Reparatur nicht vom selben
  ungesicherten Zustand ableiten dürfen.

Diese Reihenfolge ist eine Empfehlung in einem Report. Erst angenommene ADRs und
`docs/ROADMAP.md` dürfen sie verbindlich machen.

## 10. Vorgeschlagene ADR-Landkarte

| Kandidat | Entscheidet | Entscheidet ausdrücklich nicht |
|---|---|---|
| **ADR-0005 — Explicit Schema Evolution and Migration Boundary** | Version/Fingerprint, Runner, Startup-Verweigerung, Migrationstypen, Backup/Recovery, human-owned Autorität | Golden-Inhalt, Reseal, Signatur |
| **ADR-0006 — Golden Ledger and Independent Replay Oracle** | Fixture-Provenienz, Datenschutz, Kanonisierung, zwölf Digests, Oracle-Governance, CI-/Migrationsmatrix | Produktmigration, Key Custody |
| **ADR-0007 — Bounded Replay and Integrity Verification** | fixed head, bounded stream, Transaktionsownership, Topologie-Gate, Progress, Pi-/Crash-/Concurrency-Abnahme | Schemaänderung, Reseal |
| **ADR-0008 — External Anchor Trust, Key Custody and Ledger Repair** | Anchor-v2-Aussage, Signatur/Custody, Trust/Revocation, Witness, Reseal-Ausnahme, Multi-Epoch-Richtung | produktive Ausführung des jeweiligen Incidents |

ADR-0005 und ADR-0006 können in derselben menschlichen Sitzung entschieden
werden. Ein verändernder Migration Runner darf aber nicht mergefähig werden,
bevor das ADR-0006-Orakel als unabhängige Testbasis verfügbar ist. ADR-0007 darf
die Topologie bis zum Experiment offen lassen, nicht jedoch die Bounded-/No-
Write-/Atomic-Visibility-Invarianten. ADR-0008 benötigt mehrere explizite
Unterentscheidungen; sein Titel allein ist keine Freigabe.

## 11. Decision Sheet für Ronny

Keine Checkbox ist vorausgefüllt. `accept recommendation` nimmt nur die hier
formulierte Architekturentscheidung an; es autorisiert noch keinen Patch,
Produktlauf, Commit, Push oder Deploy. Notizen sollten Entscheidung, Abweichung,
Owner, Datum und offene Bedingung nennen.

### D-A0.1 — Schema Evolution

| Feld | Inhalt |
|---|---|
| **Frage** | Soll Schemaänderung strikt von Connect/Startup getrennt und nur durch einen expliziten human-owned Runner ausgeführt werden? |
| **Empfohlene Antwort** | Option C: explizite Version + Fingerprint, read-only `db status`, Fail-Closed, manueller forward-only Runner; Copy/Cutover für riskante Klassen. |
| **Alternative** | Option B: nummerierte Migration automatisch beim Startup; Option A: Status quo. |
| **Unmittelbare Folge** | ADR-0005 spezifizieren; unterstützte Versionen, Journal, Gates und Recovery festlegen; noch keine Implementierung. |
| **Risiko bei Aufschub** | Normale Dienste behalten implizite DDL-Autorität; kein belastbarer Altversion-/Recovery-Vertrag. |
| **Spätere ADR-Datei** | `docs/decisions/ADR-0005-EXPLICIT-SCHEMA-EVOLUTION.md` |

RONNY DECISION:

- [ ] accept recommendation
- [ ] choose alternative
- [ ] defer

Note:

---

### D-A0.2 — Golden Ledger and Oracle

| Feld | Inhalt |
|---|---|
| **Frage** | Soll eine datenschutzfreie handgeprüfte historische Fixture mit unabhängig versioniertem Oracle die gemeinsame Beweisbasis für Replay und Migration werden? |
| **Empfohlene Antwort** | Option C: statische SQLite-Altfixture + deterministischer menschenlesbarer Export + separates handgeprüftes Manifest/Oracle; Signatur erst additiv nach ADR-0008. |
| **Alternative** | Nur frische CI-DBs oder runtime-generiertes „Golden“; langfristig ein größerer mehrstufiger Corpus. |
| **Unmittelbare Folge** | ADR-0006 spezifizieren; Owner, Kanonisierung, 13-Punkte-Coverage und Oracle-Änderungsprozess festlegen. |
| **Risiko bei Aufschub** | Migration und Replay-Optimierung könnten Fehler und Erwartung gemeinsam verschieben. |
| **Spätere ADR-Datei** | `docs/decisions/ADR-0006-GOLDEN-LEDGER-ORACLE.md` |

RONNY DECISION:

- [ ] accept recommendation
- [ ] choose alternative
- [ ] defer

Note:

---

### D-A0.3 — Replay Atomicity Strategy

| Feld | Inhalt |
|---|---|
| **Frage** | Welche Sichtbarkeits-/Recovery-Topologie soll bounded Replay und Integrity verwenden? |
| **Empfohlene Antwort** | Invarianten jetzt annehmen; Option B (bounded Cursor in einer atomaren Transaktion) experimentell prüfen und nur bei bestandenen Pi-/Reader-/Kill-/WAL-Gates wählen, sonst Option C Shadow-Projektionen. Option D dient Kopien/Migrationsvalidierung. |
| **Alternative** | Option C sofort festlegen; Option D als Live-Blue/Green; Option A beibehalten. |
| **Unmittelbare Folge** | ADR-0007 zunächst mit festem Head, No-Write, vollständigem Oracle und Experimentgate spezifizieren; Topologie bleibt bis zu Messwerten offen. |
| **Risiko bei Aufschub** | Replay/Integrity bleiben O(N) RAM ohne Crash-/Pi-Budget; Migrationen haben keinen skalierten Verifikationspfad. |
| **Spätere ADR-Datei** | `docs/decisions/ADR-0007-BOUNDED-REPLAY-INTEGRITY.md` |

RONNY DECISION:

- [ ] accept recommendation
- [ ] choose alternative
- [ ] defer

Note:

---

### D-A0.4 — Key Custody

| Feld | Inhalt |
|---|---|
| **Frage** | Wo liegen Primär- und Recovery-Schlüssel, und wer darf eine Anchor-Signatur auslösen? |
| **Empfohlene Antwort** | Hardware-Token auf separater Vertrauensstation als Primärschlüssel; verschlüsseltes Offline-Recovery-Medium an getrenntem Ort; menschlicher Trigger/Approver. Workstation-Software-Key nur befristete Übergangslösung. |
| **Alternative** | Dauerhafter verschlüsselter Workstation-Key; separater Online-Software-Signer plus Offline-Recovery. Pi-Key ist ausgeschlossen. |
| **Unmittelbare Folge** | Custody Owner, Ort, Algorithmuskompatibilität, Mehrpersonenregel, Rotation, Widerruf und Verlustfall vor Implementierung festlegen. |
| **Risiko bei Aufschub** | Anchors bleiben unsigned; Status-Transport kann keinen unabhängigen kryptografischen Zeugen darstellen. |
| **Spätere ADR-Datei** | `docs/decisions/ADR-0008-EXTERNAL-ANCHOR-TRUST.md` |

RONNY DECISION:

- [ ] accept recommendation
- [ ] choose alternative
- [ ] defer

Note:

---

### D-A0.5 — Anchor v2

| Feld | Inhalt |
|---|---|
| **Frage** | Soll Anchor v2 ein kanonisches, domain-separiert signiertes Envelope mit Key-ID, Algorithmus, Epoche und Vorgängerbindung sein? |
| **Empfohlene Antwort** | Ja; signiertes `statement` plus getrennte Signaturliste, ausstellungs-eindeutiger append-only Pfad, Legacy-v1 bleibt unverändert unsigned. GitHub ist Transport, signer-owned Witness die Zielautorität. |
| **Alternative** | Detached `.sig` neben v1 oder minimale nicht-null-Erweiterung von v1. |
| **Unmittelbare Folge** | Exakte signierte Bytes, Aussage/Nichtgarantien, Kadenz, Trust-Manifest und Verifier-Testvektoren menschlich spezifizieren. |
| **Risiko bei Aufschub** | Pi und Veröffentlichungsrepo bleiben einzige operative Herkunft; Same-Head-Dateien können weiter überschrieben werden. |
| **Spätere ADR-Datei** | `docs/decisions/ADR-0008-EXTERNAL-ANCHOR-TRUST.md` |

RONNY DECISION:

- [ ] accept recommendation
- [ ] choose alternative
- [ ] defer

Note:

---

### D-A0.6 — Reseal Ceremony

| Feld | Inhalt |
|---|---|
| **Frage** | Unter welchen Ausnahmebedingungen darf vor einem Multi-Epoch-Protokoll ein Production-Reseal stattfinden? |
| **Empfohlene Antwort** | Default verboten; nur dokumentierte Verfügbarkeitsnotlage mit Writer-Stopp, unverändertem Backup/Restore-Test, letztem Anchor, Operator + separatem Approver, Bereich, externem Maintenance-Receipt, externer Signatur und erhaltenen alten Anchors. |
| **Alternative** | Absolutes Verbot bis Multi-Epoch; weniger strenge Solo-Zeremonie mit ausdrücklich dokumentierter Ausnahme. |
| **Unmittelbare Folge** | Approval-Schwelle, Incident-Klassen, Belegformat, Abbruch-/Restore-Regel und Aufbewahrung entscheiden; noch kein Gate implementieren. |
| **Risiko bei Aufschub** | Der heutige `--force`-Pfad bleibt technisch ausführbar, ohne die dokumentierte Norm maschinell zu erzwingen. |
| **Spätere ADR-Datei** | `docs/decisions/ADR-0008-EXTERNAL-ANCHOR-TRUST.md` |

RONNY DECISION:

- [ ] accept recommendation
- [ ] choose alternative
- [ ] defer

Note:

---

### D-A0.7 — Multi-Epoch Direction

| Feld | Inhalt |
|---|---|
| **Frage** | Soll Ledger Repair langfristig als explizite neue Epoche mit sichtbarer Schadensgrenze statt als kosmetisches In-place-Neusiegeln modelliert werden? |
| **Empfohlene Antwort** | Ja: Repair-Transition bindet letzte vertrauenswürdige Position, erste untrusted Position, alten Anchor, Damage-/Repair-Manifest und neue Epoche; nicht reparierbare Fälle beginnen eine neue Ledger-Generation mit Lineage. |
| **Alternative** | Single-Epoch dauerhaft beibehalten und Reseal vollständig verbieten; neue Ledger-Generation für jeden Schaden. |
| **Unmittelbare Folge** | Nur Protokollrichtung annehmen; Zustandsautomat, Epochenverifier und E2→neue-Generation-Schwelle später getrennt spezifizieren. |
| **Risiko bei Aufschub** | Es gibt keinen erklärbaren, historisch sichtbaren Repair-Pfad; ein späterer Incident erzwingt Ad-hoc-Entscheidungen. |
| **Spätere ADR-Datei** | `docs/decisions/ADR-0008-EXTERNAL-ANCHOR-TRUST.md` |

RONNY DECISION:

- [ ] accept recommendation
- [ ] choose alternative
- [ ] defer

Note:

---

### D-A0.8 — Parallel Developer-Loop Boundary

| Feld | Inhalt |
|---|---|
| **Frage** | Soll eine aktivierte A0-Produktlinie der einzige mergefähige kritische Pfad sein, während der Entwickler-Loop nur isoliert und nicht produktiv lernt? |
| **Empfohlene Antwort** | Ja: human-owned critical lane + isolated non-production learning lane; keine kritischen Modellfiles, Produktdaten, Rechteausweitung oder konkurrierenden Produktmerges. |
| **Alternative** | Parallele Produktentwicklung zulassen, aber mit getrennten Integrationsfenstern; erhöht Drift- und Abnahmerisiko. |
| **Unmittelbare Folge** | Nach Annahme der A0-ADRs die tatsächliche Aktivierung gesondert in ROADMAP/NOW entscheiden; ADR-0004-Grenze explizit bestätigen. |
| **Risiko bei Aufschub** | Kritische Fundamentänderungen und andere Produktänderungen können Evidenzbasis, Merge-Reihenfolge und Laufzeitabnahme vermischen. |
| **Spätere ADR-Datei** | ADR-0004 als bestätigte Grenze; bei neuer bindender Scope-Regel ein eigener Folge-ADR durch Ronny |

RONNY DECISION:

- [ ] accept recommendation
- [ ] choose alternative
- [ ] defer

Note:

## 12. Nicht-Ziele und Stopplinie

Dieses Packet implementiert oder autorisiert ausdrücklich nicht:

- `schema_migrations`, Schema-Versionen oder neue CLI-Befehle;
- Golden Ledger, SQL-/SQLite-/JSONL-Fixtures oder Oracle-Dateien;
- Replay-Batches, Cursor, Shadow-Projektionen oder temporäre Cutover-Logik;
- Anchor v2, Signaturen, Schlüssel, Trust-Manifeste oder Testschlüssel;
- Reseal-Gates, einen Reseal oder ein Multi-Epoch-Protokoll;
- Änderungen an Runtime, Schema, Tests, CI, Deploy oder Produktdaten;
- weitere Branch-Protection-/GitHub-Regeln oder Deploy-Key-Änderungen;
- `NOW.md`-/`ROADMAP.md`-Änderungen;
- angenommene ADRs;
- Commit, Push, Pull Request oder Deploy für dieses Decision Packet.

Insbesondere wurden keine Checkboxes ausgefüllt. Die vier ADR-Kandidaten sind
Namen und Zuständigkeitsvorschläge, keine angelegten oder angenommenen
Entscheidungen.

## 13. Evidenz und Verifikation

### Vollständig gelesene Entscheidungsbasis

- `docs/reports/2026-08-09-a0-foundation-audit.md`
- `docs/README.md`
- `docs/CHARTER.md`
- `docs/NOW.md`
- `docs/ROADMAP.md`
- `docs/ARCHITECTURE.md`
- `docs/EVENT_CONTRACT.md`
- `docs/SECURITY_MODEL.md`
- `docs/QUALITY.md`
- `docs/design/SELF_CODING.md`
- ADR-0001 bis ADR-0004

Der Commitvergleich wurde mit `git rev-parse HEAD`, `git log`, `git show` und
`git diff --stat cadcda8..cd22fc4` durchgeführt. Geprüfter Packet-Commit ist
`cd22fc42cab9d5a693336f47ffea7aaf53782d2f`; Auditbasis ist
`cadcda834a5d8e61be357f90b0db11c284ea9a9a`.

### Dokumentprüfungen

```text
.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider \
  tests/test_docs_structure.py \
  tests/test_event_contract_docs.py \
  tests/test_atlas_facts.py

9 passed
```

Strukturprüfungen des Decision Sheets:

- achtmal `[ ] accept recommendation`;
- achtmal `[ ] choose alternative`;
- achtmal `[ ] defer`;
- null vorausgefüllte Checkboxen;
- null TODO/TBD/PLACEHOLDER;
- genau ein Index-Link auf dieses Packet.

### Finaler Diff-Scope

Der erwartete Arbeitsumfang dieses Packets besteht ausschließlich aus:

- `docs/reports/2026-08-09-a0-decision-packet.md`
- `docs/README.md`

```text
git diff --check
→ Exit 0, keine Ausgabe

git status --short
→  M docs/README.md
→ ?? docs/reports/2026-08-09-a0-decision-packet.md

git diff --stat
→ docs/README.md | 1 +
```

`git diff --stat` zeigt nur bereits getrackte Dateien; der neue Report bleibt
bis zu einer späteren ausdrücklichen menschlichen Entscheidung untracked und
wird deshalb dort nicht mitgezählt. Maßgeblich für die vollständige Liste ist
`git status --short`.

### Scope-Bestätigung

Die vor diesem Packet separat und ausdrücklich angeordnete Branch-Protection-
Härtung ist in Abschnitt 1 offengelegt. Für die Erstellung dieses Decision
Packets selbst gilt:

**No runtime, schema, ledger, replay, seal, anchor, key, GitHub setting or production data was modified.**
