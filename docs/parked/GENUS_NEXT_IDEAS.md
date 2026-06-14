# GENUS Next Ideas

Status: parked, non-canonical.

This file captures important ideas that are not build input yet. They become
actionable only when a roadmap step promotes the minimum necessary part into a
canonical document.

## 1. Backup / Availability

**Idea:** Add a small backup command for Pi operation.

Possible shape:

- `genus backup create --out PATH`
- copy the SQLite DB
- include the newest anchor artifact
- include a manifest with `core_id`, DB hash, anchor head, created time, and
  GENUS version
- later: `genus backup verify PATH`

**Why it matters:** Sealing and anchors help prove that history was not changed.
They do not help if the SD card dies. Anchors stored on the same Pi are not
availability.

**Promote when:** The Pi starts running continuously or before data becomes
valuable enough that losing it would hurt.

## 2. Private vs. Structural Event Layers

**Idea:** Decide whether future events need two layers:

- structural/open metadata that remains visible and replayable
- encrypted/private payload content for personal or sensitive material

**Why it matters:** Append-only storage makes privacy decisions hard to retrofit.
The system should not accidentally store personal raw material forever in plain
JSON once conversation, family, or character domains begin.

**Promote when:** GENUS is about to ingest personal text, family context, or
other sensitive user-provided content.

## 3. Crypto-Shredding

**Idea:** Preserve append-only history while allowing practical deletion by
encrypting sensitive payloads and later destroying keys.

**Why it matters:** Some domains require deletion. Deleting rows conflicts with
the ledger contract; deleting keys may satisfy the practical need while keeping
the event structure intact.

**Promote when:** Personal/private event layers become a concrete roadmap step.

## 4. First Model Slot: Memory From Sentence

**Idea:** When the Model Era begins, start with one narrow slot:
turn a user sentence into candidate memory evidence.

Possible measurement:

- 30 typical user sentences
- model output enters only as Evidence
- deterministic validation/sieve
- count how often useful candidates survive the sieve

**Why it matters:** The whole Model Era depends on whether model output can be
bounded without breaking GENUS' epistemic contract. This should be measured
before building larger language machinery.

**Promote when:** Roadmap reaches v2.0 Meaning Engine.

## 5. Federation / One Core Per Character

**Idea:** Use separate GENUS cores and databases for meaningfully separate
characters or trust domains.

**Why it matters:** A single governance bug should not bridge contexts that must
stay isolated, especially child-facing and adult-facing domains.

**Promote when:** Character systems, multi-user systems, or child/family
contexts become active work.

## 6. Verified Cache Risk

**Idea:** A human-confirmed model answer can still be false. If cached forever
as deterministic truth, one bad confirmation becomes durable.

Possible future mechanics:

- expiry
- revision lifecycle
- contradiction checks
- periodic re-validation

**Why it matters:** "Verified" must not quietly become "eternally true".

**Promote when:** Model output, verified cache, or remembered language facts are
introduced.

## 7. Anchor Cadence

**Idea:** Decide how often a running Pi should export external anchors.

Questions:

- maximum acceptable unanchored tail length
- anchor after every deploy?
- anchor every N minutes/hours?
- anchor before and after backups?
- later: `genus ledger anchor verify-all DIR`

**Why it matters:** v1.2 anchors prove only the prefix up to `head_event_id`.
Events after the last anchor remain local-only until the next anchor.

**Promote when:** Backup v1 or continuous Pi operation needs an operating
procedure.
