import numpy as np

from stage2_robotwin.stage2b.baselines.distance_router import distance_weights
from stage2_robotwin.stage2b.baselines.force_router import force_weights
from stage2_robotwin.stage2b.baselines.phase_blend import phase_weights
from stage2_robotwin.stage2b.operator.effect_conserving_transfer_1d import (
    OneDimensionalEffectConservingTransfer,
)
from stage2_robotwin.stage2b.operator.joint_support_mode import responsibility_weights
from stage2_robotwin.stage2b.operator.release_guard import ResponsibilityReleaseGuard


def test_transfer_conserves_local_effect_and_moves_toward_responsibility():
    solver = OneDimensionalEffectConservingTransfer(
        ridge_lambda=0.01, trust_region_m=0.02, action_bound_m=0.05
    )
    result = solver.solve(
        base_action=[0.01, 0.01],
        local_gain=[1.0, 1.0],
        responsibility=[0.8, 0.2],
    )
    assert result.feasible
    assert abs(result.effect_error) <= 1e-9
    assert result.action_left > result.action_right
    assert np.isclose(result.action_left + result.action_right, 0.02)


def test_transfer_fails_to_exact_base_when_gain_is_degenerate():
    result = OneDimensionalEffectConservingTransfer().solve(
        base_action=[0.001, -0.001],
        local_gain=[0.0, 0.0],
        responsibility=[1.0, 0.0],
    )
    assert not result.feasible
    assert result.action_left == 0.001
    assert result.action_right == -0.001
    assert "BASE_FALLBACK" in result.solver_status


def test_three_way_joint_mode_does_not_split_interaction():
    weights, audit = responsibility_weights(0.8, 0.2, 0.4, 0.2, three_way=True)
    np.testing.assert_allclose(weights, [0.5, 0.5])
    assert audit["mode"] == "JOINT_SUPPORT"
    assert audit["bypass_transfer"]


def test_two_way_mode_ignores_joint_only_for_ablation():
    weights, audit = responsibility_weights(0.8, 0.2, 0.9, 0.2, three_way=False)
    np.testing.assert_allclose(weights, [0.8, 0.2])
    assert not audit["bypass_transfer"]


def test_release_guard_requires_all_independent_checks():
    guard = ResponsibilityReleaseGuard(receiver_contact_stable_steps=2)
    guard.update_contact(True)
    blocked = guard.allow(1.0, 1.0, 0.0, False)
    assert not blocked["allow"]
    guard.update_contact(True)
    allowed = guard.allow(1.0, 1.0, 0.0, False)
    assert allowed["allow"]
    assert not guard.allow(1.0, 1.0, 0.1, False)["allow"]


def test_profile_blind_baselines_are_normalized():
    for weights in (
        phase_weights(5, 0, 10),
        distance_weights(0.1, 0.2),
        force_weights(2.0, 1.0),
        force_weights(0.0, 0.0),
    ):
        assert np.isclose(weights.sum(), 1.0)
        assert np.all(weights >= 0.0)

