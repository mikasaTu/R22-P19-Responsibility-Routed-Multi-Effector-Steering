"""Episode-level analysis for Stage 2B signal calibration and held-out replay."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_identity(path: Path) -> Tuple[int, int]:
    stem = path.stem
    parts = stem.split("_")
    try:
        return int(parts[1]), int(parts[3])
    except (IndexError, ValueError) as exc:
        raise ValueError(f"cannot parse episode/seed from {path.name}") from exc


def load_records(paths: Iterable[Path]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for path in paths:
        episode, seed = parse_identity(path)
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            value = json.loads(line)
            value["episode"] = episode
            value["seed"] = seed
            value["source_file"] = str(path)
            records.append(value)
    return records


def _projection(record: Mapping[str, Any], branch: str) -> float:
    direction = np.asarray(record["task_frame"]["e_parallel"], dtype=np.float64)
    zero = np.asarray(record["outcomes"]["ZERO"]["translation"], dtype=np.float64)
    value = np.asarray(record["outcomes"][branch]["translation"], dtype=np.float64)
    return float((value - zero) @ direction)


def _rho(record: Mapping[str, Any]) -> Tuple[float, float, float]:
    value = record["responsibility"]["three_channel"]
    return float(value["rho_left"]), float(value["rho_right"]), float(value["rho_joint"])


def paired_details(
    records: Iterable[Mapping[str, Any]],
    motion_threshold_m: float,
    dominance_threshold_m: float,
) -> List[Dict[str, Any]]:
    indexed: Dict[Tuple[int, int, float, int, int], Dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for record in records:
        profile = record["profile"]
        key = (
            int(record["episode"]),
            int(record["seed"]),
            float(profile["gamma"]),
            int(record["step"]),
            int(record["horizon"]),
        )
        indexed[key][profile["driver"]] = record

    details: List[Dict[str, Any]] = []
    for (episode, seed, gamma, step, horizon), profiles in sorted(indexed.items()):
        if set(profiles) != {"left", "right"}:
            continue
        profile_checks = {}
        pair_valid = True
        for expected in ("left", "right"):
            record = profiles[expected]
            effects = {"left": _projection(record, "L"), "right": _projection(record, "R")}
            other = "right" if expected == "left" else "left"
            valid = (
                effects[expected] > motion_threshold_m
                and effects[expected] - effects[other] > dominance_threshold_m
            )
            pair_valid &= valid
            profile_checks[expected] = {
                "singleton_task_direction_effect_m": effects,
                "positive_expected_effect": effects[expected] > motion_threshold_m,
                "expected_dominates": (
                    effects[expected] - effects[other] > dominance_threshold_m
                ),
                "valid": bool(valid),
            }
        left_rho = _rho(profiles["left"])
        right_rho = _rho(profiles["right"])
        oracle_margin = (left_rho[0] - left_rho[1]) - (right_rho[0] - right_rho[1])
        harmful = []
        for record in profiles.values():
            opposing = record["responsibility"]["harmful_opposing"]
            harmful.extend([float(opposing["left"]), float(opposing["right"])])
        baseline_equal = profiles["left"]["baseline_features"] == profiles["right"]["baseline_features"]
        details.append(
            {
                "episode": episode,
                "seed": seed,
                "gamma": gamma,
                "step": step,
                "e4_relative_step": int(profiles["left"]["e4_relative_step"]),
                "horizon": horizon,
                "pair_valid": bool(pair_valid),
                "invalid_pair_treatment": (
                    "intervention failure; excluded from oracle accuracy"
                    if not pair_valid
                    else None
                ),
                "profiles": profile_checks,
                "oracle_oriented_margin": float(oracle_margin),
                "oracle_correct": bool(oracle_margin > 0.0) if pair_valid else None,
                "rho_left_profile": list(left_rho),
                "rho_right_profile": list(right_rho),
                "rho_joint_abs_mean": float((abs(left_rho[2]) + abs(right_rho[2])) / 2),
                "harmful_opposing_min": float(min(harmful)),
                "profile_blind_baselines_identical": bool(baseline_equal),
            }
        )
    return details


def episode_metrics(details: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[int, int, float], List[Mapping[str, Any]]] = defaultdict(list)
    for item in details:
        grouped[(int(item["episode"]), int(item["seed"]), float(item["gamma"]))].append(item)
    values = []
    for (episode, seed, gamma), items in sorted(grouped.items()):
        valid = [item for item in items if item["pair_valid"]]
        margins = [float(item["oracle_oriented_margin"]) for item in valid]
        values.append(
            {
                "episode": episode,
                "seed": seed,
                "gamma": gamma,
                "paired_state_horizon_count": len(items),
                "valid_pair_count": len(valid),
                "valid_pair_rate": float(len(valid) / len(items)) if items else None,
                "oracle_orientation_accuracy": (
                    float(np.mean(np.asarray(margins) > 0.0)) if margins else None
                ),
                "episode_responsibility_margin_median": (
                    float(np.median(margins)) if margins else None
                ),
                "rho_joint_abs_median": (
                    float(np.median([item["rho_joint_abs_mean"] for item in valid]))
                    if valid
                    else None
                ),
                "harmful_opposing_min": (
                    float(min(item["harmful_opposing_min"] for item in valid))
                    if valid
                    else None
                ),
            }
        )
    return values


def bootstrap_mean_ci(
    values: Sequence[float], repetitions: int = 10000, seed: int = 22019
) -> Dict[str, Any]:
    array = np.asarray(values, dtype=np.float64)
    if not len(array):
        return {"episode_count": 0, "mean": None, "ci95": [None, None]}
    rng = np.random.default_rng(seed)
    sampled = array[rng.integers(0, len(array), size=(repetitions, len(array)))]
    means = sampled.mean(axis=1)
    return {
        "episode_count": len(array),
        "mean": float(array.mean()),
        "ci95": [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))],
        "bootstrap_repetitions": repetitions,
        "bootstrap_seed": seed,
        "statistical_unit": "episode",
    }


def gamma_summary(per_episode: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    grouped: Dict[float, List[Mapping[str, Any]]] = defaultdict(list)
    for item in per_episode:
        grouped[float(item["gamma"])].append(item)
    result = {}
    for gamma, items in sorted(grouped.items(), reverse=True):
        accuracies = [
            float(item["oracle_orientation_accuracy"])
            for item in items
            if item["oracle_orientation_accuracy"] is not None
        ]
        result[str(gamma)] = {
            "episode_count": len(items),
            "episodes_with_valid_pairs": sum(item["valid_pair_count"] > 0 for item in items),
            "valid_pair_rate": bootstrap_mean_ci(
                [float(item["valid_pair_rate"]) for item in items]
            ),
            "oracle_orientation_accuracy": bootstrap_mean_ci(accuracies),
            "per_episode": items,
        }
    return result


def shuffled_orientation_control(
    details: Sequence[Mapping[str, Any]], gamma: float, repetitions: int = 4096
) -> Dict[str, Any]:
    grouped: Dict[int, List[float]] = defaultdict(list)
    for item in details:
        if float(item["gamma"]) == gamma and item["pair_valid"]:
            grouped[int(item["seed"])].append(float(item["oracle_oriented_margin"]))
    episode_accuracy = np.asarray(
        [np.mean(np.asarray(values) > 0.0) for values in grouped.values()],
        dtype=np.float64,
    )
    if not len(episode_accuracy):
        return {
            "episode_count": 0,
            "correct_orientation_accuracy": None,
            "shuffled_orientation_accuracy": None,
        }
    rng = np.random.default_rng(22019)
    # One sign per episode keeps the episode, not branch point, as the random unit.
    signs = rng.choice([-1.0, 1.0], size=(repetitions, len(grouped)))
    shuffled = []
    for row in signs:
        accuracies = []
        for sign, margins in zip(row, grouped.values()):
            accuracies.append(np.mean(sign * np.asarray(margins) > 0.0))
        shuffled.append(float(np.mean(accuracies)))
    return {
        "episode_count": len(grouped),
        "correct_orientation_accuracy": float(episode_accuracy.mean()),
        "shuffled_orientation_accuracy": float(np.mean(shuffled)),
        "shuffle_repetitions": repetitions,
        "shuffle_seed": 22019,
        "shuffle_unit": "episode profile orientation",
    }


def relative_curve(details: Sequence[Mapping[str, Any]], gamma: float) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[int, int], List[Mapping[str, Any]]] = defaultdict(list)
    for item in details:
        if float(item["gamma"]) == gamma:
            grouped[(int(item["e4_relative_step"]), int(item["horizon"]))].append(item)
    result = []
    for (relative, horizon), items in sorted(grouped.items()):
        valid = [item for item in items if item["pair_valid"]]
        result.append(
            {
                "e4_relative_step": relative,
                "horizon": horizon,
                "episode_count": len({int(item["seed"]) for item in items}),
                "valid_pair_rate_across_episodes": float(np.mean([item["pair_valid"] for item in items])),
                "oracle_margin_median_valid": (
                    float(np.median([item["oracle_oriented_margin"] for item in valid]))
                    if valid
                    else None
                ),
                "rho_joint_abs_median_valid": (
                    float(np.median([item["rho_joint_abs_mean"] for item in valid]))
                    if valid
                    else None
                ),
            }
        )
    return result


def plot_curve(curve: Sequence[Mapping[str, Any]], path: Path) -> None:
    figure, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    for horizon in sorted({int(item["horizon"]) for item in curve}):
        values = [item for item in curve if int(item["horizon"]) == horizon]
        axes[0].plot(
            [item["e4_relative_step"] for item in values],
            [item["valid_pair_rate_across_episodes"] for item in values],
            marker="o",
            label=f"H={horizon}",
        )
        axes[1].plot(
            [item["e4_relative_step"] for item in values],
            [np.nan if item["rho_joint_abs_median_valid"] is None else item["rho_joint_abs_median_valid"] for item in values],
            marker="o",
            label=f"H={horizon}",
        )
    axes[0].set_ylabel("valid-pair rate")
    axes[1].set_ylabel("median |rho_joint|")
    axes[1].set_xlabel("physics steps relative to E4")
    for axis in axes:
        axis.axvline(0, color="black", linestyle="--", linewidth=1)
        axis.grid(alpha=0.25)
        axis.legend()
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=170)
    plt.close(figure)


def select_calibration(
    per_episode: Sequence[Mapping[str, Any]],
    details: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    input_paths: Sequence[Path],
) -> Dict[str, Any]:
    rule = config["calibration_selection_rule"]
    min_rate = float(rule["min_valid_pair_rate_each_calibration_episode"])
    candidates = sorted(
        [float(value) for value in config["intervention"]["gamma_candidates"]],
        reverse=True,
    )
    diagnostic = float(config["intervention"]["diagnostic_positive_control_gamma"])
    by_gamma: Dict[float, List[Mapping[str, Any]]] = defaultdict(list)
    for item in per_episode:
        by_gamma[float(item["gamma"])].append(item)
    eligible = [
        gamma
        for gamma in candidates
        if len(by_gamma[gamma]) == len(config["split_contract"]["calibration_seeds"])
        and all(float(item["valid_pair_rate"]) >= min_rate for item in by_gamma[gamma])
    ]
    if eligible:
        selected = max(eligible)
        basis = "largest non-extreme gamma meeting the preregistered per-episode rate"
        only_extreme = False
    elif by_gamma[diagnostic] and all(
        float(item["valid_pair_rate"]) >= min_rate for item in by_gamma[diagnostic]
    ):
        selected = diagnostic
        basis = "no non-extreme candidate passed; diagnostic positive control only"
        only_extreme = True
    else:
        selected = None
        basis = "no candidate met the preregistered pair-validity rule"
        only_extreme = False

    if selected is None:
        synergy_threshold = 0.5
    else:
        episode_joint = [
            float(item["rho_joint_abs_median"])
            for item in by_gamma[selected]
            if item["rho_joint_abs_median"] is not None
        ]
        raw = float(np.quantile(episode_joint, 0.75)) if episode_joint else 0.5
        synergy_threshold = float(np.clip(raw, 0.20, 0.50))
    return {
        "frozen": True,
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "calibration_seeds": list(config["split_contract"]["calibration_seeds"]),
        "heldout_seeds": list(config["split_contract"]["heldout_seeds"]),
        "selected_gamma": selected,
        "selected_gamma_is_diagnostic_only": only_extreme,
        "selection_basis": basis,
        "eligible_non_extreme_gammas": eligible,
        "motion_effect_threshold_m": float(rule["motion_effect_threshold_m"]),
        "dominance_margin_threshold_m": float(rule["dominance_margin_threshold_m"]),
        "synergy_threshold": synergy_threshold,
        "task_direction": "horizontal target displacement in object task frame",
        "window": "[E4-250,min(E5,E4+150)] stride 25",
        "horizons": list(config["sampling"]["horizons_physics_steps"]),
        "calibration_input_sha256": {str(path): sha256_file(path) for path in input_paths},
        "no_heldout_retuning": True,
        "pai_job_created": False,
        "accepted": False,
    }


def classify_heldout(
    per_episode: Sequence[Mapping[str, Any]], frozen: Mapping[str, Any]
) -> Dict[str, Any]:
    selected = frozen["selected_gamma"]
    if selected is None:
        return {
            "decision": "SIGNAL_NOT_REPLICATED",
            "reason": "calibration produced no valid frozen gamma",
        }
    primary = [item for item in per_episode if float(item["gamma"]) == float(selected)]
    valid_episodes = [item for item in primary if item["valid_pair_count"] > 0]
    rate_mean = float(np.mean([item["valid_pair_rate"] for item in primary])) if primary else 0.0
    accuracy_mean = (
        float(np.mean([item["oracle_orientation_accuracy"] for item in valid_episodes]))
        if valid_episodes
        else 0.0
    )
    joint_occupancy = (
        float(
            np.mean(
                [
                    float(item["rho_joint_abs_median"]) > float(frozen["synergy_threshold"])
                    for item in valid_episodes
                    if item["rho_joint_abs_median"] is not None
                ]
            )
        )
        if valid_episodes
        else 0.0
    )
    if frozen["selected_gamma_is_diagnostic_only"]:
        decision = "ONLY_EXTREME_INTERVENTION_SUPPORTED"
    elif len(valid_episodes) >= 4 and rate_mean >= 0.25 and accuracy_mean >= 0.8:
        decision = (
            "THREE_WAY_RESPONSIBILITY_REQUIRED"
            if joint_occupancy >= 0.5
            else "MULTISEED_SIGNAL_SUPPORTED"
        )
    elif len(valid_episodes) >= 3 and accuracy_mean >= 0.65:
        decision = "MULTISEED_SIGNAL_PARTIAL"
    else:
        decision = "SIGNAL_NOT_REPLICATED"
    return {
        "decision": decision,
        "selected_gamma": selected,
        "heldout_episode_count": len(primary),
        "episodes_with_valid_pairs": len(valid_episodes),
        "mean_episode_valid_pair_rate": rate_mean,
        "mean_episode_oracle_accuracy_on_valid_pairs": accuracy_mean,
        "episode_joint_mode_occupancy": joint_occupancy,
        "criteria": (
            "supported: >=4/5 episodes with valid pairs, mean episode rate >=0.25, "
            "mean episode oracle accuracy >=0.8; partial: >=3 episodes and accuracy >=0.65"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("calibrate", "evaluate"), required=True)
    parser.add_argument("--inputs", nargs="+", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-summary", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--plot", required=True)
    parser.add_argument("--frozen-config", required=True)
    args = parser.parse_args()

    paths = [Path(value).resolve() for value in args.inputs]
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    run_summary = json.loads(Path(args.run_summary).read_text(encoding="utf-8"))
    expected_split = "calibration" if args.mode == "calibrate" else "heldout"
    if run_summary["split"] != expected_split or run_summary["status"] != "SIGNAL_REPLAY_COMPLETE":
        raise RuntimeError("run summary does not prove a complete matching split")
    records = load_records(paths)
    rule = config["calibration_selection_rule"]
    details = paired_details(
        records,
        float(rule["motion_effect_threshold_m"]),
        float(rule["dominance_margin_threshold_m"]),
    )
    per_episode = episode_metrics(details)
    summary = gamma_summary(per_episode)

    if args.mode == "calibrate":
        frozen = select_calibration(per_episode, details, config, paths)
        write_json(Path(args.frozen_config), frozen)
        selected = frozen["selected_gamma"]
        decision = {
            "decision": (
                "CALIBRATION_NON_EXTREME_FROZEN"
                if selected is not None and not frozen["selected_gamma_is_diagnostic_only"]
                else (
                    "CALIBRATION_DIAGNOSTIC_ONLY"
                    if selected is not None
                    else "CALIBRATION_NO_VALID_SETTING"
                )
            ),
            "selected_gamma": selected,
        }
    else:
        frozen = json.loads(Path(args.frozen_config).read_text(encoding="utf-8"))
        observed_seeds = sorted({int(item["seed"]) for item in per_episode})
        if set(observed_seeds) & set(frozen["calibration_seeds"]):
            raise RuntimeError("held-out analysis contains calibration seeds")
        if observed_seeds != sorted(frozen["heldout_seeds"]):
            raise RuntimeError(
                f"held-out seeds {observed_seeds} do not match frozen {frozen['heldout_seeds']}"
            )
        selected = frozen["selected_gamma"]
        decision = classify_heldout(per_episode, frozen)

    curve = relative_curve(details, float(selected)) if selected is not None else []
    metrics = {
        "mode": args.mode,
        "decision": decision,
        "record_count": len(records),
        "paired_state_horizon_count": len(details),
        "per_episode": per_episode,
        "gamma_sensitivity": summary,
        "e4_relative_curve": curve,
        "shuffled_orientation_control": (
            shuffled_orientation_control(details, float(selected))
            if selected is not None
            else None
        ),
        "profile_blind_baseline_control": {
            "all_force_distance_phase_features_identical_across_matched_profiles": all(
                item["profile_blind_baselines_identical"] for item in details
            ),
            "expected_orientation_accuracy": 0.5,
            "reason": (
                "force, distance, and E4 phase are measured at the shared pre-intervention "
                "snapshot and cannot observe randomized LEFT/RIGHT profile assignment"
            ),
        },
        "invalid_pair_policy": "intervention failure only; excluded from oracle accuracy",
        "statistical_unit": "episode",
        "branch_points_used_as_independent_inference_samples": False,
        "frozen_config": frozen,
        "raw_input_sha256": {str(path): sha256_file(path) for path in paths},
        "evidence_boundary": "simulator privileged oracle; not deployable",
        "pai_job_created": False,
        "accepted": False,
    }
    write_json(Path(args.output), metrics)
    if curve:
        plot_curve(curve, Path(args.plot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

