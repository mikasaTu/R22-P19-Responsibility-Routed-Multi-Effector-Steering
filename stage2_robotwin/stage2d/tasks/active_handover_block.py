from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class ActiveWindowAudit:
    duration_steps: int
    moving_fraction: float
    mean_speed_mps: float
    max_tracking_error_m: float
    valid: bool


def audit_active_window(object_positions, reference_positions, physics_hz: float,
                        speed_threshold: float = 0.002, min_steps: int = 50) -> ActiveWindowAudit:
    positions = np.asarray(object_positions, dtype=float)
    reference = np.asarray(reference_positions, dtype=float)
    if positions.shape != reference.shape or positions.ndim != 2 or positions.shape[1] != 3:
        raise ValueError("positions/reference must both be [T,3]")
    speeds = np.linalg.norm(np.diff(positions, axis=0), axis=1) * physics_hz
    tracking = np.linalg.norm(positions - reference, axis=1)
    moving = float(np.mean(speeds > speed_threshold)) if len(speeds) else 0.0
    return ActiveWindowAudit(len(positions), moving, float(np.mean(speeds)) if len(speeds) else 0.0,
                             float(np.max(tracking, initial=0.0)),
                             bool(len(positions) >= min_steps and moving >= 0.5))

