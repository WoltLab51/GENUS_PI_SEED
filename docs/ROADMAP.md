# GENUS · Roadmap

> **Status:** aktuelle Zukunftsplanung
>
> **Stand:** 9. August 2026
>
> **Enthält:** Reihenfolge, Abhängigkeiten und Definition of Done – keine
> Bauchronik und keine flüchtigen Live-Zahlen

Die Roadmap sichert zuerst das A0-Wahrheitsfundament und führt danach vom
gehärteten Kern zum persönlichen, lernenden Begleiter. Der aktuelle
Ausgangspunkt steht in [NOW.md](NOW.md), ausgelieferte Etappen im
[history/BUILD_JOURNAL.md](history/BUILD_JOURNAL.md).

## Nordstern

GENUS wächst vom Wahrnehmen über Wissen und Verstehen zum Können und Erschaffen –
und wendet diese Fähigkeiten schließlich kontrolliert auf sich selbst an. Jede
Erkenntnis und jede Veränderung bleibt belegbar, prüfbar und im Dienst des
Menschen.

## So wird diese Karte benutzt

1. Es gibt genau **einen aktiven Entwicklungsschritt**. Reine Mess- und
   Sicherungsarbeiten dürfen daneben laufen, solange sie den Zustand nicht
   konkurrierend verändern.
2. Ein Schritt beginnt mit Material, Ereignisvertrag, Risiko und Messplan.
3. Er endet erst, wenn seine Definition of Done im Repo **und** auf dem Pi gilt.
4. Neue Erkenntnis darf die Route ändern. Die Leitplanken ändern sich nicht
   stillschweigend.

## Die Abhängigkeiten

```text
A0.2 Golden Ledger + Oracle ──> A0.1 read-only Schemaerkennung
A0.1 + A0.2 ──────────────────> A0.3 B/C-Experiment

A0.1 + A0.2 + A0.3 ──> Migration Runner nur auf Kopien
A0.2 ──> A0.4 Custody-/Anchor-v2-Vertrag ──> Witness ──> Signatur
                                                        └──> Reseal-Zeremonie
                                                             └──> Multi-Epoch

A0-Wahrheitsfundament ──> H1 Begleiter ──> H2 Fähigkeitsloop ──> H3 Erschaffen
zulässige H0-Read-only-Teile ─┘                    │
                                                  └──> H4 Markt-Membran

H3 + geklärte Isolation/Löschung/Governance ─────────> H5 Föderation
```

Die Horizonte sind keine Versionsnummern. Ein später Horizont darf erforscht,
aber nicht als Produktpfad geöffnet werden, bevor seine Abhängigkeiten grün sind.

## A0 · Wahrheitsfundament vor Migration

**Status:** einziger mergefähiger aktiver Produktpfad; in A0.2 ist nach Annahme
des Golden-JSONL-/Replay-Oracle-Teils nur noch das historische SQLite-Gate aktiv.

**Ziel:** Bevor GENUS Schema, Replay, Integrity, Seals oder Anchors verändert,
besitzt es eine unabhängige semantische Beweisbasis, explizite
Migrationsgrenzen, bounded Laufzeitmechanik und extern getrenntes
Anchor-Vertrauen. Die angenommenen Verträge stehen in
[ADR-0005](decisions/ADR-0005-EXPLICIT-SCHEMA-EVOLUTION.md),
[ADR-0006](decisions/ADR-0006-GOLDEN-LEDGER-ORACLE.md),
[ADR-0007](decisions/ADR-0007-BOUNDED-REPLAY-INTEGRITY.md),
[ADR-0008](decisions/ADR-0008-EXTERNAL-ANCHOR-TRUST.md) und
[ADR-0009](decisions/ADR-0009-HUMAN-OWNED-CRITICAL-LANE.md).

Die technische Reihenfolge folgt Beweisabhängigkeiten, nicht der Nummer der
Auditkapitel.

### A0.2 · Golden Ledger und unabhängiges Oracle

**Abhängigkeit:** angenommene ADRs und menschliches Fixture-/Oracle-Ownership.

**Stand 13. August 2026:** Golden Ledger V2 und unabhängiges Replay-Oracle sind
hashgebunden, menschlich angenommen und als versioniertes Testfundament
abgeschlossen. Das historische SQLite-Artefakt bleibt der aktive, separat
abzunehmende A0.2-Teilschritt; A0.2 insgesamt ist deshalb noch nicht abgeschlossen.

**Arbeit:** Eine kanonische synthetische JSONL-Eventfixture, ein statisches,
unabhängig geprüftes Oracle-Manifest und eine daraus erzeugte temporäre
SQLite-Testdatenbank aufbauen. Eine kleine statische historische
SQLite-Altfixture ergänzt die reale Schema-Migrationsmatrix und wird vor dem
ersten Migration-Runner als eigenes A0.2-Gate fertiggestellt.

**Definition of Done**

- nichtleerer Legacy-Präfix, korrektes Epochen-/Genesis-Event und versiegelter
  Tail sind enthalten
- projizierte und bewusst rohe Eventtypen sowie die in ADR-0006 genannten
  fachlichen Zustände und Lebenszyklen sind abgedeckt
- Fixture enthält nur synthetische, nicht persönliche und nicht produktive Daten
- Eventzahl, IDs, Reihenfolge, Präfix, Genesis, Epoche, Head, Seal, Integrity und
  historischer Anchor sind festgeschrieben
- erwartete normalisierte Daten, Digest jeder Projektion und Gesamtdigest sind
  unabhängig versioniert
- Manifest bindet JSONL-Digest, Altfixture-Digest, historischen
  Schema-Fingerprint und die read-only bewiesene Eventstrom-Gleichheit
- Corpus Owner, Datenschutzprüfer, Oracle-Reviewer und Kanonisierungsvertrag
  sind vor Artefakterzeugung menschlich festgelegt
- zwei Replays erzeugen weder Events noch Drift; negative Tamper-Fälle schlagen an
- Oracle-Erwartungen werden nicht ausschließlich vom Runtime-Code unter Test
  erzeugt oder aktualisiert

### A0.1 · Explizite Schemaerkennung und Migration Boundary

**Abhängigkeit:** A0.2 definiert zuerst Corpus und Oracle. Eine ausschließlich
read-only Version-/Fingerprint-Erkennung darf danach als nichtmutierende Scheibe
entstehen; sie autorisiert keine Migration.

**Arbeit:** Normale Connect-/Startup-Pfade von Schemaänderung trennen,
Schema-Version und Fingerprint fail-closed erkennen und anschließend einen
manuell aufgerufenen, nummerierten Runner nur gegen Kopien entwickeln.

**Definition of Done**

- Statusabfrage verändert Datei, Schema und Ledger nicht
- alte, neue, unbekannte und teilweise migrierte Schemas werden eindeutig
  erkannt und verständlich verweigert
- normaler Connect und Dienststart führen an bestehenden Datenbanken keine DDL aus
- Migrationen sind nummeriert, deterministisch, idempotent und menschlich ausgelöst
- Backup, Restore-Probe, Integrity und Seal sind Vorbedingungen; ein gültiger
  externer Anchor ist zusätzliches Gate jedes späteren Produktlaufs nach A0.4,
  nicht des Kopien-Runners
- Alt-Schemafixture → Migration → gewählter bounded Replay → zweiter Replay →
  Golden Oracle/Integrity/Seal/Anchor ist auf einer Kopie grün
- keine Produktmigration wird durch diesen Schritt automatisch freigegeben
- ein grünes Kopien-Receipt braucht vor Produkt-Cutover ein zweites gebundenes
  Human-Go; nach Cutover bleibt der Dienst bis zum grünen read-only
  Post-Cutover-Receipt gestoppt

### A0.3 · Bounded Replay und Integrity topologiegegated entscheiden

**Abhängigkeit:** A0.2 ist grün; die read-only Schemaerkennung aus A0.1 steht vor
Replay einer fremden Datenbank. Ein verändernder Migration Runner wartet auf
Golden Oracle und die A0.3-Abnahme.

**Arbeit:** Vollständiges `fetchall()` durch einen fixed-head, deterministisch
geordneten und speicherbegrenzten Eventstrom ersetzen. Option B als kleinsten
Live-Kandidaten in einer atomaren Transaktion prüfen. Nur wenn B alle vorab
menschlich beschlossenen Pi-, Reader-, Writer-, WAL-, Kill- und
Recovery-Budgets besteht, wird B gewählt; sonst folgt Option C mit
Shadow-Projektionen und atomarem Wechsel. Option D validiert Migrationen und
forensische Kopien, entscheidet aber keinen Live-Cutover.

**Definition of Done**

- kein Replay-/Integrity-Pfad materialisiert den vollständigen Ledger im RAM
- fixer Head, stabile Reihenfolge, begrenzte Batchgröße und payloadfreier
  Fortschritt sind explizit
- Event-Log, Präfix, Genesis, Epoche, Head, Seal und Anchor bleiben exakt gleich
- Golden Oracle und Digests aller Projektionen stimmen; zweiter Replay erzeugt
  weder Events noch Drift
- 0/1/Batchgrenzen sowie 10k, 100k und 1M Events sind gemessen
- Ziel-Pi-Receipts binden Peak RSS, Laufzeit, Datei-/WAL-Hochwasser,
  Reader-Kohärenz, Writer-Block/-Timeout und Recoveryzeit
- Projector-Fehler, konkurrierender Leser/Writer, Kill, Reopen und Retry sind
  fault-injected; Leser sehen nur einen vollständigen alten oder neuen Stand
- Projector-, Oracle- und Validierungsfehler prüfen vor Commit/Cutover und rollen
  vollständig auf alt zurück; nur ein Crash an der atomaren Grenze darf nach
  Reopen eindeutig alt oder den vollständig geprüften neuen Stand ergeben
- B ist nur nach vollständig bestandenem Gate grün; andernfalls ist C samt
  Generation-, Cutover-, Cleanup- und Recovery-Vertrag grün
- die gemessene Wahl B oder C und die vorab akzeptierten Budgets ergänzen
  ADR-0007 als versioniertes Receipt

### A0.4 · Externes Anchor-Vertrauen und erklärbare Reparatur

**Abhängigkeit:** Golden Ledger steht. Custody, kanonische Bytes, Algorithmus,
Trust-Manifest, Rotation und Widerruf werden vor Signaturcode entschieden. Diese
Vorbereitung darf organisatorisch parallel laufen, öffnet aber keinen zweiten
Produktmerge.

**Arbeit in dieser Reihenfolge:**

1. Hardware-Token-/Offline-Recovery-Custody und Anchor-v2-Vertrag festlegen;
   kein privater Signaturschlüssel liegt auf dem Pi.
2. Status-/Witness-Pfade nach dem v2-Vertrag härten; minimaler Git-Ref-Schutz
   allein ist keine Signatur- oder Dateiunveränderlichkeitsgarantie.
3. Getrennten Signierer, Verifier, Legacy-v1-Regel, Rotation, Widerruf und
   Recovery-Drill abnehmen; erst dann signierte Anchors ausstellen.
4. Production-Reseal nur als menschliche Notfallzeremonie mit externem Receipt,
   separatem Approver, Signatur und erhaltenen Altankern implementieren.
5. Zuletzt ein versioniertes Multi-Epoch-/Repair-Transition-Protokoll entwickeln;
   nicht reparierbare Geschichte bleibt sichtbar oder beginnt eine neue,
   lineage-gebundene Ledger-Generation.

**Definition of Done**

- Pi kann allein keine gültige externe Signatur erzeugen
- Anchor v1 bleibt historisch unsigned; die v2-Envelope trennt kanonisches
  Statement und Signaturenliste und bindet Epoche, Vorgänger, Algorithmus,
  `key_id`, Signatur und Lineage
- GitHub ist Transport, nicht alleinige Signaturautorität; eine signer-owned
  Witness-Fläche ist geprüft, unabhängige Mirrors dürfen sie nur ergänzen
- alte Anchors bleiben unverändert; neue Ausstellungen überschreiben keinen Pfad
- vor erfüllter v2-/Custody-/Approver-/Witness-Kette bleibt Production-Reseal
  vollständig gestoppt
- Repair-Transitions bewahren Schadensgrenze, menschliche Freigabe und externen
  Beleg, statt gebrochene Geschichte unsichtbar neu zu versiegeln

## H0 · Betrieb beweisen

**Ziel:** Der gehärtete Kern zeigt unter realer Last, dass Ereignisfluss, Wahrheit und
Betriebsgrenzen beobachtbar bleiben.

### H0.1 · 24/48/72-Stunden-Betriebs- und Ereignisprofil

**Abhängigkeit:** keine.

**Arbeit:** Ledger-, DB- und WAL-Veränderung pro Ereignistyp, kontrollierter Herkunftsfamilie und
aus dem Ereignistyp abgeleitetem Produzenten-Proxy messen; neue Evidenz,
notwendige Betriebsspur und vermeidbare Wiederholung unterscheiden; alte Flutfenster vom neuen
Normalbetrieb trennen; Budget und Alarmgrenzen ableiten. Das Ledger soll nicht um seiner selbst
willen wachsen.

**Definition of Done**

- drei vergleichbare Messpunkte mit gleicher Methodik
- Top-Verursacher nach Ereignistyp und Quelle ausgewiesen
- Eventrate, Dateiwachstum und flüchtige WAL-Dateiallokation getrennt
- jeder wesentliche Zuwachs als Erkenntnis, notwendige Betriebsspur oder vermeidbare Last bewertet
- begründetes Tagesbudget plus Warn- und Eingriffsschwelle dokumentiert
- Messung verändert weder Ledger noch Projektionen
- Leitmaß ist mehr belegbares Können pro gespeichertem Ereignis, nicht eine höhere Ereigniszahl

### H0.2 · Externen Anker etablieren

**Abhängigkeit:** gültiger lokaler Anker.

**Arbeit:** Anker außerhalb des Pi verwahren und die Prüfung vom externen Zeugen
bis zum lokalen Siegelkopf üben.

**Definition of Done**

- mindestens eine getrennte, zugriffsgeschützte Verwahrung
- Hash, `core_id`, Eventposition und Siegelkopf read-only verifiziert
- Abruf- und Prüfablauf dokumentiert und einmal erfolgreich geprobt
- Rotation erzeugt keine Ereignisse im Produkt-Ledger

### H0.3 · Umstrittenen `system.load`-Belief klären

**Abhängigkeit:** ausreichend Beobachtungsmaterial aus H0.1.

**Arbeit:** Stütz- und Gegenbelege, Zeitfenster, Sensordefinition und Schwellen
untersuchen; Semantik korrigieren oder bewusst Enthaltung erhalten.

**Definition of Done**

- der Widerspruch ist mit reproduzierbarer Abfrage erklärt
- Entscheidung beruht auf Evidenz, nicht auf gewünschtem Zustand
- Regressionstest deckt Stützung, Widerspruch und Unsicherheit ab
- Replay bleibt event- und projektionsstabil

### H0.4 · Gesprächsdateien und historische Logs bewusst behandeln

**Abhängigkeit:** keine; Löschung braucht eine ausdrückliche Betriebsentscheidung.

**Arbeit:** Umfang und Alter alter Telegram-Journal-/Legacy-Logs sowie der aktuellen begrenzten
Korrektur- und optionalen Wortlern-Dateien nur über Metadaten erfassen, Retention/Opt-in
entscheiden und anschließend gezielt löschen oder geschützt archivieren.

**Definition of Done**

- Bestandsaufnahme nennt Pfadklasse, Zeitraum, Größe und Rechte, nicht den Gesprächsinhalt
- Ronny entscheidet Retention, Löschung oder geschützte Archivierung ausdrücklich
- Ausführung ist protokolliert und anschließend read-only verifiziert
- neue Telegram-Journalzeilen enthalten weiterhin nur Betriebsmetadaten, insbesondere Länge
  und Fehlerklasse — keinen Text und keine Nutzer-ID

## H1 · Der alltagstaugliche Begleiter

**Abhängigkeit:** H0 ohne unkontrolliertes Wachstum oder ungeklärte
Betriebsgefährdung.

**Ziel:** Antworten fühlen sich persönlich und zusammenhängend an, ohne die
epistemischen Grenzen zu verwischen.

### H1.1 · Kontextgedächtnis

- relevanten statt nur ähnlichen Kontext auswählen
- Zeit, Quelle, Beziehung, Aktualität und Unsicherheit gemeinsam gewichten
- Privates nicht über Gesprächs- oder Nutzergrenzen tragen
- persönliche Inhalte aus dem append-only Ledger in einen isolierten, exportierbaren und
  tatsächlich löschbaren Memory-Vault überführen
- `vergiss`, Retention und Löschbestätigung als einen gemeinsamen Vertrag bauen

### H1.2 · Seele der Antworten

- Antwortbogen aus Absicht, belegtem Kontext, Unsicherheit und hilfreichem
  nächsten Schritt bilden
- Persönlichkeit als kontrollierte Darstellungsschicht halten
- Modellformulierungen niemals als neue Evidenz zurückschreiben

**Pilotstand:** Der erste geschlossene Vertikalschnitt ist gebaut. Definitionen und
Beziehungen tragen `AnswerDraft` mit Claims und vorhandener Provenienz; ein kleiner
`DialogueFrame` führt Absicht, strukturelle Ankerkontinuität und kontrollierte
Würfel-Belegung in den treuen
Renderer. Telegram erzeugt erst nach belegter Zustellung ein typisiertes
`ResponseOutcome`; reine 👍-/👎-Nachrichten und enge Intent-Korrekturen werden über die
Response-ID replaybar verknüpft.

Die hermetische [`alltagsprobe`](design/ANSWER_QUALITY.md) macht die nächste Reifestufe
wiederholbar: 17 synthetische Alltagssituationen prüfen derzeit 85 harte Verträge für
Treue, Ehrlichkeit, Provenienz, Transparenz, Dialog, Komposition, Alltagsform und
Datensparsamkeit. Alle 85 stehen grün. Die menschliche Abnahme steht mit 4/17 bewusst
offen; Fall- und Antwort-Hashes verhindern, dass eine alte Zustimmung nach einer Änderung
unbemerkt weitergilt.

Das ist bewusst noch nicht H1-fertig: Die übrigen Handler liefern weiter Legacy-Strings,
ein vollständiger Diskursplan fehlt, Feedback ändert keine Strategie automatisch und der
Telegram-Bezug zur letzten Response-ID überlebt keinen Prozessneustart. Der löschbare
Memory-Vault bleibt Teil von H1.1. Ebenso fehlt noch eine löschbare Edge-Outbox: Scheitert
die Outcome-Persistenz erst nach einer belegten Zustellung, bleibt diese Antwort im Pilot
zugestellt, aber ungemessen. Die synthetische Probe ersetzt außerdem weder Ronnys Urteil
über Ton und Nutzen noch die spätere Abnahme auf dem echten Pi.

**Definition of Done für H1**

- ein kuratiertes Set realer Alltagssituationen ist wiederholbar bewertet
- jede Tatsachenbehauptung ist belegt oder ausdrücklich als unsicher erkennbar
- Korrekturen wirken im nächsten passenden Dialog und sind replaybar
- sensible oder irrelevante Erinnerungen werden nachweislich nicht eingeblendet
- persönliche Episoden können exportiert und physisch gelöscht werden; eine Retraktion allein
  gilt nicht als „vergessen“
- Ronny bestätigt, dass Ton und Nützlichkeit im Alltag tragen

## H2 · Der generalisierende Fähigkeitsloop

**Abhängigkeit:** H1 liefert verständliche Rückfragen, Kontext und Feedback.

**Ziel:** GENUS schließt wiederkehrende Fähigkeitslücken durch geprüfte,
übertragbare Werkzeuge – nicht durch eine Sammlung von Sonderfällen.

```text
Lücke → Inquiry → Plan → Vorschlag → Sandbox → Test → Freigabe
      → Ausführung → Wirkungsmessung → behalten, verbessern oder zurückrollen
```

**Definition of Done**

- jeder Übergang besitzt ein definiertes Ereignis oder eine abgeleitete Projektion
- Vorschlag, menschliche Entscheidung und Ausführung sind technisch getrennt
- Sandbox hat feste Zeit-, Speicher-, Netzwerk- und Dateigrenzen
- mindestens drei strukturell verschiedene Aufgaben nutzen denselben Loop
- Erfolg misst Generalisierung und Laufzeitwirkung, nicht nur Testgrün
- Fehlschlag und Rollback sind absichtlich getestet und vollständig nachvollziehbar
- kein selbst erzeugter Code wird automatisch gemergt oder privilegiert ausgeführt

**Fundament umgesetzt (2026-07-15):** GENUS kann seine generierte Selbstkarte und den
Basiscommit lesen, Symptome als Quell- und Wirkungsraum diagnostizieren, risikogestufte
ChangeSpecs erzeugen, eine menschliche `draft_only`-Freigabe hashbinden und einen externen
Coder in einen detached Worktree mit Scope-, Secret-, Budget- und Testgates einsperren. Der
Loop endet technisch vor Commit, Merge, Push und Deploy. Für H2 fehlen weiterhin drei
strukturell verschiedene Live-Aufgaben, belastbare Wirkungsrückführung und absichtliche
Rollback-Nachweise.

## H3 · Erschaffen mit Beweis

**Abhängigkeit:** H2 ist über mehrere Aufgaben stabil.

**Ziel:** GENUS erzeugt Werkzeuge, Erklärungen und Code, deren Zweck, Grenzen und
Wirksamkeit er selbst prüfen kann.

**Definition of Done**

- jedes Artefakt hat Bedarf, Herkunft, Prüfkriterien und Besitzer
- deterministische Prüfer bewerten, was deterministisch prüfbar ist
- offene Qualitätsfragen werden dem Menschen sichtbar übergeben
- Live-Wirkung fließt als Evidenz zurück, nicht als selbsterteiltes Lob
- veraltete Fähigkeiten lassen sich deaktivieren und reproduzierbar ersetzen

## H4 · Markt- und Außenwelt-Membran

**Abhängigkeit:** H0-Ereignisbudget und H2-Governance sind belastbar.

**Ziel:** externe Signale beobachten und Entscheidungen simulieren, ohne Wahrheit,
Interesse und Handlung zu vermischen.

**Definition of Done**

- Quellenvertrag, Provenienz, Aktualität und Ausfallverhalten sind explizit
- Simulation und echte Handlung sind strukturell getrennt
- Bilanz berücksichtigt Kosten, Unsicherheit und Gegenfaktum
- kein echtes Geld wird automatisch bewegt
- Membranverlust beeinträchtigt weder Replay noch lokalen Kernbetrieb

## H5 · Föderation

**Abhängigkeit:** H3 ist stabil; Isolation, Einwilligung, Export und Löschung sind
vorher gelöst.

**Ziel:** ein getrennt verantwortbarer Kern pro Person oder Charakter – ohne
unbeabsichtigtes gemeinsames Gedächtnis.

**Definition of Done**

- Daten, Schlüssel, Prozesse und Sicherungen sind strukturell isoliert
- Einwilligung, Export, Widerruf und Löschung sind praktisch getestet
- Austausch erfolgt nur über explizite, belegte Protokolle
- Ausfall oder Kompromittierung eines Kerns greift nicht auf andere über
- besondere Schutzregeln für Kinder sind technisch erzwungen, nicht nur versprochen

## Das Gate vor jedem Merge

Jeder Roadmap-Schritt beantwortet vor seiner Freigabe:

- Welches Material rechtfertigt ihn?
- Welches Ereignis hält Input oder Transition fest?
- Ist der abgeleitete Zustand vollständig rebuildbar?
- Bleibt Replay ohne neue Events und ohne Drift?
- Wird Confidence berechnet statt als Wahrheit gespeichert?
- Sind Root, User, Modell, Netzwerk und Sandbox sauber begrenzt?
- Welche Metrik zeigt Nutzen, Wachstum und möglichen Schaden?
- Wie wird gestoppt oder zurückgerollt?
- Welche Dokumente und Tests machen die Änderung verständlich?

Wenn eine Antwort fehlt, ist der Schritt nicht klein genug oder noch nicht reif.

---

**Aktive Baulinie:** In A0.2 folgt auf das angenommene Golden Ledger mit
unabhängigem Oracle das separat gegatete historische SQLite-Artefakt. Danach
folgen read-only Schemaerkennung und das A0.3-Experiment zwischen Option B und
dem verbindlichen Fallback C. H1.2 bleibt Produktziel, ist aber kein paralleler
mergefähiger Pfad. Rein read-only Messungen und die isolierte nichtproduktive
Lernlinie dürfen nach Regel 1 weiterlaufen.
