from __future__ import annotations

import numpy as np
from stage2_robotwin.stage2b.operator.local_effect_gain import _arm_model


def task_effect_joint_delta(task, side: str, frame, effect4, max_joint_delta_rad: float = 0.08):
    """Map [parallel, lateral, vertical, world-yaw] TCP effect to bounded joints."""
    _, model, qpos, link_index, move_indices, root_rotation = _arm_model(task, side)
    model.compute_forward_kinematics(qpos)
    jacobian = np.asarray(model.compute_single_link_jacobian(qpos, link_index, local=False), dtype=float)[:, move_indices]
    value = np.asarray(effect4, dtype=float)
    world_translation = value[0]*np.asarray(frame.e_parallel)+value[1]*np.asarray(frame.e_perp)+value[2]*np.asarray([0.,0.,1.])
    root_translation = root_rotation.T @ world_translation
    root_rotation_target = root_rotation.T @ np.asarray([0.,0.,value[3]])
    delta = np.linalg.pinv(jacobian, rcond=1e-4) @ np.r_[root_translation, root_rotation_target]
    peak=float(np.max(np.abs(delta),initial=0.0))
    if peak>max_joint_delta_rad: delta*=max_joint_delta_rad/peak
    return delta, {"effect4":value.tolist(),"joint_delta_l2":float(np.linalg.norm(delta)),"joint_delta_max":float(np.max(np.abs(delta),initial=0.0)),"jacobian_condition":float(np.linalg.cond(jacobian))}

