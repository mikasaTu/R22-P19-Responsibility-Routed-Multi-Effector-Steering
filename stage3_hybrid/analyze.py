from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np


MODES = ["M0_BASE", "M1_EARLY_100", "M2_EARLY_50", "M3_DELAY_50", "M4_DELAY_100", "M5_ABORT_HOLD"]


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def load_roots(roots):
    rows = []
    for root in roots:
        completion = json.loads((root / "completion.json").read_text())
        if not completion["matrix_complete"]:
            raise RuntimeError(f"incomplete matrix {root}")
        rows.extend(json.loads(path.read_text()) for path in sorted((root / "cells").glob("*.json")) if not path.name.endswith("failure.json"))
    return rows


def key(row):
    m = row["metrics"]
    return (int(m["eventual_task_success"]), int(not m["drop"]), int(not m["takeover_failure"]),
            -float(m["peak_relative_slip_m"]), -float(m["peak_object_linear_jerk"]),
            -float(m["donor_action_deviation_mean"]))


def summarize(rows):
    expected = defaultdict(set)
    for row in rows:
        expected[(row["condition"], row["seed"], row["repeat"])].add(row["mode"])
    missing = [list(k) + [sorted(set(MODES) - v)] for k, v in expected.items() if v != set(MODES)]
    if missing:
        raise RuntimeError(f"missing mode cells: {missing[:3]}")
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["condition"]].append(row)
    conditions, eligible = [], []
    for name, values in sorted(grouped.items()):
        instances = defaultdict(list)
        for row in values:
            instances[(row["seed"], row["repeat"])].append(row)
        base_success, oracle_success, disagreement = [], [], []
        selections = defaultdict(int)
        for _, cells in instances.items():
            base = next(row for row in cells if row["mode"] == "M0_BASE")
            oracle = max(cells, key=key)
            selections[oracle["mode"]] += 1
            bs = int(base["metrics"]["eventual_task_success"])
            os = int(oracle["metrics"]["eventual_task_success"])
            base_success.append(bs); oracle_success.append(os)
            successes = {int(row["metrics"]["eventual_task_success"]) for row in cells}
            spread = max(float(row["metrics"]["peak_relative_slip_m"]) for row in cells) - min(float(row["metrics"]["peak_relative_slip_m"]) for row in cells)
            disagreement.append(int(len(successes) > 1 or spread >= 0.02))
        base_rate, oracle_rate, disagree = map(float, (np.mean(base_success), np.mean(oracle_success), np.mean(disagreement)))
        parameters = values[0]["condition_parameters"]
        is_eligible = bool(name != "clean" and .30 <= base_rate <= .80 and disagree >= .30 and oracle_rate - base_rate >= .15 and oracle_rate >= .60)
        mode_summaries = {}
        for mode in MODES:
            mode_rows = [item for item in values if item["mode"] == mode]
            mode_summaries[mode] = {
                "success_rate": float(np.mean([item["metrics"]["eventual_task_success"] for item in mode_rows])),
                "handover_rate": float(np.mean([item["metrics"]["handover_complete"] for item in mode_rows])),
                "drop_rate": float(np.mean([item["metrics"]["drop"] for item in mode_rows])),
                "mean_peak_slip_m": float(np.mean([item["metrics"]["peak_relative_slip_m"] for item in mode_rows])),
                "mean_peak_jerk": float(np.mean([item["metrics"]["peak_object_linear_jerk"] for item in mode_rows])),
                "mean_action_deviation": float(np.mean([item["metrics"]["donor_action_deviation_mean"] for item in mode_rows])),
                "mean_donor_residual_steps": float(np.mean([item["metrics"]["donor_residual_duration_steps"] for item in mode_rows])),
            }
        row = {"name": name, "parameters": parameters, "episodes_x_repeats": len(instances),
               "base_success": base_rate, "oracle_success": oracle_rate,
               "oracle_minus_base": oracle_rate - base_rate, "candidate_disagreement": disagree,
               "oracle_selection_counts": dict(selections), "mode_summaries": mode_summaries,
               "eligible": is_eligible}
        conditions.append(row)
        if is_eligible:
            eligible.append({"name": name, "parameters": parameters})
    return conditions, eligible


def main():
    p = argparse.ArgumentParser(); p.add_argument("--roots", type=Path, nargs="+", required=True); p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(); rows = load_roots(args.roots); conditions, eligible = summarize(rows)
    decision = "CALIBRATION_ELIGIBLE" if len(eligible) >= 2 else "NO_INFORMATIVE_FAILURE_SPACE"
    result = {"schema": "r22p19.stage3a.calibration_analysis.v1", "decision": decision,
              "eligible_count": len(eligible), "eligible_conditions": eligible,
              "conditions": conditions, "accepted": False, "pai_job_count": 0}
    write_json(args.output, result); print(f"STAGE3_ANALYSIS {decision} eligible={len(eligible)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
