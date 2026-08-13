# Golden Ledger v1
> Status: CANDIDATE — PENDING HUMAN REVIEW

## Purpose

This fixture is a synthetic, privacy-free candidate for independently checking
GENUS event integrity, seal continuity, replay projections, deterministic belief
read models, a governed rule lifecycle, and an historical Anchor-v1 boundary.

## Artifact Inventory

- `events.jsonl` is the canonical 42-event history.
- `oracle.json` contains manually derived projection and read-model expectations.
- `manifest.json` binds the corpus, Oracle, Anchor, and digest set.
- `import_receipt.json` is the static expected import receipt.
- `anchor_v1.json` binds the historical head at event 41.
- `ORACLE_REVIEW.md` records the still-pending human review.

## Corpus Design

The corpus uses fixed synthetic identifiers, values, sources, and timestamps. It
covers claim-coherent independent support and counterevidence, five linked
activity observations and evidence records, an `ActivityDailyRhythm` experience,
the current governed `RuleProposal` review and activation path, all twelve replay
targets, terminal Proposal and Inquiry lifecycles, supported and contested
read-time belief cases, and a persisted superseded-belief lifecycle.

## Legacy Prefix and Seal Epoch

Events 1 through 5 form the nonempty unsealed legacy prefix. Event 6 is the sole
`ledger_epoch_opened` marker and binds that prefix through its genesis digest.
Events 6 through 42 carry a continuous `sha256-chain-v1` seal chain; the
manifest's sealed-tail count excludes the epoch marker as required by contract.

## Oracle Independence

Projection columns, sort keys, rows, lifecycle effects, timestamps, and read-time
belief expectations were manually derived from the accepted contracts and the
approved read-only projector sources. Runtime replay output was not used as the
authority for these expectations and is applied only as a verification step.

## Canonicalization and Digests

JSONL, JSON files, projection rows, semantic event-stream records, Anchor bytes,
and the bundle each use their separately contracted serialization domains. The
literal JSONL includes a precomposed non-ASCII source so NFC, UTF-8, ASCII-escaped
semantic-stream, and ASCII-escaped Oracle domains are exercised in practice.

## Import Receipt

`import_receipt.json` is immutable expected data. A test may independently build
an in-memory actual receipt from source bytes and a temporary database, but it
must not rewrite or derive authority from the static receipt.

## Anchor v1 Boundary

`anchor_v1.json` binds event 41 at 02:26:00 UTC and was created at 02:26:30 UTC,
while event 42 at 02:27:00 UTC is a deliberately later sealed tail event. This
proves that Anchor-v1 verification accepts a valid historical head without
requiring it to be the current fixture head.

## Human Review

The candidate remains unapproved until Ronny separately completes corpus/privacy
review and Oracle review. Passing automated checks does not alter its status.

## Change Procedure

Any event, expected row, field set, sort key, canonical byte change, or lifecycle
change requires intentional regeneration of all affected seals and digests and a
renewed human review. Old accepted fixture versions remain immutable and later
eras are additive.

## Non-Goals

This candidate does not contain product data, a historical SQLite migration
fixture, a signing key, a signature, production state, or authority to modify
runtime, schema, replay, sealing, Anchor, deployment, or CI behavior.
