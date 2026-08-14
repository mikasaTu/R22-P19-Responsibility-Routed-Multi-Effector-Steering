"""Closed-form one-dimensional effect-nullspace responsibility transfer."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Sequence

import numpy as np


@dataclass(frozen=True)
class NullspaceTransferResult:
    action_left: float
    action_right: float
    base_contribution: tuple[float, float]
    target_contribution: tuple[float, float]
    routed_contribution: tuple[float, float]
    predicted_total_effect: float
    base_total_effect: float
    effect_error: float
    effect_error_ratio: float
    action_correction_ratio: float
    nullspace_residual: float
    alpha_star: float
    eta: float
    applied_scale: float
    safety_clipping: tuple[str, ...]
    feasible: bool
    solver_status: str

    @property
    def action(self) -> np.ndarray:
        return np.asarray([self.action_left, self.action_right], dtype=np.float64)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EffectNullspaceTransfer1D:
    """Move per-arm contributions while preserving ``b @ a``.

    For gains ``b=[b_L,b_R]`` the vector ``n=[b_R,-b_L]`` is an exact
    one-dimensional nullspace direction.  Unlike the Stage 2B ridge solver,
    no absolute regularizer competes with a small physical gain.
    """

    def __init__(
        self,
        eta: float = 0.75,
        relative_trust_region: float = 0.20,
        action_floor_m: float = 5e-4,
        action_bound_m: float = 0.02,
        effect_relative_tolerance: float = 0.05,
        min_gain_product: float = 1e-8,
    ) -> None:
        if not 0.0 <= eta <= 1.0:
            raise ValueError("eta must lie in [0, 1]")
        if not 0.0 < relative_trust_region <= 1.0:
            raise ValueError("relative_trust_region must lie in (0, 1]")
        if action_floor_m <= 0 or action_bound_m <= 0:
            raise ValueError("action limits must be positive")
        if effect_relative_tolerance < 0 or min_gain_product <= 0:
            raise ValueError("invalid effect tolerance")
        self.eta = float(eta)
        self.relative_trust_region = float(relative_trust_region)
        self.action_floor_m = float(action_floor_m)
        self.action_bound_m = float(action_bound_m)
        self.effect_relative_tolerance = float(effect_relative_tolerance)
        self.min_gain_product = float(min_gain_product)

    def solve(
        self,
        base_action: Sequence[float],
        local_gain: Sequence[float],
        target_share: Sequence[float],
        *,
        contact_ok: bool = True,
        support_height_m: float | None = None,
        min_support_height_m: float = 0.78,
    ) -> NullspaceTransferResult:
        base = np.asarray(base_action, dtype=np.float64)
        gain = np.asarray(local_gain, dtype=np.float64)
        share = np.asarray(target_share, dtype=np.float64)
        if base.shape != (2,) or gain.shape != (2,) or share.shape != (2,):
            raise ValueError("base_action, local_gain, and target_share must be length two")
        if not np.all(np.isfinite(np.concatenate([base, gain, share]))):
            raise ValueError("operator inputs must be finite")
        if abs(float(share.sum()) - 1.0) > 1e-6:
            raise ValueError("target_share must sum to one")

        base_contribution = gain * base
        total = float(base_contribution.sum())
        target_contribution = share * total
        null = np.asarray([gain[1], -gain[0]], dtype=np.float64)
        gain_product = float(gain[0] * gain[1])
        clipping: list[str] = []
        status = "NULLSPACE_APPLIED"

        if not contact_ok:
            clipping.append("CONTACT_RETENTION")
        if support_height_m is not None and support_height_m < min_support_height_m:
            clipping.append("SUPPORT_HEIGHT")
        if abs(gain_product) < self.min_gain_product or np.linalg.norm(null) < 1e-10:
            clipping.append("DEGENERATE_GAIN")
        if clipping:
            return self._base_result(
                base, gain, base_contribution, target_contribution, tuple(clipping),
                "_".join(clipping) + "_BASE_FALLBACK",
            )

        # Both contribution residuals carry the same solution when the target
        # sum equals the conserved total; averaging makes numerical mismatch
        # explicit instead of silently selecting one arm.
        alpha_candidates = np.asarray(
            [
                (target_contribution[0] - base_contribution[0]) / gain_product,
                (base_contribution[1] - target_contribution[1]) / gain_product,
            ],
            dtype=np.float64,
        )
        alpha_star = float(alpha_candidates.mean())
        correction = self.eta * alpha_star * null

        relative_limit = self.relative_trust_region * np.maximum(
            np.abs(base), self.action_floor_m
        )
        scale = 1.0
        over_relative = np.abs(correction) > relative_limit + 1e-15
        if np.any(over_relative):
            scale = min(scale, float(np.min(relative_limit[over_relative] / np.abs(correction[over_relative]))))
            clipping.append("RELATIVE_TRUST_REGION")

        candidate = base + scale * correction
        over_bounds = np.abs(candidate) > self.action_bound_m + 1e-15
        if np.any(over_bounds):
            direction = scale * correction
            ratios = []
            for index in np.flatnonzero(over_bounds):
                bound = np.sign(candidate[index]) * self.action_bound_m
                if abs(direction[index]) > 1e-15:
                    ratios.append((bound - base[index]) / direction[index])
            valid = [value for value in ratios if 0.0 <= value <= 1.0]
            scale *= min(valid) if valid else 0.0
            clipping.append("ACTION_BOUND")
            candidate = base + scale * correction

        routed = gain * candidate
        routed_total = float(routed.sum())
        effect_error = routed_total - total
        denominator = max(abs(total), 1e-8)
        effect_error_ratio = abs(effect_error) / denominator
        null_residual = abs(float(gain @ (candidate - base)))
        correction_ratio = float(
            np.linalg.norm(candidate - base) / max(np.linalg.norm(base), self.action_floor_m)
        )
        feasible = effect_error_ratio <= self.effect_relative_tolerance + 1e-12
        if not feasible:
            return self._base_result(
                base,
                gain,
                base_contribution,
                target_contribution,
                tuple(clipping + ["EFFECT_ERROR"]),
                "EFFECT_ERROR_BASE_FALLBACK",
            )
        if clipping:
            status = "NULLSPACE_CLIPPED"
        return NullspaceTransferResult(
            action_left=float(candidate[0]),
            action_right=float(candidate[1]),
            base_contribution=tuple(float(x) for x in base_contribution),
            target_contribution=tuple(float(x) for x in target_contribution),
            routed_contribution=tuple(float(x) for x in routed),
            predicted_total_effect=routed_total,
            base_total_effect=total,
            effect_error=float(effect_error),
            effect_error_ratio=float(effect_error_ratio),
            action_correction_ratio=correction_ratio,
            nullspace_residual=float(null_residual),
            alpha_star=alpha_star,
            eta=self.eta,
            applied_scale=float(scale),
            safety_clipping=tuple(clipping),
            feasible=True,
            solver_status=status,
        )

    def _base_result(
        self,
        base: np.ndarray,
        gain: np.ndarray,
        base_contribution: np.ndarray,
        target_contribution: np.ndarray,
        clipping: tuple[str, ...],
        status: str,
    ) -> NullspaceTransferResult:
        total = float(gain @ base)
        return NullspaceTransferResult(
            action_left=float(base[0]),
            action_right=float(base[1]),
            base_contribution=tuple(float(x) for x in base_contribution),
            target_contribution=tuple(float(x) for x in target_contribution),
            routed_contribution=tuple(float(x) for x in base_contribution),
            predicted_total_effect=total,
            base_total_effect=total,
            effect_error=0.0,
            effect_error_ratio=0.0,
            action_correction_ratio=0.0,
            nullspace_residual=0.0,
            alpha_star=0.0,
            eta=self.eta,
            applied_scale=0.0,
            safety_clipping=clipping,
            feasible=False,
            solver_status=status,
        )
