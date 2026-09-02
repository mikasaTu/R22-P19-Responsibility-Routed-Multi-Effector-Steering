from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import re
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

GAMMAS = (1.0, 0.8, 0.6, 0.4, 0.2, 0.05)
SEEDS = (0, 1)
SOFT_ARMS = ("left", "right")
REPEATS = (0, 1)


def _rankdata(values: Sequence[float]) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=np.float64)
    index = 0
    while index < len(values):
        end = index + 1
        while end < len(values) and values[order[end]] == values[order[index]]:
            end += 1
        ranks[order[index:end]] = 0.5 * (index + end - 1) + 1.0
        index = end
    return ranks


def spearman_rho(x: Sequence[float], y: Sequence[float]) -> float:
    if len(x) != len(y) or len(x) < 2:
        raise ValueError("Spearman inputs must have equal length >=2")
    rx, ry = _rankdata(x), _rankdata(y)
    if np.ptp(rx) == 0.0 or np.ptp(ry) == 0.0:
        return 0.0
    return float(np.corrcoef(rx, ry)[0, 1])


def weak_monotonic_fraction(groups: Iterable[Sequence[float]], tolerance: float = 0.0) -> dict[str, float]:
    """Values are ordered by increasing gamma.

    A positive delta means the command strictly decreases when gamma is reduced;
    ties satisfy weak monotonicity but are not counted as strict decreases.
    """
    weak, strict, total = 0, 0, 0
    for values in groups:
        array = np.asarray(values, dtype=np.float64)
        if len(array) < 2 or not np.all(np.isfinite(array)):
            continue
        total += 1
        deltas = np.diff(array)
        if np.all(deltas >= -float(tolerance)):
            weak += 1
            if np.any(deltas > float(tolerance)):
                strict += 1
    fraction = float(strict / total) if total else 0.0
    return {
        "weak_monotonic_fraction": float(weak / total) if total else 0.0,
        "strict_decrease_when_gamma_reduced_fraction": fraction,
        "strict_decrease_fraction": fraction,
        "group_count": int(total),
    }


def percentile95_pairwise_spread(values: Sequence[float]) -> float:
    array = np.asarray(values, dtype=np.float64)
    if len(array) < 2 or not np.all(np.isfinite(array)):
        raise ValueError("null spread requires at least two finite episode values")
    differences = np.abs(array[:, None] - array[None, :])
    return float(np.quantile(differences[np.triu_indices(len(array), 1)], 0.95))


def _mean(rows: Sequence[Mapping[str, Any]], key: str) -> float:
    values = np.asarray([float(row[key]) for row in rows], dtype=np.float64)
    if not len(values) or not np.all(np.isfinite(values)):
        raise ValueError(f"{key} is missing or non-finite")
    return float(np.mean(values))


def cell_to_gate_row(cell: Mapping[str, Any]) -> dict[str, Any]:
    """Strictly adapt one production cell JSON into the gate summary schema."""
    if cell.get("schema") != "r22p19.stage2f.authority_knob_cell.v1":
        raise ValueError("unexpected cell schema")
    if cell.get("status") != "COMPLETE" or cell.get("disposition") == "INVALID":
        raise ValueError("only valid COMPLETE cells may enter gate analysis")
    if cell.get("accepted") is not False or cell.get("pai_job_created") is not False:
        raise ValueError("cell must retain accepted=false and pai_job_created=false")
    physical = cell.get("physical_summary")
    states = cell.get("command_states")
    if not isinstance(physical, Mapping) or not isinstance(states, list) or not states:
        raise ValueError("cell is missing physical_summary or command_states")
    if not cell.get("oracle_alignment_exact_at_all_samples", False):
        raise ValueError("counterfactual oracle was not aligned at every sampled state")
    rho = {}
    for horizon in (5, 10, 20):
        values = np.asarray([
            float(state["by_horizon"][str(horizon)]["rho_soft"])
            for state in states
        ], dtype=np.float64)
        if len(values) != int(cell["sample_count"]) or not np.all(np.isfinite(values)):
            raise ValueError(f"invalid rho_soft horizon {horizon}")
        rho[f"rho_soft_h{horizon}"] = float(np.mean(values))
    for key in ("soft_parallel_impulse_integral", "dual_contact_fraction", "donor_contact_not_early"):
        if key not in physical:
            raise ValueError(f"physical_summary missing field: {key}")
    for key in ("receiver_command_sha256", "effect_vector_sha256", "frozen_active_reference_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(cell.get(key, ""))):
            raise ValueError(f"invalid SHA-256 format: {key}")
    return {
        "seed": int(cell["seed"]), "knob": str(cell["knob"]),
        "soft_arm": str(cell["soft_arm"]), "gamma": float(cell["gamma"]),
        "repeat": int(cell["repeat"]),
        "soft_parallel_impulse": float(physical["soft_parallel_impulse_integral"]),
        "dual_contact_fraction": float(physical["dual_contact_fraction"]),
        "donor_contact_not_early": bool(physical["donor_contact_not_early"]),
        "task_success": bool(cell["task_success"]),
        "receiver_command_sha256": str(cell["receiver_command_sha256"]),
        "effect_vector_sha256": str(cell["effect_vector_sha256"]),
        "frozen_active_reference_sha256": str(cell["frozen_active_reference_sha256"]),
        "command_states": deepcopy(states), **rho,
    }


def attach_matched_gamma1_action_ratios(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Derive the pre-registered ratio once all matched gamma=1 cells exist."""
    baselines: dict[tuple[int, str, int, int], float] = {}
    for row in rows:
        if float(row["gamma"]) != 1.0:
            continue
        for state in row["command_states"]:
            key = (int(row["seed"]), str(row["soft_arm"]), int(row["repeat"]), int(state["step"]))
            if key in baselines:
                raise ValueError(f"duplicate gamma=1 action baseline: {key}")
            baselines[key] = float(state["parallel_action_abs"])
    result = deepcopy(list(rows))
    for row in result:
        for state in row["command_states"]:
            key = (int(row["seed"]), str(row["soft_arm"]), int(row["repeat"]), int(state["step"]))
            if key not in baselines:
                raise ValueError(f"missing matched gamma=1 action baseline: {key}")
            baseline = baselines[key]
            actual = float(state["parallel_action_abs"])
            state["parallel_action_abs_ratio_to_matched_gamma_1"] = (
                actual / baseline if baseline > 1e-12 else (1.0 if actual <= 1e-12 else float("inf"))
            )
    return result


def _validate_matrix(rows: Sequence[Mapping[str, Any]]) -> str:
    if len(rows) != 48:
        raise ValueError(f"one-knob matrix must contain exactly 48 cells, got {len(rows)}")
    knobs = {str(row["knob"]) for row in rows}
    if len(knobs) != 1:
        raise ValueError(f"evaluate_knob requires exactly one knob, got {sorted(knobs)}")
    observed = [
        (int(row["seed"]), str(row["soft_arm"]), float(row["gamma"]), int(row["repeat"]))
        for row in rows
    ]
    expected = {
        (seed, arm, gamma, repeat)
        for seed in SEEDS for arm in SOFT_ARMS for gamma in GAMMAS for repeat in REPEATS
    }
    if len(set(observed)) != len(observed):
        raise ValueError("duplicate seed/arm/gamma/repeat cell")
    if set(observed) != expected:
        raise ValueError("matrix does not exactly match the frozen 2x2x6x2 contract")
    return next(iter(knobs))


def _validate_nulls(null_by_seed: Mapping[int, Sequence[float]]) -> None:
    if set(int(seed) for seed in null_by_seed) != set(SEEDS):
        raise ValueError("null floor must contain exactly seeds 0 and 1")
    for seed in SEEDS:
        values = np.asarray(null_by_seed[seed], dtype=np.float64)
        if len(values) != 5 or not np.all(np.isfinite(values)):
            raise ValueError(f"seed {seed} must contain exactly five finite null episodes")


def evaluate_knob(rows: Sequence[Mapping[str, Any]], null_by_seed: Mapping[int, Sequence[float]]) -> dict[str, Any]:
    """Evaluate frozen G1-G6 from one exact 48-cell knob matrix."""
    knob = _validate_matrix(rows)
    _validate_nulls(null_by_seed)
    rows = attach_matched_gamma1_action_ratios(rows)
    grouped: dict[tuple[int, str], dict[float, list[Mapping[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        grouped[(int(row["seed"]), str(row["soft_arm"]))][float(row["gamma"])].append(row)
    g1_groups, g2_groups, g3_groups = [], [], []
    for (seed, soft_arm), by_gamma in sorted(grouped.items()):
        increasing = sorted(GAMMAS)
        impulse = [_mean(by_gamma[g], "soft_parallel_impulse") for g in increasing]
        rho10 = [_mean(by_gamma[g], "rho_soft_h10") for g in increasing]
        rho5 = [_mean(by_gamma[g], "rho_soft_h5") for g in increasing]
        rho20 = [_mean(by_gamma[g], "rho_soft_h20") for g in increasing]
        r1 = spearman_rho(increasing, impulse)
        r10, r5, r20 = (spearman_rho(increasing, values) for values in (rho10, rho5, rho20))
        g1_groups.append({"seed": seed, "soft_arm": soft_arm, "rho": r1})
        g2_groups.append({"seed": seed, "soft_arm": soft_arm, "rho_h10": r10, "rho_h5": r5, "rho_h20": r20})
        baseline = _mean(by_gamma[1.0], "soft_parallel_impulse")
        reduced = _mean(by_gamma[0.2], "soft_parallel_impulse")
        floor = percentile95_pairwise_spread(null_by_seed[seed])
        g3_groups.append({
            "seed": seed, "soft_arm": soft_arm, "gamma_1": baseline,
            "gamma_0p2": reduced,
            "ratio": reduced / baseline if abs(baseline) > 1e-12 else float("inf"),
            "absolute_difference": baseline - reduced, "null_p95": floor,
            "pass": bool(reduced <= 0.5 * baseline and baseline - reduced > 3.0 * floor),
        })
    g1 = all(item["rho"] >= 0.9 for item in g1_groups)
    g2 = all(item["rho_h10"] >= 0.9 and item["rho_h5"] >= 0.0 and item["rho_h20"] >= 0.0 for item in g2_groups)
    g3 = all(item["pass"] for item in g3_groups)

    g4_groups = []
    for gamma in sorted(value for value in GAMMAS if value >= 0.2):
        subset = [row for row in rows if float(row["gamma"]) == gamma]
        success_rate = float(np.mean([bool(row["task_success"]) for row in subset]))
        passed = bool(
            len(subset) == 8
            and all(float(row["dual_contact_fraction"]) >= 0.90 for row in subset)
            and all(bool(row["donor_contact_not_early"]) for row in subset)
            and success_rate >= 0.80
        )
        g4_groups.append({"gamma": gamma, "success_rate": success_rate, "episode_count": len(subset), "pass": passed})
    g4 = all(item["pass"] for item in g4_groups)

    state_groups: dict[tuple[int, str, int, int], dict[float, float]] = defaultdict(dict)
    for row in rows:
        for state in row["command_states"]:
            key = (int(row["seed"]), str(row["soft_arm"]), int(row["repeat"]), int(state["step"]))
            gamma = float(row["gamma"])
            if gamma in state_groups[key]:
                raise ValueError(f"duplicate command state gamma for {key}")
            state_groups[key][gamma] = float(state["parallel_action_abs"])
    if not state_groups or any(set(values) != set(GAMMAS) for values in state_groups.values()):
        raise ValueError("command states do not form complete cross-gamma groups")
    monotonic_inputs = [[values[g] for g in sorted(GAMMAS)] for values in state_groups.values()]
    command = weak_monotonic_fraction(monotonic_inputs)
    g5 = command["weak_monotonic_fraction"] > 0.95

    receiver_hashes: dict[tuple[int, str], set[str]] = defaultdict(set)
    effect_hashes: dict[tuple[int, str, float], set[str]] = defaultdict(set)
    active_hashes: dict[int, set[str]] = defaultdict(set)
    for row in rows:
        receiver_key = (int(row["seed"]), str(row["soft_arm"]))
        effect_key = (*receiver_key, float(row["gamma"]))
        receiver_hashes[receiver_key].add(str(row["receiver_command_sha256"]))
        effect_hashes[effect_key].add(str(row["effect_vector_sha256"]))
        active_hashes[int(row["seed"])].add(str(row["frozen_active_reference_sha256"]))
    g6 = bool(
        all(len(values) == 1 and next(iter(values)) for values in receiver_hashes.values())
        and all(len(values) == 1 and next(iter(values)) for values in effect_hashes.values())
        and all(len(values) == 1 and next(iter(values)) for values in active_hashes.values())
    )
    gates = {"G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5, "G6": g6}
    if all(gates.values()):
        decision = "AUTHORITY_KNOB_SUPPORTED"
    elif g1 and g2 and g5 and not g4:
        decision = "AUTHORITY_KNOB_DEGENERATE"
    else:
        decision = "AUTHORITY_KNOB_NOT_IMPLEMENTABLE"
    return {
        "knob": knob, "gates": gates, "decision": decision,
        "G1_groups": g1_groups, "G2_groups": g2_groups, "G3_groups": g3_groups,
        "G4": {"per_gamma": g4_groups}, "G5": command,
        "G6": {
            "receiver_groups": len(receiver_hashes), "effect_groups": len(effect_hashes),
            "active_reference_groups": len(active_hashes),
        },
        "accepted": False, "pai_job_created": False,
    }
