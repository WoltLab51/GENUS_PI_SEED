from __future__ import annotations

import math
from datetime import datetime, timezone


# TODO: aus Ledger-Daten kalibrieren, nicht final.
HALFLIFE_SECONDS_BY_CLAIM_KEY = {
    "system.activity": 1800.0,
    "system.network": 1800.0,
    "system.disk": 86400.0,
    # Clock sync is an inert property: it flips rarely and then for a while, so
    # it belongs in the slow (disk) class, not the 30-minute network class.
    "system.clock": 86400.0,
}
FALLBACK_HALFLIFE_SECONDS = 1800.0


def calculate_confidence(
    supporting_evidence_times: list[datetime | str],
    contradicting_evidence_times: list[datetime | str] | None = None,
    claim_key: str | None = None,
    now: datetime | None = None,
    halflife_seconds: float | None = None,
) -> float:
    if not supporting_evidence_times:
        return 0.0

    contradicting_evidence_times = contradicting_evidence_times or []
    effective_now = _normalize_time(now or datetime.now(timezone.utc))
    halflife = halflife_seconds or halflife_for_claim(claim_key)
    supporting_weight = _effective_weight(
        supporting_evidence_times,
        now=effective_now,
        halflife_seconds=halflife,
    )
    contradicting_weight = _effective_weight(
        contradicting_evidence_times,
        now=effective_now,
        halflife_seconds=halflife,
    )
    return round(
        supporting_weight / (supporting_weight + contradicting_weight + 1.0),
        3,
    )


def halflife_for_claim(claim_key: str | None) -> float:
    if claim_key is None:
        return FALLBACK_HALFLIFE_SECONDS
    return HALFLIFE_SECONDS_BY_CLAIM_KEY.get(claim_key, FALLBACK_HALFLIFE_SECONDS)


def _effective_weight(
    evidence_times: list[datetime | str],
    now: datetime,
    halflife_seconds: float,
) -> float:
    if halflife_seconds <= 0:
        raise ValueError("halflife_seconds must be positive")
    return sum(
        math.pow(2.0, -_age_seconds(evidence_time, now) / halflife_seconds)
        for evidence_time in evidence_times
    )


def _age_seconds(evidence_time: datetime | str, now: datetime) -> float:
    observed_at = _normalize_time(evidence_time)
    return max(0.0, (now - observed_at).total_seconds())


def _normalize_time(value: datetime | str) -> datetime:
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        parsed = value
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
