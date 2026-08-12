"""Persisted LIBERO oracle-responsibility audit for R22-P19.

This module intentionally stops at a single-arm action-subspace substrate
test. It does not turn successful expert replay into a learned-policy result.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import h5py
import numpy as np
import yaml

from .config import LOG_ROOT, SignalConfig, TaskSpec, default_config_path, load_config, validate_paths
from .env import LiberoBranchEnv, quaternion_angle_wxyz
from .events import (
    EventAudit,
    assign_primary_phase,
    control_branch_indices,
    detect_primary_events,
    manual_audit_rows,
    primary_branch_indices,
    scan_demo_trace,
)
from .io import atomic_json, atomic_jsonl, sha256_file
from .responsibility import (
    OUTCOME_NAMES,
    finite_summary,
    rank_auc,
    shapley_responsibility,
    shuffled_auc_distribution,
)


SEED = 2219


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_head(path: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        text=True,
        stderr=subprocess.STDOUT,
    ).strip()


def _git_dirty(path: Path) -> bool:
    value = subprocess.check_output(
        ["git", "-C", str(path), "status", "--porcelain"],
        text=True,
        stderr=subprocess.STDOUT,
    )
    return bool(value.strip())


def _h5_contract(task: TaskSpec) -> Dict[str, Any]:
    with h5py.File(str(task.dataset_path), "r") as handle:
        data = handle["data"]
        demo_names = sorted(data.keys(), key=lambda name: int(name.split("_")[-1]))
        rows = []
        for demo_id in task.demo_ids:
            name = "demo_%d" % int(demo_id)
            if name not in data:
                raise RuntimeError("missing %s in %s" % (name, task.dataset_path))
            group = data[name]
            rows.append(
                {
                    "demo_id": int(demo_id),
                    "length": int(len(group["actions"])),
                    "action_shape": list(group["actions"].shape),
                    "state_shape": list(group["states"].shape),
                    "terminal_reward": int(np.asarray(group["rewards"])[-1]),
                }
            )
    return {
        "path": str(task.dataset_path),
        "sha256": sha256_file(task.dataset_path),
        "available_demo_count": len(demo_names),
        "selected_demo_count": len(task.demo_ids),
        "selected_demos": rows,
    }


def build_manifest(config: SignalConfig, mode: str) -> Dict[str, Any]:
    expected_libero = str(config.raw["sources"]["libero_commit"])
    actual_libero = _git_head(config.libero_root)
    if actual_libero != expected_libero:
        raise RuntimeError(
            "LIBERO commit mismatch: expected %s, got %s" % (expected_libero, actual_libero)
        )
    if _git_dirty(config.libero_root):
        raise RuntimeError("LIBERO source tree is dirty: %s" % config.libero_root)
    return {
        "created_at_utc": utc_now(),
        "mode": mode,
        "proposal_id": "R22-P19",
        "accepted": False,
        "evidence_kind": "libero_single_arm_action_subspace_preliminary",
        "host": platform.node(),
        "platform": platform.platform(),
        "python": sys.version,
        "executable": sys.executable,
        "pid": os.getpid(),
        "uid": os.getuid(),
        "gid": os.getgid(),
        "config_path": str(config.path),
        "config_sha256": sha256_file(config.path),
        "libero_root": str(config.libero_root),
        "libero_commit_expected": expected_libero,
        "libero_commit_actual": actual_libero,
        "libero_dirty": False,
        "branch_hidden_state_contract": {
            "mujoco_flat_state": "restored",
            "model_body_poses": "restored_from_demo_model_file",
            "osc": "anchored_to_restored_robot_state",
            "gripper_target": "hold_restored_finger_qpos",
        },
        "versions": {
            "numpy": np.__version__,
            "h5py": h5py.__version__,
        },
        "primary_dataset": _h5_contract(config.primary),
        "control_dataset": _h5_contract(config.control),
        "claim_boundary": config.raw["boundary"],
    }


def _load_arrays(task: TaskSpec, demo_id: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    with h5py.File(str(task.dataset_path), "r") as handle:
        group = handle["data/demo_%d" % int(demo_id)]
        return (
            np.asarray(group["states"], dtype=np.float64),
            np.asarray(group["actions"], dtype=np.float64),
            np.asarray(group["rewards"], dtype=np.uint8),
        )


def deterministic_audit(
    env: LiberoBranchEnv,
    config: SignalConfig,
    task: TaskSpec,
    demo_ids: Sequence[int],
    checks_per_demo: int,
) -> Dict[str, Any]:
    repeated_rows: List[Dict[str, Any]] = []
    repeated_branch_rows: List[Dict[str, Any]] = []
    alignment_rows: List[Dict[str, Any]] = []
    for demo_id in demo_ids:
        states, actions, _ = _load_arrays(task, int(demo_id))
        candidates = sorted(
            set(
                int(value)
                for value in np.linspace(0, max(0, len(states) - 2), checks_per_demo)
            )
        )
        for index in candidates:
            env.set_state(states[index], int(demo_id))
            first_sim = np.asarray(env.env.get_sim_state(), dtype=np.float64).copy()
            first = env.snapshot()
            env.set_state(states[index], int(demo_id))
            second_sim = np.asarray(env.env.get_sim_state(), dtype=np.float64).copy()
            second = env.snapshot()
            state_error = float(np.max(np.abs(first_sim - second_sim)))
            position_error = float(
                np.linalg.norm(
                    np.asarray(first["object"]["position"])
                    - np.asarray(second["object"]["position"])
                )
            )
            rotation_error = quaternion_angle_wxyz(
                np.asarray(first["object"]["quaternion_wxyz"]),
                np.asarray(second["object"]["quaternion_wxyz"]),
            )
            repeated_pass = bool(
                state_error <= config.state_tolerance
                and position_error <= config.object_position_tolerance
                and rotation_error <= config.object_rotation_tolerance
            )
            repeated_rows.append(
                {
                    "demo_id": int(demo_id),
                    "step_id": int(index),
                    "max_sim_state_error": state_error,
                    "object_position_error_m": position_error,
                    "object_rotation_error_rad": rotation_error,
                    "pass": repeated_pass,
                }
            )

            branch = env.rollout(
                states[index],
                actions[index : index + 1],
                int(demo_id),
                "AB",
                config.arm_dims,
                config.gripper_dims,
            )
            repeated_branch = env.rollout(
                states[index],
                actions[index : index + 1],
                int(demo_id),
                "AB",
                config.arm_dims,
                config.gripper_dims,
            )
            branch_state = np.asarray(branch["final_sim_state"], dtype=np.float64)
            repeated_branch_state = np.asarray(
                repeated_branch["final_sim_state"], dtype=np.float64
            )
            repeated_branch_error = float(
                np.max(np.abs(branch_state - repeated_branch_state))
            )
            repeated_branch_rows.append(
                {
                    "demo_id": int(demo_id),
                    "step_id": int(index),
                    "max_final_sim_state_error": repeated_branch_error,
                    "pass": bool(repeated_branch_error <= config.state_tolerance),
                }
            )
            actual = np.asarray(branch["final_sim_state"], dtype=np.float64)
            expected = np.asarray(states[index + 1], dtype=np.float64)
            if actual.shape != expected.shape:
                raise RuntimeError(
                    "one-step state shape mismatch: %s != %s" % (actual.shape, expected.shape)
                )
            state_linf = float(np.max(np.abs(actual - expected)))
            env.set_state(expected, int(demo_id))
            expected_object = env.object_state().position.copy()
            env.set_state(actual, int(demo_id))
            actual_object = env.object_state().position.copy()
            object_error = float(np.linalg.norm(actual_object - expected_object))
            alignment_pass = bool(
                state_linf <= config.one_step_state_tolerance
                and object_error <= config.one_step_object_position_tolerance
            )
            alignment_rows.append(
                {
                    "demo_id": int(demo_id),
                    "step_id": int(index),
                    "compared_to": "states[t+1]",
                    "max_sim_state_error": state_linf,
                    "object_position_error_m": object_error,
                    "pass": alignment_pass,
                }
            )
    return {
        "repeated_restore": {
            "tolerances": {
                "max_sim_state_error": config.state_tolerance,
                "object_position_error_m": config.object_position_tolerance,
                "object_rotation_error_rad": config.object_rotation_tolerance,
            },
            "rows": repeated_rows,
            "pass": bool(repeated_rows and all(row["pass"] for row in repeated_rows)),
        },
        "one_step_alignment": {
            "diagnostic_only": True,
            "non_identifiable_hidden_state": [
                "PandaGripper.current_action",
                "OSC Python controller buffers",
            ],
            "tolerances": {
                "max_sim_state_error": config.one_step_state_tolerance,
                "object_position_error_m": config.one_step_object_position_tolerance,
            },
            "rows": alignment_rows,
            "pass": bool(alignment_rows and all(row["pass"] for row in alignment_rows)),
        },
        "repeated_branch": {
            "hidden_state_contract": "hold_restored_finger_qpos_and_anchor_osc",
            "tolerance": config.state_tolerance,
            "rows": repeated_branch_rows,
            "pass": bool(
                repeated_branch_rows and all(row["pass"] for row in repeated_branch_rows)
            ),
        },
        "pass": bool(
            repeated_rows
            and repeated_branch_rows
            and all(row["pass"] for row in repeated_rows)
            and all(row["pass"] for row in repeated_branch_rows)
        ),
    }


def _compact_branch(value: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "branch": value["branch"],
        "gains": value["gains"],
        "keep_background": value["keep_background"],
        "start": value["start"],
        "end": value["end"],
        "outcome": value["outcome"],
        "applied_actions": value["applied_actions"],
        "model_file_sha256": value["model_file_sha256"],
    }


def _branch_point(
    env: LiberoBranchEnv,
    config: SignalConfig,
    demo_id: int,
    index: int,
    horizon: int,
    state: np.ndarray,
    actions: np.ndarray,
    phase: str,
    group_a: Sequence[int],
    group_b: Sequence[int],
    gains: Tuple[float, float] = (1.0, 1.0),
    keep_background: bool = False,
) -> Dict[str, Any]:
    branches = {
        name: env.rollout(
            state,
            actions,
            int(demo_id),
            name,
            group_a,
            group_b,
            gains=gains,
            keep_background=keep_background,
        )
        for name in ("AB", "A", "B", "ZERO")
    }
    responsibility = shapley_responsibility(branches)
    arm_action_magnitude = float(
        np.mean(np.linalg.norm(np.asarray(actions)[:, list(config.arm_dims)], axis=1))
    )
    return {
        "demo_id": int(demo_id),
        "step_id": int(index),
        "horizon": int(horizon),
        "phase": phase,
        "group_a": [int(value) for value in group_a],
        "group_b": [int(value) for value in group_b],
        "gains": [float(gains[0]), float(gains[1])],
        "keep_background": bool(keep_background),
        "raw_action_l1_a": float(np.sum(np.abs(np.asarray(actions)[:, list(group_a)]))),
        "raw_action_l1_b": float(np.sum(np.abs(np.asarray(actions)[:, list(group_b)]))),
        "arm_action_magnitude_baseline": arm_action_magnitude,
        "responsibility": responsibility,
        "branches": {name: _compact_branch(value) for name, value in branches.items()},
    }


def _scan_primary(
    env: LiberoBranchEnv,
    config: SignalConfig,
    demo_ids: Sequence[int],
) -> Tuple[Dict[int, List[Dict[str, Any]]], Dict[int, EventAudit], List[Dict[str, Any]]]:
    traces: Dict[int, List[Dict[str, Any]]] = {}
    audits: Dict[int, EventAudit] = {}
    all_rows: List[Dict[str, Any]] = []
    for demo_id in demo_ids:
        rows, _, actions, rewards = scan_demo_trace(env, config.primary, int(demo_id))
        audit = detect_primary_events(rows, actions, rewards)
        traces[int(demo_id)] = rows
        audits[int(demo_id)] = audit
        all_rows.extend(rows)
    return traces, audits, all_rows


def _responsibility_records(
    env: LiberoBranchEnv,
    config: SignalConfig,
    task: TaskSpec,
    demo_ids: Sequence[int],
    audits: Optional[Mapping[int, EventAudit]],
    horizons: Sequence[int],
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for demo_id in demo_ids:
        states, actions, _ = _load_arrays(task, int(demo_id))
        for horizon in horizons:
            if audits is None:
                indices = control_branch_indices(len(states), config.branch_stride, int(horizon))
            else:
                indices = primary_branch_indices(
                    audits[int(demo_id)], config.branch_stride, int(horizon)
                )
            for index in indices:
                phase = (
                    "gate_off_control"
                    if audits is None
                    else assign_primary_phase(index, audits[int(demo_id)].events)
                )
                record = _branch_point(
                    env,
                    config,
                    int(demo_id),
                    int(index),
                    int(horizon),
                    states[index],
                    actions[index : index + int(horizon)],
                    phase,
                    config.arm_dims,
                    config.gripper_dims,
                )
                record["task_role"] = task.role
                record["task"] = task.name
                records.append(record)
    return records


def _authority_records(
    env: LiberoBranchEnv,
    config: SignalConfig,
    demo_ids: Sequence[int],
    audits: Mapping[int, EventAudit],
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    horizon = max(config.branch_horizons)
    threshold = config.gate["authority_eligibility_action_l1_min"]
    for demo_id in demo_ids:
        states, actions, _ = _load_arrays(config.primary, int(demo_id))
        indices = primary_branch_indices(audits[int(demo_id)], config.branch_stride, horizon)
        for index in indices:
            phase = assign_primary_phase(index, audits[int(demo_id)].events)
            if phase != "transport":
                continue
            window = actions[index : index + horizon]
            action_l1_x = float(np.sum(np.abs(window[:, list(config.x_dims)])))
            action_l1_y = float(np.sum(np.abs(window[:, list(config.y_dims)])))
            if min(action_l1_x, action_l1_y) < threshold:
                continue
            pair_records = []
            for gains in config.authority_gain_pairs:
                pair_records.append(
                    _branch_point(
                        env,
                        config,
                        int(demo_id),
                        int(index),
                        horizon,
                        states[index],
                        window,
                        phase,
                        config.x_dims,
                        config.y_dims,
                        gains=gains,
                        keep_background=True,
                    )
                )
            by_gain = {tuple(row["gains"]): row for row in pair_records}
            high_x = by_gain[(1.3, 0.7)]["responsibility"]
            high_y = by_gain[(0.7, 1.3)]["responsibility"]
            x_high = abs(float(high_x["phi_a"][OUTCOME_NAMES.index("translation_x")]))
            x_low = abs(float(high_y["phi_a"][OUTCOME_NAMES.index("translation_x")]))
            y_low = abs(float(high_x["phi_b"][OUTCOME_NAMES.index("translation_y")]))
            y_high = abs(float(high_y["phi_b"][OUTCOME_NAMES.index("translation_y")]))
            records.append(
                {
                    "demo_id": int(demo_id),
                    "step_id": int(index),
                    "horizon": int(horizon),
                    "phase": phase,
                    "action_l1_x": action_l1_x,
                    "action_l1_y": action_l1_y,
                    "x_response_correct": bool(x_high > x_low),
                    "y_response_correct": bool(y_high > y_low),
                    "both_response_correct": bool(x_high > x_low and y_high > y_low),
                    "x_effect_gain_1p3": x_high,
                    "x_effect_gain_0p7": x_low,
                    "y_effect_gain_0p7": y_low,
                    "y_effect_gain_1p3": y_high,
                    "gain_records": pair_records,
                }
            )
    return records


def compute_metrics(
    config: SignalConfig,
    audits: Mapping[int, EventAudit],
    primary_records: Sequence[Dict[str, Any]],
    control_records: Sequence[Dict[str, Any]],
    authority_records: Sequence[Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    valid_fraction = float(
        sum(int(audit.ordered_complete) for audit in audits.values()) / max(len(audits), 1)
    )
    phase_rows = [
        row for row in primary_records if row["phase"] in ("grasp_close", "transport")
    ]
    labels = [int(row["phase"] == "transport") for row in phase_rows]
    scores = [float(row["responsibility"]["motion_share_a"]) for row in phase_rows]
    baselines = [float(row["arm_action_magnitude_baseline"]) for row in phase_rows]
    if not phase_rows or len(set(labels)) != 2:
        raise RuntimeError("phase AUC population lacks both grasp and transport rows")
    phase_auc = rank_auc(labels, scores)
    baseline_auc_raw = rank_auc(labels, baselines)
    baseline_auc = max(baseline_auc_raw, 1.0 - baseline_auc_raw)
    shuffled = shuffled_auc_distribution(labels, scores, seed=SEED, repeats=200)
    shuffled_p95 = float(np.quantile(np.asarray(shuffled), 0.95))
    grasp_scores = [score for label, score in zip(labels, scores) if label == 0]
    transport_scores = [score for label, score in zip(labels, scores) if label == 1]
    phase_shift = float(np.mean(transport_scores) - np.mean(grasp_scores))
    conservation = [
        float(row["responsibility"]["relative_conservation_error"])
        for row in list(primary_records) + list(control_records)
    ]
    control_floor = config.gate["control_effect_norm_floor"]
    control_threshold = config.gate["control_gripper_gate_threshold"]
    control_activations = [
        bool(
            float(row["responsibility"]["motion_share_b"]) > control_threshold
            and float(row["responsibility"]["motion_magnitude_b"]) > control_floor
        )
        for row in control_records
    ]
    control_activation = float(np.mean(control_activations)) if control_activations else 1.0
    authority_accuracy = float(
        np.mean([int(row["both_response_correct"]) for row in authority_records])
    ) if authority_records else 0.0
    gates = {
        "valid_primary_event_fraction": bool(
            valid_fraction >= config.gate["valid_primary_event_fraction_min"]
        ),
        "phase_auc": bool(phase_auc >= config.gate["phase_auc_min"]),
        "shuffle_control": bool(shuffled_p95 <= config.gate["shuffled_auc_max"]),
        "phase_auc_over_action_magnitude": bool(
            phase_auc - baseline_auc
            >= config.gate["phase_auc_over_action_magnitude_min"]
        ),
        "phase_shift": bool(
            phase_shift >= config.gate["arm_share_transport_minus_grasp_min"]
        ),
        "conservation": bool(
            max(conservation) <= config.gate["relative_conservation_error_max"]
        ),
        "authority_eligible_count": bool(
            len(authority_records) >= int(config.gate["authority_swap_eligible_min"])
        ),
        "authority_swap_response": bool(
            authority_accuracy >= config.gate["authority_swap_response_accuracy_min"]
        ),
        "gate_off_control": bool(
            control_activation <= config.gate["control_gripper_gate_activation_max"]
        ),
    }
    metrics = {
        "valid_primary_event_fraction": valid_fraction,
        "valid_primary_event_count": int(sum(a.ordered_complete for a in audits.values())),
        "primary_demo_count": len(audits),
        "primary_branch_count": len(primary_records),
        "control_branch_count": len(control_records),
        "phase_population_count": len(phase_rows),
        "phase_label_counts": {
            "grasp_close": int(labels.count(0)),
            "transport": int(labels.count(1)),
        },
        "phase_auc": phase_auc,
        "action_magnitude_baseline_auc_best_direction": baseline_auc,
        "phase_auc_over_action_magnitude": float(phase_auc - baseline_auc),
        "shuffled_auc": {
            "repeats": 200,
            "seed": SEED,
            "summary": finite_summary(shuffled),
            "p95": shuffled_p95,
        },
        "arm_share_grasp_close": finite_summary(grasp_scores),
        "arm_share_transport": finite_summary(transport_scores),
        "arm_share_transport_minus_grasp": phase_shift,
        "relative_conservation_error": finite_summary(conservation),
        "relative_conservation_error_max": max(conservation),
        "authority_swap_eligible_count": len(authority_records),
        "authority_swap_response_accuracy": authority_accuracy,
        "gate_off_control_activation_fraction": control_activation,
        "gate_off_control_activation_count": int(sum(control_activations)),
        "gates": gates,
    }
    passed = bool(all(gates.values()))
    decision = {
        "decision": "LIBERO_SUBSTRATE_GO" if passed else "LIBERO_SUBSTRATE_NO_GO",
        "all_registered_gates_pass": passed,
        "failed_gates": sorted(name for name, value in gates.items() if not value),
        "act_pai_authorized_by_gate": passed,
        "original_bimanual_signal_go": "not_tested",
        "accepted": False,
        "claim_boundary": config.raw["boundary"],
    }
    return metrics, decision


def run_smoke(config: SignalConfig, output: Path) -> Dict[str, Any]:
    env = LiberoBranchEnv(config.primary, config.libero_root, seed=SEED, render=False)
    try:
        demo_id = int(config.primary.demo_ids[0])
        deterministic = deterministic_audit(env, config, config.primary, [demo_id], 2)
        traces, audits, all_rows = _scan_primary(env, config, [demo_id])
        audit = audits[demo_id]
        if audit.ordered_complete:
            states, actions, _ = _load_arrays(config.primary, demo_id)
            indices = primary_branch_indices(audit, config.branch_stride, min(config.branch_horizons))
            if not indices:
                raise RuntimeError("smoke produced no branch index")
            index = indices[min(1, len(indices) - 1)]
            branch_record = _branch_point(
                env,
                config,
                demo_id,
                index,
                min(config.branch_horizons),
                states[index],
                actions[index : index + min(config.branch_horizons)],
                assign_primary_phase(index, audit.events),
                config.arm_dims,
                config.gripper_dims,
            )
            atomic_json(output / "smoke_branch.json", branch_record)
        else:
            branch_record = None
        atomic_json(output / "determinism.json", deterministic)
        atomic_jsonl(output / "expert_trace.jsonl", all_rows)
        atomic_json(output / "event_audit.json", audit.as_json())
        status = {
            "status": "SMOKE_COMPLETE",
            "implementation_smoke_pass": bool(
                deterministic["pass"] and audit.ordered_complete and branch_record is not None
            ),
            "determinism_pass": bool(deterministic["pass"]),
            "ordered_event_chain": bool(audit.ordered_complete),
            "method_performance_evidence": False,
            "accepted": False,
            "completed_at_utc": utc_now(),
        }
        atomic_json(output / "SMOKE_COMPLETE.json", status)
        return status
    finally:
        env.close()


def run_signal(config: SignalConfig, output: Path) -> Dict[str, Any]:
    primary_env = LiberoBranchEnv(config.primary, config.libero_root, seed=SEED, render=False)
    try:
        deterministic = deterministic_audit(
            primary_env, config, config.primary, config.primary.demo_ids[:3], 3
        )
        atomic_json(output / "determinism.json", deterministic)
        if not deterministic["pass"]:
            decision = {
                "decision": "LIBERO_SUBSTRATE_NO_GO",
                "failed_gates": ["deterministic_replay"],
                "act_pai_authorized_by_gate": False,
                "original_bimanual_signal_go": "not_tested",
                "accepted": False,
            }
            atomic_json(output / "decision.json", decision)
            return decision
        traces, audits, all_trace_rows = _scan_primary(
            primary_env, config, config.primary.demo_ids
        )
        atomic_jsonl(output / "expert_traces.jsonl", all_trace_rows)
        atomic_jsonl(output / "event_audits.jsonl", [a.as_json() for a in audits.values()])
        atomic_json(
            output / "manual_event_audit.json",
            manual_audit_rows(traces, audits, count=10),
        )
        valid_fraction = float(sum(a.ordered_complete for a in audits.values()) / len(audits))
        if valid_fraction < config.gate["valid_primary_event_fraction_min"]:
            decision = {
                "decision": "LIBERO_SUBSTRATE_NO_GO",
                "failed_gates": ["valid_primary_event_fraction"],
                "valid_primary_event_fraction": valid_fraction,
                "act_pai_authorized_by_gate": False,
                "original_bimanual_signal_go": "not_tested",
                "accepted": False,
            }
            atomic_json(output / "decision.json", decision)
            return decision
        primary_records = _responsibility_records(
            primary_env,
            config,
            config.primary,
            config.primary.demo_ids,
            audits,
            config.branch_horizons,
        )
        atomic_jsonl(output / "primary_responsibility.jsonl", primary_records)
        authority_records = _authority_records(
            primary_env, config, config.primary.demo_ids, audits
        )
        atomic_jsonl(output / "authority_swap.jsonl", authority_records)
    finally:
        primary_env.close()

    control_env = LiberoBranchEnv(config.control, config.libero_root, seed=SEED, render=False)
    try:
        control_records = _responsibility_records(
            control_env,
            config,
            config.control,
            config.control.demo_ids,
            None,
            config.branch_horizons,
        )
        atomic_jsonl(output / "control_responsibility.jsonl", control_records)
    finally:
        control_env.close()

    metrics, decision = compute_metrics(
        config, audits, primary_records, control_records, authority_records
    )
    atomic_json(output / "metrics.json", metrics)
    atomic_json(output / "decision.json", decision)
    completion = {
        "status": "EVALUATION_COMPLETE",
        "completed_at_utc": utc_now(),
        "decision": decision["decision"],
        "act_pai_authorized_by_gate": decision["act_pai_authorized_by_gate"],
        "original_bimanual_signal_go": "not_tested",
        "accepted": False,
        "method_performance_evidence": True,
    }
    atomic_json(output / "EVALUATION_COMPLETE.json", completion)
    return decision


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("smoke", "signal"), required=True)
    parser.add_argument("--config", type=Path, default=default_config_path())
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    try:
        errors = validate_paths(config)
        if errors:
            raise RuntimeError("; ".join(errors))
        manifest = build_manifest(config, args.mode)
        with config.path.open("r", encoding="utf-8") as handle:
            frozen_config = yaml.safe_load(handle)
        atomic_json(output / "manifest.json", manifest)
        atomic_json(output / "frozen_config.json", frozen_config)
        result = run_smoke(config, output) if args.mode == "smoke" else run_signal(config, output)
        print(json.dumps(result, sort_keys=True))
        if args.mode == "smoke" and not result["implementation_smoke_pass"]:
            return 2
        return 0
    except Exception as error:
        atomic_json(
            output / "FAILURE.json",
            {
                "status": "FAILURE",
                "error_type": type(error).__name__,
                "error": str(error),
                "traceback": traceback.format_exc(),
                "failed_at_utc": utc_now(),
                "accepted": False,
            },
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
