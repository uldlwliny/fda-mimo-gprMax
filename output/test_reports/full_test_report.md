# Full Test Report: Real-run diagnostics and scatter

Date: 2026-06-06

## Pytest

Command:

```bash
source ~/miniconda3/etc/profile.d/conda.sh && conda activate gprMax && PYTHONPATH=src pytest -q
```

Result:

```text
64 passed, 2 skipped in 14.44s
```

## CLI smoke tests

Commands:

```bash
fda-mimo-gprmax validate examples/minimal_fda_mimo_scene.yaml
fda-mimo-gprmax render examples/minimal_fda_mimo_scene.yaml --variant target --run-dir runs/smoke_scene
fda-mimo-gprmax run examples/minimal_fda_mimo_scene.yaml --variant target --run-dir runs/smoke_scene --dry-run
fda-mimo-gprmax evidence examples/minimal_fda_mimo_scene.yaml --output-dir output/evidence/latest --overwrite
```

Result: all commands returned success; validation/render/dry-run JSON had `ok=true`, evidence suite had `passed=true`.

## Real gprMax target/background/scatter test

Commands:

```bash
fda-mimo-gprmax workflow examples/minimal_fda_mimo_scene.yaml --variant target --run-dir runs/scene_001_minimal_fixed --timeout 120
fda-mimo-gprmax workflow examples/minimal_fda_mimo_scene.yaml --variant background --run-dir runs/scene_001_minimal_fixed --timeout 120
fda-mimo-gprmax subtract examples/minimal_fda_mimo_scene.yaml --run-dir runs/scene_001_minimal_fixed
fda-mimo-gprmax inspect-run runs/scene_001_minimal_fixed --with-scatter
fda-mimo-gprmax protocol-real runs/scene_001_minimal_fixed --with-scatter --allow-not-accepted
```

Result:

- target workflow: success; `target/processed/snapshot.h5` and `.npz` exist.
- background workflow: success; `background/processed/snapshot.h5` and `.npz` exist.
- scatter subtraction: success; `scatter/processed/scatter_snapshot.h5` exists.
- raw count: target 4, background 4.
- inspect-run decision: `ACCEPTED_FOR_TARGET_BACKGROUND_SCATTER`.
- scatter/target energy ratio: `4.5009916640207943e-04`.
- FDA status: `PASS-CONFIG` with `WARNING-SPECTRAL-UNRESOLVED` for quick minimal scene.
- coordinate warning: requested/actual Rx max error is `0.005 m`, caused by grid quantization of the quick scene's 5 mm offset on a 10 mm grid.
- numerical dispersion: warning present, risk `HIGH`, max absolute phase velocity error `8.27%`.

## Long-window/grid-aligned physical check

Commands:

```bash
fda-mimo-gprmax validate examples/minimal_fda_mimo_scene_long_window.yaml
fda-mimo-gprmax workflow examples/minimal_fda_mimo_scene_long_window.yaml --variant target --run-dir runs/long_window_target --timeout 600
fda-mimo-gprmax inspect-run runs/long_window_target --paper-mode --allow-not-accepted
```

Result:

- workflow success.
- inspect decision: `ACCEPTED_FOR_REAL_FULLWAVE_TARGET_SNAPSHOT`.
- FDA status: `PASS-CONFIG` and `PASS-SPECTRAL`.
- FFT bin spacing: `8.330751949 MHz`.
- FDA step: `25 MHz`.
- FFT resolution ratio: `0.3332`.
- numerical-dispersion risk: `LOW`, max absolute phase velocity error `0.81%`.
- requested/actual Tx/Rx coordinate error: `0.0 m`.

## Deliverable paths

```text
runs/scene_001_minimal_fixed/
  target/
  background/
  scatter/
  diagnostics/

runs/long_window_target/
  target/
  diagnostics/

output/test_reports/full_test_report.md
```

## Remaining warnings and limitations

- The quick minimal scene remains an engineering smoke test; its FFT bins cannot resolve a 25 MHz FDA step and it has HIGH numerical-dispersion risk.
- The quick minimal scene intentionally demonstrates requested/actual coordinate mismatch because `rx_offset=0.005 m` is below the `0.01 m` grid spacing.
- The long-window/grid-aligned example resolves the FDA step spectrally and reduces numerical-dispersion risk to LOW.
- Real-run V1-V4 are supported by `inspect-run`/`protocol-real`; V5-V8 are explicitly reported as not evaluated unless additional real baselines, depth sweeps, dictionary candidates, and random-medium ensembles are generated.
- The implementation does not model real hardware T/R switch behavior, mutual coupling, oscillator phase noise, or RF calibration errors.
