"""Vector-valued two-effector counterfactual responsibility decomposition."""

from __future__ import annotations

from typing import Any, Dict, Mapping

import numpy as np


BRANCHES = ("LR", "L", "R", "ZERO")


def _array(value: Any) -> np.ndarray:
    return np.asarray(value, dtype=np.float64)


def shapley_effects(values: Mapping[str, Any]) -> Dict[str, Any]:
    """Return left/right Shapley effects and the non-additive interaction."""

    missing = set(BRANCHES) - set(values)
    if missing:
        raise ValueError(f"missing counterfactual branches: {sorted(missing)}")
    lr, left, right, zero = (_array(values[name]) for name in BRANCHES)
    if not (lr.shape == left.shape == right.shape == zero.shape):
        raise ValueError("counterfactual outcomes have different shapes")
    phi_left = 0.5 * ((left - zero) + (lr - right))
    phi_right = 0.5 * ((right - zero) + (lr - left))
    synergy = lr - left - right + zero
    return {
        "phi_left": phi_left.tolist(),
        "phi_right": phi_right.tolist(),
        "synergy": synergy.tolist(),
        "reconstruction_error": float(
            np.max(np.abs(phi_left + phi_right - (lr - zero)))
        ),
    }


def quaternion_delta_rotvec(start_wxyz: Any, end_wxyz: Any) -> np.ndarray:
    """Log-map the start-to-end quaternion rotation into a 3-vector."""

    start = _array(start_wxyz)
    end = _array(end_wxyz)
    start = start / np.linalg.norm(start)
    end = end / np.linalg.norm(end)
    inverse = start * np.array([1.0, -1.0, -1.0, -1.0])
    w1, x1, y1, z1 = end
    w2, x2, y2, z2 = inverse
    relative = np.array(
        [
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        ]
    )
    if relative[0] < 0:
        relative = -relative
    vector_norm = np.linalg.norm(relative[1:])
    if vector_norm < 1e-12:
        return np.zeros(3, dtype=np.float64)
    angle = 2.0 * np.arctan2(vector_norm, np.clip(relative[0], -1.0, 1.0))
    return relative[1:] / vector_norm * angle


def decompose_outcomes(
    outcomes: Mapping[str, Mapping[str, Any]], rotation_scale_m: float = 0.1
) -> Dict[str, Any]:
    """Keep motion, support, progress, harm, and synergy as separate channels."""

    for branch in BRANCHES:
        if branch not in outcomes:
            raise ValueError(f"missing outcome for {branch}")

    motion_values = {
        branch: np.concatenate(
            [
                _array(outcomes[branch]["translation"]),
                rotation_scale_m * _array(outcomes[branch]["rotation_vector"]),
            ]
        )
        for branch in BRANCHES
    }
    motion = shapley_effects(motion_values)
    support = shapley_effects(
        {branch: outcomes[branch]["support_delta"] for branch in BRANCHES}
    )
    progress = shapley_effects(
        {branch: outcomes[branch]["task_progress"] for branch in BRANCHES}
    )
    retention = shapley_effects(
        {
            branch: outcomes[branch]["contact_retention"]
            for branch in BRANCHES
        }
    )
    slip = shapley_effects(
        {branch: -_array(outcomes[branch]["slip"] ) for branch in BRANCHES}
    )

    desired = motion_values["LR"] - motion_values["ZERO"]
    norm_sq = float(desired @ desired)
    phi_left = _array(motion["phi_left"])
    phi_right = _array(motion["phi_right"])
    synergy = _array(motion["synergy"])
    if norm_sq < 1e-16:
        shapley_projections = {"left": 0.0, "right": 0.0}
        three_channel = {"left": 0.0, "right": 0.0, "joint": 0.0}
    else:
        shapley_projections = {
            "left": float(phi_left @ desired / norm_sq),
            "right": float(phi_right @ desired / norm_sq),
        }
        three_channel = {
            "left": float(
                (motion_values["L"] - motion_values["ZERO"]) @ desired
                / norm_sq
            ),
            "right": float(
                (motion_values["R"] - motion_values["ZERO"]) @ desired
                / norm_sq
            ),
            "joint": float(synergy @ desired / norm_sq),
        }
    return {
        "motion": motion,
        "support": support,
        "task_progress": progress,
        "contact_retention": retention,
        "negative_slip": slip,
        "motion_shapley_projection": shapley_projections,
        "harmful_opposing": {
            "left": float(min(shapley_projections["left"], 0.0)),
            "right": float(min(shapley_projections["right"], 0.0)),
        },
        "three_channel": {
            "rho_left": three_channel["left"],
            "rho_right": three_channel["right"],
            "rho_joint": three_channel["joint"],
            "reconstruction_error": float(
                abs(
                    three_channel["left"]
                    + three_channel["right"]
                    + three_channel["joint"]
                    - 1.0
                )
                if norm_sq >= 1e-16
                else 0.0
            ),
            "normalization": "singleton main effects plus interaction; not simplex-normalized",
        },
    }
