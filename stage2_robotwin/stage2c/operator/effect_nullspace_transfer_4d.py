"""Bounded 4-D task-effect nullspace transfer (2 arms x 4 task channels)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Sequence

import numpy as np


@dataclass(frozen=True)
class Transfer4DResult:
    action: tuple[tuple[float, ...], tuple[float, ...]]
    base_total_effect: tuple[float, ...]
    routed_total_effect: tuple[float, ...]
    effect_error_norm: float
    correction_ratio: float
    nullspace_dimension: int
    clipped: bool
    feasible: bool
    solver_status: str

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EffectNullspaceTransfer4D:
    """Project a contribution-target step into the total-effect nullspace.

    ``effect_matrix`` maps the flattened 8-vector ``[left4,right4]`` to the
    four total task effects.  The update is constrained to its numerical
    nullspace, so parallel/lateral/vertical/yaw total effects are conserved.
    """

    def __init__(self, eta: float = 0.5, relative_trust_region: float = 0.15) -> None:
        if not 0.0 <= eta <= 1.0:
            raise ValueError("eta must lie in [0, 1]")
        if not 0.0 < relative_trust_region <= 1.0:
            raise ValueError("relative trust region must lie in (0, 1]")
        self.eta = float(eta)
        self.relative_trust_region = float(relative_trust_region)

    def solve(
        self,
        base_action: Sequence[Sequence[float]],
        effect_matrix: Sequence[Sequence[float]],
        target_left_contribution: Sequence[float],
    ) -> Transfer4DResult:
        base = np.asarray(base_action, dtype=np.float64)
        matrix = np.asarray(effect_matrix, dtype=np.float64)
        target_left = np.asarray(target_left_contribution, dtype=np.float64)
        if base.shape != (2, 4) or matrix.shape != (4, 8) or target_left.shape != (4,):
            raise ValueError("expected base (2,4), effect_matrix (4,8), target_left (4,)")
        flat = base.reshape(-1)
        total = matrix @ flat
        left_matrix = matrix[:, :4]
        left_base = left_matrix @ flat[:4]
        desired_delta = target_left - left_base

        _, singular, vh = np.linalg.svd(matrix, full_matrices=True)
        rank = int(np.sum(singular > max(matrix.shape) * np.finfo(float).eps * max(singular, default=0.0)))
        null_basis = vh[rank:].T
        if null_basis.shape[1] == 0:
            return self._fallback(base, total, 0, "NO_NULLSPACE")
        projected_left = left_matrix @ null_basis[:4, :]
        coefficient, *_ = np.linalg.lstsq(projected_left, desired_delta, rcond=1e-8)
        correction = self.eta * (null_basis @ coefficient)
        limits = self.relative_trust_region * np.maximum(np.abs(flat), 5e-4)
        over = np.abs(correction) > limits + 1e-15
        scale = 1.0
        if np.any(over):
            scale = float(np.min(limits[over] / np.abs(correction[over])))
        routed_flat = flat + scale * correction
        routed_total = matrix @ routed_flat
        error = float(np.linalg.norm(routed_total - total))
        correction_ratio = float(np.linalg.norm(routed_flat - flat) / max(np.linalg.norm(flat), 5e-4))
        feasible = error <= 1e-8 + 1e-5 * max(float(np.linalg.norm(total)), 1.0)
        return Transfer4DResult(
            action=tuple(tuple(float(x) for x in row) for row in routed_flat.reshape(2, 4)),
            base_total_effect=tuple(float(x) for x in total),
            routed_total_effect=tuple(float(x) for x in routed_total),
            effect_error_norm=error,
            correction_ratio=correction_ratio,
            nullspace_dimension=int(null_basis.shape[1]),
            clipped=bool(scale < 1.0),
            feasible=feasible,
            solver_status="NULLSPACE_4D_APPLIED" if feasible else "NULLSPACE_4D_EFFECT_ERROR",
        )

    @staticmethod
    def _fallback(base: np.ndarray, total: np.ndarray, dimension: int, status: str) -> Transfer4DResult:
        return Transfer4DResult(
            action=tuple(tuple(float(x) for x in row) for row in base),
            base_total_effect=tuple(float(x) for x in total),
            routed_total_effect=tuple(float(x) for x in total),
            effect_error_norm=0.0,
            correction_ratio=0.0,
            nullspace_dimension=dimension,
            clipped=False,
            feasible=False,
            solver_status=status + "_BASE_FALLBACK",
        )
