from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from stage3_hybrid.baselines import oracle


MODES = ["M0_BASE", "M1_EARLY_100", "M2_EARLY_50", "M3_DELAY_50", "M4_DELAY_100", "M5_ABORT_HOLD"]


def bootstrap_ci(values, seed=20260818):
    values = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    draws = [float(np.mean(rng.choice(values, size=len(values), replace=True))) for _ in range(10000)]
    return [float(np.quantile(draws, .025)), float(np.quantile(draws, .975))]


def main():
    p = argparse.ArgumentParser(); p.add_argument("--calibration", type=Path, required=True); p.add_argument("--heldout", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    calibration = json.loads(args.calibration.read_text())
    if calibration["eligible_count"] < 2: raise RuntimeError("heldout prohibited without two eligible calibration stresses")
    completion = json.loads((args.heldout / "completion.json").read_text())
    if not completion["matrix_complete"]: raise RuntimeError("heldout matrix incomplete")
    rows = [json.loads(path.read_text()) for path in sorted((args.heldout / "cells").glob("*.json"))]
    groups = defaultdict(list)
    for row in rows: groups[(row["condition"], row["seed"], row["repeat"])].append(row)
    if any({x["mode"] for x in cells} != set(MODES) for cells in groups.values()): raise RuntimeError("missing heldout candidate cell")
    by_condition = defaultdict(list)
    for (condition, seed, repeat), cells in groups.items(): by_condition[condition].append((seed, repeat, cells))
    results, passing = [], []
    for condition, instances in sorted(by_condition.items()):
        per_seed = defaultdict(list)
        for seed, repeat, cells in instances:
            base = next(x for x in cells if x["mode"] == "M0_BASE"); best = oracle(cells)
            bs, os = int(base["metrics"]["eventual_task_success"]), int(best["metrics"]["eventual_task_success"])
            slip_base = float(base["metrics"]["peak_relative_slip_m"]); slip_best = float(best["metrics"]["peak_relative_slip_m"])
            successes = {int(x["metrics"]["eventual_task_success"]) for x in cells}
            spread = max(float(x["metrics"]["peak_relative_slip_m"]) for x in cells) - min(float(x["metrics"]["peak_relative_slip_m"]) for x in cells)
            per_seed[seed].append({"base": bs, "oracle": os, "disagree": int(len(successes)>1 or spread>=.02),
                                   "reduction": (slip_base-slip_best)/max(abs(slip_base),1e-12), "mode": best["mode"]})
        episode_rows = []
        for seed, reps in sorted(per_seed.items()):
            episode_rows.append({"seed": seed, "base": float(np.mean([x["base"] for x in reps])),
                                 "oracle": float(np.mean([x["oracle"] for x in reps])),
                                 "disagree": float(np.mean([x["disagree"] for x in reps])),
                                 "reduction": float(np.mean([x["reduction"] for x in reps])),
                                 "selected_modes": [x["mode"] for x in reps]})
        base_rate=float(np.mean([x["base"] for x in episode_rows])); oracle_rate=float(np.mean([x["oracle"] for x in episode_rows])); disagreement=float(np.mean([x["disagree"] for x in episode_rows]))
        reductions=[x["reduction"] for x in episode_rows]; reduction=float(np.mean(reductions)); ci=bootstrap_ci(reductions)
        success_path=disagreement>=.30 and oracle_rate-base_rate>=.15
        disturbance_path=reduction>=.20 and ci[0]>0 and oracle_rate>=base_rate
        passed=bool(success_path or disturbance_path)
        row={"condition":condition,"episode_count":len(episode_rows),"base_success":base_rate,"oracle_success":oracle_rate,
             "success_gain":oracle_rate-base_rate,"candidate_disagreement":disagreement,"mean_slip_reduction":reduction,
             "paired_episode_bootstrap_ci95":ci,"success_path":success_path,"disturbance_path":disturbance_path,"passed":passed,
             "episodes":episode_rows}
        results.append(row)
        if passed: passing.append(condition)
    decision="ORACLE_UPPER_BOUND_GO_SHORT_HORIZON_PENDING" if len(passing)>=2 else "MODE_LIBRARY_NO_GO"
    output={"schema":"r22p19.stage3a.heldout.v1","decision":decision,"passing_stresses":passing,"conditions":results,
            "accepted":False,"pai_job_count":0}
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(output,indent=2,sort_keys=True)+"\n")
    print(f"STAGE3_HELDOUT {decision} passing={len(passing)}"); return 0


if __name__ == "__main__": raise SystemExit(main())
