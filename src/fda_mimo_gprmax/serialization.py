"""Processed snapshot serialization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from .processing import Snapshot


def _write_json_dataset(group: h5py.Group, name: str, data: Any) -> None:
    group.create_dataset(name, data=json.dumps(data, ensure_ascii=False, sort_keys=True))


def _array_or_default(value: np.ndarray | None, fallback: np.ndarray) -> np.ndarray:
    return fallback if value is None else value


def write_snapshot_h5(snapshot: Snapshot, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as h5:
        g = h5.create_group("snapshot")
        g.create_dataset("time_traces", data=snapshot.time_traces.astype(np.float32), compression="gzip")
        g.create_dataset("frequency_tensor_raw", data=snapshot.frequency_tensor_raw.astype(np.complex64), compression="gzip")
        if snapshot.frequency_tensor_cal is not None:
            g.create_dataset("frequency_tensor_cal", data=snapshot.frequency_tensor_cal.astype(np.complex64), compression="gzip")
        g.create_dataset("source_spectra", data=snapshot.source_spectra.astype(np.complex64), compression="gzip")
        g.create_dataset("valid_band_mask", data=snapshot.valid_band_mask.astype(bool), compression="gzip")
        if snapshot.scatter_tensor is not None:
            g.create_dataset("scatter_tensor", data=snapshot.scatter_tensor.astype(np.complex64), compression="gzip")

        axis = h5.create_group("axis")
        axis.create_dataset("tx_positions", data=snapshot.tx_positions.astype(np.float64))
        axis.create_dataset("rx_positions", data=snapshot.rx_positions.astype(np.float64))
        axis.create_dataset("tx_positions_requested", data=_array_or_default(snapshot.tx_positions_requested, snapshot.tx_positions).astype(np.float64))
        axis.create_dataset("rx_positions_requested", data=_array_or_default(snapshot.rx_positions_requested, snapshot.rx_positions).astype(np.float64))
        axis.create_dataset("tx_positions_actual", data=_array_or_default(snapshot.tx_positions_actual, snapshot.tx_positions).astype(np.float64))
        axis.create_dataset("rx_positions_actual", data=_array_or_default(snapshot.rx_positions_actual, snapshot.rx_positions[None, :, :]).astype(np.float64))
        axis.create_dataset("position_quantization_error_tx", data=_array_or_default(snapshot.position_quantization_error_tx, np.zeros_like(snapshot.tx_positions)).astype(np.float64))
        rx_err_fallback = np.zeros((snapshot.tx_positions.shape[0], snapshot.rx_positions.shape[0], 3), dtype=np.float64)
        axis.create_dataset("position_quantization_error_rx", data=_array_or_default(snapshot.position_quantization_error_rx, rx_err_fallback).astype(np.float64))
        axis.create_dataset("time", data=snapshot.time.astype(np.float64))
        axis.create_dataset("frequencies", data=snapshot.frequencies.astype(np.float64))
        axis.create_dataset("fda_center_frequencies", data=snapshot.fda_center_frequencies.astype(np.float64))

        scene = h5.create_group("scene")
        meta_scene = snapshot.metadata.get("scene", {})
        domain = snapshot.metadata.get("domain", {})
        grid = snapshot.metadata.get("grid", {})
        _write_json_dataset(scene, "target_params", snapshot.metadata.get("variants", []))
        _write_json_dataset(scene, "material_table", meta_scene.get("materials", []))
        scene.create_dataset("domain", data=np.asarray(domain.get("size", []), dtype=np.float64))
        scene.create_dataset("grid_spacing", data=np.asarray(grid.get("spacing", []), dtype=np.float64))

        meta = h5.create_group("metadata")
        _write_json_dataset(meta, "config", snapshot.metadata)
        meta.create_dataset("config_yaml", data=json.dumps(snapshot.metadata, ensure_ascii=False, sort_keys=True))
        meta.create_dataset("adapter_version", data=str(snapshot.metadata.get("adapter_version", "0.1.0")))
        meta.create_dataset("gprmax_version", data=str(snapshot.metadata.get("gprmax_version", "unknown")))
        meta.create_dataset("random_seed", data=int(snapshot.metadata.get("random_seed", 0)))
        meta.create_dataset("axis_convention", data=str(snapshot.metadata.get("axis_convention", "actual positions preferred; requested positions stored separately")))
        meta.create_dataset("actual_positions_available", data=bool(snapshot.metadata.get("coordinates", {}).get("actual_positions_available", False)))
        _write_json_dataset(meta, "coordinate_warnings", snapshot.coordinate_warnings)
        _write_json_dataset(meta, "checksums", {
            "config_checksum": snapshot.metadata.get("config_checksum"),
            "input_file_checksums": snapshot.metadata.get("run_evidence", {}).get("input_file_checksums", []),
            "raw_output_checksums": snapshot.metadata.get("run_evidence", {}).get("raw_output_checksums", []),
        })
        _write_json_dataset(meta, "run_evidence", snapshot.metadata.get("run_evidence", {}))
        _write_json_dataset(meta, "processing_metrics", snapshot.metadata.get("processing_metrics", {}))
        _write_json_dataset(meta, "media", snapshot.metadata.get("media", {}))
        _write_json_dataset(meta, "numerical_dispersion", snapshot.metadata.get("run_evidence", {}).get("numerical_dispersion", {}))
    return path


def write_snapshot_npz(snapshot: Snapshot, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        time_traces=snapshot.time_traces,
        frequency_tensor_raw=snapshot.frequency_tensor_raw,
        frequency_tensor_cal=snapshot.frequency_tensor_cal if snapshot.frequency_tensor_cal is not None else np.asarray([]),
        source_spectra=snapshot.source_spectra,
        valid_band_mask=snapshot.valid_band_mask,
        tx_positions=snapshot.tx_positions,
        rx_positions=snapshot.rx_positions,
        tx_positions_requested=_array_or_default(snapshot.tx_positions_requested, snapshot.tx_positions),
        rx_positions_requested=_array_or_default(snapshot.rx_positions_requested, snapshot.rx_positions),
        tx_positions_actual=_array_or_default(snapshot.tx_positions_actual, snapshot.tx_positions),
        rx_positions_actual=_array_or_default(snapshot.rx_positions_actual, snapshot.rx_positions[None, :, :]),
        position_quantization_error_tx=_array_or_default(snapshot.position_quantization_error_tx, np.zeros_like(snapshot.tx_positions)),
        position_quantization_error_rx=_array_or_default(snapshot.position_quantization_error_rx, np.zeros((snapshot.tx_positions.shape[0], snapshot.rx_positions.shape[0], 3))),
        time=snapshot.time,
        frequencies=snapshot.frequencies,
        fda_center_frequencies=snapshot.fda_center_frequencies,
        metadata=json.dumps(snapshot.metadata, ensure_ascii=False, sort_keys=True),
    )
    return path


def write_processed_snapshot(snapshot: Snapshot, processed_dir: str | Path, export_npz: bool = True) -> dict[str, Path]:
    processed_dir = Path(processed_dir)
    paths = {"h5": write_snapshot_h5(snapshot, processed_dir / "snapshot.h5")}
    if export_npz:
        paths["npz"] = write_snapshot_npz(snapshot, processed_dir / "snapshot.npz")
    return paths
