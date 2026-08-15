from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence, Tuple

import numpy as np

from stage2_robotwin.stage2b.intervention.task_frame import ObjectTaskFrame
from stage2_robotwin.stage2b.operator.local_effect_gain import _arm_model
from stage2_robotwin.wrappers.counterfactual_brancher import object_state


def _unit(value: Sequence[float]) -> np.ndarray:
    value = np.asarray(value, dtype=np.float64)
    return value / max(float(np.linalg.norm(value)), 1e-12)


def _project(vector: np.ndarray, axis: np.ndarray, offset: int) -> np.ndarray:
    result = np.zeros(6, dtype=np.float64)
    part = vector[offset:offset + 3]
    result[offset:offset + 3] = axis * float(part @ axis)
    return result


def channel_projected_target(task: Any, side: str, target_position: Sequence[float],
                             target_velocity: Sequence[float], frame: ObjectTaskFrame,
                             channel: str, fade: float) -> Tuple[np.ndarray, np.ndarray, dict]:
    """Remove one commanded task-space component while leaving the rest unchanged.

    SAPIEN exposes diagonal joint-drive impedance, not Cartesian-axis impedance.  A
    direct stiffness fade would remove every channel.  This adapter therefore applies
    the plan's object-following fallback: it projects the expert joint target through
    the live Jacobian, attenuates exactly one task-space component, then maps the
    remaining twist back into the same joint drive.
    """
    if channel not in {"motion", "support", "rotation"}:
        raise ValueError(f"arm target withdrawal does not support {channel}")
    if not 0.0 <= fade <= 1.0:
        raise ValueError("fade must lie in [0,1]")
    entity, model, qpos, link_index, move_indices, root_rotation = _arm_model(task, side)
    model.compute_forward_kinematics(qpos)
    jacobian = np.asarray(model.compute_single_link_jacobian(
        qpos, link_index, local=False), dtype=np.float64)[:, move_indices]
    measured = qpos[move_indices]
    target_position = np.asarray(target_position, dtype=np.float64)
    target_velocity = np.asarray(target_velocity, dtype=np.float64)
    delta = target_position - measured
    twist = jacobian @ delta
    velocity_twist = jacobian @ target_velocity
    if channel == "motion":
        axis = _unit(root_rotation.T @ np.asarray(frame.e_parallel))
        selected = _project(twist, axis, 0)
        selected_velocity = _project(velocity_twist, axis, 0)
    elif channel == "support":
        axis = _unit(root_rotation.T @ np.asarray(frame.e_vertical))
        selected = _project(twist, axis, 0)
        selected_velocity = _project(velocity_twist, axis, 0)
    else:
        axis = _unit(root_rotation.T @ np.asarray(frame.e_vertical))
        selected = _project(twist, axis, 3)
        selected_velocity = _project(velocity_twist, axis, 3)
    commanded_twist = twist - (1.0 - float(fade)) * selected
    commanded_velocity_twist = velocity_twist - (1.0 - float(fade)) * selected_velocity
    pinv = np.linalg.pinv(jacobian, rcond=1e-4)
    command_position = measured + pinv @ commanded_twist
    command_velocity = pinv @ commanded_velocity_twist
    return command_position, command_velocity, {
        "control_mode": "live_jacobian_task_component_object_following_fallback",
        "cartesian_axis_impedance_available": False,
        "joint_diagonal_impedance_available": True,
        "channel": channel,
        "fade": float(fade),
        "selected_twist_norm": float(np.linalg.norm(selected)),
        "unselected_twist_norm": float(np.linalg.norm(twist - selected)),
        "command_delta_l2_rad": float(np.linalg.norm(command_position - target_position)),
        "jacobian_condition_number": float(np.linalg.cond(jacobian)),
    }


def retention_command(base_command, fade: float) -> tuple[float, float]:
    """Continuously interpolate donor closure to a real open-gripper command."""
    base_value, base_step = (0.0, 0.1) if base_command is None else base_command
    value = float(fade) * float(base_value) + (1.0 - float(fade)) * 1.0
    # Positive eps is required by RoboTwin's incremental opening path.
    return float(np.clip(value, 0.0, 1.0)), max(abs(float(base_step)), 0.1)


def receiver_command_hash(future: Sequence[Mapping], receiver: str) -> str:
    payload = []
    for item in future:
        payload.append({
            "position": np.asarray(item[f"{receiver}_position"], dtype=float).round(12).tolist(),
            "velocity": np.asarray(item[f"{receiver}_velocity"], dtype=float).round(12).tolist(),
            "gripper": item[f"{receiver}_gripper"],
        })
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def contact_wrench_by_side(task: Any, frame: ObjectTaskFrame) -> dict:
    """Measure per-hand object contact impulse and torque in the object frame proxy."""
    object_id = int(task.box.actor.per_scene_id)
    object_com = np.asarray(object_state(task)["pose"][:3], dtype=np.float64)
    names = {
        "left": {j[0].child_link.get_name() for j in task.robot.left_gripper},
        "right": {j[0].child_link.get_name() for j in task.robot.right_gripper},
    }
    result = {side: {"impulse": np.zeros(3), "torque": np.zeros(3),
                     "points": 0} for side in names}
    for contact in task.scene.get_contacts():
        first, second = contact.bodies[0].entity, contact.bodies[1].entity
        if int(first.per_scene_id) == object_id:
            other, sign = second, 1.0
        elif int(second.per_scene_id) == object_id:
            other, sign = first, -1.0
        else:
            continue
        side = next((s for s, values in names.items() if other.name in values), None)
        if side is None:
            continue
        for point in contact.points:
            impulse = sign * np.asarray(point.impulse, dtype=np.float64)
            position = np.asarray(point.position, dtype=np.float64)
            result[side]["impulse"] += impulse
            result[side]["torque"] += np.cross(position - object_com, impulse)
            result[side]["points"] += 1
    axes = {
        "motion": np.asarray(frame.e_parallel, dtype=np.float64),
        "support": np.asarray(frame.e_vertical, dtype=np.float64),
        "rotation": np.asarray(frame.e_vertical, dtype=np.float64),
    }
    for side, values in result.items():
        values.update({
            "motion": abs(float(values["impulse"] @ axes["motion"])),
            "support": abs(float(values["impulse"] @ axes["support"])),
            "rotation": abs(float(values["torque"] @ axes["rotation"])),
            "retention": float(np.linalg.norm(values["impulse"])),
            "contact": bool(values["points"]),
            "impulse": values["impulse"].tolist(),
            "torque": values["torque"].tolist(),
        })
    return result
