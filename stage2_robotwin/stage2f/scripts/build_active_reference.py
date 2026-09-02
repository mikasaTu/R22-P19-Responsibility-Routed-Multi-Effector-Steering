"""Freeze one nominal active-reference command tape for cross-gamma isolation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from stage2_robotwin.stage2b.intervention.task_frame import ObjectTaskFrame
from stage2_robotwin.stage2c.replay.tape import ExpertTape
from stage2_robotwin.stage2d.scripts.run_capacity_audit import _active_item, _drive
from stage2_robotwin.wrappers.robotwin_runtime import build_handover_block


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--robotwin-root", type=Path, required=True)
    parser.add_argument("--tape", type=Path, required=True)
    parser.add_argument("--meta", type=Path, required=True)
    parser.add_argument("--seed", type=int, choices=(0, 1), required=True)
    parser.add_argument("--active-amplitude-m", type=float, default=0.015)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    tape = ExpertTape.load(args.tape)
    meta = json.loads(args.meta.read_text(encoding="utf-8"))
    if int(meta["seed"]) != args.seed:
        raise ValueError("seed mismatch")
    events = {key: int(value) for key, value in meta["events"].items()}
    task = None
    try:
        task, kwargs = build_handover_block(str(args.robotwin_root), planner="mplib_screw")
        task.setup_demo(now_ep_num=int(meta["episode"]), seed=args.seed, **kwargs)
        frame = ObjectTaskFrame.from_task(task)
        records = []
        for index in range(len(tape)):
            raw = tape.item(index)
            item, _ = _active_item(task, raw, int(raw["step"]), events, frame, args.active_amplitude_m)
            records.append(item)
            _drive(task, item)
        payload: dict[str, np.ndarray] = {"steps": np.asarray([int(item["step"]) for item in records], dtype=np.int64)}
        for side in ("left", "right"):
            payload[f"{side}_position"] = np.asarray([item[f"{side}_position"] for item in records], dtype=np.float64)
            payload[f"{side}_velocity"] = np.asarray([item[f"{side}_velocity"] for item in records], dtype=np.float64)
            payload[f"{side}_gripper_valid"] = np.asarray([item[f"{side}_gripper"] is not None for item in records], dtype=bool)
            payload[f"{side}_gripper"] = np.asarray([
                item[f"{side}_gripper"] if item[f"{side}_gripper"] is not None else (0.0, 0.0)
                for item in records
            ], dtype=np.float64)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(args.output, **payload)
        digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
        receipt = {
            "schema": "r22p19.stage2f.frozen_active_reference.v1",
            "status": "COMPLETE",
            "seed": args.seed,
            "episode": int(meta["episode"]),
            "events": events,
            "amplitude_m": float(args.active_amplitude_m),
            "axis": "e_perp",
            "both_arms_common_mode": True,
            "source_tape_sha256": str(meta.get("tape_sha256", "")),
            "command_count": len(records),
            "npz_sha256": digest,
            "accepted": False,
            "pai_job_created": False,
        }
        args.output.with_suffix(".json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        print(f"ACTIVE_REFERENCE seed={args.seed} commands={len(records)} sha256={digest} COMPLETE", flush=True)
        return 0
    finally:
        if task is not None:
            try:
                task.close_env(clear_cache=True)
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())

