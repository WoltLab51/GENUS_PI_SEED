"""Operating references and the preset budget.

GENUS's goal is no *arbitrary* presets: contextual magnitudes (what counts as
heavy churn, an anomalous temperature) are self-calibrated from the core's own
lived distribution. But not every fixed number is an arbitrary preset — some are
absolute physical references that are correctly fixed. This file separates the two
honestly: the genuine preset budget (relative load thresholds) should shrink as it
is self-calibrated; the absolute references are not presets and stay.
"""

from __future__ import annotations


# --- Absolute physical references (correctly fixed, NOT presets) --------------
# Free disk space and the thermal ceiling are absolute facts: a disk chronically
# at 85% is still near-full, and ~75-85 C is warm for a Pi regardless of history.
# Self-calibrating these would erase a real warning, so they stay fixed.
DISK_HIGH_THRESHOLD = 85.0
DISK_LOW_THRESHOLD = 60.0
TEMP_HIGH_THRESHOLD = 75.0
TEMP_LOW_THRESHOLD = 55.0

# --- Relative load thresholds (the genuine preset budget) --------------------
# "High load" depends on what the machine is for, so these could be self-calibrated
# per machine, like churn/thermal. Kept fixed for now because on an idle Pi the
# distribution is degenerate and self-calibration would simply withhold.
CPU_HIGH_THRESHOLD = 80.0
CPU_LOW_THRESHOLD = 60.0
MEMORY_HIGH_THRESHOLD = 85.0
MEMORY_LOW_THRESHOLD = 70.0


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
