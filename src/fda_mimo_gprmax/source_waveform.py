"""Source-waveform sampling consistent with the active gprMax runtime."""

from __future__ import annotations

import numpy as np

from .config import WaveformConfig


class SourceWaveformError(RuntimeError):
    """Raised when the actual source waveform cannot be reconstructed safely."""


def sample_gprmax_builtin_waveform(
    shape: str,
    amplitude: float,
    center_frequency: float,
    time: np.ndarray,
    dt: float,
) -> np.ndarray:
    """Sample a built-in waveform using the installed gprMax implementation.

    The FDA-MIMO adapter intentionally does not maintain an independent copy
    of gprMax's waveform equations. The waveform used for source-spectrum
    deembedding must come from the same implementation used by gprMax.
    """

    try:
        from gprMax.waveforms import Waveform as GprMaxWaveform
    except Exception as exc:
        raise SourceWaveformError(
            "gprMax must be importable to reconstruct built-in source "
            "waveforms for source-spectrum deembedding"
        ) from exc

    shape = str(shape).lower()

    if shape not in GprMaxWaveform.types or shape == "user":
        raise SourceWaveformError(
            f"unsupported gprMax built-in waveform for deembedding: {shape}"
        )

    waveform = GprMaxWaveform()
    waveform.type = shape
    waveform.amp = float(amplitude)
    waveform.freq = float(center_frequency)

    out = np.empty(len(time), dtype=np.float64)

    for i, t in enumerate(np.asarray(time, dtype=np.float64)):
        out[i] = waveform.calculate_value(float(t), float(dt))

    return out


def sample_excitation_file_waveform(
    waveform: WaveformConfig,
    time: np.ndarray,
) -> np.ndarray:
    """Reconstruct the adapter-defined excitation-file sequence.

    This path is retained for compatibility. Publication FDA runs should use
    built-in gprMax waveforms unless excitation-file semantics have been
    validated independently.
    """

    samples = (
        np.asarray(waveform.samples, dtype=np.float64)
        * float(waveform.amplitude)
    )

    if waveform.time:
        src_t = np.asarray(waveform.time, dtype=np.float64)

        return np.interp(
            np.asarray(time, dtype=np.float64),
            src_t,
            samples,
            left=0.0,
            right=0.0,
        )

    out = np.zeros_like(time, dtype=np.float64)
    n = min(len(samples), len(out))
    out[:n] = samples[:n]

    return out


def sample_waveform(
    waveform: WaveformConfig,
    center_frequency: float,
    time: np.ndarray,
    dt: float,
) -> np.ndarray:
    """Return the source waveform on the FDTD whole-timestep grid."""

    if waveform.mode == "builtin":
        return sample_gprmax_builtin_waveform(
            waveform.shape,
            waveform.amplitude,
            center_frequency,
            time,
            dt,
        )

    if waveform.mode == "excitation_file":
        return sample_excitation_file_waveform(
            waveform,
            time,
        )

    raise SourceWaveformError(
        f"unsupported waveform mode: {waveform.mode}"
    )
