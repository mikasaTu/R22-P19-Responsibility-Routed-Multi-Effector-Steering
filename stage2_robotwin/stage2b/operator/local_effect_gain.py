"""Simulator-oracle local responsibility and central finite-difference gains."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Sequence, Tuple

import numpy as np

from stage2_robotwin.responsibility.oracle import decompose_outcomes
from stage2_robotwin.responsibility.oracle_brancher import (
    _direction_joint_delta,
    _joint_neutral_state,
    _quaternion_matrix_wxyz,
    capture_outcome_origin,
    measure_outcome,
)
from stage2_robotwin.wrappers.counterfactual_brancher import BRANCHES, SapienSnapshot

from stage2_robotwin.stage2b.intervention.task_frame import ObjectTaskFrame


def _arm_model(task: Any, side: str):
    entity = task.robot.left_entity if side == "left" else task.robot.right_entity
    adapter = (
        task.robot.left_mplib_planner
        if side == "left"
        else task.robot.right_mplib_planner
    )
    planner = adapter.planner
    model = planner.pinocchio_model
    qpos = np.asarray(entity.get_qpos(), dtype=np.float64)
    link_index = int(planner.move_group_link_id)
    move_indices = np.asarray(planner.move_group_joint_indices, dtype=np.int64)
    root_rotation = _quaternion_matrix_wxyz(entity.get_root_pose().q)
    return entity, model, qpos, link_index, move_indices, root_rotation


def task_direction_joint_delta(
    task: Any,
    side: str,
    e_parallel_world: Sequence[float],
    displacement_m: float,
    max_joint_delta_rad: float = 0.05,
) -> Tuple[np.ndarray, Dict[str, float]]:
    _, model, qpos, link_index, move_indices, root_rotation = _arm_model(task, side)
    model.compute_forward_kinematics(qpos)
    jacobian = np.asarray(
        model.compute_single_link_jacobian(qpos, link_index, local=False),
        dtype=np.float64,
    )[:, move_indices]
    root_direction = root_rotation.T @ np.asarray(e_parallel_world, dtype=np.float64)
    sign = 1.0 if displacement_m >= 0 else -1.0
    delta, audit = _direction_joint_delta(
        jacobian,
        sign * root_direction,
        abs(displacement_m),
        max_joint_delta_rad,
    )
    return delta, audit


def scalar_base_action(
    task: Any,
    side: str,
    target_position: Sequence[float],
    e_parallel_world: Sequence[float],
) -> Tuple[float, Dict[str, Any]]:
    _, model, qpos, link_index, move_indices, root_rotation = _arm_model(task, side)
    model.compute_forward_kinematics(qpos)
    jacobian = np.asarray(
        model.compute_single_link_jacobian(qpos, link_index, local=False),
        dtype=np.float64,
    )[:, move_indices]
    measured = qpos[move_indices]
    delta = np.asarray(target_position, dtype=np.float64) - measured
    predicted_twist = jacobian @ delta
    root_direction = root_rotation.T @ np.asarray(e_parallel_world, dtype=np.float64)
    value = float(predicted_twist[:3] @ root_direction)
    return value, {
        "predicted_translation_root": predicted_twist[:3].tolist(),
        "predicted_rotation_root": predicted_twist[3:].tolist(),
        "scalar_task_direction_action_m": value,
        "joint_target_delta_l2_rad": float(np.linalg.norm(delta)),
    }


def _projected_translation(outcome: Mapping[str, Any], direction: np.ndarray) -> float:
    return float(np.asarray(outcome["translation"], dtype=np.float64) @ direction)


class SimulatorLocalEffectEstimator:
    def __init__(self, horizon_steps: int = 5, finite_difference_delta_m: float = 0.0005):
        if horizon_steps < 1 or finite_difference_delta_m <= 0:
            raise ValueError("invalid local effect estimator settings")
        self.horizon_steps = int(horizon_steps)
        self.finite_difference_delta_m = float(finite_difference_delta_m)

    def _rollout(
        self,
        task: Any,
        snapshot: Mapping[str, Any],
        origin: Mapping[str, Any],
        targets: Mapping[str, Tuple[np.ndarray, np.ndarray]],
        active: Mapping[str, bool],
    ) -> Dict[str, Any]:
        SapienSnapshot.restore(task, snapshot)
        neutral = {
            side: _joint_neutral_state(task, side) for side in ("left", "right")
        }
        for _ in range(self.horizon_steps):
            for side in ("left", "right"):
                position, velocity = targets[side] if active[side] else neutral[side]
                task.robot.set_arm_joints(position, velocity, side)
            # Existing gripper drive targets and normalized closure bookkeeping
            # remain untouched in all estimator branches.
            task.scene.step()
        return measure_outcome(task, origin)

    def estimate(
        self,
        task: Any,
        left_target: Tuple[Sequence[float], Sequence[float]],
        right_target: Tuple[Sequence[float], Sequence[float]],
        frame: ObjectTaskFrame,
    ) -> Dict[str, Any]:
        snapshot = SapienSnapshot.capture(task)
        origin = capture_outcome_origin(task)
        direction = np.asarray(frame.e_parallel, dtype=np.float64)
        targets = {
            "left": (
                np.asarray(left_target[0], dtype=np.float64),
                np.asarray(left_target[1], dtype=np.float64),
            ),
            "right": (
                np.asarray(right_target[0], dtype=np.float64),
                np.asarray(right_target[1], dtype=np.float64),
            ),
        }
        outcomes = {}
        for branch in BRANCHES:
            outcomes[branch] = self._rollout(
                task,
                snapshot,
                origin,
                targets,
                {
                    "left": branch in {"LR", "L"},
                    "right": branch in {"LR", "R"},
                },
            )
        responsibility = decompose_outcomes(outcomes)

        finite_difference = {}
        gains = []
        for side in ("left", "right"):
            SapienSnapshot.restore(task, snapshot)
            delta_q, delta_audit = task_direction_joint_delta(
                task,
                side,
                frame.e_parallel,
                self.finite_difference_delta_m,
            )
            values = {}
            for sign, name in ((1.0, "plus"), (-1.0, "minus")):
                perturbed = {
                    key: (value[0].copy(), value[1].copy())
                    for key, value in targets.items()
                }
                perturbed[side] = (
                    perturbed[side][0] + sign * delta_q,
                    perturbed[side][1],
                )
                values[name] = self._rollout(
                    task,
                    snapshot,
                    origin,
                    perturbed,
                    {"left": True, "right": True},
                )
            plus = _projected_translation(values["plus"], direction)
            minus = _projected_translation(values["minus"], direction)
            gain = (plus - minus) / (2.0 * self.finite_difference_delta_m)
            gains.append(float(gain))
            finite_difference[side] = {
                "plus_effect_m": plus,
                "minus_effect_m": minus,
                "central_gain": float(gain),
                "joint_delta_audit": delta_audit,
            }

        base_actions = []
        base_action_audit = {}
        SapienSnapshot.restore(task, snapshot)
        for side in ("left", "right"):
            value, audit = scalar_base_action(
                task, side, targets[side][0], frame.e_parallel
            )
            base_actions.append(value)
            base_action_audit[side] = audit
        channel = responsibility["three_channel"]
        SapienSnapshot.restore(task, snapshot)
        return {
            "base_action": base_actions,
            "base_action_audit": base_action_audit,
            "local_gain": gains,
            "finite_difference": finite_difference,
            "rho_left": float(channel["rho_left"]),
            "rho_right": float(channel["rho_right"]),
            "rho_joint": float(channel["rho_joint"]),
            "responsibility": responsibility,
            "outcomes": outcomes,
            "lr_receiver_contact_retention": float(outcomes["LR"]["contact_retention"][1]),
            "lr_max_slip_m": float(max(outcomes["LR"]["slip"])),
            "lr_drop": bool(outcomes["LR"]["drop"]),
            "branch_rollout_count": 8,
            "simulated_physics_steps": 8 * self.horizon_steps,
            "grippers_held": True,
        }
