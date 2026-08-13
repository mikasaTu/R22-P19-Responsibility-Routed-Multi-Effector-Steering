import json
from pathlib import Path

import numpy as np

from stage2_robotwin.stage2b.scripts.analyze_stage2b import (
    bootstrap_mean_ci,
    classify_heldout,
    episode_metrics,
    paired_details,
)


def record(driver, gamma, left_effect, right_effect, rho):
    direction = [1.0, 0.0, 0.0]
    outcomes = {
        "ZERO": {"translation": [0, 0, 0]},
        "L": {"translation": [left_effect, 0, 0]},
        "R": {"translation": [right_effect, 0, 0]},
    }
    return {
        "episode": 0,
        "seed": 2,
        "step": 100,
        "e4_relative_step": -25,
        "horizon": 5,
        "profile": {"driver": driver, "gamma": gamma},
        "task_frame": {"e_parallel": direction},
        "outcomes": outcomes,
        "responsibility": {
            "three_channel": {
                "rho_left": rho[0],
                "rho_right": rho[1],
                "rho_joint": rho[2],
            },
            "harmful_opposing": {"left": 0.0, "right": 0.0},
        },
        "baseline_features": {"same": True},
    }


def test_invalid_pair_is_excluded_not_counted_as_oracle_error():
    records = [
        record("left", 0.4, 2e-6, 0.0, (1, 0, 0)),
        record("right", 0.4, 2e-6, 1e-6, (0, 1, 0)),
    ]
    details = paired_details(records, 1e-6, 1e-6)
    assert len(details) == 1
    assert details[0]["pair_valid"] is False
    assert details[0]["oracle_correct"] is None
    metrics = episode_metrics(details)[0]
    assert metrics["valid_pair_count"] == 0
    assert metrics["oracle_orientation_accuracy"] is None


def test_valid_matched_pair_has_oriented_oracle_margin():
    records = [
        record("left", 0.4, 4e-6, 0.0, (0.9, 0.1, 0.2)),
        record("right", 0.4, 0.0, 4e-6, (0.1, 0.9, 0.3)),
    ]
    details = paired_details(records, 1e-6, 1e-6)
    assert details[0]["pair_valid"] is True
    assert details[0]["oracle_correct"] is True
    assert np.isclose(details[0]["oracle_oriented_margin"], 1.6)


def test_bootstrap_resamples_episodes_and_is_deterministic():
    first = bootstrap_mean_ci([0.0, 1.0], repetitions=1000, seed=7)
    second = bootstrap_mean_ci([0.0, 1.0], repetitions=1000, seed=7)
    assert first == second
    assert first["statistical_unit"] == "episode"
    assert first["mean"] == 0.5


def test_heldout_classifier_keeps_diagnostic_separate():
    items = [
        {
            "gamma": 0.05,
            "valid_pair_count": 2,
            "valid_pair_rate": 0.5,
            "oracle_orientation_accuracy": 1.0,
            "rho_joint_abs_median": 0.1,
        }
        for _ in range(5)
    ]
    frozen = {
        "selected_gamma": 0.05,
        "selected_gamma_is_diagnostic_only": True,
        "synergy_threshold": 0.2,
    }
    result = classify_heldout(items, frozen)
    assert result["decision"] == "ONLY_EXTREME_INTERVENTION_SUPPORTED"

