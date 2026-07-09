from __future__ import annotations

import json
import os
from pathlib import Path

import click

from genus import (
    abnahme,
    abstraktion,
    anchor,
    bauplan,
    besinnung,
    companion,
    control,
    db,
    deduktion,
    druck,
    doctor as doctor_checks,
    event_router,
    experience,
    gedanke,
    gender_rule,
    governance,
    hypothese,
    inference,
    inquiries,
    integrity,
    learning,
    ledger,
    mathematik,
    maturation,
    motor,
    operation,
    planer,
    projection,
    proposals,
    query,
    reactors,
    recht,
    sealing,
    sensor,
    sources,
    state,
    umsetzung,
    werkstatt,
    werkzeug,
    werkzeuge_seed,
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
    from genus import auskunft, companion, constants, experience, maturation, rechnen, rules, verstehen, werkzeug, werkzeuge_seed, ziele

    metric_keys = sorted({getattr(rules, n) for n in dir(rules) if n.endswith("_METRIC_KEY")})
    reactors = [reactor.__name__ for reactor in rules.REACTORS]
    detectors = [detector.__name__ for detector in experience.DETECTORS]
    kandidaten = [quelle.__name__ for quelle in maturation.KANDIDATEN]
    budget = sorted(n for n in dir(constants) if n.endswith("_THRESHOLD"))

    # Ronnys Frage (2026-07-03: "kann die Doku nicht völlig abgeleitet sein? dann wäre sie
    # immer auf Stand") -- der Zustand des Ziel-Graphen und der Dispatch-Umfang sind
    # CODE-Zustand (keine DB nötig, ziele.py/companion.py/verstehen.py sind die Quelle), also
    # gehören auch sie hierher statt als von-Hand-getippte Zahl in Commit-Texten und Roadmap.
    faehigkeiten_status = {f_id: status for f_id, _, status in ziele.FAEHIGKEIT_SEED}
    status_zaehlung = {"live": 0, "teilweise": 0, "fehlt": 0}
    for status in faehigkeiten_status.values():
        status_zaehlung[status] = status_zaehlung.get(status, 0) + 1
    # Die deterministischen Dispatch-Muster leben teils in companion, teils in den seit Schritt ②
    # herausgelösten Werkzeug-Modulen (rechnen). Der Fakt zählt die FÄHIGKEIT, nicht die Datei --
    # also über alle Dispatch-tragenden Module, damit ein reiner Umzug die Zahl nicht driften lässt.
    _MUSTER_MODULE = (companion, rechnen, auskunft)
    pattern_listen = [(m, n) for m in _MUSTER_MODULE for n in dir(m)
                      if n.isupper() and n.endswith("_PATTERNS")]
    muster_gesamt = sum(len(getattr(m, n)) for m, n in pattern_listen)
    werkzeuge_seed.registriere_mathe_werkzeuge()
    companion.registriere_zellen()
    werkzeuge = werkzeug.alle()
    wortlautfest_n = sum(1 for w in werkzeuge if w.wortlautfest)
    zellen_n = sum(1 for w in werkzeuge if w.name.startswith(companion.ZELLE_PREFIX))

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
            f"- **Reifungs-Kandidaten ({len(kandidaten)}):** " + ", ".join(kandidaten),
            f"- **Preset-Budget ({len(budget)} feste Schwellen):** " + ", ".join(budget),
            f"- **Ziele:** {len(ziele.ZIEL_SEED) - 1} Ziele, {len(ziele.FAEHIGKEIT_SEED)} "
            f"Fähigkeiten ({status_zaehlung['live']} live, {status_zaehlung['teilweise']} "
            f"teilweise, {status_zaehlung['fehlt']} fehlt), {len(ziele.ZIEL_BRAUCHT)} braucht-Kanten",
            f"- **Verstehens-Raster:** {len(verstehen.RASTER_SEED)} Feinblätter, "
            f"{len(verstehen.ZELLEN)} Zwicky-Zellen",
            f"- **Companion-Dispatch:** {len(pattern_listen)} Muster-Listen "
            f"({muster_gesamt} Muster gesamt), {zellen_n} handelbare Zellen "
            f"(als Werkzeuge registriert)",
            f"- **Werkzeugbauer:** {len(werkzeuge)} registrierte Werkzeuge "
            f"({wortlautfest_n} wortlautfest, davon {zellen_n} Gesprächszellen)",
            f"- **Event-Router:** {len(event_router.PROJEKTOREN)} registrierte Projektoren, "
            f"{len(event_router.BEWUSST_ROH)} bewusst-rohe Event-Typen "
            f"(Vertrag: jeder geschriebene Typ ist entschieden, test_event_vertrag)",
            f"- **Selbst-Codieren Stufe 1:** {len(umsetzung.UMSETZUNGEN)} registrierte "
            f"Umsetzungs-Art(en) ({', '.join(sorted(umsetzung.UMSETZUNGEN))}) — nur "
            f"Graph-Wissen, Ausführung erst nach Freigabe",
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
    """Ask GENUS something — about its own state (status/zustand/…) or about a word it knows."""
    conn = get_conn()
    try:
        q = " ".join(question)
        state = query.ask(conn, q)                 # first: a recognised state/belief query?
        if state.get("kind") != "unknown":
            _print_ask_response(state)
            return
        rel = companion.relate(conn, q)            # then: a relational "ist ein X ein Y?" question?
        if rel.get("relational"):
            click.echo(f"[ASK] {companion.narrate_relation(conn, rel)}")
            return
        kau = companion.relate_kausal(conn, q)     # then: a causal "verursacht X Y?" question?
        if kau.get("kausal_q"):
            click.echo(f"[ASK] {companion.narrate_kausal(conn, kau)}")
            return
        com = companion.common(conn, q)            # then: "was haben X und Y gemeinsam?"
        if com.get("common"):
            click.echo(f"[ASK] {companion.narrate_common(conn, com)}")
            return
        gen = companion.gender_question(conn, q)   # then: "welches Geschlecht hat X?"
        if gen.get("gender_q"):
            click.echo(f"[ASK] {companion.narrate_gender(gen)}")
            return
        knows = companion.answer(conn, q)          # else: does GENUS know a word in the question?
        if knows["found"]:
            _print_companion_answer(knows)
        else:
            _print_ask_response(state)             # neither -> the "unknown pattern" help
    finally:
        conn.close()


def _print_companion_answer(a: dict) -> None:
    click.echo(f"[ASK] {companion.narrate(a)}")          # the glass-box voice
    if a.get("concept"):
        click.echo(f"[ASK] (Konzept {a['concept']} — `genus concept {a['concept']}` für die Herkunft)")


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


@main.command("teach-relation")
@click.argument("subject")
@click.argument("predicate")
@click.argument("object")
@click.option("--source", default="human", show_default=True)
def teach_relation_command(subject: str, predicate: str, object: str, source: str) -> None:
    """Teach the correct relation and settle any open conflict — the teacher-loop for knowledge."""
    conn = get_conn()
    try:
        result = reactors.teach_relation(conn, subject, predicate, object, source)
        settled = len(result["resolved_inquiries"])
        dropped = result["retracted_objects"]
        msg = (f"[TCH] {sources.display(conn, subject)} -[{predicate}]-> "
               f"{sources.display(conn, object)} (source={source}) — "
               f"settled {settled} inquiry(ies)")
        if dropped:
            msg += f", retracted {len(dropped)} wrong object(s)"
        click.echo(msg)
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


@main.command("knowledge")
@click.option("--weakest", default=5, show_default=True, help="how many least-confident relations to show")
def knowledge_command(weakest: int) -> None:
    """GENUS's epistemic self-report for the knowledge graph — how much it knows and how surely."""
    conn = get_conn()
    try:
        k = sources.characterize_knowledge(conn, weakest=weakest)
        click.echo(
            f"[KNOW] {k['n_relations']} relation(s), mean confidence {k['mean_confidence']:.2f}, "
            f"{k['n_uncorroborated']} uncorroborated (single source), "
            f"{k['open_contradictions']} open contradiction(s), "
            f"{len(k['is_a_cycles'])} is_a cycle(s)"
        )
        if k["is_a_cycles"]:
            click.echo("[KNOW] is_a cycles (structural self-contradictions — a hierarchy must be acyclic):")
            for cycle in k["is_a_cycles"]:
                ring = " -> ".join(sources.display(conn, n) for n in cycle) + " -> " + sources.display(conn, cycle[0])
                click.echo(f"[KNOW]   {ring}")
        thr, seed = k["transitivity_threshold"], k["transitivity_seed"]
        if thr is None:
            click.echo(f"[KNOW] transitivity threshold: {seed} (seed — not yet self-calibrated; run 'genus scan')")
        elif thr == seed:
            click.echo(f"[KNOW] transitivity threshold: {thr} (self-calibrated, equals the seed — validated by the data)")
        else:
            click.echo(f"[KNOW] transitivity threshold: {thr} (self-calibrated from the natural gap; seed was {seed})")
        srate, sseed = k["symmetry_rate"], k["symmetry_seed"]
        if srate is None:
            click.echo(f"[KNOW] symmetry rate: {sseed} (seed — not yet self-calibrated; run 'genus scan')")
        elif abs(srate - sseed) < 1e-9:
            click.echo(f"[KNOW] symmetry rate: {srate} (self-calibrated, equals the seed — validated by the data)")
        else:
            click.echo(f"[KNOW] symmetry rate: {srate} (self-calibrated from the natural gap; seed was {sseed})")
        if k["weakest"]:
            click.echo("[KNOW] least confident:")
            for r in k["weakest"]:
                click.echo(
                    f"[KNOW]   {sources.display(conn, r['subject'])} -[{r['predicate']}]-> "
                    f"{sources.display(conn, r['object'])}   conf {r['confidence']:.2f}  ({r['n_sources']} src)"
                )
    finally:
        conn.close()


@main.command("motor")
def motor_command() -> None:
    """GENUS's live self-measurement of its own reasoning engine (der Denk-Motor): for each
    Denkweise, whether its calibration is learned or still on seed, and how often it actually
    fires -- naming honestly the modes that leave no countable trace. Read-time, writes nothing."""
    conn = get_conn()
    try:
        for line in motor.narrate(conn):
            click.echo(line)
    finally:
        conn.close()


@main.command("predict-gender")
@click.argument("noun")
def predict_gender_command(noun: str) -> None:
    """Predict a German noun's grammatical gender from GENUS's own induced suffix rule — glass-
    box (shows the rule, its reliability and support), withholds when the evidence is too thin
    or too noisy to trust rather than guessing."""
    conn = get_conn()
    try:
        form = noun if "@" in noun else f"{noun}@de"
        r = gender_rule.predict_gender(conn, form)
        if not r["found"]:
            click.echo(f"[GEN] kein verlässlicher Hinweis für »{noun}« (Schwelle {r['cut']:.2f}) — GENUS rät nicht.")
            return
        click.echo(
            f"[GEN] »{noun}« vermutlich {r['gender']} — Regel: Endung „-{r['suffix']}\" "
            f"({r['reliability']:.0%} Trefferquote über {r['support']} bekannte Nomen, Schwelle {r['cut']:.2f})"
        )
    finally:
        conn.close()


@main.command("gender-rule")
def gender_rule_command() -> None:
    """GENUS's self-test report for the induced gender-by-suffix rule: leave-one-out accuracy
    and the concrete exceptions a confident rule gets wrong (informative, not a defect)."""
    conn = get_conn()
    try:
        r = gender_rule.self_test(conn)
        if r["accuracy"] is None:
            click.echo("[GEN] noch nicht genug Evidenz für einen Selbst-Test (genus predict-gender liefert erst mit mehr Nomen).")
            return
        click.echo(f"[GEN] Selbst-Test: {r['correct']}/{r['checked']} korrekt (Genauigkeit {r['accuracy']:.0%}), Schwelle {r['cut']:.2f}")
        if r["exceptions"]:
            click.echo("[GEN] Ausnahmen (die Regel sagt X vorher, GENUS kennt tatsächlich Y):")
            for e in r["exceptions"]:
                click.echo(
                    f"[GEN]   {e['noun']}: Regel „-{e['rule']}\" ({e['rule_reliability']:.0%}) sagt "
                    f"{e['predicted']} vorher, tatsächlich: {', '.join(e['actual'])}"
                )
    finally:
        conn.close()


@main.command("ableitung")
@click.argument("term")
@click.option("--variable", default="x", show_default=True)
@click.option("--ordnung", default=1, show_default=True, type=int, help="1=erste, 2=zweite, ...")
def ableitung_command(term: str, variable: str, ordnung: int) -> None:
    """Die Ableitung eines Funktionsterms -- exakt über sympy, nie geraten (Abitur-Ziel,
    erste Aufgabenart: docs/GENUS_ROADMAP.md). Beispiel: genus ableitung "3x^2 + 2x" """
    r = mathematik.ableitung(term, variable, ordnung)
    if not r["ok"]:
        click.echo(f"[MATH] {r['fehler']}")
        raise SystemExit(1)
    strich = "'" * ordnung
    click.echo(f"[MATH] f({variable}) = {r['term']}  ->  f{strich}({variable}) = {r['ableitung']}")


@main.command("extremstellen")
@click.argument("term")
@click.option("--variable", default="x", show_default=True)
def extremstellen_command(term: str, variable: str) -> None:
    """Die Extremstellen eines Funktionsterms -- exakt über sympy (f'=0, klassifiziert über
    f''). Beispiel: genus extremstellen "x^3 - 3x" """
    r = mathematik.extremstellen(term, variable)
    if not r["ok"]:
        click.echo(f"[MATH] {r['fehler']}")
        raise SystemExit(1)
    if not r["punkte"]:
        click.echo(f"[MATH] f({variable}) = {r['term']} hat keine Extremstellen.")
        return
    for p in r["punkte"]:
        click.echo(f"[MATH] {p['art']} bei {variable} = {p['x']} (f({variable}) = {p['y']})")


@main.command("stammfunktion")
@click.argument("term")
@click.option("--variable", default="x", show_default=True)
def stammfunktion_command(term: str, variable: str) -> None:
    """Eine Stammfunktion (unbestimmtes Integral) eines Funktionsterms -- exakt über sympy.
    Beispiel: genus stammfunktion "3x^2 + 2x" """
    r = mathematik.stammfunktion(term, variable)
    if not r["ok"]:
        click.echo(f"[MATH] {r['fehler']}")
        raise SystemExit(1)
    click.echo(f"[MATH] f({variable}) = {r['term']}  ->  F({variable}) = {r['stammfunktion']}")


@main.command("integral")
@click.argument("term")
@click.argument("untere_grenze")
@click.argument("obere_grenze")
@click.option("--variable", default="x", show_default=True)
def integral_command(term: str, untere_grenze: str, obere_grenze: str, variable: str) -> None:
    """Das bestimmte Integral eines Funktionsterms zwischen zwei Grenzen -- exakt über sympy.
    Beispiel: genus integral "x^2" 0 3 """
    r = mathematik.integral(term, untere_grenze, obere_grenze, variable)
    if not r["ok"]:
        click.echo(f"[MATH] {r['fehler']}")
        raise SystemExit(1)
    click.echo(
        f"[MATH] Integral von f({variable}) = {r['term']} von {r['untere_grenze']} bis "
        f"{r['obere_grenze']} = {r['integral']}"
    )


@main.group(name="werkstatt")
def werkstatt_group() -> None:
    """Die Werkstatt (Selbst-Codieren Stufe 2): Code-Entwürfe entstehen, werden geprüft
    und warten auf den menschlichen Merge -- nie automatisch Teil der Hülle."""


@werkstatt_group.command("entwerfe")
@click.argument("blatt")
@click.option("--code-datei", default=None,
              help="fertiger Handler-Code aus einer Datei (die Membran schreibt, "
                   "der Kern nimmt an — z.B. vom Schmied)")
@click.option("--bauplan-datei", default=None,
              help="morphologischer Bauplan (JSON) — das Fügewerk baut den Code "
                   "deterministisch (genus/bauplan.py)")
@click.option("--abnahme-datei", default=None,
              help="Abnahme-Vertrag (JSON) — Beispielfälle (guess+Graph → erwarteter Satz "
                   "oder None), aus denen der Kern den VERHALTENS-Test erzeugt (genus/abnahme.py)")
@click.option("--quelle", default=None,
              help="Herkunfts-Angabe für die Ledger-Spur (z.B. werkstatt:schmied)")
def werkstatt_entwerfe(blatt: str, code_datei: str | None, bauplan_datei: str | None,
                       abnahme_datei: str | None, quelle: str | None) -> None:
    """Erzeugt ein Entwurfs-Paar (Handler + Sandbox-Test) für ein Raster-Blatt."""
    generator = None
    vertrag = None
    if abnahme_datei is not None:
        daten = json.loads(Path(abnahme_datei).read_text(encoding="utf-8"))
        vertrag = abnahme.aus_json(daten)
        fehler = abnahme.pruefe_vertrag(vertrag)
        if fehler:
            raise click.ClickException("Abnahme-Vertrag nicht prüfbar:\n" + "\n".join(fehler))
    if code_datei is not None and bauplan_datei is not None:
        raise click.ClickException("--code-datei und --bauplan-datei schließen sich aus")
    if bauplan_datei is not None:
        plan = json.loads(Path(bauplan_datei).read_text(encoding="utf-8"))
        fehler = bauplan.pruefe_bauplan(plan)
        if fehler:
            raise click.ClickException("Bauplan nicht fügbar:\n" + "\n".join(fehler))
        code = bauplan.fuege_zusammen(blatt, plan)
        generator = lambda _blatt: code   # noqa: E731 - gefügter Code kommt als Daten
        if quelle is None:
            quelle = "werkstatt:bauplan"
    if code_datei is not None:
        code = Path(code_datei).read_text(encoding="utf-8")
        generator = lambda _blatt: code   # noqa: E731 - bewusst: Code kommt als Daten herein
        if quelle is None:
            quelle = "werkstatt:datei"
    conn = get_conn()
    try:
        ergebnis = werkstatt.entwerfe_zelle(conn, blatt, generator=generator, quelle=quelle,
                                            vertrag=vertrag)
    finally:
        conn.close()
    if not ergebnis["erstellt"]:
        click.echo(f"[WERKSTATT] {ergebnis['grund']}")
        raise click.exceptions.Exit(1)
    click.echo(f"[WERKSTATT] Entwurf erstellt ({ergebnis['quelle']}):")
    click.echo(f"[WERKSTATT]   Handler: {ergebnis['handler']}")
    click.echo(f"[WERKSTATT]   Test:    {ergebnis['test']}")
    click.echo("[WERKSTATT] Probefahrt: deploy/werkstatt_probefahrt.sh " + blatt)


@werkstatt_group.command("finde")
@click.argument("blatt")
@click.option("--abnahme-datei", required=True,
              help="Abnahme-Vertrag (JSON): die Beispielfälle, aus denen GENUS den Bauplan SCHLIESST")
def werkstatt_finde(blatt: str, abnahme_datei: str) -> None:
    """SCHLIESST aus einem Abnahme-Vertrag selbst einen Bauplan (Deduktion über die bewährten
    Bausteine, KEIN LLM) und legt daraus einen Entwurf an -- gläsern: zeigt, was es sich
    zusammengeschlossen hat. Der Abnahme-Vertrag beweist die Zelle in der Probefahrt; der
    Merge bleibt menschlich."""
    daten = json.loads(Path(abnahme_datei).read_text(encoding="utf-8"))
    vertrag = abnahme.aus_json(daten)
    fehler = abnahme.pruefe_vertrag(vertrag)
    if fehler:
        raise click.ClickException("Abnahme-Vertrag nicht prüfbar:\n" + "\n".join(fehler))
    plan = planer.finde_bauplan(vertrag)
    click.echo(f"[PLANER] {planer.narrate(plan)}")
    if plan is None:
        raise click.exceptions.Exit(1)
    code = bauplan.fuege_zusammen(blatt, plan)
    conn = get_conn()
    try:
        ergebnis = werkstatt.entwerfe_zelle(conn, blatt, generator=lambda _b: code,
                                            quelle="werkstatt:planer", vertrag=vertrag)
    finally:
        conn.close()
    if not ergebnis["erstellt"]:
        click.echo(f"[WERKSTATT] {ergebnis['grund']}")
        raise click.exceptions.Exit(1)
    click.echo(f"[WERKSTATT] Entwurf erstellt ({ergebnis['quelle']}):")
    click.echo(f"[WERKSTATT]   Handler: {ergebnis['handler']}")
    click.echo(f"[WERKSTATT]   Test:    {ergebnis['test']}")
    click.echo("[WERKSTATT] Probefahrt: deploy/werkstatt_probefahrt.sh " + blatt)


@werkstatt_group.command("liste")
def werkstatt_liste() -> None:
    """Alle Entwürfe in der Werkstatt."""
    eintraege = werkstatt.liste()
    if not eintraege:
        click.echo(f"[WERKSTATT] leer ({werkstatt.verzeichnis()})")
        return
    for e in eintraege:
        click.echo(f"[WERKSTATT] {e['blatt']:<20} {e['fingerabdruck']}  {e['pfad']}")


@werkstatt_group.command("pruefe")
@click.argument("blatt")
@click.option("--tests-exit", type=int, default=None,
              help="Ergebnis der Sandbox-Probefahrt (übergibt die Membran)")
def werkstatt_pruefe(blatt: str, tests_exit: int | None) -> None:
    """Prüft einen Entwurf und protokolliert die Entscheidung: Verbots-Scan immer (Kern),
    Probefahrt-Ergebnis, falls die Membran (deploy/werkstatt_probefahrt.sh) eines übergibt."""
    conn = get_conn()
    try:
        ergebnis = werkstatt.protokolliere_pruefung(conn, blatt, tests_exit)
    finally:
        conn.close()
    if not ergebnis["gefunden"]:
        click.echo(f"[WERKSTATT] {ergebnis['grund']}")
        raise click.exceptions.Exit(1)
    if ergebnis["verbote"]:
        click.echo(f"[WERKSTATT] VERBOTE gefunden: {', '.join(ergebnis['verbote'])}")
    if ergebnis["tests_exit"] is None:
        click.echo("[WERKSTATT] nur statisch geprüft — Probefahrt: "
                   f"deploy/werkstatt_probefahrt.sh {blatt}")
    else:
        click.echo(f"[WERKSTATT] Probefahrt tests_exit={ergebnis['tests_exit']}")
    click.echo(f"[WERKSTATT] bestanden={ergebnis['bestanden']} "
               "(bestanden = merge-REIF; der Merge bleibt menschlich)")


@main.command("kurvendiskussion")
@click.argument("term")
@click.option("--variable", default="x", show_default=True)
def kurvendiskussion_command(term: str, variable: str) -> None:
    """Die Kurvendiskussion eines Funktionsterms -- das erste komponierte Werkzeug (Rezept):
    Nullstellen -> Extremstellen -> Grenzverhalten, jeder Schritt exakt über sympy."""
    werkzeuge_seed.registriere_mathe_werkzeuge()
    w = werkzeug.registriert("kurvendiskussion")
    r = w.implementierung(term, variable)
    for zeile in w.formulierung(r).splitlines():
        click.echo(f"[MATH] {zeile}")


@main.command("subsumtion")
@click.argument("norm")
@click.option("--erfuellt", "erfuellt", multiple=True, metavar="merkmal=quelle",
              help="ein im Fall erfülltes Merkmal mit seiner Quelle, z.B. "
                   "merkmal:angebot=dokument:vertrag  oder  merkmal:faelligkeit=ronny")
@click.option("--text", "text", default=None, metavar="SCHILDERUNG",
              help="freie Fallschilderung -- das Sprachmodell liest sie in Merkmale "
                   "(Fakt→Merkmal, an der Grenze gehalten), der Kern rechnet die Subsumtion")
def subsumtion_command(norm: str, erfuellt: tuple[str, ...], text: str | None) -> None:
    """Die erste Denkweise: juristische Subsumtion (docs/GENUS_INTELLIGENZ.md §4). Prüft eine
    Anspruchsnorm (Bauplan im Graphen) gegen einen Sachverhalt und rendert den Beweisbaum
    inkl. Beweislast-Radar. Entweder --erfuellt (Merkmal=Quelle, exakt) ODER --text (freie
    Schilderung, vom Modell gelesen). Read-only; kein Anwalt."""
    conn = get_conn()
    try:
        recht.seed_normen(conn)
        conn.commit()
        if text:
            import sys as _sys
            _sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "deploy"))
            import deuter as _deuter

            def _lies(t, blaetter):
                grenze = recht.gbnf_sachverhalt([b["id"] for b in blaetter])
                return _deuter.merkmale(t, blaetter, grammatik=grenze)

            frei = recht.subsumiere_frei(conn, norm, text, _lies)
            for zeile in recht.narrate_frei(conn, frei).splitlines():
                click.echo(f"[RECHT] {zeile}")
            e = frei["ergebnis"]
        else:
            sachverhalt: dict[str, str] = {}
            for paar in erfuellt:
                merkmal, _, quelle = paar.partition("=")
                if merkmal and quelle:
                    sachverhalt[merkmal] = quelle
            e = recht.subsumiere(conn, norm, sachverhalt)
            for zeile in recht.narrate_subsumtion(conn, e).splitlines():
                click.echo(f"[RECHT] {zeile}")
        if e["vertrauen"] is not None:
            click.echo(f"[RECHT] Vertrauen (schwächste Prämisse): {e['vertrauen']}")
    finally:
        conn.close()


@main.command("hypothese")
@click.argument("subjekt")
@click.option("--tick", is_flag=True,
              help="die eine offene Top-Vermutung als gedeckelte Kante aussprechen (Proposal≠Change)")
def hypothese_command(subjekt: str, tick: bool) -> None:
    """Die Denkweise HYPOTHESE (docs/GENUS_INTELLIGENZ.md): GENUS VERMUTET per Geschwister-Analogie
    eine neue Beziehung und PRÜFT sie mit der Inferenz (bestätigt/widerlegt/offen) — der aktive
    Halbkreis, der den Methoden-Bogen schließt. Ohne --tick wird KEINE VERMUTUNG geschrieben (das
    Reflektieren ist schreibfrei; nur das geerdete Disjunktheits-Weltwissen wird einmalig gesät,
    wie die Norm); --tick spricht die eine offene Vermutung gedeckelt aus (model:hypothese, Trust
    ≤ 0.25 — überstimmt nie Geerdetes)."""
    conn = get_conn()
    try:
        hypothese.seed_hypothesen(conn)   # geerdetes Bootstrap-Wissen (welt), idempotent — wie recht.seed_normen
        conn.commit()
        e = hypothese.vermute_und_teste(conn, subjekt)
        if e is None:
            click.echo(f"[HYP] Zu „{subjekt}“ finde ich keine testbare Vermutung "
                       f"(zu wenige Geschwister oder alles schon bekannt).")
            return
        for z in hypothese.narrate_hypothese(conn, e).splitlines():
            click.echo(f"[HYP] {z}")
        if not tick:
            if e["urteil"] == "offen":
                click.echo(f"[HYP] (genus hypothese {subjekt} --tick, um sie als Vermutung "
                           f"auszusprechen — gedeckelt, überstimmt nichts.)")
            return
        if e["urteil"] != "offen":
            click.echo("[HYP] Diese Vermutung ist nicht offen — ich spreche nur offene aus.")
            return
        if hypothese.emit_vermutung(conn, e):
            conn.commit()
            click.echo("[HYP] ausgesprochen als Vermutung (model:hypothese, Trust ≤ 0.25).")
        else:
            click.echo("[HYP] war schon ausgesprochen — kein Duplikat.")
    finally:
        conn.close()


@main.command("abstraktion")
@click.option("--limit", "limit", default=10, show_default=True,
              help="wie viele Begriffs-Kandidaten höchstens zeigen")
@click.option("--unter", "unter", default=None, metavar="KNOTEN",
              help="nur unter diesem is_a-Elternteil suchen (sonst der ganze Graph)")
@click.option("--tick", is_flag=True,
              help="den EINEN stärksten Kandidaten als gedeckelten Knoten PRÄGEN (Proposal≠Change)")
@click.option("--pruefe", is_flag=True,
              help="die schon geprägten Begriffe gegen den Graphen prüfen (Vorhersage/Widerspruch, rein lesend)")
def abstraktion_command(limit: int, unter: str | None, tick: bool, pruefe: bool) -> None:
    """Die Operation ABSTRAHIEREN (faehigkeit:abstrahieren): GENUS findet Gruppen von Geschwistern,
    die ein noch UNBENANNTES Merkmal-Bündel teilen UND eine weitere Eigenschaft vorhersagen — der
    Keim eines eigenen Begriffs (docs/GENUS_INTELLIGENZ.md: Verdichtung, kürzer als die Fakten).
    Ohne --tick REIN LESEND (zeigt nur, was GENUS abstrahieren würde; schreibt nichts, ruft kein
    Modell). --tick PRÄGT den stärksten Kandidaten als gedeckelten Knoten (Quelle model:abstraktion,
    Trust ≤ 0.25 — überstimmt nie Geerdetes); der Mensch bestätigt (teach) oder verwirft (retract)."""
    conn = get_conn()
    try:
        if pruefe:
            begriffe = abstraktion.gepraegte_begriffe(conn)
            if not begriffe:
                click.echo("[ABS] Noch kein geprägter Begriff.")
                return
            click.echo(f"[ABS] {len(begriffe)} geprägte(r) Begriff(e) — Rückkopplung gegen den Graphen:")
            for kid, _p in begriffe:
                r = abstraktion.rueckkopplung(conn, kid)
                click.echo(f"\n[ABS] {kid} (unter {r['elternteil']}, {len(r['mitglieder'])} Mitglieder)")
                if r["vorhergesagt"]:
                    click.echo(f"[ABS]   VORHERSAGE: auch {', '.join(r['vorhergesagt'][:8])} tragen "
                               f"das ganze Bündel — sollten sie dazugehören?")
                if not r["stimmig"]:
                    click.echo("[ABS]   WIDERSPRUCH: die Mitglieder bilden keine kohärente Gruppe mehr.")
                if r["stimmig"] and not r["vorhergesagt"]:
                    click.echo("[ABS]   stimmig, keine offene Vorhersage.")
            return
        kandidaten = (abstraktion.verdichte(conn, unter) if unter
                      else abstraktion.entdecke(conn, hoechstens=limit))[:limit]
        if not kandidaten:
            click.echo("[ABS] Kein Begriffs-Kandidat gefunden — noch kein ungenanntes Muster, "
                       "das eine Überraschung vorhersagt.")
            return
        click.echo(f"[ABS] {len(kandidaten)} Begriffs-Kandidat(en) — noch unbenannte Muster im "
                   f"eigenen Graphen:")
        for k in kandidaten:
            click.echo("")
            for z in abstraktion.narrate(conn, k).splitlines():
                click.echo(f"[ABS] {z}")
        if not tick:
            click.echo("")
            click.echo("[ABS] (--tick, um den stärksten zu PRÄGEN — gedeckelt, überstimmt nichts.)")
            return
        ergebnis = abstraktion.praege(conn, kandidaten[0])
        if ergebnis["gesaet"]:
            conn.commit()
            click.echo(f"\n[ABS] geprägt: {ergebnis['konzept']} ({ergebnis['gesaet']} Kanten, "
                       f"model:abstraktion, Trust ≤ 0.25). Fragen: genus concept "
                       f"{ergebnis['konzept']}. Bestätigen/verwerfen wie jede model:*-Kante.")
        else:
            click.echo(f"\n[ABS] {ergebnis['konzept']} war schon geprägt — kein Duplikat.")
    finally:
        conn.close()


@main.command("gedanken-push")
def gedanken_push_command() -> None:
    """Der proaktive GEDANKE (Ronny 2026-07-08): das WICHTIGE — Entscheidungs-Vorschläge + selbst
    gebildete Begriffs-Fragen — wird SOFORT eine bestätigte Nachricht-Hand (fällig jetzt), statt bis
    zum Morgen aufgestaut zu werden. Idempotent (ein Gedanke → einmal), gedeckelt durch den Anti-
    Weglauf der Hand. Der Membran-Cron (hand_ausfuehren.sh) sendet die fälligen Hände."""
    if control.is_paused():
        click.echo("[GEDANKE] paused — skipping (genus resume to continue)")
        return
    conn = get_conn()
    try:
        neu = gedanke.push(conn)
        if neu:
            conn.commit()
        click.echo(f"[GEDANKE] {len(neu)} neue(r) proaktive(r) Gedanke(n) als Nachricht angelegt "
                   f"(der Sende-Cron schickt sie).")
    finally:
        conn.close()


@main.command("beweise")
@click.argument("ziel")
@click.option("--gegeben", "gegeben", multiple=True, metavar="atom=quelle",
              help="ein als gegeben angenommener Fakt mit seiner Quelle, mehrfach")
def beweise_command(ziel: str, gegeben: tuple[str, ...]) -> None:
    """Der allgemeine Deduktions-Schließer (Rückwärtsverkettung, docs/GENUS_INTELLIGENZ.md):
    „beweise mir ZIEL" — sucht eine Regel (braucht/bewirkt-Bauplan im Graphen), die das Ziel
    bewirkt, und zeigt den gläsernen Beweis inkl. schwächster Prämisse. Domänenfrei, read-only."""
    conn = get_conn()
    try:
        fakten: dict[str, str] = {}
        for paar in gegeben:
            atom, _, quelle = paar.partition("=")
            if atom and quelle:
                fakten[atom] = quelle
        b = deduktion.beweise(conn, ziel, fakten)
        if b is None:
            click.echo(f"[DED] Keine Regel bewirkt „{ziel}“ — kein ableitbares Ziel.")
            return
        for zeile in deduktion.narrate(conn, b["ergebnis"]).splitlines():
            click.echo(f"[DED] {zeile}")
    finally:
        conn.close()


@main.command("besinnung")
@click.option("--tick", is_flag=True, help="einen Besinnungs-Schritt tun (der eine gegatete "
              "Zug: die drängendste unausgesprochene Lücke aussprechen)")
def besinnung_command(tick: bool) -> None:
    """Der innere Loop, dem der Druck sein Gefälle gibt: GENUS' gerichtete Agenda aus dem
    Druck-Gefälle (docs/GENUS_INTELLIGENZ.md §9). Ohne --tick rein lesend (nichts wird
    getan); mit --tick der EINE erlaubte inwendige Schritt (gegatetes Proposal, Proposal≠
    Change) -- bewegt den Geist, nie die Hand."""
    conn = get_conn()
    try:
        for zeile in besinnung.narrate(conn).splitlines():
            click.echo(f"[BESINNUNG] {zeile}")
        if not tick:
            return
        s = besinnung.besinne(conn)
        conn.commit()
        if s["getan"] == "ausgesprochen":
            click.echo(f"[BESINNUNG] ausgesprochen: „{s['kind']}“ -> Proposal #{s['proposal_id']} "
                       f"(Freigabe über genus governance)"
                       + ("  — weitere Not wartet" if s["weiter"] else ""))
        else:
            w = s["worauf"]
            click.echo("[BESINNUNG] nichts selbst zu tun — ich warte "
                       + (f"{w['text']} („{w['was']}“)" if w else "auf nichts Bestimmtes."))
    finally:
        conn.close()


@main.command("werkzeuge")
def werkzeuge_command() -> None:
    """Alle beim Werkzeugbauer registrierten Werkzeuge -- das, was ein Planer sehen würde
    (Ronnys Frage: "woraus besteht ein Werkzeug eigentlich genau?", docs/GENUS_AUDIT_2026_07.md).
    Protokolliert dabei jede noch nicht im Ledger stehende Registrierungs-ENTSCHEIDUNG
    (Phase 3 Scheibe 2: die Hülle hat Herkunft -- dedupliziert, ein zweiter Aufruf schreibt
    nichts)."""
    werkzeuge_seed.registriere_mathe_werkzeuge()
    companion.registriere_zellen()
    for w in werkzeug.alle():
        parameter = ", ".join(
            f"{name}" + ("" if p.pflicht else f"={p.standard!r}")
            for name, p in w.parameter.items()
        )
        flags = []
        if w.schreibt:
            flags.append("schreibt")
        if w.wortlautfest:
            flags.append("wortlautfest")
        flags.append(f"prüfbar_als={w.pruefbar_als}")
        click.echo(f"[WERKZEUG] {w.name}({parameter}) — {w.beschreibung}")
        click.echo(f"[WERKZEUG]   {', '.join(flags)}")
    conn = get_conn()
    try:
        neu = werkzeug.protokolliere_registrierungen(conn)
    finally:
        conn.close()
    click.echo(f"[WERKZEUG] {neu} neue Registrierungs-Entscheidung(en) im Ledger protokolliert")


@main.command("concept")
@click.argument("qid")
def concept_command(qid: str) -> None:
    """What a concept MEANS — its German meaning, is_a, and the words that express it (read-time)."""
    conn = get_conn()
    try:
        c = sources.concept_meaning(conn, qid)
        click.echo(f"[CON] {c['label']}")
        if c["meaning"]:
            for g in c["meaning"]:
                click.echo(f"[CON]   bedeutet: {g}")
        else:
            click.echo("[CON]   (noch keine Bedeutung gebrückt)")
        if c["is_a"]:
            click.echo(f"[CON]   is_a: {', '.join(sources.display(conn, p) for p in c['is_a'])}")
        if c["words"]:
            click.echo(f"[CON]   ausgedrückt durch: {', '.join(c['words'][:12])}")
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


@why_group.command("answer")
@click.argument("question", nargs=-1, required=True)
def why_answer_command(question: tuple[str, ...]) -> None:
    """The provenance behind an answer — origin, sources, trust, the whole chain (glass-box)."""
    conn = get_conn()
    try:
        for line in companion.render_trace(conn, companion.trace(conn, " ".join(question))):
            click.echo(f"[WHY] {line}")
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
    # autonomer Cron-Tick (1-59/5) -- respektiert den Pause-Schalter wie observe-all
    # (Pause-Vertrags-Fund 2026-07-04: dieser Einstieg ignorierte ihn als einziger CLI-Tick)
    if control.is_paused():
        click.echo("[STATE] paused — skipping (genus resume to continue)")
        return
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
        # Selbst-Codieren Stufe 1: trägt das akzeptierte Proposal eine deklarative
        # Umsetzung, wird sie JETZT ausgeführt -- die Freigabe eben war das Gate
        # (Gate-Politik §8: Freigabe pro Stück), genau einmal, nur registrierte Arten.
        if decision == "accepted":
            ergebnis = umsetzung.umsetzen(conn, proposal_id)
            if ergebnis["umgesetzt"]:
                click.echo(f"[GOV] umgesetzt ({ergebnis['art']}): {ergebnis['ergebnis']}")
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


@governance_group.command("acquisition-allowed")
@click.argument("source")
def governance_acquisition_allowed(source: str) -> None:
    """Exit 0 if the autonomous learner may acquire from <source> now, else non-zero — the
    learner consults this each word (pause + self-calibrating source-trust gate)."""
    conn = get_conn()
    try:
        verdict = governance.acquisition_allowed(conn, source)
        if verdict["allowed"]:
            click.echo(f"[GOV] acquisition allowed for {source}")
        else:
            click.echo(f"[GOV] acquisition BLOCKED for {source}: {verdict['reason']}")
            raise SystemExit(1)
    finally:
        conn.close()


@governance_group.command("reboot-threshold")
@click.option("--value-only", is_flag=True, help="Print only the integer (for scripts).")
def governance_reboot_threshold(value_only: bool) -> None:
    """The current reboot-recovery threshold -- self-calibrated from GENUS's own outage history,
    the seed as fallback while there isn't enough of it yet. The network watchdog reads this
    (--value-only) each tick instead of carrying its own separate copy of the number."""
    conn = get_conn()
    try:
        report = governance.reboot_threshold_report(conn)
        if value_only:
            click.echo(report["threshold"])
            return
        basis = "derived from data" if report["derived"] else "seed (no distinguishing pattern yet)"
        click.echo(
            f"[GOV] reboot threshold: {report['threshold']} consecutive failures "
            f"({basis}, {report['episodes']} completed outage episode(s) observed)"
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
