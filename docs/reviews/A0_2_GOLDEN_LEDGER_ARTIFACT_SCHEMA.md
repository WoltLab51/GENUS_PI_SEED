# A0.2 Golden Ledger Artifact Schema Contract

> **Status:** accepted supporting contract
>
> **Owner:** Ronny
>
> **Datum:** 2026-08-10
>
> **Zweck:** Exakte Dateinamen, Schema-IDs, Feldmengen, Dateibytes und
> Digestbindungen für den A0.2-Golden-Ledger-Kandidaten festlegen.

## 1. Geltung und Autoritätsgrenze

Dieser Supporting Contract ist eine mechanische Ergänzung zu
[ADR-0006](../decisions/ADR-0006-GOLDEN-LEDGER-ORACLE.md),
[ADR-0009](../decisions/ADR-0009-HUMAN-OWNED-CRITICAL-LANE.md),
[ADR-0010](../decisions/ADR-0010-HUMAN-SUPERVISED-MODEL-ASSISTANCE-A0.md),
[ADR-0011](../decisions/ADR-0011-GOLDEN-LEDGER-CANONICALIZATION-AND-BELIEF-COVERAGE.md)
und dem
[A0.2 Golden Ledger Entry Contract](A0_2_GOLDEN_LEDGER_ENTRY_CONTRACT.md).
Er ist kein neuer ADR und erweitert keine Runtime-, Schema- oder
Implementierungsautorität.

Dieser Vertrag ist ausschließlich maßgeblich für:

- Dateinamen;
- Schema-IDs;
- exakte Feldmengen;
- JSON-Dateiserialisierung;
- Count-Feldnamen;
- Digestnamen;
- Digest-Byteformen;
- Digestbindungen;
- die Form des Anchor-v1-Testartefakts;
- die Platzierung des Kandidatenstatus.

Für die in diesem Dokument ausdrücklich spezifizierten mechanischen Formen
ersetzt dieser Vertrag widersprechende frühere mechanische Formulierungen aus
Entry Contract 1.0 und 1.1. Nicht neu spezifizierte Byteformen bleiben beim
Entry Contract. Das gilt insbesondere für die kanonischen `events.jsonl`-Bytes,
`fixture_sha256` und die vollständige Byteform von `event_stream_sha256`.
Der Entry Contract bleibt außerdem maßgeblich für:

- Rollen;
- Corpus und Datenschutz;
- Oracle-Unabhängigkeit;
- Human Review;
- Read- und Write-Scope;
- Stop Conditions;
- den Kandidatenlebenszyklus.

Die ADRs bleiben übergeordnet. Bei einem Widerspruch außerhalb der ausdrücklich
delegierten mechanischen Themen gewinnt nicht dieser Supporting Contract.

## 2. Exakte Artefaktnamen

Der spätere Kandidat besteht unter
`tests/fixtures/golden_ledger_v1/` exakt aus:

```text
tests/fixtures/golden_ledger_v1/events.jsonl
tests/fixtures/golden_ledger_v1/manifest.json
tests/fixtures/golden_ledger_v1/oracle.json
tests/fixtures/golden_ledger_v1/import_receipt.json
tests/fixtures/golden_ledger_v1/anchor_v1.json
tests/fixtures/golden_ledger_v1/README.md
tests/fixtures/golden_ledger_v1/ORACLE_REVIEW.md
```

Aliasnamen und alternativ zulässige Namen gibt es nicht.

## 3. Kandidatenstatus

Der maschinenlesbare Kandidatenstatus gilt ausschließlich für
`manifest.json`, `oracle.json` und `import_receipt.json`. Dort lautet er exakt:

```json
"status": "candidate_pending_human_review"
```

`events.jsonl` und `anchor_v1.json` enthalten kein `status`-Feld. Insbesondere
bleibt `anchor_v1.json` bei der unveränderten exakten Feldmenge des bestehenden
`genus-ledger-anchor-v1`-Vertrags.

In `README.md` und `ORACLE_REVIEW.md` steht sichtbar:

```text
CANDIDATE — PENDING HUMAN REVIEW
```

Als Artefaktstatus unzulässig sind insbesondere `approved`, `canonical`,
`complete` und `human_reviewed`. Testgrün ändert den Kandidatenstatus nicht.

## 4. Gemeinsamer JSON-Dateivertrag

Für `manifest.json`, `oracle.json` und `import_receipt.json` gilt exakt:

```python
json.dumps(
    value,
    ensure_ascii=True,
    sort_keys=True,
    indent=2,
) + "\n"
```

Die daraus gebildeten Dateibytes sind:

- UTF-8;
- ohne BOM;
- mit LF-Zeilenenden;
- mit genau einer finalen LF.

Ein Dateidigest wird als SHA-256 über exakt diese Dateibytes gebildet und als
64 Kleinbuchstaben-Hexzeichen ausgegeben. `anchor_v1.json` besitzt den eigenen
v1-Dateivertrag aus Abschnitt 10. Die äußere Dateiserialisierung eines
JSON-Artefakts ist von einer semantischen Digestserialisierung innerhalb des
Artefakts zu unterscheiden.

## 5. `manifest.json`

### 5.1 Schema und Top-Level-Felder

Schema-ID und Formatversion lauten exakt:

```text
schema = "genus-golden-ledger-manifest-v1"
format_version = 1
```

Die Top-Level-Feldmenge besteht exakt aus:

```text
schema
format_version
status
fixture_schema_version
canonicalization
files
counts
epoch
head
digests
```

Weitere Top-Level-Felder sind nicht zulässig. Die festen Werte sind:

```text
schema = "genus-golden-ledger-manifest-v1"
format_version = 1
status = "candidate_pending_human_review"
fixture_schema_version = "genus-golden-ledger-fixture-v1"
```

### 5.2 `canonicalization`

`canonicalization` besitzt exakt:

```text
event_stream_digest_schema
projection_digest_schema
projection_digest_set_schema
bundle_digest_schema
```

mit den exakten Werten:

```text
event_stream_digest_schema = "genus-golden-ledger-event-stream-digest-v1"
projection_digest_schema = "genus-golden-ledger-projection-digest-v1"
projection_digest_set_schema = "genus-golden-ledger-projection-digest-set-v1"
bundle_digest_schema = "genus-golden-ledger-bundle-digest-v1"
```

### 5.3 `files`

`files` besitzt exakt:

```text
events
oracle
import_receipt
anchor_v1
readme
human_review
```

mit den exakten Werten:

```text
events = "events.jsonl"
oracle = "oracle.json"
import_receipt = "import_receipt.json"
anchor_v1 = "anchor_v1.json"
readme = "README.md"
human_review = "ORACLE_REVIEW.md"
```

### 5.4 `counts`

`counts` besitzt exakt:

```text
event_count
legacy_prefix_event_count
sealed_tail_event_count
projection_target_count
```

Die Felder bedeuten:

- `event_count`: Gesamtzahl aller Fixture-Events einschließlich des
  Epochen-Events;
- `legacy_prefix_event_count`: Zahl der Events mit `id < epoch.event_id`;
- `sealed_tail_event_count`: Zahl der Events mit `id > epoch.event_id`;
- `projection_target_count`: exakt `12`.

Das Epochen-Event zählt weder zum Legacy-Präfix noch zum versiegelten Tail. Es
gilt hart:

```text
event_count = legacy_prefix_event_count + 1 + sealed_tail_event_count
```

### 5.5 `epoch`, `head` und `digests`

`epoch` besitzt exakt:

```text
event_id
prefix_count
prefix_max_id
genesis_digest
algo
```

`head` besitzt exakt:

```text
event_id
event_type
created_at
seal
```

`digests` besitzt exakt:

```text
fixture_sha256
event_stream_sha256
oracle_sha256
anchor_v1_sha256
projection_digest_set_sha256
```

`fixture_sha256` bindet die exakten `events.jsonl`-Dateibytes nach dem Entry
Contract. `event_stream_sha256` bindet den dort definierten semantischen
Eventstrom. Die übrigen Digests folgen den nachstehenden Abschnitten.

Das Manifest enthält weder `manifest_sha256` noch `bundle_sha256` und bindet
damit keinen Digest seiner eigenen Dateibytes.

## 6. `oracle.json`

### 6.1 Schema und Top-Level-Felder

Schema-ID und Formatversion lauten exakt:

```text
schema = "genus-golden-ledger-replay-oracle-v1"
format_version = 1
```

Die Top-Level-Feldmenge besteht exakt aus:

```text
schema
format_version
status
fixture_schema_version
source_bindings
canonicalization
expected
projection_digest_set_sha256
```

Weitere Top-Level-Felder sind nicht zulässig. Die festen Werte sind:

```text
schema = "genus-golden-ledger-replay-oracle-v1"
format_version = 1
status = "candidate_pending_human_review"
fixture_schema_version = "genus-golden-ledger-fixture-v1"
```

`oracle.json` enthält keinen Digest seiner eigenen Dateibytes.

### 6.2 Direkte Source-Bindings

`source_bindings` besitzt exakt:

```text
events_file
fixture_sha256
event_stream_digest_schema
event_stream_sha256
```

mit den festen Werten:

```text
events_file = "events.jsonl"
event_stream_digest_schema = "genus-golden-ledger-event-stream-digest-v1"
```

`fixture_sha256` und `event_stream_sha256` sind jeweils 64
Kleinbuchstaben-Hexzeichen. Damit bindet das Oracle die kanonische Eventdatei
und den semantischen Eventstrom direkt und getrennt.

### 6.3 `canonicalization`

`canonicalization` besitzt exakt:

```text
projection_rows_schema
projection_digest_schema
projection_digest_set_schema
read_model_schema
```

mit den exakten Werten:

```text
projection_rows_schema = "genus-golden-ledger-projection-rows-v1"
projection_digest_schema = "genus-golden-ledger-projection-digest-v1"
projection_digest_set_schema = "genus-golden-ledger-projection-digest-set-v1"
read_model_schema = "genus-golden-ledger-belief-epistemic-read-model-v1"
```

### 6.4 `expected`

`expected` besitzt exakt:

```text
event_count
legacy_prefix
epoch
head
integrity
projections
read_models
```

`legacy_prefix` besitzt exakt:

```text
event_count
max_event_id
genesis_digest
```

`epoch` besitzt exakt:

```text
event_id
algo
```

`head` besitzt exakt:

```text
event_id
event_type
created_at
seal
```

`integrity` besitzt exakt:

```text
ok
issues
```

Für den gültigen Kandidaten gilt:

```text
ok = true
issues = []
```

### 6.5 Zwölf Projektionen

`expected.projections` besitzt exakt alle zwölf Replayziele:

```text
response_feedback_log
response_outcome_log
rule_projection
governance_log
operation_log
inquiry_log
proposal_log
experience_log
state_projection
belief_projection
relation_projection
value_projection
```

Jede dieser Projektionen besitzt exakt:

```text
columns
sort_by
rows
sha256
```

- `columns` ist die geordnete Liste der normalisierten Vergleichsspalten.
- `sort_by` ist die geordnete Liste der Sortierspalten.
- `rows` enthält die statischen normalisierten Erwartungszeilen.
- `sha256` ist deren Projektiondigest nach Abschnitt 7.

Auch eine erwartbar leere Projektion wird vollständig geführt. Ihre
`rows`-Liste ist `[]`; ihr `sha256` bindet das kanonische leere JSON-Array.

### 6.6 Deterministische Read-Modelle

`expected.read_models` besitzt exakt:

```text
belief_epistemic_state_v1
```

`belief_epistemic_state_v1` besitzt exakt:

```text
as_of
halflife_seconds
cases
```

mit den exakten Werten:

```text
as_of = "2026-01-01T00:00:00.000Z"
halflife_seconds = 3600.0
```

Jeder Eintrag in `cases` besitzt exakt:

```text
belief_id
supporting_event_ids
contradicting_event_ids
expected_confidence
expected_epistemic_state
```

Die fachliche Semantik der Fälle, einschließlich Rundung und Trennung vom
persistierten Belief-Lifecycle, bleibt im Entry Contract festgelegt.

## 7. Projektiondigest

Die Schema-ID lautet exakt:

```text
genus-golden-ledger-projection-digest-v1
```

Für jede Projektion wird die nach dem Entry Contract normalisierte und stabil
sortierte `rows`-Liste exakt so serialisiert. Die Eingabe ist bereits rekursiv
Unicode-NFC-normalisiert, enthält ausschließlich endliche Zahlen und hat `-0.0`
zu `0.0` normalisiert; eine Verletzung dieser Vorbedingungen ist ein Fehler.
Die Schema-ID `genus-golden-ledger-projection-rows-v1` bezeichnet diese
normalisierte Row-Darstellung nach dem weiterhin geltenden
`genus-projection-normalization-v1`-Vertrag:

```python
json.dumps(
    rows,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
)
```

Das Ergebnis wird als UTF-8 ohne BOM und ohne abschließende Newline codiert.
`sha256` ist SHA-256 über exakt diese Bytes und besteht aus 64
Kleinbuchstaben-Hexzeichen.

Diese semantische Digestform mit `ensure_ascii=False` ist unabhängig von der
äußeren `ensure_ascii=True`-Dateiserialisierung von `oracle.json` nach
Abschnitt 4.

## 8. Projection-Digest-Set

Schema-ID und Feldname lauten exakt:

```text
schema = "genus-golden-ledger-projection-digest-set-v1"
field = "projection_digest_set_sha256"
```

Das Eingabeobjekt bildet exakt jeden der zwölf Replayzielnamen auf seinen
kleingeschriebenen hexadezimalen Projektiondigest ab:

```json
{
  "<projection_table_name>": "<projection_sha256>"
}
```

Es wird exakt so serialisiert:

```python
json.dumps(
    digest_map,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
)
```

Das Ergebnis wird als UTF-8 ohne BOM und ohne abschließende Newline codiert.
`projection_digest_set_sha256` ist SHA-256 über exakt diese Bytes und besteht
aus 64 Kleinbuchstaben-Hexzeichen.

Der identische Wert steht an exakt diesen drei Stellen:

- `oracle.json` im Top-Level-Feld `projection_digest_set_sha256`;
- `manifest.json` unter `digests.projection_digest_set_sha256`;
- `import_receipt.json` unter
  `digests.projection_digest_set_sha256`.

## 9. Oracle-Dateidigest

Der Feldname lautet exakt `oracle_sha256`. Sein Wert ist SHA-256 über die
exakten `oracle.json`-Dateibytes nach Abschnitt 4 und besteht aus 64
Kleinbuchstaben-Hexzeichen.

Der identische Wert steht an exakt diesen zwei Stellen:

- `manifest.json` unter `digests.oracle_sha256`;
- `import_receipt.json` unter `digests.oracle_sha256`.

`oracle.json` enthält keinen eigenen Dateidigest. Damit entsteht keine
Selbstreferenz.

## 10. `anchor_v1.json`

### 10.1 Unveränderte v1-Form

Der Dateiname ist exakt `anchor_v1.json`. Das Artefakt folgt unverändert dem
bestehenden v1-Vertrag mit der Schema-ID:

```text
genus-ledger-anchor-v1
```

Die Top-Level-Feldmenge besteht exakt aus:

```text
algo
core_id
created_at
derivation
epoch_event_id
event_count
head
head_created_at
head_event_id
head_event_type
schema
signature
```

Weitere Felder sind nicht zulässig. Insbesondere enthält der Anchor kein
`status`-Feld. Die festen Werte sind:

```text
algo = "sha256-chain-v1"
core_id = "golden-ledger-v1"
derivation = "ledger_anchor:v1"
schema = "genus-ledger-anchor-v1"
signature = null
```

Alle übrigen Werte werden statisch aus der synthetischen Fixture festgelegt.

### 10.2 Historische Head-Grenze

`head_event_id` bezeichnet einen statischen historischen Head der Fixture.
Spätere Fixture-Events dürfen nach diesem Head existieren. Der Anchor bezeugt
damit einen historischen Präfix und nicht zwingend den späteren Endstand der
Fixture.

`event_count` ist die Eventzahl zum Zeitpunkt des Anchors, also die Zahl der
Fixture-Events mit `id <= head_event_id`. Bei lückenlosen IDs ab `1` entspricht
`event_count` dem `head_event_id`. Das Feld bezeichnet nicht zwingend die
spätere Gesamtzahl der Fixture.

`created_at` ist ein fester synthetischer, menschlich reviewbarer Zeitstempel.
Er stammt nicht aus der Wall Clock und liegt nicht vor `head_created_at`.

### 10.3 Anchor-Dateibytes und Digest

Die exakten Dateibytes entstehen aus:

```python
anchor.canonical_json(artifact) + "\n"
```

Semantisch entspricht dies exakt:

```python
json.dumps(
    artifact,
    ensure_ascii=True,
    sort_keys=True,
    separators=(",", ":"),
) + "\n"
```

Das Ergebnis wird als UTF-8 ohne BOM, mit LF-Zeilenende und genau einer finalen
LF codiert.

`anchor_v1_sha256` ist SHA-256 über exakt diese Dateibytes und besteht aus 64
Kleinbuchstaben-Hexzeichen. Der identische Wert steht an exakt diesen zwei
Stellen:

- `manifest.json` unter `digests.anchor_v1_sha256`;
- `import_receipt.json` unter `digests.anchor_v1_sha256`.

## 11. `import_receipt.json`

### 11.1 Schema und Top-Level-Felder

Schema-ID und Formatversion lauten exakt:

```text
schema = "genus-golden-ledger-import-receipt-v1"
format_version = 1
```

Die Top-Level-Feldmenge besteht exakt aus:

```text
schema
format_version
status
fixture_schema_version
source_files
counts
digests
bundle_digest_schema
bundle_sha256
```

Weitere Top-Level-Felder sind nicht zulässig. Die festen Werte sind:

```text
schema = "genus-golden-ledger-import-receipt-v1"
format_version = 1
status = "candidate_pending_human_review"
fixture_schema_version = "genus-golden-ledger-fixture-v1"
bundle_digest_schema = "genus-golden-ledger-bundle-digest-v1"
```

### 11.2 `source_files`

`source_files` besitzt exakt:

```text
events
manifest
oracle
anchor_v1
```

mit den exakten Werten:

```text
events = "events.jsonl"
manifest = "manifest.json"
oracle = "oracle.json"
anchor_v1 = "anchor_v1.json"
```

### 11.3 `counts`

`counts` besitzt exakt:

```text
expected_event_count
imported_event_count
```

`expected_event_count` ist die Eventzahl laut Manifest.
`imported_event_count` ist die Zahl der Events, die der Testloader tatsächlich
in die temporäre `event_log`-Tabelle eingefügt hat. Beide Werte müssen identisch
sein.

### 11.4 `digests`

`digests` besitzt exakt:

```text
fixture_sha256
event_stream_sha256
manifest_sha256
oracle_sha256
anchor_v1_sha256
projection_digest_set_sha256
```

`manifest_sha256` ist SHA-256 über die exakten `manifest.json`-Dateibytes nach
Abschnitt 4 und besteht aus 64 Kleinbuchstaben-Hexzeichen. Die übrigen Werte
entsprechen den gleichnamigen gebundenen Digests ihrer jeweiligen Domäne.

### 11.5 Rolle des statischen Receipts

`import_receipt.json` ist das statische erwartete Receipt-Artefakt. Der
Testloader erzeugt während des Tests ein Actual Receipt ausschließlich im
Arbeitsspeicher und vergleicht es vollständig mit `import_receipt.json`.

Die statische Datei wird vom Test weder erzeugt noch verändert. Eine temporäre
SQLite-Datenbank ist weiterhin nur ein nicht normatives Derivat der statischen
Fixture.

## 12. Bundle-Digest

Schema-ID und Feldname lauten exakt:

```text
schema = "genus-golden-ledger-bundle-digest-v1"
field = "bundle_sha256"
```

Das Eingabeobjekt besitzt exakt diese Feldmenge:

```json
{
  "anchor_v1_sha256": "<value>",
  "event_stream_sha256": "<value>",
  "fixture_schema_version": "genus-golden-ledger-fixture-v1",
  "fixture_sha256": "<value>",
  "manifest_sha256": "<value>",
  "oracle_sha256": "<value>",
  "projection_digest_set_sha256": "<value>"
}
```

Weitere Felder sind nicht zulässig. Das Objekt wird exakt so serialisiert:

```python
json.dumps(
    bundle_object,
    ensure_ascii=True,
    sort_keys=True,
    separators=(",", ":"),
)
```

Das Ergebnis wird als UTF-8 ohne BOM und ohne abschließende Newline codiert.
`bundle_sha256` ist SHA-256 über exakt diese Bytes und besteht aus 64
Kleinbuchstaben-Hexzeichen.

`bundle_sha256` steht ausschließlich im Top-Level-Feld `bundle_sha256` von
`import_receipt.json`. Das Eingabeobjekt enthält weder `bundle_sha256` noch
einen Digest der Receipt-Datei; die Bindung besitzt deshalb keine
Selbstreferenz. Das Feld ist ein Digest der exakt benannten Komponenten, kein
Digest der Receipt-Datei und kein Digest des gesamten Artefaktverzeichnisses.

Das Bundle-Eingabeobjekt wird aus
`import_receipt.json.fixture_schema_version` und den gleichnamigen Werten unter
`import_receipt.json.digests` gebildet. Bevor der Bundle-Digest verglichen wird,
müssen diese Receipt-Werte unabhängig aus den statischen Quelldateibytes, dem
Manifest, dem Oracle, dem Anchor und dem aus der temporären Datenbank
exportierten Eventstrom nachgerechnet und gegen ihre gebundenen Sollwerte
geprüft werden. Ein Actual Receipt darf keine Werte aus dem statischen Receipt
als berechnete Ist-Werte übernehmen.

## 13. Artefaktübergreifende Gleichheiten

Alle mehrfach gespeicherten Werte sind identische Bindungen, keine voneinander
unabhängigen Behauptungen. Der spätere Test prüft mindestens exakt diese
Gleichheiten:

- `manifest.digests.fixture_sha256`,
  `oracle.source_bindings.fixture_sha256` und
  `import_receipt.digests.fixture_sha256` entsprechen SHA-256 über die exakten
  `events.jsonl`-Dateibytes;
- `manifest.digests.event_stream_sha256`,
  `oracle.source_bindings.event_stream_sha256` und
  `import_receipt.digests.event_stream_sha256` entsprechen dem nach Entry
  Contract gebildeten Digest des Source- und des importierten Eventstroms;
- `manifest.digests.oracle_sha256` und
  `import_receipt.digests.oracle_sha256` entsprechen SHA-256 über die exakten
  `oracle.json`-Dateibytes;
- `manifest.digests.anchor_v1_sha256` und
  `import_receipt.digests.anchor_v1_sha256` entsprechen SHA-256 über die
  exakten `anchor_v1.json`-Dateibytes;
- `oracle.projection_digest_set_sha256`,
  `manifest.digests.projection_digest_set_sha256` und
  `import_receipt.digests.projection_digest_set_sha256` entsprechen dem neu aus
  den zwölf Projektionsdigests berechneten Digest-Set;
- `import_receipt.digests.manifest_sha256` entspricht SHA-256 über die exakten
  `manifest.json`-Dateibytes;
- `manifest.counts.event_count`, `oracle.expected.event_count`,
  `import_receipt.counts.expected_event_count` und
  `import_receipt.counts.imported_event_count` sind identisch;
- `manifest.counts.legacy_prefix_event_count`,
  `manifest.epoch.prefix_count` und
  `oracle.expected.legacy_prefix.event_count` sind identisch;
- `manifest.epoch.prefix_max_id` und
  `oracle.expected.legacy_prefix.max_event_id` sind identisch; bei lückenlosen
  IDs ab `1` gilt außerdem
  `manifest.epoch.prefix_max_id = manifest.epoch.event_id - 1`;
- `manifest.epoch.genesis_digest` und
  `oracle.expected.legacy_prefix.genesis_digest` sind identisch;
- `manifest.epoch.event_id` und `manifest.epoch.algo` sind mit den
  gleichnamigen Werten unter `oracle.expected.epoch` identisch;
- die vier Werte unter `manifest.head` und `oracle.expected.head` sind
  feldgleich und bezeichnen den aktuellen Fixture-Head.

Der Anchor-Head darf als ausdrücklich historische Präfixgrenze vom aktuellen
Manifest-/Oracle-Head abweichen. Seine `event_count`-Semantik folgt Abschnitt
10.2.

## 14. `README.md`

Der Dateiname ist exakt `README.md`. Die Hauptüberschrift lautet exakt:

```markdown
# Golden Ledger v1
```

Direkt darunter steht exakt:

```markdown
> Status: CANDIDATE — PENDING HUMAN REVIEW
```

Danach folgen exakt diese Abschnitte in dieser Reihenfolge:

```markdown
## Purpose
## Artifact Inventory
## Corpus Design
## Legacy Prefix and Seal Epoch
## Oracle Independence
## Canonicalization and Digests
## Import Receipt
## Anchor v1 Boundary
## Human Review
## Change Procedure
## Non-Goals
```

Die erklärende Prosa darf sachlich formuliert werden. Sie darf keine
menschliche Abnahme behaupten.

## 15. `ORACLE_REVIEW.md`

Der Dateiname ist exakt `ORACLE_REVIEW.md`. Die Hauptüberschrift lautet exakt:

```markdown
# A0.2 Golden Ledger Oracle Review
```

Direkt darunter stehen exakt diese vier Zeilen:

```markdown
> Status: CANDIDATE — PENDING HUMAN REVIEW
> Reviewer: Ronny
> Review date:
> Baseline commit:
```

Danach folgen exakt diese Abschnitte in dieser Reihenfolge:

```markdown
## 1. Corpus and Privacy
## 2. Event Contract
## 3. Legacy Prefix and Genesis Digest
## 4. Seal Epoch and Tail
## 5. Projection Oracle
## 6. Belief Lifecycle and Read-Time Epistemics
## 7. Canonicalization and Digests
## 8. Anchor v1 and Negative Cases
## 9. Final Decision
```

Alle Reviewpunkte bleiben als ungeprüfte Checkboxen `- [ ]` offen. Im letzten
Abschnitt stehen exakt:

```markdown
- [ ] Accept candidate
- [ ] Reject candidate
- [ ] Request changes
```

Keine Checkbox darf durch Codex, einen Testlauf oder einen Generator markiert
werden.

## 16. Erlaubte Kandidatenfreiheit

Der spätere nicht autoritative Modellassistent darf innerhalb der festgelegten
Verträge als Kandidaten vorschlagen:

- eine synthetische Eventauswahl;
- synthetische Payloadwerte;
- feste IDs;
- feste Zeitstempel;
- einen historischen Anchor-Head;
- statische erwartete Projektionszeilen;
- Projektionsspalten und Sortierschlüssel, feldgenau abgeleitet aus dem
  genehmigten Read-only-Scope.

Diese Werte müssen statisch, synthetisch, datenschutzfrei, menschlich
nachvollziehbar und vollständig reviewbar sein. Sie bleiben
`CANDIDATE — PENDING HUMAN REVIEW`. Nicht jede synthetische Einzelzahl muss vor
dem Kandidatenbau separat durch Ronny festgelegt werden.

Diese Freiheit erlaubt weder neue Eventtypen noch eine Ableitung statischer
Erwartungen aus dem Runtimeoutput als Autorität. Corpus-, Unabhängigkeits-,
Scope-, Review- und Stop-Verträge bleiben unverändert beim Entry Contract.

## 17. Änderung und Nicht-Ziele

Eine Änderung an Dateinamen, Schema-IDs, Feldmengen, Serialisierungsbytes,
Digestdomänen oder Bindungen ist eine bewusste Vertragsänderung unter Ronnys
Patchhoheit. Ein Runtime-Test darf diese Werte nicht automatisch aktualisieren
oder freigeben.

Dieser Supporting Contract erzeugt noch keine Fixture, kein Oracle, kein
Manifest, kein Import Receipt, keinen Anchor, keinen Loader, keinen Testcode und
keinen Digest. Er ändert weder Runtime, Schema, Ledger, Replay, Seal, Anchor,
Schlüssel, CI, GitHub-Einstellungen noch Produktdaten. Der persistente
Write-Scope des Entry Contracts bleibt unverändert.
