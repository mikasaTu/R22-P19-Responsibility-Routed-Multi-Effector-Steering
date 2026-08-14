"""Projected low-pass responsibility control with a maximum share slew rate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


def project_simplex2(value: Sequence[float]) -> np.ndarray:
    values = np.asarray(value, dtype=np.float64)
    if values.shape != (2,) or not np.all(np.isfinite(values)):
        raise ValueError("value must be a finite length-two vector")
    left = float(np.clip((values[0] - values[1] + 1.0) / 2.0, 0.0, 1.0))
    return np.asarray([left, 1.0 - left], dtype=np.float64)


@dataclass
class StatefulResponsibilityFilter:
    beta: float = 0.25
    max_share_change: float = 0.08
    initial: tuple[float, float] = (0.5, 0.5)

    def __post_init__(self) -> None:
        if not 0.0 < self.beta <= 1.0:
            raise ValueError("beta must lie in (0, 1]")
        if not 0.0 < self.max_share_change <= 1.0:
            raise ValueError("max_share_change must lie in (0, 1]")
        self._value = project_simplex2(self.initial)

    @property
    def value(self) -> np.ndarray:
        return self._value.copy()

    def update(self, oracle_share: Sequence[float]) -> np.ndarray:
        target = project_simplex2(oracle_share)
        proposal = project_simplex2((1.0 - self.beta) * self._value + self.beta * target)
        delta_left = float(
            np.clip(
                proposal[0] - self._value[0],
                -self.max_share_change,
                self.max_share_change,
            )
        )
        self._value = np.asarray(
            [self._value[0] + delta_left, self._value[1] - delta_left],
            dtype=np.float64,
        )
        return self.value
