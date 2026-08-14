from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from scipy.optimize import minimize

from .system import AnalyticCase, contributions, internal_force_proxy


@dataclass(frozen=True)
class OperatorResult:
    action: np.ndarray
    success: bool
    solver_message: str


def allocate(case: AnalyticCase, target: float, *, lambda_target: float = 18.0,
             lambda_internal: float = 0.0, lambda_action: float = 0.08) -> OperatorResult:
    gl, gr, e = case.g_left, case.g_right, case.e_star
    base = case.u_base

    def objective(u: np.ndarray) -> float:
        left, right = gl @ u[:4], gr @ u[4:]
        net = left + right
        internal = internal_force_proxy(case, u)
        return float(
            80.0 * np.sum((net - e) ** 2)
            + lambda_target * np.sum((right - target * e) ** 2)
            + lambda_internal * internal**2
            + lambda_action * np.sum((u - base) ** 2)
        )

    lo = np.maximum(-case.action_limit, base - case.slew_limit)
    hi = np.minimum(case.action_limit, base + case.slew_limit)
    constraints = [
        {"type": "ineq", "fun": lambda u: 0.05 - np.linalg.norm(
            gl @ u[:4] + gr @ u[4:] - e) / max(np.linalg.norm(e), 1e-12)},
        {"type": "ineq", "fun": lambda u: (gl @ u[:4] + gr @ u[4:])[2] - 0.95 * e[2]},
    ]
    result = minimize(objective, base.copy(), method="SLSQP", bounds=list(zip(lo, hi)),
                      constraints=constraints, options={"maxiter": 300, "ftol": 1e-10})
    return OperatorResult(np.asarray(result.x), bool(result.success), str(result.message))

