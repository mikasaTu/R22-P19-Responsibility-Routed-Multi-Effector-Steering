from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from stage3_hybrid.modes import MODE_BY_NAME


FINAL_DECISIONS = {"BLOCKED_RUNTIME", "NO_INFORMATIVE_FAILURE_SPACE", "MODE_LIBRARY_NO_GO",
                   "ORACLE_UPPER_BOUND_GO_SHORT_HORIZON_PENDING", "SHORT_HORIZON_SIGNAL_WEAK",
                   "HYBRID_ROUTING_SIGNAL_GO"}


def validate_receipt_flags(row: dict) -> bool:
    return bool(row["fresh_process"] and row["fresh_scene"]
                and row["replayed_from_episode_start"]
                and not row["snapshot_restore_used"])


def validate_final_decision(decision: str) -> None:
    if decision not in FINAL_DECISIONS:
        raise ValueError(f"unregistered final decision {decision}")


def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("--root", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    completion = json.loads((args.root / "completion.json").read_text())
    if not completion["matrix_complete"]:
        raise RuntimeError("audit refuses an incomplete matrix")
    rows = [json.loads(path.read_text()) for path in sorted((args.root / "cells").glob("*.json"))]
    groups = defaultdict(list)
    for row in rows: groups[(row["seed"], row["condition"], row["repeat"])].append(row)
    checks = {"all_fresh_process": True, "no_snapshot_restore": True,
              "receiver_hash_invariant": True, "prefix_hash_invariant": True,
              "m0_noop": True, "activation_exact": True, "all_accepted_false": True,
              "all_pai_job_false": True}
    failures = []
    for key, cells in groups.items():
        if len({row["receiver_command_sha256"] for row in cells}) != 1:
            checks["receiver_hash_invariant"] = False; failures.append([*key, "receiver_hash"])
        if len({row["prefix_command_sha256"] for row in cells}) != 1:
            checks["prefix_hash_invariant"] = False; failures.append([*key, "prefix_hash"])
        for row in cells:
            checks["all_fresh_process"] &= validate_receipt_flags(row)
            checks["no_snapshot_restore"] &= not bool(row["snapshot_restore_used"])
            checks["all_accepted_false"] &= not bool(row["accepted"])
            checks["all_pai_job_false"] &= not bool(row["pai_job_created"])
            if row["mode"] == "M0_BASE": checks["m0_noop"] &= row["metrics"]["donor_action_deviation_mean"] == 0.0
            mode = MODE_BY_NAME[row["mode"]]
            expected = None if mode.kind == "base" else (row["events"]["E4"] - mode.offset if mode.kind == "early" else row["events"]["E4"])
            checks["activation_exact"] &= row["donor_source_first_changed"] == expected
    result = {"schema": "r22p19.stage3a.audit.v1", "cell_count": len(rows),
              "group_count": len(groups), "checks": checks, "failures": failures,
              "audit_pass": all(checks.values()), "accepted": False, "pai_job_count": 0}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"STAGE3_AUDIT pass={result['audit_pass']} cells={len(rows)}")
    return 0 if result["audit_pass"] else 1


if __name__ == "__main__": raise SystemExit(main())
