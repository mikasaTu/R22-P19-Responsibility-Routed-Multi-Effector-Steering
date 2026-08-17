from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import random
import subprocess
import sys
import threading
from pathlib import Path

from stage2_robotwin.stage2c.scripts.run_natural_responsibility import discover_tapes

from stage3_hybrid.conditions import single_factor_conditions, two_factor_conditions
from stage3_hybrid.modes import MODES


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def canonical_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def run_one(cell, python, repo, robotwin):
    output = Path(cell["output"])
    if output.is_file():
        return {"status": "REUSED_COMPLETE", "returncode": 0}
    output.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = str(cell["gpu"])
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["__EGL_VENDOR_LIBRARY_FILENAMES"] = "/mnt/cpfs/zbl-cpfs-new/USERS/leon/deps/r22p19_stage2/venv/lib/python3.10/site-packages/sapien/vulkan_library/10_nvidia.json"
    command = [python, "-m", "stage3_hybrid.run_cell", "--robotwin-root", robotwin,
               "--tape", cell["tape"], "--meta", cell["meta"],
               "--condition-name", cell["condition"], "--condition-json", json.dumps(cell["parameters"], sort_keys=True),
               "--mode", cell["mode"], "--repeat", str(cell["repeat"]),
               "--launch-index", str(cell["launch_index"]), "--output", str(output)]
    completed = subprocess.run(command, cwd=repo, env=env, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output.with_suffix(".runtime.log").write_text(completed.stdout)
    return {"status": "COMPLETE" if completed.returncode == 0 and output.is_file() else "FAILED",
            "returncode": completed.returncode}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--robotwin-root", required=True)
    p.add_argument("--tape-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--phase", choices=("single", "two_factor", "heldout"), required=True)
    p.add_argument("--eligible", type=Path)
    p.add_argument("--gpus", type=int, nargs="+", required=True)
    args = p.parse_args()
    if not 1 <= len(args.gpus) <= 2:
        raise ValueError("Stage3A contract permits one or two GPUs only")
    repo = str(Path(__file__).resolve().parents[1])
    python = sys.executable
    tapes = discover_tapes(args.tape_root.resolve())
    if args.phase == "single":
        seeds, conditions = [0, 1], single_factor_conditions()
    elif args.phase == "two_factor":
        seeds, conditions = [0, 1], two_factor_conditions()
    else:
        if args.eligible is None:
            raise ValueError("heldout phase requires --eligible")
        payload = json.loads(args.eligible.read_text())
        conditions = payload["eligible_conditions"]
        seeds = [2, 3, 5, 6, 7, 8, 9, 10]
    missing = sorted(set(seeds) - set(tapes))
    if missing:
        raise ValueError(f"missing tapes {missing}")
    cells = []
    for condition in conditions:
        for seed in seeds:
            for mode in MODES:
                for repeat in range(2):
                    cells.append({"seed": seed, "condition": condition["name"],
                                  "parameters": condition["parameters"], "mode": mode.name,
                                  "repeat": repeat, "tape": str(tapes[seed][0]), "meta": str(tapes[seed][1])})
    random.Random(20260818 + {"single": 1, "two_factor": 2, "heldout": 3}[args.phase]).shuffle(cells)
    for index, cell in enumerate(cells):
        cell["launch_index"] = index
        cell["gpu"] = args.gpus[index % len(args.gpus)]
        cell["output"] = str(args.output / "cells" /
            f"seed{cell['seed']:04d}__{cell['condition']}__{cell['mode']}__r{cell['repeat']}.json")
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {"schema": "r22p19.stage3a.launch.v1", "phase": args.phase,
                "cell_count": len(cells), "max_parallel": len(args.gpus), "gpus": args.gpus,
                "randomization_seed": 20260818 + {"single": 1, "two_factor": 2, "heldout": 3}[args.phase],
                "cells": cells, "accepted": False, "pai_job_count": 0}
    manifest["contract_sha256"] = canonical_hash({key: value for key, value in manifest.items() if key != "contract_sha256"})
    write_json(args.output / "launch_manifest.json", manifest)
    locks = {gpu: threading.Lock() for gpu in args.gpus}
    receipts = []
    def locked(cell):
        with locks[cell["gpu"]]:
            return run_one(cell, python, repo, args.robotwin_root)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(args.gpus)) as pool:
        futures = {pool.submit(locked, cell): cell for cell in cells}
        for count, future in enumerate(concurrent.futures.as_completed(futures), 1):
            cell = futures[future]
            try:
                outcome = future.result()
            except Exception as exc:
                outcome = {"status": "FAILED", "error": f"{type(exc).__name__}: {exc}"}
            row = {key: cell[key] for key in ("seed", "condition", "mode", "repeat", "gpu", "launch_index")}
            row.update(outcome); receipts.append(row)
            write_json(args.output / "receipts.partial.json", receipts)
            print(f"STAGE3_MATRIX {args.phase} {count}/{len(cells)} {row['status']}", flush=True)
    write_json(args.output / "receipts.json", receipts)
    complete = all(row["status"] in {"COMPLETE", "REUSED_COMPLETE"} for row in receipts)
    write_json(args.output / "completion.json", {"phase": args.phase, "expected": len(cells),
               "complete": sum(row["status"] in {"COMPLETE", "REUSED_COMPLETE"} for row in receipts),
               "failed": sum(row["status"] == "FAILED" for row in receipts),
               "matrix_complete": complete, "accepted": False, "pai_job_count": 0})
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
