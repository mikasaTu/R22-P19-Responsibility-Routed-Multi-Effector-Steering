"""Public Stage 2G dual-frequency probe API.

The implementation is kept in tape.py so the pure offline transformation is
also easy to unit-test; this module is the stable contract used by scripts.
"""
from .tape import (
    DEFAULT_FREQUENCY_PAIRS_HZ, PHYSICS_HZ, PROBE_AMPLITUDES_M,
    FrozenNominalTape, ProbePairTape, build_frequency_pair,
    cartesian_offset_to_joint_delta, load_pair_with_sidecar,
)

__all__ = [
    "DEFAULT_FREQUENCY_PAIRS_HZ", "PHYSICS_HZ", "PROBE_AMPLITUDES_M",
    "FrozenNominalTape", "ProbePairTape", "build_frequency_pair",
    "cartesian_offset_to_joint_delta", "load_pair_with_sidecar",
]
