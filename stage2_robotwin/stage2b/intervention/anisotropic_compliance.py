"""Fail-closed capability audit for Cartesian anisotropic arm compliance."""

from __future__ import annotations

from typing import Any, Dict


def audit_native_anisotropic_compliance(task: Any) -> Dict[str, Any]:
    """Describe the controller capability without mutating its drive settings.

    The pinned RoboTwin Aloha adapter exposes one scalar stiffness/damping pair
    per joint.  It has no Cartesian stiffness matrix or task-frame impedance
    entrypoint, so setting ``K_parallel`` alone would require an unvalidated
    controller replacement.  Stage 2B uses the explicitly allowed follower
    target fallback instead.
    """

    joints = list(task.robot.left_arm_joints) + list(task.robot.right_arm_joints)
    scalar_properties = all(
        isinstance(float(joint.get_stiffness()), float)
        and isinstance(float(joint.get_damping()), float)
        for joint in joints
    )
    return {
        "native_cartesian_stiffness_matrix": False,
        "per_joint_scalar_drive_properties": bool(scalar_properties),
        "arm_joint_count_audited": len(joints),
        "selected_fallback": "task_frame_follower_target",
        "reason": (
            "RoboTwin Robot.set_arm_joints writes joint drive position/velocity targets; "
            "SAPIEN exposes scalar stiffness and damping per joint, not a task-frame K matrix"
        ),
        "mutated_controller_properties": False,
    }

