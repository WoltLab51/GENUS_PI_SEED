"""Source trust — the read-time reputation of the sources GENUS knows things from.

Completing the WISSEN layer of the core: a belief is no longer only "what my sensor
measured" but "what some source asserted", and GENUS learns *which sources to trust*
from their own track record -- never a preset. Trust is computed read-time over the
assertion stream (the sensor path ``evidence_recorded`` + the general path
``assertion_recorded``), exactly like confidence and the learned half-life: nothing
is stored, there is no ``source_trust_updated`` event.

A source earns trust by *agreeing* with other sources where their claims overlap.
With no overlap it is simply unproven and held at a seed -- so adding a brand-new
source never silently overrules one that has actually earned agreement.

Efficiency: the stream is read from the ledger *once* per call and all trust /
consensus is computed in memory (grouped by claim). The live Pi proved this matters --
a per-source/per-claim re-query took seconds on a 20k-event ledger.
"""
from __future__ import annotations

from collections import defaultdict

# A new/unproven source starts here. Structural seed, not an epistemic threshold:
# a source we have no agreement record for is held at arm's length. As it builds a
# track record against other sources, the learned agreement rate (below) replaces
# this. Capped under 1.0 so the unproven never outrank the earned.
SOURCE_TRUST_SEED = 0.5


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def assertions(conn, claim_key: str | None = None) -> list[dict]:
    """The assertion stream: every (claim_key, value, source) the ledger holds.

    Unifies the sensor path (``evidence_recorded``, source carried from the
    observation; older events without one read as ``sensor``) and the general path
    (``assertion_recorded``, explicit source). The one DB read; callers group it in
    memory. Read-only, ordered by event id.
    """
    rows = conn.execute(
        """
        SELECT id,
               json_extract(payload, '$.metric_key')   AS claim_key,
               json_extract(payload, '$.metric_value')  AS value,
               COALESCE(json_extract(payload, '$.source'), 'sensor') AS source,
               created_at
        FROM event_log
        WHERE event_type = 'evidence_recorded'
        UNION ALL
        SELECT id,
               json_extract(payload, '$.claim_key')    AS claim_key,
               json_extract(payload, '$.claim_value')   AS value,
               json_extract(payload, '$.source')        AS source,
               created_at
        FROM event_log
        WHERE event_type = 'assertion_recorded'
        ORDER BY id
        """
    ).fetchall()
    out = [dict(row) for row in rows]
    if claim_key is not None:
        out = [row for row in out if row["claim_key"] == claim_key]
    return out


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


def _consensus(by_claim: dict[str, list[dict]], claim_key: str) -> dict:
    rows = by_claim.get(claim_key, [])
    latest = _latest_by_source(rows)
    candidates = {
        src: {"value": row["value"], "trust": _trust(by_claim, src), "event_id": row["id"]}
        for src, row in latest.items()
    }
    if not candidates:
        return {
            "claim_key": claim_key,
            "value": None,
            "chosen_source": None,
            "candidates": {},
            "contradiction": False,
        }
    chosen = max(
        candidates,
        key=lambda src: (candidates[src]["trust"], candidates[src]["event_id"]),
    )
    tolerance = _tolerance([v for v in (_to_float(r["value"]) for r in rows) if v is not None])
    numeric = [v for v in (_to_float(c["value"]) for c in candidates.values()) if v is not None]
    contradiction = any(not _agree(a, b, tolerance) for a in numeric for b in numeric)
    return {
        "claim_key": claim_key,
        "value": candidates[chosen]["value"],
        "chosen_source": chosen,
        "candidates": candidates,
        "contradiction": contradiction,
    }


def sources(conn) -> list[str]:
    return sorted({row["source"] for row in assertions(conn) if row["source"]})


def source_trust(conn, source: str) -> float:
    """Read-time trust for ``source``: how often it agrees with other sources.

    Assessed only on claims where at least one *other* source asserted too; with no
    such overlap the source is unproven and held at :data:`SOURCE_TRUST_SEED`. The
    agreement band is self-calibrated per claim (:func:`_tolerance`).
    """
    return _trust(_group_by_claim(assertions(conn)), source)


def consensus(conn, claim_key: str) -> dict:
    """Read-time consensus over a claim's candidate assertions (one per source).

    The morphological cell: candidates (the latest value per source) selected by a
    *pluggable criterion* -- today source trust (highest-trust source's value; ties
    broken by the most recent assertion). Reports whether the sources agree or
    contradict, with each source's value and trust. Read-only, nothing stored; the
    same shape later carries an evaluation criterion (e.g. a chess move score).
    """
    return _consensus(_group_by_claim(assertions(conn)), claim_key)


def report(conn) -> dict:
    """A read-time summary for the CLI -- each source's trust and the consensus for
    every claim more than one source speaks to. One ledger read, grouped once."""
    by_claim = _group_by_claim(assertions(conn))
    source_names = sorted(
        {row["source"] for rows in by_claim.values() for row in rows if row["source"]}
    )
    contested = [
        _consensus(by_claim, claim_key)
        for claim_key, rows in by_claim.items()
        if len({row["source"] for row in rows if row["source"]}) > 1
    ]
    return {
        "sources": [{"source": src, "trust": _trust(by_claim, src)} for src in source_names],
        "consensus": contested,
    }
