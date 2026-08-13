"""Matched contact-aware LEFT/RIGHT authority counterfactual profiles."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Mapping, Sequence

import numpy as np

from stage2_robotwin.responsibility.oracle import decompose_outcomes
from stage2_robotwin.responsibility.oracle_brancher import (
    _direction_target,
    _joint_neutral_state,
    baseline_features,
    capture_outcome_origin,
    measure_outcome,
)
from stage2_robotwin.wrappers.counterfactual_brancher import BRANCHES, SapienSnapshot

from .follower_mode import TaskFrameFollower
from .task_frame import ObjectTaskFrame


@dataclass(frozen=True)
class ContactAwareAuthorityProfile:
    name: str
    driver: str
    follower: str
    gamma: float
    implementation: str = "task_frame_follower_target"
    driver_amplitude_m: float = 0.004


def gamma_label(gamma: float) -> str:
    return f"{gamma:.3f}".rstrip("0").rstrip(".").replace(".", "p")


class ContactAwareAuthorityProbe:
    """Replay exact E4-relative snapshots with profile-level follower support."""

    def __init__(
        self,
        reference_e4: int,
        reference_e5: int,
        gammas: Sequence[float] = (0.6, 0.4, 0.2, 0.05),
        horizons: Sequence[int] = (5, 10),
        stride: int = 25,
        pre_e4_steps: int = 250,
        post_e4_steps: int = 150,
        driver_amplitude_m: float = 0.004,
    ) -> None:
        if reference_e5 <= reference_e4:
            raise ValueError("reference E5 must follow E4")
        if not horizons or min(horizons) < 1:
            raise ValueError("horizons must be positive")
        if stride < 1:
            raise ValueError("stride must be positive")
        values = tuple(float(value) for value in gammas)
        if not values or any(value <= 0.0 or value > 1.0 for value in values):
            raise ValueError("gammas must lie in (0, 1]")
        self.reference_e4 = int(reference_e4)
        self.reference_e5 = int(reference_e5)
        self.gammas = values
        self.horizons = tuple(sorted(set(int(value) for value in horizons)))
        self.stride = int(stride)
        self.window_start = self.reference_e4 - int(pre_e4_steps)
        self.window_end = min(
            self.reference_e5, self.reference_e4 + int(post_e4_steps)
        )
        self.sample_steps = tuple(
            range(self.window_start, self.window_end + 1, self.stride)
        )
        self._sample_set = set(self.sample_steps)
        self.driver_amplitude_m = float(driver_amplitude_m)

    def should_sample(self, step: int, events: Mapping[str, Any]) -> bool:
        # The window is frozen from a prior clean expert pass, allowing samples
        # before online E4 is observed.  The runner verifies actual E4/E5 match.
        return int(step) in self._sample_set

    def _profiles(self) -> Sequence[ContactAwareAuthorityProfile]:
        profiles = []
        for gamma in self.gammas:
            label = gamma_label(gamma)
            profiles.extend(
                [
                    ContactAwareAuthorityProfile(
                        f"contact_left_gamma_{label}",
                        driver="left",
                        follower="right",
                        gamma=gamma,
                        driver_amplitude_m=self.driver_amplitude_m,
                    ),
                    ContactAwareAuthorityProfile(
                        f"contact_right_gamma_{label}",
                        driver="right",
                        follower="left",
                        gamma=gamma,
                        driver_amplitude_m=self.driver_amplitude_m,
                    ),
                ]
            )
        return tuple(profiles)

    def _rollout(
        self,
        task: Any,
        snapshot: Mapping[str, Any],
        origin: Mapping[str, Any],
        frame: ObjectTaskFrame,
        profile: ContactAwareAuthorityProfile,
        branch: str,
        driver_target: np.ndarray,
    ) -> tuple[Dict[int, Dict[str, Any]], Dict[str, Any]]:
        SapienSnapshot.restore(task, snapshot)
        neutral = {
            side: _joint_neutral_state(task, side) for side in ("left", "right")
        }
        follower = TaskFrameFollower(task, profile.follower, frame, profile.gamma)
        driver_active = (
            profile.driver == "left" and branch in {"LR", "L"}
        ) or (profile.driver == "right" and branch in {"LR", "R"})
        outputs: Dict[int, Dict[str, Any]] = {}
        follower_audit = []
        for rollout_idx in range(max(self.horizons)):
            for side in ("left", "right"):
                if side == profile.driver:
                    position, velocity = (
                        (driver_target, np.zeros_like(driver_target))
                        if driver_active
                        else neutral[side]
                    )
                    task.robot.set_arm_joints(position, velocity, side)
                else:
                    position, velocity, audit = follower.target()
                    task.robot.set_arm_joints(position, velocity, side)
                    follower_audit.append(audit)
            # Direction probes intentionally never alter either gripper target.
            task.scene.step()
            horizon = rollout_idx + 1
            if horizon in self.horizons:
                outputs[horizon] = measure_outcome(task, origin)
        return outputs, {
            "sample_count": len(follower_audit),
            "any_joint_delta_clipped": any(
                item["joint_delta_clipped"] for item in follower_audit
            ),
            "max_position_error_norm_m": max(
                (item["position_error_norm_m"] for item in follower_audit),
                default=0.0,
            ),
            "max_rotation_error_norm_rad": max(
                (item["rotation_error_norm_rad"] for item in follower_audit),
                default=0.0,
            ),
            "last": follower_audit[-1] if follower_audit else None,
        }

    def evaluate(
        self,
        task: Any,
        step: int,
        control_seq: Mapping[str, Any],
        control_idx: int,
        event_names: Sequence[str],
    ) -> Sequence[Dict[str, Any]]:
        snapshot = SapienSnapshot.capture(task)
        origin = capture_outcome_origin(task)
        frame = ObjectTaskFrame.from_task(task)
        frame_audit = frame.audit()
        if not frame_audit["orthonormal_at_1e-12"]:
            raise RuntimeError("task frame failed orthonormality audit")
        baselines = baseline_features(task, control_seq, control_idx)
        driver_targets = {}
        driver_diagnostics = {}
        for side in ("left", "right"):
            driver_targets[side], driver_diagnostics[side] = _direction_target(
                task,
                side,
                frame.e_parallel,
                amplitude_m=self.driver_amplitude_m,
            )

        records = []
        for profile in self._profiles():
            by_horizon: Dict[int, Dict[str, Dict[str, Any]]] = {
                horizon: {} for horizon in self.horizons
            }
            branch_follower_audit = {}
            for branch in BRANCHES:
                rollout, follower_audit = self._rollout(
                    task,
                    snapshot,
                    origin,
                    frame,
                    profile,
                    branch,
                    driver_targets[profile.driver],
                )
                branch_follower_audit[branch] = follower_audit
                for horizon, outcome in rollout.items():
                    by_horizon[horizon][branch] = outcome
            for horizon in self.horizons:
                records.append(
                    {
                        "step": int(step),
                        "e4_relative_step": int(step - self.reference_e4),
                        "time_s": step / 250.0,
                        "event_names_observed": list(event_names),
                        "profile": asdict(profile),
                        "task_frame": frame_audit,
                        "driver_target_audit": driver_diagnostics[profile.driver],
                        "follower_audit": branch_follower_audit,
                        "baseline_features": baselines,
                        "horizon": int(horizon),
                        "outcomes": by_horizon[horizon],
                        "responsibility": decompose_outcomes(by_horizon[horizon]),
                        "neutral_contract": (
                            "measured qpos hold, zero target velocity, unchanged low-level mode; "
                            "both gripper drive targets held"
                        ),
                        "accepted": False,
                    }
                )
        SapienSnapshot.restore(task, snapshot)
        return records

    def contract(self) -> Dict[str, Any]:
        return {
            "reference_e4": self.reference_e4,
            "reference_e5": self.reference_e5,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "sample_steps": list(self.sample_steps),
            "stride": self.stride,
            "horizons": list(self.horizons),
            "gammas": list(self.gammas),
            "driver_amplitude_m": self.driver_amplitude_m,
            "profile_count": len(self._profiles()),
            "intervention": "contact-aware task-frame follower target",
            "both_grippers_held": True,
            "accepted": False,
        }

