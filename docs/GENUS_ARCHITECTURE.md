# GENUS Architecture

GENUS is a ledger-first epistemic system. It stores what happened, derives what
it currently believes, and keeps every important state change replayable.

## Core Principles

- **Ledger-first:** `event_log` is the source of truth. It is append-only and
  ordered.
- **Sealed epochs:** After `ledger_epoch_opened`, new events carry a local
  `prev_seal`/`seal` chain. This detects non-resealed tampering, but external
  anchoring is required for adaptive local attackers.
- **External witnesses:** Offline anchor artifacts can witness a specific seal
  head for a specific `core_id` without writing a new ledger event.
- **Projection-only state:** Tables such as `belief_projection`,
  `state_projection`, `experience_log`, `proposal_log`, `inquiry_log`, and
  `governance_log`, `operation_log`, and `rule_projection` are derived views. They may be
  cleared and rebuilt by replay.
- **Deterministic first:** current processing is synchronous and ordered.
  Parallel workers are out of scope until replay and idempotency rules are
  explicit.
- **No magic knowledge:** Confidence is calculated at read time from
  time-weighted supporting and contradicting evidence. A language output or
  external answer is never knowledge by itself.
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
- **Update is not trust:** A code change or deploy is a proposal about GENUS,
  not a trusted change. Trust is earned only after verification and observed
  runtime evidence.

## Layer Model

```text
Observation -> Evidence -> Rules -> Beliefs -> State -> Governance
                    ^             \-> Contradictions -> Proposals/Inquiries
                    |-> Active Rules -> Expectation Inquiries
                     \-> Experience -> RuleProposal -> Human -> Active Rule
Operation Checks -> Operation Evidence -> Network Belief -> Governed Recovery
       \______________________________________________________________/
                              Event Ledger
```

Every layer consumes events and writes new events. Projections are updated from
those events so the current state can always be reconstructed.

## Change Trust

GENUS applies its own epistemic discipline to GENUS itself. A new version is
not trusted at merge time. It starts as a proposal about the system.

Verification gates provide regression evidence:

- tests are green
- `genus replay` matches current projections
- `genus integrity check` is clean
- `genus ledger verify` is clean when sealing is active
- `genus doctor` reports the expected operating state

These gates prove that existing history and contracts survived the change. They
do not, by themselves, prove that new behavior is mature. New behavior earns
trust the same way a belief does: by collecting repeated supporting evidence in
real operation. A single green deploy is supporting evidence; stable runtime,
fresh anchors, growing event counts, quiet logs, and repeated clean status
reports increase confidence.

Operationally:

- no change is trusted immediately
- every change must pass the deterministic gate before deploy
- every deployed change must be observed in runtime before it is treated as
  mature
- public witnesses prove only what they actually witness, never more

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
  review, rule activation, and operation recovery, writes governance audit events, and projects
  `governance_decision` rows.
- `operation.py` records self-operation checks and recovery attempts, projects
  `operation_log`, and derives the `system.network` belief from network checks.
- `maturation.py` turns recorded experiences into `RuleProposal` rows and
  activates accepted rule proposals through a second governed human act.
- `inquiries.py` coordinates `inquiry_created` and `inquiry_resolved` events
  with `inquiry_log` rows.
- `ledger.py` stores and reads immutable events.
- `sealing.py` opens a local sealing epoch, computes event seals, verifies the
  chain, and exposes the current ledger head for future external anchors.
- `anchor.py` exports and verifies offline JSON anchors for a sealed ledger
  head. Anchor creation is read-only and has no replay effect.
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

v1.1 adds local Ledger Sealing. A `ledger_epoch_opened` event pins the legacy
prefix with a genesis digest, and subsequent events carry `prev_seal` and
`seal`. Integrity verifies the chain, while `genus ledger head` exports the
head for later external anchoring.

v1.2 adds external Ledger Anchors as offline JSON artifacts. An anchor records
`core_id`, `head_event_id`, `head_created_at`, and the current seal head without
emitting an event. It protects only the prefix up to that head; events after the
anchor require a later anchor to be externally witnessed.

v1.3 adds Self-Operation Evidence. The Pi can record deterministic checks about
its own operating condition, starting with `network.gateway`. Those checks are
normal events and can create or update the `system.network` belief. The current
operation view is rebuildable in `operation_log`.

v1.4 adds the first Self-Healing Governance. A systemd timer outside GENUS may
restart the network stack or reboot the Pi, but only after GENUS records a
governed `operation.recovery` decision. The operating system performs the
action; GENUS records the reason, the allowed/blocked decision, and the result.

## Document Family

- `GENUS_GESAMTBILD.md` synthesizes the whole project direction.
- `GENUS_ROADMAP.md` defines the build order and next-step discipline.
- `GENUS_GRUNDAUSBILDUNG.md` maps local sensors to epistemic training forms.
- `GENUS_SENSOR_PRINCIPLE.md` defines what sensors may and may not do.
- `GENUS_PHYSIK.md`, `GENUS_ANTIZIPATION.md`, and
  `GENUS_VISUAL_THINKING.md` preserve later-stage concepts without pulling
  them into the current core.
- `parked/` holds non-canonical sketches. Nothing there is build input until
  promoted into a canonical document.

## Growth Rule

New capabilities must answer these questions before being added:

- What event records the input or transition?
- Is the current state rebuildable from `event_log`?
- Does replay leave `event_log` unchanged?
- Is confidence calculated rather than stored?
- Does the change avoid LLM, web, worker, and HTTP dependencies unless a later
  version explicitly permits them?
- What runtime evidence will show that the new behavior is actually working?
