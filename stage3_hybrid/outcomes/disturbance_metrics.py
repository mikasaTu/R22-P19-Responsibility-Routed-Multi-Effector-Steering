from __future__ import annotations

import numpy as np


def trajectory_rmse(candidate, base) -> float:
    candidate, base = np.asarray(candidate), np.asarray(base)
    if candidate.shape != base.shape: raise ValueError("trajectory shapes differ")
    return float(np.sqrt(np.mean(np.square(candidate - base))))

