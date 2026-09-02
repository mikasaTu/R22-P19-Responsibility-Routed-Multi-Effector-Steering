from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence, Tuple

import numpy as np


DriveProperties = Tuple[float, float, float, Any]


def validate(task: Any, soft_arm: str, gamma: float) -> None:
    if task is None:
        raise ValueError("task is required")
    if soft_arm not in {"left", "right"}:
        raise ValueError("soft_arm must be left or right")
    if not 0.0 <= float(gamma) <= 1.0:
        raise ValueError("gamma must lie in [0,1]")


def arm_joints(task: Any, side: str) -> Sequence[Any]:
    return task.robot.left_arm_joints if side == "left" else task.robot.right_arm_joints


def snapshot_drive_properties(joints: Iterable[Any]) -> list[DriveProperties]:
    return [
        (
            float(joint.get_stiffness()),
            float(joint.get_damping()),
            float(joint.get_force_limit()),
            joint.get_drive_mode(),
        )
        for joint in joints
    ]


def drive_properties_equal(left: Sequence[DriveProperties], right: Sequence[DriveProperties]) -> bool:
    if len(left) != len(right):
        return False
    return all(
        np.array_equal(np.asarray(a[:3], dtype=np.float64), np.asarray(b[:3], dtype=np.float64))
        and a[3] == b[3]
        for a, b in zip(left, right)
    )


def serializable_properties(values: Sequence[DriveProperties]) -> list[dict[str, Any]]:
    return [
        {
            "stiffness": float(value[0]),
            "damping": float(value[1]),
            "force_limit": float(value[2]),
            "drive_mode": str(value[3]),
        }
        for value in values
    ]


def _append_array(payload: bytearray, value: Any) -> None:
    array = np.ascontiguousarray(value, dtype=np.float64)
    payload.extend(struct.pack("<I", array.ndim))
    for size in array.shape:
        payload.extend(struct.pack("<Q", int(size)))
    payload.extend(array.astype("<f8", copy=False).tobytes(order="C"))


def canonical_command_sha256(commands: Sequence[dict[str, Any]], side: str) -> str:
    """Hash exact canonical IEEE-754 command bytes without rounding."""
    payload = bytearray(b"r22p19.stage2f.command.v1\0")
    payload.extend(side.encode("ascii"))
    payload.extend(b"\0")
    for item in commands:
        _append_array(payload, item[f"{side}_position"])
        _append_array(payload, item[f"{side}_velocity"])
        gripper = item.get(f"{side}_gripper")
        if gripper is None:
            payload.extend(b"N")
        else:
            payload.extend(b"G")
            _append_array(payload, np.asarray(gripper, dtype=np.float64))
    return hashlib.sha256(payload).hexdigest()


def canonical_effect_sha256(values: Sequence[float | bool]) -> str:
    array = np.asarray(values, dtype=np.float64)
    if not np.all(np.isfinite(array)):
        raise ValueError("effect vector contains non-finite values")
    return hashlib.sha256(np.ascontiguousarray(array.astype("<f8")).tobytes()).hexdigest()


@dataclass
class KnobHandle:
    name: str
    task: Any
    soft_arm: str
    gamma: float
    joints: list[Any]
    original: list[DriveProperties]
    modified_joint_count: int = 0
    action_modification_count: int = 0
    actuator_application_count: int = 0
    target_modification_count: int = 0
    restored: list[DriveProperties] = field(default_factory=list)
    restoration_exact: bool = False
    profile: Any = None
    audits: list[dict[str, Any]] = field(default_factory=list)

    def route_target(self, side: str, target: tuple[Any, Any]) -> tuple[np.ndarray, np.ndarray]:
        position = np.asarray(target[0], dtype=np.float64)
        velocity = np.asarray(target[1], dtype=np.float64)
        if side != self.soft_arm:
            return position.copy(), velocity.copy()
        if self.name in {"K1_drive_compliance", "K2_force_limit"}:
            self.actuator_application_count += 1
        if self.profile is None:
            return position.copy(), velocity.copy()
        routed, audit = self.profile.blend((position, velocity))
        self.audits.append(audit)
        if not np.array_equal(np.asarray(routed[0]), position) or not np.array_equal(np.asarray(routed[1]), velocity):
            self.action_modification_count += 1
            self.target_modification_count += 1
        return np.asarray(routed[0], dtype=np.float64), np.asarray(routed[1], dtype=np.float64)

    def finalize(self) -> None:
        self.restored = snapshot_drive_properties(self.joints)
        self.restoration_exact = drive_properties_equal(self.original, self.restored)

    def receipt(self) -> dict[str, Any]:
        return {
            "knob": self.name,
            "soft_arm": self.soft_arm,
            "gamma": float(self.gamma),
            "modified_joint_count": int(self.modified_joint_count),
            "action_modification_count": int(self.action_modification_count),
            "actuator_application_count": int(self.actuator_application_count),
            "target_modification_count": int(self.target_modification_count),
            "original_drive_properties": serializable_properties(self.original),
            "restored_drive_properties": serializable_properties(self.restored),
            "restoration_exact": bool(self.restoration_exact),
            "snapshot_covers_drive_properties": False,
        }
