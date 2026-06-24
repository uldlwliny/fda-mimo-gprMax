from __future__ import annotations

import h5py
import numpy as np

from fda_mimo_gprmax.config import load_scenario
from fda_mimo_gprmax.diagnostics import write_diagnostics
from fda_mimo_gprmax.parsing import parse_tx_outputs
from fda_mimo_gprmax.processing import make_snapshot
from fda_mimo_gprmax.serialization import write_processed_snapshot, write_snapshot_h5, write_snapshot_npz


def _snapshot(scenario_yaml, synthetic_out_factory):
    scenario = load_scenario(scenario_yaml)
    outputs = parse_tx_outputs([synthetic_out_factory(f"tx_{i:03d}.out", iterations=16) for i in range(scenario.nt)], "Ez", expected_nrx=scenario.nr)
    return make_snapshot(outputs, scenario), scenario


def test_h5_snapshot_schema(scenario_yaml, synthetic_out_factory, tmp_path):
    snapshot, _ = _snapshot(scenario_yaml, synthetic_out_factory)
    path = write_snapshot_h5(snapshot, tmp_path / "snapshot.h5")
    with h5py.File(path, "r") as h5:
        assert "/snapshot/time_traces" in h5
        assert "/snapshot/frequency_tensor_raw" in h5
        assert "/snapshot/source_spectra" in h5
        assert "/snapshot/valid_band_mask" in h5
        assert "/axis/tx_positions" in h5
        assert "/axis/tx_positions_requested" in h5
        assert "/axis/tx_positions_actual" in h5
        assert "/axis/rx_positions_requested" in h5
        assert "/axis/rx_positions_actual" in h5
        assert "/axis/position_quantization_error_rx" in h5
        assert "/axis/frequencies" in h5
        assert "/metadata/config" in h5
        assert "/metadata/run_evidence" in h5
        assert "/metadata/processing_metrics" in h5
        assert "/metadata/axis_convention" in h5
        assert h5["/snapshot/time_traces"].shape == snapshot.time_traces.shape
        assert h5["/snapshot/time_traces"].dtype == np.float32
        assert h5["/axis/rx_positions_actual"].shape == (snapshot.time_traces.shape[0], snapshot.time_traces.shape[1], 3)


def test_npz_snapshot_roundtrip(scenario_yaml, synthetic_out_factory, tmp_path):
    snapshot, _ = _snapshot(scenario_yaml, synthetic_out_factory)
    path = write_snapshot_npz(snapshot, tmp_path / "snapshot.npz")
    data = np.load(path)
    assert data["time_traces"].shape == snapshot.time_traces.shape
    assert data["fda_center_frequencies"].shape == (2,)
    assert "metadata" in data


def test_write_processed_snapshot_and_diagnostics(scenario_yaml, synthetic_out_factory, tmp_path):
    snapshot, scenario = _snapshot(scenario_yaml, synthetic_out_factory)
    paths = write_processed_snapshot(snapshot, tmp_path / "processed", export_npz=scenario.processing.export_npz)
    assert paths["h5"].exists()
    assert paths["npz"].exists()
    diag = write_diagnostics(snapshot, tmp_path / "figures")
    assert diag["summary"].exists()
    assert diag["trace_preview"].exists()
