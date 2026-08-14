"""Explicit harmful-arm handling for signed responsibility control."""

from __future__ import annotations

from typing import Sequence

import numpy as np


def suppress_harmful_and_compensate(
    contribution: Sequence[float], harmful: Sequence[float]
) -> np.ndarray:
    """Suppress a harmful contribution and compensate on the other arm.

    The returned two-vector has the same sum as the input.  This helper does
    not hide negative channels behind ``max(rho, 0)``; callers must persist the
    signed ``harmful`` vector separately.
    """

    values = np.asarray(contribution, dtype=np.float64).copy()
    harm = np.asarray(harmful, dtype=np.float64)
    if values.shape != (2,) or harm.shape != (2,):
        raise ValueError("contribution and harmful must be length two")
    for index in np.argsort(harm):
        if harm[index] >= 0:
            continue
        other = 1 - int(index)
        transferred = values[index]
        values[index] = 0.0
        values[other] += transferred
    return values
