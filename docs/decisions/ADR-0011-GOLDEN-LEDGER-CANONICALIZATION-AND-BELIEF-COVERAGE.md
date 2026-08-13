# ADR-0011 — Golden Ledger Canonicalization, Belief Coverage and Projector Read Scope

> **Status:** accepted · **Datum:** 2026-08-10
>
> **Owner:** Ronny
>
> **Scope:** ausschließlich Präzisierung des A0.2-Kandidatenbaus

## 1. Context

[ADR-0006](ADR-0006-GOLDEN-LEDGER-ORACLE.md) verlangt ein synthetisches
Golden Ledger mit unabhängigem Replay-Oracle. [ADR-0009](ADR-0009-HUMAN-OWNED-CRITICAL-LANE.md)
hält A0 in menschlicher Verantwortung. [ADR-0010](ADR-0010-HUMAN-SUPERVISED-MODEL-ASSISTANCE-A0.md)
erlaubt Ronny eine eng begrenzte, nicht autoritative Modellassistenz für A0.2.
Der zugehörige
[Entry Contract](../reviews/A0_2_GOLDEN_LEDGER_ENTRY_CONTRACT.md) legt die
Grenzen vor dem ersten Artefakt fest.

## 2. Stopped candidate build

Der erste Kandidatenbau wurde vor jeder Fixture-, Oracle-, Loader- oder
Testdatei korrekt gestoppt. Nicht bytegenau bestimmt waren der separate
semantische Eventstromdigest und der Wert der Fixture-Schemaversion. Außerdem
waren persistierter Belief-Lifecycle und read-time Epistemik vermischt, während
die freigegebenen Quellen die feldgenaue Projektorwirkung nicht vollständig
offenlegten.

Der Stopp war eine Anwendung der bestehenden Verträge, keine Ablehnung des
Golden-Ledger-Ziels.

## 3. Human decision

Ronny legt die folgenden Werte, Hashdomänen, Belief-Fälle und namentlichen
Read-only-Pfade fest. Diese Entscheidung schafft keine Autorität für Codex oder
GENUS. Corpus, erwartete Semantik, Review, Annahme und ein späterer Commit
bleiben menschlich verantwortet.

## 4. Fixture schema version

Der verbindliche Wert lautet:

```text
fixture_schema_version = "genus-golden-ledger-fixture-v1"
```

Er erscheint später mindestens in `manifest.json`, `oracle.json` und
`import_receipt.json`. Er bezeichnet die Form der statischen Golden-Fixture,
nicht die SQLite-Schema- oder Oracle-Schemaversion. Eine `events.jsonl`-Zeile
wiederholt ihn nicht und beschreibt ausschließlich eine historische
`event_log`-Zeile mit `id`, `event_type`, `payload`, `created_at`, `prev_seal`
und `seal`.

## 5. Exact fixture-byte digest

Das Feld `fixture_sha256` bindet ausschließlich die exakten Bytes von
`events.jsonl`:

- UTF-8 ohne BOM;
- LF-Zeilenenden;
- genau eine finale LF;
- keine automatische Neuformatierung;
- SHA-256 als 64 Kleinbuchstaben-Hexzeichen.

Dieser Digest bindet die menschlich reviewte Datei einschließlich ihrer äußeren
kanonischen Darstellung.

## 6. Exact semantic event-stream digest

Der semantische Eventstromdigest besitzt die Schema-ID

```text
event_stream_digest_schema = "genus-golden-ledger-event-stream-digest-v1"
```

und den Feldnamen `event_stream_sha256`. Seine Bytes werden exakt so gebildet:

1. Alle Fixture-Events werden nach ganzzahliger `id` aufsteigend sortiert.
2. Das `payload`-Feld jeder Fixture-Zeile wird als JSON-Objekt gelesen.
3. `payload_text` wird exakt gebildet mit
   `json.dumps(payload, ensure_ascii=True, sort_keys=True,
   separators=(",", ":"))`.
4. Für jedes Event wird genau dieses semantische Record-Objekt gebildet:

   ```json
   {
     "created_at": "<exakter created_at-String>",
     "event_type": "<exakter event_type-String>",
     "id": 1,
     "payload_text": "<kanonischer payload-String>",
     "prev_seal": null,
     "seal": null
   }
   ```

   `id` ist dabei der jeweilige Integer; `prev_seal` und `seal` sind der
   jeweilige String oder JSON `null`.
5. Die geordnete Liste aller Record-Objekte wird als JSON-Array exakt mit
   `json.dumps(records, ensure_ascii=True, sort_keys=True,
   separators=(",", ":"))` serialisiert.
6. Das Ergebnis wird als UTF-8 ohne BOM und ohne abschließende Newline codiert.
7. `event_stream_sha256` ist SHA-256 über exakt diese Bytes, ausgegeben als 64
   Kleinbuchstaben-Hexzeichen.

`fixture_sha256` und `event_stream_sha256` besitzen verschiedene Hashdomänen:
Der erste bindet die Datei-Bytes, der zweite die semantisch zu importierenden
`event_log`-Zeilen. Beide stehen später im Manifest. Das Import Receipt weist
`fixture_schema_version`, `fixture_sha256`, `event_stream_digest_schema`, den
aus dem read-only importierten Eventstrom erneut berechneten
`event_stream_sha256` und die importierte Zeilenzahl aus. Der Source- und der
Import-Eventstrom müssen denselben `event_stream_sha256` ergeben; eine
Gleichheit mit `fixture_sha256` wird nicht behauptet.

## 7. Belief lifecycle versus epistemic state

Das persistierte Feld `belief_projection.state` wird im Golden Oracle
ausschließlich mit den tatsächlich persistierten Lifecyclewerten `active` und
`superseded` erwartet.

`supported`, `contested` und `uncertain` sind keine persistierten Werte dieses
Felds. Sie sind read-time Epistemik. Persistierte Projektionszeilen und ihre
Digests bleiben deshalb getrennt von den erwarteten read-time Fällen.

## 8. Deterministic belief coverage

Die Golden Fixture trägt drei getrennte Fälle:

### A. Supported

- persistierter `state = active`;
- genau zwei Supporting-Events;
- genau null Contradicting-Events;
- alle verwendeten Evidence-Zeitpunkte bezeichnen nach Parsing denselben
  UTC-Zeitpunkt wie das feste `as_of`; ihre Fixture-Strings bleiben im
  Fixtureformat `YYYY-MM-DDTHH:MM:SS.ffffff+00:00`;
- erwartete Confidence `2 / (2 + 0 + 1)`, für das statische Feld und den
  Vergleich auf drei Dezimalstellen gerundet: `0.667`;
- erwarteter read-time `epistemic_state = supported`.

### B. Contested

- persistierter `state = active`;
- genau ein Supporting-Event;
- genau zwei Contradicting-Events;
- alle verwendeten Evidence-Zeitpunkte bezeichnen nach Parsing denselben
  UTC-Zeitpunkt wie das feste `as_of`; ihre Fixture-Strings bleiben im
  Fixtureformat `YYYY-MM-DDTHH:MM:SS.ffffff+00:00`;
- erwartete Confidence `1 / (1 + 2 + 1)`, für das statische Feld und den
  Vergleich auf drei Dezimalstellen gerundet: `0.250`;
- erwarteter read-time `epistemic_state = contested`.

### C. Superseded

- der alte Belief besitzt `state = superseded`;
- sein `superseded_by` verweist auf den Nachfolger;
- der Nachfolger besitzt `state = active`;
- `superseded` wird als persistierter Lifecycle geprüft und nicht zusätzlich
  durch `epistemic_state()` klassifiziert.

Das Oracle erhält getrennt von `expected_projections` den Bereich:

```yaml
expected_read_models:
  belief_epistemic_state_v1:
    as_of: "2026-01-01T00:00:00.000Z"
    halflife_seconds: 3600.0
    cases: []
```

Jeder statische Fall enthält `belief_id`, `supporting_event_ids`,
`contradicting_event_ids`, `expected_confidence` und
`expected_epistemic_state`. Der spätere Test darf die Fälle mit
`confidence.calculate_confidence(..., now=as_of,
halflife_seconds=3600.0)` und `projection.epistemic_state` deterministisch
gegenprüfen. `expected_confidence` ist eine JSON-Zahl; der Test rundet den
berechneten Wert vor dem Vergleich ebenfalls auf drei Dezimalstellen. Aktuelle
Wall Clock, implizit gelernte Half-life,
`belief_with_confidence()` als Golden-Zeitquelle sowie `supported` oder
`contested` als persistierter `belief_projection.state` sind ausgeschlossen.

Die statischen Erwartungen werden menschlich aus dem angenommenen Vertrag
hergeleitet. Die aktuellen Funktionen und ihr Output dürfen sie prüfen, aber
weder erzeugen, aktualisieren noch freigeben.

## 9. Extended read-only projector scope

Für einen späteren, erneut ausdrücklich von Ronny erteilten A0.2-
Implementierungsauftrag darf Ronny Codex zusätzlich genau diese Quellen
read-only analysieren lassen:

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

Zweck ist ausschließlich, feldgenaue Projektorsemantik, Defaults,
Lifecyclewirkungen und die deterministische read-time Belief-Prüfung
nachvollziehbar zu machen. Die Liste ist statisch; Kategorien, Globs,
Verzeichnisse, Import-Closure und automatisch nachgezogene Dateien sind nicht
freigegeben.

Diese enge, menschlich erteilte A0.2-Spezialentscheidung präzisiert die
eingefrorene Read-only-Liste aus ADR-0010 und dem Entry Contract und besitzt nur
für die vorstehenden Pfade denselben engen Vorrang vor ADR-0009s absolutem
Modell-Leseverbot. Alle übrigen Grenzen bleiben unverändert. Codex erhält keine
eigene, dauerhafte oder übertragbare Critical-Scope-Autorität.

Dieser docs-only Auftrag ist ausdrücklich noch kein A0.2-Implementierungsauftrag
und aktiviert weder die neuen Lesepfade noch irgendeinen Kandidaten-Write-Scope.

## 10. Unchanged test-only write scope

Der persistente Write-Scope bleibt unverändert und ausschließlich:

- `tests/fixtures/golden_ledger_v1/*`
- `tests/golden_ledger_support.py`
- `tests/test_golden_ledger_oracle.py`

Temporäre SQLite-, WAL- und SHM-Dateien bleiben ausschließlich unter pytest-
`tmp_path` oder dem ausdrücklich benannten `--basetemp` erlaubt. Kein Runtime-,
Schema-, Projektor-, Replay-, Seal-, Anchor-, Deploy- oder CI-Pfad wird zum
Write-Scope.

## 11. Relationship to ADR-0006

ADR-0006 bleibt vollständig gültig. ADR-0011 präzisiert für den ersten A0.2-
Kandidaten die Fixture-Schemaversion, zwei getrennte Digestdomänen und die
Belief-Coverage. Es ändert weder die Golden-first-Reihenfolge noch das
Unabhängigkeitsgebot des Oracles.

## 12. Relationship to ADR-0009

A0 bleibt human-owned Critical Lane. Der enge, namentliche und nur read-only
geltende Carve-out erweitert weder die autonome Coding-Membran noch eine
mergefähige Modellspur. Ronny behält Corpus, Datenschutzprüfung, Oracle-Review,
Patchhoheit, Annahme und Commit.

## 13. Relationship to ADR-0010

ADR-0010 bleibt der Autoritätsvertrag für menschlich geführte Modellassistenz.
ADR-0011 präzisiert ausschließlich seinen späteren A0.2-Read-only-Pfadsatz und
den fachlichen Vertrag, gegen den ein Kandidat gebaut werden kann. Weder
Projektorcode noch Runtimeoutput wird dadurch zur Oracle-Autorität. Eine spätere
Ausführung benötigt weiterhin einen neuen ausdrücklichen Implementierungsauftrag
von Ronny.

## 14. Consequences

- Fixture-Version und beide Digestdomänen sind bytegenau bestimmt.
- Der Import kann Dateiidentität und semantische Eventstromgleichheit getrennt
  beweisen.
- Persistierter Belief-Lifecycle und read-time Epistemik sind getrennte
  Oracle-Bereiche.
- Der spätere Read-only-Scope deckt die tatsächlich zuständigen Projektoren
  namentlich ab, ohne den Write-Scope zu erweitern.
- Alle Kandidaten bleiben `CANDIDATE — PENDING HUMAN REVIEW`; grüne Tests sind
  keine menschliche Oracle-Abnahme.

## 15. Stop conditions

Der spätere Kandidatenbau stoppt weiterhin bei jedem Widerspruch zu ADR-0006,
ADR-0009, ADR-0010, ADR-0011 oder Entry Contract, insbesondere bei:

- Abweichung von den festgelegten Versionen oder Digestbytes;
- Vermischung von `fixture_sha256` und `event_stream_sha256`;
- `supported` oder `contested` als persistiertem Lifecyclewert;
- wall-clock- oder implizit Half-life-abhängigen Golden-Erwartungen;
- Ableitung statischer Projektionen, read-time Erwartungen oder Digests aus
  aktuellem Runtimeoutput als Autorität;
- Lesen oder Schreiben eines nicht namentlich freigegebenen Pfads;
- notwendiger Änderung an Runtime, Schema, Replay, Integrity, Seal, Anchor,
  Deploy oder CI;
- Produktdaten, Secrets, Hostdaten, Produktdatenbank oder Netzwerkbedarf.

## 16. Non-goals

ADR-0011 erzeugt keine Fixture, kein Oracle, kein Manifest, kein Import Receipt,
keinen Loader und keinen Test. Es ändert keinen Runtime-, Schema-, Ledger-,
Replay-, Seal-, Anchor-, Key-, GitHub-, Deploy- oder Produktdatenpfad. Es
autorisiert keinen Commit, Push, Merge, Deploy oder Pull Request durch Codex und
ersetzt weder ADR-0006 noch ADR-0009 noch ADR-0010.
