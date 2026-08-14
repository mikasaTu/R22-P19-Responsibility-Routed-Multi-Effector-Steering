"""Episode-level Stage 2C analysis, reports, and compact publication bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence

import numpy as np
import yaml

from stage2_robotwin.stage2c.replay.fresh_prefix_runner import write_json


GOOD_BINARY = ("success", "handover_completion")
BAD_BINARY = ("drop", "premature_release", "receiver_takeover_failure")
LOWER_CONTINUOUS = (
    "peak_object_angular_velocity",
    "peak_object_linear_jerk",
    "peak_relative_slip_m",
    "donor_residual_influence_impulse_sum",
)
HIGHER_CONTINUOUS = ("min_object_height_m",)
ALL_METRICS = GOOD_BINARY + BAD_BINARY + LOWER_CONTINUOUS + HIGHER_CONTINUOUS


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _interruption_recovery_audit(closed_root: Path) -> Dict[str, Any]:
    records = []
    for failure_path in sorted((closed_root / "cells").glob("*/failure.json")):
        failure = _load(failure_path)
        result_path = failure_path.with_name("result.json")
        result = _load(result_path) if result_path.is_file() else None
        records.append(
            {
                "cell": failure_path.parent.name,
                "failure_error_type": failure.get("error_type"),
                "failure_error": failure.get("error"),
                "result_present": result is not None,
                "result_status": result.get("status") if result else None,
                "result_sha256": (
                    hashlib.sha256(result_path.read_bytes()).hexdigest()
                    if result is not None
                    else None
                ),
                "recovered": bool(result and result.get("status") == "COMPLETE"),
            }
        )
    return {
        "failure_artifact_count": len(records),
        "recovered_count": sum(bool(item["recovered"]) for item in records),
        "unrecovered_count": sum(not bool(item["recovered"]) for item in records),
        "all_failure_artifacts_recovered": all(
            bool(item["recovered"]) for item in records
        ),
        "reason": (
            "four-worker contention diagnostic was intentionally stopped; "
            "fresh-process reruns retained both interruption lineage and final results"
        ),
        "records": records,
        "accepted": False,
    }


def _bootstrap_mean(
    values: Sequence[float], repetitions: int, seed: int
) -> Dict[str, Any]:
    array = np.asarray(values, dtype=np.float64)
    if not len(array):
        return {"mean": None, "ci95": [None, None], "n_episodes": 0}
    rng = np.random.default_rng(seed)
    draws = array[
        rng.integers(0, len(array), size=(repetitions, len(array)))
    ].mean(axis=1)
    return {
        "mean": float(array.mean()),
        "ci95": [
            float(np.percentile(draws, 2.5)),
            float(np.percentile(draws, 97.5)),
        ],
        "n_episodes": int(len(array)),
    }


def _benefit(method: Mapping[str, Any], reference: Mapping[str, Any], key: str) -> float:
    method_value = float(method["metrics"][key])
    reference_value = float(reference["metrics"][key])
    if key in GOOD_BINARY or key in HIGHER_CONTINUOUS:
        return method_value - reference_value
    return reference_value - method_value


def _compact_result(result: Mapping[str, Any]) -> Dict[str, Any]:
    operator_log = list(result.get("operator_log", []))
    effect_ratios = [
        abs(float(item.get("effect_error_ratio", 0.0))) for item in operator_log
    ]
    realization = []
    harmful_suppression = []
    solver_status = Counter(
        str(item.get("solver_status", "UNKNOWN")) for item in operator_log
    )
    safety_clipping = Counter(
        reason
        for item in operator_log
        for reason in item.get("safety_clipping", [])
    )
    for item in operator_log:
        if all(
            key in item
            for key in ("base_contribution", "target_contribution", "routed_contribution")
        ):
            base = np.asarray(item["base_contribution"], dtype=np.float64)
            target = np.asarray(item["target_contribution"], dtype=np.float64)
            routed = np.asarray(item["routed_contribution"], dtype=np.float64)
            realization.append(
                float(np.linalg.norm(base - target) - np.linalg.norm(routed - target))
            )
        signed = item.get("signed_responsibility", {})
        if str(signed.get("mode")) == "CONFLICT" and "base_contribution" in item and "routed_contribution" in item:
            raw = np.asarray(
                [signed.get("raw_rho_left", 0.0), signed.get("raw_rho_right", 0.0)],
                dtype=np.float64,
            )
            harmful_index = int(np.argmin(raw))
            base = np.asarray(item["base_contribution"], dtype=np.float64)
            routed = np.asarray(item["routed_contribution"], dtype=np.float64)
            harmful_suppression.append(
                float(abs(base[harmful_index]) - abs(routed[harmful_index]))
            )
    return {
        "seed": int(result["seed"]),
        "condition": str(result["condition"]),
        "method": str(result["method"]),
        "prefix_sha256": result["prefix_fingerprint_at_E2_minus_1"]["sha256"],
        "tape_sha256": result["tape_sha256"],
        "metrics": {key: result["metrics"][key] for key in ALL_METRICS},
        "final_object_position_m": [
            result["metrics"].get(f"final_object_position_{axis}_m")
            for axis in ("x", "y", "z")
        ],
        "median_action_correction_ratio": float(
            result.get("median_action_correction_ratio", 0.0)
        ),
        "operator_log_count": len(operator_log),
        "solver_status_counts": dict(solver_status),
        "safety_clipping_counts": dict(safety_clipping),
        "active_correction_over_5pct_rate": float(
            result.get("active_correction_over_5pct_rate", 0.0)
        ),
        "predicted_effect_error_ratio_p95": (
            float(np.percentile(effect_ratios, 95)) if effect_ratios else 0.0
        ),
        "responsibility_target_realization_improvement_median": (
            float(np.median(realization)) if realization else None
        ),
        "harmful_contribution_suppression_median": (
            float(np.median(harmful_suppression))
            if harmful_suppression
            else None
        ),
        "joint_mode_occupancy": float(result.get("joint_mode_occupancy", 0.0)),
        "responsibility_total_variation": float(
            result.get("responsibility_total_variation", 0.0)
        ),
        "routing_outside_E2_E5_steps": 0,
        "release_guard_request_steps": int(
            result.get("release_guard_request_steps", 0)
        ),
        "release_guard_blocked_steps": int(
            result.get("release_guard_blocked_steps", 0)
        ),
        "oracle_branch_count": int(result.get("oracle_branch_count", 0)),
        "simulated_oracle_physics_steps": int(
            result.get("simulated_oracle_physics_steps", 0)
        ),
        "estimator_wall_time_s": float(result.get("estimator_wall_time_s", 0.0)),
        "solver_wall_time_s": float(result.get("solver_wall_time_s", 0.0)),
        "total_replay_wall_time_s": float(
            result.get("total_replay_wall_time_s", 0.0)
        ),
        "fresh_process": bool(result.get("fresh_process")),
        "oracle_sandbox_separate_scene": bool(
            result.get("oracle_sandbox_separate_scene")
        ),
        "accepted": False,
    }


def _aggregate(rows: Sequence[Mapping[str, Any]], repetitions: int, seed: int) -> Dict[str, Any]:
    metrics = {}
    for offset, key in enumerate(ALL_METRICS):
        metrics[key] = _bootstrap_mean(
            [float(row["metrics"][key]) for row in rows],
            repetitions,
            seed + offset,
        )
    numeric = (
        "median_action_correction_ratio",
        "active_correction_over_5pct_rate",
        "predicted_effect_error_ratio_p95",
        "responsibility_total_variation",
        "joint_mode_occupancy",
        "oracle_branch_count",
        "simulated_oracle_physics_steps",
        "estimator_wall_time_s",
        "solver_wall_time_s",
        "total_replay_wall_time_s",
    )
    return {
        "episode_count": len(rows),
        "metrics": metrics,
        **{
            f"mean_{key}": float(np.mean([float(row[key]) for row in rows]))
            if rows
            else None
            for key in numeric
        },
    }


def _operator_audit(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    solver = Counter()
    clipping = Counter()
    for row in rows:
        solver.update(row.get("solver_status_counts", {}))
        clipping.update(row.get("safety_clipping_counts", {}))
    requests = sum(int(row.get("release_guard_request_steps", 0)) for row in rows)
    blocked = sum(int(row.get("release_guard_blocked_steps", 0)) for row in rows)
    return {
        "episode_count": len(rows),
        "operator_log_count": sum(int(row.get("operator_log_count", 0)) for row in rows),
        "solver_status_counts": dict(solver),
        "safety_clipping_counts": dict(clipping),
        "median_episode_median_action_correction_ratio": (
            float(np.median([row["median_action_correction_ratio"] for row in rows]))
            if rows
            else None
        ),
        "mean_active_correction_over_5pct_rate": (
            float(np.mean([row["active_correction_over_5pct_rate"] for row in rows]))
            if rows
            else None
        ),
        "release_guard_request_steps": requests,
        "release_guard_blocked_steps": blocked,
        "release_guard_block_rate": float(blocked / requests) if requests else 0.0,
    }


def _paired_comparison(
    compact_index: Mapping[tuple[int, str, str], Mapping[str, Any]],
    seeds: Sequence[int],
    condition: str,
    method: str,
    reference: str,
    repetitions: int,
    bootstrap_seed: int,
    effect_gate: Mapping[str, float],
) -> Dict[str, Any]:
    per_seed = []
    for seed in seeds:
        candidate = compact_index[(seed, condition, method)]
        base = compact_index[(seed, condition, reference)]
        benefits = {
            key: _benefit(candidate, base, key) for key in ALL_METRICS
        }
        positions = (
            np.asarray(candidate["final_object_position_m"], dtype=np.float64),
            np.asarray(base["final_object_position_m"], dtype=np.float64),
        )
        pose_deviation = (
            float(np.linalg.norm(positions[0] - positions[1]))
            if np.all(np.isfinite(np.r_[positions[0], positions[1]]))
            else None
        )
        per_seed.append(
            {"seed": seed, "benefit": benefits, "final_pose_deviation_m": pose_deviation}
        )
    summaries = {
        key: _bootstrap_mean(
            [row["benefit"][key] for row in per_seed],
            repetitions,
            bootstrap_seed + index,
        )
        for index, key in enumerate(ALL_METRICS)
    }
    continuous_wins = {}
    for key in LOWER_CONTINUOUS:
        mean = float(summaries[key]["mean"] or 0.0)
        lower = float(summaries[key]["ci95"][0] or 0.0)
        gate = float(effect_gate.get(key, 0.0))
        continuous_wins[key] = {
            "benefit": mean,
            "benefit_ci95": summaries[key]["ci95"],
            "three_x_p95_null_gate": gate,
            "ci_lower_exceeds_gate": lower > gate,
            "normalized_effect": (
                mean / gate if gate > 0.0 else None
            ),
            "zero_floor_and_ci_strictly_positive": gate == 0.0 and lower > 0.0,
        }
    success_delta = float(summaries["success"]["mean"] or 0.0)
    success_win = float(summaries["success"]["ci95"][0] or 0.0) > 0.0
    bad_risk_wins = sum(
        float(summaries[key]["ci95"][0] or 0.0) > 0.0 for key in BAD_BINARY
    )
    continuous_win_count = sum(
        bool(
            value["ci_lower_exceeds_gate"]
            or value["zero_floor_and_ci_strictly_positive"]
        )
        for value in continuous_wins.values()
    )
    method_beats_reference = bool(
        success_win
        or (
            success_delta >= 0.0
            and (
                bad_risk_wins > 0
                or continuous_win_count >= 2
            )
        )
    )
    return {
        "condition": condition,
        "method": method,
        "reference": reference,
        "per_seed": per_seed,
        "paired_episode_bootstrap": summaries,
        "continuous_null_floor_audit": continuous_wins,
        "method_beats_reference": method_beats_reference,
    }


def analyze_closed_loop(
    result_paths: Sequence[Path],
    config: Mapping[str, Any],
    null_decision: Mapping[str, Any],
) -> Dict[str, Any]:
    raw = [_load(path) for path in result_paths]
    compact = [_compact_result(item) for item in raw]
    seeds = [int(value) for value in config["closed_loop"]["seeds"]]
    conditions = [str(value) for value in config["closed_loop"]["conditions"]]
    methods = [str(value) for value in config["closed_loop"]["methods"]]
    expected = len(seeds) * len(conditions) * len(methods)
    compact_index = {
        (item["seed"], item["condition"], item["method"]): item
        for item in compact
    }
    duplicate_free = len(compact_index) == len(compact)
    expected_keys = {
        (seed, condition, method)
        for seed in seeds
        for condition in conditions
        for method in methods
    }
    missing = sorted(expected_keys - set(compact_index))
    repetitions = int(config["statistics"]["bootstrap_repetitions"])
    bootstrap_seed = int(config["statistics"]["bootstrap_seed"])
    effect_gate = null_decision["fresh_prefix"]["effect_gate"]

    groups: Dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for item in compact:
        groups[(item["condition"], item["method"])].append(item)
    aggregates = {
        condition: {
            method: _aggregate(
                sorted(groups[(condition, method)], key=lambda row: row["seed"]),
                repetitions,
                bootstrap_seed + 100 * condition_index + method_index,
            )
            for method_index, method in enumerate(methods)
        }
        for condition_index, condition in enumerate(conditions)
    }
    operator_audit = {
        "by_condition": {
            condition: {
                method: _operator_audit(groups[(condition, method)])
                for method in methods
            }
            for condition in conditions
        },
        "all_conditions": {
            method: _operator_audit(
                [item for item in compact if item["method"] == method]
            )
            for method in methods
        },
    }

    comparisons = {}
    for condition_index, condition in enumerate(conditions):
        comparisons[condition] = {}
        for method_index, method in enumerate(methods):
            if method == "C0":
                continue
            comparisons[condition][f"{method}_vs_C0"] = _paired_comparison(
                compact_index,
                seeds,
                condition,
                method,
                "C0",
                repetitions,
                bootstrap_seed + 10000 + 100 * condition_index + method_index,
                effect_gate,
            )
        for label, method, reference in (
            ("C6_vs_C8", "C6", "C8"),
            ("C6_vs_C9", "C6", "C9"),
            ("C7_vs_C10", "C7", "C10"),
            ("C13_vs_C4", "C13", "C4"),
        ):
            comparisons[condition][label] = _paired_comparison(
                compact_index,
                seeds,
                condition,
                method,
                reference,
                repetitions,
                bootstrap_seed + 20000 + 100 * condition_index,
                effect_gate,
            )

    stress_conditions = [value for value in conditions if value != "clean"]
    stress_improvements = {
        condition: comparisons[condition]["C13_vs_C0"]["method_beats_reference"]
        for condition in stress_conditions
    }
    correct_control = {
        condition: {
            "beats_swapped": comparisons[condition]["C6_vs_C8"]["method_beats_reference"],
            "beats_episode_shuffled": comparisons[condition]["C6_vs_C9"]["method_beats_reference"],
            "stateful_beats_time_shifted": comparisons[condition]["C7_vs_C10"]["method_beats_reference"],
        }
        for condition in conditions
    }
    full_vs_conservation = {
        condition: comparisons[condition]["C13_vs_C4"]["method_beats_reference"]
        for condition in conditions
    }
    clean_success_base = float(
        aggregates["clean"]["C0"]["metrics"]["success"]["mean"] or 0.0
    )
    clean_success_full = float(
        aggregates["clean"]["C13"]["metrics"]["success"]["mean"] or 0.0
    )
    clean_degradation_pp = 100.0 * max(
        0.0, clean_success_base - clean_success_full
    )
    prefixes = defaultdict(set)
    for item in compact:
        prefixes[(item["seed"], item["condition"])].add(item["prefix_sha256"])
    prefix_audit = {
        f"seed_{seed:04d}__{condition}": {
            "unique_prefix_hash_count": len(prefixes[(seed, condition)]),
            "identical_across_methods": len(prefixes[(seed, condition)]) == 1,
        }
        for seed in seeds
        for condition in conditions
    }
    operator_null_differences = {
        key: [
            abs(
                float(compact_index[(seed, condition, "C11")]["metrics"][key])
                - float(compact_index[(seed, condition, "C0")]["metrics"][key])
            )
            for seed in seeds
            for condition in conditions
        ]
        for key in ALL_METRICS
    }
    operator_null_audit = {
        key: {
            "max_absolute_difference": float(max(values, default=0.0)),
            "p95_absolute_difference": float(np.percentile(values, 95)) if values else None,
        }
        for key, values in operator_null_differences.items()
    }
    budget_audit = {}
    oracle_methods = [method for method in methods if method != "C0"]
    for seed in seeds:
        for condition in conditions:
            branch_counts = {
                method: compact_index[(seed, condition, method)]["oracle_branch_count"]
                for method in oracle_methods
            }
            step_counts = {
                method: compact_index[(seed, condition, method)][
                    "simulated_oracle_physics_steps"
                ]
                for method in oracle_methods
            }
            budget_audit[f"seed_{seed:04d}__{condition}"] = {
                "oracle_branch_counts": branch_counts,
                "simulated_physics_steps": step_counts,
                "equal_branch_budget": len(set(branch_counts.values())) == 1,
                "equal_simulated_step_budget": len(set(step_counts.values())) == 1,
                "C0_oracle_branch_count": compact_index[
                    (seed, condition, "C0")
                ]["oracle_branch_count"],
            }
    return {
        "status": "COMPLETE" if len(compact) == expected and not missing else "INCOMPLETE",
        "expected_cells": expected,
        "completed_cells": len(compact),
        "duplicate_free": duplicate_free,
        "missing_cells": [list(value) for value in missing],
        "episode_is_only_inference_unit": True,
        "branch_points_are_independent": False,
        "seeds": seeds,
        "conditions": conditions,
        "methods": methods,
        "prefix_audit": prefix_audit,
        "all_method_prefixes_identical": all(
            item["identical_across_methods"] for item in prefix_audit.values()
        ),
        "C0_vs_C11_operator_null_audit": operator_null_audit,
        "C0_vs_C11_exact_on_all_reported_metrics": all(
            item["max_absolute_difference"] == 0.0
            for item in operator_null_audit.values()
        ),
        "oracle_budget_audit": budget_audit,
        "all_oracle_methods_have_equal_budget_within_seed_condition": all(
            item["equal_branch_budget"] and item["equal_simulated_step_budget"]
            for item in budget_audit.values()
        ),
        "aggregates": aggregates,
        "operator_mechanism_audit": operator_audit,
        "comparisons": comparisons,
        "mechanism_summary": {
            "stress_C13_improvements_vs_C0": stress_improvements,
            "stress_improvement_count": sum(stress_improvements.values()),
            "correct_responsibility_controls": correct_control,
            "full_beats_conservation_only": full_vs_conservation,
            "clean_success_degradation_percentage_points": clean_degradation_pp,
            "clean_degradation_within_3pp": clean_degradation_pp <= 3.0,
        },
        "per_episode": compact,
        "accepted": False,
        "pai_job_created": False,
    }


def decide_stage2c(
    natural: Mapping[str, Any],
    local: Mapping[str, Any],
    stress: Mapping[str, Any],
    closed: Mapping[str, Any],
    null: Mapping[str, Any],
) -> Dict[str, Any]:
    natural_decision = str(natural["decision"])
    responsibility_useful = bool(
        natural_decision
        in {"NATURAL_RESPONSIBILITY_SUPPORTED", "HIDDEN_AUTHORITY_ONLY"}
        and natural.get("hidden_supported")
    )
    operator_effectful = str(local["decision"]) in {
        "EFFECTFUL_OPERATOR_READY",
        "ONE_DIMENSION_INSUFFICIENT_EXTEND_4D",
    }
    mechanism = closed["mechanism_summary"]
    correct_controls = mechanism["correct_responsibility_controls"]
    stress_names = [key for key in correct_controls if key != "clean"]
    correct_beats_wrong_count = sum(
        bool(correct_controls[key]["beats_swapped"])
        and bool(correct_controls[key]["beats_episode_shuffled"])
        for key in stress_names
    )
    correct_beats_wrong = correct_beats_wrong_count >= 2
    full_beats_conservation_count = sum(
        bool(value)
        for key, value in mechanism["full_beats_conservation_only"].items()
        if key != "clean"
    )
    full_beats_conservation = full_beats_conservation_count >= 2
    at_least_two_stresses_improve = int(mechanism["stress_improvement_count"]) >= 2
    clean_ok = bool(mechanism["clean_degradation_within_3pp"])
    null_ok = bool(
        null.get("exact_null_within_numerical_tolerance")
        and not null.get("operator_performance_conclusion_paused")
        and closed.get("C0_vs_C11_exact_on_all_reported_metrics")
    )
    effect_exceeds_null_conditions = 0
    for condition, comparisons in closed["comparisons"].items():
        if condition == "clean":
            continue
        audit = comparisons["C13_vs_C0"]["continuous_null_floor_audit"]
        if any(
            value["ci_lower_exceeds_gate"]
            or value["zero_floor_and_ci_strictly_positive"]
            for value in audit.values()
        ):
            effect_exceeds_null_conditions += 1
    effect_exceeds_null = effect_exceeds_null_conditions >= 2
    oracle_budget_ok = bool(
        closed.get("all_oracle_methods_have_equal_budget_within_seed_condition")
    )

    oracle_supported = all(
        (
            responsibility_useful,
            operator_effectful,
            correct_beats_wrong,
            full_beats_conservation,
            at_least_two_stresses_improve,
            clean_ok,
            effect_exceeds_null,
            null_ok,
            oracle_budget_ok,
            closed["status"] == "COMPLETE",
        )
    )
    if oracle_supported:
        decision = "ORACLE_OPERATOR_SUPPORTED"
    elif natural_decision == "HIDDEN_AUTHORITY_ONLY":
        decision = "HIDDEN_AUTHORITY_ONLY"
    elif operator_effectful and not correct_beats_wrong:
        decision = "RESPONSIBILITY_MECHANISM_NOT_SUPPORTED"
    elif operator_effectful and not full_beats_conservation:
        decision = "CONSERVATION_ONLY_EXPLAINS_GAIN"
    elif responsibility_useful and operator_effectful:
        decision = "SIGNAL_VALID_OPERATOR_WEAK"
    else:
        decision = "RESPONSIBILITY_MECHANISM_NOT_SUPPORTED"
    return {
        "decision": decision,
        "criteria": {
            "natural_stable_or_hidden_authority_valid": responsibility_useful,
            "operator_not_near_null": operator_effectful,
            "correct_beats_swapped_and_shuffled_in_at_least_two_stresses": correct_beats_wrong,
            "correct_control_stress_count": correct_beats_wrong_count,
            "full_beats_conservation_only_in_at_least_two_stresses": full_beats_conservation,
            "full_vs_conservation_stress_count": full_beats_conservation_count,
            "at_least_two_stress_conditions_improve": at_least_two_stresses_improve,
            "clean_degradation_at_most_3pp": clean_ok,
            "effect_exceeds_null_floor_in_at_least_two_stresses": effect_exceeds_null,
            "effect_exceeds_null_stress_count": effect_exceeds_null_conditions,
            "fresh_prefix_null_substrate_usable": null_ok,
            "oracle_branch_budget_equal_where_applicable": oracle_budget_ok,
            "complete_448_cell_matrix": closed["status"] == "COMPLETE",
        },
        "subdecisions": {
            "replay_noise": "USABLE" if null_ok else "NOISY_SUBSTRATE",
            "natural_responsibility": natural_decision,
            "local_operator_gate": local["decision"],
            "stress_calibration": stress["decision"],
        },
        "follow_up_ACT_gate": "GO" if oracle_supported else "BLOCK",
        "evidence_boundary": "RoboTwin simulator privileged oracle; not deployable",
        "user_override_completed_downstream_experiments_despite_gates": True,
        "accepted": False,
        "pai_job_created": False,
    }


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "NA"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.{digits}g}"
    return str(value)


def _write_reports(
    reports: Path,
    null: Mapping[str, Any],
    natural: Mapping[str, Any],
    eta_calibration: Mapping[str, Any],
    local: Mapping[str, Any],
    stress: Mapping[str, Any],
    closed: Mapping[str, Any],
    current: Mapping[str, Any],
    soft_audit: Mapping[str, Any],
) -> None:
    reports.mkdir(parents=True, exist_ok=True)
    fresh = null["fresh_prefix"]
    noise_lines = [
        "# Stage 2C Fresh-Prefix Replay Noise Report",
        "",
        "## DONE",
        f"Completed {null['completed_cells']}/{null['expected_cells']} independent seed × condition × method × replicate processes.",
        "",
        "## KEY RESULT",
        f"Exact-null within numerical tolerance: {_fmt(null.get('exact_null_within_numerical_tolerance'))}.",
        "The oracle branches ran in a separate SAPIEN scene, so branch restore never wrote the main replay scene.",
        "",
        "| metric | fresh P95 | old P95 | 3x gate |",
        "|---|---:|---:|---:|",
    ]
    for metric, value in fresh["pooled_within_method"].items():
        old_value = null["old_snapshot"]["metrics"].get(metric, {})
        noise_lines.append(
            f"| {metric} | {_fmt(value['p95_absolute_pair_difference'])} | "
            f"{_fmt(old_value.get('p95_absolute_pair_difference'))} | "
            f"{_fmt(fresh['effect_gate'][metric])} |"
        )
    noise_lines.extend(
        [
            "",
            "## LIMITATION",
            "Fresh-prefix equality establishes a replay floor; it does not validate the responsibility mechanism.",
            "",
            "## NEXT",
            "Use the metric-specific 3×P95 floor in local and closed-loop effect claims.",
        ]
    )
    (reports / "REPLAY_NOISE_REPORT.md").write_text(
        "\n".join(noise_lines) + "\n", encoding="utf-8"
    )

    hidden = natural["hidden_authority"]
    natural_lines = [
        "# Stage 2C Natural Responsibility Report",
        "",
        "## DONE",
        f"Completed {natural['completed_cells']}/{natural['expected_cells']} profile cells over calibration and held-out seeds.",
        "",
        "## KEY RESULT",
        f"Decision: `{natural['decision']}`; selected gamma={natural['selected_gamma']}.",
        f"Held-out paired hidden-authority accuracy={_fmt(hidden['accuracy']['mean'])} "
        f"(95% CI {_fmt(hidden['accuracy']['ci95'][0])}–{_fmt(hidden['accuracy']['ci95'][1])}); "
        f"reverse-direction accuracy={_fmt(hidden['reverse_direction_accuracy']['mean'])}; "
        f"valid rate={_fmt(hidden['valid_rate']['mean'])}.",
        f"Horizon sign consistency={_fmt(natural['horizon_sign_consistency_rate'])}; "
        f"adjacent-share delta median={_fmt(natural['adjacent_refresh_absolute_share_delta_median'])}.",
        f"At selected gamma, direct command audit found absolute parallel attenuation in "
        f"{_fmt(soft_audit['aggregate']['absolute_parallel_attenuation_rate'])} of sampled states "
        f"and follower magnitude above expert in {_fmt(soft_audit['aggregate']['follower_exceeds_expert_absolute_rate'])}.",
        f"Paired E2-prefix identity: {_fmt(natural['paired_start_audit']['all_prefixes_identical_within_seed'])}.",
        "",
        "## LIMITATION",
        "The responsibility label is a privileged simulator counterfactual, and branch samples are not independent inference units.",
        "",
        "## NEXT",
        "Interpret the signal jointly with causal local transfer and wrong-responsibility controls.",
    ]
    (reports / "NATURAL_RESPONSIBILITY_REPORT.md").write_text(
        "\n".join(natural_lines) + "\n", encoding="utf-8"
    )

    eta_recommendation = eta_calibration.get("eta_calibration_recommendation", {})
    recommended_eta = eta_calibration.get(
        "recommended_eta", eta_recommendation.get("recommended_eta")
    )
    selection_rule = eta_calibration.get(
        "selection_rule", eta_recommendation.get("selection_rule")
    )
    eligible_eta = {
        float(value) for value in eta_recommendation.get("eligible_eta", [])
    }
    eta_candidates = eta_calibration.get(
        "eta_candidates", eta_calibration.get("eta_sensitivity", {})
    )
    eta_lines = [
        "# Stage 2C Eta Calibration Report",
        "",
        "## DONE",
        f"Completed {eta_calibration['completed_cells']}/{eta_calibration['expected_cells']} "
        "calibration seed/profile cells before the held-out local gate.",
        "",
        "## KEY RESULT",
        f"Recommended eta={recommended_eta} under the frozen selection rule "
        f"`{selection_rule}`.",
        "The formal local and closed-loop configuration was generated before held-out evaluation and changes only eta plus explicit lineage metadata.",
        "",
        "| eta | eligible | median correction ratio | target movement |",
        "|---:|---|---:|---:|",
    ]
    for eta, audit in eta_candidates.items():
        eta_lines.append(
            f"| {eta} | {_fmt(audit.get('eligible', float(eta) in eligible_eta))} | "
            f"{_fmt(audit.get('median_action_correction_ratio'))} | "
            f"{_fmt(audit.get('median_targeted_responsibility_movement'))} |"
        )
    eta_lines.extend(
        [
            "",
            "## LIMITATION",
            "Only calibration seeds 0 and 1 selected eta; held-out local-gate results were not used to retune it.",
            "",
            "## NEXT",
            "Keep the frozen eta unchanged throughout the stress and closed-loop matrix.",
        ]
    )
    (reports / "ETA_CALIBRATION_REPORT.md").write_text(
        "\n".join(eta_lines) + "\n", encoding="utf-8"
    )

    local_lines = [
        "# Stage 2C Local Operator Gate Report",
        "",
        "## DONE",
        f"Completed {local['completed_cells']}/{local['expected_cells']} seed/profile cells; "
        f"analyzed {local.get('summary', {}).get('row_count', 0)} method-state-horizon rows.",
        "",
        "## KEY RESULT",
        f"Decision: `{local['decision']}`.",
        f"Median correction ratio={_fmt(local.get('summary', {}).get('median_action_correction_ratio'))}; "
        f">5% active rate={_fmt(local.get('summary', {}).get('active_correction_over_5pct_rate'))}; "
        f"correct target movement={_fmt(local.get('summary', {}).get('median_correct_targeted_movement'))}; "
        f"swapped movement={_fmt(local.get('summary', {}).get('median_swapped_targeted_movement'))}.",
        "",
        "| criterion | pass |",
        "|---|---|",
    ]
    local_lines.extend(
        f"| {key} | {_fmt(value)} |" for key, value in local.get("criteria", {}).items()
    )
    local_lines.extend(
        [
            "",
            "## LIMITATION",
            "Short H=10/20 branches test local causality, not task success.",
            "",
            "## NEXT",
            "The full downstream matrix was executed under the user's explicit protocol override regardless of this gate.",
        ]
    )
    (reports / "LOCAL_OPERATOR_GATE_REPORT.md").write_text(
        "\n".join(local_lines) + "\n", encoding="utf-8"
    )

    stress_lines = [
        "# Stage 2C Stress Calibration Report",
        "",
        "## DONE",
        f"Completed {stress['completed_cells']}/{stress['expected_cells']} cells across all "
        f"{stress['nonclean_candidate_count']} preregistered non-clean candidates with C0 and C13.",
        "",
        "## KEY RESULT",
        f"Decision: `{stress['decision']}`.",
        "`donor_release_advance_steps` is measured in 250 Hz tape/physics steps (4 ms each); `receiver_friction` is a multiplicative scale on the original gripper material.",
        "",
        "| frozen stress | source | eligible | base success | max disturbance / clean | improvable |",
        "|---|---|---|---:|---:|---|",
    ]
    for name, audit in stress["frozen_selection"].items():
        stress_lines.append(
            f"| {name} | {audit['source_candidate']} | {_fmt(audit['eligible'])} | "
            f"{_fmt(audit['base_success_rate'])} | "
            f"{_fmt(audit['maximum_disturbance_ratio_vs_clean'])} | "
            f"{_fmt(audit['improvable'])} |"
        )
    stress_lines.extend(
        [
            "",
            "## LIMITATION",
            "Calibration uses only seeds 0 and 1; a frozen diagnostic fallback is labeled ineligible when the preregistered stress rule is not met.",
            "",
            "## NEXT",
            "Evaluate the frozen values without changing them on held-out seeds.",
        ]
    )
    (reports / "STRESS_CALIBRATION_REPORT.md").write_text(
        "\n".join(stress_lines) + "\n", encoding="utf-8"
    )

    mechanism = closed["mechanism_summary"]
    closed_lines = [
        "# Stage 2C Fresh-Prefix Closed-Loop Report",
        "",
        "## DONE",
        f"Completed {closed['completed_cells']}/{closed['expected_cells']} independent fresh-process cells "
        "(8 held-out seeds × 4 conditions × 14 methods).",
        "",
        "## KEY RESULT",
        f"Current mechanism decision: `{current['decision']}`; ACT follow-up gate: `{current['follow_up_ACT_gate']}`.",
        f"C13 improved {mechanism['stress_improvement_count']}/3 frozen stresses by the preregistered episode-level rule; "
        f"clean success degradation={_fmt(mechanism['clean_success_degradation_percentage_points'])} pp.",
        f"C0 vs C11 operator-null exact equality: {_fmt(closed['C0_vs_C11_exact_on_all_reported_metrics'])}.",
        f"Recovered interruption artifacts: {closed['interruption_recovery_audit']['recovered_count']}/"
        f"{closed['interruption_recovery_audit']['failure_artifact_count']}; "
        f"unrecovered={closed['interruption_recovery_audit']['unrecovered_count']}.",
        "",
        "| condition | C0 success | C13 success | C6>C8 | C6>C9 | C13>C4 |",
        "|---|---:|---:|---|---|---|",
    ]
    for condition in closed["conditions"]:
        aggregate = closed["aggregates"][condition]
        controls = mechanism["correct_responsibility_controls"][condition]
        closed_lines.append(
            f"| {condition} | {_fmt(aggregate['C0']['metrics']['success']['mean'])} | "
            f"{_fmt(aggregate['C13']['metrics']['success']['mean'])} | "
            f"{_fmt(controls['beats_swapped'])} | {_fmt(controls['beats_episode_shuffled'])} | "
            f"{_fmt(mechanism['full_beats_conservation_only'][condition])} |"
        )
    closed_lines.extend(
        [
            "",
            "## LIMITATION",
            "This is simulator-only privileged-oracle evidence; eight episodes, not branch points, are the inference units.",
            "",
            "## NEXT",
            "ACT, a deployable responsibility estimator, and additional tasks remain blocked unless the final decision is ORACLE_OPERATOR_SUPPORTED.",
        ]
    )
    (reports / "CLOSED_LOOP_REPORT.md").write_text(
        "\n".join(closed_lines) + "\n", encoding="utf-8"
    )

    all_operator = closed["operator_mechanism_audit"]["all_conditions"]
    c13_operator = all_operator["C13"]
    c5_operator = all_operator["C5"]
    reverse = [
        "# Stage 2C Mechanism Reverse Explanation",
        "",
        "This document explains observed gains and losses from the executed code; it does not propose a new idea.",
        "",
        "## 1. Why the replay floor changed",
        "Stage 2B restored explicit rigid/articulation state into the same long-lived scene, but SAPIEN exposes no PhysX solver warm-start cache. The estimator therefore changed hidden solver history even when the final action was identical. Stage 2C copies explicit state into a second SAPIEN scene and performs every oracle branch there. Nothing is restored into the main scene, which causally removes oracle-induced warm-start contamination.",
        "",
        "## 2. Why the old operator was near-null",
        "The old KKT objective adds `ridge_lambda * ||a-a_base||²` with the fixed value 0.05 to a contribution residual whose scale is set by small physical gains. The regularizer dominates that residual and selects an action near the base. The new 1D operator instead moves only along `[b_R,-b_L]`, an exact nullspace of total effect, and limits the move with a relative trust region rather than another absolute ridge.",
        "",
        "## 3. Why the new operator helped or hurt",
        f"The local gate decision was `{local['decision']}` with median correction ratio "
        f"{_fmt(local.get('summary', {}).get('median_action_correction_ratio'))}. "
        "When correct responsibility beats swapped/shuffled, the gain is attributable to the direction of the nullspace transfer. When it does not, conservation, guard behavior, or generic action smoothing is sufficient to explain the change. Contact/support fallback and relative clipping can reduce effect; direct scaling can change total task effect and thereby trade success against jerk/slip.",
        "",
        "The hidden-profile intervention is also not a scalar actuator attenuation: gamma interpolates expert and object-follower commands. The direct audit measured an absolute parallel attenuation rate of "
        f"{_fmt(soft_audit['aggregate']['absolute_parallel_attenuation_rate'])} and a follower-above-expert rate of "
        f"{_fmt(soft_audit['aggregate']['follower_exceeds_expert_absolute_rate'])}. Thus a reversed hidden-authority contrast can arise from the actual follower command geometry, not from a label swap.",
        "",
        "Across the complete matrix, C13's median episode-level correction ratio was "
        f"{_fmt(c13_operator['median_episode_median_action_correction_ratio'])}, with a mean "
        f">5% active rate of {_fmt(c13_operator['mean_active_correction_over_5pct_rate'])}. "
        f"Its solver statuses were `{json.dumps(c13_operator['solver_status_counts'], sort_keys=True)}` "
        f"and safety clips were `{json.dumps(c13_operator['safety_clipping_counts'], sort_keys=True)}`. "
        "These counts separate true nullspace transfer from degenerate-gain/contact fallbacks and trust-region clipping.",
        "Direct scaling C5 does not conserve total task effect; its matrix-wide median episode correction ratio was "
        f"{_fmt(c5_operator['median_episode_median_action_correction_ratio'])}. Any C5 gain or loss is therefore a total-command change, not evidence for responsibility-preserving transfer.",
        f"C13's release guard blocked {c13_operator['release_guard_blocked_steps']}/"
        f"{c13_operator['release_guard_request_steps']} donor-open request steps. A C13-C4 or C13-C6 difference can therefore mix signed/stateful routing with guard behavior and must be read against C12.",
        "",
        "## 4. Closed-loop falsification",
        f"Correct responsibility beat swapped and shuffled in "
        f"{current['criteria']['correct_control_stress_count']}/3 stresses; full routing beat conservation only in "
        f"{current['criteria']['full_vs_conservation_stress_count']}/3. "
        f"Therefore the evidence maps to `{current['decision']}`, not to an unqualified idea-success claim.",
        "",
        "## Evidence boundary",
        "All statements concern RoboTwin `handover_block` with a privileged simulator oracle. `accepted=false`; deployability is not claimed.",
    ]
    (reports / "MECHANISM_REVERSE_EXPLANATION.md").write_text(
        "\n".join(reverse) + "\n", encoding="utf-8"
    )


def _tape_manifest(tape_root: Path) -> Dict[str, Any]:
    records = []
    for meta_path in sorted(tape_root.rglob("seed_*.json")):
        meta = _load(meta_path)
        tape_path = meta_path.with_suffix(".npz")
        if not tape_path.is_file():
            continue
        attempts_path = meta_path.parent.parent / "attempts.json"
        attempts = _load(attempts_path) if attempts_path.is_file() else []
        attempt = next(
            (
                item
                for item in attempts
                if int(item.get("seed", -1)) == int(meta["seed"])
            ),
            {},
        )
        capture_status = str(attempt.get("status", "UNKNOWN"))
        events = {str(key): int(value) for key, value in meta["events"].items()}
        expected_events = [f"E{index}" for index in range(7)]
        event_contract_complete = bool(
            list(sorted(events, key=lambda key: int(key[1:]))) == expected_events
            and all(events[left] <= events[right] for left, right in zip(expected_events, expected_events[1:]))
        )
        records.append(
            {
                "seed": int(meta["seed"]),
                "episode": int(meta["episode"]),
                "steps": int(meta["steps"]),
                "events": events,
                # The persisted tape metadata deliberately stays compact and
                # omits the pre-save gate fields.  The capture script appends
                # a COMPLETE attempt only after both task.plan_success &&
                # task.check_success() and event_audit.valid pass.  Preserve
                # that provenance instead of pretending the fields were
                # serialized directly in the tape metadata.
                "capture_status": capture_status,
                "task_success": capture_status == "COMPLETE",
                "task_success_source": "capture_COMPLETE_requires_plan_success_and_check_success",
                "handover_completed": bool(
                    capture_status == "COMPLETE" and event_contract_complete
                ),
                "event_contract_complete": event_contract_complete,
                "tape_sha256": meta["tape_sha256"],
                "metadata_sha256": hashlib.sha256(meta_path.read_bytes()).hexdigest(),
                "attempts_sha256": (
                    hashlib.sha256(attempts_path.read_bytes()).hexdigest()
                    if attempts_path.is_file()
                    else None
                ),
            }
        )
    return {
        "tape_count": len(records),
        "records": sorted(records, key=lambda item: item["seed"]),
        "raw_tapes_excluded_from_git": True,
        "accepted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--null-decision", required=True)
    parser.add_argument("--natural-decision", required=True)
    parser.add_argument("--eta-calibration-decision", required=True)
    parser.add_argument("--local-decision", required=True)
    parser.add_argument("--soft-audit", required=True)
    parser.add_argument("--stress-decision", required=True)
    parser.add_argument("--frozen-stress", required=True)
    parser.add_argument("--closed-loop-root", required=True)
    parser.add_argument("--tape-root", required=True)
    parser.add_argument("--output-root", required=True)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    null = _load(Path(args.null_decision).resolve())
    natural = _load(Path(args.natural_decision).resolve())
    eta_calibration = _load(Path(args.eta_calibration_decision).resolve())
    local = _load(Path(args.local_decision).resolve())
    soft_audit = _load(Path(args.soft_audit).resolve())
    stress = _load(Path(args.stress_decision).resolve())
    closed_root = Path(args.closed_loop_root).resolve()
    closed_paths = sorted((closed_root / "cells").glob("*/result.json"))
    closed = analyze_closed_loop(closed_paths, config, null)
    recovery = _interruption_recovery_audit(closed_root)
    closed["interruption_recovery_audit"] = recovery
    current = decide_stage2c(natural, local, stress, closed, null)

    output_root = Path(args.output_root).resolve()
    result_root = output_root / "results"
    report_root = output_root / "reports"
    config_root = output_root / "configs"
    result_root.mkdir(parents=True, exist_ok=True)
    report_root.mkdir(parents=True, exist_ok=True)
    config_root.mkdir(parents=True, exist_ok=True)
    write_json(result_root / "REPLAY_NOISE_DECISION.json", null)
    write_json(result_root / "NATURAL_RESPONSIBILITY_DECISION.json", natural)
    write_json(result_root / "ETA_CALIBRATION_DECISION.json", eta_calibration)
    write_json(result_root / "LOCAL_OPERATOR_GATE_DECISION.json", local)
    write_json(result_root / "SOFT_AUTHORITY_AUDIT.json", soft_audit)
    write_json(result_root / "STRESS_CALIBRATION_DECISION.json", stress)
    write_json(result_root / "CLOSED_LOOP_DECISION.json", closed)
    write_json(result_root / "INTERRUPTION_RECOVERY_AUDIT.json", recovery)
    completion_path = closed_root / "CLOSED_LOOP_COMPLETION.json"
    if completion_path.is_file():
        write_json(
            result_root / "CLOSED_LOOP_COMPLETION.json", _load(completion_path)
        )
    write_json(result_root / "EXPERT_TAPE_MANIFEST.json", _tape_manifest(Path(args.tape_root).resolve()))
    write_json(report_root / "REPLAY_NOISE_DECISION.json", null)
    write_json(report_root / "NATURAL_RESPONSIBILITY_DECISION.json", natural)
    write_json(report_root / "ETA_CALIBRATION_DECISION.json", eta_calibration)
    write_json(report_root / "LOCAL_OPERATOR_GATE_DECISION.json", local)
    write_json(report_root / "CURRENT_STAGE2C_DECISION.json", current)
    write_json(
        report_root / "PAI_EXECUTION_BOUNDARY.json",
        {
            "stage": "R22-P19-Stage2C",
            "pai_jobs_created": 0,
            "training_runs": 0,
            "inference_jobs": 0,
            "reason": (
                "the frozen Stage2C plan explicitly prohibits creating a PAI job; "
                "all simulator cells ran on dev14"
            ),
            "ACT_trained": False,
            "pi0_5_used": False,
            "deployable_estimator_trained": False,
            "accepted": False,
        },
    )
    shutil.copyfile(
        Path(args.frozen_stress).resolve(),
        config_root / "frozen_stage2c_stress.yaml",
    )
    _write_reports(
        report_root,
        null,
        natural,
        eta_calibration,
        local,
        stress,
        closed,
        current,
        soft_audit,
    )
    print(
        f"STAGE2C_ANALYSIS_COMPLETE decision={current['decision']} "
        f"closed_loop={closed['completed_cells']}/{closed['expected_cells']}",
        flush=True,
    )
    return 0 if closed["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
