"""Tensor processing for FDA-MIMO-GPR snapshots."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from .config import ScenarioConfig, WaveformConfig
from .log_analysis import collect_run_log_summaries, summarize_numerical_dispersion
from .parsing import TxTrace


class ProcessingError(RuntimeError):
    """Raised when tensor processing fails."""


@dataclass(frozen=True)
class Snapshot:
    time_traces: np.ndarray  # [Nt, Nr, Lt]
    time: np.ndarray
    frequencies: np.ndarray
    frequency_tensor_raw: np.ndarray  # [Nt, Nr, Kf]
    source_spectra: np.ndarray  # [Nt, Kf]
    valid_band_mask: np.ndarray  # [Nt, Kf]
    frequency_tensor_cal: np.ndarray | None
    tx_positions: np.ndarray
    rx_positions: np.ndarray
    fda_center_frequencies: np.ndarray
    metadata: dict
    scatter_tensor: np.ndarray | None = None
    tx_positions_requested: np.ndarray | None = None
    rx_positions_requested: np.ndarray | None = None
    tx_positions_actual: np.ndarray | None = None
    rx_positions_actual: np.ndarray | None = None
    position_quantization_error_tx: np.ndarray | None = None
    position_quantization_error_rx: np.ndarray | None = None
    coordinate_warnings: list[str] = field(default_factory=list)


def _file_sha256(path: str | Path) -> str | None:
    path = Path(path)
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def assemble_time_tensor(outputs: Sequence[TxTrace], expected_nt: int | None = None, expected_nr: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    if not outputs:
        raise ProcessingError("no Tx traces supplied")
    if expected_nt is not None and len(outputs) != expected_nt:
        raise ProcessingError(f"expected {expected_nt} Tx outputs, got {len(outputs)}")
    dt0 = outputs[0].dt
    shape0 = outputs[0].traces.shape
    for item in outputs:
        if item.traces.ndim != 2:
            raise ProcessingError(f"tx {item.tx_index} traces must be [Nr, Lt]")
        if expected_nr is not None and item.traces.shape[0] != expected_nr:
            raise ProcessingError(f"tx {item.tx_index} expected {expected_nr} receivers, got {item.traces.shape[0]}")
        if item.traces.shape != shape0:
            raise ProcessingError(f"tx {item.tx_index} shape {item.traces.shape} differs from {shape0}")
        if not np.isclose(item.dt, dt0, rtol=0, atol=1e-18):
            raise ProcessingError(f"tx {item.tx_index} dt {item.dt} differs from {dt0}")
    return np.stack([item.traces for item in outputs], axis=0), outputs[0].time


def _window(name: str, lt: int) -> np.ndarray:
    name = name.lower()
    if name in {"none", "rect", "rectangular"}:
        return np.ones(lt, dtype=np.float64)
    if name == "hann":
        return np.hanning(lt)
    if name == "hamming":
        return np.hamming(lt)
    raise ProcessingError(f"unsupported FFT window: {name}")


def frequency_transform(time_traces: np.ndarray, dt: float, window: str = "none", frequency_range: tuple[float, float] | None = None) -> tuple[np.ndarray, np.ndarray]:
    if time_traces.ndim != 3:
        raise ProcessingError("time_traces must have shape [Nt, Nr, Lt]")
    lt = time_traces.shape[-1]
    win = _window(window, lt)
    spectra = np.fft.rfft(time_traces * win[None, None, :], axis=-1) * dt
    freqs = np.fft.rfftfreq(lt, d=dt)
    if frequency_range is not None:
        lo, hi = frequency_range
        mask = (freqs >= lo) & (freqs <= hi)
        freqs = freqs[mask]
        spectra = spectra[..., mask]
    return spectra.astype(np.complex64), freqs.astype(np.float64)


def sample_builtin_waveform(shape: str, amplitude: float, center_frequency: float, time: np.ndarray) -> np.ndarray:
    f = float(center_frequency)
    t = time.astype(np.float64)
    shape = shape.lower()
    if shape == "gaussian":
        zeta = 2 * np.pi**2 * f**2
        chi = 1 / f
        y = np.exp(-zeta * (t - chi) ** 2)
    elif shape in {"gaussiandot", "gaussian_dot"}:
        zeta = 2 * np.pi**2 * f**2
        chi = 1 / f
        y = -2 * zeta * (t - chi) * np.exp(-zeta * (t - chi) ** 2)
    elif shape in {"gaussiandotdot", "ricker"}:
        tau = t - 1 / f
        a = (np.pi * f * tau) ** 2
        y = (1 - 2 * a) * np.exp(-a)
    elif shape in {"sine", "sinusoid"}:
        y = np.sin(2 * np.pi * f * t)
    else:
        zeta = 2 * np.pi**2 * f**2
        chi = 1 / f
        y = np.exp(-zeta * (t - chi) ** 2) * np.cos(2 * np.pi * f * t)
    return (amplitude * y).astype(np.float64)


def sample_waveform(waveform: WaveformConfig, center_frequency: float, time: np.ndarray) -> np.ndarray:
    if waveform.mode == "builtin":
        return sample_builtin_waveform(waveform.shape, waveform.amplitude, center_frequency, time)
    samples = np.asarray(waveform.samples, dtype=np.float64) * waveform.amplitude
    if waveform.time:
        src_t = np.asarray(waveform.time, dtype=np.float64)
        return np.interp(time, src_t, samples, left=0.0, right=0.0)
    out = np.zeros_like(time, dtype=np.float64)
    n = min(len(samples), len(out))
    out[:n] = samples[:n]
    return out


def compute_source_spectra(scenario: ScenarioConfig, time: np.ndarray, frequencies: np.ndarray, full_frequency_range: tuple[float, float] | None = None) -> np.ndarray:
    dt = float(time[1] - time[0]) if len(time) > 1 else 1.0
    spectra = []
    for freq in scenario.fda.frequencies:
        waveform = sample_waveform(scenario.waveform, freq, time)
        spec = np.fft.rfft(waveform, axis=-1) * dt
        spec_freqs = np.fft.rfftfreq(len(time), d=dt)
        if full_frequency_range is not None:
            lo, hi = full_frequency_range
            mask = (spec_freqs >= lo) & (spec_freqs <= hi)
            spec = spec[mask]
        if len(spec) != len(frequencies):
            spec = np.interp(frequencies, spec_freqs[: len(spec)], spec.real) + 1j * np.interp(frequencies, spec_freqs[: len(spec)], spec.imag)
        spectra.append(spec.astype(np.complex64))
    return np.stack(spectra, axis=0)


def valid_band_mask(source_spectra: np.ndarray, threshold: float) -> np.ndarray:
    mags = np.abs(source_spectra)
    maxima = mags.max(axis=1, keepdims=True)
    maxima[maxima == 0] = np.inf
    return mags > (threshold * maxima)


def normalize_by_source(frequency_tensor: np.ndarray, source_spectra: np.ndarray, mask: np.ndarray, eta: float) -> np.ndarray:
    denom = source_spectra[:, None, :] + eta
    out = np.full_like(frequency_tensor, np.nan + 1j * np.nan, dtype=np.complex64)
    valid = mask[:, None, :]
    np.divide(frequency_tensor, denom, out=out, where=valid)
    return out


def _coordinate_evidence(outputs: Sequence[TxTrace], scenario: ScenarioConfig, tolerance: float = 1e-9) -> dict[str, Any]:
    requested_tx = scenario.array.tx_positions.astype(np.float64)
    requested_rx = scenario.array.rx_positions.astype(np.float64)
    warnings: list[str] = []

    actual_tx_rows: list[np.ndarray] = []
    for i, item in enumerate(outputs):
        if item.source_position_actual is None:
            warnings.append(f"tx {i}: actual source position unavailable; falling back to requested position")
            actual_tx_rows.append(requested_tx[i])
        else:
            actual_tx_rows.append(np.asarray(item.source_position_actual, dtype=np.float64))
        warnings.extend([f"tx {i}: {w}" for w in item.warnings])
    actual_tx = np.stack(actual_tx_rows, axis=0)

    actual_rx_rows: list[np.ndarray] = []
    for i, item in enumerate(outputs):
        rx = item.receiver_positions_actual if item.receiver_positions_actual is not None else item.receiver_positions
        rx = np.asarray(rx, dtype=np.float64)
        if rx.shape != requested_rx.shape or not np.all(np.isfinite(rx)):
            warnings.append(f"tx {i}: actual receiver positions unavailable or invalid; falling back to requested receiver positions")
            rx = requested_rx
        actual_rx_rows.append(rx)
    actual_rx = np.stack(actual_rx_rows, axis=0)

    err_tx = actual_tx - requested_tx
    err_rx = actual_rx - requested_rx[None, :, :]
    if np.nanmax(np.abs(err_tx)) > tolerance:
        warnings.append(f"requested/actual Tx coordinate mismatch exceeds {tolerance:g} m")
    if np.nanmax(np.abs(err_rx)) > tolerance:
        warnings.append(f"requested/actual Rx coordinate mismatch exceeds {tolerance:g} m")
    if len(actual_rx) > 1 and not np.allclose(actual_rx, actual_rx[0][None, :, :], rtol=0, atol=tolerance):
        warnings.append("actual receiver positions are not consistent across Tx outputs")

    actual_positions_available = not any("unavailable" in w or "not found" in w or "missing" in w for w in warnings)
    canonical_rx = actual_rx[0] if actual_rx.size else requested_rx
    return {
        "tx_positions_requested": requested_tx,
        "rx_positions_requested": requested_rx,
        "tx_positions_actual": actual_tx,
        "rx_positions_actual": actual_rx,
        "rx_positions_actual_canonical": canonical_rx,
        "position_quantization_error_tx": err_tx,
        "position_quantization_error_rx": err_rx,
        "coordinate_warnings": warnings,
        "actual_positions_available": bool(actual_positions_available),
        "max_requested_actual_tx_error_m": float(np.nanmax(np.abs(err_tx))) if err_tx.size else 0.0,
        "max_requested_actual_rx_error_m": float(np.nanmax(np.abs(err_rx))) if err_rx.size else 0.0,
    }


def _read_manifest_for_outputs(outputs: Sequence[TxTrace]) -> dict[str, Any] | None:
    if not outputs:
        return None
    raw_dir = Path(outputs[0].path).parent
    manifest = raw_dir.parent / "logs" / "run_manifest.json"
    if manifest.exists():
        try:
            return json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    return None


def _run_evidence_metadata(outputs: Sequence[TxTrace], scenario: ScenarioConfig, frequencies: np.ndarray, valid_mask: np.ndarray) -> dict[str, Any]:
    raw_paths = [Path(item.path) for item in outputs]
    raw_dir = raw_paths[0].parent if raw_paths else Path(".")
    variant_dir = raw_dir.parent
    config_dir = variant_dir / "config"
    logs_dir = variant_dir / "logs"
    manifest = _read_manifest_for_outputs(outputs)
    input_records = manifest.get("render_plan", {}).get("inputs", []) if manifest else []

    input_checksums = []
    for i in range(len(outputs)):
        candidate = config_dir / f"generated_tx_{i:03d}.in"
        rec = next((r for r in input_records if int(r.get("tx_index", -1)) == i), {})
        input_checksums.append({
            "tx_index": i,
            "path": str(candidate),
            "sha256": _file_sha256(candidate),
            "render_checksum": rec.get("checksum"),
        })
    raw_checksums = [{"tx_index": i, "path": str(path), "sha256": _file_sha256(path)} for i, path in enumerate(raw_paths)]

    logs = collect_run_log_summaries(logs_dir) if logs_dir.exists() else []
    dispersion = summarize_numerical_dispersion(logs)
    gprmax_version = next((item.gprmax_version for item in logs if item.gprmax_version), None)
    if gprmax_version is None:
        gprmax_version = next((str(item.attrs.get("gprMax")) for item in outputs if item.attrs.get("gprMax")), "unknown")

    fft_bin_spacing = float(np.median(np.diff(frequencies))) if frequencies.size > 1 else None
    fda_freqs = np.asarray(scenario.fda.frequencies, dtype=np.float64)
    diffs = np.diff(fda_freqs)
    fda_delta = float(np.median(np.abs(diffs))) if diffs.size else 0.0
    ratio = None if not fft_bin_spacing or fda_delta == 0 else float(fft_bin_spacing / fda_delta)
    can_resolve = bool(fft_bin_spacing is not None and fda_delta > 0 and fft_bin_spacing <= fda_delta / 2.0)

    return {
        "variant_dir": str(variant_dir),
        "manifest_available": manifest is not None,
        "input_file_checksums": input_checksums,
        "raw_output_checksums": raw_checksums,
        "configured_center_frequencies_hz": fda_freqs.tolist(),
        "stdout_center_frequencies_hz": [item.waveform_frequency_hz for item in logs],
        "log_summaries": [item.to_dict() for item in logs],
        "numerical_dispersion": dispersion.to_dict(),
        "gprmax_version": gprmax_version,
        "fft_bin_spacing_hz": fft_bin_spacing,
        "fda_delta_f_hz": fda_delta,
        "fft_resolution_ratio": ratio,
        "can_resolve_fda_step_by_fft": can_resolve,
        "valid_fraction": float(valid_mask.mean()) if valid_mask.size else None,
        "nan_count_valid_mask": int(np.isnan(valid_mask.astype(float)).sum()) if valid_mask.size else 0,
    }


def make_snapshot(outputs: Sequence[TxTrace], scenario: ScenarioConfig, normalize: bool = True) -> Snapshot:
    yt, time = assemble_time_tensor(outputs, expected_nt=scenario.nt, expected_nr=scenario.nr)
    yf, freqs = frequency_transform(yt, outputs[0].dt, window=scenario.processing.window, frequency_range=scenario.processing.frequency_range)
    src = compute_source_spectra(scenario, time, freqs, scenario.processing.frequency_range)
    mask = valid_band_mask(src, scenario.processing.valid_band_threshold)
    cal = normalize_by_source(yf, src, mask, scenario.processing.eta) if normalize else None
    coords = _coordinate_evidence(outputs, scenario)
    evidence = _run_evidence_metadata(outputs, scenario, freqs, mask)
    metadata = scenario.metadata()
    metadata.update({
        "gprmax_version": evidence.get("gprmax_version", "unknown"),
        "run_evidence": evidence,
        "coordinates": {
            "actual_positions_available": coords["actual_positions_available"],
            "max_requested_actual_tx_error_m": coords["max_requested_actual_tx_error_m"],
            "max_requested_actual_rx_error_m": coords["max_requested_actual_rx_error_m"],
            "warnings": coords["coordinate_warnings"],
        },
        "axis_convention": "/axis/tx_positions and /axis/rx_positions use actual positions when available; requested positions are stored separately.",
        "processing_metrics": {
            "fft_bin_spacing_hz": evidence["fft_bin_spacing_hz"],
            "fda_delta_f_hz": evidence["fda_delta_f_hz"],
            "fft_resolution_ratio": evidence["fft_resolution_ratio"],
            "can_resolve_fda_step_by_fft": evidence["can_resolve_fda_step_by_fft"],
            "valid_fraction": evidence["valid_fraction"],
        },
    })
    return Snapshot(
        time_traces=yt.astype(np.float32),
        time=time,
        frequencies=freqs,
        frequency_tensor_raw=yf,
        source_spectra=src,
        valid_band_mask=mask,
        frequency_tensor_cal=cal,
        tx_positions=coords["tx_positions_actual"].astype(np.float64),
        rx_positions=coords["rx_positions_actual_canonical"].astype(np.float64),
        fda_center_frequencies=np.asarray(scenario.fda.frequencies, dtype=np.float64),
        metadata=metadata,
        tx_positions_requested=coords["tx_positions_requested"],
        rx_positions_requested=coords["rx_positions_requested"],
        tx_positions_actual=coords["tx_positions_actual"],
        rx_positions_actual=coords["rx_positions_actual"],
        position_quantization_error_tx=coords["position_quantization_error_tx"],
        position_quantization_error_rx=coords["position_quantization_error_rx"],
        coordinate_warnings=coords["coordinate_warnings"],
    )


def _axis_compatible(a: Snapshot, b: Snapshot) -> bool:
    return (
        a.time_traces.shape == b.time_traces.shape
        and np.array_equal(a.time, b.time)
        and np.array_equal(a.frequencies, b.frequencies)
        and np.array_equal(a.fda_center_frequencies, b.fda_center_frequencies)
        and np.allclose(a.tx_positions, b.tx_positions)
        and np.allclose(a.rx_positions, b.rx_positions)
    )


def subtract_background(target: Snapshot, background: Snapshot, calibrated: bool = False) -> np.ndarray:
    if not _axis_compatible(target, background):
        raise ProcessingError("target/background snapshots have incompatible axes or acquisition metadata")
    a = target.frequency_tensor_cal if calibrated else target.frequency_tensor_raw
    b = background.frequency_tensor_cal if calibrated else background.frequency_tensor_raw
    if a is None or b is None:
        raise ProcessingError("calibrated subtraction requested but calibrated tensors are unavailable")
    return a - b
