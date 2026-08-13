import numpy as np


def direct_scale_action(base_action, responsibility):
    """B4 deliberately scales without conserving total predicted effect."""
    return np.asarray(base_action, dtype=float) * np.asarray(responsibility, dtype=float)

