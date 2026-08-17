from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import traceback
from pathlib import Path

import numpy as np

from stage2_robotwin.stage2b.intervention.task_frame import ObjectTaskFrame
from stage2_robotwin.stage2b.operator.local_effect_gain import task_direction_joint_delta
from stage2_robotwin.stage2c.replay.fresh_prefix_runner import ConditionOverride
from stage2_robotwin.stage2c.replay.tape import ExpertTape
from stage2_robotwin.stage2d.scripts.run_capacity_audit import _drive
from stage2_robotwin.responsibility.oracle_brancher import _tcp_position
from stage2_robotwin.wrappers.counterfactual_brancher import gripper_object_contacts, object_state
from stage2_robotwin.wrappers.robotwin_runtime import build_handover_block

from stage3_hybrid.modes import MODE_BY_NAME, command_hash, compose_item


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def sha256_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def receiver_item(tape: ExpertTape, step: int, receiver: str, e2: int,
                  condition: dict, grasp_delta: np.ndarray | None) -> dict:
    delay = int(condition.get("receiver_delay_steps", 0))
    source = max(e2, step - delay) if step >= e2 else step
    item = tape.item(source)
    base = tape.item(e2)
    gain = float(condition.get("receiver_gain", 1.0))
    if step >= e2 and gain != 1.0:
        item[f"{receiver}_position"] = (
            np.asarray(base[f"{receiver}_position"]) + gain *
            (np.asarray(item[f"{receiver}_position"]) - np.asarray(base[f"{receiver}_position"]))
        )
        item[f"{receiver}_velocity"] = gain * np.asarray(item[f"{receiver}_velocity"])
    if step >= e2 and grasp_delta is not None:
        item[f"{receiver}_position"] = np.asarray(item[f"{receiver}_position"]) + grasp_delta
    return item


def run(args) -> dict:
    tape = ExpertTape.load(args.tape)
    meta = json.loads(args.meta.read_text())
    condition = json.loads(args.condition_json)
    seed, episode = int(meta["seed"]), int(meta["episode"])
    donor, receiver = str(meta["donor"]), str(meta["receiver"])
    events = {key: int(value) for key, value in meta["events"].items()}
    e2, e3, e4 = events["E2"], events["E3"], events["E4"]
    anchor = max(e3 + 25, e4 - 100)
    task = override = None
    started = time.perf_counter()
    try:
        task, kwargs = build_handover_block(str(args.robotwin_root), planner="mplib_screw")
        task.setup_demo(now_ep_num=episode, seed=seed, **kwargs)
        frame = ObjectTaskFrame.from_task(task)
        override = ConditionOverride(task, receiver, condition, frame)
        grasp_delta = None
        positions, linear, angular, contacts, tcp_left, tcp_right = [], [], [], [], [], []
        command_items, base_items, prefix_items = [], [], []
        donor_sources, deviations, release_steps = [], [], []
        donor_contact_steps, receiver_only_streak, max_receiver_only = [], 0, 0
        anchor_relative = None
        for step in range(len(tape)):
            if step == e2:
                override.apply()
                offset = float(condition.get("receiver_grasp_offset_mm", 0.0)) / 1000.0
                if offset:
                    grasp_delta, _ = task_direction_joint_delta(
                        task, receiver, frame.e_perp, offset, max_joint_delta_rad=0.12)
            item, donor_source = compose_item(tape, step, donor, args.mode, e4)
            receiver_raw = receiver_item(tape, step, receiver, e2, condition, grasp_delta)
            for suffix in ("position", "velocity", "gripper"):
                item[f"{receiver}_{suffix}"] = receiver_raw[f"{receiver}_{suffix}"]
            command_items.append(item)
            base_items.append(tape.item(step))
            if step < anchor:
                prefix_items.append(item)
            donor_sources.append(donor_source)
            original = tape.item(step)
            deviations.append(float(np.linalg.norm(
                np.asarray(item[f"{donor}_position"]) - np.asarray(original[f"{donor}_position"]))))
            command = item[f"{donor}_gripper"]
            if command is not None and command[0] > 0.2:
                release_steps.append(step)
            _drive(task, item)
            state = object_state(task)
            touch = gripper_object_contacts(task)
            positions.append(np.asarray(state["pose"][:3], dtype=float))
            linear.append(np.asarray(state["linear_velocity"], dtype=float))
            angular.append(np.asarray(state["angular_velocity"], dtype=float))
            contacts.append([touch["left"], touch["right"]])
            tcp_left.append(_tcp_position(task, "left"))
            tcp_right.append(_tcp_position(task, "right"))
            if step == anchor:
                anchor_relative = {
                    "left": positions[-1] - tcp_left[-1],
                    "right": positions[-1] - tcp_right[-1],
                }
            if step >= anchor:
                if touch[donor]:
                    donor_contact_steps.append(step)
                receiver_only_streak = receiver_only_streak + 1 if touch[receiver] and not touch[donor] else 0
                max_receiver_only = max(max_receiver_only, receiver_only_streak)
        success = bool(task.plan_success and task.check_success())
        pos, vel, omg = map(np.asarray, (positions, linear, angular))
        con = np.asarray(contacts, dtype=bool)
        tcps = {"left": np.asarray(tcp_left), "right": np.asarray(tcp_right)}
        jerk = np.diff(vel[anchor:], axis=0) * 250.0
        slip = {}
        for side in ("left", "right"):
            rel = pos[anchor:] - tcps[side][anchor:]
            mask = con[anchor:, 0 if side == "left" else 1]
            values = np.linalg.norm(rel - anchor_relative[side], axis=1)
            slip[side] = values[mask]
        retention = max_receiver_only >= 50
        first_takeover = None
        streak = 0
        for index in range(anchor, len(tape)):
            touch = con[index]
            streak = streak + 1 if touch[0 if receiver == "left" else 1] and not touch[0 if donor == "left" else 1] else 0
            if streak >= 50:
                first_takeover = index - 49
                break
        short = {}
        for horizon in (50, 100, 200):
            idx = min(anchor + horizon, len(tape) - 1)
            short[str(horizon)] = {
                "object_height_m": float(pos[idx, 2]),
                "object_displacement_m": float(np.linalg.norm(pos[idx] - pos[anchor])),
                "linear_speed": float(np.linalg.norm(vel[idx])),
                "angular_speed": float(np.linalg.norm(omg[idx])),
                "donor_contact": bool(con[idx, 0 if donor == "left" else 1]),
                "receiver_contact": bool(con[idx, 0 if receiver == "left" else 1]),
                "donor_action_deviation_mean": float(np.mean(deviations[anchor:idx + 1])),
            }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        trace_path = args.output.with_suffix(".trace.npz")
        np.savez_compressed(trace_path, object_position=pos, object_linear_velocity=vel,
                            object_angular_velocity=omg, contacts=con)
        return {
            "schema": "r22p19.stage3a.cell.v1", "status": "COMPLETE",
            "seed": seed, "episode": episode, "condition": args.condition_name,
            "condition_parameters": condition, "mode": args.mode, "repeat": args.repeat,
            "launch_index": args.launch_index, "pid": os.getpid(), "donor": donor,
            "receiver": receiver, "events": events, "anchor_step": anchor,
            "fresh_process": True, "fresh_scene": True,
            "replayed_from_episode_start": True, "snapshot_restore_used": False,
            "receiver_command_sha256": command_hash(command_items, receiver),
            "donor_base_command_sha256": command_hash(base_items, donor),
            "donor_modified_command_sha256": command_hash(command_items, donor),
            "prefix_command_sha256": command_hash(prefix_items, "left") + ":" + command_hash(prefix_items, "right"),
            "tape_sha256": sha256_file(args.tape), "meta_sha256": sha256_file(args.meta),
            "donor_source_first_changed": next((i for i, value in enumerate(donor_sources) if i != value), None),
            "trace": trace_path.name,
            "metrics": {
                "eventual_task_success": success,
                "handover_complete": retention,
                "receiver_only_retention_steps": max_receiver_only,
                "receiver_only_retention": retention,
                "drop": bool(np.min(pos[anchor:, 2]) < 0.78),
                "takeover_failure": not retention,
                "final_left_contact": bool(con[-1, 0]), "final_right_contact": bool(con[-1, 1]),
                "donor_final_contact": bool(con[-1, 0 if donor == "left" else 1]),
                "receiver_final_contact": bool(con[-1, 0 if receiver == "left" else 1]),
                "donor_residual_duration_steps": max(0, max(donor_contact_steps, default=e4) - e4),
                "takeover_delay_steps": None if first_takeover is None else first_takeover - e4,
                "min_object_height_m": float(np.min(pos[anchor:, 2])),
                "trajectory_rmse_to_base_m": None,
                "peak_object_linear_jerk": float(np.linalg.norm(jerk, axis=1).max(initial=0.0)),
                "peak_object_angular_velocity": float(np.linalg.norm(omg[anchor:], axis=1).max(initial=0.0)),
                "peak_relative_slip_m": float(max(slip["left"].max(initial=0.0), slip["right"].max(initial=0.0))),
                "donor_action_deviation_mean": float(np.mean(deviations[anchor:])),
                "donor_release_step": min(release_steps) if release_steps else None,
                "release_time": None if not release_steps else min(release_steps) / 250.0,
            },
            "short_horizon_features": short, "wall_time_s": time.perf_counter() - started,
            "accepted": False, "pai_job_created": False,
        }
    finally:
        if override is not None:
            override.close()
        if task is not None:
            try:
                task.close_env(clear_cache=True)
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--robotwin-root", type=Path, required=True)
    parser.add_argument("--tape", type=Path, required=True)
    parser.add_argument("--meta", type=Path, required=True)
    parser.add_argument("--condition-name", required=True)
    parser.add_argument("--condition-json", required=True)
    parser.add_argument("--mode", choices=tuple(MODE_BY_NAME), required=True)
    parser.add_argument("--repeat", type=int, required=True)
    parser.add_argument("--launch-index", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args)
        write_json(args.output, result)
        print(f"STAGE3_CELL {args.condition_name} {args.mode} r{args.repeat} COMPLETE", flush=True)
        return 0
    except Exception as exc:
        write_json(args.output.with_suffix(".failure.json"), {
            "status": "FAILED", "error_type": type(exc).__name__, "error": str(exc),
            "traceback": traceback.format_exc(), "accepted": False, "pai_job_created": False})
        raise


if __name__ == "__main__":
    raise SystemExit(main())
