import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which("bash")
if BASH is None and os.name == "nt":
    candidate = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git/bin/bash.exe"
    BASH = str(candidate) if candidate.is_file() else None


def _write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _bash_path(path: Path) -> str:
    value = path.resolve().as_posix()
    if os.name == "nt" and len(value) > 2 and value[1] == ":":
        return f"/{value[0].lower()}{value[2:]}"
    return value


def _fixture(tmp_path: Path, *, dirty=False, backup_ok=True, test_ok=True, health_ok=True):
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    bin_dir = tmp_path / "bin"
    state = tmp_path / "git-head"
    log = tmp_path / "calls.log"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "deploy").mkdir()
    (repo / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    shutil.copy(ROOT / "deploy" / "pi_safe_update.sh", repo / "deploy" / "pi_safe_update.sh")
    (repo / "deploy" / "pi_safe_update.sh").chmod(0o755)
    (home / ".genus").mkdir(parents=True)
    (home / ".genus" / "genus.sqlite3").write_bytes(b"ledger-unchanged")
    (home / ".genus" / "core_id").write_text("test-core\n", encoding="utf-8")
    backup_dir = home / "genus-sd-backup"
    backup_dir.mkdir()
    state.write_text("old\n", encoding="utf-8")
    log.write_text("", encoding="utf-8")

    _write_executable(
        bin_dir / "git",
        """#!/usr/bin/env bash
set -u
printf 'git %s\\n' "$*" >> "$CALL_LOG"
case "$1 $2" in
  'status --porcelain=v1') [ "${DIRTY:-0}" = 1 ] && echo ' M local.txt'; exit 0 ;;
  'status --short') echo ' M local.txt'; exit 0 ;;
  'branch --show-current') echo main; exit 0 ;;
  'rev-parse HEAD') cat "$STATE_FILE"; exit 0 ;;
  'rev-parse origin/main') echo new; exit 0 ;;
  'ls-remote --exit-code') printf 'new\\trefs/heads/main\\n'; exit 0 ;;
  'fetch origin') exit 0 ;;
  'merge-base --is-ancestor') exit 0 ;;
  'merge --ff-only') echo new > "$STATE_FILE"; exit 0 ;;
  'diff --quiet') exit "${DEPS_CHANGED:-0}" ;;
  'reset --keep') echo "$3" > "$STATE_FILE"; exit 0 ;;
esac
exit 2
""",
    )
    _write_executable(
        bin_dir / "systemctl",
        """#!/usr/bin/env bash
printf 'systemctl %s head=%s\\n' "$*" "$(cat "$STATE_FILE")" >> "$CALL_LOG"
case "$1" in
  is-active) exit 0 ;;
  restart) exit 0 ;;
esac
exit 1
""",
    )
    _write_executable(
        repo / ".venv" / "bin" / "python",
        """#!/usr/bin/env bash
printf 'python %s head=%s\\n' "$*" "$(cat "$STATE_FILE")" >> "$CALL_LOG"
if [ "$*" = '-m pytest -q' ] && [ "${TEST_OK:-1}" != 1 ]; then exit 9; fi
exit 0
""",
    )
    _write_executable(
        repo / ".venv" / "bin" / "genus",
        """#!/usr/bin/env bash
printf 'genus %s head=%s\\n' "$*" "$(cat "$STATE_FILE")" >> "$CALL_LOG"
if [ "$1" = doctor ] && [ "$(cat "$STATE_FILE")" = new ] && [ "${HEALTH_OK:-1}" != 1 ]; then exit 8; fi
exit 0
""",
    )
    _write_executable(
        repo / "deploy" / "backup.sh",
        """#!/usr/bin/env bash
printf 'backup head=%s\\n' "$(cat "$STATE_FILE")" >> "$CALL_LOG"
[ "${BACKUP_OK:-1}" = 1 ] || exit 7
sleep 0.02
printf snapshot > "$GENUS_SD_BACKUP/genus-test.sqlite3"
""",
    )

    env = {
        **os.environ,
        "PATH": f"{_bash_path(bin_dir)}:/usr/bin:/bin",
        "HOME": str(home),
        "GENUS_HOME": str(home),
        "GENUS_REPO_DIR": str(repo),
        "GENUS_DB_PATH": str(home / ".genus" / "genus.sqlite3"),
        "GENUS_SD_BACKUP": str(backup_dir),
        "GENUS_UPDATE_BACKUP_SCRIPT": str(repo / "deploy" / "backup.sh"),
        "GENUS_UPDATE_SUDO": "",
        "GENUS_UPDATE_GIT": _bash_path(bin_dir / "git"),
        "GENUS_UPDATE_SYSTEMCTL": _bash_path(bin_dir / "systemctl"),
        "STATE_FILE": str(state),
        "CALL_LOG": str(log),
        "DIRTY": "1" if dirty else "0",
        "BACKUP_OK": "1" if backup_ok else "0",
        "TEST_OK": "1" if test_ok else "0",
        "HEALTH_OK": "1" if health_ok else "0",
    }
    return repo, home, state, log, env


def _run(repo: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [BASH, str(repo / "deploy" / "pi_safe_update.sh"), *args],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


pytestmark = pytest.mark.skipif(BASH is None, reason="needs bash")
posix_only = pytest.mark.skipif(os.name == "nt", reason="validates POSIX permissions and tools")


@posix_only
def test_dirty_worktree_aborts_before_backup(tmp_path):
    repo, _, state, log, env = _fixture(tmp_path, dirty=True)
    result = _run(repo, env)

    assert result.returncode == 65
    assert state.read_text().strip() == "old"
    assert "backup" not in log.read_text()


@posix_only
def test_missing_backup_aborts_before_fetch_or_update(tmp_path):
    repo, _, state, log, env = _fixture(tmp_path, backup_ok=False)
    result = _run(repo, env)

    assert result.returncode != 0
    assert state.read_text().strip() == "old"
    calls = log.read_text()
    assert "backup head=old" in calls
    assert "git fetch" not in calls
    assert "git merge --ff-only" not in calls


@posix_only
def test_failed_tests_roll_back_before_new_version_restart(tmp_path):
    repo, _, state, log, env = _fixture(tmp_path, test_ok=False)
    result = _run(repo, env)

    assert result.returncode == 9
    assert state.read_text().strip() == "old"
    calls = log.read_text().splitlines()
    assert any("python -m pytest -q head=new" in line for line in calls)
    assert not any("systemctl restart" in line and "head=new" in line for line in calls)
    assert any("systemctl restart" in line and "head=old" in line for line in calls)


@posix_only
def test_failed_healthcheck_rolls_back_and_restarts_old_version(tmp_path):
    repo, _, state, log, env = _fixture(tmp_path, health_ok=False)
    result = _run(repo, env)

    assert result.returncode == 8
    assert state.read_text().strip() == "old"
    calls = log.read_text()
    assert "genus doctor head=new" in calls
    assert "git reset --keep old" in calls
    assert "genus doctor head=old" in calls


@posix_only
def test_rollback_preserves_database_and_configuration(tmp_path):
    repo, home, state, _, env = _fixture(tmp_path, health_ok=False)
    db = home / ".genus" / "genus.sqlite3"
    config = home / ".genus" / "core_id"
    before = (db.read_bytes(), config.read_bytes())

    result = _run(repo, env)

    assert result.returncode != 0
    assert state.read_text().strip() == "old"
    assert (db.read_bytes(), config.read_bytes()) == before
    snapshots = list((home / "genus-sd-backup").glob("update-config-*/core_id"))
    assert len(snapshots) == 1
    assert snapshots[0].read_bytes() == before[1]


@posix_only
def test_dry_run_makes_no_backup_fetch_or_update(tmp_path):
    repo, _, state, log, env = _fixture(tmp_path)
    result = _run(repo, env, "--dry-run")

    assert result.returncode == 0
    assert state.read_text().strip() == "old"
    calls = log.read_text()
    assert "backup" not in calls
    assert "git fetch" not in calls
    assert "git merge --ff-only" not in calls


def test_status_script_is_strict_and_reports_required_fields():
    script = (ROOT / "deploy" / "genus_status.sh").read_text(encoding="utf-8")

    assert "set -Eeuo pipefail" in script
    for label in (
        "Host", "Zeit", "GENUS", "Branch", "Commit", "Git", "Dienst", "CPU", "RAM",
        "Speicher", "CPU-Temp", "Datenbank", "Backup", "Fehler (letzte 5)",
    ):
        assert label in script
