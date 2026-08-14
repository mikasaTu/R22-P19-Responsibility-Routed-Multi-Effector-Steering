from stage2_robotwin.stage2d.capacity.capacity_analysis import _auc, _calibration


def test_auc_and_calibration():
    assert _auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == 1.0
    assert _auc([1, 1], [0.2, 0.8]) is None
    assert _calibration([0, 1], [0, 1])["brier"] == 0.0

