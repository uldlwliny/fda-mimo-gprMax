from __future__ import annotations

import json

from fda_mimo_gprmax.cli import main
from fda_mimo_gprmax.config import load_scenario
from fda_mimo_gprmax.parsing import parse_tx_outputs
from fda_mimo_gprmax.processing import make_snapshot
from fda_mimo_gprmax.serialization import write_snapshot_h5


def test_cli_workflow_dry_run_uses_variant_subdir(scenario_yaml, tmp_path, capsys):
    code = main(["workflow", str(scenario_yaml), "--variant", "target", "--run-dir", str(tmp_path / "scene"), "--dry-run"])
    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["render_plan"]["run_dir"].endswith("target")


def _mock_real_scene(scenario_yaml, synthetic_out_factory, tmp_path):
    scenario = load_scenario(scenario_yaml)
    scene = tmp_path / "scene"
    raw = scene / "target" / "raw"
    raw.mkdir(parents=True)
    paths = []
    for i in range(scenario.nt):
        src = synthetic_out_factory(f"cli_tx_{i:03d}.out", iterations=16)
        dst = raw / f"tx_{i:03d}.out"
        dst.write_bytes(src.read_bytes())
        paths.append(dst)
    snapshot = make_snapshot(parse_tx_outputs(paths, "Ez", expected_nrx=scenario.nr), scenario)
    write_snapshot_h5(snapshot, scene / "target" / "processed" / "snapshot.h5")
    return scene


def test_cli_inspect_run(scenario_yaml, synthetic_out_factory, tmp_path, capsys):
    scene = _mock_real_scene(scenario_yaml, synthetic_out_factory, tmp_path)
    code = main(["inspect-run", str(scene)])
    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out)
    assert payload["decision"] == "ACCEPTED_FOR_REAL_FULLWAVE_TARGET_SNAPSHOT"
    assert (scene / "diagnostics" / "run_analysis_report.md").exists()


def test_cli_protocol_real_labels_real_run_and_limits_v5_v8(scenario_yaml, synthetic_out_factory, tmp_path, capsys):
    scene = _mock_real_scene(scenario_yaml, synthetic_out_factory, tmp_path)
    code = main(["protocol-real", str(scene), "--allow-not-accepted"])
    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out)
    assert payload["type"] == "real-run"
    assert payload["checks"]["V5"].startswith("NOT_EVALUATED")
