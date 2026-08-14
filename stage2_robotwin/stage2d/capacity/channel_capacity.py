from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
import numpy as np


@dataclass(frozen=True)
class CapacityChannels:
    translation: float
    support: float
    rotation: float
    full: float
    capable: bool

    def as_dict(self) -> dict:
        return {"translation": self.translation, "support": self.support,
                "rotation": self.rotation, "full": self.full, "capable": self.capable}


def score_channels(full: Mapping, faded: Mapping, receiver_index: int) -> CapacityChannels:
    eps = 1e-8
    ref_t = np.asarray(full["translation"], dtype=float)
    got_t = np.asarray(faded["translation"], dtype=float)
    translation = float(np.exp(-np.linalg.norm(got_t - ref_t) / max(np.linalg.norm(ref_t), 0.002)))
    ref_r = np.asarray(full["rotation_vector"], dtype=float)
    got_r = np.asarray(faded["rotation_vector"], dtype=float)
    rotation = float(np.exp(-np.linalg.norm(got_r - ref_r) / max(np.linalg.norm(ref_r), 0.02)))
    support_error = abs(float(faded["support_delta"]) - float(full["support_delta"]))
    support = float(np.exp(-support_error / 0.005))
    retained = float(faded["contact_retention"][receiver_index])
    no_drop = float(not faded["drop"])
    progress_ref = max(float(full["task_progress"]), eps)
    progress_ratio = float(np.clip(float(faded["task_progress"]) / progress_ref, 0.0, 1.0))
    combined = float(np.mean([translation, support, rotation, retained, no_drop, progress_ratio]))
    capable = bool(no_drop and retained and combined >= 0.65)
    return CapacityChannels(translation, support, rotation, combined, capable)

