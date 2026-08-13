import numpy as np

from stage2_robotwin.responsibility.oracle import (
    decompose_outcomes,
    quaternion_delta_rotvec,
    shapley_effects,
)
from stage2_robotwin.responsibility.joint_synergy import joint_synergy


def test_shapley_reconstructs_total_effect_with_interaction():
    result = shapley_effects({"LR": 7.0, "L": 2.0, "R": 3.0, "ZERO": 0.0})
    assert result["phi_left"] == 3.0
    assert result["phi_right"] == 4.0
    assert result["synergy"] == 2.0
    assert result["reconstruction_error"] == 0.0
    assert joint_synergy({"LR": 7.0, "L": 2.0, "R": 3.0, "ZERO": 0.0}) == 2.0


def test_quaternion_delta_uses_short_rotation():
    half = np.pi / 4
    value = quaternion_delta_rotvec([1, 0, 0, 0], [np.cos(half), 0, 0, np.sin(half)])
    np.testing.assert_allclose(value, [0, 0, np.pi / 2], atol=1e-12)


def test_decomposition_keeps_joint_channel_separate():
    template = {
        "translation": [0.0, 0.0, 0.0],
        "rotation_vector": [0.0, 0.0, 0.0],
        "support_delta": 0.0,
        "task_progress": 0.0,
        "contact_retention": [1.0, 1.0],
        "slip": [0.0, 0.0],
    }
    outcomes = {name: dict(template) for name in ("LR", "L", "R", "ZERO")}
    outcomes["LR"] = {**template, "translation": [1.0, 0.0, 0.0]}
    result = decompose_outcomes(outcomes)
    assert result["three_channel"]["rho_left"] == 0.0
    assert result["three_channel"]["rho_right"] == 0.0
    assert result["three_channel"]["rho_joint"] == 1.0
    assert result["three_channel"]["reconstruction_error"] == 0.0
