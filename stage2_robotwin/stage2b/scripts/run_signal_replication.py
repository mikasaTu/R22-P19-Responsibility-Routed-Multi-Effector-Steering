"""Run exact-seed Stage 2B contact-aware authority replication episodes."""

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
from typing import Any, Dict, Iterable, List, Mapping

import numpy as np
import pandas as pd

from stage2_robotwin.stage2b.intervention.anisotropic_compliance import (
    audit_native_anisotropic_compliance,
)
from stage2_robotwin.stage2b.intervention.paired_authority_profiles import (
    ContactAwareAuthorityProbe,
)
from stage2_robotwin.wrappers.bimanual_trace_wrapper import BimanualTraceWrapper
from stage2_robotwin.wrappers.robotwin_runtime import build_handover_block


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def git_head(path: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
    ).strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def reference_episodes(summary: Mapping[str, Any]) -> Dict[int, Mapping[str, Any]]:
    return {int(item["seed"]): item for item in summary["episodes"]}


def persist_trace(
    wrapper: BimanualTraceWrapper, path: Path
) -> str | None:
    if not wrapper.trace:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(wrapper.trace)
    frame["contact_pairs"] = frame["contact_pairs"].map(json.dumps)
    frame["event_labels"] = frame["event_labels"].map(json.dumps)
    frame.to_parquet(path, index=False)
    return str(path)


def persist_branches(
    wrapper: BimanualTraceWrapper, path: Path
) -> str | None:
    if not wrapper.branch_records:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(value, sort_keys=True) + "\n" for value in wrapper.branch_records),
        encoding="utf-8",
    )
    return str(path)


def _event_steps(receipt: Mapping[str, Any]) -> Dict[str, int]:
    return {
        name: int(value["step"])
        for name, value in receipt["event_audit"]["events"].items()
        if value is not None
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--robotwin-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--reference-smoke-summary", required=True)
    parser.add_argument("--split", choices=("calibration", "heldout"), required=True)
    parser.add_argument("--seeds", type=int, nargs="+", required=True)
    parser.add_argument("--gammas", type=float, nargs="+", required=True)
    parser.add_argument("--horizons", type=int, nargs="+", default=[5, 10])
    parser.add_argument("--stride", type=int, default=25)
    parser.add_argument("--driver-amplitude-m", type=float, default=0.004)
    parser.add_argument("--planner", choices=("mplib_screw", "mplib_RRT"), default="mplib_screw")
    args = parser.parse_args()

    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any((output / "branches").glob("*.jsonl")):
        raise FileExistsError(f"refusing to overwrite existing branch evidence in {output}")
    repo_root = Path(__file__).resolve().parents[3]
    stage2b_root = repo_root / "stage2_robotwin" / "stage2b"
    robotwin_root = Path(args.robotwin_root).resolve()
    reference_path = Path(args.reference_smoke_summary).resolve()
    reference_summary = json.loads(reference_path.read_text(encoding="utf-8"))
    references = reference_episodes(reference_summary)
    missing = sorted(set(args.seeds) - set(references))
    if missing:
        raise ValueError(f"seeds absent from successful reference smoke: {missing}")

    import sapien
    import torch

    code_files = [
        stage2b_root / "intervention/task_frame.py",
        stage2b_root / "intervention/follower_mode.py",
        stage2b_root / "intervention/paired_authority_profiles.py",
        Path(__file__).resolve(),
    ]
    manifest = {
        "experiment": "R22-P19-Stage2B-I",
        "split": args.split,
        "requested_seeds": list(args.seeds),
        "gammas": list(args.gammas),
        "horizons": sorted(set(args.horizons)),
        "stride": args.stride,
        "driver_amplitude_m": args.driver_amplitude_m,
        "repo_commit_at_launch": git_head(repo_root),
        "repo_dirty_at_launch": bool(
            subprocess.check_output(
                ["git", "-C", str(repo_root), "status", "--porcelain"],
                text=True,
            ).strip()
        ),
        "code_sha256": {
            str(path.relative_to(repo_root)): sha256_file(path)
            for path in code_files
        },
        "reference_smoke_summary": str(reference_path),
        "reference_smoke_summary_sha256": sha256_file(reference_path),
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
        "physics_hz": 250,
        "planner": args.planner,
        "controller": "RoboTwin expert with MPLib explicit adapter",
        "intervention": "task-frame follower target; scalar joint drives unchanged",
        "evidence_boundary": "simulator privileged oracle; not deployable",
        "pai_job_created": False,
        "accepted": False,
    }
    write_json(output / "source_manifest.json", manifest)

    attempts: List[Dict[str, Any]] = []
    successes: List[Dict[str, Any]] = []
    capability = None
    for seed in args.seeds:
        reference = references[int(seed)]
        episode_index = int(reference["episode"])
        reference_events = {
            name: int(value["step"])
            for name, value in reference["event_audit"]["events"].items()
        }
        probe = ContactAwareAuthorityProbe(
            reference_e4=reference_events["E4"],
            reference_e5=reference_events["E5"],
            gammas=args.gammas,
            horizons=args.horizons,
            stride=args.stride,
            driver_amplitude_m=args.driver_amplitude_m,
        )
        task = wrapper = None
        try:
            task, task_args = build_handover_block(
                str(robotwin_root), planner=args.planner
            )
            task.setup_demo(now_ep_num=episode_index, seed=seed, **task_args)
            if capability is None:
                capability = audit_native_anisotropic_compliance(task)
            wrapper = BimanualTraceWrapper(
                task,
                output_dir=output / "videos",
                episode_index=episode_index,
                seed=seed,
                branch_auditor=probe,
            )
            task.play_once()
            receipt = wrapper.finish()
            receipt["task_success"] = bool(task.plan_success and task.check_success())
            receipt["plan_success"] = bool(task.plan_success)
            receipt["probe_contract"] = probe.contract()
            actual_events = _event_steps(receipt)
            receipt["reference_event_steps"] = reference_events
            receipt["actual_event_steps"] = actual_events
            receipt["reference_window_reproduced"] = all(
                actual_events.get(name) == reference_events[name]
                for name in ("E2", "E3", "E4", "E5")
            )
            stem = f"episode_{episode_index:02d}_seed_{seed:04d}"
            receipt["trace"] = persist_trace(
                wrapper, output / "traces" / f"{stem}.parquet"
            )
            receipt["branches"] = persist_branches(
                wrapper, output / "branches" / f"{stem}.jsonl"
            )
            receipt["expected_branch_record_count"] = (
                len(probe.sample_steps)
                * len(args.gammas)
                * 2
                * len(set(args.horizons))
            )
            receipt["branch_record_count_matches_contract"] = (
                receipt["oracle_branch_record_count"]
                == receipt["expected_branch_record_count"]
            )
            valid = (
                receipt["task_success"]
                and receipt["event_audit"]["valid"]
                and receipt["reference_window_reproduced"]
                and receipt["branch_record_count_matches_contract"]
            )
            receipt["episode_contract_valid"] = bool(valid)
            attempts.append(receipt)
            if valid:
                successes.append(receipt)
        except Exception as exc:
            failure: Dict[str, Any] = {
                "episode": episode_index,
                "seed": seed,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "probe_contract": probe.contract(),
            }
            if wrapper is not None:
                stem = f"episode_{episode_index:02d}_seed_{seed:04d}"
                try:
                    failure["partial_receipt"] = wrapper.finish()
                    failure["partial_trace"] = persist_trace(
                        wrapper, output / "traces" / f"{stem}.partial.parquet"
                    )
                    failure["partial_branches"] = persist_branches(
                        wrapper, output / "branches" / f"{stem}.partial.jsonl"
                    )
                except Exception as artifact_exc:
                    failure["artifact_error"] = (
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
        "status": (
            "SIGNAL_REPLAY_COMPLETE"
            if len(successes) == len(args.seeds)
            else "SIGNAL_REPLAY_INCOMPLETE"
        ),
        "split": args.split,
        "requested_seeds": list(args.seeds),
        "successful_contract_seeds": [item["seed"] for item in successes],
        "attempt_count": len(attempts),
        "capability_audit": capability,
        "episodes": successes,
        "pai_job_created": False,
        "accepted": False,
    }
    write_json(output / "run_summary.json", summary)
    return 0 if summary["status"] == "SIGNAL_REPLAY_COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
