from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
import numpy as np

from .channel_capacity import score_channels


def _auc(labels, scores):
    y, s = np.asarray(labels, dtype=int), np.asarray(scores, dtype=float)
    if len(np.unique(y)) < 2:
        return None
    pos, neg = s[y == 1], s[y == 0]
    return float(np.mean([(p > n) + 0.5 * (p == n) for p in pos for n in neg]))


def _calibration(labels, scores, bins=5):
    y, s = np.asarray(labels, dtype=float), np.clip(np.asarray(scores, dtype=float), 0, 1)
    brier = float(np.mean((s-y)**2))
    ece = 0.0
    for lo, hi in zip(np.linspace(0, 1, bins+1)[:-1], np.linspace(0, 1, bins+1)[1:]):
        mask = (s >= lo) & (s < hi if hi < 1 else s <= hi)
        if np.any(mask):
            ece += float(np.mean(mask) * abs(np.mean(s[mask])-np.mean(y[mask])))
    return {"brier": brier, "ece": ece}


def analyze(roots: list[Path]) -> dict:
    records = []
    episodes = []
    for root in roots:
        for path in sorted(root.rglob("seed_*.json")):
            data = json.loads(path.read_text())
            if data.get("status") != "COMPLETE":
                continue
            condition_name = path.parent.name if path.parent.name != "clean_raw" else "clean"
            episodes.append({"seed": data["seed"], "condition": condition_name,
                             "active_valid": data["active_window"]["valid"],
                             "task_success": data["task_success_after_active_reference"],
                             "moving_fraction": data["active_window"]["moving_fraction"],
                             "speed": data["active_window"]["mean_speed_mps"],
                             "overlap_contact": data["overlap_contact_fraction"]})
            receiver_index = 0 if data["receiver"] == "left" else 1
            for state in data["states"]:
                outcomes = state["rollout"]["outcomes"]
                full = outcomes["1.0"]
                intermediate = [score_channels(full, outcomes[str(level)], receiver_index)
                                for level in (0.75, 0.5, 0.25)]
                heldout = score_channels(full, outcomes["0.0"], receiver_index)
                impulse_sum = state["receiver_impulse"] + state["donor_impulse"]
                records.append({
                    "seed": data["seed"], "condition": condition_name,
                    "phase": state["normalized_phase"],
                    "label": int(heldout.capable),
                    "capacity": float(np.mean([v.full for v in intermediate])),
                    "translation": float(np.mean([v.translation for v in intermediate])),
                    "support": float(np.mean([v.support for v in intermediate])),
                    "rotation": float(np.mean([v.rotation for v in intermediate])),
                    "phase_baseline": state["normalized_phase"],
                    "contact_duration_baseline": state["normalized_phase"] if state["receiver_contact"] else 0.0,
                    "force_baseline": state["receiver_impulse"] / impulse_sum if impulse_sum > 1e-12 else 0.0,
                    "heldout_full": heldout.full,
                })
    predictors = ["capacity", "translation", "support", "rotation", "phase_baseline",
                  "contact_duration_baseline", "force_baseline"]
    labels = [r["label"] for r in records]
    metrics = {name: {"auroc": _auc(labels, [r[name] for r in records]),
                      **_calibration(labels, [r[name] for r in records])} for name in predictors}
    grouped = defaultdict(list)
    for row in records: grouped[row["condition"]].append(row)
    conditions = {name: {"states": len(rows), "capable_rate": float(np.mean([r["label"] for r in rows])),
                         "mean_capacity": float(np.mean([r["capacity"] for r in rows])),
                         "capacity_auroc": _auc([r["label"] for r in rows], [r["capacity"] for r in rows])}
                  for name, rows in sorted(grouped.items())}
    eligible = [name for name, value in conditions.items()
                if name != "clean" and 0.30 <= value["capable_rate"] <= 0.80]
    return {"schema": "r22p19-stage2d-capacity-analysis-v1", "episode_count": len(episodes),
            "state_count": len(records), "positive_rate": float(np.mean(labels)) if labels else None,
            "active_task": {"valid_rate": float(np.mean([e["active_valid"] for e in episodes])),
                            "success_rate": float(np.mean([e["task_success"] for e in episodes])),
                            "mean_moving_fraction": float(np.mean([e["moving_fraction"] for e in episodes])),
                            "mean_speed_mps": float(np.mean([e["speed"] for e in episodes])),
                            "mean_overlap_contact": float(np.mean([e["overlap_contact"] for e in episodes]))},
            "predictors": metrics, "conditions": conditions, "eligible_conditions": eligible,
            "records": records, "episodes": episodes}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, action="append", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = analyze(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True)+"\n")
    print(json.dumps({k: result[k] for k in ("episode_count", "state_count", "positive_rate", "eligible_conditions")}, indent=2))


if __name__ == "__main__": main()

