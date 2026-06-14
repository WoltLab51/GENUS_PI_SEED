# docs/parked/ - Ideas, Not Contracts

This folder is a parking place for sketches, prompts, reviews, and future ideas
that should not yet drive implementation.

## Status

Everything in `docs/parked/` is explicitly non-canonical:

- It is not a roadmap step.
- It is not an event contract.
- It is not an architecture decision.
- It must not be treated as build input by default.

The canonical sources remain:

- `../GENUS_ROADMAP.md`
- `../GENUS_ARCHITECTURE.md`
- `../GENUS_EVENT_CONTRACT.md`
- `../GENUS_LEDGER_AUDIT.md`

## Why This Exists

GENUS benefits from thinking ahead, but the codebase must stay disciplined.
Some ideas are valuable before they are ready to become commitments. Parking
them here keeps them visible without quietly turning them into scope.

This protects the project rule:

> Build one proven step at a time.

## Promotion Rule

An idea may leave `docs/parked/` only when a concrete roadmap step needs it.
When that happens:

1. Move the minimum necessary part into the canonical document where it belongs.
2. Keep the wording short and testable.
3. Do not import a whole parked framework when one small decision is enough.
4. Implement only after the canonical roadmap step is explicit.

## Good Parking Candidates

- Future threat models.
- Raw review notes.
- Larger concept sketches.
- Alternative designs that lost today but may matter later.
- Pi operation notes that are not yet stable enough for README/deploy docs.

## Not Parking Candidates

- Current build instructions.
- Current event schema rules.
- Active deploy steps.
- Anything a test or implementation must obey today.

Those belong in the canonical docs or in code.
