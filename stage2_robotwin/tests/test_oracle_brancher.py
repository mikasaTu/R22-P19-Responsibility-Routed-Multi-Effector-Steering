from types import SimpleNamespace

import numpy as np

from stage2_robotwin.responsibility.oracle_brancher import (
    OracleBranchAuditor,
    _direction_joint_delta,
    _joint_neutral_state,
    _scheduled_arm,
)


def test_scheduled_arm_applies_delay_and_gain_around_hold_target():
    result = {
        "position": np.asarray([[2.0], [3.0], [4.0]]),
        "velocity": np.asarray([[0.5], [0.6], [0.7]]),
    }
    hold_position = np.asarray([1.0])
    hold_velocity = np.asarray([0.0])
    delayed = _scheduled_arm(
        result, 0, 0, delay=1, gain=1.3,
        hold_position=hold_position, hold_velocity=hold_velocity,
    )
    np.testing.assert_allclose(delayed[0], hold_position)
    np.testing.assert_allclose(delayed[1], hold_velocity)
    active = _scheduled_arm(
        result, 0, 1, delay=1, gain=1.3,
        hold_position=hold_position, hold_velocity=hold_velocity,
    )
    np.testing.assert_allclose(active[0], [2.3])
    np.testing.assert_allclose(active[1], [0.65])


def test_neutral_state_uses_measured_qpos_not_old_drive_target():
    robot = SimpleNamespace(
        get_left_arm_real_jointState=lambda: [0.1, 0.2, 0.3, 0.4],
        get_right_arm_real_jointState=lambda: [0.5, 0.6, 0.7, 0.8],
    )
    task = SimpleNamespace(robot=robot)
    left_position, left_velocity = _joint_neutral_state(task, "left")
    right_position, right_velocity = _joint_neutral_state(task, "right")
    np.testing.assert_allclose(left_position, [0.1, 0.2, 0.3])
    np.testing.assert_allclose(right_position, [0.5, 0.6, 0.7])
    np.testing.assert_array_equal(left_velocity, np.zeros(3))
    np.testing.assert_array_equal(right_velocity, np.zeros(3))


def test_direction_joint_delta_tracks_translation_and_zero_rotation():
    jacobian = np.eye(6)
    delta, audit = _direction_joint_delta(
        jacobian,
        direction=[1.0, 0.0, 0.0],
        amplitude_m=0.004,
        max_joint_delta_rad=0.05,
    )
    np.testing.assert_allclose(delta, [0.004, 0, 0, 0, 0, 0], atol=1e-12)
    assert audit["predicted_translation_m"] == 0.004
    assert audit["predicted_direction_cosine"] == 1.0


def test_unknown_profile_mode_fails_closed():
    import pytest

    with pytest.raises(ValueError, match="unknown authority profile mode"):
        OracleBranchAuditor(profile_mode="typo")
