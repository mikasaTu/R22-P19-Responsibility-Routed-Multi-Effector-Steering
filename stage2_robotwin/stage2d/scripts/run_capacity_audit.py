"""Run actual same-state donor-fade branches in RoboTwin/SAPIEN.

This audit replays a frozen successful expert tape in the main scene and copies only
explicit state into a disjoint oracle scene at each branch point.  It never restores
the main scene and holds both grippers in all fade branches.
"""
from __future__ import annotations

import argparse
import json
import time
import traceback
from pathlib import Path
from typing import Optional
import numpy as np

from stage2_robotwin.stage2c.replay.tape import ExpertTape
from stage2_robotwin.stage2c.scripts.run_natural_responsibility import discover_tapes
from stage2_robotwin.stage2b.intervention.task_frame import ObjectTaskFrame
from stage2_robotwin.stage2b.operator.local_effect_gain import task_direction_joint_delta
from stage2_robotwin.stage2c.replay.fresh_prefix_runner import ConditionOverride
from stage2_robotwin.stage2d.capacity.channel_capacity import score_channels
from stage2_robotwin.stage2d.capacity.donor_fade import donor_fade_rollouts
from stage2_robotwin.stage2d.tasks.active_handover_block import audit_active_window
from stage2_robotwin.responsibility.oracle_brancher import _contact_impulses
from stage2_robotwin.wrappers.counterfactual_brancher import SapienSnapshot, gripper_object_contacts, object_state
from stage2_robotwin.wrappers.robotwin_runtime import build_handover_block


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _drive(task, item, include_grippers=True):
    for side in ("left", "right"):
        task.robot.set_arm_joints(np.asarray(item[f"{side}_position"]),
                                  np.asarray(item[f"{side}_velocity"]), side)
        command = item[f"{side}_gripper"]
        if include_grippers and command is not None:
            task.robot.set_gripper(command[0], side, command[1])
    task.scene.step()


def _active_item(task, item, step: int, events: dict, frame: ObjectTaskFrame,
                 amplitude_m: float) -> tuple[dict, float]:
    value = dict(item)
    if not (events["E3"] <= step <= events["E5"]):
        return value, 0.0
    phase = (step - events["E3"]) / max(events["E5"] - events["E3"], 1)
    offset = float(amplitude_m * np.sin(np.pi * phase))
    for side in ("left", "right"):
        delta, _ = task_direction_joint_delta(task, side, frame.e_perp, offset,
                                               max_joint_delta_rad=0.12)
        value[f"{side}_position"] = np.asarray(item[f"{side}_position"]) + delta
    return value, offset


def audit_seed(robotwin_root: Path, tape_path: Path, meta_path: Path, output: Path,
               condition: dict, states: int, horizon: int, active_amplitude_m: float,
               video_dir: Optional[Path] = None) -> dict:
    meta = json.loads(meta_path.read_text())
    tape = ExpertTape.load(tape_path)
    seed, episode = int(meta["seed"]), int(meta["episode"])
    donor, receiver = str(meta["donor"]), str(meta["receiver"])
    receiver_index = 0 if receiver == "left" else 1
    events = {k: int(v) for k, v in meta["events"].items()}
    branch_steps = np.linspace(events["E3"], events["E4"], states, dtype=int).tolist() if states else []
    task = oracle = override = None
    started = time.perf_counter()
    try:
        task, kwargs = build_handover_block(str(robotwin_root), planner="mplib_screw")
        task.setup_demo(now_ep_num=episode, seed=seed, **kwargs)
        oracle, okwargs = build_handover_block(str(robotwin_root), planner="mplib_screw")
        oracle.setup_demo(now_ep_num=episode, seed=seed, **okwargs)
        frame = ObjectTaskFrame.from_task(task)
        override = ConditionOverride(oracle, receiver, condition, frame)
        override.apply()
        rows, positions, references, contacts, frames = [], [], [], [], []
        branch_set = set(branch_steps)
        reference_origin = None
        for index in range(len(tape)):
            raw_item = tape.item(index)
            step = int(raw_item["step"])
            item, active_offset = _active_item(task, raw_item, step, events, frame,
                                               active_amplitude_m)
            _drive(task, item)
            if video_dir is not None and events["E3"] <= step <= events["E5"] and step % 25 == 0:
                task._update_render()
                frames.append(np.ascontiguousarray(task.cameras.get_observer_rgb().copy()))
            if events["E3"] <= step <= events["E5"]:
                position = object_state(task)["pose"][:3]
                if reference_origin is None:
                    reference_origin = position.copy()
                positions.append(position.tolist())
                references.append((reference_origin + active_offset * np.asarray(frame.e_perp)).tolist())
                contacts.append(gripper_object_contacts(task))
            if step not in branch_set:
                continue
            future = []
            for j in range(index + 1, min(len(tape), index + 1 + horizon)):
                raw_future = tape.item(j)
                modified, _ = _active_item(task, raw_future, int(raw_future["step"]),
                                           events, frame, active_amplitude_m)
                future.append(modified)
            snapshot = SapienSnapshot.capture(task)
            SapienSnapshot.restore(oracle, snapshot)
            impulses = _contact_impulses(task)
            rollout = donor_fade_rollouts(
                oracle, snapshot, future, donor,
                receiver_gain=float(condition.get("receiver_gain", 1.0)),
                receiver_delay=int(condition.get("receiver_delay_steps", 0)),
            )
            full = rollout["outcomes"]["1.0"]
            faded = rollout["outcomes"]["0.0"]
            channels = score_channels(full, faded, receiver_index)
            rows.append({
                "step": step, "normalized_phase": (step-events["E3"])/max(events["E5"]-events["E3"], 1),
                "capacity": channels.as_dict(), "rollout": rollout,
                "receiver_contact": gripper_object_contacts(task)[receiver],
                "receiver_impulse": float(impulses[receiver]),
                "donor_impulse": float(impulses[donor]),
            })
        pos = np.asarray(positions)
        reference = np.asarray(references)
        active = audit_active_window(pos, reference, 250.0).__dict__ if len(pos) else {"valid": False}
        video_path = None
        if video_dir is not None:
            import imageio.v2 as imageio
            video_dir.mkdir(parents=True, exist_ok=True)
            video_path = video_dir / f"active_seed_{seed:04d}.mp4"
            imageio.mimsave(video_path, frames, fps=10, macro_block_size=1)
        return {"status": "COMPLETE", "seed": seed, "episode": episode,
                "donor": donor, "receiver": receiver, "condition": condition,
                "branch_count": len(rows) * 5, "simulated_physics_steps": len(rows) * 5 * horizon,
                "active_window": active, "overlap_contact_fraction": float(np.mean([
                    c["left"] and c["right"] for c in contacts])) if contacts else 0.0,
                "active_reference_amplitude_m": active_amplitude_m,
                "task_success_after_active_reference": bool(task.plan_success and task.check_success()),
                "video": str(video_path) if video_path else None,
                "states": rows, "wall_time_s": time.perf_counter()-started,
                "fresh_main_scene": True, "disjoint_oracle_scene": True,
                "main_scene_restored": False, "accepted": False, "pai_job_created": False}
    finally:
        if override is not None:
            override.close()
        for value in (oracle, task):
            if value is not None:
                try: value.close_env(clear_cache=True)
                except Exception: pass


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--robotwin-root", type=Path, required=True)
    p.add_argument("--tape-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--seeds", type=int, nargs="+", required=True)
    p.add_argument("--condition-json", default="{}")
    p.add_argument("--states", type=int, default=5)
    p.add_argument("--horizon", type=int, default=50)
    p.add_argument("--active-amplitude-m", type=float, default=0.015)
    p.add_argument("--video-dir", type=Path)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    tapes = discover_tapes(args.tape_root)
    condition = json.loads(args.condition_json)
    receipts = []
    for seed in args.seeds:
        try:
            pair = tapes[seed]
            result = audit_seed(args.robotwin_root, pair[0], pair[1], args.output, condition,
                                args.states, args.horizon, args.active_amplitude_m, args.video_dir)
            write_json(args.output / f"seed_{seed:04d}.json", result)
            receipts.append({"seed": seed, "status": "COMPLETE", "path": f"seed_{seed:04d}.json"})
        except Exception as exc:
            receipts.append({"seed": seed, "status": "FAILED", "error": str(exc),
                             "traceback": traceback.format_exc()})
        write_json(args.output / "receipts.json", receipts)
        print(f"CAPACITY_AUDIT seed={seed} status={receipts[-1]['status']}", flush=True)
    return 0 if all(r["status"] == "COMPLETE" for r in receipts) else 1


if __name__ == "__main__":
    raise SystemExit(main())
