"""Pure numeric Step 9 analysis tests; no simulator or PAI is imported."""
import numpy as np
import pytest

from stage2_robotwin.stage2g.analysis.authority_ratio import authority_ratio, detrend_hann_fft
from stage2_robotwin.stage2g.analysis.repeat_hash import (
    assert_repeat_effect_vectors,
    compare_effect_vectors,
    effect_vector_sha256,
    effect_vectors_bitwise_equal,
)
from stage2_robotwin.stage2g.analysis.wrench_decomposition import (
    contact_wrench,
    decompose_contact_wrenches,
    decompose_side_records,
    decompose_wrenches,
)


def test_fft_recovers_known_double_frequency_amplitude_ratio():
    sample_rate = 100.0
    n_samples = 1000
    time = np.arange(n_samples, dtype=np.float64) / sample_rate
    signal = 0.70 * np.sin(2.0 * np.pi * 1.0 * time) + 0.30 * np.sin(2.0 * np.pi * 2.5 * time)
    result = authority_ratio(signal, sample_rate, f_soft=1.0, f_receiver=2.5)
    assert result["valid"]
    assert abs(result["a_soft"] - 0.70) < 0.02
    assert result["noise_floor_valid"]
    assert result["coherence_valid"] is False
    assert result["coherence"]["soft"] is None
    assert result["coherence"]["receiver"] is None
    assert result["noise_exclusion_radius_hz"] == pytest.approx(2.0 * result["frequency_resolution_hz"])


def test_coherence_requires_real_reference_and_short_window_is_explicitly_invalid():
    sample_rate = 100.0
    time = np.arange(1000, dtype=np.float64) / sample_rate
    soft = np.sin(2.0 * np.pi * time)
    receiver = np.sin(2.0 * np.pi * 2.5 * time)
    signal = 0.7 * soft + 0.3 * receiver
    result = authority_ratio(signal, sample_rate, 1.0, 2.5, reference_soft=soft, reference_receiver=receiver)
    assert result["coherence_valid"]
    assert result["coherence"]["soft"] is not None
    assert result["coherence"]["receiver"] is not None
    assert result["coherence_nperseg"]["soft"] == 256
    assert result["coherence_frequency_resolution_hz"]["soft"] == pytest.approx(sample_rate / 256.0)
    assert result["coherence_observed_frequency_hz"]["soft"] == pytest.approx(1.171875)
    short = authority_ratio(signal[:7], sample_rate, 1.0, 2.5)
    assert short["valid"] is False
    assert "short" in short["validity_reason"]
    zero = authority_ratio(np.zeros(1000), sample_rate, 1.0, 2.5)
    assert zero["valid"] is False
    assert "zero total probe amplitude" in zero["validity_reason"]


def test_contact_wrench_and_pure_internal_or_net_force_fractions():
    one = contact_wrench([0.0, 2.0, 0.0], [0.5, 0.0, 0.0], [0.0, 0.0, 0.0])
    np.testing.assert_allclose(one, [0.0, 2.0, 0.0, 0.0, 0.0, 1.0])
    internal = decompose_wrenches([1.0, 0.0, 0.0, 0.0, 0.0, 0.0], [-1.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    assert internal["valid"]
    assert internal["internal_fraction"] == pytest.approx(1.0)
    net = decompose_wrenches([1.0, 0.0, 0.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    assert net["internal_fraction"] == pytest.approx(0.0)
    zero = decompose_wrenches(np.zeros(6), np.zeros(6))
    assert zero["valid"] is False
    assert zero["internal_fraction"] is None


def test_contact_mapping_sums_per_side_and_keeps_units_transparent():
    left = [{"force": [1.0, 0.0, 0.0], "position": [0.0, 0.0, 0.0]}]
    right = [{"force": [1.0, 0.0, 0.0], "position": [0.0, 0.0, 0.0]}]
    result = decompose_contact_wrenches(left, right, [0.0, 0.0, 0.0])
    assert result["units"] == "inherited from contact vector and position inputs"
    assert result["internal_fraction"] == pytest.approx(0.0)


def test_repeat_effect_vector_hash_is_bitwise_and_no_rounding():
    first = np.asarray([0.1, 0.2, -0.0], dtype=np.float64)
    same = first.copy()
    one_ulp = first.copy()
    one_ulp[0] = np.nextafter(one_ulp[0], np.inf)
    assert effect_vectors_bitwise_equal(first, same)
    assert not effect_vectors_bitwise_equal(first, one_ulp)
    assert effect_vector_sha256(first) != effect_vector_sha256(one_ulp)
    report = compare_effect_vectors(first, same)
    assert report["bitwise_equal"] is True
    assert_repeat_effect_vectors(first, same)
    with pytest.raises(AssertionError):
        assert_repeat_effect_vectors(first, one_ulp)


def test_four_point_five_second_off_bin_native_bin_ratio_stays_within_two_percent():
    # The actual 250 Hz, 1132-step E3..E5 window has 4.528 s and does not put
    # 1.0/2.5 Hz exactly on native bins.  The frozen nearest-bin convention
    # remains within the pre-registered 0.02 synthetic error bound.
    sample_rate = 250.0
    n_samples = 1132
    time = np.arange(n_samples, dtype=np.float64) / sample_rate
    for expected in (0.20, 0.50, 0.80):
        signal = expected * np.sin(2.0 * np.pi * 1.0 * time)
        signal += (1.0 - expected) * np.sin(2.0 * np.pi * 2.5 * time)
        result = authority_ratio(signal, sample_rate, f_soft=1.0, f_receiver=2.5)
        assert result["valid"]
        assert abs(result["a_soft"] - expected) < 0.02


def test_nonuniform_timestamps_fail_closed_instead_of_using_median_dt():
    sample_rate = 100.0
    time = np.arange(1000, dtype=np.float64) / sample_rate
    time[400:] += 0.01
    signal = np.sin(2.0 * np.pi * time)
    with pytest.raises(ValueError, match="uniformly sampled"):
        authority_ratio(signal, sample_rate, 1.0, 2.5, times=time)


def test_stage2e_side_record_adapter_preserves_impulse_units():
    left = {"impulse": [1.0, 0.0, 0.0], "torque": [0.0, 0.0, 0.0]}
    right = {"impulse": [1.0, 0.0, 0.0], "torque": [0.0, 0.0, 0.0]}
    result = decompose_side_records(left, right)
    assert result["internal_fraction"] == pytest.approx(0.0)
    assert "inherited" in result["units"]
