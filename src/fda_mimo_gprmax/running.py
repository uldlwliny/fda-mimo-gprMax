"""External gprMax execution and run manifest helpers."""

from __future__ import annotations

import hashlib
import json
import os
import statistics
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import ScenarioConfig, stable_json
from .rendering import RenderPlan, RenderedInput


def _format_duration(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, sec = divmod(int(round(seconds)), 60)
    if minutes < 60:
        return f"{minutes}m {sec:02d}s"
    hours, minute = divmod(minutes, 60)
    return f"{hours}h {minute:02d}m"


def _emit_progress(message: str) -> None:
    """Emit human-readable progress without contaminating stdout JSON."""
    print(f"[fda-mimo-gprmax] {message}", file=sys.stderr, flush=True)


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
    geometry_only: bool = False

    @property
    def ok(self) -> bool:
        if self.geometry_only:
            return self.returncode == 0
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
            "geometry_only": self.geometry_only,
            "ok": self.ok,
        }


def build_command_plan(
    scenario: ScenarioConfig,
    plan: RenderPlan,
    item: RenderedInput,
    geometry_only: bool = False,
) -> CommandPlan:
    command = [*scenario.execution.executable, str(item.input_path)]
    if geometry_only:
        command.append("--geometry-only")
        command.extend(scenario.execution.extra_args)
    else:
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


def output_is_stale(
    item: RenderedInput, manifest: dict[str, Any] | None = None
) -> bool:
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
    with (
        command_plan.stdout_path.open("w", encoding="utf-8") as stdout,
        command_plan.stderr_path.open("w", encoding="utf-8") as stderr,
    ):
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
    if command_plan.geometry_only:
        exists = False
        checksum = None

    else:
        gprmax_output = _gprmax_output_for_input(command_plan.input_path)

        if gprmax_output.exists():
            command_plan.expected_output_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

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
        geometry_only=command_plan.geometry_only,
    )


def write_manifest(
    plan: RenderPlan,
    scenario: ScenarioConfig,
    command_plans: list[CommandPlan],
    results: list[RunResult] | None = None,
    stage: str = "planned",
) -> Path:
    payload = {
        "stage": stage,
        "scenario": scenario.metadata(),
        "media": scenario.media.metadata(),
        "render_plan": plan.to_manifest(),
        "commands": [cmd.to_dict() for cmd in command_plans],
        "results": [] if results is None else [res.to_dict() for res in results],
        "checksums": {
            "manifest_basis": hashlib.sha256(
                stable_json(plan.to_manifest()).encode("utf-8")
            ).hexdigest(),
        },
    }
    path = plan.logs_dir / "run_manifest.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def run_plan(
    scenario: ScenarioConfig,
    plan: RenderPlan,
    geometry_only: bool = False,
    timeout: float | None = None,
    progress: bool = True,
    heartbeat_seconds: float = 30.0,
) -> list[RunResult]:
    commands = [
        build_command_plan(scenario, plan, item, geometry_only=geometry_only)
        for item in plan.inputs
    ]
    write_manifest(plan, scenario, commands, stage="planned")
    results: list[RunResult] = []
    durations: list[float] = []
    total = len(commands)
    run_start = time.perf_counter()

    if progress:
        mode = "geometry-only" if geometry_only else "FDTD"
        _emit_progress(
            f"{plan.scenario_name}/{plan.variant}: {mode} start | {total} Tx"
        )

    for ordinal, cmd in enumerate(commands, start=1):
        tx_start = time.perf_counter()

        if progress:
            eta = (
                statistics.median(durations) * (total - len(results))
                if durations
                else None
            )
            eta_text = "unknown" if eta is None else _format_duration(eta)
            _emit_progress(
                f"{plan.scenario_name}/{plan.variant}: "
                f"Tx {ordinal}/{total} (tx_{cmd.tx_index:03d}) START | "
                f"elapsed {_format_duration(tx_start - run_start)} | "
                f"sim ETA {eta_text}"
            )

        heartbeat_stop = threading.Event()
        heartbeat_thread: threading.Thread | None = None

        if progress and heartbeat_seconds > 0:
            def heartbeat(
                *,
                _ordinal: int = ordinal,
                _cmd: CommandPlan = cmd,
                _tx_start: float = tx_start,
            ) -> None:
                while not heartbeat_stop.wait(heartbeat_seconds):
                    tx_elapsed = time.perf_counter() - _tx_start
                    if durations:
                        median_tx = statistics.median(durations)
                        remaining = max(
                            0.0,
                            median_tx * (total - len(results)) - tx_elapsed,
                        )
                        eta_text = _format_duration(remaining)
                    else:
                        eta_text = "unknown"
                    _emit_progress(
                        f"{plan.scenario_name}/{plan.variant}: "
                        f"Tx {_ordinal}/{total} (tx_{_cmd.tx_index:03d}) RUNNING | "
                        f"tx elapsed {_format_duration(tx_elapsed)} | "
                        f"sim ETA {eta_text}"
                    )

            heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
            heartbeat_thread.start()

        try:
            result = run_command(cmd, timeout=timeout)
        finally:
            heartbeat_stop.set()
            if heartbeat_thread is not None:
                heartbeat_thread.join()

        results.append(result)
        durations.append(result.elapsed_seconds)
        write_manifest(plan, scenario, commands, results, stage="running")

        if progress:
            completed = len(results)
            remaining = total - completed
            eta = statistics.median(durations) * remaining
            status = "DONE" if result.ok else f"FAILED(rc={result.returncode})"
            _emit_progress(
                f"{plan.scenario_name}/{plan.variant}: "
                f"Tx {ordinal}/{total} (tx_{cmd.tx_index:03d}) {status} | "
                f"{100.0 * completed / total:.1f}% | "
                f"tx {_format_duration(result.elapsed_seconds)} | "
                f"elapsed {_format_duration(time.perf_counter() - run_start)} | "
                f"sim ETA {_format_duration(eta)}"
            )

        if not result.ok and scenario.execution.failure_policy == "stop":
            break

    write_manifest(
        plan,
        scenario,
        commands,
        results,
        stage=(
            "complete"
            if all(r.ok for r in results) and len(results) == len(commands)
            else "failed"
        ),
    )

    if progress:
        ok_count = sum(r.ok for r in results)
        _emit_progress(
            f"{plan.scenario_name}/{plan.variant}: simulation phase finished | "
            f"{ok_count}/{total} Tx OK | "
            f"elapsed {_format_duration(time.perf_counter() - run_start)}"
        )

    return results
