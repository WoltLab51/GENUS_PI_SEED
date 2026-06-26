"""The preset budget — every hardcoded value that GENUS has *not yet* learned.

GENUS's goal is no presets: each magnitude should be self-calibrated from the
core's own lived distribution (as churn, trend, and thermal already are, and as
the confidence half-life now is). This file is the honest, single home for what
is *still* imposed. It should shrink toward empty: when a value here becomes
self-calibrated, it leaves the file. The scaffold elsewhere stays pure structure.
"""

from __future__ import annotations


# --- Preset budget: fixed high/normal thresholds -----------------------------
# The last epistemic magnitudes still imposed rather than learned. Each should be
# self-calibrated against this core's own percentile distribution, exactly like
# repo.churn and system.thermal already are. Until then, they live here.
CPU_HIGH_THRESHOLD = 80.0
CPU_LOW_THRESHOLD = 60.0
MEMORY_HIGH_THRESHOLD = 85.0
MEMORY_LOW_THRESHOLD = 70.0
DISK_HIGH_THRESHOLD = 85.0
DISK_LOW_THRESHOLD = 60.0
TEMP_HIGH_THRESHOLD = 75.0
TEMP_LOW_THRESHOLD = 55.0


# --- Seed half-lives: fallback only ------------------------------------------
# Superseded by projection.learned_halflife (v1.11), which derives each belief's
# decay timescale from its own flip history. These seeds apply only until a belief
# has enough tenure to learn its own.
HALFLIFE_SECONDS_BY_CLAIM_KEY = {
    "system.activity": 1800.0,
    "system.network": 1800.0,
    "system.disk": 86400.0,
    "system.clock": 86400.0,
    "repo.activity": 86400.0,
    "repo.churn": 86400.0,
    "disk.trend": 86400.0,
    "weather.trend": 86400.0,
}
FALLBACK_HALFLIFE_SECONDS = 1800.0
