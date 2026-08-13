"""Named entry point for vector-valued responsibility analysis."""

from .oracle import decompose_outcomes, quaternion_delta_rotvec

__all__ = ["decompose_outcomes", "quaternion_delta_rotvec"]
