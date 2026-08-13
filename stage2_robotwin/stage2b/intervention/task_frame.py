"""Object-centred orthonormal task frame used by Stage 2B probes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Sequence

import numpy as np


def _unit(value: Sequence[float], fallback: Sequence[float]) -> np.ndarray:
    vector = np.asarray(value, dtype=np.float64)
    norm = float(np.linalg.norm(vector))
    if norm < 1e-9:
        vector = np.asarray(fallback, dtype=np.float64)
        norm = float(np.linalg.norm(vector))
    return vector / norm


@dataclass(frozen=True)
class ObjectTaskFrame:
    """Separate horizontal transport from support and lateral motion.

    RoboTwin's placement target lies both horizontally away from and below the
    object during handover.  Treating the full target vector as one direction
    couples transport to gravity support.  Stage 2B therefore projects the
    target displacement onto the horizontal plane for ``e_parallel`` and keeps
    world-up as an independent ``e_vertical`` axis.
    """

    e_parallel: tuple[float, float, float]
    e_vertical: tuple[float, float, float]
    e_perp: tuple[float, float, float]
    source: str = "horizontal projection of target minus object functional point"

    @classmethod
    def from_points(
        cls,
        object_point: Sequence[float],
        target_point: Sequence[float],
    ) -> "ObjectTaskFrame":
        displacement = np.asarray(target_point, dtype=np.float64) - np.asarray(
            object_point, dtype=np.float64
        )
        horizontal = displacement.copy()
        horizontal[2] = 0.0
        parallel = _unit(horizontal, [1.0, 0.0, 0.0])
        vertical = np.asarray([0.0, 0.0, 1.0], dtype=np.float64)
        perp = _unit(np.cross(vertical, parallel), [0.0, 1.0, 0.0])
        # Re-orthogonalize to prevent accumulated numerical skew.
        parallel = _unit(np.cross(perp, vertical), parallel)
        return cls(tuple(parallel), tuple(vertical), tuple(perp))

    @classmethod
    def from_task(cls, task: Any) -> "ObjectTaskFrame":
        return cls.from_points(
            task.box.get_functional_point(0, "pose").p,
            task.target_box.get_functional_point(1, "pose").p,
        )

    def matrix(self) -> np.ndarray:
        """Return columns ``[parallel, vertical, perp]`` in world coordinates."""

        return np.column_stack(
            [
                np.asarray(self.e_parallel),
                np.asarray(self.e_vertical),
                np.asarray(self.e_perp),
            ]
        )

    def audit(self) -> Dict[str, Any]:
        matrix = self.matrix()
        gram = matrix.T @ matrix
        return {
            **asdict(self),
            "determinant": float(np.linalg.det(matrix)),
            "max_abs_orthonormal_error": float(np.max(np.abs(gram - np.eye(3)))),
            "orthonormal_at_1e-12": bool(np.max(np.abs(gram - np.eye(3))) <= 1e-12),
        }

