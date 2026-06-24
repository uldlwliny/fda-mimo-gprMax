"""Parse gprMax HDF5 receiver outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import h5py
import numpy as np


class OutputParseError(RuntimeError):
    """Raised when a gprMax output file cannot be parsed."""


@dataclass(frozen=True)
class OutputInfo:
    path: Path
    iterations: int
    dt: float
    nrx: int
    gprmax_version: str
    available_components: dict[int, list[str]]
    receiver_positions: np.ndarray
    source_position: np.ndarray | None = None
    warnings: list[str] = field(default_factory=list)
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TxTrace:
    tx_index: int
    path: Path
    component: str
    traces: np.ndarray  # [Nr, Lt]
    dt: float
    time: np.ndarray
    receiver_positions: np.ndarray
    attrs: dict[str, Any]
    source_position_actual: np.ndarray | None = None
    receiver_positions_actual: np.ndarray | None = None
    hdf5_attrs: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


# Backward-compatible alias used by the new OpenSpec wording.
ParsedTxOutput = TxTrace


def _decode_attr(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def _attrs_dict(obj: h5py.Group | h5py.File) -> dict[str, Any]:
    return {str(k): _decode_attr(v) for k, v in obj.attrs.items()}


def _position_from_attrs(attrs: h5py.AttributeManager) -> np.ndarray | None:
    for key in ("Position", "position", "Coordinates", "coordinates"):
        if key in attrs:
            arr = np.asarray(attrs[key], dtype=np.float64).reshape(-1)
            if arr.size >= 3:
                return arr[:3].astype(np.float64)
    return None


def _read_source_position(h5: h5py.File) -> tuple[np.ndarray | None, list[str]]:
    warnings: list[str] = []
    candidate_groups: list[h5py.Group] = []
    for root in ("/srcs", "/sources"):
        if root in h5 and isinstance(h5[root], h5py.Group):
            for name in sorted(h5[root].keys()):
                obj = h5[root][name]
                if isinstance(obj, h5py.Group):
                    candidate_groups.append(obj)
    # Some gprMax-like mock files may store the source position directly on root attrs.
    root_pos = _position_from_attrs(h5.attrs)
    if root_pos is not None:
        return root_pos, warnings
    for group in candidate_groups:
        pos = _position_from_attrs(group.attrs)
        if pos is not None:
            return pos, warnings
    warnings.append("actual source position not found in gprMax HDF5")
    return None, warnings


def inspect_output(path: str | Path) -> OutputInfo:
    path = Path(path)
    if not path.exists():
        raise OutputParseError(f"output file does not exist: {path}")
    warnings: list[str] = []
    with h5py.File(path, "r") as h5:
        try:
            iterations = int(h5.attrs["Iterations"])
            dt = float(h5.attrs["dt"])
            nrx = int(h5.attrs["nrx"])
        except KeyError as exc:
            raise OutputParseError(f"missing required gprMax attribute {exc!s} in {path}") from exc
        version = str(_decode_attr(h5.attrs.get("gprMax", "unknown")))
        attrs = _attrs_dict(h5)
        components: dict[int, list[str]] = {}
        positions: list[list[float]] = []
        for rx in range(1, nrx + 1):
            group_name = f"/rxs/rx{rx}"
            if group_name not in h5:
                raise OutputParseError(f"missing receiver group {group_name} in {path}")
            group = h5[group_name]
            components[rx - 1] = sorted(list(group.keys()))
            pos = _position_from_attrs(group.attrs)
            if pos is None:
                warnings.append(f"actual receiver position missing for rx{rx} in {path}")
                positions.append([np.nan, np.nan, np.nan])
            else:
                positions.append([float(v) for v in pos])
        source_position, source_warnings = _read_source_position(h5)
        warnings.extend(source_warnings)
    return OutputInfo(
        path=path,
        iterations=iterations,
        dt=dt,
        nrx=nrx,
        gprmax_version=version,
        available_components=components,
        receiver_positions=np.asarray(positions, dtype=float),
        source_position=source_position,
        warnings=warnings,
        attrs=attrs,
    )


def extract_component(path: str | Path, component: str, expected_nrx: int | None = None, tx_index: int = 0) -> TxTrace:
    path = Path(path)
    info = inspect_output(path)
    if expected_nrx is not None and info.nrx != expected_nrx:
        raise OutputParseError(f"receiver count mismatch in {path}: expected {expected_nrx}, got {info.nrx}")
    traces: list[np.ndarray] = []
    hdf5_attrs: dict[str, Any] = dict(info.attrs)
    with h5py.File(path, "r") as h5:
        attrs = {str(k): _decode_attr(v) for k, v in h5.attrs.items()}
        for rx in range(1, info.nrx + 1):
            ds = f"/rxs/rx{rx}/{component}"
            if ds not in h5:
                available = sorted(list(h5[f"/rxs/rx{rx}"].keys())) if f"/rxs/rx{rx}" in h5 else []
                raise OutputParseError(f"missing dataset {ds} in {path}; available={available}")
            arr = np.asarray(h5[ds], dtype=np.float64)
            if arr.ndim != 1:
                raise OutputParseError(f"dataset {ds} in {path} must be 1-D")
            traces.append(arr)
    lengths = {len(arr) for arr in traces}
    if len(lengths) != 1:
        raise OutputParseError(f"inconsistent trace lengths in {path}: {sorted(lengths)}")
    lt = lengths.pop()
    if lt != info.iterations:
        raise OutputParseError(f"trace length {lt} does not match Iterations {info.iterations} in {path}")
    time = np.arange(lt, dtype=np.float64) * info.dt
    return TxTrace(
        tx_index=tx_index,
        path=path,
        component=component,
        traces=np.stack(traces, axis=0),
        dt=info.dt,
        time=time,
        receiver_positions=info.receiver_positions,
        attrs=attrs,
        source_position_actual=info.source_position,
        receiver_positions_actual=info.receiver_positions,
        hdf5_attrs=hdf5_attrs,
        warnings=info.warnings,
    )


def parse_tx_outputs(paths: Sequence[str | Path], component: str, expected_nrx: int | None = None) -> list[TxTrace]:
    outputs = [extract_component(path, component, expected_nrx=expected_nrx, tx_index=i) for i, path in enumerate(paths)]
    if not outputs:
        raise OutputParseError("no output paths provided")
    dt0 = outputs[0].dt
    lt0 = outputs[0].traces.shape[1]
    for item in outputs[1:]:
        if not np.isclose(item.dt, dt0, rtol=0, atol=1e-18):
            raise OutputParseError(f"incompatible dt for tx {item.tx_index}: {item.dt} != {dt0}")
        if item.traces.shape[1] != lt0:
            raise OutputParseError(f"incompatible sample count for tx {item.tx_index}: {item.traces.shape[1]} != {lt0}")
    return outputs
