# GENUS Pi Deployment

This folder contains the small, boring deployment path for a Raspberry Pi.

No daemon, no web API, no automatic remote execution by GENUS itself:

- GitHub `main` is the source of code truth.
- The Pi pulls `main` by fast-forward only.
- The Pi runs tests before accepting the deploy.
- The Pi verifies integrity, sealing, replay, and optionally exports an anchor.
- The Pi prints a final `genus doctor` report.

## First Pi Setup

```bash
sudo apt update
sudo apt install -y git python3 python3-venv
git clone https://github.com/WoltLab51/GENUS_PI_SEED.git "$HOME/GENUS_PI_SEED"
cd "$HOME/GENUS_PI_SEED"
GENUS_CORE_ID=pi-core ./deploy/pi_deploy.sh
GENUS_CORE_ID=pi-core ./deploy/pi_install_cron.sh
```

Use a stable `GENUS_CORE_ID`. Anchor files are long-lived witness artifacts, so
the ID should name this specific GENUS core, not just a temporary hostname.

## Deploy From Windows

From the local workstation:

```powershell
.\deploy\deploy_to_pi.ps1 -HostName ronny@pi.local -CoreId pi-core -InstallCron
```

Run this command in Windows PowerShell on the workstation, not inside the SSH
session on the Pi. Inside SSH, use the `.sh` scripts directly.

If Windows blocks `.ps1` script execution, use the matching `.cmd` launcher.
It applies `-ExecutionPolicy Bypass` only to that one command:

```powershell
.\deploy\deploy_to_pi.cmd -HostName ronny@pi.local -CoreId pi-core -InstallCron
```

Useful overrides:

```powershell
.\deploy\deploy_to_pi.ps1 `
  -HostName pi@192.168.178.40 `
  -RepoDir /home/ronny/GENUS_PI_SEED `
  -DbPath /home/ronny/.genus/genus.sqlite3 `
  -AnchorDir /home/ronny/.genus/anchors `
  -StatusRepoDir /home/ronny/GENUS_PI_STATUS `
  -CoreId pi-core
```

## Pi-Side Deploy Script

`pi_deploy.sh` can also be run directly over SSH:

```bash
ssh ronny@pi.local 'cd "$HOME/GENUS_PI_SEED" && GENUS_CORE_ID=pi-core ./deploy/pi_deploy.sh'
```

Environment knobs:

- `GENUS_DB_PATH` defaults to `$HOME/.genus/genus.sqlite3`.
- `GENUS_ANCHOR_DIR` defaults to `$HOME/.genus/anchors`.
- `GENUS_DEPLOY_BRANCH` defaults to `main`.
- `GENUS_DEPLOY_SKIP_TESTS=1` skips pytest.
- `GENUS_DEPLOY_SKIP_ANCHOR=1` skips anchor export.

The script refuses to run on a dirty working tree and refuses non-fast-forward
deploys. Its final `genus doctor` step reports database, integrity, sealing,
core ID, sensors, and forbidden-import guards.

## Cron Installation

`pi_install_cron.sh` installs an idempotent marked block in the current user's
crontab:

```bash
cd "$HOME/GENUS_PI_SEED"
GENUS_CORE_ID=pi-core ./deploy/pi_install_cron.sh
```

Schedule:

- every 5 minutes: `genus observe-all`
- every 5 minutes, one minute later: `genus state refresh`
- daily at 03:17: `genus experience scan`
- daily at 03:27: `genus doctor`

Every scheduled job writes a UTC `[TICK] ...` line before it runs. Those lines
make the cron rhythm visible in the logs without opening the database.

The script replaces only the block between `BEGIN GENUS_PI_SEED` and
`END GENUS_PI_SEED`. Other crontab entries stay untouched.

Logs:

```bash
tail -f "$HOME/.genus/logs/cron.log"
tail -f "$HOME/.genus/logs/doctor.log"
```

## Network Watchdog

`pi_install_network_watchdog.sh` installs a root-owned systemd timer that checks
the Pi default gateway every five minutes. The check itself is recorded in
GENUS as `operation_check_recorded`. If the gateway is unreachable, GENUS first
records the unstable network belief and a governed recovery attempt.

Recovery policy:

- first failures: restart the active network service
- after 3 consecutive failures: schedule a reboot only if the governance
  cooldown allows it
- every recovery attempt and result is written to the ledger

Install it from Windows PowerShell:

```powershell
.\deploy\install_pi_network_watchdog.cmd -HostName ronny@Pi -CoreId pi-core
```

The installer uses `sudo` on the Pi and may ask for the Pi password. Check it
with:

```bash
systemctl status genus-network-watchdog.timer
tail -f "$HOME/.genus/logs/network-watchdog.log"
GENUS_DB_PATH="$HOME/.genus/genus.sqlite3" "$HOME/GENUS_PI_SEED/.venv/bin/genus" operation list
```

## Clock Check

`pi_clock_check.sh` probes whether the system clock is NTP-synchronized and
records the result as self-operation evidence (`clock.sync`), driving a
`system.clock` belief. The Pi 5 onboard RTC only survives a power loss with a
coin cell on the RTC connector; without one, a boot before NTP catches up could
write events with a stale clock. This check turns that risk into visible
material: a fresh drop to `unsynchronized` raises one review-only proposal
instead of silently corrupting the timestamps the temporal patterns depend on.

The cron installer adds it automatically, every 15 minutes. Run it by hand with:

```bash
cd "$HOME/GENUS_PI_SEED"
GENUS_CORE_ID=pi-core ./deploy/pi_clock_check.sh
GENUS_DB_PATH="$HOME/.genus/genus.sqlite3" .venv/bin/genus operation list
```

## Status Repository

`GENUS_PI_STATUS` is the intended off-device exchange repository for anchors
and health summaries. It must not receive the SQLite database.

Published content:

- `anchors/*.json` - offline ledger anchors
- `status/<core_id>/latest.json` - structured counts, seal head, and integrity
  result

The public status export intentionally omits local filesystem paths, raw
`genus doctor` output, and recent event timelines. Keep the SQLite database and
local logs private on the Pi.

First set up write access from the Pi to GitHub, preferably with a repository
deploy key that has write access only to `WoltLab51/GENUS_PI_STATUS`.

From Windows PowerShell on the workstation, create or reuse that Pi-side key:

```powershell
.\deploy\setup_pi_status_key.ps1 -HostName ronny@pi.local -CoreId pi-core
```

If PowerShell script execution is disabled:

```powershell
.\deploy\setup_pi_status_key.cmd -HostName ronny@pi.local -CoreId pi-core
```

Copy the printed public key into GitHub:

- repository: `WoltLab51/GENUS_PI_STATUS`
- path: `Settings -> Deploy keys -> Add deploy key`
- title: `pi-core status publisher`
- required checkbox: `Allow write access`

Then publish from Windows PowerShell:

```powershell
.\deploy\publish_pi_status.ps1 -HostName ronny@pi.local -CoreId pi-core
```

The Pi synchronizes its local `GENUS_PI_STATUS` checkout to `origin/main`
before each publish. That repository is treated as generated exchange output,
so failed prior publishes or manual redactions on GitHub do not create a
long-lived divergent local branch.

Or, if PowerShell script execution is disabled:

```powershell
.\deploy\publish_pi_status.cmd -HostName ronny@pi.local -CoreId pi-core
```

Or publish manually inside an SSH session:

```bash
cd "$HOME/GENUS_PI_SEED"
GENUS_CORE_ID=pi-core ./deploy/pi_publish_status.sh
```

To add daily status publishing to the GENUS cron block:

```bash
cd "$HOME/GENUS_PI_SEED"
GENUS_CORE_ID=pi-core GENUS_ENABLE_STATUS_PUBLISH=1 ./deploy/pi_install_cron.sh
```

From Windows PowerShell:

```powershell
.\deploy\deploy_to_pi.ps1 -HostName ronny@pi.local -CoreId pi-core -InstallCron -EnableStatusPublish
```

## Manual Routine Collection

The cron script installs this routine automatically. The equivalent manual
entries are:

```cron
*/5 * * * * cd "$GENUS_REPO_DIR" && echo "[TICK] observe-all $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ)" >> "$GENUS_LOG_DIR/cron.log" 2>&1 && .venv/bin/genus observe-all >> "$GENUS_LOG_DIR/cron.log" 2>&1
1-59/5 * * * * cd "$GENUS_REPO_DIR" && echo "[TICK] state-refresh $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ)" >> "$GENUS_LOG_DIR/cron.log" 2>&1 && .venv/bin/genus state refresh >> "$GENUS_LOG_DIR/cron.log" 2>&1
```
