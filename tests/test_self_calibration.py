from genus import self_calibration


def test_widest_gap_count_threshold_derives_above_the_low_group():
    # low group {1,2}, high group {8} -> widest gap is 8-2=6, threshold = 2+1
    assert self_calibration.widest_gap_count_threshold([1, 1, 2, 8], seed=99) == 3


def test_widest_gap_count_threshold_falls_back_to_seed_when_too_thin():
    assert self_calibration.widest_gap_count_threshold([5, 5, 5], seed=3) == 3
    assert self_calibration.widest_gap_count_threshold([], seed=3) == 3
    assert self_calibration.widest_gap_count_threshold([0, 0], seed=3) == 3   # zeros don't count


def test_widest_gap_rate_cut_derives_the_midpoint_of_the_widest_gap():
    # low group {0.1, 0.12}, high group {0.9} -> cut = midpoint(0.12, 0.9)
    assert self_calibration.widest_gap_rate_cut([0.1, 0.12, 0.9], seed=0.5) == 0.51


def test_widest_gap_rate_cut_falls_back_to_seed_when_too_thin():
    assert self_calibration.widest_gap_rate_cut([0.5, 0.5], seed=0.2) == 0.2
    assert self_calibration.widest_gap_rate_cut([], seed=0.2) == 0.2
    assert self_calibration.widest_gap_rate_cut([0.0, 0.0], seed=0.2) == 0.2   # zeros don't count
