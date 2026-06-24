"""Validation evidence suite for the FDA-MIMO-GPR compatibility layer.

The cases in this module are deliberately small and deterministic. They validate
compatibility-layer semantics and data-flow contracts; they do not claim to
validate hardware-realistic FDA-MIMO-GPR physics.
"""

from __future__ import annotations

import csv
import json
import math
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import h5py
import numpy as np

from .config import ScenarioConfig, load_scenario
from .parsing import OutputParseError, parse_tx_outputs
from .processing import (
    ProcessingError,
    Snapshot,
    assemble_time_tensor,
    frequency_transform,
    normalize_by_source,
    subtract_background,
    valid_band_mask,
)
from .rendering import render_scenario_inputs
from .running import build_command_plan, run_plan
from .serialization import write_processed_snapshot

SCOPE_LIMITATION = (
    "This case validates compatibility-layer semantics and I/O contracts; "
    "it does not validate hardware-realistic FDA-MIMO-GPR physics."
)


class ValidationSuiteError(RuntimeError):
    """Raised for validation-suite setup errors."""


def json_safe(value: Any) -> Any:
    """Convert common scientific Python values to JSON-safe objects."""

    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, complex):
        return {"real": value.real, "imag": value.imag}
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return str(value)
    return value


@dataclass(frozen=True)
class ValidationResult:
    """Machine-readable result for one validation evidence case."""

    case_name: str
    claim: str
    passed: bool
    inputs: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=lambda: [SCOPE_LIMITATION])

    def to_dict(self) -> dict[str, Any]:
        return json_safe(
            {
                "case_name": self.case_name,
                "claim": self.claim,
                "passed": self.passed,
                "inputs": self.inputs,
                "metrics": self.metrics,
                "artifacts": self.artifacts,
                "errors": self.errors,
                "limitations": self.limitations,
            }
        )


@dataclass(frozen=True)
class ValidationSuiteResult:
    """Aggregate result for a validation evidence suite run."""

    suite_name: str
    output_dir: Path
    results: tuple[ValidationResult, ...]
    artifacts: dict[str, str] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    def to_dict(self) -> dict[str, Any]:
        return json_safe(
            {
                "suite_name": self.suite_name,
                "passed": self.passed,
                "output_dir": self.output_dir,
                "num_cases": len(self.results),
                "num_passed": sum(result.passed for result in self.results),
                "num_failed": sum(not result.passed for result in self.results),
                "results": [result.to_dict() for result in self.results],
                "artifacts": self.artifacts,
            }
        )


def prepare_output_dir(path: str | Path, overwrite: bool = False) -> Path:
    out = Path(path).resolve()
    if out.exists() and overwrite:
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    return out


def case_dir(output_dir: Path, case_name: str) -> Path:
    path = output_dir / case_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: str | Path, data: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(data), indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def write_csv(path: str | Path, rows: Sequence[dict[str, Any]]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return path
    fields = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json_safe(v) for k, v in row.items()})
    return path


def write_markdown_table(path: str | Path, rows: Sequence[dict[str, Any]]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return path
    fields = list(rows[0].keys())
    lines = ["| " + " | ".join(fields) + " |", "| " + " | ".join("---" for _ in fields) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(json_safe(row.get(f, ""))) for f in fields) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _mpl():
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    return plt


def _relative_artifacts(artifacts: dict[str, Path], root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in artifacts.items():
        try:
            out[key] = str(value.resolve().relative_to(root.resolve()))
        except ValueError:
            out[key] = str(value)
    return out


def render_contract_case(scenario: ScenarioConfig, output_dir: str | Path, tolerance: float = 1e-6) -> ValidationResult:
    name = "01_render_contract"
    cdir = case_dir(Path(output_dir), name)
    plan = render_scenario_inputs(scenario, variant_name=scenario.variants[0].name, run_dir=cdir / "rendered_run")
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for item in plan.inputs:
        lines = item.input_path.read_text(encoding="utf-8").splitlines()
        source_count = sum(line.startswith("#hertzian_dipole:") for line in lines)
        rx_count = sum(line.startswith("#rx:") for line in lines)
        wave_lines = [line for line in lines if line.startswith("#waveform:")]
        rendered_freq = float("nan")
        if wave_lines:
            tokens = wave_lines[0].split()
            if len(tokens) >= 4:
                rendered_freq = float(tokens[3])
        freq_error = abs(rendered_freq - item.center_frequency)
        row_passed = source_count == 1 and rx_count == scenario.nr and freq_error <= tolerance
        if not row_passed:
            errors.append(f"tx {item.tx_index} render contract failed")
        rows.append(
            {
                "tx_index": item.tx_index,
                "active_source_count": source_count,
                "receiver_count": rx_count,
                "rendered_frequency_hz": rendered_freq,
                "expected_frequency_hz": item.center_frequency,
                "frequency_error_hz": freq_error,
                "passed": row_passed,
            }
        )
    table_csv = write_csv(cdir / "render_contract_table.csv", rows)
    table_md = write_markdown_table(cdir / "render_contract_table.md", rows)
    plt = _mpl()
    fig, ax = plt.subplots(figsize=(6, 3.5))
    matrix = np.tile(np.asarray(scenario.fda.frequencies, dtype=float)[:, None] / 1e9, (1, scenario.nr))
    im = ax.imshow(matrix, aspect="auto", origin="lower")
    ax.set_xlabel("Rx index")
    ax.set_ylabel("Tx index")
    ax.set_title("FDA frequency bound to each Tx (GHz)")
    fig.colorbar(im, ax=ax, label="GHz")
    fig.tight_layout()
    fig_path = cdir / "tx_rx_fda_grid.png"
    fig.savefig(fig_path, dpi=160)
    plt.close(fig)
    passed = len(plan.inputs) == scenario.nt and all(bool(row["passed"]) for row in rows)
    artifacts = _relative_artifacts({"csv": table_csv, "table": table_md, "figure": fig_path}, Path(output_dir))
    result = ValidationResult(
        case_name=name,
        claim="Rendered gprMax inputs preserve TDM-MIMO source activation, all-Rx reception, and Tx-index-bound FDA frequencies.",
        passed=passed,
        inputs={"scenario": scenario.name, "nt": scenario.nt, "nr": scenario.nr, "variant": scenario.variants[0].name},
        metrics={"num_inputs": len(plan.inputs), "expected_inputs": scenario.nt, "rows": rows},
        artifacts=artifacts,
        errors=errors,
    )
    write_json(cdir / "result.json", result.to_dict())
    return result


def _write_synthetic_outputs(base: Path, nt: int, nr: int, lt: int, component: str, dt: float) -> list[Path]:
    raw = base / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for m in range(nt):
        path = raw / f"tx_{m:03d}.out"
        with h5py.File(path, "w") as h5:
            h5.attrs["Iterations"] = lt
            h5.attrs["dt"] = dt
            h5.attrs["nrx"] = nr
            h5.attrs["gprMax"] = "synthetic-validation"
            for n in range(nr):
                group = h5.create_group(f"/rxs/rx{n + 1}")
                group.attrs["Position"] = (float(n), 0.0, 0.0)
                values = 1000.0 * m + 10.0 * n + np.arange(lt, dtype=np.float64)
                group.create_dataset(component, data=values)
        paths.append(path)
    return paths


def parser_roundtrip_case(scenario: ScenarioConfig, output_dir: str | Path, tolerance: float = 0.0) -> ValidationResult:
    name = "02_parser_roundtrip"
    cdir = case_dir(Path(output_dir), name)
    lt = 16
    dt = 1e-11
    paths = _write_synthetic_outputs(cdir, scenario.nt, scenario.nr, lt, scenario.receiver.component, dt)
    traces = parse_tx_outputs(paths, scenario.receiver.component, expected_nrx=scenario.nr)
    yt, _time = assemble_time_tensor(traces, expected_nt=scenario.nt, expected_nr=scenario.nr)
    expected = np.zeros_like(yt)
    for m in range(scenario.nt):
        for n in range(scenario.nr):
            expected[m, n, :] = 1000.0 * m + 10.0 * n + np.arange(lt)
    max_error = float(np.max(np.abs(yt - expected)))
    passed = max_error <= tolerance
    slice0 = yt[:, :, 0]
    slice_csv = write_csv(
        cdir / "yt_slice_l0.csv",
        [{"tx_index": m, **{f"rx_{n}": float(slice0[m, n]) for n in range(scenario.nr)}} for m in range(scenario.nt)],
    )
    plt = _mpl()
    fig, ax = plt.subplots(figsize=(6, 4))
    im = ax.imshow(slice0, aspect="auto", origin="lower")
    ax.set_xlabel("Rx index")
    ax.set_ylabel("Tx index")
    ax.set_title("Parser round-trip index map: Y_t[m,n,0]")
    fig.colorbar(im, ax=ax)
    fig.tight_layout()
    fig_path = cdir / "yt_index_map.png"
    fig.savefig(fig_path, dpi=160)
    plt.close(fig)
    result = ValidationResult(
        case_name=name,
        claim="Synthetic gprMax-like HDF5 receiver datasets map to the expected Y_t[Tx,Rx,time] tensor indices.",
        passed=passed,
        inputs={"nt": scenario.nt, "nr": scenario.nr, "lt": lt, "component": scenario.receiver.component},
        metrics={"max_abs_error": max_error, "tensor_shape": list(yt.shape), "tolerance": tolerance},
        artifacts=_relative_artifacts({"csv": slice_csv, "figure": fig_path}, Path(output_dir)),
        errors=[] if passed else [f"parser round-trip max error {max_error} exceeds tolerance {tolerance}"],
    )
    write_json(cdir / "result.json", result.to_dict())
    return result


def fft_sanity_case(_scenario: ScenarioConfig, output_dir: str | Path, tolerance: float = 1e-9) -> ValidationResult:
    name = "03_fft_sanity"
    cdir = case_dir(Path(output_dir), name)
    lt = 128
    dt = 1e-9
    expected_bin = 8
    expected_frequency = expected_bin / (lt * dt)
    time_axis = np.arange(lt, dtype=np.float64) * dt
    yt = np.sin(2 * np.pi * expected_frequency * time_axis)[None, None, :]
    yf, freqs = frequency_transform(yt, dt)
    magnitudes = np.abs(yf[0, 0])
    detected_bin = int(np.argmax(magnitudes))
    detected_frequency = float(freqs[detected_bin])
    frequency_error = abs(detected_frequency - expected_frequency)
    passed = frequency_error <= tolerance
    rows = [{"frequency_hz": float(f), "magnitude": float(v)} for f, v in zip(freqs, magnitudes, strict=True)]
    spectrum_csv = write_csv(cdir / "spectrum.csv", rows)
    peak_json = write_json(
        cdir / "peak_summary.json",
        {"expected_frequency_hz": expected_frequency, "detected_frequency_hz": detected_frequency, "frequency_error_hz": frequency_error},
    )
    plt = _mpl()
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.plot(freqs, magnitudes)
    ax.axvline(expected_frequency, color="r", linestyle="--", label="expected")
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Magnitude")
    ax.set_title("FFT sanity: bin-aligned sinusoid")
    ax.legend()
    fig.tight_layout()
    fig_path = cdir / "fft_peak.png"
    fig.savefig(fig_path, dpi=160)
    plt.close(fig)
    result = ValidationResult(
        case_name=name,
        claim="Frequency transform places a bin-aligned sinusoid peak at the expected FFT frequency bin.",
        passed=passed,
        inputs={"lt": lt, "dt": dt, "expected_bin": expected_bin},
        metrics={"expected_frequency_hz": expected_frequency, "detected_frequency_hz": detected_frequency, "frequency_error_hz": frequency_error, "tolerance": tolerance},
        artifacts=_relative_artifacts({"csv": spectrum_csv, "peak_summary": peak_json, "figure": fig_path}, Path(output_dir)),
        errors=[] if passed else [f"FFT peak error {frequency_error} exceeds tolerance {tolerance}"],
    )
    write_json(cdir / "result.json", result.to_dict())
    return result


def normalization_sanity_case(scenario: ScenarioConfig, output_dir: str | Path, tolerance: float = 1e-6) -> ValidationResult:
    name = "04_normalization_sanity"
    cdir = case_dir(Path(output_dir), name)
    nt, nr, kf = scenario.nt, scenario.nr, 12
    k = np.arange(kf, dtype=np.float64)
    source = np.stack([(1.0 + 0.1 * m) * np.exp(1j * 0.05 * k) for m in range(nt)], axis=0).astype(np.complex64)
    source[:, -1] = 1e-12 + 0j
    h_true = np.zeros((nt, nr, kf), dtype=np.complex64)
    for m in range(nt):
        for n in range(nr):
            h_true[m, n, :] = (1.0 + 0.2 * m + 0.05 * n) * np.exp(1j * 0.02 * k)
    y_rx = h_true * source[:, None, :]
    mask = valid_band_mask(source, threshold=1e-3)
    y_cal = normalize_by_source(y_rx, source, mask, eta=1e-12)
    valid = mask[:, None, :]
    max_valid_error = float(np.nanmax(np.abs(y_cal[valid.repeat(nr, axis=1)] - h_true[valid.repeat(nr, axis=1)])))
    invalid_values = y_cal[:, :, ~mask.any(axis=0)] if np.any(~mask.any(axis=0)) else np.asarray([])
    invalid_has_nan = bool(invalid_values.size == 0 or np.isnan(invalid_values.real).any())
    passed = max_valid_error <= tolerance and invalid_has_nan
    error_by_tx = []
    for m in range(nt):
        tx_valid = mask[m]
        err = np.abs(y_cal[m, :, tx_valid] - h_true[m, :, tx_valid])
        error_by_tx.append({"tx_index": m, "max_valid_error": float(np.nanmax(err)), "valid_bins": int(tx_valid.sum()), "invalid_bins": int((~tx_valid).sum())})
    err_csv = write_csv(cdir / "normalization_error.csv", error_by_tx)
    plt = _mpl()
    fig, ax = plt.subplots(figsize=(6, 3.5))
    im = ax.imshow(np.abs(y_cal[:, 0, :] - h_true[:, 0, :]), aspect="auto", origin="lower")
    ax.set_xlabel("Frequency bin")
    ax.set_ylabel("Tx index")
    ax.set_title("Normalization error |Y_cal - H_true| for Rx0")
    fig.colorbar(im, ax=ax)
    fig.tight_layout()
    fig_path = cdir / "normalization_error.png"
    fig.savefig(fig_path, dpi=160)
    plt.close(fig)
    result = ValidationResult(
        case_name=name,
        claim="Source normalization recovers known channel response on valid bands and preserves invalid-band masking.",
        passed=passed,
        inputs={"nt": nt, "nr": nr, "kf": kf, "threshold": 1e-3},
        metrics={"max_valid_error": max_valid_error, "invalid_has_nan": invalid_has_nan, "tolerance": tolerance, "by_tx": error_by_tx},
        artifacts=_relative_artifacts({"csv": err_csv, "figure": fig_path}, Path(output_dir)),
        errors=[] if passed else ["normalization recovery or invalid-band handling failed"],
    )
    write_json(cdir / "result.json", result.to_dict())
    return result


def _synthetic_snapshot(scenario: ScenarioConfig, raw: np.ndarray, freqs: np.ndarray, time: np.ndarray) -> Snapshot:
    return Snapshot(
        time_traces=np.zeros((scenario.nt, scenario.nr, len(time)), dtype=np.float32),
        time=time,
        frequencies=freqs,
        frequency_tensor_raw=raw.astype(np.complex64),
        source_spectra=np.ones((scenario.nt, len(freqs)), dtype=np.complex64),
        valid_band_mask=np.ones((scenario.nt, len(freqs)), dtype=bool),
        frequency_tensor_cal=raw.astype(np.complex64),
        tx_positions=scenario.array.tx_positions.astype(np.float64),
        rx_positions=scenario.array.rx_positions.astype(np.float64),
        fda_center_frequencies=np.asarray(scenario.fda.frequencies, dtype=np.float64),
        metadata=scenario.metadata(),
    )


def background_subtraction_case(scenario: ScenarioConfig, output_dir: str | Path, tolerance: float = 1e-6) -> ValidationResult:
    name = "05_background_subtraction"
    cdir = case_dir(Path(output_dir), name)
    kf = 10
    freqs = np.linspace(1e8, 1e9, kf)
    time = np.arange(16) * 1e-11
    background = np.ones((scenario.nt, scenario.nr, kf), dtype=np.complex64) * (2.0 + 0.5j)
    scatter_true = np.zeros_like(background)
    for m in range(scenario.nt):
        for n in range(scenario.nr):
            scatter_true[m, n, :] = (0.1 * (m + 1) + 0.01 * n) * np.exp(1j * np.linspace(0, 0.5, kf))
    target = background + scatter_true
    target_snapshot = _synthetic_snapshot(scenario, target, freqs, time)
    background_snapshot = _synthetic_snapshot(scenario, background, freqs, time)
    recovered = subtract_background(target_snapshot, background_snapshot)
    max_error = float(np.max(np.abs(recovered - scatter_true)))
    incompatible_rejected = False
    try:
        bad_background = _synthetic_snapshot(scenario, background, freqs + 1.0, time)
        subtract_background(target_snapshot, bad_background)
    except ProcessingError:
        incompatible_rejected = True
    passed = max_error <= tolerance and incompatible_rejected
    rows = [{"tx_index": m, **{f"rx_{n}": float(np.abs(recovered[m, n, 0])) for n in range(scenario.nr)}} for m in range(scenario.nt)]
    scatter_csv = write_csv(cdir / "scatter_slice_k0.csv", rows)
    plt = _mpl()
    fig, ax = plt.subplots(figsize=(6, 3.5))
    im = ax.imshow(np.abs(recovered[:, :, 0]), aspect="auto", origin="lower")
    ax.set_xlabel("Rx index")
    ax.set_ylabel("Tx index")
    ax.set_title("Recovered scatter magnitude at k=0")
    fig.colorbar(im, ax=ax)
    fig.tight_layout()
    fig_path = cdir / "scatter_recovery.png"
    fig.savefig(fig_path, dpi=160)
    plt.close(fig)
    result = ValidationResult(
        case_name=name,
        claim="Target/background subtraction recovers known scatter tensors and rejects incompatible axes.",
        passed=passed,
        inputs={"nt": scenario.nt, "nr": scenario.nr, "kf": kf},
        metrics={"max_scatter_error": max_error, "incompatible_rejected": incompatible_rejected, "tolerance": tolerance},
        artifacts=_relative_artifacts({"csv": scatter_csv, "figure": fig_path}, Path(output_dir)),
        errors=[] if passed else ["scatter recovery or incompatible-axis rejection failed"],
    )
    write_json(cdir / "result.json", result.to_dict())
    return result


SyntheticCase = Callable[[ScenarioConfig, str | Path, float], ValidationResult]


def default_synthetic_cases() -> tuple[SyntheticCase, ...]:
    return (
        render_contract_case,
        parser_roundtrip_case,
        fft_sanity_case,
        normalization_sanity_case,
        background_subtraction_case,
    )


def _failed_result(case_name: str, exc: BaseException) -> ValidationResult:
    return ValidationResult(
        case_name=case_name,
        claim="Validation case failed before completing its evidence claim.",
        passed=False,
        metrics={"exception_type": type(exc).__name__},
        errors=[str(exc)],
        limitations=[SCOPE_LIMITATION, "This result may indicate a validation harness error rather than a semantic failure."],
    )


def write_summary(suite: ValidationSuiteResult) -> Path:
    path = suite.output_dir / "summary.json"
    write_json(path, suite.to_dict())
    return path


def write_report(suite: ValidationSuiteResult) -> Path:
    path = suite.output_dir / "validation_report.md"
    lines = [
        "# FDA-MIMO-GPR Validation Evidence Report",
        "",
        f"Suite: `{suite.suite_name}`",
        f"Status: **{'PASS' if suite.passed else 'FAIL'}**",
        "",
        "## Scope",
        "",
        "This suite validates compatibility-layer semantics and I/O contracts: configuration semantics, render contract, HDF5 parsing, tensor indexing, FFT behavior, source normalization, and background subtraction. It does **not** validate hardware-realistic FDA-MIMO-GPR physics, antenna coupling, T/R switch behavior, platform motion, or measured-data calibration.",
        "",
        "## Evidence Pyramid",
        "",
        "1. Render contract: one Tx source, all Rx commands, Tx-bound FDA frequencies.",
        "2. Parser round-trip: gprMax-like HDF5 receiver datasets map to `Y_t[m,n,l]`.",
        "3. FFT sanity: known sinusoid peak appears at the expected frequency bin.",
        "4. Source normalization: `Y_rx = H_true * S_m` recovers `H_true` on valid bands.",
        "5. Background subtraction: known scatter is recovered and incompatible axes are rejected.",
        "",
        "## Case Results",
        "",
    ]
    for result in suite.results:
        status = "PASS" if result.passed else "FAIL"
        lines.extend(
            [
                f"### {result.case_name}: {status}",
                "",
                f"**Claim:** {result.claim}",
                "",
                "**Metrics:**",
                "",
                "```json",
                json.dumps(json_safe(result.metrics), indent=2, ensure_ascii=False),
                "```",
                "",
            ]
        )
        if result.artifacts:
            lines.append("**Artifacts:**")
            lines.append("")
            for key, artifact in result.artifacts.items():
                lines.append(f"- `{key}`: `{artifact}`")
            lines.append("")
        if result.errors:
            lines.append("**Errors:**")
            lines.append("")
            for err in result.errors:
                lines.append(f"- {err}")
            lines.append("")
        lines.append("**Limitations:**")
        lines.append("")
        for limitation in result.limitations:
            lines.append(f"- {limitation}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def run_synthetic_validation_suite(
    scenario: ScenarioConfig | str | Path,
    output_dir: str | Path,
    tolerance: float = 1e-6,
    overwrite: bool = False,
    write_report_file: bool = True,
) -> ValidationSuiteResult:
    scenario_obj = load_scenario(scenario) if isinstance(scenario, (str, Path)) else scenario
    out = prepare_output_dir(output_dir, overwrite=overwrite)
    results: list[ValidationResult] = []
    for case in default_synthetic_cases():
        try:
            results.append(case(scenario_obj, out, tolerance))
        except Exception as exc:  # keep partial suite evidence available for diagnosis
            results.append(_failed_result(case.__name__.replace("_case", ""), exc))
    suite = ValidationSuiteResult("synthetic-validation", out, tuple(results))
    summary_path = write_summary(suite)
    artifacts = {"summary": str(summary_path.relative_to(out))}
    if write_report_file:
        report_path = write_report(suite)
        artifacts["report"] = str(report_path.relative_to(out))
    suite = ValidationSuiteResult("synthetic-validation", out, tuple(results), artifacts=artifacts)
    write_summary(suite)
    return suite


def gprmax_smoke_validation_case(
    scenario: ScenarioConfig,
    output_dir: str | Path,
    timeout: float | None = None,
    tolerance: float = 1e-6,
) -> ValidationResult:
    name = "06_gprmax_smoke"
    cdir = case_dir(Path(output_dir), name)
    start = time.perf_counter()
    plan = render_scenario_inputs(scenario, variant_name=scenario.variants[0].name, run_dir=cdir / "run")
    commands = [build_command_plan(scenario, plan, item) for item in plan.inputs]
    try:
        results = run_plan(scenario, plan, timeout=timeout)
        if not all(result.ok for result in results):
            return ValidationResult(
                case_name=name,
                claim="Opt-in real gprMax smoke validates rendered-input to raw-output to processed-snapshot interface closure.",
                passed=False,
                inputs={"scenario": scenario.name, "commands": [cmd.to_dict() for cmd in commands]},
                metrics={"runtime_seconds": time.perf_counter() - start, "failure_category": "environment_or_runtime", "results": [r.to_dict() for r in results]},
                artifacts={"run_manifest": str((plan.logs_dir / "run_manifest.json").relative_to(Path(output_dir)))},
                errors=["gprMax execution did not complete successfully for every Tx"],
                limitations=[SCOPE_LIMITATION, "Smoke validation is runtime-dependent and may fail due to environment setup."],
            )
        traces = parse_tx_outputs([item.output_path for item in plan.inputs], scenario.receiver.component, expected_nrx=scenario.nr)
        from .processing import make_snapshot
        from .diagnostics import write_diagnostics

        snapshot = make_snapshot(traces, scenario, normalize=True)
        outputs = write_processed_snapshot(snapshot, plan.processed_dir, export_npz=scenario.processing.export_npz)
        diagnostics = write_diagnostics(snapshot, plan.figures_dir) if scenario.processing.diagnostics else {}
        passed = snapshot.time_traces.shape[:2] == (scenario.nt, scenario.nr) and snapshot.frequency_tensor_raw.size > 0
        artifacts = {"run_manifest": str((plan.logs_dir / "run_manifest.json").relative_to(Path(output_dir)))}
        artifacts.update({f"snapshot_{k}": str(v.relative_to(Path(output_dir))) for k, v in outputs.items()})
        artifacts.update({f"diagnostic_{k}": str(v.relative_to(Path(output_dir))) for k, v in diagnostics.items()})
        return ValidationResult(
            case_name=name,
            claim="Opt-in real gprMax smoke validates rendered-input to raw-output to processed-snapshot interface closure.",
            passed=passed,
            inputs={"scenario": scenario.name, "commands": [cmd.to_dict() for cmd in commands]},
            metrics={"runtime_seconds": time.perf_counter() - start, "tensor_shape": list(snapshot.time_traces.shape), "frequency_shape": list(snapshot.frequency_tensor_raw.shape), "tolerance": tolerance},
            artifacts=artifacts,
            errors=[] if passed else ["smoke snapshot tensors were empty or had unexpected dimensions"],
            limitations=[SCOPE_LIMITATION, "This smoke test checks interface closure, not physical fidelity."],
        )
    except (OSError, OutputParseError, ProcessingError, RuntimeError) as exc:
        return ValidationResult(
            case_name=name,
            claim="Opt-in real gprMax smoke validates rendered-input to raw-output to processed-snapshot interface closure.",
            passed=False,
            inputs={"scenario": scenario.name, "commands": [cmd.to_dict() for cmd in commands]},
            metrics={"runtime_seconds": time.perf_counter() - start, "failure_category": "environment_or_runtime", "exception_type": type(exc).__name__},
            artifacts={"run_manifest": str((plan.logs_dir / "run_manifest.json").relative_to(Path(output_dir))) if (plan.logs_dir / "run_manifest.json").exists() else ""},
            errors=[str(exc)],
            limitations=[SCOPE_LIMITATION, "Smoke validation is runtime-dependent and may fail due to environment setup."],
        )
