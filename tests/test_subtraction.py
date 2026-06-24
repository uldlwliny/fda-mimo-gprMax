from __future__ import annotations

import h5py
import numpy as np
import pytest

from fda_mimo_gprmax.config import load_scenario
from fda_mimo_gprmax.parsing import parse_tx_outputs
from fda_mimo_gprmax.processing import make_snapshot
from fda_mimo_gprmax.serialization import write_snapshot_h5
from fda_mimo_gprmax.subtraction import SubtractionError, subtract_scene_run, subtract_snapshots


def _write_pair(tmp_path, scenario_yaml, synthetic_out_factory):
    scenario = load_scenario(scenario_yaml)
    target_outputs = parse_tx_outputs([synthetic_out_factory(f"target_tx_{i:03d}.out", iterations=16) for i in range(scenario.nt)], "Ez", expected_nrx=scenario.nr)
    background_outputs = parse_tx_outputs([synthetic_out_factory(f"background_tx_{i:03d}.out", iterations=16) for i in range(scenario.nt)], "Ez", expected_nrx=scenario.nr)
    target = make_snapshot(target_outputs, scenario)
    background = make_snapshot(background_outputs, scenario)
    target_path = tmp_path / "scene" / "target" / "processed" / "snapshot.h5"
    background_path = tmp_path / "scene" / "background" / "processed" / "snapshot.h5"
    write_snapshot_h5(target, target_path)
    write_snapshot_h5(background, background_path)
    return target_path, background_path


def test_subtract_snapshots_success(tmp_path, scenario_yaml, synthetic_out_factory):
    target, background = _write_pair(tmp_path, scenario_yaml, synthetic_out_factory)
    result = subtract_snapshots(target, background, tmp_path / "scene" / "scatter" / "processed" / "scatter_snapshot.h5")
    assert result.output_path.exists()
    assert result.summary["time_traces_shape"] == [2, 2, 16]
    with h5py.File(result.output_path, "r") as h5:
        assert "/scatter/time_traces" in h5
        assert "/scatter/frequency_tensor_raw" in h5
        assert "/scatter/frequency_tensor_cal" in h5
        assert "/scatter/valid_band_mask_pair" in h5
        assert "/metadata/subtraction_summary" in h5


def test_subtract_scene_run_success(tmp_path, scenario_yaml, synthetic_out_factory):
    _write_pair(tmp_path, scenario_yaml, synthetic_out_factory)
    result = subtract_scene_run(tmp_path / "scene")
    assert result.output_path.name == "scatter_snapshot.h5"
    assert result.output_path.exists()


def test_axis_mismatch_fails(tmp_path, scenario_yaml, synthetic_out_factory):
    target, background = _write_pair(tmp_path, scenario_yaml, synthetic_out_factory)
    with h5py.File(background, "a") as h5:
        h5["/axis/time"][1] = h5["/axis/time"][1] + 1e-12
    with pytest.raises(SubtractionError, match="time axis"):
        subtract_snapshots(target, background, tmp_path / "bad.h5")


def test_pair_mask_and_nan_preservation(tmp_path, scenario_yaml, synthetic_out_factory):
    target, background = _write_pair(tmp_path, scenario_yaml, synthetic_out_factory)
    with h5py.File(target, "a") as h5:
        h5["/snapshot/valid_band_mask"][0, 0] = False
        h5["/snapshot/frequency_tensor_cal"][0, 0, 0] = np.nan + 1j * np.nan
    result = subtract_snapshots(target, background, tmp_path / "scatter.h5")
    with h5py.File(result.output_path, "r") as h5:
        assert not bool(h5["/scatter/valid_band_mask_pair"][0, 0])
        assert np.isnan(h5["/scatter/frequency_tensor_cal"][0, 0, 0].real)
