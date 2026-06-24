# Real gprMax run diagnostics

This document describes the real-run inspection workflow for `fda-mimo-gprmax`. It is intentionally separate from the synthetic V1-V8 protocol validation outputs under `output/protocol/`.

## Commands

```bash
fda-mimo-gprmax workflow examples/minimal_fda_mimo_scene.yaml --variant target
fda-mimo-gprmax workflow examples/minimal_fda_mimo_scene.yaml --variant background
fda-mimo-gprmax subtract examples/minimal_fda_mimo_scene.yaml
fda-mimo-gprmax inspect-run runs/scene_001_minimal --with-scatter
```

For an explicit scene run root:

```bash
fda-mimo-gprmax workflow examples/minimal_fda_mimo_scene.yaml --variant target --run-dir runs/pair_smoke
fda-mimo-gprmax workflow examples/minimal_fda_mimo_scene.yaml --variant background --run-dir runs/pair_smoke
fda-mimo-gprmax subtract examples/minimal_fda_mimo_scene.yaml --run-dir runs/pair_smoke
fda-mimo-gprmax inspect-run runs/pair_smoke --with-scatter
```

## Outputs

`inspect-run` writes:

```text
runs/<scene>/diagnostics/run_analysis_report.md
runs/<scene>/diagnostics/run_analysis_summary.json
runs/<scene>/diagnostics/tables/*.csv
runs/<scene>/diagnostics/figures/*.png
```

The report covers run overview, FDA scheduling evidence, MIMO tensor evidence, GPR physical evidence, coordinate consistency, source normalization, valid-band masks, target/background/scatter status, and recommended next actions.

## Decision levels

- `ACCEPTED_FOR_ENGINEERING_SMOKE`: rendered or partial products are inspectable, but real full-wave snapshot evidence is incomplete.
- `ACCEPTED_FOR_REAL_FULLWAVE_TARGET_SNAPSHOT`: target raw `.out` files and processed target snapshot exist and pass tensor/FDA configuration checks.
- `ACCEPTED_FOR_TARGET_BACKGROUND_SCATTER`: target, background, and scatter products are complete and mutually consistent.
- `ACCEPTED_FOR_STAGE1_REAL_VALIDATION`: stricter real-run Stage-1 criteria are satisfied.
- `NOT_ACCEPTED`: required products are missing or inconsistent.

## FDA law evidence

Real-run V1 is layered:

- `PASS-CONFIG`: configured/rendered/logged Tx center frequencies follow the FDA law.
- `PASS-SPECTRAL`: FFT source spectra can also resolve the FDA step.
- `WARNING-SPECTRAL-UNRESOLVED`: configuration evidence is valid, but FFT bin spacing is too coarse to resolve the FDA step.
- `FAIL`: configured/logged center frequencies do not follow the FDA law.

The quick minimal scene has a short time window and may report `PASS-CONFIG` plus `WARNING-SPECTRAL-UNRESOLVED`. This is not an FDA scheduling failure.

## Coordinate evidence

Processed snapshots store requested and actual geometry separately:

```text
/axis/tx_positions_requested
/axis/rx_positions_requested
/axis/tx_positions_actual
/axis/rx_positions_actual
/axis/position_quantization_error_tx
/axis/position_quantization_error_rx
```

`/axis/tx_positions` and `/axis/rx_positions` prefer actual positions when available. If actual positions are missing, they fall back to requested positions and `actual_positions_available=false` is recorded.

## Numerical dispersion

`inspect-run` parses gprMax stdout and grades numerical-dispersion risk:

- `< 2%`: LOW
- `2-5%`: MODERATE
- `5-10%`: HIGH
- `>= 10%`: SEVERE

High or severe risk does not necessarily invalidate a smoke run, but it limits physical interpretation of phase and group-delay structure.

## Scope boundary

The current implementation models ideal co-platform TDM FDA-MIMO-GPR only. It does not claim real T/R switch behavior, hardware mutual coupling, oscillator phase noise, or RF calibration error modeling.
