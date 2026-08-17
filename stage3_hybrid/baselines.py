from __future__ import annotations

from stage3_hybrid.modes import MODES


BASELINES = {
    "B0": "M0_BASE", "B1": "M1_EARLY_100", "B2": "M2_EARLY_50",
    "B3": "M3_DELAY_50", "B4": "M4_DELAY_100", "B5": "M5_ABORT_HOLD",
    "B6": "ORACLE_LEXICOGRAPHIC", "B7": "RANDOM_BUDGET_MATCHED",
    "B8": "PHASE_HEURISTIC", "B9": "CONTACT_HEURISTIC",
    "B10": "EPISODE_SHUFFLED", "B11": "TIME_SHIFTED",
}


def oracle(cells: list[dict]) -> dict:
    def score(row):
        m = row["metrics"]
        return (int(m["eventual_task_success"]), int(not m["drop"]),
                int(not m["takeover_failure"]), -float(m["peak_relative_slip_m"]),
                -float(m["peak_object_linear_jerk"]),
                -float(m["donor_action_deviation_mean"]))
    return max(cells, key=score)


def validate_library() -> None:
    if set(BASELINES) != {f"B{i}" for i in range(12)}:
        raise ValueError("B0-B11 comparator contract incomplete")
    if [mode.name for mode in MODES] != [BASELINES[f"B{i}"] for i in range(6)]:
        raise ValueError("fixed mode baselines changed")

