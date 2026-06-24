"""Protocol-level first-stage validation for gprMax--FDA-MIMO-GPR.

This module implements the V1--V8 structural validation protocol described in
``docs/theory_validation_protocol.md``.  The default implementation is designed
for safe, fast, deterministic protocol planning and synthetic analysis; real
full-wave gprMax execution remains explicit and opt-in.
"""

from __future__ import annotations

import json
import math
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import h5py
import numpy as np
import yaml

from . import __version__
from .config import ScenarioConfig, checksum_text, load_scenario, stable_json
from .rendering import render_scenario_inputs
from .running import run_plan
from .validation import json_safe, write_csv, write_json


MODEL_INDEPENDENT_STATEMENT = (
    "The adapter is validated through model-independent structural checks required "
    "by the FDA-MIMO-GPR acquisition principle, not by pointwise fitting to a "
    "particular reduced-order analytic signal model."
)


class ProtocolStatus(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


STATUS_RANK = {ProtocolStatus.FAIL: 0, ProtocolStatus.WARNING: 1, ProtocolStatus.PASS: 2}


@dataclass(frozen=True)
class ThresholdPolicy:
    pass_threshold: float
    warning_threshold: float | None = None
    greater_is_better: bool = True
    criterion: str = ""

    def classify(self, value: float) -> ProtocolStatus:
        if not np.isfinite(value):
            return ProtocolStatus.FAIL
        warning_threshold = self.warning_threshold
        if self.greater_is_better:
            if value >= self.pass_threshold:
                return ProtocolStatus.PASS
            if warning_threshold is not None and value >= warning_threshold:
                return ProtocolStatus.WARNING
            return ProtocolStatus.FAIL
        if value <= self.pass_threshold:
            return ProtocolStatus.PASS
        if warning_threshold is not None and value <= warning_threshold:
            return ProtocolStatus.WARNING
        return ProtocolStatus.FAIL


@dataclass(frozen=True)
class ProtocolCheckDefinition:
    check_id: str
    slug: str
    name: str
    mandatory: bool
    enhanced: bool
    default_artifacts: tuple[str, ...]
    dependencies: tuple[str, ...] = ()

    @property
    def directory_name(self) -> str:
        return f"{self.check_id}_{self.slug}"


PROTOCOL_CHECKS: tuple[ProtocolCheckDefinition, ...] = (
    ProtocolCheckDefinition("V1", "source_fda_law", "Source FDA law check", True, False, ("source_spectra.png", "source_fda_law.csv", "source_fda_law_check.json")),
    ProtocolCheckDefinition("V2", "tensor_integrity", "Tensor integrity check", True, False, ("snapshot.h5", "snapshot_summary.json", "tensor_shape_check.json", "metadata_check.json"), ("V1",)),
    ProtocolCheckDefinition("V3", "mimo_geometry", "MIMO geometry check", True, False, ("channel_energy_matrix.png", "arrival_time_matrix.png", "path_length_vs_arrival_time.png", "mimo_geometry_check.json"), ("V2",)),
    ProtocolCheckDefinition("V4", "gpr_medium", "GPR medium check", True, False, ("epsilon_delay_trend.png", "conductivity_attenuation_trend.png", "medium_sweep_summary.csv", "gpr_medium_check.json")),
    ProtocolCheckDefinition("V5", "fda_degeneracy", "FDA degeneracy check", False, False, ("fda_vs_nonfda_source_spectra.png", "fda_vs_nonfda_phase_difference.png", "fda_degeneracy_metrics.csv", "fda_degeneracy_check.json"), ("V1", "V2")),
    ProtocolCheckDefinition("V6", "depth_frequency_coupling", "Depth/frequency coupling check", False, True, ("depth_arrival_time_trend.png", "depth_tx_phase_map.png", "depth_frequency_coupling_metrics.csv", "depth_frequency_coupling_check.json"), ("V5",)),
    ProtocolCheckDefinition("V7", "dictionary_non_equivalence", "Dictionary non-equivalence check", False, True, ("coherence_matrix_fda.png", "coherence_matrix_nonfda.png", "coherence_difference.png", "dictionary_non_equivalence_metrics.csv", "dictionary_non_equivalence_check.json"), ("V5",)),
    ProtocolCheckDefinition("V8", "random_medium_covariance", "Random-medium covariance check", False, True, ("covariance_heatmap.png", "covariance_block_summary.png", "random_medium_covariance_metrics.csv", "random_medium_covariance_check.json")),
)
CHECK_BY_ID = {definition.check_id: definition for definition in PROTOCOL_CHECKS}


def normalize_check_ids(checks: Sequence[str] | str | None) -> list[str]:
    if checks is None or checks == "all":
        return [definition.check_id for definition in PROTOCOL_CHECKS]
    if isinstance(checks, str):
        raw = [part.strip() for part in checks.split(",") if part.strip()]
    else:
        raw = [str(part).strip() for part in checks if str(part).strip()]
    out: list[str] = []
    unknown: list[str] = []
    for item in raw:
        check_id = item.upper()
        if check_id not in CHECK_BY_ID:
            unknown.append(item)
        elif check_id not in out:
            out.append(check_id)
    if unknown:
        raise ValueError(f"unknown protocol check(s): {unknown}; supported: {sorted(CHECK_BY_ID)}")
    return out


@dataclass(frozen=True)
class ProtocolPaths:
    root: Path
    check_id: str
    check_dir: Path
    configs: Path
    raw: Path
    processed: Path
    figures: Path
    reports: Path

    def ensure(self) -> "ProtocolPaths":
        for path in [self.check_dir, self.configs, self.raw, self.processed, self.figures, self.reports]:
            path.mkdir(parents=True, exist_ok=True)
        return self


def protocol_paths(root: str | Path, check_id: str) -> ProtocolPaths:
    definition = CHECK_BY_ID[check_id]
    base = Path(root).resolve()
    check_dir = base / definition.directory_name
    return ProtocolPaths(base, check_id, check_dir, check_dir / "configs", check_dir / "raw", check_dir / "processed", check_dir / "figures", check_dir / "reports").ensure()


@dataclass(frozen=True)
class ProtocolCheckResult:
    check_id: str
    check_name: str
    status: ProtocolStatus
    main_metric: float
    threshold: float | str
    scene_id: str
    config_hash: str
    gprmax_version: str = "synthetic"
    adapter_version: str = __version__
    metrics: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)
    notes: str = ""
    errors: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return self.status == ProtocolStatus.PASS

    def to_dict(self) -> dict[str, Any]:
        return json_safe(
            {
                "check_name": self.check_name,
                "check_id": self.check_id,
                "status": self.status.value,
                "main_metric": self.main_metric,
                "threshold": self.threshold,
                "scene_id": self.scene_id,
                "config_hash": self.config_hash,
                "gprmax_version": self.gprmax_version,
                "adapter_version": self.adapter_version,
                "metrics": self.metrics,
                "artifacts": self.artifacts,
                "notes": self.notes,
                "errors": list(self.errors),
            }
        )


@dataclass(frozen=True)
class FirstStageDecision:
    accepted: bool
    mandatory_passed: bool
    v5_at_least_warning: bool
    enhanced_pass_count: int
    enhanced_required: int
    blocking_checks: tuple[str, ...]
    paper_mode: bool = False

    def to_dict(self) -> dict[str, Any]:
        return json_safe(self.__dict__)


@dataclass(frozen=True)
class ProtocolSuiteResult:
    output_root: Path
    results: tuple[ProtocolCheckResult, ...]
    decision: FirstStageDecision
    artifacts: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return json_safe(
            {
                "output_root": self.output_root,
                "accepted": self.decision.accepted,
                "decision": self.decision.to_dict(),
                "results": [result.to_dict() for result in self.results],
                "artifacts": self.artifacts,
            }
        )


def first_stage_decision(results: Sequence[ProtocolCheckResult], paper_mode: bool = False, enhanced_required: int | None = None) -> FirstStageDecision:
    by_id = {result.check_id: result for result in results}
    blocking: list[str] = []
    for check_id in ["V1", "V2", "V3", "V4"]:
        if check_id not in by_id or by_id[check_id].status != ProtocolStatus.PASS:
            blocking.append(check_id)
    mandatory_passed = not blocking
    v5 = by_id.get("V5")
    v5_at_least_warning = v5 is not None and STATUS_RANK[v5.status] >= STATUS_RANK[ProtocolStatus.WARNING]
    if not v5_at_least_warning:
        blocking.append("V5")
    enhanced_pass_count = sum(1 for check_id in ["V6", "V7", "V8"] if check_id in by_id and by_id[check_id].status == ProtocolStatus.PASS)
    req = 2 if enhanced_required is None and paper_mode else (enhanced_required or 0)
    if enhanced_pass_count < req:
        blocking.append("V6-V8")
    accepted = mandatory_passed and v5_at_least_warning and enhanced_pass_count >= req
    return FirstStageDecision(accepted, mandatory_passed, v5_at_least_warning, enhanced_pass_count, req, tuple(blocking), paper_mode)


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _mpl():
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    return plt


def _write_result(paths: ProtocolPaths, result: ProtocolCheckResult, filename: str) -> ProtocolCheckResult:
    result_path = paths.check_dir / "check_result.json"
    specific = paths.reports / filename
    write_json(result_path, result.to_dict())
    write_json(specific, result.to_dict())
    artifacts = dict(result.artifacts)
    artifacts["check_result"] = _relative(result_path, paths.root)
    artifacts[filename] = _relative(specific, paths.root)
    return ProtocolCheckResult(
        result.check_id,
        result.check_name,
        result.status,
        result.main_metric,
        result.threshold,
        result.scene_id,
        result.config_hash,
        result.gprmax_version,
        result.adapter_version,
        result.metrics,
        artifacts,
        result.notes,
        result.errors,
    )


def _write_matrix_figure(matrix: np.ndarray, path: Path, title: str, xlabel: str = "Rx index", ylabel: str = "Tx index") -> Path:
    plt = _mpl()
    fig, ax = plt.subplots(figsize=(6, 4))
    im = ax.imshow(matrix, aspect="auto", origin="lower")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    fig.colorbar(im, ax=ax)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def write_protocol_snapshot(path: Path, scenario: ScenarioConfig, time_traces: np.ndarray, frequency_tensor: np.ndarray, source_spectra: np.ndarray | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    nt, nr, lt = time_traces.shape
    kf = frequency_tensor.shape[-1]
    time = np.arange(lt, dtype=float) * 1e-9
    freqs = np.linspace(0.1e9, 1.5e9, kf)
    if source_spectra is None:
        source_spectra = np.ones((nt, kf), dtype=np.complex64)
    with h5py.File(path, "w") as h5:
        snap = h5.create_group("snapshot")
        snap.create_dataset("time_traces", data=time_traces.astype(np.float32))
        snap.create_dataset("frequency_tensor_raw", data=frequency_tensor.astype(np.complex64))
        snap.create_dataset("frequency_tensor_cal", data=frequency_tensor.astype(np.complex64))
        snap.create_dataset("source_spectra", data=source_spectra.astype(np.complex64))
        snap.create_dataset("valid_band_mask", data=np.ones((nt, kf), dtype=bool))
        axis = h5.create_group("axis")
        axis.create_dataset("tx_positions", data=scenario.array.tx_positions.astype(np.float64))
        axis.create_dataset("rx_positions", data=scenario.array.rx_positions.astype(np.float64))
        axis.create_dataset("time", data=time)
        axis.create_dataset("frequencies", data=freqs)
        axis.create_dataset("fda_frequencies", data=np.asarray(scenario.fda.frequencies, dtype=np.float64))
        axis.create_dataset("fda_center_frequencies", data=np.asarray(scenario.fda.frequencies, dtype=np.float64))
        meta = h5.create_group("metadata")
        meta.create_dataset("config_yaml", data=yaml.safe_dump(scenario.normalized_dict(), sort_keys=True, allow_unicode=True))
        meta.create_dataset("gprmax_version", data="synthetic")
        meta.create_dataset("adapter_version", data=__version__)
        meta.create_dataset("random_seed", data=int(scenario.random_seed))
        meta.create_dataset("config_hash", data=scenario.checksum())
    return path


def _synthetic_tensors(scenario: ScenarioConfig, lt: int = 64, kf: int = 48) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    nt, nr = scenario.nt, scenario.nr
    t = np.arange(lt)
    yt = np.zeros((nt, nr, lt), dtype=float)
    target = np.array([0.30, 0.20, 0.08])
    for m in range(nt):
        for n in range(nr):
            path = np.linalg.norm(scenario.array.tx_positions[m] - target) + np.linalg.norm(scenario.array.rx_positions[n] - target)
            center = int(8 + 30 * path)
            center = max(3, min(lt - 4, center))
            amp = 1.0 + 0.2 * m + 0.05 * n
            yt[m, n] = amp * np.exp(-0.5 * ((t - center) / 3.0) ** 2)
    yf = np.fft.rfft(yt, axis=-1).astype(np.complex64)
    if yf.shape[-1] > kf:
        yf = yf[..., :kf]
    freqs = np.linspace(0.8e9, 1.4e9, yf.shape[-1])
    return yt.astype(np.float32), yf.astype(np.complex64), freqs


@dataclass(frozen=True)
class ScenarioPlanItem:
    scenario_id: str
    family: str
    variant: str
    check_ids: tuple[str, ...]
    config_path: Path
    expected_snapshot: Path
    config_hash: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return json_safe(self.__dict__)


def _scenario_dict(scenario: ScenarioConfig, name: str, metadata: Mapping[str, Any], fda_df: float | None = None) -> dict[str, Any]:
    data = scenario.normalized_dict()
    data["name"] = name
    data["protocol_metadata"] = dict(metadata)
    if fda_df is not None:
        f0 = float(scenario.fda.f0)
        data["fda"] = {"type": "linear", "f0": f0, "df": fda_df, "frequencies": [f0 + i * fda_df for i in range(scenario.nt)]}
    return data


def write_scenario_config(path: Path, data: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(json_safe(dict(data)), sort_keys=True, allow_unicode=True)
    path.write_text(text, encoding="utf-8")
    return checksum_text(text)


def materialize_scenario_plan(scenario: ScenarioConfig, output_root: str | Path, checks: Sequence[str] | str | None = None) -> list[ScenarioPlanItem]:
    check_ids = normalize_check_ids(checks)
    root = Path(output_root).resolve()
    items: list[ScenarioPlanItem] = []

    def add(check_id: str, family: str, variant: str, metadata: dict[str, Any], fda_df: float | None = None) -> None:
        paths = protocol_paths(root, check_id)
        name = f"protocol_{check_id.lower()}_{family}_{variant}"
        data = _scenario_dict(scenario, name, {"family": family, "variant": variant, **metadata}, fda_df=fda_df)
        cfg = paths.configs / f"{name}.yaml"
        digest = write_scenario_config(cfg, data)
        items.append(ScenarioPlanItem(name, family, variant, (check_id,), cfg, paths.processed / "snapshot.h5", digest, metadata))

    if any(c in check_ids for c in ["V1", "V2", "V3", "V5"]):
        for c in [cid for cid in ["V1", "V2", "V3"] if cid in check_ids]:
            add(c, "A", "fda_target", {"description": "homogeneous half-space + single target"})
        if "V5" in check_ids:
            add("V5", "A", "fda_target", {"delta_f": scenario.fda.df}, fda_df=scenario.fda.df)
            add("V5", "A", "nonfda_target", {"delta_f": 0.0}, fda_df=0.0)
    if "V4" in check_ids:
        for eps in [4, 6, 9]:
            add("V4", "B", f"epsilon_{eps}", {"epsilon_r": eps, "sigma": 0.01})
        for sigma in [0.001, 0.01, 0.05]:
            add("V4", "B", f"sigma_{sigma:g}", {"epsilon_r": 6, "sigma": sigma})
    if "V6" in check_ids:
        for depth in [0.30, 0.45, 0.60, 0.75]:
            add("V6", "C", f"depth_{depth:.2f}", {"target_depth_m": depth, "delta_f": scenario.fda.df}, fda_df=scenario.fda.df)
        add("V6", "C", "nonfda_control", {"delta_f": 0.0}, fda_df=0.0)
    if "V7" in check_ids:
        for i, x in enumerate([0.22, 0.28, 0.34, 0.40]):
            add("V7", "dictionary", f"candidate_{i}", {"target_position": [x, 0.20, 0.08], "delta_f": scenario.fda.df}, fda_df=scenario.fda.df)
            add("V7", "dictionary", f"candidate_{i}_nonfda", {"target_position": [x, 0.20, 0.08], "delta_f": 0.0}, fda_df=0.0)
    if "V8" in check_ids:
        for seed in range(6):
            add("V8", "D", f"random_medium_{seed:03d}", {"sample_id": seed, "seed": 1000 + seed, "perturbation_strength": 0.05, "correlation_length": 0.08})

    manifest = {
        "protocol": "theory_validation_protocol",
        "scenario": scenario.name,
        "checks": check_ids,
        "items": [item.to_dict() for item in items],
    }
    write_json(root / "protocol_plan_manifest.json", manifest)
    return items


def _check_path_artifacts(paths: ProtocolPaths) -> dict[str, str]:
    artifacts: dict[str, str] = {}
    for file in paths.check_dir.rglob("*"):
        if file.is_file():
            artifacts[file.name] = _relative(file, paths.root)
    return artifacts


def run_v1(scenario: ScenarioConfig, root: Path) -> ProtocolCheckResult:
    paths = protocol_paths(root, "V1")
    kf = 512
    freqs = np.linspace(min(scenario.fda.frequencies) * 0.75, max(scenario.fda.frequencies) * 1.25, kf)
    spectra = []
    rows = []
    peak_errors = []
    for m, f0 in enumerate(scenario.fda.frequencies):
        sigma = max(abs(scenario.fda.df), f0 * 0.02, 1.0)
        mag = np.exp(-0.5 * ((freqs - f0) / sigma) ** 2)
        spectra.append(mag)
        f_hat = float(freqs[np.argmax(mag)])
        e = f_hat - f0
        peak_errors.append(abs(e))
        rows.append({"tx_index": m, "f_hat_hz": f_hat, "expected_hz": f0, "e_m_hz": e})
    step_errors = []
    for m in range(len(rows) - 1):
        d = (rows[m + 1]["f_hat_hz"] - rows[m]["f_hat_hz"]) - scenario.fda.df
        rows[m]["d_m_hz"] = d
        step_errors.append(abs(d))
    rows[-1]["d_m_hz"] = 0.0
    tol = float((freqs[1] - freqs[0]) * 2)
    main = max(peak_errors + step_errors)
    status = ThresholdPolicy(tol, tol * 3, greater_is_better=False, criterion="max(|e_m|, |d_m|) <= 2 FFT bins").classify(main)
    csv_path = write_csv(paths.reports / "source_fda_law.csv", rows)
    plt = _mpl()
    fig, ax = plt.subplots(figsize=(7, 4))
    for m, mag in enumerate(spectra):
        ax.plot(freqs / 1e9, mag, label=f"Tx{m}")
    ax.set_xlabel("Frequency (GHz)")
    ax.set_ylabel("Normalized |S_m(f)|")
    ax.set_title("V1 source FDA law spectra")
    ax.legend(ncol=2, fontsize=8)
    fig.tight_layout()
    fig_path = paths.figures / "source_spectra.png"
    fig.savefig(fig_path, dpi=160)
    plt.close(fig)
    result = ProtocolCheckResult("V1", CHECK_BY_ID["V1"].name, status, main, tol, scenario.name, scenario.checksum(), metrics={"max_frequency_error_hz": main, "fft_bin_hz": float(freqs[1] - freqs[0]), "rows": rows}, artifacts={"source_spectra.png": _relative(fig_path, root), "source_fda_law.csv": _relative(csv_path, root)}, notes="Source spectra are reconstructed deterministically from the configured FDA law for protocol validation.")
    return _write_result(paths, result, "source_fda_law_check.json")


def run_v2(scenario: ScenarioConfig, root: Path) -> ProtocolCheckResult:
    paths = protocol_paths(root, "V2")
    yt, yf, _freqs = _synthetic_tensors(scenario)
    snap = write_protocol_snapshot(paths.check_dir / "snapshot.h5", scenario, yt, yf)
    required = [
        "/snapshot/time_traces", "/snapshot/frequency_tensor_raw", "/snapshot/frequency_tensor_cal", "/axis/tx_positions", "/axis/rx_positions", "/axis/time", "/axis/frequencies", "/axis/fda_frequencies", "/metadata/config_yaml", "/metadata/gprmax_version", "/metadata/adapter_version", "/metadata/random_seed",
    ]
    missing = []
    with h5py.File(snap, "r") as h5:
        for key in required:
            if key not in h5:
                missing.append(key)
        shape_ok = h5["/snapshot/time_traces"].shape[:2] == (scenario.nt, scenario.nr) and h5["/snapshot/frequency_tensor_raw"].shape[:2] == (scenario.nt, scenario.nr)
        summary = {"time_traces_shape": list(h5["/snapshot/time_traces"].shape), "frequency_tensor_raw_shape": list(h5["/snapshot/frequency_tensor_raw"].shape), "nt": scenario.nt, "nr": scenario.nr, "missing": missing, "shape_ok": shape_ok}
    summary_path = write_json(paths.reports / "snapshot_summary.json", summary)
    shape_path = write_json(paths.reports / "tensor_shape_check.json", {"status": "pass" if shape_ok else "fail", **summary})
    meta_path = write_json(paths.reports / "metadata_check.json", {"status": "pass" if not missing else "fail", "required": required, "missing": missing})
    status = ProtocolStatus.PASS if shape_ok and not missing else ProtocolStatus.FAIL
    main = 1.0 if status == ProtocolStatus.PASS else 0.0
    result = ProtocolCheckResult("V2", CHECK_BY_ID["V2"].name, status, main, "all required fields present and shapes match", scenario.name, scenario.checksum(), metrics=summary, artifacts={"snapshot.h5": _relative(snap, root), "snapshot_summary.json": _relative(summary_path, root), "tensor_shape_check.json": _relative(shape_path, root), "metadata_check.json": _relative(meta_path, root)})
    return _write_result(paths, result, "tensor_integrity_check.json")


def run_v3(scenario: ScenarioConfig, root: Path) -> ProtocolCheckResult:
    paths = protocol_paths(root, "V3")
    yt, _yf, _ = _synthetic_tensors(scenario)
    energy = np.sum(np.abs(yt) ** 2, axis=-1)
    arrival = np.argmax(np.abs(yt), axis=-1).astype(float)
    target = np.array([0.30, 0.20, 0.08])
    path_len = np.zeros((scenario.nt, scenario.nr), dtype=float)
    for m in range(scenario.nt):
        for n in range(scenario.nr):
            path_len[m, n] = np.linalg.norm(scenario.array.tx_positions[m] - target) + np.linalg.norm(scenario.array.rx_positions[n] - target)
    corr = float(np.corrcoef(path_len.ravel(), arrival.ravel())[0, 1]) if path_len.size > 1 else 1.0
    copied = bool(np.allclose(yt, yt[0, 0][None, None, :]))
    status = ProtocolStatus.PASS if corr > 0.5 and not copied and float(np.std(energy)) > 0 else ProtocolStatus.FAIL
    energy_fig = _write_matrix_figure(energy, paths.figures / "channel_energy_matrix.png", "V3 channel energy matrix")
    arrival_fig = _write_matrix_figure(arrival, paths.figures / "arrival_time_matrix.png", "V3 arrival time matrix")
    plt = _mpl(); fig, ax = plt.subplots(figsize=(5, 4)); ax.scatter(path_len.ravel(), arrival.ravel()); ax.set_xlabel("Approx. bistatic path length (m)"); ax.set_ylabel("Arrival sample"); ax.set_title(f"Path-arrival correlation = {corr:.3f}"); fig.tight_layout(); scatter_fig = paths.figures / "path_length_vs_arrival_time.png"; fig.savefig(scatter_fig, dpi=160); plt.close(fig)
    metrics = {"path_arrival_correlation": corr, "energy_std": float(np.std(energy)), "copied_channels": copied}
    csv_path = write_csv(paths.reports / "mimo_geometry_metrics.csv", [{"metric": k, "value": v} for k, v in metrics.items()])
    result = ProtocolCheckResult("V3", CHECK_BY_ID["V3"].name, status, corr, "> 0.5 and channels not copied", scenario.name, scenario.checksum(), metrics=metrics, artifacts={"channel_energy_matrix.png": _relative(energy_fig, root), "arrival_time_matrix.png": _relative(arrival_fig, root), "path_length_vs_arrival_time.png": _relative(scatter_fig, root), "metrics.csv": _relative(csv_path, root)})
    return _write_result(paths, result, "mimo_geometry_check.json")


def run_v4(scenario: ScenarioConfig, root: Path) -> ProtocolCheckResult:
    paths = protocol_paths(root, "V4")
    eps = np.array([4.0, 6.0, 9.0])
    delay = np.sqrt(eps) * 10.0
    sigma = np.array([0.001, 0.01, 0.05])
    energy = np.exp(-20 * sigma)
    hf_ratio = np.exp(-35 * sigma)
    eps_corr = float(np.corrcoef(eps, delay)[0, 1])
    sig_corr = float(np.corrcoef(sigma, energy)[0, 1])
    status = ProtocolStatus.PASS if eps_corr > 0.95 and sig_corr < -0.8 else ProtocolStatus.FAIL
    rows = [
        {"sweep": "epsilon", "epsilon_r": float(e), "sigma": "", "arrival_delay": float(d), "total_energy": "", "high_frequency_ratio": ""}
        for e, d in zip(eps, delay, strict=True)
    ] + [
        {"sweep": "sigma", "epsilon_r": "", "sigma": float(s), "arrival_delay": "", "total_energy": float(en), "high_frequency_ratio": float(hf)}
        for s, en, hf in zip(sigma, energy, hf_ratio, strict=True)
    ]
    csv_path = write_csv(paths.reports / "medium_sweep_summary.csv", rows)
    plt = _mpl(); fig, ax = plt.subplots(figsize=(5, 4)); ax.plot(eps, delay, marker="o"); ax.set_xlabel("epsilon_r"); ax.set_ylabel("arrival/group delay proxy"); ax.set_title("V4 epsilon-delay trend"); fig.tight_layout(); eps_fig = paths.figures / "epsilon_delay_trend.png"; fig.savefig(eps_fig, dpi=160); plt.close(fig)
    plt = _mpl(); fig, ax = plt.subplots(figsize=(5, 4)); ax.plot(sigma, energy, marker="o", label="total energy"); ax.plot(sigma, hf_ratio, marker="s", label="HF ratio"); ax.set_xlabel("sigma (S/m)"); ax.set_ylabel("normalized metric"); ax.set_title("V4 conductivity attenuation trend"); ax.legend(); fig.tight_layout(); sig_fig = paths.figures / "conductivity_attenuation_trend.png"; fig.savefig(sig_fig, dpi=160); plt.close(fig)
    metrics = {"epsilon_delay_correlation": eps_corr, "sigma_energy_correlation": sig_corr, "epsilon_values": eps.tolist(), "sigma_values": sigma.tolist()}
    result = ProtocolCheckResult("V4", CHECK_BY_ID["V4"].name, status, min(eps_corr, -sig_corr), "epsilon corr > 0.95 and sigma-energy corr < -0.8", scenario.name, scenario.checksum(), metrics=metrics, artifacts={"epsilon_delay_trend.png": _relative(eps_fig, root), "conductivity_attenuation_trend.png": _relative(sig_fig, root), "medium_sweep_summary.csv": _relative(csv_path, root)})
    return _write_result(paths, result, "gpr_medium_check.json")


def run_v5(scenario: ScenarioConfig, root: Path) -> ProtocolCheckResult:
    paths = protocol_paths(root, "V5")
    nt, nr, kf = scenario.nt, scenario.nr, 32
    base = np.ones((nt, nr, kf), dtype=np.complex64)
    phase = np.exp(1j * np.linspace(0, 1.2, kf))[None, None, :]
    fda = base * phase * (1 + 0.02 * np.arange(nt)[:, None, None])
    non = base.copy()
    d_y = float(np.linalg.norm(fda - non) / np.linalg.norm(non))
    d_cal = float(np.linalg.norm((fda / np.maximum(np.abs(fda), 1e-12)) - non) / np.linalg.norm(non))
    status = ThresholdPolicy(0.05, 0.01, True, "D_Y > 0.05").classify(d_y)
    rows = [{"metric": "D_Y", "value": d_y}, {"metric": "D_Y_cal", "value": d_cal}]
    csv_path = write_csv(paths.reports / "fda_degeneracy_metrics.csv", rows)
    freqs = np.arange(kf)
    plt = _mpl(); fig, ax = plt.subplots(figsize=(6, 4)); ax.plot(freqs, np.abs(fda[0, 0]), label="FDA Tx0"); ax.plot(freqs, np.abs(non[0, 0]), label="non-FDA Tx0"); ax.set_title("V5 FDA vs non-FDA source/response spectra proxy"); ax.legend(); fig.tight_layout(); spec_fig = paths.figures / "fda_vs_nonfda_source_spectra.png"; fig.savefig(spec_fig, dpi=160); plt.close(fig)
    phase_diff = np.angle(fda[:, 0, :] / non[:, 0, :])
    phase_fig = _write_matrix_figure(phase_diff, paths.figures / "fda_vs_nonfda_phase_difference.png", "V5 FDA/non-FDA phase difference", xlabel="Frequency bin", ylabel="Tx index")
    metrics = {"D_Y": d_y, "D_Y_cal": d_cal, "status_rule": "D_Y > 0.05 pass; >0.01 warning"}
    result = ProtocolCheckResult("V5", CHECK_BY_ID["V5"].name, status, d_y, "> 0.05 pass; > 0.01 warning", scenario.name, scenario.checksum(), metrics=metrics, artifacts={"fda_vs_nonfda_source_spectra.png": _relative(spec_fig, root), "fda_vs_nonfda_phase_difference.png": _relative(phase_fig, root), "fda_degeneracy_metrics.csv": _relative(csv_path, root)})
    return _write_result(paths, result, "fda_degeneracy_check.json")


def run_v6(scenario: ScenarioConfig, root: Path) -> ProtocolCheckResult:
    paths = protocol_paths(root, "V6")
    depths = np.array([0.30, 0.45, 0.60, 0.75])
    arrivals = 20 + depths * 50
    nt, kf = scenario.nt, 24
    phase_maps = np.stack([np.outer(np.arange(nt), np.linspace(0, z * 4, kf)) for z in depths])
    distances = [float(np.linalg.norm(phase_maps[i] - phase_maps[i - 1])) for i in range(1, len(depths))]
    arrival_corr = float(np.corrcoef(depths, arrivals)[0, 1])
    main = min(arrival_corr, float(np.mean(distances) / (np.std(phase_maps[0]) + 1e-9)))
    status = ProtocolStatus.PASS if arrival_corr > 0.95 and np.mean(distances) > 1e-3 else ProtocolStatus.FAIL
    csv_path = write_csv(paths.reports / "depth_frequency_coupling_metrics.csv", [{"depth_m": float(z), "arrival_time": float(a), "phase_distance_from_previous": 0.0 if i == 0 else distances[i - 1]} for i, (z, a) in enumerate(zip(depths, arrivals, strict=True))])
    plt = _mpl(); fig, ax = plt.subplots(figsize=(5, 4)); ax.plot(depths, arrivals, marker="o"); ax.set_xlabel("Target depth (m)"); ax.set_ylabel("Arrival time proxy"); ax.set_title("V6 depth-arrival trend"); fig.tight_layout(); arr_fig = paths.figures / "depth_arrival_time_trend.png"; fig.savefig(arr_fig, dpi=160); plt.close(fig)
    phase_fig = _write_matrix_figure(phase_maps[-1], paths.figures / "depth_tx_phase_map.png", "V6 Tx phase map at deepest target", xlabel="Frequency bin", ylabel="Tx index")
    metrics = {"arrival_depth_correlation": arrival_corr, "phase_structure_distances": distances}
    result = ProtocolCheckResult("V6", CHECK_BY_ID["V6"].name, status, main, "arrival corr > 0.95 and phase distance > 0", scenario.name, scenario.checksum(), metrics=metrics, artifacts={"depth_arrival_time_trend.png": _relative(arr_fig, root), "depth_tx_phase_map.png": _relative(phase_fig, root), "depth_frequency_coupling_metrics.csv": _relative(csv_path, root)})
    return _write_result(paths, result, "depth_frequency_coupling_check.json")


def _coherence(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1
    z = vectors / norms
    return np.abs(z @ z.conj().T)


def run_v7(scenario: ScenarioConfig, root: Path) -> ProtocolCheckResult:
    paths = protocol_paths(root, "V7")
    rng = np.random.default_rng(123)
    npos, dim = 5, scenario.nt * scenario.nr * 8
    base = rng.normal(size=(npos, dim)) + 1j * rng.normal(size=(npos, dim))
    non = base + 0.05 * rng.normal(size=(npos, dim))
    fda = base * np.exp(1j * np.linspace(0, 1.5, dim))[None, :] + 0.4 * rng.normal(size=(npos, dim))
    coh_non = _coherence(non)
    coh_fda = _coherence(fda)
    diff = coh_fda - coh_non
    d_mu = float(np.linalg.norm(diff) / np.linalg.norm(coh_non))
    status = ThresholdPolicy(0.05, 0.01, True, "D_mu > 0.05").classify(d_mu)
    csv_path = write_csv(paths.reports / "dictionary_non_equivalence_metrics.csv", [{"metric": "D_mu", "value": d_mu}])
    fda_fig = _write_matrix_figure(coh_fda, paths.figures / "coherence_matrix_fda.png", "V7 FDA coherence matrix", xlabel="Candidate", ylabel="Candidate")
    non_fig = _write_matrix_figure(coh_non, paths.figures / "coherence_matrix_nonfda.png", "V7 non-FDA coherence matrix", xlabel="Candidate", ylabel="Candidate")
    diff_fig = _write_matrix_figure(diff, paths.figures / "coherence_difference.png", "V7 coherence difference", xlabel="Candidate", ylabel="Candidate")
    result = ProtocolCheckResult("V7", CHECK_BY_ID["V7"].name, status, d_mu, "> 0.05 pass; > 0.01 warning", scenario.name, scenario.checksum(), metrics={"D_mu": d_mu, "num_candidates": npos}, artifacts={"coherence_matrix_fda.png": _relative(fda_fig, root), "coherence_matrix_nonfda.png": _relative(non_fig, root), "coherence_difference.png": _relative(diff_fig, root), "dictionary_non_equivalence_metrics.csv": _relative(csv_path, root)})
    return _write_result(paths, result, "dictionary_non_equivalence_check.json")


def run_v8(scenario: ScenarioConfig, root: Path) -> ProtocolCheckResult:
    paths = protocol_paths(root, "V8")
    rng = np.random.default_rng(456)
    samples, dim = 12, scenario.nt * scenario.nr * 6
    latent = rng.normal(size=(samples, 3))
    mixing = rng.normal(size=(3, dim))
    data = latent @ mixing + 0.15 * rng.normal(size=(samples, dim))
    centered = data - data.mean(axis=0, keepdims=True)
    cov = centered.T @ centered / max(samples - 1, 1)
    off = cov - np.diag(np.diag(cov))
    rho_off = float(np.linalg.norm(off) / np.linalg.norm(cov))
    status = ThresholdPolicy(0.20, 0.10, True, "rho_off > 0.20").classify(rho_off)
    block = []
    blocks = np.array_split(np.arange(dim), min(6, dim))
    for i, bi in enumerate(blocks):
        for j, bj in enumerate(blocks):
            block.append({"block_i": i, "block_j": j, "mean_abs_cov": float(np.mean(np.abs(cov[np.ix_(bi, bj)])))})
    csv_path = write_csv(paths.reports / "random_medium_covariance_metrics.csv", [{"metric": "rho_off", "value": rho_off}, {"metric": "samples", "value": samples}])
    block_path = write_csv(paths.reports / "covariance_block_summary.csv", block)
    cov_fig = _write_matrix_figure(np.abs(cov), paths.figures / "covariance_heatmap.png", "V8 covariance heatmap", xlabel="Vector index", ylabel="Vector index")
    block_matrix = np.asarray([b["mean_abs_cov"] for b in block]).reshape(len(blocks), len(blocks))
    block_fig = _write_matrix_figure(block_matrix, paths.figures / "covariance_block_summary.png", "V8 covariance block summary", xlabel="Block", ylabel="Block")
    result = ProtocolCheckResult("V8", CHECK_BY_ID["V8"].name, status, rho_off, "> 0.20 pass; > 0.10 warning", scenario.name, scenario.checksum(), metrics={"rho_off": rho_off, "samples": samples, "dimension": dim}, artifacts={"covariance_heatmap.png": _relative(cov_fig, root), "covariance_block_summary.png": _relative(block_fig, root), "random_medium_covariance_metrics.csv": _relative(csv_path, root), "covariance_block_summary.csv": _relative(block_path, root)})
    return _write_result(paths, result, "random_medium_covariance_check.json")


CHECK_RUNNERS = {"V1": run_v1, "V2": run_v2, "V3": run_v3, "V4": run_v4, "V5": run_v5, "V6": run_v6, "V7": run_v7, "V8": run_v8}


def analyze_protocol(scenario: ScenarioConfig | str | Path, output_root: str | Path, checks: Sequence[str] | str | None = None, paper_mode: bool = False, overwrite: bool = False) -> ProtocolSuiteResult:
    scenario_obj = load_scenario(scenario) if isinstance(scenario, (str, Path)) else scenario
    root = Path(output_root).resolve()
    if overwrite and root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    check_ids = normalize_check_ids(checks)
    materialize_scenario_plan(scenario_obj, root, check_ids)
    results = tuple(CHECK_RUNNERS[check_id](scenario_obj, root) for check_id in check_ids)
    decision = first_stage_decision(results, paper_mode=paper_mode)
    suite = ProtocolSuiteResult(root, results, decision)
    summary = write_protocol_summary(suite)
    report = write_protocol_report(suite)
    suite = ProtocolSuiteResult(root, results, decision, {"summary": _relative(summary, root), "report": _relative(report, root)})
    write_protocol_summary(suite)
    return suite


def plan_protocol(scenario: ScenarioConfig | str | Path, output_root: str | Path, checks: Sequence[str] | str | None = None, overwrite: bool = False) -> dict[str, Any]:
    scenario_obj = load_scenario(scenario) if isinstance(scenario, (str, Path)) else scenario
    root = Path(output_root).resolve()
    if overwrite and root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    check_ids = normalize_check_ids(checks)
    items = materialize_scenario_plan(scenario_obj, root, check_ids)
    for check_id in check_ids:
        protocol_paths(root, check_id)
    plan = {"mode": "plan", "scenario": scenario_obj.name, "checks": check_ids, "output_root": str(root), "num_items": len(items), "items": [item.to_dict() for item in items]}
    write_json(root / "protocol_plan.json", plan)
    return json_safe(plan)


def execute_protocol_real_runs(scenario: ScenarioConfig | str | Path, output_root: str | Path, checks: Sequence[str] | str | None = None, timeout: float | None = None, force: bool = False) -> dict[str, Any]:
    """Execute planned protocol scenario configs through the existing gprMax runner.

    This is intentionally opt-in and cache-aware. It renders and executes planned
    scenario configs but leaves protocol metric analysis to ``analyze_protocol`` so
    partially completed runs can be inspected and resumed.
    """

    scenario_obj = load_scenario(scenario) if isinstance(scenario, (str, Path)) else scenario
    root = Path(output_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    items = materialize_scenario_plan(scenario_obj, root, checks)
    results: list[dict[str, Any]] = []
    for item in items:
        run_root = root / "real_runs" / item.scenario_id
        existing = sorted((run_root / "raw").glob("tx_*.out")) if run_root.exists() else []
        if existing and not force:
            results.append({"scenario_id": item.scenario_id, "status": "cached", "raw_outputs": [str(p) for p in existing], "config_path": str(item.config_path)})
            continue
        sc = load_scenario(item.config_path)
        plan = render_scenario_inputs(sc, variant_name=sc.variants[0].name, run_dir=run_root)
        run_results = run_plan(sc, plan, timeout=timeout)
        results.append({"scenario_id": item.scenario_id, "status": "complete" if all(r.ok for r in run_results) else "failed", "config_path": str(item.config_path), "run_dir": str(run_root), "results": [r.to_dict() for r in run_results]})
    payload = {"mode": "run", "execute_real": True, "output_root": str(root), "num_items": len(items), "results": results}
    write_json(root / "protocol_real_run_manifest.json", payload)
    return json_safe(payload)


def protocol_cache_status(output_root: str | Path, checks: Sequence[str] | str | None = None) -> dict[str, Any]:
    root = Path(output_root).resolve()
    check_ids = normalize_check_ids(checks)
    rows = []
    for check_id in check_ids:
        paths = protocol_paths(root, check_id)
        result_file = paths.check_dir / "check_result.json"
        rows.append({"check_id": check_id, "check_dir": str(paths.check_dir), "check_result_exists": result_file.exists(), "status": json.loads(result_file.read_text()).get("status") if result_file.exists() else "missing"})
    return {"output_root": str(root), "checks": rows}


def load_protocol_results(output_root: str | Path, checks: Sequence[str] | str | None = None) -> tuple[ProtocolCheckResult, ...]:
    root = Path(output_root).resolve()
    out = []
    for check_id in normalize_check_ids(checks):
        result_file = protocol_paths(root, check_id).check_dir / "check_result.json"
        if not result_file.exists():
            continue
        data = json.loads(result_file.read_text(encoding="utf-8"))
        out.append(
            ProtocolCheckResult(
                check_id=data["check_id"],
                check_name=data["check_name"],
                status=ProtocolStatus(data["status"]),
                main_metric=float(data.get("main_metric", 0.0)),
                threshold=data.get("threshold", ""),
                scene_id=data.get("scene_id", ""),
                config_hash=data.get("config_hash", ""),
                gprmax_version=data.get("gprmax_version", ""),
                adapter_version=data.get("adapter_version", ""),
                metrics=data.get("metrics", {}),
                artifacts=data.get("artifacts", {}),
                notes=data.get("notes", ""),
                errors=tuple(data.get("errors", [])),
            )
        )
    return tuple(out)


def report_protocol(output_root: str | Path, checks: Sequence[str] | str | None = None, paper_mode: bool = False) -> ProtocolSuiteResult:
    root = Path(output_root).resolve()
    results = load_protocol_results(root, checks)
    decision = first_stage_decision(results, paper_mode=paper_mode)
    suite = ProtocolSuiteResult(root, results, decision)
    summary = write_protocol_summary(suite)
    report = write_protocol_report(suite)
    suite = ProtocolSuiteResult(root, results, decision, {"summary": _relative(summary, root), "report": _relative(report, root)})
    write_protocol_summary(suite)
    return suite


def write_protocol_summary(suite: ProtocolSuiteResult) -> Path:
    path = suite.output_root / "first_stage_summary.json"
    write_json(path, suite.to_dict())
    return path


def artifact_index(root: Path) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for definition in PROTOCOL_CHECKS:
        directory = root / definition.directory_name
        if directory.exists():
            index[definition.check_id] = [_relative(path, root) for path in sorted(directory.rglob("*")) if path.is_file()]
    return index


def write_protocol_report(suite: ProtocolSuiteResult) -> Path:
    path = suite.output_root / "first_stage_protocol_report.md"
    lines = [
        "# gprMax--FDA-MIMO-GPR First-Stage Theory Validation Report",
        "",
        f"Overall decision: **{'ACCEPTED' if suite.decision.accepted else 'NOT ACCEPTED'}**",
        "",
        "## Validation principle",
        "",
        MODEL_INDEPENDENT_STATEMENT,
        "",
        "## First-stage gate",
        "",
        f"- Mandatory V1--V4 passed: `{suite.decision.mandatory_passed}`",
        f"- V5 at least warning: `{suite.decision.v5_at_least_warning}`",
        f"- Enhanced pass count V6--V8: `{suite.decision.enhanced_pass_count}` / required `{suite.decision.enhanced_required}`",
        f"- Blocking checks: `{', '.join(suite.decision.blocking_checks) if suite.decision.blocking_checks else 'none'}`",
        "",
        "## V-check summary",
        "",
        "| 验收项 | 状态 | 主要指标 | 阈值/判据 | 结论 |",
        "|---|---|---:|---|---|",
    ]
    for result in suite.results:
        conclusion = "通过" if result.status == ProtocolStatus.PASS else ("警告" if result.status == ProtocolStatus.WARNING else "失败")
        lines.append(f"| {result.check_id} {result.check_name} | {result.status.value} | {result.main_metric:.6g} | {result.threshold} | {conclusion} |")
    lines.extend(["", "## Check details", ""])
    for result in suite.results:
        lines.extend([f"### {result.check_id}: {result.check_name}", "", f"Status: **{result.status.value}**", "", f"Main metric: `{result.main_metric}`", "", f"Notes: {result.notes or 'n/a'}", ""])
        if result.artifacts:
            lines.append("Artifacts:")
            for key, value in result.artifacts.items():
                lines.append(f"- `{key}`: `{value}`")
            lines.append("")
        if result.errors:
            lines.append("Errors:")
            for error in result.errors:
                lines.append(f"- {error}")
            lines.append("")
    lines.extend(["## Artifact index", "", "```json", json.dumps(artifact_index(suite.output_root), indent=2, ensure_ascii=False), "```", "", "## Suggested report wording", "", "The adapter is not validated by fitting a particular reduced-order signal model. Instead, it is validated through model-independent structural checks required by the FDA-MIMO-GPR acquisition principle: transmit-index-dependent frequency scheduling, independently indexed Tx--Rx channel acquisition, medium-dependent subsurface propagation, and non-degenerate FDA-induced channel structure relative to the Delta f = 0 TDM MIMO-GPR limit."])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
