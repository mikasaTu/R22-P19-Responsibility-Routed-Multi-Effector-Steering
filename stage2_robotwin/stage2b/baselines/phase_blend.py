import numpy as np


def phase_weights(step: int, e3: int, e5: int, donor: str = "left") -> np.ndarray:
    progress = float(np.clip((step - e3) / max(e5 - e3, 1), 0.0, 1.0))
    values = np.asarray([1.0 - progress, progress])
    return values if donor == "left" else values[::-1]

