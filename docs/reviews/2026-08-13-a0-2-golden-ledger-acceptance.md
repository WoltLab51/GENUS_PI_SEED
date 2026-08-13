# A0.2 Golden Ledger V2 · menschlicher Annahmebeleg

> **Status:** accepted human decision
>
> **Reviewer:** Ronny
>
> **Decision date:** 2026-08-13
>
> **Entscheidung:** accepted

## Gebundene Fassung

Ronny nimmt den revidierten A0.2 Golden-Ledger- und Replay-Oracle-Kandidaten V2
fachlich und technisch an. Die angenommene Fassung ist durch folgende Werte
eindeutig gebunden:

| Bindung | SHA-256 |
|---|---|
| ZIP | `a558ad2e5285fb195b3811d611ca8d4846b9e01e3cda79ffb319d160e752ff64` |
| Bundle | `4db7306c912ae50f32895f7e3764355e28b72e23c083484475eea9f64f933c0e` |
| Fixture | `950a39ea033f7867b2ad45e9807806c0ecd9f08f6bb4ef5a6504934a518ce839` |
| Oracle | `b11b1ab61b81015ce27aa3d1546f4516fafbaad60744d959fbaff51e9e9c4869` |

- **Governance-Baseline:** `1a102979b3a53d68207a86147005e137e6b0a5db`
- **Promotion-Baseline-Commit:** `8322b1f206f139abafd844d0b874df91d4c1617f`

Die neun geprüften Kandidatendateien werden byteidentisch angenommen:

- `tests/fixtures/golden_ledger_v1/ORACLE_REVIEW.md`
- `tests/fixtures/golden_ledger_v1/README.md`
- `tests/fixtures/golden_ledger_v1/anchor_v1.json`
- `tests/fixtures/golden_ledger_v1/events.jsonl`
- `tests/fixtures/golden_ledger_v1/import_receipt.json`
- `tests/fixtures/golden_ledger_v1/manifest.json`
- `tests/fixtures/golden_ledger_v1/oracle.json`
- `tests/golden_ledger_support.py`
- `tests/test_golden_ledger_oracle.py`

## Governance und Verträge

Die Annahme folgt
[ADR-0006](../decisions/ADR-0006-GOLDEN-LEDGER-ORACLE.md),
[ADR-0009](../decisions/ADR-0009-HUMAN-OWNED-CRITICAL-LANE.md),
[ADR-0010](../decisions/ADR-0010-HUMAN-SUPERVISED-MODEL-ASSISTANCE-A0.md) und
[ADR-0011](../decisions/ADR-0011-GOLDEN-LEDGER-CANONICALIZATION-AND-BELIEF-COVERAGE.md)
sowie dem
[A0.2 Golden Ledger Entry Contract](A0_2_GOLDEN_LEDGER_ENTRY_CONTRACT.md) und dem
[A0.2 Golden Ledger Artifact Schema Contract](A0_2_GOLDEN_LEDGER_ARTIFACT_SCHEMA.md).

Ronny bleibt Eigentümer der Annahmeentscheidung und der fachlichen
Verantwortung. Codex setzt diese Entscheidung ausschließlich als technischer,
nicht autoritativer Operator um.

## Verifikation

- 19 fokussierte Golden-Ledger-Tests bestanden
- 92 relevante Regressionen bestanden
- 1.509 Volltests bestanden
- Ruff bestanden
- unabhängige Digest-, Corpus-, Oracle- und Anchor-Prüfung bestanden

Die offenen Checkboxen in `ORACLE_REVIEW.md` bleiben Teil des unveränderten,
historisch geprüften Kandidatenpakets. Die verbindliche spätere
Annahmeentscheidung lebt in diesem separaten menschlichen Beleg.

## Verbleibende Grenze

Der angenommene Golden-JSONL-/Replay-Oracle-Teil ist das versionierte
Testfundament. Das nach den committed Verträgen separat gegatete historische
SQLite-Artefakt bleibt als eigener A0.2-Teilschritt offen. Diese Annahme
autorisiert weder Produktmigration noch Schema-, Ledger-, Seal-, Reseal- oder
Anchor-v2-Änderungen.
