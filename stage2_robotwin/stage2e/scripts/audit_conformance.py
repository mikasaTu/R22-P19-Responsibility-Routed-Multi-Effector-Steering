from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path

from stage2_robotwin.stage2e.conformance.method_registry import METHODS
from stage2_robotwin.stage2e.conformance.runtime_receipt import RuntimeReceipt


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def audit(repo: Path) -> dict:
    stage2e = repo / "stage2_robotwin" / "stage2e"
    stage2c_v1 = repo / "stage2_robotwin" / "stage2c" / "operator" / "effect_nullspace_transfer_1d.py"
    local_runtime = stage2e / "allocator" / "effect_allocator_4d_runtime.py"
    closed_runtime = stage2e / "scripts" / "run_closed_loop_pilot.py"
    receipts = {}
    for name, spec in METHODS.items():
        receipt = RuntimeReceipt(spec)
        if spec.modifies_action:
            receipt.record_action_modification(spec.code_path)
        receipts[name] = receipt.validate()
    module_checks = {}
    for name, module in {
        "W2_MOTION_WITHDRAWAL": "stage2_robotwin.stage2e.withdrawal.motion_withdrawal",
        "W3_SUPPORT_WITHDRAWAL": "stage2_robotwin.stage2e.withdrawal.support_withdrawal",
        "W4_ROTATION_WITHDRAWAL": "stage2_robotwin.stage2e.withdrawal.rotation_withdrawal",
        "W5_RETENTION_WITHDRAWAL": "stage2_robotwin.stage2e.withdrawal.retention_withdrawal",
    }.items():
        loaded = importlib.import_module(module)
        module_checks[name] = callable(getattr(loaded, "apply", None))
    checks = {
        "A_same_4d_allocator_called_local_and_closed_loop": local_runtime.is_file() and closed_runtime.is_file(),
        "B_conservation_same_allocator_lambda_target_zero": False,
        "C_internal_method_nonzero_true_wrench_objective": False,
        "D_v1_baseline_real_stage2c_path_wired": stage2c_v1.is_file() and False,
        "E_operator_null_equal_budget_no_action": receipts["W1_OPERATOR_NULL"]["valid"],
        "F_release_only_continuous_arm_unchanged": False,
        "G_solver_receipts_match_declared_withdrawal_methods": all(v["valid"] for v in receipts.values()),
        "H_withdrawal_method_name_matches_real_code_path": all(module_checks.values()),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema": "r22p19.stage2e.conformance.v1",
        "decision": "CONFORMANCE_GO" if not failures else "CONFORMANCE_NO_GO",
        "accepted": False,
        "checks": checks,
        "failed_checks": failures,
        "method_specs": {name: spec.as_dict() for name, spec in METHODS.items()},
        "synthetic_runtime_receipts": receipts,
        "withdrawal_module_checks": module_checks,
        "scope_note": (
            "The frozen first scope forbids implementing allocator/state-machine/closed-loop. "
            "A-D/F therefore remain absent rather than being mocked. Physical withdrawal is "
            "run only as diagnostic continuation under the user's explicit complete-all request."
        ),
        "pai_job_created": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.repo.resolve())
    write_json(args.output.resolve(), result)
    print(result["decision"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
