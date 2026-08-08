from __future__ import annotations

import math

import numpy as np
import pytest

from fda_mimo_gprmax.media import (
    EPSILON_0,
    ColeColeMedium,
    DEFAULT_COLE_COLE_CATALOG,
    cole_cole_complex_permittivity,
    debye_complex_permittivity,
    fit_cole_cole_to_debye,
    material_from_mapping,
    render_debye_material_commands,
)


def _manual(freq: np.ndarray, **params: float) -> np.ndarray:
    omega = 2.0 * np.pi * freq
    return (
        params["eps_inf"]
        + (params["eps_s"] - params["eps_inf"])
        / (1.0 + (1j * omega * params["tau"]) ** (1.0 - params["alpha"]))
        + params["sigma"] / (1j * omega * EPSILON_0)
    )


def test_cole_cole_reference_values_s5() -> None:
    params = dict(eps_s=30.26, eps_inf=10.7, tau=9.55e-12, alpha=0.062, sigma=0.0)
    freq = np.array([50e6, 70e6, 90e6, 110e6, 130e6, 150e6])
    np.testing.assert_allclose(
        cole_cole_complex_permittivity(freq, **params),
        _manual(freq, **params),
        rtol=1e-12,
        atol=1e-12,
    )


def test_cole_cole_reference_values_s1() -> None:
    params = dict(eps_s=3.05, eps_inf=3.00, tau=1.0e-6, alpha=0.30, sigma=1.0e-14)
    freq = np.array([50e6, 70e6, 90e6, 110e6, 130e6, 150e6])
    np.testing.assert_allclose(
        cole_cole_complex_permittivity(freq, **params),
        _manual(freq, **params),
        rtol=1e-12,
        atol=1e-12,
    )


def test_debye_fit_reconstructs_debye_case() -> None:
    medium = ColeColeMedium(
        material_id="ice", eps_s=91.0, eps_inf=3.15, tau=2.5e-5, alpha=0.0, sigma=1.0e-8
    )
    freq = np.logspace(6, 9, 256)
    approx = fit_cole_cole_to_debye(medium, freq, n_poles=12)
    assert approx.max_rel_error < 1e-3
    eps_debye = debye_complex_permittivity(
        freq,
        eps_inf=approx.eps_inf,
        sigma=approx.sigma,
        delta_eps=np.asarray(approx.delta_eps),
        tau=np.asarray(approx.tau),
    )
    eps_cc = cole_cole_complex_permittivity(
        freq,
        eps_s=medium.eps_s,
        eps_inf=medium.eps_inf,
        tau=medium.tau,
        alpha=medium.alpha,
        sigma=medium.sigma,
    )
    np.testing.assert_allclose(eps_debye, eps_cc, rtol=1e-3, atol=1e-6)


def test_debye_fit_cole_cole_reasonable_error() -> None:
    medium = ColeColeMedium(
        material_id="soil",
        eps_s=30.26,
        eps_inf=10.7,
        tau=9.55e-12,
        alpha=0.062,
        sigma=0.0,
    )
    freq = np.logspace(np.log10(50e6), np.log10(150e6), 256)
    approx = fit_cole_cole_to_debye(medium, freq, n_poles=12)
    assert approx.max_rel_error < 0.15
    assert all(x >= -1e-12 for x in approx.delta_eps)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"alpha": 1.0},
        {"alpha": -0.1},
        {"tau": 0.0},
        {"eps_s": 2.0, "eps_inf": 3.0},
        {"eps_inf": 0.0},
        {"eps_s": 0.0},
        {"sigma": -1.0},
        {"tau": math.inf},
    ],
)
def test_invalid_cole_cole_params_rejected(kwargs: dict[str, float]) -> None:
    params = dict(
        material_id="soil",
        eps_s=3.05,
        eps_inf=3.00,
        tau=1.0e-6,
        alpha=0.30,
        sigma=1.0e-14,
    )
    params.update(kwargs)
    with pytest.raises(ValueError):
        ColeColeMedium(**params)


def test_invalid_frequency_rejected() -> None:
    with pytest.raises(ValueError):
        cole_cole_complex_permittivity(
            np.array([0.0]), eps_s=3, eps_inf=2, tau=1e-9, alpha=0.1, sigma=0.0
        )


def test_catalog_resolution_and_render_commands() -> None:
    medium = material_from_mapping(
        "soil", {"from_catalog": "S1"}, use_default_catalog=True
    )
    assert medium.material_id == "soil"
    assert medium.eps_s == DEFAULT_COLE_COLE_CATALOG["S1"]["eps_s"]

    approx = fit_cole_cole_to_debye(
        medium,
        np.logspace(7, 8, 32),
        n_poles=4,
    )

    commands = render_debye_material_commands(approx)
    text = "\n".join(commands)

    assert "#material:" in text
    assert "#add_dispersion_debye:" in text
    assert "soil" in text

    rendered_poles = sum(de > 1e-30 for de in approx.delta_eps)

    assert rendered_poles > 0
    assert rendered_poles <= len(approx.delta_eps)
    assert f"#add_dispersion_debye: {rendered_poles}" in text


def test_unknown_catalog_key_rejected() -> None:
    with pytest.raises(ValueError, match="available keys"):
        material_from_mapping(
            "soil", {"from_catalog": "NOPE"}, use_default_catalog=True
        )


def test_debye_fit_respects_fdtd_tau_floor():
    medium = ColeColeMedium(
        material_id="soil",
        eps_s=30.26,
        eps_inf=10.7,
        tau=9.55e-12,
        alpha=0.062,
        sigma=0.0,
    )

    freq = np.logspace(
        np.log10(50e6),
        np.log10(150e6),
        256,
    )

    dt = 2.0e-11

    tau_min = np.nextafter(
        dt,
        np.inf,
    )

    approx = fit_cole_cole_to_debye(
        medium,
        freq,
        n_poles=12,
        tau_min=tau_min,
    )

    assert min(approx.tau) > dt
