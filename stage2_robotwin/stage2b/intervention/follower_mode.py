"""Task-frame follower target that preserves support and gripper closure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Sequence, Tuple

import numpy as np

from stage2_robotwin.responsibility.oracle import quaternion_delta_rotvec
from stage2_robotwin.wrappers.counterfactual_brancher import object_state

from .task_frame import ObjectTaskFrame


def parallel_follower_displacement(
    object_displacement_world: Sequence[float],
    e_parallel_world: Sequence[float],
    gamma: float,
) -> np.ndarray:
    """Return the follower setpoint displacement along ``e_parallel`` only.

    ``gamma`` retains the Stage 2B compliance-ratio interpretation.  A nominal
    rigid hold is gamma=1 (zero setpoint following); gamma=0 follows the object
    fully.  Candidates 0.6/0.4/0.2 therefore preserve 60/40/20 percent of the
    parallel positional error while all other task-frame targets stay fixed.
    """

    if not 0.0 <= gamma <= 1.0:
        raise ValueError("gamma must lie in [0, 1]")
    direction = np.asarray(e_parallel_world, dtype=np.float64)
    direction /= np.linalg.norm(direction)
    scalar = float(np.asarray(object_displacement_world, dtype=np.float64) @ direction)
    return (1.0 - gamma) * scalar * direction


def _quaternion_matrix_wxyz(value: Sequence[float]) -> np.ndarray:
    q = np.asarray(value, dtype=np.float64)
    q /= np.linalg.norm(q)
    w, x, y, z = q
    return np.asarray(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def _kinematics(task: Any, side: str) -> Tuple[Any, Any, Any, int, np.ndarray]:
    entity = task.robot.left_entity if side == "left" else task.robot.right_entity
    adapter = (
        task.robot.left_mplib_planner
        if side == "left"
        else task.robot.right_mplib_planner
    )
    planner = adapter.planner
    model = planner.pinocchio_model
    link_index = int(planner.move_group_link_id)
    move_indices = np.asarray(planner.move_group_joint_indices, dtype=np.int64)
    return entity, planner, model, link_index, move_indices


@dataclass
class TaskFrameFollower:
    task: Any
    side: str
    frame: ObjectTaskFrame
    gamma: float
    max_joint_delta_rad: float = 0.03
    max_translation_correction_m: float = 0.006
    max_rotation_correction_rad: float = 0.06

    def __post_init__(self) -> None:
        if self.side not in {"left", "right"}:
            raise ValueError("side must be left or right")
        if not 0.0 <= self.gamma <= 1.0:
            raise ValueError("gamma must lie in [0, 1]")
        entity, _, model, link_index, move_indices = _kinematics(self.task, self.side)
        qpos = np.asarray(entity.get_qpos(), dtype=np.float64)
        model.compute_forward_kinematics(qpos)
        pose = model.get_link_pose(link_index)
        self._start_link_position_root = np.asarray(pose.p, dtype=np.float64).copy()
        self._start_link_quaternion_root = np.asarray(pose.q, dtype=np.float64).copy()
        self._start_object_position_world = object_state(self.task)["pose"][:3].copy()
        self._move_indices = move_indices
        self._root_rotation = _quaternion_matrix_wxyz(entity.get_root_pose().q)
        self._parallel_root = self._root_rotation.T @ np.asarray(
            self.frame.e_parallel, dtype=np.float64
        )

    def target(self) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
        entity, _, model, link_index, move_indices = _kinematics(self.task, self.side)
        qpos = np.asarray(entity.get_qpos(), dtype=np.float64)
        model.compute_forward_kinematics(qpos)
        pose = model.get_link_pose(link_index)
        current_position = np.asarray(pose.p, dtype=np.float64)
        current_quaternion = np.asarray(pose.q, dtype=np.float64)

        object_displacement = (
            object_state(self.task)["pose"][:3] - self._start_object_position_world
        )
        desired_world = parallel_follower_displacement(
            object_displacement, self.frame.e_parallel, self.gamma
        )
        desired_root = self._root_rotation.T @ desired_world
        target_position = self._start_link_position_root + desired_root
        position_error = target_position - current_position
        position_norm = float(np.linalg.norm(position_error))
        if position_norm > self.max_translation_correction_m:
            position_error *= self.max_translation_correction_m / position_norm

        rotation_error = quaternion_delta_rotvec(
            current_quaternion, self._start_link_quaternion_root
        )
        rotation_norm = float(np.linalg.norm(rotation_error))
        if rotation_norm > self.max_rotation_correction_rad:
            rotation_error *= self.max_rotation_correction_rad / rotation_norm

        jacobian = np.asarray(
            model.compute_single_link_jacobian(qpos, link_index, local=False),
            dtype=np.float64,
        )[:, move_indices]
        twist = np.concatenate([position_error, rotation_error])
        delta = np.linalg.pinv(jacobian, rcond=1e-4) @ twist
        peak = float(np.max(np.abs(delta), initial=0.0))
        clipped = peak > self.max_joint_delta_rad
        if clipped:
            delta *= self.max_joint_delta_rad / peak

        target_qpos = qpos[move_indices] + delta
        return target_qpos, np.zeros_like(target_qpos), {
            "side": self.side,
            "gamma": float(self.gamma),
            "parallel_follow_fraction": float(1.0 - self.gamma),
            "object_parallel_displacement_m": float(
                object_displacement @ np.asarray(self.frame.e_parallel)
            ),
            "target_parallel_displacement_m": float(
                desired_world @ np.asarray(self.frame.e_parallel)
            ),
            "position_error_norm_m": position_norm,
            "rotation_error_norm_rad": rotation_norm,
            "joint_delta_max_abs_rad_before_clip": peak,
            "joint_delta_clipped": bool(clipped),
            "jacobian_condition_number": float(np.linalg.cond(jacobian)),
        }

