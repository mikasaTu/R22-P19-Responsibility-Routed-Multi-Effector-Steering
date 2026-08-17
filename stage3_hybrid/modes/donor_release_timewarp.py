from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

import numpy as np

from stage3_hybrid.modes.candidate_library import MODE_BY_NAME, Mode


def donor_source_step(step: int, e4: int, mode: Mode, tape_steps: int) -> int:
    if mode.kind == "base": source = step
    elif mode.kind == "early": source = step + mode.offset if step >= e4 - mode.offset else step
    elif mode.kind == "delay":
        source = step if step < e4 else (e4 - 1 if step < e4 + mode.offset else step - mode.offset)
    elif mode.kind == "abort_hold": source = step if step < e4 else e4 - 1
    else: raise ValueError(f"unknown mode kind {mode.kind}")
    return int(np.clip(source, 0, tape_steps - 1))


def compose_item(tape: Any, step: int, donor: str, mode_name: str, e4: int) -> tuple[dict, int]:
    mode = MODE_BY_NAME[mode_name]; item = tape.item(step)
    source = donor_source_step(step, e4, mode, len(tape)); donor_item = tape.item(source)
    for suffix in ("position", "velocity", "gripper"):
        item[f"{donor}_{suffix}"] = donor_item[f"{donor}_{suffix}"]
    return item, source


def command_hash(items: list[Mapping[str, Any]], side: str) -> str:
    rows = [{"position": np.asarray(item[f"{side}_position"]).round(12).tolist(),
             "velocity": np.asarray(item[f"{side}_velocity"]).round(12).tolist(),
             "gripper": item[f"{side}_gripper"]} for item in items]
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

