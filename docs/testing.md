# Testing Notes

Unit tests are designed to run without executing gprMax. Synthetic HDF5 fixtures mimic the relevant gprMax receiver-output structure under `/rxs/rxN/<component>`.

Validated command:

```bash
conda activate gprMax
uv pip install -e '.[test]'
pytest -q
```

Current result after protocol validation implementation: `47 passed, 2 skipped` (skipped tests are opt-in gprMax smoke/protocol integration paths).

Integration tests that execute full FDTD simulations are not enabled by default. They require:

- an installed and importable `gprMax` runtime in the `gprMax` conda environment;
- enough CPU/GPU resources for the selected scenario;
- explicit user opt-in, e.g. future tests marked `@pytest.mark.integration` or `@pytest.mark.slow`.

## Full real-run test matrix

```bash
PYTHONPATH=src pytest -q
fda-mimo-gprmax validate examples/minimal_fda_mimo_scene.yaml
fda-mimo-gprmax render examples/minimal_fda_mimo_scene.yaml --variant target --run-dir runs/smoke_scene
fda-mimo-gprmax run examples/minimal_fda_mimo_scene.yaml --variant target --run-dir runs/smoke_scene --dry-run
fda-mimo-gprmax evidence examples/minimal_fda_mimo_scene.yaml --output-dir output/evidence/latest --overwrite

fda-mimo-gprmax workflow examples/minimal_fda_mimo_scene.yaml --variant target --run-dir runs/pair_smoke --timeout 120
fda-mimo-gprmax workflow examples/minimal_fda_mimo_scene.yaml --variant background --run-dir runs/pair_smoke --timeout 120
fda-mimo-gprmax subtract examples/minimal_fda_mimo_scene.yaml --run-dir runs/pair_smoke
fda-mimo-gprmax inspect-run runs/pair_smoke --with-scatter
```

Optional stricter physical validation:

```bash
fda-mimo-gprmax workflow examples/minimal_fda_mimo_scene_long_window.yaml --variant target --run-dir runs/long_window_target --timeout 600
fda-mimo-gprmax inspect-run runs/long_window_target --paper-mode
```
