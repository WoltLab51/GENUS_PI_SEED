from __future__ import annotations

import getpass
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy" / "pi_a0_3c_runtime.sh"
BASH = shutil.which("bash")
if BASH is None and os.name == "nt":
    candidate = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git/bin/bash.exe"
    BASH = str(candidate) if candidate.is_file() else None

pytestmark = pytest.mark.skipif(BASH is None, reason="needs bash")
posix_only = pytest.mark.skipif(os.name == "nt", reason="validates POSIX filesystem semantics")


def _bash_path(path: Path) -> str:
    value = path.resolve().as_posix()
    if os.name == "nt" and len(value) > 2 and value[1] == ":":
        return f"/{value[0].lower()}{value[2:]}"
    return value


def _script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _function(name: str) -> str:
    script = _script()
    starts = list(re.finditer(r"(?m)^([A-Za-z_]\w*)\(\) ([{(])\n", script))
    match = next((item for item in starts if item.group(1) == name), None)
    assert match is not None, name
    end = next(
        (item.start() for item in starts if item.start() > match.start()), len(script)
    )
    return script[match.end() : end]


def _env(tmp_path: Path) -> dict[str, str]:
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    state = home / ".genus" / "runtime-a0.3c"
    home.mkdir(exist_ok=True)
    repo.mkdir(exist_ok=True)
    return {
        **os.environ,
        "GENUS_USER": getpass.getuser(),
        "GENUS_HOME": _bash_path(home),
        "GENUS_REPO_DIR": _bash_path(repo),
        "GENUS_A03C_STATE_ROOT": _bash_path(state),
        "GENUS_A03C_RUNTIME_PREFIX": _bash_path(tmp_path / "private-runtime"),
        "GENUS_A03C_TEST_MODE": "1",
    }


def _run(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [BASH, _bash_path(SCRIPT), *args],
        env=_env(tmp_path),
        text=True,
        capture_output=True,
        check=False,
    )


def _source(tmp_path: Path, command: str, *, extra_env: dict[str, str] | None = None):
    env = _env(tmp_path)
    env["GENUS_A03C_SOURCE_ONLY"] = "1"
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [BASH, "-c", f"source '{_bash_path(SCRIPT)}'; {command}"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_script_is_strict_and_syntactically_valid():
    assert "set -Eeuo pipefail" in _script()
    result = subprocess.run(
        [BASH, "-n", _bash_path(SCRIPT)], text=True, capture_output=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_official_python_and_sqlite_artifacts_are_fully_pinned():
    script = _script()
    assert 'PYTHON_VERSION="3.13.15"' in script
    assert 'PYTHON_ARCHIVE="Python-${PYTHON_VERSION}.tar.xz"' in script
    assert "1e66a7945a48390ee4c2a4268a0e4185884059a13c4aab6d148aa208deea4a76" in script
    assert 'SQLITE_NUMBER="3530400"' in script
    assert 'SQLITE_ARCHIVE="sqlite-autoconf-${SQLITE_NUMBER}.tar.gz"' in script
    assert "454e45f61c6bd75b7420e7190732dea03ce6639c63ada47bbc592f67fc340338" in script
    assert (
        "2026-07-24 19:02:57 bf7c7f30031888f4e796e429ab3978879485813aaca6f641c7b33e4e09459bcc"
    ) in script


def test_bootstrap_covers_private_python_sqlite_and_aarch64_wheel_builds():
    script = _script()
    for package in (
        "cmake",
        "ninja-build",
        "psmisc",
        "libgdbm-dev",
        "libgdbm-compat-dev",
        "libexpat1-dev",
    ):
        assert package in script


def test_runtime_is_private_and_never_injects_loader_environment():
    script = _script()
    assert "/opt/genus/runtime/cpython-${PYTHON_VERSION}-sqlite-${SQLITE_VERSION}" in script
    assert '--prefix="$RUNTIME_PREFIX"' in script
    assert "Library runpath: [$RUNTIME_PREFIX/lib]" in script
    # Genau eine bewusste Ausnahme (Live-Fund 2026-08-20): Der Bau braucht einen
    # bauzeitlichen Suchpfad auf den GESTAGTEN Prefix, weil CPythons Import-Pruefung
    # sonst am noch unveroeffentlichten RUNPATH scheitert. Die veroeffentlichte
    # Runtime bleibt davon unberuehrt und loest allein ueber ihren RUNPATH auf.
    loader = re.findall(r"(?m)^\s*(?:export\s+)?LD_(?:LIBRARY_PATH|PRELOAD)=.*", script)
    assert loader == ['        export LD_LIBRARY_PATH="$stage$RUNTIME_PREFIX/lib"'], loader
    assert loader[0].strip() in _function("build_runtime")
    for forbidden in ("/usr/lib/libsqlite", "/lib/libsqlite", "ldconfig"):
        assert forbidden not in script


def test_status_json_is_hermetic_and_contains_no_private_paths(tmp_path):
    result = _run(tmp_path, "status", "--json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {
        "active": "",
        "previous": "",
        "runtime_present": False,
        "staged": "",
    }
    assert str(tmp_path) not in result.stdout


def test_stage_builds_venvs_at_final_path_never_renames_them():
    stage = _function("stage_set")
    assert '"$RUNTIME_PREFIX/bin/python3.13" -m venv "$set/core"' in stage
    assert '"$RUNTIME_PREFIX/bin/python3.13" -m venv "$set/embed"' in stage
    assert 'building="$SETS_ROOT/.building-$manifest"' in stage
    assert ".pending-$manifest" not in stage
    assert 'mv -T -- "$pending"' not in stage
    assert "build_wheelhouse" in stage and "install_offline_lock" in stage


def test_console_script_shebangs_are_bound_to_the_final_manifest_set():
    stage = _function("stage_set")
    creation = stage.index('-m venv "$set/core"')
    editable = stage.index('-e "$REPO_DIR"')
    sealing = stage.index('seal_set_modes "$set"')
    assert creation < editable < sealing


def test_wheel_lock_tree_and_bootstrap_are_manifest_bound():
    script = _script()
    for contract in (
        "requirements-core.lock",
        "requirements-embed.lock",
        "wheels-core.sha256",
        "wheels-embed.sha256",
        "tree.inventory",
        "BUILD-BOOTSTRAP.lock",
        "repo_tree",
        "bootstrap_inventory_sha256",
    ):
        assert contract in script
    assert "--no-index --no-deps" in script
    assert "sha256sum -c ../wheels-core.sha256" in script
    assert "manifest id is not reproducible from bound inputs" in script
    bootstrap = _function("bootstrap_build_dependencies")
    assert 'as_root "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$APT_GET_BIN" update' in bootstrap
    assert "DEBIAN_FRONTEND=noninteractive" in bootstrap


def test_runtime_publication_is_inventory_bound_durable_and_recoverable():
    build = _function("build_runtime")
    durable = build.index('durably_sync_tree "$RUNTIME_PENDING"')
    marker = build.index('write_runtime_publication_marker "$inventory_hash"')
    move = build.index('"$ROOT_MV_BIN" -T -- "$RUNTIME_PENDING" "$RUNTIME_PREFIX"')
    probe = build.index("verify_runtime_prefix", move)
    finalize = build.index('"$ROOT_RM_BIN" -f -- "$RUNTIME_PUBLICATION"', probe)
    assert durable < marker < move < probe < finalize
    assert 'runtime_tree_inventory "$stage_runtime" > "$build/runtime.inventory.tmp"' in build
    assert 'install -m 0644 "$build/runtime.inventory.tmp"' in build
    assert 'verify_runtime_tree_inventory "$RUNTIME_PENDING"' in build
    recovery = _function("recover_runtime_publication")
    assert "quarantine_runtime_path" in recovery
    assert recovery.count('"$ROOT_SYNC_BIN" -f "$RUNTIME_PARENT"') >= 3
    assert 'runtime_probe "$stage$RUNTIME_PREFIX' not in build


def test_activation_requires_external_private_readiness_manifest_and_invocation():
    script = _script()
    assert "activate EXPECTED_COMMIT READINESS_MANIFEST [SET_MANIFEST]" in script
    verify = _function("verify_readiness_manifest")
    assert 'stat -c %a "$readiness")" = 600' in verify
    assert "experiments.a0_3c manifest-verify" in verify
    assert '--expected-invocation "$set/core/bin/python"' in verify
    switch = _function("switch_with_quiescence")
    assert switch.index("verify_readiness_manifest") < switch.index("fresh_backup_receipt")


def test_activation_is_exact_clean_including_untracked_files():
    gate = _function("assert_expected_commit")
    assert "--untracked-files=all" in gate
    assert "--untracked-files=no" not in gate


def test_single_active_selector_controls_both_stable_pointer_directories():
    create = _function("create_pointer_dir")
    assert '"$STATE_ROOT/active/$role" "$pointer/current"' in create
    assert '"current/$name" "$pointer/$name"' in create
    switch = _function("switch_with_quiescence")
    assert switch.count('atomic_link "sets/$target_manifest" "$ACTIVE_LINK"') == 1
    assert "CORE_POINTER/current" not in switch and "EMBED_POINTER/current" not in switch


def test_split_filesystem_legacy_moves_stay_within_each_parent():
    migrate = _function("prepare_legacy_pointer_unit")
    assert 'mv -T -- "$CORE_POINTER" "$MIGRATION_CORE_BACKUP"' in migrate
    assert 'mv -T -- "$EMBED_POINTER" "$MIGRATION_EMBED_BACKUP"' in migrate
    assert 'mv -T -- "$CORE_POINTER" "$EMBED_POINTER"' not in migrate
    for contract in ("migration.pending", "tree.inventory", "runtime.json", "manifest.json"):
        assert contract in migrate


def test_rollback_refuses_candidate_toggle_and_never_rolls_back_data():
    rollback = _function("rollback_runtime")
    assert "^legacy-[a-f0-9]{64}$" in rollback
    assert "activate+Readiness" in rollback
    for forbidden in ("sqlite", "DB_PATH", "replay", "reseal", "seal-init", "checkpoint"):
        assert forbidden not in rollback.lower()


def test_resume_failure_stops_services_before_pointer_restore():
    switch = _function("switch_with_quiescence")
    cleanup = switch[
        switch.index("cleanup_switch()") : switch.index("trap 'cleanup_switch $?' EXIT")
    ]
    assert "recover_pending_activation" in cleanup
    recovery = _function("recover_pending_activation")
    assert recovery.index("remove_autostart_approval") < recovery.index("stop_all_genus_units")
    assert recovery.index("stop_all_genus_units") < recovery.index("prove_no_db_handles")
    assert recovery.index("prove_no_db_handles") < recovery.index("restore_selector_from_journal")
    assert recovery.index("restore_selector_from_journal") < recovery.index(
        "start_recorded_services"
    )
    assert recovery.index("start_recorded_services") < recovery.index(" resume")
    normal = switch[
        switch.index("start_previous_services", switch.index("trap 'cleanup_switch $?' EXIT")) :
    ]
    assert normal.index("start_previous_services") < normal.index(" resume")
    assert normal.index(" resume") < normal.index("SERVICES_RESTARTED=0")


def test_quiescence_covers_cron_fallback_handles_maps_and_nrestarts():
    script = _script()
    services = re.search(r"(?m)^SERVICES=\(([^)]*)\)", script)
    assert services is not None and "cron.service" not in services.group(1)
    assert "capture_activation_crontab" in script
    assert "disable_genus_cron_block" in script
    assert "restore_genus_cron_block" in script
    assert 'CRON_BEGIN="# BEGIN GENUS_PI_SEED"' in script
    assert "genus-telegram-bot-fallback.service" in script
    assert 'entry / "maps"' in script and 'entry / "exe"' in script
    assert "prove_no_old_runtime_processes" in _function("switch_with_quiescence")
    assert "prove_no_db_handles" in _function("switch_with_quiescence")
    assert 'restarts" != "${old_restarts[$index]}' in script
    process_probe = _function("prove_no_old_runtime_processes")
    assert '"$SYSTEM_PYTHON_BIN" -I -P' in process_probe
    assert 'as_root "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin' in process_probe
    assert 'as_root env -i PATH=/usr/bin:/bin "$CORE_POINTER/bin/python"' not in script
    assert "inspection_errors" in process_probe
    assert 'raise SystemExit("process inspection was incomplete")' in process_probe


def test_restore_handler_covers_explicit_exit_set_e_and_signals():
    switch = _function("switch_with_quiescence")
    exit_trap = switch.index("trap 'cleanup_switch $?' EXIT")
    pause = switch.index(' pause --reason "A0.3c runtime switch"')
    stop = switch.index("stop_services", pause)
    assert exit_trap < pause < stop
    assert "trap 'cleanup_switch 130' INT" in switch
    assert "trap 'cleanup_switch 143' TERM" in switch
    assert "trap - EXIT INT TERM" in switch
    assert "trap cleanup_switch ERR" not in switch


def test_postflight_attests_live_bot_learner_and_activation_evidence():
    postflight = _function("attest_restarted_services")
    activation = _function("write_activation_receipt")
    switch = _function("switch_with_quiescence")
    assert "consecutive=$((consecutive + 1))" in postflight
    assert "genus-telegram-bot.service" in postflight
    assert "bot process does not use the selected private runtime" in postflight
    assert "genus-learner.service" in postflight
    assert "learner process is not the pinned repository script" in postflight
    for field in (
        "previous_set_manifest",
        "activated_set_manifest",
        "backup_receipt_sha256",
        "readiness_manifest_sha256",
        "verification_receipt_sha256",
        "postflight_receipt_sha256",
        "service_state_sha256",
    ):
        assert field in activation
    normal = switch[
        switch.index("start_previous_services", switch.index("trap 'cleanup_switch $?' EXIT")) :
    ]
    assert normal.index(" resume") < normal.index("attest_restarted_services")
    assert normal.index("attest_restarted_services") < normal.index("SERVICES_RESTARTED=0")


@posix_only
def test_db_handle_probe_does_not_pass_missing_wal_or_shm(tmp_path):
    env = _env(tmp_path)
    db = Path(env["GENUS_HOME"]) / ".genus" / "genus.sqlite3"
    db.parent.mkdir(parents=True)
    db.write_bytes(b"db")
    fake = tmp_path / "fuser"
    log = tmp_path / "fuser.log"
    fake.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$CALL_LOG"\nexit 1\n')
    fake.chmod(0o755)
    result = _source(
        tmp_path,
        "prove_no_db_handles",
        extra_env={"GENUS_A03C_FUSER": _bash_path(fake), "CALL_LOG": _bash_path(log)},
    )
    assert result.returncode == 0, result.stderr
    called = log.read_text()
    assert "genus.sqlite3" in called
    assert "genus.sqlite3-wal" not in called
    assert "genus.sqlite3-shm" not in called


@posix_only
def test_operator_lock_rejects_a_concurrent_mutation(tmp_path):
    env = _env(tmp_path)
    env["GENUS_A03C_SOURCE_ONLY"] = "1"
    source = f"source '{_bash_path(SCRIPT)}'; init_user_roots; acquire_operator_lock"
    holder = subprocess.Popen(
        [BASH, "-c", f"{source}; echo ready; read -r _"],
        env=env,
        text=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert holder.stdout is not None and holder.stdout.readline().strip() == "ready"
    contender = subprocess.run(
        [BASH, "-c", source], env=env, text=True, capture_output=True, check=False
    )
    assert contender.returncode == 75
    assert "Operator-Lock" in contender.stderr
    assert holder.stdin is not None
    holder.stdin.write("done\n")
    holder.stdin.flush()
    assert holder.wait(timeout=10) == 0


def test_stable_core_and_embed_invocations_are_both_attested():
    attest = _function("attest_active_pointer_unit")
    assert '"$CORE_POINTER/bin/python"' in attest
    assert '"$EMBED_POINTER/bin/python"' in attest
    assert "expected-invocation" in attest
    assert "sys._base_executable" in attest


def test_runtime_identity_tree_and_db_handle_gates_are_fail_closed():
    probe = _function("runtime_probe")
    prefix = _function("verify_runtime_prefix")
    handles = _function("prove_no_db_handles")
    pointers = _function("create_pointer_dir")
    assert "sys.version_info[:3] != (3, 13, 15)" in probe
    assert 'actual="$(realpath -e -- "$RUNTIME_PREFIX")"' in prefix
    assert '"$ROOT_FIND_BIN" "$RUNTIME_PREFIX" -xdev ! -user root' in prefix
    assert "runtime symlink escapes private prefix" in prefix
    assert "runtime tree inspection incomplete" in prefix
    assert 'output="$(as_root "$FUSER_BIN"' in handles
    assert 'sync -f "$pointer/.a03c-pointer-unit"' in pointers
    assert 'fsync_dir "$pointer"' in pointers


def test_activation_journal_and_autostart_approval_are_durable_and_bound():
    create = _script()
    validate = _function("validate_activation_journal")
    approval = _function("validate_autostart_approval")
    switch = _function("switch_with_quiescence")
    assert "os.O_EXCL" in create and "os.O_NOFOLLOW" in create
    assert create.count("os.fsync") >= 2
    for contract in (
        "candidate_commit",
        "target_manifest_sha256",
        "readiness_sha256",
        "active_manifest_sha256",
        "cron_original_sha256",
    ):
        assert contract in create and contract in validate
    for stat_gate in ("stat -c %u", "stat -c %a", "stat -c %h"):
        assert stat_gate in validate
        assert stat_gate in approval
    assert "ACTIVE binding differs" in validate
    assert "start authorization ACTIVE binding differs" in approval
    assert switch.index("create_activation_journal") < switch.index(" pause --reason")
    assert switch.index("disable_genus_cron_block") < switch.index(" pause --reason")
    assert switch.index("install_systemd_autostart_guard") < switch.index(" pause --reason")
    assert switch.index("receipt-written") < switch.index("finalize_guarded_transition")
    boot_guard = _script()
    systemd_payload = _function("systemd_guard_payload")
    for contract in (
        "safe.directory",
        "active_manifest_sha256",
        "target_manifest_sha256",
        "readiness_sha256",
        "st_nlink",
        "O_NOFOLLOW",
    ):
        assert contract in boot_guard
    assert "ExecCondition=%s" in systemd_payload
    assert "BOOT_GUARD_PATH" in systemd_payload


def test_preexisting_pause_is_blocked_and_identity_receipt_is_activation_bound():
    pause_gate = _function("assert_not_previously_paused")
    activation = _function("write_activation_receipt")
    switch = _function("switch_with_quiescence")
    assert '"$CORE_POINTER/bin/genus" paused' in pause_gate
    assert "Runtimewechsel blockiert" in pause_gate
    assert "vorheriger Pausezustand ist nicht eindeutig lesbar" in pause_gate
    assert "active_identity_receipt_path" in activation
    assert "active_identity_receipt_sha256" in activation
    assert 'active_identity_receipt="$(attest_active_pointer_unit' in switch


@posix_only
def test_active_timer_does_not_require_service_only_pid_or_nrestarts(tmp_path):
    fake = tmp_path / "systemctl"
    unexpected = tmp_path / "unexpected"
    fake.write_text(
        """#!/bin/sh
unit="$2"
prop=""
shift 2
while [ "$#" -gt 0 ]; do
    if [ "$1" = -p ]; then prop="$2"; shift 2; else shift; fi
done
if [ "$unit" = genus-network-watchdog.timer ]; then
    case "$prop" in
        ActiveState) printf 'active\\n' ;;
        InvocationID) printf 'timer-invocation\\n' ;;
        ActiveEnterTimestampMonotonic) printf '123456\\n' ;;
        MainPID|NRestarts) printf '%s\\n' "$prop" >> "$UNEXPECTED"; exit 70 ;;
    esac
else
    [ "$prop" = ActiveState ] && printf 'inactive\\n'
fi
""",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    result = _source(
        tmp_path,
        'remember_services; printf "%s|%s|%s|%s\\n" "${active_services[*]}" '
        '"${old_pids[*]}" "${old_restarts[*]}" "${old_active_enters[*]}"',
        extra_env={
            "GENUS_A03C_SYSTEMCTL": _bash_path(fake),
            "UNEXPECTED": _bash_path(unexpected),
        },
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "genus-network-watchdog.timer|0|0|123456"
    assert not unexpected.exists()


@pytest.mark.parametrize(
    "phase",
    [
        "prepared",
        "guarded",
        "paused",
        "stopped",
        "legacy-ready",
        "swapped",
        "target-verified",
        "resumed",
        "postflight",
    ],
)
def test_each_unfinished_journal_phase_runs_fail_closed_recovery(tmp_path, phase):
    events = tmp_path / "events"
    repo = tmp_path / "repo"
    genus = repo / ".venv" / "bin" / "genus"
    journal = tmp_path / "home" / ".genus" / "runtime-a0.3c" / "activation.pending"
    genus.parent.mkdir(parents=True)
    journal.parent.mkdir(parents=True)
    genus.write_text(
        '#!/bin/sh\nprintf "genus:%s\\n" "$1" >> "$EVENT_LOG"\nexit 0\n',
        encoding="utf-8",
    )
    genus.chmod(0o700)
    journal.touch()
    command = r"""
recover_incomplete_migration() { printf 'migration\n' >> "$EVENT_LOG"; }
validate_activation_journal() { printf 'validate:%s\n' "${1:-strict}" >> "$EVENT_LOG"; }
journal_field() { [ "$1" = phase ] && printf '%s\n' "$TEST_PHASE"; }
install_systemd_autostart_guard() { printf 'guard\n' >> "$EVENT_LOG"; }
remove_autostart_approval() { printf 'approval-removed\n' >> "$EVENT_LOG"; }
disable_genus_cron_block() { printf 'cron-disabled\n' >> "$EVENT_LOG"; }
journal_service_lines() { printf 'genus-learner.service\n'; }
stop_all_genus_units() { printf 'services-stopped\n' >> "$EVENT_LOG"; }
prove_no_old_runtime_processes() { printf 'proc-gate\n' >> "$EVENT_LOG"; }
prove_no_db_handles() { printf 'fuser-gate\n' >> "$EVENT_LOG"; }
restore_selector_from_journal() { printf 'selectors-restored\n' >> "$EVENT_LOG"; }
write_autostart_approval() { printf 'approval-written\n' >> "$EVENT_LOG"; }
start_recorded_services() { printf 'services-restored:%s\n' "${recovery_services[*]}" >> "$EVENT_LOG"; }
attest_recovered_services() { printf 'services-attested\n' >> "$EVENT_LOG"; }
write_transition_completion_receipt() { printf 'completion-written\n' >> "$EVENT_LOG"; printf '/receipt\n'; }
validate_completion_receipt() { printf 'completion-validated\n' >> "$EVENT_LOG"; }
update_activation_journal() { printf 'journal:%s\n' "$1" >> "$EVENT_LOG"; }
finalize_guarded_transition() { printf 'finalized\n' >> "$EVENT_LOG"; rm -f "$ACTIVATION_JOURNAL"; }
recover_pending_activation
[ ! -e "$ACTIVATION_JOURNAL" ]
"""
    result = _source(
        tmp_path,
        command,
        extra_env={"EVENT_LOG": _bash_path(events), "TEST_PHASE": phase},
    )
    assert result.returncode == 0, result.stderr
    rows = events.read_text(encoding="utf-8").splitlines()
    assert rows == [
        "migration",
        "validate:1",
        "guard",
        "approval-removed",
        "cron-disabled",
        "genus:pause",
        "services-stopped",
        "proc-gate",
        "fuser-gate",
        "selectors-restored",
        "approval-written",
        "services-restored:genus-learner.service",
        "services-attested",
        "genus:resume",
        "completion-written",
        "completion-validated",
        "journal:receipt-written",
        "finalized",
    ]


@pytest.mark.parametrize(
    "resolver", ['selector_manifest "$ACTIVE_LINK"', "resolve_manifest active"]
)
def test_selector_rejects_path_traversal_even_with_a_safe_basename(tmp_path, resolver):
    manifest = "a" * 64
    result = _source(
        tmp_path,
        f"readlink() {{ printf 'sets/../../{manifest}\\n'; }}; {resolver}",
    )
    assert result.returncode in {65, 70}
    assert "exakt" in result.stderr


def test_split_filesystem_migration_restore_is_fsynced_before_journal_removal():
    persistent = _function("recover_incomplete_migration")
    in_process = _function("rollback_incomplete_migration")
    for body in (persistent, in_process):
        core_move = (
            body.index('mv -T -- "$core_backup" "$CORE_POINTER"')
            if "core_backup" in body
            else body.index('mv -T -- "$MIGRATION_CORE_BACKUP" "$CORE_POINTER"')
        )
        core_sync = body.index('fsync_dir "$(dirname "$CORE_POINTER")"', core_move)
        embed_move = (
            body.index('mv -T -- "$embed_backup" "$EMBED_POINTER"')
            if "embed_backup" in body
            else body.index('mv -T -- "$MIGRATION_EMBED_BACKUP" "$EMBED_POINTER"')
        )
        embed_sync = body.index('fsync_dir "$(dirname "$EMBED_POINTER")"', embed_move)
        journal_remove = (
            body.index('rm -f -- "$journal"', embed_sync)
            if '"$journal"' in body
            else body.index('rm -f -- "$STATE_ROOT/migration.pending"', embed_sync)
        )
        assert core_move < core_sync < journal_remove
        assert embed_move < embed_sync < journal_remove
        assert '[ ! -e "$core_backup" ]' in body or '[ ! -e "$MIGRATION_CORE_BACKUP" ]' in body


def test_root_python_probes_are_isolated_from_cwd_and_environment(tmp_path):
    script = _script()
    assert 'as_root "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN"' in script
    assert 'as_root env -i PATH=/usr/bin:/bin "$CORE_POINTER/bin/python"' not in script
    assert 'as_root "$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$python"' not in script
    assert script.count('"$SYSTEM_PYTHON_BIN" -I -P -') >= 4
    canary = tmp_path / "CANARY"
    (tmp_path / "pathlib.py").write_text(
        f"from pathlib import *\nopen({str(canary)!r}, 'w').write('loaded')\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-I", "-P", "-c", "import pathlib; print(pathlib.__file__)"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not canary.exists()


def test_privileged_program_overrides_are_test_only_and_root_owned_in_production():
    harden = _function("harden_privileged_boundary")
    validator = _function("validate_root_owned_program")
    assert 'GENUS_A03C_TEST_MODE:-0}" = 1' in harden
    assert 'GENUS_A03C_SOURCE_ONLY:-0}" = 1' in harden
    for variable, path in (
        ("SUDO_BIN", "/usr/bin/sudo"),
        ("SYSTEMCTL_BIN", "/usr/bin/systemctl"),
        ("FUSER_BIN", "/usr/bin/fuser"),
        ("GIT_BIN", "/usr/bin/git"),
        ("APT_GET_BIN", "/usr/bin/apt-get"),
        ("CRONTAB_BIN", "/usr/bin/crontab"),
    ):
        assert f'validate_root_owned_program "${variable}" {path}' in harden
    assert '"$candidate" = "$expected"' in validator
    assert "/usr/bin/readlink -f" in validator
    assert "/usr/bin/stat -Lc %u" in validator
    assert "8#$mode & 8#22" in validator


@posix_only
def test_production_crontab_override_is_rejected_without_executing_the_shadow(tmp_path):
    required = (
        "/usr/bin/sudo",
        "/usr/bin/systemctl",
        "/usr/bin/fuser",
        "/usr/bin/git",
        "/usr/bin/apt-get",
        "/usr/bin/python3",
        "/usr/bin/crontab",
    )
    if not all(Path(path).exists() for path in required):
        pytest.skip("canonical Pi tool inventory is unavailable")
    canary = tmp_path / "CRONTAB-CANARY"
    shadow = tmp_path / "crontab"
    shadow.write_text(f'#!/bin/sh\ntouch "{canary}"\n', encoding="utf-8")
    shadow.chmod(0o755)
    result = _source(
        tmp_path,
        "harden_privileged_boundary",
        extra_env={
            "GENUS_A03C_TEST_MODE": "0",
            "GENUS_A03C_RUNTIME_PREFIX": "/opt/genus/runtime/cpython-3.13.15-sqlite-3.53.4",
            "GENUS_A03C_CRONTAB": str(shadow),
        },
    )
    assert result.returncode == 77
    assert "crontab darf" in result.stderr
    assert not canary.exists()


def test_boot_guard_drops_uid_gid_before_any_evidence_or_git_read():
    script = _script()
    payload = script[
        script.index("write_boot_guard_payload()") : script.index("systemd_guard_payload()")
    ]
    main = payload[payload.index("def main():") :]
    assert '"gid": int(sys.argv[9])' in payload
    assert "os.setgroups([])" in payload
    assert 'os.setgid(CONFIG["gid"])' in payload
    assert 'os.setuid(CONFIG["uid"])' in payload
    assert main.index("drop_to_runtime_user()") < main.index("regular_bytes(")
    assert main.index("drop_to_runtime_user()") < main.index("subprocess.run(")
    assert '"$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin "$SYSTEM_PYTHON_BIN" -I -P' in payload
    assert 'command -v "$GIT_BIN"' not in payload


@posix_only
def test_git_fsmonitor_canary_documents_the_pre_drop_execution_boundary(tmp_path):
    git = shutil.which("git")
    if git is None:
        pytest.skip("git unavailable")
    repo = tmp_path / "repo"
    repo.mkdir()
    canary = tmp_path / "FSMONITOR-CANARY"
    hook = tmp_path / "fsmonitor-hook"
    hook.write_text(f'#!/bin/sh\nprintf invoked > "{canary}"\nexit 0\n', encoding="utf-8")
    hook.chmod(0o755)
    subprocess.run([git, "init", "-q", str(repo)], check=True)
    subprocess.run([git, "-C", str(repo), "config", "core.fsmonitor", str(hook)], check=True)
    subprocess.run([git, "-C", str(repo), "status", "--porcelain=v1"], check=True)
    assert canary.is_file(), "the configured fsmonitor is executable during git status"
    script = _script()
    payload = script[
        script.index("write_boot_guard_payload()") : script.index("systemd_guard_payload()")
    ]
    assert payload.index("drop_to_runtime_user()") < payload.index("subprocess.run(")


def test_oneshot_watchdog_is_stopped_but_never_persisted_as_restart_inventory():
    script = _script()
    services = re.search(r"(?m)^SERVICES=\(([^)]*)\)", script)
    autostarts = re.search(r"(?m)^AUTOSTART_UNITS=\(([^)]*)\)", script)
    assert services is not None and "genus-network-watchdog.service" not in services.group(1)
    assert autostarts is not None and "genus-network-watchdog.service" in autostarts.group(1)
    assert 'for service in "${AUTOSTART_UNITS[@]}"' in _function("stop_services")


def test_mutations_recover_under_one_idempotent_operator_lock():
    lock = _function("acquire_operator_lock")
    stage = _function("stage_set")
    rollback = _function("rollback_runtime")
    assert "OPERATOR_LOCK_HELD" in lock
    assert stage.index("acquire_operator_lock") < stage.index("recover_pending_activation")
    assert stage.index("recover_pending_activation") < stage.index("build_runtime")
    assert rollback.index("acquire_operator_lock") < rollback.index("recover_pending_activation")
    assert rollback.index("recover_pending_activation") < rollback.index("selector_manifest")


def test_candidate_set_and_boot_guard_bind_canonical_roles_and_stable_pointers():
    verify = _function("verify_set")
    boot = _script()
    assert '[ ! -L "$set/core" ] && [ ! -L "$set/embed" ]' in verify
    assert 'canonical_set" = "$SETS_ROOT/$manifest"' in verify
    for contract in (
        "runtime directory is not canonical",
        "runtime role escapes set",
        "pointer marker differs",
        "pointer current resolves to wrong role",
        "stable pointer member escapes role",
        "repo worktree is not exactly clean",
        "evidence file changed during read",
    ):
        assert contract in boot


def test_forward_legacy_migration_is_durable_and_fully_verified_before_completion():
    prepare = _function("prepare_legacy_pointer_unit")
    recovery = _function("recover_incomplete_migration")
    durable = _function("durably_sync_tree")
    pointer_publish = prepare.index('create_pointer_dir "$CORE_POINTER" core')
    for tree in (
        'durably_sync_tree "$MIGRATION_CORE_BACKUP"',
        'durably_sync_tree "$MIGRATION_EMBED_BACKUP"',
        'durably_sync_tree "$MIGRATION_LEGACY_SET"',
        'fsync_dir "$SETS_ROOT"',
        'verify_legacy_set "$legacy"',
    ):
        assert prepare.index(tree) < pointer_publish
    assert "os.fsync(fd)" in durable
    assert 'getattr(os, "O_NOFOLLOW", 0)' in durable
    assert "reversed(directories)" in durable
    completed = recovery[: recovery.index('if [ -f "$CORE_POINTER/.a03c-pointer-unit"')]
    assert 'readlink "$PREVIOUS_LINK"' in completed
    assert 'verify_legacy_set "$legacy"' in completed
    assert completed.count("pointer_dir_valid") >= 4
    assert completed.index('verify_legacy_set "$legacy"') < completed.index('rm -f -- "$journal"')


def test_finalize_and_receipt_reattest_failures_converge_fail_closed():
    script = _script()
    helper = script[
        script.index("force_pending_transition_fail_closed()") : script.index(
            "finalize_guarded_transition()"
        )
    ]
    for operation in (
        "install_systemd_autostart_guard",
        "systemd_autostart_guard_present",
        "remove_autostart_approval",
        "disable_genus_cron_block",
        " pause ",
        "stop_all_genus_units",
        "prove_no_old_runtime_processes",
        "prove_no_db_handles",
    ):
        assert operation in helper
    assert helper.index("remove_autostart_approval") < helper.index("disable_genus_cron_block")
    assert helper.index("disable_genus_cron_block") < helper.index(" pause ")
    assert helper.index(" pause ") < helper.index("stop_all_genus_units")
    recovery = _function("recover_pending_activation")
    assert "recovery_status=$?" in recovery
    assert "set -Eeuo pipefail" in recovery
    assert "force_pending_transition_fail_closed || true" not in recovery
    assert "|| exit $?" not in recovery
    assert recovery.index("set +e", recovery.index("local phase")) < recovery.index(
        "set -Eeuo pipefail"
    )
    assert recovery.index("set -Eeuo pipefail") < recovery.index("recovery_status=$?")
    assert '"$recovery_status"' in recovery
    clear = _function("clear_activation_state")
    assert 'rm -f -- "$ACTIVATION_JOURNAL"' in clear
    assert "ACTIVATION_CRON_SNAPSHOT" not in clear
    assert "ACTIVATION_CRON_DISABLED" not in clear


@pytest.mark.parametrize(("failure", "status"), [("inner", 1), ("attest", 83), ("finalize", 84)])
def test_receipt_written_error_preserves_status_journal_and_snapshots(tmp_path, failure, status):
    env = _env(tmp_path)
    state = tmp_path / "home" / ".genus" / "runtime-a0.3c"
    state.mkdir(parents=True)
    journal = state / "activation.pending"
    original = state / "activation.crontab.original"
    disabled = state / "activation.crontab.disabled"
    receipt = state / "receipt.json"
    events = state / "events"
    for path in (journal, original, disabled, receipt):
        path.write_text("evidence\n", encoding="utf-8")
    command = r"""
recover_incomplete_migration() { :; }
validate_activation_journal() { :; }
validate_autostart_approval() {
    if [ "$FAILURE" = inner ]; then
        printf 'inner-started\n' >> "$EVENT_LOG"
        false
        printf 'INNER_MASKED\n' >> "$EVENT_LOG"
    fi
}
journal_field() {
    case "$1" in
        phase) printf 'receipt-written\n' ;;
        activation_receipt_path) printf '%s\n' "$TEST_RECEIPT" ;;
        activation_receipt_sha256) printf 'bound-hash\n' ;;
    esac
}
sha256_file() { printf 'bound-hash\n'; }
validate_completion_receipt() { :; }
journal_service_lines() { printf 'genus-learner.service\n'; }
attest_recovered_services() {
    if [ "$FAILURE" = attest ]; then printf 'attest-failed\n' >> "$EVENT_LOG"; return 83; fi
}
finalize_guarded_transition() {
    if [ "$FAILURE" = finalize ]; then printf 'finalize-failed\n' >> "$EVENT_LOG"; return 84; fi
}
force_pending_transition_fail_closed() { printf 'fail-closed\n' >> "$EVENT_LOG"; return 0; }
recover_pending_activation
"""
    result = _source(
        tmp_path,
        command,
        extra_env={
            "EVENT_LOG": _bash_path(events),
            "FAILURE": failure,
            "TEST_RECEIPT": _bash_path(receipt),
        },
    )
    assert result.returncode == status, result.stderr
    rows = events.read_text(encoding="utf-8").splitlines()
    assert rows[-1] == "fail-closed"
    assert "INNER_MASKED" not in rows
    assert journal.is_file()
    assert original.is_file()
    assert disabled.is_file()


def test_all_embedded_python_contracts_compile():
    blocks = re.findall(r"<<'PY'\n(.*?)\nPY\n", _script(), re.S)
    assert len(blocks) >= 50
    for index, block in enumerate(blocks, start=1):
        compile(block, f"<pi-a0.3c-heredoc-{index}>", "exec")


def test_supply_chain_is_two_phase_fixed_origin_offline_and_sandboxed():
    script = _script()
    acquire = _function("acquire_locked_sources")
    prepare = _function("prepare_wheelhouse_inputs")
    build = _function("build_wheelhouse")
    sandbox = _function("sandbox_run")
    stage = _function("stage_set")
    assert 'PYPI_INDEX_URL="https://pypi.org/simple"' in script
    assert '"$ROOT_ENV_BIN" -i PATH=/usr/bin:/bin HOME="$STATE_ROOT"' in acquire
    assert 'parsed.hostname != "files.pythonhosted.org"' in acquire
    assert '"@" in item' in _function("build_backend_requirements")
    assert prepare.index("artifact_inventory") < prepare.index("seal_artifact_store")
    assert stage.index("SUPPLY_SEAL") < stage.index("build_wheelhouse")
    assert "EXPECTED_SUPPLY_SEAL" in stage and "fail" in stage
    assert build.index("verify_artifact_store") < build.index("sandbox_run")
    for contract in (
        "User=nobody",
        "Group=nogroup",
        "ProtectHome=yes",
        "ProtectSystem=strict",
        "PrivateNetwork=yes",
        "NoNewPrivileges=yes",
        "CapabilityBoundingSet=",
        "ReadWritePaths=$scratch/work $scratch/output",
        "InaccessiblePaths=$REPO_DIR $STATE_ROOT $DB_PATH",
        "PATH=/usr/bin:/bin",
        "TasksMax=512",
        "RuntimeMaxSec=4h",
    ):
        assert contract in sandbox
    assert "sandbox_canary" in build
    assert "root_artifact_inventory" in build
    assert "--no-index" in build


def test_manifest_binds_sources_backends_and_full_private_runtime():
    writer = _function("write_manifest")
    verifier = _function("verify_set")
    stage = _function("stage_set")
    for contract in (
        "source_inventories",
        "build_backend_inventories",
        "runtime_inventory_sha256",
        "executable_sha256",
        "stdlib_sha256",
        "whole_tree_sha256",
    ):
        assert contract in writer and contract in verifier
    for seed in (
        "core_sources=",
        "embed_sources=",
        "core_backends=",
        "embed_backends=",
        "runtime_inventory=",
        "runtime_python=",
        "runtime_stdlib=",
        "runtime_tree=",
    ):
        assert seed in stage and seed in verifier


def test_set_publication_uses_distinct_recovery_status_and_durable_order():
    stage = _function("stage_set")
    recovery = _function("recover_set_publication")
    marker = _function("write_set_publication_marker")
    assert "os.O_EXCL" in marker and "O_NOFOLLOW" in marker
    assert "os.fsync(fd)" in marker and "os.fsync(parent)" in marker
    assert "return 10" in recovery
    assert "( set -Eeuo pipefail; recover_set_publication" in stage
    assert 'case "$recovery_status"' in stage
    assert "10)" in stage
    seal = stage.index('seal_set_modes "$set"')
    durable = stage.index('durably_sync_tree "$set"', seal)
    verify = stage.index('verify_set "$manifest"', durable)
    remove = stage.index('rm -f -- "$building"', verify)
    staged = stage.index('atomic_link "sets/$manifest" "$STAGED_LINK"', remove)
    assert seal < durable < verify < remove < staged


def test_set_recovery_does_not_mask_inner_durability_failure(tmp_path):
    manifest = "a" * 64
    state = tmp_path / "home" / ".genus" / "runtime-a0.3c"
    set_path = state / "sets" / manifest
    marker = state / "sets" / f".building-{manifest}"
    set_path.mkdir(parents=True)
    marker.write_text("marker", encoding="utf-8")
    events = tmp_path / "events"
    command = rf'''
validate_set_publication_marker() {{ :; }}
verify_set() {{ :; }}
durably_sync_tree() {{ printf 'sync-failed\n' >> "$EVENT_LOG"; return 83; printf 'INNER_MASKED\n' >> "$EVENT_LOG"; }}
set +e
( set -Eeuo pipefail; recover_set_publication "{manifest}" )
status=$?
set -e
printf '%s\n' "$status"
'''
    result = _source(tmp_path, command, extra_env={"EVENT_LOG": _bash_path(events)})
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "83"
    assert marker.is_file()
    assert events.read_text(encoding="utf-8").splitlines() == ["sync-failed"]


def test_runtime_marker_pending_recovery_converges_in_order(tmp_path):
    runtime = tmp_path / "private-runtime"
    pending = Path(f"{runtime}.building")
    marker = Path(f"{runtime}.publication.pending")
    pending.mkdir()
    marker.write_text("marker", encoding="utf-8")
    events = tmp_path / "events"
    command = r'''
as_root() { "$@"; }
ROOT_INSTALL_BIN=true
ROOT_TEST_BIN=test
ROOT_SYNC_BIN=true
ROOT_MV_BIN=mv
ROOT_RM_BIN=rm
validate_runtime_publication_marker() { printf 'bound-digest\n'; }
verify_runtime_tree_inventory() { printf 'verify:%s\n' "$1" >> "$EVENT_LOG"; }
sha256_file() { printf 'bound-digest\n'; }
durably_sync_tree() { printf 'durable:%s\n' "$1" >> "$EVENT_LOG"; }
verify_runtime_prefix() { printf 'verify-final\n' >> "$EVENT_LOG"; }
recover_runtime_publication
test -d "$RUNTIME_PREFIX"
test ! -e "$RUNTIME_PENDING"
test ! -e "$RUNTIME_PUBLICATION"
'''
    result = _source(tmp_path, command, extra_env={"EVENT_LOG": _bash_path(events)})
    assert result.returncode == 0, result.stderr
    rows = events.read_text(encoding="utf-8").splitlines()
    assert rows[0].startswith("verify:") and rows[0].endswith(".building")
    assert rows[1].startswith("durable:") and rows[1].endswith(".building")
    assert rows[-1] == "verify-final"


def test_backup_isolated_generation_is_immutable_complete_and_cron_ordered():
    backup = _function("fresh_backup_receipt")
    validator = _function("validate_backup_receipt")
    switch = _function("switch_with_quiescence")
    assert "BACKUP_SCRIPT" not in backup
    assert "a03c-activation-snapshots" in backup
    assert "sqlite3.connect" in backup and "source.backup(target)" in backup
    assert "config-inventory.json" in backup and "anchor-inventory.json" in backup
    assert 'find "$partial" -type d -exec chmod 0500' in backup
    assert 'find "$partial" -type f -exec chmod 0400' in backup
    assert backup.index('durably_sync_tree "$partial"') < backup.index('mv -T -- "$partial" "$final"')
    assert "actual_config" in validator and "actual_anchors" in validator
    assert "changed during read" in validator
    assert switch.index("disable_genus_cron_block") < switch.index("prove_no_backup_in_progress")
    assert switch.index("prove_no_backup_in_progress") < switch.index("fresh_backup_receipt")


def test_activation_v2_deeply_crossbinds_all_evidence_and_exact_booleans():
    writer = _function("write_activation_receipt")
    validator = _function("validate_completion_receipt")
    for evidence in (
        "activated_set_manifest_path",
        "previous_set_manifest_path",
        "backup_receipt_path",
        "readiness_manifest_path",
        "verification_receipt_path",
        "active_identity_receipt_path",
        "postflight_receipt_path",
        "operator_reauthorization_receipt_path",
    ):
        assert evidence in writer and evidence in validator
        assert evidence.replace("_path", "_sha256") in writer
    for crossbinding in (
        "verification/readiness crossbinding differs",
        "active runtime/stable invocation differs",
        "postflight service inventory differs",
        "backup crossbinding differs",
        "operator reauthorization binding differs",
    ):
        assert crossbinding in validator
    assert 'top["core_embed_single_selector"] is not True' in validator
    assert 'top["database_rollback_performed"] is not False' in validator
    assert 'top["payloads_logged"] is not False' in validator


def test_reauthorization_is_clean_ff_one_shot_and_never_boot_authorization():
    command = _function("reauthorize_runtime")
    validator = _function("validate_operator_reauthorization")
    recovery = _function("recover_pending_activation")
    finalize = _function("finalize_guarded_transition")
    assert 'assert_expected_commit "$new"' in command
    assert "merge-base --is-ancestor" in command and "diff --name-only -z" in command
    assert "boot_approval_updated\":False" in command
    assert "write_autostart_approval" not in command
    assert "os.O_EXCL" in command and "os.fsync(directory)" in command
    assert "old_tree" in validator and "new_tree" in validator
    assert "allowed_diff_sha256" in validator
    assert "validate_stale_autostart_approval" in validator
    assert "validate_operator_reauthorization" in recovery
    assert "unterbrochener reautorisierter Transition" in recovery
    assert "consume_operator_reauthorization" in finalize
    boot_payload = _function("write_boot_guard_payload")
    assert "OPERATOR_REAUTH_TOKEN" not in boot_payload


def test_guard_is_installed_before_first_durable_activation_journal():
    switch = _function("switch_with_quiescence")
    guard = switch.index("install_systemd_autostart_guard")
    guard_verify = switch.index("systemd_autostart_guard_present", guard)
    journal = switch.index("create_activation_journal", guard_verify)
    assert guard < guard_verify < journal

def _acquirer_selectors() -> dict[str, object]:
    """Die Wheel-/sdist-Auswahl des Akquirierers gegen das Pi-Ziel scharf schalten.

    Der Block laeuft im Skript unter dem gepinnten Kandidaten-Python auf dem Pi;
    hier wird genau dieses Ziel simuliert (aarch64, glibc 2.41, CPython 3.13),
    damit die Auswahl ohne Pi und ohne Netz pruefbar bleibt.
    """
    import types

    acquire = _function("acquire_locked_sources")
    block = re.search(r"<<'PY'\n(.*?)\nPY\n", acquire, re.S)
    assert block is not None, "acquire_locked_sources hat keinen Python-Block"
    body = block.group(1)
    helpers = body[body.index("def sdist_identity") : body.index("missing = []")]
    assert "wheel_rank" in helpers, "Wheel-Auswahl fehlt im Akquirierer"
    namespace: dict[str, object] = {
        "os": types.SimpleNamespace(
            uname=lambda: types.SimpleNamespace(machine="aarch64"),
            confstr=lambda key: "glibc 2.41",
        ),
        "sys": types.SimpleNamespace(version_info=(3, 13, 15)),
        "re": re,
    }
    exec(compile(helpers, "<acquire_locked_sources>", "exec"), namespace)
    return namespace


def test_acquirer_prefers_wheels_and_keeps_sdist_as_fallback():
    acquire = _function("acquire_locked_sources")
    # Wheel schlaegt sdist, sdist bleibt Rueckfall, fehlt beides greift pip.
    assert acquire.index("if wheels:") < acquire.index("elif not candidates:")
    assert acquire.index("elif not candidates:") < acquire.index("ambiguous sdist set")
    # Die Herkunftsbindung gilt unveraendert fuer beide Artefaktarten.
    assert 'parsed.hostname != "files.pythonhosted.org"' in acquire
    assert 'digest.hexdigest() != expected' in acquire


def test_acquirer_wheel_selection_matches_the_pi_target():
    selectors = _acquirer_selectors()
    rank = selectors["wheel_rank"]
    identity = selectors["wheel_identity"]

    def accepted(filename: str) -> bool:
        parsed = identity(filename)
        assert parsed is not None, filename
        return rank(parsed) is not None

    # Genau die Rust-Extensions, die in der netzlosen Sandbox nicht baubar sind.
    assert accepted("tokenizers-0.23.1-cp310-abi3-manylinux_2_17_aarch64.manylinux2014_aarch64.whl")
    assert accepted("hf_xet-1.5.1-cp37-abi3-manylinux_2_28_aarch64.whl")
    assert accepted("py_rust_stemmers-0.1.8-cp313-cp313-manylinux_2_17_aarch64.whl")
    assert accepted("packaging-26.2-py3-none-any.whl")

    # Fremde Plattform, fremde libc, zu junge glibc und zu junger Interpreter.
    assert not accepted("foo-1.0-cp313-cp313-manylinux_2_28_x86_64.whl")
    assert not accepted("foo-1.0-cp313-cp313-musllinux_1_2_aarch64.whl")
    assert not accepted("foo-1.0-cp313-cp313-manylinux_2_99_aarch64.whl")
    assert not accepted("foo-1.0-cp314-abi3-manylinux_2_28_aarch64.whl")
    # Ein lokal gebautes Wheel ohne manylinux-Zusage bleibt ausgeschlossen.
    assert not accepted("foo-1.0-py3-none-linux_aarch64.whl")
    assert identity("foo-1.0.tar.gz") is None


def test_acquirer_wheel_choice_is_deterministic():
    selectors = _acquirer_selectors()
    rank, identity = selectors["wheel_rank"], selectors["wheel_identity"]

    def pick(*filenames: str) -> str:
        scored = [(rank(identity(name)), name) for name in filenames]
        assert all(entry[0] is not None for entry in scored), filenames
        scored.sort(key=lambda entry: (entry[0], entry[1]))
        return scored[-1][1]

    # Plattform-Wheel schlaegt das reine Python-Wheel, exaktes cp313 schlaegt abi3,
    # und unter gleichwertigen manylinux-Zusagen gewinnt die hoechste erfuellte glibc.
    assert pick(
        "foo-1.0-py3-none-any.whl",
        "foo-1.0-cp313-cp313-manylinux_2_28_aarch64.whl",
    ) == "foo-1.0-cp313-cp313-manylinux_2_28_aarch64.whl"
    assert pick(
        "foo-1.0-cp310-abi3-manylinux_2_28_aarch64.whl",
        "foo-1.0-cp313-cp313-manylinux_2_28_aarch64.whl",
    ) == "foo-1.0-cp313-cp313-manylinux_2_28_aarch64.whl"
    assert pick(
        "foo-1.0-cp313-cp313-manylinux_2_17_aarch64.whl",
        "foo-1.0-cp313-cp313-manylinux_2_28_aarch64.whl",
    ) == "foo-1.0-cp313-cp313-manylinux_2_28_aarch64.whl"


def test_stage_recovers_stale_scratch_and_open_publication_before_building():
    stage = _function("stage_set")
    # Beide Recovery-Schritte laufen vor jedem Bau und vor der Prefix-Weiche,
    # damit weder ein root-eigener Sandbox-Rest noch ein offener
    # Publikationsmarker unbegrenzt liegen bleibt.
    assert "recover_stale_build_scratch" in stage
    assert "recover_runtime_publication" in stage
    assert stage.index("recover_stale_build_scratch") < stage.index("capture_locks")
    assert stage.index("recover_runtime_publication") < stage.index('if [ -e "$RUNTIME_PREFIX" ]')


def test_db_handle_probe_calls_fuser_without_a_double_dash():
    probe = _function("prove_no_db_handles")
    # psmisc' fuser hat keinen getopt-Parser: "--" erzeugt Usage-Text auf stderr
    # und Status 1 -- also genau die Signatur, die hier "keine Handles" heisst.
    assert '"$FUSER_BIN" "${paths[@]}"' in probe
    assert '"$FUSER_BIN" --' not in probe
    assert '[[ "$path" = /* ]]' in probe


def test_legacy_venv_backup_stays_out_of_the_clean_gate():
    backup_prefix = ".venv.a03c-"
    script = _script()
    assert 'MIGRATION_CORE_BACKUP="${CORE_POINTER}.a03c-${legacy}"' in script
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    # Die Sicherung liegt neben dem Pointer im Repo (atomares mv im selben
    # Dateisystem). Sie muss ignoriert sein, sonst bricht sie das exakt-clean-Gate
    # des Boot-Guards und GENUS startet nach der Aktivierung nicht mehr.
    assert any(entry.strip() == f"{backup_prefix}legacy-*" for entry in ignored), ignored


def test_reauthorize_allows_the_a0_3c_operator_documentation():
    script = _script()
    # Die A0.3c-Doku liegt in deploy/README.md. Ohne Freigabe koennte
    # ausgerechnet eine reine Doku-Nachbesserung nach der Aktivierung nicht mehr
    # per Fast-Forward nachgezogen werden.
    allowlists = [row for row in script.splitlines() if "CONTRIBUTING.md) ;;" in row]
    assert len(allowlists) == 2, allowlists
    for row in allowlists:
        assert "deploy/README.md" in row
        assert "genus/" not in row


def test_cpython_build_can_import_sqlite_before_the_prefix_exists():
    build = _function("build_runtime")
    # Live-Fund 2026-08-20: _sqlite3 traegt schon beim Bau den RUNPATH auf den
    # finalen Prefix. Der existiert dann noch nicht, CPythons Import-Pruefung
    # scheitert, das Modul landet als *_failed.so und der Install bricht ab.
    # Der bauzeitliche Suchpfad zeigt deshalb auf den gestagten Prefix.
    assert 'export LD_LIBRARY_PATH="$stage$RUNTIME_PREFIX/lib"' in build
    assert build.index("LD_LIBRARY_PATH") < build.index("--with-ensurepip=install")
    # ...und der Bau beweist den Import selbst, statt ihn dem Install zu ueberlassen.
    assert "import _sqlite3" in build
    assert 'fail "CPython wurde ohne _sqlite3 gebaut"' in build


def test_published_runtime_never_resolves_libraries_through_the_environment():
    script = _script()
    # Der bauzeitliche Suchpfad ist die EINZIGE Stelle; die veroeffentlichte
    # Runtime loest libsqlite3 ausschliesslich ueber ihren RUNPATH auf.
    for forbidden in ("LD_PRELOAD", "ldconfig"):
        assert forbidden not in _function("runtime_probe")
        assert forbidden not in _function("verify_runtime_prefix")


def test_stage_sweeps_leftover_build_trees():
    sweep = _function("recover_stale_state_builds")
    stage = _function("stage_set")
    # Der RETURN-Trap von build_runtime feuert bei errexit/exit nicht; ohne Sweep
    # bleibt ein abgebrochener Bau als Gigabyte-Rest im State-Root liegen.
    assert '"$STATE_ROOT"/build.*' in sweep
    assert '[ ! -L "$path" ]' in sweep
    assert "recover_stale_state_builds" in stage
    assert stage.index("recover_stale_state_builds") < stage.index("capture_locks")


def test_permission_scans_cannot_trip_over_symlink_modes():
    script = _script()
    # Live-Fund 2026-08-21: Symlinks tragen unter Linux immer lrwxrwxrwx. Ein
    # Rechte-Scan ohne Typfilter meldet deshalb jeden Symlink als welt-schreibbar
    # -- die Runtime-Verifikation konnte nie bestehen. Klassen-Waechter: JEDER
    # -perm-Scan muss entweder Symlinks ausschliessen, auf regulaere Dateien bzw.
    # Verzeichnisse filtern, oder mit -L die Ziele bewerten.
    scans = [row.strip() for row in script.splitlines() if "-perm /" in row]
    assert len(scans) >= 6, scans
    for scan in scans:
        assert ("! -type l" in scan or "-type f" in scan or "-type d" in scan
                or "find -L" in scan), scan


def test_runtime_verification_accepts_the_cpython_symlinks():
    verify = _function("verify_runtime_prefix")
    # bin/python3 -> python3.13 und acht weitere gehoeren zu jedem CPython-Baum.
    assert '! -type l -perm /022' in verify
    # Die Garantie bleibt: Eigentum wird weiterhin ueber den ganzen Baum geprueft,
    # und das Inventar bindet jedes Symlink-Ziel.
    assert "! -user root" in verify
    assert "target" in _function("runtime_tree_inventory")


def test_runtime_tree_is_built_readable_for_the_unprivileged_service_user():
    build = _function("build_runtime")
    verify = _function("verify_runtime_prefix")
    # Live-Fund 2026-08-21: Das globale umask 077 des Skripts vererbt sich auf alles,
    # was Python waehrend des Baus anlegt (pip-Installation, __pycache__). Nach dem
    # chown auf root lagen 136 Verzeichnisse auf 0700 -- die GENUS-Dienste laufen
    # aber unprivilegiert und haetten diese Runtime nie benutzen koennen.
    assert build.count("umask 022") == 2, "beide Bau-Subshells brauchen den offenen umask"
    assert build.index("umask 022") < build.index("./configure")
    # Und die Verifikation faengt die Klasse ab, statt sie erst live auffliegen zu lassen.
    assert "! -perm -o+r" in verify and "-type d ! -perm -o+x" in verify
    assert "nicht lesbar" in verify


def test_stage_quarantines_an_unusable_runtime_instead_of_blocking():
    stage = _function("stage_set")
    # Ohne diesen Zweig braeuchte jeder Fehlversuch eine root-Handaufraeumung:
    # verify_runtime_prefix wuerde hart scheitern und den Lauf blockiert zuruecklassen.
    assert "quarantine_runtime_path" in stage
    assert '( verify_runtime_prefix )' in stage
    assert stage.index("quarantine_runtime_path") < stage.index("build_runtime")


def test_every_found_runtime_failure_quarantines_instead_of_blocking():
    recover = _function("recover_runtime_publication")
    # Live-Fund 2026-08-21: Der markerlose Zweig rief verify_runtime_prefix ohne
    # Subshell auf; dessen fail() beendete das ganze Skript, bevor stage_set
    # quarantaenieren konnte. Jeder Fehlversuch braeuchte sonst eine
    # root-Handaufraeumung. Beide Zweige folgen jetzt derselben Regel.
    assert recover.count("quarantine_runtime_path") >= 3
    assert recover.count("( set -Eeuo pipefail; verify_runtime_prefix )") == 1
    assert "unbrauchbare markerlose Runtime" in recover
