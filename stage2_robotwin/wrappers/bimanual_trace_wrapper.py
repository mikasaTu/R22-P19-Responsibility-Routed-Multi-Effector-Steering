"""Per-physics-step trace adapter for RoboTwin expert trajectories."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from types import MethodType
from typing import Any, Dict, List, Mapping, Optional, Tuple

import cv2
import imageio.v2 as imageio
import numpy as np

from .counterfactual_brancher import deterministic_hold_replay
from .event_detector import HandoverEventDetector


@dataclass
class SidePerturbation:
    gain: float = 1.0
    delay_steps: int = 0
    friction_scale: float = 1.0


class BimanualTraceWrapper:
    def __init__(
        self,
        task: Any,
        output_dir: Path,
        episode_index: int,
        seed: int,
        stable_steps: int = 15,
        video_stride: int = 25,
        replay_horizon: int = 10,
        branch_auditor: Optional[Any] = None,
    ) -> None:
        self.task = task
        self.output_dir = Path(output_dir)
        self.episode_index = int(episode_index)
        self.seed = int(seed)
        self.video_stride = int(video_stride)
        self.replay_horizon = int(replay_horizon)
        self.branch_auditor = branch_auditor
        self.branch_records: List[Dict[str, Any]] = []
        self.trace: List[Dict[str, Any]] = []
        self.frames: List[np.ndarray] = []
        self.step = 0
        self.left = SidePerturbation()
        self.right = SidePerturbation()
        self._delay = {"left": deque(), "right": deque()}
        self._last_target: Dict[str, Optional[np.ndarray]] = {
            "left": None,
            "right": None,
        }
        self._friction_originals: List[Tuple[Any, Any]] = []
        self._donor_open_pending = False
        self.determinism: Optional[Dict[str, Any]] = None
        initial_x = float(task.box.get_pose().p[0])
        self.donor = "left" if initial_x < 0 else "right"
        self.receiver = "right" if self.donor == "left" else "left"
        self.detector = HandoverEventDetector(self.donor, stable_steps=stable_steps)
        self.object_id = int(task.box.actor.per_scene_id)
        self.left_links = {
            joint[0].child_link.get_name() for joint in task.robot.left_gripper
        }
        self.right_links = {
            joint[0].child_link.get_name() for joint in task.robot.right_gripper
        }
        self._install()

    def _install(self) -> None:
        wrapper = self

        def traced_take_dense_action(task_self: Any, control_seq: Mapping[str, Any], save_freq: int = -1) -> bool:
            return wrapper.take_dense_action(control_seq)

        self.task.take_dense_action = MethodType(traced_take_dense_action, self.task)

    @staticmethod
    def _dynamic_state(actor: Any) -> Tuple[np.ndarray, np.ndarray]:
        import sapien

        component = actor.find_component_by_type(
            sapien.physx.PhysxRigidDynamicComponent
        )
        return (
            np.asarray(component.linear_velocity, dtype=np.float64),
            np.asarray(component.angular_velocity, dtype=np.float64),
        )

    def _object_contacts(self) -> Dict[str, Any]:
        pairs = []
        left_count = right_count = 0
        left_impulse = right_impulse = 0.0
        for contact in self.task.scene.get_contacts():
            first = contact.bodies[0].entity
            second = contact.bodies[1].entity
            if int(first.per_scene_id) != self.object_id and int(second.per_scene_id) != self.object_id:
                continue
            other = second if int(first.per_scene_id) == self.object_id else first
            impulse = float(
                sum(np.linalg.norm(np.asarray(point.impulse)) for point in contact.points)
            )
            pairs.append(
                {
                    "object_id": self.object_id,
                    "other_id": int(other.per_scene_id),
                    "other_name": other.name,
                    "point_count": len(contact.points),
                    "impulse_norm_sum": impulse,
                }
            )
            if other.name in self.left_links:
                left_count += len(contact.points)
                left_impulse += impulse
            if other.name in self.right_links:
                right_count += len(contact.points)
                right_impulse += impulse
        return {
            "left_contact": left_count > 0,
            "right_contact": right_count > 0,
            "left_contact_points": left_count,
            "right_contact_points": right_count,
            "left_impulse": left_impulse,
            "right_impulse": right_impulse,
            "contact_pairs": pairs,
        }

    def _sample(self) -> Dict[str, Any]:
        pose = self.task.box.get_pose()
        linear, angular = self._dynamic_state(self.task.box.actor)
        contact = self._object_contacts()
        sample: Dict[str, Any] = {
            "episode": self.episode_index,
            "seed": self.seed,
            "step": self.step,
            "time_s": self.step / 250.0,
            "object_position": np.asarray(pose.p).tolist(),
            "object_quaternion_wxyz": np.asarray(pose.q).tolist(),
            "object_linear_velocity": linear.tolist(),
            "object_angular_velocity": angular.tolist(),
            "left_tcp_pose": list(self.task.robot.get_left_tcp_pose()),
            "right_tcp_pose": list(self.task.robot.get_right_tcp_pose()),
            "left_gripper_command": float(self.task.robot.get_left_gripper_val()),
            "right_gripper_command": float(self.task.robot.get_right_gripper_val()),
            "donor_open_command": self._donor_open_pending,
            **contact,
        }
        self._donor_open_pending = False
        self.detector.update(sample)
        sample["event_labels"] = [
            name
            for name, event in self.detector.events.items()
            if event["step"] == self.step
        ]
        return sample

    def _capture_frame(self, sample: Mapping[str, Any]) -> None:
        self.task._update_render()
        image = self.task.cameras.get_observer_rgb()
        image = np.ascontiguousarray(image.copy())
        line = (
            f"ep={self.episode_index} seed={self.seed} step={self.step} "
            f"L={int(sample['left_contact'])} R={int(sample['right_contact'])} "
            f"events={','.join(sample['event_labels']) or '-'}"
        )
        cv2.putText(
            image,
            line,
            (6, 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.36,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        self.frames.append(image)

    def _after_step(self) -> None:
        sample = self._sample()
        self.trace.append(sample)
        if self.step % self.video_stride == 0 or sample["event_labels"]:
            self._capture_frame(sample)
        if self.determinism is None and "E3" in self.detector.events:
            self.determinism = deterministic_hold_replay(
                self.task, horizon=self.replay_horizon
            )
            self.determinism["snapshot_event"] = "E3"
            self.determinism["snapshot_step"] = self.step
        self.step += 1

    def _arm_target(
        self,
        side: str,
        arm_result: Optional[Mapping[str, Any]],
        control_idx: int,
    ) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        if arm_result is None or control_idx >= arm_result["position"].shape[0]:
            return None
        perturb = self.left if side == "left" else self.right
        target = np.asarray(arm_result["position"][control_idx], dtype=np.float64)
        velocity = np.asarray(arm_result["velocity"][control_idx], dtype=np.float64)
        if self._last_target[side] is None:
            current = (
                self.task.robot.get_left_arm_real_jointState()
                if side == "left"
                else self.task.robot.get_right_arm_real_jointState()
            )
            self._last_target[side] = np.asarray(current[:-1], dtype=np.float64)
        base = self._last_target[side]
        gained = base + perturb.gain * (target - base)
        self._last_target[side] = gained
        queue = self._delay[side]
        queue.append((gained, perturb.gain * velocity))
        if len(queue) <= perturb.delay_steps:
            return base.copy(), np.zeros_like(velocity)
        return queue.popleft()

    def take_dense_action(self, control_seq: Mapping[str, Any]) -> bool:
        left_arm = control_seq["left_arm"]
        left_gripper = control_seq["left_gripper"]
        right_arm = control_seq["right_arm"]
        right_gripper = control_seq["right_gripper"]
        max_control_len = 0
        for arm in (left_arm, right_arm):
            if arm is not None:
                max_control_len = max(max_control_len, arm["position"].shape[0])
        for gripper in (left_gripper, right_gripper):
            if gripper is not None:
                max_control_len = max(max_control_len, int(gripper["num_step"]))

        donor_gripper = left_gripper if self.donor == "left" else right_gripper
        if donor_gripper is not None:
            values = np.asarray(donor_gripper["result"])
            current = (
                self.task.robot.get_left_gripper_val()
                if self.donor == "left"
                else self.task.robot.get_right_gripper_val()
            )
            if len(values) and values[-1] > 0.8 and current < 0.3:
                self._donor_open_pending = True

        for control_idx in range(max_control_len):
            if self.branch_auditor is not None and self.branch_auditor.should_sample(
                self.step, self.detector.events
            ):
                self.branch_records.extend(
                    self.branch_auditor.evaluate(
                        self.task,
                        self.step,
                        control_seq,
                        control_idx,
                        tuple(self.detector.events),
                    )
                )
            left_target = self._arm_target("left", left_arm, control_idx)
            right_target = self._arm_target("right", right_arm, control_idx)
            if left_target is not None:
                self.task.robot.set_arm_joints(*left_target, "left")
            if right_target is not None:
                self.task.robot.set_arm_joints(*right_target, "right")
            if left_gripper is not None and control_idx < left_gripper["num_step"]:
                self.task.robot.set_gripper(
                    left_gripper["result"][control_idx],
                    "left",
                    left_gripper["per_step"],
                )
            if right_gripper is not None and control_idx < right_gripper["num_step"]:
                self.task.robot.set_gripper(
                    right_gripper["result"][control_idx],
                    "right",
                    right_gripper["per_step"],
                )
            self.task.scene.step()
            self._after_step()
        return True

    def set_unilateral_friction(self, side: str, scale: float) -> int:
        if side not in {"left", "right"} or scale <= 0:
            raise ValueError("side must be left/right and scale must be positive")
        self.restore_friction()
        joints = self.task.robot.left_gripper if side == "left" else self.task.robot.right_gripper
        changed = 0
        for joint, _, _ in joints:
            link = joint.child_link
            for shape in link.collision_shapes:
                original = shape.physical_material
                replacement = self.task.scene.create_physical_material(
                    float(original.static_friction) * scale,
                    float(original.dynamic_friction) * scale,
                    float(original.restitution),
                )
                self._friction_originals.append((shape, original))
                shape.physical_material = replacement
                changed += 1
        return changed

    def restore_friction(self) -> None:
        for shape, material in self._friction_originals:
            shape.physical_material = material
        self._friction_originals.clear()

    def capability_audit(self) -> Dict[str, Any]:
        old_gain, old_delay = self.left.gain, self.right.delay_steps
        self.left.gain = 1.3
        self.right.delay_steps = 2
        friction_shapes = self.set_unilateral_friction("left", 0.7)
        self.restore_friction()
        result = {
            "unilateral_gain": self.left.gain == 1.3,
            "unilateral_delay": self.right.delay_steps == 2,
            "unilateral_friction": friction_shapes > 0,
            "left_friction_shapes_tested": friction_shapes,
        }
        self.left.gain, self.right.delay_steps = old_gain, old_delay
        return result

    def finish(self) -> Dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        video_path = self.output_dir / (
            f"episode_{self.episode_index:02d}_seed_{self.seed:04d}.mp4"
        )
        if self.frames:
            imageio.mimsave(video_path, self.frames, fps=10, macro_block_size=1)
        return {
            "episode": self.episode_index,
            "seed": self.seed,
            "donor": self.donor,
            "receiver": self.receiver,
            "steps": len(self.trace),
            "event_audit": self.detector.audit(),
            "determinism": self.determinism,
            "video": str(video_path),
            "contact_actor_ids_readable": any(
                bool(sample["contact_pairs"]) for sample in self.trace
            ),
            "oracle_branch_record_count": len(self.branch_records),
        }
