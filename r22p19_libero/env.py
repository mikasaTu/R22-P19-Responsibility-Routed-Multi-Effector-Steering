"""Deterministic LIBERO state restoration and counterfactual branching."""

from __future__ import annotations

import hashlib
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

import h5py
import numpy as np

from .config import TaskSpec


def quaternion_angle_wxyz(left: np.ndarray, right: np.ndarray) -> float:
    a = np.asarray(left, dtype=np.float64)
    b = np.asarray(right, dtype=np.float64)
    a = a / max(float(np.linalg.norm(a)), 1e-12)
    b = b / max(float(np.linalg.norm(b)), 1e-12)
    dot = float(np.clip(abs(np.dot(a, b)), 0.0, 1.0))
    return float(2.0 * math.acos(dot))


def _json_vector(value: np.ndarray) -> List[float]:
    array = np.asarray(value, dtype=np.float64)
    if not np.isfinite(array).all():
        raise FloatingPointError("non-finite simulator vector")
    return [float(item) for item in array.reshape(-1)]


@dataclass(frozen=True)
class ObjectState:
    position: np.ndarray
    quaternion: np.ndarray
    linear_velocity: np.ndarray
    angular_velocity: np.ndarray
    wrench_world_torque_force: np.ndarray

    def as_json(self) -> Dict[str, List[float]]:
        return {
            "position": _json_vector(self.position),
            "quaternion_wxyz": _json_vector(self.quaternion),
            "linear_velocity": _json_vector(self.linear_velocity),
            "angular_velocity": _json_vector(self.angular_velocity),
            "wrench_world_torque_force": _json_vector(self.wrench_world_torque_force),
        }


class LiberoBranchEnv:
    """A task-bound LIBERO environment with explicit hidden-state repair.

    LIBERO HDF5 states contain flattened MuJoCo data, but per-demonstration
    fixture placements live in the compiled model XML. Robosuite also keeps
    controller and gripper targets in Python objects. Every restore repairs
    all three layers before a branch is stepped.
    """

    def __init__(
        self,
        task: TaskSpec,
        libero_root: Path,
        seed: int = 2219,
        render: bool = False,
        render_device: int = -1,
    ) -> None:
        from libero.libero.envs.env_wrapper import ControlEnv

        np.random.seed(seed)
        self.task = task
        self.libero_root = Path(libero_root)
        self.dataset_path = task.dataset_path
        self.render_enabled = bool(render)
        self.env = ControlEnv(
            bddl_file_name=str(task.bddl_path(self.libero_root)),
            use_camera_obs=bool(render),
            has_renderer=False,
            has_offscreen_renderer=bool(render),
            render_gpu_device_id=int(render_device),
            camera_names=["agentview", "robot0_eye_in_hand"],
            camera_heights=128,
            camera_widths=128,
            ignore_done=True,
            horizon=1000,
            control_freq=20,
            hard_reset=False,
        )
        self.env.seed(seed)
        self.env.reset()
        self.object_body_id = self.env.sim.model.body_name2id(task.object_body)
        self.target_body_id = (
            self.env.sim.model.body_name2id(task.target_body)
            if task.target_body is not None
            else None
        )
        object_prefix = task.object_body.rsplit("_main", 1)[0]
        self.object_geom_ids = self._matching_geom_ids((object_prefix,))
        if not self.object_geom_ids:
            raise RuntimeError("no object geoms matched %s" % object_prefix)
        self.target_geom_ids: Set[int] = set()
        if task.target_body is not None:
            target_prefix = task.target_body.rsplit("_main", 1)[0]
            self.target_geom_ids = self._matching_geom_ids((target_prefix,))
        self.gripper_geom_ids = self._gripper_geom_ids()
        self.left_finger_geom_ids = self._named_geom_ids(("finger1", "left_finger"))
        self.right_finger_geom_ids = self._named_geom_ids(("finger2", "right_finger"))
        self._body_name_to_id = {
            (self.env.sim.model.body_id2name(body_id) or ""): body_id
            for body_id in range(self.env.sim.model.nbody)
        }
        self._base_body_pos = np.asarray(self.env.sim.model.body_pos, dtype=np.float64).copy()
        self._base_body_quat = np.asarray(self.env.sim.model.body_quat, dtype=np.float64).copy()
        self._demo_model_cache: Dict[int, Dict[str, Any]] = {}

    def _matching_geom_ids(self, prefixes: Sequence[str]) -> Set[int]:
        result: Set[int] = set()
        for geom_id in range(self.env.sim.model.ngeom):
            name = self.env.sim.model.geom_id2name(geom_id) or ""
            if any(name.startswith(prefix) for prefix in prefixes):
                result.add(geom_id)
        return result

    def _named_geom_ids(self, tokens: Sequence[str]) -> Set[int]:
        result: Set[int] = set()
        for geom_id in range(self.env.sim.model.ngeom):
            name = (self.env.sim.model.geom_id2name(geom_id) or "").lower()
            if any(token in name for token in tokens):
                result.add(geom_id)
        return result

    def _gripper_geom_ids(self) -> Set[int]:
        result: Set[int] = set()
        geom_bodyid = self.env.sim.model._model.geom_bodyid
        for geom_id in range(self.env.sim.model.ngeom):
            body_id = int(geom_bodyid[geom_id])
            body_name = (self.env.sim.model.body_id2name(body_id) or "").lower()
            geom_name = (self.env.sim.model.geom_id2name(geom_id) or "").lower()
            if any(token in (body_name + " " + geom_name) for token in ("gripper", "finger")):
                result.add(geom_id)
        return result

    def _demo_model_contract(self, demo_id: int) -> Dict[str, Any]:
        cached = self._demo_model_cache.get(int(demo_id))
        if cached is not None:
            return cached
        with h5py.File(str(self.dataset_path), "r") as handle:
            value = handle["data/demo_%d" % int(demo_id)].attrs["model_file"]
        model_xml = value.decode("utf-8") if isinstance(value, bytes) else str(value)
        body_pos = self._base_body_pos.copy()
        body_quat = self._base_body_quat.copy()
        matched = 0
        for element in ET.fromstring(model_xml).iter("body"):
            name = element.get("name")
            if not name or name not in self._body_name_to_id:
                continue
            body_id = self._body_name_to_id[name]
            if element.get("pos") is not None:
                position = np.fromstring(element.get("pos", ""), sep=" ", dtype=np.float64)
                if position.shape != (3,):
                    raise RuntimeError("invalid model body position for %s" % name)
                body_pos[body_id] = position
            if element.get("quat") is not None:
                quaternion = np.fromstring(element.get("quat", ""), sep=" ", dtype=np.float64)
                if quaternion.shape != (4,):
                    raise RuntimeError("invalid model body quaternion for %s" % name)
                body_quat[body_id] = quaternion
            matched += 1
        if matched == 0:
            raise RuntimeError("demonstration XML matched no runtime bodies")
        contract = {
            "model_file_sha256": hashlib.sha256(model_xml.encode("utf-8")).hexdigest(),
            "body_pos": body_pos,
            "body_quat": body_quat,
            "matched_named_bodies": matched,
        }
        self._demo_model_cache[int(demo_id)] = contract
        return contract

    def demo_model_sha256(self, demo_id: int) -> str:
        return str(self._demo_model_contract(demo_id)["model_file_sha256"])

    def _restore_model_parameters(self, demo_id: int) -> None:
        contract = self._demo_model_contract(demo_id)
        np.copyto(self.env.sim.model.body_pos, contract["body_pos"])
        np.copyto(self.env.sim.model.body_quat, contract["body_quat"])

    def _recover_gripper_target(self, robot: Any) -> None:
        if not robot.has_gripper or not hasattr(robot.gripper, "current_action"):
            return
        qpos_indexes = np.asarray(robot._ref_gripper_joint_pos_indexes, dtype=np.int64)
        actuator_ids = np.asarray(
            [self.env.sim.model.actuator_name2id(name) for name in robot.gripper.actuators],
            dtype=np.int64,
        )
        control_range = np.asarray(self.env.sim.model.actuator_ctrlrange[actuator_ids], dtype=np.float64)
        bias = 0.5 * (control_range[:, 1] + control_range[:, 0])
        weight = 0.5 * (control_range[:, 1] - control_range[:, 0])
        # HDF5 stores MuJoCo qpos/qvel but not PandaGripper.current_action.
        # Make that missing state a declared intervention: zero gripper action
        # holds the restored closure, identically in every branch.
        positions = np.asarray(self.env.sim.data.qpos[qpos_indexes], dtype=np.float64)
        normalized = np.clip(
            (positions - bias) / np.maximum(weight, 1e-12), -1.0, 1.0
        )
        robot.gripper.current_action = normalized.copy()
        self.env.sim.data.ctrl[actuator_ids] = positions

    def _synchronize_python_state(self) -> None:
        runtime = self.env.env
        runtime.cur_time = 0
        runtime.timestep = 0
        runtime.done = False
        runtime._obs_cache = {}
        for observable in runtime._observables.values():
            observable.reset()
        for robot in self.env.robots:
            robot.controller.update_initial_joints(robot._joint_positions)
            robot.controller.torques = np.zeros_like(robot._joint_positions, dtype=np.float64)
            robot.torques = np.zeros_like(robot._joint_positions, dtype=np.float64)
            self._recover_gripper_target(robot)
            for name in (
                "recent_qpos",
                "recent_actions",
                "recent_torques",
                "recent_ee_forcetorques",
                "recent_ee_pose",
                "recent_ee_vel",
                "recent_ee_vel_buffer",
                "recent_ee_acc",
            ):
                buffer = getattr(robot, name, None)
                if buffer is not None and hasattr(buffer, "clear"):
                    buffer.clear()

    def set_state(self, state: np.ndarray, demo_id: int) -> Dict[str, np.ndarray]:
        value = np.asarray(state, dtype=np.float64)
        self.env.sim.reset()
        self._restore_model_parameters(int(demo_id))
        self.env.set_state(value)
        self.env.sim.forward()
        self._synchronize_python_state()
        self.env._post_process()
        self.env._update_observables(force=True)
        observation = self.env.env._get_observations()
        if not np.isfinite(self.env.get_sim_state()).all():
            raise FloatingPointError("non-finite restored simulator state")
        return observation

    def object_state(self) -> ObjectState:
        name = self.task.object_body
        wrench = np.asarray(self.env.sim.data.cfrc_ext[self.object_body_id], dtype=np.float64).copy()
        return ObjectState(
            position=np.asarray(self.env.sim.data.body_xpos[self.object_body_id], dtype=np.float64).copy(),
            quaternion=np.asarray(self.env.sim.data.body_xquat[self.object_body_id], dtype=np.float64).copy(),
            linear_velocity=np.asarray(self.env.sim.data.get_body_xvelp(name), dtype=np.float64).copy(),
            angular_velocity=np.asarray(self.env.sim.data.get_body_xvelr(name), dtype=np.float64).copy(),
            wrench_world_torque_force=wrench,
        )

    def eef_state(self) -> Dict[str, List[float]]:
        robot = self.env.robots[0]
        gripper_qpos = np.asarray(
            self.env.sim.data.qpos[
                np.asarray(robot._ref_gripper_joint_pos_indexes, dtype=np.int64)
            ],
            dtype=np.float64,
        )
        gripper_qvel = np.asarray(
            self.env.sim.data.qvel[
                np.asarray(robot._ref_gripper_joint_vel_indexes, dtype=np.int64)
            ],
            dtype=np.float64,
        )
        return {
            "position": _json_vector(robot.controller.ee_pos),
            "rotation_matrix": _json_vector(robot.controller.ee_ori_mat),
            "linear_velocity": _json_vector(robot.controller.ee_pos_vel),
            "angular_velocity": _json_vector(robot.controller.ee_ori_vel),
            "gripper_qpos": _json_vector(gripper_qpos),
            "gripper_qvel": _json_vector(gripper_qvel),
        }

    def contact_summary(self) -> Dict[str, Any]:
        object_gripper = False
        object_left = False
        object_right = False
        object_target = False
        contact_points: List[List[float]] = []
        normal_forces: List[float] = []
        for index in range(int(self.env.sim.data.ncon)):
            contact = self.env.sim.data.contact[index]
            first = int(contact.geom1)
            second = int(contact.geom2)
            pair = {first, second}
            if pair.intersection(self.object_geom_ids):
                if pair.intersection(self.gripper_geom_ids):
                    object_gripper = True
                    object_left = object_left or bool(pair.intersection(self.left_finger_geom_ids))
                    object_right = object_right or bool(pair.intersection(self.right_finger_geom_ids))
                    contact_points.append(_json_vector(np.asarray(contact.pos, dtype=np.float64)))
                    address = int(contact.efc_address)
                    if address >= 0 and address < len(self.env.sim.data.efc_force):
                        normal_forces.append(float(max(0.0, self.env.sim.data.efc_force[address])))
                if self.target_geom_ids and pair.intersection(self.target_geom_ids):
                    object_target = True
        return {
            "object_gripper": bool(object_gripper),
            "object_left_finger": bool(object_left),
            "object_right_finger": bool(object_right),
            "object_two_finger": bool(object_left and object_right),
            "object_target": bool(object_target),
            "contact_points_world": contact_points,
            "contact_normal_force_sum_sim_units": float(sum(normal_forces)),
            "contact_normal_force_max_sim_units": float(max(normal_forces) if normal_forces else 0.0),
            "force_units_calibrated": False,
        }

    def target_distance(self) -> float:
        if self.target_body_id is None:
            return 0.0
        object_position = np.asarray(self.env.sim.data.body_xpos[self.object_body_id], dtype=np.float64)
        target_position = np.asarray(self.env.sim.data.body_xpos[self.target_body_id], dtype=np.float64)
        return float(np.linalg.norm(object_position - target_position))

    def snapshot(self) -> Dict[str, Any]:
        return {
            "object": self.object_state().as_json(),
            "eef": self.eef_state(),
            "contact": self.contact_summary(),
            "target_distance": self.target_distance(),
            "success": bool(self.env.check_success()),
        }

    @staticmethod
    def _masked_action(
        action: np.ndarray,
        branch: str,
        group_a: Sequence[int],
        group_b: Sequence[int],
        gains: Tuple[float, float],
        keep_background: bool,
    ) -> np.ndarray:
        value = np.asarray(action, dtype=np.float64).copy()
        group_a_set = set(int(index) for index in group_a)
        group_b_set = set(int(index) for index in group_b)
        if group_a_set.intersection(group_b_set):
            raise ValueError("counterfactual action groups overlap")
        if branch not in ("AB", "A", "B", "ZERO"):
            raise ValueError("unknown branch: %s" % branch)
        if not keep_background:
            value[:] = 0.0
            source = np.asarray(action, dtype=np.float64)
            for index in group_a_set.union(group_b_set):
                value[index] = source[index]
        for index in group_a_set:
            value[index] *= float(gains[0])
            if branch in ("B", "ZERO"):
                value[index] = 0.0
        for index in group_b_set:
            value[index] *= float(gains[1])
            if branch in ("A", "ZERO"):
                value[index] = 0.0
        return np.clip(value, -1.0, 1.0)

    def rollout(
        self,
        state: np.ndarray,
        actions: np.ndarray,
        demo_id: int,
        branch: str,
        group_a: Sequence[int],
        group_b: Sequence[int],
        gains: Tuple[float, float] = (1.0, 1.0),
        keep_background: bool = False,
    ) -> Dict[str, Any]:
        self.set_state(state, demo_id)
        start_sim_state = self.env.get_sim_state().copy()
        start = self.snapshot()
        trajectory: List[Dict[str, Any]] = []
        applied_actions: List[List[float]] = []
        minimum_height = float(start["object"]["position"][2])
        for raw_action in np.asarray(actions, dtype=np.float64):
            action = self._masked_action(
                raw_action,
                branch,
                group_a,
                group_b,
                gains,
                keep_background,
            )
            applied_actions.append(_json_vector(action))
            self.env.step(action)
            current = self.snapshot()
            minimum_height = min(minimum_height, float(current["object"]["position"][2]))
            trajectory.append(current)
        end = self.snapshot()
        end_sim_state = self.env.get_sim_state().copy()
        start_object = start["object"]
        end_object = end["object"]
        displacement = np.asarray(end_object["position"], dtype=np.float64) - np.asarray(
            start_object["position"], dtype=np.float64
        )
        rotation = quaternion_angle_wxyz(
            np.asarray(start_object["quaternion_wxyz"], dtype=np.float64),
            np.asarray(end_object["quaternion_wxyz"], dtype=np.float64),
        )
        progress = float(start["target_distance"] - end["target_distance"])
        drop = bool(minimum_height < float(start_object["position"][2]) - 0.08)
        return {
            "branch": branch,
            "gains": [float(gains[0]), float(gains[1])],
            "keep_background": bool(keep_background),
            "hidden_state_contract": {
                "mujoco_flat_state": "restored",
                "model_body_poses": "restored_from_demo_model_file",
                "osc": "anchored_to_restored_robot_state",
                "gripper_target": "hold_restored_finger_qpos",
            },
            "model_file_sha256": self.demo_model_sha256(demo_id),
            "start": start,
            "end": end,
            "applied_actions": applied_actions,
            "trajectory": trajectory,
            "outcome": {
                "translation": _json_vector(displacement),
                "rotation_angle_rad": float(rotation),
                "linear_velocity": list(end_object["linear_velocity"]),
                "angular_velocity": list(end_object["angular_velocity"]),
                "height_change": float(displacement[2]),
                "target_progress": progress,
                "minimum_height": minimum_height,
                "drop": drop,
                "success": bool(end["success"]),
                "object_target_contact": bool(end["contact"]["object_target"]),
                "object_gripper_contact": bool(end["contact"]["object_gripper"]),
            },
            "final_sim_state": _json_vector(end_sim_state),
            "restored_sim_state": _json_vector(start_sim_state),
        }

    def close(self) -> None:
        self.env.close()
