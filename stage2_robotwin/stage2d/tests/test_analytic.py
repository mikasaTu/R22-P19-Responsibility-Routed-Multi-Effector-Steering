import numpy as np

from stage2_robotwin.stage2d.analytic.baselines import run_baseline
from stage2_robotwin.stage2d.analytic.system import make_case, receiver_share


def test_desired_is_independent_of_current():
    cases = [make_case(i) for i in range(32)]
    assert all(abs(c.desired_receiver - c.current_receiver) >= 0.19 for c in cases)


def test_correct_and_swapped_move_oppositely():
    for seed in range(12):
        case = make_case(seed)
        correct, _ = run_baseline(case, "A4")
        swapped, _ = run_baseline(case, "A5")
        c_move = receiver_share(case, correct.action) - case.current_receiver
        s_move = receiver_share(case, swapped.action) - case.current_receiver
        assert np.sign(c_move) == np.sign(case.desired_receiver - case.current_receiver)
        assert np.sign(s_move) == -np.sign(case.desired_receiver - case.current_receiver)


def test_v1_self_target_is_near_identity():
    for seed in range(12):
        case = make_case(seed)
        result, _ = run_baseline(case, "A3")
        assert abs(receiver_share(case, result.action) - case.current_receiver) < 0.02

