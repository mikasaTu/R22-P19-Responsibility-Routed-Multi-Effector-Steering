from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class FrozenActiveReference:
    steps: np.ndarray
    left_position: np.ndarray
    left_velocity: np.ndarray
    right_position: np.ndarray
    right_velocity: np.ndarray
    left_gripper: np.ndarray
    right_gripper: np.ndarray
    left_gripper_valid: np.ndarray
    right_gripper_valid: np.ndarray
    sha256: str

    @classmethod
    def load(cls, path: Path) -> "FrozenActiveReference":
        raw_bytes = path.read_bytes()
        with np.load(path, allow_pickle=False) as data:
            values = {key: np.asarray(data[key]).copy() for key in data.files}
        required = {
            "steps", "left_position", "left_velocity", "right_position", "right_velocity",
            "left_gripper", "right_gripper", "left_gripper_valid", "right_gripper_valid",
        }
        missing = required - set(values)
        if missing:
            raise ValueError(f"active reference missing fields: {sorted(missing)}")
        length = len(values["steps"])
        if any(len(values[key]) != length for key in required):
            raise ValueError("active reference fields have unequal lengths")
        expected_shapes = {"steps": (length,)}
        for side in ("left", "right"):
            expected_shapes[f"{side}_position"] = (length, 6)
            expected_shapes[f"{side}_velocity"] = (length, 6)
            expected_shapes[f"{side}_gripper"] = (length, 2)
            expected_shapes[f"{side}_gripper_valid"] = (length,)
        wrong_shapes = {
            key: {"expected": shape, "actual": values[key].shape}
            for key, shape in expected_shapes.items() if values[key].shape != shape
        }
        if wrong_shapes:
            raise ValueError(f"active reference has invalid shapes: {wrong_shapes}")
        numeric = [key for key in required if not key.endswith("_valid")]
        if any(not np.all(np.isfinite(values[key])) for key in numeric):
            raise ValueError("active reference contains non-finite values")
        if not np.array_equal(values["steps"], np.arange(length)):
            raise ValueError("active reference must cover every episode step in order")
        return cls(**{key: values[key] for key in required}, sha256=hashlib.sha256(raw_bytes).hexdigest())

    @classmethod
    def load_validated(
        cls,
        path: Path,
        *,
        sidecar_path: Path,
        source_tape_path: Path,
        source_meta: dict[str, Any],
        expected_seed: int,
        expected_amplitude_m: float,
    ) -> tuple["FrozenActiveReference", dict[str, Any]]:
        """Load an active tape only after validating its complete lineage receipt."""
        tape = cls.load(path)
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        expected = {
            "schema": "r22p19.stage2f.frozen_active_reference.v1",
            "status": "COMPLETE",
            "seed": int(expected_seed),
            "episode": int(source_meta["episode"]),
            "events": {key: int(value) for key, value in source_meta["events"].items()},
            "amplitude_m": float(expected_amplitude_m),
            "axis": "e_perp",
            "both_arms_common_mode": True,
            "source_tape_sha256": str(source_meta["tape_sha256"]),
            "command_count": len(tape),
            "npz_sha256": tape.sha256,
        }
        mismatches = {
            key: {"expected": value, "actual": sidecar.get(key)}
            for key, value in expected.items()
            if sidecar.get(key) != value
        }
        actual_source_sha = hashlib.sha256(source_tape_path.read_bytes()).hexdigest()
        if actual_source_sha != str(source_meta["tape_sha256"]):
            mismatches["source_tape_file_sha256"] = {
                "expected": str(source_meta["tape_sha256"]),
                "actual": actual_source_sha,
            }
        if mismatches:
            raise ValueError(f"active-reference lineage mismatch: {mismatches}")
        return tape, sidecar

    def item(self, index: int) -> dict[str, Any]:
        if index < 0 or index >= len(self.steps):
            raise IndexError(index)
        result: dict[str, Any] = {"step": int(self.steps[index])}
        for side in ("left", "right"):
            result[f"{side}_position"] = getattr(self, f"{side}_position")[index].copy()
            result[f"{side}_velocity"] = getattr(self, f"{side}_velocity")[index].copy()
            valid = bool(getattr(self, f"{side}_gripper_valid")[index])
            result[f"{side}_gripper"] = (
                tuple(float(value) for value in getattr(self, f"{side}_gripper")[index])
                if valid else None
            )
        return result

    def __len__(self) -> int:
        return len(self.steps)
