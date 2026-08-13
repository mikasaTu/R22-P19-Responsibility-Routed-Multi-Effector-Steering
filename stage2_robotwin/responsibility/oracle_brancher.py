"""In-place LR/L/R/ZERO branching from explicit SAPIEN snapshots."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

import numpy as np

from stage2_robotwin.responsibility.oracle import (
    decompose_outcomes,
    quaternion_delta_rotvec,
)
from stage2_robotwin.wrappers.counterfactual_brancher import (
    BRANCHES,
    SapienSnapshot,
    gripper_object_contacts,
    object_state,
)


@dataclass(frozen=True)
class AuthorityProfile:
    name: str
    left_gain: float = 1.0
    right_gain: float = 1.0
    left_delay: int = 0
    right_delay: int = 0
    left_friction: float = 1.0
    right_friction: float = 1.0
    left_compliance: float = 1.0
    right_compliance: float = 1.0
    action_source: str = "expert"


BASE_PROFILE = AuthorityProfile("base")
AUTHORITY_SWAP_PROFILES = (
    AuthorityProfile("gain_left_high", left_gain=1.3, right_gain=0.7),
    AuthorityProfile("gain_right_high", left_gain=0.7, right_gain=1.3),
    AuthorityProfile("delay_left_2", left_delay=2),
    AuthorityProfile("delay_right_2", right_delay=2),
    AuthorityProfile("delay_left_4", left_delay=4),
    AuthorityProfile("delay_right_4", right_delay=4),
    AuthorityProfile("friction_left_high", left_friction=1.4, right_friction=0.6),
    AuthorityProfile("friction_right_high", left_friction=0.6, right_friction=1.4),
    AuthorityProfile("compliance_left_low", left_compliance=0.5),
    AuthorityProfile("compliance_right_low", right_compliance=0.5),
    AuthorityProfile("direction_left_authority", action_source="direction_left"),
    AuthorityProfile("direction_right_authority", action_source="direction_right"),
    AuthorityProfile(
        "direction_compliance_left_authority",
        right_compliance=0.05,
        action_source="direction_left",
    ),
    AuthorityProfile(
        "direction_compliance_right_authority",
        left_compliance=0.05,
        action_source="direction_right",
    ),
)


def _pose_vector(pose: Any) -> np.ndarray:
    return np.concatenate([np.asarray(pose.p), np.asarray(pose.q)]).astype(np.float64)


def _tcp_position(task: Any, side: str) -> np.ndarray:
    value = (
        task.robot.get_left_tcp_pose()
        if side == "left"
        else task.robot.get_right_tcp_pose()
    )
    return np.asarray(value[:3], dtype=np.float64)


def _quaternion_matrix_wxyz(value: Sequence[float]) -> np.ndarray:
    q = np.asarray(value, dtype=np.float64)
    q = q / np.linalg.norm(q)
    w, x, y, z = q
    return np.asarray(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def _direction_joint_delta(
    jacobian: np.ndarray,
    direction: Sequence[float],
    amplitude_m: float,
    max_joint_delta_rad: float,
) -> Tuple[np.ndarray, Dict[str, float]]:
    """Map a pure Cartesian translation to a bounded joint displacement."""

    matrix = np.asarray(jacobian, dtype=np.float64)
    unit = np.asarray(direction, dtype=np.float64)
    unit /= np.linalg.norm(unit)
    desired_twist = np.concatenate([unit * amplitude_m, np.zeros(3)])
    delta = np.linalg.pinv(matrix, rcond=1e-4) @ desired_twist
    peak = float(np.max(np.abs(delta), initial=0.0))
    if peak > max_joint_delta_rad:
        delta *= max_joint_delta_rad / peak
    predicted = matrix @ delta
    predicted_translation = predicted[:3]
    predicted_norm = float(np.linalg.norm(predicted_translation))
    cosine = (
        float(predicted_translation @ unit / predicted_norm)
        if predicted_norm > 1e-12
        else 0.0
    )
    return delta, {
        "desired_translation_m": float(amplitude_m),
        "predicted_translation_m": predicted_norm,
        "predicted_direction_cosine": cosine,
        "joint_delta_l2_rad": float(np.linalg.norm(delta)),
        "joint_delta_max_abs_rad": float(np.max(np.abs(delta), initial=0.0)),
        "jacobian_condition_number": float(np.linalg.cond(matrix)),
    }


def _direction_target(
    task: Any,
    side: str,
    world_direction: Sequence[float],
    amplitude_m: float = 0.004,
    max_joint_delta_rad: float = 0.05,
) -> Tuple[np.ndarray, Dict[str, Any]]:
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
    root_direction = root_rotation.T @ np.asarray(world_direction, dtype=np.float64)
    root_direction /= np.linalg.norm(root_direction)

    model.compute_forward_kinematics(qpos)
    start_position = np.asarray(model.get_link_pose(link_index).p, dtype=np.float64)
    jacobian = np.asarray(
        model.compute_single_link_jacobian(qpos, link_index, local=False),
        dtype=np.float64,
    )[:, move_indices]
    delta, diagnostics = _direction_joint_delta(
        jacobian,
        root_direction,
        amplitude_m,
        max_joint_delta_rad,
    )
    target_qpos = qpos.copy()
    target_qpos[move_indices] += delta
    model.compute_forward_kinematics(target_qpos)
    achieved = (
        np.asarray(model.get_link_pose(link_index).p, dtype=np.float64)
        - start_position
    )
    achieved_norm = float(np.linalg.norm(achieved))
    achieved_cosine = (
        float(achieved @ root_direction / achieved_norm)
        if achieved_norm > 1e-12
        else 0.0
    )
    diagnostics.update(
        {
            "side": side,
            "world_direction": np.asarray(world_direction, dtype=np.float64).tolist(),
            "root_direction": root_direction.tolist(),
            "fk_achieved_translation_m": achieved_norm,
            "fk_achieved_direction_cosine": achieved_cosine,
            "move_group_joint_indices": move_indices.tolist(),
        }
    )
    if achieved_norm < 5e-4 or achieved_cosine < 0.9:
        raise RuntimeError(
            f"{side} direction target failed validation: "
            f"translation={achieved_norm:.6g}, cosine={achieved_cosine:.6g}"
        )
    return target_qpos[move_indices], diagnostics


def direction_control_sequences(
    task: Any,
    origin: Mapping[str, Any],
    horizon: int,
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    motion = np.asarray(origin["target"]) - np.asarray(origin["box_functional"])
    if np.linalg.norm(motion) < 1e-9:
        motion = np.asarray([0.0, 0.0, 1.0])
    motion /= np.linalg.norm(motion)
    null = np.cross(motion, np.asarray([0.0, 0.0, 1.0]))
    if np.linalg.norm(null) < 1e-6:
        null = np.cross(motion, np.asarray([1.0, 0.0, 0.0]))
    null /= np.linalg.norm(null)

    targets: Dict[str, Dict[str, np.ndarray]] = {"aligned": {}, "null": {}}
    diagnostics: Dict[str, Any] = {
        "motion_direction_world": motion.tolist(),
        "null_direction_world": null.tolist(),
        "same_snapshot_contact_preload": True,
        "grippers_held": True,
    }
    for side in ("left", "right"):
        targets["aligned"][side], diagnostics[f"{side}_aligned"] = _direction_target(
            task, side, motion
        )
        targets["null"][side], diagnostics[f"{side}_null"] = _direction_target(
            task, side, null
        )

    def sequence(left_kind: str, right_kind: str) -> Dict[str, Any]:
        return {
            "left_arm": {
                "position": np.repeat(
                    targets[left_kind]["left"][None, :], horizon, axis=0
                ),
                "velocity": np.zeros((horizon, len(targets[left_kind]["left"]))),
            },
            "right_arm": {
                "position": np.repeat(
                    targets[right_kind]["right"][None, :], horizon, axis=0
                ),
                "velocity": np.zeros((horizon, len(targets[right_kind]["right"]))),
            },
            "left_gripper": None,
            "right_gripper": None,
        }

    return {
        "direction_left": sequence("aligned", "null"),
        "direction_right": sequence("null", "aligned"),
    }, diagnostics


def capture_outcome_origin(task: Any) -> Dict[str, Any]:
    state = object_state(task)
    return {
        "object": state,
        "left_tcp": _tcp_position(task, "left"),
        "right_tcp": _tcp_position(task, "right"),
        "target": np.asarray(
            task.target_box.get_functional_point(1, "pose").p, dtype=np.float64
        ),
        "box_functional": np.asarray(
            task.box.get_functional_point(0, "pose").p, dtype=np.float64
        ),
        "contacts": gripper_object_contacts(task),
    }


def measure_outcome(task: Any, origin: Mapping[str, Any]) -> Dict[str, Any]:
    state = object_state(task)
    position = state["pose"][:3]
    rotation = quaternion_delta_rotvec(origin["object"]["pose"][3:], state["pose"][3:])
    left_relative_start = origin["object"]["pose"][:3] - origin["left_tcp"]
    right_relative_start = origin["object"]["pose"][:3] - origin["right_tcp"]
    left_relative_end = position - _tcp_position(task, "left")
    right_relative_end = position - _tcp_position(task, "right")
    contacts = gripper_object_contacts(task)
    functional = np.asarray(
        task.box.get_functional_point(0, "pose").p, dtype=np.float64
    )
    start_distance = float(np.linalg.norm(origin["box_functional"] - origin["target"]))
    end_distance = float(np.linalg.norm(functional - origin["target"]))
    return {
        "translation": (position - origin["object"]["pose"][:3]).tolist(),
        "rotation_vector": rotation.tolist(),
        "linear_velocity": state["linear_velocity"].tolist(),
        "angular_velocity": state["angular_velocity"].tolist(),
        "support_delta": float(position[2] - origin["object"]["pose"][2]),
        "task_progress": start_distance - end_distance,
        "slip": [
            float(np.linalg.norm(left_relative_end - left_relative_start)),
            float(np.linalg.norm(right_relative_end - right_relative_start)),
        ],
        "drop": bool(position[2] < 0.78),
        "contact_retention": [float(contacts["left"]), float(contacts["right"])],
        "contacts": contacts,
    }


def _joint_neutral_state(task: Any, side: str) -> Tuple[np.ndarray, np.ndarray]:
    """Freeze the arm at its measured state without changing controller mode.

    Holding an old drive target is not a zero-increment command when the arm is
    still tracking that target.  The neutral counterfactual therefore installs
    the current measured joint position as the position target and zero as the
    velocity target.  Gripper targets are handled separately and remain held.
    """

    measured = (
        task.robot.get_left_arm_real_jointState()
        if side == "left"
        else task.robot.get_right_arm_real_jointState()
    )
    position = np.asarray(measured[:-1], dtype=np.float64)
    return position, np.zeros_like(position)


def _scheduled_arm(
    result: Optional[Mapping[str, Any]],
    control_idx: int,
    rollout_idx: int,
    delay: int,
    gain: float,
    hold_position: np.ndarray,
    hold_velocity: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    source_idx = rollout_idx - delay
    if result is None or source_idx < 0:
        return hold_position, hold_velocity
    index = min(control_idx + source_idx, result["position"].shape[0] - 1)
    if index < 0:
        return hold_position, hold_velocity
    position = np.asarray(result["position"][index], dtype=np.float64)
    velocity = np.asarray(result["velocity"][index], dtype=np.float64)
    return (
        hold_position + gain * (position - hold_position),
        gain * velocity,
    )


def _scheduled_gripper(
    result: Optional[Mapping[str, Any]], control_idx: int, rollout_idx: int, delay: int
) -> Optional[Tuple[float, float]]:
    source_idx = rollout_idx - delay
    if result is None or source_idx < 0:
        return None
    index = control_idx + source_idx
    if index >= int(result["num_step"]):
        return None
    return float(result["result"][index]), float(result["per_step"])


def _arm_joints(task: Any, side: str) -> Sequence[Any]:
    return task.robot.left_arm_joints if side == "left" else task.robot.right_arm_joints


def _gripper_shapes(task: Any, side: str) -> Iterable[Any]:
    joints = task.robot.left_gripper if side == "left" else task.robot.right_gripper
    for joint, _, _ in joints:
        yield from joint.child_link.collision_shapes


def _contact_impulses(task: Any) -> Dict[str, float]:
    object_id = int(task.box.actor.per_scene_id)
    link_names = {
        "left": {
            joint[0].child_link.get_name() for joint in task.robot.left_gripper
        },
        "right": {
            joint[0].child_link.get_name() for joint in task.robot.right_gripper
        },
    }
    values = {"left": 0.0, "right": 0.0}
    for contact in task.scene.get_contacts():
        first = contact.bodies[0].entity
        second = contact.bodies[1].entity
        if int(first.per_scene_id) == object_id:
            other = second
        elif int(second.per_scene_id) == object_id:
            other = first
        else:
            continue
        impulse = float(
            sum(np.linalg.norm(np.asarray(point.impulse)) for point in contact.points)
        )
        for side in ("left", "right"):
            if other.name in link_names[side]:
                values[side] += impulse
    return values


def _share(left: float, right: float, default: float = 0.5) -> float:
    total = left + right
    return default if total <= 1e-12 else float(left / total)


def baseline_features(
    task: Any, control_seq: Mapping[str, Any], control_idx: int
) -> Dict[str, Any]:
    object_position = object_state(task)["pose"][:3]
    distances = {
        side: float(np.linalg.norm(_tcp_position(task, side) - object_position))
        for side in ("left", "right")
    }
    impulses = _contact_impulses(task)
    magnitudes = {}
    for side in ("left", "right"):
        result = control_seq[f"{side}_arm"]
        hold_position, _ = _joint_neutral_state(task, side)
        if result is None or control_idx >= result["position"].shape[0]:
            magnitudes[side] = 0.0
        else:
            magnitudes[side] = float(
                np.linalg.norm(
                    np.asarray(result["position"][control_idx]) - hold_position
                )
            )
    inverse_left = 1.0 / max(distances["left"], 1e-12)
    inverse_right = 1.0 / max(distances["right"], 1e-12)
    return {
        "tcp_object_distance_m": distances,
        "contact_impulse_norm_sum": impulses,
        "arm_action_magnitude": magnitudes,
        "left_share_baselines": {
            "fixed_50_50": 0.5,
            "arm_identity_left": 1.0,
            "inverse_distance": _share(inverse_left, inverse_right),
            "contact_impulse": _share(impulses["left"], impulses["right"]),
            "action_magnitude": _share(magnitudes["left"], magnitudes["right"]),
        },
        "force_semantics": "contact impulse proxy, not calibrated force",
    }


@contextmanager
def authority_override(task: Any, profile: AuthorityProfile):
    materials = []
    drive_properties = []
    try:
        for side, scale in (
            ("left", profile.left_friction),
            ("right", profile.right_friction),
        ):
            if scale == 1.0:
                continue
            for shape in _gripper_shapes(task, side):
                original = shape.physical_material
                materials.append((shape, original))
                shape.physical_material = task.scene.create_physical_material(
                    float(original.static_friction) * scale,
                    float(original.dynamic_friction) * scale,
                    float(original.restitution),
                )
        for side, scale in (
            ("left", profile.left_compliance),
            ("right", profile.right_compliance),
        ):
            if scale == 1.0:
                continue
            for joint in _arm_joints(task, side):
                original = (
                    float(joint.get_stiffness()),
                    float(joint.get_damping()),
                    float(joint.get_force_limit()),
                    joint.get_drive_mode(),
                )
                drive_properties.append((joint, original))
                joint.set_drive_properties(
                    original[0] * scale,
                    original[1] * scale,
                    original[2],
                    original[3],
                )
        yield
    finally:
        for shape, material in materials:
            shape.physical_material = material
        for joint, values in drive_properties:
            joint.set_drive_properties(*values)


class OracleBranchAuditor:
    def __init__(
        self,
        horizons: Sequence[int] = (5, 10),
        base_stride: int = 5,
        swap_stride: int = 25,
        profile_mode: str = "all",
    ) -> None:
        if not horizons or min(horizons) < 1:
            raise ValueError("counterfactual horizons must be positive")
        self.horizons = tuple(sorted(set(int(value) for value in horizons)))
        self.base_stride = int(base_stride)
        self.swap_stride = int(swap_stride)
        if profile_mode not in {"all", "direction_diagnostic"}:
            raise ValueError(f"unknown authority profile mode: {profile_mode}")
        self.profile_mode = profile_mode

    def should_sample(self, step: int, events: Mapping[str, Any]) -> bool:
        return "E2" in events and "E5" not in events and step % self.base_stride == 0

    def _rollout(
        self,
        task: Any,
        snapshot: Mapping[str, Any],
        origin: Mapping[str, Any],
        control_seq: Mapping[str, Any],
        control_idx: int,
        branch: str,
        profile: AuthorityProfile,
        direction_sequences: Mapping[str, Mapping[str, Any]],
    ) -> Dict[int, Dict[str, Any]]:
        SapienSnapshot.restore(task, snapshot)
        hold = {
            side: _joint_neutral_state(task, side) for side in ("left", "right")
        }
        active = {
            "left": branch in {"LR", "L"},
            "right": branch in {"LR", "R"},
        }
        gains = {"left": profile.left_gain, "right": profile.right_gain}
        delays = {"left": profile.left_delay, "right": profile.right_delay}
        selected_control = (
            direction_sequences[profile.action_source]
            if profile.action_source in direction_sequences
            else control_seq
        )
        outputs: Dict[int, Dict[str, Any]] = {}
        for rollout_idx in range(max(self.horizons)):
            for side in ("left", "right"):
                arm_result = (
                    selected_control[f"{side}_arm"] if active[side] else None
                )
                position, velocity = _scheduled_arm(
                    arm_result,
                    control_idx if profile.action_source == "expert" else 0,
                    rollout_idx,
                    delays[side],
                    gains[side],
                    hold[side][0],
                    hold[side][1],
                )
                task.robot.set_arm_joints(position, velocity, side)
                if active[side]:
                    gripper = _scheduled_gripper(
                        selected_control[f"{side}_gripper"],
                        control_idx if profile.action_source == "expert" else 0,
                        rollout_idx,
                        delays[side],
                    )
                    if gripper is not None:
                        task.robot.set_gripper(gripper[0], side, gripper[1])
            task.scene.step()
            horizon = rollout_idx + 1
            if horizon in self.horizons:
                outputs[horizon] = measure_outcome(task, origin)
        return outputs

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
        baselines = baseline_features(task, control_seq, control_idx)
        profiles = [BASE_PROFILE]
        direction_sequences: Dict[str, Dict[str, Any]] = {}
        direction_validation: Optional[Dict[str, Any]] = None
        if step % self.swap_stride == 0:
            profiles.extend(
                AUTHORITY_SWAP_PROFILES
                if self.profile_mode == "all"
                else tuple(
                    profile
                    for profile in AUTHORITY_SWAP_PROFILES
                    if profile.action_source.startswith("direction_")
                )
            )
            direction_sequences, direction_validation = direction_control_sequences(
                task, origin, max(self.horizons)
            )
        records = []
        for profile in profiles:
            by_horizon: Dict[int, Dict[str, Dict[str, Any]]] = {
                horizon: {} for horizon in self.horizons
            }
            with authority_override(task, profile):
                for branch in BRANCHES:
                    rollout = self._rollout(
                        task,
                        snapshot,
                        origin,
                        control_seq,
                        control_idx,
                        branch,
                        profile,
                        direction_sequences,
                    )
                    for horizon, outcome in rollout.items():
                        by_horizon[horizon][branch] = outcome
            for horizon in self.horizons:
                records.append(
                    {
                        "step": int(step),
                        "time_s": step / 250.0,
                        "event_names_observed": list(event_names),
                        "profile": asdict(profile),
                        "baseline_features": baselines,
                        "horizon": int(horizon),
                        "outcomes": by_horizon[horizon],
                        "responsibility": decompose_outcomes(
                            by_horizon[horizon]
                        ),
                        "accepted": False,
                        "direction_validation": (
                            direction_validation
                            if profile.action_source.startswith("direction_")
                            else None
                        ),
                    }
                )
        SapienSnapshot.restore(task, snapshot)
        return records
