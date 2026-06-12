from __future__ import annotations

import json
import os

import click

from genus import (
    db,
    event_router,
    experience,
    governance,
    inquiries,
    integrity,
    ledger,
    maturation,
    projection,
    proposals,
    query,
    reactors,
    sealing,
    sensor,
    state,
)


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


@main.command("ask")
@click.argument("question", nargs=-1, required=True)
def ask_command(question: tuple[str, ...]) -> None:
    conn = get_conn()
    try:
        response = query.ask(conn, " ".join(question))
        _print_ask_response(response)
    finally:
        conn.close()


@main.group(name="explain")
def explain_group() -> None:
    pass


@explain_group.command("belief")
@click.argument("belief_id", type=int)
def explain_belief_command(belief_id: int) -> None:
    conn = get_conn()
    try:
        _print_belief_explanation(query.explain_belief(conn, belief_id))
    finally:
        conn.close()


@explain_group.command("experience")
@click.argument("experience_id", type=int)
def explain_experience_command(experience_id: int) -> None:
    conn = get_conn()
    try:
        _print_experience_explanation(query.explain_experience(conn, experience_id))
    finally:
        conn.close()


@explain_group.command("state")
@click.argument("state_id", type=int)
def explain_state_command(state_id: int) -> None:
    conn = get_conn()
    try:
        _print_state_explanation(query.explain_state(conn, state_id))
    finally:
        conn.close()


@explain_group.command("rule")
@click.argument("rule_id", type=int)
def explain_rule_command(rule_id: int) -> None:
    conn = get_conn()
    try:
        _print_rule_explanation(query.explain_rule(conn, rule_id))
    finally:
        conn.close()


@main.group(name="why")
def why_group() -> None:
    pass


@why_group.command("proposal")
@click.argument("proposal_id", type=int)
def why_proposal_command(proposal_id: int) -> None:
    conn = get_conn()
    try:
        _print_proposal_explanation(query.explain_proposal(conn, proposal_id))
    finally:
        conn.close()


@why_group.command("decision")
@click.argument("decision_id", type=int)
def why_decision_command(decision_id: int) -> None:
    conn = get_conn()
    try:
        _print_decision_explanation(query.explain_decision(conn, decision_id))
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


@main.group(name="experience")
def experience_group() -> None:
    pass


@main.group(name="state")
def state_group() -> None:
    pass


@main.group(name="governance")
def governance_group() -> None:
    pass


@main.group(name="maturation")
def maturation_group() -> None:
    pass


@main.group(name="rules")
def rules_group() -> None:
    pass


@experience_group.command("scan")
def experience_scan() -> None:
    conn = get_conn()
    try:
        try:
            rows = experience.scan(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        if not rows:
            click.echo("[EXP] no new experience")
            return
        click.echo(f"[EXP] recorded {len(rows)} experience(s)")
        for row in rows:
            click.echo(
                f"[EXP] #{row['experience_id']} {row['experience_type']} "
                f"{row['experience_key']}"
            )
    finally:
        conn.close()


@experience_group.command("show")
def experience_show() -> None:
    conn = get_conn()
    try:
        rows = experience.list_experiences(conn)
        click.echo("EXPERIENCES")
        click.echo("id  type                   subject          derivation")
        for row in rows:
            click.echo(
                f"{row['id']:<3} {row['experience_type']:<22} "
                f"{row['subject_key']:<16} {row['derivation']}"
            )
            click.echo(f"    {row['summary']}")
    finally:
        conn.close()


@maturation_group.command("scan")
def maturation_scan() -> None:
    conn = get_conn()
    try:
        try:
            rows = maturation.scan(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        if not rows:
            click.echo("[MAT] no new rule candidates")
            return
        click.echo(f"[MAT] proposed {len(rows)} rule(s)")
        for row in rows:
            click.echo(
                f"[MAT] rule_proposed {row['rule_key']} -> "
                f"RuleProposal #{row['proposal_id']}"
            )
    finally:
        conn.close()


@state_group.command("refresh")
def state_refresh() -> None:
    conn = get_conn()
    try:
        try:
            rows = state.refresh(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        if not rows:
            click.echo("[STATE] no change")
            return
        for row in rows:
            click.echo(
                f"[STATE] event #{row['id']} {row['state_key']}={row['state_value']}"
            )
    finally:
        conn.close()


@state_group.command("show")
def state_show() -> None:
    conn = get_conn()
    try:
        rows = state.list_active_states(conn)
        click.echo("ACTIVE STATES")
        click.echo("id  state_key        state_value  derivation")
        for row in rows:
            click.echo(
                f"{row['id']:<3} {row['state_key']:<16} "
                f"{row['state_value']:<12} {row['derivation']}"
            )
            click.echo(f"    reason: {row['reason']}")
    finally:
        conn.close()


@rules_group.command("list")
@click.option("--all", "include_all", is_flag=True)
def rules_list(include_all: bool) -> None:
    conn = get_conn()
    try:
        rows = maturation.list_rules(conn, active_only=not include_all)
        click.echo("RULES" if include_all else "ACTIVE RULES")
        click.echo("id  type                       subject          status    source  rule_key")
        for row in rows:
            click.echo(
                f"{row['id']:<3} {row['rule_type']:<26} "
                f"{row['subject_key']:<16} {row['status']:<9} "
                f"#{row['source_proposal']:<6} {row['rule_key']}"
            )
            click.echo(f"    spec: {json.dumps(row['spec'], sort_keys=True)}")
    finally:
        conn.close()


@rules_group.command("activate")
@click.argument("proposal_id", type=int)
@click.option("--override", is_flag=True, default=False)
def rules_activate(proposal_id: int, override: bool) -> None:
    conn = get_conn()
    try:
        try:
            verdict = maturation.activate_rule(conn, proposal_id, override)
            conn.commit()
        except ValueError as exc:
            conn.rollback()
            raise click.ClickException(str(exc)) from exc
        if verdict["decision"] == governance.BLOCKED:
            click.echo(f"[GOV] BLOCKED by {verdict['blocked_by']}: {verdict['reason']}")
            raise click.exceptions.Exit(1)
        override_text = " (override)" if verdict["override"] else ""
        click.echo(
            f"[GOV] decision #{verdict['decision_id']} allowed{override_text}"
        )
        click.echo(f"[MAT] rule {verdict['rule_key']} activated")
    finally:
        conn.close()


@proposals_group.command("list")
@click.option("--all", "include_all", is_flag=True)
def proposals_list(include_all: bool) -> None:
    conn = get_conn()
    try:
        rows = proposals.list_proposals(conn, include_all=include_all)
        click.echo("PROPOSALS" if include_all else "PENDING PROPOSALS")
        if include_all:
            click.echo(
                "id  type              claim_key    claim_value  state     "
                "decision  reviewed_at"
            )
        else:
            click.echo("id  type              claim_key    claim_value  state    created_at")
        for row in rows:
            if include_all:
                click.echo(
                    f"{row['id']:<3} {row['proposal_type']:<17} "
                    f"{row['claim_key']:<12} {row['claim_value']:<12} "
                    f"{row['state']:<9} {row['decision'] or '-':<9} "
                    f"{row['reviewed_at'] or '-'}"
                )
            else:
                click.echo(
                    f"{row['id']:<3} {row['proposal_type']:<17} "
                    f"{row['claim_key']:<12} {row['claim_value']:<12} "
                    f"{row['state']:<8} {row['created_at']}"
                )
    finally:
        conn.close()


@proposals_group.command("review")
@click.argument("proposal_id", type=int)
@click.option("--accept", "decision", flag_value="accepted", default=None)
@click.option("--reject", "decision", flag_value="rejected")
@click.option("--note", default="")
@click.option("--override", is_flag=True, default=False)
def proposals_review(
    proposal_id: int,
    decision: str | None,
    note: str,
    override: bool,
) -> None:
    if decision is None:
        raise click.ClickException("--accept or --reject required")
    conn = get_conn()
    try:
        try:
            verdict = proposals.review_proposal_governed(
                conn,
                proposal_id,
                decision,
                note,
                override,
            )
            conn.commit()
        except ValueError as exc:
            conn.rollback()
            raise click.ClickException(str(exc)) from exc
        if verdict["decision"] == governance.BLOCKED:
            click.echo(f"[GOV] BLOCKED by {verdict['blocked_by']}: {verdict['reason']}")
            raise click.exceptions.Exit(1)
        override_text = " (override)" if verdict["override"] else ""
        click.echo(
            f"[GOV] decision #{verdict['decision_id']} allowed{override_text}"
        )
        click.echo(f"[GOV] proposal {proposal_id} {decision}")
        if note:
            click.echo(f"[GOV] note: {note}")
    finally:
        conn.close()


@governance_group.command("list")
@click.option("--target", default=None, help="Filter like proposal:3")
def governance_list(target: str | None) -> None:
    conn = get_conn()
    try:
        target_type, target_id = _parse_governance_target(target)
        rows = governance.list_decisions(conn, target_type, target_id)
        click.echo("GOVERNANCE DECISIONS")
        click.echo("id  action           target       decision  override  reason")
        for row in rows:
            click.echo(
                f"{row['id']:<3} {row['action']:<16} "
                f"{row['target_type']}:{row['target_id']:<7} "
                f"{row['decision']:<9} {str(row['override']):<9} {row['reason']}"
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
        click.echo("[REPLAY] Rebuilding state_projection...")
        click.echo("[REPLAY] Rebuilding experience_log...")
        click.echo("[REPLAY] Rebuilding proposal_log...")
        click.echo("[REPLAY] Rebuilding rule_projection...")
        summary = event_router.replay(conn)
        after = _state_snapshot(conn)
        click.echo(
            f"[REPLAY] Result: {summary['active_beliefs']} active belief(s), "
            f"{summary['proposals']} proposal(s), {summary['inquiries']} inquiry(s), "
            f"{summary['experiences']} experience(s), "
            f"{summary['active_states']} active state(s), "
            f"{summary['governance_decisions']} governance decision(s), "
            f"{summary['active_rules']} active rule(s)"
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
                f"proposals={result['proposals']} inquiries={result['inquiries']} "
                f"experiences={result['experiences']} "
                f"active_states={result['active_states']} "
                f"governance_decisions={result['governance_decisions']} "
                f"active_rules={result['active_rules']}"
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


@ledger_group.command("seal-init")
def ledger_seal_init() -> None:
    conn = get_conn()
    try:
        epoch_id = sealing.open_epoch(conn)
        if epoch_id is None:
            click.echo("[SEAL] already initialized")
            return
        conn.commit()
        head = sealing.head(conn)
        click.echo(f"[SEAL] epoch opened (event id={epoch_id})")
        click.echo(f"[SEAL] head={head['seal']}")
    finally:
        conn.close()


@ledger_group.command("head")
def ledger_head() -> None:
    conn = get_conn()
    try:
        head = sealing.head(conn)
        if head is None:
            click.echo("[SEAL] sealing not initialized (run: genus ledger seal-init)")
            return
        click.echo(f"[SEAL] algo={sealing.ALGO}")
        click.echo(f"[SEAL] head_event_id={head['id']}")
        click.echo(f"[SEAL] head={head['seal']}")
    finally:
        conn.close()


@ledger_group.command("verify")
def ledger_verify() -> None:
    conn = get_conn()
    try:
        if not sealing.is_active(conn):
            click.echo("[SEAL] sealing not initialized (run: genus ledger seal-init)")
            return
        issues = sealing.verify_chain(conn)
        if not issues:
            head = sealing.head(conn)
            click.echo(f"[SEAL] OK chain intact, head={head['seal']}")
            return
        for issue in issues:
            click.echo(f"[SEAL] FAIL {issue}")
        raise click.ClickException("ledger verification failed")
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


def _print_ask_response(response: dict) -> None:
    click.echo(f"[ASK] {response['answer']}")
    if response["kind"] == "active_beliefs":
        for belief in response["beliefs"]:
            click.echo(
                f"[BLF] #{belief['id']} {belief['claim_key']}={belief['claim_value']} "
                f"state={belief['state']} confidence={belief['confidence']:.3f}"
            )
    elif response["kind"] == "pending_proposals":
        for proposal in response["proposals"]:
            click.echo(
                f"[PRP] #{proposal['id']} {proposal['proposal_type']} "
                f"{proposal['claim_key']}={proposal['claim_value']} "
                f"state={proposal['state']}"
            )
    elif response["kind"] == "open_inquiries":
        for inquiry in response["inquiries"]:
            click.echo(
                f"[INQ] #{inquiry['id']} {inquiry['inquiry_type']} "
                f"{inquiry['claim_key']} state={inquiry['state']} "
                f"question={inquiry['question_key']}"
            )
    elif response["kind"] == "experiences":
        for row in response["experiences"]:
            click.echo(
                f"[EXP] #{row['id']} {row['experience_type']} "
                f"{row['experience_key']}"
            )
    elif response["kind"] == "states":
        for row in response["states"]:
            click.echo(
                f"[STATE] #{row['id']} {row['state_key']}={row['state_value']} "
                f"reason={row['reason']}"
            )
    elif response["kind"] == "governance_decisions":
        for row in response["governance_decisions"]:
            click.echo(
                f"[GOV] #{row['id']} {row['action']} "
                f"{row['target_type']}:{row['target_id']} "
                f"decision={row['decision']} override={row['override']}"
            )
    elif response["kind"] == "rules":
        for row in response["rules"]:
            click.echo(
                f"[RULE] #{row['id']} {row['rule_type']} "
                f"{row['subject_key']} {row['rule_key']}"
            )
    elif response["kind"] == "status":
        for key, value in response["status"].items():
            click.echo(f"{key}: {value}")
    elif response["kind"] == "unknown":
        click.echo("Supported fixed queries:")
        for pattern in response["supported"]:
            click.echo(f"- genus {pattern}")


def _print_belief_explanation(explanation: dict) -> None:
    belief = explanation["belief"]
    click.echo(
        f"BELIEF #{belief['id']} {belief['claim_key']}={belief['claim_value']} "
        f"state={belief['state']}"
    )
    click.echo(
        f"confidence={belief['confidence']:.3f} supporting={belief['supporting']} "
        f"contradicting={belief['contradicting']}"
    )
    click.echo(f"derivation={belief['derivation']}")
    if explanation["created_by"] is not None:
        event = explanation["created_by"]
        click.echo(f"created_by: #{event['id']} {event['event_type']}")

    click.echo("supporting_evidence:")
    _print_evidence_chain(explanation["supporting_evidence"])
    click.echo("contradicting_evidence:")
    _print_evidence_chain(explanation["contradicting_evidence"])
    click.echo("transition_events:")
    _print_event_list(explanation["transition_events"])


def _print_proposal_explanation(explanation: dict) -> None:
    proposal = explanation["proposal"]
    payload = json.loads(proposal["payload"])
    click.echo(
        f"PROPOSAL #{proposal['id']} {proposal['proposal_type']} "
        f"{proposal['claim_key']}={proposal['claim_value']} state={proposal['state']}"
    )
    click.echo(f"reason={payload.get('description', '')}")
    if proposal["decision"] is not None:
        click.echo(
            f"review: {proposal['decision']} reviewed_at={proposal['reviewed_at']}"
        )
    proposal_event = explanation["proposal_event"]
    if proposal_event is not None:
        click.echo(f"proposal_event: #{proposal_event['id']} {proposal_event['event_type']}")
    review_event = explanation["review_event"]
    if review_event is not None:
        review_payload = review_event["payload"]
        click.echo(
            f"review_event: #{review_event['id']} {review_event['event_type']} "
            f"decision={review_payload['decision']} note={review_payload['note']}"
        )
    source_event = explanation["source_event"]
    click.echo(f"source_event: #{source_event['id']} {source_event['event_type']}")
    if explanation["source_belief"] is not None:
        click.echo("source_belief:")
        _print_belief_explanation(explanation["source_belief"])
    if explanation.get("source_experience") is not None:
        click.echo("source_experience:")
        _print_experience_explanation(explanation["source_experience"])


def _print_experience_explanation(explanation: dict) -> None:
    row = explanation["experience"]
    click.echo(
        f"EXPERIENCE #{row['id']} {row['experience_type']} "
        f"{row['experience_key']}"
    )
    click.echo(f"subject={row['subject_key']} derivation={row['derivation']}")
    click.echo(f"summary={row['summary']}")
    experience_event = explanation["experience_event"]
    if experience_event is not None:
        click.echo(
            f"experience_event: #{experience_event['id']} "
            f"{experience_event['event_type']}"
        )
    click.echo("supporting_evidence:")
    _print_evidence_chain(explanation["supporting_evidence"])
    click.echo("proposals:")
    if not explanation["proposals"]:
        click.echo("- none")
    for proposal in explanation["proposals"]:
        click.echo(
            f"- #{proposal['id']} {proposal['proposal_type']} "
            f"{proposal['claim_key']}={proposal['claim_value']} "
            f"state={proposal['state']}"
        )


def _print_state_explanation(explanation: dict) -> None:
    row = explanation["state"]
    click.echo(
        f"STATE #{row['id']} {row['state_key']}={row['state_value']} "
        f"status={row['status']}"
    )
    click.echo(f"derivation={row['derivation']}")
    click.echo(f"reason={row['reason']}")
    state_event = explanation["state_event"]
    if state_event is not None:
        click.echo(f"state_event: #{state_event['id']} {state_event['event_type']}")
    click.echo("supporting_beliefs:")
    if not explanation["supporting_beliefs"]:
        click.echo("- none")
    for belief in explanation["supporting_beliefs"]:
        click.echo(
            f"- #{belief['id']} {belief['claim_key']}={belief['claim_value']} "
            f"state={belief['state']} confidence={belief['confidence']:.3f}"
        )


def _print_decision_explanation(explanation: dict) -> None:
    decision = explanation["decision"]
    click.echo(
        f"DECISION #{decision['id']} {decision['action']} "
        f"{decision['target_type']}:{decision['target_id']} "
        f"decision={decision['decision']} override={decision['override']}"
    )
    click.echo(f"reason={decision['reason']}")
    governance_event = explanation["governance_event"]
    if governance_event is not None:
        click.echo(
            f"governance_event: #{governance_event['id']} "
            f"{governance_event['event_type']}"
        )
    click.echo("constraint_checked:")
    _print_event_payload_list(explanation["constraint_events"])
    click.echo("policy_evaluated:")
    _print_event_payload_list(explanation["policy_events"])


def _print_rule_explanation(explanation: dict) -> None:
    rule = explanation["rule"]
    click.echo(
        f"RULE #{rule['id']} {rule['rule_type']} {rule['rule_key']} "
        f"status={rule['status']}"
    )
    click.echo(f"subject={rule['subject_key']} derivation={rule['derivation']}")
    click.echo(f"spec={json.dumps(rule['spec'], sort_keys=True)}")
    rule_event = explanation["rule_event"]
    if rule_event is not None:
        click.echo(f"rule_event: #{rule_event['id']} {rule_event['event_type']}")
    proposal = explanation["source_proposal"]
    click.echo(
        f"source_proposal: #{proposal['id']} {proposal['proposal_type']} "
        f"state={proposal['state']}"
    )
    proposed = explanation["rule_proposed_event"]
    click.echo(f"rule_proposed_event: #{proposed['id']} {proposed['event_type']}")
    source_experience = explanation["source_experience"]
    if source_experience is not None:
        click.echo("source_experience:")
        _print_experience_explanation(source_experience)


def _print_evidence_chain(events: list[dict]) -> None:
    if not events:
        click.echo("- none")
        return
    for event in events:
        payload = event["payload"]
        metric_key = payload.get("metric_key", "?")
        metric_value = payload.get("metric_value", "?")
        line = f"- #{event['id']} {event['event_type']} {metric_key}={metric_value}"
        observation = event.get("observation")
        if observation is not None:
            obs_payload = observation["payload"]
            line += (
                f" via observation #{observation['id']} "
                f"source={obs_payload.get('source')}"
            )
        click.echo(line)


def _print_event_list(events: list[dict]) -> None:
    if not events:
        click.echo("- none")
        return
    for event in events:
        click.echo(f"- #{event['id']} {event['event_type']}")


def _print_event_payload_list(events: list[dict]) -> None:
    if not events:
        click.echo("- none")
        return
    for event in events:
        payload = event["payload"]
        key = payload.get("constraint_key") or payload.get("policy_key") or "?"
        click.echo(
            f"- #{event['id']} {event['event_type']} {key} "
            f"result={payload.get('result')} reason={payload.get('reason')}"
        )


def _parse_governance_target(target: str | None) -> tuple[str | None, int | None]:
    if target is None:
        return None, None
    if ":" not in target:
        raise click.ClickException("--target must look like proposal:<id>")
    target_type, raw_id = target.split(":", 1)
    if target_type != "proposal":
        raise click.ClickException("only proposal:<id> targets are supported")
    try:
        return target_type, int(raw_id)
    except ValueError as exc:
        raise click.ClickException("target id must be an integer") from exc


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
               source_event, payload, state, decision, reviewed_at
        FROM proposal_log
        ORDER BY id
        """
    ).fetchall()
    inquiry_rows = conn.execute(
        """
        SELECT id, inquiry_type, claim_key, source_belief, source_event,
               question_key, payload, state, answer, resolved_at
        FROM inquiry_log
        ORDER BY id
        """
    ).fetchall()
    experience_rows = conn.execute(
        """
        SELECT id, experience_key, experience_type, subject_key, pattern,
               supporting_events, derivation, summary
        FROM experience_log
        ORDER BY id
        """
    ).fetchall()
    state_rows = conn.execute(
        """
        SELECT id, state_key, state_value, status, derivation,
               supporting_beliefs, components, reason, superseded_by
        FROM state_projection
        ORDER BY id
        """
    ).fetchall()
    governance_rows = conn.execute(
        """
        SELECT id, action, target_type, target_id, decision, override,
               policy_results, reason
        FROM governance_log
        ORDER BY id
        """
    ).fetchall()
    rule_rows = conn.execute(
        """
        SELECT id, rule_key, rule_type, subject_key, spec, status,
               source_proposal, derivation
        FROM rule_projection
        ORDER BY id
        """
    ).fetchall()
    return {
        "beliefs": beliefs,
        "proposals": [dict(row) for row in proposal_rows],
        "inquiries": [dict(row) for row in inquiry_rows],
        "experiences": [dict(row) for row in experience_rows],
        "states": [dict(row) for row in state_rows],
        "governance": [dict(row) for row in governance_rows],
        "rules": [dict(row) for row in rule_rows],
    }


if __name__ == "__main__":
    main()
