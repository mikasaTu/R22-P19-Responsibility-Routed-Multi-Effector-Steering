from __future__ import annotations

from typing import Any

from . import drive_compliance, force_limit, target_interpolation


MODULES = {
    "K1": drive_compliance,
    "K1_drive_compliance": drive_compliance,
    "K2": force_limit,
    "K2_force_limit": force_limit,
    "K3": target_interpolation,
    "K3_target_interpolation": target_interpolation,
}


def apply(knob: str, task: Any, soft_arm: str, gamma: float):
    try:
        module = MODULES[str(knob)]
    except KeyError as exc:
        raise ValueError(f"unknown authority knob: {knob}") from exc
    return module.apply(task, soft_arm, gamma)

