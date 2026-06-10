# GENUS_PI_SEED_v0 — Codex Prompt

> Historical build prompt. This file records the original implementation
> request and is not the current source of truth. Current contracts live in
> `../GENUS_ARCHITECTURE.md`, `../GENUS_EVENT_CONTRACT.md`, and
> `../GENUS_ROADMAP.md`.

Copy this prompt verbatim into Codex. Do not paraphrase.

---

## Prompt

You are implementing GENUS_PI_SEED_v0: a minimal Python CLI that proves an epistemological system is real.

**Read the full spec first:** `GENUS_PI_SEED_v0_CPU_BELIEF_LOOP_SPEC.md`

Implement it completely. Every section. Do not skip anything.

---

## What you are building

A CLI called `genus` that:

1. Reads CPU sensor data
2. Writes immutable events to an append-only SQLite event log
3. Derives Beliefs from those events (projection, not storage)
4. Calculates Confidence from inputs — never stores a magic number
5. Generates Proposals when contradictions are detected
6. Can replay the entire event log to rebuild state from scratch

This is not a web app. Not a chatbot. Not a framework.
It is an epistemological system. The CPU is just the first sensor.

---

## Non-negotiable invariants

These must never be violated. If you feel tempted to break one, stop and re-read the spec.

```
1. event_log is append-only.
   No UPDATE. No DELETE. On any row. Ever.

2. belief_projection is fully derived.
   It can be cleared and rebuilt by replaying event_log.
   It is a projection, not a source of truth.

3. Confidence is calculated, never stored.
   The belief_projection table has NO confidence column.
   confidence.py derives it from supporting_count, contradicting_count,
   latest_evidence_age_seconds on every read.

4. No LLM calls. Zero.
   No import of anthropic, openai, ollama, transformers, or similar.

5. derivation is always set.
   Every belief row has a non-null derivation string.
   For v0 it is always "rule:cpu_threshold_v1".

6. Proposals are not changes.
   proposal_log.state defaults to "pending".
   Nothing in the codebase acts on a proposal automatically.
```

---

## Implementation order

Follow this order. Do not skip ahead.

```
1.  schema.sql              — three tables + indexes
2.  genus/db.py             — get_connection(path), init_schema(conn)
3.  genus/ledger.py         — append(), tail(), replay()
4.  genus/sensor.py         — read_cpu(), mock_cpu(value)
5.  genus/confidence.py     — calculate_confidence(...)
6.  genus/rules.py          — apply_cpu_rule(conn, evidence_event_id) → list[str]
7.  genus/projection.py     — get_active_beliefs(conn), get_belief(conn, id)
8.  genus/proposals.py      — create_proposal_if_needed(conn, belief_id, event_id)
9.  genus/cli.py            — observe-cpu, beliefs show, proposals list, replay, ledger tail
10. tests/conftest.py       — in-memory DB fixture
11. tests/test_ledger.py
12. tests/test_projection.py
13. tests/test_rules.py
14. tests/test_cli.py
15. requirements.txt
16. README.md               — setup + 5-minute quickstart
```

---

## Rules module detail

The only rule in v0 is `cpu_threshold_v1`.

```python
HIGH_THRESHOLD = 80.0
LOW_THRESHOLD  = 60.0
WINDOW_SIZE    = 3
METRIC_KEY     = "system.cpu_percent"
```

To evaluate the rule, query the last WINDOW_SIZE evidence events
where `json_extract(payload, '$.metric_key') = 'system.cpu_percent'`
from event_log, ordered by id DESC.

Then:

```
ALL values > HIGH_THRESHOLD:
  → no active belief:  write belief_created, update projection
  → belief active:     write belief_confirmed, update supporting_events

ALL values < LOW_THRESHOLD AND active belief "system.load=high" exists:
  → write belief_superseded (old belief → new "system.load=normal")
  → write contradiction_detected
  → call create_proposal_if_needed()

MIXED (neither all-high nor all-low):
  → active belief exists: write belief_weakened, update contradicting_events
  → no belief yet: do nothing (wait for full window)
```

---

## Confidence formula

```python
import math

def calculate_confidence(
    supporting_count: int,
    contradicting_count: int,
    latest_evidence_age_seconds: float,
    decay_halflife_seconds: float = 300.0,
) -> float:
    if supporting_count == 0:
        return 0.0
    ratio = supporting_count / (supporting_count + contradicting_count + 1)
    decay = math.exp(-0.693147 * latest_evidence_age_seconds / decay_halflife_seconds)
    return round(ratio * decay, 3)
```

Call this in `projection.py` when displaying beliefs. Never call it in rules.py.

---

## CLI expected output

```
$ genus observe-cpu
[OBS] CPU: 91.2% (source: psutil.cpu_percent)
[EVT] observation_created (id=47)
[EVT] evidence_recorded   (id=48, metric: system.cpu_percent=91.2)
[BLF] system.load=high confirmed (supporting: 5, contradicting: 0)
      confidence: 0.847  derivation: rule:cpu_threshold_v1

$ genus beliefs show

ACTIVE BELIEFS
──────────────────────────────────────────────────────────────────
claim_key    claim_value  confidence  supporting  contradicting  derivation
system.load  high         0.847       5           0              rule:cpu_threshold_v1

$ genus proposals list

PENDING PROPOSALS
──────────────────────────────────────────────────────────────────
id  type              claim         state    created_at
3   ResourceProposal  system.load   pending  2025-06-05T14:32:11Z

$ genus replay
[REPLAY] Reading 52 events from event_log...
[REPLAY] Rebuilding belief_projection...
[REPLAY] Rebuilding proposal_log...
[REPLAY] Result: 1 active belief, 2 superseded, 3 proposals
[REPLAY] ✓ State matches current projection
```

---

## Test requirements

- All tests use an in-memory SQLite DB via conftest.py fixture
- No psutil in tests — use mock_cpu(value) from sensor.py
- No file system writes in tests

Critical tests (must exist and must pass):

```
test_event_log_is_append_only
    — attempt UPDATE on event_log → must raise or be blocked

test_replay_rebuilds_identical_state
    — run N observations → replay() → state identical to pre-replay

test_superseded_belief_is_not_deleted
    — supersede a belief → row still exists in belief_projection

test_confidence_is_not_stored
    — belief_projection schema has no 'confidence' column

test_contradiction_creates_proposal
    — 3x high then 3x low → exactly one ResourceProposal in proposal_log

test_derivation_is_always_set
    — every belief row has non-null, non-empty derivation
```

---

## Requirements.txt

```
click>=8.0
psutil>=5.9
pytest>=7.0
```

No other dependencies. Standard library only beyond these three.

---

## Definition of done

Before submitting, verify manually:

```bash
cd genus_seed
pip install -e .
pytest                              # all green, zero warnings
genus observe-cpu                   # writes 2 events, shows belief
genus observe-cpu                   # (repeat 3+ times with high CPU)
genus beliefs show                  # shows system.load=high with confidence
genus ledger tail --n 10            # shows last 10 events
genus replay                        # exits 0, state matches
grep -r "anthropic\|openai\|ollama" genus/  # empty
```

---

## Why this matters

When `pytest` is green and `genus replay` matches, GENUS has proven:

- Observation ≠ Belief (three distinct writes per cycle)
- Beliefs are projections (replay test)
- Confidence is calculable (confidence.py with stored inputs)
- Contradictions generate Proposals (test_contradiction_creates_proposal)
- The Ledger is immutable (append-only test)
- GENUS is not a chatbot (zero language input in the entire loop)

That is the seed. Everything else grows from here. 🧬
