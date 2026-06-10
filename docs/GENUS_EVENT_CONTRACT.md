# GENUS Event Contract

All events are stored in `event_log` with a non-empty `event_type`, valid JSON
`payload`, and append-only ordering. Events are the durable record; projections
are rebuildable.

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
| `inquiry_created` | `inquiry_id`, `inquiry_type`, `claim_key`, `source_belief`, `source_event`, `question_key`, `payload`, `state` | Inquiries | Insert inquiry row |
| `inquiry_resolved` | `inquiry_id`, `answer` | Human via CLI | Mark inquiry resolved |

## Invariants

- `event_log` must never be updated or deleted.
- `replay()` may clear `belief_projection`, `proposal_log`, and `inquiry_log`,
  but never changes `event_log`.
- `belief_projection.derivation` is required for every belief event that creates
  a belief.
- `belief_projection` has no `confidence` column.
- Proposal creation is event-backed: `proposal_created` is written before
  `proposal_log` is projected.
- `proposal_created` is emitted for first sustained high and high-to-normal
  contradiction only; it is not emitted for `belief_confirmed`.
- `inquiry_created` is emitted for contradictions only; it is not an action and
  does not resolve itself automatically.
- `proposal_reviewed` and `inquiry_resolved` are terminal: at most one review
  per proposal and one resolution per inquiry, enforced before the event is
  written.
- Query commands are read-only. They do not emit events and do not rebuild
  projections.
