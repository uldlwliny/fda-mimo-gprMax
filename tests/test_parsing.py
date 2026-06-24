from __future__ import annotations

import h5py
import pytest

from fda_mimo_gprmax.parsing import OutputParseError, extract_component, inspect_output, parse_tx_outputs


def test_inspect_output(synthetic_out_factory):
    path = synthetic_out_factory("tx_000.out")
    info = inspect_output(path)
    assert info.iterations == 16
    assert info.dt == 1e-11
    assert info.nrx == 2
    assert info.gprmax_version == "test"
    assert info.available_components[0] == ["Ez"]


def test_extract_component(synthetic_out_factory):
    path = synthetic_out_factory("tx_000.out", iterations=8)
    trace = extract_component(path, "Ez", expected_nrx=2, tx_index=3)
    assert trace.tx_index == 3
    assert trace.traces.shape == (2, 8)
    assert trace.time[-1] == pytest.approx(7e-11)
    assert trace.receiver_positions_actual.shape == (2, 3)


def test_extract_actual_source_and_receiver_positions(tmp_path):
    path = tmp_path / "tx_000.out"
    with h5py.File(path, "w") as h5:
        h5.attrs["Iterations"] = 4
        h5.attrs["dt"] = 1e-11
        h5.attrs["nrx"] = 2
        h5.attrs["gprMax"] = "test"
        src = h5.create_group("/srcs/src1")
        src.attrs["Position"] = (0.22, 0.16, 0.15)
        for rx in range(1, 3):
            g = h5.create_group(f"/rxs/rx{rx}")
            g.attrs["Position"] = (0.2 + 0.04 * rx, 0.16, 0.15)
            g.create_dataset("Ez", data=[0.0, 1.0, 0.0, -1.0])
    trace = extract_component(path, "Ez", expected_nrx=2, tx_index=0)
    assert trace.source_position_actual.tolist() == [0.22, 0.16, 0.15]
    assert trace.receiver_positions_actual.shape == (2, 3)
    assert trace.warnings == []


def test_missing_actual_source_warns(synthetic_out_factory):
    path = synthetic_out_factory("tx_000.out")
    trace = extract_component(path, "Ez", expected_nrx=2)
    assert trace.source_position_actual is None
    assert any("source position" in warning for warning in trace.warnings)


def test_missing_component_error(synthetic_out_factory):
    path = synthetic_out_factory("tx_000.out")
    with pytest.raises(OutputParseError, match="missing dataset"):
        extract_component(path, "Ex")


def test_inconsistent_time_axis_error(synthetic_out_factory):
    a = synthetic_out_factory("tx_000.out", iterations=8)
    b = synthetic_out_factory("tx_001.out", iterations=9)
    with pytest.raises(OutputParseError, match="incompatible sample count"):
        parse_tx_outputs([a, b], "Ez", expected_nrx=2)


def test_missing_receiver_group_error(tmp_path):
    path = tmp_path / "bad.out"
    with h5py.File(path, "w") as h5:
        h5.attrs["Iterations"] = 4
        h5.attrs["dt"] = 1e-11
        h5.attrs["nrx"] = 1
    with pytest.raises(OutputParseError, match="missing receiver group"):
        inspect_output(path)
