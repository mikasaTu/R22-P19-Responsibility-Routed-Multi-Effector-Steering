import numpy as np

from r22p19_libero.env import LiberoBranchEnv
from r22p19_libero.responsibility import rank_auc, shapley_responsibility


def _branch(translation):
    return {
        "outcome": {
            "translation": list(translation),
            "rotation_angle_rad": 0.0,
            "linear_velocity": [0.0, 0.0, 0.0],
            "angular_velocity": [0.0, 0.0, 0.0],
            "height_change": float(translation[2]),
            "target_progress": float(translation[0]),
            "drop": False,
            "success": False,
        }
    }


def test_shapley_conservation_and_signs():
    result = shapley_responsibility(
        {
            "AB": _branch([3.0, 2.0, 0.0]),
            "A": _branch([2.0, 0.0, 0.0]),
            "B": _branch([0.0, 1.0, 0.0]),
            "ZERO": _branch([0.0, 0.0, 0.0]),
        }
    )
    assert result["relative_conservation_error"] < 1e-12
    assert result["signed_progress_a"] > result["signed_progress_b"]
    np.testing.assert_allclose(
        np.asarray(result["phi_a"]) + np.asarray(result["phi_b"]),
        np.asarray(result["total_effect"]),
    )


def test_masked_action_keeps_registered_groups_only():
    action = np.asarray([0.2, -0.3, 0.4, 0.1, -0.2, 0.5, 1.0])
    arm = LiberoBranchEnv._masked_action(action, "A", range(6), [6], (1.0, 1.0), False)
    gripper = LiberoBranchEnv._masked_action(action, "B", range(6), [6], (1.0, 1.0), False)
    zero = LiberoBranchEnv._masked_action(action, "ZERO", range(6), [6], (1.0, 1.0), False)
    np.testing.assert_allclose(arm[:6], action[:6])
    assert arm[6] == 0.0
    np.testing.assert_allclose(gripper[:6], 0.0)
    assert gripper[6] == 1.0
    np.testing.assert_allclose(zero, 0.0)


def test_rank_auc_ties_and_order():
    assert rank_auc([0, 0, 1, 1], [0.0, 0.2, 0.8, 1.0]) == 1.0
    assert rank_auc([0, 1], [0.5, 0.5]) == 0.5
