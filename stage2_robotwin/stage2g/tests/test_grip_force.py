import numpy as np
import pytest

from stage2_robotwin.stage2g.intervention import grip_force


class FakeJoint:
    def __init__(self, target, velocity, stiffness=100.0, damping=10.0, force_limit=50.0):
        self.target = np.asarray([target], dtype=np.float64)
        self.velocity = np.asarray([velocity], dtype=np.float64)
        self.values = [float(stiffness), float(damping), float(force_limit), "force"]
        self.calls = []

    def get_drive_target(self):
        return self.target.copy()

    def get_drive_velocity_target(self):
        return self.velocity.copy()

    def set_drive_target(self, value):
        self.target = np.asarray(value, dtype=np.float64).reshape(-1).copy()
        self.calls.append(("target", self.target.copy()))

    def set_drive_velocity_target(self, value):
        self.velocity = np.asarray(value, dtype=np.float64).reshape(-1).copy()
        self.calls.append(("velocity", self.velocity.copy()))

    def get_stiffness(self):
        return self.values[0]

    def get_damping(self):
        return self.values[1]

    def get_force_limit(self):
        return self.values[2]

    def get_drive_mode(self):
        return self.values[3]


class FakeRobot:
    def __init__(self):
        self.left_arm_joints = [FakeJoint(0.1 + i, 0.0, 100 + i, 10 + i, 3.4028234663852886e38)
                                for i in range(2)]
        self.right_arm_joints = [FakeJoint(0.2 + i, 0.0, 200 + i, 20 + i, 3.4028234663852886e38)
                                 for i in range(2)]
        self.left_gripper_joints = [FakeJoint(0.02, 0.01), FakeJoint(0.02, 0.01)]
        self.right_gripper_joints = [FakeJoint(0.03, 0.01), FakeJoint(0.03, 0.01)]
        self.left_gripper = [(joint, 1.0, 0.0) for joint in self.left_gripper_joints]
        self.right_gripper = [(joint, 1.0, 0.0) for joint in self.right_gripper_joints]
        self.left_gripper_val = 0.25
        self.right_gripper_val = 0.35
        self.calls = []

    def get_left_gripper_val(self):
        return self.left_gripper_val

    def get_right_gripper_val(self):
        return self.right_gripper_val

    def set_gripper(self, value, side, gripper_eps=0.1):
        value = float(np.clip(value, 0.0, 1.0))
        self.calls.append((side, value, float(gripper_eps)))
        setattr(self, f"{side}_gripper_val", value)
        for entry in getattr(self, f"{side}_gripper"):
            joint = entry[0]
            joint.set_drive_target(value * entry[1] + entry[2])
            joint.set_drive_velocity_target(0.0)


class FakeTask:
    def __init__(self):
        self.robot = FakeRobot()


def joint_state(joints):
    return [
        (
            joint.target.copy(),
            joint.velocity.copy(),
            tuple(joint.values),
        )
        for joint in joints
    ]


def assert_joint_state_equal(before, after):
    assert len(before) == len(after)
    for first, second in zip(before, after):
        assert np.array_equal(first[0], second[0])
        assert np.array_equal(first[1], second[1])
        assert first[2] == second[2]


def setter_state(joints):
    return [
        [(kind, value.copy()) for kind, value in joint.calls]
        for joint in joints
    ]


def assert_setter_state_equal(before, after):
    assert len(before) == len(after)
    for first_joint, second_joint in zip(before, after):
        assert len(first_joint) == len(second_joint)
        for (first_kind, first_value), (second_kind, second_value) in zip(first_joint, second_joint):
            assert first_kind == second_kind
            assert np.array_equal(first_value, second_value)


def test_gamma_one_is_byte_noop_for_gripper_and_arm():
    # Compare the K4 context against the same normal episode command without K4.
    # The body command must remain visible after gamma=1 exits.
    baseline = FakeTask()
    baseline.robot.set_gripper(0.7, "left", 0.0)
    expected_gripper = joint_state(baseline.robot.left_gripper_joints)
    expected_bookkeeping = baseline.robot.left_gripper_val
    expected_setter_calls = list(baseline.robot.calls)
    expected_joint_setter_calls = setter_state(baseline.robot.left_gripper_joints)

    task = FakeTask()
    before_arm = joint_state(task.robot.left_arm_joints)
    command = (0.7, 0.0)

    with grip_force.apply(task, "left", 1.0) as handle:
        assert handle.route_gripper("left", command) is command
        receiver = handle.route_gripper("right", (0.7, 0.1))
        assert receiver == (0.7, 0.1)
        # This is the normal episode update. K4 must not intercept or undo it.
        task.robot.set_gripper(command[0], "left", command[1])
        assert handle.receipt()["no_op"] is True
        assert handle.receipt()["restoration_required"] is False

    assert_joint_state_equal(expected_gripper, joint_state(task.robot.left_gripper_joints))
    assert task.robot.left_gripper_val == expected_bookkeeping
    assert task.robot.calls == expected_setter_calls
    assert_setter_state_equal(expected_joint_setter_calls, setter_state(task.robot.left_gripper_joints))
    assert_joint_state_equal(before_arm, joint_state(task.robot.left_arm_joints))
    assert handle.receipt()["restoration_exact"] is True
    assert handle.receipt()["implementation"] == "target_opening_fallback"


def test_target_opening_fallback_routes_only_soft_arm():
    task = FakeTask()
    before_arm = joint_state(task.robot.left_arm_joints)

    with grip_force.apply(task, "left", 0.25) as handle:
        # Entry maps current 0.25 toward the normalized open endpoint.
        assert task.robot.left_gripper_val == pytest.approx(0.8125)
        assert task.robot.calls[-1] == ("left", 0.8125, 0.0)
        routed = handle.route_gripper("left", (0.25, 0.1))
        assert routed == pytest.approx((0.8125, 0.0))
        assert handle.route_gripper("right", (0.25, 0.1)) == (0.25, 0.1)
        assert_joint_state_equal(before_arm, joint_state(task.robot.left_arm_joints))

    assert task.robot.left_gripper_val == pytest.approx(0.25)
    assert task.robot.right_gripper_val == pytest.approx(0.35)
    assert_joint_state_equal(before_arm, joint_state(task.robot.left_arm_joints))
    assert handle.receipt()["force_control_available"] is False
    assert handle.receipt()["arm_properties_unchanged"] is True
    assert handle.receipt()["target_modification_count"] == 1


def test_exception_path_restores_gripper_targets_and_bookkeeping():
    task = FakeTask()
    before_left = joint_state(task.robot.left_gripper_joints)
    before_right = joint_state(task.robot.right_gripper_joints)
    before_arm = joint_state(task.robot.right_arm_joints)

    with pytest.raises(RuntimeError, match="injected"):
        with grip_force.apply(task, "left", 0.2) as handle:
            handle.route_gripper("left", (0.1, 0.1))
            raise RuntimeError("injected")

    assert_joint_state_equal(before_left, joint_state(task.robot.left_gripper_joints))
    assert_joint_state_equal(before_right, joint_state(task.robot.right_gripper_joints))
    assert_joint_state_equal(before_arm, joint_state(task.robot.right_arm_joints))
    assert task.robot.left_gripper_val == pytest.approx(0.25)
    assert task.robot.right_gripper_val == pytest.approx(0.35)
    assert handle.restoration_exact is True
    assert handle.arm_properties_unchanged is True


def test_route_item_does_not_touch_arm_targets():
    task = FakeTask()
    with grip_force.apply(task, "right", 0.5) as handle:
        item = {
            "left_position": np.arange(6, dtype=np.float64),
            "left_velocity": np.zeros(6),
            "left_gripper": (0.2, 0.1),
            "right_position": np.ones(6),
            "right_velocity": np.ones(6),
            "right_gripper": (0.4, 0.1),
        }
        routed = handle.route_item(item)
        assert routed["left_gripper"] == item["left_gripper"]
        assert routed["right_gripper"] == pytest.approx((0.7, 0.0))
        assert np.array_equal(routed["left_position"], item["left_position"])
        assert np.array_equal(routed["right_position"], item["right_position"])


@pytest.mark.parametrize("gamma", [-0.1, 1.1, float("nan")])
def test_gamma_validation_is_fail_closed(gamma):
    with pytest.raises(ValueError, match="gamma"):
        with grip_force.apply(FakeTask(), "left", gamma):
            pass
