# A0.2 Historical SQLite Fixture Human Review

Status: **ACCEPTED**

Reviewer: Ronny

Review date: 2026-08-14

Decision basis: Ronny independently verified the historical source commit and
schema inventory and accepted the fixture based on the bound hashes and reported
test evidence. The local candidate files were not independently byte-opened by
the reviewer; that limitation is part of the recorded decision.

## 1. Historical provenance

- [ ] The selected commit is a real earlier GENUS revision and the documented date and message are correct.
- [ ] `schema.sql` is byte-identical to the selected commit and its SHA-256 is correct.
- [ ] The historical source is old enough to exercise meaningful schema detection.

## 2. Synthetic content and privacy

- [ ] All seven events and the single projection row are understandable and fully synthetic.
- [ ] The fixture contains no personal, productive, host, path, chat, token, or device data.
- [ ] The legacy prefix, epoch, sealed tail, and projection row are internally coherent.

## 3. Schema and inventory

- [ ] Tables and columns match the historical schema.
- [ ] Explicit indexes and append-only triggers match the historical schema.
- [ ] The schema fingerprint is independently reproducible.
- [ ] The documented differences from the current schema are accurate.

## 4. Byte and event bindings

- [ ] The SQLite, schema, and JSONL SHA-256 values match the actual files.
- [ ] The read-only SQLite export and `events.jsonl` produce the same semantic event-stream digest.
- [ ] The legacy genesis digest and all epoch/tail seals verify independently.

## 5. Read-only safety

- [ ] `genus.db.connect_readonly` inspects the original without migration or byte changes.
- [ ] No journal, WAL, or SHM sidecar remains beside the original artifact.
- [ ] Every attempted write, trigger check, or rebuild is performed only on a temporary copy or new temporary database.
- [ ] The original SQLite artifact remains byte-identical after the complete test run.

## 6. Scope and final decision

- [ ] No runtime, current schema, migration, or product-data change is part of this candidate.
- [ ] The fixture is suitable as the historical input for the later A0.1a read-only schema detector.
- [x] Accept candidate
- [ ] Reject candidate
- [ ] Request changes
