from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from stage2_robotwin.responsibility.oracle_brancher import AuthorityProfile, authority_override

from .common import KnobHandle, arm_joints, snapshot_drive_properties, validate


@contextmanager
def apply(task: Any, soft_arm: str, gamma: float) -> Iterator[KnobHandle]:
    """Scale arm-joint stiffness+damping via the existing authority override."""
    validate(task, soft_arm, gamma)
    joints = list(arm_joints(task, soft_arm))
    original = snapshot_drive_properties(joints)
    handle = KnobHandle("K1_drive_compliance", task, soft_arm, float(gamma), joints, original)
    profile = AuthorityProfile(
        name=f"stage2f_{soft_arm}_compliance_{float(gamma):.6g}",
        left_compliance=float(gamma) if soft_arm == "left" else 1.0,
        right_compliance=float(gamma) if soft_arm == "right" else 1.0,
    )
    handle.modified_joint_count = len(joints) if float(gamma) != 1.0 else 0
    try:
        with authority_override(task, profile):
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
                "K1 drive properties were not restored exactly; "
                + "; ".join(restoration_errors)
            )
