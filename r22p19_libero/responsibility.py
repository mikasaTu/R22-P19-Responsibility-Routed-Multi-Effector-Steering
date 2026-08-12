"""Counterfactual Shapley responsibility and small dependency-free metrics."""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

import numpy as np


OUTCOME_NAMES = (
    "translation_x",
    "translation_y",
    "translation_z",
    "rotation_angle_rad",
    "linear_velocity_x",
    "linear_velocity_y",
    "linear_velocity_z",
    "angular_velocity_x",
    "angular_velocity_y",
    "angular_velocity_z",
    "height_change",
    "target_progress",
    "drop",
    "success",
)


def outcome_vector(outcome: Mapping[str, Any]) -> np.ndarray:
    value = np.asarray(
        list(outcome["translation"])
        + [float(outcome["rotation_angle_rad"])]
        + list(outcome["linear_velocity"])
        + list(outcome["angular_velocity"])
        + [
            float(outcome["height_change"]),
            float(outcome["target_progress"]),
            float(bool(outcome["drop"])),
            float(bool(outcome["success"])),
        ],
        dtype=np.float64,
    )
    if value.shape != (len(OUTCOME_NAMES),):
        raise ValueError("unexpected outcome vector shape: %s" % (value.shape,))
    if not np.isfinite(value).all():
        raise FloatingPointError("non-finite outcome vector")
    return value


def shapley_responsibility(branches: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    required = {"AB", "A", "B", "ZERO"}
    if set(branches) != required:
        raise ValueError("branch set mismatch: %s" % sorted(branches))
    y_ab = outcome_vector(branches["AB"]["outcome"])
    y_a = outcome_vector(branches["A"]["outcome"])
    y_b = outcome_vector(branches["B"]["outcome"])
    y_zero = outcome_vector(branches["ZERO"]["outcome"])
    phi_a = 0.5 * ((y_a - y_zero) + (y_ab - y_b))
    phi_b = 0.5 * ((y_b - y_zero) + (y_ab - y_a))
    synergy = y_ab - y_a - y_b + y_zero
    total = y_ab - y_zero
    residual = phi_a + phi_b - total
    relative_error = float(np.linalg.norm(residual) / max(float(np.linalg.norm(total)), 1e-9))

    # Motion responsibility is measured on translation and terminal linear
    # velocity. Progress and support remain separately signed diagnostics.
    motion_indices = np.asarray([0, 1, 2, 4, 5, 6], dtype=np.int64)
    magnitude_a = float(np.linalg.norm(phi_a[motion_indices]))
    magnitude_b = float(np.linalg.norm(phi_b[motion_indices]))
    denominator = magnitude_a + magnitude_b
    share_a = float(magnitude_a / denominator) if denominator > 1e-12 else 0.5
    share_b = float(magnitude_b / denominator) if denominator > 1e-12 else 0.5
    synergy_ratio = float(
        np.linalg.norm(synergy[motion_indices])
        / max(
            float(np.linalg.norm(y_ab[motion_indices] - y_zero[motion_indices])),
            1e-9,
        )
    )
    return {
        "outcome_names": list(OUTCOME_NAMES),
        "y_ab": y_ab.tolist(),
        "y_a": y_a.tolist(),
        "y_b": y_b.tolist(),
        "y_zero": y_zero.tolist(),
        "phi_a": phi_a.tolist(),
        "phi_b": phi_b.tolist(),
        "synergy": synergy.tolist(),
        "total_effect": total.tolist(),
        "conservation_residual": residual.tolist(),
        "relative_conservation_error": relative_error,
        "motion_magnitude_a": magnitude_a,
        "motion_magnitude_b": magnitude_b,
        "motion_share_a": share_a,
        "motion_share_b": share_b,
        "signed_progress_a": float(phi_a[11]),
        "signed_progress_b": float(phi_b[11]),
        "support_height_a": float(phi_a[10]),
        "support_height_b": float(phi_b[10]),
        "harmful_progress_a": float(max(0.0, -phi_a[11])),
        "harmful_progress_b": float(max(0.0, -phi_b[11])),
        "joint_synergy_ratio": synergy_ratio,
    }


def rank_auc(labels: Sequence[int], scores: Sequence[float]) -> float:
    y = np.asarray(labels, dtype=np.int64)
    s = np.asarray(scores, dtype=np.float64)
    if y.shape != s.shape or y.ndim != 1:
        raise ValueError("AUC inputs must be aligned vectors")
    positive = np.flatnonzero(y == 1)
    negative = np.flatnonzero(y == 0)
    if not len(positive) or not len(negative):
        raise ValueError("AUC requires both classes")
    wins = 0.0
    for pos in positive:
        difference = s[pos] - s[negative]
        wins += float(np.sum(difference > 0.0))
        wins += 0.5 * float(np.sum(difference == 0.0))
    return float(wins / (len(positive) * len(negative)))


def shuffled_auc_distribution(
    labels: Sequence[int],
    scores: Sequence[float],
    seed: int,
    repeats: int = 200,
) -> List[float]:
    y = np.asarray(labels, dtype=np.int64)
    s = np.asarray(scores, dtype=np.float64)
    rng = np.random.RandomState(int(seed))
    values: List[float] = []
    for _ in range(int(repeats)):
        values.append(rank_auc(y, s[rng.permutation(len(s))]))
    return values


def finite_summary(values: Sequence[float]) -> Dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    if not len(array) or not np.isfinite(array).all():
        raise ValueError("summary requires finite values")
    return {
        "count": int(len(array)),
        "mean": float(np.mean(array)),
        "std": float(np.std(array)),
        "min": float(np.min(array)),
        "p25": float(np.quantile(array, 0.25)),
        "median": float(np.median(array)),
        "p75": float(np.quantile(array, 0.75)),
        "max": float(np.max(array)),
    }
