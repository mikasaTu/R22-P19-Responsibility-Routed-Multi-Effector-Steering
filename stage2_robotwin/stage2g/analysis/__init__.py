"""Pure numeric analysis for the Stage 2G authority probe."""

from .authority_ratio import (
    analyze_authority_ratio,
    authority_ratio,
    compute_authority_ratio,
    detrend_hann_fft,
    estimate_authority_ratio,
)
from .repeat_hash import (
    assert_repeat_effect_vectors,
    canonical_effect_sha256,
    compare_effect_vectors,
    compare_repeat_cells,
    effect_vector_sha256,
    effect_vectors_bitwise_equal,
)
from .wrench_decomposition import (
    contact_wrench,
    decompose_contact_wrenches,
    decompose_delta_wrenches,
    decompose_side_records,
    decompose_wrenches,
    side_wrench_from_record,
    delta_wrench_decomposition,
    sum_contact_wrenches,
    trajectory_wrench_decomposition,
)

__all__ = [
    "analyze_authority_ratio", "authority_ratio", "compute_authority_ratio",
    "detrend_hann_fft", "estimate_authority_ratio",
    "assert_repeat_effect_vectors", "canonical_effect_sha256",
    "compare_effect_vectors", "compare_repeat_cells", "effect_vector_sha256",
    "effect_vectors_bitwise_equal", "contact_wrench", "decompose_contact_wrenches", "decompose_side_records", "side_wrench_from_record",
    "decompose_delta_wrenches", "decompose_wrenches", "delta_wrench_decomposition",
    "sum_contact_wrenches", "trajectory_wrench_decomposition",
]
