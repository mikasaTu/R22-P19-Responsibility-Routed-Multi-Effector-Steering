"""Run one fresh-process Stage 2F physical authority-knob cell."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
import traceback
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import numpy as np

from stage2_robotwin.stage2b.intervention.task_frame import ObjectTaskFrame
from stage2_robotwin.stage2b.operator.local_effect_gain import scalar_base_action
from stage2_robotwin.stage2c.replay.tape import ExpertTape
from stage2_robotwin.stage2c.responsibility.natural_responsibility import NaturalResponsibilityEstimator
from stage2_robotwin.stage2f.active_reference import FrozenActiveReference
from stage2_robotwin.stage2e.withdrawal.common import contact_wrench_by_side
from stage2_robotwin.stage2f.intervention.common import canonical_command_sha256, canonical_effect_sha256
from stage2_robotwin.stage2f.intervention.registry import apply as apply_knob
from stage2_robotwin.wrappers.counterfactual_brancher import SapienSnapshot, gripper_object_contacts, object_state
from stage2_robotwin.wrappers.robotwin_runtime import build_handover_block


HORIZONS = (5, 10, 20)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sample_steps(events: dict[str, int], stride: int = 25) -> list[int]:
    start = max(int(events["E3"]), int(events["E4"]) - 250)
    end = min(int(events["E5"]), int(events["E4"]) + 150)
    return list(range(start, end + 1, int(stride)))


def _runtime_git(root: Path) -> dict[str, Any]:
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    status = subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"], text=True)
    diff = subprocess.check_output(["git", "-C", str(root), "diff", "--binary"], text=False)
    return {
        "head": head,
        "dirty": bool(status.strip()),
        "status_porcelain": status.splitlines(),
        "dirty_diff_sha256": hashlib.sha256(diff).hexdigest(),
    }


def _stage2f_source_sha256(root: Path) -> str:
    payload = bytearray(b"r22p19.stage2f.source.v1\0")
    for path in sorted(
        candidate for candidate in root.rglob("*")
        if candidate.is_file()
        and candidate.suffix in {".py", ".yaml"}
        and "results" not in candidate.parts
    ):
        payload.extend(str(path.relative_to(root)).encode("utf-8"))
        payload.extend(b"\0")
        payload.extend(path.read_bytes())
        payload.extend(b"\0")
    return hashlib.sha256(payload).hexdigest()


def _commands_for_future(active_tape: FrozenActiveReference, start_index: int, count: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    targets, grippers = [], []
    for index in range(start_index, min(len(active_tape), start_index + count)):
        active = active_tape.item(index)
        targets.append({
            side: (
                np.asarray(active[f"{side}_position"], dtype=np.float64),
                np.asarray(active[f"{side}_velocity"], dtype=np.float64),
            )
            for side in ("left", "right")
        })
        grippers.append({side: active[f"{side}_gripper"] for side in ("left", "right")})
    return targets, grippers


def _dynamic_state_sha256(task: Any) -> str:
    """Fingerprint replay-relevant state without scene-specific entity IDs."""
    payload = bytearray(b"r22p19.stage2f.dynamic_state.v1\0")
    for articulation in task.scene.get_all_articulations():
        pose = articulation.get_root_pose()
        for value in (
            articulation.get_qpos(), articulation.get_qvel(), pose.p, pose.q,
            articulation.get_root_linear_velocity(),
            articulation.get_root_angular_velocity(),
        ):
            payload.extend(np.ascontiguousarray(value, dtype="<f8").tobytes(order="C"))
    state = object_state(task)
    for key in ("pose", "linear_velocity", "angular_velocity"):
        payload.extend(np.ascontiguousarray(state[key], dtype="<f8").tobytes(order="C"))
    payload.extend(np.asarray([
        task.robot.get_left_gripper_val(), task.robot.get_right_gripper_val()
    ], dtype="<f8").tobytes())
    return hashlib.sha256(payload).hexdigest()


def _close_stacks_fail_closed(*stacks: ExitStack | None) -> list[str]:
    errors = []
    for index, stack in enumerate(stacks):
        if stack is None:
            continue
        try:
            stack.close()
        except Exception as exc:
            errors.append(f"stack {index}: {type(exc).__name__}: {exc}")
    return errors


def run_cell(args: argparse.Namespace) -> dict[str, Any]:
    if args.seed not in {0, 1}:
        raise ValueError("Stage2F is calibration-only; held-out seeds are forbidden")
    tape = ExpertTape.load(args.tape)
    meta = json.loads(Path(args.meta).read_text(encoding="utf-8"))
    if int(meta["seed"]) != int(args.seed):
        raise ValueError("tape/meta seed does not match requested seed")
    events = {key: int(value) for key, value in meta["events"].items()}
    samples = sample_steps(events, args.stride)
    if len(samples) < 8:
        raise RuntimeError(f"insufficient usable states: {len(samples)} < 8")
    sample_set = set(samples)
    task = oracle = None
    main_stack = oracle_stack = None
    main_handle = oracle_handle = None
    started = time.perf_counter()
    amplitude = float(args.active_amplitude_m)
    active_tape, active_receipt = FrozenActiveReference.load_validated(
        args.active_tape,
        sidecar_path=args.active_tape.with_suffix(".json"),
        source_tape_path=args.tape,
        source_meta=meta,
        expected_seed=args.seed,
        expected_amplitude_m=amplitude,
    )
    if len(active_tape) != len(tape):
        raise ValueError("frozen active reference length does not match expert tape")
    non_soft_arm = "right" if args.soft_arm == "left" else "left"
    body_error: BaseException | None = None
    try:
        task, task_kwargs = build_handover_block(str(args.robotwin_root), planner="mplib_screw")
        task.setup_demo(now_ep_num=int(meta["episode"]), seed=int(args.seed), **task_kwargs)
        oracle, oracle_kwargs = build_handover_block(str(args.robotwin_root), planner="mplib_screw")
        oracle.setup_demo(now_ep_num=int(meta["episode"]), seed=int(args.seed), **oracle_kwargs)
        frame = ObjectTaskFrame.from_task(task)
        estimator = NaturalResponsibilityEstimator(HORIZONS)
        command_records: list[dict[str, Any]] = []
        sample_records: list[dict[str, Any]] = []
        physical_rows: list[dict[str, Any]] = []
        receiver_commands: list[dict[str, Any]] = []
        donor = str(meta["donor"])
        intervention_started = False
        active_origin = None
        alignment_records: list[dict[str, Any]] = []

        for index in range(len(tape)):
            raw = tape.item(index)
            step = int(raw["step"])
            item = active_tape.item(index)
            phase = (step - events["E3"]) / max(events["E5"] - events["E3"], 1)
            offset = float(amplitude * np.sin(np.pi * phase)) if events["E3"] <= step <= events["E5"] else 0.0
            if step >= events["E3"] and not intervention_started:
                main_stack, oracle_stack = ExitStack(), ExitStack()
                main_handle = main_stack.enter_context(apply_knob(args.knob, task, args.soft_arm, args.gamma))
                oracle_handle = oracle_stack.enter_context(apply_knob(args.knob, oracle, args.soft_arm, args.gamma))
                intervention_started = True

            targets = {
                side: (
                    np.asarray(item[f"{side}_position"], dtype=np.float64),
                    np.asarray(item[f"{side}_velocity"], dtype=np.float64),
                )
                for side in ("left", "right")
            }
            expert_soft = (targets[args.soft_arm][0].copy(), targets[args.soft_arm][1].copy())
            expert_parallel = float(scalar_base_action(task, args.soft_arm, expert_soft[0], frame.e_parallel)[0])
            if intervention_started:
                for side in ("left", "right"):
                    targets[side] = main_handle.route_target(side, targets[side])
            actual_parallel = float(scalar_base_action(task, args.soft_arm, targets[args.soft_arm][0], frame.e_parallel)[0])
            commands = {side: item[f"{side}_gripper"] for side in ("left", "right")}

            if step in sample_set:
                # Capture is read-only on main.  Restore is confined to the
                # disjoint oracle so every branch starts at this sampled state.
                SapienSnapshot.restore(oracle, SapienSnapshot.capture(task))
                main_state_sha = _dynamic_state_sha256(task)
                oracle_state_sha = _dynamic_state_sha256(oracle)
                if main_state_sha != oracle_state_sha:
                    raise RuntimeError(
                        f"oracle prefix replay state mismatch at step {step}: "
                        f"main={main_state_sha} oracle={oracle_state_sha}"
                    )
                alignment_records.append({
                    "step": step,
                    "main_state_sha256": main_state_sha,
                    "oracle_state_sha256": oracle_state_sha,
                    "exact": True,
                })
                future_targets, future_grippers = _commands_for_future(active_tape, index, max(HORIZONS))
                if len(future_targets) < max(HORIZONS):
                    raise RuntimeError("sample has insufficient future horizon")
                estimate = estimator.estimate(
                    oracle,
                    future_targets,
                    frame,
                    soft_arm=args.soft_arm if args.knob in {"K3", "K3_target_interpolation"} else None,
                    gamma=float(args.gamma) if args.knob in {"K3", "K3_target_interpolation"} else None,
                    gripper_sequence=future_grippers,
                )
                by_horizon = {}
                for horizon in HORIZONS:
                    record = estimate["by_horizon"][horizon]
                    by_horizon[str(horizon)] = {
                        "rho_soft": float(record[f"rho_{args.soft_arm}"]),
                        "rho_receiver": float(record[f"rho_{non_soft_arm}"]),
                        "rho_joint": float(record["rho_joint"]),
                    }
                sample_records.append({
                    "step": step,
                    "expert_parallel_action_m": expert_parallel,
                    "actual_parallel_action_m": actual_parallel,
                    "parallel_action_abs": abs(actual_parallel),
                    "expert_soft_target": expert_soft[0].tolist(),
                    "actual_soft_target": targets[args.soft_arm][0].tolist(),
                    "by_horizon": by_horizon,
                })

            for side in ("left", "right"):
                task.robot.set_arm_joints(targets[side][0], targets[side][1], side)
                if commands[side] is not None:
                    task.robot.set_gripper(commands[side][0], side, commands[side][1])
            task.scene.step()

            if events["E3"] <= step <= events["E5"]:
                state = object_state(task)
                contacts = gripper_object_contacts(task)
                wrench = contact_wrench_by_side(task, frame)
                if active_origin is None:
                    active_origin = state["pose"][:3].copy()
                soft_parallel = float(wrench[args.soft_arm]["motion"])
                receiver_parallel = float(wrench[non_soft_arm]["motion"])
                denom = soft_parallel + receiver_parallel
                physical_rows.append({
                    "step": step,
                    "active_reference_offset_m": float(offset),
                    "soft_parallel_impulse": soft_parallel,
                    "soft_vertical_impulse": float(wrench[args.soft_arm]["support"]),
                    "receiver_parallel_impulse": receiver_parallel,
                    "soft_parallel_impulse_share": 0.5 if denom <= 1e-12 else soft_parallel / denom,
                    "object_position": state["pose"][:3].tolist(),
                    "object_linear_velocity": state["linear_velocity"].tolist(),
                    "dual_contact": bool(contacts["left"] and contacts["right"]),
                    "donor_contact": bool(contacts[donor]),
                })
                receiver_commands.append({
                    f"{non_soft_arm}_position": targets[non_soft_arm][0].copy(),
                    f"{non_soft_arm}_velocity": targets[non_soft_arm][1].copy(),
                    f"{non_soft_arm}_gripper": commands[non_soft_arm],
                })
                command_records.append({
                    "step": step,
                    "expert_parallel_action_m": expert_parallel,
                    "actual_parallel_action_m": actual_parallel,
                    "actual_target": targets[args.soft_arm][0].tolist(),
                })

        check_success = bool(task.check_success())
        plan_success = bool(task.plan_success)
        if not intervention_started:
            raise RuntimeError("E3 intervention start was never reached")
        close_errors = _close_stacks_fail_closed(oracle_stack, main_stack)
        oracle_stack = main_stack = None
        if close_errors:
            raise RuntimeError("knob restoration failed: " + "; ".join(close_errors))
        if not main_handle.restoration_exact or not oracle_handle.restoration_exact:
            raise RuntimeError("drive-property restoration receipt failed")

        positions = np.asarray([row["object_position"] for row in physical_rows], dtype=np.float64)
        velocities = np.asarray([row["object_linear_velocity"] for row in physical_rows], dtype=np.float64)
        parallel = np.asarray([row["soft_parallel_impulse"] for row in physical_rows], dtype=np.float64)
        vertical = np.asarray([row["soft_vertical_impulse"] for row in physical_rows], dtype=np.float64)
        shares = np.asarray([row["soft_parallel_impulse_share"] for row in physical_rows], dtype=np.float64)
        rho_values = []
        for record in sample_records:
            for horizon in HORIZONS:
                rho_values.extend([
                    record["by_horizon"][str(horizon)]["rho_soft"],
                    record["by_horizon"][str(horizon)]["rho_receiver"],
                    record["by_horizon"][str(horizon)]["rho_joint"],
                ])
        effect_vector = [
            float(np.sum(parallel)),
            float(np.sum(vertical)),
            float(np.mean(shares)),
            float(np.mean([row["dual_contact"] for row in physical_rows])),
            float(np.sum([row["donor_contact"] for row in physical_rows])),
            float(check_success),
            float(plan_success),
            *rho_values,
        ]
        trace_path = Path(args.output).with_suffix(".trace.npz")
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            trace_path,
            object_position=positions,
            object_linear_velocity=velocities,
            soft_parallel_impulse=parallel,
            soft_vertical_impulse=vertical,
            soft_parallel_share=shares,
            dual_contact=np.asarray([row["dual_contact"] for row in physical_rows], dtype=bool),
            donor_contact=np.asarray([row["donor_contact"] for row in physical_rows], dtype=bool),
        )
        result = {
            "schema": "r22p19.stage2f.authority_knob_cell.v1",
            "status": "COMPLETE",
            "disposition": "VALID_CELL",
            "evidence_valid": True,
            "seed": int(args.seed),
            "episode": int(meta["episode"]),
            "knob": main_handle.name,
            "soft_arm": args.soft_arm,
            "receiver_non_soft_arm": non_soft_arm,
            "task_donor": donor,
            "gamma": float(args.gamma),
            "repeat": int(args.repeat),
            "launch_index": int(args.launch_index),
            "pid": os.getpid(),
            "events": events,
            "sample_window": {"start": samples[0], "end": samples[-1], "stride": int(args.stride)},
            "available_sample_steps": samples,
            "sample_count": len(sample_records),
            "horizons": list(HORIZONS),
            "branch_count": len(sample_records) * 4,
            "simulated_oracle_physics_steps": len(sample_records) * 4 * max(HORIZONS),
            "active_reference_amplitude_m": amplitude,
            "active_reference_axis": "e_perp",
            "active_reference_both_arms_common_mode": True,
            "frozen_active_reference_sha256": active_tape.sha256,
            "frozen_active_reference_receipt": active_receipt,
            "command_states": sample_records,
            "physical_summary": {
                "soft_parallel_impulse_integral": float(np.sum(parallel)),
                "soft_vertical_impulse_integral": float(np.sum(vertical)),
                "soft_parallel_impulse_share_mean": float(np.mean(shares)),
                "object_displacement_m": (positions[-1] - positions[0]).tolist(),
                "object_speed_mean_m_s": float(np.mean(np.linalg.norm(velocities, axis=1))),
                "object_speed_peak_m_s": float(np.max(np.linalg.norm(velocities, axis=1))),
                "dual_contact_fraction": float(np.mean([row["dual_contact"] for row in physical_rows])),
                "donor_contact_duration_steps": int(np.sum([row["donor_contact"] for row in physical_rows])),
                "donor_final_contact": bool(physical_rows[-1]["donor_contact"]),
                "donor_contact_not_early": bool(physical_rows[-1]["donor_contact"]),
                "active_window_steps": len(physical_rows),
            },
            "check_success": check_success,
            "plan_success": plan_success,
            "task_success": bool(check_success and plan_success),
            "receiver_command_sha256": canonical_command_sha256(receiver_commands, non_soft_arm),
            "receiver_command_encoding": "canonical_C_order_little_endian_float64_no_rounding",
            "effect_vector_sha256": canonical_effect_sha256(effect_vector),
            "effect_vector_field_count": len(effect_vector),
            "main_knob_receipt": main_handle.receipt(),
            "oracle_knob_receipt": oracle_handle.receipt(),
            "oracle_branch_knob_exposure_steps": (
                len(sample_records) * 4 * max(HORIZONS)
                if args.knob in {"K1", "K1_drive_compliance", "K2", "K2_force_limit"}
                else len(sample_records) * 2 * max(HORIZONS)
            ),
            "oracle_prefix_replayed_in_lockstep": False,
            "oracle_sample_state_source": "explicit_copy_from_main_current_state",
            "main_scene_capture_is_read_only": True,
            "oracle_alignment_records": alignment_records,
            "oracle_alignment_exact_at_all_samples": bool(
                len(alignment_records) == len(sample_records)
                and all(record["exact"] for record in alignment_records)
            ),
            "fresh_process": True,
            "fresh_scene": True,
            "replayed_from_episode_start": True,
            "snapshot_restore_used_for_main_scene": False,
            "main_scene_restored": False,
            "oracle_snapshot_restore_isolated_to_disjoint_scene": True,
            "trace_path": str(trace_path),
            "tape_sha256": str(meta.get("tape_sha256", "")),
            "robotwin_runtime": _runtime_git(Path(args.robotwin_root)),
            "stage2f_source_sha256": _stage2f_source_sha256(Path(__file__).resolve().parents[1]),
            "wall_time_s": time.perf_counter() - started,
            "accepted": False,
            "pai_job_created": False,
        }
        return result
    except BaseException as exc:
        body_error = exc
        raise
    finally:
        cleanup_errors = _close_stacks_fail_closed(oracle_stack, main_stack)
        for value in (oracle, task):
            if value is not None:
                try:
                    value.close_env(clear_cache=True)
                except Exception:
                    pass
        if cleanup_errors:
            message = "knob cleanup failed: " + "; ".join(cleanup_errors)
            if body_error is not None:
                body_error.add_note(message)
            else:
                raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--robotwin-root", type=Path, required=True)
    parser.add_argument("--tape", type=Path, required=True)
    parser.add_argument("--meta", type=Path, required=True)
    parser.add_argument("--active-tape", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--knob", required=True)
    parser.add_argument("--soft-arm", choices=("left", "right"), required=True)
    parser.add_argument("--gamma", type=float, required=True)
    parser.add_argument("--repeat", type=int, default=0)
    parser.add_argument("--launch-index", type=int, default=0)
    parser.add_argument("--active-amplitude-m", type=float, default=0.015)
    parser.add_argument("--stride", type=int, default=25)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run_cell(args)
        write_json(args.output, result)
        print(
            f"STAGE2F_CELL seed={args.seed} knob={args.knob} soft={args.soft_arm} "
            f"gamma={args.gamma} samples={result['sample_count']} COMPLETE",
            flush=True,
        )
        return 0
    except Exception as exc:
        failure = args.output.with_suffix(".failure.json")
        write_json(failure, {
            "status": "FAILED",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "accepted": False,
            "pai_job_created": False,
        })
        raise


if __name__ == "__main__":
    raise SystemExit(main())
