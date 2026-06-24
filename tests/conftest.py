from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pytest


@pytest.fixture
def scenario_yaml(tmp_path: Path) -> Path:
    path = tmp_path / "scenario.yaml"
    path.write_text(
        """
name: unit_scene
random_seed: 123
output:
  root: runs
  export_npz: true
  diagnostics: false
  valid_band_threshold: 0.001
  eta: 1.0e-12
domain:
  size: [0.40, 0.30, 0.25]
grid:
  spacing: [0.01, 0.01, 0.01]
time:
  window: 4.0e-9
scene:
  title: Unit FDA-MIMO-GPR scene
  materials:
    - "#material: 6 0.01 1 0 soil"
  geometry:
    - "#box: 0 0 0 0.40 0.30 0.12 soil"
array:
  mode: strict
  polarization: z
  tx_positions:
    - [0.10, 0.10, 0.13]
    - [0.20, 0.10, 0.13]
fda:
  type: linear
  f0: 1.0e9
  df: 5.0e7
waveform:
  mode: builtin
  shape: ricker
  amplitude: 1.0
receiver:
  component: Ez
variants:
  target:
    geometry:
      - "#sphere: 0.20 0.15 0.08 0.03 pec"
  background:
    geometry: []
execution:
  executable: ["python", "-m", "gprMax"]
  failure_policy: stop
""".strip(),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def synthetic_out_factory(tmp_path: Path):
    def make(name: str, nrx: int = 2, iterations: int = 16, dt: float = 1e-11, component: str = "Ez") -> Path:
        path = tmp_path / name
        with h5py.File(path, "w") as h5:
            h5.attrs["Iterations"] = iterations
            h5.attrs["dt"] = dt
            h5.attrs["nrx"] = nrx
            h5.attrs["gprMax"] = "test"
            for rx in range(1, nrx + 1):
                g = h5.create_group(f"/rxs/rx{rx}")
                g.attrs["Position"] = (0.1 * rx, 0.0, 0.0)
                t = np.arange(iterations, dtype=np.float64)
                g.create_dataset(component, data=np.sin(0.1 * t + rx))
        return path

    return make
