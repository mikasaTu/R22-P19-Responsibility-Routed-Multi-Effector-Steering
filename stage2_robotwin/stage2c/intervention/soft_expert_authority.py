"""Blend expert and follower commands only along the task-parallel axis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Sequence, Tuple

import numpy as np

from stage2_robotwin.stage2b.intervention.follower_mode import TaskFrameFollower
from stage2_robotwin.stage2b.intervention.task_frame import ObjectTaskFrame
from stage2_robotwin.stage2b.operator.local_effect_gain import (
    scalar_base_action,
    task_direction_joint_delta,
)


@dataclass
class SoftExpertAuthorityProfile:
    task: Any
    soft_arm: str
    gamma: float
    frame: ObjectTaskFrame
    max_joint_delta_rad: float = 0.04

    def __post_init__(self) -> None:
        if self.soft_arm not in {"left", "right"}:
            raise ValueError("soft_arm must be left or right")
        if not 0.0 <= self.gamma <= 1.0:
            raise ValueError("gamma must lie in [0, 1]")
        self.follower = TaskFrameFollower(
            self.task, self.soft_arm, self.frame, gamma=0.0
        )

    def blend(
        self,
        expert_target: Tuple[Sequence[float], Sequence[float]],
    ) -> tuple[Tuple[np.ndarray, np.ndarray], Dict[str, Any]]:
        expert_position = np.asarray(expert_target[0], dtype=np.float64)
        expert_velocity = np.asarray(expert_target[1], dtype=np.float64)
        follower_position, _, follower_audit = self.follower.target()
        expert_parallel, expert_audit = scalar_base_action(
            self.task, self.soft_arm, expert_position, self.frame.e_parallel
        )
        follower_parallel, follower_action_audit = scalar_base_action(
            self.task, self.soft_arm, follower_position, self.frame.e_parallel
        )
        soft_parallel = self.gamma * expert_parallel + (1.0 - self.gamma) * follower_parallel
        correction = soft_parallel - expert_parallel
        joint_delta, delta_audit = task_direction_joint_delta(
            self.task,
            self.soft_arm,
            self.frame.e_parallel,
            correction,
            max_joint_delta_rad=self.max_joint_delta_rad,
        )
        routed_position = expert_position + joint_delta
        return (routed_position, expert_velocity.copy()), {
            "profile": {
                "name": "SoftExpertAuthorityProfile",
                "soft_arm": self.soft_arm,
                "gamma": float(self.gamma),
                "max_joint_delta_rad": float(self.max_joint_delta_rad),
            },
            "expert_parallel_action_m": float(expert_parallel),
            "follower_parallel_action_m": float(follower_parallel),
            "soft_parallel_action_m": float(soft_parallel),
            "parallel_correction_m": float(correction),
            "expert_action_audit": expert_audit,
            "follower_action_audit": follower_action_audit,
            "follower_state_audit": follower_audit,
            "joint_delta_audit": delta_audit,
            "perpendicular_vertical_rotation_source": "unchanged_expert_target",
            "gripper_source": "unchanged_expert_command",
        }
