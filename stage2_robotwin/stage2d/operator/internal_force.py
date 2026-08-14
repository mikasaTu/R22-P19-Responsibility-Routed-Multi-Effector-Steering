from __future__ import annotations

import numpy as np


def orthogonal_differential(left_effect, right_effect, task_effect) -> np.ndarray:
    task = np.asarray(task_effect, dtype=float)
    axis = task / max(np.linalg.norm(task), 1e-12)
    differential = np.asarray(left_effect, dtype=float) - np.asarray(right_effect, dtype=float)
    return differential - axis * float(axis @ differential)


def proxy(left_effect, right_effect, task_effect) -> float:
    return float(np.linalg.norm(orthogonal_differential(left_effect, right_effect, task_effect)))

