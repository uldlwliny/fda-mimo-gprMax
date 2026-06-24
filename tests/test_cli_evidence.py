from __future__ import annotations

import json

from fda_mimo_gprmax.cli import main


def test_cli_evidence_success(scenario_yaml, tmp_path, capsys):
    code = main(["evidence", str(scenario_yaml), "--output-dir", str(tmp_path / "evidence"), "--overwrite"])
    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out)
    assert payload["passed"] is True
    assert payload["num_cases"] == 5
    assert (tmp_path / "evidence" / "summary.json").exists()
    assert (tmp_path / "evidence" / "validation_report.md").exists()


def test_cli_evidence_controlled_failure(scenario_yaml, tmp_path, capsys):
    code = main(["evidence", str(scenario_yaml), "--output-dir", str(tmp_path / "evidence_fail"), "--tolerance", "-1", "--overwrite"])
    captured = capsys.readouterr()
    assert code == 2
    payload = json.loads(captured.out)
    assert payload["passed"] is False
    assert payload["num_failed"] >= 1
    assert (tmp_path / "evidence_fail" / "summary.json").exists()
    assert (tmp_path / "evidence_fail" / "validation_report.md").exists()
