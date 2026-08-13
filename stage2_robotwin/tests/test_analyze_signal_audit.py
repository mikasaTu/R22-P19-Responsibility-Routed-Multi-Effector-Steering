from stage2_robotwin.scripts.analyze_signal_audit import (
    authority_swap_by_horizon,
    direction_intervention_validity,
    paired_authority_metrics,
    phase_name,
)


def _record(step, profile, left, right):
    return {
        "step": step,
        "horizon": 5,
        "profile": {"name": profile},
        "responsibility": {
            "three_channel": {"rho_left": left, "rho_right": right}
        },
    }


def test_phase_names_use_latest_observed_boundary():
    assert phase_name(["E0", "E1", "E2"]) == "early_overlap"
    assert phase_name(["E0", "E1", "E2", "E3"]) == "stable_overlap"
    assert phase_name(["E0", "E1", "E2", "E3", "E4"]) == "donor_release"


def test_gain_swap_tracks_left_vs_right_authority():
    records = [
        _record(10, "gain_left_high", 0.8, 0.2),
        _record(10, "gain_right_high", 0.2, 0.8),
    ]
    result = paired_authority_metrics(records)
    assert result["gain"]["paired_state_count"] == 1
    assert result["gain"]["informative_state_count"] == 1
    assert result["gain"]["accuracy"] == 1.0


def test_zero_margin_is_a_tie_not_an_incorrect_swap():
    records = [
        _record(10, "gain_left_high", 0.0, 0.0),
        _record(10, "gain_right_high", 0.0, 0.0),
    ]
    result = paired_authority_metrics(records)
    assert result["gain"]["paired_state_count"] == 1
    assert result["gain"]["informative_state_count"] == 0
    assert result["gain"]["tie_count"] == 1
    assert result["gain"]["accuracy"] == 0.5
    assert result["gain"]["accuracy_informative_only"] is None


def test_authority_metrics_are_split_by_horizon():
    records = [
        _record(10, "gain_left_high", 0.8, 0.2),
        _record(10, "gain_right_high", 0.2, 0.8),
    ]
    records.extend({**record, "horizon": 10} for record in list(records))
    result = authority_swap_by_horizon(records)
    assert set(result) == {"H5", "H10"}
    assert result["H5"]["gain"]["accuracy"] == 1.0
    assert result["H10"]["gain"]["accuracy"] == 1.0


def test_direction_intervention_requires_real_object_authority_swap():
    def direction_record(name, left_effect, right_effect):
        left_expected = "left_authority" in name
        return {
            "step": 10,
            "horizon": 5,
            "profile": {"name": name},
            "direction_validation": {"motion_direction_world": [1.0, 0.0, 0.0]},
            "responsibility": {
                "three_channel": {
                    "rho_left": 0.8 if left_expected else 0.2,
                    "rho_right": 0.2 if left_expected else 0.8,
                }
            },
            "outcomes": {
                "ZERO": {"translation": [0.0, 0.0, 0.0]},
                "L": {"translation": [left_effect, 0.0, 0.0]},
                "R": {"translation": [right_effect, 0.0, 0.0]},
            },
        }

    valid = direction_intervention_validity(
        [
            direction_record("direction_left_authority", 0.002, 0.0),
            direction_record("direction_right_authority", 0.0, 0.002),
        ]
    )
    assert valid["valid_paired_state_count"] == 1
    assert valid["by_family"]["direction_null"]["valid_pair_oracle_accuracy"] == 1.0
    invalid = direction_intervention_validity(
        [
            direction_record("direction_left_authority", 0.002, 0.0),
            direction_record("direction_right_authority", 0.001, 0.0),
        ]
    )
    assert invalid["valid_paired_state_count"] == 0
