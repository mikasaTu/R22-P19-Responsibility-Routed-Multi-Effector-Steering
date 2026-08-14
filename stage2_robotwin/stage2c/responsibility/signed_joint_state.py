"""Explicit productive, harmful, joint, and conflict responsibility state."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict

import numpy as np

from stage2_robotwin.stage2c.operator.joint_shared_differential import (
    joint_shared_differential_share,
)


@dataclass(frozen=True)
class SignedResponsibility:
    productive_left: float
    productive_right: float
    harmful_left: float
    harmful_right: float
    rho_joint: float
    mode: str
    target_share_left: float
    target_share_right: float
    raw_rho_left: float
    raw_rho_right: float

    @property
    def target_share(self) -> np.ndarray:
        return np.asarray(
            [self.target_share_left, self.target_share_right], dtype=np.float64
        )

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def classify_signed_responsibility(
    rho_left: float,
    rho_right: float,
    rho_joint: float,
    *,
    joint_threshold: float = 0.20,
    harmful_threshold: float = 0.02,
    joint_differential_scale: float = 0.35,
    temperature: float = 0.20,
) -> SignedResponsibility:
    raw = np.asarray([rho_left, rho_right], dtype=np.float64)
    if not np.all(np.isfinite(np.r_[raw, rho_joint])):
        raise ValueError("responsibility values must be finite")
    productive = np.where(raw > 0.0, raw, 0.0)
    harmful = np.where(raw < 0.0, raw, 0.0)

    if float(np.min(raw)) < -harmful_threshold:
        mode = "CONFLICT"
        harmful_index = int(np.argmin(raw))
        share = np.zeros(2, dtype=np.float64)
        share[1 - harmful_index] = 1.0
    elif rho_joint >= joint_threshold:
        mode = "JOINT_SUPPORT"
        share = joint_shared_differential_share(
            rho_left,
            rho_right,
            differential_scale=joint_differential_scale,
            temperature=temperature,
        )
    else:
        shifted = raw - min(float(np.min(raw)), 0.0)
        total = float(shifted.sum())
        if total <= 1e-12:
            share = np.asarray([0.5, 0.5], dtype=np.float64)
        else:
            share = shifted / total
        if abs(float(share[0] - share[1])) <= 1e-6:
            mode = "JOINT_SUPPORT"
        else:
            mode = "LEFT_DOMINANT" if share[0] > share[1] else "RIGHT_DOMINANT"

    return SignedResponsibility(
        productive_left=float(productive[0]),
        productive_right=float(productive[1]),
        harmful_left=float(harmful[0]),
        harmful_right=float(harmful[1]),
        rho_joint=float(rho_joint),
        mode=mode,
        target_share_left=float(share[0]),
        target_share_right=float(share[1]),
        raw_rho_left=float(rho_left),
        raw_rho_right=float(rho_right),
    )
