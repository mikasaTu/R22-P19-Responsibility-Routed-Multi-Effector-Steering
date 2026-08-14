"""Run natural and soft hidden-authority profiles in fresh processes."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import numpy as np
import yaml

from stage2_robotwin.stage2b.baselines.phase_blend import phase_weights
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
from stage2_robotwin.stage2c.responsibility.natural_analysis import (
    analyze_natural_responsibility,
)
from stage2_robotwin.stage2c.responsibility.natural_responsibility import (
    NaturalResponsibilityEstimator,
)
from stage2_robotwin.wrappers.counterfactual_brancher import SapienSnapshot
from stage2_robotwin.wrappers.robotwin_runtime import build_handover_block


def discover_tapes(root: Path) -> Dict[int, tuple[Path, Path]]:
    found = {}
    for tape in root.rglob("seed_*.npz"):
        meta = tape.with_suffix(".json")
        if not meta.is_file():
            continue
        seed = int(json.loads(meta.read_text(encoding="utf-8"))["seed"])
        if seed in found:
            raise ValueError(f"duplicate tape for seed {seed}")
        found[seed] = (tape, meta)
    return found


def _future_risk(trace: Mapping[str, np.ndarray], step: int, horizon: int = 20) -> Dict[str, float]:
    end = min(step + horizon + 1, len(trace["object_position"]))
    linear = trace["object_linear_velocity"][step:end]
    angular = trace["object_angular_velocity"][step:end]
    contacts = trace["contacts"][step:end]
    positions = trace["object_position"][step:end]
    left_tcp = trace["left_tcp_position"][step:end]
    right_tcp = trace["right_tcp_position"][step:end]
    jerk = np.diff(linear, axis=0) * 250.0 if len(linear) > 1 else np.zeros((0, 3))
    if len(positions):
        left_relative = positions - left_tcp
        right_relative = positions - right_tcp
        left_slip = np.linalg.norm(left_relative - left_relative[0], axis=1)
        right_slip = np.linalg.norm(right_relative - right_relative[0], axis=1)
        masked_slip = max(
            left_slip[contacts[:, 0]].max(initial=0.0),
            right_slip[contacts[:, 1]].max(initial=0.0),
        )
    else:
        masked_slip = 0.0
    return {
        "peak_angular_velocity": float(np.linalg.norm(angular, axis=1).max(initial=0.0)),
        "peak_linear_jerk": float(np.linalg.norm(jerk, axis=1).max(initial=0.0)),
        "contact_masked_slip": float(masked_slip),
        "release_contact_risk": float(np.mean(~contacts[:, 1])) if len(contacts) else 0.0,
    }


def run_profile_cell(cell: Mapping[str, Any]) -> Dict[str, Any]:
    output = Path(cell["output"])
    result_path = output / "result.json"
    if result_path.is_file():
        return json.loads(result_path.read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=True)
    tape = ExpertTape.load(cell["tape"])
    meta = json.loads(Path(cell["meta"]).read_text(encoding="utf-8"))
    config = yaml.safe_load(Path(cell["config"]).read_text(encoding="utf-8"))
    seed = int(meta["seed"])
    episode = int(meta["episode"])
    donor = str(meta["donor"])
    receiver = str(meta["receiver"])
    events = {name: int(value) for name, value in meta["events"].items()}
    profile = str(cell["profile"])
    gamma = cell.get("gamma")
    soft_arm = None
    if profile == "LEFT_HIDDEN_AUTHORITY":
        soft_arm = "right"
    elif profile == "RIGHT_HIDDEN_AUTHORITY":
        soft_arm = "left"

    task = oracle_task = None
    started = time.perf_counter()
    try:
        task, task_args = build_handover_block(str(cell["robotwin_root"]), planner="mplib_screw")
        task.setup_demo(now_ep_num=episode, seed=seed, **task_args)
        oracle_task, oracle_args = build_handover_block(str(cell["robotwin_root"]), planner="mplib_screw")
        oracle_task.setup_demo(now_ep_num=episode, seed=seed, **oracle_args)
        frame = ObjectTaskFrame.from_task(task)
        horizons = tuple(int(value) for value in config["natural_responsibility"]["horizons"])
        estimator = NaturalResponsibilityEstimator(horizons)
        recorder = ReplayRecorder(task, donor, events)
        soft = None
        prefix = None
        sample_records = []
        start = events["E4"] + int(config["natural_responsibility"]["window_start_relative_to_E4"])
        end = min(
            events["E5"],
            events["E4"] + int(config["natural_responsibility"]["window_end_relative_to_E4"]),
        )
        sample_steps = set(range(start, end + 1, int(config["natural_responsibility"]["stride_steps"])))
        for index in range(len(tape)):
            item = tape.item(index)
            step = int(item["step"])
            if step == events["E2"]:
                prefix = _prefix_fingerprint(task, step - 1)
                if soft_arm is not None:
                    soft = SoftExpertAuthorityProfile(task, soft_arm, float(gamma), frame)
            targets = {
                "left": (item["left_position"], item["left_velocity"]),
                "right": (item["right_position"], item["right_velocity"]),
            }
            if events["E2"] <= step <= events["E5"] and soft is not None:
                targets[soft_arm], _ = soft.blend(targets[soft_arm])

            if step in sample_steps:
                SapienSnapshot.restore(oracle_task, SapienSnapshot.capture(task))
                sequence = tape.target_sequence(step, max(horizons))
                grippers = []
                for future in range(step, step + max(horizons)):
                    future_item = tape.item(future)
                    grippers.append(
                        {
                            "left": future_item["left_gripper"],
                            "right": future_item["right_gripper"],
                        }
                    )
                estimate = estimator.estimate(
                    oracle_task,
                    sequence,
                    frame,
                    soft_arm=soft_arm,
                    gamma=float(gamma) if gamma is not None else None,
                    gripper_sequence=grippers,
                )
                estimate["baselines"]["left_share"]["phase"] = float(
                    phase_weights(step, events["E3"], events["E5"], donor=donor)[0]
                )
                sample_records.append(
                    {
                        "step": step,
                        "e4_relative_step": step - events["E4"],
                        "by_horizon": {str(key): value for key, value in estimate["by_horizon"].items()},
                        "baselines": estimate["baselines"],
                        "future_risk": {},
                        "oracle_branch_count": estimate["branch_rollout_count"],
                        "simulated_physics_steps": estimate["simulated_physics_steps"],
                    }
                )

            commands = {"left": item["left_gripper"], "right": item["right_gripper"]}
            for side in ("left", "right"):
                task.robot.set_arm_joints(*targets[side], side)
                command = commands[side]
                if command is not None:
                    task.robot.set_gripper(command[0], side, command[1])
            task.scene.step()
            donor_open = step >= events["E3"] and commands[donor] is not None and commands[donor][0] > 0.2
            recorder.record(step, donor_open)

        metrics, trace = recorder.finish(bool(task.check_success()))
        for item in sample_records:
            item["future_risk"] = _future_risk(trace, int(item["step"]))
        trace_path = output / "trace.npz"
        np.savez_compressed(trace_path, **trace)
        result = {
            "status": "COMPLETE",
            "seed": seed,
            "episode": episode,
            "profile": profile,
            "gamma": gamma,
            "soft_arm": soft_arm,
            "donor": donor,
            "receiver": receiver,
            "records": sample_records,
            "sample_count": len(sample_records),
            "reference_events": events,
            "prefix_fingerprint_at_E2_minus_1": prefix,
            "tape_sha256": meta["tape_sha256"],
            "same_high_level_expert_tape": True,
            "assignment_unobservable_before_E2": True,
            "oracle_sandbox_separate_scene": True,
            "oracle_snapshot_restore_writes_main_scene": False,
            "metrics": metrics,
            "trace_path": str(trace_path),
            "wall_time_s": time.perf_counter() - started,
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
        for value in (oracle_task, task):
            if value is not None:
                try:
                    value.close_env(clear_cache=True)
                except Exception:
                    pass


def _run_subprocess(cell: Mapping[str, Any]) -> Dict[str, Any]:
    result_path = Path(cell["output"]) / "result.json"
    if result_path.is_file():
        return {"status": "REUSED_COMPLETE"}
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = str(cell["gpu"])
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    payload = json.dumps({key: str(value) if isinstance(value, Path) else value for key, value in cell.items()}, sort_keys=True)
    command = [sys.executable, "-m", "stage2_robotwin.stage2c.scripts.run_natural_responsibility", "--worker-json", payload]
    completed = subprocess.run(command, cwd=cell["repo_root"], env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    Path(cell["output"]).mkdir(parents=True, exist_ok=True)
    (Path(cell["output"]) / "runtime.log").write_text(completed.stdout, encoding="utf-8")
    return {"status": "COMPLETE" if completed.returncode == 0 and result_path.is_file() else "FAILED", "returncode": completed.returncode}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--robotwin-root")
    parser.add_argument("--config")
    parser.add_argument("--tape-root")
    parser.add_argument("--output")
    parser.add_argument("--gpus", nargs="+", type=int, default=[1, 2, 3])
    parser.add_argument("--worker-json")
    args = parser.parse_args()
    if args.worker_json:
        run_profile_cell(json.loads(args.worker_json))
        return 0
    for name in ("robotwin_root", "config", "tape_root", "output"):
        if getattr(args, name) is None:
            parser.error(f"--{name.replace('_', '-')} is required")

    repo_root = Path(__file__).resolve().parents[3]
    config_path = Path(args.config).resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    tapes = discover_tapes(Path(args.tape_root).resolve())
    seeds = list(config["seed_contract"]["calibration"]) + list(config["seed_contract"]["heldout"])
    missing = sorted(set(seeds) - set(tapes))
    if missing:
        raise ValueError(f"missing tapes for {missing}")
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    cells = []
    index = 0
    for seed in seeds:
        profiles = [("NATURAL", None)]
        profiles.extend(
            (profile, float(gamma))
            for profile in ("LEFT_HIDDEN_AUTHORITY", "RIGHT_HIDDEN_AUTHORITY")
            for gamma in config["natural_responsibility"]["gammas"]
        )
        for profile, gamma in profiles:
            gamma_label = "none" if gamma is None else str(gamma).replace(".", "p")
            stem = f"seed_{int(seed):04d}__{profile}__gamma_{gamma_label}"
            cells.append(
                {
                    "seed": int(seed),
                    "profile": profile,
                    "gamma": gamma,
                    "gpu": args.gpus[index % len(args.gpus)],
                    "tape": tapes[int(seed)][0],
                    "meta": tapes[int(seed)][1],
                    "config": config_path,
                    "robotwin_root": Path(args.robotwin_root).resolve(),
                    "output": output / "cells" / stem,
                    "repo_root": repo_root,
                }
            )
            index += 1

    receipts = []
    gpu_locks = {gpu: threading.Lock() for gpu in args.gpus}

    def run_locked(cell: Mapping[str, Any]) -> Dict[str, Any]:
        with gpu_locks[int(cell["gpu"])]:
            return _run_subprocess(cell)

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(args.gpus)) as pool:
        futures = {pool.submit(run_locked, cell): cell for cell in cells}
        for count, future in enumerate(concurrent.futures.as_completed(futures), 1):
            cell = futures[future]
            try:
                receipt = future.result()
            except Exception as exc:
                receipt = {"status": "FAILED", "error": f"{type(exc).__name__}: {exc}"}
            receipts.append({"seed": cell["seed"], "profile": cell["profile"], "gamma": cell["gamma"], "gpu": cell["gpu"], **receipt})
            print(f"NATURAL_PROGRESS {count}/{len(cells)} seed={cell['seed']} profile={cell['profile']} gamma={cell['gamma']} status={receipt['status']}", flush=True)
            write_json(output / "run_receipts.partial.json", receipts)

    results = [json.loads((Path(cell["output"]) / "result.json").read_text(encoding="utf-8")) for cell in cells if (Path(cell["output"]) / "result.json").is_file()]
    analysis = analyze_natural_responsibility(results, config)
    decision = {
        "status": "COMPLETE" if len(results) == len(cells) else "INCOMPLETE",
        "expected_cells": len(cells),
        "completed_cells": len(results),
        **analysis,
        "accepted": False,
        "pai_job_created": False,
    }
    write_json(output / "NATURAL_RESPONSIBILITY_DECISION.json", decision)
    write_json(output / "run_receipts.json", receipts)
    print(f"NATURAL_COMPLETE {len(results)}/{len(cells)} decision={analysis['decision']}", flush=True)
    return 0 if len(results) == len(cells) else 2


if __name__ == "__main__":
    raise SystemExit(main())
