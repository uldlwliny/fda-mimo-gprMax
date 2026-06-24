from __future__ import annotations

import json
from pathlib import Path

import pytest

from fda_mimo_gprmax.config import ValidationError, load_scenario
from fda_mimo_gprmax.rendering import render_scenario_inputs


EXAMPLE = Path("examples/minimal_cole_cole_scene.yaml")


def test_render_cole_cole_material_commands(tmp_path: Path) -> None:
    scenario = load_scenario(EXAMPLE)
    plan = render_scenario_inputs(scenario, variant_name="target", run_dir=tmp_path / "run")
    assert len(plan.inputs) == scenario.nt
    for item in plan.inputs:
        text = item.input_path.read_text(encoding="utf-8")
        assert "#material:" in text
        assert "#add_dispersion_debye:" in text
        assert "#cole_cole" not in text.lower()
        assert "soil" in text
        assert "#box: 0 0 0 0.60 0.40 0.14 soil" in text
        assert text.index("#add_dispersion_debye:") < text.index("#box:")


def test_render_cole_cole_deterministic(tmp_path: Path) -> None:
    scenario = load_scenario(EXAMPLE)
    p1 = render_scenario_inputs(scenario, variant_name="target", run_dir=tmp_path / "run1")
    p2 = render_scenario_inputs(scenario, variant_name="target", run_dir=tmp_path / "run2")
    for a, b in zip(p1.inputs, p2.inputs, strict=True):
        assert a.checksum == b.checksum
        assert a.input_path.read_text(encoding="utf-8") == b.input_path.read_text(encoding="utf-8")


def test_manifest_contains_cole_cole_metadata(tmp_path: Path) -> None:
    scenario = load_scenario(EXAMPLE)
    plan = render_scenario_inputs(scenario, variant_name="target", run_dir=tmp_path / "run")
    manifest = json.loads((plan.logs_dir / "run_manifest.json").read_text(encoding="utf-8"))
    media = manifest["media"]
    assert media["source_model"] == "cole_cole"
    assert media["approximation_model"] == "multi_pole_debye"
    assert media["materials"][0]["material_id"] == "soil"
    assert media["materials"][0]["eps_s"] == pytest.approx(30.26)
    approx = media["debye_approximations"][0]
    assert approx["material_id"] == "soil"
    assert len(approx["delta_eps"]) == 12
    assert len(approx["tau"]) == 12
    assert approx["max_rel_error"] >= 0.0
    assert approx["rms_rel_error"] >= 0.0
    assert media["fit_frequency_range"] == [5.0e7, 1.5e8]
    assert media["fit_num_frequencies"] == 256
    assert media["fit_error_policy"]["fail"] == pytest.approx(0.15)


def test_legacy_raw_materials_still_work(scenario_yaml: Path, tmp_path: Path) -> None:
    scenario = load_scenario(scenario_yaml)
    plan = render_scenario_inputs(scenario, variant_name="target", run_dir=tmp_path / "run")
    text = plan.inputs[0].input_path.read_text(encoding="utf-8")
    assert "#material: 6 0.01 1 0 soil" in text
    assert "#add_dispersion_debye:" not in text
    assert scenario.media.materials == ()


def test_material_id_collision_rejected(tmp_path: Path) -> None:
    text = EXAMPLE.read_text(encoding="utf-8")
    text = text.replace("  materials: []", "  materials:\n    - \"#material: 6 0.01 1 0 soil\"", 1)
    path = tmp_path / "collision.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValidationError, match="collide"):
        load_scenario(path)
