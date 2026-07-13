"""Read-only operating-profile command surface for the root Click group."""
from __future__ import annotations

import json
import os
from pathlib import Path

import click

from genus import betriebsprofil, db


def register(main: click.Group) -> click.Group:
    @main.group("betriebsprofil")
    def betriebsprofil_group() -> None:
        """Private read-only baseline and 24/48/72-hour operating evidence."""

    @betriebsprofil_group.command("capture")
    @click.option(
        "--start",
        is_flag=True,
        help="Start the series deliberately and capture its baseline.",
    )
    @click.option(
        "--quiet",
        is_flag=True,
        help="Stay silent while the series is not started, not due, or complete.",
    )
    @click.option(
        "--json-output",
        is_flag=True,
        help="Emit the privacy-safe result as JSON.",
    )
    @click.option(
        "--output-dir",
        type=click.Path(path_type=Path, file_okay=False),
        help="Private profile directory (default: GENUS_PROFILE_DIR beside the ledger).",
    )
    def capture(
        start: bool,
        quiet: bool,
        json_output: bool,
        output_dir: Path | None,
    ) -> None:
        db_path = os.environ.get("GENUS_DB_PATH", "genus.sqlite3")
        try:
            result = betriebsprofil.capture_due(
                db_path,
                output_dir=output_dir,
                start=start,
            )
        except (betriebsprofil.ProfileError, db.DatabaseNotFoundError) as exc:
            raise click.ClickException(str(exc)) from exc

        if json_output:
            click.echo(json.dumps(result, ensure_ascii=False, sort_keys=True))
            if result["action"] == "aborted_missed":
                raise click.exceptions.Exit(2)
            return
        if result["action"] == "captured":
            click.echo(
                f"[PROFIL] {result['label']} captured: "
                f"head={result['head_event_id']} "
                f"events={result['events_in_interval']} "
                f"late_seconds={result['late_by_seconds']}"
            )
        elif not quiet and result["action"] == "not_started":
            click.echo(
                "[PROFIL] not started; run "
                "`genus betriebsprofil capture --start` once"
            )
        elif not quiet and result["action"] == "not_due":
            click.echo(
                f"[PROFIL] next={result['next_label']} due_at={result['due_at']}"
            )
        elif result["action"] == "aborted_missed":
            click.echo(
                f"[PROFIL] aborted: missed {result['missed_label']} by "
                f"{result['late_by_seconds']} seconds",
                err=True,
            )
            raise click.exceptions.Exit(2)
        elif not quiet and result["action"] == "aborted":
            click.echo("[PROFIL] aborted after a missed schedule point")
        elif not quiet:
            click.echo("[PROFIL] complete")

    @betriebsprofil_group.command("status")
    @click.option("--json-output", is_flag=True, help="Emit the status as JSON.")
    @click.option(
        "--output-dir",
        type=click.Path(path_type=Path, file_okay=False),
        help="Private profile directory (default: GENUS_PROFILE_DIR beside the ledger).",
    )
    def status(json_output: bool, output_dir: Path | None) -> None:
        db_path = os.environ.get("GENUS_DB_PATH", "genus.sqlite3")
        try:
            result = betriebsprofil.profile_status(db_path, output_dir=output_dir)
        except betriebsprofil.ProfileError as exc:
            raise click.ClickException(str(exc)) from exc
        if json_output:
            click.echo(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return
        click.echo(
            f"[PROFIL] status={result['status']} "
            f"captures={len(result['captures'])} "
            f"next={result.get('next_label') or '-'}"
        )

    return betriebsprofil_group
