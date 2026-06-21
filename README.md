# GENUS_PI_SEED

GENUS PI SEED is a deterministic, ledger-first system belief loop:

- observations and evidence are separate immutable ledger events
- beliefs are derived projections, not source-of-truth rows
- confidence is calculated at read time and never stored
- proposals are suggestions only and default to `pending`
- no LLM, no HTTP, no worker, no web interface

## Documentation

The project documentation lives in `docs/`.

- `docs/README.md` explains which documents are canonical, supporting,
  future-facing, parked, or archived.
- `docs/GENUS_GESAMTBILD.md` is the navigation document for the overall goal.
- `docs/GENUS_ROADMAP.md`, `docs/GENUS_ARCHITECTURE.md`,
  `docs/GENUS_EVENT_CONTRACT.md`, and `docs/GENUS_LEDGER_AUDIT.md` are the
  current build contracts.
- `docs/GENUS_ARCHITECTURE.md#change-trust` defines how GENUS treats updates:
  a change earns trust only after deterministic gates and observed runtime.

## Commands

```bash
genus observe-cpu
genus observe-memory
genus observe-disk
genus observe-activity
genus observe-temperature
genus observe-all
genus doctor
genus ask "was glaubst du"
genus ask "status"
genus explain belief 1
genus explain experience 1
genus explain state 1
genus explain rule 1
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
genus operation network-check --status ok --target 192.168.178.1
genus operation recovery-result --recovery-id 1 --result succeeded
genus operation list
genus inquiries list
genus inquiries resolve 1 --answer "Backup lief"
genus replay
genus integrity check
genus ledger tail --n 20
genus ledger seal-init
genus ledger head
genus ledger verify
genus ledger anchor create --core-id pi-core
genus ledger anchor verify /path/to/genus-anchor-pi-core-3-abc123def456.json
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

## Confidence Decay

v1.5 changes confidence from raw event counts plus a latest-evidence decay gate
to time-weighted evidence counting. Each supporting or contradicting evidence
event contributes `2^(-age / H)` at read time, using a per-claim halflife. This
keeps long-running beliefs from becoming sticky only because old confirmations
accumulated. Confidence is still never stored in the database.

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

## Ledger Sealing

v1.1 adds local ledger sealing. `genus ledger seal-init` appends one
`ledger_epoch_opened` event with a genesis digest over the legacy prefix. From
that point on, new events carry `prev_seal` and `seal` in `event_log`.

- `genus ledger head` prints the current seal head for later external anchoring.
- `genus ledger verify` recomputes the local chain.
- `genus integrity check` includes the same seal verification.
- Existing events are not updated or backfilled.

This detects accidental corruption and lazy tampering. A fully adaptive local
attacker can still rewrite and re-seal without an external anchor; that boundary
is documented in `docs/GENUS_LEDGER_AUDIT.md`.

## External Ledger Anchors

v1.2 adds offline JSON anchors for the current seal head. Creating an anchor is
read-only: it writes no event, does not commit anything to the database, and
does not call Git, GitHub, HTTP, or any external API.

```bash
GENUS_CORE_ID=pi-core genus ledger anchor create
GENUS_CORE_ID=pi-core genus ledger anchor create --out /safe/place/anchors/
GENUS_CORE_ID=pi-core genus ledger anchor verify /safe/place/anchors/genus-anchor-pi-core-3-abc123def456.json
```

`--core-id` can be used instead of `GENUS_CORE_ID`. The `core_id` is required so
long-lived anchor files say which GENUS core they describe. If `--out` points to
an existing directory, GENUS writes
`genus-anchor-{core_id}-{head_event_id}-{head_prefix}.json`.

An anchor protects the ledger prefix up to its `head_event_id`. Later events are
valid local history, but they are not externally witnessed until the next anchor.
To check a directory of anchors, run `genus ledger anchor verify` for each file.

## Self-Operation And Recovery

v1.3/v1.4 add deterministic self-operation checks and governed recovery. The
first supported check is `network.gateway`, projected into `operation_log` and
the normal belief `system.network=healthy|unstable`.

```bash
genus operation network-check --status ok --target 192.168.178.1
genus operation network-check --status fail --target 192.168.178.1 --failures 1 --action restart_network
genus operation recovery-result --recovery-id 1 --result succeeded
genus operation list
genus ask "betrieb"
```

Recovery is policy-gated before the operating system does anything.
`restart_network` is allowed after a failed gateway check; `reboot` is blocked
until at least three consecutive failures and no prior reboot recovery attempt
is inside the governance cooldown window.

## Structure Material, New Forms, and Self-Calibration

v1.6 opens Phase 2: GENUS observes more than the machine, and learns its own
norms instead of being told them.

- **Clock-sync self-check** (`clock.sync` -> `system.clock`), with a one-day
  inert confidence half-life for the slow (disk-class) beliefs.
- **Structure material** — the first sensor of *your work*, measured off-device
  on the workstation and fed in over SSH (counts only, never contents):
  `repo.commits_per_day` -> `repo.activity` and `repo.lines_changed_per_day` ->
  `repo.churn`. See `deploy/observe_repo_from_x1.sh`.
- **New epistemic forms beyond threshold/binary:** `disk.trend`
  (rising/stable/falling) and `system.thermal` (temperature-vs-CPU correlation).
- **Self-calibration:** these thresholds are no longer preset. `repo.churn`,
  `disk.trend`, and `system.thermal` judge against this core's *own* lived
  distribution at read time, and withhold judgment until they have enough
  history. The only remaining preset magnitudes are the confidence half-lives.

All deterministic, replay-stable, no new event types, no LLM.

## Automatic Collection With Cron

GENUS does not need a daemon for the first Pi loop. Install the marked user
crontab block from the repository:

```bash
cd /home/pi/GENUS_PI_SEED
GENUS_CORE_ID=pi-core ./deploy/pi_install_cron.sh
```

That block runs:

- `genus observe-all` every 5 minutes
- `genus state refresh` every 5 minutes, one minute later
- `genus experience scan` daily
- `genus doctor` daily

Logs are written to `/home/pi/.genus/logs/cron.log` and
`/home/pi/.genus/logs/doctor.log`.

For headless Pi resilience, install the optional systemd network watchdog:

```powershell
.\deploy\install_pi_network_watchdog.cmd -HostName ronny@Pi -CoreId pi-core
```

The watchdog logs to `/home/pi/.genus/logs/network-watchdog.log`, records
operation events in GENUS, restarts the network stack on early failures, and
reboots only after the governed repeated-failure threshold.
Repeated reboots are rate-limited by the core governance policy, not only by the
shell script.

For off-device exchange, `deploy/pi_publish_status.sh` can publish anchors and
a minimal public health summary to `WoltLab51/GENUS_PI_STATUS`. It never uploads
the SQLite database, local paths, raw doctor output, or recent event timelines.

## Pi Deployment

Use the scripts in `deploy/` to update a Raspberry Pi without logging in and
typing the full sequence by hand:

```powershell
.\deploy\deploy_to_pi.ps1 -HostName pi@pi.local -CoreId pi-core -InstallCron
```

The remote script fast-forwards `main`, installs the package, runs tests,
checks integrity, verifies ledger sealing, exports an optional offline anchor,
prints a final `genus doctor` report, and refuses dirty working trees. See
`deploy/README.md`.

## Quality Checks

```bash
python -m pytest
genus doctor
genus replay
genus integrity check
genus ledger seal-init
genus ledger head
genus ledger verify
GENUS_CORE_ID=ci-core genus ledger anchor create --out /tmp/genus-anchor.json
GENUS_CORE_ID=ci-core genus ledger anchor verify /tmp/genus-anchor.json
genus operation network-check --status ok --target 192.168.178.1
grep -R -n -E --include='*.py' "anthropic|openai|ollama" genus/
grep -R -n -E --include='*.py' "requests|httpx|aiohttp|urllib.request" genus/
```

GitHub Actions runs the same quality gate on `main` and pull requests.
