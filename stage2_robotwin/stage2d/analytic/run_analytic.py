from __future__ import annotations

import argparse
import json
from pathlib import Path
import numpy as np

from .baselines import run_baseline
from .system import contributions, internal_force_proxy, make_case, receiver_share


METHODS = [f"A{i}" for i in range(8)]


def evaluate(count: int) -> dict:
    rows: list[dict] = []
    for seed in range(count):
        case = make_case(seed)
        for method in METHODS:
            result, routed_target = run_baseline(case, method)
            left, right = contributions(case, result.action)
            net = left + right
            share = receiver_share(case, result.action)
            rows.append({
                "seed": seed, "method": method, "desired": case.desired_receiver,
                "routed_target": routed_target, "current": case.current_receiver,
                "actual": share, "desired_mae": abs(share - case.desired_receiver),
                "routed_target_mae": abs(share - routed_target),
                "net_relative_error": float(np.linalg.norm(net - case.e_star) / np.linalg.norm(case.e_star)),
                "internal_force": internal_force_proxy(case, result.action),
                "action_modification": float(np.linalg.norm(result.action - case.u_base) /
                                             max(np.linalg.norm(case.u_base), 1e-12)),
                "feasible": bool(result.success and np.linalg.norm(net - case.e_star) <= 0.050001),
                "movement": share - case.current_receiver,
                "desired_movement": case.desired_receiver - case.current_receiver,
                "partial_failure": case.partial_failure, "delay": case.delay,
                "solver_message": result.solver_message,
            })
    summary = {}
    for method in METHODS:
        rs = [r for r in rows if r["method"] == method]
        summary[method] = {key: float(np.mean([r[key] for r in rs])) for key in
                           ["desired_mae", "routed_target_mae", "net_relative_error",
                            "internal_force", "action_modification", "feasible"]}
    by = {m: [r for r in rows if r["method"] == m] for m in METHODS}
    correct = by["A4"]
    swapped = by["A5"]
    opposite = np.mean([np.sign(a["movement"]) == -np.sign(b["desired_movement"])
                        for a, b in zip(swapped, correct)])
    v1_transfer = np.mean([abs(r["movement"]) for r in by["A3"]])
    gates = {
        "tracking_mae_le_0p15": summary["A4"]["desired_mae"] <= 0.15,
        "net_error_le_0p05": summary["A4"]["net_relative_error"] <= 0.05,
        "correct_beats_swapped_random": summary["A4"]["desired_mae"] < min(
            summary["A5"]["desired_mae"], summary["A6"]["desired_mae"]),
        "swapped_opposite_rate_ge_0p9": bool(opposite >= 0.9),
        "internal_not_above_conservation": summary["A7"]["internal_force"] <= summary["A1"]["internal_force"] + 1e-9,
        "feasibility_ge_0p9": summary["A4"]["feasible"] >= 0.9,
        "v1_cannot_transfer": bool(v1_transfer < 0.02),
    }
    return {"schema": "r22p19-stage2d-analytic-v1", "seed_count": count,
            "summary": summary, "diagnostics": {"swapped_opposite_rate": float(opposite),
            "v1_mean_absolute_movement": float(v1_transfer)}, "gates": gates,
            "decision": "ANALYTIC_GO" if all(gates.values()) else "ANALYTIC_NO_GO", "rows": rows}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--count", type=int, default=256)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = evaluate(args.count)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ["seed_count", "decision", "gates"]}, indent=2))


if __name__ == "__main__":
    main()

