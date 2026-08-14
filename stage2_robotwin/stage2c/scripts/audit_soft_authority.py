"""Directly audit what the soft expert/follower blend does to applied commands."""

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
from pathlib import Path
from typing import Any, Dict, Mapping

import numpy as np
import yaml

from stage2_robotwin.stage2b.intervention.task_frame import ObjectTaskFrame
from stage2_robotwin.stage2c.intervention.soft_expert_authority import (
    SoftExpertAuthorityProfile,
)
from stage2_robotwin.stage2c.replay.fresh_prefix_runner import (
    ReplayRecorder,
    _prefix_fingerprint,
    write_json,
)
from stage2_robotwin.stage2c.replay.tape import ExpertTape
from stage2_robotwin.stage2c.scripts.run_natural_responsibility import discover_tapes
from stage2_robotwin.wrappers.robotwin_runtime import build_handover_block


def run_audit_cell(cell: Mapping[str, Any]) -> Dict[str, Any]:
    output = Path(cell["output"])
    result_path = output / "result.json"
    if result_path.is_file():
        return json.loads(result_path.read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=True)
    tape = ExpertTape.load(cell["tape"])
    meta = json.loads(Path(cell["meta"]).read_text(encoding="utf-8"))
    config = yaml.safe_load(Path(cell["config"]).read_text(encoding="utf-8"))
    seed = int(meta["seed"])
    events = {key: int(value) for key, value in meta["events"].items()}
    profile = str(cell["profile"])
    gamma = float(cell["gamma"])
    soft_arm = "right" if profile == "LEFT_HIDDEN_AUTHORITY" else "left"
    task = None
    started = time.perf_counter()
    try:
        task, task_args = build_handover_block(
            str(cell["robotwin_root"]), planner="mplib_screw"
        )
        task.setup_demo(now_ep_num=int(meta["episode"]), seed=seed, **task_args)
        frame = ObjectTaskFrame.from_task(task)
        recorder = ReplayRecorder(task, str(meta["donor"]), events)
        soft = None
        prefix = None
        records = []
        start = events["E4"] + int(
            config["natural_responsibility"]["window_start_relative_to_E4"]
        )
        end = min(
            events["E5"],
            events["E4"]
            + int(config["natural_responsibility"]["window_end_relative_to_E4"]),
        )
        sample_steps = set(
            range(
                start,
                end + 1,
                int(config["natural_responsibility"]["stride_steps"]),
            )
        )
        for index in range(len(tape)):
            item = tape.item(index)
            step = int(item["step"])
            if step == events["E2"]:
                prefix = _prefix_fingerprint(task, step - 1)
                soft = SoftExpertAuthorityProfile(task, soft_arm, gamma, frame)
            targets = {
                "left": (item["left_position"], item["left_velocity"]),
                "right": (item["right_position"], item["right_velocity"]),
            }
            audit = None
            if events["E2"] <= step <= events["E5"] and soft is not None:
                targets[soft_arm], audit = soft.blend(targets[soft_arm])
            if step in sample_steps and audit is not None:
                expert = float(audit["expert_parallel_action_m"])
                follower = float(audit["follower_parallel_action_m"])
                blended = float(audit["soft_parallel_action_m"])
                records.append(
                    {
                        "step": step,
                        "e4_relative_step": step - events["E4"],
                        "expert_parallel_action_m": expert,
                        "follower_parallel_action_m": follower,
                        "soft_parallel_action_m": blended,
                        "parallel_correction_m": float(
                            audit["parallel_correction_m"]
                        ),
                        "absolute_parallel_attenuated": abs(blended) < abs(expert),
                        "soft_over_expert_absolute_ratio": abs(blended)
                        / max(abs(expert), 1e-9),
                        "expert_sign_preserved": bool(
                            np.sign(blended) == np.sign(expert)
                        ),
                        "follower_exceeds_expert_absolute": abs(follower)
                        > abs(expert),
                    }
                )
            commands = {
                "left": item["left_gripper"],
                "right": item["right_gripper"],
            }
            for side in ("left", "right"):
                task.robot.set_arm_joints(*targets[side], side)
                if commands[side] is not None:
                    task.robot.set_gripper(
                        commands[side][0], side, commands[side][1]
                    )
            task.scene.step()
            donor = str(meta["donor"])
            donor_open = (
                commands[donor] is not None and commands[donor][0] > 0.2
            )
            recorder.record(step, donor_open)
        metrics, _ = recorder.finish(bool(task.check_success()))
        result = {
            "status": "COMPLETE",
            "seed": seed,
            "profile": profile,
            "gamma": gamma,
            "soft_arm": soft_arm,
            "sample_count": len(records),
            "records": records,
            "summary": {
                "absolute_parallel_attenuation_rate": float(
                    np.mean([item["absolute_parallel_attenuated"] for item in records])
                ),
                "median_soft_over_expert_absolute_ratio": float(
                    np.median(
                        [item["soft_over_expert_absolute_ratio"] for item in records]
                    )
                ),
                "expert_sign_preservation_rate": float(
                    np.mean([item["expert_sign_preserved"] for item in records])
                ),
                "follower_exceeds_expert_absolute_rate": float(
                    np.mean(
                        [item["follower_exceeds_expert_absolute"] for item in records]
                    )
                ),
            },
            "metrics": metrics,
            "prefix_fingerprint_at_E2_minus_1": prefix,
            "tape_sha256": meta["tape_sha256"],
            "wall_time_s": time.perf_counter() - started,
            "interpretation_boundary": (
                "gamma controls expert-source interpolation; it does not guarantee "
                "smaller physical action magnitude"
            ),
            "accepted": False,
            "pai_job_created": False,
        }
        write_json(result_path, result)
        return result
    except Exception as exc:
        write_json(
            output / "failure.json",
            {
                "status": "FAILED",
                "seed": seed,
                "profile": profile,
                "gamma": gamma,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            },
        )
        raise
    finally:
        if task is not None:
            try:
                task.close_env(clear_cache=True)
            except Exception:
                pass


def _run_subprocess(cell: Mapping[str, Any]) -> Dict[str, Any]:
    result_path = Path(cell["output"]) / "result.json"
    if result_path.is_file():
        return {"status": "REUSED_COMPLETE"}
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = str(cell["gpu"])
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    payload = json.dumps(
        {
            key: str(value) if isinstance(value, Path) else value
            for key, value in cell.items()
        },
        sort_keys=True,
    )
    command = [
        sys.executable,
        "-m",
        "stage2_robotwin.stage2c.scripts.audit_soft_authority",
        "--worker-json",
        payload,
    ]
    completed = subprocess.run(
        command,
        cwd=cell["repo_root"],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    Path(cell["output"]).mkdir(parents=True, exist_ok=True)
    (Path(cell["output"]) / "runtime.log").write_text(
        completed.stdout, encoding="utf-8"
    )
    return {
        "status": (
            "COMPLETE"
            if completed.returncode == 0 and result_path.is_file()
            else "FAILED"
        ),
        "returncode": completed.returncode,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--robotwin-root")
    parser.add_argument("--config")
    parser.add_argument("--tape-root")
    parser.add_argument("--output")
    parser.add_argument("--gamma", type=float)
    parser.add_argument("--seeds", nargs="+", type=int, default=[0, 1])
    parser.add_argument("--gpus", nargs="+", type=int, default=[1, 2, 3])
    parser.add_argument("--worker-json")
    args = parser.parse_args()
    if args.worker_json:
        run_audit_cell(json.loads(args.worker_json))
        return 0
    for name in ("robotwin_root", "config", "tape_root", "output", "gamma"):
        if getattr(args, name) is None:
            parser.error(f"--{name.replace('_', '-')} is required")
    repo_root = Path(__file__).resolve().parents[3]
    tapes = discover_tapes(Path(args.tape_root).resolve())
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    cells = []
    index = 0
    for seed in args.seeds:
        for profile in (
            "LEFT_HIDDEN_AUTHORITY",
            "RIGHT_HIDDEN_AUTHORITY",
        ):
            cells.append(
                {
                    "seed": seed,
                    "profile": profile,
                    "gamma": args.gamma,
                    "gpu": args.gpus[index % len(args.gpus)],
                    "tape": tapes[seed][0],
                    "meta": tapes[seed][1],
                    "config": Path(args.config).resolve(),
                    "robotwin_root": Path(args.robotwin_root).resolve(),
                    "output": output
                    / "cells"
                    / f"seed_{seed:04d}__{profile}__gamma_{str(args.gamma).replace('.', 'p')}",
                    "repo_root": repo_root,
                }
            )
            index += 1
    gpu_locks = {gpu: threading.Lock() for gpu in args.gpus}

    def run_locked(cell: Mapping[str, Any]) -> Dict[str, Any]:
        with gpu_locks[int(cell["gpu"])]:
            return _run_subprocess(cell)

    receipts = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(args.gpus)) as pool:
        futures = {pool.submit(run_locked, cell): cell for cell in cells}
        for count, future in enumerate(concurrent.futures.as_completed(futures), 1):
            cell = futures[future]
            receipt = future.result()
            receipts.append({"seed": cell["seed"], "profile": cell["profile"], **receipt})
            print(
                f"SOFT_AUDIT_PROGRESS {count}/{len(cells)} seed={cell['seed']} "
                f"profile={cell['profile']} status={receipt['status']}",
                flush=True,
            )
    results = [
        json.loads((Path(cell["output"]) / "result.json").read_text(encoding="utf-8"))
        for cell in cells
        if (Path(cell["output"]) / "result.json").is_file()
    ]
    decision = {
        "status": "COMPLETE" if len(results) == len(cells) else "INCOMPLETE",
        "expected_cells": len(cells),
        "completed_cells": len(results),
        "gamma": args.gamma,
        "per_cell": [
            {
                "seed": item["seed"],
                "profile": item["profile"],
                "soft_arm": item["soft_arm"],
                **item["summary"],
                "task_success": item["metrics"]["success"],
            }
            for item in results
        ],
        "aggregate": {
            key: float(np.mean([item["summary"][key] for item in results]))
            for key in (
                "absolute_parallel_attenuation_rate",
                "median_soft_over_expert_absolute_ratio",
                "expert_sign_preservation_rate",
                "follower_exceeds_expert_absolute_rate",
            )
        },
        "accepted": False,
        "pai_job_created": False,
    }
    write_json(output / "SOFT_AUTHORITY_AUDIT.json", decision)
    write_json(output / "run_receipts.json", receipts)
    print(
        f"SOFT_AUDIT_COMPLETE {len(results)}/{len(cells)}", flush=True
    )
    return 0 if len(results) == len(cells) else 2


if __name__ == "__main__":
    raise SystemExit(main())
