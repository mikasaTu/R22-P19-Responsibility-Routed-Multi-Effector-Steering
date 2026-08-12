"""Event extraction for the LIBERO grasp-transport-release surrogate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import h5py
import numpy as np

from .config import TaskSpec
from .env import LiberoBranchEnv


EVENT_ORDER = ("P0", "P1", "P2", "P3", "P4", "P5", "P6")


@dataclass(frozen=True)
class EventAudit:
    demo_id: int
    length: int
    events: Dict[str, Optional[int]]
    ordered_complete: bool
    reason: str

    def as_json(self) -> Dict[str, Any]:
        return {
            "demo_id": int(self.demo_id),
            "length": int(self.length),
            "events": self.events,
            "ordered_complete": bool(self.ordered_complete),
            "reason": self.reason,
        }


def _first_sustained(mask: np.ndarray, start: int, count: int = 2) -> Optional[int]:
    begin = max(0, int(start))
    for index in range(begin, max(begin, len(mask) - count + 1)):
        if bool(np.all(mask[index : index + count])):
            return int(index)
    return None


def _first_true(mask: np.ndarray, start: int = 0) -> Optional[int]:
    indices = np.flatnonzero(mask[max(0, int(start)) :])
    if not len(indices):
        return None
    return int(max(0, int(start)) + indices[0])


def _event_chain_reason(events: Mapping[str, Optional[int]]) -> Tuple[bool, str]:
    missing = [name for name in EVENT_ORDER[1:] if events.get(name) is None]
    if missing:
        return False, "missing:" + ",".join(missing)
    values = [int(events[name]) for name in EVENT_ORDER[1:] if events[name] is not None]
    if values != sorted(values):
        return False, "event_order_violation"
    return True, "ordered_complete"


def detect_primary_events(rows: Sequence[Dict[str, Any]], actions: np.ndarray, rewards: np.ndarray) -> EventAudit:
    if not rows:
        raise ValueError("empty expert trace")
    demo_id = int(rows[0]["demo_id"])
    object_positions = np.asarray([row["object"]["position"] for row in rows], dtype=np.float64)
    contacts = np.asarray([row["contact"]["object_gripper"] for row in rows], dtype=bool)
    two_finger = np.asarray([row["contact"]["object_two_finger"] for row in rows], dtype=bool)
    target_contacts = np.asarray([row["contact"]["object_target"] for row in rows], dtype=bool)
    initial_position = object_positions[0]
    lifted = object_positions[:, 2] > initial_position[2] + 0.008
    p1 = _first_sustained(contacts, 0, 2)
    stable_mask = contacts & lifted
    preferred = two_finger & lifted
    p2 = _first_sustained(preferred, (p1 or 0), 2)
    if p2 is None:
        p2 = _first_sustained(stable_mask, (p1 or 0), 3)
    p3: Optional[int] = None
    if p2 is not None:
        planar = np.linalg.norm(object_positions[:, :2] - object_positions[p2, :2], axis=1)
        p3 = _first_true(planar > 0.025, p2)
    p4: Optional[int] = None
    if p3 is not None:
        # Panda action +1 closes and -1 opens in this LIBERO / robosuite version.
        opening = np.asarray(actions[:, 6] < 0.0, dtype=bool)
        p4 = _first_sustained(opening, p3, 2)
    p5: Optional[int] = None
    if p4 is not None:
        p5 = _first_sustained(~contacts, p4, 2)
    success_mask = np.asarray(rewards > 0, dtype=bool)
    support_mask = target_contacts | success_mask[: len(target_contacts)]
    # The bowl normally touches the plate before the fingers fully lose
    # contact. P6 means that support is still present after actual release.
    p6 = _first_true(support_mask, p5 if p5 is not None else (p4 or 0))
    p0 = max(0, (p1 or 1) - 5)
    events: Dict[str, Optional[int]] = {
        "P0": int(p0),
        "P1": p1,
        "P2": p2,
        "P3": p3,
        "P4": p4,
        "P5": p5,
        "P6": p6,
    }
    complete, reason = _event_chain_reason(events)
    return EventAudit(demo_id=demo_id, length=len(rows), events=events, ordered_complete=complete, reason=reason)


def scan_demo_trace(
    env: LiberoBranchEnv,
    task: TaskSpec,
    demo_id: int,
) -> Tuple[List[Dict[str, Any]], np.ndarray, np.ndarray, np.ndarray]:
    with h5py.File(str(task.dataset_path), "r") as handle:
        group = handle["data/demo_%d" % int(demo_id)]
        states = np.asarray(group["states"], dtype=np.float64)
        actions = np.asarray(group["actions"], dtype=np.float64)
        rewards = np.asarray(group["rewards"], dtype=np.uint8)
    if not (len(states) == len(actions) == len(rewards)):
        raise RuntimeError("demonstration arrays have inconsistent lengths")
    rows: List[Dict[str, Any]] = []
    for index, state in enumerate(states):
        env.set_state(state, int(demo_id))
        snapshot = env.snapshot()
        rows.append(
            {
                "task_role": task.role,
                "task": task.name,
                "demo_id": int(demo_id),
                "step_id": int(index),
                "simulator_state": [float(item) for item in state],
                "action": [float(item) for item in actions[index]],
                "reward": int(rewards[index]),
                "model_file_sha256": env.demo_model_sha256(demo_id),
                "object": snapshot["object"],
                "eef": snapshot["eef"],
                "contact": snapshot["contact"],
                "target_distance": float(snapshot["target_distance"]),
                "success": bool(snapshot["success"]),
            }
        )
    return rows, states, actions, rewards


def assign_primary_phase(index: int, events: Mapping[str, Optional[int]]) -> str:
    p1 = events.get("P1")
    p2 = events.get("P2")
    p4 = events.get("P4")
    p5 = events.get("P5")
    if p1 is None or index < p1:
        return "approach"
    if p2 is None or index < p2:
        return "grasp_close"
    if p4 is None or index < p4:
        return "transport"
    if p5 is None or index < p5:
        return "release"
    return "post_release"


def primary_branch_indices(audit: EventAudit, stride: int, horizon: int) -> List[int]:
    if not audit.ordered_complete:
        return []
    start = int(audit.events["P1"] or 0)
    stop = int(audit.events["P5"] or (audit.length - 1))
    maximum = audit.length - int(horizon)
    indices = set(range(start, min(stop, maximum) + 1, int(stride)))
    for name in ("P1", "P2", "P3", "P4", "P5"):
        value = audit.events.get(name)
        if value is not None and int(value) <= maximum:
            indices.add(int(value))
    return sorted(index for index in indices if 0 <= index <= maximum)


def control_branch_indices(length: int, stride: int, horizon: int) -> List[int]:
    maximum = int(length) - int(horizon)
    if maximum < 0:
        return []
    start = max(1, int(round(0.15 * maximum)))
    stop = max(start, int(round(0.85 * maximum)))
    return list(range(start, stop + 1, max(1, int(stride) * 2)))


def manual_audit_rows(
    traces: Mapping[int, Sequence[Dict[str, Any]]],
    audits: Mapping[int, EventAudit],
    count: int,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for demo_id in sorted(audits)[: int(count)]:
        audit = audits[demo_id]
        trace = traces[demo_id]
        event_rows: Dict[str, Any] = {}
        for name in EVENT_ORDER:
            index = audit.events.get(name)
            if index is None:
                event_rows[name] = None
                continue
            row = trace[int(index)]
            event_rows[name] = {
                "step_id": int(index),
                "object_position": row["object"]["position"],
                "eef_position": row["eef"]["position"],
                "gripper_qpos": row["eef"]["gripper_qpos"],
                "gripper_action": float(row["action"][6]),
                "object_gripper_contact": bool(row["contact"]["object_gripper"]),
                "object_two_finger_contact": bool(row["contact"]["object_two_finger"]),
                "object_target_contact": bool(row["contact"]["object_target"]),
                "reward": int(row["reward"]),
            }
        rows.append(
            {
                "demo_id": int(demo_id),
                "ordered_complete": bool(audit.ordered_complete),
                "reason": audit.reason,
                "events": event_rows,
                "review_mode": "agent_numeric_trace_manual_check",
            }
        )
    return rows
