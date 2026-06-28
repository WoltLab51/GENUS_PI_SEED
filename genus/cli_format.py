"""Presentation helpers for the CLI — formatting and printing only.

Extracted from cli.py to separate the command surface from how results are
rendered. These take plain dicts/rows and write with click.echo; the only
domain dependency is projection (for the active-belief summary).
"""

import json

import click

from genus import projection


def _print_calibration(report: dict) -> None:
    n = report["stable_count"]
    if n == 0:
        click.echo("[CAL] no stability judgments yet — nothing to calibrate")
        return
    held = n - len(report["betrayed"])
    click.echo(f"[CAL] stable judgments: {n}  ·  held: {held}  ·  betrayed: {len(report['betrayed'])}")
    click.echo(
        f"[CAL] stable-judgment accuracy: {report['stable_judgment_accuracy']:.3f}  "
        f"(1.0 = a 'stable' belief never surprised me by flipping)"
    )
    sm, vm = report["stable_mean_flip_rate"], report["volatile_mean_flip_rate"]
    if sm is not None and vm is not None:
        verb = "discriminates" if vm > sm else "does NOT discriminate"
        click.echo(
            f"[CAL] mean flip-rate  stable={sm:.3f}  volatile={vm:.3f}  "
            f"(gap {vm - sm:+.3f} — judgment {verb})"
        )
    if report["betrayed"]:
        click.echo(f"[CAL] betrayed: {', '.join(report['betrayed'])}")


def _print_learning(reports: list[dict]) -> None:
    if not reports:
        click.echo("[LRN] no scored forecasts yet — the learners are warming up")
        return
    click.echo("[LRN] forecast skill — how much better than naive (guessing the mean)? <=0 = nothing learned")
    for report in reports:
        if report["skill"] is None:
            note = "warming up" if report["scored"] < 5 else "constant signal"
            click.echo(
                f"[LRN] {report['metric_key']:22s} {report['scored']:4d} scored  "
                f"mean {report['mean_error']:7.3f}  skill    —   ({note})"
            )
            continue
        note = "  <- no real skill: signal too flat to learn" if report["skill"] <= 0.05 else ""
        click.echo(
            f"[LRN] {report['metric_key']:22s} {report['scored']:4d} scored  "
            f"mean {report['mean_error']:7.3f}  skill {report['skill']:+.2f}{note}"
        )


def _print_sources(report: dict) -> None:
    rows = report["sources"]
    if not rows:
        click.echo("[SRC] no sources yet")
        return
    click.echo("[SRC] source trust — earned by agreeing with other sources (0.50 = unproven seed)")
    for row in rows:
        click.echo(f"[SRC] {row['source']:30s} trust {row['trust']:.2f}")
    contested = report["resolved"]
    if contested:
        click.echo("[SRC] claims more than one source speaks to (resolved by trust × freshness):")
        for item in contested:
            mark = "  <- CONTRADICTION" if item["contradiction"] else ""
            cands = ", ".join(
                f"{src}={data['value']}" + ("" if data["live"] else "(faded)")
                for src, data in item["candidates"].items()
            )
            click.echo(
                f"[SRC] {item['claim_key']:22s} -> {item['value']} "
                f"via {item['chosen_source']}  [{cands}]{mark}"
            )


def _print_resolve(result: dict) -> None:
    if result["value"] is None:
        click.echo(f"[RSV] {result['claim_key']}: no source has spoken to this claim")
        return
    mark = "  <- CONTRADICTION" if result["contradiction"] else ""
    click.echo(f"[RSV] {result['claim_key']} -> {result['value']}  via {result['chosen_source']}{mark}")
    click.echo("[RSV] candidates  (value · trust × freshness = weight):")
    ordered = sorted(result["candidates"].items(), key=lambda kv: -kv[1]["weight"])
    for src, c in ordered:
        faded = "" if c["live"] else "   (faded — stale)"
        click.echo(
            f"[RSV]   {src:30s} {str(c['value']):>7}   "
            f"{c['trust']:.2f} × {c['recency']:.2f} = {c['weight']:.2f}{faded}"
        )


def _print_relations(triples: list[dict]) -> None:
    if not triples:
        click.echo("[REL] no relations yet")
        return
    click.echo("[REL] knowledge graph — (subject) -[predicate]-> (object) · source")
    for triple in sorted(triples, key=lambda t: (t["subject"], t["predicate"], t["object"])):
        click.echo(
            f"[REL] {triple['subject']} -[{triple['predicate']}]-> {triple['object']}"
            f"   · {triple['source']}"
        )


def _print_surprisal(rows: list[dict]) -> None:
    if not rows:
        click.echo("[SRP] no characterized beliefs yet")
        return
    click.echo("[SRP] surprise potential — bits a flip would carry (high = most informative)")
    for row in rows:
        click.echo(
            f"[SRP] {row['surprise_bits']:5.1f} bits  {row['subject_key']}  "
            f"({row['classification']}, flip-rate {row['flip_rate']:.3f}, {row['updates']} updates)"
        )


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
    elif response["kind"] == "operations":
        for row in response["operations"]:
            click.echo(
                f"[OP] #{row['id']} {row['operation_type']} "
                f"{row['check_key']} status={row['status']}"
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
