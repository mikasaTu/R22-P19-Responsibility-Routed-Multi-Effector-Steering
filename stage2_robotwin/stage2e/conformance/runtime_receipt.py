from __future__ import annotations

from dataclasses import asdict, dataclass, field
from time import perf_counter
from typing import List

from .method_registry import MethodSpec


@dataclass
class RuntimeReceipt:
    method: MethodSpec
    solver_call_count: int = 0
    solver_latency_s: float = 0.0
    action_modification_count: int = 0
    events: List[str] = field(default_factory=list)

    def record_action_modification(self, event: str) -> None:
        self.action_modification_count += 1
        self.events.append(event)

    def record_solver(self, latency_s: float) -> None:
        self.solver_call_count += 1
        self.solver_latency_s += float(latency_s)

    def validate(self) -> dict:
        calls_match = self.solver_call_count == self.method.expected_solver_calls
        modifies_match = bool(self.action_modification_count) == self.method.modifies_action
        return {
            "method": self.method.as_dict(),
            "solver_call_count": self.solver_call_count,
            "solver_latency_s": self.solver_latency_s,
            "action_modification_count": self.action_modification_count,
            "events": list(self.events),
            "checks": {
                "solver_call_count_matches": calls_match,
                "modifies_action_matches": modifies_match,
                "method_name_matches_code_path": self.method.name.startswith("W"),
            },
            "valid": calls_match and modifies_match,
        }
