import numpy as np

from stage2_robotwin.stage2c.operator.effect_nullspace_transfer_1d import (
    EffectNullspaceTransfer1D,
)
from stage2_robotwin.stage2c.operator.effect_nullspace_transfer_4d import (
    EffectNullspaceTransfer4D,
)
from stage2_robotwin.stage2c.responsibility.signed_joint_state import (
    classify_signed_responsibility,
)
from stage2_robotwin.stage2c.responsibility.temporal_filter import (
    StatefulResponsibilityFilter,
)


def test_1d_transfer_is_effect_conserving_and_moves_contribution():
    solver = EffectNullspaceTransfer1D(
        eta=1.0, relative_trust_region=1.0, action_bound_m=1.0
    )
    result = solver.solve([0.010, 0.010], [0.8, 1.2], [0.75, 0.25])
    assert result.feasible
    assert abs(result.effect_error) < 1e-12
    assert result.routed_contribution[0] > result.base_contribution[0]
    assert result.routed_contribution[1] < result.base_contribution[1]
    assert result.nullspace_residual < 1e-12


def test_1d_transfer_fails_closed_on_contact_or_degenerate_gain():
    solver = EffectNullspaceTransfer1D()
    contact = solver.solve([0.01, 0.01], [1.0, 1.0], [0.8, 0.2], contact_ok=False)
    degenerate = solver.solve([0.01, 0.01], [1.0, 0.0], [0.8, 0.2])
    assert not contact.feasible and contact.action_correction_ratio == 0.0
    assert not degenerate.feasible and degenerate.action_correction_ratio == 0.0


def test_4d_transfer_preserves_all_four_total_effect_channels():
    matrix = np.concatenate([np.eye(4), np.eye(4)], axis=1)
    base = np.asarray([[0.4, 0.2, 0.3, 0.1], [0.6, 0.8, 0.7, 0.9]])
    target_left = np.asarray([0.7, 0.6, 0.5, 0.4])
    result = EffectNullspaceTransfer4D(
        eta=1.0, relative_trust_region=1.0
    ).solve(base, matrix, target_left)
    assert result.feasible
    assert np.allclose(result.base_total_effect, result.routed_total_effect)
    assert result.nullspace_dimension == 4


def test_signed_modes_preserve_harmful_and_joint_information():
    conflict = classify_signed_responsibility(-0.2, 0.8, 0.1)
    joint = classify_signed_responsibility(0.55, 0.45, 0.35)
    left = classify_signed_responsibility(0.8, 0.2, 0.0)
    assert conflict.mode == "CONFLICT"
    assert conflict.harmful_left == -0.2
    assert np.allclose(conflict.target_share, [0.0, 1.0])
    assert joint.mode == "JOINT_SUPPORT"
    assert 0.5 < joint.target_share_left < 1.0
    assert left.mode == "LEFT_DOMINANT"


def test_stateful_filter_is_projected_and_rate_limited():
    filt = StatefulResponsibilityFilter(beta=1.0, max_share_change=0.1)
    first = filt.update([1.0, 0.0])
    second = filt.update([1.0, 0.0])
    assert np.allclose(first, [0.6, 0.4])
    assert np.allclose(second, [0.7, 0.3])
    assert np.isclose(first.sum(), 1.0)
