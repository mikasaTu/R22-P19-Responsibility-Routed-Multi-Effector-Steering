"""Joint-support routing that preserves shared effect and edits differential effect."""

from __future__ import annotations

import numpy as np


def joint_shared_differential_share(
    rho_left: float,
    rho_right: float,
    differential_scale: float = 0.35,
    temperature: float = 0.20,
) -> np.ndarray:
    if not 0.0 <= differential_scale <= 1.0 or temperature <= 0:
        raise ValueError("invalid joint-support parameters")
    dominance = float(np.tanh((rho_left - rho_right) / temperature))
    left = 0.5 + 0.5 * differential_scale * dominance
    return np.asarray([left, 1.0 - left], dtype=np.float64)
