"""Double-frequency authority-ratio analysis.

The object displacement along ``e_perp`` is detrended, Hann-windowed, and
transformed with a one-sided FFT.  The soft-arm authority ratio is
``A(f_soft)/(A(f_soft)+A(f_receiver))``.  Invalid windows, unresolved
frequencies, zero denominators, and empty noise bands are returned explicitly;
coherence is ``None`` unless actual probe reference signals are supplied.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np

_DEFAULT_MIN_FREQUENCY_HZ = 0.3
_DEFAULT_MAX_FREQUENCY_HZ = 5.0
_MIN_FFT_SAMPLES = 8
_MIN_COHERENCE_SAMPLES = 32
_EPS = 1e-15


def _finite_vector(values: Sequence[float], name: str) -> np.ndarray:
    try:
        array = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise TypeError("%s must be numeric" % name) from exc
    if array.ndim != 1:
        raise ValueError("%s must be one-dimensional" % name)
    if array.size == 0:
        raise ValueError("%s must not be empty" % name)
    if not np.all(np.isfinite(array)):
        raise ValueError("%s contains non-finite values" % name)
    return np.ascontiguousarray(array, dtype=np.float64)


def _sample_rate(sample_rate_hz: Optional[float], fs: Optional[float]) -> Optional[float]:
    if sample_rate_hz is not None and fs is not None and not np.isclose(float(sample_rate_hz), float(fs), rtol=0.0, atol=1e-12):
        raise ValueError("sample_rate_hz and fs disagree")
    value = fs if sample_rate_hz is None else sample_rate_hz
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError("sample_rate_hz must be numeric") from exc
    if not np.isfinite(value) or value <= 0.0:
        raise ValueError("sample_rate_hz must be finite and positive")
    return value


def _linear_detrend(values: np.ndarray) -> np.ndarray:
    if values.size < 2:
        return values - values.mean()
    x = np.linspace(-1.0, 1.0, values.size, dtype=np.float64)
    design = np.column_stack((x, np.ones(values.size, dtype=np.float64)))
    coefficients, _, _, _ = np.linalg.lstsq(design, values, rcond=None)
    return values - design @ coefficients


def detrend_hann_fft(values: Sequence[float], sample_rate_hz: float, fs: Optional[float] = None) -> Dict[str, np.ndarray]:
    """Return a calibrated one-sided amplitude spectrum.

    ``2*abs(FFT(x*Hann))/sum(Hann)`` recovers a bin-centred sinusoid's
    amplitude.  This is the native FFT-bin amplitude used by the gates.
    """
    array = _finite_vector(values, "values")
    if array.size < _MIN_FFT_SAMPLES:
        raise ValueError("window is too short for FFT estimation: need at least %d samples" % _MIN_FFT_SAMPLES)
    rate = _sample_rate(sample_rate_hz, fs)
    if rate is None:
        raise ValueError("sample_rate_hz (or fs) is required")
    detrended = _linear_detrend(array)
    window = np.hanning(array.size).astype(np.float64)
    window_sum = float(window.sum())
    if window_sum <= _EPS:
        raise ValueError("Hann window has zero normalization")
    coefficients = np.fft.rfft(detrended * window)
    amplitudes = 2.0 * np.abs(coefficients) / window_sum
    amplitudes[0] *= 0.5
    if array.size % 2 == 0:
        amplitudes[-1] *= 0.5
    return {
        "frequency_hz": np.fft.rfftfreq(array.size, d=1.0 / rate),
        "amplitude": amplitudes,
        "detrended": detrended,
        "window": window,
        "sample_rate_hz": np.asarray(rate, dtype=np.float64),
        "n_samples": np.asarray(array.size, dtype=np.int64),
    }


def _windowed(
    values: Sequence[float], sample_rate_hz: Optional[float], times: Optional[Sequence[float]],
    start_time: Optional[float], end_time: Optional[float],
    start_index: Optional[int], end_index: Optional[int],
) -> Tuple[np.ndarray, float, Optional[np.ndarray]]:
    signal = _finite_vector(values, "displacement")
    selected_times = None
    rate = sample_rate_hz
    if times is not None:
        selected_times = _finite_vector(times, "times")
        if selected_times.size != signal.size:
            raise ValueError("times and displacement must have equal length")
        if selected_times.size < 2 or np.any(np.diff(selected_times) <= 0.0):
            raise ValueError("times must be strictly increasing")
        deltas = np.diff(selected_times)
        median_dt = float(np.median(deltas))
        if np.ptp(deltas) > max(1e-9, abs(median_dt) * 2e-3):
            raise ValueError("timestamps are not uniformly sampled")
        derived_rate = 1.0 / median_dt
        if rate is not None and not np.isclose(rate, derived_rate, rtol=2e-3, atol=1e-9):
            raise ValueError("sample_rate_hz disagrees with timestamps")
        rate = derived_rate
    if rate is None:
        raise ValueError("sample_rate_hz (or timestamps) is required")
    if start_time is not None or end_time is not None:
        if selected_times is None or start_time is None or end_time is None:
            raise ValueError("start_time/end_time require timestamps and must be paired")
        start, end = float(start_time), float(end_time)
        if not np.isfinite(start) or not np.isfinite(end) or end <= start:
            raise ValueError("end_time must be finite and greater than start_time")
        mask = (selected_times >= start) & (selected_times <= end)
        signal, selected_times = signal[mask], selected_times[mask]
    elif start_index is not None or end_index is not None:
        start = 0 if start_index is None else int(start_index)
        end = signal.size if end_index is None else int(end_index)
        if start < 0 or end > signal.size or end <= start:
            raise ValueError("invalid start_index/end_index")
        signal = signal[start:end]
        if selected_times is not None:
            selected_times = selected_times[start:end]
    return signal, float(rate), selected_times


def _invalid_result(reason: str, n_samples: int = 0, sample_rate_hz: Optional[float] = None) -> Dict[str, Any]:
    return {
        "valid": False, "validity_reason": str(reason), "n_samples": int(n_samples),
        "sample_rate_hz": None if sample_rate_hz is None else float(sample_rate_hz),
        "sample_count": int(n_samples),
        "frequency_resolution_hz": None, "amplitude_soft": None, "amplitude_receiver": None,
        "frequency_soft_hz": None, "frequency_receiver_hz": None, "a_soft": None,
        "noise_floor": None, "noise_floor_valid": False,
        "noise_band_hz": [_DEFAULT_MIN_FREQUENCY_HZ, _DEFAULT_MAX_FREQUENCY_HZ],
        "noise_exclusion_radius_hz": None,
        "snr_soft": None, "snr_receiver": None, "snr_valid": False,
        "snr_reason": "noise floor was not estimated",
        "coherence": {"soft": None, "receiver": None}, "coherence_by_frequency": {},
        "coherence_nperseg": {"soft": None, "receiver": None},
        "coherence_frequency_resolution_hz": {"soft": None, "receiver": None},
        "coherence_observed_frequency_hz": {"soft": None, "receiver": None},
        "coherence_valid": False, "coherence_reason": "not estimated", "coherence_segments": 0,
    }


def _target_amplitude(frequencies: np.ndarray, amplitudes: np.ndarray, target_hz: float) -> Tuple[float, float, int]:
    index = int(np.argmin(np.abs(frequencies - target_hz)))
    return float(amplitudes[index]), float(frequencies[index]), index


def _welch_coherence(signal: np.ndarray, reference: np.ndarray, sample_rate_hz: float, target_hz: float) -> Tuple[Optional[float], int, str, Optional[int], Optional[float], Optional[float]]:
    """Estimate magnitude-squared coherence; require at least two segments.

    The returned nperseg, bin spacing, and observed bin disclose the resolution
    used for each coherence value; no coherence is fabricated for a short
    window or a zero cross-spectrum denominator.
    """
    if signal.size != reference.size:
        return None, 0, "reference length differs from displacement", None, None, None
    if signal.size < _MIN_COHERENCE_SAMPLES:
        return None, 0, "window too short for two coherence segments", None, None, None
    nperseg = min(256, signal.size // 2)
    if nperseg < 16:
        return None, 0, "window too short for two coherence segments", nperseg, sample_rate_hz / nperseg, None
    overlap = nperseg // 2
    starts = list(range(0, signal.size - nperseg + 1, nperseg - overlap))
    if len(starts) < 2:
        return None, len(starts), "fewer than two coherence segments", nperseg, sample_rate_hz / nperseg, None
    window = np.hanning(nperseg).astype(np.float64)
    pxx = pyy = pxy = None
    for start in starts:
        x = _linear_detrend(signal[start:start + nperseg]) * window
        y = _linear_detrend(reference[start:start + nperseg]) * window
        fx, fy = np.fft.rfft(x), np.fft.rfft(y)
        one_x, one_y, one_xy = np.abs(fx) ** 2, np.abs(fy) ** 2, fx * np.conj(fy)
        pxx = one_x if pxx is None else pxx + one_x
        pyy = one_y if pyy is None else pyy + one_y
        pxy = one_xy if pxy is None else pxy + one_xy
    coherence_frequencies = np.fft.rfftfreq(nperseg, d=1.0 / sample_rate_hz)
    index = int(np.argmin(np.abs(coherence_frequencies - target_hz)))
    observed_frequency = float(coherence_frequencies[index])
    bin_spacing = float(sample_rate_hz / nperseg)
    denominator = float(np.real(pxx[index] * pyy[index]))
    if not np.isfinite(denominator) or denominator <= _EPS:
        return None, len(starts), "zero cross-spectral denominator", nperseg, bin_spacing, observed_frequency
    value = float(np.abs(pxy[index]) ** 2 / denominator)
    if not np.isfinite(value):
        return None, len(starts), "non-finite coherence", nperseg, bin_spacing, observed_frequency
    return float(np.clip(value, 0.0, 1.0)), len(starts), "ok", nperseg, bin_spacing, observed_frequency


def authority_ratio(
    displacement: Sequence[float], sample_rate_hz: Optional[float] = None,
    f_soft: float = 1.0, f_receiver: float = 2.5, *, fs: Optional[float] = None,
    times: Optional[Sequence[float]] = None, start_time: Optional[float] = None,
    end_time: Optional[float] = None, start_index: Optional[int] = None,
    end_index: Optional[int] = None, reference_soft: Optional[Sequence[float]] = None,
    reference_receiver: Optional[Sequence[float]] = None,
    noise_min_hz: float = _DEFAULT_MIN_FREQUENCY_HZ,
    noise_max_hz: float = _DEFAULT_MAX_FREQUENCY_HZ, min_samples: int = _MIN_FFT_SAMPLES,
) -> Dict[str, Any]:
    """Compute ``a_soft`` and report spectral/noise/coherence validity.

    ``times`` plus ``start_time``/``end_time`` is preferred for the E3..E5
    window.  ``reference_soft``/``reference_receiver`` are the actual injected
    probe records; without them coherence stays null by design.
    """
    rate = _sample_rate(sample_rate_hz, fs)
    try:
        soft_frequency, receiver_frequency = float(f_soft), float(f_receiver)
        low, high = float(noise_min_hz), float(noise_max_hz)
    except (TypeError, ValueError) as exc:
        raise TypeError("frequencies and noise-band limits must be numeric") from exc
    if not np.isfinite(soft_frequency) or not np.isfinite(receiver_frequency) or soft_frequency <= 0.0 or receiver_frequency <= 0.0:
        raise ValueError("probe frequencies must be finite and positive")
    if not np.isfinite(low) or not np.isfinite(high) or low < 0.0 or high <= low:
        raise ValueError("noise band must satisfy 0 <= low < high")
    if soft_frequency == receiver_frequency:
        return _invalid_result("probe frequencies are identical", 0, rate)
    signal, rate, _ = _windowed(displacement, rate, times, start_time, end_time, start_index, end_index)
    if soft_frequency >= rate / 2.0 or receiver_frequency >= rate / 2.0:
        raise ValueError("probe frequencies must be below Nyquist")
    n_samples = int(signal.size)
    if n_samples < max(int(min_samples), _MIN_FFT_SAMPLES):
        return _invalid_result("window too short for amplitude estimation: need at least %d samples" % max(int(min_samples), _MIN_FFT_SAMPLES), n_samples, rate)
    spectrum = detrend_hann_fft(signal, rate)
    frequencies, amplitudes = spectrum["frequency_hz"], spectrum["amplitude"]
    resolution = float(rate / n_samples)
    amplitude_soft, observed_soft, soft_index = _target_amplitude(frequencies, amplitudes, soft_frequency)
    amplitude_receiver, observed_receiver, receiver_index = _target_amplitude(frequencies, amplitudes, receiver_frequency)
    if soft_index == receiver_index or abs(soft_frequency - receiver_frequency) < resolution:
        return _invalid_result("probe frequencies are not resolved by this window", n_samples, rate)
    denominator = amplitude_soft + amplitude_receiver
    if not np.isfinite(denominator) or denominator <= _EPS:
        result = _invalid_result("zero total probe amplitude; authority ratio is not estimable", n_samples, rate)
        result.update({"frequency_resolution_hz": resolution, "amplitude_soft": amplitude_soft, "amplitude_receiver": amplitude_receiver, "frequency_soft_hz": observed_soft, "frequency_receiver_hz": observed_receiver})
        return result
    band = (frequencies >= low) & (frequencies <= high)
    # A Hann main lobe extends beyond the nearest native bin; exclude two
    # bins around each driven line when estimating the 0.3-5 Hz floor.
    exclusion_radius = 2.0 * resolution
    band &= np.abs(frequencies - soft_frequency) > exclusion_radius
    band &= np.abs(frequencies - receiver_frequency) > exclusion_radius
    noise_values = amplitudes[band]
    if noise_values.size == 0:
        return _invalid_result("0.3-5 Hz noise band has no estimable bins", n_samples, rate)
    noise_floor = float(np.median(noise_values))
    if not np.isfinite(noise_floor) or noise_floor < 0.0:
        return _invalid_result("noise floor is non-finite", n_samples, rate)
    result: Dict[str, Any] = {
        "valid": True, "validity_reason": "ok", "n_samples": n_samples, "sample_count": n_samples, "sample_rate_hz": rate,
        "frequency_resolution_hz": resolution, "amplitude_soft": amplitude_soft,
        "amplitude_receiver": amplitude_receiver, "frequency_soft_hz": observed_soft,
        "frequency_receiver_hz": observed_receiver, "requested_frequency_soft_hz": soft_frequency,
        "requested_frequency_receiver_hz": receiver_frequency, "a_soft": float(amplitude_soft / denominator),
        "noise_floor": noise_floor, "noise_floor_valid": True, "noise_band_hz": [low, high],
        "noise_exclusion_radius_hz": exclusion_radius, "noise_bin_count": int(noise_values.size),
        "snr_soft": float(amplitude_soft / noise_floor) if noise_floor > _EPS else None,
        "snr_receiver": float(amplitude_receiver / noise_floor) if noise_floor > _EPS else None,
        "snr_valid": bool(noise_floor > _EPS),
        "snr_reason": "ok" if noise_floor > _EPS else "noise floor is zero or below epsilon",
        "coherence": {"soft": None, "receiver": None}, "coherence_by_frequency": {},
        "coherence_nperseg": {"soft": None, "receiver": None},
        "coherence_frequency_resolution_hz": {"soft": None, "receiver": None},
        "coherence_observed_frequency_hz": {"soft": None, "receiver": None},
        "coherence_valid": False, "coherence_reason": "reference signals were not supplied",
        "coherence_segments": 0,
    }
    references = (("soft", reference_soft, soft_frequency), ("receiver", reference_receiver, receiver_frequency))
    coherence_values, segments_seen, reasons = [], [], []
    for name, reference, target in references:
        if reference is None:
            reasons.append("%s reference missing" % name)
            continue
        ref = _finite_vector(reference, "reference_%s" % name)
        if times is not None:
            all_times = _finite_vector(times, "times")
            if ref.size != all_times.size:
                raise ValueError("reference_%s and times must have equal length" % name)
            if start_time is not None or end_time is not None:
                mask = (all_times >= float(start_time)) & (all_times <= float(end_time))
                ref = ref[mask]
            elif start_index is not None or end_index is not None:
                start = 0 if start_index is None else int(start_index)
                end = ref.size if end_index is None else int(end_index)
                ref = ref[start:end]
        elif start_index is not None or end_index is not None:
            start = 0 if start_index is None else int(start_index)
            end = ref.size if end_index is None else int(end_index)
            ref = ref[start:end]
        value, segments, reason, nperseg, bin_spacing, observed_frequency = _welch_coherence(signal, ref, rate, target)
        result["coherence"][name] = value
        result["coherence_by_frequency"]["%.12g" % target] = value
        result.setdefault("coherence_nperseg", {})[name] = nperseg
        result.setdefault("coherence_frequency_resolution_hz", {})[name] = bin_spacing
        result.setdefault("coherence_observed_frequency_hz", {})[name] = observed_frequency
        segments_seen.append(int(segments))
        reasons.append("%s: %s" % (name, reason))
        if value is not None:
            coherence_values.append(value)
    if segments_seen:
        result["coherence_segments"] = min(segments_seen)
    if len(coherence_values) == 2:
        result["coherence_valid"], result["coherence_reason"] = True, "ok"
    elif len(coherence_values) == 1:
        result["coherence_reason"] = "only one probe reference had a valid coherence estimate"
    else:
        result["coherence_reason"] = "; ".join(reasons)
    return result


analyze_authority_ratio = authority_ratio
estimate_authority_ratio = authority_ratio
compute_authority_ratio = authority_ratio
