"""Scenario configuration models and validation."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import yaml

from .media import (
    ColeColeMedium,
    DebyeApproximation,
    fit_cole_cole_to_debye,
    material_from_mapping,
)


class ValidationError(ValueError):
    """Raised when a scenario is invalid."""


_GPRMAX_BUILTIN_WAVEFORMS = {
    "gaussian",
    "gaussiandot",
    "gaussiandotnorm",
    "gaussiandotdot",
    "gaussiandotdotnorm",
    "gaussianprime",
    "gaussiandoubleprime",
    "ricker",
    "sine",
    "contsine",
    "impulse",
}

_WAVEFORM_ALIASES = {
    "gaussian_dot": "gaussiandot",
    "sinusoid": "sine",
}


def _as_float3(value: Any, name: str) -> tuple[float, float, float]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) != 3
    ):
        raise ValidationError(f"{name} must be a 3-element sequence")
    out = tuple(float(v) for v in value)
    if not all(np.isfinite(out)):
        raise ValidationError(f"{name} must contain finite numbers")
    return out  # type: ignore[return-value]


def _as_positions(value: Any, name: str) -> np.ndarray:
    arr = np.asarray(value, dtype=float)
    if arr.ndim != 2 or arr.shape[1] != 3 or arr.shape[0] == 0:
        raise ValidationError(f"{name} must be a non-empty [N, 3] array")
    if not np.all(np.isfinite(arr)):
        raise ValidationError(f"{name} must contain finite numbers")
    return arr


def _raw_commands(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValidationError("gprMax command sections must be lists of strings")
    return [str(v) for v in value]


def stable_json(data: Any) -> str:
    """Return deterministic JSON used for checksums and metadata."""

    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def checksum_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DomainConfig:
    size: tuple[float, float, float]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "DomainConfig":
        if "size" not in data:
            raise ValidationError("domain.size is required")
        size = _as_float3(data["size"], "domain.size")
        if any(v <= 0 for v in size):
            raise ValidationError("domain.size values must be positive")
        return cls(size=size)

    def to_gprmax(self) -> str:
        return "#domain: {:.9g} {:.9g} {:.9g}".format(*self.size)


@dataclass(frozen=True)
class GridConfig:
    spacing: tuple[float, float, float]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "GridConfig":
        if "spacing" not in data:
            raise ValidationError("grid.spacing is required")
        spacing = _as_float3(data["spacing"], "grid.spacing")
        if any(v <= 0 for v in spacing):
            raise ValidationError("grid.spacing values must be positive")
        return cls(spacing=spacing)

    def to_gprmax(self) -> str:
        return "#dx_dy_dz: {:.9g} {:.9g} {:.9g}".format(*self.spacing)


_C0 = 299792458.0


def estimate_gprmax_dt(
    domain: DomainConfig,
    grid: GridConfig,
) -> float:
    """Estimate the CFL timestep used by gprMax for this adapter grid."""

    sx, sy, sz = domain.size
    dx, dy, dz = grid.spacing

    nx = int(np.rint(sx / dx))
    ny = int(np.rint(sy / dy))
    nz = int(np.rint(sz / dz))

    if nx <= 0 or ny <= 0 or nz <= 0:
        raise ValidationError("domain/grid combination produces an invalid cell count")

    if nx == 1:
        denominator = _C0 * np.sqrt(1.0 / dy**2 + 1.0 / dz**2)

    elif ny == 1:
        denominator = _C0 * np.sqrt(1.0 / dx**2 + 1.0 / dz**2)

    elif nz == 1:
        denominator = _C0 * np.sqrt(1.0 / dx**2 + 1.0 / dy**2)

    else:
        denominator = _C0 * np.sqrt(1.0 / dx**2 + 1.0 / dy**2 + 1.0 / dz**2)

    return float(1.0 / denominator)


@dataclass(frozen=True)
class TimeConfig:
    window: float

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "TimeConfig":
        value = data.get("window", data.get("time_window"))
        if value is None:
            raise ValidationError("time.window is required")
        window = float(value)
        if not np.isfinite(window) or window <= 0:
            raise ValidationError("time.window must be positive")
        return cls(window=window)

    def to_gprmax(self) -> str:
        return f"#time_window: {self.window:.9g}"


@dataclass(frozen=True)
class ArrayConfig:
    tx_positions: np.ndarray
    rx_positions: np.ndarray
    mode: str = "explicit"
    rx_offset: tuple[float, float, float] = (0.0, 0.0, 0.0)
    polarization: str = "z"

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ArrayConfig":
        if "tx_positions" not in data:
            raise ValidationError("array.tx_positions is required")
        tx = _as_positions(data["tx_positions"], "array.tx_positions")
        mode = str(data.get("mode", "explicit")).lower()
        offset = _as_float3(data.get("rx_offset", [0.0, 0.0, 0.0]), "array.rx_offset")
        if mode in {"strict", "strict-colocated", "strict_colocated"}:
            rx = np.array(tx, copy=True)
            mode = "strict"
        elif mode in {"offset", "near", "near-colocated", "near_colocated"}:
            rx = tx + np.asarray(offset, dtype=float)[None, :]
            mode = "offset"
        else:
            if "rx_positions" not in data:
                raise ValidationError(
                    "array.rx_positions is required for explicit mode"
                )
            rx = _as_positions(data["rx_positions"], "array.rx_positions")
            mode = "explicit"
        pol = str(data.get("polarization", "z")).lower()
        if pol not in {"x", "y", "z"}:
            raise ValidationError("array.polarization must be x, y, or z")
        return cls(
            tx_positions=tx,
            rx_positions=rx,
            mode=mode,
            rx_offset=offset,
            polarization=pol,
        )

    @property
    def nt(self) -> int:
        return int(self.tx_positions.shape[0])

    @property
    def nr(self) -> int:
        return int(self.rx_positions.shape[0])

    def metadata(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "rx_offset": list(self.rx_offset),
            "polarization": self.polarization,
            "tx_positions": self.tx_positions.tolist(),
            "rx_positions": self.rx_positions.tolist(),
        }


@dataclass(frozen=True)
class FDAConfig:
    kind: str = "linear"
    f0: float = 1.0e9
    df: float = 0.0
    frequencies: tuple[float, ...] = field(default_factory=tuple)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], nt: int) -> "FDAConfig":
        kind = str(data.get("type", data.get("kind", "linear"))).lower()
        if kind == "linear":
            if "f0" not in data:
                raise ValidationError("fda.f0 is required for linear FDA law")
            f0 = float(data["f0"])
            df = float(data.get("df", 0.0))
            freqs = tuple(f0 + m * df for m in range(nt))
        elif kind in {"list", "explicit"}:
            freqs = tuple(float(v) for v in data.get("frequencies", []))
            if len(freqs) != nt:
                raise ValidationError("fda.frequencies length must equal Nt")
            f0 = freqs[0]
            df = freqs[1] - freqs[0] if len(freqs) > 1 else 0.0
            kind = "explicit"
        else:
            raise ValidationError(f"unsupported FDA law: {kind}")
        if len(freqs) != nt:
            raise ValidationError("FDA frequency count must equal Nt")
        if any((not np.isfinite(f)) or f <= 0 for f in freqs):
            raise ValidationError(
                "FDA center frequencies must be positive finite numbers"
            )
        return cls(kind=kind, f0=f0, df=df, frequencies=freqs)

    def metadata(self) -> dict[str, Any]:
        return {
            "type": self.kind,
            "f0": self.f0,
            "df": self.df,
            "frequencies": list(self.frequencies),
        }


@dataclass(frozen=True)
class WaveformConfig:
    mode: str = "builtin"
    shape: str = "ricker"
    amplitude: float = 1.0
    identifier_prefix: str = "fda_src"
    samples: tuple[float, ...] = field(default_factory=tuple)
    time: tuple[float, ...] = field(default_factory=tuple)

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, Any] | None,
    ) -> "WaveformConfig":
        data = data or {}

        mode = (
            str(data.get("mode", data.get("type", "builtin"))).lower().replace("-", "_")
        )

        shape = str(data.get("shape", data.get("name", "ricker"))).lower()

        shape = _WAVEFORM_ALIASES.get(shape, shape)

        amp = float(data.get("amplitude", 1.0))
        prefix = str(data.get("identifier_prefix", "fda_src"))

        samples = tuple(float(v) for v in data.get("samples", []))

        time = tuple(float(v) for v in data.get("time", []))

        if not np.isfinite(amp):
            raise ValidationError("waveform.amplitude must be finite")

        if mode in {"built_in", "builtin"}:
            mode = "builtin"

            if shape not in _GPRMAX_BUILTIN_WAVEFORMS:
                raise ValidationError(
                    "waveform.shape must be one of "
                    f"{sorted(_GPRMAX_BUILTIN_WAVEFORMS)}"
                )

        elif mode in {
            "excitation",
            "excitation_file",
            "custom",
        }:
            mode = "excitation_file"

            if not samples:
                raise ValidationError(
                    "waveform.samples are required " "for excitation_file mode"
                )

            if time and len(time) != len(samples):
                raise ValidationError(
                    "waveform.time length must match " "waveform.samples"
                )

            if time:
                arr_t = np.asarray(time, dtype=float)

                if not np.all(np.isfinite(arr_t)):
                    raise ValidationError("waveform.time must contain finite values")

                if np.any(np.diff(arr_t) <= 0):
                    raise ValidationError("waveform.time must be strictly increasing")

        else:
            raise ValidationError(f"unsupported waveform mode: {mode}")

        return cls(
            mode=mode,
            shape=shape,
            amplitude=amp,
            identifier_prefix=prefix,
            samples=samples,
            time=time,
        )

    def identifier(self, tx_index: int) -> str:
        return f"{self.identifier_prefix}_{tx_index:03d}"

    def metadata(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "shape": self.shape,
            "amplitude": self.amplitude,
            "identifier_prefix": self.identifier_prefix,
            "num_samples": len(self.samples),
            "has_time": bool(self.time),
        }


@dataclass(frozen=True)
class ReceiverConfig:
    component: str = "Ez"

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "ReceiverConfig":
        comp = str((data or {}).get("component", "Ez"))
        allowed = {"Ex", "Ey", "Ez", "Hx", "Hy", "Hz", "Ix", "Iy", "Iz"}
        if comp not in allowed:
            raise ValidationError(
                f"receiver.component must be one of {sorted(allowed)}"
            )
        return cls(component=comp)


@dataclass(frozen=True)
class SceneConfig:
    title: str = "FDA-MIMO-GPR scene"
    materials: tuple[str, ...] = field(default_factory=tuple)
    geometry: tuple[str, ...] = field(default_factory=tuple)
    geometry_view: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "SceneConfig":
        data = data or {}
        return cls(
            title=str(data.get("title", "FDA-MIMO-GPR scene")),
            materials=tuple(_raw_commands(data.get("materials", []))),
            geometry=tuple(_raw_commands(data.get("geometry", []))),
            geometry_view=bool(data.get("geometry_view", False)),
        )


@dataclass(frozen=True)
class VariantConfig:
    name: str
    geometry: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_obj(cls, name: str, data: Any) -> "VariantConfig":
        if data is None:
            data = {}
        if isinstance(data, Sequence) and not isinstance(data, (str, bytes, Mapping)):
            data = {"geometry": list(data)}
        if not isinstance(data, Mapping):
            raise ValidationError(f"variant {name} must be a mapping or geometry list")
        geom = data.get("geometry", data.get("include_geometry", []))
        meta = {
            k: v for k, v in data.items() if k not in {"geometry", "include_geometry"}
        }
        return cls(name=name, geometry=tuple(_raw_commands(geom)), metadata=meta)


def parse_variants(data: Any) -> tuple[VariantConfig, ...]:
    if data is None:
        return (VariantConfig(name="target"),)
    if isinstance(data, Mapping):
        variants = tuple(VariantConfig.from_obj(str(k), v) for k, v in data.items())
    elif isinstance(data, Sequence) and not isinstance(data, (str, bytes)):
        out = []
        for item in data:
            if not isinstance(item, Mapping) or "name" not in item:
                raise ValidationError(
                    "variant list entries must be mappings with a name"
                )
            out.append(VariantConfig.from_obj(str(item["name"]), item))
        variants = tuple(out)
    else:
        raise ValidationError("variants must be a mapping or list")
    names = [v.name for v in variants]
    if len(set(names)) != len(names):
        raise ValidationError("variant names must be unique")
    if not variants:
        raise ValidationError("at least one variant is required")
    return variants


@dataclass(frozen=True)
class ExecutionConfig:
    executable: tuple[str, ...] = ("python", "-m", "gprMax")
    extra_args: tuple[str, ...] = field(default_factory=tuple)
    gpu: tuple[int, ...] = field(default_factory=tuple)
    mpi: int | None = None
    omp_threads: int | None = None
    failure_policy: str = "stop"

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "ExecutionConfig":
        data = data or {}
        exe = data.get("executable", ["python", "-m", "gprMax"])
        if isinstance(exe, str):
            executable = tuple(shlex.split(exe))
        else:
            executable = tuple(str(v) for v in exe)
        extra = tuple(str(v) for v in data.get("extra_args", []))
        gpu = tuple(int(v) for v in data.get("gpu", []))
        mpi = data.get("mpi")
        omp = data.get("omp_threads")
        policy = str(data.get("failure_policy", "stop")).lower()
        if policy not in {"stop", "continue"}:
            raise ValidationError("execution.failure_policy must be stop or continue")
        return cls(
            executable=executable,
            extra_args=extra,
            gpu=gpu,
            mpi=None if mpi is None else int(mpi),
            omp_threads=None if omp is None else int(omp),
            failure_policy=policy,
        )

    def command_suffix(self) -> list[str]:
        args: list[str] = []
        if self.mpi is not None:
            args += ["-mpi", str(self.mpi)]
        if self.gpu:
            args += ["-gpu", *[str(g) for g in self.gpu]]
        args += list(self.extra_args)
        return args

    def metadata(self) -> dict[str, Any]:
        return {
            "executable": list(self.executable),
            "extra_args": list(self.extra_args),
            "gpu": list(self.gpu),
            "mpi": self.mpi,
            "omp_threads": self.omp_threads,
            "failure_policy": self.failure_policy,
        }


@dataclass(frozen=True)
class ProcessingConfig:
    export_npz: bool = True
    diagnostics: bool = True
    valid_band_threshold: float = 1e-3
    eta: float = 1e-12
    frequency_range: tuple[float, float] | None = None
    window: str = "none"

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "ProcessingConfig":
        data = data or {}
        fr = data.get("frequency_range")
        freq_range = None if fr is None else (float(fr[0]), float(fr[1]))
        if freq_range and (freq_range[0] < 0 or freq_range[1] <= freq_range[0]):
            raise ValidationError(
                "output.frequency_range must be [f_min, f_max] with f_max > f_min >= 0"
            )
        threshold = float(data.get("valid_band_threshold", 1e-3))
        if threshold < 0:
            raise ValidationError("output.valid_band_threshold must be non-negative")
        return cls(
            export_npz=bool(data.get("export_npz", True)),
            diagnostics=bool(data.get("diagnostics", True)),
            valid_band_threshold=threshold,
            eta=float(data.get("eta", 1e-12)),
            frequency_range=freq_range,
            window=str(data.get("window", "none")).lower(),
        )

    def metadata(self) -> dict[str, Any]:
        return {
            "export_npz": self.export_npz,
            "diagnostics": self.diagnostics,
            "valid_band_threshold": self.valid_band_threshold,
            "eta": self.eta,
            "frequency_range": (
                None if self.frequency_range is None else list(self.frequency_range)
            ),
            "window": self.window,
        }


_RAW_MATERIAL_RE = re.compile(r"^\s*#material:\s+(.+)$", re.IGNORECASE)


def _raw_material_ids(commands: Sequence[str]) -> set[str]:
    ids: set[str] = set()
    for command in commands:
        match = _RAW_MATERIAL_RE.match(command)
        if not match:
            continue
        parts = match.group(1).split()
        if len(parts) == 5:
            ids.add(parts[-1])
    return ids


@dataclass(frozen=True)
class MediaFitConfig:
    n_poles: int = 12
    frequency_min: float | None = None
    frequency_max: float | None = None
    num_frequencies: int = 256
    max_rel_error_warn: float = 0.05
    max_rel_error_fail: float = 0.15
    allow_poor_fit: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "MediaFitConfig":
        data = data or {}
        frequency_min = data.get("frequency_min")
        frequency_max = data.get("frequency_max")
        out = cls(
            n_poles=int(data.get("n_poles", 12)),
            frequency_min=None if frequency_min is None else float(frequency_min),
            frequency_max=None if frequency_max is None else float(frequency_max),
            num_frequencies=int(data.get("num_frequencies", 256)),
            max_rel_error_warn=float(data.get("max_rel_error_warn", 0.05)),
            max_rel_error_fail=float(data.get("max_rel_error_fail", 0.15)),
            allow_poor_fit=bool(data.get("allow_poor_fit", False)),
        )
        if out.n_poles <= 0:
            raise ValidationError("media.fit.n_poles must be positive")
        if out.num_frequencies < 2:
            raise ValidationError("media.fit.num_frequencies must be at least 2")
        for name in [
            "frequency_min",
            "frequency_max",
            "max_rel_error_warn",
            "max_rel_error_fail",
        ]:
            value = getattr(out, name)
            if value is not None and (not np.isfinite(value)):
                raise ValidationError(f"media.fit.{name} must be finite")
        if out.frequency_min is not None and out.frequency_min <= 0:
            raise ValidationError("media.fit.frequency_min must be positive")
        if out.frequency_max is not None and out.frequency_max <= 0:
            raise ValidationError("media.fit.frequency_max must be positive")
        if (
            out.frequency_min is not None
            and out.frequency_max is not None
            and out.frequency_max <= out.frequency_min
        ):
            raise ValidationError(
                "media.fit.frequency_max must be greater than frequency_min"
            )
        if out.max_rel_error_warn < 0 or out.max_rel_error_fail < 0:
            raise ValidationError("media.fit error thresholds must be non-negative")
        if out.max_rel_error_fail < out.max_rel_error_warn:
            raise ValidationError(
                "media.fit.max_rel_error_fail must be >= max_rel_error_warn"
            )
        return out

    def metadata(self) -> dict[str, Any]:
        return {
            "n_poles": self.n_poles,
            "frequency_min": self.frequency_min,
            "frequency_max": self.frequency_max,
            "num_frequencies": self.num_frequencies,
            "max_rel_error_warn": self.max_rel_error_warn,
            "max_rel_error_fail": self.max_rel_error_fail,
            "allow_poor_fit": self.allow_poor_fit,
        }


@dataclass(frozen=True)
class MediaConfig:
    materials: tuple[ColeColeMedium, ...] = ()
    fit: MediaFitConfig = field(default_factory=MediaFitConfig)
    use_default_catalog: bool = False
    debye_approximations: tuple[DebyeApproximation, ...] = ()
    fit_frequencies_hz: tuple[float, ...] = ()
    warnings: tuple[str, ...] = ()
    fdtd_dt: float | None = None

    @property
    def has_structured_media(self) -> bool:
        return bool(self.materials)

    @classmethod
    def empty(cls) -> "MediaConfig":
        return cls()

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, Any] | None,
        *,
        fda: FDAConfig,
        processing: ProcessingConfig,
        scene_materials: Sequence[str],
        fdtd_dt: float,
    ) -> "MediaConfig":
        if data is None:
            return cls.empty()
        if not isinstance(data, Mapping):
            raise ValidationError("media must be a mapping")
        fit = MediaFitConfig.from_mapping(data.get("fit"))
        use_default_catalog = bool(data.get("use_default_catalog", False))
        mats_obj = data.get("materials", {}) or {}
        if not isinstance(mats_obj, Mapping):
            raise ValidationError("media.materials must be a mapping")
        materials: list[ColeColeMedium] = []
        for material_id, entry in mats_obj.items():
            if not isinstance(entry, Mapping):
                raise ValidationError(
                    f"media.materials.{material_id} must be a mapping"
                )
            try:
                materials.append(
                    material_from_mapping(
                        str(material_id), entry, use_default_catalog=use_default_catalog
                    )
                )
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
        names = [m.material_id for m in materials]
        if len(set(names)) != len(names):
            raise ValidationError("media.materials ids must be unique")
        raw_ids = _raw_material_ids(scene_materials)
        collisions = sorted(raw_ids.intersection(names))
        if collisions:
            raise ValidationError(
                f"structured media id(s) collide with raw scene.materials #material definitions: {collisions}"
            )
        if not materials:
            return cls(
                materials=(),
                fit=fit,
                use_default_catalog=use_default_catalog,
                fdtd_dt=float(fdtd_dt),
            )
        fit_freqs = _fit_frequencies(fit, fda, processing)
        approximations: list[DebyeApproximation] = []
        fit_warnings: list[str] = []
        for medium in materials:
            tau_floor = np.nextafter(float(fdtd_dt), np.inf)
            approx = fit_cole_cole_to_debye(
                medium, fit_freqs, n_poles=fit.n_poles, tau_min=tau_floor
            )
            active_taus = [
                tq
                for de, tq in zip(
                    approx.delta_eps,
                    approx.tau,
                    strict=True,
                )
                if de > 1e-30
            ]

            if not active_taus:
                raise ValidationError(
                    f"media.materials.{medium.material_id}: "
                    "Debye approximation has no active poles"
                )

            if min(active_taus) <= fdtd_dt:
                raise ValidationError(
                    f"media.materials.{medium.material_id}: "
                    "Debye relaxation time must be greater than "
                    f"the FDTD timestep; min_tau={min(active_taus):.6g}, "
                    f"dt={fdtd_dt:.6g}"
                )
            if approx.max_rel_error > fit.max_rel_error_warn:
                fit_warnings.append(
                    f"media.materials.{medium.material_id}: max_rel_error {approx.max_rel_error:.6g} exceeds warn threshold {fit.max_rel_error_warn:.6g}"
                )
            if approx.max_rel_error > fit.max_rel_error_fail and not fit.allow_poor_fit:
                raise ValidationError(
                    f"media.materials.{medium.material_id}: Debye approximation max_rel_error {approx.max_rel_error:.6g} exceeds fail threshold {fit.max_rel_error_fail:.6g}; set media.fit.allow_poor_fit: true to allow"
                )
            approximations.append(approx)
        return cls(
            materials=tuple(materials),
            fit=fit,
            use_default_catalog=use_default_catalog,
            debye_approximations=tuple(approximations),
            fit_frequencies_hz=tuple(float(v) for v in fit_freqs),
            warnings=tuple(fit_warnings),
            fdtd_dt=float(fdtd_dt),
        )

    def metadata(self) -> dict[str, Any]:
        if not self.has_structured_media:
            return {
                "use_default_catalog": self.use_default_catalog,
                "fit": self.fit.metadata(),
                "materials": [],
                "debye_approximations": [],
            }
        return {
            "source_model": "cole_cole",
            "approximation_model": "multi_pole_debye",
            "use_default_catalog": self.use_default_catalog,
            "fdtd_dt_estimate_s": self.fdtd_dt,
            "fit": self.fit.metadata(),
            "fit_frequency_range": (
                [
                    (
                        self.fit.frequency_min
                        if self.fit.frequency_min is not None
                        else min(self.fit_frequencies_hz)
                    ),
                    (
                        self.fit.frequency_max
                        if self.fit.frequency_max is not None
                        else max(self.fit_frequencies_hz)
                    ),
                ]
                if self.fit_frequencies_hz
                else None
            ),
            "fit_num_frequencies": len(self.fit_frequencies_hz),
            "fit_error_policy": {
                "warn": self.fit.max_rel_error_warn,
                "fail": self.fit.max_rel_error_fail,
                "allow_poor_fit": self.fit.allow_poor_fit,
            },
            "materials": [m.to_dict() for m in self.materials],
            "debye_approximations": [
                a.to_dict(include_frequencies=False) for a in self.debye_approximations
            ],
            "debye_stability": [
                {
                    "material_id": approx.material_id,
                    "min_tau_s": min(approx.tau),
                    "min_tau_over_dt": (
                        min(approx.tau) / self.fdtd_dt if self.fdtd_dt else None
                    ),
                }
                for approx in self.debye_approximations
            ],
            "warnings": list(self.warnings),
        }


def _fit_frequencies(
    fit: MediaFitConfig, fda: FDAConfig, processing: ProcessingConfig
) -> np.ndarray:
    fda_freqs = np.asarray(fda.frequencies, dtype=float)
    positive_fda = fda_freqs[fda_freqs > 0]
    if positive_fda.size == 0:
        raise ValidationError(
            "FDA frequencies must contain positive values for media fitting"
        )
    if fit.frequency_min is not None:
        lo = fit.frequency_min
    elif processing.frequency_range is not None and processing.frequency_range[0] > 0:
        lo = processing.frequency_range[0]
    else:
        lo = max(float(np.min(positive_fda)) * 0.5, 1.0)
    if fit.frequency_max is not None:
        hi = fit.frequency_max
    elif processing.frequency_range is not None:
        hi = max(
            float(processing.frequency_range[1]), float(np.max(positive_fda)) * 1.5
        )
    else:
        hi = float(np.max(positive_fda)) * 1.5
    if hi <= lo:
        hi = lo * 10.0
    return np.logspace(np.log10(lo), np.log10(hi), fit.num_frequencies)


@dataclass(frozen=True)
class ScenarioConfig:
    name: str
    domain: DomainConfig
    grid: GridConfig
    time: TimeConfig
    array: ArrayConfig
    fda: FDAConfig
    waveform: WaveformConfig
    receiver: ReceiverConfig
    scene: SceneConfig
    variants: tuple[VariantConfig, ...]
    execution: ExecutionConfig
    processing: ProcessingConfig
    output_root: Path
    media: MediaConfig = field(default_factory=MediaConfig)
    random_seed: int = 0
    source_path: Path | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(
        cls, data: Mapping[str, Any], source_path: Path | None = None
    ) -> "ScenarioConfig":
        for key in ["domain", "grid", "time", "array", "fda"]:
            if key not in data:
                raise ValidationError(f"{key} section is required")
        array = ArrayConfig.from_mapping(data["array"])
        fda = FDAConfig.from_mapping(data["fda"], array.nt)
        output = data.get("output", {}) or {}
        processing = ProcessingConfig.from_mapping(output)
        scene = SceneConfig.from_mapping(data.get("scene"))
        domain = DomainConfig.from_mapping(data["domain"])
        grid = GridConfig.from_mapping(data["grid"])
        time_config = TimeConfig.from_mapping(data["time"])
        fdtd_dt = estimate_gprmax_dt(
            domain,
            grid,
        )
        array = ArrayConfig.from_mapping(data["array"])
        fda = FDAConfig.from_mapping(
            data["fda"],
            array.nt,
        )
        waveform = WaveformConfig.from_mapping(data.get("waveform"))

        if waveform.mode == "excitation_file":
            fda_freqs = np.asarray(
                fda.frequencies,
                dtype=float,
            )

            if not np.allclose(
                fda_freqs,
                fda_freqs[0],
                rtol=0,
                atol=0,
            ):
                raise ValidationError(
                    "excitation_file mode currently defines one "
                    "absolute waveform shared by all Tx and therefore "
                    "cannot represent a non-degenerate FDA frequency "
                    "schedule safely"
                )

        output = data.get("output", {}) or {}
        media = MediaConfig.from_mapping(
            data.get("media"),
            fda=fda,
            processing=processing,
            scene_materials=scene.materials,
            fdtd_dt=fdtd_dt,
        )
        output_root = Path(output.get("root", data.get("output_root", "runs")))
        if source_path is not None and not output_root.is_absolute():
            output_root = (source_path.parent / output_root).resolve()
        return cls(
            name=str(data.get("name", "scene")),
            domain=domain,
            grid=grid,
            time=time_config,
            array=array,
            fda=fda,
            waveform=waveform,
            receiver=ReceiverConfig.from_mapping(data.get("receiver")),
            scene=scene,
            variants=parse_variants(data.get("variants")),
            execution=ExecutionConfig.from_mapping(data.get("execution")),
            processing=processing,
            output_root=output_root,
            media=media,
            random_seed=int(data.get("random_seed", 0)),
            source_path=source_path,
            raw_data=dict(data),
        )

    @property
    def nt(self) -> int:
        return self.array.nt

    @property
    def nr(self) -> int:
        return self.array.nr

    def normalized_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "random_seed": self.random_seed,
            "domain": {"size": list(self.domain.size)},
            "grid": {"spacing": list(self.grid.spacing)},
            "time": {"window": self.time.window},
            "array": self.array.metadata(),
            "fda": self.fda.metadata(),
            "waveform": self.waveform.metadata(),
            "receiver": {"component": self.receiver.component},
            "scene": {
                "title": self.scene.title,
                "materials": list(self.scene.materials),
                "geometry": list(self.scene.geometry),
                "geometry_view": self.scene.geometry_view,
            },
            "media": self.media.metadata(),
            "variants": [
                {"name": v.name, "geometry": list(v.geometry), "metadata": v.metadata}
                for v in self.variants
            ],
            "execution": self.execution.metadata(),
            "output": {"root": str(self.output_root), **self.processing.metadata()},
        }

    def normalized_json(self) -> str:
        return stable_json(self.normalized_dict())

    def checksum(self) -> str:
        return checksum_text(self.normalized_json())

    def metadata(self) -> dict[str, Any]:
        return {**self.normalized_dict(), "config_checksum": self.checksum()}

    def variant(self, name: str) -> VariantConfig:
        for variant in self.variants:
            if variant.name == name:
                return variant
        raise ValidationError(f"unknown variant: {name}")


def load_scenario(path: str | Path) -> ScenarioConfig:
    path = Path(path).resolve()
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, Mapping):
        raise ValidationError("scenario YAML must contain a mapping at the top level")
    return ScenarioConfig.from_mapping(data, source_path=path)
