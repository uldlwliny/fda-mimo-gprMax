from __future__ import annotations

import numpy as np

from fda_mimo_gprmax.config import estimate_gprmax_dt, load_scenario
from fda_mimo_gprmax.exact_frequency import (
    frequency_transform_at,
    source_spectra_at,
)


def test_exact_frequency_matches_rfft_at_fft_bins():
    rng = np.random.default_rng(1234)
    dt = 2.0e-11
    nt = 256
    time = np.arange(nt, dtype=np.float64) * dt
    traces = rng.normal(size=(2, 3, nt))
    full_freqs = np.fft.rfftfreq(nt, d=dt)
    indices = np.array([3, 17, 61, 97])
    freqs = full_freqs[indices]

    direct = frequency_transform_at(traces, time, freqs)
    expected = np.fft.rfft(traces, axis=-1)[..., indices] * dt

    np.testing.assert_allclose(direct, expected, rtol=2e-6, atol=2e-7)


def test_exact_frequency_off_bin_impulse_has_analytic_phase():
    dt = 1.0e-10
    nt = 64
    time = np.arange(nt, dtype=np.float64) * dt
    impulse_index = 13
    traces = np.zeros((1, 1, nt), dtype=np.float64)
    traces[0, 0, impulse_index] = 2.5
    freqs = np.array([0.73e9, 1.13e9], dtype=np.float64)

    direct = frequency_transform_at(traces, time, freqs)
    expected = (
        2.5
        * dt
        * np.exp(-2j * np.pi * freqs * time[impulse_index])
    )

    np.testing.assert_allclose(direct[0, 0], expected, rtol=2e-6, atol=1e-12)


def test_source_spectra_at_requested_frequencies(scenario_yaml):
    scenario = load_scenario(scenario_yaml)
    dt = estimate_gprmax_dt(scenario.domain, scenario.grid)
    time = np.arange(int(np.floor(scenario.time.window / dt)) + 1) * dt
    freqs = np.array([0.9e9, 1.0e9, 1.1e9], dtype=np.float64)

    spectra = source_spectra_at(scenario, time, freqs)

    assert spectra.shape == (scenario.nt, len(freqs))
    assert np.all(np.isfinite(spectra))
    assert np.all(np.abs(spectra) > 0)
