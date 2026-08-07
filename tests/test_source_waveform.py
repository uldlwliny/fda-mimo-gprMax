from __future__ import annotations

import numpy as np
import pytest

from fda_mimo_gprmax.source_waveform import (
    sample_gprmax_builtin_waveform,
)

pytestmark = pytest.mark.integration


def test_ricker_wrapper_matches_gprmax_runtime():
    gprmax_waveforms = pytest.importorskip("gprMax.waveforms")

    GprMaxWaveform = gprmax_waveforms.Waveform

    f = 1.0e9
    dt = 1.0e-11

    time = np.arange(512) * dt

    actual = sample_gprmax_builtin_waveform(
        "ricker",
        1.7,
        f,
        time,
        dt,
    )

    waveform = GprMaxWaveform()
    waveform.type = "ricker"
    waveform.amp = 1.7
    waveform.freq = f

    expected = np.asarray(
        [
            waveform.calculate_value(
                float(t),
                dt,
            )
            for t in time
        ]
    )

    np.testing.assert_allclose(
        actual,
        expected,
        rtol=0,
        atol=0,
    )


def test_sine_wrapper_obeys_gprmax_one_cycle_definition():
    pytest.importorskip("gprMax.waveforms")

    f = 1.0e9
    dt = 1.0e-11

    time = np.arange(300) * dt

    actual = sample_gprmax_builtin_waveform(
        "sine",
        1.0,
        f,
        time,
        dt,
    )

    assert np.all(actual[time * f > 1.0] == 0)
