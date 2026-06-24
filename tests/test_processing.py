from __future__ import annotations

import numpy as np
import pytest

from fda_mimo_gprmax.config import load_scenario
from fda_mimo_gprmax.parsing import parse_tx_outputs
from fda_mimo_gprmax.processing import (
    ProcessingError,
    assemble_time_tensor,
    frequency_transform,
    make_snapshot,
    normalize_by_source,
    subtract_background,
    valid_band_mask,
)


def test_assemble_and_fft_shapes(scenario_yaml, synthetic_out_factory):
    scenario = load_scenario(scenario_yaml)
    paths = [synthetic_out_factory(f"tx_{i:03d}.out", iterations=16) for i in range(scenario.nt)]
    outputs = parse_tx_outputs(paths, "Ez", expected_nrx=scenario.nr)
    yt, time = assemble_time_tensor(outputs, expected_nt=2, expected_nr=2)
    assert yt.shape == (2, 2, 16)
    yf, freqs = frequency_transform(yt, outputs[0].dt, frequency_range=(0, 2e9))
    assert yf.shape[:2] == (2, 2)
    assert yf.shape[-1] == len(freqs)
    assert np.all(freqs <= 2e9)


def test_make_snapshot_and_valid_mask(scenario_yaml, synthetic_out_factory):
    scenario = load_scenario(scenario_yaml)
    paths = [synthetic_out_factory(f"tx_{i:03d}.out", iterations=32) for i in range(scenario.nt)]
    outputs = parse_tx_outputs(paths, "Ez", expected_nrx=scenario.nr)
    snapshot = make_snapshot(outputs, scenario)
    assert snapshot.time_traces.shape == (2, 2, 32)
    assert snapshot.frequency_tensor_raw.shape[:2] == (2, 2)
    assert snapshot.source_spectra.shape == snapshot.valid_band_mask.shape
    assert snapshot.frequency_tensor_cal is not None


def test_valid_band_and_normalization_guard():
    yf = np.ones((1, 2, 3), dtype=np.complex64)
    src = np.asarray([[1, 1e-9, 0]], dtype=np.complex64)
    mask = valid_band_mask(src, 1e-3)
    out = normalize_by_source(yf, src, mask, eta=1e-12)
    assert mask.tolist() == [[True, False, False]]
    assert np.isfinite(out[0, 0, 0])
    assert np.isnan(out[0, 0, 1].real)


def test_background_subtraction_accepts_compatible(scenario_yaml, synthetic_out_factory):
    scenario = load_scenario(scenario_yaml)
    outputs = parse_tx_outputs([synthetic_out_factory(f"a_{i}.out", iterations=16) for i in range(2)], "Ez", expected_nrx=2)
    target = make_snapshot(outputs, scenario)
    background = make_snapshot(outputs, scenario)
    scat = subtract_background(target, background)
    assert scat.shape == target.frequency_tensor_raw.shape
    assert np.allclose(scat, 0)


def test_background_subtraction_rejects_incompatible(scenario_yaml, synthetic_out_factory):
    scenario = load_scenario(scenario_yaml)
    outputs = parse_tx_outputs([synthetic_out_factory(f"a_{i}.out", iterations=16) for i in range(2)], "Ez", expected_nrx=2)
    target = make_snapshot(outputs, scenario)
    other = make_snapshot(outputs, scenario)
    object.__setattr__(other, "frequencies", other.frequencies + 1.0)
    with pytest.raises(ProcessingError, match="incompatible"):
        subtract_background(target, other)
