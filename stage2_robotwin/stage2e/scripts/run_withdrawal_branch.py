from __future__ import annotations

import argparse
import json
import os
import time
import traceback
from pathlib import Path

import numpy as np

from stage2_robotwin.stage2b.intervention.task_frame import ObjectTaskFrame
from stage2_robotwin.stage2c.replay.tape import ExpertTape
from stage2_robotwin.stage2d.scripts.run_capacity_audit import _active_item, _drive
from stage2_robotwin.stage2e.conformance.method_registry import get_method
from stage2_robotwin.stage2e.conformance.runtime_receipt import RuntimeReceipt
from stage2_robotwin.stage2e.withdrawal.common import (
    contact_wrench_by_side,
    receiver_command_hash,
)
from stage2_robotwin.stage2e.withdrawal import motion_withdrawal
from stage2_robotwin.stage2e.withdrawal import retention_withdrawal
from stage2_robotwin.stage2e.withdrawal import rotation_withdrawal
from stage2_robotwin.stage2e.withdrawal import support_withdrawal
from stage2_robotwin.wrappers.counterfactual_brancher import gripper_object_contacts, object_state
from stage2_robotwin.wrappers.robotwin_runtime import build_handover_block


METHOD_BY_CHANNEL = {
    "motion": "W2_MOTION_WITHDRAWAL",
    "support": "W3_SUPPORT_WITHDRAWAL",
    "rotation": "W4_ROTATION_WITHDRAWAL",
    "retention": "W5_RETENTION_WITHDRAWAL",
}
ARM_APPLIERS = {
    "motion": motion_withdrawal.apply,
    "support": support_withdrawal.apply,
    "rotation": rotation_withdrawal.apply,
}


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def run_branch(args) -> dict:
    tape = ExpertTape.load(args.tape)
    meta = json.loads(Path(args.meta).read_text())
    seed, episode = int(meta["seed"]), int(meta["episode"])
    donor, receiver = str(meta["donor"]), str(meta["receiver"])
    events = {key: int(value) for key, value in meta["events"].items()}
    anchor_step = int(round((events["E3"] + events["E4"]) / 2))
    task = None
    started = time.perf_counter()
    method = get_method(METHOD_BY_CHANNEL[args.channel])
    receipt = RuntimeReceipt(method)
    try:
        task, kwargs = build_handover_block(str(args.robotwin_root), planner="mplib_screw")
        task.setup_demo(now_ep_num=episode, seed=seed, **kwargs)
        frame = ObjectTaskFrame.from_task(task)
        anchor_index = None
        active_future = []
        for index in range(len(tape)):
            raw = tape.item(index)
            step = int(raw["step"])
            item, _ = _active_item(task, raw, step, events, frame, args.active_amplitude_m)
            _drive(task, item)
            if step >= anchor_step:
                anchor_index = index
                break
        if anchor_index is None:
            raise RuntimeError("withdrawal anchor was not reached")
        for index in range(anchor_index + 1, min(len(tape), anchor_index + 1 + args.horizon)):
            raw = tape.item(index)
            item, _ = _active_item(task, raw, int(raw["step"]), events, frame,
                                   args.active_amplitude_m)
            active_future.append(item)
        if len(active_future) < args.horizon:
            raise RuntimeError("insufficient future horizon")
        receiver_hash = receiver_command_hash(active_future, receiver)
        start_state = object_state(task)
        rows = []
        command_audits = []
        donor_arm_modifications = []
        for item in active_future:
            targets = {
                side: (np.asarray(item[f"{side}_position"], dtype=float).copy(),
                       np.asarray(item[f"{side}_velocity"], dtype=float).copy())
                for side in ("left", "right")
            }
            commands = {side: item[f"{side}_gripper"] for side in ("left", "right")}
            if args.channel == "retention":
                commands[donor] = retention_withdrawal.apply(commands[donor], args.fade)
                audit = {"channel": args.channel, "fade": args.fade,
                         "control_mode": "real_gripper_open_target_interpolation"}
                donor_arm_modifications.append(0.0)
            else:
                base_position = targets[donor][0].copy()
                targets[donor] = ARM_APPLIERS[args.channel](
                    task, donor, targets[donor][0], targets[donor][1], frame, args.fade)
                position, velocity, audit = targets[donor]
                targets[donor] = (position, velocity)
                donor_arm_modifications.append(float(np.linalg.norm(position - base_position)))
            receipt.record_action_modification(f"{args.channel}:fade={args.fade}")
            command_audits.append(audit)
            for side in ("left", "right"):
                task.robot.set_arm_joints(*targets[side], side)
                if commands[side] is not None:
                    task.robot.set_gripper(commands[side][0], side, commands[side][1])
            task.scene.step()
            wrench = contact_wrench_by_side(task, frame)
            contacts = gripper_object_contacts(task)
            state = object_state(task)
            rows.append({
                "step": int(item["step"]),
                "donor_wrench": wrench[donor],
                "receiver_wrench": wrench[receiver],
                "contacts": contacts,
                "object_pose": state["pose"].tolist(),
            })
        effects = {
            channel: float(sum(row["donor_wrench"][channel] for row in rows))
            for channel in ("motion", "support", "rotation", "retention")
        }
        contact_fraction = float(np.mean([row["contacts"][donor] for row in rows]))
        final_state = object_state(task)
        runtime = receipt.validate()
        return {
            "schema": "r22p19.stage2e.withdrawal_branch.v1",
            "status": "COMPLETE",
            "seed": seed,
            "episode": episode,
            "donor": donor,
            "receiver": receiver,
            "channel": args.channel,
            "fade": float(args.fade),
            "repeat": int(args.repeat),
            "launch_index": int(args.launch_index),
            "pid": os.getpid(),
            "fresh_process": True,
            "fresh_scene": True,
            "replayed_from_episode_start": True,
            "snapshot_restore_used": False,
            "anchor_step": anchor_step,
            "horizon_steps": len(rows),
            "receiver_command_sha256": receiver_hash,
            "donor_effect_integrals": effects,
            "donor_contact_fraction": contact_fraction,
            "donor_final_contact": bool(rows[-1]["contacts"][donor]),
            "receiver_contact_fraction": float(np.mean([row["contacts"][receiver] for row in rows])),
            "donor_arm_modification_l2_mean": float(np.mean(donor_arm_modifications)),
            "object_translation_m": (final_state["pose"][:3] - start_state["pose"][:3]).tolist(),
            "command_audit_summary": {
                "control_mode": command_audits[0]["control_mode"],
                "mean_selected_twist_norm": float(np.mean([
                    item.get("selected_twist_norm", 0.0) for item in command_audits])),
                "mean_unselected_twist_norm": float(np.mean([
                    item.get("unselected_twist_norm", 0.0) for item in command_audits])),
            },
            "method_receipt": runtime,
            "wall_time_s": time.perf_counter() - started,
            "accepted": False,
            "pai_job_created": False,
        }
    finally:
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
    parser.add_argument("--channel", choices=("motion", "support", "rotation", "retention"), required=True)
    parser.add_argument("--fade", type=float, required=True)
    parser.add_argument("--repeat", type=int, required=True)
    parser.add_argument("--launch-index", type=int, required=True)
    parser.add_argument("--horizon", type=int, default=60)
    parser.add_argument("--active-amplitude-m", type=float, default=0.015)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run_branch(args)
        write_json(args.output, result)
        print(f"WITHDRAWAL_BRANCH {args.channel} fade={args.fade} repeat={args.repeat} COMPLETE", flush=True)
        return 0
    except Exception as exc:
        write_json(args.output.with_suffix(".failure.json"), {
            "status": "FAILED", "error_type": type(exc).__name__, "error": str(exc),
            "traceback": traceback.format_exc(), "accepted": False, "pai_job_created": False})
        raise


if __name__ == "__main__":
    raise SystemExit(main())
