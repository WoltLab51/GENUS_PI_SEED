# A0.2 Golden Ledger Entry Contract

> **Status:** accepted entry contract · **Datum:** 2026-08-10
>
> **Owner:** Ronny
>
> **Gilt vor:** dem ersten Golden-Ledger-, Oracle-, Anchor-Fixture- oder
> Testartefakt
>
> **Entscheidungsgrundlage:**
> [ADR-0006](../decisions/ADR-0006-GOLDEN-LEDGER-ORACLE.md),
> [ADR-0009](../decisions/ADR-0009-HUMAN-OWNED-CRITICAL-LANE.md) und
> [ADR-0010](../decisions/ADR-0010-HUMAN-SUPERVISED-MODEL-ASSISTANCE-A0.md)

## Zweck und Gate

Dieser Vertrag legt Rollen, Corpusgrenzen, Kanonisierung, Oracle-Digests,
menschliche Abnahme und Stop Conditions fest, bevor das erste A0.2-Artefakt
entsteht. Er autorisiert noch keine Fixture, kein Oracle und keinen Testcode.

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
- mit Belief-Zuständen `supported`, `contested` und `superseded` ausgestattet;
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

Das statische `oracle.json` bindet mindestens:

- seine eigene Schema- und Formatversion;
- den Fixture-Dateinamen und SHA-256 der exakten `events.jsonl`-Bytes;
- Eventzahl und einen kanonischen Digest des vollständigen Eventstroms;
- Legacy-Präfix, Genesis, Epoche, Head und erwarteten Seal-/Integrity-Status;
- die vollständige statische Projektionsinventarliste aus Abschnitt D;
- Normalisierungs- und Digestversion sowie jeden Projektionsdigest und den
  Gesamtdigest.

Der deterministische Import in eine temporäre Current-Schema-SQLite-Datenbank
erzeugt ein Test-Receipt mit JSONL-Digest, Fixture-Schemaversion und dem
resultierenden read-only Eventdigest. Dieser Eventdigest muss dem im Manifest
gebundenen Eventstrom entsprechen. Die temporäre Datenbank ist nie normative
Quelle.

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

## E. Projection Digest Contract

Für jede Projektion gilt:

1. Die nach Abschnitt D normalisierten und stabil sortierten Zeilen werden als
   ein kanonisches JSON-Array serialisiert.
2. Die Kodierung ist UTF-8.
3. Die Serialisierung verwendet vollständig den Encodervertrag aus Abschnitt C,
   einschließlich Unicode-NFC, `ensure_ascii=false`, `allow_nan=false`,
   `sort_keys=true` und `separators=(",", ":")`, ohne zusätzliche
   Whitespace-Varianz.
4. Der Digest ist SHA-256 über genau diese kanonischen Bytes.
5. Das Oracle nennt Digestalgorithmus und Normalisierungsversion ausdrücklich.
6. Auch eine leere Projektion besitzt die explizite Zeilenliste `[]` und deren
   kanonischen Digest.

Ein Gesamtdigest ist verpflichtend. Dafür wird ein JSON-Objekt aus exakt den
zwölf Projektionsnamen und ihren kleingeschriebenen hexadezimalen SHA-256-
Digests gebildet und mit dem Encodervertrag aus Abschnitt C kanonisch
serialisiert; der Gesamtdigest ist SHA-256 über diese Bytes. Eine Änderung an
Spalten, Sortierung, JSON-Behandlung,
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
- [ ] jede ausdrücklich leere Projektion
- [ ] Feldmengen, Sortierung und JSON-Normalisierung
- [ ] jeden Projektionsdigest und den Gesamtdigest
- [ ] das Anchor-v1-Testartefakt und seine historische Head-Grenze
- [ ] Datenschutzfreiheit und ausschließlich synthetischen Inhalt
- [ ] den SHA-256-Digest der exakten `events.jsonl`-Bytes
- [ ] Manifestversion, Eventdigest und Import-Receipt-Bindung
- [ ] exakte Gleichheit der zwölf Oracle- und Runtime-Projektionsnamen
- [ ] Legacy-, Tail-, Anchor- und Oracle-Gegenfälle

Alle Checkboxen bleiben bis zum menschlichen Review offen. Codex darf sie weder
markieren noch eine Annahme formulieren. Werden Fixture oder Oracle danach
geändert, werden alle betroffenen Prüfpunkte wieder offen.

## G. Stop Conditions

Die Arbeit stoppt sofort bei:

- Widerspruch zu ADR-0006, ADR-0009, ADR-0010 oder diesem Vertrag;
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
- `docs/reviews/A0_2_GOLDEN_LEDGER_ENTRY_CONTRACT.md`

### Test-only write

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

Der Eingangskontrakt ist angenommen. Es existiert aus diesem Auftrag noch kein
Golden Ledger, Oracle, Anchor-Testartefakt, Loader, Digest oder Golden-Testcode.
A0.2 bleibt aktiv und wartet auf einen gesonderten Implementierungsauftrag.
