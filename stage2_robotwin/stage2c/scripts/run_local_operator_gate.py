"""Short-horizon local causal gate for old/new responsibility operators."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence, Tuple

import numpy as np
import yaml

from stage2_robotwin.responsibility.oracle import decompose_outcomes
from stage2_robotwin.responsibility.oracle_brancher import (
    _joint_neutral_state,
    capture_outcome_origin,
    measure_outcome,
)
from stage2_robotwin.stage2b.baselines.direct_scale import direct_scale_action
from stage2_robotwin.stage2b.intervention.task_frame import ObjectTaskFrame
from stage2_robotwin.stage2b.operator.effect_conserving_transfer_1d import (
    OneDimensionalEffectConservingTransfer,
)
from stage2_robotwin.stage2b.operator.local_effect_gain import (
    SimulatorLocalEffectEstimator,
    task_direction_joint_delta,
)
from stage2_robotwin.stage2c.intervention.soft_expert_authority import (
    SoftExpertAuthorityProfile,
)
from stage2_robotwin.stage2c.operator.effect_nullspace_transfer_1d import (
    EffectNullspaceTransfer1D,
)
from stage2_robotwin.stage2c.replay.fresh_prefix_runner import (
    _prefix_fingerprint,
    write_json,
)
from stage2_robotwin.stage2c.replay.tape import ExpertTape
from stage2_robotwin.stage2c.responsibility.signed_joint_state import (
    classify_signed_responsibility,
)
from stage2_robotwin.stage2c.responsibility.temporal_filter import (
    StatefulResponsibilityFilter,
    project_simplex2,
)
from stage2_robotwin.wrappers.counterfactual_brancher import (
    BRANCHES,
    SapienSnapshot,
    gripper_object_contacts,
    object_state,
)
from stage2_robotwin.wrappers.robotwin_runtime import build_handover_block


METHODS = ("L0", "L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8")


def discover_tapes(root: Path) -> Dict[int, tuple[Path, Path]]:
    result = {}
    for tape in root.rglob("seed_*.npz"):
        meta = tape.with_suffix(".json")
        if not meta.is_file():
            continue
        seed = int(json.loads(meta.read_text(encoding="utf-8"))["seed"])
        if seed in result:
            raise ValueError(f"duplicate tape seed {seed}")
        result[seed] = (tape, meta)
    return result


def _projected_effect(outcome: Mapping[str, Any], frame: ObjectTaskFrame) -> float:
    return float(np.asarray(outcome["translation"], dtype=np.float64) @ np.asarray(frame.e_parallel))


def _routed_action(
    method: str,
    estimate: Mapping[str, Any],
    share: Sequence[float],
    config: Mapping[str, Any],
    eta: float,
) -> tuple[np.ndarray, Dict[str, Any]]:
    base = np.asarray(estimate["base_action"], dtype=np.float64)
    gain = np.asarray(estimate["local_gain"], dtype=np.float64)
    share = np.asarray(share, dtype=np.float64)
    if method == "L0":
        return base.copy(), {"solver_status": "BASE", "action_correction_ratio": 0.0, "effect_error": 0.0, "effect_error_ratio": 0.0}
    if method == "L1":
        old = OneDimensionalEffectConservingTransfer(
            ridge_lambda=float(config["operator"]["old_ridge_lambda"]),
            trust_region_m=0.002,
            action_bound_m=float(config["operator"]["scalar_action_bound_m"]),
            effect_tolerance_m=1e-6,
        ).solve(base, gain, share)
        action = np.asarray([old.action_left, old.action_right])
        audit = old.as_dict()
        audit["action_correction_ratio"] = float(np.linalg.norm(action - base) / max(np.linalg.norm(base), 5e-4))
        audit["effect_error_ratio"] = abs(float(old.effect_error)) / max(abs(float(gain @ base)), 1e-8)
        return action, audit
    if method == "L3":
        action = direct_scale_action(base, share)
        total = float(gain @ base)
        routed = float(gain @ action)
        return action, {
            "solver_status": "DIRECT_SCALE_NO_CONSERVATION",
            "action_correction_ratio": float(np.linalg.norm(action - base) / max(np.linalg.norm(base), 5e-4)),
            "effect_error": routed - total,
            "effect_error_ratio": abs(routed - total) / max(abs(total), 1e-8),
        }
    new = EffectNullspaceTransfer1D(
        eta=eta,
        relative_trust_region=float(config["operator"]["relative_trust_region"]),
        action_floor_m=float(config["operator"]["action_floor_m"]),
        action_bound_m=float(config["operator"]["scalar_action_bound_m"]),
        effect_relative_tolerance=float(config["operator"]["effect_relative_tolerance"]),
    ).solve(
        base,
        gain,
        share,
        contact_ok=bool(estimate["contact_ok"]),
        support_height_m=float(estimate["support_height_m"]),
        min_support_height_m=float(config["operator"]["min_support_height_m"]),
    )
    return new.action, new.as_dict()


def _local_rollout(
    task: Any,
    snapshot: Mapping[str, Any],
    origin: Mapping[str, Any],
    target_sequence: Sequence[Mapping[str, Any]],
    gripper_sequence: Sequence[Mapping[str, Any]],
    branch: str,
    frame: ObjectTaskFrame,
    correction: Sequence[float],
    horizon: int,
    soft_arm: str | None,
    gamma: float | None,
) -> Dict[str, Any]:
    SapienSnapshot.restore(task, snapshot)
    neutral = {side: _joint_neutral_state(task, side) for side in ("left", "right")}
    joint_delta = {}
    for index, side in enumerate(("left", "right")):
        joint_delta[side], _ = task_direction_joint_delta(
            task, side, frame.e_parallel, float(correction[index])
        )
    soft = SoftExpertAuthorityProfile(task, soft_arm, float(gamma), frame) if soft_arm is not None and gamma is not None else None
    positions = []
    linear = []
    angular = []
    contacts = []
    for index in range(horizon):
        for side in ("left", "right"):
            active = branch == "LR" or branch == side[0].upper()
            if active:
                position = np.asarray(target_sequence[index][side][0], dtype=np.float64)
                velocity = np.asarray(target_sequence[index][side][1], dtype=np.float64)
                if soft is not None and side == soft.soft_arm:
                    (position, velocity), _ = soft.blend((position, velocity))
                position = position + joint_delta[side]
            else:
                position, velocity = neutral[side]
            task.robot.set_arm_joints(position, velocity, side)
            command = gripper_sequence[index][side]
            if command is not None:
                task.robot.set_gripper(command[0], side, command[1])
        task.scene.step()
        state = object_state(task)
        positions.append(state["pose"][:3])
        linear.append(state["linear_velocity"])
        angular.append(state["angular_velocity"])
        current = gripper_object_contacts(task)
        contacts.append([current["left"], current["right"]])
    outcome = measure_outcome(task, origin)
    position_array = np.asarray(positions)
    linear_array = np.asarray(linear)
    angular_array = np.asarray(angular)
    jerk = np.diff(linear_array, axis=0) * 250.0 if len(linear_array) > 1 else np.zeros((0, 3))
    outcome.update(
        {
            "peak_angular_velocity": float(np.linalg.norm(angular_array, axis=1).max(initial=0.0)),
            "peak_linear_jerk": float(np.linalg.norm(jerk, axis=1).max(initial=0.0)),
            "min_height_m": float(position_array[:, 2].min(initial=np.inf)),
            "both_contact_rate": float(np.mean(np.all(np.asarray(contacts), axis=1))),
        }
    )
    return outcome


def run_local_cell(cell: Mapping[str, Any]) -> Dict[str, Any]:
    output = Path(cell["output"])
    if (output / "result.json").is_file():
        return json.loads((output / "result.json").read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=True)
    config = yaml.safe_load(Path(cell["config"]).read_text(encoding="utf-8"))
    tape = ExpertTape.load(cell["tape"])
    meta = json.loads(Path(cell["meta"]).read_text(encoding="utf-8"))
    seed = int(meta["seed"])
    episode = int(meta["episode"])
    events = {key: int(value) for key, value in meta["events"].items()}
    profile = str(cell["profile"])
    soft_arm = meta["receiver"] if profile != "clean" else None
    gamma = 0.6 if soft_arm else None
    task = sandbox = None
    started = time.perf_counter()
    try:
        task, task_args = build_handover_block(str(cell["robotwin_root"]), planner="mplib_screw")
        task.setup_demo(now_ep_num=episode, seed=seed, **task_args)
        sandbox, sandbox_args = build_handover_block(str(cell["robotwin_root"]), planner="mplib_screw")
        sandbox.setup_demo(now_ep_num=episode, seed=seed, **sandbox_args)
        frame = ObjectTaskFrame.from_task(task)
        estimator = SimulatorLocalEffectEstimator(
            int(config["operator"]["oracle_horizon_steps"]),
            float(config["operator"]["finite_difference_delta_m"]),
        )
        sample_steps = list(
            np.linspace(
                events["E4"] + int(config["local_gate"]["window_start_relative_to_E4"]),
                events["E4"] + int(config["local_gate"]["window_end_relative_to_E4"]),
                int(config["local_gate"]["states_per_seed"]),
                dtype=int,
            )
        )
        samples = []
        soft = None
        prefix = None
        for index in range(len(tape)):
            item = tape.item(index)
            step = int(item["step"])
            if step == events["E2"]:
                prefix = _prefix_fingerprint(task, step - 1)
                if soft_arm:
                    soft = SoftExpertAuthorityProfile(task, soft_arm, gamma, frame)
            targets = {
                "left": (item["left_position"], item["left_velocity"]),
                "right": (item["right_position"], item["right_velocity"]),
            }
            if events["E2"] <= step <= events["E5"] and soft is not None:
                targets[soft_arm], _ = soft.blend(targets[soft_arm])
            if step in sample_steps:
                snapshot = SapienSnapshot.capture(task)
                SapienSnapshot.restore(sandbox, snapshot)
                estimate = estimator.estimate(sandbox, targets["left"], targets["right"], frame)
                estimate["contact_ok"] = bool(
                    all(gripper_object_contacts(task).values())
                )
                estimate["support_height_m"] = float(
                    object_state(task)["pose"][2]
                )
                max_horizon = max(int(value) for value in config["local_gate"]["horizons"])
                sequence = tape.target_sequence(step, max_horizon)
                grippers = []
                for future in range(step, step + max_horizon):
                    future_item = tape.item(future)
                    grippers.append({"left": future_item["left_gripper"], "right": future_item["right_gripper"]})
                samples.append({"step": step, "snapshot": snapshot, "estimate": estimate, "sequence": sequence, "grippers": grippers})
            for side in ("left", "right"):
                task.robot.set_arm_joints(*targets[side], side)
                command = item[f"{side}_gripper"]
                if command is not None:
                    task.robot.set_gripper(command[0], side, command[1])
            task.scene.step()

        estimates = [sample["estimate"] for sample in samples]
        shifted = np.roll(np.arange(len(samples)), 2)
        shuffled_by_relative = {
            int(key): np.asarray(value, dtype=np.float64)
            for key, value in cell["shuffle_share_by_relative"].items()
        }
        stateful = StatefulResponsibilityFilter(
            beta=float(config["responsibility_control"]["stateful_beta"]),
            max_share_change=float(config["responsibility_control"]["max_share_change_per_refresh"]),
        )
        stateful_shares = []
        for estimate in estimates:
            signed = classify_signed_responsibility(estimate["rho_left"], estimate["rho_right"], estimate["rho_joint"])
            stateful_shares.append(stateful.update(signed.target_share))

        records = []
        eta_candidates = [float(value) for value in config["operator"]["eta_candidates"]]
        selected_eta = float(config["operator"]["selected_eta"])
        for sample_index, sample in enumerate(samples):
            estimate = sample["estimate"]
            signed = classify_signed_responsibility(estimate["rho_left"], estimate["rho_right"], estimate["rho_joint"])
            instant = project_simplex2([estimate["rho_left"], estimate["rho_right"]])
            shares = {
                "L0": instant,
                "L1": instant,
                "L2": np.asarray([0.5, 0.5]),
                "L3": instant,
                "L4": signed.target_share,
                "L5": signed.target_share[::-1],
                "L6": shuffled_by_relative[sample["step"] - events["E4"]],
                "L7": classify_signed_responsibility(
                    estimates[int(shifted[sample_index])]["rho_left"],
                    estimates[int(shifted[sample_index])]["rho_right"],
                    estimates[int(shifted[sample_index])]["rho_joint"],
                ).target_share,
                "L8": stateful_shares[sample_index],
            }
            method_variants = [(method, selected_eta) for method in METHODS]
            method_variants.extend((f"L4_eta_{eta}", eta) for eta in eta_candidates if eta != selected_eta)
            by_variant = {}
            for method_label, eta in method_variants:
                method = "L4" if method_label.startswith("L4_eta_") else method_label
                action, solver = _routed_action(method, estimate, shares[method], config, eta)
                correction = action - np.asarray(estimate["base_action"], dtype=np.float64)
                by_horizon = {}
                for horizon in (int(value) for value in config["local_gate"]["horizons"]):
                    origin_task_snapshot = sample["snapshot"]
                    SapienSnapshot.restore(sandbox, origin_task_snapshot)
                    origin = capture_outcome_origin(sandbox)
                    outcomes = {}
                    for branch in BRANCHES:
                        outcomes[branch] = _local_rollout(
                            sandbox,
                            origin_task_snapshot,
                            origin,
                            sample["sequence"],
                            sample["grippers"],
                            branch,
                            frame,
                            correction,
                            horizon,
                            soft_arm,
                            gamma,
                        )
                    decomposition = decompose_outcomes(outcomes)
                    by_horizon[str(horizon)] = {
                        "outcomes": outcomes,
                        "responsibility": decomposition,
                        "realized_total_effect": _projected_effect(outcomes["LR"], frame),
                        "rho_left": decomposition["three_channel"]["rho_left"],
                        "rho_right": decomposition["three_channel"]["rho_right"],
                        "rho_joint": decomposition["three_channel"]["rho_joint"],
                    }
                by_variant[method_label] = {
                    "eta": eta,
                    "target_share": shares[method].tolist(),
                    "action": action.tolist(),
                    "correction": correction.tolist(),
                    "solver": solver,
                    "by_horizon": by_horizon,
                }
            records.append(
                {
                    "step": sample["step"],
                    "e4_relative_step": sample["step"] - events["E4"],
                    "oracle": {
                        "rho_left": estimate["rho_left"],
                        "rho_right": estimate["rho_right"],
                        "rho_joint": estimate["rho_joint"],
                        "base_action": estimate["base_action"],
                        "local_gain": estimate["local_gain"],
                        "signed": signed.as_dict(),
                    },
                    "variants": by_variant,
                }
            )

        result = {
            "status": "COMPLETE",
            "seed": seed,
            "episode": episode,
            "profile": profile,
            "soft_arm": soft_arm,
            "gamma": gamma,
            "sample_count": len(records),
            "records": records,
            "reference_events": events,
            "tape_sha256": meta["tape_sha256"],
            "prefix_fingerprint_at_E2_minus_1": prefix,
            "oracle_sandbox_separate_scene": True,
            "episode_shuffle_source_seed": int(cell["shuffle_source_seed"]),
            "wall_time_s": time.perf_counter() - started,
            "accepted": False,
            "pai_job_created": False,
        }
        write_json(output / "result.json", result)
        return result
    finally:
        for value in (sandbox, task):
            if value is not None:
                try:
                    value.close_env(clear_cache=True)
                except Exception:
                    pass


def analyze_local_gate(cells: Sequence[Mapping[str, Any]], null_floor: Mapping[str, Any], config: Mapping[str, Any]) -> Dict[str, Any]:
    selected_eta = float(config["operator"]["selected_eta"])
    rows = []
    eta_rows: Dict[str, list[Dict[str, float]]] = {
        str(float(value)): [] for value in config["operator"]["eta_candidates"]
    }
    for cell in cells:
        for record in cell["records"]:
            for horizon in (str(value) for value in config["local_gate"]["horizons"]):
                base = record["variants"]["L0"]["by_horizon"][horizon]
                for method in METHODS:
                    variant = record["variants"][method]
                    result = variant["by_horizon"][horizon]
                    base_effect = float(base["realized_total_effect"])
                    realized_effect = float(result["realized_total_effect"])
                    base_left = float(base["rho_left"])
                    realized_left = float(result["rho_left"])
                    correct_target_left = float(
                        record["variants"]["L4"]["target_share"][0]
                    )
                    target_direction = np.sign(correct_target_left - base_left)
                    rows.append(
                        {
                            "seed": cell["seed"],
                            "profile": cell["profile"],
                            "step": record["step"],
                            "horizon": int(horizon),
                            "method": method,
                            "solver_status": str(variant["solver"].get("solver_status", "UNKNOWN")),
                            "safety_clipping": list(variant["solver"].get("safety_clipping", [])),
                            "correction_ratio": float(variant["solver"].get("action_correction_ratio", 0.0)),
                            "predicted_effect_error_ratio": float(variant["solver"].get("effect_error_ratio", 0.0)),
                            "realized_effect_delta_abs": abs(realized_effect - base_effect),
                            "realized_effect_deviation_ratio": abs(realized_effect - base_effect) / max(abs(base_effect), 1e-6),
                            "targeted_responsibility_movement": float(target_direction * (realized_left - base_left)),
                            "peak_angular_velocity": result["outcomes"]["LR"]["peak_angular_velocity"],
                            "peak_angular_delta_abs": abs(
                                float(result["outcomes"]["LR"]["peak_angular_velocity"])
                                - float(base["outcomes"]["LR"]["peak_angular_velocity"])
                            ),
                            "peak_linear_jerk": result["outcomes"]["LR"]["peak_linear_jerk"],
                            "max_slip": max(result["outcomes"]["LR"]["slip"]),
                            "max_slip_delta_abs": abs(
                                float(max(result["outcomes"]["LR"]["slip"]))
                                - float(max(base["outcomes"]["LR"]["slip"]))
                            ),
                            "min_height_m": result["outcomes"]["LR"]["min_height_m"],
                            "both_contact_rate": result["outcomes"]["LR"]["both_contact_rate"],
                        }
                    )
                for eta in (float(value) for value in config["operator"]["eta_candidates"]):
                    label = "L4" if eta == selected_eta else f"L4_eta_{eta}"
                    variant = record["variants"][label]
                    result = variant["by_horizon"][horizon]
                    base_effect = float(base["realized_total_effect"])
                    realized_effect = float(result["realized_total_effect"])
                    base_left = float(base["rho_left"])
                    target_left = float(record["variants"]["L4"]["target_share"][0])
                    target_direction = np.sign(target_left - base_left)
                    eta_rows[str(eta)].append(
                        {
                            "correction_ratio": float(variant["solver"].get("action_correction_ratio", 0.0)),
                            "predicted_effect_error_ratio": float(variant["solver"].get("effect_error_ratio", 0.0)),
                            "realized_effect_deviation_ratio": abs(realized_effect - base_effect) / max(abs(base_effect), 1e-6),
                            "targeted_responsibility_movement": float(target_direction * (float(result["rho_left"]) - base_left)),
                            "both_contact_rate": float(result["outcomes"]["LR"]["both_contact_rate"]),
                            "min_height_m": float(result["outcomes"]["LR"]["min_height_m"]),
                        }
                    )
    correct = [row for row in rows if row["method"] == "L4"]
    swapped = [row for row in rows if row["method"] == "L5"]
    conservation = [row for row in rows if row["method"] == "L2"]
    episode_groups: Dict[Tuple[int, str], list[Mapping[str, Any]]] = {}
    for cell in cells:
        episode_groups[(int(cell["seed"]), str(cell["profile"]))] = [
            row
            for row in correct
            if int(row["seed"]) == int(cell["seed"])
            and str(row["profile"]) == str(cell["profile"])
        ]
    episode_gate_summary = [
        {
            "seed": seed,
            "profile": profile,
            "branch_row_count": len(values),
            "median_action_correction_ratio": float(
                np.median([row["correction_ratio"] for row in values])
            ),
            "active_correction_over_5pct_rate": float(
                np.mean([row["correction_ratio"] > 0.05 for row in values])
            ),
            "median_targeted_responsibility_movement": float(
                np.median(
                    [row["targeted_responsibility_movement"] for row in values]
                )
            ),
            "median_peak_angular_delta_abs": float(
                np.median([row["peak_angular_delta_abs"] for row in values])
            ),
            "median_max_slip_delta_abs": float(
                np.median([row["max_slip_delta_abs"] for row in values])
            ),
        }
        for (seed, profile), values in sorted(episode_groups.items())
        if values
    ]
    ratios = np.asarray([row["correction_ratio"] for row in correct])
    null_gate = null_floor["fresh_prefix"]["effect_gate"]
    displacement_floor = float(null_gate.get("final_object_displacement_m", 0.0))
    realized_effect_gate = max(1e-9, displacement_floor)
    angular_gate = float(null_gate.get("peak_object_angular_velocity", 0.0))
    slip_gate = float(null_gate.get("peak_relative_slip_m", 0.0))
    criteria = {
        "median_action_correction_between_5_and_20pct": bool(len(ratios) and 0.05 <= float(np.median(ratios)) <= 0.20),
        "active_correction_over_5pct_rate_at_least_30pct": bool(len(ratios) and float(np.mean(ratios > 0.05)) >= 0.30),
        "realized_intervention_exceeds_3x_null_floor": bool(correct and float(np.median([row["realized_effect_delta_abs"] for row in correct])) > realized_effect_gate),
        "predicted_total_effect_error_below_5pct": bool(correct and float(np.percentile([row["predicted_effect_error_ratio"] for row in correct], 95)) < 0.05),
        "realized_total_effect_deviation_below_10pct": bool(correct and float(np.median([row["realized_effect_deviation_ratio"] for row in correct])) < 0.10),
        "correct_moves_responsibility_at_least_0p15": bool(correct and float(np.median([row["targeted_responsibility_movement"] for row in correct])) >= 0.15),
        "swap_reverses_direction": bool(swapped and float(np.median([row["targeted_responsibility_movement"] for row in swapped])) < 0.0),
        "conservation_only_not_same_shift": bool(correct and conservation and abs(float(np.median([row["targeted_responsibility_movement"] for row in correct])) - float(np.median([row["targeted_responsibility_movement"] for row in conservation]))) >= 0.05),
        "contact_and_height_not_degraded": bool(correct and float(np.median([row["both_contact_rate"] for row in correct])) >= 0.8 and float(np.min([row["min_height_m"] for row in correct])) >= 0.78),
        "angular_or_slip_effect_exceeds_null_floor": bool(
            correct
            and (
                float(np.median([row["peak_angular_delta_abs"] for row in correct])) > angular_gate
                or float(np.median([row["max_slip_delta_abs"] for row in correct])) > slip_gate
            )
        ),
    }
    transfer_core = all(
        value
        for key, value in criteria.items()
        if key != "angular_or_slip_effect_exceeds_null_floor"
    )
    if all(criteria.values()):
        decision = "EFFECTFUL_OPERATOR_READY"
    elif transfer_core and not criteria["angular_or_slip_effect_exceeds_null_floor"]:
        decision = "ONE_DIMENSION_INSUFFICIENT_EXTEND_4D"
    elif ratios.size and float(np.median(ratios)) < 0.05:
        decision = "OPERATOR_STILL_NEAR_NULL"
    elif not criteria["contact_and_height_not_degraded"]:
        decision = "OPERATOR_UNSAFE"
    else:
        decision = "RESPONSIBILITY_NOT_CAUSAL"
    eta_sensitivity = {
        eta: {
            "row_count": len(values),
            "median_action_correction_ratio": float(np.median([item["correction_ratio"] for item in values])) if values else None,
            "active_correction_over_5pct_rate": float(np.mean([item["correction_ratio"] > 0.05 for item in values])) if values else None,
            "p95_predicted_effect_error_ratio": float(np.percentile([item["predicted_effect_error_ratio"] for item in values], 95)) if values else None,
            "median_realized_effect_deviation_ratio": float(np.median([item["realized_effect_deviation_ratio"] for item in values])) if values else None,
            "median_targeted_responsibility_movement": float(np.median([item["targeted_responsibility_movement"] for item in values])) if values else None,
            "median_both_contact_rate": float(np.median([item["both_contact_rate"] for item in values])) if values else None,
            "minimum_height_m": float(np.min([item["min_height_m"] for item in values])) if values else None,
        }
        for eta, values in eta_rows.items()
    }
    eta_eligible = [
        float(eta)
        for eta, values in eta_sensitivity.items()
        if values["median_action_correction_ratio"] is not None
        and 0.05 <= values["median_action_correction_ratio"] <= 0.20
        and values["active_correction_over_5pct_rate"] >= 0.30
        and values["p95_predicted_effect_error_ratio"] < 0.05
        and values["median_realized_effect_deviation_ratio"] < 0.10
        and values["median_both_contact_rate"] >= 0.80
        and values["minimum_height_m"] >= 0.78
    ]
    recommended_eta = (
        min(
            eta_eligible,
            key=lambda eta: (
                abs(
                    eta_sensitivity[str(eta)]["median_action_correction_ratio"]
                    - 0.125
                ),
                eta,
            ),
        )
        if eta_eligible
        else None
    )
    return {
        "decision": decision,
        "selected_eta": selected_eta,
        "criteria": criteria,
        "summary": {
            "median_action_correction_ratio": float(np.median(ratios)) if len(ratios) else None,
            "active_correction_over_5pct_rate": float(np.mean(ratios > 0.05)) if len(ratios) else None,
            "median_correct_targeted_movement": float(np.median([row["targeted_responsibility_movement"] for row in correct])) if correct else None,
            "median_swapped_targeted_movement": float(np.median([row["targeted_responsibility_movement"] for row in swapped])) if swapped else None,
            "median_peak_angular_delta_abs": float(np.median([row["peak_angular_delta_abs"] for row in correct])) if correct else None,
            "median_max_slip_delta_abs": float(np.median([row["max_slip_delta_abs"] for row in correct])) if correct else None,
            "correct_solver_status_counts": dict(Counter(row["solver_status"] for row in correct)),
            "correct_safety_clipping_counts": dict(
                Counter(
                    reason
                    for row in correct
                    for reason in row["safety_clipping"]
                )
            ),
            "episode_gate_summary": episode_gate_summary,
            "row_count": len(rows),
        },
        "eta_sensitivity": eta_sensitivity,
        "eta_calibration_recommendation": {
            "eligible_eta": eta_eligible,
            "recommended_eta": recommended_eta,
            "selection_rule": config["operator"]["eta_calibration"]["selection_rule"],
            "target_median_correction_ratio": 0.125,
        },
        "selected_eta_source": "frozen_stage2c_config_before_formal_local_gate",
        "rows": rows,
        "episode_is_only_inference_unit": True,
        "branch_points_are_independent": False,
        "accepted": False,
    }


def _worker_subprocess(cell: Mapping[str, Any]) -> Dict[str, Any]:
    result = Path(cell["output"]) / "result.json"
    if result.is_file():
        return {"status": "REUSED_COMPLETE"}
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = str(cell["gpu"])
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    payload = json.dumps({key: str(value) if isinstance(value, Path) else value for key, value in cell.items()}, sort_keys=True)
    command = [sys.executable, "-m", "stage2_robotwin.stage2c.scripts.run_local_operator_gate", "--worker-json", payload]
    completed = subprocess.run(command, cwd=cell["repo_root"], env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    Path(cell["output"]).mkdir(parents=True, exist_ok=True)
    (Path(cell["output"]) / "runtime.log").write_text(completed.stdout, encoding="utf-8")
    return {"status": "COMPLETE" if completed.returncode == 0 and result.is_file() else "FAILED", "returncode": completed.returncode}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--robotwin-root")
    parser.add_argument("--config")
    parser.add_argument("--tape-root")
    parser.add_argument("--null-floor")
    parser.add_argument("--natural-root")
    parser.add_argument("--output")
    parser.add_argument("--gpus", nargs="+", type=int, default=[1, 2, 3])
    parser.add_argument("--cell-seeds", nargs="+", type=int)
    parser.add_argument("--cell-profiles", nargs="+")
    parser.add_argument("--worker-json")
    args = parser.parse_args()
    if args.worker_json:
        run_local_cell(json.loads(args.worker_json))
        return 0
    for name in ("robotwin_root", "config", "tape_root", "null_floor", "natural_root", "output"):
        if getattr(args, name) is None:
            parser.error(f"--{name.replace('_', '-')} is required")
    repo_root = Path(__file__).resolve().parents[3]
    config_path = Path(args.config).resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    tapes = discover_tapes(Path(args.tape_root).resolve())
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    natural_cells = []
    for result_path in Path(args.natural_root).resolve().rglob("result.json"):
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("status") == "COMPLETE":
            natural_cells.append(result)
    natural_index = {
        (int(result["seed"]), str(result["profile"]), result.get("gamma")): result
        for result in natural_cells
    }
    local_seeds = [int(value) for value in config["local_gate"]["seeds"]]
    eta_calibration_seeds = [
        int(value) for value in config["operator"]["eta_calibration"]["seeds"]
    ]
    shuffle_seed = {}
    for seed_pool in (local_seeds, eta_calibration_seeds):
        shuffle_seed.update(
            {
                seed: seed_pool[(index + 1) % len(seed_pool)]
                for index, seed in enumerate(seed_pool)
            }
        )
    cells = []
    index = 0
    execution_seeds = (
        [int(value) for value in args.cell_seeds]
        if args.cell_seeds
        else local_seeds
    )
    execution_profiles = (
        [str(value) for value in args.cell_profiles]
        if args.cell_profiles
        else [str(value) for value in config["local_gate"]["profiles"]]
    )
    if not set(execution_seeds).issubset(set(local_seeds) | set(eta_calibration_seeds)):
        raise ValueError(
            "cell-seeds must be a subset of the frozen local-gate or eta-calibration seeds"
        )
    if not set(execution_profiles).issubset(config["local_gate"]["profiles"]):
        raise ValueError("cell-profiles must be a subset of the frozen local-gate profiles")
    for seed in execution_seeds:
        for profile in execution_profiles:
            natural_profile = (
                "NATURAL"
                if profile == "clean"
                else "LEFT_HIDDEN_AUTHORITY"
            )
            natural_gamma = None if profile == "clean" else 0.6
            source_seed = shuffle_seed[int(seed)]
            source = natural_index.get((source_seed, natural_profile, natural_gamma))
            if source is None:
                raise ValueError(
                    f"missing natural responsibility control for seed={source_seed} "
                    f"profile={natural_profile} gamma={natural_gamma}"
                )
            shuffle_share_by_relative = {}
            for record in source["records"]:
                relative = int(record["e4_relative_step"])
                if relative < int(config["local_gate"]["window_start_relative_to_E4"]) or relative > int(config["local_gate"]["window_end_relative_to_E4"]):
                    continue
                estimate = record["by_horizon"]["5"]
                share = classify_signed_responsibility(
                    estimate["rho_left"],
                    estimate["rho_right"],
                    estimate["rho_joint"],
                    joint_threshold=float(config["responsibility_control"]["joint_threshold"]),
                    harmful_threshold=float(config["responsibility_control"]["harmful_threshold"]),
                    joint_differential_scale=float(config["responsibility_control"]["joint_differential_scale"]),
                    temperature=float(config["responsibility_control"]["temperature"]),
                ).target_share
                shuffle_share_by_relative[relative] = share.tolist()
            expected_relative = set(
                np.linspace(
                    int(config["local_gate"]["window_start_relative_to_E4"]),
                    int(config["local_gate"]["window_end_relative_to_E4"]),
                    int(config["local_gate"]["states_per_seed"]),
                    dtype=int,
                ).tolist()
            )
            if set(shuffle_share_by_relative) != expected_relative:
                raise ValueError(
                    f"incomplete episode-shuffle control for seed={source_seed}: "
                    f"expected={sorted(expected_relative)} got={sorted(shuffle_share_by_relative)}"
                )
            stem = f"seed_{int(seed):04d}__{profile}"
            cells.append(
                {
                    "seed": int(seed),
                    "profile": profile,
                    "gpu": args.gpus[index % len(args.gpus)],
                    "tape": tapes[int(seed)][0],
                    "meta": tapes[int(seed)][1],
                    "config": config_path,
                    "robotwin_root": Path(args.robotwin_root).resolve(),
                    "output": output / "cells" / stem,
                    "repo_root": repo_root,
                    "shuffle_source_seed": source_seed,
                    "shuffle_share_by_relative": shuffle_share_by_relative,
                }
            )
            index += 1
    receipts = []
    gpu_locks = {gpu: threading.Lock() for gpu in args.gpus}

    def run_locked(cell: Mapping[str, Any]) -> Dict[str, Any]:
        with gpu_locks[int(cell["gpu"])]:
            return _worker_subprocess(cell)

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(args.gpus)) as pool:
        futures = {pool.submit(run_locked, cell): cell for cell in cells}
        for count, future in enumerate(concurrent.futures.as_completed(futures), 1):
            cell = futures[future]
            try:
                receipt = future.result()
            except Exception as exc:
                receipt = {"status": "FAILED", "error": f"{type(exc).__name__}: {exc}"}
            receipts.append({"seed": cell["seed"], "profile": cell["profile"], "gpu": cell["gpu"], **receipt})
            print(f"LOCAL_GATE_PROGRESS {count}/{len(cells)} seed={cell['seed']} profile={cell['profile']} status={receipt['status']}", flush=True)
            write_json(output / "run_receipts.partial.json", receipts)
    results = [json.loads((Path(cell["output"]) / "result.json").read_text(encoding="utf-8")) for cell in cells if (Path(cell["output"]) / "result.json").is_file()]
    null_floor = json.loads(Path(args.null_floor).read_text(encoding="utf-8"))
    analysis = analyze_local_gate(results, null_floor, config) if results else {"decision": "RESPONSIBILITY_NOT_CAUSAL", "accepted": False}
    decision = {"status": "COMPLETE" if len(results) == len(cells) else "INCOMPLETE", "expected_cells": len(cells), "completed_cells": len(results), **analysis, "accepted": False, "pai_job_created": False}
    write_json(output / "LOCAL_OPERATOR_GATE_DECISION.json", decision)
    write_json(output / "run_receipts.json", receipts)
    print(f"LOCAL_GATE_COMPLETE {len(results)}/{len(cells)} decision={analysis['decision']}", flush=True)
    return 0 if len(results) == len(cells) else 2


if __name__ == "__main__":
    raise SystemExit(main())
