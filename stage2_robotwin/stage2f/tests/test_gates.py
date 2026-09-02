import numpy as np
import pytest
import json
from pathlib import Path

from stage2_robotwin.stage2f.analysis.gates import (
    GAMMAS,
    cell_to_gate_row,
    evaluate_knob,
    percentile95_pairwise_spread,
    spearman_rho,
    weak_monotonic_fraction,
)


def test_spearman_ties_and_direction():
    assert spearman_rho([1, 2, 3], [1, 2, 3]) == 1.0
    assert spearman_rho([1, 2, 3], [3, 2, 1]) == -1.0
    assert spearman_rho([1, 2, 3], [5, 5, 5]) == 0.0
    assert spearman_rho([1, 2, 3, 4], [1, 2, 2, 4]) > 0.9


def test_weak_monotonic_reports_constant_as_weak_not_strict():
    result = weak_monotonic_fraction([[1, 1, 1], [1, 2, 3], [1, 3, 2]])
    assert result["weak_monotonic_fraction"] == 2 / 3
    assert result["strict_decrease_fraction"] == 1 / 3


def test_strict_decrease_direction_is_relative_to_reducing_gamma():
    result = weak_monotonic_fraction([[1.0, 2.0, 3.0], [3.0, 2.0, 1.0]])
    assert result["weak_monotonic_fraction"] == 0.5
    assert result["strict_decrease_when_gamma_reduced_fraction"] == 0.5


def test_null_spread_uses_pairwise_absolute_differences():
    assert percentile95_pairwise_spread([1.0, 1.0, 1.0]) == 0.0
    assert percentile95_pairwise_spread([0.0, 1.0]) == 1.0


def synthetic_rows(success=True):
    rows = []
    for seed in (0, 1):
        for arm in ("left", "right"):
            for gamma in GAMMAS:
                for repeat in (0, 1):
                    rows.append({
                        "seed": seed,
                        "knob": "K1_drive_compliance",
                        "soft_arm": arm,
                        "gamma": gamma,
                        "repeat": repeat,
                        "soft_parallel_impulse": gamma,
                        "rho_soft_h5": gamma,
                        "rho_soft_h10": gamma,
                        "rho_soft_h20": gamma,
                        "dual_contact_fraction": 1.0,
                        "donor_contact_not_early": True,
                        "task_success": success,
                        "receiver_command_sha256": f"receiver-{seed}-{arm}",
                        "effect_vector_sha256": f"effect-{seed}-{arm}-{gamma}",
                        "frozen_active_reference_sha256": f"active-{seed}",
                        "command_states": [{"step": 10, "parallel_action_abs": gamma}],
                    })
    return rows


def test_all_gates_pass_on_isolated_monotone_synthetic_data():
    result = evaluate_knob(synthetic_rows(), {0: [0.0] * 5, 1: [0.0] * 5})
    assert all(result["gates"].values())
    assert result["decision"] == "AUTHORITY_KNOB_SUPPORTED"


def test_degenerate_decision_when_only_nondegeneracy_fails():
    result = evaluate_knob(synthetic_rows(success=False), {0: [0.0] * 5, 1: [0.0] * 5})
    assert result["gates"]["G1"] and result["gates"]["G2"] and result["gates"]["G5"]
    assert not result["gates"]["G4"]
    assert result["decision"] == "AUTHORITY_KNOB_DEGENERATE"


def test_repeat_byte_mismatch_fails_g6():
    rows = synthetic_rows()
    rows[0]["effect_vector_sha256"] = "mismatch"
    result = evaluate_knob(rows, {0: [0.0] * 5, 1: [0.0] * 5})
    assert not result["gates"]["G6"]


def test_cross_gamma_receiver_drift_fails_g6():
    rows = synthetic_rows()
    rows[0]["receiver_command_sha256"] = "cross-gamma-drift"
    result = evaluate_knob(rows, {0: [0.0] * 5, 1: [0.0] * 5})
    assert not result["gates"]["G6"]


def test_active_reference_drift_fails_g6():
    rows = synthetic_rows()
    rows[0]["frozen_active_reference_sha256"] = "wrong-active-tape"
    result = evaluate_knob(rows, {0: [0.0] * 5, 1: [0.0] * 5})
    assert not result["gates"]["G6"]


@pytest.mark.parametrize("nulls", [{0: [0.0] * 5}, {0: [0.0] * 4, 1: [0.0] * 5}])
def test_missing_or_short_null_floor_fails_closed(nulls):
    with pytest.raises(ValueError, match="null"):
        evaluate_knob(synthetic_rows(), nulls)


def test_duplicate_or_missing_matrix_cell_fails_closed():
    rows = synthetic_rows()
    with pytest.raises(ValueError, match="48 cells"):
        evaluate_knob(rows[:-1], {0: [0.0] * 5, 1: [0.0] * 5})
    rows[-1] = rows[0].copy()
    with pytest.raises(ValueError, match="duplicate"):
        evaluate_knob(rows, {0: [0.0] * 5, 1: [0.0] * 5})


def test_g4_is_evaluated_per_gamma_not_pooled():
    rows = synthetic_rows()
    for row in rows:
        if row["gamma"] == 0.2 and row["seed"] == 0:
            row["task_success"] = False
    result = evaluate_knob(rows, {0: [0.0] * 5, 1: [0.0] * 5})
    group = next(item for item in result["G4"]["per_gamma"] if item["gamma"] == 0.2)
    assert group["success_rate"] == 0.5 and not group["pass"]
    assert not result["gates"]["G4"]


def test_production_schema_adapter_rejects_unaligned_oracle_and_flattens():
    state = {
        "step": 10, "parallel_action_abs": 0.5,
        "by_horizon": {
            str(h): {"rho_soft": 0.1, "rho_receiver": 0.2, "rho_joint": 0.3}
            for h in (5, 10, 20)
        },
    }
    cell = {
        "schema": "r22p19.stage2f.authority_knob_cell.v1", "status": "COMPLETE",
        "seed": 0, "knob": "K1_drive_compliance", "soft_arm": "left",
        "gamma": 1.0, "repeat": 0, "sample_count": 1,
        "physical_summary": {
            "soft_parallel_impulse_integral": 1.0, "dual_contact_fraction": 1.0,
            "donor_contact_not_early": True,
        },
        "task_success": True, "receiver_command_sha256": "a" * 64,
        "effect_vector_sha256": "b" * 64, "frozen_active_reference_sha256": "c" * 64,
        "accepted": False, "pai_job_created": False,
        "command_states": [state], "oracle_alignment_exact_at_all_samples": True,
    }
    row = cell_to_gate_row(cell)
    assert row["soft_parallel_impulse"] == 1.0 and row["rho_soft_h10"] == 0.1
    cell["oracle_alignment_exact_at_all_samples"] = False
    with pytest.raises(ValueError, match="not aligned"):
        cell_to_gate_row(cell)


def test_matched_gamma_one_action_ratio_is_materialized():
    from stage2_robotwin.stage2f.analysis.gates import attach_matched_gamma1_action_ratios

    rows = [
        {"seed": 0, "soft_arm": "left", "repeat": 0, "gamma": 1.0,
         "command_states": [{"step": 10, "parallel_action_abs": 2.0}]},
        {"seed": 0, "soft_arm": "left", "repeat": 0, "gamma": 0.2,
         "command_states": [{"step": 10, "parallel_action_abs": 0.5}]},
    ]
    derived = attach_matched_gamma1_action_ratios(rows)
    assert derived[0]["command_states"][0]["parallel_action_abs_ratio_to_matched_gamma_1"] == 1.0
    assert derived[1]["command_states"][0]["parallel_action_abs_ratio_to_matched_gamma_1"] == 0.25


def test_adapter_accepts_both_published_valid_smoke_jsons():
    root = Path(__file__).parents[1] / "results" / "preflight"
    for name in ("SMOKE_K1_LEFT_GAMMA_1P0.json", "SMOKE_K1_LEFT_GAMMA_0P2.json"):
        row = cell_to_gate_row(json.loads((root / name).read_text(encoding="utf-8")))
        assert row["seed"] == 0 and row["soft_arm"] == "left"
        assert np.isfinite(row["rho_soft_h10"])
