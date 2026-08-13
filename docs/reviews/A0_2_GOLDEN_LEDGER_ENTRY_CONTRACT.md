# A0.2 Golden Ledger Entry Contract

> **Status:** accepted entry contract · **Datum:** 2026-08-10
>
> **Owner:** Ronny
>
> **Contract version:** 1.4
>
> **Amended by:**
> [ADR-0011 — Golden Ledger Canonicalization, Belief Coverage and Projector Read Scope](../decisions/ADR-0011-GOLDEN-LEDGER-CANONICALIZATION-AND-BELIEF-COVERAGE.md)
> and the
> [A0.2 Golden Ledger Artifact Schema Contract 1.2](A0_2_GOLDEN_LEDGER_ARTIFACT_SCHEMA.md)
>
> **Gilt vor:** dem ersten Golden-Ledger-, Oracle-, Anchor-Fixture- oder
> Testartefakt
>
> **Entscheidungsgrundlage:**
> [ADR-0006](../decisions/ADR-0006-GOLDEN-LEDGER-ORACLE.md),
> [ADR-0009](../decisions/ADR-0009-HUMAN-OWNED-CRITICAL-LANE.md) und
> [ADR-0010](../decisions/ADR-0010-HUMAN-SUPERVISED-MODEL-ASSISTANCE-A0.md),
> präzisiert durch [ADR-0011](../decisions/ADR-0011-GOLDEN-LEDGER-CANONICALIZATION-AND-BELIEF-COVERAGE.md)
> und den
> [Artifact Schema Contract](A0_2_GOLDEN_LEDGER_ARTIFACT_SCHEMA.md)

## Amendment history

- **Version 1.0:** initial accepted entry contract
- **Version 1.1:** fixture schema version, semantic event-stream digest,
  belief coverage and projector read scope made explicit
- **Version 1.2:** artifact filenames, JSON schemas, status placement, source
  bindings, count fields, oracle file digest, anchor bytes and bundle binding
  made explicit
- **Version 1.3:** import-receipt event-stream schema binding, separate
  `expected_projections` and `expected_read_models` sections, and expected
  Anchor-v1 outcomes aligned with ADR-0006 and ADR-0011
- **Version 1.4:** explicit bundle-bound oracle provenance added to satisfy
  ADR-0006 without duplicating provenance across manifest and import receipt

## Zweck und Gate

Dieser Vertrag legt Rollen, Corpusgrenzen, Kanonisierung, Oracle-Digests,
menschliche Abnahme und Stop Conditions fest, bevor das erste A0.2-Artefakt
entsteht. Er autorisiert noch keine Fixture, kein Oracle und keinen Testcode.

Der
[Artifact Schema Contract](A0_2_GOLDEN_LEDGER_ARTIFACT_SCHEMA.md) ist
ausschließlich für die dort ausdrücklich spezifizierten Dateinamen,
Schema-IDs, exakten Feldmengen, JSON-Dateiserialisierungen, Count-Feldnamen,
Digestnamen, Digest-Byteformen und Digestbindungen, die
Anchor-v1-Testartefaktform sowie die Platzierung des Kandidatenstatus
maßgeblich. In diesen eng delegierten mechanischen Themen ersetzt er
widersprechende Formulierungen aus den früheren Versionen 1.0 bis 1.2.

Dieser Entry Contract bleibt maßgeblich für Rollen, Corpus, Datenschutz,
Oracle-Unabhängigkeit, Human Review, Read- und Write-Scope, Stop Conditions und
den Kandidatenlebenszyklus. Seine nicht ersetzten JSONL-, Fixture-,
Eventstrom- und fachlichen Normalisierungsregeln gelten fort. Die ADRs bleiben
übergeordnet; außerhalb der ausdrücklich delegierten mechanischen Themen hat
der Supporting Contract keinen Vorrang.

ADR-0006 und ADR-0011 bleiben auch für die in Version 1.4 harmonisierte Form
übergeordnet. Artifact Schema Contract 1.2 macht ihre mechanische Ausprägung
explizit: `expected.projections` und `expected.read_models` sind nicht mehr
gültig; ausschließlich die getrennten Oracle-Top-Level-Bereiche
`expected_projections` und `expected_read_models` sind zulässig.
`expected_anchor_v1` trägt die statischen Anchor-Verifikationsergebnisse, und
`event_stream_digest_schema` ist im Import Receipt verpflichtend.

`source_bindings` bezeichnet ausschließlich die technische Bindung des Oracle
an Fixture-Datei, Fixture-Digest und semantischen Eventstrom und ist keine
vollständige Provenienz. `oracle.json.provenance` ist der einzige autoritative
Provenienzwohnort und bindet Repository, Baseline-Commit, geltende
Vertragsdokumente, Ableitung und Rollen. `baseline_commit` ist der saubere HEAD
zu Beginn des späteren Kandidatenbaus.

Die Provenienz ist als Teil der Oracle-Dateibytes durch `oracle_sha256`, über
die Manifest-Dateibytes durch `manifest_sha256` und durch den beide Werte
enthaltenden `bundle_sha256` in den Kandidatenverbund eingebunden. Manifest und
Import Receipt duplizieren das Provenienzobjekt nicht; ein separater
`provenance_sha256` wird nicht eingeführt.

Ein später von Codex erzeugtes Artefakt bleibt bis zu Ronnys getrenntem Review:

> **CANDIDATE — PENDING HUMAN REVIEW**

Testgrün ändert diesen Status nicht.

## A. Rollen

| Rolle | Träger | Verbindliche Trennung |
|---|---|---|
| Corpus Owner | Ronny | bestimmt und verantwortet den synthetischen Corpus |
| Datenschutzprüfer | Ronny | prüft den fertigen Corpus in einer eigenen Prüftätigkeit |
| Oracle Reviewer | Ronny | prüft das Oracle in einem ausdrücklich getrennten zweiten Review-Durchlauf |
| Canonicalization and Digest Contract Owner | Ronny | besitzt diesen Vertrag und bewusste spätere Änderungen |
| Human Implementer and Committer of Record | Ronny | besitzt Patchhoheit, Annahme und jeden späteren Commit |
| Non-authoritative Model Assistant | Codex | darf nur innerhalb ADR-0010 Kandidaten erzeugen und erklären |

In diesem privaten Ein-Personen-Projekt darf Ronny mehrere menschliche Rollen
wahrnehmen. Corpus-Erstellung, Datenschutzprüfung und Oracle-Abnahme bleiben
trotzdem getrennt dokumentierte Handlungen. Codex ist in keiner Rolle
menschlicher Reviewer oder Freigeber und darf keine Review-Checkbox markieren.
Automatische Tests ersetzen keine menschliche Oracle-Abnahme. Eine spätere
zweite menschliche Prüfung ist willkommen, aber keine Voraussetzung für Golden
Ledger v1.

## B. Corpus Contract

Der Golden-Ledger-v1-Corpus ist:

- vollständig synthetisch;
- frei von Produktdaten;
- frei von Namen, Familieninformationen, Telegram-Inhalten, Hostnamen, lokalen
  Pfaden, Secrets und echten Systemwerten;
- auf bereits registrierte Eventtypen und bestehende Eventverträge begrenzt;
- mit einem nichtleeren unversiegelten Legacy-Präfix aufgebaut;
- mit genau einem vorhandenen v1-Epochen-Event aufgebaut;
- nach der Epoche mit einem lückenlos versiegelten Tail aufgebaut;
- mit festen IDs und festen Zeitstempeln definiert;
- mit expliziten terminalen Lebenszyklen ausgestattet;
- fachlich aus projizierten und bewusst rohen Events zusammengesetzt;
- mit persistiertem Belief-Lifecycle `active` und `superseded` sowie getrennten,
  statischen read-time Fällen für `supported` und `contested` ausgestattet;
- mit Relation, Inquiry, Experience, Proposal und Governance ausgestattet.

Die kanonische Ereignismenge wird nicht beim Testlauf durch `ledger.append()`,
`sealing.open_epoch()`, `reseal()` oder andere aktuelle Producer neu erzeugt
oder korrigiert. Eine temporäre SQLite-Datenbank ist nur ein deterministisches
Testderivat der statischen Fixture.

## C. Canonical JSONL Contract

Für `events.jsonl` gilt:

- Kodierung ist UTF-8 ohne BOM;
- Zeilenenden sind LF;
- jede Zeile enthält genau ein JSON-Objekt;
- alle Strings sind vor Serialisierung Unicode-NFC-normalisiert;
- Objektschlüssel sind auf jeder Verschachtelungsebene lexikografisch sortiert;
- jede Zeile besteht exakt aus den UTF-8-Bytes von
  `json.dumps(object, ensure_ascii=False, allow_nan=False, sort_keys=True,
  separators=(",", ":"))` und einem abschließenden LF;
- Integer verwenden die minimale JSON-Dezimaldarstellung ohne führende Nullen;
- nichtintegrale Zahlen müssen endlich sein; `NaN` und positive oder negative
  Unendlichkeit sind verboten, `-0.0` wird vor Serialisierung zu `0.0`
  normalisiert;
- Fixture-Zeitstempel verwenden exakt
  `YYYY-MM-DDTHH:MM:SS.ffffff+00:00`; sie werden nicht in lokale Zeit oder `Z`
  umgeschrieben;
- bedeutungslose Formatierungsvarianz und Pretty-Printing sind ausgeschlossen;
- die Datei endet verpflichtend mit genau einer finalen Newline;
- `payload` wird in der Fixture als lesbares JSON-Objekt geführt;
- der Loader serialisiert den `event_log.payload` mit `sort_keys=true` und
  `separators=(",", ":")`, `ensure_ascii=false` und `allow_nan=false` nach
  derselben NFC-Regel;
- Fixture-SHA-256 wird über die exakten Bytes von `events.jsonl` gebildet.

Die Datei ist die kanonische Eventdarstellung. Ein Loader darf ihre IDs,
Zeitstempel, Payloads, `prev_seal`- oder `seal`-Werte weder ergänzen noch
reparieren. Jede Byteänderung ist eine bewusste Corpusänderung und verlangt ein
neues menschliches Review der betroffenen Verträge und Erwartungen.

## C.1 Manifest- und Derivatbindung

Die Fixture-Schemaversion lautet exakt:

```text
fixture_schema_version = "genus-golden-ledger-fixture-v1"
```

Sie erscheint mindestens in `manifest.json`, `oracle.json` und
`import_receipt.json`. Sie bezeichnet die Form einer Fixture-Zeile mit exakt
`id`, `event_type`, `payload`, `created_at`, `prev_seal` und `seal`, nicht die
SQLite-Schema- oder Oracle-Schemaversion. `events.jsonl` wiederholt sie nicht in
jeder Zeile.

Zwei getrennte SHA-256-Domänen sind verbindlich:

- `fixture_sha256` bindet die exakten, nach Abschnitt C kanonischen
  `events.jsonl`-Dateibytes einschließlich genau einer finalen LF.
- `event_stream_sha256` bindet die semantisch zu importierenden
  `event_log`-Zeilen. Seine Schema-ID lautet exakt
  `genus-golden-ledger-event-stream-digest-v1` und steht im Feld
  `event_stream_digest_schema`.

Für `event_stream_sha256` gilt diese exakte Byteform:

1. Events nach ganzzahliger `id` aufsteigend sortieren.
2. Das `payload` jeder Fixture-Zeile als JSON-Objekt lesen.
3. `payload_text` mit
   `json.dumps(payload, ensure_ascii=True, sort_keys=True,
   separators=(",", ":"))` bilden.
4. Je Event genau ein Objekt aus `created_at`, `event_type`, `id`,
   `payload_text`, `prev_seal` und `seal` bilden. `id` ist Integer;
   `prev_seal` und `seal` sind String oder JSON `null`.
5. Die ID-geordnete Liste dieser Objekte mit
   `json.dumps(records, ensure_ascii=True, sort_keys=True,
   separators=(",", ":"))` als JSON-Array serialisieren.
6. Als UTF-8 ohne BOM und ohne abschließende Newline codieren.
7. SHA-256 über exakt diese Bytes bilden und als 64 Kleinbuchstaben-Hexzeichen
   ausgeben.

`fixture_sha256` und `event_stream_sha256` werden nicht gleichgesetzt. Der
erste bindet die reviewte Datei einschließlich ihrer äußeren Darstellung, der
zweite den semantischen Eventstrom. Derselbe Eventstromalgorithmus wird auf die
Fixture und auf den read-only Export der importierten Temp-DB angewandt; beide
Eventstromdigests müssen gleich sein.

Die exakten Dateinamen, Schema-IDs, Feldmengen, Count-Feldnamen und
artefaktübergreifenden Bindungen von Manifest, Oracle, statischem Import
Receipt und Anchor stehen im
[Artifact Schema Contract](A0_2_GOLDEN_LEDGER_ARTIFACT_SCHEMA.md).
Insbesondere bindet `oracle.json` die Fixture-Datei und den semantischen
Eventstrom direkt und getrennt unter `source_bindings`. Der dort festgelegte
`projection_digest_set_sha256` ist der verpflichtende Gesamtdigest aller zwölf
Projektionsdigests. `import_receipt.json.event_stream_digest_schema` ist
verpflichtend, besitzt denselben festen Schemawert wie die entsprechenden
Manifest- und Oracle-Bindungen und bezeichnet getrennt vom konkreten
`import_receipt.json.digests.event_stream_sha256` dessen Algorithmus- und
Byteformvertrag.

`import_receipt.json` ist das statische erwartete Receipt. Der deterministische
Import in eine temporäre Current-Schema-SQLite-Datenbank erzeugt kein
persistentes Receipt-Artefakt, sondern berechnet ein Actual Receipt
ausschließlich im Arbeitsspeicher. Dieses wird vollständig und unabhängig aus
Quelldateibytes, importierten Zeilen und read-only Exporten gebildet und gegen
die statische Datei verglichen. Der nach diesem Abschnitt berechnete
`event_stream_sha256` des Imports muss dem Source-Eventstrom entsprechen. Die
Identität des Current-Schema-Temp-Derivats bleibt davon getrennt; die temporäre
Datenbank ist nie normative Quelle.

Die separate statische historische SQLite-Altfixture aus ADR-0006 gehört nicht
zum ersten A0.2-Kandidatenauftrag. Sie benötigt vor einem späteren
Migration-Runner ein eigenes menschliches Gate, das mindestens Dateidigest,
historischen Schema-Fingerprint und read-only bewiesene Eventstrom-Gleichheit
mit der zugeordneten JSONL-Historie bindet. Der Wildcard-Schreibscope dieses
Vertrags autorisiert ihre vorzeitige Erzeugung nicht.

## D. Projection Oracle Contract

Die menschlich eingefrorene v1-Projektionsinventarliste besteht exakt aus:

- `belief_projection`
- `relation_projection`
- `value_projection`
- `proposal_log`
- `inquiry_log`
- `experience_log`
- `state_projection`
- `governance_log`
- `operation_log`
- `rule_projection`
- `response_outcome_log`
- `response_feedback_log`

Das statische Oracle führt jede dieser zwölf Projektionen ausdrücklich, auch
wenn deren erwartete Zeilenliste leer ist. Ein Test vergleicht die
Oracle-Namensmenge auf exakte Gleichheit mit der read-only ermittelten
Runtime-Replayzielmenge: fehlende und unerwartete Namen schlagen fehl. Die
Runtime-Liste dient ausschließlich als Drift-Gegenprüfung und erzeugt die
statische Oracle-Inventarliste nicht.

Für jede Projektion enthält das Oracle:

- die kanonische, explizit benannte Feldmenge;
- statische normalisierte erwartete Zeilen;
- eine stabile, dokumentierte Sortierreihenfolge;
- die zugehörige Normalisierungs- und Digestversion;
- einen Projektiondigest nach Abschnitt E.

Die exakte Ablageform aus `columns`, `sort_by`, `rows` und `sha256` sowie die
Schema-ID `genus-golden-ledger-projection-rows-v1` stehen im Artifact Schema
Contract. Diese Row-Schema-ID bezeichnet die nach der folgenden weiterhin
geltenden Normalisierungsversion gebildete Darstellung.

Die Normalisierungsversion für den ersten Kandidaten heißt
`genus-projection-normalization-v1` und legt SQLite-Werte wie folgt fest:

- SQL `NULL` wird JSON `null`;
- SQLite `INTEGER` wird eine JSON-Ganzzahl; ein Integer wird nicht ohne
  expliziten Spaltenvertrag zu einem Boolean umgedeutet;
- SQLite `REAL` wird eine endliche JSON-Zahl nach dem Encodervertrag aus
  Abschnitt C; `NaN` und Unendlichkeiten sind Fehler, `-0.0` wird `0.0`;
- SQLite `TEXT` wird Unicode-NFC-normalisierter JSON-Text;
- Zeit- und `created_at`-Spalten bleiben exakt im Fixtureformat
  `YYYY-MM-DDTHH:MM:SS.ffffff+00:00`; keine Zeitzonen- oder
  Präzisionskonvertierung ist erlaubt;
- JSON-Spalten werden geparst, alle enthaltenen Strings rekursiv NFC-normalisiert
  und mit dem Encodervertrag aus Abschnitt C neu serialisiert;
- SQLite `BLOB` ist in v1 nicht erlaubt und löst bis zu einer neuen
  menschlichen Vertragsentscheidung einen Stopp aus.

Feste Eventzeitstempel und replaybare `created_at`-Werte werden mitgeprüft. Ein
Feld darf nur mit dokumentierter Begründung ausgeschlossen werden, wenn es nicht
aus dem Ledger rekonstruierbar oder nach dem bestehenden Projektionsvertrag
nicht Teil der replaybaren Semantik ist.

Erwartete semantische Zeilen werden weder zur Testlaufzeit noch zur
Oracle-Ersterzeugung aus dem aktuellen Projektor- oder Replayoutput als
Autorität übernommen. Ein Runtime-Lauf darf ausschließlich als nicht
autoritative Gegenprüfung dienen.

### D.1 Persistierter Belief-Lifecycle und read-time Epistemik

`expected_projections.belief_projection` enthält ausschließlich die statisch
erwarteten persistierten Projektionszeilen. Für deren Feld `state` sind im
Golden Oracle nur die Lifecyclewerte `active` und `superseded` zulässig.
`supported`, `contested` und `uncertain` sind read-time Epistemik und keine
persistierten Werte von `belief_projection.state`.

Die Fixture enthält drei getrennte Fälle:

- **Supported:** `state = active`, genau zwei Supporting-Events, null
  Contradicting-Events und alle verwendeten Evidence-Zeitpunkte nach Parsing
  gleich dem festen UTC-`as_of`; ihre Fixture-Strings bleiben im Format
  `YYYY-MM-DDTHH:MM:SS.ffffff+00:00`. Die erwartete Confidence ist der Quotient
  `2 / (2 + 0 + 1)`, für das statische Feld und den Vergleich auf drei
  Dezimalstellen gerundet `0.667`; erwarteter read-time Zustand ist
  `supported`.
- **Contested:** `state = active`, genau ein Supporting-Event, zwei
  Contradicting-Events und alle verwendeten Evidence-Zeitpunkte nach Parsing
  gleich dem festen UTC-`as_of`; ihre Fixture-Strings bleiben im Format
  `YYYY-MM-DDTHH:MM:SS.ffffff+00:00`. Die erwartete Confidence ist der Quotient
  `1 / (1 + 2 + 1)`, für das statische Feld und den Vergleich auf drei
  Dezimalstellen gerundet `0.250`; erwarteter read-time Zustand ist
  `contested`.
- **Superseded:** Der alte Belief besitzt `state = superseded` und verweist mit
  `superseded_by` auf den Nachfolger; der Nachfolger besitzt `state = active`.
  Dieser Fall wird als persistierter Lifecycle und nicht zusätzlich über
  `epistemic_state()` geprüft.

Das Oracle führt getrennt von `expected_projections` exakt diesen
Top-Level-Bereich:

```yaml
expected_read_models:
  belief_epistemic_state_v1:
    as_of: "2026-01-01T00:00:00.000Z"
    halflife_seconds: 3600.0
    cases: []
```

Jeder Fall enthält `belief_id`, `supporting_event_ids`,
`contradicting_event_ids`, `expected_confidence` und
`expected_epistemic_state`. Der Test darf `confidence.calculate_confidence`
nur mit explizitem `now=as_of` und `halflife_seconds=3600.0` sowie
`projection.epistemic_state` aufrufen. `expected_confidence` ist eine JSON-Zahl;
der berechnete Wert wird vor dem Vergleich ebenfalls auf drei Dezimalstellen
gerundet. Aktuelle Wall Clock, implizit gelernte Half-life und
`belief_with_confidence()` als Golden-Zeitquelle sind unzulässig.
Die statischen read-time Erwartungen dürfen ebenso wenig wie Projektionszeilen
oder Digests aus aktuellem Runtimeoutput als Autorität übernommen werden.

## E. Projection Digest Contract

Die Eingabe jedes Projektiondigests ist die nach Abschnitt D normalisierte und
stabil sortierte `rows`-Liste. Sie enthält nur endliche Zahlen, ist rekursiv
Unicode-NFC-normalisiert und hat `-0.0` vor der Serialisierung zu `0.0`
normalisiert. Auch eine leere Projektion besitzt die explizite Liste `[]` und
deren Digest.

Die exakten kompakten Bytes des einzelnen Projektiondigests und des
Projection-Digest-Sets definiert der Artifact Schema Contract. Beide verwenden
`ensure_ascii=False`, UTF-8 ohne BOM und keine abschließende Newline. Diese
semantischen Byteformen sind von der äußeren `ensure_ascii=True`-
Dateiserialisierung des Oracle getrennt.

`projection_digest_set_sha256` ist der verpflichtende Gesamtdigest aus exakt
den zwölf Projektionsnamen und ihren kleingeschriebenen hexadezimalen
SHA-256-Digests. Eine Änderung an Spalten, Sortierung, JSON-Behandlung,
Normalisierungsversion oder Digestbildung ist eine bewusste Vertragsänderung
unter Ronnys Patchhoheit und kein beiläufiges Testupdate.

## F. Human Review Contract

Vor einer Annahme prüft Ronny in dem ausdrücklich getrennten
Oracle-Review-Durchlauf mindestens:

- [ ] jede Eventzeile gegen `EVENT_CONTRACT.md`
- [ ] den nichtleeren unversiegelten Legacy-Präfix
- [ ] `prefix_count`, `prefix_max_id` und Genesis-Digest
- [ ] das vorhandene v1-Epochen-Event
- [ ] die vollständige Seal-Kette und den erwarteten Head
- [ ] jede erwartete Projektionswirkung gegen ihre Quell-Events
- [ ] persistierten Belief-Lifecycle `active`/`superseded` einschließlich Nachfolger
- [ ] getrennte read-time Fälle `supported`/`contested` bei festem `as_of` und fester Half-life
- [ ] jede ausdrücklich leere Projektion
- [ ] Feldmengen, Sortierung und JSON-Normalisierung
- [ ] jeden Projektionsdigest und `projection_digest_set_sha256`
- [ ] das Anchor-v1-Testartefakt und seine historische Head-Grenze
- [ ] Datenschutzfreiheit und ausschließlich synthetischen Inhalt
- [ ] den exakten Wert und alle Pflichtvorkommen von `fixture_schema_version`
- [ ] `fixture_sha256` über die exakten `events.jsonl`-Bytes
- [ ] die vollständige Eventstrom-Byteform einschließlich Record-Feldmenge,
  `payload_text`, Arrayserialisierung ohne finale Newline und 64-stelligem
  lowercase `event_stream_sha256`
- [ ] `event_stream_digest_schema` und Source-/Import-Gleichheit von `event_stream_sha256`
- [ ] Manifestversion und vollständige Import-Receipt-Bindung
- [ ] exakte Dateinamen, Schema-IDs und Kandidatenstatus-Platzierung
- [ ] direkte Oracle-Source-Bindings und artefaktübergreifende Count-Gleichheiten
- [ ] Oracle-, Manifest-, Anchor- und Bundle-Digest nach ihrer jeweiligen Byteform
- [ ] statisches Import Receipt gegen das unabhängig berechnete In-Memory-Actual-Receipt
- [ ] exakte Gleichheit der zwölf Oracle- und Runtime-Projektionsnamen
- [ ] Legacy-, Tail-, Anchor- und Oracle-Gegenfälle

Alle Checkboxen bleiben bis zum menschlichen Review offen. Codex darf sie weder
markieren noch eine Annahme formulieren. Werden Fixture oder Oracle danach
geändert, werden alle betroffenen Prüfpunkte wieder offen.

## G. Stop Conditions

Die Arbeit stoppt sofort bei:

- Widerspruch zu ADR-0006, ADR-0009, ADR-0010, ADR-0011 oder diesem Vertrag;
- Produktdaten oder identifizierenden Inhalten im Corpus;
- notwendiger Änderung an Runtime, Schema, Replay, Integrity, Seal, Anchor,
  Deploy oder CI;
- Ableitung des Oracles aus dem aktuell geprüften Replay-/Projektoroutput;
- unklarem Eventvertrag oder erfundenem Eventtyp beziehungsweise Pflichtfeld;
- ungeklärter JSONL-, Projektions- oder Digestkanonisierung;
- fremden Änderungen im Worktree;
- erforderlichem Zugriff auf Produktdatenbank, Produktanchor, Secret, Hostdaten
  oder Netzwerk;
- jeder nicht vorab von Ronny freigegebenen Scope-Erweiterung.

Ein Stopp darf keine dauerhafte Fixture verändern, keine Review-Checkbox
markieren und keinen Teilkandidaten als akzeptiert darstellen.

## Später erlaubter A0.2-Modellscope

Dieser Scope gilt erst mit einem neuen ausdrücklichen Implementierungsauftrag
unter ADR-0010.

`70565fe` ist die Code-/Test-Ausgangsbaseline vor ADR-0010 und diesem Vertrag.
Der spätere Lauf erfasst seinen dann sauberen HEAD; diese namentliche Pfadliste
bleibt statisch. Die nach `70565fe` angenommenen Governance-Dokumente gelten in
der von Ronny später committeten Fassung. Jede weitere Inhalts- oder
Pfaderweiterung benötigt vor dem Lesen eine erneute menschliche Freigabe.

### Read-only

- `genus/db.py`
- `genus/ledger.py`
- `genus/sealing.py`
- `genus/anchor.py`
- `genus/event_router.py`
- `genus/integrity.py`
- `genus/projection.py`
- `genus/relation_semantics.py`
- `genus/confidence.py`
- `genus/proposals.py`
- `genus/inquiries.py`
- `genus/experience.py`
- `genus/state.py`
- `genus/governance.py`
- `genus/operation.py`
- `genus/maturation.py`
- `genus/response_outcomes.py`
- `schema.sql`
- `tests/test_anchor.py`
- `tests/test_integrity.py`
- `tests/test_ledger.py`
- `tests/test_sealing.py`
- `docs/ARCHITECTURE.md`
- `docs/EVENT_CONTRACT.md`
- `docs/SECURITY_MODEL.md`
- `docs/QUALITY.md`
- `docs/decisions/ADR-0006-GOLDEN-LEDGER-ORACLE.md`
- `docs/decisions/ADR-0009-HUMAN-OWNED-CRITICAL-LANE.md`
- `docs/decisions/ADR-0010-HUMAN-SUPERVISED-MODEL-ASSISTANCE-A0.md`
- `docs/decisions/ADR-0011-GOLDEN-LEDGER-CANONICALIZATION-AND-BELIEF-COVERAGE.md`
- `docs/reviews/A0_2_GOLDEN_LEDGER_ENTRY_CONTRACT.md`
- `docs/reviews/A0_2_GOLDEN_LEDGER_ARTIFACT_SCHEMA.md`

### Test-only write

Die Read-only-Erweiterungen aus ADR-0011 und Version 1.2 erweitern diesen
Write-Scope nicht.

Persistente Repository-Kandidatenwrites sind ausschließlich erlaubt in:

- `tests/fixtures/golden_ledger_v1/*`
- `tests/golden_ledger_support.py`
- `tests/test_golden_ledger_oracle.py`

Zusätzlich darf der Testprozess disposable SQLite-Dateien einschließlich ihrer
WAL-/SHM-Begleiter ausschließlich unter pytest-`tmp_path` oder einem vorab
benannten temporären `--basetemp` erzeugen. Diese Dateien sind keine
Repository-Kandidaten, werden nie als Oracle verwendet und dürfen keine
Produktpfade referenzieren. Python-Bytecode und pytest-Cache werden mit `-B`
und `-p no:cacheprovider` deaktiviert; weitere Cache- oder Arbeitsverzeichnisse
sind nicht autorisiert.

### Ausgeschlossen

- Änderungen unter `genus/`
- Änderungen an `schema.sql`
- Änderungen unter `deploy/`
- Änderungen an CI oder produktiver Konfiguration
- Änderungen an Produktdaten
- Commit, Merge, Push, Deploy oder Pull Request durch Codex

## Aktueller Stand

Der Eingangskontrakt und sein mechanischer Artifact Schema Contract sind
angenommen. Es existiert aus diesem Auftrag noch kein Golden Ledger, Oracle,
Anchor-Testartefakt, Loader, Digest oder Golden-Testcode. A0.2 bleibt aktiv und
wartet auf einen gesonderten Implementierungsauftrag.
