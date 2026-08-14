from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass
class DesiredResponsibilityState:
    value: float = 0.1
    enter_capacity: float = 0.70
    exit_capacity: float = 0.50
    max_slew: float = 0.08
    active: bool = False

    def update(self, capacity: float, phase: float, contact_safe: bool) -> float:
        if self.active and (capacity < self.exit_capacity or not contact_safe):
            self.active = False
        elif not self.active and capacity >= self.enter_capacity and contact_safe:
            self.active = True
        target = np.clip(0.1 + 0.8 * phase, 0.1, 0.9) if self.active else 0.1
        delta = float(np.clip(target - self.value, -self.max_slew, self.max_slew))
        self.value = float(np.clip(self.value + delta, 0.0, 1.0))
        return self.value

