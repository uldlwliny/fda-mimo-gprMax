# FDA-MIMO-GPR gprMax Compatibility Layer

This project adds a Python compatibility layer around gprMax for ideal co-platform TDM FDA-MIMO-GPR snapshot generation. It does not modify gprMax. Instead, it validates a scenario YAML file, renders one gprMax input file per active Tx, optionally executes gprMax, and converts receiver traces into Tx-Rx-time and Tx-Rx-frequency tensors.

## Quick start

```bash
conda activate gprMax
uv pip install -e '.[test]'
fda-mimo-gprmax validate examples/minimal_fda_mimo_scene.yaml
fda-mimo-gprmax render examples/minimal_fda_mimo_scene.yaml
fda-mimo-gprmax workflow examples/minimal_fda_mimo_scene.yaml --dry-run
```

Run full gprMax simulations only after inspecting generated `.in` files.

## Project directories

- `examples/`: minimal reusable scenario examples for API/CLI documentation and tests.
- `experiments/`: application-oriented experiment archives containing configs, scripts, summaries, figures, and reports.
- `runs/`: default or temporary simulation run outputs.
- `output/`: validation evidence and protocol-analysis artifacts.

For new research experiments, copy `experiments/_template/` into `experiments/<application>/<experiment-id>/` and keep heavy run products under that experiment's `runs/` directory. Large `.out`, `.h5`, and `.npz` products are ignored by default; preserve their external storage location in `experiment.yaml` if they need long-term retention.

## Structured Cole--Cole media

Legacy raw gprMax material commands are still supported through `scene.materials`. For Cole--Cole five-parameter media, use the structured `media` section and let the adapter render a gprMax-compatible multi-pole Debye approximation:

```yaml
media:
  fit:
    n_poles: 12
    frequency_min: 5.0e7
    frequency_max: 1.5e8
    num_frequencies: 256
  materials:
    soil:
      model: cole_cole
      eps_s: 30.26
      eps_inf: 10.7
      tau: 9.55e-12
      alpha: 0.062
      sigma: 0.0
scene:
  materials: []
  geometry:
    - "#box: 0 0 0 0.60 0.40 0.14 soil"
```

Try the included examples:

```bash
fda-mimo-gprmax validate examples/minimal_cole_cole_scene.yaml
fda-mimo-gprmax render examples/minimal_cole_cole_scene.yaml --variant target
fda-mimo-gprmax validate examples/minimal_cole_cole_catalog_scene.yaml
```

The physical model remains Cole--Cole in metadata; generated `.in` files contain only gprMax-supported `#material` and `#add_dispersion_debye` commands. Manifests and processed snapshots record the original Cole--Cole parameters, Debye poles, fit band, and approximation errors.

## First-version scope

- TDM-MIMO: exactly one Tx is active per generated gprMax input file.
- FDA: each Tx index is bound to a source center frequency.
- GPR: propagation is delegated to gprMax full-wave FDTD.
- Primary data products are channel tensors and metadata, not B-scans or migrated images.

See `docs/schema.md` for the YAML and output schema. See `docs/validation.md` for the validation evidence suite that generates automated checks plus human-readable figures and reports. See `docs/protocol_validation.md` for the V1--V8 first-stage theory validation protocol.

## Real gprMax workflows and diagnostics

Use the high-level workflow commands for real target/background/scatter products:

```bash
fda-mimo-gprmax workflow examples/minimal_fda_mimo_scene.yaml --variant target
fda-mimo-gprmax workflow examples/minimal_fda_mimo_scene.yaml --variant background
fda-mimo-gprmax subtract examples/minimal_fda_mimo_scene.yaml
fda-mimo-gprmax inspect-run runs/scene_001_minimal --with-scatter
```

With an explicit run root, `workflow --run-dir runs/pair_smoke` writes `runs/pair_smoke/<variant>/`, so target and background can be subtracted directly:

```bash
fda-mimo-gprmax workflow examples/minimal_fda_mimo_scene.yaml --variant target --run-dir runs/pair_smoke --timeout 120
fda-mimo-gprmax workflow examples/minimal_fda_mimo_scene.yaml --variant background --run-dir runs/pair_smoke --timeout 120
fda-mimo-gprmax subtract examples/minimal_fda_mimo_scene.yaml --run-dir runs/pair_smoke
fda-mimo-gprmax inspect-run runs/pair_smoke --with-scatter
```

`inspect-run` generates `diagnostics/run_analysis_report.md`, `run_analysis_summary.json`, CSV tables, and matplotlib figures. It distinguishes configured FDA-law evidence (`PASS-CONFIG`) from FFT spectral resolvability (`PASS-SPECTRAL` or `WARNING-SPECTRAL-UNRESOLVED`). A short quick-smoke time window can prove that the FDA law entered the input/logs even when FFT bins cannot resolve a 25 MHz step.

Current scope: ideal near-co-located TDM FDA-MIMO-GPR with one active Tx and all Rx recording. The model does not include real T/R switch behavior, hardware mutual coupling, oscillator phase noise, or RF calibration errors.
