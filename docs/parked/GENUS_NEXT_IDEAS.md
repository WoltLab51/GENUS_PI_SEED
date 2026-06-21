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

**First atom already exists (2026-06-21):** the `repo.commits_per_day` membrane
runs on the X1 (a second machine) and feeds a provenance-stamped observation
(`measured_on`) into the Pi core. That is the inter-core sensor principle in the
small — a foreign machine is an eye, its contribution is an observation, not
truth. The X1 is still only a sensor, not its own core. Full federation (the X1
gets its own ledger and two cores exchange) can build the inter-core contract on
this provenance pattern. The binding rule already holds: write nothing that
assumes a single database.

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

## 8. Self-Calibrated Confidence Half-Lives (flip-rate)

**Idea:** Replace the hardcoded `HALFLIFE_SECONDS_BY_CLAIM_KEY` constants with a
half-life each belief derives from its own history: decay as fast as the belief
actually changes. Concretely, set the half-life from the belief's own
supersession (flip) rate — a belief that flips often forgets old evidence
quickly, a stable one keeps it longer.

**Why it matters:** The half-lives are the last imposed magnitude in the system
(`confidence.py` already says `# TODO: aus Ledger-Daten kalibrieren`). A
cadence-based half-life ("decay relative to how often you observe") was
considered and **rejected**: it conflates observation frequency with how fast
the truth changes. Flip-rate is the decided principle (2026-06-21), to stay
read-time and replay-stable like the churn / trend / thermal calibrations.

**Promote when:** Beliefs have accumulated enough flip history on the Pi for a
stable rate estimate (needs burn-in). Pairs naturally with extending Experience
to the new beliefs — both wait on lived material.

## 9. Architecture Hardening Backlog (audit 2026-06-21, v1.6.0)

From the v1.6.0 architecture audit, ordered by urgency.

- **Bound `supporting_events` per belief (Tier 0 — promote now).** A belief
  confirmed every tick (e.g. `system.activity`) accumulates every supporting
  event id forever. This makes confidence O(n) per read and confirm O(n) per
  write, and — critically — `evidence_created_at_times` builds `WHERE id IN (...)`
  with one host parameter per event, so the query layer hits SQLite's parameter
  ceiling (~32k) within months and raises "too many SQL variables". Fix: keep
  only evidence within a window / N half-lives (older terms decay to ~0 anyway)
  and track the displayed count separately. Read-time, replay-safe.
- **`busy_timeout` + WAL (cheap).** `db.connect` sets neither; observe-all,
  state refresh, clock-check, the root network watchdog, and the X1 membrane all
  write the same SQLite from separate processes, so overlapping writes can raise
  "database is locked" with no retry wait.
- **Index `metric_key` (cheap).** Hot evidence queries filter
  `json_extract(payload,'$.metric_key')`, which is unindexed; scans grow with the
  ledger. A generated/extracted indexed column fixes it.
- **Bound the self-calibration scan.** `_calibrated_threshold` (used by
  `system.thermal`) scans all prior evidence for a metric every tick, unbounded.
  Window it to recent N — also more honest (the current distribution).
- **Snapshots / checkpoints for replay & integrity.** Replay and
  `integrity.check` are O(n) over the whole ledger and run on every doctor,
  deploy, and CI; the live ledger grows ~12k events/day. Pairs with item 1.
- **Generalize the learning layer + experience/rule lifecycle.** Experience and
  Maturation are hard-wired to `system.activity` hour-of-day; the new beliefs are
  never learned from, and experiences/rules never expire. The eye->mind
  deepening. Promote when there are weeks of burn-in for day-of-week and
  cross-belief patterns.
- **A performance/scale test as a CI guard.** Tests use tiny ledgers, so O(n)
  and unbounded-growth issues stay invisible until they hurt.

## 10. GENUS Observes Its Own Development

**Idea:** Let GENUS hold its own open items — audit findings, decisions, debts —
as its own beliefs/proposals/inquiries, instead of relying on docs plus
discipline to keep them from being lost. The project governs itself with its own
machinery: a finding becomes an inquiry, a decision a governed act, a fix a
proposal that closes.

**Why it matters:** It is the same self-reflection family the project keeps
reaching for (self-observation, metacognition, self-calibration). It also turns
"did this finding actually flow in?" into a checkable belief rather than a hope.

**Promote when:** There is a self-observation / ledger-introspection capability
to build on (pairs with item 8), and after the deterministic core's scaling
backlog (item 9) is under control.
