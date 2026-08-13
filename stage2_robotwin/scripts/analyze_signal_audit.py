"""Summarize oracle branches and paired authority swaps without overclaiming."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


PAIR_CONTRACT = (
    ("gain", "gain_left_high", "gain_right_high", 1.0),
    ("delay_2", "delay_left_2", "delay_right_2", -1.0),
    ("delay_4", "delay_left_4", "delay_right_4", -1.0),
    ("friction", "friction_left_high", "friction_right_high", 1.0),
    ("compliance", "compliance_left_low", "compliance_right_low", -1.0),
    (
        "direction_null",
        "direction_left_authority",
        "direction_right_authority",
        1.0,
    ),
    (
        "direction_compliance_diagnostic",
        "direction_compliance_left_authority",
        "direction_compliance_right_authority",
        1.0,
    ),
)

DIRECTION_PROFILE_PAIRS = (
    (
        "direction_null",
        "direction_left_authority",
        "direction_right_authority",
    ),
    (
        "direction_compliance_diagnostic",
        "direction_compliance_left_authority",
        "direction_compliance_right_authority",
    ),
)


def load_jsonl(paths: Iterable[Path]) -> List[Dict[str, Any]]:
    values = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                values.append(json.loads(line))
    return values


def phase_name(event_names: Iterable[str]) -> str:
    events = set(event_names)
    if "E4" in events:
        return "donor_release"
    if "E3" in events:
        return "stable_overlap"
    return "early_overlap"


def left_minus_right(record: Mapping[str, Any]) -> float:
    channel = record["responsibility"]["three_channel"]
    return float(channel["rho_left"] - channel["rho_right"])


def paired_authority_metrics(records: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    indexed: Dict[Tuple[int, int], Dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for record in records:
        indexed[(int(record["step"]), int(record["horizon"]))][
            record["profile"]["name"]
        ] = record

    results: Dict[str, Any] = {}
    all_oriented_margins = []
    tie_tolerance = 1e-9
    for family, left_name, right_name, orientation in PAIR_CONTRACT:
        margins = []
        for profiles in indexed.values():
            if left_name not in profiles or right_name not in profiles:
                continue
            raw = left_minus_right(profiles[left_name]) - left_minus_right(
                profiles[right_name]
            )
            margins.append(orientation * raw)
        all_oriented_margins.extend(margins)
        margin_array = np.asarray(margins, dtype=np.float64)
        informative = np.abs(margin_array) > tie_tolerance
        results[family] = {
            "paired_state_count": len(margins),
            "informative_state_count": int(informative.sum()),
            "tie_count": int((~informative).sum()),
            "accuracy": (
                float(np.mean(np.where(informative, margin_array > 0, 0.5)))
                if margins
                else None
            ),
            "accuracy_informative_only": (
                float(np.mean(margin_array[informative] > 0))
                if informative.any()
                else None
            ),
            "median_oriented_margin": float(np.median(margins)) if margins else None,
            "mean_oriented_margin": float(np.mean(margins)) if margins else None,
        }
    if all_oriented_margins:
        margin_array = np.asarray(all_oriented_margins, dtype=np.float64)
        informative = np.abs(margin_array) > tie_tolerance
        rng = np.random.default_rng(22019)
        random_orientations = rng.choice(
            [-1.0, 1.0], (4096, len(all_oriented_margins))
        )
        shuffled = margin_array[None, :] * random_orientations
        aggregate_accuracy = float(
            np.mean(np.where(informative, margin_array > 0, 0.5))
        )
        informative_accuracy = (
            float(np.mean(margin_array[informative] > 0))
            if informative.any()
            else None
        )
        shuffled_accuracy = float(
            np.mean(
                np.where(
                    informative[None, :],
                    shuffled > 0,
                    0.5,
                )
            )
        )
    else:
        informative = np.asarray([], dtype=bool)
        aggregate_accuracy = informative_accuracy = shuffled_accuracy = None
    results["aggregate"] = {
        "paired_state_count": len(all_oriented_margins),
        "informative_state_count": int(informative.sum()),
        "tie_count": int((~informative).sum()),
        "accuracy": aggregate_accuracy,
        "accuracy_informative_only": informative_accuracy,
        "shuffled_orientation_accuracy": shuffled_accuracy,
        "shuffle_seed": 22019,
        "shuffle_repetitions": 4096,
        "tie_tolerance": tie_tolerance,
    }
    return results


def reconstruction_audit(records: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    errors = []
    for record in records:
        responsibility = record["responsibility"]
        for channel in (
            "motion",
            "support",
            "task_progress",
            "contact_retention",
            "negative_slip",
        ):
            errors.append(float(responsibility[channel]["reconstruction_error"]))
    return {
        "value_count": len(errors),
        "max_abs_error": max(errors, default=None),
        "all_at_or_below_1e-12": bool(errors) and max(errors) <= 1e-12,
    }


def base_phase_curve(records: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    grouped: Dict[Tuple[str, int], List[Tuple[float, float, float]]] = defaultdict(list)
    for record in records:
        if record["profile"]["name"] != "base":
            continue
        channel = record["responsibility"]["three_channel"]
        grouped[(phase_name(record["event_names_observed"]), int(record["horizon"]))].append(
            (
                float(channel["rho_left"]),
                float(channel["rho_right"]),
                float(channel["rho_joint"]),
            )
        )
    result = {}
    for (phase, horizon), values in grouped.items():
        array = np.asarray(values)
        result[f"{phase}_H{horizon}"] = {
            "count": len(values),
            "nonzero_responsibility_count_at_1e-12": int(
                np.sum(np.max(np.abs(array), axis=1) > 1e-12)
            ),
            "rho_left_mean": float(array[:, 0].mean()),
            "rho_right_mean": float(array[:, 1].mean()),
            "rho_joint_mean": float(array[:, 2].mean()),
            "rho_joint_abs_median": float(np.median(np.abs(array[:, 2]))),
        }
    return result


def channel_effect_audit(records: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    """Report which outcome channels are numerically informative per horizon."""

    grouped: Dict[Tuple[str, int], List[Tuple[float, float]]] = defaultdict(list)
    for record in records:
        if record["profile"]["name"] != "base":
            continue
        responsibility = record["responsibility"]
        horizon = int(record["horizon"])
        for channel in (
            "motion",
            "support",
            "task_progress",
            "contact_retention",
            "negative_slip",
        ):
            value = responsibility[channel]
            total = _vector_norm_sum(value["phi_left"], value["phi_right"])
            synergy = float(np.linalg.norm(np.asarray(value["synergy"], dtype=np.float64)))
            grouped[(channel, horizon)].append((total, synergy))
    result: Dict[str, Any] = {}
    for (channel, horizon), values in grouped.items():
        array = np.asarray(values, dtype=np.float64)
        result[f"{channel}_H{horizon}"] = {
            "count": len(values),
            "nonzero_effect_count_at_1e-12": int(np.sum(array[:, 0] > 1e-12)),
            "total_effect_norm_median": float(np.median(array[:, 0])),
            "total_effect_norm_max": float(np.max(array[:, 0])),
            "synergy_norm_median": float(np.median(array[:, 1])),
            "synergy_norm_max": float(np.max(array[:, 1])),
        }
    return result


def _vector_norm_sum(left: Any, right: Any) -> float:
    return float(
        np.linalg.norm(
            np.asarray(left, dtype=np.float64)
            + np.asarray(right, dtype=np.float64)
        )
    )


def authority_swap_by_horizon(
    records: Iterable[Mapping[str, Any]],
) -> Dict[str, Any]:
    values = list(records)
    return {
        f"H{horizon}": paired_authority_metrics(
            record for record in values if int(record["horizon"]) == horizon
        )
        for horizon in sorted({int(record["horizon"]) for record in values})
    }


def direction_intervention_validity(
    records: Iterable[Mapping[str, Any]], tolerance_m: float = 1e-6
) -> Dict[str, Any]:
    """Check that nominal direction/null profiles really swap object authority.

    A Jacobian-aligned TCP command is not automatically an object-driving
    command under contact.  We therefore validate the intervention with an
    independent fixed task-direction projection before interpreting oracle
    responsibility.  Both sides of a paired swap must have a positive,
    dominant singleton object effect.
    """

    indexed: Dict[Tuple[int, int], Dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for record in records:
        name = record["profile"]["name"]
        if name.startswith("direction_"):
            indexed[(int(record["step"]), int(record["horizon"]))][name] = record

    details = []
    valid_pairs = 0
    profile_valid_count = 0
    by_family: Dict[str, Dict[str, Any]] = {}
    for family, left_name, right_name in DIRECTION_PROFILE_PAIRS:
        family_pair_count = family_valid_count = family_profile_valid = 0
        valid_pair_oracle_margins = []
        for (step, horizon), profiles in sorted(indexed.items()):
            names = (left_name, right_name)
            if any(name not in profiles for name in names):
                continue
            family_pair_count += 1
            pair_valid = True
            profile_details = []
            for name, expected in zip(names, ("left", "right")):
                record = profiles[name]
                direction = np.asarray(
                    record["direction_validation"]["motion_direction_world"],
                    dtype=np.float64,
                )
                zero = np.asarray(record["outcomes"]["ZERO"]["translation"])
                effects = {
                    "left": float(
                        (np.asarray(record["outcomes"]["L"]["translation"]) - zero)
                        @ direction
                    ),
                    "right": float(
                        (np.asarray(record["outcomes"]["R"]["translation"]) - zero)
                        @ direction
                    ),
                }
                other = "right" if expected == "left" else "left"
                valid = (
                    effects[expected] > tolerance_m
                    and effects[expected] > effects[other] + tolerance_m
                )
                profile_valid_count += int(valid)
                family_profile_valid += int(valid)
                pair_valid &= valid
                profile_details.append(
                    {
                        "profile": name,
                        "expected_authority": expected,
                        "singleton_task_direction_effect_m": effects,
                        "valid": bool(valid),
                    }
                )
            valid_pairs += int(pair_valid)
            family_valid_count += int(pair_valid)
            oracle_margin = left_minus_right(profiles[left_name]) - left_minus_right(
                profiles[right_name]
            )
            if pair_valid:
                valid_pair_oracle_margins.append(oracle_margin)
            details.append(
                {
                    "family": family,
                    "step": step,
                    "horizon": horizon,
                    "pair_valid": bool(pair_valid),
                    "oracle_oriented_margin": oracle_margin,
                    "profiles": profile_details,
                }
            )
        margin_array = np.asarray(valid_pair_oracle_margins, dtype=np.float64)
        informative = np.abs(margin_array) > 1e-9
        by_family[family] = {
            "paired_state_count": family_pair_count,
            "valid_paired_state_count": family_valid_count,
            "profile_count": 2 * family_pair_count,
            "valid_profile_count": family_profile_valid,
            "valid_pair_oracle_informative_count": int(informative.sum()),
            "valid_pair_oracle_accuracy": (
                float(np.mean(np.where(informative, margin_array > 0, 0.5)))
                if len(margin_array)
                else None
            ),
            "valid_pair_oracle_accuracy_informative_only": (
                float(np.mean(margin_array[informative] > 0))
                if informative.any()
                else None
            ),
        }
    return {
        "paired_state_count": len(details),
        "valid_paired_state_count": valid_pairs,
        "profile_count": 2 * len(details),
        "valid_profile_count": profile_valid_count,
        "positive_dominance_tolerance_m": tolerance_m,
        "oracle_direction_accuracy_interpretable": valid_pairs > 0,
        "by_family": by_family,
        "details": details,
    }


def plot_records(records: List[Mapping[str, Any]], output: Path) -> None:
    base = [record for record in records if record["profile"]["name"] == "base"]
    if not base:
        return
    has_direction = any(
        record["profile"]["name"].startswith("direction_") for record in records
    )
    row_count = 3 if has_direction else 2
    figure, axes = plt.subplots(row_count, 1, figsize=(11, 4 * row_count), sharex=True)
    for horizon in sorted({int(record["horizon"]) for record in base}):
        selected = sorted(
            (record for record in base if int(record["horizon"]) == horizon),
            key=lambda value: int(value["step"]),
        )
        steps = [record["step"] for record in selected]
        axes[0].plot(
            steps,
            [record["responsibility"]["three_channel"]["rho_left"] for record in selected],
            label=f"left H={horizon}",
        )
        axes[0].plot(
            steps,
            [record["responsibility"]["three_channel"]["rho_right"] for record in selected],
            label=f"right H={horizon}",
        )
        axes[1].plot(
            steps,
            [record["responsibility"]["three_channel"]["rho_joint"] for record in selected],
            label=f"joint H={horizon}",
        )
    if has_direction:
        indexed: Dict[Tuple[int, int], Dict[str, Mapping[str, Any]]] = defaultdict(dict)
        for record in records:
            indexed[(int(record["step"]), int(record["horizon"]))][
                record["profile"]["name"]
            ] = record
        for family, left_name, right_name in DIRECTION_PROFILE_PAIRS:
            for horizon in sorted({int(record["horizon"]) for record in records}):
                points = []
                for (step, value_horizon), profiles in indexed.items():
                    if value_horizon != horizon:
                        continue
                    if left_name not in profiles or right_name not in profiles:
                        continue
                    margin = left_minus_right(profiles[left_name]) - left_minus_right(
                        profiles[right_name]
                    )
                    points.append((step, margin))
                if points:
                    points.sort()
                    axes[2].plot(
                        [value[0] for value in points],
                        [value[1] for value in points],
                        marker="o",
                        markersize=2.5,
                        label=f"{family} H={horizon}",
                    )
    axes[0].set_ylabel("motion projection")
    axes[1].set_ylabel("joint synergy projection")
    if has_direction:
        axes[2].set_ylabel("paired L-R margin")
    axes[-1].set_xlabel("expert physics step")
    for axis in axes:
        axis.axhline(0, color="black", linewidth=0.8)
        axis.grid(alpha=0.25)
        axis.legend(ncol=2)
    figure.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=170)
    plt.close(figure)


def classify_signal(metrics: Mapping[str, Any]) -> str:
    if int(metrics["successful_episode_count"]) < 30:
        return "PILOT_ONLY_INSUFFICIENT_N"
    aggregate = metrics["authority_swap"]["aggregate"]
    accuracy = aggregate["accuracy"]
    paired = aggregate["informative_state_count"]
    if paired < 20 or accuracy is None:
        return "PILOT_ONLY_INSUFFICIENT_N"
    joint_values = [
        value["rho_joint_abs_median"] for value in metrics["phase_curve"].values()
    ]
    joint_median = float(np.median(joint_values)) if joint_values else float("inf")
    if accuracy >= 0.8 and joint_median < 0.5:
        return "SIGNAL_STRONG"
    if accuracy >= 0.65:
        return "SIGNAL_PARTIAL"
    if accuracy >= 0.5 and joint_median >= 0.5:
        return "SIGNAL_NEEDS_THREE_WAY"
    return "SIGNAL_WEAK"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+")
    parser.add_argument("--output", required=True)
    parser.add_argument("--plot", required=True)
    parser.add_argument("--successful-episodes", type=int, required=True)
    args = parser.parse_args()
    records = load_jsonl(Path(value) for value in args.inputs)
    direction_records = [
        value
        for value in records
        if value["profile"]["name"].startswith("direction_")
    ]
    direction_validity = direction_intervention_validity(records)
    base_direction_valid = direction_validity["by_family"].get(
        "direction_null", {}
    ).get("valid_paired_state_count", 0)
    diagnostic_direction_valid = direction_validity["by_family"].get(
        "direction_compliance_diagnostic", {}
    ).get("valid_paired_state_count", 0)
    metrics = {
        "accepted": False,
        "evidence_boundary": "simulator privileged oracle; not deployable",
        "record_count": len(records),
        "successful_episode_count": args.successful_episodes,
        "branch_state_count": len({int(value["step"]) for value in records}),
        "reconstruction": reconstruction_audit(records),
        "phase_curve": base_phase_curve(records),
        "channel_effect_audit": channel_effect_audit(records),
        "authority_swap": paired_authority_metrics(records),
        "authority_swap_by_horizon": authority_swap_by_horizon(records),
        "direction_null_status": (
            "OBJECT_AUTHORITY_SWAP_VALIDATED"
            if base_direction_valid > 0
            else (
                "DIAGNOSTIC_COMPLIANCE_ASSISTED_SWAP_VALIDATED"
                if diagnostic_direction_valid > 0
                else (
                    "JACOBIAN_COMMAND_VALID_BUT_OBJECT_AUTHORITY_SWAP_INVALID"
                    if direction_records
                    else "not implemented in this pilot"
                )
            )
        ),
        "direction_null_record_count": len(direction_records),
        "direction_intervention_validity": direction_validity,
    }
    metrics["status"] = classify_signal(metrics)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    plot_records(records, Path(args.plot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
