from pathlib import Path
import json

import yaml

from stage2_robotwin.stage2c.scripts.calibrate_stress import (
    analyze_calibration,
    build_candidates,
)
from stage2_robotwin.stage2c.scripts.analyze_stage2c import (
    _interruption_recovery_audit,
    _tape_manifest,
    analyze_closed_loop,
)


def test_stress_candidate_contract_covers_every_preregistered_value_once():
    config_path = (
        Path(__file__).resolve().parents[1] / "configs" / "stage2c.yaml"
    )
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    candidates = build_candidates(config)
    assert len(candidates) == 24
    assert candidates[0] == {"name": "clean", "factor": "clean", "parameters": {}}
    assert len({item["name"] for item in candidates}) == len(candidates)
    assert sum(item["factor"] == "two_factor" for item in candidates) == 2
    for factor, values in config["stress_calibration"]["candidates"].items():
        observed = [
            item["parameters"][factor]
            for item in candidates
            if item["factor"] == factor
        ]
        assert observed == values


def test_two_factor_candidates_can_be_frozen_without_duplicate_stress_sources():
    config_path = (
        Path(__file__).resolve().parents[1] / "configs" / "stage2c.yaml"
    )
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    candidates = build_candidates(config)
    results = []
    for candidate in candidates:
        for seed in config["stress_calibration"]["seeds"]:
            for method in ("C0", "C13"):
                angular = 1.0
                if candidate["name"] in {
                    "hidden_authority_gamma_0p8",
                    "two_factor_01__donor_release_advance_steps_20__receiver_friction_0p5",
                    "receiver_friction_0p3",
                }:
                    angular = 3.0 if method == "C0" else 1.0
                results.append(
                    {
                        "seed": seed,
                        "condition": candidate["name"],
                        "method": method,
                        "metrics": {
                            "success": True,
                            "handover_completion": True,
                            "drop": False,
                            "premature_release": False,
                            "receiver_takeover_failure": False,
                            "peak_object_angular_velocity": angular,
                            "peak_object_linear_jerk": 1.0,
                            "peak_relative_slip_m": 1.0,
                            "donor_residual_influence_impulse_sum": 1.0,
                            "min_object_height_m": 1.0,
                        },
                    }
                )
    decision, _ = analyze_calibration(results, candidates, config)
    frozen = decision["frozen_selection"]
    sources = [item["source_candidate"] for item in frozen.values()]
    assert (
        frozen["S2_premature_release_risk"]["source_candidate"]
        == "two_factor_01__donor_release_advance_steps_20__receiver_friction_0p5"
    )
    assert len(sources) == len(set(sources))


def _closed_result(seed, condition, method):
    angular = 1.0
    jerk = 2.0
    slip = 0.02
    if method in {"C6", "C7", "C13"}:
        angular, jerk, slip = 0.5, 1.0, 0.01
    metrics = {
        "success": True,
        "handover_completion": True,
        "drop": False,
        "premature_release": False,
        "receiver_takeover_failure": False,
        "peak_object_angular_velocity": angular,
        "peak_object_linear_jerk": jerk,
        "peak_relative_slip_m": slip,
        "donor_residual_influence_impulse_sum": 0.1,
        "min_object_height_m": 0.9,
        "final_object_position_x_m": 1.0,
        "final_object_position_y_m": 2.0,
        "final_object_position_z_m": 0.9,
    }
    return {
        "seed": seed,
        "condition": condition,
        "method": method,
        "metrics": metrics,
        "prefix_fingerprint_at_E2_minus_1": {
            "sha256": f"prefix-{seed}-{condition}"
        },
        "tape_sha256": f"tape-{seed}",
        "operator_log": [],
        "fresh_process": True,
        "oracle_sandbox_separate_scene": method != "C0",
        "oracle_branch_count": 0 if method == "C0" else 80,
        "simulated_oracle_physics_steps": 0 if method == "C0" else 400,
    }


def test_closed_loop_analysis_enforces_matrix_prefix_null_and_budget_contract(tmp_path):
    paths = []
    methods = [f"C{index}" for index in range(14)]
    for seed in (1, 2):
        for condition in ("clean", "S1"):
            for method in methods:
                path = tmp_path / f"{seed}-{condition}-{method}.json"
                path.write_text(
                    json.dumps(_closed_result(seed, condition, method)),
                    encoding="utf-8",
                )
                paths.append(path)
    config = {
        "closed_loop": {
            "seeds": [1, 2],
            "conditions": ["clean", "S1"],
            "methods": methods,
        },
        "statistics": {"bootstrap_repetitions": 100, "bootstrap_seed": 22},
    }
    null = {
        "fresh_prefix": {
            "effect_gate": {
                "peak_object_angular_velocity": 0.0,
                "peak_object_linear_jerk": 0.0,
                "peak_relative_slip_m": 0.0,
                "donor_residual_influence_impulse_sum": 0.0,
            }
        }
    }
    result = analyze_closed_loop(paths, config, null)
    assert result["status"] == "COMPLETE"
    assert result["completed_cells"] == 56
    assert result["all_method_prefixes_identical"]
    assert result["C0_vs_C11_exact_on_all_reported_metrics"]
    assert result["all_oracle_methods_have_equal_budget_within_seed_condition"]
    assert result["operator_mechanism_audit"]["all_conditions"]["C6"][
        "episode_count"
    ] == 4


def test_interruption_audit_distinguishes_recovered_and_unrecovered_cells(tmp_path):
    recovered = tmp_path / "cells" / "recovered"
    recovered.mkdir(parents=True)
    (recovered / "failure.json").write_text(
        json.dumps({"error_type": "BrokenPipeError", "error": "pipe"}),
        encoding="utf-8",
    )
    (recovered / "result.json").write_text(
        json.dumps({"status": "COMPLETE"}), encoding="utf-8"
    )
    unrecovered = tmp_path / "cells" / "unrecovered"
    unrecovered.mkdir(parents=True)
    (unrecovered / "failure.json").write_text(
        json.dumps({"error_type": "RuntimeError", "error": "failed"}),
        encoding="utf-8",
    )
    audit = _interruption_recovery_audit(tmp_path)
    assert audit["failure_artifact_count"] == 2
    assert audit["recovered_count"] == 1
    assert audit["unrecovered_count"] == 1
    assert not audit["all_failure_artifacts_recovered"]


def test_tape_manifest_uses_capture_attempt_gate_for_compact_metadata(tmp_path):
    shard = tmp_path / "shard-gpu1"
    tapes = shard / "tapes"
    tapes.mkdir(parents=True)
    tape_path = tapes / "seed_0002.npz"
    tape_path.write_bytes(b"formal-tape-placeholder")
    metadata = {
        "seed": 2,
        "episode": 2,
        "steps": 100,
        "events": {f"E{index}": 10 * index for index in range(7)},
        "tape_sha256": "formal-tape-sha256",
    }
    (tapes / "seed_0002.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )
    (shard / "attempts.json").write_text(
        json.dumps([{"seed": 2, "status": "COMPLETE"}]),
        encoding="utf-8",
    )

    manifest = _tape_manifest(tmp_path)
    assert manifest["tape_count"] == 1
    record = manifest["records"][0]
    assert record["capture_status"] == "COMPLETE"
    assert record["task_success"]
    assert record["handover_completed"]
    assert record["event_contract_complete"]
    assert record["task_success_source"] == (
        "capture_COMPLETE_requires_plan_success_and_check_success"
    )
