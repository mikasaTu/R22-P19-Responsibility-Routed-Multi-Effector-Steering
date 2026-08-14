"""Natural expert-command oracle responsibility over H=5/10/20 horizons."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence, Tuple

import numpy as np

from stage2_robotwin.responsibility.oracle import decompose_outcomes
from stage2_robotwin.responsibility.oracle_brancher import (
    _contact_impulses,
    _joint_neutral_state,
    _tcp_position,
    capture_outcome_origin,
    measure_outcome,
)
from stage2_robotwin.stage2b.operator.local_effect_gain import scalar_base_action
from stage2_robotwin.stage2b.intervention.task_frame import ObjectTaskFrame
from stage2_robotwin.stage2c.intervention.soft_expert_authority import (
    SoftExpertAuthorityProfile,
)
from stage2_robotwin.wrappers.counterfactual_brancher import BRANCHES, SapienSnapshot
from stage2_robotwin.wrappers.counterfactual_brancher import object_state


def _share(left: float, right: float) -> float:
    total = float(left + right)
    return 0.5 if total <= 1e-12 else float(left / total)


class NaturalResponsibilityEstimator:
    """Evaluate all horizons in one four-branch rollout per sampled state."""

    def __init__(self, horizons: Sequence[int] = (5, 10, 20)) -> None:
        values = tuple(sorted(set(int(value) for value in horizons)))
        if not values or values[0] < 1:
            raise ValueError("horizons must be positive")
        self.horizons = values

    @staticmethod
    def _rollout(
        task: Any,
        snapshot: Mapping[str, Any],
        origin: Mapping[str, Any],
        target_sequence: Sequence[Mapping[str, Tuple[np.ndarray, np.ndarray]]],
        branch: str,
        horizons: Sequence[int],
        frame: ObjectTaskFrame,
        soft_arm: str | None,
        gamma: float | None,
        gripper_sequence: Sequence[Mapping[str, Tuple[float, float] | None]],
    ) -> Dict[int, Dict[str, Any]]:
        SapienSnapshot.restore(task, snapshot)
        neutral = {side: _joint_neutral_state(task, side) for side in ("left", "right")}
        soft_profile = (
            SoftExpertAuthorityProfile(task, soft_arm, float(gamma), frame)
            if soft_arm is not None and gamma is not None
            else None
        )
        outputs: Dict[int, Dict[str, Any]] = {}
        for index, targets in enumerate(target_sequence[: max(horizons)]):
            for side in ("left", "right"):
                active = branch == "LR" or branch == side[0].upper()
                if active:
                    position, velocity = targets[side]
                    if soft_profile is not None and side == soft_profile.soft_arm:
                        (position, velocity), _ = soft_profile.blend(
                            (position, velocity)
                        )
                else:
                    position, velocity = neutral[side]
                task.robot.set_arm_joints(position, velocity, side)
                command = gripper_sequence[index][side]
                if command is not None:
                    task.robot.set_gripper(command[0], side, command[1])
            task.scene.step()
            horizon = index + 1
            if horizon in horizons:
                outputs[horizon] = measure_outcome(task, origin)
        return outputs

    def estimate(
        self,
        task: Any,
        target_sequence: Sequence[Mapping[str, Tuple[Sequence[float], Sequence[float]]]],
        frame: ObjectTaskFrame,
        *,
        soft_arm: str | None = None,
        gamma: float | None = None,
        gripper_sequence: Sequence[Mapping[str, Tuple[float, float] | None]] | None = None,
    ) -> Dict[str, Any]:
        if len(target_sequence) < max(self.horizons):
            raise ValueError("target_sequence is shorter than the largest horizon")
        if gripper_sequence is None:
            gripper_sequence = [
                {"left": None, "right": None} for _ in target_sequence
            ]
        if len(gripper_sequence) < max(self.horizons):
            raise ValueError("gripper_sequence is shorter than the largest horizon")
        targets = [
            {
                side: (
                    np.asarray(item[side][0], dtype=np.float64),
                    np.asarray(item[side][1], dtype=np.float64),
                )
                for side in ("left", "right")
            }
            for item in target_sequence
        ]
        snapshot = SapienSnapshot.capture(task)
        origin = capture_outcome_origin(task)
        by_horizon: Dict[int, Dict[str, Dict[str, Any]]] = {
            horizon: {} for horizon in self.horizons
        }
        try:
            for branch in BRANCHES:
                rollout = self._rollout(
                    task,
                    snapshot,
                    origin,
                    targets,
                    branch,
                    self.horizons,
                    frame,
                    soft_arm,
                    gamma,
                    gripper_sequence,
                )
                for horizon, outcome in rollout.items():
                    by_horizon[horizon][branch] = outcome
        finally:
            SapienSnapshot.restore(task, snapshot)

        position = object_state(task)["pose"][:3]
        distances = {
            side: float(np.linalg.norm(_tcp_position(task, side) - position))
            for side in ("left", "right")
        }
        impulses = _contact_impulses(task)
        action_magnitudes = {}
        scalar_actions = {}
        for side in ("left", "right"):
            measured = np.asarray(
                (
                    task.robot.get_left_arm_real_jointState()
                    if side == "left"
                    else task.robot.get_right_arm_real_jointState()
                )[:-1],
                dtype=np.float64,
            )
            action_magnitudes[side] = float(
                np.linalg.norm(targets[0][side][0] - measured)
            )
            scalar_actions[side] = float(
                scalar_base_action(
                    task, side, targets[0][side][0], frame.e_parallel
                )[0]
            )
        inverse_distance = {
            side: 1.0 / max(value, 1e-12) for side, value in distances.items()
        }
        records = {}
        for horizon in self.horizons:
            decomposition = decompose_outcomes(by_horizon[horizon])
            channel = decomposition["three_channel"]
            records[horizon] = {
                "horizon": horizon,
                "outcomes": by_horizon[horizon],
                "responsibility": decomposition,
                "rho_left": float(channel["rho_left"]),
                "rho_right": float(channel["rho_right"]),
                "rho_joint": float(channel["rho_joint"]),
                "productive_left": float(max(channel["rho_left"], 0.0)),
                "productive_right": float(max(channel["rho_right"], 0.0)),
                "harmful_left": float(min(channel["rho_left"], 0.0)),
                "harmful_right": float(min(channel["rho_right"], 0.0)),
            }
        return {
            "by_horizon": records,
            "baselines": {
                "tcp_object_distance_m": distances,
                "contact_impulse_norm_sum": impulses,
                "arm_action_magnitude": action_magnitudes,
                "scalar_parallel_action_m": scalar_actions,
                "left_share": {
                    "fixed_50_50": 0.5,
                    "inverse_distance": _share(
                        inverse_distance["left"], inverse_distance["right"]
                    ),
                    "contact_impulse": _share(impulses["left"], impulses["right"]),
                    "action_magnitude": _share(
                        action_magnitudes["left"], action_magnitudes["right"]
                    ),
                },
            },
            "branch_rollout_count": 4,
            "simulated_physics_steps": 4 * max(self.horizons),
            "gripper_source": "expert_command_sequence",
            "soft_arm": soft_arm,
            "soft_gamma": gamma,
            "accepted": False,
        }
