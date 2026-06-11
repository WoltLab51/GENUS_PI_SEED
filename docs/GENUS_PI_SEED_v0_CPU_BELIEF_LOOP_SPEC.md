# GENUS_PI_SEED_v0 — CPU Belief Loop Spec

> Version: 0.7.0
> Target: Raspberry Pi 5 / ThinkPad X1, Python 3.11+
> Purpose: Prove GENUS is real. Not a demo. A working epistemological system.

---

## What this proves

This single build proves, in runnable code:

1. GENUS is not a chatbot — it learns from sensor data, zero language input required
2. Beliefs are projections derived from an immutable event log, not stored values
3. Confidence is calculated from stored inputs, never stored as a magic number
4. Contradictions automatically generate Proposals
5. The Ledger is immutable — replay produces identical state
6. GENUS has no external dependencies — no LLM, no web, no HTTP

---

## Hard scope (v0)

**In:**

- SQLite (stdlib sqlite3, no ORM)
- CLI (Click)
- CPU sensor (psutil)
- Append-only event_log
- belief_projection (derived, rebuildable)
- proposal_log
- pytest

**Out (not in v0, no exceptions):**

- FastAPI
- Worker / daemon
- LLM / model calls
- HTTP / web requests
- Web interface
- Graph / network between beliefs
- DailyReview formatting
- Config files
- Background scheduler

---

## Project structure

```
genus_seed/
├── genus/
│   ├── __init__.py
│   ├── cli.py            # CLI entry point (Click)
│   ├── db.py             # DB connection, schema init
│   ├── sensor.py         # CPU reading via psutil
│   ├── ledger.py         # Append-only event log
│   ├── projection.py     # BeliefProjection (derived from ledger)
│   ├── rules.py          # Deterministic belief rules (no LLM)
│   ├── confidence.py     # Confidence calculation (inputs stored, number derived)
│   └── proposals.py      # Proposal generation
├── tests/
│   ├── conftest.py       # In-memory DB fixture
│   ├── test_ledger.py
│   ├── test_projection.py
│   ├── test_rules.py
│   └── test_cli.py
├── schema.sql
├── requirements.txt
└── README.md
```

---

## Database schema

### event_log — immutable ledger, append-only

```sql
CREATE TABLE IF NOT EXISTS event_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT    NOT NULL,
    payload     TEXT    NOT NULL,  -- JSON, always valid
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_event_log_type    ON event_log(event_type);
CREATE INDEX IF NOT EXISTS idx_event_log_created ON event_log(created_at);
```

**Invariant:** No UPDATE, no DELETE on this table. Ever. Enforced by test.

### belief_projection — derived state, fully rebuildable from event_log

```sql
CREATE TABLE IF NOT EXISTS belief_projection (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_key            TEXT    NOT NULL,   -- e.g. "system.load"
    claim_value          TEXT    NOT NULL,   -- e.g. "high"
    state                TEXT    NOT NULL,   -- active | superseded | archived
    derivation           TEXT    NOT NULL,   -- e.g. "rule:cpu_threshold_v1"
    supporting_events    TEXT    NOT NULL DEFAULT '[]',   -- JSON array of event_log ids
    contradicting_events TEXT    NOT NULL DEFAULT '[]',   -- JSON array of event_log ids
    created_at           TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_updated_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    superseded_by        INTEGER REFERENCES belief_projection(id)
);
```

**Naming:** `claim_key` + `claim_value` are intentionally non-linguistic.
A belief is a structured claim like `("system.load", "high")`, not a sentence.
Human-readable text is a display concern, never stored here.

**No `confidence` column.** Confidence is always calculated by confidence.py
from `supporting_events`, `contradicting_events`, and event timestamps.

**Invariant:** This table can be cleared and rebuilt by replaying event_log.
State here is always a projection, not a source of truth.

### proposal_log

```sql
CREATE TABLE IF NOT EXISTS proposal_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_type  TEXT    NOT NULL,   -- e.g. "ResourceProposal"
    claim_key      TEXT    NOT NULL,
    claim_value    TEXT    NOT NULL,
    source_belief  INTEGER REFERENCES belief_projection(id),
    source_event   INTEGER REFERENCES event_log(id),
    payload        TEXT    NOT NULL,   -- JSON
    state          TEXT    NOT NULL DEFAULT 'pending',  -- pending | reviewed
    created_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
```

---

## Event types

All events are written to event_log. payload is always a valid JSON string.

| event_type              | required payload keys                                         |
|-------------------------|---------------------------------------------------------------|
| `observation_created`   | `source`, `raw_value`, `unit`                                 |
| `evidence_recorded`     | `observation_id`, `metric_key`, `metric_value`                |
| `belief_created`        | `claim_key`, `claim_value`, `derivation`, `supporting_events` |
| `belief_confirmed`      | `belief_id`, `new_supporting_event`                           |
| `belief_weakened`       | `belief_id`, `contradicting_event`                            |
| `belief_superseded`     | `old_belief_id`, `new_belief_id`, `reason`                    |
| `contradiction_detected`| `belief_id`, `reason`                                         |
| `proposal_created`      | `proposal_id`, `proposal_type`, `reason`                      |

---

## sensor.py

```python
import psutil

def read_cpu() -> dict:
    """
    Takes one CPU reading via psutil.
    Returns a raw observation dict — no interpretation, no belief.

    Returns:
        {
            "source": "psutil.cpu_percent",
            "raw_value": 82.3,
            "unit": "percent",
            "interval": 1.0
        }
    """
    return {
        "source": "psutil.cpu_percent",
        "raw_value": psutil.cpu_percent(interval=1.0),
        "unit": "percent",
        "interval": 1.0,
    }

def mock_cpu(value: float) -> dict:
    """For tests. Returns a fixed value without calling psutil."""
    return {
        "source": "mock",
        "raw_value": value,
        "unit": "percent",
        "interval": 0.0,
    }
```

---

## ledger.py

```python
def append(conn, event_type: str, payload: dict) -> int:
    """
    Append one event to event_log.
    Returns the new event id.
    Never updates or deletes existing rows.
    """

def tail(conn, n: int = 20) -> list[dict]:
    """Return the last n events from event_log, oldest first."""

def replay(conn) -> dict:
    """
    Clear belief_projection and proposal_log.
    Replay all events in event_log chronologically.
    Rebuild projections from scratch.
    Return summary: {"events": int, "active_beliefs": int, "proposals": int}
    """
```

---

## confidence.py

```python
import math

def calculate_confidence(
    supporting_count: int,
    contradicting_count: int,
    latest_evidence_age_seconds: float,
    decay_halflife_seconds: float = 300.0,
) -> float:
    """
    Confidence is always derived from stored inputs. Never stored directly.

    Inputs are stored in belief_projection (supporting_events, contradicting_events,
    timestamps in event_log). This function is called at read time, not write time.

    Formula:
        ratio = supporting / (supporting + contradicting + 1)
        decay = exp(-ln(2) * age / halflife)
        confidence = ratio * decay

    Args:
        supporting_count:             Number of events supporting this belief
        contradicting_count:          Number of events contradicting this belief
        latest_evidence_age_seconds:  Seconds since most recent supporting evidence
        decay_halflife_seconds:       Time for confidence to halve with no new evidence

    Returns:
        float in [0.0, 1.0], rounded to 3 decimal places
    """
    if supporting_count == 0:
        return 0.0
    ratio = supporting_count / (supporting_count + contradicting_count + 1)
    decay = math.exp(-0.693147 * latest_evidence_age_seconds / decay_halflife_seconds)
    return round(ratio * decay, 3)
```

---

## rules.py — cpu_threshold_v1

**Constants (hardcoded in v0):**

```python
HIGH_THRESHOLD = 80.0   # % CPU — above this counts as high load
LOW_THRESHOLD  = 60.0   # % CPU — below this counts as normal load
WINDOW_SIZE    = 3      # consecutive readings required to act
METRIC_KEY     = "system.cpu_percent"
```

**Logic:**

```
Step 1 — Read last WINDOW_SIZE evidence events
         WHERE metric_key = "system.cpu_percent"
         FROM event_log ORDER BY id DESC LIMIT WINDOW_SIZE

Step 2 — Evaluate window:

  CASE A: All values > HIGH_THRESHOLD
    → no active belief "system.load = high":
        write belief_created → update projection
    → belief already active:
        write belief_confirmed → update supporting_events

  CASE B: All values < LOW_THRESHOLD
         AND active belief "system.load = high" exists
    → write belief_superseded (old → new "system.load = normal")
    → write contradiction_detected
    → call create_proposal_if_needed()

  CASE C: Mixed window
    → active belief exists:
        write belief_weakened → add to contradicting_events
    → no belief yet: do nothing (wait for full window)

Step 3 — Return list of event_types written (for CLI to display)
```

**Invariants:**
- rules.py never calls an LLM
- rules.py never makes HTTP calls
- derivation is always `"rule:cpu_threshold_v1"`

---

## proposals.py

```python
def create_proposal_if_needed(
    conn,
    trigger_belief_id: int,
    trigger_event_id: int
) -> int | None:
    """
    Called after a contradiction_detected event.
    Creates a ResourceProposal in proposal_log.
    Writes a proposal_created event to event_log.
    Returns proposal id, or None if no proposal was needed.

    Proposal payload example:
    {
        "description": "CPU load was high, then dropped. Investigate cause.",
        "observed_pattern": "system.load: high → normal",
        "action_required": false,
        "review_recommended": true
    }

    Note: Proposals are suggestions only. state defaults to "pending".
    Nothing acts on a proposal automatically.
    """
```

---

## CLI commands

```bash
# Take one CPU reading → write events → apply rules → update projection
genus observe-cpu

# Show all active beliefs with calculated confidence
genus beliefs show

# List proposals (default: pending only)
genus proposals list [--all]

# Replay event_log → rebuild projections → verify integrity
genus replay

# Show last N events from event_log
genus ledger tail [--n 20]
```

---

## Expected CLI output

```
$ genus observe-cpu
[OBS] CPU: 91.2% (source: psutil.cpu_percent)
[EVT] observation_created     (id=47)
[EVT] evidence_recorded       (id=48, metric: system.cpu_percent=91.2)
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
id  type              claim_key    claim_value  state    created_at
3   ResourceProposal  system.load  high         pending  2025-06-05T14:32:11Z

$ genus replay
[REPLAY] Reading 52 events from event_log...
[REPLAY] Rebuilding belief_projection...
[REPLAY] Rebuilding proposal_log...
[REPLAY] Result: 1 active belief, 2 superseded, 3 proposals
[REPLAY] ✓ State matches current projection
```

---

## Test requirements

All tests use an **in-memory SQLite database** via a conftest.py fixture.
No psutil calls in tests — use `mock_cpu(value)` from sensor.py.
No file system writes. No HTTP calls.

### conftest.py

```python
import pytest
import sqlite3
from genus.db import init_schema

@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    init_schema(c)
    yield c
    c.close()
```

### test_ledger.py

```
test_append_creates_row
    append one event → row exists in event_log with correct type and payload

test_event_log_is_append_only
    attempt UPDATE on event_log → must raise or fail explicitly

test_tail_returns_correct_count
    append 30 events → tail(n=10) returns exactly 10

test_replay_rebuilds_identical_state
    run 10 observe-cpu cycles (mixed high/low) → replay()
    → active beliefs and proposals match pre-replay state exactly
```

### test_projection.py

```
test_high_cpu_creates_belief
    3x mock_cpu(92.0) → belief system.load=high is active

test_low_after_high_supersedes_belief
    3x mock_cpu(92.0) then 3x mock_cpu(40.0)
    → old belief state = superseded
    → new belief system.load=normal is active
    → old belief row still exists in DB (not deleted)
    → superseded_by links correctly

test_superseded_belief_is_not_deleted
    supersede a belief → query by id → row still exists, state = superseded

test_confidence_decreases_with_contradicting_evidence
    5 supporting, 0 contradicting → confidence X
    5 supporting, 3 contradicting → confidence Y
    assert Y < X

test_confidence_is_not_stored
    create any belief → belief_projection row has no "confidence" column
```

### test_rules.py

```
test_window_below_threshold_does_not_create_belief
    2x mock_cpu(92.0) → no belief created (window not full yet)

test_mixed_window_weakens_belief_not_supersedes
    3x high, then 1x low → belief weakened, not superseded

test_contradiction_creates_proposal
    3x mock_cpu(92.0) → 3x mock_cpu(40.0)
    → proposal_log has exactly one ResourceProposal

test_derivation_is_always_set
    create any belief → derivation field is not null and not empty

test_no_http_in_rules
    import rules → no import of requests, httpx, aiohttp, urllib anywhere
```

### test_cli.py

```
test_observe_cpu_writes_two_base_events (mock sensor at 92%)
    invoke observe-cpu → event_log has observation_created + evidence_recorded

test_beliefs_show_returns_active_only
    1 active + 1 superseded belief → beliefs show lists only 1

test_proposals_list_shows_pending
    1 proposal created → proposals list output contains it

test_replay_command_exits_zero
    run 5 observations → genus replay → exit code 0
```

---

## Success criteria (definition of done)

All of these must be true before v0 is merged:

- [ ] `pytest` green, zero warnings
- [ ] `genus observe-cpu` (mocked at 92%) writes exactly 2 base events
- [ ] After 3 high readings: `genus beliefs show` shows `system.load=high`
- [ ] After 3 low readings: old belief is `superseded`, new belief is `active`
- [ ] Old belief row still exists in DB after supersession (select by id → found)
- [ ] `genus replay` exits 0 and matches current state
- [ ] **`grep -r "anthropic\|openai\|ollama" genus/` → empty**
- [ ] **`grep -r "requests\|httpx\|aiohttp\|urllib.request" genus/` → empty**
- [ ] Zero stored confidence values — `belief_projection` has no confidence column
- [ ] `belief_projection.derivation` is never null in any test

The two grep checks together prove:
- No LLM → GENUS is not a model wrapper
- No HTTP → GENUS makes no external calls in v0

---

## DNA invariants (must never be violated)

```
Observation ≠ Evidence     → separate DB rows, separate events
Evidence ≠ Belief          → belief only after WINDOW_SIZE readings
Belief ≠ Truth             → state is "active", never "true"
Model Output ≠ Knowledge   → no LLM in v0
Ledger ≠ Memory            → event_log immutable; projection is derived
Proposal ≠ Change          → proposal_log.state defaults to "pending"
claim_key + claim_value    → not a sentence, not a "statement"
confidence                 → calculated at read time, never written to DB
```

---

*GENUS_PI_SEED_v0 — the smallest thing that can prove GENUS is real. 🧬*
