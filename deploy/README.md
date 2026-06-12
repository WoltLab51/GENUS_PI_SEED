# GENUS Pi Deployment

This folder contains the small, boring deployment path for a Raspberry Pi.

No daemon, no web API, no automatic remote execution by GENUS itself:

- GitHub `main` is the source of code truth.
- The Pi pulls `main` by fast-forward only.
- The Pi runs tests before accepting the deploy.
- The Pi verifies integrity, sealing, replay, and optionally exports an anchor.

## First Pi Setup

```bash
sudo apt update
sudo apt install -y git python3 python3-venv
git clone https://github.com/WoltLab51/GENUS_PI_SEED.git /home/pi/GENUS_PI_SEED
cd /home/pi/GENUS_PI_SEED
GENUS_CORE_ID=pi-core ./deploy/pi_deploy.sh
```

Use a stable `GENUS_CORE_ID`. Anchor files are long-lived witness artifacts, so
the ID should name this specific GENUS core, not just a temporary hostname.

## Deploy From Windows

From the local workstation:

```powershell
.\deploy\deploy_to_pi.ps1 -HostName pi@pi.local -CoreId pi-core
```

Useful overrides:

```powershell
.\deploy\deploy_to_pi.ps1 `
  -HostName pi@192.168.178.40 `
  -RepoDir /home/pi/GENUS_PI_SEED `
  -DbPath /home/pi/.genus/genus.sqlite3 `
  -AnchorDir /home/pi/.genus/anchors `
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
deploys.

## Routine Collection

After deployment, keep collection boring and explicit:

```cron
*/5 * * * * cd /home/pi/GENUS_PI_SEED && GENUS_DB_PATH=/home/pi/.genus/genus.sqlite3 .venv/bin/genus observe-all >> /home/pi/.genus/cron.log 2>&1
*/5 * * * * cd /home/pi/GENUS_PI_SEED && GENUS_DB_PATH=/home/pi/.genus/genus.sqlite3 .venv/bin/genus state refresh >> /home/pi/.genus/cron.log 2>&1
```
