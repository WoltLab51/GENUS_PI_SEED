# GENUS_PI_SEED

GENUS PI SEED v0 is a minimal system belief loop:

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
genus why proposal 1
genus beliefs show
genus proposals list
genus proposals list --all
genus inquiries list
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

## Automatic Collection With Cron

GENUS does not need a daemon for the first Pi loop. Run all local sensors from
cron and keep the core UNIX-simple:

```bash
crontab -e
```

```cron
*/5 * * * * cd /path/to/GENUS_PI_SEED && .venv/bin/genus observe-all >> ~/.genus/cron.log 2>&1
```

With an explicit database path:

```cron
*/5 * * * * cd /path/to/GENUS_PI_SEED && GENUS_DB_PATH=/home/pi/.genus/genus.sqlite3 .venv/bin/genus observe-all >> /home/pi/.genus/cron.log 2>&1
```

## Quality Checks

```bash
pytest
genus replay
grep -r "anthropic|openai|ollama" genus/
grep -r "requests|httpx|aiohttp|urllib.request" genus/
```
