from __future__ import annotations

from fda_mimo_gprmax.config import ScenarioConfig, load_scenario
from fda_mimo_gprmax.rendering import render_scenario_inputs


def test_render_per_tx_inputs(scenario_yaml, tmp_path):
    scenario = load_scenario(scenario_yaml)
    plan = render_scenario_inputs(scenario, "target", run_dir=tmp_path / "run")
    assert len(plan.inputs) == scenario.nt
    for item in plan.inputs:
        text = item.input_path.read_text()
        assert text.count("#hertzian_dipole:") == 1
        assert text.count("#rx:") == scenario.nr
        assert f"{item.center_frequency:.9g}" in text
        assert item.component == "Ez"
    assert (plan.logs_dir / "run_manifest.json").exists()


def test_render_deterministic(scenario_yaml, tmp_path):
    scenario = load_scenario(scenario_yaml)
    plan1 = render_scenario_inputs(scenario, "target", run_dir=tmp_path / "r1")
    plan2 = render_scenario_inputs(scenario, "target", run_dir=tmp_path / "r2")
    assert [i.checksum for i in plan1.inputs] == [i.checksum for i in plan2.inputs]


def test_render_excitation_file_mode(scenario_yaml, tmp_path):
    import yaml

    data = yaml.safe_load(scenario_yaml.read_text())
    data["waveform"] = {"mode": "excitation_file", "samples": [0, 1, 0, -1], "identifier_prefix": "custom"}
    scenario = ScenarioConfig.from_mapping(data, source_path=scenario_yaml)
    plan = render_scenario_inputs(scenario, "target", run_dir=tmp_path / "run")
    text = plan.inputs[0].input_path.read_text()
    assert "#excitation_file:" in text
    assert plan.inputs[0].excitation_path is not None
    assert plan.inputs[0].excitation_path.exists()


def test_geometry_only_hint(scenario_yaml, tmp_path):
    import yaml

    data = yaml.safe_load(scenario_yaml.read_text())
    data["scene"]["geometry_view"] = True
    scenario = ScenarioConfig.from_mapping(data, source_path=scenario_yaml)
    plan = render_scenario_inputs(scenario, "target", run_dir=tmp_path / "run")
    assert "--geometry-only" in plan.geometry_only_command_hint
    assert "#geometry_view:" in plan.inputs[0].input_path.read_text()
