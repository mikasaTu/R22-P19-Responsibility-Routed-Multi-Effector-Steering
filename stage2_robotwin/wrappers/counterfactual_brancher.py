"""Snapshot contracts and LR/L/R/ZERO action construction."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, Mapping, MutableMapping, Sequence

import numpy as np


BRANCHES = ("LR", "L", "R", "ZERO")


def hold_neutral_action(action: Sequence[float], branch: str) -> np.ndarray:
    """Return a 14-D RoboTwin joint action with held gripper commands.

    Layout is left arm 6, left gripper 1, right arm 6, right gripper 1.
    Neutral arm targets are represented by NaNs here and must be replaced with
    current joint drive targets by the environment adapter.  Gripper entries
    are always copied from the base action, so neutral never opens a hand.
    """

    value = np.asarray(action, dtype=np.float64)
    if value.shape != (14,):
        raise ValueError(f"expected 14-D action, got {value.shape}")
    if branch not in BRANCHES:
        raise ValueError(f"unknown branch {branch}")
    result = value.copy()
    if branch in {"R", "ZERO"}:
        result[:6] = np.nan
    if branch in {"L", "ZERO"}:
        result[7:13] = np.nan
    result[6] = value[6]
    result[13] = value[13]
    return result


def _pose_array(pose: Any) -> np.ndarray:
    return np.concatenate([np.asarray(pose.p), np.asarray(pose.q)]).astype(np.float64)


class SapienSnapshot:
    """Explicit SAPIEN state contract used for deterministic replay.

    `Scene.pack_poses` alone omits rigid velocities, articulation qpos/qvel,
    root velocities, joint drive targets, and normalized gripper bookkeeping.
    Those fields are captured explicitly.  Solver warm-start caches are not
    exposed by SAPIEN and remain a documented boundary.
    """

    @staticmethod
    def capture(task: Any) -> Dict[str, Any]:
        articulations = []
        for articulation in task.scene.get_all_articulations():
            joints = articulation.get_active_joints()
            articulations.append(
                {
                    "qpos": np.asarray(articulation.get_qpos()).copy(),
                    "qvel": np.asarray(articulation.get_qvel()).copy(),
                    "root_pose": _pose_array(articulation.get_root_pose()),
                    "root_linear_velocity": np.asarray(
                        articulation.get_root_linear_velocity()
                    ).copy(),
                    "root_angular_velocity": np.asarray(
                        articulation.get_root_angular_velocity()
                    ).copy(),
                    "drive_target": [
                        np.asarray(joint.get_drive_target()).copy() for joint in joints
                    ],
                    "drive_velocity_target": [
                        np.asarray(joint.get_drive_velocity_target()).copy()
                        for joint in joints
                    ],
                }
            )

        dynamics = []
        for actor in task.scene.get_all_actors():
            component = actor.find_component_by_type(
                __import__("sapien").physx.PhysxRigidDynamicComponent
            )
            if component is None:
                dynamics.append(None)
                continue
            dynamics.append(
                {
                    "pose": _pose_array(actor.get_pose()),
                    "linear_velocity": np.asarray(component.linear_velocity).copy(),
                    "angular_velocity": np.asarray(component.angular_velocity).copy(),
                    "sleeping": bool(component.is_sleeping),
                }
            )
        return {
            # SAPIEN 3 serializes poses as an opaque byte string.  Converting
            # it through NumPy changes the Python type and makes
            # ``Scene.unpack_poses`` reject the snapshot.
            "poses": bytes(task.scene.pack_poses()),
            "articulations": articulations,
            "dynamics": dynamics,
            "left_gripper_val": float(task.robot.get_left_gripper_val()),
            "right_gripper_val": float(task.robot.get_right_gripper_val()),
        }

    @staticmethod
    def restore(task: Any, snapshot: Mapping[str, Any]) -> None:
        import sapien

        # Do not call ``unpack_poses`` here.  It writes every entity pose,
        # including articulation links, before qpos is restored.  In an
        # articulated contact state that creates an inconsistent transient
        # and changes the next PhysX solve.  Restore articulation generalized
        # state and dynamic rigid actors through their physics APIs instead.
        for articulation, state in zip(
            task.scene.get_all_articulations(), snapshot["articulations"]
        ):
            articulation.set_qpos(np.asarray(state["qpos"]).copy())
            articulation.set_qvel(np.asarray(state["qvel"]).copy())
            root = state["root_pose"]
            articulation.set_root_pose(sapien.Pose(root[:3], root[3:]))
            articulation.set_root_linear_velocity(
                np.asarray(state["root_linear_velocity"]).copy()
            )
            articulation.set_root_angular_velocity(
                np.asarray(state["root_angular_velocity"]).copy()
            )
            for joint, target, velocity in zip(
                articulation.get_active_joints(),
                state["drive_target"],
                state["drive_velocity_target"],
            ):
                joint.set_drive_target(np.asarray(target).copy())
                joint.set_drive_velocity_target(np.asarray(velocity).copy())

        for actor, state in zip(task.scene.get_all_actors(), snapshot["dynamics"]):
            if state is None:
                continue
            component = actor.find_component_by_type(
                sapien.physx.PhysxRigidDynamicComponent
            )
            pose = np.asarray(state["pose"])
            actor.set_pose(sapien.Pose(pose[:3], pose[3:]))
            component.linear_velocity = np.asarray(state["linear_velocity"]).copy()
            component.angular_velocity = np.asarray(state["angular_velocity"]).copy()
            if state["sleeping"]:
                component.put_to_sleep()
            else:
                component.wake_up()
        task.robot.left_gripper_val = float(snapshot["left_gripper_val"])
        task.robot.right_gripper_val = float(snapshot["right_gripper_val"])


def object_state(task: Any) -> Dict[str, np.ndarray]:
    import sapien

    actor = task.box.actor
    component = actor.find_component_by_type(sapien.physx.PhysxRigidDynamicComponent)
    pose = actor.get_pose()
    return {
        "pose": _pose_array(pose),
        "linear_velocity": np.asarray(component.linear_velocity).copy(),
        "angular_velocity": np.asarray(component.angular_velocity).copy(),
    }


def gripper_object_contacts(task: Any) -> Dict[str, bool]:
    object_id = int(task.box.actor.per_scene_id)
    left_names = {
        joint[0].child_link.get_name() for joint in task.robot.left_gripper
    }
    right_names = {
        joint[0].child_link.get_name() for joint in task.robot.right_gripper
    }
    flags = {"left": False, "right": False}
    for contact in task.scene.get_contacts():
        first = contact.bodies[0].entity
        second = contact.bodies[1].entity
        if int(first.per_scene_id) == object_id:
            other = second
        elif int(second.per_scene_id) == object_id:
            other = first
        else:
            continue
        flags["left"] |= other.name in left_names
        flags["right"] |= other.name in right_names
    return flags


def deterministic_hold_replay(task: Any, horizon: int = 10) -> Dict[str, Any]:
    if horizon < 1:
        raise ValueError("horizon must be positive")
    snapshot = SapienSnapshot.capture(task)
    start_contacts = gripper_object_contacts(task)
    start_grippers = {
        "left": float(task.robot.get_left_gripper_val()),
        "right": float(task.robot.get_right_gripper_val()),
    }

    def run_once() -> Dict[str, Any]:
        SapienSnapshot.restore(task, snapshot)
        for _ in range(horizon):
            task.scene.step()
        return {
            "object": object_state(task),
            "contacts": gripper_object_contacts(task),
            "grippers": {
                "left": float(task.robot.get_left_gripper_val()),
                "right": float(task.robot.get_right_gripper_val()),
            },
        }

    first = run_once()
    second = run_once()
    SapienSnapshot.restore(task, snapshot)
    differences = {
        key: float(
            np.max(np.abs(first["object"][key] - second["object"][key]))
        )
        for key in first["object"]
    }
    return {
        "horizon_steps": int(horizon),
        "max_abs_difference": differences,
        "pose_equal_at_1e-8": differences["pose"] <= 1e-8,
        "twist_equal_at_1e-8": max(
            differences["linear_velocity"], differences["angular_velocity"]
        )
        <= 1e-8,
        "start_contacts": start_contacts,
        "replay_contacts": [first["contacts"], second["contacts"]],
        "start_grippers": start_grippers,
        "replay_grippers": [first["grippers"], second["grippers"]],
        "gripper_values_held": first["grippers"] == start_grippers
        and second["grippers"] == start_grippers,
        "contact_flags_repeatable": first["contacts"] == second["contacts"],
        "hidden_state_boundary": "PhysX solver warm-start caches are not exposed",
        "neutral_contract": "unchanged joint drive targets and held normalized gripper closure",
    }
