from __future__ import annotations

import json
import os
from pathlib import Path

import click

from genus import (
    anchor,
    control,
    db,
    doctor as doctor_checks,
    event_router,
    experience,
    governance,
    inference,
    inquiries,
    integrity,
    learning,
    ledger,
    maturation,
    operation,
    projection,
    proposals,
    query,
    reactors,
    sealing,
    sensor,
    sources,
    state,
)
from genus.cli_format import (
    _print_active_belief_summary,
    _print_ask_response,
    _print_belief_explanation,
    _print_calibration,
    _print_decision_explanation,
    _print_experience_explanation,
    _print_inferences,
    _print_learning,
    _print_lexeme_inferences,
    _print_observation_result,
    _print_proposal_explanation,
    _print_relations,
    _print_resolve,
    _print_rule_explanation,
    _print_sources,
    _print_state_explanation,
    _print_surprisal,
)


def get_conn():
    return db.connect(os.environ.get("GENUS_DB_PATH", "genus.sqlite3"))


@click.group()
def main() -> None:
    pass


@main.command("doctor")
def doctor() -> None:
    db_path = os.environ.get("GENUS_DB_PATH", "genus.sqlite3")
    conn = get_conn()
    try:
        checks = doctor_checks.run(
            conn,
            db_path=db_path,
            core_id=os.environ.get("GENUS_CORE_ID"),
        )
        for check in checks:
            click.echo(f"[{check.status}] {check.name}: {check.detail}")
        if doctor_checks.has_failures(checks):
            raise click.ClickException("doctor found failing checks")
    finally:
        conn.close()


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
    if control.is_paused():
        click.echo("[OBS] paused — skipping (genus resume to continue)")
        return
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


@main.command("pause")
@click.option("--reason", default="", help="why (recorded in the marker)")
def pause_command(reason: str) -> None:
    """Freeze all autonomous activity — sensor ticks, membranes, the background learner all
    skip while paused. Reads and manual commands keep working; the ledger is untouched."""
    path = control.pause(reason)
    click.echo(f"[CTL] PAUSED — autonomous activity will skip until 'genus resume' ({path})")


@main.command("resume")
def resume_command() -> None:
    """Lift the pause — autonomous activity runs again."""
    if control.resume():
        click.echo("[CTL] resumed — autonomous activity will run")
    else:
        click.echo("[CTL] not paused — nothing to resume")


@main.command("paused")
def paused_command() -> None:
    """Show whether autonomous activity is paused (exit 0 = paused, 1 = running)."""
    if control.is_paused():
        why = control.reason()
        click.echo("[CTL] PAUSED" + (f" — {why}" if why else ""))
    else:
        click.echo("[CTL] running")
        raise SystemExit(1)


@main.command("observe-repo")
@click.option("--commits-per-day", "commits", required=True, type=int)
@click.option("--lines-changed", "lines", default=None, type=int)
@click.option("--measured-on", default="unknown", show_default=True)
@click.option("--window-hours", default=24, show_default=True, type=int)
def observe_repo(
    commits: int,
    lines: int | None,
    measured_on: str,
    window_hours: int,
) -> None:
    """Record structural observations of repo activity.

    The counts are measured by the membrane (off-device) and handed in here; the
    core never runs git. ``--lines-changed`` additionally records the day's churn
    intensity. A missing run records nothing, so the beliefs simply age —
    absence of a measurement is not an observation of quiet.
    """
    if commits < 0:
        raise click.ClickException("--commits-per-day must be >= 0")
    if lines is not None and lines < 0:
        raise click.ClickException("--lines-changed must be >= 0")
    conn = get_conn()
    try:
        reading = sensor.repo_commits_reading(commits, measured_on, window_hours)
        result = reactors.observe_repo_reading(conn, reading)
        _print_observation_result("REPO", reading, result)
        if lines is not None:
            churn_reading = sensor.repo_lines_reading(lines, measured_on, window_hours)
            churn_result = reactors.observe_repo_lines_reading(conn, churn_reading)
            _print_observation_result("CHURN", churn_reading, churn_result)
        _print_active_belief_summary(conn)
    finally:
        conn.close()


@main.command("observe-weather")
@click.option("--temp-outside", "temp_outside", required=True, type=float)
@click.option("--source", default="unknown", show_default=True)
def observe_weather(temp_outside: float, source: str) -> None:
    """Record an outside-temperature observation fetched by the membrane.

    The membrane reaches the network and hands in only the number; the core never
    fetches. The location stays in the membrane configuration — only the
    temperature and its source provenance enter the ledger. A failed fetch records
    nothing, so the belief simply ages: absence of a reading is not a reading.
    """
    conn = get_conn()
    try:
        reading = sensor.weather_reading(temp_outside, source)
        result = reactors.observe_weather_reading(conn, reading)
        _print_observation_result("WTR", reading, result)
        _print_active_belief_summary(conn)
    finally:
        conn.close()


@main.command("observe-assertion")
@click.option("--claim-key", "claim_key", required=True)
@click.option("--value", "value", required=True, type=float)
@click.option("--source", required=True)
def observe_assertion(claim_key: str, value: float, source: str) -> None:
    """Record a claim asserted by an external source — the general WISSEN entry point.

    The membrane fetches the value and hands in only (claim, source, value); the core
    never reaches out. Used to feed a second source for an existing claim so GENUS
    learns whom to trust (see `genus sources`).
    """
    conn = get_conn()
    try:
        result = reactors.observe_assertion(conn, claim_key, value, source)
        click.echo(
            f"[ASR] {claim_key} = {value} (source={source}) — event {result['event_id']}"
        )
    finally:
        conn.close()


def _atlas_facts() -> str:
    """Derive the atlas's drift-prone facts from the code itself.

    The visual atlas hand-draws stable principles, but its state-dependent facts
    (sensors, reactors, detectors, the preset budget) should be a projection of
    the code, not a snapshot that silently drifts. This renders them so the atlas
    can be regenerated and a test can enforce currency.
    """
    import genus
    from genus import constants, experience, rules

    metric_keys = sorted({getattr(rules, n) for n in dir(rules) if n.endswith("_METRIC_KEY")})
    reactors = [reactor.__name__ for reactor in rules.REACTORS]
    detectors = [detector.__name__ for detector in experience.DETECTORS]
    budget = sorted(n for n in dir(constants) if n.endswith("_THRESHOLD"))

    return "\n".join(
        [
            "# GENUS Atlas — generierte Fakten",
            "",
            "> Aus dem Code erzeugt via `genus atlas-facts`. Nicht von Hand editieren —",
            "> bei Code-Änderungen neu generieren; ein Test erzwingt die Aktualität.",
            "",
            f"- **Version:** {genus.__version__}",
            f"- **Sensor-Metriken ({len(metric_keys)}):** " + ", ".join(metric_keys),
            f"- **Beobachtungs-Reaktoren ({len(reactors)}):** " + ", ".join(reactors),
            f"- **Kognitions-Detektoren ({len(detectors)}):** " + ", ".join(detectors),
            f"- **Preset-Budget ({len(budget)} feste Schwellen):** " + ", ".join(budget),
            "",
        ]
    )


@main.command("atlas-facts")
def atlas_facts_command() -> None:
    """Print the atlas's drift-prone facts, derived from the code."""
    click.echo(_atlas_facts())


@main.command("ask")
@click.argument("question", nargs=-1, required=True)
def ask_command(question: tuple[str, ...]) -> None:
    conn = get_conn()
    try:
        response = query.ask(conn, " ".join(question))
        _print_ask_response(response)
    finally:
        conn.close()


@main.command("calibration")
def calibration_command() -> None:
    """Report whether GENUS's own stability judgments have held up."""
    conn = get_conn()
    try:
        _print_calibration(query.calibration(conn))
    finally:
        conn.close()


@main.command("surprisal")
def surprisal_command() -> None:
    """Rank beliefs by how many bits a flip would carry (information-theoretic surprise)."""
    conn = get_conn()
    try:
        _print_surprisal(query.surprisal(conn))
    finally:
        conn.close()


@main.command("learning")
def learning_command() -> None:
    """Show GENUS's forecast learning curves — is its prediction error shrinking?"""
    conn = get_conn()
    try:
        _print_learning(learning.curves(conn))
    finally:
        conn.close()


@main.command("sources")
def sources_command() -> None:
    """Show each source's learned trust and the read-time resolution where sources overlap."""
    conn = get_conn()
    try:
        _print_sources(sources.report(conn))
    finally:
        conn.close()


@main.command("resolve")
@click.argument("claim_key")
def resolve_command(claim_key: str) -> None:
    """Resolve a claim to its current value over all sources (trust × freshness)."""
    conn = get_conn()
    try:
        _print_resolve(sources.resolve(conn, claim_key))
    finally:
        conn.close()


@main.command("teach")
@click.argument("claim_key")
@click.argument("value", type=float)
@click.option("--source", default="human", show_default=True)
def teach_command(claim_key: str, value: float, source: str) -> None:
    """Teach a claim's value as a human source and settle any open contradiction for it."""
    conn = get_conn()
    try:
        result = reactors.teach(conn, claim_key, value, source)
        settled = len(result["resolved_inquiries"])
        click.echo(
            f"[TCH] {claim_key} = {value} (source={source}) — "
            f"settled {settled} contradiction inquiry(ies)"
        )
    finally:
        conn.close()


@main.command("relate")
@click.argument("subject")
@click.argument("predicate")
@click.argument("object")
@click.option("--source", default="human", show_default=True)
def relate_command(subject: str, predicate: str, object: str, source: str) -> None:
    """Assert a relation between two entities — networked knowledge (subject -[pred]-> object)."""
    conn = get_conn()
    try:
        reactors.observe_relation(conn, subject, predicate, object, source)
        click.echo(f"[REL] {subject} -[{predicate}]-> {object}   · {source}")
    finally:
        conn.close()


@main.command("unrelate")
@click.argument("subject")
@click.argument("predicate")
@click.argument("object")
@click.option("--source", default=None, help="retract only this source's edge (default: every source)")
def unrelate_command(subject: str, predicate: str, object: str, source: str | None) -> None:
    """Retract a relation — take a wrong or corrected assertion back (relation_retracted)."""
    conn = get_conn()
    try:
        reactors.retract_relation(conn, subject, predicate, object, source)
        where = f"· {source}" if source else "· all sources"
        click.echo(f"[REL] retracted {subject} -[{predicate}]-> {object}   {where}")
    finally:
        conn.close()


@main.command("relations")
@click.argument("subject", required=False)
def relations_command(subject: str | None) -> None:
    """Show the knowledge graph — relations GENUS holds (optionally for one subject)."""
    conn = get_conn()
    try:
        _print_relations(sources.relations(conn, subject), label=lambda n: sources.display(conn, n))
    finally:
        conn.close()


@main.command("confidence")
@click.argument("subject")
@click.argument("predicate")
@click.argument("object")
def confidence_command(subject: str, predicate: str, object: str) -> None:
    """How confident is GENUS that a relation holds — read-time, from source trust × corroboration."""
    conn = get_conn()
    try:
        c = sources.relation_confidence(conn, subject, predicate, object)
        s, p, o = sources.display(conn, subject), predicate, sources.display(conn, object)
        if c["n_sources"] == 0:
            click.echo(f"[CNF] {s} -[{p}]-> {o}: not asserted")
            return
        click.echo(f"[CNF] {s} -[{p}]-> {o}   confidence {c['confidence']:.2f}  "
                   f"({c['n_sources']} source(s), noisy-OR of trust)")
        for src in c["sources"]:
            click.echo(f"[CNF]   {src['source']}   trust {src['trust']:.2f}")
    finally:
        conn.close()


@main.command("gaps")
@click.option("--limit", default=20, type=int, show_default=True)
@click.option("--predicate", "predicates", multiple=True,
              help="relation predicate(s) to follow (default: synonym, antonym; e.g. is_a to climb a hierarchy)")
def gaps_command(limit: int, predicates: tuple[str, ...]) -> None:
    """List knowledge gaps — referenced words GENUS doesn't know yet (one per line)."""
    conn = get_conn()
    try:
        for word in sources.gaps(conn, limit, predicates or ("synonym", "antonym")):
            click.echo(word)
    finally:
        conn.close()


@main.command("infer")
@click.argument("subject")
@click.argument("predicate")
@click.option("--lang", default=None,
              help="treat SUBJECT as a word in this language: map it to its concept(s), reason at the concept level, answer in this language")
def infer_command(subject: str, predicate: str, lang: str | None) -> None:
    """Derive new relations from known ones (transitive/symmetric), each with its why.

    With --lang, SUBJECT is a word: GENUS reasons through its language-neutral concept
    (sense-coherent) and renders the answer back into that language."""
    conn = get_conn()
    try:
        lbl = lambda n: sources.display(conn, n)
        if lang:
            _print_lexeme_inferences(
                inference.infer_lexeme(conn, subject, predicate, lang), subject, predicate, lang, label=lbl)
        else:
            _print_inferences(inference.infer(conn, subject, predicate), subject, predicate, label=lbl)
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


@main.group(name="operation")
def operation_group() -> None:
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
        click.echo(f"[EXP] recorded {len(rows)} experience update(s)")
        for row in rows:
            tag = "re-characterized" if row.get("recharacterized") else "new"
            click.echo(
                f"[EXP] #{row['experience_id']} {tag} {row['experience_type']} "
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


@operation_group.command("network-check")
@click.option(
    "--status",
    "status_value",
    required=True,
    type=click.Choice([operation.STATUS_OK, operation.STATUS_FAIL]),
)
@click.option("--target", required=True)
@click.option("--failures", default=0, show_default=True, type=int)
@click.option(
    "--action",
    type=click.Choice([operation.ACTION_RESTART_NETWORK, operation.ACTION_REBOOT]),
    default=None,
)
@click.option("--detail", default="")
@click.option("--json", "as_json", is_flag=True)
def operation_network_check(
    status_value: str,
    target: str,
    failures: int,
    action: str | None,
    detail: str,
    as_json: bool,
) -> None:
    conn = get_conn()
    try:
        try:
            result = operation.record_network_check(
                conn,
                status=status_value,
                target=target,
                failures=failures,
                action=action,
                detail=detail,
            )
            conn.commit()
        except ValueError as exc:
            conn.rollback()
            raise click.ClickException(str(exc)) from exc
        if as_json:
            click.echo(json.dumps(result, sort_keys=True, separators=(",", ":")))
            return
        click.echo(
            f"[OP] network.gateway {status_value} target={target} "
            f"event={result['check_event_id']} failures={failures}"
        )
        belief = result["belief"]
        click.echo(
            f"[BLF] system.network={belief['claim_value']} "
            f"{belief['event_type']} belief={belief['belief_id']}"
        )
        recovery = result["recovery"]
        if recovery is not None:
            verdict = recovery["verdict"]
            click.echo(
                f"[GOV] recovery {verdict['decision']} action={action} "
                f"recovery_id={recovery['recovery_id']} reason={verdict['reason']}"
            )
    finally:
        conn.close()


@operation_group.command("clock-check")
@click.option(
    "--status",
    "status_value",
    required=True,
    type=click.Choice([operation.STATUS_OK, operation.STATUS_FAIL]),
)
@click.option("--detail", default="")
@click.option("--json", "as_json", is_flag=True)
def operation_clock_check(
    status_value: str,
    detail: str,
    as_json: bool,
) -> None:
    conn = get_conn()
    try:
        try:
            result = operation.record_clock_check(
                conn,
                status=status_value,
                detail=detail,
            )
            conn.commit()
        except ValueError as exc:
            conn.rollback()
            raise click.ClickException(str(exc)) from exc
        if as_json:
            click.echo(json.dumps(result, sort_keys=True, separators=(",", ":")))
            return
        click.echo(
            f"[OP] clock.sync {status_value} target={operation.CLOCK_TARGET} "
            f"event={result['check_event_id']}"
        )
        belief = result["belief"]
        click.echo(
            f"[BLF] system.clock={belief['claim_value']} "
            f"{belief['event_type']} belief={belief['belief_id']}"
        )
    finally:
        conn.close()


@operation_group.command("recovery-result")
@click.option("--recovery-id", required=True, type=int)
@click.option(
    "--result",
    "result_value",
    required=True,
    type=click.Choice(
        [
            operation.RECOVERY_SUCCEEDED,
            operation.RECOVERY_FAILED,
            operation.RECOVERY_SCHEDULED,
        ]
    ),
)
@click.option("--detail", default="")
@click.option("--json", "as_json", is_flag=True)
def operation_recovery_result(
    recovery_id: int,
    result_value: str,
    detail: str,
    as_json: bool,
) -> None:
    conn = get_conn()
    try:
        try:
            event_id = operation.record_recovery_result(
                conn,
                recovery_id=recovery_id,
                result=result_value,
                detail=detail,
            )
            conn.commit()
        except ValueError as exc:
            conn.rollback()
            raise click.ClickException(str(exc)) from exc
        result = {
            "recovery_id": recovery_id,
            "result": result_value,
            "event_id": event_id,
        }
        if as_json:
            click.echo(json.dumps(result, sort_keys=True, separators=(",", ":")))
            return
        click.echo(
            f"[OP] recovery {recovery_id} {result_value} event={event_id}"
        )
    finally:
        conn.close()


@operation_group.command("list")
@click.option("--n", default=20, show_default=True, type=int)
def operation_list(n: int) -> None:
    conn = get_conn()
    try:
        rows = operation.list_operations(conn, limit=n)
        click.echo("OPERATIONS")
        click.echo("id  type      check_key        status     target")
        for row in rows:
            click.echo(
                f"{row['id']:<3} {row['operation_type']:<9} "
                f"{row['check_key']:<16} {row['status']:<10} {row['target']}"
            )
            click.echo(f"    payload: {json.dumps(row['payload'], sort_keys=True)}")
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
        click.echo("[REPLAY] Rebuilding operation_log...")
        summary = event_router.replay(conn)
        after = _state_snapshot(conn)
        click.echo(
            f"[REPLAY] Result: {summary['active_beliefs']} active belief(s), "
            f"{summary['proposals']} proposal(s), {summary['inquiries']} inquiry(s), "
            f"{summary['experiences']} experience(s), "
            f"{summary['active_states']} active state(s), "
            f"{summary['governance_decisions']} governance decision(s), "
            f"{summary['operations']} operation(s), "
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
                f"operations={result['operations']} "
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


@ledger_group.command("reseal")
@click.option("--force", is_flag=True, help="reseal even if the chain currently verifies")
def ledger_reseal(force: bool) -> None:
    """Repair the seal chain after an accidental fork (e.g. concurrent writers). Recomputes
    the chain hashes in id order; event content and order are untouched. Deliberate
    maintenance — resets tamper-evidence over the span."""
    conn = get_conn()
    try:
        if not sealing.is_active(conn):
            click.echo("[SEAL] sealing not initialized")
            return
        issues = sealing.verify_chain(conn)
        if not issues and not force:
            click.echo("[SEAL] chain already verifies — nothing to reseal (use --force to reseal anyway)")
            return
        if issues:
            click.echo(f"[SEAL] chain broken: {issues[0]} — resealing…")
        n = sealing.reseal(conn)
        conn.commit()
        remaining = sealing.verify_chain(conn)
        if remaining:
            for issue in remaining:
                click.echo(f"[SEAL] STILL FAIL {issue}")
            raise click.ClickException("reseal did not produce a valid chain")
        click.echo(f"[SEAL] resealed {n} event(s); chain now verifies, head={sealing.head(conn)['seal']}")
    finally:
        conn.close()


@ledger_group.group("anchor")
def ledger_anchor_group() -> None:
    pass


@ledger_anchor_group.command("create")
@click.option("--core-id", envvar="GENUS_CORE_ID")
@click.option("--out", "out_path", type=click.Path(path_type=Path))
def ledger_anchor_create(core_id: str | None, out_path: Path | None) -> None:
    conn = get_conn()
    try:
        try:
            artifact = anchor.create_anchor(conn, core_id)
        except anchor.AnchorError as exc:
            raise click.ClickException(str(exc)) from exc

        text = anchor.canonical_json(artifact)
        if out_path is None:
            click.echo(text)
            return

        target = out_path
        if target.exists() and target.is_dir():
            target = target / anchor.filename_for_anchor(artifact)
        target.write_text(text + "\n", encoding="utf-8")
        click.echo(f"[ANCHOR] wrote {target}")
    finally:
        conn.close()


@ledger_anchor_group.command("verify")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--core-id", envvar="GENUS_CORE_ID")
def ledger_anchor_verify(path: Path, core_id: str | None) -> None:
    conn = get_conn()
    try:
        try:
            artifact = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise click.ClickException(f"invalid anchor file: {exc}") from exc

        issues = anchor.verify_anchor(conn, artifact, core_id=core_id)
        if not issues:
            click.echo(
                f"[ANCHOR] OK core_id={artifact['core_id']} "
                f"head_event_id={artifact['head_event_id']} head={artifact['head']}"
            )
            return

        for issue in issues:
            click.echo(f"[ANCHOR] FAIL {issue}")
        raise click.ClickException("anchor verification failed")
    finally:
        conn.close()


def _parse_governance_target(target: str | None) -> tuple[str | None, int | None]:
    if target is None:
        return None, None
    if ":" not in target:
        raise click.ClickException("--target must look like proposal:<id>")
    target_type, raw_id = target.split(":", 1)
    if target_type not in {"proposal", "operation_recovery"}:
        raise click.ClickException(
            "only proposal:<id> and operation_recovery:<id> targets are supported"
        )
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
    operation_rows = conn.execute(
        """
        SELECT id, operation_type, check_key, status, target, payload,
               derivation, source_event
        FROM operation_log
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
        "operations": [dict(row) for row in operation_rows],
        "rules": [dict(row) for row in rule_rows],
    }


if __name__ == "__main__":
    main()
