"""K4 grip-authority adapter for the pinned RoboTwin runtime.

The pinned Robot wrapper exposes normalized gripper position targets and drive
target velocities, not a finite task-level gripper force command. K4 therefore
uses target opening as an explicit fallback:
    u -> gamma*u + (1-gamma)*1
The endpoint is the wrapper normalized open endpoint, not a guessed force.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping, Optional, Sequence, Tuple

import numpy as np


OPEN_TARGET = 1.0
_MISSING = object()


def _copy(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.copy()
    if isinstance(value, np.generic):
        return value.copy()
    if isinstance(value, (list, tuple)):
        return type(value)(_copy(x) for x in value)
    return value


def _equal(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is right
    try:
        return bool(np.array_equal(np.asarray(left), np.asarray(right), equal_nan=True))
    except (TypeError, ValueError):
        return left == right


def _json(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, tuple):
        return [_json(x) for x in value]
    if isinstance(value, list):
        return [_json(x) for x in value]
    if isinstance(value, dict):
        return {str(k): _json(v) for k, v in value.items()}
    return value


def _validate(task: Any, side: str, gamma: float) -> float:
    if task is None or not hasattr(task, "robot"):
        raise ValueError("task with robot is required")
    if side not in {"left", "right"}:
        raise ValueError("soft_arm must be left or right")
    value = float(gamma)
    if not np.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError("gamma must lie in [0,1]")
    return value


def _entries(robot: Any, side: str) -> list[Any]:
    values = getattr(robot, f"{side}_gripper", _MISSING)
    if values is _MISSING or values is None:
        raise ValueError(f"robot has no {side}_gripper entries")
    values = list(values)
    if not values:
        raise ValueError(f"robot has empty {side}_gripper")
    for entry in values:
        joint = entry[0] if isinstance(entry, (tuple, list)) else entry
        if joint is None:
            raise ValueError(f"{side} gripper contains null joint")
    return values


def _joint(entry: Any) -> Any:
    return entry[0] if isinstance(entry, (tuple, list)) else entry


def _get_drive(joint: Any, name: str, required: bool) -> Tuple[Any, bool]:
    getter = getattr(joint, f"get_drive_{name}", None)
    if callable(getter):
        return _copy(getter()), True
    value = getattr(joint, f"drive_{name}", _MISSING)
    if value is not _MISSING:
        return _copy(value), True
    if required:
        raise AttributeError(f"gripper joint has no drive {name} getter")
    return None, False


def _set_drive(joint: Any, name: str, value: Any) -> None:
    setter = getattr(joint, f"set_drive_{name}", None)
    if not callable(setter):
        raise AttributeError(f"gripper joint has no drive {name} setter")
    try:
        setter(_copy(value))
    except TypeError as error:
        array = np.asarray(value)
        if array.size != 1:
            raise error
        setter(float(array.reshape(-1)[0]))


@dataclass
class _JointTarget:
    target: Any
    velocity: Any
    has_velocity: bool

    def receipt(self) -> dict[str, Any]:
        return {
            "target": _json(self.target),
            "velocity": _json(self.velocity) if self.has_velocity else None,
            "velocity_available": bool(self.has_velocity),
        }


def _snapshot_targets(entries: Sequence[Any]) -> list[_JointTarget]:
    result = []
    for entry in entries:
        joint = _joint(entry)
        target, _ = _get_drive(joint, "target", True)
        velocity, available = _get_drive(joint, "velocity_target", False)
        result.append(_JointTarget(target, velocity, available))
    return result


def _restore_targets(entries: Sequence[Any], originals: Sequence[_JointTarget]) -> list[str]:
    errors = []
    if len(entries) != len(originals):
        return [f"joint count changed: original={len(originals)} restored={len(entries)}"]
    for index, (entry, original) in enumerate(zip(entries, originals)):
        try:
            joint = _joint(entry)
            _set_drive(joint, "target", original.target)
            if original.has_velocity:
                _set_drive(joint, "velocity_target", original.velocity)
        except Exception as exc:
            errors.append(f"joint {index}: {type(exc).__name__}: {exc}")
    return errors


def _snapshot_gripper_value(robot: Any, side: str) -> Tuple[Any, bool]:
    name = f"{side}_gripper_val"
    if hasattr(robot, name):
        return _copy(getattr(robot, name)), True
    getter = getattr(robot, f"get_{side}_gripper_val", None)
    if callable(getter):
        return _copy(getter()), False
    raise AttributeError(f"cannot snapshot {name}")


def _current_value(robot: Any, side: str, snapshot: Any) -> float:
    getter = getattr(robot, f"get_{side}_gripper_val", None)
    value = getter() if callable(getter) else snapshot
    value = float(np.asarray(value).reshape(-1)[0])
    if not np.isfinite(value):
        raise ValueError(f"{side} normalized gripper value is non-finite")
    return float(np.clip(value, 0.0, 1.0))


def _snapshot_arm_properties(robot: Any) -> dict[str, Optional[list[dict[str, Any]]]]:
    result = {}
    for side in ("left", "right"):
        joints = getattr(robot, f"{side}_arm_joints", _MISSING)
        if joints is _MISSING:
            result[side] = None
            continue
        records = []
        for joint in list(joints):
            getters = [
                getattr(joint, "get_stiffness", None),
                getattr(joint, "get_damping", None),
                getattr(joint, "get_force_limit", None),
                getattr(joint, "get_drive_mode", None),
            ]
            if not all(callable(x) for x in getters):
                result[side] = None
                break
            records.append({
                "stiffness": _copy(getters[0]()),
                "damping": _copy(getters[1]()),
                "force_limit": _copy(getters[2]()),
                "drive_mode": _copy(getters[3]()),
            })
        else:
            result[side] = records
    return result


def _arm_properties_equal(left: dict, right: dict) -> bool:
    for side in ("left", "right"):
        before, after = left.get(side), right.get(side)
        if before is None or after is None:
            if before is not after:
                return False
            continue
        if len(before) != len(after):
            return False
        for first, second in zip(before, after):
            for key in ("stiffness", "damping", "force_limit", "drive_mode"):
                if not _equal(first[key], second[key]):
                    return False
    return True


def _set_gripper(robot: Any, value: float, side: str) -> None:
    setter = getattr(robot, "set_gripper", None)
    if not callable(setter):
        raise AttributeError("target-opening fallback requires robot.set_gripper")
    try:
        setter(float(value), side, gripper_eps=0.0)
    except TypeError as first_error:
        try:
            setter(float(value), side, 0.0)
        except TypeError:
            raise first_error


def _command_value(command: Any) -> float:
    if isinstance(command, np.ndarray):
        value = command.item() if command.ndim == 0 else command.reshape(-1)[0]
    elif isinstance(command, (tuple, list)):
        if not command:
            raise ValueError("empty gripper command")
        value = command[0]
    else:
        value = command
    value = float(value)
    if not np.isfinite(value):
        raise ValueError("gripper command is non-finite")
    return float(np.clip(value, 0.0, 1.0))


def _routed_command(command: Any, value: float) -> Any:
    if isinstance(command, np.ndarray):
        result = np.array(command, copy=True)
        if result.ndim == 0:
            result[...] = value
        else:
            flat = result.reshape(-1)
            flat[0] = value
            if flat.size >= 2:
                flat[1] = 0.0
        return result
    if isinstance(command, tuple):
        values = list(command)
        values[0] = value
        if len(values) >= 2:
            values[1] = 0.0
        return tuple(values)
    if isinstance(command, list):
        values = list(command)
        values[0] = value
        if len(values) >= 2:
            values[1] = 0.0
        return values
    return float(value)


@dataclass
class GripForceHandle:
    task: Any
    soft_arm: str
    gamma: float
    entries: list[Any]
    original_targets: list[_JointTarget]
    original_gripper_value: Any
    value_attribute_present: bool
    original_arm_properties: dict
    name: str = "K4_grip_force"
    implementation: str = "target_opening_fallback"
    physical_quantity: str = "normalized_gripper_target_opening"
    force_control_available: bool = False
    open_target: float = OPEN_TARGET
    epsilon_override: float = 0.0
    initial_target: Optional[float] = None
    initial_target_applied: bool = False
    action_modification_count: int = 0
    target_modification_count: int = 0
    actuator_application_count: int = 0
    routed_commands: list[dict[str, Any]] = field(default_factory=list)
    restored_targets: list[_JointTarget] = field(default_factory=list)
    restored_gripper_value: Any = None
    restored_arm_properties: dict = field(default_factory=dict)
    restoration_exact: bool = False
    arm_properties_unchanged: bool = False

    @property
    def no_op(self) -> bool:
        return self.gamma == 1.0

    def _mix(self, value: float) -> float:
        return float(self.gamma * value + (1.0 - self.gamma) * self.open_target)

    def route_target(self, side: str, target: tuple[Any, Any]) -> tuple[np.ndarray, np.ndarray]:
        return np.asarray(target[0], dtype=np.float64).copy(), np.asarray(target[1], dtype=np.float64).copy()

    def route_gripper(self, side: str, command: Any) -> Any:
        if command is None or side != self.soft_arm or self.gamma == 1.0:
            return command
        source = _command_value(command)
        routed = self._mix(source)
        result = _routed_command(command, routed)
        self.action_modification_count += int(not _equal(command, result))
        self.target_modification_count += int(source != routed)
        self.routed_commands.append({
            "side": side,
            "source": _json(command),
            "routed": _json(result),
            "source_value": source,
            "routed_value": routed,
        })
        return result

    route_gripper_command = route_gripper

    def route_item(self, item: Mapping[str, Any]) -> dict[str, Any]:
        result = dict(item)
        key = f"{self.soft_arm}_gripper"
        if key in result:
            result[key] = self.route_gripper(self.soft_arm, result[key])
        return result

    def apply_initial_target(self) -> None:
        if self.gamma == 1.0:
            return
        source = _current_value(self.task.robot, self.soft_arm, self.original_gripper_value)
        self.initial_target = self._mix(source)
        _set_gripper(self.task.robot, self.initial_target, self.soft_arm)
        self.initial_target_applied = True
        self.actuator_application_count += 1

    def finalize(self) -> None:
        self.restored_targets = _snapshot_targets(self.entries)
        if self.value_attribute_present:
            self.restored_gripper_value = _copy(
                getattr(self.task.robot, f"{self.soft_arm}_gripper_val")
            )
        else:
            getter = getattr(self.task.robot, f"get_{self.soft_arm}_gripper_val", None)
            self.restored_gripper_value = _copy(getter()) if callable(getter) else None
        self.restored_arm_properties = _snapshot_arm_properties(self.task.robot)
        if self.no_op:
            # Gamma=1 is a true no-op. A normal rollout may advance gripper
            # targets while the context is open; do not write them back to the
            # E3 snapshot or mistake that normal evolution for failed restore.
            self.restoration_exact = True
        else:
            self.restoration_exact = (
                len(self.restored_targets) == len(self.original_targets)
                and all(
                    _equal(before.target, after.target)
                    and before.has_velocity == after.has_velocity
                    and (not before.has_velocity or _equal(before.velocity, after.velocity))
                    for before, after in zip(self.original_targets, self.restored_targets)
                )
                and _equal(self.original_gripper_value, self.restored_gripper_value)
            )
        self.arm_properties_unchanged = _arm_properties_equal(
            self.original_arm_properties, self.restored_arm_properties
        )

    def receipt(self) -> dict[str, Any]:
        return {
            "schema": "r22p19.stage2g.k4_grip_force_receipt.v1",
            "knob": self.name,
            "soft_arm": self.soft_arm,
            "gamma": float(self.gamma),
            "implementation": self.implementation,
            "physical_quantity": self.physical_quantity,
            "force_control_available": bool(self.force_control_available),
            "force_limit_scaled": False,
            "open_target": float(self.open_target),
            "open_target_source": "RoboTwin Robot.set_gripper normalized clamp [0,1]",
            "epsilon_override": float(self.epsilon_override),
            "initial_target": self.initial_target,
            "initial_target_applied": bool(self.initial_target_applied),
            "no_op": bool(self.no_op),
            "restoration_required": not self.no_op,
            "action_modification_count": int(self.action_modification_count),
            "target_modification_count": int(self.target_modification_count),
            "actuator_application_count": int(self.actuator_application_count),
            "routed_command_count": len(self.routed_commands),
            "original_gripper_value": _json(self.original_gripper_value),
            "restored_gripper_value": _json(self.restored_gripper_value),
            "original_drive_targets": [x.receipt() for x in self.original_targets],
            "restored_drive_targets": [x.receipt() for x in self.restored_targets],
            "restoration_exact": bool(self.restoration_exact),
            "arm_properties_unchanged": bool(self.arm_properties_unchanged),
            "arm_properties_modified_by_knob": False,
            "snapshot_covers_drive_properties": False,
        }


@contextmanager
def apply(task: Any, soft_arm: str, gamma: float) -> Iterator[GripForceHandle]:
    """Apply K4; restore only K4-owned state on exit (gamma=1 is a no-op)."""
    value = _validate(task, soft_arm, gamma)
    robot = task.robot
    entries = _entries(robot, soft_arm)
    originals = _snapshot_targets(entries)
    original_value, attribute_present = _snapshot_gripper_value(robot, soft_arm)
    original_arm = _snapshot_arm_properties(robot)
    handle = GripForceHandle(
        task=task,
        soft_arm=soft_arm,
        gamma=value,
        entries=entries,
        original_targets=originals,
        original_gripper_value=original_value,
        value_attribute_present=attribute_present,
        original_arm_properties=original_arm,
    )
    errors: list[str] = []
    try:
        handle.apply_initial_target()
        yield handle
    finally:
        if not handle.no_op:
            errors.extend(_restore_targets(entries, originals))
            if attribute_present:
                try:
                    setattr(robot, f"{soft_arm}_gripper_val", _copy(original_value))
                except Exception as exc:
                    errors.append(f"normalized value: {type(exc).__name__}: {exc}")
        handle.finalize()
        if errors or (not handle.no_op and not handle.restoration_exact) or not handle.arm_properties_unchanged:
            detail = "; ".join(errors)
            if not handle.no_op and not handle.restoration_exact:
                detail = (detail + "; " if detail else "") + "gripper state mismatch"
            if not handle.arm_properties_unchanged:
                detail = (detail + "; " if detail else "") + "arm properties changed"
            raise RuntimeError("K4 gripper state was not restored exactly: " + detail)
