from stage2_robotwin.stage2c.responsibility.natural_analysis import (
    analyze_natural_responsibility,
    projected_share,
)


def test_projected_share_is_bounded_and_oriented():
    assert projected_share(1.0, 0.0) == 1.0
    assert projected_share(0.0, 1.0) == 0.0
    assert projected_share(0.4, 0.4) == 0.5
    assert 0.0 <= projected_share(-4.0, 8.0) <= 1.0


def _estimate(left, right):
    outcome = {
        "translation": [0.01, 0.0, 0.0],
        "rotation_vector": [0.0, 0.0, 0.0],
    }
    zero = {
        "translation": [0.0, 0.0, 0.0],
        "rotation_vector": [0.0, 0.0, 0.0],
    }
    return {
        "rho_left": left,
        "rho_right": right,
        "rho_joint": 0.0,
        "outcomes": {"LR": outcome, "ZERO": zero},
    }


def _cell(seed, profile, score, gamma):
    left = 0.5 * (1.0 + score)
    right = 0.5 * (1.0 - score)
    record = {
        "step": 100,
        "e4_relative_step": 0,
        "future_risk": {"peak_object_angular_velocity": float(seed)},
        "baselines": {"left_share": {"phase": 0.5}},
        "oracle_branch_count": 4,
        "simulated_physics_steps": 80,
        "by_horizon": {
            str(horizon): _estimate(left, right) for horizon in (5, 10, 20)
        },
    }
    return {
        "seed": seed,
        "profile": profile,
        "gamma": gamma,
        "records": [record],
        "prefix_fingerprint_at_E2_minus_1": {"sha256": f"prefix-{seed}"},
        "tape_sha256": f"tape-{seed}",
        "assignment_unobservable_before_E2": True,
    }


def test_hidden_accuracy_uses_paired_profile_contrast_not_absolute_dominance():
    # LEFT_HIDDEN is still right-dominant in absolute terms (-0.3), but it is
    # more leftward than the paired RIGHT_HIDDEN profile (-0.7).  The correct
    # authority statistic is therefore the paired contrast (+0.4).
    cells = []
    for seed in (0, 1, 2):
        cells.extend(
            [
                _cell(seed, "NATURAL", 0.1, None),
                _cell(seed, "LEFT_HIDDEN_AUTHORITY", -0.3, 0.8),
                _cell(seed, "RIGHT_HIDDEN_AUTHORITY", -0.7, 0.8),
            ]
        )
    config = {
        "seed_contract": {"calibration": [0, 1], "heldout": [2]},
        "natural_responsibility": {
            "gammas": [0.8],
            "min_motion_effect_m": 1e-6,
            "min_dominance_margin": 1e-6,
            "bootstrap_repetitions": 100,
            "bootstrap_seed": 22,
        },
    }
    result = analyze_natural_responsibility(cells, config)
    assert result["selected_gamma"] == 0.8
    assert result["hidden_authority"]["accuracy"]["mean"] == 1.0
    assert result["hidden_authority"]["valid_rate"]["mean"] == 1.0
