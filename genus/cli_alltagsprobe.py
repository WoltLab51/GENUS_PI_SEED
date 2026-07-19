"""Click-Slice für die hermetische GENUS-Alltagsprobe."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import click

from genus import alltagsprobe


def register(main: click.Group) -> click.Command:
    @main.command("alltagsprobe")
    @click.option("--json-output", is_flag=True, help="Emit the complete report as JSON.")
    @click.option("--markdown", is_flag=True, help="Emit the human review report as Markdown.")
    @click.option("--details", is_flag=True, help="Show every synthetic question and answer.")
    @click.option(
        "--write-report",
        type=click.Path(path_type=Path, dir_okay=False),
        help="Write the deterministic Markdown review report to this path.",
    )
    @click.option(
        "--contracts-only",
        is_flag=True,
        help="Exit successfully when hard contracts pass, even if human review is open.",
    )
    @click.option(
        "--reviews",
        type=click.Path(path_type=Path, dir_okay=False),
        help="Read hash-bound human reviews from this JSON file.",
    )
    def command(
        json_output: bool,
        markdown: bool,
        details: bool,
        write_report: Path | None,
        contracts_only: bool,
        reviews: Path | None,
    ) -> None:
        """Run synthetic everyday dialogues without model, network, or live database."""
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass
        if sum(bool(value) for value in (json_output, markdown, write_report)) > 1:
            raise click.UsageError(
                "--json-output, --markdown und --write-report schließen einander aus."
            )
        try:
            loaded = alltagsprobe.load_reviews(reviews) if reviews else None
            report = alltagsprobe.run_suite(reviews=loaded)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise click.ClickException(str(exc)) from exc

        if write_report:
            path = alltagsprobe.write_markdown_report(report, write_report)
            click.echo(f"[ALLTAG] Bericht geschrieben: {path}")
        elif json_output:
            click.echo(json.dumps(
                alltagsprobe.report_dict(report),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ))
        elif markdown:
            click.echo(alltagsprobe.render_markdown(report), nl=False)
        else:
            hard_passed = sum(
                value["passed"] for value in report.dimensions.values()
            )
            hard_total = sum(value["total"] for value in report.dimensions.values())
            click.echo(
                "[ALLTAG] "
                f"{len(report.cases)} Fälle · harte Verträge {hard_passed}/{hard_total} · "
                f"menschlich akzeptiert {report.human_statuses['accepted']}/{len(report.cases)} · "
                f"Inhalt {report.content_sha256[:16]}"
            )
            for key, values in report.dimensions.items():
                status = "OK" if not values["failed"] else "FAIL"
                click.echo(
                    f"[{status}] {alltagsprobe.DIMENSION_LABELS[key]}: "
                    f"{values['passed']}/{values['total']}"
                )
            if details:
                for case in report.cases:
                    status = "OK" if case.hard_ok else "FAIL"
                    click.echo(f"\n[{status}] {case.id} · {case.title}")
                    for index, turn in enumerate(case.turns, 1):
                        click.echo(f"  Frage {index}: {turn.question}")
                        click.echo(f"  GENUS {index}: {turn.text}")
                    click.echo(f"  Mensch: {case.human_status} · {case.human_prompt}")
                    click.echo(
                        f"  Hashes: Fall {case.case_fingerprint[:12]} · "
                        f"Antwort {case.response_sha256[:12]}"
                    )
            elif report.human_statuses["review_pending"] or report.human_statuses["review_stale"]:
                click.echo(
                    "[OFFEN] Ton und Nutzen sind nicht automatisch beweisbar; "
                    "`genus alltagsprobe --details` zeigt die exakten Antworten."
                )

        if not report.hard_ok:
            raise click.exceptions.Exit(1)
        if not contracts_only and report.human_statuses["accepted"] != len(report.cases):
            raise click.exceptions.Exit(2)

    return command
