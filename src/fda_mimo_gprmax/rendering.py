"""gprMax input rendering for TDM FDA-MIMO acquisitions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import ScenarioConfig, VariantConfig, checksum_text, stable_json
from .media import render_debye_material_commands


@dataclass(frozen=True)
class RenderedInput:
    tx_index: int
    variant: str
    input_path: Path
    output_path: Path
    waveform_id: str
    center_frequency: float
    source_position: tuple[float, float, float]
    receiver_positions: list[list[float]]
    component: str
    excitation_path: Path | None = None
    checksum: str = ""

    def to_manifest(self) -> dict[str, Any]:
        return {
            "tx_index": self.tx_index,
            "variant": self.variant,
            "input_path": str(self.input_path),
            "output_path": str(self.output_path),
            "waveform_id": self.waveform_id,
            "center_frequency": self.center_frequency,
            "source_position": list(self.source_position),
            "receiver_positions": self.receiver_positions,
            "component": self.component,
            "excitation_path": (
                None if self.excitation_path is None else str(self.excitation_path)
            ),
            "checksum": self.checksum,
        }


@dataclass(frozen=True)
class RenderPlan:
    scenario_name: str
    variant: str
    run_dir: Path
    config_dir: Path
    raw_dir: Path
    logs_dir: Path
    processed_dir: Path
    figures_dir: Path
    inputs: tuple[RenderedInput, ...]
    config_checksum: str
    geometry_only_command_hint: list[str]

    def to_manifest(self) -> dict[str, Any]:
        return {
            "scenario_name": self.scenario_name,
            "variant": self.variant,
            "run_dir": str(self.run_dir),
            "config_dir": str(self.config_dir),
            "raw_dir": str(self.raw_dir),
            "logs_dir": str(self.logs_dir),
            "processed_dir": str(self.processed_dir),
            "figures_dir": str(self.figures_dir),
            "config_checksum": self.config_checksum,
            "geometry_only_command_hint": self.geometry_only_command_hint,
            "inputs": [item.to_manifest() for item in self.inputs],
        }


def _fmt(values: tuple[float, ...] | list[float]) -> str:
    return " ".join(f"{float(v):.9g}" for v in values)


def _rx_line(index: int, position: list[float], component: str) -> str:
    return f"#rx: {_fmt(position)} rx{index + 1:03d} {component}"


def _source_line(scenario: ScenarioConfig, tx_index: int, waveform_id: str) -> str:
    pos = scenario.array.tx_positions[tx_index].tolist()
    return f"#hertzian_dipole: {scenario.array.polarization} {_fmt(pos)} {waveform_id}"


def _write_excitation_file(
    scenario: ScenarioConfig,
    path: Path,
    waveform_id: str,
) -> None:
    wf = scenario.waveform

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    scaled_samples = [float(sample) * float(wf.amplitude) for sample in wf.samples]

    with path.open(
        "w",
        encoding="utf-8",
    ) as f:
        if wf.time:
            f.write(f"time {waveform_id}\n")

            for t, sample in zip(
                wf.time,
                scaled_samples,
                strict=True,
            ):
                f.write(f"{t:.17g} {sample:.17g}\n")

        else:
            f.write(f"{waveform_id}\n")

            for sample in scaled_samples:
                f.write(f"{sample:.17g}\n")


def _waveform_lines(
    scenario: ScenarioConfig, tx_index: int, config_dir: Path
) -> tuple[list[str], Path | None, str]:
    wf = scenario.waveform
    waveform_id = wf.identifier(tx_index)
    center_frequency = scenario.fda.frequencies[tx_index]
    if wf.mode == "builtin":
        return (
            [
                f"#waveform: {wf.shape} {wf.amplitude:.9g} {center_frequency:.9g} {waveform_id}"
            ],
            None,
            waveform_id,
        )
    excitation_path = config_dir / f"excitation_tx_{tx_index:03d}.txt"
    _write_excitation_file(scenario, excitation_path, waveform_id)
    rel = excitation_path.name
    return [f"#excitation_file: {rel}"], excitation_path, waveform_id


def render_structured_media_commands(scenario: ScenarioConfig) -> list[str]:
    commands: list[str] = []
    for approx in scenario.media.debye_approximations:
        commands.extend(render_debye_material_commands(approx))
    return commands


def render_input_text(
    scenario: ScenarioConfig,
    variant: VariantConfig,
    tx_index: int,
    config_dir: Path,
    *,
    geometry_only: bool = False,
) -> tuple[str, Path | None, str]:
    waveform_lines, excitation_path, waveform_id = _waveform_lines(
        scenario, tx_index, config_dir
    )
    lines: list[str] = [
        f"#title: {scenario.scene.title} | {scenario.name} | {variant.name} | tx_{tx_index:03d}",
        scenario.domain.to_gprmax(),
        scenario.grid.to_gprmax(),
        scenario.time.to_gprmax(),
        "",
    ]
    media_commands = render_structured_media_commands(scenario)
    lines.extend(media_commands)
    if media_commands:
        lines.append("")
    lines.extend(scenario.scene.materials)
    if scenario.scene.materials:
        lines.append("")
    lines.extend(scenario.scene.geometry)
    lines.extend(variant.geometry)
    if scenario.scene.geometry or variant.geometry:
        lines.append("")
    lines.extend(waveform_lines)
    lines.append(_source_line(scenario, tx_index, waveform_id))
    for rx_index, pos in enumerate(scenario.array.rx_positions.tolist()):
        lines.append(_rx_line(rx_index, pos, scenario.receiver.component))
    if geometry_only and scenario.scene.geometry_view:
        sx, sy, sz = scenario.domain.size
        dx, dy, dz = scenario.grid.spacing
        lines.extend(
            [
                "",
                f"#geometry_view: 0 0 0 {sx:.9g} {sy:.9g} {sz:.9g} {dx:.9g} {dy:.9g} {dz:.9g} geometry_tx_{tx_index:03d} n",
            ]
        )
    lines.append("")
    return "\n".join(lines), excitation_path, waveform_id


def render_scenario_inputs(
    scenario: ScenarioConfig,
    variant_name: str | None = None,
    run_dir: str | Path | None = None,
    *,
    geometry_only: bool = False,
) -> RenderPlan:
    variant = scenario.variant(variant_name or scenario.variants[0].name)
    base = (
        Path(run_dir)
        if run_dir is not None
        else scenario.output_root / scenario.name / variant.name
    )
    base = base.resolve()
    config_dir = base / "config"
    raw_dir = base / "raw"
    logs_dir = base / "logs"
    processed_dir = base / "processed"
    figures_dir = base / "figures"
    for d in [config_dir, raw_dir, logs_dir, processed_dir, figures_dir]:
        d.mkdir(parents=True, exist_ok=True)

    rendered: list[RenderedInput] = []
    for tx_index in range(scenario.nt):
        text, excitation_path, waveform_id = render_input_text(
            scenario,
            variant,
            tx_index,
            config_dir,
            geometry_only=geometry_only,
        )
        input_path = config_dir / f"generated_tx_{tx_index:03d}.in"
        input_path.write_text(text, encoding="utf-8")
        digest = checksum_text(text)
        output_path = raw_dir / f"tx_{tx_index:03d}.out"
        rendered.append(
            RenderedInput(
                tx_index=tx_index,
                variant=variant.name,
                input_path=input_path,
                output_path=output_path,
                waveform_id=waveform_id,
                center_frequency=scenario.fda.frequencies[tx_index],
                source_position=tuple(
                    float(v) for v in scenario.array.tx_positions[tx_index].tolist()
                ),
                receiver_positions=scenario.array.rx_positions.tolist(),
                component=scenario.receiver.component,
                excitation_path=excitation_path,
                checksum=digest,
            )
        )

    plan = RenderPlan(
        scenario_name=scenario.name,
        variant=variant.name,
        run_dir=base,
        config_dir=config_dir,
        raw_dir=raw_dir,
        logs_dir=logs_dir,
        processed_dir=processed_dir,
        figures_dir=figures_dir,
        inputs=tuple(rendered),
        config_checksum=scenario.checksum(),
        geometry_only_command_hint=(
            [
                *scenario.execution.executable,
                str(rendered[0].input_path),
                "--geometry-only",
            ]
            if rendered and geometry_only
            else []
        ),
    )
    write_render_manifest(plan, scenario)
    return plan


def write_render_manifest(plan: RenderPlan, scenario: ScenarioConfig) -> Path:
    path = plan.logs_dir / "run_manifest.json"
    payload = {
        "stage": "rendered",
        "scenario": scenario.metadata(),
        "media": scenario.media.metadata(),
        "render_plan": plan.to_manifest(),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def manifest_checksum(plan: RenderPlan) -> str:
    return checksum_text(stable_json(plan.to_manifest()))
