from __future__ import annotations

from fda_mimo_gprmax.log_analysis import collect_run_log_summaries, dispersion_risk, parse_gprmax_stdout, summarize_numerical_dispersion


STDOUT = """
=== Electromagnetic modelling software based on the Finite-Difference Time-Domain (FDTD) method
                     v3.1.7 (Big Smoke)
Spatial discretisation: 0.01 x 0.01 x 0.01m
Domain size: 0.6 x 0.4 x 0.3m (60 x 40 x 30 = 72000 cells)
Time window: 6e-09 secs (313 iterations)
Waveform fda_ricker_003 of type ricker with maximum amplitude scaling 1, frequency 1.075e+09Hz created.
WARNING: Potentially significant numerical dispersion. Estimated largest physical phase-velocity error is -7.15% in material 'soil' whose wavelength sampled by 4 cells.
""".strip()


def test_parse_gprmax_stdout_current_style(tmp_path):
    path = tmp_path / "gprmax_stdout_tx_003.txt"
    path.write_text(STDOUT, encoding="utf-8")
    summary = parse_gprmax_stdout(path)
    assert summary.tx_index == 3
    assert summary.gprmax_version.startswith("3.1.7")
    assert summary.spatial_step == (0.01, 0.01, 0.01)
    assert summary.domain_size == (0.6, 0.4, 0.3)
    assert summary.grid_cells == (60, 40, 30)
    assert summary.time_window_s == 6e-9
    assert summary.iterations == 313
    assert summary.waveform_frequency_hz == 1.075e9
    assert summary.numerical_dispersion_warning is True
    assert summary.max_phase_velocity_error_percent == -7.15
    assert summary.dispersion_risk == "HIGH"


def test_empty_log_returns_warning(tmp_path):
    path = tmp_path / "gprmax_stdout_tx_000.txt"
    path.write_text("", encoding="utf-8")
    summary = parse_gprmax_stdout(path)
    assert summary.tx_index == 0
    assert summary.dispersion_risk == "UNKNOWN"
    assert summary.warnings


def test_dispersion_risk_thresholds():
    assert dispersion_risk(1.9) == "LOW"
    assert dispersion_risk(2.0) == "MODERATE"
    assert dispersion_risk(5.0) == "HIGH"
    assert dispersion_risk(10.0) == "SEVERE"
    assert dispersion_risk(None) == "UNKNOWN"


def test_collect_and_summarize_logs(tmp_path):
    for i, freq in enumerate([1.0e9, 1.025e9]):
        (tmp_path / f"gprmax_stdout_tx_{i:03d}.txt").write_text(STDOUT.replace("1.075e+09", f"{freq:.3e}"), encoding="utf-8")
    summaries = collect_run_log_summaries(tmp_path)
    assert [s.tx_index for s in summaries] == [0, 1]
    dispersion = summarize_numerical_dispersion(summaries)
    assert dispersion.warning is True
    assert dispersion.risk == "HIGH"
    assert dispersion.max_abs_phase_velocity_error_percent == 7.15
