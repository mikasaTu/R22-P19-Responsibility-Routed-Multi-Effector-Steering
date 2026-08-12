"""Configuration loading with the dev14 storage contract frozen by default."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import yaml


NEW_ROOT = Path(os.environ.get("R22P19_NEW_ROOT", "/mnt/cpfs/zbl-cpfs-new"))
USER_ROOT = NEW_ROOT / "USERS/leon"
CODE_ROOT = USER_ROOT / "code"
DATA_ROOT = NEW_ROOT / "dataset/leon"
LOG_ROOT = USER_ROOT / "logs"

DEFAULT_LIBERO_ROOT = CODE_ROOT / "LIBERO-r16p19-official-8f1084e"
DEFAULT_SIM_PYTHON = USER_ROOT / "envs/libero-original/bin/python"


@dataclass(frozen=True)
class TaskSpec:
    role: str
    suite: str
    name: str
    object_body: str
    target_body: Optional[str]
    demo_ids: Tuple[int, ...]

    @property
    def dataset_path(self) -> Path:
        return DATA_ROOT / "libero" / self.suite / (self.name + "_demo.hdf5")

    def bddl_path(self, libero_root: Path) -> Path:
        return libero_root / "libero/libero/bddl_files" / self.suite / (self.name + ".bddl")


@dataclass(frozen=True)
class SignalConfig:
    path: Path
    raw: Dict[str, Any]
    libero_root: Path
    sim_python: Path
    branch_horizons: Tuple[int, ...]
    branch_stride: int
    state_tolerance: float
    object_position_tolerance: float
    object_rotation_tolerance: float
    one_step_state_tolerance: float
    one_step_object_position_tolerance: float
    primary: TaskSpec
    control: TaskSpec
    arm_dims: Tuple[int, ...]
    gripper_dims: Tuple[int, ...]
    x_dims: Tuple[int, ...]
    y_dims: Tuple[int, ...]
    authority_gain_pairs: Tuple[Tuple[float, float], ...]
    gate: Dict[str, float]


def _task(role: str, value: Dict[str, Any]) -> TaskSpec:
    target = value.get("target_body")
    if target in (None, "null", "None"):
        target = None
    return TaskSpec(
        role=role,
        suite=str(value["suite"]),
        name=str(value["name"]),
        object_body=str(value["object_body"]),
        target_body=target,
        demo_ids=tuple(int(item) for item in value["demo_ids"]),
    )


def load_config(path: Union[os.PathLike, str]) -> SignalConfig:
    config_path = Path(path).resolve()
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    runtime = raw["runtime"]
    tasks = raw["tasks"]
    counterfactuals = raw["counterfactuals"]
    primary_groups = counterfactuals["primary_groups"]
    stress_groups = counterfactuals["authority_stress_groups"]
    return SignalConfig(
        path=config_path,
        raw=raw,
        libero_root=Path(os.environ.get("R22P19_LIBERO_ROOT", str(DEFAULT_LIBERO_ROOT))).resolve(),
        sim_python=Path(os.environ.get("R22P19_SIM_PYTHON", str(DEFAULT_SIM_PYTHON))).resolve(),
        branch_horizons=tuple(int(item) for item in runtime["branch_horizons"]),
        branch_stride=int(runtime["branch_stride"]),
        state_tolerance=float(runtime["deterministic_state_tolerance"]),
        object_position_tolerance=float(runtime["deterministic_object_position_tolerance_m"]),
        object_rotation_tolerance=float(runtime["deterministic_object_rotation_tolerance_rad"]),
        one_step_state_tolerance=float(runtime["one_step_state_tolerance"]),
        one_step_object_position_tolerance=float(runtime["one_step_object_position_tolerance_m"]),
        primary=_task("primary", tasks["primary"]),
        control=_task("gate_off_control", tasks["gate_off_control"]),
        arm_dims=tuple(int(item) for item in primary_groups["arm_pose"]),
        gripper_dims=tuple(int(item) for item in primary_groups["gripper"]),
        x_dims=tuple(int(item) for item in stress_groups["x_translation"]),
        y_dims=tuple(int(item) for item in stress_groups["y_translation"]),
        authority_gain_pairs=tuple(
            (float(pair[0]), float(pair[1]))
            for pair in counterfactuals["authority_gain_pairs"]
        ),
        gate={key: float(value) for key, value in raw["signal_gate"].items()},
    )


def default_config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "configs/signal_pilot.yaml"


def validate_paths(config: SignalConfig) -> List[str]:
    errors: List[str] = []
    checks: Sequence[Tuple[str, Path, str]] = (
        ("new_root", NEW_ROOT, "dir"),
        ("libero_root", config.libero_root, "dir"),
        ("sim_python", config.sim_python, "file"),
        ("primary_dataset", config.primary.dataset_path, "file"),
        ("control_dataset", config.control.dataset_path, "file"),
        ("primary_bddl", config.primary.bddl_path(config.libero_root), "file"),
        ("control_bddl", config.control.bddl_path(config.libero_root), "file"),
    )
    for label, path, kind in checks:
        valid = path.is_dir() if kind == "dir" else path.is_file()
        if not valid:
            errors.append("%s missing: %s" % (label, path))
    legacy_prefixes = ("/mnt/data", "/mnt/cpfs/leon", "/open_data", "/x2robot_v2")
    for task in (config.primary, config.control):
        value = str(task.dataset_path)
        if any(value.startswith(prefix) for prefix in legacy_prefixes):
            errors.append("legacy dataset path is forbidden: %s" % value)
    return errors
