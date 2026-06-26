from genus import confidence, constants, rules


def test_preset_budget_thresholds_are_centralized():
    # the fixed high/normal thresholds (the preset budget) live in constants and
    # are re-exported by rules, so existing call sites keep working unchanged.
    assert constants.DISK_HIGH_THRESHOLD == 85.0
    assert rules.DISK_HIGH_THRESHOLD == constants.DISK_HIGH_THRESHOLD
    assert rules.CPU_HIGH_THRESHOLD == constants.CPU_HIGH_THRESHOLD
    assert rules.TEMP_LOW_THRESHOLD == constants.TEMP_LOW_THRESHOLD


def test_seed_halflives_are_centralized():
    assert (
        confidence.HALFLIFE_SECONDS_BY_CLAIM_KEY
        is constants.HALFLIFE_SECONDS_BY_CLAIM_KEY
    )
    assert confidence.FALLBACK_HALFLIFE_SECONDS == constants.FALLBACK_HALFLIFE_SECONDS
