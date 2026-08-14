"""Capture uncontaminated full-episode low-level expert tapes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

import numpy as np
import yaml

from stage2_robotwin.stage2c.replay.tape import ExpertTape
from stage2_robotwin.wrappers.bimanual_trace_wrapper import BimanualTraceWrapper
from stage2_robotwin.wrappers.robotwin_runtime import build_handover_block


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head(path: Path) -> str:
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()


def _drive_target(task: Any, side: str) -> Tuple[np.ndarray, np.ndarray]:
    joints = task.robot.left_arm_joints if side == "left" else task.robot.right_arm_joints
    return (
        np.asarray([joint.get_drive_target()[0] for joint in joints], dtype=np.float64),
        np.asarray([joint.get_drive_velocity_target()[0] for joint in joints], dtype=np.float64),
    )


class FullExpertTapeWrapper(BimanualTraceWrapper):
    """Record every expert physics command without any snapshot/restore audit."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.action_tape: List[Dict[str, Any]] = []
        super().__init__(*args, **kwargs)

    def _after_step(self) -> None:
        # Stage 2B's wrapper runs an E3 snapshot determinism audit.  It is
        # intentionally disabled here so the reference tape accumulates only
        # a natural fresh-prefix solver history.
        sample = self._sample()
        self.trace.append(sample)
        self.step += 1

    def take_dense_action(self, control_seq: Mapping[str, Any]) -> bool:
        left_arm = control_seq["left_arm"]
        right_arm = control_seq["right_arm"]
        left_gripper = control_seq["left_gripper"]
        right_gripper = control_seq["right_gripper"]
        max_control_len = 0
        for arm in (left_arm, right_arm):
            if arm is not None:
                max_control_len = max(max_control_len, int(arm["position"].shape[0]))
        for gripper in (left_gripper, right_gripper):
            if gripper is not None:
                max_control_len = max(max_control_len, int(gripper["num_step"]))

        donor_gripper = left_gripper if self.donor == "left" else right_gripper
        if donor_gripper is not None:
            values = np.asarray(donor_gripper["result"])
            current = self.task.robot.get_left_gripper_val() if self.donor == "left" else self.task.robot.get_right_gripper_val()
            if len(values) and values[-1] > 0.8 and current < 0.3:
                self._donor_open_pending = True

        for control_idx in range(max_control_len):
            targets: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
            for side, arm in (("left", left_arm), ("right", right_arm)):
                target = self._arm_target(side, arm, control_idx)
                targets[side] = _drive_target(self.task, side) if target is None else target
            commands: Dict[str, Optional[Tuple[float, float]]] = {"left": None, "right": None}
            for side, gripper in (("left", left_gripper), ("right", right_gripper)):
                if gripper is not None and control_idx < int(gripper["num_step"]):
                    commands[side] = (
                        float(gripper["result"][control_idx]),
                        float(gripper["per_step"]),
                    )
            self.action_tape.append(
                {
                    "step": int(self.step),
                    "left_position": targets["left"][0].copy(),
                    "left_velocity": targets["left"][1].copy(),
                    "right_position": targets["right"][0].copy(),
                    "right_velocity": targets["right"][1].copy(),
                    "left_gripper": commands["left"],
                    "right_gripper": commands["right"],
                }
            )
            for side in ("left", "right"):
                self.task.robot.set_arm_joints(*targets[side], side)
                if commands[side] is not None:
                    self.task.robot.set_gripper(commands[side][0], side, commands[side][1])
            self.task.scene.step()
            self._after_step()
        return True


def event_steps(receipt: Mapping[str, Any]) -> Dict[str, int]:
    return {
        name: int(value["step"])
        for name, value in receipt["event_audit"]["events"].items()
        if value is not None
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--robotwin-root", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--seeds", nargs="+", type=int)
    parser.add_argument("--planner", default="mplib_screw", choices=("mplib_screw", "mplib_RRT"))
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    robotwin_root = Path(args.robotwin_root).resolve()
    config_path = Path(args.config).resolve()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    mapping = {int(key): int(value) for key, value in config["seed_contract"]["episode_index"].items()}
    seeds = list(args.seeds or sorted(mapping))
    unknown = sorted(set(seeds) - set(mapping))
    if unknown:
        raise ValueError(f"episode indices are not frozen for seeds {unknown}")

    import sapien
    import torch

    manifest = {
        "experiment": "R22-P19-Stage2C-full-expert-tape-capture",
        "repo_commit_at_launch": git_head(repo_root),
        "repo_dirty_at_launch": bool(subprocess.check_output(["git", "-C", str(repo_root), "status", "--porcelain"], text=True).strip()),
        "robotwin_commit": git_head(robotwin_root),
        "xpolicylab_commit": subprocess.check_output(["git", "-C", str(robotwin_root), "rev-parse", "HEAD:XPolicyLab"], text=True).strip(),
        "config_sha256": sha256_file(config_path),
        "python": sys.version,
        "platform": platform.platform(),
        "numpy": np.__version__,
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "sapien": sapien.__version__,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "snapshot_restore_during_capture": False,
        "seeds": seeds,
        "accepted": False,
        "pai_job_created": False,
    }
    write_json(output / "source_manifest.json", manifest)

    attempts = []
    for seed in seeds:
        episode = mapping[seed]
        target = output / "tapes" / f"seed_{seed:04d}.npz"
        meta_target = output / "tapes" / f"seed_{seed:04d}.json"
        if target.exists() or meta_target.exists():
            raise FileExistsError(f"refusing to overwrite tape evidence for seed {seed}")
        task = wrapper = None
        started = time.perf_counter()
        try:
            task, task_args = build_handover_block(str(robotwin_root), planner=args.planner)
            task.setup_demo(now_ep_num=episode, seed=seed, **task_args)
            wrapper = FullExpertTapeWrapper(
                task,
                output_dir=output / "unused_videos",
                episode_index=episode,
                seed=seed,
                video_stride=10**9,
            )
            task.play_once()
            receipt = wrapper.finish()
            receipt["task_success"] = bool(task.plan_success and task.check_success())
            if not receipt["task_success"] or not receipt["event_audit"]["valid"]:
                raise RuntimeError("expert episode failed task/event contract")
            tape = ExpertTape.from_records(wrapper.action_tape)
            tape.save(target)
            metadata = {
                "seed": seed,
                "episode": episode,
                "donor": wrapper.donor,
                "receiver": wrapper.receiver,
                "events": event_steps(receipt),
                "steps": len(tape),
                "tape": str(target),
                "tape_sha256": sha256_file(target),
                "capture_wall_time_s": time.perf_counter() - started,
                "fresh_solver_history": True,
                "snapshot_restore_during_capture": False,
                "accepted": False,
            }
            write_json(meta_target, metadata)
            attempts.append({"status": "COMPLETE", **metadata})
        except Exception as exc:
            attempts.append(
                {
                    "status": "FAILED",
                    "seed": seed,
                    "episode": episode,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                    "wall_time_s": time.perf_counter() - started,
                }
            )
        finally:
            if task is not None:
                try:
                    task.close_env(clear_cache=True)
                except Exception:
                    pass
        write_json(output / "attempts.json", attempts)
    complete = sum(item["status"] == "COMPLETE" for item in attempts)
    write_json(
        output / "capture_summary.json",
        {
            "status": "COMPLETE" if complete == len(seeds) else "INCOMPLETE",
            "requested": len(seeds),
            "completed": complete,
            "attempts": attempts,
            "accepted": False,
            "pai_job_created": False,
        },
    )
    return 0 if complete == len(seeds) else 2


if __name__ == "__main__":
    raise SystemExit(main())
