"""Inquiry command surface, registered onto the root Click group.

The lifecycle belongs to :mod:`genus.inquiries`; this module contains presentation
and argument handling only. Keeping this slice out of ``cli.py`` limits the root
integration module's change radius as the maintenance surface grows.
"""
from __future__ import annotations

from collections.abc import Callable

import click

from genus import inquiries


def register(main: click.Group, get_conn: Callable):
    @main.group(name="inquiries")
    def inquiries_group() -> None:
        pass

    @inquiries_group.command("list")
    @click.option("--all", "include_all", is_flag=True)
    def inquiries_list(include_all: bool) -> None:
        conn = get_conn()
        try:
            rows = inquiries.list_inquiries(conn, include_all=include_all)
            click.echo("INQUIRIES" if include_all else "OPEN INQUIRIES")
            click.echo("id  type          claim_key      state     question_key")
            for row in rows:
                click.echo(
                    f"{row['id']:<3} {row['inquiry_type']:<13} {row['claim_key']:<14} "
                    f"{row['state']:<9} {row['question_key']}"
                )
        finally:
            conn.close()

    @inquiries_group.command("resolve")
    @click.argument("inquiry_id", type=int)
    @click.option("--answer", required=True)
    def inquiries_resolve(inquiry_id: int, answer: str) -> None:
        conn = get_conn()
        try:
            try:
                inquiries.record_inquiry_resolved_event(conn, inquiry_id, answer)
                conn.commit()
            except ValueError as exc:
                raise click.ClickException(str(exc)) from exc
            click.echo(f"[GOV] inquiry {inquiry_id} resolved")
        finally:
            conn.close()

    @inquiries_group.command("reconcile")
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Report mechanically resolvable inquiries without writing.",
    )
    @click.option(
        "--repair-cycles",
        is_flag=True,
        help="Retract historically accepted hierarchy-cycle edges and resolve their inquiries.",
    )
    def inquiries_reconcile(dry_run: bool, repair_cycles: bool) -> None:
        """Resolve false structural alarms and duplicate stability questions."""
        conn = get_conn()
        try:
            report = inquiries.reconcile(
                conn, dry_run=dry_run, repair_cycles=repair_cycles
            )
            action = "would resolve" if dry_run else "resolved"
            click.echo(
                f"[INQ] {action} {len(report['resolved'])} inquiry/inquiries "
                f"(false_acyclicity={report['false_acyclicity']}, "
                f"duplicate_stability={report['duplicate_stability']})"
            )
            click.echo(
                f"[INQ] hierarchy cycles repairable={report['repairable_cycles']} "
                f"repaired={report['repaired_cycles']}"
            )
            if report["event_id"] is not None:
                click.echo(f"[EVT] inquiries_reconciled (id={report['event_id']})")
        finally:
            conn.close()

    return inquiries_group
