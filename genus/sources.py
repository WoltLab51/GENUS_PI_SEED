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
"""
from __future__ import annotations

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
    (``assertion_recorded``, explicit source). Read-only, ordered by event id.
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


def sources(conn) -> list[str]:
    return sorted({row["source"] for row in assertions(conn) if row["source"]})


def latest_by_source(conn, claim_key: str) -> dict[str, dict]:
    """The most recent assertion for ``claim_key`` from each source (the candidates)."""
    latest: dict[str, dict] = {}
    for row in assertions(conn, claim_key):
        if row["source"]:
            latest[row["source"]] = row  # later id wins -> latest per source
    return latest


def _claim_tolerance(conn, claim_key: str) -> float | None:
    """Self-calibrated agree/disagree band: the claim's own spread (1 std).

    Not a constant -- a value within one standard deviation of the claim's lived
    variation counts as agreement. ``None`` when there is too little history to
    learn a band (caller then requires exact agreement). The Pi sharpens this.
    """
    values = [_to_float(row["value"]) for row in assertions(conn, claim_key)]
    values = [v for v in values if v is not None]
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return variance ** 0.5


def _agree(a: float, b: float, tolerance: float | None) -> bool:
    if tolerance is None:
        return a == b
    return abs(a - b) <= tolerance


def source_trust(conn, source: str) -> float:
    """Read-time trust for ``source``: how often it agrees with other sources.

    Assessed only on claims where at least one *other* source asserted too; with no
    such overlap the source is unproven and held at :data:`SOURCE_TRUST_SEED`. The
    agreement band is self-calibrated per claim (:func:`_claim_tolerance`).
    """
    claim_keys = {row["claim_key"] for row in assertions(conn) if row["source"] == source}
    agreements: list[float] = []
    for claim_key in claim_keys:
        latest = latest_by_source(conn, claim_key)
        mine = _to_float(latest.get(source, {}).get("value"))
        if mine is None:
            continue
        tolerance = _claim_tolerance(conn, claim_key)
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


def report(conn) -> dict:
    """A read-time summary for the CLI: each source's trust, and the consensus for
    every claim more than one source speaks to."""
    claim_keys = sorted({row["claim_key"] for row in assertions(conn) if row["claim_key"]})
    contested = [
        consensus(conn, claim_key)
        for claim_key in claim_keys
        if len(latest_by_source(conn, claim_key)) > 1
    ]
    return {
        "sources": [{"source": src, "trust": source_trust(conn, src)} for src in sources(conn)],
        "consensus": contested,
    }


def consensus(conn, claim_key: str) -> dict:
    """Read-time consensus over a claim's candidate assertions (one per source).

    The morphological cell: candidates (the latest value per source) selected by a
    *pluggable criterion* -- today source trust (highest-trust source's value; ties
    broken by the most recent assertion). Reports whether the sources agree or
    contradict, with each source's value and trust. Read-only, nothing stored; the
    same shape later carries an evaluation criterion (e.g. a chess move score).
    """
    latest = latest_by_source(conn, claim_key)
    candidates = {
        src: {
            "value": row["value"],
            "trust": source_trust(conn, src),
            "event_id": row["id"],
        }
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
    tolerance = _claim_tolerance(conn, claim_key)
    numeric = [_to_float(c["value"]) for c in candidates.values()]
    numeric = [v for v in numeric if v is not None]
    contradiction = any(not _agree(a, b, tolerance) for a in numeric for b in numeric)
    return {
        "claim_key": claim_key,
        "value": candidates[chosen]["value"],
        "chosen_source": chosen,
        "candidates": candidates,
        "contradiction": contradiction,
    }
