import numpy as np
import pytest

from stage2_robotwin.stage2f.intervention import drive_compliance, force_limit, target_interpolation
from stage2_robotwin.stage2f.intervention.common import canonical_command_sha256


class FakeJoint:
    def __init__(self, stiffness, damping, force_limit, mode="force"):
        self.values = [float(stiffness), float(damping), float(force_limit), mode]
        self.calls = []

    def get_stiffness(self): return self.values[0]
    def get_damping(self): return self.values[1]
    def get_force_limit(self): return self.values[2]
    def get_drive_mode(self): return self.values[3]

    def set_drive_properties(self, stiffness, damping, force_limit, mode):
        self.values = [float(stiffness), float(damping), float(force_limit), mode]
        self.calls.append(tuple(self.values))


class FakeRobot:
    def __init__(self):
        self.left_arm_joints = [FakeJoint(100 + i, 10 + i, 50 + i) for i in range(6)]
        self.right_arm_joints = [FakeJoint(200 + i, 20 + i, 60 + i) for i in range(6)]


class FakeTask:
    def __init__(self): self.robot = FakeRobot()


def values(joints):
    return [tuple(joint.values) for joint in joints]


@pytest.mark.parametrize("module", [drive_compliance, force_limit, target_interpolation])
def test_gamma_one_is_bitwise_noop(module):
    task = FakeTask()
    original = values(task.robot.left_arm_joints)
    position = np.arange(6, dtype=np.float64)
    velocity = -position
    with module.apply(task, "left", 1.0) as handle:
        routed = handle.route_target("left", (position, velocity))
        assert np.array_equal(routed[0], position)
        assert np.array_equal(routed[1], velocity)
        assert values(task.robot.left_arm_joints) == original
        assert all(not joint.calls for joint in task.robot.left_arm_joints)
    assert handle.restoration_exact
    assert handle.modified_joint_count == 0


def test_k1_changes_only_stiffness_and_damping_and_restores_after_exception():
    task = FakeTask()
    original = values(task.robot.left_arm_joints)
    with pytest.raises(RuntimeError, match="injected"):
        with drive_compliance.apply(task, "left", 0.2) as handle:
            for before, joint in zip(original, task.robot.left_arm_joints):
                assert joint.get_stiffness() == before[0] * 0.2
                assert joint.get_damping() == before[1] * 0.2
                assert joint.get_force_limit() == before[2]
                assert joint.get_drive_mode() == before[3]
            raise RuntimeError("injected")
    assert values(task.robot.left_arm_joints) == original
    assert handle.restoration_exact
    assert handle.modified_joint_count == 6


def test_k2_changes_only_force_limit_and_restores_after_exception():
    task = FakeTask()
    original = values(task.robot.right_arm_joints)
    with pytest.raises(RuntimeError, match="injected"):
        with force_limit.apply(task, "right", 0.4) as handle:
            for before, joint in zip(original, task.robot.right_arm_joints):
                assert joint.get_stiffness() == before[0]
                assert joint.get_damping() == before[1]
                assert joint.get_force_limit() == before[2] * 0.4
                assert joint.get_drive_mode() == before[3]
            raise RuntimeError("injected")
    assert values(task.robot.right_arm_joints) == original
    assert handle.restoration_exact


@pytest.mark.parametrize("module", [drive_compliance, force_limit])
def test_actuator_knobs_do_not_claim_target_action_modification(module):
    task = FakeTask()
    target = (np.arange(6, dtype=np.float64), np.zeros(6, dtype=np.float64))
    with module.apply(task, "left", 0.2) as handle:
        handle.route_target("left", target)
        handle.route_target("right", target)
    assert handle.action_modification_count == 0
    assert handle.target_modification_count == 0
    assert handle.actuator_application_count == 1


def test_k3_routes_only_soft_arm_and_never_mutates_drive_properties(monkeypatch):
    task = FakeTask()
    original_left = values(task.robot.left_arm_joints)
    original_right = values(task.robot.right_arm_joints)

    class Frame:
        @staticmethod
        def from_task(task): return object()

    class Profile:
        def __init__(self, task, soft_arm, gamma, frame): self.soft_arm, self.gamma = soft_arm, gamma
        def blend(self, target):
            return (np.asarray(target[0]) + 1.0, np.asarray(target[1]).copy()), {"fake": True}

    monkeypatch.setattr(target_interpolation, "ObjectTaskFrame", Frame)
    monkeypatch.setattr(target_interpolation, "SoftExpertAuthorityProfile", Profile)
    base = (np.arange(6, dtype=np.float64), np.zeros(6, dtype=np.float64))
    with target_interpolation.apply(task, "left", 0.2) as handle:
        receiver = handle.route_target("right", base)
        soft = handle.route_target("left", base)
        assert np.array_equal(receiver[0], base[0])
        assert np.array_equal(receiver[1], base[1])
        assert np.array_equal(soft[0], base[0] + 1.0)
    assert values(task.robot.left_arm_joints) == original_left
    assert values(task.robot.right_arm_joints) == original_right
    assert handle.restoration_exact and handle.target_modification_count == 1


def test_receiver_hash_is_exact_bytes_not_rounded():
    first = [{
        "right_position": np.asarray([1.0], dtype=np.float64),
        "right_velocity": np.asarray([0.0], dtype=np.float64),
        "right_gripper": (0.0, 0.1),
    }]
    second = [{**first[0], "right_position": np.nextafter(first[0]["right_position"], np.inf)}]
    assert canonical_command_sha256(first, "right") == canonical_command_sha256(first, "right")
    assert canonical_command_sha256(first, "right") != canonical_command_sha256(second, "right")
