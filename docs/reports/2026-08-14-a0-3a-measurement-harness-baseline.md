# A0.3a — Measurement Harness und Pi-Baseline

## 1. Status und Entscheidungspunkt

**Status:** uncommitteter Mess- und Human-Review-Kandidat vom 2026-08-14.

**Geprüfter Ausgangspunkt:**
`3ccf5b5329a8297d4f548d36b27267af74e6326c` auf dem isolierten Branch
`codex/a0-3a-measurement-harness`.

Der große Pi-Lauf verwendete die vor dem finalen Read-only-Codeaudit gebundene
Harnessrevision (`harness.py` SHA-256
`c52ae92fc3ac0eca7f563d21f5105d3485d9a13cb7fa5885803fafd51af0ec15`,
`__main__.py`
`c59c258f7b563add79b13b4b3c0fa1128153ecdd05e78dcd3ab61d4b89ff6956`).
Danach wurden ausschließlich drei Receipt-/Telemetrieaussagen
gehärtet: `mid_batch` heißt korrekt `mid_replay`, der nach einem Writer-Timeout
neu geöffnete Writer heißt nicht mehr „resumed“, und ein Fehler des
Post-Commit-Hooks wird nicht mehr als Rollback gemeldet. SQL, Batchloop,
Transaktionsgrenze, Projektoren, Prüfer und Sampler blieben unverändert. Die
finalen Codehashes sind
`aa0a2828b0bbb91590840a6eb2ec1605e70f1eb1293cc040c6c1b3347f7716c3`
für `harness.py` und
`0f33d454f1a7d07b6e78ecc75cdab3fe79c500d986f34bc1505b7b0401d43d37`
für `__main__.py`; die korrigierten kleinen Fault-/Concurrency-Matrizen wurden
lokal erneut ausgeführt.

Dieser Bericht nimmt **keine** Budgets an, wählt **keine** Replay-Topologie und
aktiviert keinen Produktpfad. Er beendet ausschließlich A0.3a: experimenteller
Prüfstand, lokale Messmatrix, read-only/copy-only Pi-Baseline und ein Vorschlag
für das nächste menschliche Gate.

Der technische Befund ist eindeutig zweigeteilt:

- Der begrenzte Option-B-Prototyp hält seine Python-Speichernutzung auch bei
  1.166.876 realen Events klein und bewahrt Ledger, Seals und alle zwölf
  Projektionen exakt.
- Dieselbe Ein-Transaktions-Topologie hält auf dem Pi den Writer-Gate rund
  106,8 Sekunden. Ein konkurrierender Writer erreicht mit dem heutigen
  5-Sekunden-Timeout reproduzierbar einen Lock-Timeout.

Damit ist Option B als **bounded Wartungs-/Offline-Primitiv** realistisch. Für
den kontinuierlichen Livebetrieb empfiehlt dieser Bericht **Option C mit
Shadow-Projektionen und atomarem Cutover**. Das ist eine Empfehlung aus den
Messdaten, noch keine angenommene Architekturentscheidung.

## 2. Scope- und Sicherheitsgrenze

Geändert wurden ausschließlich neue experimentelle bzw. test-only Pfade:

- `experiments/__init__.py`
- `experiments/a0_3a/__init__.py`
- `experiments/a0_3a/harness.py`
- `experiments/a0_3a/__main__.py`
- `tests/test_a0_3a_measurement_harness.py`
- `docs/README.md` (nur der Link auf diesen datierten Report)
- dieser Bericht

Nicht geändert wurden Runtime-Replay, Integrity, DB-Initialisierung, Sealing,
Anchor, Schema, Deploypfade, A0.2-Fixtures, NOW und ROADMAP. Es gab keinen
Commit, Push oder Pull Request.

Die zwei nutzereigenen Änderungen im Haupt-Worktree wurden weder gelesen noch
gestaged, gestasht oder übernommen:

- `docs/README.md`
- `docs/reports/2026-08-13-vollaudit.md`

Auf dem Pi wurde die Produktdatenbank nur über eine bestehende
`mode=ro`-/`query_only`-Connection beobachtet und mit der SQLite Backup API in
einen privaten Laufordner kopiert. Replay, Integrity, Seal, Anchor-Verifikation
und Fault-Tests liefen ausschließlich gegen Kopien. Kein Dienst wurde pausiert
oder neu gestartet; es gab keinen Checkpoint, kein `VACUUM`, kein `ANALYZE` und
keinen Produkt-Cutover.

Mess- und Phasendateien enthalten keine Payloads und keine absoluten
Datenbankpfade. Produktkopien bleiben außerhalb von Git und werden nicht
hochgeladen.

## 3. Architektur-Istbefund

Der read-only Codeaudit bestätigt die Ausgangslage aus ADR-0007:

| Pfad | Heutige vollständige Materialisierung / Grenze |
|---|---|
| `genus/event_router.py` | `replay()` lädt alle Eventzeilen per `fetchall()` vor dem Löschen und erneuten Anwenden der Projektionen. |
| `genus/integrity.py` | Eventvertrag, Event-Snapshot und alle zwölf Projektions-Snapshots werden vollständig materialisiert; anschließend entsteht zusätzlich eine vollständige In-Memory-DB mit erneutem Replay. |
| `genus/sealing.py` | Der Verifier lädt alle Zeilen, erzeugt Legacy-/Sealed-Listen und für den Genesis-Digest zusätzlich eine vollständige Records-Liste samt Gesamtstring. |
| `genus/anchor.py` | Anchor-Erzeugung und -Verifikation erreichen den unbounded Seal-Pfad. |
| `genus/cli.py` | Nur die CLI besitzt heute eine klare Option-B-artige Ownership mit `BEGIN IMMEDIATE`, Replay, Vergleich und Commit/Rollback. Ihr Zustandsvergleich umfasst aber nur acht der zwölf Projektionen. |

Der vollständige Replay-Zielsatz ist:

1. `response_feedback_log`
2. `response_outcome_log`
3. `rule_projection`
4. `governance_log`
5. `operation_log`
6. `inquiry_log`
7. `proposal_log`
8. `experience_log`
9. `state_projection`
10. `belief_projection`
11. `relation_projection`
12. `value_projection`

Der bestehende CLI-Snapshot lässt `relation_projection`, `value_projection`,
`response_outcome_log` und `response_feedback_log` aus. Seine Meldung
`State matches current projection` ist deshalb nur eine Altbaseline und kein
A0.3-Orakel. Der Harness vergleicht alle zwölf Ziele.

Die heutige Integrity-Prüfung führt Schema-, Eventvertrags- und Seal-Prüfungen
vor ihrer stabilen Snapshot-Transaktion aus. Diese Prüfungen können bei
gleichzeitigen Appends unterschiedliche Heads sehen. Ein späterer bounded
Integrity-Produktpfad muss alle Prüfungen unter denselben festen Head bzw.
dieselbe Snapshot-Grenze stellen.

## 4. Experimenteller Vertrag

Der neue Prüfstand liegt bewusst außerhalb von `genus/` und aktiviert keine
Produktfunktion. Sein Option-B-Kandidat besitzt folgenden Ablauf:

```text
bestehende disposable Current-DB öffnen
→ BEGIN IMMEDIATE
→ fixed head und Eventzahl erfassen
→ Ledgerbindung + 12 Projektionsdigests vor dem Lauf
→ alle 12 Projektionen einmal leeren
→ Events per Keyset-Batches bis fixed_head anwenden
→ Schema-, Eventvertrag- und Seal-Prüfung
→ Ledgerbindung + 12 Projektionsdigests nach dem Lauf
→ unabhängiges bzw. vorher gebundenes Oracle vergleichen
→ COMMIT

bei jeder Ausnahme oder Abweichung
→ ROLLBACK
```

Die Batchabfrage ist fest:

```sql
WHERE id > :last_id AND id <= :fixed_head
ORDER BY id
LIMIT :batch_size
```

Ein Batch ist nur ein begrenzter Lesepuffer, nie eine Commit-Grenze. Der
Transaktionsowner bleibt der aufrufende Option-B-Runner. Belegt werden:

- streng steigende IDs;
- genau eine Verarbeitung jedes Events bis zum festen Head;
- keine Verarbeitung einer späteren ID;
- unveränderte Eventzahl und Ledgerbindung;
- Streaming-Seal-/Genesis-Prüfung ohne vollständige Eventliste;
- kanonische Streaming-Digests für alle zwölf Projektionen;
- alter oder vollständig neuer Zustand nach Fehler/Kill, nie ein akzeptierter
  Zwischenstand.

Der begrenzte Eventvertragsprüfer hält Lifecycle-Zustand in SQLite-TEMP-Tabellen
statt in wachsenden Python-Sets. `json.loads()` verarbeitet weiterhin jeweils
eine vollständige Payload. Deshalb werden zusätzlich maximale Einzel- und
Batch-Payloadbytes gemessen; `batch_size` allein ist keine harte Byte-Grenze.

## 5. Lokale Matrix

Lokale Laufzeit: Windows 11, CPython 3.12.13, SQLite 3.53.1. Default-Batch ist
1.024; synthetische Zielpayloadgröße ist 256 Bytes. Der deterministische Mix
enthält `assertion_recorded`, `observation_created`, `evidence_recorded` und
`relation_asserted`. Golden A0.2 deckt unabhängig davon alle zwölf
Projektorsemantiken ab.

| Events | Dauer (s) | Peak RSS (B) | DB High-Water (B) | WAL High-Water (B) | Oracle/Seal/Ledger |
|---:|---:|---:|---:|---:|---|
| 0 | 0,011560 | 27.561.984 | 159.744 | 0 | korrekt |
| 1 | 0,012611 | 27.549.696 | 159.744 | 0 | korrekt |
| 1.023 | 0,088661 | 30.789.632 | 888.832 | 0 | korrekt |
| 1.024 | 0,084314 | 31.154.176 | 888.832 | 32 | korrekt |
| 1.025 | 0,090448 | 30.941.184 | 888.832 | 0 | korrekt |
| 10.000 | 0,832293 | 33.550.336 | 7.196.672 | 32 | korrekt |
| 100.000 | 8,371364 | 33.832.960 | 70.955.008 | 16.966.192 | korrekt |
| 1.000.000 | 116,020116 | 35.225.600 | 710.885.376 | 170.448.552 | korrekt |

Alle Läufe meldeten `strictly_ordered=true`, `exactly_once=true`,
`processed_above_fixed_head=0`, unveränderte Ledgerbindung, passendes
Projektionsorakel und passende Seal-Kette.

Der Null-Event-Fall bleibt ausdrücklich unversiegelt und besitzt keinen Anchor.
Der Harness erzeugt dafür keine künstliche Epoche.

## 6. Golden Ledger und historische SQLite-Fixture

### Golden Ledger A0.2

Der 42-Event-Kandidat wurde mit Batchgröße 7 vollständig neu aufgebaut:

- Dauer: 0,0204485 s
- Peak RSS: 24.928.256 B
- alle zwölf statischen Projektionsorakel: korrekt
- Projektionsdigest-Set:
  `a0b60c847573beae7ac085d32d34e9aba7ca2b984c28372e9f862af41aa0656d`
- Seal: korrekt
- historischer Anchor: korrekt
- Fixturebytes: unverändert

### Historische SQLite-Fixture

Die historische Quelldatei wurde ausschließlich als Kopie read-only erkannt:

- Klassifikation: `historical-v1.1`
- sieben Events exportiert
- Quelldatei, Metadaten und Sidecar-Abwesenheit unverändert
- Export in eine getrennte, disposable Current-Schema-DB
- bounded Replay, Eventvertrag und Seal auf dieser Current-Kopie korrekt

Dieser Ablauf heißt im Receipt
`historical_export_to_disposable_current`. Er ist ausdrücklich **keine
Migration** und öffnet die historische DB nie über das heutige `init_schema()`.

## 7. Fault-, Kill- und Concurrent-Verhalten

### Transaktionale Fehler

Ein Projector-Fehler mitten im Batch und ein absichtlich falscher
Projektionsdigest führten jeweils zum exakten alten Projektionszustand. Der
anschließende Retry committete den vollständig geprüften neuen Zustand.

### Prozess-Kill

Ein echter Subprozess wurde mit `Popen.kill()` beendet. Die 1.000-Event-Matrix
ergab lokal:

| Killphase | Reopen | Recovery (s) | Retry |
|---|---|---:|---|
| `mid_replay` | alter Zustand | 0,028449 | committed |
| `pre_commit` | alter Zustand | 0,024208 | committed |
| `commit_returned` | neuer Zustand | 0,035778 | nicht nötig |

Auf dem Pi lagen die entsprechenden kleinen Recoveryzeiten zwischen 0,0123 und
0,0128 Sekunden. In allen Fällen war Reopen eindeutig alt oder neu, nie
intermediär.

Die Phasenbarrieren liegen vor und nach `COMMIT`; sie beweisen keinen echten
Stromausfall während des Commit-Systemaufrufs. Eine solche Behauptung wird nicht
erhoben.

Ein zusätzlicher Regressionstest lässt den Telemetrie-Hook erst **nach** dem
erfolgreichen Commit timeouten. Der Worker meldet dann korrekt
`outcome=committed` und `post_commit_progress=failed`, nicht fälschlich
`rolled_back`; die vollständig neue Projektion ist nach Reopen sichtbar.

### Reader und Writer

Ein unabhängiger Reader sah vor Commit nur den alten und danach nur den
vollständigen neuen Stand. Der während des Replayversuchs gestartete Writer
timeoutete und schrieb nichts. Nach Commit öffnete der Test eine **neue**
Writer-Connection; diese schrieb exakt Event `fixed_head + 1`. Der separate
Keyset-Test beweist, dass eine bereits vorhandene ID oberhalb des festen Heads
nicht verarbeitet wird.

Lokaler Test mit 0,25-s-Timeout:

- Writer-Blockzeit: 0,333667 s
- Timeout: ja
- neue Writer-Connection nach Commit erfolgreich: ja
- Fixed-Head-Präfix unverändert: ja

Pi-Test mit dem realen heutigen 5-s-Timeout:

- Writer-Blockzeit: 5,003508 s
- Timeout: ja
- neue Writer-Connection nach Commit erfolgreich: ja
- Fixed-Head-Präfix nach dem späteren Event unverändert: ja

Der Timeout ist kein RAM-Problem, sondern eine direkte Folge der langen
`BEGIN IMMEDIATE`-Grenze.

## 8. Pi-Live-Baseline

Der Pi war clean auf demselben Commit `3ccf5b5...`; Learner und Telegram-Bot
blieben durchgehend aktiv, der Pause-Marker fehlte. Die Produkt-DB wurde 900
Sekunden lang alle zwei Sekunden über eine persistente read-only
Autocommit-Connection beobachtet.

| Merkmal | Wert |
|---|---:|
| Samples | 451 |
| Events / Head Start | 1.166.814 |
| Events / Head Ende | 1.166.876 |
| sichtbare neue Events | 62 |
| Gesamt-RAM | 8.454.619.136 B |
| verfügbarer RAM, Minimum | 7.660.044.288 B |
| Learner RSS | 3.440.640 B |
| Telegram-Bot RSS | 31.866.880 B |
| Produkt-DB | 610.222.080 B, konstant |
| Produkt-WAL | 4.433.152 B, konstant |
| Produkt-SHM | 32.768 B |
| Produkt-Journal | nicht vorhanden |

Die sichtbaren 62 Events sind normale Produktaktivität, keine Wirkung des
Collectors. Es wurden weder Payloadspalten noch Prozess-Argumente oder
Environmentwerte gesammelt.

Die konsistente Masterkopie entstand per SQLite Backup API aus
`mode=ro`, `query_only=ON`, Autocommit:

- Dauer: 3,808793 s
- Größe: 610.283.520 B
- Modus: `0600`
- `quick_check`: `ok`
- Schema: `current`
- Events / fester Head: 1.166.876
- SHA-256:
  `1c88786c6d1474911672d37d19149023f635c131b98bafc64e07c106cdfc7ba7`

Die Masterkopie behielt den WAL-Journalmodus. Innerhalb des privaten
Laufordners entstanden deshalb ein leeres WAL (0 B) und ein SHM von 32.768 B;
es entstand kein Journal. Das ist kein Sidecar der Produktdatei.

Der private, nicht hochgeladene Messordner bleibt für menschliche Prüfung
erhalten:

`/home/ronny/.genus/a03-baseline.20260814T.Uv46fi`

## 9. Pi-Vergleich: heutige Implementierung und bounded Option B

Alle folgenden Befehle liefen auf getrennten Backup-API-Kopien.

| Messung | Events | Dauer (s) | Peak RSS (B) | WAL High-Water (B) | Ergebnis |
|---|---:|---:|---:|---:|---|
| heutige unbounded Integrity | 1.166.876 | 71,851944 | 3.128.098.816 | 0 | Integrity OK |
| heutiger Seal-Verifier | 1.166.876 | 7,7473 | nicht separat | 0 | Seal OK |
| heutiges unbounded Replay | 1.166.876 | 46,149562 | 978.894.848 | 151.636.632 | rc 0; CLI-State matches |
| bounded Option-B-Prototyp | 1.166.876 | 106,775489 | 38.387.712 | 151.636.632 | committed; 12/12 gegen gebundenen Vorzustand |

Der bounded Prototyp benötigt damit rund 2,31-mal so lange wie das heutige
Replay, aber nur rund 3,9 % dessen Peak RSS. Gegenüber der heutigen
Integrity-Prüfung liegt sein Peak RSS bei rund 1,2 %. Die WAL-Spitze ist beim
heutigen und beim bounded Replay in dieser Messung gleich.

Für den bounded Pi-Lauf wurden zusätzlich gemessen:

- DB High-Water: 610.283.520 B
- SHM High-Water: 294.912 B
- maximale Einzelpayload: 205.498 B
- maximale Payloadbytes eines 1.024er Batches: 324.175 B
- Ledger-SHA vor/nach:
  `9f6c0fa13d8876c163c2f71aa8e429b07b260a3f03140dbc0fc9afdd8edb85f6`
- Projektionsdigest-Set vor/nach:
  `9a2434dde1c89a7f57536a36ac9b0e61861bd12e3c065c241f286b85441cbf61`
- Schema-, Eventvertrags- und Seal-Issues: keine
- alle zwölf Projektionsdigests: identisch

Nach dem unbounded Replay waren ebenfalls Ledgerbindung und alle zwölf
Projektionsdigests exakt identisch. Die anschließende Integrity- und
Seal-Prüfung der Replay-Kopie war grün.

Auf der Produktkopie ist der gebundene Vorzustand ein vollständiger
12-Projektions-Idempotenznachweis, aber kein externes Bedeutungsoracle. Das
unabhängige semantische Oracle liefert ausschließlich Golden A0.2.

Der jüngste bestehende Anchor für Head 1.162.076 wurde gegen die Masterkopie
erfolgreich verifiziert. Seine Datei blieb unverändert; es wurde kein Anchor
erzeugt.

Die erste Altbaseline versuchte `/usr/bin/time`, das auf dem Pi nicht vorhanden
ist, und hinterließ einen Wrapper-Rückgabewert 127. Die anschließende
`/proc`-Messung sowie die fachliche Integrity-Ausgabe melden unabhängig Exit 0
und `INTEGRITY OK`. Dieser Wrapperbefund wird nicht als Produktergebnis
interpretiert.

## 10. Budgetvorschlag — noch nicht angenommen

Die folgenden Zahlen sind ein **Human-Review-Vorschlag**, keine gültigen Gates.
Sie gelten für einen festen Head bis etwa 1,2 Millionen Events auf der
gemessenen Pi-Hardware und müssen bei Hardware-, Payload- oder deutlichem
Ledgerwachstum neu kalibriert werden.

| Budget | Vorgeschlagene Grenze | Begründung / heutige Evidenz |
|---|---:|---|
| Peak RSS des Replay-Workers | max. 268.435.456 B (256 MiB) | etwa 7-mal der gemessene bounded Peak und rund 3,5 % des minimal verfügbaren RAM |
| Replay-Laufzeit | max. 180 s | etwa 1,69-mal die bounded Pi-Messung; hält einen Wartungslauf zeitlich vorhersehbar |
| WAL High-Water | max. 268.435.456 B (256 MiB) | etwa 1,77-mal der Pi-Messung und kleiner als die Hälfte der aktuellen Hauptdatei |
| Writer-Blockzeit | max. 2,0 s und **kein Timeout** | entspricht der heutigen Learner-Taktgröße und bleibt klar unter `busy_timeout=5 s` |
| Recovery nach Kill | max. 10 s; ausschließlich `old` oder `new` | kleine Killmatrix liegt unter 0,013 s; produktgroßer Kill bleibt noch nachzuweisen |

Zusätzliche vorgeschlagene Vorbedingungen:

- freier Speicher mindestens viermal Hauptdatei plus normales WAL;
- feste Batchgröße 1.024 und explizite Messung der Batch-Payloadbytes;
- Abbruch bei unbekanntem Schema, Eventvertrags-, Seal-, Ledger- oder
  Projektionsdigestfehler;
- kein Commit ohne alle zwölf Projektionsdigests;
- keine Payloads in Fortschritt oder Receipts.

Option B würde nach diesen **nur vorgeschlagenen** Zahlen Peak-RSS-, Zeit- und
WAL-Grenze einhalten, die Writer-Grenze aber deutlich verfehlen. Formell wird
kein Budget als bestanden oder nicht bestanden erklärt, bevor Ronny es
menschlich annimmt. Unabhängig davon ist bereits faktisch bewiesen, dass der
heutige 5-s-Writer während eines rund 107-s-Laufs timeoutet.

## 11. Topologieempfehlung

### Livebetrieb: Option C

Für kontinuierliche Learner-, Bot-, Watchdog- und Cron-Writer ist eine lange
`BEGIN IMMEDIATE`-Transaktion kein tragfähiger Normalpfad. Die Messung spricht
deshalb für versionierte Shadow-Projektionen, vollständige Prüfung außerhalb
des aktiven Projektionssatzes und einen kurzen atomaren Cutover.

Ein späterer Option-C-Vertrag muss insbesondere definieren:

- versionierte Shadow-Namen und vollständiges 12-Tabellen-Inventar;
- fixed-head und Behandlung späterer Events;
- Aufbau ohne Blockierung normaler Writer;
- Delta-Catch-up oder kurzer Writer-Fence vor Cutover;
- alle zwölf Digests, Golden Oracle, Ledger und Seal vor Umschaltung;
- atomarer alter-oder-neuer Cutover und sichere Aufbewahrung/Rücknahme des
  alten Satzes;
- bounded Integrity unter derselben Head-Grenze.

### Wartung, Migration und Forensik: Option B/D

Der bounded Ein-Transaktions-Runner bleibt wertvoll:

- auf Kopien und in Migrationstests;
- in expliziten Wartungsfenstern mit bewusst gestoppten Writern;
- als Referenz für Streaming-Digests, Seal-Prüfung und fixed-head;
- als Vergleichsorakel für eine spätere Option-C-Implementierung.

Er darf nicht still als Livepfad aktiviert werden.

## 12. Offene Risiken und fehlende A0.3-Gates

1. Physisches `ENOSPC` wurde nicht reproduziert; es existiert noch kein
   SQLite-VFS-/Quota-Test für echte Speichererschöpfung.
2. Der Killtest begrenzt die Commit-Grenze, ersetzt aber keinen echten
   Stromausfall während des SQLite-Systemaufrufs.
3. Ein produktgroßer Kill-/Recoverylauf wurde noch nicht gemessen; die
   Recoverywerte stammen aus 1.000-Event-Fällen.
4. Ein explizit ungültiges Event als eigener End-to-End-Fault sowie ein zweiter
   Replay derselben großen DB gehören noch zum vollständigen ADR-0007-Gate.
5. Ein absichtlich langer Reader mit WAL-Pinning wurde nicht separat vermessen.
6. CPU- und I/O-Zähler wurden nicht portabel erhoben; RSS und
   DB/WAL/SHM-Highwater stammen aus externem Sampling.
7. Die 20-ms-Pi-Abtastung liefert High-Water-Untergrenzen; kürzere Spitzen
   können fehlen.
8. `batch_size` ist keine harte Speichergrenze bei unbegrenzten Payloads. Die
   größte reale Einzelpayload war 205.498 B; ein späterer Vertrag braucht eine
   Bytegrenze oder eine explizite Max-Payload-Vorbedingung.
9. Der bounded Eventvertragsprüfer nutzt TEMP-Tabellen. Das begrenzt
   Python-Sets, benötigt aber ein eigenes Scratch-/Temp-Speicherbudget.
10. Die synthetische Skalenmatrix deckt vier häufige Eventtypen ab; Golden A0.2
    deckt alle zwölf Projektoren, und die Produktkopie die reale Mischung. Das
    ist kein vollständiger synthetischer Lastmix aller Eventtypen.
11. Die historische Rehydration ist kein Migrationsnachweis.
12. Der Harness ist experimenteller Code und noch keine produktive bounded
    Integrity-/Replay-Implementierung.
13. Die Pi-Fault-Receipts entstanden vor der auditgetriebenen Umbenennung des
    ersten vollständigen Batchabschlusses von `mid_batch` zu `mid_replay`. Der
    Messpunkt und die Datenbankwirkung sind unverändert; die neue Bezeichnung
    ist die semantisch korrekte Aussage.
14. `write_receipt()` serialisiert ein vom Aufrufer geliefertes Mapping und ist
    selbst kein allgemeiner Sanitizer. Die vorhandenen Harness-Aufrufer und
    Tests erzwingen payload-/pfadfreie Schemata; neue Aufrufer müssen denselben
    Vertrag ausdrücklich prüfen.

## 13. Verifikation

Ausgeführte lokale Gates:

- fokussiert: `14 passed`
- Ruff für `genus`, `experiments` und `tests`: grün
- Full Suite: `1558 passed, 9 skipped, 1 failed`

Der einzelne Full-Suite-Fehler ist der bereits auf unveränderter Baseline
reproduzierbare Windows-CRLF-Befund in
`docs/generated/GENUS_ALLTAGSPROBE.md`. Er liegt außerhalb von A0.3a und wurde
weder behoben noch verdeckt. Daher wird nicht behauptet, die Full Suite sei
vollständig grün.

Die Produktpfade blieben byteinhaltlich unverändert. Der Pi endete clean auf
`3ccf5b5...`; Learner und Telegram-Bot behielten ihre ursprünglichen PIDs und
blieben aktiv, der Pause-Marker fehlte und es existierte kein Produkt-Journal.

## 14. Menschliches Gate und Stopp

Zu entscheiden sind jetzt getrennt:

- [ ] vorgeschlagene Budgets annehmen
- [ ] vorgeschlagene Budgets ändern und gezielt nachmessen
- [ ] Option C als Live-Topologie und Option B/D als Wartungs-/Prüfpfad
      festlegen
- [ ] vor der Topologieentscheidung weitere A0.3-Pflichtexperimente verlangen

Bis zu dieser Entscheidung gilt:

- keine Option-B-Abnahme;
- keine Option-C-Implementierung;
- kein produktiver Replay-/Integrity-Umbau;
- kein Commit, Push oder Pull Request;
- keine Änderung an A0.2, A0.1a oder A0.1b.

**A0.3a stoppt hier planmäßig für menschliche Review.**
