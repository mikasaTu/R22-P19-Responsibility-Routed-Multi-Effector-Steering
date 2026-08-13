"""Online E0--E6 detector for a bimanual object handover."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Mapping, Optional


EVENT_ORDER = ("E0", "E1", "E2", "E3", "E4", "E5", "E6")


@dataclass
class HandoverEventDetector:
    donor: str
    stable_steps: int = 15
    events: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _receiver_streak: int = 0
    _receiver_only_streak: int = 0

    def __post_init__(self) -> None:
        if self.donor not in {"left", "right"}:
            raise ValueError("donor must be left or right")
        if self.stable_steps < 1:
            raise ValueError("stable_steps must be positive")

    @property
    def receiver(self) -> str:
        return "right" if self.donor == "left" else "left"

    def _emit(self, name: str, sample: Mapping[str, Any], reason: str) -> None:
        if name in self.events:
            return
        self.events[name] = {
            "event": name,
            "step": int(sample["step"]),
            "time_s": float(sample["time_s"]),
            "reason": reason,
        }

    def update(self, sample: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
        left = bool(sample["left_contact"])
        right = bool(sample["right_contact"])
        donor_contact = left if self.donor == "left" else right
        receiver_contact = right if self.donor == "left" else left

        if donor_contact and not receiver_contact:
            self._emit("E0", sample, "donor-only object contact")
        if receiver_contact:
            self._emit("E1", sample, "receiver first object contact")
        if donor_contact and receiver_contact:
            self._emit("E2", sample, "first simultaneous object contact")

        self._receiver_streak = (
            self._receiver_streak + 1
            if donor_contact and receiver_contact
            else 0
        )
        if self._receiver_streak >= self.stable_steps:
            self._emit(
                "E3",
                sample,
                f"receiver contact held for {self.stable_steps} physics steps",
            )

        if bool(sample.get("donor_open_command", False)):
            self._emit("E4", sample, "donor open command issued")

        if "E4" in self.events and not donor_contact and receiver_contact:
            self._emit("E5", sample, "donor contact lost after open command")

        self._receiver_only_streak = (
            self._receiver_only_streak + 1
            if receiver_contact and not donor_contact
            else 0
        )
        if "E5" in self.events and self._receiver_only_streak >= self.stable_steps:
            self._emit(
                "E6",
                sample,
                f"receiver-only contact held for {self.stable_steps} physics steps",
            )
        return dict(self.events)

    def audit(self) -> Dict[str, Any]:
        missing = [name for name in EVENT_ORDER if name not in self.events]
        steps = [self.events[name]["step"] for name in EVENT_ORDER if name in self.events]
        nondecreasing = all(a <= b for a, b in zip(steps, steps[1:]))
        strict_stage_boundaries = True
        for earlier, later in (("E0", "E1"), ("E2", "E3"), ("E3", "E4"), ("E4", "E5")):
            if earlier in self.events and later in self.events:
                strict_stage_boundaries &= self.events[earlier]["step"] < self.events[later]["step"]
        return {
            "valid": not missing and nondecreasing and strict_stage_boundaries,
            "missing": missing,
            "nondecreasing": nondecreasing,
            "strict_stage_boundaries": strict_stage_boundaries,
            "events": {name: self.events.get(name) for name in EVENT_ORDER},
            "donor": self.donor,
            "receiver": self.receiver,
        }
