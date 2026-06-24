"""Parse gprMax stdout logs and numerical-dispersion diagnostics."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class GprMaxStdoutSummary:
    tx_index: int
    path: str
    gprmax_version: str | None = None
    domain_size: tuple[float, float, float] | None = None
    grid_cells: tuple[int, int, int] | None = None
    spatial_step: tuple[float, float, float] | None = None
    time_window_s: float | None = None
    iterations: int | None = None
    waveform_frequency_hz: float | None = None
    warnings: list[str] = field(default_factory=list)
    numerical_dispersion_warning: bool = False
    max_phase_velocity_error_percent: float | None = None
    dispersion_risk: str = "UNKNOWN"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DispersionSummary:
    warning: bool
    risk: str
    max_abs_phase_velocity_error_percent: float | None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def dispersion_risk(error_percent: float | None) -> str:
    if error_percent is None:
        return "UNKNOWN"
    err = abs(float(error_percent))
    if err < 2.0:
        return "LOW"
    if err < 5.0:
        return "MODERATE"
    if err < 10.0:
        return "HIGH"
    return "SEVERE"


def _parse_float3(text: str) -> tuple[float, float, float] | None:
    vals = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", text)
    if len(vals) < 3:
        return None
    return (float(vals[0]), float(vals[1]), float(vals[2]))


def _tx_index_from_path(path: Path) -> int:
    m = re.search(r"tx[_-]?(\d+)", path.stem)
    return int(m.group(1)) if m else -1


def parse_gprmax_stdout(path: str | Path) -> GprMaxStdoutSummary:
    path = Path(path)
    tx_index = _tx_index_from_path(path)
    warnings: list[str] = []
    if not path.exists():
        return GprMaxStdoutSummary(tx_index=tx_index, path=str(path), warnings=[f"log file does not exist: {path}"])
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        return GprMaxStdoutSummary(tx_index=tx_index, path=str(path), warnings=["stdout log is empty"])

    version = None
    domain_size = None
    grid_cells = None
    spatial_step = None
    time_window_s = None
    iterations = None
    waveform_frequency_hz = None
    max_err = None
    numerical_warning = False

    m = re.search(r"\bv(\d+\.\d+\.\d+[^\n]*)", text)
    if m:
        version = m.group(1).strip()

    for line in text.splitlines():
        line_stripped = line.strip()
        lower = line_stripped.lower()
        if "warning" in lower:
            warnings.append(line_stripped)
        if lower.startswith("spatial discretisation:"):
            spatial_step = _parse_float3(line_stripped)
        elif lower.startswith("domain size:"):
            domain_size = _parse_float3(line_stripped)
            cells = re.search(r"\((\d+)\s*x\s*(\d+)\s*x\s*(\d+)\s*=", line_stripped)
            if cells:
                grid_cells = (int(cells.group(1)), int(cells.group(2)), int(cells.group(3)))
        elif lower.startswith("time window:"):
            m_time = re.search(r"Time window:\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*secs\s*\((\d+)\s+iterations\)", line_stripped, re.I)
            if m_time:
                time_window_s = float(m_time.group(1))
                iterations = int(m_time.group(2))
        if "waveform" in lower and "frequency" in lower:
            m_freq = re.search(r"frequency\s+([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*hz", line_stripped, re.I)
            if m_freq:
                waveform_frequency_hz = float(m_freq.group(1))
        if "numerical dispersion" in lower or "phase-velocity error" in lower or "phase velocity error" in lower:
            numerical_warning = True
            m_err = re.search(r"phase[- ]velocity error is\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*%", line_stripped, re.I)
            if m_err:
                max_err = float(m_err.group(1))

    if version is None:
        warnings.append("gprMax version not found in stdout")
    if waveform_frequency_hz is None:
        warnings.append("waveform frequency not found in stdout")
    if numerical_warning and max_err is None:
        warnings.append("numerical dispersion warning found but phase-velocity error could not be parsed")

    return GprMaxStdoutSummary(
        tx_index=tx_index,
        path=str(path),
        gprmax_version=version,
        domain_size=domain_size,
        grid_cells=grid_cells,
        spatial_step=spatial_step,
        time_window_s=time_window_s,
        iterations=iterations,
        waveform_frequency_hz=waveform_frequency_hz,
        warnings=warnings,
        numerical_dispersion_warning=numerical_warning,
        max_phase_velocity_error_percent=max_err,
        dispersion_risk=dispersion_risk(max_err),
    )


def collect_run_log_summaries(logs_dir: str | Path) -> list[GprMaxStdoutSummary]:
    logs_dir = Path(logs_dir)
    paths = sorted(logs_dir.glob("gprmax_stdout_tx_*.txt"))
    return sorted((parse_gprmax_stdout(path) for path in paths), key=lambda item: item.tx_index)


def summarize_numerical_dispersion(summaries: Iterable[GprMaxStdoutSummary]) -> DispersionSummary:
    summaries = list(summaries)
    errs = [abs(s.max_phase_velocity_error_percent) for s in summaries if s.max_phase_velocity_error_percent is not None]
    max_abs = max(errs) if errs else None
    risk_order = {"UNKNOWN": 0, "LOW": 1, "MODERATE": 2, "HIGH": 3, "SEVERE": 4}
    risk = "UNKNOWN"
    for summary in summaries:
        if risk_order.get(summary.dispersion_risk, 0) > risk_order.get(risk, 0):
            risk = summary.dispersion_risk
    return DispersionSummary(
        warning=any(s.numerical_dispersion_warning for s in summaries),
        risk=risk,
        max_abs_phase_velocity_error_percent=max_abs,
        warnings=[w for s in summaries for w in s.warnings if "dispersion" in w.lower() or "phase-velocity" in w.lower()],
    )
