# Validation Evidence Suite

The validation evidence suite provides small, reproducible checks for the FDA-MIMO-GPR compatibility layer. It combines automated pass/fail criteria with human-readable tables, figures, JSON summaries, and a Markdown report.

## Scope statement

The suite validates compatibility-layer semantics and I/O contracts:

- scenario configuration semantics;
- TDM/FDA render contract;
- gprMax-like HDF5 receiver parsing;
- Tx/Rx/time tensor indexing;
- FFT frequency-axis behavior;
- source-spectrum normalization and valid-band masking;
- target/background subtraction compatibility checks;
- optional real gprMax interface closure.

It does **not** validate hardware-realistic FDA-MIMO-GPR physics, real antenna mutual coupling, T/R switch behavior, receiver saturation, oscillator phase noise, moving-platform effects, measured-data calibration, or full system manufacturability.

## Run the synthetic evidence suite

```bash
conda activate gprMax
PYTHONPATH=src fda-mimo-gprmax evidence examples/minimal_fda_mimo_scene.yaml \
  --output-dir output/evidence/minimal \
  --overwrite
```

The command exits with status `0` only when all required synthetic validation cases pass. A non-zero status preserves generated artifacts for diagnosis.

## Output layout

```text
output/evidence/minimal/
  summary.json
  validation_report.md
  01_render_contract/
    render_contract_table.csv
    render_contract_table.md
    tx_rx_fda_grid.png
    result.json
  02_parser_roundtrip/
    yt_slice_l0.csv
    yt_index_map.png
    result.json
  03_fft_sanity/
    spectrum.csv
    peak_summary.json
    fft_peak.png
    result.json
  04_normalization_sanity/
    normalization_error.csv
    normalization_error.png
    result.json
  05_background_subtraction/
    scatter_slice_k0.csv
    scatter_recovery.png
    result.json
```

## Evidence cases

| Case | What it checks | What the artifact shows |
|---|---|---|
| `01_render_contract` | One active Tx source per input, all Rx in every input, Tx-bound FDA frequencies | Tx/Rx frequency grid and render-contract table |
| `02_parser_roundtrip` | `/rxs/rxN/<component>` maps to `Y_t[m,n,l]` correctly | Fixed time-slice index map |
| `03_fft_sanity` | Bin-aligned sinusoid peaks at expected FFT frequency | Spectrum plot and peak summary |
| `04_normalization_sanity` | `Y_rx = H_true * S_m` normalizes back to `H_true` on valid bands | Normalization error table/figure |
| `05_background_subtraction` | Known scatter is recovered and incompatible axes are rejected | Scatter magnitude slice and rejection metric |

## Optional real gprMax smoke validation

The real gprMax smoke path is disabled by default. Enable it only when a working gprMax runtime is available and you accept the extra runtime cost:

```bash
conda activate gprMax
PYTHONPATH=src fda-mimo-gprmax evidence examples/minimal_fda_mimo_scene.yaml \
  --output-dir output/evidence/minimal_smoke \
  --overwrite \
  --include-smoke \
  --timeout 120
```

Smoke validation records command lines, return codes, log paths, durations, raw-output paths, and processed snapshot artifacts. If gprMax is unavailable or fails before parseable outputs exist, the result is reported as an environment/runtime failure rather than semantic validation success.

## Interpreting failures

- Render-contract failures usually indicate broken scenario expansion or input rendering.
- Parser round-trip failures usually indicate HDF5 path/index mapping regressions.
- FFT sanity failures usually indicate frequency-axis or transform regressions.
- Normalization failures usually indicate source-spectrum masking or division regressions.
- Background-subtraction failures usually indicate axis compatibility or scatter subtraction regressions.
- Smoke failures may be caused by local gprMax installation, GPU/CPU runtime, geometry validity, or implementation errors; inspect the recorded logs before assigning cause.

## Real gprMax validation tiers

Validation outputs are separated by evidence type:

1. **Synthetic validation**: `fda-mimo-gprmax evidence ...` and `protocol analyze` use deterministic/synthetic evidence to validate formulas and reporting logic.
2. **Real gprMax smoke validation**: `workflow --variant target` proves real gprMax can produce raw `.out` files and a processed target snapshot.
3. **Target/background/scatter validation**: target and background workflows plus `subtract` produce a real scatter snapshot.
4. **Real-run Stage-1 validation**: `inspect-run --paper-mode` or future protocol-real checks evaluate real-run V1-V4 with stricter warnings.

Synthetic V1-V8 reports must not be described as real full-wave V1-V8 validation. Current real-run checks focus on V1-V4: FDA law, tensor integrity, MIMO geometry, and GPR physical sanity. V5-V8 require additional real baselines, sweeps, dictionary candidates, and random-medium ensembles.
