from __future__ import annotations

import json

from fda_mimo_gprmax.config import load_scenario
from fda_mimo_gprmax.inspection import inspect_run
from fda_mimo_gprmax.parsing import parse_tx_outputs
from fda_mimo_gprmax.processing import make_snapshot
from fda_mimo_gprmax.serialization import write_snapshot_h5


def _write_target_scene(tmp_path, scenario_yaml, synthetic_out_factory, with_log: bool = False):
    scenario = load_scenario(scenario_yaml)
    scene = tmp_path / "scene"
    raw = scene / "target" / "raw"
    raw.mkdir(parents=True)
    paths = []
    for i in range(scenario.nt):
        src = synthetic_out_factory(f"inspect_tx_{i:03d}.out", iterations=16)
        dst = raw / f"tx_{i:03d}.out"
        dst.write_bytes(src.read_bytes())
        paths.append(dst)
    outputs = parse_tx_outputs(paths, "Ez", expected_nrx=scenario.nr)
    snapshot = make_snapshot(outputs, scenario)
    write_snapshot_h5(snapshot, scene / "target" / "processed" / "snapshot.h5")
    (scene / "background" / "config").mkdir(parents=True)
    (scene / "background" / "config" / "generated_tx_000.in").write_text("#title: dry-run", encoding="utf-8")
    if with_log:
        logs = scene / "target" / "logs"
        logs.mkdir(parents=True)
        (logs / "gprmax_stdout_tx_000.txt").write_text(
            """
                     v3.1.7 (Big Smoke)
Waveform fda_ricker_000 of type ricker with maximum amplitude scaling 1, frequency 1e+09Hz created.
WARNING: Potentially significant numerical dispersion. Estimated largest physical phase-velocity error is -7.15% in material 'soil'.
""".strip(),
            encoding="utf-8",
        )
    return scene


def test_inspect_target_complete_background_dry_run(tmp_path, scenario_yaml, synthetic_out_factory):
    scene = _write_target_scene(tmp_path, scenario_yaml, synthetic_out_factory)
    result = inspect_run(scene)
    assert result.summary_path.exists()
    assert result.report_path.exists()
    assert result.summary["decision"] == "ACCEPTED_FOR_REAL_FULLWAVE_TARGET_SNAPSHOT"
    assert result.summary["variants"]["target"]["run_stage"] == "real"
    assert result.summary["variants"]["background"]["run_stage"] == "dry-run"
    assert (scene / "diagnostics" / "tables" / "channel_energy_matrix.csv").exists()
    assert (scene / "diagnostics" / "figures" / "channel_energy_matrix.png").exists()


def test_inspect_missing_processed_does_not_crash(tmp_path):
    scene = tmp_path / "scene"
    (scene / "target" / "config").mkdir(parents=True)
    (scene / "target" / "config" / "generated_tx_000.in").write_text("#title: dry-run", encoding="utf-8")
    result = inspect_run(scene, variants=["target"], output=scene / "diag")
    assert result.summary["decision"] == "ACCEPTED_FOR_ENGINEERING_SMOKE"
    assert result.summary["variants"]["target"]["has_processed"] is False


def test_coordinate_warning_enters_json(tmp_path, scenario_yaml, synthetic_out_factory):
    scene = _write_target_scene(tmp_path, scenario_yaml, synthetic_out_factory)
    result = inspect_run(scene)
    coords = result.summary["coordinates"]
    assert coords["max_requested_actual_rx_error_m"] is not None


def test_paper_mode_is_stricter(tmp_path, scenario_yaml, synthetic_out_factory):
    scene = _write_target_scene(tmp_path, scenario_yaml, synthetic_out_factory)
    result = inspect_run(scene, paper_mode=True)
    assert result.summary["decision"] in {"ACCEPTED_FOR_ENGINEERING_SMOKE", "ACCEPTED_FOR_REAL_FULLWAVE_TARGET_SNAPSHOT"}
    data = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert "V5" in data["real_run_checks"]
