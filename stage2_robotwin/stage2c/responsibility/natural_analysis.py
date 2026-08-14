"""Episode-level analysis for natural and hidden-authority responsibility."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, Mapping, Sequence

import numpy as np


def _bootstrap_mean(values: Sequence[float], repetitions: int, seed: int) -> Dict[str, Any]:
    array = np.asarray(values, dtype=np.float64)
    if not len(array):
        return {"mean": None, "ci95": [None, None], "n_episodes": 0}
    rng = np.random.default_rng(seed)
    samples = array[rng.integers(0, len(array), size=(repetitions, len(array)))].mean(axis=1)
    return {
        "mean": float(array.mean()),
        "ci95": [float(np.percentile(samples, 2.5)), float(np.percentile(samples, 97.5))],
        "n_episodes": int(len(array)),
    }


def _rank_correlation(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) < 3:
        return None
    a = np.asarray(left, dtype=np.float64)
    b = np.asarray(right, dtype=np.float64)
    if np.std(a) <= 1e-12 or np.std(b) <= 1e-12:
        return 0.0
    ra = np.argsort(np.argsort(a)).astype(np.float64)
    rb = np.argsort(np.argsort(b)).astype(np.float64)
    return float(np.corrcoef(ra, rb)[0, 1])


def _effect_norm(record: Mapping[str, Any]) -> float:
    outcomes = record["outcomes"]
    lr = outcomes["LR"]
    zero = outcomes["ZERO"]
    translation = np.asarray(lr["translation"]) - np.asarray(zero["translation"])
    rotation = 0.1 * (np.asarray(lr["rotation_vector"]) - np.asarray(zero["rotation_vector"]))
    return float(np.linalg.norm(np.r_[translation, rotation]))


def analyze_natural_responsibility(
    cells: Iterable[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> Dict[str, Any]:
    cells = list(cells)
    calibration = set(int(value) for value in config["seed_contract"]["calibration"])
    heldout = set(int(value) for value in config["seed_contract"]["heldout"])
    minimum_effect = float(config["natural_responsibility"]["min_motion_effect_m"])
    margin = float(config["natural_responsibility"]["min_dominance_margin"])
    repetitions = int(config["natural_responsibility"]["bootstrap_repetitions"])
    bootstrap_seed = int(config["natural_responsibility"]["bootstrap_seed"])

    prefix_audit = []
    for seed in sorted({int(cell["seed"]) for cell in cells}):
        subset = [cell for cell in cells if int(cell["seed"]) == seed]
        prefix_hashes = {
            str(cell.get("prefix_fingerprint_at_E2_minus_1", {}).get("sha256"))
            for cell in subset
        }
        tape_hashes = {str(cell.get("tape_sha256")) for cell in subset}
        prefix_audit.append(
            {
                "seed": seed,
                "profile_cells": len(subset),
                "prefix_hash_count": len(prefix_hashes),
                "tape_hash_count": len(tape_hashes),
                "paired_start_identical": len(prefix_hashes) == 1,
                "high_level_tape_identical": len(tape_hashes) == 1,
            }
        )

    hidden_records = []
    natural_records = []
    for cell in cells:
        for item in cell["records"]:
            base = {
                "seed": int(cell["seed"]),
                "profile": str(cell["profile"]),
                "gamma": cell.get("gamma"),
                "step": int(item["step"]),
                "e4_relative_step": int(item["e4_relative_step"]),
                "future_risk": item["future_risk"],
                "baselines": item["baselines"],
            }
            for horizon, estimate in item["by_horizon"].items():
                record = {
                    **base,
                    "horizon": int(horizon),
                    **estimate,
                }
                record["effect_norm"] = _effect_norm(record)
                record["valid"] = bool(
                    record["effect_norm"] > minimum_effect
                    and abs(record["rho_left"] - record["rho_right"]) > margin
                )
                if cell["profile"] == "NATURAL":
                    natural_records.append(record)
                else:
                    expected_left = cell["profile"] == "LEFT_HIDDEN_AUTHORITY"
                    record["expected_left"] = expected_left
                    record["correct"] = bool(
                        (record["rho_left"] > record["rho_right"]) == expected_left
                    )
                    hidden_records.append(record)

    hidden_index = {
        (
            item["seed"],
            float(item["gamma"]),
            item["e4_relative_step"],
            item["horizon"],
            item["profile"],
        ): item
        for item in hidden_records
    }
    hidden_pairs = []
    for key, left in sorted(hidden_index.items()):
        seed, gamma, relative, horizon, profile = key
        if profile != "LEFT_HIDDEN_AUTHORITY":
            continue
        right = hidden_index.get(
            (seed, gamma, relative, horizon, "RIGHT_HIDDEN_AUTHORITY")
        )
        if right is None:
            continue
        left_score = float(left["rho_left"] - left["rho_right"])
        right_score = float(right["rho_left"] - right["rho_right"])
        pair_score = left_score - right_score
        hidden_pairs.append(
            {
                "seed": seed,
                "gamma": gamma,
                "e4_relative_step": relative,
                "horizon": horizon,
                "left_profile": left,
                "right_profile": right,
                "left_score": left_score,
                "right_score": right_score,
                "pair_score": pair_score,
                "valid": bool(
                    left["effect_norm"] > minimum_effect
                    and right["effect_norm"] > minimum_effect
                    and abs(pair_score) > margin
                ),
                "correct": bool(pair_score > 0.0),
            }
        )

    gamma_calibration = {}
    gamma_contrast_summary = {}
    gamma_candidates = sorted(
        (float(value) for value in config["natural_responsibility"]["gammas"]),
        reverse=True,
    )
    for gamma in gamma_candidates:
        per_episode = []
        for seed in sorted(calibration):
            subset = [item for item in hidden_pairs if item["seed"] == seed and item["gamma"] == gamma and item["horizon"] == 10]
            valid = [item for item in subset if item["valid"]]
            per_episode.append(
                {
                    "seed": seed,
                    "valid_rate": len(valid) / len(subset) if subset else 0.0,
                    "accuracy": float(np.mean([item["correct"] for item in valid])) if valid else 0.0,
                }
            )
        gamma_calibration[str(gamma)] = per_episode
        all_gamma = [
            item for item in hidden_pairs if item["gamma"] == gamma and item["horizon"] == 10
        ]
        valid_gamma = [item for item in all_gamma if item["valid"]]
        by_split = {}
        for split_name, split_seeds in (("calibration", calibration), ("heldout", heldout)):
            split_values = [item for item in valid_gamma if item["seed"] in split_seeds]
            by_split[split_name] = {
                "pair_count": len(split_values),
                "episode_count": len({item["seed"] for item in split_values}),
                "expected_direction_rate": float(np.mean([item["correct"] for item in split_values])) if split_values else None,
                "reverse_direction_rate": float(np.mean([not item["correct"] for item in split_values])) if split_values else None,
                "pair_score_median": float(np.median([item["pair_score"] for item in split_values])) if split_values else None,
                "pair_score_p05_p95": [
                    float(np.percentile([item["pair_score"] for item in split_values], 5)),
                    float(np.percentile([item["pair_score"] for item in split_values], 95)),
                ] if split_values else [None, None],
            }
        gamma_contrast_summary[str(gamma)] = by_split
    selected_gamma = None
    for gamma in gamma_candidates:
        episodes = gamma_calibration[str(gamma)]
        if episodes and all(item["valid_rate"] >= 0.25 and item["accuracy"] >= 0.8 for item in episodes):
            selected_gamma = gamma
            break
    if selected_gamma is None:
        selected_gamma = max(
            gamma_candidates,
            key=lambda value: np.mean([item["accuracy"] for item in gamma_calibration[str(value)]]) if gamma_calibration[str(value)] else -1.0,
        )

    primary = [item for item in hidden_pairs if item["seed"] in heldout and item["gamma"] == selected_gamma and item["horizon"] == 10]
    episode_hidden = []
    for seed in sorted(heldout):
        subset = [item for item in primary if item["seed"] == seed]
        valid = [item for item in subset if item["valid"]]
        episode_hidden.append(
            {
                "seed": seed,
                "sample_count": len(subset),
                "valid_count": len(valid),
                "valid_rate": len(valid) / len(subset) if subset else 0.0,
                "accuracy": float(np.mean([item["correct"] for item in valid])) if valid else 0.0,
                "reverse_direction_accuracy": float(np.mean([not item["correct"] for item in valid])) if valid else 0.0,
            }
        )
    hidden_accuracy = _bootstrap_mean(
        [item["accuracy"] for item in episode_hidden], repetitions, bootstrap_seed
    )
    hidden_valid_rate = _bootstrap_mean(
        [item["valid_rate"] for item in episode_hidden], repetitions, bootstrap_seed + 1
    )
    hidden_reverse_accuracy = _bootstrap_mean(
        [item["reverse_direction_accuracy"] for item in episode_hidden],
        repetitions,
        bootstrap_seed + 2,
    )

    matched_horizons: Dict[tuple, list[float]] = defaultdict(list)
    for item in hidden_pairs:
        if item["seed"] in heldout and item["gamma"] == selected_gamma and item["valid"]:
            matched_horizons[(item["seed"], "HIDDEN_PAIR", item["e4_relative_step"])].append(float(item["pair_score"]))
    for item in natural_records:
        if item["seed"] in heldout and item["valid"]:
            matched_horizons[(item["seed"], "NATURAL", item["e4_relative_step"])].append(float(item["rho_left"] - item["rho_right"]))
    sign_consistency = []
    for values in matched_horizons.values():
        if len(values) != 3:
            continue
        signs = [np.sign(value) for value in values]
        sign_consistency.append(len(set(signs)) == 1)

    adjacent_deltas = []
    adjacent_by_episode: Dict[tuple, list[Mapping[str, Any]]] = defaultdict(list)
    for item in hidden_records + natural_records:
        if item["seed"] in heldout and item["horizon"] == 10 and (
            item["profile"] == "NATURAL" or float(item["gamma"]) == selected_gamma
        ):
            adjacent_by_episode[(item["seed"], item["profile"])].append(item)
    for values in adjacent_by_episode.values():
        values.sort(key=lambda item: item["step"])
        shares = [float(projected_share(item["rho_left"], item["rho_right"])) for item in values]
        adjacent_deltas.extend(abs(left - right) for left, right in zip(shares, shares[1:]))

    natural_curve: Dict[str, list[Dict[str, Any]]] = defaultdict(list)
    curve_groups: Dict[tuple[int, int], list[Mapping[str, Any]]] = defaultdict(list)
    for item in natural_records:
        if item["seed"] in heldout:
            curve_groups[(item["horizon"], item["e4_relative_step"])].append(item)
    for (horizon, relative), values in sorted(curve_groups.items()):
        natural_curve[str(horizon)].append(
            {
                "e4_relative_step": relative,
                "rho_left_mean": float(np.mean([item["rho_left"] for item in values])),
                "rho_right_mean": float(np.mean([item["rho_right"] for item in values])),
                "rho_joint_mean": float(np.mean([item["rho_joint"] for item in values])),
                "n_episodes": len({item["seed"] for item in values}),
            }
        )

    baseline_accuracy = {}
    baseline_names = sorted(
        set.intersection(
            *(
                set(item["left_profile"]["baselines"]["left_share"])
                & set(item["right_profile"]["baselines"]["left_share"])
                for item in primary
            )
        )
        if primary
        else []
    )
    for name in baseline_names:
        values = [
            item["left_profile"]["baselines"]["left_share"][name]
            > item["right_profile"]["baselines"]["left_share"][name]
            for item in primary
            if item["valid"]
        ]
        baseline_accuracy[name] = float(np.mean(values)) if values else None

    rng = np.random.default_rng(22019)
    valid_primary = [item for item in primary if item["valid"]]
    shuffled_scores = []
    primary_index = {
        (item["seed"], item["e4_relative_step"]): item for item in primary
    }
    primary_seeds = sorted({item["seed"] for item in primary})
    if len(primary_seeds) > 1:
        for _ in range(1000):
            permuted = rng.permutation(primary_seeds)
            mapped = dict(zip(primary_seeds, permuted))
            comparisons = []
            for (seed, relative), left_item in primary_index.items():
                right_item = primary_index.get((int(mapped[seed]), relative))
                if right_item is None:
                    continue
                pair_score = float(left_item["left_score"] - right_item["right_score"])
                if (
                    left_item["left_profile"]["effect_norm"] > minimum_effect
                    and right_item["right_profile"]["effect_norm"] > minimum_effect
                    and abs(pair_score) > margin
                ):
                    comparisons.append(pair_score > 0.0)
            if comparisons:
                shuffled_scores.append(float(np.mean(comparisons)))
    swapped_accuracy = float(np.mean([item["pair_score"] < 0.0 for item in valid_primary])) if valid_primary else None

    shifted_correct = []
    pairs_by_episode: Dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for item in primary:
        pairs_by_episode[item["seed"]].append(item)
    for values in pairs_by_episode.values():
        values.sort(key=lambda item: item["e4_relative_step"])
        shift = max(1, len(values) // 3)
        shifted_right = np.roll([item["right_score"] for item in values], shift)
        shifted_correct.extend(
            np.asarray([item["left_score"] for item in values]) > shifted_right
        )

    mismatch = []
    risks: Dict[str, list[float]] = defaultdict(list)
    baseline_mismatch: Dict[str, list[float]] = defaultdict(list)
    for item in valid_primary:
        mismatch.append(float(1.0 / (1.0 + np.exp(5.0 * item["pair_score"]))))
        for key in item["left_profile"]["future_risk"]:
            risks[key].append(
                0.5
                * (
                    float(item["left_profile"]["future_risk"][key])
                    + float(item["right_profile"]["future_risk"][key])
                )
            )
        for name in baseline_names:
            delta = float(item["left_profile"]["baselines"]["left_share"][name]) - float(item["right_profile"]["baselines"]["left_share"][name])
            baseline_mismatch[name].append(float(1.0 / (1.0 + np.exp(5.0 * delta))))
    risk_prediction = {
        key: _rank_correlation(mismatch, values) for key, values in risks.items()
    }
    baseline_risk_prediction = {
        name: {
            key: _rank_correlation(values, risks[key])
            for key in risks
        }
        for name, values in baseline_mismatch.items()
    }

    horizon_consistency_rate = float(np.mean(sign_consistency)) if sign_consistency else 0.0
    adjacent_median = float(np.median(adjacent_deltas)) if adjacent_deltas else None
    hidden_supported = bool(
        hidden_accuracy["mean"] is not None
        and hidden_accuracy["mean"] >= 0.8
        and hidden_valid_rate["mean"] is not None
        and hidden_valid_rate["mean"] >= 0.25
    )
    natural_stable = bool(
        horizon_consistency_rate >= 0.70
        and adjacent_median is not None
        and adjacent_median <= 0.25
    )
    predictive = max((abs(value) for value in risk_prediction.values() if value is not None), default=0.0) >= 0.10
    if hidden_supported and natural_stable and predictive:
        decision = "NATURAL_RESPONSIBILITY_SUPPORTED"
    elif hidden_supported:
        decision = "HIDDEN_AUTHORITY_ONLY"
    elif horizon_consistency_rate < 0.70:
        decision = "RESPONSIBILITY_UNSTABLE"
    else:
        decision = "SIGNAL_NOT_SUPPORTED"

    return {
        "decision": decision,
        "selected_gamma": selected_gamma,
        "gamma_calibration": gamma_calibration,
        "gamma_paired_contrast_summary": gamma_contrast_summary,
        "hidden_authority": {
            "episode_results": episode_hidden,
            "accuracy": hidden_accuracy,
            "reverse_direction_accuracy": hidden_reverse_accuracy,
            "valid_rate": hidden_valid_rate,
        },
        "paired_start_audit": {
            "per_seed": prefix_audit,
            "all_prefixes_identical_within_seed": bool(prefix_audit)
            and all(item["paired_start_identical"] for item in prefix_audit),
            "all_high_level_tapes_identical_within_seed": bool(prefix_audit)
            and all(item["high_level_tape_identical"] for item in prefix_audit),
            "assignment_unobservable_before_E2": bool(cells)
            and all(bool(cell.get("assignment_unobservable_before_E2")) for cell in cells),
        },
        "natural_phase_curve": dict(natural_curve),
        "horizon_sign_consistency_rate": horizon_consistency_rate,
        "adjacent_refresh_absolute_share_delta_median": adjacent_median,
        "adjacent_refresh_absolute_share_delta_p95": float(np.percentile(adjacent_deltas, 95)) if adjacent_deltas else None,
        "baselines_hidden_accuracy": baseline_accuracy,
        "controls": {
            "left_right_swapped_accuracy": swapped_accuracy,
            "episode_shuffle_accuracy_mean": float(np.mean(shuffled_scores)) if shuffled_scores else None,
            "temporal_circular_shift_accuracy": float(np.mean(shifted_correct)) if shifted_correct else None,
        },
        "mismatch_future_risk_rank_correlation": risk_prediction,
        "baseline_mismatch_future_risk_rank_correlation": baseline_risk_prediction,
        "oracle_cost": {
            "branch_rollouts": int(
                sum(
                    int(record.get("oracle_branch_count", 0))
                    for cell in cells
                    for record in cell.get("records", [])
                )
            ),
            "simulated_physics_steps": int(
                sum(
                    int(record.get("simulated_physics_steps", 0))
                    for cell in cells
                    for record in cell.get("records", [])
                )
            ),
        },
        "hidden_supported": hidden_supported,
        "natural_stable": natural_stable,
        "mismatch_predictive": predictive,
        "episode_is_only_inference_unit": True,
        "branch_points_are_independent": False,
        "accepted": False,
    }


def projected_share(rho_left: float, rho_right: float) -> float:
    values = np.asarray([rho_left, rho_right], dtype=np.float64)
    left = float(np.clip((values[0] - values[1] + 1.0) / 2.0, 0.0, 1.0))
    return left
