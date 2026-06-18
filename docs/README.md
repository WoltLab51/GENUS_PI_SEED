# GENUS Documentation Index

This directory has three shelves. Only the first shelf is build authority.

## 1. Canonical Contracts

These files define what the current system is allowed to do:

- `GENUS_ARCHITECTURE.md` - core principles, layer model, module direction.
- `GENUS_EVENT_CONTRACT.md` - event types and required payload keys.
- `GENUS_ROADMAP.md` - the next build step and growth discipline.
- `GENUS_LEDGER_AUDIT.md` - integrity boundary, sealing, anchors, threat model.
- `genus_core_map.html` - visual maturity map for the current architecture.

When code and docs disagree, fix the canonical document or the code before
building further.

## 2. Supporting Doctrine

These files explain why the roadmap is shaped the way it is. They are stable
guidance, but not standalone implementation specs:

- `GENUS_GESAMTBILD.md` - synthesis and project navigation.
- `GENUS_SENSOR_PRINCIPLE.md` - what sensors may and may not do.
- `GENUS_GRUNDAUSBILDUNG.md` - which local sensors train which epistemic forms.

## 3. Future Concepts

These files preserve later-stage ideas. They are useful, but they are not build
input until a roadmap step explicitly promotes a concrete part of them:

- `GENUS_PHYSIK.md` - map of epistemic operation families.
- `GENUS_ANTIZIPATION.md` - anticipation and prediction as a later phase.
- `GENUS_VISUAL_THINKING.md` - visual thinking for the model era.
- `parked/` - loose ideas, deliberately non-canonical.
- `archive/` - historical prompts and specs, never current authority.

## Maintenance Rule

Do not create a new concept document between two builds. Update the smallest
existing document that owns the fact:

- Current invariant changed? Update architecture or event contract.
- Build order changed? Update roadmap.
- Integrity boundary changed? Update ledger audit.
- A thought is interesting but not actionable yet? Put it in `parked/`.
- A spec has been implemented and superseded? Move it to `archive/`.
