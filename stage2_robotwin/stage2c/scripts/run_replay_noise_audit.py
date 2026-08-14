"""Launch all 100 exact-null fresh-process replay cells and analyze them."""

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
from typing import Any, Dict, Iterable, Mapping

import yaml

from stage2_robotwin.stage2c.replay.null_floor import (
    analyze_fresh_null_floor,
    analyze_old_snapshot_floor,
)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def discover_tapes(root: Path) -> Dict[int, tuple[Path, Path]]:
    found = {}
    for tape in root.rglob("seed_*.npz"):
        meta = tape.with_suffix(".json")
        if not meta.is_file():
            continue
        seed = int(json.loads(meta.read_text(encoding="utf-8"))["seed"])
        if seed in found:
            raise ValueError(f"duplicate tape for seed {seed}: {found[seed][0]} and {tape}")
        found[seed] = (tape, meta)
    return found


def _run_cell(cell: Mapping[str, Any]) -> Dict[str, Any]:
    output = Path(cell["output"])
    result_path = output / "result.json"
    if result_path.is_file():
        result = json.loads(result_path.read_text(encoding="utf-8"))
        return {"status": "REUSED_COMPLETE", "result": result, "output": str(output)}
    output.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = str(cell["gpu"])
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [
        sys.executable,
        "-m",
        "stage2_robotwin.stage2c.replay.fresh_prefix_runner",
        "--robotwin-root",
        str(cell["robotwin_root"]),
        "--config",
        str(cell["config"]),
        "--tape",
        str(cell["tape"]),
        "--tape-meta",
        str(cell["meta"]),
        "--method",
        str(cell["method"]),
        "--condition-name",
        str(cell["condition_name"]),
        "--condition-json",
        json.dumps(cell["condition"], sort_keys=True),
        "--output",
        str(output),
        "--replicate",
        str(cell["replicate"]),
    ]
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=cell["repo_root"],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    (output / "runtime.log").write_text(completed.stdout, encoding="utf-8")
    if completed.returncode != 0 or not result_path.is_file():
        return {
            "status": "FAILED",
            "returncode": completed.returncode,
            "output": str(output),
            "wall_time_s": time.perf_counter() - started,
        }
    return {
        "status": "COMPLETE",
        "result": json.loads(result_path.read_text(encoding="utf-8")),
        "output": str(output),
        "wall_time_s": time.perf_counter() - started,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--robotwin-root", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--tape-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--old-pilot", required=True)
    parser.add_argument("--gpus", nargs="+", type=int, default=[1, 2, 3])
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    config_path = Path(args.config).resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    tapes = discover_tapes(Path(args.tape_root).resolve())
    seeds = [int(value) for value in config["seed_contract"]["replay_noise"]]
    missing = sorted(set(seeds) - set(tapes))
    if missing:
        raise ValueError(f"missing formal tapes for seeds {missing}")
    conditions = config["fresh_prefix"]["null_conditions"]
    methods = list(config["fresh_prefix"]["null_methods"])
    replicates = int(config["fresh_prefix"]["null_replicates"])

    cells = []
    index = 0
    for seed in seeds:
        for condition_name, condition in conditions.items():
            for method in methods:
                for replicate in range(replicates):
                    stem = f"seed_{seed:04d}__{condition_name}__{method}__rep_{replicate:02d}"
                    cells.append(
                        {
                            "seed": seed,
                            "condition_name": condition_name,
                            "condition": condition,
                            "method": method,
                            "replicate": replicate,
                            "gpu": args.gpus[index % len(args.gpus)],
                            "tape": tapes[seed][0],
                            "meta": tapes[seed][1],
                            "output": output / "cells" / stem,
                            "repo_root": repo_root,
                            "robotwin_root": Path(args.robotwin_root).resolve(),
                            "config": config_path,
                        }
                    )
                    index += 1

    receipts = []
    gpu_locks = {gpu: threading.Lock() for gpu in args.gpus}

    def run_locked(cell: Mapping[str, Any]) -> Dict[str, Any]:
        with gpu_locks[int(cell["gpu"])]:
            return _run_cell(cell)

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(args.gpus)) as pool:
        future_to_cell = {pool.submit(run_locked, cell): cell for cell in cells}
        for completed_count, future in enumerate(concurrent.futures.as_completed(future_to_cell), 1):
            cell = future_to_cell[future]
            try:
                receipt = future.result()
            except Exception as exc:
                receipt = {
                    "status": "FAILED",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                    "output": str(cell["output"]),
                }
            receipts.append(
                {
                    "seed": cell["seed"],
                    "condition": cell["condition_name"],
                    "method": cell["method"],
                    "replicate": cell["replicate"],
                    "gpu": cell["gpu"],
                    **{key: value for key, value in receipt.items() if key != "result"},
                }
            )
            print(
                f"NULL_AUDIT_PROGRESS {completed_count}/{len(cells)} "
                f"seed={cell['seed']} condition={cell['condition_name']} "
                f"method={cell['method']} rep={cell['replicate']} status={receipt['status']}",
                flush=True,
            )
            write_json(output / "run_receipts.partial.json", receipts)

    results = [
        json.loads((Path(cell["output"]) / "result.json").read_text(encoding="utf-8"))
        for cell in cells
        if (Path(cell["output"]) / "result.json").is_file()
    ]
    fresh = analyze_fresh_null_floor(results)
    old = analyze_old_snapshot_floor(
        json.loads(Path(args.old_pilot).read_text(encoding="utf-8"))
    )
    fresh_p95 = {
        metric: value["p95_absolute_pair_difference"]
        for metric, value in fresh["pooled_within_method"].items()
    }
    exact_null_within_numerical_tolerance = all(
        value is None or float(value) <= 1e-10 for value in fresh_p95.values()
    )
    expected = len(cells)
    complete = len(results)
    decision = {
        "status": "COMPLETE" if complete == expected else "INCOMPLETE",
        "expected_cells": expected,
        "completed_cells": complete,
        "fresh_prefix": fresh,
        "old_snapshot": old,
        "main_scene_oracle_isolation": True,
        "exact_null_within_numerical_tolerance": exact_null_within_numerical_tolerance,
        "operator_performance_conclusion_paused": not exact_null_within_numerical_tolerance,
        "accepted": False,
        "pai_job_created": False,
    }
    write_json(output / "REPLAY_NOISE_DECISION.json", decision)
    write_json(output / "run_receipts.json", receipts)
    print(f"NULL_AUDIT_COMPLETE {complete}/{expected}", flush=True)
    return 0 if complete == expected else 2


if __name__ == "__main__":
    raise SystemExit(main())
