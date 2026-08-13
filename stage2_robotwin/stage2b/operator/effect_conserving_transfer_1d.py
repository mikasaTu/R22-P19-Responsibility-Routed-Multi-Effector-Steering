"""Bounded two-variable effect-conserving responsibility transfer."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, Sequence

import numpy as np


@dataclass(frozen=True)
class TransferResult:
    action_left: float
    action_right: float
    desired_effect: float
    routed_effect: float
    effect_error: float
    objective: float
    feasible: bool
    solver_status: str
    trust_region_clipped: bool

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _objective(
    action: np.ndarray,
    base: np.ndarray,
    gain: np.ndarray,
    responsibility: np.ndarray,
    desired_effect: float,
    ridge_lambda: float,
) -> float:
    routed = gain * action
    return float(
        np.sum((routed - responsibility * desired_effect) ** 2)
        + ridge_lambda * np.sum((action - base) ** 2)
    )


class OneDimensionalEffectConservingTransfer:
    def __init__(
        self,
        ridge_lambda: float = 0.05,
        trust_region_m: float = 0.002,
        action_bound_m: float = 0.02,
        effect_tolerance_m: float = 1e-6,
    ) -> None:
        if ridge_lambda < 0 or trust_region_m <= 0 or action_bound_m <= 0:
            raise ValueError("invalid transfer hyperparameters")
        self.ridge_lambda = float(ridge_lambda)
        self.trust_region_m = float(trust_region_m)
        self.action_bound_m = float(action_bound_m)
        self.effect_tolerance_m = float(effect_tolerance_m)

    def solve(
        self,
        base_action: Sequence[float],
        local_gain: Sequence[float],
        responsibility: Sequence[float],
    ) -> TransferResult:
        base = np.asarray(base_action, dtype=np.float64)
        gain = np.asarray(local_gain, dtype=np.float64)
        rho = np.asarray(responsibility, dtype=np.float64)
        if base.shape != (2,) or gain.shape != (2,) or rho.shape != (2,):
            raise ValueError("base_action, local_gain, responsibility must be length two")
        desired = float(gain @ base)
        lower = np.maximum(base - self.trust_region_m, -self.action_bound_m)
        upper = np.minimum(base + self.trust_region_m, self.action_bound_m)
        if np.any(lower > upper) or float(np.linalg.norm(gain)) < 1e-10:
            return self._fallback(base, gain, rho, desired, "DEGENERATE_GAIN")

        min_effect = float(
            sum(value * (lower[i] if value >= 0 else upper[i]) for i, value in enumerate(gain))
        )
        max_effect = float(
            sum(value * (upper[i] if value >= 0 else lower[i]) for i, value in enumerate(gain))
        )
        if desired < min_effect - self.effect_tolerance_m or desired > max_effect + self.effect_tolerance_m:
            return self._fallback(base, gain, rho, desired, "EFFECT_OUTSIDE_BOUNDS")

        hessian = np.diag(gain * gain + self.ridge_lambda)
        linear = -(gain * rho * desired + self.ridge_lambda * base)
        kkt = np.block(
            [
                [hessian, gain[:, None]],
                [gain[None, :], np.zeros((1, 1), dtype=np.float64)],
            ]
        )
        rhs = np.concatenate([-linear, [desired]])
        candidates = []
        try:
            unconstrained = np.linalg.solve(kkt, rhs)[:2]
            if np.all(unconstrained >= lower - 1e-12) and np.all(unconstrained <= upper + 1e-12):
                candidates.append(unconstrained)
        except np.linalg.LinAlgError:
            pass

        # With two variables, every bound-active equality solution is explicit.
        for index in (0, 1):
            other = 1 - index
            for value in (lower[index], upper[index]):
                if abs(gain[other]) < 1e-12:
                    continue
                candidate = np.zeros(2, dtype=np.float64)
                candidate[index] = value
                candidate[other] = (desired - gain[index] * value) / gain[other]
                if lower[other] - 1e-12 <= candidate[other] <= upper[other] + 1e-12:
                    candidates.append(candidate)

        if not candidates:
            return self._fallback(base, gain, rho, desired, "NO_FEASIBLE_KKT_POINT")
        action = min(
            candidates,
            key=lambda value: _objective(
                value, base, gain, rho, desired, self.ridge_lambda
            ),
        )
        routed = float(gain @ action)
        error = routed - desired
        feasible = abs(error) <= self.effect_tolerance_m + 1e-12
        clipped = bool(np.any(np.abs(action - base) >= self.trust_region_m - 1e-12))
        return TransferResult(
            action_left=float(action[0]),
            action_right=float(action[1]),
            desired_effect=desired,
            routed_effect=routed,
            effect_error=float(error),
            objective=_objective(action, base, gain, rho, desired, self.ridge_lambda),
            feasible=feasible,
            solver_status="KKT_FEASIBLE" if feasible else "KKT_EFFECT_ERROR",
            trust_region_clipped=clipped,
        )

    def _fallback(
        self,
        base: np.ndarray,
        gain: np.ndarray,
        rho: np.ndarray,
        desired: float,
        status: str,
    ) -> TransferResult:
        routed = float(gain @ base)
        return TransferResult(
            action_left=float(base[0]),
            action_right=float(base[1]),
            desired_effect=desired,
            routed_effect=routed,
            effect_error=float(routed - desired),
            objective=_objective(base, base, gain, rho, desired, self.ridge_lambda),
            feasible=False,
            solver_status=status + "_BASE_FALLBACK",
            trust_region_clipped=False,
        )

