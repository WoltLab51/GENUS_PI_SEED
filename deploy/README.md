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
git clone https://github.com/WoltLab51/GENUS_PI_SEED.git /home/pi/GENUS_PI_SEED
cd /home/pi/GENUS_PI_SEED
GENUS_CORE_ID=pi-core ./deploy/pi_deploy.sh
GENUS_CORE_ID=pi-core ./deploy/pi_install_cron.sh
```

Use a stable `GENUS_CORE_ID`. Anchor files are long-lived witness artifacts, so
the ID should name this specific GENUS core, not just a temporary hostname.

## Deploy From Windows

From the local workstation:

```powershell
.\deploy\deploy_to_pi.ps1 -HostName pi@pi.local -CoreId pi-core -InstallCron
```

Run this command in Windows PowerShell on the workstation, not inside the SSH
session on the Pi. Inside SSH, use the `.sh` scripts directly.

Useful overrides:

```powershell
.\deploy\deploy_to_pi.ps1 `
  -HostName pi@192.168.178.40 `
  -RepoDir /home/pi/GENUS_PI_SEED `
  -DbPath /home/pi/.genus/genus.sqlite3 `
  -AnchorDir /home/pi/.genus/anchors `
  -StatusRepoDir /home/pi/GENUS_PI_STATUS `
  -CoreId pi-core
```

## Pi-Side Deploy Script

`pi_deploy.sh` can also be run directly over SSH:

```bash
ssh pi@pi.local 'cd /home/pi/GENUS_PI_SEED && GENUS_CORE_ID=pi-core ./deploy/pi_deploy.sh'
```

Environment knobs:

- `GENUS_DB_PATH` defaults to `/home/pi/.genus/genus.sqlite3` when run as user
  `pi`.
- `GENUS_ANCHOR_DIR` defaults to `/home/pi/.genus/anchors`.
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
cd /home/pi/GENUS_PI_SEED
GENUS_CORE_ID=pi-core ./deploy/pi_install_cron.sh
```

Schedule:

- every 5 minutes: `genus observe-all`
- every 5 minutes, one minute later: `genus state refresh`
- daily at 03:17: `genus experience scan`
- daily at 03:27: `genus doctor`

The script replaces only the block between `BEGIN GENUS_PI_SEED` and
`END GENUS_PI_SEED`. Other crontab entries stay untouched.

Logs:

```bash
tail -f /home/pi/.genus/logs/cron.log
tail -f /home/pi/.genus/logs/doctor.log
```

## Status Repository

`GENUS_PI_STATUS` is the intended off-device exchange repository for anchors
and health summaries. It must not receive the SQLite database.

Published content:

- `anchors/*.json` - offline ledger anchors
- `status/<core_id>/latest.json` - structured counts, seal head, recent event
  metadata, and integrity result
- `doctor/<core_id>/latest.txt` - human-readable doctor report

First set up write access from the Pi to GitHub, preferably with a repository
deploy key that has write access only to `WoltLab51/GENUS_PI_STATUS`.

Then publish manually:

```bash
cd /home/pi/GENUS_PI_SEED
GENUS_CORE_ID=pi-core ./deploy/pi_publish_status.sh
```

To add daily status publishing to the GENUS cron block:

```bash
cd /home/pi/GENUS_PI_SEED
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
*/5 * * * * cd /home/pi/GENUS_PI_SEED && GENUS_DB_PATH=/home/pi/.genus/genus.sqlite3 .venv/bin/genus observe-all >> /home/pi/.genus/logs/cron.log 2>&1
1-59/5 * * * * cd /home/pi/GENUS_PI_SEED && GENUS_DB_PATH=/home/pi/.genus/genus.sqlite3 .venv/bin/genus state refresh >> /home/pi/.genus/logs/cron.log 2>&1
```
