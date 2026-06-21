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
- `inquiry_created` is emitted for contradictions only; it is not an action and
  does not resolve itself automatically.
- `experience_recorded` is emitted by deterministic ledger aggregation. The
  first v0.9 detector records contrasted activity hours instead of raw sample
  frequency.
- An experience may create an `ExperienceProposal`, but the proposal is still
  review work only and does not execute changes.
- `state_changed` is emitted by deterministic aggregation over active beliefs.
  v0.10 records `system.pressure` from activity and resource-pressure beliefs.
- `repo.commits_per_day` is structural material fed in via `observe-repo`: a
  count measured off-device (the membrane), never git contents. It reuses
  `observation_created` + `evidence_recorded` (no new types) and drives a binary
  `repo.activity` belief (`active`/`quiet`). The `observation_created` payload
  carries `measured_on` provenance. A missing measurement records nothing (the
  belief ages); only a real run reports `quiet`. Absence of a run is not `quiet`.
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
