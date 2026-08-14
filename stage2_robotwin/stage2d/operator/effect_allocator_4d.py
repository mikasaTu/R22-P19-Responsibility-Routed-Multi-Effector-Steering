from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from scipy.optimize import minimize


@dataclass(frozen=True)
class Allocation4D:
    action: np.ndarray
    net_effect: np.ndarray
    receiver_effect: np.ndarray
    feasible: bool
    latency_s: float


def allocate_4d(g_left, g_right, base_action, desired_effect, receiver_share,
                action_limit=2.0, slew_limit=1.0, internal_weight=0.0) -> Allocation4D:
    import time
    started = time.perf_counter()
    gl, gr = np.asarray(g_left), np.asarray(g_right)
    base, desired = np.asarray(base_action), np.asarray(desired_effect)

    def loss(u):
        left, right = gl @ u[:gl.shape[1]], gr @ u[gl.shape[1]:]
        net = left + right
        axis = desired / max(np.linalg.norm(desired), 1e-12)
        diff = left - right
        internal = diff - axis * float(axis @ diff)
        return (80 * np.sum((net - desired) ** 2)
                + 18 * np.sum((right - receiver_share * desired) ** 2)
                + internal_weight * np.sum(internal**2)
                + 0.08 * np.sum((u - base) ** 2))

    lo, hi = np.maximum(-action_limit, base - slew_limit), np.minimum(action_limit, base + slew_limit)
    result = minimize(loss, base, method="SLSQP", bounds=list(zip(lo, hi)),
                      options={"maxiter": 300, "ftol": 1e-10})
    split = gl.shape[1]
    left, right = gl @ result.x[:split], gr @ result.x[split:]
    relative_error = np.linalg.norm(left + right - desired) / max(np.linalg.norm(desired), 1e-12)
    return Allocation4D(np.asarray(result.x), left + right, right,
                        bool(result.success and relative_error <= 0.10), time.perf_counter() - started)

