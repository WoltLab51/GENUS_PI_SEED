# GENUS Architecture

GENUS is a ledger-first epistemic system. It stores what happened, derives what
it currently believes, and keeps every important state change replayable.

## Core Principles

- **Ledger-first:** `event_log` is the source of truth. It is append-only and
  ordered.
- **Projection-only state:** Tables such as `belief_projection`,
  `proposal_log`, and `inquiry_log` are derived views. They may be cleared and
  rebuilt by replay.
- **Deterministic first:** v0.x processing is synchronous and ordered. Parallel
  workers are out of scope until replay and idempotency rules are explicit.
- **No magic knowledge:** Confidence is calculated at read time. A language
  output or external answer is never knowledge by itself.
- **Belief is not truth:** Beliefs have lifecycle states such as `active` and
  `superseded`. They are never stored as `true`.
- **Proposal is not action:** Proposals create attention and review work. They
  do not execute changes.
- **Inquiry is not action:** Inquiries name open uncertainty. They ask what
  should be clarified, but do not execute changes.

## Layer Model

```text
Observation -> Evidence -> Rules -> Beliefs -> Contradictions -> Proposals/Inquiries
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
- `proposals.py` coordinates `proposal_created` events and `proposal_log` rows.
- `inquiries.py` coordinates `inquiry_created` events and `inquiry_log` rows.
- `ledger.py` stores and reads immutable events.
- `event_router.py` replays events into rebuildable projections.
- `integrity.py` checks schema, event contracts, and replay stability.

Supported local metrics in v0.6 are CPU percent, memory percent, disk percent,
activity, and temperature. Disk and temperature are threshold/revision training
in v0.6; activity is binary and changes belief immediately.

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
