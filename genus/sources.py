"""Source trust + claim resolution — the read-time heart of the WISSEN layer.

A belief is no longer only "what my sensor measured" but "what some source asserted",
and GENUS learns *which sources to trust* from their own track record -- never a preset.
Everything is read-time over the assertion stream (the sensor path ``evidence_recorded``
+ the general path ``assertion_recorded``), exactly like confidence and the learned
half-life: nothing is stored, there is no ``source_trust_updated`` event.

The general form is :func:`resolve` -- *given a claim, what is its current value?* It
takes the candidate assertions (latest value per source) and chooses by a pluggable
criterion: today **trust × freshness**. A stale source fades (recency), a distrusted
one is outweighed (trust). The same shape later carries other criteria (a chess move's
evaluation, a sentence's grounding) -- resolve always *chooses* among candidates; it
never *generates* them.

Efficiency: the stream is read once per call and resolved in memory (grouped by claim).
The live Pi proved this matters -- a per-source/per-claim re-query took seconds on a
20k-event ledger.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

# A new/unproven source starts here. Structural seed, not an epistemic threshold:
# a source we have no agreement record for is held at arm's length. As it builds a
# track record against other sources, the learned agreement rate replaces this.
SOURCE_TRUST_SEED = 0.5

# A candidate counts as a *current* claimant only while it is at least this fresh
# relative to the freshest source -- i.e. within one cadence (one freshness
# half-life). Beyond that it fades and no longer drives selection or contradiction.
# Structural ("one cadence"), derived from the claim's own rhythm, not a magic value.
LIVE_RECENCY = 0.5


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_ts(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def assertions(conn, claim_key: str | None = None) -> list[dict]:
    """The assertion stream: every (claim_key, value, source, time) the ledger holds.

    Unifies the sensor path (``evidence_recorded``, source carried from the
    observation; older events without one read as ``sensor``) and the general path
    (``assertion_recorded``, explicit source). The one DB read; callers resolve it in
    memory. Read-only, ordered by event id.
    """
    # Filter by claim in SQL when one is given, so resolving a single claim (e.g. in a
    # reactor, per observation) reads only that claim's rows -- not the whole stream.
    evidence_filter = "" if claim_key is None else "AND json_extract(payload, '$.metric_key') = ?"
    assertion_filter = "" if claim_key is None else "AND json_extract(payload, '$.claim_key') = ?"
    params = () if claim_key is None else (claim_key, claim_key)
    rows = conn.execute(
        f"""
        SELECT id,
               json_extract(payload, '$.metric_key')   AS claim_key,
               json_extract(payload, '$.metric_value')  AS value,
               COALESCE(json_extract(payload, '$.source'), 'sensor') AS source,
               created_at
        FROM event_log
        WHERE event_type = 'evidence_recorded' {evidence_filter}
        UNION ALL
        SELECT id,
               json_extract(payload, '$.claim_key')    AS claim_key,
               json_extract(payload, '$.claim_value')   AS value,
               json_extract(payload, '$.source')        AS source,
               created_at
        FROM event_log
        WHERE event_type = 'assertion_recorded' {assertion_filter}
        ORDER BY id
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def _group_by_claim(stream: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in stream:
        grouped[row["claim_key"]].append(row)
    return grouped


def _latest_by_source(rows: list[dict]) -> dict[str, dict]:
    """The most recent assertion from each source (the candidates), for one claim."""
    latest: dict[str, dict] = {}
    for row in rows:  # rows are id-ordered, so later overwrites -> latest per source
        if row["source"]:
            latest[row["source"]] = row
    return latest


def _tolerance(values: list[float]) -> float | None:
    """Self-calibrated agree/disagree band: the claim's own spread (1 std).

    Not a constant -- a value within one standard deviation of the claim's lived
    variation counts as agreement. ``None`` when there is too little history to learn
    a band (caller then requires exact agreement). The Pi sharpens this.
    """
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return variance ** 0.5


def _agree(a: float, b: float, tolerance: float | None) -> bool:
    if tolerance is None:
        return a == b
    return abs(a - b) <= tolerance


def _cadence_halflife(rows: list[dict]) -> float | None:
    """The claim's own rhythm: the median time between assertions, in seconds.

    Used as the freshness half-life -- a source that has not spoken for one cadence is
    half as current. Self-calibrated from the data; ``None`` when there is too little
    history (then nothing fades -- behaviour stays as it was before recency).
    """
    times = sorted(t for t in (_parse_ts(r["created_at"]) for r in rows) if t is not None)
    if len(times) < 2:
        return None
    gaps = [(times[i + 1] - times[i]).total_seconds() for i in range(len(times) - 1)]
    gaps = sorted(g for g in gaps if g > 0)
    if not gaps:
        return None
    mid = len(gaps) // 2
    return gaps[mid] if len(gaps) % 2 else (gaps[mid - 1] + gaps[mid]) / 2


def _trust(by_claim: dict[str, list[dict]], source: str) -> float:
    agreements: list[float] = []
    for rows in by_claim.values():
        latest = _latest_by_source(rows)
        mine = _to_float(latest.get(source, {}).get("value"))
        if mine is None:
            continue
        tolerance = _tolerance([v for v in (_to_float(r["value"]) for r in rows) if v is not None])
        for other, row in latest.items():
            if other == source:
                continue
            theirs = _to_float(row["value"])
            if theirs is None:
                continue
            agreements.append(1.0 if _agree(mine, theirs, tolerance) else 0.0)
    if not agreements:
        return SOURCE_TRUST_SEED
    return round(sum(agreements) / len(agreements), 3)


def _resolve(by_claim: dict[str, list[dict]], claim_key: str) -> dict:
    rows = by_claim.get(claim_key, [])
    latest = _latest_by_source(rows)
    if not latest:
        return {
            "claim_key": claim_key,
            "value": None,
            "chosen_source": None,
            "chosen_event": None,
            "candidates": {},
            "contradiction": False,
        }
    halflife = _cadence_halflife(rows)
    times = {src: _parse_ts(row["created_at"]) for src, row in latest.items()}
    reference = max((t for t in times.values() if t is not None), default=None)

    def recency(src: str) -> float:
        if halflife is None or reference is None or times[src] is None:
            return 1.0
        age = max((reference - times[src]).total_seconds(), 0.0)
        return 2 ** (-age / halflife)

    candidates = {}
    for src, row in latest.items():
        rec = recency(src)
        trust = _trust(by_claim, src)
        candidates[src] = {
            "value": row["value"],
            "trust": trust,
            "recency": round(rec, 3),
            "weight": round(trust * rec, 3),
            "live": rec >= LIVE_RECENCY,
        }
    chosen = max(candidates, key=lambda src: (candidates[src]["weight"], latest[src]["id"]))
    chosen_event = int(latest[chosen]["id"])
    # contradiction is judged only among *live* candidates -- a faded source's stale
    # value must not raise a false alarm.
    live_values = [
        v
        for v in (_to_float(c["value"]) for c in candidates.values() if c["live"])
        if v is not None
    ]
    tolerance = _tolerance(
        [v for v in (_to_float(r["value"]) for r in rows) if v is not None]
    )
    contradiction = any(not _agree(a, b, tolerance) for a in live_values for b in live_values)
    return {
        "claim_key": claim_key,
        "value": candidates[chosen]["value"],
        "chosen_source": chosen,
        "chosen_event": chosen_event,
        "candidates": candidates,
        "contradiction": contradiction,
    }


def sources(conn) -> list[str]:
    return sorted({row["source"] for row in assertions(conn) if row["source"]})


def source_trust(conn, source: str) -> float:
    """Read-time trust for ``source``: how often it agrees with other sources.

    Assessed only on claims where at least one *other* source asserted too; with no
    such overlap the source is unproven and held at :data:`SOURCE_TRUST_SEED`.
    """
    return _trust(_group_by_claim(assertions(conn)), source)


def resolve(conn, claim_key: str) -> dict:
    """Resolve a claim to its current value over all sources -- the general form.

    Candidates are the latest value per source; the chosen value is the one with the
    highest **trust × freshness** (ties broken by the most recent assertion). Reports
    each candidate's value/trust/recency/weight and whether it is still *live*, plus a
    contradiction flag judged among the live candidates only. Read-only, nothing stored.
    """
    return _resolve(_group_by_claim(assertions(conn)), claim_key)


def report(conn) -> dict:
    """A read-time summary for the CLI -- each source's trust and the resolution for
    every claim more than one source speaks to. One ledger read, grouped once."""
    by_claim = _group_by_claim(assertions(conn))
    source_names = sorted(
        {row["source"] for rows in by_claim.values() for row in rows if row["source"]}
    )
    contested = [
        _resolve(by_claim, claim_key)
        for claim_key, rows in by_claim.items()
        if len({row["source"] for row in rows if row["source"]}) > 1
    ]
    return {
        "sources": [{"source": src, "trust": _trust(by_claim, src)} for src in source_names],
        "resolved": contested,
    }
