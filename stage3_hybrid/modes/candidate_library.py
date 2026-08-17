from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Mode:
    name: str
    kind: str
    offset: int = 0


MODES = (
    Mode("M0_BASE", "base"), Mode("M1_EARLY_100", "early", 100),
    Mode("M2_EARLY_50", "early", 50), Mode("M3_DELAY_50", "delay", 50),
    Mode("M4_DELAY_100", "delay", 100), Mode("M5_ABORT_HOLD", "abort_hold"),
)
MODE_BY_NAME = {mode.name: mode for mode in MODES}

