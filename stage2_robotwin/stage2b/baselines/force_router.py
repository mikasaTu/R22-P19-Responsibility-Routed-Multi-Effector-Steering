import numpy as np


def force_weights(left_impulse: float, right_impulse: float) -> np.ndarray:
    values = np.maximum([left_impulse, right_impulse], 0.0)
    return np.asarray([0.5, 0.5]) if values.sum() <= 1e-12 else values / values.sum()

