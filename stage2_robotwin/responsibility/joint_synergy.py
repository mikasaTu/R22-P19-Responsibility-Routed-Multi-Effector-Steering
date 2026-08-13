"""Joint interaction term kept separate from per-arm responsibility."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np


def joint_synergy(values: Mapping[str, Any]) -> Any:
    required = {"LR", "L", "R", "ZERO"}
    missing = required - set(values)
    if missing:
        raise ValueError(f"missing counterfactual branches: {sorted(missing)}")
    result = (
        np.asarray(values["LR"], dtype=np.float64)
        - np.asarray(values["L"], dtype=np.float64)
        - np.asarray(values["R"], dtype=np.float64)
        + np.asarray(values["ZERO"], dtype=np.float64)
    )
    return result.item() if result.ndim == 0 else result.tolist()


__all__ = ["joint_synergy"]
