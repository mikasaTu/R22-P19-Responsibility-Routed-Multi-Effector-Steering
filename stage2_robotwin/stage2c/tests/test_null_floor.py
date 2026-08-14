from stage2_robotwin.stage2c.replay.null_floor import analyze_fresh_null_floor


def _result(method, replicate, value):
    return {
        "seed": 0,
        "condition": "clean",
        "method": method,
        "replicate": replicate,
        "metrics": {
            "peak_object_angular_velocity": value,
            "peak_object_linear_jerk": 2 * value,
            "peak_relative_slip_m": 3 * value,
            "min_object_height_m": 1 - value,
            "donor_residual_influence_impulse_sum": 4 * value,
        },
    }


def test_null_floor_reports_within_and_cross_method_differences():
    values = [_result(method, replicate, replicate * 0.1) for method in ("B0", "OPERATOR_NULL") for replicate in range(3)]
    report = analyze_fresh_null_floor(values)
    assert report["pooled_within_method"]["peak_object_angular_velocity"]["count"] == 6
    assert report["paired_B0_vs_operator_null"]["peak_object_angular_velocity"]["max_absolute_pair_difference"] == 0.0
    assert report["effect_gate"]["peak_relative_slip_m"] > 0.0
