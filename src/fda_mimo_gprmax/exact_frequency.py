"""Exact-frequency transforms for broadband FDA-MIMO-GPR responses.

The helpers in this module evaluate the discrete-time Fourier transform directly
at requested frequencies. They are intended for off-bin FDA/event frequencies
and preserve the same rectangular/no-window scientific convention used by the
existing FFT processing path unless another supported window is requested.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import ScenarioConfig
from .source_waveform import SourceWaveformError, sample_waveform


class ExactFrequencyError(ValueError):
    """Raised when an exact-frequency transform request is invalid."""


@dataclass(frozen=True)
class ExactFrequencyResponse:
    frequencies: np.ndarray
    frequency_tensor_raw: np.ndarray
    source_spectra: np.ndarray
    valid_band_mask: np.ndarray
    frequency_tensor_deembedded: np.ndarray


def _window(name: str, length: int) -> np.ndarray:
    name = str(name).lower()
    if name in {"none", "rect", "rectangular"}:
        return np.ones(length, dtype=np.float64)
    if name == "hann":
        return np.hanning(length)
    if name == "hamming":
        return np.hamming(length)
    raise ExactFrequencyError(f"unsupported DTFT window: {name}")


def _validate_time_and_frequencies(
    time: np.ndarray, frequencies: np.ndarray
) -> tuple[np.ndarray, np.ndarray, float]:
    time = np.asarray(time, dtype=np.float64)
    frequencies = np.asarray(frequencies, dtype=np.float64)
    if time.ndim != 1 or time.size < 2 or not np.all(np.isfinite(time)):
        raise ExactFrequencyError("time must be a finite one-dimensional array with at least two samples")
    dt = np.diff(time)
    if np.any(dt <= 0):
        raise ExactFrequencyError("time must be strictly increasing")
    dt0 = float(dt[0])
    if not np.allclose(dt, dt0, rtol=1e-10, atol=max(1e-18, abs(dt0) * 1e-12)):
        raise ExactFrequencyError("exact-frequency DTFT requires a uniformly sampled time axis")
    if frequencies.ndim != 1 or frequencies.size == 0:
        raise ExactFrequencyError("frequencies must be a non-empty one-dimensional array")
    if np.any(~np.isfinite(frequencies)) or np.any(frequencies < 0):
        raise ExactFrequencyError("frequencies must be finite and non-negative")
    return time, frequencies, dt0


def frequency_transform_at(
    time_traces: np.ndarray,
    time: np.ndarray,
    frequencies: np.ndarray,
    window: str = "none",
) -> np.ndarray:
    """Evaluate receiver traces at arbitrary frequencies by direct DTFT.

    ``time_traces`` may have any leading dimensions; its final dimension must
    match ``time``. The returned array has the same leading dimensions with the
    final time axis replaced by the requested frequency axis.
    """

    traces = np.asarray(time_traces)
    time, frequencies, dt = _validate_time_and_frequencies(time, frequencies)
    if traces.ndim < 1 or traces.shape[-1] != time.size:
        raise ExactFrequencyError("time_traces final dimension must match time")
    if not np.all(np.isfinite(traces)):
        raise ExactFrequencyError("time_traces must contain finite values")
    win = _window(window, time.size)
    kernel = np.exp(-2j * np.pi * frequencies[:, None] * time[None, :])
    weighted = traces * win
    out = np.tensordot(weighted, kernel, axes=([-1], [1])) * dt
    return np.asarray(out, dtype=np.complex64)


def source_spectra_at(
    scenario: ScenarioConfig,
    time: np.ndarray,
    frequencies: np.ndarray,
    window: str = "none",
) -> np.ndarray:
    """Evaluate each configured Tx source waveform at arbitrary frequencies."""

    time, frequencies, _ = _validate_time_and_frequencies(time, frequencies)
    spectra: list[np.ndarray] = []
    for center_frequency in scenario.fda.frequencies:
        try:
            waveform = np.asarray(
                sample_waveform(
                    scenario.waveform,
                    float(center_frequency),
                    time,
                    float(time[1] - time[0]),
                ),
                dtype=np.float64,
            )
        except SourceWaveformError as exc:
            raise ExactFrequencyError(str(exc)) from exc
        waveform = np.array(waveform, copy=True)
        waveform[time > scenario.time.window] = 0.0
        spectra.append(
            frequency_transform_at(waveform, time, frequencies, window=window)
        )
    return np.stack(spectra, axis=0).astype(np.complex64)


def valid_band_mask_at(source_spectra: np.ndarray, threshold: float) -> np.ndarray:
    spectra = np.asarray(source_spectra, dtype=np.complex64)
    threshold = float(threshold)
    if threshold < 0 or not np.isfinite(threshold):
        raise ExactFrequencyError("threshold must be finite and non-negative")
    if spectra.ndim != 2:
        raise ExactFrequencyError("source_spectra must have shape [Nt, Kf]")
    magnitudes = np.abs(spectra)
    maxima = magnitudes.max(axis=1, keepdims=True)
    maxima[maxima == 0] = np.inf
    return magnitudes > threshold * maxima


def deembed_at(
    frequency_tensor: np.ndarray,
    source_spectra: np.ndarray,
    valid_mask: np.ndarray,
) -> np.ndarray:
    tensor = np.asarray(frequency_tensor, dtype=np.complex64)
    spectra = np.asarray(source_spectra, dtype=np.complex64)
    mask = np.asarray(valid_mask, dtype=bool)
    if tensor.ndim != 3:
        raise ExactFrequencyError("frequency_tensor must have shape [Nt, Nr, Kf]")
    if spectra.shape != (tensor.shape[0], tensor.shape[2]):
        raise ExactFrequencyError("source_spectra shape must be [Nt, Kf]")
    if mask.shape != spectra.shape:
        raise ExactFrequencyError("valid_mask shape must match source_spectra")
    valid = mask & np.isfinite(spectra) & (np.abs(spectra) > 0)
    out = np.full_like(tensor, np.nan + 1j * np.nan, dtype=np.complex64)
    np.divide(
        tensor,
        spectra[:, None, :],
        out=out,
        where=valid[:, None, :],
    )
    return out


def transfer_function_at(
    time_traces: np.ndarray,
    scenario: ScenarioConfig,
    time: np.ndarray,
    frequencies: np.ndarray,
    *,
    valid_band_threshold: float | None = None,
    window: str = "none",
) -> ExactFrequencyResponse:
    """Evaluate and source-deembed a broadband Tx-Rx response at exact frequencies."""

    frequencies = np.asarray(frequencies, dtype=np.float64)
    raw = frequency_transform_at(time_traces, time, frequencies, window=window)
    if raw.ndim != 3:
        raise ExactFrequencyError("time_traces must produce a [Nt, Nr, Kf] tensor")
    if raw.shape[0] != scenario.nt:
        raise ExactFrequencyError("time_traces Tx dimension does not match scenario Nt")
    source = source_spectra_at(scenario, time, frequencies, window=window)
    threshold = (
        scenario.processing.valid_band_threshold
        if valid_band_threshold is None
        else float(valid_band_threshold)
    )
    mask = valid_band_mask_at(source, threshold)
    deembedded = deembed_at(raw, source, mask)
    return ExactFrequencyResponse(
        frequencies=frequencies,
        frequency_tensor_raw=raw,
        source_spectra=source,
        valid_band_mask=mask,
        frequency_tensor_deembedded=deembedded,
    )
