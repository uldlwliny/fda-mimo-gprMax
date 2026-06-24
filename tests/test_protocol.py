from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from fda_mimo_gprmax.cli import main
from fda_mimo_gprmax.config import load_scenario
from fda_mimo_gprmax.protocol import (
    CHECK_BY_ID,
    ProtocolStatus,
    ThresholdPolicy,
    analyze_protocol,
    first_stage_decision,
    load_protocol_results,
    normalize_check_ids,
    plan_protocol,
    protocol_cache_status,
    protocol_paths,
    report_protocol,
    run_v1,
    run_v2,
    run_v3,
    run_v4,
    run_v5,
    run_v6,
    run_v7,
    run_v8,
)


def test_protocol_status_threshold_and_check_ids():
    assert ThresholdPolicy(1.0, 0.5, greater_is_better=True).classify(1.2) == ProtocolStatus.PASS
    assert ThresholdPolicy(1.0, 0.5, greater_is_better=True).classify(0.7) == ProtocolStatus.WARNING
    assert ThresholdPolicy(1.0, 2.0, greater_is_better=False).classify(0.5) == ProtocolStatus.PASS
    assert normalize_check_ids("V1,V3") == ["V1", "V3"]
    with pytest.raises(ValueError, match="unknown protocol"):
        normalize_check_ids("V9")
    assert CHECK_BY_ID["V1"].directory_name == "V1_source_fda_law"


def test_protocol_paths(tmp_path):
    paths = protocol_paths(tmp_path, "V2")
    assert paths.configs.exists()
    assert paths.raw.exists()
    assert paths.processed.exists()
    assert paths.figures.exists()
    assert paths.reports.exists()


def test_protocol_acceptance_gate(scenario_yaml, tmp_path):
    scenario = load_scenario(scenario_yaml)
    results = [run_v1(scenario, tmp_path), run_v2(scenario, tmp_path), run_v3(scenario, tmp_path), run_v4(scenario, tmp_path), run_v5(scenario, tmp_path)]
    decision = first_stage_decision(results)
    assert decision.accepted
    paper_decision = first_stage_decision(results, paper_mode=True)
    assert not paper_decision.accepted
    assert "V6-V8" in paper_decision.blocking_checks


def test_scenario_plan_materialization(scenario_yaml, tmp_path):
    plan = plan_protocol(scenario_yaml, tmp_path / "plan", checks="V1,V4,V6", overwrite=True)
    assert plan["mode"] == "plan"
    assert plan["checks"] == ["V1", "V4", "V6"]
    assert plan["num_items"] > 0
    manifest = tmp_path / "plan" / "protocol_plan_manifest.json"
    assert manifest.exists()
    loaded = json.loads(manifest.read_text())
    assert loaded["checks"] == ["V1", "V4", "V6"]
    config_paths = [Path(item["config_path"]) for item in loaded["items"]]
    assert all(p.exists() for p in config_paths)


def test_v1_to_v8_protocol_checks(scenario_yaml, tmp_path):
    scenario = load_scenario(scenario_yaml)
    runners = [run_v1, run_v2, run_v3, run_v4, run_v5, run_v6, run_v7, run_v8]
    results = [runner(scenario, tmp_path) for runner in runners]
    assert all(result.status == ProtocolStatus.PASS for result in results)
    for result in results:
        result_path = tmp_path / CHECK_BY_ID[result.check_id].directory_name / "check_result.json"
        assert result_path.exists()
        assert json.loads(result_path.read_text())["check_id"] == result.check_id
        assert result.artifacts


def test_analyze_protocol_outputs_report_and_summary(scenario_yaml, tmp_path):
    suite = analyze_protocol(scenario_yaml, tmp_path / "analysis", overwrite=True)
    assert suite.decision.accepted
    assert len(suite.results) == 8
    assert (suite.output_root / "first_stage_summary.json").exists()
    report = suite.output_root / "first_stage_protocol_report.md"
    assert report.exists()
    text = report.read_text()
    assert "model-independent structural checks" in text
    assert "V1 Source FDA law check" in text


def test_report_protocol_from_existing_results(scenario_yaml, tmp_path):
    suite = analyze_protocol(scenario_yaml, tmp_path / "analysis", checks="V1,V2,V3,V4,V5", overwrite=True)
    loaded = load_protocol_results(suite.output_root, "V1,V2")
    assert [r.check_id for r in loaded] == ["V1", "V2"]
    regenerated = report_protocol(suite.output_root, checks="V1,V2,V3,V4,V5")
    assert regenerated.decision.accepted
    assert (suite.output_root / "first_stage_protocol_report.md").exists()


def test_protocol_cache_status(scenario_yaml, tmp_path):
    root = tmp_path / "analysis"
    analyze_protocol(scenario_yaml, root, checks="V1,V2", overwrite=True)
    cache = protocol_cache_status(root, checks="V1,V2,V3")
    status = {row["check_id"]: row["status"] for row in cache["checks"]}
    assert status["V1"] == "pass"
    assert status["V2"] == "pass"
    assert status["V3"] == "missing"


def test_protocol_cli_plan_analyze_report_and_invalid(scenario_yaml, tmp_path, capsys):
    out = tmp_path / "protocol_cli"
    code = main(["protocol", "plan", str(scenario_yaml), "--output-root", str(out), "--checks", "V1,V2", "--overwrite"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "plan"
    assert payload["checks"] == ["V1", "V2"]

    code = main(["protocol", "analyze", str(scenario_yaml), "--output-root", str(out), "--checks", "V1,V2,V3,V4,V5", "--overwrite"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["accepted"] is True

    code = main(["protocol", "report", "--output-root", str(out), "--checks", "V1,V2,V3,V4,V5"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["accepted"] is True

    code = main(["protocol", "plan", str(scenario_yaml), "--output-root", str(tmp_path / "bad"), "--checks", "V9"])
    assert code == 1
    assert "unknown protocol" in capsys.readouterr().err


def test_protocol_cli_run_without_real_execution(scenario_yaml, tmp_path, capsys):
    out = tmp_path / "protocol_run"
    code = main(["protocol", "run", str(scenario_yaml), "--output-root", str(out), "--checks", "V1", "--overwrite"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["execute_real"] is False
    assert "skipped" in payload["message"]


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.skipif(os.environ.get("RUN_GPRMAX_PROTOCOL_INTEGRATION") != "1", reason="real protocol gprMax execution is opt-in")
def test_protocol_real_run_marker_is_opt_in(scenario_yaml, tmp_path):
    # This documents the opt-in path; full real execution is intentionally not part of the default unit-test suite.
    code = main(["protocol", "run", str(scenario_yaml), "--output-root", str(tmp_path / "real"), "--checks", "V1", "--execute-real", "--allow-not-accepted"])
    assert code in {0, 2}
