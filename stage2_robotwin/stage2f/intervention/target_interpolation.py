from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from stage2_robotwin.stage2b.intervention.task_frame import ObjectTaskFrame
from stage2_robotwin.stage2c.intervention.soft_expert_authority import SoftExpertAuthorityProfile

from .common import KnobHandle, arm_joints, snapshot_drive_properties, validate


@contextmanager
def apply(task: Any, soft_arm: str, gamma: float) -> Iterator[KnobHandle]:
    """Defect control: call the existing expert/follower target interpolator."""
    validate(task, soft_arm, gamma)
    joints = list(arm_joints(task, soft_arm))
    original = snapshot_drive_properties(joints)
    handle = KnobHandle("K3_target_interpolation", task, soft_arm, float(gamma), joints, original)
    if float(gamma) != 1.0:
        handle.profile = SoftExpertAuthorityProfile(task, soft_arm, float(gamma), ObjectTaskFrame.from_task(task))
    try:
        yield handle
    finally:
        handle.finalize()
        if not handle.restoration_exact:
            raise RuntimeError("K3 unexpectedly changed drive properties")

