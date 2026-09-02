from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from .common import KnobHandle, arm_joints, snapshot_drive_properties, validate


@contextmanager
def apply(task: Any, soft_arm: str, gamma: float) -> Iterator[KnobHandle]:
    """Scale only arm-joint force limits and restore in a fail-closed finally."""
    validate(task, soft_arm, gamma)
    joints = list(arm_joints(task, soft_arm))
    original = snapshot_drive_properties(joints)
    handle = KnobHandle("K2_force_limit", task, soft_arm, float(gamma), joints, original)
    handle.modified_joint_count = len(joints) if float(gamma) != 1.0 else 0
    try:
        if float(gamma) != 1.0:
            for joint, values in zip(joints, original):
                joint.set_drive_properties(values[0], values[1], values[2] * float(gamma), values[3])
        yield handle
    finally:
        restoration_errors = []
        if float(gamma) != 1.0:
            for index, (joint, values) in enumerate(zip(joints, original)):
                try:
                    joint.set_drive_properties(*values)
                except Exception as exc:
                    restoration_errors.append(f"joint {index}: {type(exc).__name__}: {exc}")
        handle.finalize()
        if restoration_errors or not handle.restoration_exact:
            raise RuntimeError(
                "K2 drive properties were not restored exactly; "
                + "; ".join(restoration_errors)
            )
