# GENUS_PI_SEED_v0 CPU Belief Loop Spec

Source: `C:\Users\ronny\Downloads\GENUS_PI_SEED_v0_CPU_BELIEF_LOOP_SPEC.md`.

This repository implements the v0.2.0 CPU belief loop described in the source
specification, with the following binding clarifications:

- `HIGH_THRESHOLD=80.0`, `LOW_THRESHOLD=60.0`, `WINDOW_SIZE=3`.
- Confidence is calculated only in `genus/confidence.py` and is never stored.
- `replay()` may clear `belief_projection` and `proposal_log` and reset their
  `sqlite_sequence` values, but it never mutates `event_log`.
- A proposal is created exactly for `belief_created` on first sustained high and
  for `contradiction_detected` on high-to-normal contradiction. It is never
  created for `belief_confirmed`.
- No LLM, web, worker, HTTP client, or external API imports are allowed.

The implemented project layout:

```text
genus/
  __init__.py
  cli.py
  confidence.py
  db.py
  ledger.py
  projection.py
  proposals.py
  rules.py
  sensor.py
tests/
schema.sql
requirements.txt
pyproject.toml
README.md
```

Core invariants:

- `event_log` is append-only.
- `belief_projection` is fully rebuildable from `event_log`.
- `proposal_log` is rebuilt from proposal events during replay.
- `derivation` is never null or empty.
- `confidence` is a derived value, not a database value.
