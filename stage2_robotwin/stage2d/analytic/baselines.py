from __future__ import annotations

import numpy as np
from .operator import OperatorResult, allocate
from .system import AnalyticCase


def run_baseline(case: AnalyticCase, method: str) -> tuple[OperatorResult, float]:
    rng = np.random.default_rng(1_000_003 + case.seed)
    if method == "A0":
        return OperatorResult(case.u_base.copy(), True, "base"), case.current_receiver
    if method == "A1":
        return allocate(case, case.current_receiver, lambda_target=0.0), case.current_receiver
    if method == "A2":
        return allocate(case, 0.5), 0.5
    if method == "A3":
        return allocate(case, case.current_receiver), case.current_receiver
    if method == "A4":
        return allocate(case, case.desired_receiver), case.desired_receiver
    if method == "A5":
        target = 1.0 - case.desired_receiver
        return allocate(case, target), target
    if method == "A6":
        target = float(rng.uniform(0.08, 0.92))
        return allocate(case, target), target
    if method == "A7":
        return allocate(case, case.desired_receiver, lambda_internal=5.0), case.desired_receiver
    raise ValueError(f"unknown method {method}")

