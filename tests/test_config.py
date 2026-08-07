from __future__ import annotations

import pytest

from fda_mimo_gprmax.config import ScenarioConfig, ValidationError, load_scenario


def test_load_valid_config_and_checksum(scenario_yaml):
    scenario = load_scenario(scenario_yaml)
    assert scenario.name == "unit_scene"
    assert scenario.nt == 2
    assert scenario.nr == 2
    assert scenario.fda.frequencies == (1.0e9, 1.05e9)
    assert (
        scenario.checksum()
        == ScenarioConfig.from_mapping(
            scenario.raw_data, source_path=scenario_yaml
        ).checksum()
    )


def test_missing_required_section_rejected(scenario_yaml):
    import yaml

    data = yaml.safe_load(scenario_yaml.read_text())
    data.pop("array")
    with pytest.raises(ValidationError, match="array section is required"):
        ScenarioConfig.from_mapping(data)


def test_invalid_fda_schedule_rejected(scenario_yaml):
    import yaml

    data = yaml.safe_load(scenario_yaml.read_text())
    data["fda"]["f0"] = -1.0
    with pytest.raises(ValidationError, match="positive"):
        ScenarioConfig.from_mapping(data)


def test_strict_array_expansion_preserves_axes(scenario_yaml):
    scenario = load_scenario(scenario_yaml)
    assert scenario.array.mode == "strict"
    assert (scenario.array.tx_positions == scenario.array.rx_positions).all()
    assert scenario.array.metadata()["tx_positions"] != []


def test_offset_array_expansion(scenario_yaml):
    import yaml

    data = yaml.safe_load(scenario_yaml.read_text())
    data["array"]["mode"] = "offset"
    data["array"]["rx_offset"] = [0.01, 0.0, 0.0]
    scenario = ScenarioConfig.from_mapping(data)
    assert scenario.array.mode == "offset"
    assert scenario.array.rx_positions[0, 0] == pytest.approx(
        scenario.array.tx_positions[0, 0] + 0.01
    )


def test_variants_unique_names(scenario_yaml):
    import yaml

    data = yaml.safe_load(scenario_yaml.read_text())
    data["variants"] = [{"name": "target"}, {"name": "target"}]
    with pytest.raises(ValidationError, match="unique"):
        ScenarioConfig.from_mapping(data)


def test_unknown_builtin_waveform_rejected(
    scenario_yaml,
):
    import yaml

    data = yaml.safe_load(scenario_yaml.read_text())

    data["waveform"] = {
        "mode": "builtin",
        "shape": "not_a_gprmax_waveform",
    }

    with pytest.raises(
        ValidationError,
        match="waveform.shape",
    ):
        ScenarioConfig.from_mapping(data)


def test_gprmax_dt_estimate_for_3d_1cm_grid():
    from fda_mimo_gprmax.config import (
        DomainConfig,
        GridConfig,
        estimate_gprmax_dt,
    )

    domain = DomainConfig(
        size=(
            0.6,
            0.4,
            0.3,
        )
    )

    grid = GridConfig(
        spacing=(
            0.01,
            0.01,
            0.01,
        )
    )

    dt = estimate_gprmax_dt(
        domain,
        grid,
    )

    assert dt == pytest.approx(
        1.9258332e-11,
        rel=1e-6,
    )
