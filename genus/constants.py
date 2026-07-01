"""Operating references and the preset budget.

GENUS's goal is no *arbitrary* presets: contextual magnitudes (what counts as
heavy churn, an anomalous temperature CORRELATION) are self-calibrated from the
core's own lived distribution. But not every fixed number is an arbitrary preset
-- the criterion is not "do we have enough data yet", it's whether the quantity's
meaning is RELATIVE to this system's own history (a comparison, fit for self-
calibration) or ABSOLUTE (the same meaning on any machine, regardless of this
one's personal history -- self-calibrating those manufactures false alarms on a
quiet system rather than removing an arbitrary guess). This file keeps the
absolute references fixed; the genuine preset budget (comparative judgments,
not yet calibrated) should keep shrinking as material allows.
"""

from __future__ import annotations


# --- Absolute physical references (correctly fixed, NOT presets) --------------
# Free disk space, the thermal ceiling, and CPU/memory load are absolute facts:
# a disk chronically at 85% is still near-full, ~75-85 C is warm for a Pi, and 80%
# CPU means the same thing regardless of THIS machine's history. Self-calibrating
# any of these to the system's own distribution would erase a real warning (or,
# verified live 2026-07-02: on a mostly-idle Pi -- median CPU 0%, p99 30%, max ever
# seen 59% over ~5000 readings -- it would set "high" at ~3-30%, flagging completely
# normal activity). So they stay fixed, unlike churn/thermal-correlation, whose
# "heavy"/"anomalous" is inherently a comparison to this system's OWN personality.
DISK_HIGH_THRESHOLD = 85.0
DISK_LOW_THRESHOLD = 60.0
TEMP_HIGH_THRESHOLD = 75.0
TEMP_LOW_THRESHOLD = 55.0
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
