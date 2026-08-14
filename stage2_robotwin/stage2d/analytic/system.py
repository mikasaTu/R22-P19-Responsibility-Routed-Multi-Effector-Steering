from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class AnalyticCase:
    seed: int
    g_left: np.ndarray
    g_right: np.ndarray
    u_base: np.ndarray
    e_star: np.ndarray
    desired_receiver: float
    current_receiver: float
    action_limit: float
    slew_limit: float
    partial_failure: bool
    delay: int


def _gain(rng: np.random.Generator, mismatch: float) -> np.ndarray:
    q, _ = np.linalg.qr(rng.normal(size=(4, 4)))
    singular = np.geomspace(1.0, rng.uniform(0.18, 0.85), 4)
    return q @ np.diag(singular * mismatch) @ q.T


def make_case(seed: int) -> AnalyticCase:
    rng = np.random.default_rng(seed)
    g_left = _gain(rng, rng.uniform(0.75, 1.25))
    g_right = _gain(rng, rng.uniform(0.65, 1.35))
    partial_failure = seed % 11 == 0
    if partial_failure:
        g_right[:, seed % 4] *= 0.2
    # Freeze transition states near shared support.  The desired receiver share and
    # its left/right-swapped control deliberately straddle the current share, so the
    # signed-response gate is identifiable rather than an artifact of saturation.
    current = rng.uniform(0.42, 0.58)
    desired = rng.uniform(0.72, 0.90) if rng.random() < 0.5 else rng.uniform(0.10, 0.28)
    e_star = rng.normal(size=4)
    e_star[2] = rng.uniform(0.55, 1.25)  # positive support
    e_star /= max(np.linalg.norm(e_star), 1e-9)
    # Add a cancelling orthogonal component.  It changes neither net effect nor the
    # scalar current share, but creates the conflict/internal-force cases needed to
    # distinguish conservation-only from explicit internal suppression.
    internal = rng.normal(size=4)
    internal -= e_star * float(internal @ e_star) / float(e_star @ e_star)
    internal *= rng.uniform(0.02, 0.18) / max(np.linalg.norm(internal), 1e-12)
    u_left = np.linalg.lstsq(g_left, (1.0 - current) * e_star + internal, rcond=None)[0]
    u_right = np.linalg.lstsq(g_right, current * e_star - internal, rcond=None)[0]
    u_base = np.r_[u_left, u_right]
    limit = max(2.0, float(np.max(np.abs(u_base)) + 0.8))
    return AnalyticCase(
        seed=seed, g_left=g_left, g_right=g_right, u_base=u_base,
        e_star=e_star, desired_receiver=float(desired), current_receiver=float(current),
        action_limit=limit, slew_limit=1.0, partial_failure=partial_failure,
        delay=seed % 5,
    )


def contributions(case: AnalyticCase, action: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return case.g_left @ action[:4], case.g_right @ action[4:]


def receiver_share(case: AnalyticCase, action: np.ndarray) -> float:
    _, right = contributions(case, action)
    denom = float(case.e_star @ case.e_star)
    return float((right @ case.e_star) / max(denom, 1e-12))


def internal_force_proxy(case: AnalyticCase, action: np.ndarray) -> float:
    left, right = contributions(case, action)
    axis = case.e_star / max(np.linalg.norm(case.e_star), 1e-12)
    differential = left - right
    orthogonal = differential - axis * float(axis @ differential)
    return float(np.linalg.norm(orthogonal))
