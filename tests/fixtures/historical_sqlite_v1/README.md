# Historical SQLite v1 candidate

Status: **ACCEPTED**

Human decision: Ronny accepted the candidate on 2026-08-14. The decision and
its stated evidence boundary are recorded in `HUMAN_REVIEW.md`.

This fixture preserves a real earlier GENUS storage shape for future read-only
schema detection and migration tests against copies. It is not a migration and
must never be opened through current schema initialization.

## Historical source

- Repository: `WoltLab51/GENUS_PI_SEED`
- Commit: `2bf67e6ded3164ad5d4a977954639cc294568633`
- Date: `2026-06-12T11:33:48+02:00`
- Message: `Implement v1.1 ledger sealing`
- Historical schema path: `schema.sql`
- Historical schema SHA-256: `1ef8229402abb6203623f38fbc3a7fb35cf74c6c60bb4c6908c62d36cd9c5ddb`

This source is suitable as the first historical fixture because it already has
the append-only six-column `event_log`, the sealing epoch, a genesis binding,
and projection tables, while remaining visibly older than the current schema.
Compared with the current schema it lacks five tables and nine explicit
indexes; these differences give later schema detection a meaningful boundary.
The comparison is bound to current commit
`0f6074707642d0b58543f122fbae18ff44a46ff6`; its `schema.sql` digest uses the
repository text normalized to LF so that checkout line endings cannot change
the comparison identity.

## Contents

- `schema.sql`: byte-exact historical schema copied from the source commit.
- `events.jsonl`: seven fixed synthetic events, including a three-event legacy
  prefix, one epoch-opening event, and a three-event sealed tail.
- `legacy_v1.sqlite3`: immutable binary fixture created directly from the
  historical schema, containing the seven events and one synthetic belief row.
- `manifest.json`: provenance, byte digests, schema fingerprint, inventory,
  current-schema differences, and SQLite build metadata.
- `HUMAN_REVIEW.md`: the signed human acceptance record and evidence boundary.
- `.gitignore`/`.gitattributes`: narrowly make the immutable SQLite binary
  trackable and preserve the candidate's exact text/binary byte domains.

The database contains no personal or productive data. The only domain values
are the synthetic temperature observations `21.5` and `22.0`, the synthetic
claim `synthetic.temperature = nominal`, and the source/derivation label
`fixture:legacy-v1`.

## Bound values

- SQLite SHA-256: `459e266c3fcc40f7ea9df21aa4e2fd0fc6106210266b9d7032cfeab721a36682`
- Events JSONL SHA-256: `fd6dfe2eb4a8ec8c022c6e25d494f59d9cc4397ea2f47777d81c8a736ff0efaf`
- Semantic event-stream SHA-256: `cf80f53802594f48eb09e00f694fabacbd2d9b9a6eb969ce174bd8a3f9dcecbb`
- Schema fingerprint SHA-256: `e73837d56217169b1365a75ca404d6512ff7c9655d3e5dc993ba12b368d446a3`

The event-stream digest uses
`genus-golden-ledger-event-stream-digest-v1`; the schema fingerprint hashes the
canonical full table-column/index/trigger inventory defined by
`genus-sqlite-schema-inventory-v1`.

## Construction and safety boundary

The candidate was built by executing only the checked-in historical
`schema.sql`, then inserting the exact canonical payload texts from
`events.jsonl` and one fixed projection row. Current `init_schema`, current
`schema.sql`, migration code, replay, and producers were not used.

Tests inspect the original only with `genus.db.connect_readonly`. Every test
that attempts a write first copies the SQLite file into a temporary directory.
The original fixture must remain byte-identical and must never leave a
`-journal`, `-wal`, or `-shm` sidecar.

No migration behavior is claimed by this candidate. Acceptance only confirms
that the historical bytes, provenance, inventory, synthetic content, and
read-only behavior form a trustworthy test input for the next A0.1a step.
