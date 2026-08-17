from __future__ import annotations

import numpy as np


FEATURE_KEYS = ("object_height_m", "object_displacement_m", "linear_speed",
                "angular_speed", "donor_contact", "receiver_contact",
                "donor_action_deviation_mean")
FORBIDDEN = ("eventual_task_success", "handover_complete", "drop",
             "takeover_failure", "oracle_mode")


def feature_vector(cell: dict, horizon: int) -> np.ndarray:
    values = cell["short_horizon_features"][str(horizon)]
    if any(key in values for key in FORBIDDEN):
        raise ValueError("outcome leakage in short-horizon features")
    if set(values) != set(FEATURE_KEYS):
        raise ValueError("feature schema changed")
    return np.asarray([float(values[key]) for key in FEATURE_KEYS], dtype=float)


def shifted_mapping(items: list, shift: int = 1) -> list:
    if len(items) < 2:
        raise ValueError("control needs at least two items")
    return items[-shift:] + items[:-shift]

