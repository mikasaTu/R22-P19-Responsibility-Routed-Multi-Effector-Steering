"""Fresh-prefix exact-null replay-floor analysis."""

from __future__ import annotations

import itertools
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence

import numpy as np


DEFAULT_METRICS = (
    "peak_object_angular_velocity",
    "peak_object_linear_jerk",
    "peak_relative_slip_m",
    "min_object_height_m",
    "final_object_displacement_m",
    "donor_residual_influence_impulse_sum",
)


def _metric(result: Mapping[str, Any], name: str) -> float | None:
    """Read a metric, deriving additions from a persisted trace when possible.

    Stage 2C's formal null sweep was intentionally launched before the final
    displacement metric was added to ``ReplayRecorder``.  The full trace is
    nevertheless persisted, so this is an evidence-preserving derivation, not
    an experiment rerun.  Truly unavailable fields are skipped rather than
    making older results unreadable.
    """

    if name in result.get("metrics", {}):
        return float(result["metrics"][name])
    if name != "final_object_displacement_m":
        return None
    trace_path = result.get("trace_path")
    if not trace_path or not Path(trace_path).is_file():
        return None
    with np.load(trace_path) as trace:
        position = np.asarray(trace["object_position"], dtype=np.float64)
    start = int(result.get("reference_events", {}).get("E2", 0))
    if not len(position) or start >= len(position):
        return None
    return float(np.linalg.norm(position[-1] - position[start]))


def _absolute_difference(
    left: Mapping[str, Any], right: Mapping[str, Any], metric: str
) -> float | None:
    left_value = _metric(left, metric)
    right_value = _metric(right, metric)
    if left_value is None or right_value is None:
        return None
    return abs(left_value - right_value)


def _summary(values: Sequence[float]) -> Dict[str, Any]:
    array = np.asarray(values, dtype=np.float64)
    return {
        "count": int(len(array)),
        "median_absolute_pair_difference": float(np.median(array)) if len(array) else None,
        "p95_absolute_pair_difference": float(np.percentile(array, 95)) if len(array) else None,
        "max_absolute_pair_difference": float(array.max()) if len(array) else None,
    }


def analyze_fresh_null_floor(
    results: Iterable[Mapping[str, Any]],
    metrics: Sequence[str] = DEFAULT_METRICS,
) -> Dict[str, Any]:
    groups: Dict[tuple[int, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for result in results:
        groups[(int(result["seed"]), str(result["condition"]), str(result["method"]))].append(result)

    group_reports = {}
    pooled: Dict[str, list[float]] = {name: [] for name in metrics}
    paired_cross_method: Dict[str, list[float]] = {name: [] for name in metrics}
    for key, values in sorted(groups.items()):
        values = sorted(values, key=lambda item: int(item["replicate"]))
        report = {"replicate_count": len(values), "metrics": {}}
        for metric in metrics:
            differences = [
                difference
                for left, right in itertools.combinations(values, 2)
                if (difference := _absolute_difference(left, right, metric))
                is not None
            ]
            pooled[metric].extend(differences)
            report["metrics"][metric] = _summary(differences)
        group_reports[f"seed_{key[0]:04d}__{key[1]}__{key[2]}"] = report

    pair_index: Dict[tuple[int, str, int, str], Mapping[str, Any]] = {}
    for result in itertools.chain.from_iterable(groups.values()):
        pair_index[
            (
                int(result["seed"]),
                str(result["condition"]),
                int(result["replicate"]),
                str(result["method"]),
            )
        ] = result
    for seed, condition, replicate, method in list(pair_index):
        if method != "B0":
            continue
        base = pair_index[(seed, condition, replicate, method)]
        null = pair_index.get((seed, condition, replicate, "OPERATOR_NULL"))
        if null is None:
            continue
        for metric in metrics:
            difference = _absolute_difference(base, null, metric)
            if difference is not None:
                paired_cross_method[metric].append(difference)

    return {
        "groups": group_reports,
        "pooled_within_method": {
            metric: _summary(values) for metric, values in pooled.items()
        },
        "paired_B0_vs_operator_null": {
            metric: _summary(values)
            for metric, values in paired_cross_method.items()
        },
        "effect_gate": {
            metric: 3.0 * float(_summary(values)["p95_absolute_pair_difference"] or 0.0)
            for metric, values in pooled.items()
        },
        "metric_contract": list(metrics),
        "episode_is_inference_unit": True,
        "accepted": False,
    }


def analyze_old_snapshot_floor(
    pilot: Mapping[str, Any],
    metrics: Sequence[str] = DEFAULT_METRICS,
) -> Dict[str, Any]:
    index = {
        (int(item["seed"]), str(item["condition"]), str(item["method"])): item
        for item in pilot["results"]
    }
    values: Dict[str, list[float]] = {metric: [] for metric in metrics}
    pairs = []
    for seed, condition, method in sorted(index):
        if method != "B0" or (seed, condition, "B9") not in index:
            continue
        base = index[(seed, condition, "B0")]
        null = index[(seed, condition, "B9")]
        pairs.append({"seed": seed, "condition": condition})
        for metric in metrics:
            if metric not in base or metric not in null:
                continue
            values[metric].append(abs(float(base[metric]) - float(null[metric])))
    return {
        "paired_cells": pairs,
        "metrics": {metric: _summary(items) for metric, items in values.items()},
        "substrate": "Stage2B same E2 snapshot sequential restore",
        "accepted": False,
    }
