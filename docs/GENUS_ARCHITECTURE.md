# GENUS Architecture

GENUS is a ledger-first epistemic system. It stores what happened, derives what
it currently believes, and keeps every important state change replayable.

## Core Principles

- **Ledger-first:** `event_log` is the source of truth. It is append-only and
  ordered.
- **Projection-only state:** Tables such as `belief_projection` and
  `proposal_log` are derived views. They may be cleared and rebuilt by replay.
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
Observation -> Evidence -> Rules -> Beliefs -> Contradictions -> Proposals
       \______________________________________________________________/
                              Event Ledger
```

Every layer consumes events and writes new events. Projections are updated from
those events so the current state can always be reconstructed.

## Reactor Direction

Reactors decide when a transition is needed. Domain modules coordinate how their
own events and projections are written.

- `rules.py` detects CPU threshold conditions and belief transitions.
- `reactors.py` runs synchronous CPU and memory observation-to-evidence-to-rules cycles.
- `proposals.py` coordinates `proposal_created` events and `proposal_log` rows.
- `inquiries.py` coordinates `inquiry_created` events and `inquiry_log` rows.
- `ledger.py` stores and reads immutable events.
- `event_router.py` replays events into rebuildable projections.
- `integrity.py` checks schema, event contracts, and replay stability.

## Growth Rule

New capabilities must answer these questions before being added:

- What event records the input or transition?
- Is the current state rebuildable from `event_log`?
- Does replay leave `event_log` unchanged?
- Is confidence calculated rather than stored?
- Does the change avoid LLM, web, worker, and HTTP dependencies unless a later
  version explicitly permits them?
