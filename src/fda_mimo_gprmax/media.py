"""Structured media models for gprMax compatibility rendering.

This module keeps the physical Cole--Cole medium definition in the adapter while
rendering a deterministic multi-pole Debye approximation that gprMax can execute.
"""

from __future__ import annotations

import math
import re
import warnings
from dataclasses import dataclass
from typing import Any, Mapping, Tuple
from scipy.optimize import nnls

import numpy as np

EPSILON_0 = 8.854187817e-12
C0 = 299792458.0

_MATERIAL_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")


DEFAULT_COLE_COLE_CATALOG: dict[str, dict[str, Any]] = {
    "S1": {
        "medium_type": "Dry lunar regolith / dry low-loss soil analog",
        "model": "cole_cole",
        "eps_s": 3.05,
        "eps_inf": 3.00,
        "tau": 1.0e-6,
        "alpha": 0.30,
        "sigma": 1.0e-14,
        "source": "Strangway 1974",
        "role": "low-loss propagation-dominated baseline",
    },
    "S2": {
        "medium_type": "Basalt / moist-dispersive analog",
        "model": "cole_cole",
        "eps_s": 1000.0,
        "eps_inf": 8.0,
        "tau": 1.0e-6,
        "alpha": 0.30,
        "sigma": 1.0e-8,
        "source": "Olhoeft 1973",
        "role": "strongly dispersive anchor",
    },
    "S3": {
        "medium_type": "Water ice / frozen ground anchor",
        "model": "cole_cole",
        "eps_s": 91.0,
        "eps_inf": 3.15,
        "tau": 2.5e-5,
        "alpha": 0.0,
        "sigma": 1.0e-8,
        "source": "Auty 1952",
        "role": "low-loss but highly polar medium",
    },
    "S4": {
        "medium_type": "Water-bearing kaolinite / concrete-like engineering anchor",
        "model": "cole_cole",
        "eps_s": 35.6,
        "eps_inf": 2.0,
        "tau": 5.0e-12,
        "alpha": 0.20,
        "sigma": 0.08,
        "source": "Mansour 2020",
        "role": "lossy engineering medium",
    },
    "S5": {
        "medium_type": "Fine-grained clay / pavement-soil anchor",
        "model": "cole_cole",
        "eps_s": 30.26,
        "eps_inf": 10.7,
        "tau": 9.55e-12,
        "alpha": 0.062,
        "sigma": 0.0,
        "source": "Schwing 2013",
        "role": "fine-grained lossy soil anchor",
    },
}


def _finite_float(value: Any, name: str) -> float:
    out = float(value)
    if not math.isfinite(out):
        raise ValueError(f"{name} must be finite")
    return out


@dataclass(frozen=True)
class ColeColeMedium:
    material_id: str
    eps_s: float
    eps_inf: float
    tau: float
    alpha: float
    sigma: float = 0.0
    source: str | None = None
    role: str | None = None
    medium_type: str | None = None

    def __post_init__(self) -> None:
        material_id = str(self.material_id).strip()
        if not material_id or not _MATERIAL_ID_RE.match(material_id):
            raise ValueError(
                "media.materials.<id> must be a non-empty gprMax-compatible material id"
            )
        values = {
            "eps_s": _finite_float(self.eps_s, f"media.materials.{material_id}.eps_s"),
            "eps_inf": _finite_float(
                self.eps_inf, f"media.materials.{material_id}.eps_inf"
            ),
            "tau": _finite_float(self.tau, f"media.materials.{material_id}.tau"),
            "alpha": _finite_float(self.alpha, f"media.materials.{material_id}.alpha"),
            "sigma": _finite_float(self.sigma, f"media.materials.{material_id}.sigma"),
        }
        if values["eps_s"] <= 0:
            raise ValueError(f"media.materials.{material_id}.eps_s must be > 0")
        if values["eps_inf"] <= 0:
            raise ValueError(f"media.materials.{material_id}.eps_inf must be > 0")
        if values["eps_s"] < values["eps_inf"]:
            raise ValueError(f"media.materials.{material_id}.eps_s must be >= eps_inf")
        if values["tau"] <= 0:
            raise ValueError(f"media.materials.{material_id}.tau must be > 0")
        if not (0 <= values["alpha"] < 1):
            raise ValueError(
                f"media.materials.{material_id}.alpha must satisfy 0 <= alpha < 1"
            )
        if values["sigma"] < 0:
            raise ValueError(f"media.materials.{material_id}.sigma must be >= 0")
        object.__setattr__(self, "material_id", material_id)
        for key, value in values.items():
            object.__setattr__(self, key, value)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "material_id": self.material_id,
            "model": "cole_cole",
            "eps_s": self.eps_s,
            "eps_inf": self.eps_inf,
            "tau": self.tau,
            "alpha": self.alpha,
            "sigma": self.sigma,
        }
        if self.source is not None:
            out["source"] = self.source
        if self.role is not None:
            out["role"] = self.role
        if self.medium_type is not None:
            out["medium_type"] = self.medium_type
        return out


@dataclass(frozen=True)
class DebyeApproximation:
    material_id: str
    eps_inf: float
    sigma: float
    delta_eps: Tuple[float, ...]
    tau: Tuple[float, ...]
    fit_frequencies_hz: Tuple[float, ...]
    max_rel_error: float
    rms_rel_error: float

    def to_dict(self, include_frequencies: bool = False) -> dict[str, Any]:
        out: dict[str, Any] = {
            "material_id": self.material_id,
            "eps_inf": self.eps_inf,
            "sigma": self.sigma,
            "delta_eps": list(self.delta_eps),
            "tau": list(self.tau),
            "n_poles": len(self.delta_eps),
            "fit_frequency_min_hz": (
                min(self.fit_frequencies_hz) if self.fit_frequencies_hz else None
            ),
            "fit_frequency_max_hz": (
                max(self.fit_frequencies_hz) if self.fit_frequencies_hz else None
            ),
            "fit_num_frequencies": len(self.fit_frequencies_hz),
            "max_rel_error": self.max_rel_error,
            "rms_rel_error": self.rms_rel_error,
        }
        if include_frequencies:
            out["fit_frequencies_hz"] = list(self.fit_frequencies_hz)
        return out


def cole_cole_complex_permittivity(
    freq_hz: np.ndarray | float,
    *,
    eps_s: float,
    eps_inf: float,
    tau: float,
    alpha: float,
    sigma: float,
) -> np.ndarray:
    """Return complex relative permittivity of a conductive Cole--Cole medium."""

    freq = np.asarray(freq_hz, dtype=float)
    if np.any(freq <= 0) or not np.all(np.isfinite(freq)):
        raise ValueError("freq_hz must contain positive finite frequencies")
    omega = 2.0 * np.pi * freq
    delta_eps = float(eps_s) - float(eps_inf)
    return (
        float(eps_inf)
        + delta_eps / (1.0 + (1j * omega * float(tau)) ** (1.0 - float(alpha)))
        + float(sigma) / (1j * omega * EPSILON_0)
    )


def debye_complex_permittivity(
    freq_hz: np.ndarray | float,
    *,
    eps_inf: float,
    sigma: float,
    delta_eps: np.ndarray,
    tau: np.ndarray,
) -> np.ndarray:
    freq = np.asarray(freq_hz, dtype=float)
    if np.any(freq <= 0) or not np.all(np.isfinite(freq)):
        raise ValueError("freq_hz must contain positive finite frequencies")
    omega = 2.0 * np.pi * freq
    out = np.full(freq.shape, complex(eps_inf), dtype=complex)
    for de, tq in zip(
        np.asarray(delta_eps, dtype=float), np.asarray(tau, dtype=float), strict=True
    ):
        out = out + de / (1.0 + 1j * omega * tq)
    out = out + sigma / (1j * omega * EPSILON_0)
    return out


def complex_wavenumber_from_epsilon(
    freq_hz: np.ndarray | float, epsilon_r: np.ndarray
) -> np.ndarray:
    """Return complex wavenumber k = omega / c0 * sqrt(epsilon_r)."""

    freq = np.asarray(freq_hz, dtype=float)
    if np.any(freq <= 0) or not np.all(np.isfinite(freq)):
        raise ValueError("freq_hz must contain positive finite frequencies")
    omega = 2.0 * np.pi * freq
    return omega / C0 * np.sqrt(epsilon_r)


def _default_tau_grid(
    medium: ColeColeMedium,
    frequencies: np.ndarray,
    n_poles: int,
    tau_min: float | None,
    tau_max: float | None,
) -> np.ndarray:
    f_min = float(np.min(frequencies))
    f_max = float(np.max(frequencies))
    lo = (
        float(tau_min)
        if tau_min is not None
        else min(medium.tau / 100.0, 1.0 / (2.0 * np.pi * f_max * 100.0))
    )
    hi = (
        float(tau_max)
        if tau_max is not None
        else max(medium.tau * 100.0, 100.0 / (2.0 * np.pi * f_min))
    )
    if not math.isfinite(lo) or lo <= 0:
        raise ValueError("tau_min must be positive and finite")
    if not math.isfinite(hi) or hi <= lo:
        raise ValueError("tau_max must be finite and greater than tau_min")
    grid = np.logspace(np.log10(lo), np.log10(hi), n_poles)
    if lo <= medium.tau <= hi and n_poles > 0:
        grid[int(np.argmin(np.abs(np.log(grid) - np.log(medium.tau))))] = medium.tau
        grid = np.sort(grid)
    return grid


def _solve_weights(
    a_real: np.ndarray,
    y_real: np.ndarray,
    allow_negative_weights: bool,
) -> np.ndarray:
    if allow_negative_weights:
        weights, *_ = np.linalg.lstsq(
            a_real,
            y_real,
            rcond=None,
        )

        return weights.astype(float)

    weights, _ = nnls(
        a_real,
        y_real,
    )

    return weights.astype(float)


def fit_cole_cole_to_debye(
    medium: ColeColeMedium,
    fit_frequencies_hz: np.ndarray,
    *,
    n_poles: int = 12,
    tau_min: float | None = None,
    tau_max: float | None = None,
    allow_negative_weights: bool = False,
) -> DebyeApproximation:
    if n_poles <= 0:
        raise ValueError("n_poles must be positive")
    freq = np.asarray(fit_frequencies_hz, dtype=float).reshape(-1)
    if freq.size == 0 or np.any(freq <= 0) or not np.all(np.isfinite(freq)):
        raise ValueError("fit_frequencies_hz must contain positive finite frequencies")
    freq = np.unique(np.sort(freq))
    tau_grid = _default_tau_grid(medium, freq, int(n_poles), tau_min, tau_max)
    omega = 2.0 * np.pi * freq
    eps_cc = cole_cole_complex_permittivity(
        freq,
        eps_s=medium.eps_s,
        eps_inf=medium.eps_inf,
        tau=medium.tau,
        alpha=medium.alpha,
        sigma=medium.sigma,
    )
    y = eps_cc - medium.eps_inf - medium.sigma / (1j * omega * EPSILON_0)
    a = np.stack([1.0 / (1.0 + 1j * omega * tq) for tq in tau_grid], axis=1)
    a_real = np.vstack([a.real, a.imag])
    y_real = np.concatenate([y.real, y.imag])
    weights = _solve_weights(a_real, y_real, allow_negative_weights)
    if not allow_negative_weights:
        weights = np.maximum(weights, 0.0)
    eps_debye = debye_complex_permittivity(
        freq,
        eps_inf=medium.eps_inf,
        sigma=medium.sigma,
        delta_eps=weights,
        tau=tau_grid,
    )
    rel_error = np.abs(eps_debye - eps_cc) / np.maximum(np.abs(eps_cc), 1e-12)
    max_rel_error = float(np.max(rel_error))
    rms_rel_error = float(np.sqrt(np.mean(rel_error**2)))
    if max_rel_error > 0.05:
        warnings.warn(
            f"Cole-Cole Debye approximation for {medium.material_id} has max_rel_error={max_rel_error:.6g}",
            RuntimeWarning,
            stacklevel=2,
        )
    return DebyeApproximation(
        material_id=medium.material_id,
        eps_inf=medium.eps_inf,
        sigma=medium.sigma,
        delta_eps=tuple(float(v) for v in weights),
        tau=tuple(float(v) for v in tau_grid),
        fit_frequencies_hz=tuple(float(v) for v in freq),
        max_rel_error=max_rel_error,
        rms_rel_error=rms_rel_error,
    )


def render_debye_material_commands(approx: DebyeApproximation) -> list[str]:
    n_poles = len(approx.delta_eps)
    if n_poles != len(approx.tau):
        raise ValueError("Debye approximation delta_eps and tau lengths differ")
    # gprMax requires all permittivity differences (delta_eps) to be strictly positive.
    # Filter out poles with zero (or near-zero) amplitude.
    filtered = [
        (de, tq)
        for de, tq in zip(approx.delta_eps, approx.tau, strict=True)
        if de > 1e-30
    ]
    if not filtered:
        raise ValueError(
            f"Debye approximation for {approx.material_id} has no non-zero poles"
        )
    parts = [f"#add_dispersion_debye: {len(filtered)}"]
    for de, tq in filtered:
        parts.append(f"{de:.17g}")
        parts.append(f"{tq:.17g}")
    parts.append(approx.material_id)
    return [
        f"#material: {approx.eps_inf:.17g} {approx.sigma:.17g} 1 0 {approx.material_id}",
        " ".join(parts),
    ]


def material_from_mapping(
    material_id: str, data: Mapping[str, Any], *, use_default_catalog: bool = False
) -> ColeColeMedium:
    merged: dict[str, Any] = {}
    catalog_key = data.get("from_catalog")
    if catalog_key is not None:
        key = str(catalog_key)
        if not use_default_catalog:
            raise ValueError(
                f"media.materials.{material_id}.from_catalog requires media.use_default_catalog: true"
            )
        if key not in DEFAULT_COLE_COLE_CATALOG:
            available = ", ".join(sorted(DEFAULT_COLE_COLE_CATALOG))
            raise ValueError(
                f"unknown media catalog key {key!r}; available keys: {available}"
            )
        merged.update(DEFAULT_COLE_COLE_CATALOG[key])
    merged.update({k: v for k, v in data.items() if k != "from_catalog"})
    model = str(merged.get("model", "cole_cole")).lower().replace("-", "_")
    if model != "cole_cole":
        raise ValueError(f"media.materials.{material_id}.model must be cole_cole")
    try:
        return ColeColeMedium(
            material_id=material_id,
            eps_s=merged["eps_s"],
            eps_inf=merged["eps_inf"],
            tau=merged["tau"],
            alpha=merged["alpha"],
            sigma=merged.get("sigma", 0.0),
            source=None if merged.get("source") is None else str(merged.get("source")),
            role=None if merged.get("role") is None else str(merged.get("role")),
            medium_type=(
                None
                if merged.get("medium_type") is None
                else str(merged.get("medium_type"))
            ),
        )
    except KeyError as exc:
        raise ValueError(
            f"media.materials.{material_id}.{exc.args[0]} is required"
        ) from exc
