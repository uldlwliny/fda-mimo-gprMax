"""Inspect real run products and generate diagnostic reports."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import h5py
import numpy as np

from .log_analysis import collect_run_log_summaries, summarize_numerical_dispersion


DECISIONS = [
    "NOT_ACCEPTED",
    "ACCEPTED_FOR_ENGINEERING_SMOKE",
    "ACCEPTED_FOR_REAL_FULLWAVE_TARGET_SNAPSHOT",
    "ACCEPTED_FOR_TARGET_BACKGROUND_SCATTER",
    "ACCEPTED_FOR_STAGE1_REAL_VALIDATION",
]


@dataclass(frozen=True)
class InspectRunResult:
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"summary": str(self.summary_path), "report": str(self.report_path), "decision": self.summary.get("decision"), "ok": self.summary.get("decision") != "NOT_ACCEPTED"}


def _mpl():
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    return plt


def _json_from_dataset(h5: h5py.File, path: str, default: Any = None) -> Any:
    if path not in h5:
        return default
    raw = h5[path][()]
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(str(raw))
    except json.JSONDecodeError:
        return default


def _read_snapshot(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with h5py.File(path, "r") as h5:
        out: dict[str, Any] = {
            "path": str(path),
            "time_traces": h5["/snapshot/time_traces"][...] if "/snapshot/time_traces" in h5 else None,
            "frequency_tensor_raw": h5["/snapshot/frequency_tensor_raw"][...] if "/snapshot/frequency_tensor_raw" in h5 else None,
            "frequency_tensor_cal": h5["/snapshot/frequency_tensor_cal"][...] if "/snapshot/frequency_tensor_cal" in h5 else None,
            "source_spectra": h5["/snapshot/source_spectra"][...] if "/snapshot/source_spectra" in h5 else None,
            "valid_band_mask": h5["/snapshot/valid_band_mask"][...] if "/snapshot/valid_band_mask" in h5 else None,
            "time": h5["/axis/time"][...] if "/axis/time" in h5 else None,
            "frequencies": h5["/axis/frequencies"][...] if "/axis/frequencies" in h5 else None,
            "fda_center_frequencies": h5["/axis/fda_center_frequencies"][...] if "/axis/fda_center_frequencies" in h5 else None,
            "tx_positions": h5["/axis/tx_positions"][...] if "/axis/tx_positions" in h5 else None,
            "rx_positions": h5["/axis/rx_positions"][...] if "/axis/rx_positions" in h5 else None,
            "tx_positions_requested": h5["/axis/tx_positions_requested"][...] if "/axis/tx_positions_requested" in h5 else None,
            "rx_positions_requested": h5["/axis/rx_positions_requested"][...] if "/axis/rx_positions_requested" in h5 else None,
            "tx_positions_actual": h5["/axis/tx_positions_actual"][...] if "/axis/tx_positions_actual" in h5 else None,
            "rx_positions_actual": h5["/axis/rx_positions_actual"][...] if "/axis/rx_positions_actual" in h5 else None,
            "domain": h5["/scene/domain"][...] if "/scene/domain" in h5 else None,
            "grid_spacing": h5["/scene/grid_spacing"][...] if "/scene/grid_spacing" in h5 else None,
            "metadata": _json_from_dataset(h5, "/metadata/config", {}),
            "run_evidence": _json_from_dataset(h5, "/metadata/run_evidence", {}),
            "processing_metrics": _json_from_dataset(h5, "/metadata/processing_metrics", {}),
            "numerical_dispersion": _json_from_dataset(h5, "/metadata/numerical_dispersion", {}),
        }
    return out


def _read_scatter(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with h5py.File(path, "r") as h5:
        summary = _json_from_dataset(h5, "/metadata/subtraction_summary", {})
        return {
            "path": str(path),
            "time_traces_shape": list(h5["/scatter/time_traces"].shape) if "/scatter/time_traces" in h5 else None,
            "frequency_tensor_raw_shape": list(h5["/scatter/frequency_tensor_raw"].shape) if "/scatter/frequency_tensor_raw" in h5 else None,
            "summary": summary,
        }


def _variant_summary(scene_dir: Path, variant: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    vdir = scene_dir / variant
    raw_files = sorted((vdir / "raw").glob("tx_*.out"))
    config_files = sorted((vdir / "config").glob("generated_tx_*.in"))
    snapshot_path = vdir / "processed" / "snapshot.h5"
    snapshot = _read_snapshot(snapshot_path)
    logs = collect_run_log_summaries(vdir / "logs") if (vdir / "logs").exists() else []
    if snapshot is not None and raw_files:
        stage = "real"
    elif config_files or (vdir / "logs" / "run_manifest.json").exists():
        stage = "dry-run"
    elif vdir.exists():
        stage = "incomplete"
    else:
        stage = "absent"
    tensor = {}
    if snapshot and snapshot.get("time_traces") is not None:
        yt = snapshot["time_traces"]
        yf = snapshot["frequency_tensor_raw"]
        tensor = {
            "time_traces_shape": list(yt.shape),
            "frequency_tensor_raw_shape": list(yf.shape) if yf is not None else None,
            "frequency_tensor_cal_shape": list(snapshot["frequency_tensor_cal"].shape) if snapshot.get("frequency_tensor_cal") is not None else None,
            "nan_count_cal": int(np.isnan(snapshot["frequency_tensor_cal"]).sum()) if snapshot.get("frequency_tensor_cal") is not None else 0,
            "channel_energy": np.linalg.norm(yt, axis=2).tolist(),
            "peak_time_index": np.argmax(np.abs(yt), axis=2).astype(int).tolist(),
        }
    summary = {
        "path": str(vdir),
        "has_raw": bool(raw_files),
        "raw_count": len(raw_files),
        "has_processed": snapshot is not None,
        "has_npz": (vdir / "processed" / "snapshot.npz").exists(),
        "has_config": bool(config_files),
        "config_count": len(config_files),
        "run_stage": stage,
        "logs_count": len(logs),
        "tensor": tensor,
        "log_summaries": [item.to_dict() for item in logs],
        "numerical_dispersion": summarize_numerical_dispersion(logs).to_dict(),
    }
    return summary, snapshot


def _fda_summary(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not snapshot:
        return {"status": "MISSING", "configured_center_frequencies_hz": []}
    freqs = np.asarray(snapshot.get("fda_center_frequencies"), dtype=float)
    metrics = snapshot.get("processing_metrics", {}) or {}
    source_spectra = snapshot.get("source_spectra")
    fft_freqs = snapshot.get("frequencies")
    peaks = []
    if source_spectra is not None and fft_freqs is not None and len(fft_freqs):
        for row in np.abs(source_spectra):
            peaks.append(float(fft_freqs[int(np.argmax(row))]))
    if freqs.size > 1:
        df = float(np.median(np.diff(freqs)))
        expected = freqs[0] + np.arange(freqs.size) * df
        law_error = float(np.max(np.abs(freqs - expected)))
    else:
        df = 0.0
        law_error = 0.0
    can_resolve = bool(metrics.get("can_resolve_fda_step_by_fft", False))
    status = "PASS-CONFIG"
    spectral_status = "PASS-SPECTRAL" if can_resolve else "WARNING-SPECTRAL-UNRESOLVED"
    if law_error > 1e-6:
        status = "FAIL"
    return {
        "status": status,
        "spectral_status": spectral_status,
        "configured_center_frequencies_hz": freqs.tolist(),
        "delta_f_hz": df,
        "law_max_error_hz": law_error,
        "measured_spectral_peaks_hz": peaks,
        "fft_bin_spacing_hz": metrics.get("fft_bin_spacing_hz"),
        "fft_resolution_ratio": metrics.get("fft_resolution_ratio"),
        "can_resolve_fda_step_by_fft": can_resolve,
    }


def _coordinate_summary(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not snapshot:
        return {"actual_positions_available": False}
    req_tx = snapshot.get("tx_positions_requested")
    act_tx = snapshot.get("tx_positions_actual")
    req_rx = snapshot.get("rx_positions_requested")
    act_rx = snapshot.get("rx_positions_actual")
    max_tx = None
    max_rx = None
    if req_tx is not None and act_tx is not None:
        max_tx = float(np.nanmax(np.abs(np.asarray(act_tx) - np.asarray(req_tx))))
    if req_rx is not None and act_rx is not None:
        max_rx = float(np.nanmax(np.abs(np.asarray(act_rx) - np.asarray(req_rx)[None, :, :])))
    grid = snapshot.get("grid_spacing")
    grid_min = float(np.nanmin(grid)) if grid is not None and np.asarray(grid).size else None
    return {
        "actual_positions_available": act_tx is not None and act_rx is not None,
        "max_requested_actual_tx_error_m": max_tx,
        "max_requested_actual_rx_error_m": max_rx,
        "grid_quantization_warning": bool((max_tx or 0.0) > 1e-9 or (max_rx or 0.0) > 1e-9),
        "grid_spacing_min_m": grid_min,
    }


def _write_csv(path: Path, rows: Iterable[Iterable[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)


def _fig_matrix(matrix: np.ndarray, path: Path, title: str, xlabel: str = "Rx index", ylabel: str = "Tx index") -> None:
    plt = _mpl()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(5, 4))
    im = ax.imshow(matrix, aspect="auto", origin="lower")
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    fig.colorbar(im, ax=ax)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _write_artifacts(summary: dict[str, Any], snapshots: dict[str, dict[str, Any] | None], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    tables = out_dir / "tables"
    figures = out_dir / "figures"
    target = snapshots.get("target") or next((s for s in snapshots.values() if s), None)
    if target and target.get("time_traces") is not None:
        yt = target["time_traces"]
        energy = np.linalg.norm(yt, axis=2)
        peak_idx = np.argmax(np.abs(yt), axis=2)
        time = target.get("time")
        peak_time = time[peak_idx] if time is not None else peak_idx
        _write_csv(tables / "channel_energy_matrix.csv", [["tx/rx", *range(energy.shape[1])], *[[i, *row] for i, row in enumerate(energy)]])
        _write_csv(tables / "peak_time_matrix.csv", [["tx/rx", *range(peak_time.shape[1])], *[[i, *row] for i, row in enumerate(peak_time)]])
        _fig_matrix(energy, figures / "channel_energy_matrix.png", "Channel energy matrix")
        _fig_matrix(peak_time, figures / "peak_time_matrix.png", "Peak time matrix")
        if target.get("valid_band_mask") is not None:
            _fig_matrix(target["valid_band_mask"].astype(float), figures / "valid_band_mask.png", "Valid-band mask", xlabel="Frequency bin")
        if target.get("source_spectra") is not None and target.get("frequencies") is not None:
            plt = _mpl()
            fig, ax = plt.subplots(figsize=(6, 4))
            for i, spec in enumerate(np.abs(target["source_spectra"])):
                ax.plot(target["frequencies"], spec, label=f"Tx {i}")
            ax.set_xlabel("Frequency (Hz)")
            ax.set_ylabel("|S(f)|")
            ax.set_title("Source spectra with FFT bins")
            ax.legend(fontsize=8)
            fig.tight_layout()
            figures.mkdir(parents=True, exist_ok=True)
            fig.savefig(figures / "source_spectra_with_fft_bins.png", dpi=160)
            plt.close(fig)
        if target.get("tx_positions_requested") is not None and target.get("tx_positions_actual") is not None:
            req = np.asarray(target["tx_positions_requested"])
            act = np.asarray(target["tx_positions_actual"])
            plt = _mpl()
            fig, ax = plt.subplots(figsize=(5, 4))
            ax.scatter(req[:, 0], req[:, 1], marker="o", label="requested Tx")
            ax.scatter(act[:, 0], act[:, 1], marker="x", label="actual Tx")
            ax.set_xlabel("x (m)")
            ax.set_ylabel("y (m)")
            ax.set_title("Requested vs actual geometry")
            ax.legend()
            fig.tight_layout()
            figures.mkdir(parents=True, exist_ok=True)
            fig.savefig(figures / "requested_vs_actual_geometry.png", dpi=160)
            plt.close(fig)
    fda = summary.get("fda", {})
    _write_csv(tables / "fda_frequency_evidence.csv", [["tx", "configured_hz", "spectral_peak_hz"], *[[i, f, (fda.get("measured_spectral_peaks_hz") or [None] * len(fda.get("configured_center_frequencies_hz", [])))[i]] for i, f in enumerate(fda.get("configured_center_frequencies_hz", []))]])
    summary_path = out_dir / "run_analysis_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    report_path = out_dir / "run_analysis_report.md"
    report_path.write_text(_render_report(summary), encoding="utf-8")
    return summary_path, report_path


def _render_report(summary: dict[str, Any]) -> str:
    lines = [
        f"# Real gprMax Run Analysis: {summary.get('scene')}",
        "",
        f"**Decision:** `{summary.get('decision')}`",
        "",
        "## Run overview",
    ]
    for name, data in summary.get("variants", {}).items():
        lines.append(f"- `{name}`: stage={data.get('run_stage')}, raw={data.get('raw_count')}, processed={data.get('has_processed')}")
    lines += [
        "",
        "## FDA scheduling evidence",
        f"- Status: `{summary.get('fda', {}).get('status')}` / `{summary.get('fda', {}).get('spectral_status')}`",
        f"- Configured center frequencies (Hz): {summary.get('fda', {}).get('configured_center_frequencies_hz')}",
        f"- FFT bin spacing (Hz): {summary.get('fda', {}).get('fft_bin_spacing_hz')}",
        "",
        "## MIMO tensor evidence",
        f"- Tensor: {summary.get('tensor')}",
        "",
        "## Coordinate consistency",
        f"- {summary.get('coordinates')}",
        "",
        "## Numerical dispersion",
        f"- {summary.get('numerical_dispersion')}",
        "",
        "## Target/background/scatter status",
        f"- Scatter: {summary.get('scatter')}",
        "",
        "## Decision and next actions",
    ]
    for item in summary.get("recommended_next_actions", []):
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def inspect_run(scene_run_dir: str | Path, variants: list[str] | None = None, with_scatter: bool = False, paper_mode: bool = False, output: str | Path | None = None) -> InspectRunResult:
    scene_dir = Path(scene_run_dir)
    variants = variants or ["target", "background"]
    variant_summaries: dict[str, Any] = {}
    snapshots: dict[str, dict[str, Any] | None] = {}
    for variant in variants:
        summary, snapshot = _variant_summary(scene_dir, variant)
        variant_summaries[variant] = summary
        snapshots[variant] = snapshot
    scatter_path = scene_dir / "scatter" / "processed" / "scatter_snapshot.h5"
    scatter = _read_scatter(scatter_path) if with_scatter or scatter_path.exists() else None
    target_snapshot = snapshots.get("target") or next((s for s in snapshots.values() if s), None)
    fda = _fda_summary(target_snapshot)
    coords = _coordinate_summary(target_snapshot)
    tensor = variant_summaries.get("target", {}).get("tensor", {})
    dispersion = (target_snapshot or {}).get("numerical_dispersion") or variant_summaries.get("target", {}).get("numerical_dispersion", {})

    target_complete = bool(variant_summaries.get("target", {}).get("has_raw") and variant_summaries.get("target", {}).get("has_processed"))
    background_complete = bool(variant_summaries.get("background", {}).get("has_raw") and variant_summaries.get("background", {}).get("has_processed"))
    scatter_complete = scatter is not None
    decision = "NOT_ACCEPTED"
    if target_complete:
        decision = "ACCEPTED_FOR_REAL_FULLWAVE_TARGET_SNAPSHOT"
    elif any(v.get("has_config") for v in variant_summaries.values()):
        decision = "ACCEPTED_FOR_ENGINEERING_SMOKE"
    if target_complete and background_complete and scatter_complete:
        decision = "ACCEPTED_FOR_TARGET_BACKGROUND_SCATTER"
    if paper_mode and decision == "ACCEPTED_FOR_REAL_FULLWAVE_TARGET_SNAPSHOT" and (fda.get("spectral_status") != "PASS-SPECTRAL" or dispersion.get("risk") in {"HIGH", "SEVERE"}):
        decision = "ACCEPTED_FOR_ENGINEERING_SMOKE"

    next_actions: list[str] = []
    if not background_complete:
        next_actions.append("run background variant")
    if target_complete and background_complete and not scatter_complete:
        next_actions.append("generate scatter snapshot")
    if fda.get("spectral_status") == "WARNING-SPECTRAL-UNRESOLVED":
        next_actions.append("increase time_window or use configured center-frequency evidence")
    if coords.get("grid_quantization_warning"):
        next_actions.append("align Tx/Rx coordinates with grid or reduce grid spacing")
    if dispersion.get("risk") in {"HIGH", "SEVERE"}:
        next_actions.append("reduce numerical dispersion by refining grid or lowering frequency")

    summary = {
        "scene": scene_dir.name,
        "decision": decision,
        "variants": variant_summaries,
        "tensor": tensor,
        "fda": fda,
        "coordinates": coords,
        "numerical_dispersion": dispersion,
        "scatter": scatter or {"present": False},
        "real_run_checks": {
            "V1": f"{fda.get('status')}:{fda.get('spectral_status')}",
            "V2": "PASS" if tensor else "NOT_EVALUATED",
            "V3": "PASS" if coords.get("actual_positions_available") else "WARNING_ACTUAL_POSITIONS_UNAVAILABLE",
            "V4": "PASS_WITH_WARNINGS" if dispersion.get("warning") else "PASS",
            "V5": "NOT_EVALUATED_REQUIRES_DF_ZERO_BASELINE",
            "V6": "NOT_EVALUATED_REQUIRES_DEPTH_SWEEP",
            "V7": "NOT_EVALUATED_REQUIRES_DICTIONARY_CANDIDATES",
            "V8": "NOT_EVALUATED_REQUIRES_RANDOM_MEDIUM_ENSEMBLE",
        },
        "recommended_next_actions": next_actions,
    }
    out_dir = Path(output) if output else scene_dir / "diagnostics"
    summary_path, report_path = _write_artifacts(summary, snapshots, out_dir)
    return InspectRunResult(summary_path=summary_path, report_path=report_path, summary=summary)
