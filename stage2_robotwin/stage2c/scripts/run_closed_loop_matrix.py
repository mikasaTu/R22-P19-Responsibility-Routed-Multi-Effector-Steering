"""Run the complete fresh-process Stage 2C held-out closed-loop matrix."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

import numpy as np
import yaml

from stage2_robotwin.stage2c.replay.fresh_prefix_runner import (
    sha256_file,
    write_json,
)
from stage2_robotwin.stage2c.scripts.run_natural_responsibility import discover_tapes


def _run_cell(cell: Mapping[str, Any]) -> Dict[str, Any]:
    result_path = Path(cell["output"]) / "result.json"
    if result_path.is_file():
        return {"status": "REUSED_COMPLETE", "returncode": 0}
    output = Path(cell["output"])
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
        json.dumps(cell["condition_parameters"], sort_keys=True),
        "--output",
        str(output),
    ]
    if cell.get("oracle_control"):
        command.extend(["--oracle-control", str(cell["oracle_control"])])
    completed = subprocess.run(
        command,
        cwd=cell["repo_root"],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    (output / "runtime.log").write_text(completed.stdout, encoding="utf-8")
    return {
        "status": (
            "COMPLETE"
            if completed.returncode == 0 and result_path.is_file()
            else "FAILED"
        ),
        "returncode": completed.returncode,
    }


def _run_cells(
    cells: Sequence[Mapping[str, Any]],
    gpus: Sequence[int],
    output: Path,
    stage: str,
) -> list[Dict[str, Any]]:
    receipts = []
    gpu_locks = {gpu: threading.Lock() for gpu in gpus}

    def run_locked(cell: Mapping[str, Any]) -> Dict[str, Any]:
        with gpu_locks[int(cell["gpu"])]:
            return _run_cell(cell)

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(gpus)) as pool:
        futures = {pool.submit(run_locked, cell): cell for cell in cells}
        for count, future in enumerate(concurrent.futures.as_completed(futures), 1):
            cell = futures[future]
            try:
                receipt = future.result()
            except Exception as exc:
                receipt = {
                    "status": "FAILED",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            row = {
                "stage": stage,
                "seed": cell["seed"],
                "condition": cell["condition_name"],
                "method": cell["method"],
                "gpu": cell["gpu"],
                **receipt,
            }
            receipts.append(row)
            print(
                f"CLOSED_LOOP_{stage.upper()} {count}/{len(cells)} "
                f"seed={cell['seed']} condition={cell['condition_name']} "
                f"method={cell['method']} status={receipt['status']}",
                flush=True,
            )
            write_json(output / f"run_receipts.{stage}.partial.json", receipts)
    return receipts


def _make_cell(
    *,
    seed: int,
    method: str,
    condition_name: str,
    condition_parameters: Mapping[str, Any],
    gpu: int,
    robotwin_root: Path,
    config_path: Path,
    tape: tuple[Path, Path],
    output: Path,
    repo_root: Path,
    oracle_control: Path | None = None,
) -> Dict[str, Any]:
    return {
        "seed": seed,
        "method": method,
        "condition_name": condition_name,
        "condition_parameters": dict(condition_parameters),
        "gpu": gpu,
        "robotwin_root": robotwin_root,
        "config": config_path,
        "tape": tape[0],
        "meta": tape[1],
        "output": output
        / "cells"
        / f"seed_{seed:04d}__{condition_name}__{method}",
        "repo_root": repo_root,
        "oracle_control": oracle_control,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--robotwin-root")
    parser.add_argument("--config")
    parser.add_argument("--tape-root")
    parser.add_argument("--frozen-stress")
    parser.add_argument("--output")
    parser.add_argument("--gpus", nargs="+", type=int, default=[1, 2, 3])
    args = parser.parse_args()
    for name in (
        "robotwin_root",
        "config",
        "tape_root",
        "frozen_stress",
        "output",
    ):
        if getattr(args, name) is None:
            parser.error(f"--{name.replace('_', '-')} is required")

    repo_root = Path(__file__).resolve().parents[3]
    config_path = Path(args.config).resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    frozen_path = Path(args.frozen_stress).resolve()
    frozen = yaml.safe_load(frozen_path.read_text(encoding="utf-8"))
    expected_conditions = list(config["closed_loop"]["conditions"])
    conditions = frozen["conditions"]
    if set(conditions) != set(expected_conditions):
        raise ValueError(
            f"frozen conditions mismatch: expected={expected_conditions} "
            f"got={sorted(conditions)}"
        )
    methods = [str(value) for value in config["closed_loop"]["methods"]]
    if methods != [f"C{index}" for index in range(14)]:
        raise ValueError(f"closed-loop method contract changed: {methods}")
    seeds = [int(value) for value in config["closed_loop"]["seeds"]]
    tapes = discover_tapes(Path(args.tape_root).resolve())
    missing = sorted(set(seeds) - set(tapes))
    if missing:
        raise ValueError(f"missing held-out tapes for {missing}")
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    robotwin_root = Path(args.robotwin_root).resolve()

    # C6 is both a formal cell and the source of preregistered wrong-trace
    # controls.  Running it first does not share simulator state: every C6
    # cell remains its own process, and C9/C10 consume only persisted shares.
    reference_cells = []
    index = 0
    for condition_name in expected_conditions:
        for seed in seeds:
            reference_cells.append(
                _make_cell(
                    seed=seed,
                    method="C6",
                    condition_name=condition_name,
                    condition_parameters=conditions[condition_name],
                    gpu=args.gpus[index % len(args.gpus)],
                    robotwin_root=robotwin_root,
                    config_path=config_path,
                    tape=tapes[seed],
                    output=output,
                    repo_root=repo_root,
                )
            )
            index += 1
    receipts = _run_cells(reference_cells, args.gpus, output, "reference")

    controls = {}
    control_root = output / "controls"
    shift = int(config["closed_loop"]["oracle_shift_refreshes"])
    shuffled_seed = {
        seed: seeds[(seed_index + 1) % len(seeds)]
        for seed_index, seed in enumerate(seeds)
    }
    for condition_name in expected_conditions:
        reference_results = {}
        for seed in seeds:
            path = (
                output
                / "cells"
                / f"seed_{seed:04d}__{condition_name}__C6"
                / "result.json"
            )
            if path.is_file():
                reference_results[seed] = (
                    path,
                    json.loads(path.read_text(encoding="utf-8")),
                )
        if set(reference_results) != set(seeds):
            missing_references = sorted(set(seeds) - set(reference_results))
            raise RuntimeError(
                f"cannot construct C9/C10 controls for {condition_name}; "
                f"missing C6 references {missing_references}"
            )
        for seed in seeds:
            source_seed = shuffled_seed[seed]
            source_path, source = reference_results[source_seed]
            own_path, own = reference_results[seed]
            shuffled_sequence = [
                item["target_share"] for item in source["oracle_trace"]
            ]
            own_sequence = [item["target_share"] for item in own["oracle_trace"]]
            if not shuffled_sequence or not own_sequence:
                raise RuntimeError("C6 oracle trace is empty")
            shifted_sequence = np.roll(
                np.asarray(own_sequence, dtype=np.float64), shift, axis=0
            ).tolist()
            c9_path = (
                control_root
                / f"seed_{seed:04d}__{condition_name}__C9_control.json"
            )
            c10_path = (
                control_root
                / f"seed_{seed:04d}__{condition_name}__C10_control.json"
            )
            write_json(
                c9_path,
                {
                    "control_type": "EPISODE_SHUFFLED",
                    "target_seed": seed,
                    "source_seed": source_seed,
                    "condition": condition_name,
                    "source_result_sha256": sha256_file(source_path),
                    "phase_alignment": "normalized_E2_to_E5",
                    "share_sequence": shuffled_sequence,
                    "accepted": False,
                },
            )
            write_json(
                c10_path,
                {
                    "control_type": "TEMPORAL_CIRCULAR_SHIFT",
                    "target_seed": seed,
                    "source_seed": seed,
                    "condition": condition_name,
                    "source_result_sha256": sha256_file(own_path),
                    "shift_refreshes": shift,
                    "phase_alignment": "normalized_E2_to_E5",
                    "share_sequence": shifted_sequence,
                    "accepted": False,
                },
            )
            controls[(seed, condition_name, "C9")] = c9_path
            controls[(seed, condition_name, "C10")] = c10_path

    remaining_cells = []
    for condition_name in expected_conditions:
        for seed in seeds:
            for method in methods:
                if method == "C6":
                    continue
                remaining_cells.append(
                    _make_cell(
                        seed=seed,
                        method=method,
                        condition_name=condition_name,
                        condition_parameters=conditions[condition_name],
                        gpu=args.gpus[index % len(args.gpus)],
                        robotwin_root=robotwin_root,
                        config_path=config_path,
                        tape=tapes[seed],
                        output=output,
                        repo_root=repo_root,
                        oracle_control=controls.get(
                            (seed, condition_name, method)
                        ),
                    )
                )
                index += 1
    receipts.extend(
        _run_cells(remaining_cells, args.gpus, output, "matrix")
    )

    expected = len(seeds) * len(expected_conditions) * len(methods)
    results = list((output / "cells").glob("*/result.json"))
    failures = list((output / "cells").glob("*/failure.json"))
    summary = {
        "status": "COMPLETE" if len(results) == expected else "INCOMPLETE",
        "expected_cells": expected,
        "completed_cells": len(results),
        "failure_artifact_count": len(failures),
        "seeds": seeds,
        "conditions": expected_conditions,
        "methods": methods,
        "fresh_process_per_cell": True,
        "user_override_completed_matrix_after_gates": bool(
            config["closed_loop"]["user_override_complete_matrix_after_any_gate"]
        ),
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "frozen_stress_sha256": hashlib.sha256(frozen_path.read_bytes()).hexdigest(),
        "accepted": False,
        "pai_job_created": False,
    }
    write_json(output / "CLOSED_LOOP_COMPLETION.json", summary)
    write_json(output / "run_receipts.json", receipts)
    print(
        f"CLOSED_LOOP_COMPLETE {len(results)}/{expected} "
        f"status={summary['status']}",
        flush=True,
    )
    return 0 if len(results) == expected else 2


if __name__ == "__main__":
    raise SystemExit(main())
