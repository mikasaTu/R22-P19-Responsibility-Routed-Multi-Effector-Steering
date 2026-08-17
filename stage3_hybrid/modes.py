from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np


@dataclass(frozen=True)
class Mode:
    name: str
    kind: str
    offset: int = 0


MODES = (
    Mode("M0_BASE", "base"),
    Mode("M1_EARLY_100", "early", 100),
    Mode("M2_EARLY_50", "early", 50),
    Mode("M3_DELAY_50", "delay", 50),
    Mode("M4_DELAY_100", "delay", 100),
    Mode("M5_ABORT_HOLD", "abort_hold"),
)
MODE_BY_NAME = {mode.name: mode for mode in MODES}


def donor_source_step(step: int, e4: int, mode: Mode, tape_steps: int) -> int:
    if mode.kind == "base":
        source = step
    elif mode.kind == "early":
        activation = e4 - mode.offset
        source = step + mode.offset if step >= activation else step
    elif mode.kind == "delay":
        if step < e4:
            source = step
        elif step < e4 + mode.offset:
            source = e4 - 1
        else:
            source = step - mode.offset
    elif mode.kind == "abort_hold":
        source = step if step < e4 else e4 - 1
    else:
        raise ValueError(f"unknown mode kind {mode.kind}")
    return int(np.clip(source, 0, tape_steps - 1))


def compose_item(tape: Any, step: int, donor: str, mode_name: str, e4: int) -> tuple[dict, int]:
    mode = MODE_BY_NAME[mode_name]
    item = tape.item(step)
    source = donor_source_step(step, e4, mode, len(tape))
    donor_item = tape.item(source)
    # Paired time warp: arm position, velocity and gripper always share one source.
    for suffix in ("position", "velocity", "gripper"):
        item[f"{donor}_{suffix}"] = donor_item[f"{donor}_{suffix}"]
    return item, source


def command_hash(items: list[Mapping[str, Any]], side: str) -> str:
    rows = []
    for item in items:
        rows.append({
            "position": np.asarray(item[f"{side}_position"]).round(12).tolist(),
            "velocity": np.asarray(item[f"{side}_velocity"]).round(12).tolist(),
            "gripper": item[f"{side}_gripper"],
        })
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()

