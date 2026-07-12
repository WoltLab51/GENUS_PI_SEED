# GENUS Event Contract

All events are stored in `event_log` with a non-empty `event_type`, valid JSON
`payload`, and append-only ordering. Events are the durable record; projections
are rebuildable.

External ledger anchors are JSON artifacts, not events. They never appear in
`event_log` and have no replay effect.

## Event Types

| Event type | Required payload keys | Producer | Replay effect |
| --- | --- | --- | --- |
| `observation_created` | `source`, `raw_value`, `unit` | Sensor/CLI | None directly; may include raw sensor metadata |
| `evidence_recorded` | `observation_id`, `metric_key`, `metric_value` | Synchronous reactor | None directly |
| `belief_created` | `belief_id`, `claim_key`, `claim_value`, `derivation`, `supporting_events` | Rules | Insert active belief |
| `belief_confirmed` | `belief_id`, `new_supporting_event` | Rules | Add supporting event |
| `belief_weakened` | `belief_id`, `contradicting_event` | Rules | Add contradicting event |
| `belief_superseded` | `old_belief_id`, `new_belief_id`, `claim_key`, `claim_value`, `derivation`, `supporting_events`, `reason` | Rules | Insert new belief and supersede old one |
| `contradiction_detected` | `belief_id`, `reason` | Rules | None directly |
| `proposal_created` | `proposal_id`, `proposal_type`, `claim_key`, `claim_value`, `source_belief`, `source_event`, `payload`, `reason` | Proposals | Insert proposal row |
| `proposal_reviewed` | `proposal_id`, `decision`, `note` | Human via CLI | Mark proposal accepted/rejected |
| `experience_recorded` | `experience_id`, `experience_key`, `experience_type`, `subject_key`, `pattern`, `supporting_events`, `derivation`, `summary` | Experience | Insert experience row |
| `experience_recharacterized` | `experience_id`, `experience_key`, `pattern`, `supporting_events`, `summary`, `reason` | Experience | Update the experience row in place |
| `state_changed` | `state_id`, `state_key`, `state_value`, `previous_state_id`, `derivation`, `supporting_beliefs`, `components`, `reason` | State | Insert active state row and supersede previous state |
| `rule_proposed` | `rule_key`, `rule_type`, `subject_key`, `spec`, `source_experience`, `derivation`, `summary` | Maturation | Audit only; source event for RuleProposal |
| `rule_activated` | `rule_id`, `rule_key`, `rule_type`, `subject_key`, `spec`, `source_proposal`, `derivation` | Maturation | Insert active rule row |
| `ledger_epoch_opened` | `algo`, `genesis_digest`, `prefix_max_id`, `prefix_count` | Ledger sealing | Starts sealed epoch; no projection effect |
| `constraint_checked` | `decision_id`, `constraint_key`, `action`, `target_type`, `target_id`, `result`, `reason` | Governance | Audit only |
| `policy_evaluated` | `decision_id`, `policy_key`, `action`, `target_type`, `target_id`, `result`, `reason` | Governance | Audit only |
| `governance_decision` | `decision_id`, `action`, `target_type`, `target_id`, `decision`, `override`, `policy_results`, `reason` | Governance | Insert governance decision row |
| `operation_check_recorded` | `operation_id`, `check_key`, `status`, `target`, `payload`, `derivation` | Operation | Insert operation check row |
| `operation_recovery_attempted` | `recovery_id`, `check_key`, `action`, `target`, `failures`, `reason`, `derivation` | Operation | Insert operation recovery row |
| `operation_recovery_result` | `recovery_id`, `result`, `action`, `target`, `detail`, `derivation` | Operation | Update operation recovery row |
| `inquiry_created` | `inquiry_id`, `inquiry_type`, `claim_key`, `source_belief`, `source_event`, `question_key`, `payload`, `state` | Inquiries | Insert inquiry row |
| `inquiry_resolved` | `inquiry_id`, `answer` | Human via CLI | Mark inquiry resolved |
| `inquiries_reconciled` | `inquiry_ids`, `answer` | Deterministic maintenance | Resolve a mechanically proven batch of false or duplicate inquiries |
| `forecast_made` | `metric_key`, `predicted_value`, `method`, `support` | Learning engine (24/7 loop) | None directly; raw fact, read by the learning curve |
| `forecast_scored` | `forecast_event`, `metric_key`, `predicted_value`, `actual_value`, `error` | Learning engine | None directly; the accumulating error is the learning curve |

## Invariants

- `event_log` must never be updated or deleted.
- `event_log.prev_seal` and `event_log.seal` are append-time fields. Legacy
  rows may be null; sealed rows must verify against the local chain.
- `replay()` may clear `belief_projection`, `state_projection`,
  `experience_log`, `proposal_log`, `inquiry_log`, `governance_log`, and
  `operation_log`, and `rule_projection`, but never changes `event_log`.
- `belief_projection.derivation` is required for every belief event that creates
  a belief.
- `belief_projection` has no `confidence` column.
- Confidence is calculated at read time from the `created_at` timestamps of
  supporting and contradicting evidence events. It has no replay side effect.
- The confidence half-life is **learned per belief** from its own flip history:
  `H = observation span / number of flips` (the mean time between belief changes),
  via `projection.learned_halflife`. A belief that never flips earns a long
  half-life; one that flips often gets a short one. The seed
  `HALFLIFE_SECONDS_BY_CLAIM_KEY` table is only a fallback for beliefs without
  enough tenure. This is read-time and replay-safe.
- `belief_projection.supporting_events` and `contradicting_events` are bounded to
  a recent window. The full evidence history always remains in `event_log`; the
  projection keeps only the most recent ids. The bound is confidence-negligible
  (evidence decays as `2^(-age/H)`, so older ids carry ~0) and replay re-applies
  it deterministically, so the projection stays rebuildable. This keeps the
  evidence-time lookup far under SQLite's parameter limit and makes each confirm
  O(window) rather than O(n).
- `experience_log.derivation` is required and `experience_log` has no
  `confidence` column.
- `state_projection.derivation` is required and `state_projection` has no
  `confidence` column.
- `rule_projection.derivation` is required and `rule_projection` has no
  `confidence` column.
- `operation_log.derivation` is required and `operation_log` has no
  `confidence` column.
- Proposal creation is event-backed: `proposal_created` is written before
  `proposal_log` is projected.
- `proposal_created` is emitted for first sustained high and high-to-normal
  contradiction only; it is not emitted for `belief_confirmed`.
- `inquiry_created` is emitted for contradictions and for self-reflection
  surprises (a `StabilityInquiry`); it is not an action and does not resolve
  itself automatically.
- `StabilityInquiry` closes the expect-then-be-surprised loop: when a belief the
  `BeliefStability` experience characterized as `stable` later supersedes, the
  experience scan raises one inquiry per such flip (deduped by `source_event`).
  A volatile belief flipping is expected and raises nothing. Like the
  contradiction inquiry it is raised directly (ungoverned), and replay re-applies
  the `inquiry_created` event rather than re-scanning.
- `experience_recorded` is emitted by deterministic ledger aggregation. The
  first v0.9 detector records contrasted activity hours instead of raw sample
  frequency. Detectors are a registry of pure functions (`conn -> candidates`);
  cognition grows by registering one, not by rewriting the scan.
- `BeliefStability` is the first experience whose subject is GENUS's own cognition
  rather than a sensor metric: per `claim_key` it measures `flip_rate =
  supersessions / (confirmations + supersessions)` from the belief lifecycle and
  classifies the belief stable/volatile relative to the core's own population of
  flip-rates. It withholds until a belief has enough lifecycle history and the
  population has spread (premise of meaning). It is recorded knowledge only and
  raises no proposal. Determinism is preserved by freezing the measure in the
  `experience_recorded` event; replay re-applies it and does not re-scan.
- An experience is re-characterized in place when its characterization changes
  (a belief that was `stable` later reads `volatile`): the scan emits
  `experience_recharacterized`, which updates the existing row's `pattern`,
  `supporting_events`, and `summary`. The `experience_key` stays unique (one row);
  the full history of characterizations remains in `event_log`. Experiences
  without a characterization (the activity rhythm) are recorded once and never
  re-characterized. Replay re-applies the update deterministically.
- An experience may create an `ExperienceProposal`, but the proposal is still
  review work only and does not execute changes.
- `state_changed` is emitted by deterministic aggregation over active beliefs.
  v0.10 records `system.pressure` from activity and resource-pressure beliefs.
- A metric may feed more than one belief. `system.disk` evidence drives both the
  threshold belief `system.disk` and the trend belief `disk.trend`
  (`rising`/`stable`/`falling`), the latter judged over a window of recent
  evidence. Its sensitivity is self-calibrated to the core's own scatter (no
  imposed epsilon). No new event types — both use the `belief_*` events and
  replay identically.
- `system.thermal` (`anomalous`/`normal`) is a cross-metric belief: temperature
  read against CPU on each temperature observation. `anomalous` means temperature
  is high while CPU is not. Both "high" thresholds are the core's own percentiles
  (no preset), and it withholds until both metrics have enough history **and** the
  CPU actually varies — an idle CPU with no spread has no high regime to decouple
  from, so a verdict would be vacuous (the "withhold when the premise of meaning
  is missing" principle). No new event types; the decision is recorded in
  `belief_*` events, so replay is stable.
- `repo.commits_per_day` and `repo.lines_changed_per_day` are structural material
  fed in via `observe-repo`: counts measured off-device (the membrane), never git
  contents. They reuse `observation_created` + `evidence_recorded` (no new types)
  and drive binary beliefs `repo.activity` (`active`/`quiet`) and `repo.churn`
  (`heavy`/`light`). `repo.churn` has **no imposed threshold**: heavy is judged
  against this core's own lived churn distribution (a read-time percentile over
  prior evidence — causal, so the belief stays replay-stable), and it withholds
  until there is enough history. The `observation_created` payload carries
  `measured_on` provenance. A missing measurement records nothing (the belief
  ages); only a real run reports the quiet/light state. Absence is not quiet.
- `weather.temp_outside` is the first **external** material: the outside
  temperature fetched by the membrane from a public, no-auth source. HTTP lives
  only in the membrane — `genus/` never reaches the network. It reuses
  `observation_created` + `evidence_recorded` (no new types) and drives the trend
  belief `weather.trend` (`rising`/`stable`/`falling`), self-calibrated to the
  core's own scatter like `disk.trend`. The `observation_created` payload carries
  the `provider` (source) but **never the location** — latitude/longitude stay in
  the membrane configuration and never enter the ledger. A failed fetch records
  nothing (the belief ages); absence is not a reading.
- Governance checks write all `constraint_checked` events, then all
  `policy_evaluated` events, then exactly one `governance_decision` event.
- `constraint_checked` and `policy_evaluated` are audit-only. Replay projects
  only `governance_decision` into `governance_log`.
- Kernel constraints are never overrideable. v0.11 requires an existing pending
  proposal and a valid review decision before a proposal review can continue.
- Policies are overrideable only when the CLI passes `--override`; the override
  is recorded in `governance_decision`.
- A blocked governance decision is still durable and committed. It leaves the
  target proposal pending.
- Operation checks record self-operation evidence. `system.network` is a normal
  rebuildable belief derived from `operation_check_recorded` events.
- The `clock.sync` check reuses `operation_check_recorded` (no new event type).
  `system.clock` is a normal rebuildable belief (`synchronized`/`unsynchronized`).
  A fresh drop to `unsynchronized` raises one review-only `OperationProposal`; a
  confirmed `unsynchronized` check does not. The clock check has no recovery
  action.
- Operation recovery is governed before execution. `restart_network` is allowed
  after a failed gateway check; `reboot` is blocked until the configured
  repeated-failure threshold is reached and no reboot recovery attempt is inside
  the governance cooldown window.
- Operation recovery results are explicit events. Replay rebuilds the recovery
  attempt and then applies the terminal result to `operation_log`.
- `rule_proposed` is emitted by deterministic maturation over recorded
  experiences. It becomes the `source_event` of its `RuleProposal`.
- Accepting a `RuleProposal` activates nothing. Rule activation is a separate,
  governed, event-backed human act.
- `rule_activated` requires an accepted `RuleProposal` and is terminal per
  `rule_key`; a rule key may be activated at most once.
- Active v1.0 rules may only create `ExpectationInquiry` records. They never
  change beliefs and never execute actions.
- Replay applies `rule_activated` events into `rule_projection`; it does not
  rescan experiences and does not re-evaluate active rule effects.
- `ledger_epoch_opened` pins a genesis digest over the unsealed legacy prefix.
  Replay ignores it as a projection event, but Integrity verifies it.
- Local sealing detects accidental corruption and lazy tampering.
- A `genus-ledger-anchor-v1` artifact witnesses one `core_id`, one
  `head_event_id`, the head event timestamp, and the seal at that head.
- Anchor creation is read-only. It must not write `event_log`, update
  projections, or call external services.
- An anchor protects only the prefix up to its `head_event_id`. Adaptive
  re-sealing or truncation after that point remains unproven until a later
  anchor exists.
- `proposal_reviewed` and `inquiry_resolved` are terminal: at most one review
  per proposal and one resolution per inquiry, enforced before the event is
  written.
- Inquiry resolution is deliberately ungoverned in v0.11.
- Query commands are read-only. They do not emit events and do not rebuild
  projections.
