"""Bounded Stage 2C stress calibration on the two preregistered seeds."""

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
from typing import Any, Dict, Iterable, Mapping, Sequence

import numpy as np
import yaml

from stage2_robotwin.stage2c.replay.fresh_prefix_runner import write_json
from stage2_robotwin.stage2c.scripts.run_natural_responsibility import discover_tapes


LOWER_IS_BETTER = (
    "peak_object_angular_velocity",
    "peak_object_linear_jerk",
    "peak_relative_slip_m",
    "donor_residual_influence_impulse_sum",
)
BINARY_RISK = ("drop", "premature_release", "receiver_takeover_failure")


def _label(value: Any) -> str:
    return str(value).replace("-", "m").replace(".", "p")


def build_candidates(config: Mapping[str, Any]) -> list[Dict[str, Any]]:
    """Return every preregistered single-factor and two-factor candidate."""

    candidates = [
        {"name": "clean", "factor": "clean", "parameters": {}}
    ]
    for factor, values in config["stress_calibration"]["candidates"].items():
        for value in values:
            candidates.append(
                {
                    "name": f"{factor}_{_label(value)}",
                    "factor": factor,
                    "parameters": {factor: value},
                }
            )
    for index, parameters in enumerate(
        config["stress_calibration"].get("two_factor_candidates", []), 1
    ):
        components = "__".join(
            f"{key}_{_label(value)}" for key, value in sorted(parameters.items())
        )
        candidates.append(
            {
                "name": f"two_factor_{index:02d}__{components}",
                "factor": "two_factor",
                "parameters": dict(parameters),
            }
        )
    names = [item["name"] for item in candidates]
    if len(names) != len(set(names)):
        raise ValueError("stress candidate names are not unique")
    return candidates


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


def _mean_boolean(results: Sequence[Mapping[str, Any]], key: str) -> float:
    return float(np.mean([bool(item["metrics"][key]) for item in results]))


def _median(results: Sequence[Mapping[str, Any]], key: str) -> float:
    return float(np.median([float(item["metrics"][key]) for item in results]))


def _summarize(results: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    if not results:
        return {"completed_seeds": 0}
    return {
        "completed_seeds": len(results),
        "seeds": sorted(int(item["seed"]) for item in results),
        "success_rate": _mean_boolean(results, "success"),
        "handover_completion_rate": _mean_boolean(
            results, "handover_completion"
        ),
        **{
            f"{key}_rate": _mean_boolean(results, key) for key in BINARY_RISK
        },
        **{f"median_{key}": _median(results, key) for key in LOWER_IS_BETTER},
        "median_min_object_height_m": _median(results, "min_object_height_m"),
    }


def _safe_ratio(value: float, reference: float) -> float:
    return float(value / max(abs(reference), 1e-12))


def analyze_calibration(
    results: Iterable[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    results = list(results)
    index: Dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for candidate in candidates:
        for method in ("C0", "C13"):
            index[(candidate["name"], method)] = [
                item
                for item in results
                if item["condition"] == candidate["name"]
                and item["method"] == method
            ]
    clean = {
        method: _summarize(index[("clean", method)])
        for method in ("C0", "C13")
    }
    rows = []
    for candidate in candidates:
        name = str(candidate["name"])
        base = _summarize(index[(name, "C0")])
        full = _summarize(index[(name, "C13")])
        if name == "clean":
            disturbance_ratios = {key: 1.0 for key in LOWER_IS_BETTER}
        else:
            disturbance_ratios = {
                key: _safe_ratio(
                    float(base[f"median_{key}"]),
                    float(clean["C0"][f"median_{key}"]),
                )
                for key in LOWER_IS_BETTER
            }
        finite_ratios = [
            value for value in disturbance_ratios.values() if np.isfinite(value)
        ]
        maximum_disturbance_ratio = max(finite_ratios, default=1.0)
        relative_reductions = {
            key: (
                float(base[f"median_{key}"] - full[f"median_{key}"])
                / max(abs(float(base[f"median_{key}"])), 1e-12)
            )
            for key in LOWER_IS_BETTER
        }
        success_delta = float(full["success_rate"] - base["success_rate"])
        handover_delta = float(
            full["handover_completion_rate"]
            - base["handover_completion_rate"]
        )
        binary_risk_reduction = max(
            float(base[f"{key}_rate"] - full[f"{key}_rate"])
            for key in BINARY_RISK
        )
        continuous_improvement = max(relative_reductions.values(), default=0.0)
        improvable = bool(
            success_delta > 0.0
            or handover_delta > 0.0
            or binary_risk_reduction > 0.0
            or (
                continuous_improvement >= 0.10
                and full["success_rate"] >= base["success_rate"]
            )
        )
        base_success_in_target_range = bool(
            0.30 <= float(base["success_rate"]) <= 0.80
        )
        disturbance_at_least_2x = bool(maximum_disturbance_ratio >= 2.0)
        eligible = bool(
            name != "clean"
            and (
                base_success_in_target_range
                or (disturbance_at_least_2x and improvable)
            )
        )
        rows.append(
            {
                **candidate,
                "base": base,
                "full": full,
                "disturbance_ratios_vs_clean": disturbance_ratios,
                "maximum_disturbance_ratio_vs_clean": maximum_disturbance_ratio,
                "success_delta_full_minus_base": success_delta,
                "handover_delta_full_minus_base": handover_delta,
                "binary_risk_reduction": binary_risk_reduction,
                "continuous_relative_reductions": relative_reductions,
                "maximum_continuous_relative_reduction": continuous_improvement,
                "improvable": improvable,
                "base_success_in_30_to_80_percent": base_success_in_target_range,
                "base_disturbance_at_least_2x_clean": disturbance_at_least_2x,
                "eligible": eligible,
            }
        )

    def choose(
        parameter_keys: set[str],
        excluded_names: set[str] | None = None,
    ) -> Mapping[str, Any]:
        excluded_names = excluded_names or set()
        pool = [
            row
            for row in rows
            if row["name"] not in excluded_names
            and any(key in row["parameters"] for key in parameter_keys)
        ]
        if not pool:
            raise ValueError(
                "no candidates for stress family parameters "
                f"{sorted(parameter_keys)}"
            )

        def score(row: Mapping[str, Any]) -> tuple[float, ...]:
            disturbance = float(row["maximum_disturbance_ratio_vs_clean"])
            failure_rate = 1.0 - float(row["base"]["success_rate"])
            return (
                float(bool(row["eligible"])),
                float(bool(row["base_success_in_30_to_80_percent"])),
                float(row["success_delta_full_minus_base"]),
                float(row["binary_risk_reduction"]),
                float(row["maximum_continuous_relative_reduction"]),
                disturbance,
                failure_rate,
            )

        return max(pool, key=score)

    hidden = choose({"hidden_authority_gamma"})
    release = choose({"donor_release_advance_steps"}, {hidden["name"]})
    contact = choose(
        {
            "receiver_friction",
            "receiver_grasp_offset_mm",
            "object_com_shift_mm",
        },
        {hidden["name"], release["name"]},
    )
    selections = {
        "S1_hidden_authority_mismatch": hidden,
        "S2_premature_release_risk": release,
        "S3_contact_quality_degradation": contact,
    }
    frozen = {
        "experiment": "R22-P19-Stage2C",
        "source": "preregistered_calibration_seeds_0_1",
        "selection_rule": (
            "base success 30-80 percent, or disturbance >=2x clean with "
            "C13-improvable space; deterministic diagnostic fallback retained"
        ),
        "conditions": {"clean": {}},
        "selection_audit": {},
        "accepted": False,
        "pai_job_created": False,
    }
    for frozen_name, row in selections.items():
        frozen["conditions"][frozen_name] = dict(row["parameters"])
        frozen["selection_audit"][frozen_name] = {
            "source_candidate": row["name"],
            "eligible": row["eligible"],
            "base_success_rate": row["base"]["success_rate"],
            "maximum_disturbance_ratio_vs_clean": row[
                "maximum_disturbance_ratio_vs_clean"
            ],
            "improvable": row["improvable"],
        }
    decision = {
        "status": "COMPLETE",
        "candidate_count_including_clean": len(candidates),
        "nonclean_candidate_count": len(candidates) - 1,
        "methods": ["C0", "C13"],
        "expected_cells": len(candidates)
        * len(config["stress_calibration"]["seeds"])
        * 2,
        "completed_cells": len(results),
        "all_preregistered_candidates_tested": all(
            len(index[(candidate["name"], method)])
            == len(config["stress_calibration"]["seeds"])
            for candidate in candidates
            for method in ("C0", "C13")
        ),
        "clean": clean,
        "candidates": rows,
        "frozen_selection": frozen["selection_audit"],
        "all_frozen_stresses_eligible": all(
            bool(row["eligible"]) for row in selections.values()
        ),
        "decision": (
            "THREE_STRESSES_FROZEN"
            if all(bool(row["eligible"]) for row in selections.values())
            else "DIAGNOSTIC_STRESSES_FROZEN_WITH_ELIGIBILITY_FAILURE"
        ),
        "accepted": False,
        "pai_job_created": False,
    }
    return decision, frozen


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--robotwin-root")
    parser.add_argument("--config")
    parser.add_argument("--tape-root")
    parser.add_argument("--output")
    parser.add_argument("--gpus", nargs="+", type=int, default=[1, 2, 3])
    args = parser.parse_args()
    for name in ("robotwin_root", "config", "tape_root", "output"):
        if getattr(args, name) is None:
            parser.error(f"--{name.replace('_', '-')} is required")

    repo_root = Path(__file__).resolve().parents[3]
    config_path = Path(args.config).resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    candidates = build_candidates(config)
    tapes = discover_tapes(Path(args.tape_root).resolve())
    seeds = [int(value) for value in config["stress_calibration"]["seeds"]]
    missing = sorted(set(seeds) - set(tapes))
    if missing:
        raise ValueError(f"missing expert tapes for calibration seeds {missing}")
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    cells = []
    index = 0
    for candidate in candidates:
        for seed in seeds:
            for method in ("C0", "C13"):
                cells.append(
                    {
                        "gpu": args.gpus[index % len(args.gpus)],
                        "seed": seed,
                        "method": method,
                        "condition_name": candidate["name"],
                        "condition_parameters": candidate["parameters"],
                        "robotwin_root": Path(args.robotwin_root).resolve(),
                        "config": config_path,
                        "tape": tapes[seed][0],
                        "meta": tapes[seed][1],
                        "output": output
                        / "cells"
                        / f"seed_{seed:04d}__{candidate['name']}__{method}",
                        "repo_root": repo_root,
                    }
                )
                index += 1

    receipts = []
    gpu_locks = {gpu: threading.Lock() for gpu in args.gpus}

    def run_locked(cell: Mapping[str, Any]) -> Dict[str, Any]:
        with gpu_locks[int(cell["gpu"])]:
            return _run_cell(cell)

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(args.gpus)) as pool:
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
            receipts.append(
                {
                    "seed": cell["seed"],
                    "condition": cell["condition_name"],
                    "method": cell["method"],
                    "gpu": cell["gpu"],
                    **receipt,
                }
            )
            print(
                f"STRESS_PROGRESS {count}/{len(cells)} seed={cell['seed']} "
                f"condition={cell['condition_name']} method={cell['method']} "
                f"status={receipt['status']}",
                flush=True,
            )
            write_json(output / "run_receipts.partial.json", receipts)

    results = [
        json.loads((Path(cell["output"]) / "result.json").read_text(encoding="utf-8"))
        for cell in cells
        if (Path(cell["output"]) / "result.json").is_file()
    ]
    decision, frozen = analyze_calibration(results, candidates, config)
    decision["status"] = "COMPLETE" if len(results) == len(cells) else "INCOMPLETE"
    decision["config_sha256"] = hashlib.sha256(config_path.read_bytes()).hexdigest()
    write_json(output / "STRESS_CALIBRATION_DECISION.json", decision)
    (output / "frozen_stage2c_stress.yaml").write_text(
        yaml.safe_dump(frozen, sort_keys=False), encoding="utf-8"
    )
    write_json(output / "run_receipts.json", receipts)
    print(
        f"STRESS_COMPLETE {len(results)}/{len(cells)} decision={decision['decision']}",
        flush=True,
    )
    return 0 if len(results) == len(cells) else 2


if __name__ == "__main__":
    raise SystemExit(main())
