from __future__ import annotations

import json
from pathlib import Path
import os

import pytest

from fda_mimo_gprmax.config import load_scenario
from fda_mimo_gprmax.validation import (
    ValidationResult,
    ValidationSuiteResult,
    background_subtraction_case,
    fft_sanity_case,
    gprmax_smoke_validation_case,
    normalization_sanity_case,
    parser_roundtrip_case,
    render_contract_case,
    run_synthetic_validation_suite,
    write_report,
    write_summary,
)


def test_validation_result_serialization(tmp_path):
    result = ValidationResult(
        case_name="case",
        claim="claim",
        passed=True,
        inputs={"path": tmp_path, "values": [1]},
        metrics={"value": 1.0},
        artifacts={"a": "a.txt"},
    )
    data = result.to_dict()
    assert data["case_name"] == "case"
    assert data["passed"] is True
    assert isinstance(data["inputs"]["path"], str)
    suite = ValidationSuiteResult("suite", tmp_path, (result,))
    assert suite.passed is True
    summary = write_summary(suite)
    assert json.loads(summary.read_text())["passed"] is True


def test_validation_suite_failure_aggregate(tmp_path):
    ok = ValidationResult("ok", "ok", True)
    bad = ValidationResult("bad", "bad", False, errors=["controlled failure"])
    suite = ValidationSuiteResult("suite", tmp_path, (ok, bad))
    assert suite.passed is False
    report = write_report(suite)
    text = report.read_text()
    assert "controlled failure" in text
    assert "hardware-realistic" in text


def test_render_contract_case_artifacts(scenario_yaml, tmp_path):
    scenario = load_scenario(scenario_yaml)
    result = render_contract_case(scenario, tmp_path)
    assert result.passed
    assert (tmp_path / result.artifacts["csv"]).exists()
    assert (tmp_path / result.artifacts["figure"]).exists()
    assert result.metrics["num_inputs"] == scenario.nt


def test_parser_roundtrip_case(scenario_yaml, tmp_path):
    scenario = load_scenario(scenario_yaml)
    result = parser_roundtrip_case(scenario, tmp_path)
    assert result.passed
    assert result.metrics["max_abs_error"] == 0.0
    assert (tmp_path / result.artifacts["figure"]).exists()


def test_fft_sanity_case_success_and_failure(scenario_yaml, tmp_path):
    scenario = load_scenario(scenario_yaml)
    ok = fft_sanity_case(scenario, tmp_path / "ok")
    assert ok.passed
    bad = fft_sanity_case(scenario, tmp_path / "bad", tolerance=-1.0)
    assert not bad.passed
    assert bad.errors


def test_normalization_sanity_case(scenario_yaml, tmp_path):
    scenario = load_scenario(scenario_yaml)
    result = normalization_sanity_case(scenario, tmp_path)
    assert result.passed
    assert result.metrics["invalid_has_nan"] is True
    assert (tmp_path / result.artifacts["csv"]).exists()


def test_background_subtraction_case(scenario_yaml, tmp_path):
    scenario = load_scenario(scenario_yaml)
    result = background_subtraction_case(scenario, tmp_path)
    assert result.passed
    assert result.metrics["incompatible_rejected"] is True


def test_synthetic_suite_report_and_summary(scenario_yaml, tmp_path):
    suite = run_synthetic_validation_suite(scenario_yaml, tmp_path / "validation", write_report_file=True)
    assert suite.passed
    summary = json.loads((suite.output_dir / "summary.json").read_text())
    assert summary["num_cases"] == 5
    assert summary["passed"] is True
    assert (suite.output_dir / "validation_report.md").exists()
    assert "compatibility-layer semantics" in (suite.output_dir / "validation_report.md").read_text()


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.skipif(os.environ.get("RUN_GPRMAX_INTEGRATION") != "1", reason="gprMax smoke validation is opt-in")
def test_gprmax_smoke_validation_path_is_opt_in(scenario_yaml, tmp_path):
    scenario = load_scenario(scenario_yaml)
    result = gprmax_smoke_validation_case(scenario, tmp_path, timeout=1.0)
    assert result.case_name == "06_gprmax_smoke"
    assert "failure_category" in result.metrics or result.passed
