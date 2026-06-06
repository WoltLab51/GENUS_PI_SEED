from __future__ import annotations

import json
import os

import click

from genus import db, integrity, ledger, projection, proposals, reactors, sensor


def get_conn():
    return db.connect(os.environ.get("GENUS_DB_PATH", "genus.sqlite3"))


@click.group()
def main() -> None:
    pass


@main.command("observe-cpu")
def observe_cpu() -> None:
    reading = sensor.read_cpu()
    conn = get_conn()
    try:
        result = reactors.observe_cpu_reading(conn, reading)

        click.echo(
            f"[OBS] CPU: {reading['raw_value']:.1f}% (source: {reading['source']})"
        )
        click.echo(f"[EVT] observation_created     (id={result['observation_id']})")
        for event in result["events"]:
            if event["event_type"] == "evidence_recorded":
                click.echo(
                    f"[EVT] evidence_recorded       "
                    f"(id={event['id']}, metric: {event['metric_key']}={event['metric_value']:.1f})"
                )
            else:
                click.echo(f"[EVT] {event['event_type']}")
        _print_active_belief_summary(conn)
    finally:
        conn.close()


@main.group()
def beliefs() -> None:
    pass


@beliefs.command("show")
def beliefs_show() -> None:
    conn = get_conn()
    try:
        rows = projection.list_active_beliefs(conn)
        click.echo("ACTIVE BELIEFS")
        click.echo("claim_key    claim_value  confidence  supporting  contradicting  derivation")
        for row in rows:
            click.echo(
                f"{row['claim_key']:<12} {row['claim_value']:<12} "
                f"{row['confidence']:<10.3f} {row['supporting']:<11} "
                f"{row['contradicting']:<14} {row['derivation']}"
            )
    finally:
        conn.close()


@main.group(name="proposals")
def proposals_group() -> None:
    pass


@proposals_group.command("list")
@click.option("--all", "include_all", is_flag=True)
def proposals_list(include_all: bool) -> None:
    conn = get_conn()
    try:
        rows = proposals.list_proposals(conn, include_all=include_all)
        click.echo("PROPOSALS" if include_all else "PENDING PROPOSALS")
        click.echo("id  type              claim_key    claim_value  state    created_at")
        for row in rows:
            click.echo(
                f"{row['id']:<3} {row['proposal_type']:<17} {row['claim_key']:<12} "
                f"{row['claim_value']:<12} {row['state']:<8} {row['created_at']}"
            )
    finally:
        conn.close()


@main.command("replay")
def replay_command() -> None:
    conn = get_conn()
    try:
        before = _state_snapshot(conn)
        event_count = conn.execute("SELECT COUNT(*) AS count FROM event_log").fetchone()[
            "count"
        ]
        click.echo(f"[REPLAY] Reading {event_count} events from event_log...")
        click.echo("[REPLAY] Rebuilding belief_projection...")
        click.echo("[REPLAY] Rebuilding proposal_log...")
        summary = ledger.replay(conn)
        after = _state_snapshot(conn)
        click.echo(
            f"[REPLAY] Result: {summary['active_beliefs']} active belief(s), "
            f"{summary['proposals']} proposal(s)"
        )
        if before == after:
            click.echo("[REPLAY] State matches current projection")
        else:
            raise click.ClickException("state changed after replay")
    finally:
        conn.close()


@main.group(name="integrity")
def integrity_group() -> None:
    pass


@integrity_group.command("check")
def integrity_check() -> None:
    conn = get_conn()
    try:
        result = integrity.check(conn)
        if result["ok"]:
            click.echo(
                f"[INTEGRITY] OK events={result['events']} "
                f"active_beliefs={result['active_beliefs']} proposals={result['proposals']}"
            )
            return
        for issue in result["issues"]:
            click.echo(f"[INTEGRITY] FAIL {issue}")
        raise click.ClickException("integrity check failed")
    finally:
        conn.close()


@main.group(name="ledger")
def ledger_group() -> None:
    pass


@ledger_group.command("tail")
@click.option("--n", default=20, show_default=True, type=int)
def ledger_tail(n: int) -> None:
    conn = get_conn()
    try:
        for event in ledger.tail(conn, n):
            click.echo(
                f"{event['id']:<5} {event['event_type']:<24} "
                f"{json.dumps(event['payload'], sort_keys=True)}"
            )
    finally:
        conn.close()


def _print_active_belief_summary(conn) -> None:
    rows = projection.list_active_beliefs(conn)
    for row in rows:
        click.echo(
            f"[BLF] {row['claim_key']}={row['claim_value']} active "
            f"(supporting: {row['supporting']}, contradicting: {row['contradicting']})"
        )
        click.echo(
            f"      confidence: {row['confidence']:.3f}  derivation: {row['derivation']}"
        )


def _state_snapshot(conn) -> dict:
    beliefs = [
        dict(row)
        for row in conn.execute(
            """
            SELECT id, claim_key, claim_value, state, derivation,
                   supporting_events, contradicting_events, superseded_by
            FROM belief_projection
            ORDER BY id
            """
        ).fetchall()
    ]
    proposal_rows = conn.execute(
        """
        SELECT id, proposal_type, claim_key, claim_value, source_belief,
               source_event, payload, state
        FROM proposal_log
        ORDER BY id
        """
    ).fetchall()
    return {
        "beliefs": beliefs,
        "proposals": [dict(row) for row in proposal_rows],
    }


if __name__ == "__main__":
    main()
