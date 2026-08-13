"""Two-way versus explicit joint-support responsibility selection."""

from __future__ import annotations

from typing import Any, Dict, Sequence, Tuple

import numpy as np


def responsibility_weights(
    rho_left: float,
    rho_right: float,
    rho_joint: float,
    synergy_threshold: float,
    three_way: bool,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    if three_way and abs(rho_joint) > synergy_threshold:
        # Joint support keeps the base split.  The transfer solver is bypassed;
        # it must not arbitrarily assign interaction to one arm.
        return np.asarray([0.5, 0.5]), {
            "mode": "JOINT_SUPPORT",
            "bypass_transfer": True,
            "rho_joint": float(rho_joint),
        }
    values = np.maximum(np.asarray([rho_left, rho_right], dtype=np.float64), 0.0)
    total = float(values.sum())
    if total < 1e-12:
        values[:] = 0.5
        mode = "CONFLICT"
    else:
        values /= total
        mode = "LEFT_DOMINANT" if values[0] > values[1] else "RIGHT_DOMINANT"
    return values, {
        "mode": mode,
        "bypass_transfer": False,
        "rho_joint": float(rho_joint),
    }

