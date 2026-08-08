from __future__ import annotations

import json
import subprocess

from fda_mimo_gprmax.config import load_scenario
from fda_mimo_gprmax.rendering import render_scenario_inputs
from fda_mimo_gprmax.running import build_command_plan, output_is_stale, run_plan


def test_build_command_plan_contains_flags(scenario_yaml, tmp_path):
    scenario = load_scenario(scenario_yaml)
    plan = render_scenario_inputs(scenario, "target", run_dir=tmp_path / "run")
    cmd = build_command_plan(scenario, plan, plan.inputs[0], geometry_only=True)
    assert cmd.command[:3] == ("python", "-m", "gprMax")
    assert "--geometry-only" in cmd.command
    assert "-gpu" not in cmd.command
    assert "-mpi" not in cmd.command
    assert cmd.env == {}


def test_run_plan_success_mocked(monkeypatch, scenario_yaml, tmp_path):
    scenario = load_scenario(scenario_yaml)
    plan = render_scenario_inputs(scenario, "target", run_dir=tmp_path / "run")

    def fake_run(command, cwd, env, stdout, stderr, text, timeout, check):
        tx = int(str(command[3]).split("generated_tx_")[1].split(".in")[0])
        (plan.raw_dir / f"tx_{tx:03d}.out").write_bytes(b"fake")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    results = run_plan(scenario, plan)
    assert len(results) == scenario.nt
    assert all(r.ok for r in results)
    manifest = json.loads((plan.logs_dir / "run_manifest.json").read_text())
    assert manifest["stage"] == "complete"
    assert len(manifest["results"]) == scenario.nt


def test_run_plan_failure_stops(monkeypatch, scenario_yaml, tmp_path):
    scenario = load_scenario(scenario_yaml)
    plan = render_scenario_inputs(scenario, "target", run_dir=tmp_path / "run")

    def fake_run(command, cwd, env, stdout, stderr, text, timeout, check):
        return subprocess.CompletedProcess(command, 2)

    monkeypatch.setattr(subprocess, "run", fake_run)
    results = run_plan(scenario, plan)
    assert len(results) == 1
    assert not results[0].ok
    manifest = json.loads((plan.logs_dir / "run_manifest.json").read_text())
    assert manifest["stage"] == "failed"


def test_stale_output_detection(scenario_yaml, tmp_path):
    scenario = load_scenario(scenario_yaml)
    plan = render_scenario_inputs(scenario, "target", run_dir=tmp_path / "run")
    item = plan.inputs[0]
    assert output_is_stale(item)
    item.output_path.write_bytes(b"raw")
    assert not output_is_stale(item)
    assert output_is_stale(
        item,
        {
            "render_plan": {
                "inputs": [{"tx_index": item.tx_index, "checksum": "different"}]
            }
        },
    )


def test_geometry_only_success_does_not_require_out(
    monkeypatch,
    scenario_yaml,
    tmp_path,
):
    scenario = load_scenario(scenario_yaml)

    plan = render_scenario_inputs(
        scenario,
        "target",
        run_dir=tmp_path / "run",
    )

    def fake_run(
        command,
        cwd,
        env,
        stdout,
        stderr,
        text,
        timeout,
        check,
    ):
        return subprocess.CompletedProcess(
            command,
            0,
        )

    monkeypatch.setattr(
        subprocess,
        "run",
        fake_run,
    )

    results = run_plan(
        scenario,
        plan,
        geometry_only=True,
    )

    assert len(results) == scenario.nt

    assert all(r.ok for r in results)

    assert all(r.geometry_only for r in results)

    assert all(not r.output_exists for r in results)

    manifest = json.loads((plan.logs_dir / "run_manifest.json").read_text())

    assert manifest["stage"] == "complete"


def test_run_plan_progress_is_emitted_to_stderr(
    monkeypatch,
    scenario_yaml,
    tmp_path,
    capsys,
):
    scenario = load_scenario(scenario_yaml)
    plan = render_scenario_inputs(scenario, "target", run_dir=tmp_path / "run")

    def fake_run(command, cwd, env, stdout, stderr, text, timeout, check):
        tx = int(str(command[3]).split("generated_tx_")[1].split(".in")[0])
        (plan.raw_dir / f"tx_{tx:03d}.out").write_bytes(b"fake")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    results = run_plan(
        scenario,
        plan,
        progress=True,
        heartbeat_seconds=0,
    )
    captured = capsys.readouterr()

    assert all(r.ok for r in results)
    assert captured.out == ""
    assert "Tx 1/" in captured.err
    assert "DONE" in captured.err
    assert "simulation phase finished" in captured.err
