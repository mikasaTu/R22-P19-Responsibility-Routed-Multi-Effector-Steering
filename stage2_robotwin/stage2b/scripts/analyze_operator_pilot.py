"""Episode-level paired analysis and mechanism audit for Stage 2B-II."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


LOWER_IS_BETTER = (
    "drop",
    "premature_release",
    "peak_object_angular_velocity",
    "peak_object_linear_jerk",
    "peak_relative_slip_m",
    "receiver_takeover_delay_steps",
)
HIGHER_IS_BETTER = ("success", "handover_completion", "min_object_height_m")
PRIMARY_CONTINUOUS = (
    "peak_object_angular_velocity",
    "peak_object_linear_jerk",
    "peak_relative_slip_m",
)
HEURISTIC_BASELINES = ("B1", "B2", "B3")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bootstrap_mean(
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


def metric_value(row: Mapping[str, Any], metric: str) -> Optional[float]:
    value = row.get(metric)
    if value is None:
        return None
    return float(value)


def improvement(method: float, reference: float, metric: str) -> float:
    if metric in LOWER_IS_BETTER:
        return reference - method
    if metric in HIGHER_IS_BETTER:
        return method - reference
    raise KeyError(metric)


def index_rows(rows: Iterable[Mapping[str, Any]]) -> Dict[Tuple[int, str, str], Mapping[str, Any]]:
    result = {}
    for row in rows:
        key = (int(row["seed"]), str(row["condition"]), str(row["method"]))
        if key in result:
            raise ValueError(f"duplicate paired result: {key}")
        result[key] = row
    return result


def paired_improvements(
    indexed: Mapping[Tuple[int, str, str], Mapping[str, Any]],
    seeds: Sequence[int],
    conditions: Sequence[str],
    method: str,
    reference: str,
    metric: str,
) -> List[float]:
    per_episode = []
    for seed in seeds:
        values = []
        for condition in conditions:
            method_value = metric_value(indexed[(seed, condition, method)], metric)
            reference_value = metric_value(indexed[(seed, condition, reference)], metric)
            if method_value is None or reference_value is None:
                continue
            values.append(improvement(method_value, reference_value, metric))
        if values:
            per_episode.append(float(np.mean(values)))
    return per_episode


def method_table(
    indexed: Mapping[Tuple[int, str, str], Mapping[str, Any]],
    seeds: Sequence[int],
    methods: Sequence[str],
    conditions: Sequence[str],
) -> Dict[str, Any]:
    scopes = {"all_stress": [value for value in conditions if value != "clean"]}
    scopes.update({value: [value] for value in conditions})
    metrics = LOWER_IS_BETTER + HIGHER_IS_BETTER
    result: Dict[str, Any] = {}
    for scope, selected_conditions in scopes.items():
        result[scope] = {}
        for method in methods:
            result[scope][method] = {}
            for metric in metrics:
                values = paired_improvements(
                    indexed,
                    seeds,
                    selected_conditions,
                    method,
                    "B0",
                    metric,
                )
                result[scope][method][metric] = bootstrap_mean(values)
    return result


def exact_null_floor(
    indexed: Mapping[Tuple[int, str, str], Mapping[str, Any]],
    seeds: Sequence[int],
    conditions: Sequence[str],
) -> Dict[str, Any]:
    result = {}
    for metric in LOWER_IS_BETTER + HIGHER_IS_BETTER:
        signed = paired_improvements(
            indexed, seeds, conditions, "B9", "B0", metric
        )
        result[metric] = {
            "signed_B9_vs_B0": bootstrap_mean(signed),
            "mean_abs_episode_delta": float(np.mean(np.abs(signed))) if signed else None,
            "max_abs_episode_delta": float(np.max(np.abs(signed))) if signed else None,
            "contract": (
                "B0 and B9 execute identical arm/gripper targets and identical oracle "
                "branch schedule; any outcome difference is replay/hidden-state noise"
            ),
        }
    return result


def condition_means(
    indexed: Mapping[Tuple[int, str, str], Mapping[str, Any]],
    seeds: Sequence[int],
    methods: Sequence[str],
    conditions: Sequence[str],
) -> Dict[str, Any]:
    result = {}
    metrics = LOWER_IS_BETTER + HIGHER_IS_BETTER + (
        "mean_action_deviation_m",
        "effect_conservation_error_mean_abs_m",
        "effect_conservation_error_max_abs_m",
        "solver_feasible_rate",
        "release_guard_blocked_steps",
    )
    for condition in conditions:
        result[condition] = {}
        for method in methods:
            rows = [indexed[(seed, condition, method)] for seed in seeds]
            result[condition][method] = {
                metric: (
                    float(np.mean([float(row[metric]) for row in rows if row.get(metric) is not None]))
                    if any(row.get(metric) is not None for row in rows)
                    else None
                )
                for metric in metrics
            }
    return result


def log_mechanism_audit(log_dir: Path) -> Dict[str, Any]:
    by_method: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "log_count": 0,
            "solver_status": Counter(),
            "selected_mode": Counter(),
            "correction_abs": [],
            "local_gain_abs_nonzero": [],
            "base_action_abs_nonzero": [],
            "trust_region_clipped_count": 0,
            "release_guard_requested_count": 0,
            "release_guard_blocked_count": 0,
        }
    )
    for path in sorted(log_dir.glob("*.jsonl.gz")):
        method = path.stem.split("__")[-1].split(".")[0]
        target = by_method[method]
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                value = json.loads(line)
                target["log_count"] += 1
                target["solver_status"][value["solver_status"]] += 1
                target["selected_mode"][value["selected_mode"]] += 1
                correction = np.asarray(value["routed_action"]) - np.asarray(
                    value["base_action"]
                )
                target["correction_abs"].extend(np.abs(correction).tolist())
                target["local_gain_abs_nonzero"].extend(
                    abs(float(item))
                    for item in value["local_gain"]
                    if abs(float(item)) > 1e-12
                )
                target["base_action_abs_nonzero"].extend(
                    abs(float(item))
                    for item in value["base_action"]
                    if abs(float(item)) > 1e-12
                )
                target["trust_region_clipped_count"] += int(
                    value.get("trust_region_clipped", False)
                )
                guard = value.get("release_guard", {})
                if "not_requested" not in guard.get("checks", {}):
                    target["release_guard_requested_count"] += 1
                    target["release_guard_blocked_count"] += int(
                        not guard.get("allow", False)
                    )
    result = {}
    for method, value in sorted(by_method.items()):
        correction = np.asarray(value.pop("correction_abs"), dtype=np.float64)
        gains = np.asarray(value.pop("local_gain_abs_nonzero"), dtype=np.float64)
        base = np.asarray(value.pop("base_action_abs_nonzero"), dtype=np.float64)
        result[method] = {
            **value,
            "solver_status": dict(value["solver_status"]),
            "selected_mode": dict(value["selected_mode"]),
            "action_correction_abs_median_m": float(np.median(correction)) if len(correction) else None,
            "action_correction_abs_p95_m": float(np.quantile(correction, 0.95)) if len(correction) else None,
            "action_correction_abs_max_m": float(np.max(correction)) if len(correction) else None,
            "fraction_action_correction_above_1um": float(np.mean(correction > 1e-6)) if len(correction) else None,
            "local_gain_abs_nonzero_median": float(np.median(gains)) if len(gains) else None,
            "local_gain_squared_median": float(np.median(gains * gains)) if len(gains) else None,
            "base_action_abs_nonzero_median_m": float(np.median(base)) if len(base) else None,
        }
    return result


def specificity_audit(
    table: Mapping[str, Any],
    means: Mapping[str, Any],
    conditions: Sequence[str],
) -> Dict[str, Any]:
    stress = [value for value in conditions if value != "clean"]
    b11_beats_all_heuristics = []
    for condition in stress:
        wins = {}
        for metric in PRIMARY_CONTINUOUS:
            full = means[condition]["B11"][metric]
            wins[metric] = all(
                full < means[condition][baseline][metric]
                for baseline in HEURISTIC_BASELINES
            )
        b11_beats_all_heuristics.append(
            {"condition": condition, "per_metric": wins, "all_primary_metrics": all(wins.values())}
        )
    stress_full = table["all_stress"]["B11"]
    correct_positive = all(
        stress_full[metric]["mean"] is not None and stress_full[metric]["mean"] > 0
        for metric in PRIMARY_CONTINUOUS
    )
    return {
        "B11_beats_every_phase_distance_force_baseline": b11_beats_all_heuristics,
        "stress_condition_count_beating_all_heuristics_on_all_primary_metrics": sum(
            item["all_primary_metrics"] for item in b11_beats_all_heuristics
        ),
        "B11_all_stress_primary_metrics_improve_over_B0": correct_positive,
        "note": "specific method-vs-method paired tables are stored separately",
    }


def pairwise_table(
    indexed: Mapping[Tuple[int, str, str], Mapping[str, Any]],
    seeds: Sequence[int],
    conditions: Sequence[str],
    method: str,
    references: Sequence[str],
) -> Dict[str, Any]:
    stress = [value for value in conditions if value != "clean"]
    result = {}
    for reference in references:
        result[f"{method}_vs_{reference}"] = {
            metric: bootstrap_mean(
                paired_improvements(
                    indexed, seeds, stress, method, reference, metric
                )
            )
            for metric in LOWER_IS_BETTER + HIGHER_IS_BETTER
        }
    return result


def plot_improvements(
    table: Mapping[str, Any], methods: Sequence[str], output: Path
) -> None:
    selected = list(methods)
    figure, axes = plt.subplots(1, 3, figsize=(16, 5))
    for axis, metric in zip(axes, PRIMARY_CONTINUOUS):
        values = [table["all_stress"][method][metric] for method in selected]
        means = np.asarray([item["mean"] for item in values], dtype=np.float64)
        lower = means - np.asarray([item["ci95"][0] for item in values])
        upper = np.asarray([item["ci95"][1] for item in values]) - means
        axis.bar(np.arange(len(selected)), means, color="#4472C4")
        axis.errorbar(
            np.arange(len(selected)), means, yerr=np.vstack([lower, upper]), fmt="none", color="black", capsize=3
        )
        axis.axhline(0.0, color="black", linewidth=1)
        axis.set_xticks(np.arange(len(selected)), selected, rotation=45)
        axis.set_title(metric.replace("peak_object_", "").replace("_", " "))
        axis.set_ylabel("paired improvement over B0")
        axis.grid(axis="y", alpha=0.25)
    figure.suptitle("Stage 2B operator: episode-level mean across three stresses (95% bootstrap CI)")
    figure.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=170)
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--plot", required=True)
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if payload["status"] != "OPERATOR_PILOT_COMPLETE":
        raise RuntimeError("operator pilot is not complete")
    rows = payload["results"]
    seeds = [int(value) for value in payload["seeds"]]
    methods = list(payload["methods"])
    conditions = list(payload["conditions"])
    expected_keys = {
        (seed, condition, method)
        for seed in seeds
        for condition in conditions
        for method in methods
    }
    indexed = index_rows(rows)
    if set(indexed) != expected_keys:
        raise RuntimeError(
            f"paired matrix mismatch missing={sorted(expected_keys-set(indexed))} "
            f"extra={sorted(set(indexed)-expected_keys)}"
        )

    table = method_table(indexed, seeds, methods, conditions)
    means = condition_means(indexed, seeds, methods, conditions)
    null = exact_null_floor(indexed, seeds, conditions)
    pairwise = pairwise_table(indexed, seeds, conditions, "B11", ("B0", "B5", "B8", "B9"))
    mechanisms = log_mechanism_audit(input_path.parent / "operator_logs")
    specificity = specificity_audit(table, means, conditions)

    all_success = all(bool(row["success"]) for row in rows)
    no_drops = all(not bool(row["drop"]) for row in rows)
    stress_success = {
        condition: float(
            np.mean([row["success"] for row in rows if row["condition"] == condition and row["method"] == "B0"])
        )
        for condition in conditions
        if condition != "clean"
    }
    specificity_pass = (
        specificity["stress_condition_count_beating_all_heuristics_on_all_primary_metrics"] >= 2
        and all(
            pairwise["B11_vs_B8"][metric]["mean"] > 0
            for metric in PRIMARY_CONTINUOUS
        )
        and all(
            pairwise["B11_vs_B9"][metric]["mean"] > 0
            for metric in PRIMARY_CONTINUOUS
        )
    )
    operator_positive = specificity_pass and all_success and no_drops
    decision = "ORACLE_OPERATOR_PROMISING" if operator_positive else "SIGNAL_VALID_OPERATOR_WEAK"

    lambda_value = 0.05
    b7_gain_sq = mechanisms["B7"]["local_gain_squared_median"]
    regularization_ratio = (
        lambda_value / b7_gain_sq if b7_gain_sq and b7_gain_sq > 0 else None
    )
    mechanism_explanation = {
        "confirmed_from_code_and_logs": [
            {
                "finding": "contact-aware follower fixes the signal intervention",
                "evidence": (
                    "follower target updates only e_parallel while snapshot rotation/support targets remain; "
                    "held-out signal metrics are analyzed separately"
                ),
            },
            {
                "finding": "the continuous conserved operator is numerically near-null",
                "evidence": {
                    "B7_action_correction_abs_median_m": mechanisms["B7"]["action_correction_abs_median_m"],
                    "B7_action_correction_abs_p95_m": mechanisms["B7"]["action_correction_abs_p95_m"],
                    "B7_fraction_above_1um": mechanisms["B7"]["fraction_action_correction_above_1um"],
                    "ridge_lambda": lambda_value,
                    "median_local_gain_squared": b7_gain_sq,
                    "lambda_over_median_gain_squared": regularization_ratio,
                    "cause": (
                        "the ridge term dominates b_i squared in the KKT Hessian, so exact effect "
                        "conservation is achieved mostly by preserving the base action"
                    ),
                },
            },
            {
                "finding": "small apparent improvements/degradations are not attributable to routing",
                "evidence": {
                    "exact_null_control": null,
                    "cause": (
                        "B0 and B9 use identical commands but diverge because SAPIEN does not expose or "
                        "restore the PhysX solver warm-start cache; method order was rotated but n=5 remains small"
                    ),
                },
            },
            {
                "finding": "three-way mode rarely changes the action",
                "evidence": {
                    "B7_modes": mechanisms["B7"]["selected_mode"],
                    "B6_modes": mechanisms["B6"]["selected_mode"],
                    "cause": "frozen |rho_joint| threshold is exceeded in only a small fraction of logged steps",
                },
            },
            {
                "finding": "release guard is a separate sparse intervention",
                "evidence": {
                    "B10_requests": mechanisms["B10"]["release_guard_requested_count"],
                    "B10_blocks": mechanisms["B10"]["release_guard_blocked_count"],
                    "B11_requests": mechanisms["B11"]["release_guard_requested_count"],
                    "B11_blocks": mechanisms["B11"]["release_guard_blocked_count"],
                },
            },
        ],
        "not_claimed": [
            "no causal physical benefit is assigned to differences within the B0/B9 null replay floor",
            "no learned policy or deployable estimator was tested",
        ],
    }

    result = {
        "decision": decision,
        "operator_positive_trend": operator_positive,
        "signal_validity": "MULTISEED_SIGNAL_SUPPORTED (from frozen held-out Stage 2B-I)",
        "operator_validity": "WEAK_NOT_DEMONSTRATED" if not operator_positive else "PROMISING",
        "specificity": "NOT_DEMONSTRATED" if not specificity_pass else "SUPPORTED",
        "policy_compatibility": "NOT_TESTED",
        "deployability": "NOT_TESTED_SIMULATOR_ORACLE_ONLY",
        "matrix_contract": {
            "expected_count": len(expected_keys),
            "observed_count": len(indexed),
            "unique_count": len(set(indexed)),
            "seeds": seeds,
            "conditions": conditions,
            "methods": methods,
            "episode_is_statistical_unit": True,
            "replay_count_used_as_independent_inference_n": False,
        },
        "task_outcomes": {
            "all_240_success": all_success,
            "all_240_no_drop": no_drops,
            "base_stress_success_rate": stress_success,
            "stress_calibration_target_40_to_80_percent_met": any(
                0.4 <= value <= 0.8 for value in stress_success.values()
            ),
        },
        "condition_means": means,
        "paired_improvement_over_B0": table,
        "B11_pairwise_stress": pairwise,
        "exact_action_null_floor": null,
        "specificity_audit": specificity,
        "mechanism_log_audit": mechanisms,
        "mechanism_reverse_explanation": mechanism_explanation,
        "effect_conservation": {
            "B11_max_mean_abs_error_m": max(
                means[condition]["B11"]["effect_conservation_error_mean_abs_m"]
                for condition in conditions
            ),
            "B11_min_solver_feasible_rate": min(
                means[condition]["B11"]["solver_feasible_rate"]
                for condition in conditions
            ),
        },
        "cost": {
            "total_extra_simulator_rollouts": int(
                sum(row["extra_simulator_rollouts"] for row in rows)
            ),
            "total_extra_simulated_physics_steps": int(
                sum(row["extra_simulated_physics_steps"] for row in rows)
            ),
            "total_estimator_wall_time_s": float(
                sum(row["estimator_wall_time_s"] for row in rows)
            ),
            "total_solver_wall_time_s": float(sum(row["solver_wall_time_s"] for row in rows)),
            "total_replay_wall_time_s": float(
                sum(row["total_replay_wall_time_s"] for row in rows)
            ),
        },
        "act_status": "SKIPPED_BY_ORACLE_OPERATOR_GATE" if not operator_positive else "ELIGIBLE_NOT_STARTED",
        "pai_job_created": False,
        "accepted": False,
        "input": str(input_path),
        "input_sha256": sha256_file(input_path),
        "evidence_boundary": "simulator privileged oracle operator pilot; not deployable",
    }
    write_json(Path(args.output), result)
    plot_improvements(table, methods, Path(args.plot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
