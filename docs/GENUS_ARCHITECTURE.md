# GENUS Architecture

GENUS is a ledger-first epistemic system. It stores what happened, derives what
it currently believes, and keeps every important state change replayable.

## Core Principles

- **Ledger-first:** `event_log` is the source of truth. It is append-only and
  ordered.
- **Projection-only state:** Tables such as `belief_projection`,
  `state_projection`, `experience_log`, `proposal_log`, `inquiry_log`, and
  `governance_log`, and `rule_projection` are derived views. They may be
  cleared and rebuilt by replay.
- **Deterministic first:** current processing is synchronous and ordered.
  Parallel workers are out of scope until replay and idempotency rules are
  explicit.
- **No magic knowledge:** Confidence is calculated at read time. A language
  output or external answer is never knowledge by itself.
- **Belief is not truth:** Beliefs have lifecycle states such as `active` and
  `superseded`. They are never stored as `true`.
- **Proposal is not action:** Proposals create attention and review work.
  Reviews are event-backed human acts, but they do not execute changes.
- **Inquiry is not action:** Inquiries name open uncertainty. They ask what
  should be clarified. Resolution is event-backed, but does not execute
  changes.
- **Policy is not decision:** Policies and constraints are evaluated as audit
  events. The durable outcome is a separate `governance_decision` event.
- **Review is not activation:** Accepting a `RuleProposal` documents human
  agreement. Activating the rule is a second governed act that changes future
  deterministic behavior.

## Layer Model

```text
Observation -> Evidence -> Rules -> Beliefs -> State -> Governance
                    ^             \-> Contradictions -> Proposals/Inquiries
                    |-> Active Rules -> Expectation Inquiries
                     \-> Experience -> RuleProposal -> Human -> Active Rule
       \______________________________________________________________/
                              Event Ledger
```

Every layer consumes events and writes new events. Projections are updated from
those events so the current state can always be reconstructed.

## Reactor Direction

Reactors decide when a transition is needed. Domain modules coordinate how their
own events and projections are written.

- `rules.py` detects threshold and binary belief-transition conditions for
  supported metrics.
- `reactors.py` runs synchronous observation-to-evidence-to-rules cycles.
- `proposals.py` coordinates `proposal_created` and `proposal_reviewed` events
  with `proposal_log` rows.
- `experience.py` scans the ledger for deterministic repeated patterns and
  coordinates `experience_recorded` events with `experience_log` rows.
- `state.py` derives deterministic state vectors from active beliefs and
  coordinates `state_changed` events with `state_projection` rows.
- `governance.py` evaluates kernel constraints and policies around proposal
  review and rule activation, writes governance audit events, and projects
  `governance_decision` rows.
- `maturation.py` turns recorded experiences into `RuleProposal` rows and
  activates accepted rule proposals through a second governed human act.
- `inquiries.py` coordinates `inquiry_created` and `inquiry_resolved` events
  with `inquiry_log` rows.
- `ledger.py` stores and reads immutable events.
- `event_router.py` replays events into rebuildable projections.
- `integrity.py` checks schema, event contracts, and replay stability.
- `query.py` reads projections and ledger events to explain state without
  writing events.

Supported local metrics in v0.6 are CPU percent, memory percent, disk percent,
activity, and temperature. Disk and temperature are threshold/revision training
in v0.6; activity is binary and changes belief immediately.

v0.9 adds the first Experience detector: contrasted `system.activity` hours are
recorded as an `ActivityDailyRhythm`. Experience records are projections from
`experience_recorded` events and may create review-only `ExperienceProposal`
rows.

v0.10 adds the first State vector: `system.pressure` is derived from active
activity and resource-pressure beliefs. State rows are projections from
`state_changed` events and are not truth rows.

v0.11 adds Governance v1 around proposal review. Kernel constraints block
invalid or non-pending review attempts and cannot be overridden. The first
policy, `policy:pressure_guard_v1`, blocks accepting proposals while
`system.pressure=elevated` unless the human passes `--override`. Audit events
remain in the ledger, while `governance_log` is rebuilt from
`governance_decision` events.

v1.0 adds Maturation v1. `ActivityDailyRhythm` experiences can propose
`activity_expectation_v1` rules. Accepted `RuleProposal` rows do not activate
anything by themselves; `genus rules activate` is a separate governed event
that writes `rule_activated` and rebuilds into `rule_projection`. In v1.0 an
active rule may only create an `ExpectationInquiry` when new activity evidence
deviates from the learned expectation.

## Document Family

- `GENUS_GESAMTBILD.md` synthesizes the whole project direction.
- `GENUS_ROADMAP.md` defines the build order and next-step discipline.
- `GENUS_GRUNDAUSBILDUNG.md` maps local sensors to epistemic training forms.
- `GENUS_SENSOR_PRINCIPLE.md` defines what sensors may and may not do.
- `GENUS_PHYSIK.md`, `GENUS_ANTIZIPATION.md`, and
  `GENUS_VISUAL_THINKING.md` preserve later-stage concepts without pulling
  them into the current core.

## Growth Rule

New capabilities must answer these questions before being added:

- What event records the input or transition?
- Is the current state rebuildable from `event_log`?
- Does replay leave `event_log` unchanged?
- Is confidence calculated rather than stored?
- Does the change avoid LLM, web, worker, and HTTP dependencies unless a later
  version explicitly permits them?
