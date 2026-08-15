from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from stage2_robotwin.stage2c.scripts.run_natural_responsibility import discover_tapes
from stage2_robotwin.stage2e.withdrawal import CHANNELS, FADE_LEVELS
from stage2_robotwin.stage2e.withdrawal.branch_isolation import randomized_cells, launch_order_sha256


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--robotwin-root", type=Path, required=True)
    parser.add_argument("--tape-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--horizon", type=int, default=60)
    parser.add_argument("--active-amplitude-m", type=float, default=0.015)
    parser.add_argument("--max-workers", type=int, default=2)
    parser.add_argument("--gpus", nargs="+", default=["2"])
    parser.add_argument("--random-seed", type=int, default=220619)
    args = parser.parse_args()
    if args.max_workers > 2:
        raise ValueError("Stage2E dev14 contract allows at most two concurrent workers")
    tapes = discover_tapes(args.tape_root.resolve())
    cells = randomized_cells(args.seeds, CHANNELS, FADE_LEVELS, args.repeats,
                             args.random_seed)
    args.output.mkdir(parents=True, exist_ok=True)
    write_json(args.output / "launch_manifest.json", {
        "schema": "r22p19.stage2e.withdrawal_launch.v1",
        "random_seed": args.random_seed,
        "launch_order_sha256": launch_order_sha256(cells),
        "cells": [asdict(cell) for cell in cells],
        "fresh_process_per_cell": True,
        "max_workers": args.max_workers,
        "gpus": args.gpus,
        "expected_cells": len(cells),
        "accepted": False,
        "pai_job_created": False,
    })

    def run(cell):
        target = args.output / "branches" / f"{cell.key}.json"
        if target.is_file():
            return {"key": cell.key, "status": "REUSED_COMPLETE", "output": str(target)}
        tape, meta = tapes[cell.seed]
        env = os.environ.copy()
        env["CUDA_VISIBLE_DEVICES"] = str(args.gpus[cell.launch_index % len(args.gpus)])
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        command = [
            sys.executable, "-m", "stage2_robotwin.stage2e.scripts.run_withdrawal_branch",
            "--robotwin-root", str(args.robotwin_root), "--tape", str(tape),
            "--meta", str(meta), "--channel", cell.channel, "--fade", str(cell.fade),
            "--repeat", str(cell.repeat), "--launch-index", str(cell.launch_index),
            "--horizon", str(args.horizon), "--active-amplitude-m", str(args.active_amplitude_m),
            "--output", str(target),
        ]
        completed = subprocess.run(command, cwd=args.repo, env=env, text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        log = args.output / "logs" / f"{cell.key}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(completed.stdout)
        return {"key": cell.key, "status": "COMPLETE" if completed.returncode == 0 and target.is_file() else "FAILED",
                "returncode": completed.returncode, "output": str(target), "log": str(log)}

    receipts = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as pool:
        futures = {pool.submit(run, cell): cell for cell in cells}
        for future in concurrent.futures.as_completed(futures):
            receipt = future.result()
            receipts.append(receipt)
            write_json(args.output / "receipts.json", receipts)
            print(f"WITHDRAWAL_MATRIX {len(receipts)}/{len(cells)} {receipt['key']} {receipt['status']}", flush=True)
    complete = sum(item["status"] in {"COMPLETE", "REUSED_COMPLETE"} for item in receipts)
    write_json(args.output / "completion.json", {"expected": len(cells), "complete": complete,
                                                  "failed": len(cells) - complete})
    return 0 if complete == len(cells) else 1


if __name__ == "__main__":
    raise SystemExit(main())
