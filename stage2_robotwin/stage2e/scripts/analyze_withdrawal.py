from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from stage2_robotwin.stage2e.withdrawal import CHANNELS, FADE_LEVELS


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _ratio(a: float, b: float) -> float:
    return float(a / b) if abs(b) > 1e-12 else (0.0 if abs(a) <= 1e-12 else float("inf"))


def analyze(records: list[dict]) -> dict:
    groups = defaultdict(list)
    for record in records:
        groups[(record["seed"], record["channel"])].append(record)
    audits = []
    for (seed, channel), rows in sorted(groups.items()):
        by_fade = defaultdict(list)
        for row in rows:
            by_fade[float(row["fade"])].append(row)
        cell_complete = set(by_fade) == set(FADE_LEVELS) and all(
            len(by_fade[fade]) == 2 for fade in FADE_LEVELS
        )
        medians = {fade: {effect: float(np.median([r["donor_effect_integrals"][effect]
                                                   for r in by_fade[fade]]))
                          for effect in CHANNELS}
                   for fade in FADE_LEVELS}
        selected = [medians[fade][channel] for fade in sorted(FADE_LEVELS)]
        tolerance = 0.05 * max(medians[1.0][channel], 1e-12)
        monotone = bool(np.all(np.diff(selected) >= -tolerance))
        fade_ratio = _ratio(medians[0.0][channel], medians[1.0][channel])
        other_ratios = {effect: _ratio(medians[0.0][effect], medians[1.0][effect])
                        for effect in CHANNELS if effect != channel}
        hashes = {r["receiver_command_sha256"] for r in rows}
        duplicate_errors = {}
        for fade in FADE_LEVELS:
            values = [r["donor_effect_integrals"][channel] for r in by_fade[fade]]
            scale = max(max(values, default=0.0), 1e-12)
            duplicate_errors[str(fade)] = float((max(values) - min(values)) / scale)
        duplicate_ok = max(duplicate_errors.values(), default=float("inf")) <= 0.05
        retention_contact_ratio = None
        retention_contact_ok = True
        if channel == "retention":
            c0 = float(np.median([r["donor_contact_fraction"] for r in by_fade[0.0]]))
            c1 = float(np.median([r["donor_contact_fraction"] for r in by_fade[1.0]]))
            retention_contact_ratio = _ratio(c0, c1)
            retention_contact_ok = retention_contact_ratio <= 0.10 and all(
                not r["donor_final_contact"] for r in by_fade[0.0])
        checks = {
            "all_fades_have_two_fresh_repeats": cell_complete,
            "targeted_effect_monotone": monotone,
            "fade_zero_le_10pct": fade_ratio <= 0.10,
            "nonwithdrawn_channels_ge_80pct": all(value >= 0.80 for value in other_ratios.values()),
            "receiver_command_identical": len(hashes) == 1,
            "duplicate_relative_error_le_5pct": duplicate_ok,
            "retention_zero_contact_valid": retention_contact_ok,
        }
        audits.append({"seed": seed, "channel": channel, "medians": medians,
                       "selected_fade_zero_over_one": fade_ratio,
                       "nonwithdrawn_fade_zero_over_one": other_ratios,
                       "duplicate_relative_errors": duplicate_errors,
                       "retention_contact_ratio": retention_contact_ratio,
                       "checks": checks, "valid": all(checks.values())})
    complete_groups = len(audits) == 3 * len(CHANNELS)
    valid_groups = sum(item["valid"] for item in audits)
    decision = "WITHDRAWAL_GO" if complete_groups and valid_groups == len(audits) else "WITHDRAWAL_NOT_IMPLEMENTABLE"
    return {"schema": "r22p19.stage2e.withdrawal_analysis.v1", "decision": decision,
            "accepted": False, "complete_groups": len(audits), "expected_groups": 12,
            "valid_groups": valid_groups, "audits": audits, "pai_job_created": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = [json.loads(path.read_text()) for path in sorted((args.input / "branches").glob("*.json"))]
    result = analyze(records)
    write_json(args.output, result)
    print(result["decision"], result["valid_groups"], "/", result["expected_groups"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
