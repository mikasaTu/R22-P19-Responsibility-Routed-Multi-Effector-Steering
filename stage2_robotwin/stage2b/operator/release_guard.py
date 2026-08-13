"""Responsibility-aware donor release guard kept separate from continuous routing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping


@dataclass
class ResponsibilityReleaseGuard:
    receiver_contact_stable_steps: int = 15
    min_receiver_responsibility: float = 0.5
    max_predicted_slip_m: float = 0.01
    _stable_steps: int = 0

    def update_contact(self, receiver_contact: bool) -> None:
        self._stable_steps = self._stable_steps + 1 if receiver_contact else 0

    def allow(
        self,
        receiver_responsibility: float,
        predicted_receiver_retention: float,
        predicted_slip_m: float,
        predicted_drop: bool,
    ) -> Dict[str, Any]:
        checks = {
            "stable_receiver_contact": self._stable_steps >= self.receiver_contact_stable_steps,
            "receiver_responsibility": receiver_responsibility >= self.min_receiver_responsibility,
            "receiver_retention": predicted_receiver_retention > 0.5,
            "slip_risk": predicted_slip_m <= self.max_predicted_slip_m,
            "drop_risk": not predicted_drop,
        }
        return {
            "allow": all(checks.values()),
            "checks": checks,
            "receiver_contact_streak": self._stable_steps,
        }

