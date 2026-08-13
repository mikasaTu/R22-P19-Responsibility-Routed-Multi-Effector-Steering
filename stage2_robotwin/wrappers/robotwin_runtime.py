"""Explicit external-runtime bootstrap for RoboTwin 2.0."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Tuple
import os
import sys

import yaml


def prepare_import(robotwin_root: str) -> Path:
    root = Path(robotwin_root).expanduser().resolve()
    if not (root / "envs" / "handover_block.py").is_file():
        raise FileNotFoundError(f"not a RoboTwin 2.0 checkout: {root}")
    if not (root / "assets" / "embodiments" / "aloha-agilex" / "config.yml").is_file():
        raise FileNotFoundError("aloha-agilex embodiment asset is missing")
    for metadata in (
        root / "assets" / "objects" / "objaverse" / "list.json",
        root / "assets" / "objects" / "same.json",
    ):
        if not metadata.is_file():
            raise FileNotFoundError(f"official object metadata is missing: {metadata}")
    os.chdir(root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


def install_mplib_runtime_adapter() -> None:
    """Select MPLib only when the embodiment explicitly requests it."""

    import numpy as np

    from envs.robot.planner import CuroboPlanner, MplibPlanner
    from envs.robot.robot import Robot

    original_plan_path = MplibPlanner.plan_path

    def compatible_plan_path(
        self: Any,
        now_qpos: Any,
        target_pose: Any,
        constraint_pose: Any = None,
        use_point_cloud: bool = False,
        use_attach: bool = False,
        arms_tag: str = None,
        log: bool = True,
    ) -> Dict[str, Any]:
        """Accept RoboTwin's CuRobo-shaped call while using MPLib.

        MPLib 0.2.1 has no partial-pose hold-vector API.  The exact target pose
        is still planned, but a non-null hold vector is counted as an explicit
        runtime deviation instead of being silently forgotten.
        """

        if constraint_pose is not None:
            self.stage2_ignored_constraint_requests = int(
                getattr(self, "stage2_ignored_constraint_requests", 0)
            ) + 1
        return original_plan_path(
            self,
            now_qpos,
            target_pose,
            use_point_cloud=use_point_cloud,
            use_attach=use_attach,
            arms_tag=arms_tag,
            log=log,
        )

    MplibPlanner.plan_path = compatible_plan_path

    def plan_batch(
        self: Any,
        now_qpos: Any,
        target_pose_list: Any,
        constraint_pose: Any = None,
        arms_tag: str = None,
    ) -> Dict[str, Any]:
        """Compatibility implementation for RoboTwin's pose-choice API.

        CuRobo exposes a vectorized `plan_batch`; MPLib 0.2.1 does not.  The
        expert only consumes per-candidate status and path length, so invoking
        the same official MPLib `plan_path` sequentially preserves semantics
        without synthesizing trajectories.
        """

        statuses = []
        positions = []
        velocities = []
        for target_pose in target_pose_list:
            result = self.plan_path(
                now_qpos,
                target_pose,
                constraint_pose=constraint_pose,
                arms_tag=arms_tag,
                log=False,
            )
            status = result.get("status", "Fail")
            statuses.append(status)
            if status == "Success":
                positions.append(np.asarray(result["position"]))
                velocities.append(np.asarray(result["velocity"]))
            else:
                positions.append(np.empty((0, 0), dtype=np.float64))
                velocities.append(np.empty((0, 0), dtype=np.float64))
        return {
            "status": np.asarray(statuses, dtype=object),
            "position": positions,
            "velocity": velocities,
        }

    if not hasattr(MplibPlanner, "plan_batch"):
        MplibPlanner.plan_batch = plan_batch

    def set_planner(self: Any, scene: Any = None) -> None:
        requested = {self.left_planner_type, self.right_planner_type}
        if not all(name in {"mplib_RRT", "mplib_screw"} for name in requested):
            if CuroboPlanner is None:
                raise RuntimeError(
                    "CuRobo was requested but is unavailable; refusing silent planner substitution"
                )
            raise RuntimeError(
                "Stage-2 adapter only authorizes explicit MPLib planners on this runtime"
            )
        self.communication_flag = False
        self.left_planner = MplibPlanner(
            self.left_urdf_path,
            self.left_srdf_path,
            self.left_move_group,
            self.left_entity_origion_pose,
            self.left_entity,
            self.left_planner_type,
            scene,
        )
        self.right_planner = MplibPlanner(
            self.right_urdf_path,
            self.right_srdf_path,
            self.right_move_group,
            self.right_entity_origion_pose,
            self.right_entity,
            self.right_planner_type,
            scene,
        )
        self.left_mplib_planner = self.left_planner
        self.right_mplib_planner = self.right_planner

    Robot.set_planner = set_planner


def build_handover_block(
    robotwin_root: str, planner: str = "mplib_screw"
) -> Tuple[Any, Dict[str, Any]]:
    if planner not in {"mplib_RRT", "mplib_screw"}:
        raise ValueError(f"unsupported Stage-2 planner: {planner}")
    root = prepare_import(robotwin_root)
    install_mplib_runtime_adapter()

    from envs.handover_block import handover_block

    config_path = root / "env_cfg" / "task_config" / "demo_clean.yml"
    embodiment_path = root / "assets" / "embodiments" / "aloha-agilex"
    task_args = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    embodiment = yaml.safe_load(
        (embodiment_path / "config.yml").read_text(encoding="utf-8")
    )
    embodiment["planner"] = planner
    args: Dict[str, Any] = deepcopy(task_args)
    args.update(
        {
            "task_name": "handover_block",
            "task_config": "demo_clean",
            "left_robot_file": str(embodiment_path),
            "right_robot_file": str(embodiment_path),
            "left_embodiment_config": deepcopy(embodiment),
            "right_embodiment_config": deepcopy(embodiment),
            "dual_arm_embodied": True,
            "render_freq": 0,
            "save_freq": None,
            "save_data": False,
            "collect_data": False,
            "need_plan": True,
            "eval_mode": False,
        }
    )
    return handover_block(), args
