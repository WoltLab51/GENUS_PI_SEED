# GENUS_PI_SEED

GENUS PI SEED is a deterministic, ledger-first system belief loop:

- observations and evidence are separate immutable ledger events
- beliefs are derived projections, not source-of-truth rows
- confidence is calculated at read time and never stored
- proposals are suggestions only and default to `pending`
- no LLM, no HTTP, no worker, no web interface

## Documentation

The project documentation lives in `docs/`.

- `docs/GENUS_GESAMTBILD.md` is the navigation document for the overall goal.
- `docs/GENUS_ROADMAP.md` defines the next build steps and growth gates.
- `docs/GENUS_ARCHITECTURE.md` and `docs/GENUS_EVENT_CONTRACT.md` are the
  current technical contracts.
- `docs/GENUS_LEDGER_AUDIT.md` documents the current ledger integrity boundary
  and the recommended sealing path.
- `docs/GENUS_SENSOR_PRINCIPLE.md` defines the boundary for future sensors.

## Commands

```bash
genus observe-cpu
genus observe-memory
genus observe-disk
genus observe-activity
genus observe-temperature
genus observe-all
genus ask "was glaubst du"
genus ask "status"
genus explain belief 1
genus explain experience 1
genus explain state 1
genus why proposal 1
genus why decision 1
genus beliefs show
genus experience scan
genus experience show
genus state refresh
genus state show
genus maturation scan
genus rules list
genus rules activate 2
genus proposals list
genus proposals list --all
genus proposals review 1 --accept --note "makes sense"
genus proposals review 1 --accept --override --note "override under pressure"
genus governance list
genus governance list --target proposal:1
genus inquiries list
genus inquiries resolve 1 --answer "Backup lief"
genus replay
genus integrity check
genus ledger tail --n 20
```

The default SQLite database is `genus.sqlite3`. Override it with:

```bash
GENUS_DB_PATH=/path/to/genus.sqlite3 genus replay
```

## Habitat Sensors

v0.6 extends the local, offline habitat with disk, activity, and temperature
observations. Disk and temperature currently use the same threshold/revision
mechanic as CPU and memory. Activity is binary and creates or supersedes a
belief immediately without waiting for the three-reading threshold window.

## Query Layer

v0.7 adds deterministic read-only queries. Query commands explain current state
from projections and ledger events; they do not write events.

- `genus ask "was glaubst du"` lists active beliefs.
- `genus ask "status"` summarizes event and projection counts.
- `genus explain belief <id>` shows supporting and contradicting evidence.
- `genus why proposal <id>` shows the source event and source belief chain.

## Proposal And Inquiry Lifecycle

v0.8 adds the first event-backed human governance actions:

- `genus proposals review <id> --accept|--reject [--note "..."]`
- `genus inquiries resolve <id> --answer "..."`

Reviews and resolutions are terminal. A second review or resolve attempt fails.
Accepting a proposal does not execute anything; `Proposal != Change` is still a
hard rule. Existing databases get the new projection columns automatically on
startup; run `genus replay` after upgrading to rebuild projections from the
ledger.

## Experience Core

v0.9 adds deterministic first learning from the ledger. `genus experience scan`
aggregates existing `event_log` evidence and records contrasted activity hours
as an `ActivityDailyRhythm` experience.

- `experience_recorded` is the durable event.
- `experience_log` is a rebuildable projection.
- `genus experience show` lists recorded experiences.
- `genus explain experience <id>` shows the source event, supporting evidence,
  and any review-only `ExperienceProposal`.
- `genus ask "welche muster"` exposes the same records through the query layer.

## State Core

v0.10 adds the first deterministic state vector. `genus state refresh` derives
`system.pressure` from active beliefs and records a `state_changed` event only
when the vector changes.

- `state_changed` is the durable event.
- `state_projection` is a rebuildable projection.
- `genus state show` lists active states.
- `genus explain state <id>` shows the state event and supporting beliefs.
- `genus ask "zustand"` exposes active states through the query layer.

## Governance v1

v0.11 adds event-backed governance for proposal review. Kernel constraints are
hard and never overrideable; policies can block a decision unless an explicit
human override is supplied.

- `constraint_checked` records non-overrideable kernel checks.
- `policy_evaluated` records overrideable policy checks.
- `governance_decision` is the durable allowed/blocked decision event.
- `governance_log` is a rebuildable projection of decision events only.
- `policy:pressure_guard_v1` blocks accepting a proposal while
  `system.pressure=elevated`, unless `--override` is passed.
- Inquiry resolution is deliberately ungoverned in v0.11.

Blocked reviews still commit their governance audit events and leave the
proposal pending. Accepted proposals remain review decisions only:
`Proposal != Change`.

## Maturation v1

v1.0 closes the first deterministic metabolism loop. `genus maturation scan`
turns confirmed `ActivityDailyRhythm` experiences into pending `RuleProposal`
records. Accepting that proposal still activates nothing. A second, governed
human act is required:

- `rule_proposed` records the learned deterministic rule candidate.
- `rule_activated` records the second human gate and projects an active rule.
- `rule_projection` is rebuildable from `rule_activated` events.
- `genus rules activate <proposal_id>` requires an accepted `RuleProposal`.
- Active `activity_expectation_v1` rules only create `ExpectationInquiry`
  records on deviations; they never change beliefs or execute actions.
- `genus explain rule <id>` shows the active rule, source proposal,
  `rule_proposed` event, and source experience.

This keeps `Proposal != Change` hard at the exact point where GENUS starts
compiling experience into behavior.

## Automatic Collection With Cron

GENUS does not need a daemon for the first Pi loop. Run all local sensors from
cron and keep the core UNIX-simple:

```bash
crontab -e
```

```cron
*/5 * * * * cd /path/to/GENUS_PI_SEED && .venv/bin/genus observe-all >> ~/.genus/cron.log 2>&1
*/5 * * * * cd /path/to/GENUS_PI_SEED && .venv/bin/genus state refresh >> ~/.genus/cron.log 2>&1
```

With an explicit database path:

```cron
*/5 * * * * cd /path/to/GENUS_PI_SEED && GENUS_DB_PATH=/home/pi/.genus/genus.sqlite3 .venv/bin/genus observe-all >> /home/pi/.genus/cron.log 2>&1
*/5 * * * * cd /path/to/GENUS_PI_SEED && GENUS_DB_PATH=/home/pi/.genus/genus.sqlite3 .venv/bin/genus state refresh >> /home/pi/.genus/cron.log 2>&1
```

Run `genus experience scan` manually or from a slower daily cron. It looks for
contrasting activity rhythms, not raw sample frequency, and creates at most one
review proposal per scan.

## Quality Checks

```bash
python -m pytest
genus replay
genus integrity check
grep -r "anthropic|openai|ollama" genus/
grep -r "requests|httpx|aiohttp|urllib.request" genus/
```

GitHub Actions runs the same quality gate on `main` and pull requests.
