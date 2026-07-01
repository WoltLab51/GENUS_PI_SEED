"""Shared primitives for self-calibration (see [[self-calibration-no-presets]]): every
rule-domain that derives a threshold from the natural gap in a population of its own
counts/rates, instead of a typed-in constant, reuses one of the two shapes below.

Named ``self_calibration`` (not ``calibration``) to stay distinct from ``query.calibration``
-- the Bayesian judgment-calibration report (are GENUS's stability judgments borne out?),
a different, already-established concept in this codebase.
"""
from __future__ import annotations


def widest_gap_count_threshold(counts, seed: int) -> int:
    """A count threshold derived from the natural gap in a population of positive counts: the
    widest gap between distinct values separates an incidental (low) group from a systematic
    (high) one, and the threshold sits just above the low group. Falls back to ``seed`` when
    there are fewer than two distinct positive values to show a gap. Shared by every rule-domain
    that calibrates a COUNT this way (transitivity vindications, recovery-episode lengths, ...)."""
    values = sorted({c for c in counts if c > 0})
    if len(values) < 2:
        return seed
    _, low = max((values[i + 1] - values[i], values[i]) for i in range(len(values) - 1))
    return low + 1


def widest_gap_rate_cut(rates, seed: float) -> float:
    """A rate cut derived from the natural gap in a population of positive rates: the midpoint of
    the widest gap separates incidental mirroring/agreement from systematic. Falls back to
    ``seed`` when there are fewer than two distinct positive values to show a gap. Shared by
    rule-domains whose population is deduplicated positive rates (symmetry today; gender-suffix
    reliability keeps its own variant -- it deliberately does not dedupe or drop zero rates, a
    real semantic difference, not an oversight)."""
    values = sorted({r for r in rates if r > 0})
    if len(values) < 2:
        return seed
    _, lo, hi = max((values[i + 1] - values[i], values[i], values[i + 1]) for i in range(len(values) - 1))
    return round((lo + hi) / 2, 4)
