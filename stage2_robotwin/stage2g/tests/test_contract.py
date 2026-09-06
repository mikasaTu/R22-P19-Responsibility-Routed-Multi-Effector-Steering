from pathlib import Path
import yaml
def contract():
    return yaml.safe_load((Path(__file__).parents[1]/"preregistration/EXPERIMENT_CONTRACT.yaml").read_text())
def test_scope_and_exact_gates():
    c=contract()
    assert c["seed_contract"]["calibration"] == [0,1]
    assert c["accepted"] is False and c["pai_job_created"] is False
    assert c["hypotheses"]["P2_requires_all_P1_gates"] is True
    assert c["gates"]["I1"]["both_peak_to_noise_floor_median_min"] == 10
    assert c["gates"]["I2"]["uninjected_to_injected_amplitude_max"] == .10
    assert c["gates"]["I3"]["swapped_a_soft_absolute_difference_max"] == .10
    assert c["gates"]["I4"]["unlocked_arm_authority_min"] == .85
    assert c["gates"]["I5"] == {"dual_contact_fraction_min":.95,"task_success_rate_min":.9}
    assert c["gates"]["A1"]["spearman_gamma_a_soft_min"] == .9
    assert c["gates"]["A2"]["lowest_nondegenerate_a_over_nominal_max"] == .6
    assert c["gates"]["A2"]["absolute_difference_strictly_greater_than_repeat_difference_p95_times"] == 3
    assert c["gates"]["A3"]["relative_gripper_slip_m_strict_max"] == .005
def test_matrix_is_complete_and_conditional():
    c=contract()
    s=c["matrix"]["stage_I"]
    assert sum(s[k]["cells"] for k in ["I_A","I_B","I_C","I_D","I_E"]) == s["total_cells"] == 24
    t=c["matrix"]["stage_II"]
    assert len(t["gammas"])*len(t["seeds"])*len(t["soft_arms"])*len(t["repeats"]) == t["total_cells"] == 48
    assert c["matrix"]["main_scene_snapshot_restore"] == "forbidden"
    assert c["premises"]["stage2f_144_plus_10"] == "VOID_DO_NOT_RUN"
def test_amplitude_freeze_cannot_rescue_failed_smoke():
    c=contract()
    assert c["probe"]["amplitude_candidates_m"] == [.003,.005,.008]
    assert c["amplitude_smoke"]["none_pass"] == "NO_ELIGIBLE_AMPLITUDE_DO_NOT_FREEZE"
    assert c["statistics"]["inference_unit"] == "episode"
    assert c["statistics"]["bootstrap_repetitions"] == 10000
    assert c["statistics"]["bootstrap_seed"] == 22019
