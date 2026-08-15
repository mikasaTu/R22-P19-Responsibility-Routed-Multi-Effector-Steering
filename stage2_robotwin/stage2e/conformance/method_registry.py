from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict


@dataclass(frozen=True)
class MethodSpec:
    name: str
    uses_capacity: bool
    uses_desired_target: bool
    uses_allocator: bool
    lambda_target: float
    lambda_internal: float
    uses_release_guard: bool
    uses_v1_path: bool
    modifies_action: bool
    expected_solver_calls: int
    code_path: str

    def as_dict(self) -> dict:
        return asdict(self)


METHODS: Dict[str, MethodSpec] = {
    "W0_BASE": MethodSpec("W0_BASE", False, False, False, 0.0, 0.0, False,
                          False, False, 0, "base_expert_replay"),
    "W1_OPERATOR_NULL": MethodSpec("W1_OPERATOR_NULL", False, False, False,
                                   0.0, 0.0, False, False, False, 0,
                                   "equal_budget_no_action_change"),
    "W2_MOTION_WITHDRAWAL": MethodSpec("W2_MOTION_WITHDRAWAL", False, False,
                                        False, 0.0, 0.0, False, False, True, 0,
                                        "withdrawal.motion_withdrawal"),
    "W3_SUPPORT_WITHDRAWAL": MethodSpec("W3_SUPPORT_WITHDRAWAL", False, False,
                                         False, 0.0, 0.0, False, False, True, 0,
                                         "withdrawal.support_withdrawal"),
    "W4_ROTATION_WITHDRAWAL": MethodSpec("W4_ROTATION_WITHDRAWAL", False, False,
                                          False, 0.0, 0.0, False, False, True, 0,
                                          "withdrawal.rotation_withdrawal"),
    "W5_RETENTION_WITHDRAWAL": MethodSpec("W5_RETENTION_WITHDRAWAL", False,
                                           False, False, 0.0, 0.0, False, False,
                                           True, 0,
                                           "withdrawal.retention_withdrawal"),
}


def get_method(name: str) -> MethodSpec:
    try:
        return METHODS[name]
    except KeyError as exc:
        raise ValueError(f"unknown Stage2E method {name}") from exc
