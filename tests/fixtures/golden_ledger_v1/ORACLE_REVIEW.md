# A0.2 Golden Ledger Oracle Review
> Status: CANDIDATE — PENDING HUMAN REVIEW
> Reviewer: Ronny
> Review date:
> Baseline commit:

## 1. Corpus and Privacy

- [ ] Confirm every value is synthetic and privacy-free.
- [ ] Confirm the corpus contains no product data, names, hostnames, local paths, secrets, or real system values.
- [ ] Confirm corpus construction, privacy review, and Oracle review are treated as separate human actions.

## 2. Event Contract

- [ ] Review every event type and payload against `docs/EVENT_CONTRACT.md`.
- [ ] Confirm event IDs are contiguous from 1 through 42 and timestamps are fixed.
- [ ] Confirm raw and projected event choices are intentional.
- [ ] Confirm Proposal 1 is terminally accepted and Inquiry 1 is terminally resolved.

## 3. Legacy Prefix and Genesis Digest

- [ ] Confirm events 1 through 5 are the complete unsealed legacy prefix.
- [ ] Recalculate `prefix_count = 5` and `prefix_max_id = 5`.
- [ ] Independently recalculate the prefix genesis digest.

## 4. Seal Epoch and Tail

- [ ] Confirm event 6 is the sole `ledger_epoch_opened` event.
- [ ] Confirm its `algo`, genesis digest, prefix count, and prefix maximum ID.
- [ ] Independently verify every `prev_seal` and `seal` from event 6 through event 42.
- [ ] Confirm the current head is event 42.

## 5. Projection Oracle

- [ ] Review the exact inventory of twelve projection targets.
- [ ] Trace every expected row and field to its source event and projector contract.
- [ ] Confirm JSON columns, SQLite types, timestamps, columns, and sort keys are normalized as contracted.
- [ ] Independently recalculate every projection digest and the projection-digest-set digest.

## 6. Belief Lifecycle and Read-Time Epistemics

- [ ] Confirm Belief 1 is persistently active with supporting events 1 and 2.
- [ ] Confirm Belief 2 is persistently active with support event 3 and contradicting events 4 and 5.
- [ ] Confirm Belief 3 is superseded by active Belief 4.
- [ ] Recalculate supported confidence as `2 / (2 + 0 + 1) = 0.667` at the fixed `as_of`.
- [ ] Recalculate contested confidence as `1 / (1 + 2 + 1) = 0.250` at the fixed `as_of`.
- [ ] Confirm `supported` and `contested` appear only as read-time epistemic states.

## 7. Canonicalization and Digests

- [ ] Confirm JSONL UTF-8, NFC, sorted compact keys, LF endings, and exactly one final LF.
- [ ] Independently recalculate fixture and semantic event-stream digests.
- [ ] Confirm Oracle, Manifest, Anchor, and bundle byte domains and cross-artifact equalities.
- [ ] Confirm provenance binds repository, baseline commit, governing documents, derivation, and roles only in `oracle.json`.

## 8. Anchor v1 and Negative Cases

- [ ] Confirm `anchor_v1.json` has exactly the twelve Anchor-v1 fields and no status field.
- [ ] Confirm historical head event 41 and the deliberately later event 42.
- [ ] Confirm the valid historical head is accepted for core `golden-ledger-v1`.
- [ ] Confirm wrong core ID, wrong head event ID, and wrong head seal are rejected.

## 9. Final Decision

- [ ] Accept candidate
- [ ] Reject candidate
- [ ] Request changes
