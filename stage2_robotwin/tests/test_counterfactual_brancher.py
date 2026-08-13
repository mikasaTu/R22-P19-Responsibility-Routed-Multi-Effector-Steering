import sys
from types import SimpleNamespace

import numpy as np
import pytest

from stage2_robotwin.wrappers.counterfactual_brancher import (
    SapienSnapshot,
    hold_neutral_action,
)


def test_neutral_branches_hold_grippers_and_mask_only_arm_targets():
    action = np.arange(14, dtype=np.float64)
    left = hold_neutral_action(action, "L")
    right = hold_neutral_action(action, "R")
    zero = hold_neutral_action(action, "ZERO")
    np.testing.assert_array_equal(left[:7], action[:7])
    assert np.isnan(left[7:13]).all()
    np.testing.assert_array_equal(right[7:], action[7:])
    assert np.isnan(right[:6]).all()
    assert np.isnan(zero[:6]).all() and np.isnan(zero[7:13]).all()
    assert zero[6] == action[6] and zero[13] == action[13]


def test_action_contract_is_14d():
    with pytest.raises(ValueError):
        hold_neutral_action(np.zeros(13), "LR")


def test_snapshot_restore_does_not_unpack_articulation_link_poses(monkeypatch):
    class Scene:
        restored = None

        def unpack_poses(self, value):
            raise AssertionError("opaque entity poses must not be unpacked")

        def get_all_articulations(self):
            return []

        def get_all_actors(self):
            return []

    robot = SimpleNamespace(left_gripper_val=None, right_gripper_val=None)
    task = SimpleNamespace(scene=Scene(), robot=robot)
    monkeypatch.setitem(sys.modules, "sapien", SimpleNamespace())
    SapienSnapshot.restore(
        task,
        {
            "poses": b"opaque-scene-state",
            "articulations": [],
            "dynamics": [],
            "left_gripper_val": 0.25,
            "right_gripper_val": 0.75,
        },
    )
    assert task.scene.restored is None
    assert robot.left_gripper_val == 0.25
    assert robot.right_gripper_val == 0.75
