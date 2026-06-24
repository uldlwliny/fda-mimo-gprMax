"""Diagnostic figures for processed snapshots."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .processing import Snapshot


def _mpl():
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    return plt


def write_trace_preview(snapshot: Snapshot, path: str | Path) -> Path:
    plt = _mpl()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(snapshot.time, snapshot.time_traces[0, 0], label="tx0-rx0")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Amplitude")
    ax.set_title("Receiver trace preview")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def write_spectrum_preview(snapshot: Snapshot, path: str | Path) -> Path:
    plt = _mpl()
    path = Path(path)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(snapshot.frequencies, np.abs(snapshot.frequency_tensor_raw[0, 0]), label="|Y(tx0,rx0)|")
    ax.plot(snapshot.frequencies, np.abs(snapshot.source_spectra[0]), label="|S(tx0)|", alpha=0.7)
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Magnitude")
    ax.set_title("Spectrum preview")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def write_phase_map(snapshot: Snapshot, path: str | Path) -> Path:
    plt = _mpl()
    path = Path(path)
    fig, ax = plt.subplots(figsize=(7, 4))
    k = min(max(snapshot.frequency_tensor_raw.shape[-1] // 2, 0), snapshot.frequency_tensor_raw.shape[-1] - 1)
    im = ax.imshow(np.angle(snapshot.frequency_tensor_raw[:, :, k]), aspect="auto", origin="lower")
    ax.set_xlabel("Rx index")
    ax.set_ylabel("Tx index")
    ax.set_title(f"Phase map at {snapshot.frequencies[k]:.3g} Hz")
    fig.colorbar(im, ax=ax)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def write_valid_band_mask(snapshot: Snapshot, path: str | Path) -> Path:
    plt = _mpl()
    path = Path(path)
    fig, ax = plt.subplots(figsize=(7, 4))
    im = ax.imshow(snapshot.valid_band_mask, aspect="auto", origin="lower", interpolation="nearest")
    ax.set_xlabel("Frequency bin")
    ax.set_ylabel("Tx index")
    ax.set_title("Valid-band mask")
    fig.colorbar(im, ax=ax)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def write_processing_summary(snapshot: Snapshot, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "time_traces_shape": list(snapshot.time_traces.shape),
        "frequency_tensor_raw_shape": list(snapshot.frequency_tensor_raw.shape),
        "source_spectra_shape": list(snapshot.source_spectra.shape),
        "valid_fraction": float(snapshot.valid_band_mask.mean()),
        "frequency_min": float(snapshot.frequencies.min()) if snapshot.frequencies.size else None,
        "frequency_max": float(snapshot.frequencies.max()) if snapshot.frequencies.size else None,
        "fft_bin_spacing_hz": snapshot.metadata.get("processing_metrics", {}).get("fft_bin_spacing_hz"),
        "fda_delta_f_hz": snapshot.metadata.get("processing_metrics", {}).get("fda_delta_f_hz"),
        "fft_resolution_ratio": snapshot.metadata.get("processing_metrics", {}).get("fft_resolution_ratio"),
        "can_resolve_fda_step_by_fft": snapshot.metadata.get("processing_metrics", {}).get("can_resolve_fda_step_by_fft"),
        "actual_positions_available": snapshot.metadata.get("coordinates", {}).get("actual_positions_available"),
        "max_requested_actual_rx_error_m": snapshot.metadata.get("coordinates", {}).get("max_requested_actual_rx_error_m"),
        "numerical_dispersion": snapshot.metadata.get("run_evidence", {}).get("numerical_dispersion", {}),
    }
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return path


def write_diagnostics(snapshot: Snapshot, figures_dir: str | Path) -> dict[str, Path]:
    figures_dir = Path(figures_dir)
    figures_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "trace_preview": write_trace_preview(snapshot, figures_dir / "trace_preview.png"),
        "spectrum_preview": write_spectrum_preview(snapshot, figures_dir / "spectrum_preview.png"),
        "phase_map": write_phase_map(snapshot, figures_dir / "phase_map.png"),
        "valid_band_mask": write_valid_band_mask(snapshot, figures_dir / "valid_band_mask.png"),
        "summary": write_processing_summary(snapshot, figures_dir / "processing_summary.json"),
    }
    return paths
