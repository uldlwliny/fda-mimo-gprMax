"""External gprMax execution and run manifest helpers."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import ScenarioConfig, stable_json
from .rendering import RenderPlan, RenderedInput


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class CommandPlan:
    tx_index: int
    command: tuple[str, ...]
    cwd: Path
    env: dict[str, str]
    input_path: Path
    expected_output_path: Path
    stdout_path: Path
    stderr_path: Path
    geometry_only: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "tx_index": self.tx_index,
            "command": list(self.command),
            "cwd": str(self.cwd),
            "env": self.env,
            "input_path": str(self.input_path),
            "expected_output_path": str(self.expected_output_path),
            "stdout_path": str(self.stdout_path),
            "stderr_path": str(self.stderr_path),
            "geometry_only": self.geometry_only,
        }


@dataclass(frozen=True)
class RunResult:
    tx_index: int
    command: tuple[str, ...]
    returncode: int
    elapsed_seconds: float
    stdout_path: Path
    stderr_path: Path
    output_path: Path
    output_exists: bool
    output_checksum: str | None

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and self.output_exists

    def to_dict(self) -> dict[str, Any]:
        return {
            "tx_index": self.tx_index,
            "command": list(self.command),
            "returncode": self.returncode,
            "elapsed_seconds": self.elapsed_seconds,
            "stdout_path": str(self.stdout_path),
            "stderr_path": str(self.stderr_path),
            "output_path": str(self.output_path),
            "output_exists": self.output_exists,
            "output_checksum": self.output_checksum,
            "ok": self.ok,
        }


def build_command_plan(scenario: ScenarioConfig, plan: RenderPlan, item: RenderedInput, geometry_only: bool = False) -> CommandPlan:
    command = [*scenario.execution.executable, str(item.input_path)]
    if geometry_only:
        command.append("--geometry-only")
    command.extend(scenario.execution.command_suffix())
    env: dict[str, str] = {}
    if scenario.execution.omp_threads is not None:
        env["OMP_NUM_THREADS"] = str(scenario.execution.omp_threads)
    return CommandPlan(
        tx_index=item.tx_index,
        command=tuple(command),
        cwd=plan.run_dir,
        env=env,
        input_path=item.input_path,
        expected_output_path=item.output_path,
        stdout_path=plan.logs_dir / f"gprmax_stdout_tx_{item.tx_index:03d}.txt",
        stderr_path=plan.logs_dir / f"gprmax_stderr_tx_{item.tx_index:03d}.txt",
        geometry_only=geometry_only,
    )


def output_is_stale(item: RenderedInput, manifest: dict[str, Any] | None = None) -> bool:
    if not item.output_path.exists():
        return True
    if manifest is None:
        return False
    prior = manifest.get("render_plan", {}).get("inputs", [])
    for rec in prior:
        if rec.get("tx_index") == item.tx_index:
            return rec.get("checksum") != item.checksum
    return True


def _gprmax_output_for_input(input_path: Path) -> Path:
    """Return the path gprMax uses for its output given an input file.

    gprMax writes the output file to the same directory as the input file
    with the same base name but a ``.out`` extension.
    """
    return input_path.with_suffix(".out")


def run_command(command_plan: CommandPlan, timeout: float | None = None) -> RunResult:
    env = os.environ.copy()
    env.update(command_plan.env)
    command_plan.stdout_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    with command_plan.stdout_path.open("w", encoding="utf-8") as stdout, command_plan.stderr_path.open("w", encoding="utf-8") as stderr:
        proc = subprocess.run(
            command_plan.command,
            cwd=command_plan.cwd,
            env=env,
            stdout=stdout,
            stderr=stderr,
            text=True,
            timeout=timeout,
            check=False,
        )
    elapsed = time.perf_counter() - start
    # gprMax writes ``.out`` next to the input file; relocate it to the expected path.
    gprmax_output = _gprmax_output_for_input(command_plan.input_path)
    if gprmax_output.exists():
        command_plan.expected_output_path.parent.mkdir(parents=True, exist_ok=True)
        gprmax_output.replace(command_plan.expected_output_path)
    exists = command_plan.expected_output_path.exists()
    checksum = file_sha256(command_plan.expected_output_path) if exists else None
    return RunResult(
        tx_index=command_plan.tx_index,
        command=command_plan.command,
        returncode=proc.returncode,
        elapsed_seconds=elapsed,
        stdout_path=command_plan.stdout_path,
        stderr_path=command_plan.stderr_path,
        output_path=command_plan.expected_output_path,
        output_exists=exists,
        output_checksum=checksum,
    )


def write_manifest(plan: RenderPlan, scenario: ScenarioConfig, command_plans: list[CommandPlan], results: list[RunResult] | None = None, stage: str = "planned") -> Path:
    payload = {
        "stage": stage,
        "scenario": scenario.metadata(),
        "media": scenario.media.metadata(),
        "render_plan": plan.to_manifest(),
        "commands": [cmd.to_dict() for cmd in command_plans],
        "results": [] if results is None else [res.to_dict() for res in results],
        "checksums": {
            "manifest_basis": hashlib.sha256(stable_json(plan.to_manifest()).encode("utf-8")).hexdigest(),
        },
    }
    path = plan.logs_dir / "run_manifest.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def run_plan(scenario: ScenarioConfig, plan: RenderPlan, geometry_only: bool = False, timeout: float | None = None) -> list[RunResult]:
    commands = [build_command_plan(scenario, plan, item, geometry_only=geometry_only) for item in plan.inputs]
    write_manifest(plan, scenario, commands, stage="planned")
    results: list[RunResult] = []
    for cmd in commands:
        result = run_command(cmd, timeout=timeout)
        results.append(result)
        write_manifest(plan, scenario, commands, results, stage="running")
        if not result.ok and scenario.execution.failure_policy == "stop":
            break
    write_manifest(plan, scenario, commands, results, stage="complete" if all(r.ok for r in results) and len(results) == len(commands) else "failed")
    return results
