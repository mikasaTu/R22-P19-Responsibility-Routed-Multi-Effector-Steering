"""Frozen Stage 2D comparator registry."""

CLOSED_LOOP_BASELINES = {
    "C0": "base_expert", "C1": "fixed_phase_ramp", "C2": "contact_duration",
    "C3": "force_impulse", "C4": "release_guard_only", "C5": "v1_shapley",
    "C6": "capacity_release_only", "C7": "phase_target_v2_operator",
    "C8": "correct_capacity_desired", "C9": "episode_shuffled_capacity",
    "C10": "time_shifted_capacity", "C11": "swapped_desired",
    "C12": "conservation_only", "C13": "capacity_hysteresis_4d",
    "C14": "full_internal_suppression", "C15": "operator_null",
}

