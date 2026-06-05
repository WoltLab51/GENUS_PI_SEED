import math


def calculate_confidence(
    supporting_count: int,
    contradicting_count: int,
    latest_evidence_age_seconds: float,
    decay_halflife_seconds: float = 300.0,
) -> float:
    if supporting_count == 0:
        return 0.0
    ratio = supporting_count / (supporting_count + contradicting_count + 1)
    decay = math.exp(-0.693147 * latest_evidence_age_seconds / decay_halflife_seconds)
    return round(ratio * decay, 3)
