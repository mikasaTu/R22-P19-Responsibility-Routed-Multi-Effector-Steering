"""Compact full-episode expert low-level tape schema."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

import numpy as np


@dataclass(frozen=True)
class ExpertTape:
    step: np.ndarray
    left_position: np.ndarray
    left_velocity: np.ndarray
    right_position: np.ndarray
    right_velocity: np.ndarray
    left_gripper: np.ndarray
    right_gripper: np.ndarray

    def __post_init__(self) -> None:
        lengths = {
            len(self.step),
            len(self.left_position),
            len(self.left_velocity),
            len(self.right_position),
            len(self.right_velocity),
            len(self.left_gripper),
            len(self.right_gripper),
        }
        if len(lengths) != 1:
            raise ValueError("expert tape arrays have inconsistent lengths")
        if len(self.step) and not np.array_equal(self.step, np.arange(len(self.step))):
            raise ValueError("full-prefix tape steps must be contiguous and start at zero")
        if self.left_gripper.shape != (len(self.step), 2) or self.right_gripper.shape != (len(self.step), 2):
            raise ValueError("gripper command arrays must have shape [T,2]")

    def __len__(self) -> int:
        return len(self.step)

    @staticmethod
    def _gripper(value: np.ndarray) -> tuple[float, float] | None:
        return None if np.isnan(value).all() else (float(value[0]), float(value[1]))

    def item(self, index: int) -> Dict[str, Any]:
        return {
            "step": int(self.step[index]),
            "left_position": self.left_position[index].copy(),
            "left_velocity": self.left_velocity[index].copy(),
            "right_position": self.right_position[index].copy(),
            "right_velocity": self.right_velocity[index].copy(),
            "left_gripper": self._gripper(self.left_gripper[index]),
            "right_gripper": self._gripper(self.right_gripper[index]),
        }

    def target_sequence(self, start: int, horizon: int) -> list[Dict[str, Any]]:
        if start < 0 or horizon < 1 or start + horizon > len(self):
            raise ValueError("requested target sequence lies outside the tape")
        values = []
        for index in range(start, start + horizon):
            item = self.item(index)
            values.append(
                {
                    "left": (item["left_position"], item["left_velocity"]),
                    "right": (item["right_position"], item["right_velocity"]),
                }
            )
        return values

    def save(self, path: Path | str) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            target,
            step=self.step,
            left_position=self.left_position,
            left_velocity=self.left_velocity,
            right_position=self.right_position,
            right_velocity=self.right_velocity,
            left_gripper=self.left_gripper,
            right_gripper=self.right_gripper,
        )

    @classmethod
    def from_records(cls, records: Sequence[Mapping[str, Any]]) -> "ExpertTape":
        if not records:
            raise ValueError("cannot build an empty expert tape")

        def gripper(side: str) -> np.ndarray:
            return np.asarray(
                [record[f"{side}_gripper"] or (np.nan, np.nan) for record in records],
                dtype=np.float64,
            )

        return cls(
            step=np.asarray([record["step"] for record in records], dtype=np.int64),
            left_position=np.asarray([record["left_position"] for record in records], dtype=np.float64),
            left_velocity=np.asarray([record["left_velocity"] for record in records], dtype=np.float64),
            right_position=np.asarray([record["right_position"] for record in records], dtype=np.float64),
            right_velocity=np.asarray([record["right_velocity"] for record in records], dtype=np.float64),
            left_gripper=gripper("left"),
            right_gripper=gripper("right"),
        )

    @classmethod
    def load(cls, path: Path | str) -> "ExpertTape":
        with np.load(Path(path), allow_pickle=False) as data:
            return cls(**{name: np.asarray(data[name]) for name in cls.__dataclass_fields__})
