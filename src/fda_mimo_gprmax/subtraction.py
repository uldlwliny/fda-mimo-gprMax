"""Target/background snapshot subtraction for scatter products."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np


class SubtractionError(RuntimeError):
    """Raised when target/background subtraction cannot be performed."""


@dataclass(frozen=True)
class ScatterResult:
    output_path: Path
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"output_path": str(self.output_path), "summary": self.summary}


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


def _load_snapshot(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise SubtractionError(f"snapshot does not exist: {path}")
    with h5py.File(path, "r") as h5:
        required = [
            "/snapshot/time_traces",
            "/snapshot/frequency_tensor_raw",
            "/snapshot/source_spectra",
            "/snapshot/valid_band_mask",
            "/axis/time",
            "/axis/frequencies",
            "/axis/fda_center_frequencies",
            "/axis/tx_positions",
            "/axis/rx_positions",
        ]
        for item in required:
            if item not in h5:
                raise SubtractionError(f"missing required dataset {item} in {path}")
        cal = h5["/snapshot/frequency_tensor_cal"][...] if "/snapshot/frequency_tensor_cal" in h5 else None
        return {
            "path": path,
            "time_traces": h5["/snapshot/time_traces"][...],
            "frequency_tensor_raw": h5["/snapshot/frequency_tensor_raw"][...],
            "frequency_tensor_cal": cal,
            "source_spectra": h5["/snapshot/source_spectra"][...],
            "valid_band_mask": h5["/snapshot/valid_band_mask"][...].astype(bool),
            "time": h5["/axis/time"][...],
            "frequencies": h5["/axis/frequencies"][...],
            "fda_center_frequencies": h5["/axis/fda_center_frequencies"][...],
            "tx_positions": h5["/axis/tx_positions"][...],
            "rx_positions": h5["/axis/rx_positions"][...],
            "tx_positions_actual": h5["/axis/tx_positions_actual"][...] if "/axis/tx_positions_actual" in h5 else h5["/axis/tx_positions"][...],
            "rx_positions_actual": h5["/axis/rx_positions_actual"][...] if "/axis/rx_positions_actual" in h5 else h5["/axis/rx_positions"][...],
            "scene_domain": h5["/scene/domain"][...] if "/scene/domain" in h5 else np.asarray([]),
            "scene_grid_spacing": h5["/scene/grid_spacing"][...] if "/scene/grid_spacing" in h5 else np.asarray([]),
            "metadata": _json_from_dataset(h5, "/metadata/config", {}),
        }


def _require_same(name: str, a: np.ndarray, b: np.ndarray, atol: float = 0.0) -> None:
    if a.shape != b.shape:
        raise SubtractionError(f"{name} shape mismatch: {a.shape} != {b.shape}")
    if atol == 0.0:
        ok = np.array_equal(a, b)
    else:
        ok = np.allclose(a, b, rtol=0, atol=atol, equal_nan=True)
    if not ok:
        raise SubtractionError(f"{name} values mismatch")


def validate_pair(target: dict[str, Any], background: dict[str, Any], coordinate_atol: float = 1e-9, source_atol: float = 1e-9) -> list[str]:
    warnings: list[str] = []
    for key in ["time_traces", "frequency_tensor_raw", "source_spectra", "valid_band_mask"]:
        if target[key].shape != background[key].shape:
            raise SubtractionError(f"{key} shape mismatch: {target[key].shape} != {background[key].shape}")
    _require_same("time axis", target["time"], background["time"])
    _require_same("frequency axis", target["frequencies"], background["frequencies"])
    _require_same("FDA center frequencies", target["fda_center_frequencies"], background["fda_center_frequencies"])
    _require_same("Tx positions", target["tx_positions"], background["tx_positions"], atol=coordinate_atol)
    _require_same("Rx positions", target["rx_positions"], background["rx_positions"], atol=coordinate_atol)
    if target["scene_domain"].size and background["scene_domain"].size:
        _require_same("domain", target["scene_domain"], background["scene_domain"], atol=0.0)
    if target["scene_grid_spacing"].size and background["scene_grid_spacing"].size:
        _require_same("grid spacing", target["scene_grid_spacing"], background["scene_grid_spacing"], atol=0.0)
    if not np.allclose(target["source_spectra"], background["source_spectra"], rtol=0, atol=source_atol, equal_nan=True):
        warnings.append("target/background source spectra differ beyond tolerance")
    return warnings


def subtract_snapshots(target_snapshot: str | Path, background_snapshot: str | Path, output_path: str | Path, coordinate_atol: float = 1e-9, source_atol: float = 1e-9) -> ScatterResult:
    target = _load_snapshot(target_snapshot)
    background = _load_snapshot(background_snapshot)
    warnings = validate_pair(target, background, coordinate_atol=coordinate_atol, source_atol=source_atol)

    time_scat = target["time_traces"].astype(np.float32) - background["time_traces"].astype(np.float32)
    raw_scat = target["frequency_tensor_raw"].astype(np.complex64) - background["frequency_tensor_raw"].astype(np.complex64)
    pair_mask = target["valid_band_mask"] & background["valid_band_mask"]
    cal_scat = None
    if target["frequency_tensor_cal"] is not None and background["frequency_tensor_cal"] is not None:
        cal_scat = target["frequency_tensor_cal"].astype(np.complex64) - background["frequency_tensor_cal"].astype(np.complex64)
        invalid = ~pair_mask[:, None, :]
        cal_scat = np.array(cal_scat, copy=True)
        cal_scat[invalid.repeat(cal_scat.shape[1], axis=1)] = np.nan + 1j * np.nan

    target_energy = float(np.linalg.norm(target["time_traces"].ravel()))
    scatter_energy = float(np.linalg.norm(time_scat.ravel()))
    energy_ratio = None if target_energy == 0 else scatter_energy / target_energy
    summary = {
        "target_path": str(target["path"]),
        "background_path": str(background["path"]),
        "time_traces_shape": list(time_scat.shape),
        "frequency_tensor_raw_shape": list(raw_scat.shape),
        "valid_fraction_pair": float(pair_mask.mean()) if pair_mask.size else None,
        "target_energy_fro": target_energy,
        "scatter_energy_fro": scatter_energy,
        "scatter_to_target_energy_ratio": energy_ratio,
        "warnings": warnings,
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(output_path, "w") as h5:
        scatter = h5.create_group("scatter")
        scatter.create_dataset("time_traces", data=time_scat.astype(np.float32), compression="gzip")
        scatter.create_dataset("frequency_tensor_raw", data=raw_scat.astype(np.complex64), compression="gzip")
        if cal_scat is not None:
            scatter.create_dataset("frequency_tensor_cal", data=cal_scat.astype(np.complex64), compression="gzip")
        scatter.create_dataset("valid_band_mask_pair", data=pair_mask.astype(bool), compression="gzip")
        axis = h5.create_group("axis")
        for key in ["time", "frequencies", "fda_center_frequencies", "tx_positions", "rx_positions", "tx_positions_actual", "rx_positions_actual"]:
            axis.create_dataset(key, data=target[key])
        scene = h5.create_group("scene")
        scene.create_dataset("domain", data=target["scene_domain"])
        scene.create_dataset("grid_spacing", data=target["scene_grid_spacing"])
        tgrp = h5.create_group("target")
        tgrp.create_dataset("ref_path", data=str(target["path"]))
        bgrp = h5.create_group("background")
        bgrp.create_dataset("ref_path", data=str(background["path"]))
        meta = h5.create_group("metadata")
        meta.create_dataset("subtraction_summary", data=json.dumps(summary, ensure_ascii=False, sort_keys=True))
        meta.create_dataset("config", data=json.dumps(target["metadata"], ensure_ascii=False, sort_keys=True))
    return ScatterResult(output_path=output_path, summary=summary)


def subtract_scene_run(scene_run_dir: str | Path, target_variant: str = "target", background_variant: str = "background") -> ScatterResult:
    scene_run_dir = Path(scene_run_dir)
    target_snapshot = scene_run_dir / target_variant / "processed" / "snapshot.h5"
    background_snapshot = scene_run_dir / background_variant / "processed" / "snapshot.h5"
    output_path = scene_run_dir / "scatter" / "processed" / "scatter_snapshot.h5"
    return subtract_snapshots(target_snapshot, background_snapshot, output_path)
