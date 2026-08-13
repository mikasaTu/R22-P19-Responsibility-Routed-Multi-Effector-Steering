"""Run bounded real RoboTwin handover_block expert smoke episodes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
import yaml

from stage2_robotwin.wrappers.bimanual_trace_wrapper import BimanualTraceWrapper
from stage2_robotwin.wrappers.robotwin_runtime import build_handover_block
from stage2_robotwin.responsibility.oracle_brancher import OracleBranchAuditor


def git_head(path: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
    ).strip()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def persist_trace(
    wrapper: BimanualTraceWrapper,
    traces: Path,
    episode_index: int,
    seed: int,
) -> str | None:
    """Persist a complete or partial trace without overwriting another seed."""

    if not wrapper.trace:
        return None
    trace_path = traces / f"episode_{episode_index:02d}_seed_{seed:04d}.parquet"
    traces.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(wrapper.trace)
    frame["contact_pairs"] = frame["contact_pairs"].map(json.dumps)
    frame["event_labels"] = frame["event_labels"].map(json.dumps)
    frame.to_parquet(trace_path, index=False)
    return str(trace_path)


def persist_branches(
    wrapper: BimanualTraceWrapper,
    output: Path,
    episode_index: int,
    seed: int,
) -> str | None:
    if not wrapper.branch_records:
        return None
    path = output / f"episode_{episode_index:02d}_seed_{seed:04d}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(value, sort_keys=True) + "\n" for value in wrapper.branch_records),
        encoding="utf-8",
    )
    return str(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--robotwin-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--episodes", type=int, default=10)
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--seed-stop", type=int, default=100)
    parser.add_argument("--episode-offset", type=int, default=0)
    parser.add_argument(
        "--planner",
        choices=("mplib_RRT", "mplib_screw"),
        default="mplib_screw",
    )
    parser.add_argument("--oracle-branches", action="store_true")
    parser.add_argument("--branch-base-stride", type=int, default=5)
    parser.add_argument("--branch-swap-stride", type=int, default=25)
    parser.add_argument(
        "--branch-profile-mode",
        choices=("all", "direction_diagnostic"),
        default="all",
    )
    parser.add_argument(
        "--branch-horizons",
        type=int,
        nargs="+",
        default=[5, 10],
        help="counterfactual horizons in 250 Hz physics/control steps",
    )
    args = parser.parse_args()

    output = Path(args.output).resolve()
    videos = output / "videos"
    traces = output / "traces"
    branches = output / "branches"
    output.mkdir(parents=True, exist_ok=True)
    robotwin_root = Path(args.robotwin_root).resolve()
    repo_root = Path(__file__).resolve().parents[2]

    import sapien
    import torch

    source_manifest = {
        "r22p19_commit_before_stage2": git_head(repo_root),
        "robotwin_commit": git_head(robotwin_root),
        "xpolicylab_pinned_commit": subprocess.check_output(
            ["git", "-C", str(robotwin_root), "rev-parse", "HEAD:XPolicyLab"],
            text=True,
        ).strip(),
        "python": sys.version,
        "platform": platform.platform(),
        "numpy": np.__version__,
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "sapien": sapien.__version__,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "planner": f"{args.planner} explicit runtime adapter",
        "planner_deviation": (
            "MPLib 0.2.1 plans the exact target pose but cannot enforce "
            "CuRobo partial-pose hold vectors; requests are counted per episode"
        ),
        "robot": "aloha-agilex dual arm",
        "physics_hz": 250,
        "learned_action_order": "left_arm_6,left_gripper_1,right_arm_6,right_gripper_1",
        "learned_action_dim": 14,
        "action_chunk_size": 1,
        "camera_keys": ["head_camera", "left_camera", "right_camera"],
        "task": "handover_block",
        "task_config": "demo_clean",
        "evidence_boundary": "expert/simulator privileged smoke; no learned policy",
        "accepted": False,
        "oracle_branches_enabled": bool(args.oracle_branches),
        "counterfactual_horizons": (
            sorted(set(args.branch_horizons)) if args.oracle_branches else []
        ),
        "authority_profile_mode": (
            args.branch_profile_mode if args.oracle_branches else None
        ),
    }
    write_json(output / "source_manifest.json", source_manifest)

    successful: List[Dict[str, Any]] = []
    attempts: List[Dict[str, Any]] = []
    capabilities = None
    for seed in range(args.seed_start, args.seed_stop):
        if len(successful) >= args.episodes:
            break
        episode_index = args.episode_offset + len(successful)
        task = None
        wrapper = None
        try:
            task, task_args = build_handover_block(
                str(robotwin_root), planner=args.planner
            )
            task.setup_demo(now_ep_num=episode_index, seed=seed, **task_args)
            wrapper = BimanualTraceWrapper(
                task,
                output_dir=videos,
                episode_index=episode_index,
                seed=seed,
                branch_auditor=(
                    OracleBranchAuditor(
                        horizons=args.branch_horizons,
                        base_stride=args.branch_base_stride,
                        swap_stride=args.branch_swap_stride,
                        profile_mode=args.branch_profile_mode,
                    )
                    if args.oracle_branches
                    else None
                ),
            )
            if capabilities is None:
                capabilities = wrapper.capability_audit()
            task.play_once()
            success = bool(task.plan_success and task.check_success())
            receipt = wrapper.finish()
            receipt["task_success"] = success
            receipt["plan_success"] = bool(task.plan_success)
            receipt["planner_constraint_requests_ignored"] = int(
                getattr(task.robot.left_planner, "stage2_ignored_constraint_requests", 0)
                + getattr(task.robot.right_planner, "stage2_ignored_constraint_requests", 0)
            )
            attempts.append(receipt)
            receipt["trace"] = persist_trace(
                wrapper, traces, episode_index, seed
            )
            receipt["oracle_branches"] = persist_branches(
                wrapper, branches, episode_index, seed
            )
            if success and receipt["event_audit"]["valid"]:
                successful.append(receipt)
        except Exception as exc:
            failure: Dict[str, Any] = {
                "episode": episode_index,
                "seed": seed,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
            if wrapper is not None:
                try:
                    failure["partial_receipt"] = wrapper.finish()
                    failure["partial_trace"] = persist_trace(
                        wrapper, traces, episode_index, seed
                    )
                    failure["partial_oracle_branches"] = persist_branches(
                        wrapper, branches, episode_index, seed
                    )
                except Exception as artifact_exc:
                    failure["partial_artifact_error"] = (
                        f"{type(artifact_exc).__name__}: {artifact_exc}"
                    )
            attempts.append(failure)
        finally:
            if task is not None:
                try:
                    task.close_env(clear_cache=True)
                except Exception:
                    pass
        write_json(output / "attempts.json", attempts)

    summary = {
        "status": "SMOKE_COMPLETE" if len(successful) == args.episodes else "SMOKE_INCOMPLETE",
        "task": "handover_block",
        "requested_episodes": args.episodes,
        "successful_valid_event_episodes": len(successful),
        "selected_seeds": [item["seed"] for item in successful],
        "attempt_count": len(attempts),
        "all_event_chains_valid": len(successful) == args.episodes,
        "all_snapshot_replays_deterministic": bool(successful)
        and all(
            item.get("determinism", {}).get("pose_equal_at_1e-8")
            and item.get("determinism", {}).get("twist_equal_at_1e-8")
            for item in successful
        ),
        "capability_audit": capabilities,
        "episodes": successful,
        "original_bimanual_signal_tested": bool(args.oracle_branches),
        "oracle_signal_evidence_level": (
            "bounded_pilot_unclassified" if args.oracle_branches else "not_tested"
        ),
        "next": (
            "Validate authority interventions before formal Stage-2A scaling"
            if args.oracle_branches
            else "Stage-2A Oracle signal audit only after all 10 videos are manually inspected"
        ),
        "accepted": False,
    }
    write_json(output / "smoke_summary.json", summary)
    return 0 if summary["status"] == "SMOKE_COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
