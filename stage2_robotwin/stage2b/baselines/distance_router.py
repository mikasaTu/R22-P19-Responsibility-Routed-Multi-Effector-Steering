import numpy as np


def distance_weights(left_distance: float, right_distance: float) -> np.ndarray:
    inverse = 1.0 / np.maximum([left_distance, right_distance], 1e-12)
    return inverse / inverse.sum()

