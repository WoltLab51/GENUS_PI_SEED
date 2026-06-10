from __future__ import annotations

import json
import os

import click

from genus import db, event_router, inquiries, integrity, ledger, projection, proposals, reactors, sensor


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

        _print_observation_result("CPU", reading, result)
        _print_active_belief_summary(conn)
    finally:
        conn.close()


@main.command("observe-memory")
def observe_memory() -> None:
    reading = sensor.read_memory()
    conn = get_conn()
    try:
        result = reactors.observe_memory_reading(conn, reading)

        _print_observation_result("MEM", reading, result)
        _print_active_belief_summary(conn)
    finally:
        conn.close()


@main.command("observe-disk")
def observe_disk() -> None:
    reading = sensor.read_disk()
    conn = get_conn()
    try:
        result = reactors.observe_disk_reading(conn, reading)

        _print_observation_result("DSK", reading, result)
        _print_active_belief_summary(conn)
    finally:
        conn.close()


@main.command("observe-activity")
def observe_activity() -> None:
    reading = sensor.read_activity()
    conn = get_conn()
    try:
        result = reactors.observe_activity_reading(conn, reading)

        _print_observation_result("ACT", reading, result)
        _print_active_belief_summary(conn)
    finally:
        conn.close()


@main.command("observe-temperature")
def observe_temperature() -> None:
    reading = sensor.read_temperature()
    if reading is None:
        click.echo("[OBS] TMP: not available on this system")
        return

    conn = get_conn()
    try:
        result = reactors.observe_temperature_reading(conn, reading)

        _print_observation_result("TMP", reading, result)
        _print_active_belief_summary(conn)
    finally:
        conn.close()


@main.command("observe-all")
def observe_all() -> None:
    conn = get_conn()
    try:
        for label, reading_fn, observe_fn in [
            ("CPU", sensor.read_cpu, reactors.observe_cpu_reading),
            ("MEM", sensor.read_memory, reactors.observe_memory_reading),
            ("DSK", sensor.read_disk, reactors.observe_disk_reading),
            ("ACT", sensor.read_activity, reactors.observe_activity_reading),
        ]:
            reading = reading_fn()
            result = observe_fn(conn, reading)
            _print_observation_result(label, reading, result)

        temperature = sensor.read_temperature()
        if temperature is None:
            click.echo("[OBS] TMP: not available on this system")
        else:
            result = reactors.observe_temperature_reading(conn, temperature)
            _print_observation_result("TMP", temperature, result)

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
        summary = event_router.replay(conn)
        after = _state_snapshot(conn)
        click.echo(
            f"[REPLAY] Result: {summary['active_beliefs']} active belief(s), "
            f"{summary['proposals']} proposal(s), {summary['inquiries']} inquiry(s)"
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
                f"active_beliefs={result['active_beliefs']} "
                f"proposals={result['proposals']} inquiries={result['inquiries']}"
            )
            return
        for issue in result["issues"]:
            click.echo(f"[INTEGRITY] FAIL {issue}")
        raise click.ClickException("integrity check failed")
    finally:
        conn.close()


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
        click.echo("id  type          claim_key      state  question_key")
        for row in rows:
            click.echo(
                f"{row['id']:<3} {row['inquiry_type']:<13} {row['claim_key']:<14} "
                f"{row['state']:<6} {row['question_key']}"
            )
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


def _print_observation_result(label: str, reading: dict, result: dict) -> None:
    click.echo(f"[OBS] {label}: {_format_reading_value(reading)} (source: {reading['source']})")
    click.echo(f"[EVT] observation_created     (id={result['observation_id']})")
    for event in result["events"]:
        if event["event_type"] == "evidence_recorded":
            click.echo(
                f"[EVT] evidence_recorded       "
                f"(id={event['id']}, metric: {event['metric_key']}="
                f"{_format_metric_value(event['metric_key'], event['metric_value'])})"
            )
        else:
            click.echo(f"[EVT] {event['event_type']}")


def _format_reading_value(reading: dict) -> str:
    value = float(reading["raw_value"])
    unit = reading.get("unit", "")
    if unit == "percent":
        return f"{value:.1f}%"
    if unit == "celsius":
        return f"{value:.1f}C"
    if unit == "binary":
        return "active" if value >= 1.0 else "idle"
    return f"{value:.1f} {unit}".strip()


def _format_metric_value(metric_key: str, value: float) -> str:
    if metric_key == "system.activity":
        return "active" if float(value) >= 1.0 else "idle"
    if metric_key == "system.temperature":
        return f"{float(value):.1f}C"
    return f"{float(value):.1f}"


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
    inquiry_rows = conn.execute(
        """
        SELECT id, inquiry_type, claim_key, source_belief, source_event,
               question_key, payload, state, resolved_at
        FROM inquiry_log
        ORDER BY id
        """
    ).fetchall()
    return {
        "beliefs": beliefs,
        "proposals": [dict(row) for row in proposal_rows],
        "inquiries": [dict(row) for row in inquiry_rows],
    }


if __name__ == "__main__":
    main()
