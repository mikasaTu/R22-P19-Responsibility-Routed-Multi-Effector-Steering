"""One fresh RoboTwin process for one Stage 2C replay cell."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import time
import traceback
from collections import deque
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping, Optional, Sequence, Tuple

import numpy as np
import yaml

from stage2_robotwin.responsibility.oracle_brancher import (
    AuthorityProfile,
    _contact_impulses,
    _quaternion_matrix_wxyz,
    _tcp_position,
    authority_override,
)
from stage2_robotwin.stage2b.baselines.direct_scale import direct_scale_action
from stage2_robotwin.stage2b.baselines.distance_router import distance_weights
from stage2_robotwin.stage2b.baselines.force_router import force_weights
from stage2_robotwin.stage2b.baselines.phase_blend import phase_weights
from stage2_robotwin.stage2b.intervention.task_frame import ObjectTaskFrame
from stage2_robotwin.stage2b.operator.local_effect_gain import (
    SimulatorLocalEffectEstimator,
    task_direction_joint_delta,
)
from stage2_robotwin.stage2b.operator.release_guard import ResponsibilityReleaseGuard
from stage2_robotwin.stage2c.intervention.soft_expert_authority import (
    SoftExpertAuthorityProfile,
)
from stage2_robotwin.stage2c.operator.effect_nullspace_transfer_1d import (
    EffectNullspaceTransfer1D,
)
from stage2_robotwin.stage2c.replay.tape import ExpertTape
from stage2_robotwin.stage2c.responsibility.signed_joint_state import (
    classify_signed_responsibility,
)
from stage2_robotwin.stage2c.responsibility.temporal_filter import (
    StatefulResponsibilityFilter,
    project_simplex2,
)
from stage2_robotwin.wrappers.counterfactual_brancher import (
    SapienSnapshot,
    gripper_object_contacts,
    object_state,
)
from stage2_robotwin.wrappers.event_detector import HandoverEventDetector
from stage2_robotwin.wrappers.robotwin_runtime import build_handover_block


BASE_METHODS = {"B0", "C0"}
NULL_METHODS = {"OPERATOR_NULL", "C11"}
ORACLE_METHODS = {
    "OPERATOR_NULL",
    "C1",
    "C2",
    "C3",
    "C4",
    "C5",
    "C6",
    "C7",
    "C8",
    "C9",
    "C10",
    "C11",
    "C12",
    "C13",
}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _condition_targets(
    task: Any,
    item: Mapping[str, Any],
    receiver: str,
    condition: Mapping[str, Any],
    delay_queue: deque,
    initial_receiver_target: Tuple[np.ndarray, np.ndarray],
    active: bool,
) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
    targets = {
        "left": (
            np.asarray(item["left_position"], dtype=np.float64).copy(),
            np.asarray(item["left_velocity"], dtype=np.float64).copy(),
        ),
        "right": (
            np.asarray(item["right_position"], dtype=np.float64).copy(),
            np.asarray(item["right_velocity"], dtype=np.float64).copy(),
        ),
    }
    if not active:
        return targets
    gain = float(condition.get("receiver_gain", 1.0))
    if gain != 1.0:
        measured = np.asarray(
            (
                task.robot.get_left_arm_real_jointState()
                if receiver == "left"
                else task.robot.get_right_arm_real_jointState()
            )[:-1],
            dtype=np.float64,
        )
        position, velocity = targets[receiver]
        targets[receiver] = (
            measured + gain * (position - measured),
            gain * velocity,
        )
    delay = int(condition.get("receiver_delay_steps", 0))
    if delay:
        delay_queue.append(targets[receiver])
        targets[receiver] = (
            initial_receiver_target
            if len(delay_queue) <= delay
            else delay_queue.popleft()
        )
    return targets


def _shift_release_commands(
    tape: ExpertTape, donor: str, advance_steps: int
) -> np.ndarray:
    source = getattr(tape, f"{donor}_gripper").copy()
    if advance_steps <= 0:
        return source
    selected = np.flatnonzero(np.isfinite(source[:, 0]) & (source[:, 0] > 0.2))
    result = source.copy()
    result[selected] = np.nan
    for index in selected:
        result[max(0, int(index) - advance_steps)] = source[index]
    return result


def _prefix_fingerprint(task: Any, step: int) -> Dict[str, Any]:
    state = object_state(task)
    contacts = gripper_object_contacts(task)
    value = {
        "step": int(step),
        "object_pose": state["pose"].tolist(),
        "object_linear_velocity": state["linear_velocity"].tolist(),
        "object_angular_velocity": state["angular_velocity"].tolist(),
        "left_tcp": _tcp_position(task, "left").tolist(),
        "right_tcp": _tcp_position(task, "right").tolist(),
        "contacts": contacts,
        "left_qpos": np.asarray(task.robot.get_left_arm_real_jointState()[:-1]).tolist(),
        "right_qpos": np.asarray(task.robot.get_right_arm_real_jointState()[:-1]).tolist(),
    }
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    value["sha256"] = hashlib.sha256(canonical).hexdigest()
    return value


class ConditionOverride:
    """Apply stress exactly at frozen E2 and restore process-local properties."""

    def __init__(self, task: Any, receiver: str, condition: Mapping[str, Any], frame: ObjectTaskFrame):
        self.task = task
        self.receiver = receiver
        self.condition = condition
        self.frame = frame
        self.stack = contextlib.ExitStack()
        self.applied = False
        self._component = None
        self._original_cmass_pose = None
        self.audit: Dict[str, Any] = {"applied_at_E2": False}

    def apply(self) -> None:
        if self.applied:
            return
        friction = float(self.condition.get("receiver_friction", self.condition.get("receiver_friction_scale", 1.0)))
        if friction != 1.0:
            profile = AuthorityProfile(
                name="stage2c_receiver_friction",
                left_friction=friction if self.receiver == "left" else 1.0,
                right_friction=friction if self.receiver == "right" else 1.0,
            )
            self.stack.enter_context(authority_override(self.task, profile))
            self.audit["receiver_friction_scale"] = friction
            self.audit["receiver_friction_semantics"] = (
                "multiplicative scale on original static and dynamic gripper friction"
            )

        shift_mm = float(self.condition.get("object_com_shift_mm", 0.0))
        if shift_mm:
            import sapien

            self._component = self.task.box.actor.find_component_by_type(
                sapien.physx.PhysxRigidDynamicComponent
            )
            self._original_cmass_pose = self._component.cmass_local_pose
            direction_world = np.asarray(self.frame.e_perp, dtype=np.float64)
            object_pose = object_state(self.task)["pose"]
            direction_local = _quaternion_matrix_wxyz(object_pose[3:]).T @ direction_world
            local_shift = direction_local * (shift_mm / 1000.0)
            original = self._original_cmass_pose
            self._component.cmass_local_pose = sapien.Pose(
                np.asarray(original.p, dtype=np.float64) + local_shift,
                np.asarray(original.q, dtype=np.float64),
            )
            self.audit["object_com_shift_mm"] = shift_mm
            self.audit["object_com_shift_vector_local_m"] = local_shift.tolist()
            self.audit["object_com_shift_direction_world"] = direction_world.tolist()
        self.applied = True
        self.audit["applied_at_E2"] = True

    def close(self) -> None:
        if self._component is not None and self._original_cmass_pose is not None:
            self._component.cmass_local_pose = self._original_cmass_pose
        self.stack.close()


def _simple_instant_share(estimate: Mapping[str, Any]) -> np.ndarray:
    return project_simplex2([estimate["rho_left"], estimate["rho_right"]])


def _route_targets(
    method: str,
    task: Any,
    targets: Mapping[str, Tuple[np.ndarray, np.ndarray]],
    estimate: Mapping[str, Any],
    frame: ObjectTaskFrame,
    transfer: EffectNullspaceTransfer1D,
    step: int,
    events: Mapping[str, int],
    donor: str,
    stateful: StatefulResponsibilityFilter,
    full_stateful: StatefulResponsibilityFilter,
    override_share: Optional[Sequence[float]],
    update_state: bool,
) -> tuple[Dict[str, Tuple[np.ndarray, np.ndarray]], Dict[str, Any]]:
    base_action = np.asarray(estimate["base_action"], dtype=np.float64)
    local_gain = np.asarray(estimate["local_gain"], dtype=np.float64)
    signed = classify_signed_responsibility(
        estimate["rho_left"], estimate["rho_right"], estimate["rho_joint"]
    )
    instant = _simple_instant_share(estimate)
    mode = "UNSET"

    if method == "C1":
        share = phase_weights(step, events["E3"], events["E5"], donor=donor)
        mode = "PHASE_ONLY_SMOOTH_BLEND"
    elif method == "C2":
        position = object_state(task)["pose"][:3]
        share = distance_weights(
            float(np.linalg.norm(_tcp_position(task, "left") - position)),
            float(np.linalg.norm(_tcp_position(task, "right") - position)),
        )
        mode = "DISTANCE_ROUTING"
    elif method == "C3":
        impulse = _contact_impulses(task)
        share = force_weights(impulse["left"], impulse["right"])
        mode = "CONTACT_IMPULSE_ROUTING"
    elif method == "C4":
        share = np.asarray([0.5, 0.5])
        mode = "CONSERVATION_ONLY"
    elif method == "C5":
        share = instant
        action = direct_scale_action(base_action, share)
        contribution = local_gain * action
        total = float(local_gain @ base_action)
        routed = {
            side: (value[0].copy(), value[1].copy()) for side, value in targets.items()
        }
        for index, side in enumerate(("left", "right")):
            correction = float(action[index] - base_action[index])
            if abs(correction) > 1e-12:
                delta, _ = task_direction_joint_delta(task, side, frame.e_parallel, correction)
                routed[side] = (routed[side][0] + delta, routed[side][1])
        return routed, {
            "mode": "DIRECT_RESPONSIBILITY_SCALE_NO_CONSERVATION",
            "base_action": base_action.tolist(),
            "routed_action": action.tolist(),
            "local_gain": local_gain.tolist(),
            "base_total_effect": total,
            "predicted_total_effect": float(contribution.sum()),
            "effect_error": float(contribution.sum() - total),
            "action_correction_ratio": float(np.linalg.norm(action - base_action) / max(np.linalg.norm(base_action), 5e-4)),
            "target_share": share.tolist(),
            "signed_responsibility": signed.as_dict(),
            "feasible": True,
        }
    elif method == "C6":
        share = instant
        mode = "INSTANTANEOUS_RESPONSIBILITY"
    elif method == "C7":
        share = stateful.update(instant) if update_state else stateful.value
        mode = "STATEFUL_RESPONSIBILITY"
    elif method == "C8":
        share = instant[::-1]
        mode = "LEFT_RIGHT_SWAPPED_RESPONSIBILITY"
    elif method in {"C9", "C10"}:
        if override_share is None:
            raise ValueError(f"{method} requires an oracle control trace")
        share = project_simplex2(override_share)
        mode = "EPISODE_SHUFFLED_RESPONSIBILITY" if method == "C9" else "TIME_SHIFTED_RESPONSIBILITY"
    elif method == "C13":
        share = (
            full_stateful.update(signed.target_share)
            if update_state
            else full_stateful.value
        )
        mode = f"FULL_{signed.mode}_STATEFUL"
    else:
        share = instant
        mode = "OPERATOR_NULL"

    result = transfer.solve(
        base_action,
        local_gain,
        share,
        contact_ok=all(gripper_object_contacts(task).values()),
        support_height_m=float(object_state(task)["pose"][2]),
    )
    routed = {
        side: (value[0].copy(), value[1].copy()) for side, value in targets.items()
    }
    for index, side in enumerate(("left", "right")):
        correction = float(result.action[index] - base_action[index])
        if abs(correction) > 1e-12:
            delta, _ = task_direction_joint_delta(task, side, frame.e_parallel, correction)
            routed[side] = (routed[side][0] + delta, routed[side][1])
    audit = result.as_dict()
    audit.update(
        {
            "mode": mode,
            "base_action": base_action.tolist(),
            "routed_action": result.action.tolist(),
            "local_gain": local_gain.tolist(),
            "target_share": np.asarray(share).tolist(),
            "instant_share": instant.tolist(),
            "signed_responsibility": signed.as_dict(),
        }
    )
    return routed, audit


class ReplayRecorder:
    def __init__(self, task: Any, donor: str, events: Mapping[str, int], physics_hz: float = 250.0) -> None:
        self.task = task
        self.donor = donor
        self.receiver = "right" if donor == "left" else "left"
        self.events = events
        self.physics_hz = float(physics_hz)
        self.detector = HandoverEventDetector(donor)
        state = object_state(task)
        self.start_position = state["pose"][:3].copy()
        self.start_relative: Optional[Dict[str, np.ndarray]] = None
        self.positions = []
        self.quaternions = []
        self.linear = []
        self.angular = []
        self.tcp = {"left": [], "right": []}
        self.contacts = []
        self.grippers = []
        self.impulses = []
        self.receiver_only_streak = 0
        self.max_receiver_only_streak = 0
        self.premature_release = False

    def record(self, step: int, donor_open_command: bool) -> None:
        state = object_state(self.task)
        contacts = gripper_object_contacts(self.task)
        impulse = _contact_impulses(self.task)
        if step == self.events["E2"]:
            self.start_position = state["pose"][:3].copy()
            self.start_relative = {
                side: self.start_position - _tcp_position(self.task, side)
                for side in ("left", "right")
            }
        self.positions.append(state["pose"][:3].copy())
        self.quaternions.append(state["pose"][3:].copy())
        self.linear.append(state["linear_velocity"].copy())
        self.angular.append(state["angular_velocity"].copy())
        for side in ("left", "right"):
            self.tcp[side].append(_tcp_position(self.task, side).copy())
        self.contacts.append([contacts["left"], contacts["right"]])
        self.grippers.append(
            [self.task.robot.get_left_gripper_val(), self.task.robot.get_right_gripper_val()]
        )
        self.impulses.append([impulse["left"], impulse["right"]])
        self.receiver_only_streak = (
            self.receiver_only_streak + 1
            if contacts[self.receiver] and not contacts[self.donor]
            else 0
        )
        self.max_receiver_only_streak = max(
            self.max_receiver_only_streak, self.receiver_only_streak
        )
        donor_value = self.task.robot.get_left_gripper_val() if self.donor == "left" else self.task.robot.get_right_gripper_val()
        self.premature_release |= bool(
            step >= self.events["E2"]
            and donor_value > 0.2
            and not contacts[self.receiver]
        )
        self.detector.update(
            {
                "step": step,
                "time_s": step / self.physics_hz,
                "left_contact": contacts["left"],
                "right_contact": contacts["right"],
                "donor_open_command": donor_open_command,
            }
        )

    def finish(self, task_success: bool) -> tuple[Dict[str, Any], Dict[str, np.ndarray]]:
        position = np.asarray(self.positions)
        linear = np.asarray(self.linear)
        angular = np.asarray(self.angular)
        contacts = np.asarray(self.contacts, dtype=bool)
        tcp = {side: np.asarray(value) for side, value in self.tcp.items()}
        if self.start_relative is None:
            raise RuntimeError("replay never reached the frozen E2 anchor")
        slip = {
            side: np.linalg.norm(
                (position - tcp[side]) - self.start_relative[side], axis=1
            )
            for side in ("left", "right")
        }
        window_start = int(self.events["E2"])
        window = slice(window_start, None)
        masked = {
            "left": slip["left"][window][contacts[window, 0]],
            "right": slip["right"][window][contacts[window, 1]],
        }
        window_linear = linear[window]
        window_angular = angular[window]
        window_position = position[window]
        jerk = (
            np.diff(window_linear, axis=0) * self.physics_hz
            if len(window_linear) > 1
            else np.zeros((0, 3))
        )
        impulses = np.asarray(self.impulses)
        donor_index = 0 if self.donor == "left" else 1
        post_e5 = impulses[self.events["E5"] :, donor_index] if len(impulses) > self.events["E5"] else np.zeros(0)
        metrics = {
            "success": bool(task_success),
            "handover_completion": self.max_receiver_only_streak >= 15,
            "drop": bool(np.any(window_position[:, 2] < 0.78)),
            "premature_release": bool(self.premature_release),
            "receiver_takeover_failure": self.max_receiver_only_streak < 15,
            "peak_object_angular_velocity": float(np.linalg.norm(window_angular, axis=1).max(initial=0.0)),
            "peak_object_linear_jerk": float(np.linalg.norm(jerk, axis=1).max(initial=0.0)),
            "peak_relative_slip_m": float(max(masked["left"].max(initial=0.0), masked["right"].max(initial=0.0))),
            "peak_unmasked_relative_separation_m": float(max(slip["left"][window].max(initial=0.0), slip["right"][window].max(initial=0.0))),
            "min_object_height_m": float(window_position[:, 2].min(initial=np.inf)),
            "final_object_displacement_m": float(
                np.linalg.norm(window_position[-1] - window_position[0])
            ),
            "final_object_position_x_m": float(window_position[-1, 0]),
            "final_object_position_y_m": float(window_position[-1, 1]),
            "final_object_position_z_m": float(window_position[-1, 2]),
            "donor_residual_influence_impulse_sum": float(post_e5.sum()),
            "actual_event_audit": self.detector.audit(),
            "trace_steps": len(position),
        }
        trace = {
            "object_position": position,
            "object_quaternion_wxyz": np.asarray(self.quaternions),
            "object_linear_velocity": linear,
            "object_angular_velocity": angular,
            "left_tcp_position": tcp["left"],
            "right_tcp_position": tcp["right"],
            "contacts": contacts,
            "grippers": np.asarray(self.grippers),
            "contact_impulses": impulses,
        }
        return metrics, trace


def run_replay_cell(
    *,
    robotwin_root: Path,
    config: Mapping[str, Any],
    tape: ExpertTape,
    tape_meta: Mapping[str, Any],
    method: str,
    condition_name: str,
    condition: Mapping[str, Any],
    output: Path,
    replicate: int,
    oracle_control: Optional[Mapping[str, Any]],
    planner: str,
) -> Dict[str, Any]:
    seed = int(tape_meta["seed"])
    episode = int(tape_meta["episode"])
    donor = str(tape_meta["donor"])
    receiver = str(tape_meta["receiver"])
    events = {name: int(value) for name, value in tape_meta["events"].items()}
    if events["E2"] >= len(tape) or events["E5"] >= len(tape):
        raise ValueError("event anchors lie outside the full tape")
    if method not in BASE_METHODS | ORACLE_METHODS:
        raise ValueError(f"unknown replay method {method}")

    task = None
    oracle_task = None
    started = time.perf_counter()
    operator_logs = []
    oracle_trace = []
    branch_rollouts = 0
    branch_steps = 0
    estimator_wall = 0.0
    solver_wall = 0.0
    prefix = None
    condition_override = None
    oracle_condition_override = None
    try:
        task, task_args = build_handover_block(str(robotwin_root), planner=planner)
        task.setup_demo(now_ep_num=episode, seed=seed, **task_args)
        frame = ObjectTaskFrame.from_task(task)
        condition_override = ConditionOverride(task, receiver, condition, frame)
        if method in ORACLE_METHODS:
            oracle_task, oracle_task_args = build_handover_block(
                str(robotwin_root), planner=planner
            )
            oracle_task.setup_demo(
                now_ep_num=episode, seed=seed, **oracle_task_args
            )
            oracle_condition_override = ConditionOverride(
                oracle_task, receiver, condition, frame
            )
        recorder = ReplayRecorder(task, donor, events)
        estimator = SimulatorLocalEffectEstimator(
            int(config["operator"]["oracle_horizon_steps"]),
            float(config["operator"]["finite_difference_delta_m"]),
        )
        transfer = EffectNullspaceTransfer1D(
            eta=float(config["operator"]["selected_eta"]),
            relative_trust_region=float(config["operator"]["relative_trust_region"]),
            action_floor_m=float(config["operator"]["action_floor_m"]),
            action_bound_m=float(config["operator"]["scalar_action_bound_m"]),
            effect_relative_tolerance=float(config["operator"]["effect_relative_tolerance"]),
        )
        stateful = StatefulResponsibilityFilter(
            beta=float(config["responsibility_control"]["stateful_beta"]),
            max_share_change=float(config["responsibility_control"]["max_share_change_per_refresh"]),
        )
        full_stateful = StatefulResponsibilityFilter(
            beta=float(config["responsibility_control"]["stateful_beta"]),
            max_share_change=float(config["responsibility_control"]["max_share_change_per_refresh"]),
        )
        guard = ResponsibilityReleaseGuard(
            receiver_contact_stable_steps=int(config["release_guard"]["receiver_contact_stable_steps"]),
            min_receiver_responsibility=float(config["release_guard"]["min_receiver_responsibility"]),
            max_predicted_slip_m=float(config["release_guard"]["max_predicted_slip_m"]),
        )
        delay_queue: deque = deque()
        initial_receiver = (
            np.asarray(
                [joint.get_drive_target()[0] for joint in (task.robot.left_arm_joints if receiver == "left" else task.robot.right_arm_joints)],
                dtype=np.float64,
            ),
            np.asarray(
                [joint.get_drive_velocity_target()[0] for joint in (task.robot.left_arm_joints if receiver == "left" else task.robot.right_arm_joints)],
                dtype=np.float64,
            ),
        )
        shifted_donor = _shift_release_commands(
            tape, donor, int(condition.get("donor_release_advance_steps", 0))
        )
        latest_estimate = None
        soft_profile = None
        override_by_step = {}
        override_sequence = []
        oracle_control_metadata = None
        if oracle_control is not None:
            override_by_step = {
                int(item["step"]): item["target_share"]
                for item in oracle_control.get("oracle_trace", oracle_control.get("trace", []))
            }
            override_sequence = list(oracle_control.get("share_sequence", []))
            oracle_control_metadata = {
                key: value
                for key, value in oracle_control.items()
                if key not in {"oracle_trace", "trace", "share_sequence"}
            }
        refresh_stride = int(config["operator"]["oracle_refresh_stride"])
        last_override = None
        release_guard_request_steps = 0
        release_guard_blocked_steps = 0

        for index in range(len(tape)):
            item = tape.item(index)
            step = int(item["step"])
            active = events["E2"] <= step <= events["E5"]
            if step == events["E2"]:
                prefix = _prefix_fingerprint(task, step - 1)
                condition_override.apply()
                if oracle_condition_override is not None:
                    oracle_condition_override.apply()
                arm_joints = (
                    task.robot.left_arm_joints
                    if receiver == "left"
                    else task.robot.right_arm_joints
                )
                initial_receiver = (
                    np.asarray(
                        [joint.get_drive_target()[0] for joint in arm_joints],
                        dtype=np.float64,
                    ),
                    np.asarray(
                        [joint.get_drive_velocity_target()[0] for joint in arm_joints],
                        dtype=np.float64,
                    ),
                )
                gamma = condition.get("hidden_authority_gamma")
                soft_arm = condition.get("soft_arm", receiver)
                if gamma is not None:
                    soft_profile = SoftExpertAuthorityProfile(
                        task, str(soft_arm), float(gamma), frame
                    )
            targets = _condition_targets(
                task,
                item,
                receiver,
                condition,
                delay_queue,
                initial_receiver,
                active,
            )
            if active and float(condition.get("receiver_grasp_offset_mm", 0.0)):
                offset = float(condition["receiver_grasp_offset_mm"]) / 1000.0
                delta, _ = task_direction_joint_delta(
                    task, receiver, frame.e_perp, offset
                )
                targets[receiver] = (
                    targets[receiver][0] + delta,
                    targets[receiver][1],
                )
            if active and soft_profile is not None:
                targets[soft_profile.soft_arm], soft_audit = soft_profile.blend(
                    targets[soft_profile.soft_arm]
                )
            else:
                soft_audit = None

            estimate_refreshed = False
            if method in ORACLE_METHODS and active and (step - events["E2"]) % refresh_stride == 0:
                estimate_started = time.perf_counter()
                # The simulator oracle is evaluated in a disjoint SAPIEN
                # scene.  Snapshot/restore therefore cannot mutate the main
                # closed-loop PhysX warm-start cache.  Only explicit state is
                # copied from main to the sandbox; nothing is copied back.
                SapienSnapshot.restore(
                    oracle_task, SapienSnapshot.capture(task)
                )
                latest_estimate = estimator.estimate(
                    oracle_task, targets["left"], targets["right"], frame
                )
                estimator_wall += time.perf_counter() - estimate_started
                branch_rollouts += int(latest_estimate["branch_rollout_count"])
                branch_steps += int(latest_estimate["simulated_physics_steps"])
                estimate_refreshed = True
                signed = classify_signed_responsibility(
                    latest_estimate["rho_left"],
                    latest_estimate["rho_right"],
                    latest_estimate["rho_joint"],
                    joint_threshold=float(config["responsibility_control"]["joint_threshold"]),
                    harmful_threshold=float(config["responsibility_control"]["harmful_threshold"]),
                    joint_differential_scale=float(config["responsibility_control"]["joint_differential_scale"]),
                    temperature=float(config["responsibility_control"]["temperature"]),
                )
                instant_share = _simple_instant_share(latest_estimate)
                oracle_trace.append(
                    {
                        "step": step,
                        "e2_relative_step": step - events["E2"],
                        "normalized_phase": float(
                            (step - events["E2"])
                            / max(events["E5"] - events["E2"], 1)
                        ),
                        "rho_left": latest_estimate["rho_left"],
                        "rho_right": latest_estimate["rho_right"],
                        "rho_joint": latest_estimate["rho_joint"],
                        # C9/C10 are controls for the instantaneous C6 route.
                        # Keep signed control separately for C13 diagnostics.
                        "target_share": instant_share.tolist(),
                        "instant_share": instant_share.tolist(),
                        "signed_target_share": signed.target_share.tolist(),
                        "mode": signed.mode,
                    }
                )
                if override_sequence:
                    phase = float(
                        (step - events["E2"])
                        / max(events["E5"] - events["E2"], 1)
                    )
                    control_index = int(
                        np.clip(
                            round(phase * (len(override_sequence) - 1)),
                            0,
                            len(override_sequence) - 1,
                        )
                    )
                    last_override = override_sequence[control_index]
                elif step in override_by_step:
                    last_override = override_by_step[step]

            route_audit = None
            if active and latest_estimate is not None and method not in NULL_METHODS | {"C12"}:
                solve_started = time.perf_counter()
                targets, route_audit = _route_targets(
                    method,
                    task,
                    targets,
                    latest_estimate,
                    frame,
                    transfer,
                    step,
                    events,
                    donor,
                    stateful,
                    full_stateful,
                    last_override,
                    estimate_refreshed,
                )
                solver_wall += time.perf_counter() - solve_started

            current_contacts = gripper_object_contacts(task)
            guard.update_contact(current_contacts[receiver])
            commands = {
                "left": item["left_gripper"],
                "right": item["right_gripper"],
            }
            donor_shift = shifted_donor[index]
            commands[donor] = None if np.isnan(donor_shift).all() else (float(donor_shift[0]), float(donor_shift[1]))
            guard_enabled = method in {"C12", "C13"}
            donor_command = commands[donor]
            if guard_enabled and donor_command is not None and donor_command[0] > 0.2:
                release_guard_request_steps += 1
                if latest_estimate is not None:
                    receiver_rho = latest_estimate["rho_left"] if receiver == "left" else latest_estimate["rho_right"]
                    receiver_index = 0 if receiver == "left" else 1
                    decision = guard.allow(
                        receiver_rho,
                        latest_estimate["outcomes"]["LR"]["contact_retention"][receiver_index],
                        latest_estimate["lr_max_slip_m"],
                        latest_estimate["lr_drop"],
                    )
                    if not decision["allow"]:
                        commands[donor] = None
                        release_guard_blocked_steps += 1

            before_position = object_state(task)["pose"][:3].copy()
            for side in ("left", "right"):
                task.robot.set_arm_joints(*targets[side], side)
                if commands[side] is not None:
                    task.robot.set_gripper(commands[side][0], side, commands[side][1])
            task.scene.step()
            donor_open = (
                commands[donor] is not None
                and commands[donor][0] > 0.2
            )
            recorder.record(step, donor_open)
            if route_audit is not None and estimate_refreshed:
                after_position = object_state(task)["pose"][:3]
                route_audit.update(
                    {
                        "step": step,
                        "realized_effect_one_step_m": float(
                            (after_position - before_position) @ np.asarray(frame.e_parallel)
                        ),
                        "soft_authority": soft_audit,
                    }
                )
                operator_logs.append(route_audit)

        task_success = bool(task.check_success())
        metrics, trace = recorder.finish(task_success)
        output.mkdir(parents=True, exist_ok=True)
        trace_path = output / "trace.npz"
        np.savez_compressed(trace_path, **trace)

        corrections = [float(item.get("action_correction_ratio", 0.0)) for item in operator_logs]
        effect_errors = [abs(float(item.get("effect_error", 0.0))) for item in operator_logs]
        modes = [str(item.get("mode", "UNKNOWN")) for item in operator_logs]
        shares = [np.asarray(item["target_share"], dtype=np.float64) for item in operator_logs if "target_share" in item]
        responsibility_tv = float(sum(np.abs(a - b).sum() for a, b in zip(shares, shares[1:]))) if len(shares) > 1 else 0.0
        result = {
            "status": "COMPLETE",
            "seed": seed,
            "episode": episode,
            "replicate": int(replicate),
            "method": method,
            "condition": condition_name,
            "condition_parameters": dict(condition),
            "donor": donor,
            "receiver": receiver,
            "reference_events": events,
            "prefix_fingerprint_at_E2_minus_1": prefix,
            "condition_override": condition_override.audit,
            "tape_sha256": tape_meta["tape_sha256"],
            "tape_steps": len(tape),
            "fresh_process": True,
            "scene_snapshot_used_for_prefix": False,
            "oracle_sandbox_separate_scene": method in ORACLE_METHODS,
            "oracle_snapshot_restore_writes_main_scene": False,
            "oracle_trace": oracle_trace,
            "oracle_control_metadata": oracle_control_metadata,
            "operator_log": operator_logs,
            "operator_log_count": len(operator_logs),
            "median_action_correction_ratio": float(np.median(corrections)) if corrections else 0.0,
            "active_correction_over_5pct_rate": float(np.mean(np.asarray(corrections) > 0.05)) if corrections else 0.0,
            "max_predicted_effect_error_abs": float(max(effect_errors, default=0.0)),
            "responsibility_total_variation": responsibility_tv,
            "joint_mode_occupancy": float(np.mean(["JOINT_SUPPORT" in value for value in modes])) if modes else 0.0,
            "release_guard_request_steps": release_guard_request_steps,
            "release_guard_blocked_steps": release_guard_blocked_steps,
            "oracle_branch_count": branch_rollouts,
            "simulated_oracle_physics_steps": branch_steps,
            "estimator_wall_time_s": estimator_wall,
            "solver_wall_time_s": solver_wall,
            "total_replay_wall_time_s": time.perf_counter() - started,
            "trace_path": str(trace_path),
            "trace_sha256": sha256_file(trace_path),
            "metrics": metrics,
            "accepted": False,
            "pai_job_created": False,
        }
        write_json(output / "result.json", result)
        return result
    finally:
        if condition_override is not None:
            condition_override.close()
        if oracle_condition_override is not None:
            oracle_condition_override.close()
        if oracle_task is not None:
            try:
                oracle_task.close_env(clear_cache=True)
            except Exception:
                pass
        if task is not None:
            try:
                task.close_env(clear_cache=True)
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--robotwin-root", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--tape", required=True)
    parser.add_argument("--tape-meta", required=True)
    parser.add_argument("--method", required=True)
    parser.add_argument("--condition-name", required=True)
    parser.add_argument("--condition-json", default="{}")
    parser.add_argument("--output", required=True)
    parser.add_argument("--replicate", type=int, default=0)
    parser.add_argument("--oracle-control")
    parser.add_argument("--planner", default="mplib_screw", choices=("mplib_screw", "mplib_RRT"))
    args = parser.parse_args()

    output = Path(args.output).resolve()
    if (output / "result.json").exists():
        raise FileExistsError(f"refusing to overwrite replay evidence: {output}")
    try:
        config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
        tape = ExpertTape.load(args.tape)
        tape_meta = json.loads(Path(args.tape_meta).read_text(encoding="utf-8"))
        condition = json.loads(args.condition_json)
        oracle_control = (
            json.loads(Path(args.oracle_control).read_text(encoding="utf-8"))
            if args.oracle_control
            else None
        )
        run_replay_cell(
            robotwin_root=Path(args.robotwin_root).resolve(),
            config=config,
            tape=tape,
            tape_meta=tape_meta,
            method=args.method,
            condition_name=args.condition_name,
            condition=condition,
            output=output,
            replicate=args.replicate,
            oracle_control=oracle_control,
            planner=args.planner,
        )
        return 0
    except Exception as exc:
        write_json(
            output / "failure.json",
            {
                "status": "FAILED",
                "method": args.method,
                "condition": args.condition_name,
                "replicate": args.replicate,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "accepted": False,
            },
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
