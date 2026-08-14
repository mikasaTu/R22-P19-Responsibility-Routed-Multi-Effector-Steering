from __future__ import annotations

from typing import Any, Mapping, Sequence
import numpy as np

from stage2_robotwin.responsibility.oracle_brancher import capture_outcome_origin, measure_outcome
from stage2_robotwin.wrappers.counterfactual_brancher import SapienSnapshot
from stage2_robotwin.responsibility.oracle_brancher import _joint_neutral_state


FADE_LEVELS = (1.0, 0.75, 0.5, 0.25, 0.0)


def donor_fade_rollouts(task: Any, snapshot: Mapping, future: Sequence[Mapping],
                        donor: str, fade_levels=FADE_LEVELS,
                        receiver_gain: float = 1.0, receiver_delay: int = 0) -> dict:
    """Roll out the same state/future tape while continuously fading donor arm authority.

    Gripper commands are deliberately held to isolate arm takeover capacity from release.
    """
    receiver = "right" if donor == "left" else "left"
    origin = None
    outcomes = {}
    for fade in fade_levels:
        SapienSnapshot.restore(task, snapshot)
        if origin is None:
            origin = capture_outcome_origin(task)
        neutral = {side: _joint_neutral_state(task, side) for side in ("left", "right")}
        for future_index, item in enumerate(future):
            for side in ("left", "right"):
                source_index = max(0, future_index - receiver_delay) if side == receiver else future_index
                source = future[source_index]
                pos = np.asarray(source[f"{side}_position"], dtype=float)
                vel = np.asarray(source[f"{side}_velocity"], dtype=float)
                if side == donor:
                    pos = neutral[side][0] + float(fade) * (pos - neutral[side][0])
                    vel = float(fade) * vel
                elif side == receiver and receiver_gain != 1.0:
                    pos = neutral[side][0] + receiver_gain * (pos - neutral[side][0])
                    vel = receiver_gain * vel
                task.robot.set_arm_joints(pos, vel, side)
            task.scene.step()
        outcomes[str(fade)] = measure_outcome(task, origin)
    SapienSnapshot.restore(task, snapshot)
    return {"donor": donor, "receiver": receiver, "fade_levels": list(fade_levels),
            "receiver_gain": receiver_gain, "receiver_delay": receiver_delay,
            "grippers_held": True, "outcomes": outcomes}

