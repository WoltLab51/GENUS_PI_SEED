"""Disposable Linux/systemd+Polkit staging for the workload self-probe.

This test is deliberately inert during normal pytest runs.  It creates system
units and a site Polkit rule, so it may run only in a disposable Linux VM whose
operator set the exact destructive-staging acknowledgement below.
"""

from __future__ import annotations

import ast
import os
import platform
import re
import subprocess
import time
from pathlib import Path

import pytest


ACK = "I_UNDERSTAND_THIS_IS_A_DISPOSABLE_VM"
ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "deploy" / "pi_a0_3c_runtime.sh"
GUARD = Path("/usr/local/libexec/genus-a0-3c-boot-guard")
RULE = Path("/etc/polkit-1/rules.d/49-genus-a03c-self-probe-staging.rules")
UNITS = {
    "genus-learner.service": ("genus-runtime", "genus-runtime"),
    "genus-telegram-bot.service": ("genus-telegram", "genus-telegram"),
    "genus-backup.service": ("genus-backup", "genus-backup"),
    "genus-cron@.service": ("genus-runtime", "genus-runtime"),
}
CONCRETE_CRON = "genus-cron@doctor.service"
GROUPS = ("genus-data", "genus-runtime", "genus-telegram", "genus-backup")
USERS = ("genus-runtime", "genus-telegram", "genus-backup")
POLKIT_ACTIONS = (
    "org.freedesktop.systemd1.manage-units",
    "org.freedesktop.systemd1.manage-unit-files",
    "org.freedesktop.systemd1.reload-daemon",
    "org.freedesktop.systemd1.set-environment",
)


def _run(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"},
    )


def _unit_payload(name: str, user: str, group: str) -> str:
    description = name.replace("%", "%%")
    return f"""[Unit]
Description=Disposable GENUS self-probe staging {description}

[Service]
Type=oneshot
User={user}
Group={group}
SupplementaryGroups=genus-data
NoNewPrivileges=true
RestrictSUIDSGID=true
CapabilityBoundingSet=
AmbientCapabilities=
ExecStartPre=+{GUARD} --probe-workload-authority-root %n
ExecStartPre={GUARD} --probe-workload-context %n
ExecStart=/bin/true
    """


def _candidate_guard_payload() -> bytes:
    source = RUNTIME.read_text(encoding="utf-8")
    function = source[source.index("write_boot_guard_payload() {") :]
    function = function[: function.index("\nwrite_boot_guard_payload_from_commit()")]
    for block in re.findall(r"<<'PY'\n(.*?)\nPY", function, re.S):
        tree = ast.parse(block)
        for node in tree.body:
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "program"
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                config = {
                    "journal": "/staging/activation.pending",
                    "code_journal": "/staging/code-release.pending",
                    "approval": "/staging/runtime.start-authorized",
                    "active": "/staging/ACTIVE",
                    "sets": "/staging/sets",
                    "repo": "/staging/repo",
                    "git": "/usr/bin/git",
                    "uid": 65534,
                    "gid": 65534,
                    "state": "/staging",
                    "core_pointer": "/staging/core",
                    "embed_pointer": "/staging/embed",
                    "series_root": "/staging/series",
                    "receipt_root": "/staging/receipts",
                    "database": "/staging/genus.sqlite3",
                    "start_capability": "/staging/start-capability",
                    "start_marker": "/staging/start-marker",
                    "trust_anchor": "/staging/code-release.trust-anchor",
                    "code_backup_root": "/staging/code-backup",
                    "public_sets": "/staging/public-sets",
                    "public_active": "/staging/public-active",
                    "projection_trust": "/staging/projection-trust",
                    "runtime_prefix": "/staging/runtime",
                    "projection_helper": "/usr/local/libexec/genus/pi_a0_3c_projection.py",
                    "consumer_publisher": "/usr/local/libexec/genus/pi_a0_3c_consumer_publish.py",
                    "consumer_renderer": "/usr/local/libexec/genus/pi_a0_3c_consumer_bundle.py",
                }
                return node.value.value.replace("__CONFIG__", repr(config)).encode("utf-8")
    raise AssertionError("embedded candidate boot guard program is absent")


def _account_exists(database: str, name: str) -> bool:
    return _run("/usr/bin/getent", database, name, check=False).returncode == 0


@pytest.mark.skipif(platform.system() != "Linux", reason="Linux staging only")
def test_exact_unit_context_denies_targeted_polkit_authority() -> None:
    if os.environ.get("GENUS_A03C_DISPOSABLE_SYSTEMD_POLKIT_STAGING") != ACK:
        pytest.skip("exact disposable-VM acknowledgement is absent")
    if os.geteuid() != 0 or Path("/proc/1/comm").read_text().strip() != "systemd":
        pytest.fail("acknowledged staging requires root in a systemd-booted disposable VM")
    required = (
        Path("/usr/bin/getent"),
        Path("/usr/bin/journalctl"),
        Path("/usr/bin/pkaction"),
        Path("/usr/bin/pkcheck"),
        Path("/usr/bin/systemctl"),
        Path("/usr/sbin/groupadd"),
        Path("/usr/sbin/groupdel"),
        Path("/usr/sbin/useradd"),
        Path("/usr/sbin/userdel"),
    )
    if any(not path.is_file() for path in required):
        pytest.fail("systemd, Polkit, or account-management staging dependency is absent")
    if GUARD.exists() or GUARD.is_symlink() or RULE.exists() or RULE.is_symlink():
        pytest.fail("an exact staging guard or Polkit rule path already exists")
    if any(_account_exists("group", name) for name in GROUPS) or any(
        _account_exists("passwd", name) for name in USERS
    ):
        pytest.fail("a GENUS staging account name already exists")
    catalog_result = _run("/usr/bin/pkaction", check=False)
    catalog = set(catalog_result.stdout.splitlines())
    missing_actions = sorted(set(POLKIT_ACTIONS) - catalog)
    if catalog_result.returncode != 0 or missing_actions:
        pytest.fail(
            f"systemd Polkit action catalog is incomplete: rc={catalog_result.returncode}, "
            f"missing={missing_actions}, stderr={catalog_result.stderr!r}"
        )

    unit_paths = {name: Path("/run/systemd/system") / name for name in UNITS}
    if any(path.exists() or path.is_symlink() for path in unit_paths.values()):
        pytest.fail("a staging unit name already exists under /run/systemd/system")

    created_groups: list[str] = []
    created_users: list[str] = []
    created_guard = False
    try:
        for group in GROUPS:
            _run("/usr/sbin/groupadd", "--system", group)
            created_groups.append(group)
        for user in USERS:
            _run(
                "/usr/sbin/useradd",
                "--system",
                "--no-create-home",
                "--shell",
                "/usr/sbin/nologin",
                "--gid",
                user,
                user,
            )
            created_users.append(user)
        GUARD.parent.mkdir(parents=True, exist_ok=True)
        GUARD.write_bytes(_candidate_guard_payload())
        GUARD.chmod(0o755)
        created_guard = True

        for name, (user, group) in UNITS.items():
            unit_paths[name].write_text(_unit_payload(name, user, group), encoding="ascii")
            unit_paths[name].chmod(0o644)
        _run("/usr/bin/systemctl", "daemon-reload")

        # Every exact workload context must pass while Polkit conclusively denies it.
        for unit in ("genus-learner.service", "genus-telegram-bot.service", "genus-backup.service", CONCRETE_CRON):
            result = _run("/usr/bin/systemctl", "start", unit, check=False)
            if result.returncode != 0:
                show = _run(
                    "/usr/bin/systemctl",
                    "show",
                    unit,
                    "--property=Result",
                    "--property=ExecMainStatus",
                    "--property=ExecStartPre",
                    check=False,
                )
                journal = _run(
                    "/usr/bin/journalctl",
                    "--unit",
                    unit,
                    "--no-pager",
                    "--lines=30",
                    "--output=cat",
                    check=False,
                )
                pytest.fail(
                    f"baseline workload self-probe rejected {unit}: rc={result.returncode}, "
                    f"stdout={result.stdout!r}, stderr={result.stderr!r}, "
                    f"journal={journal.stdout!r}, show={show.stdout!r}",
                    pytrace=False,
                )

        # This adversarial rule grants only the concrete cron cgroup a single
        # systemd verb.  Generic synthetic subjects cannot observe this grant.
        RULE.write_text(
            """polkit.addRule(function(action, subject) {
    if (action.id == "org.freedesktop.systemd1.manage-units" &&
        subject.system_unit == "genus-cron@doctor.service" &&
        subject.no_new_privileges == true &&
        action.lookup("unit") == "genus-telegram-bot.service" &&
        action.lookup("verb") == "start") {
        return polkit.Result.YES;
    }
});
""",
            encoding="ascii",
        )
        RULE.chmod(0o644)
        # polkitd watches its rule directories.  Poll the start edge instead of
        # assuming one fixed reload latency; success would mean the rule is not
        # loaded yet, while failure proves the in-unit self-probe saw rc=0.
        deadline = time.monotonic() + 10
        result: subprocess.CompletedProcess[str] | None = None
        while time.monotonic() < deadline:
            _run("/usr/bin/systemctl", "reset-failed", CONCRETE_CRON, check=False)
            result = _run("/usr/bin/systemctl", "start", CONCRETE_CRON, check=False)
            if result.returncode != 0:
                break
            time.sleep(0.25)
        assert result is not None and result.returncode != 0, (
            "targeted concrete-unit Polkit grant did not block ExecStartPre"
        )
        show = _run(
            "/usr/bin/systemctl",
            "show",
            CONCRETE_CRON,
            "--property=Result",
            "--property=ExecMainStatus",
        ).stdout
        assert "Result=exit-code" in show
    finally:
        RULE.unlink(missing_ok=True)
        for unit in (*UNITS.keys(), CONCRETE_CRON):
            _run("/usr/bin/systemctl", "stop", unit, check=False)
            _run("/usr/bin/systemctl", "reset-failed", unit, check=False)
        for path in unit_paths.values():
            path.unlink(missing_ok=True)
        _run("/usr/bin/systemctl", "daemon-reload", check=False)
        if created_guard:
            GUARD.unlink(missing_ok=True)
        for user in reversed(created_users):
            _run("/usr/sbin/userdel", user, check=False)
        for group in reversed(created_groups):
            _run("/usr/sbin/groupdel", group, check=False)
