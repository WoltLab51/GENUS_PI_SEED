# GENUS_PI_SEED

GENUS PI SEED v0 is a minimal system belief loop:

- observations and evidence are separate immutable ledger events
- beliefs are derived projections, not source-of-truth rows
- confidence is calculated at read time and never stored
- proposals are suggestions only and default to `pending`
- no LLM, no HTTP, no worker, no web interface

## Commands

```bash
genus observe-cpu
genus observe-memory
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

## Quality Checks

```bash
pytest
genus replay
grep -r "anthropic|openai|ollama" genus/
grep -r "requests|httpx|aiohttp|urllib.request" genus/
```
