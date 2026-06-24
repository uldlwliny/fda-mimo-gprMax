# FDA-MIMO-GPR Compatibility Layer Schema

## Scenario YAML

Required top-level sections:

- `name`: scenario identifier used in run paths.
- `random_seed`: integer stored in metadata.
- `domain.size`: gprMax domain size `[x, y, z]` in metres.
- `grid.spacing`: FDTD cell size `[dx, dy, dz]` in metres.
- `time.window`: gprMax time window in seconds.
- `scene.materials`: raw gprMax material commands.
- `scene.geometry`: raw gprMax geometry commands shared by all variants.
- `array`: Tx/Rx geometry.
- `fda`: FDA source-frequency schedule.
- `waveform`: source waveform settings.
- `receiver.component`: one of `Ex`, `Ey`, `Ez`, `Hx`, `Hy`, `Hz`, `Ix`, `Iy`, `Iz`.
- `variants`: target/background scene differences.
- `execution`: external gprMax command settings.
- `output`: export, diagnostics, FFT, and valid-band settings.

### Array modes

- `strict`: `rx_positions` are copied from `tx_positions`.
- `offset`: `rx_positions = tx_positions + rx_offset`.
- `explicit`: both `tx_positions` and `rx_positions` are required.

All modes preserve explicit Tx and Rx axes. Strict co-location does not collapse MIMO channels.

### FDA law

Version 0 supports:

```yaml
fda:
  type: linear
  f0: 1.0e9
  df: 2.5e7
```

The implementation uses zero-based index `m`: `f_m = f0 + m * df`.

### Waveforms

Built-in mode renders a gprMax `#waveform` command for each Tx:

```yaml
waveform:
  mode: builtin
  shape: ricker
  amplitude: 1.0
```

Excitation-file mode writes one custom excitation file per Tx and references it with `#excitation_file`.

## Structured Cole--Cole media

Legacy raw gprMax material commands remain valid:

```yaml
scene:
  materials:
    - "#material: 6 0.01 1 0 soil"
```

For frequency-dispersive physical media, scenarios may instead declare structured Cole--Cole media. The compatibility layer treats the Cole--Cole parameters as the physical source model and renders a deterministic multi-pole Debye approximation for gprMax execution:

```yaml
media:
  fit:
    n_poles: 12
    frequency_min: 5.0e7
    frequency_max: 1.5e8
    num_frequencies: 256
    max_rel_error_warn: 0.05
    max_rel_error_fail: 0.15
    allow_poor_fit: false
  materials:
    soil:
      model: cole_cole
      eps_s: 30.26
      eps_inf: 10.7
      tau: 9.55e-12
      alpha: 0.062
      sigma: 0.0
      source: Schwing 2013
      role: fine-grained lossy soil anchor
scene:
  materials: []
  geometry:
    - "#box: 0 0 0 0.60 0.40 0.14 soil"
```

Cole--Cole five-parameter fields are:

- `eps_s`: static relative permittivity.
- `eps_inf`: high-frequency limiting relative permittivity.
- `tau`: characteristic relaxation time in seconds.
- `alpha`: Cole--Cole broadening factor, constrained by `0 <= alpha < 1`.
- `sigma`: DC conductivity in S/m.

The rendered gprMax input contains only commands supported by gprMax, for example:

```text
#material: <eps_inf> <sigma> 1 0 soil
#add_dispersion_debye: <n_poles> <delta_eps_1> <tau_1> ... <delta_eps_n> <tau_n> soil
```

The optional default catalog can be enabled with:

```yaml
media:
  use_default_catalog: true
  materials:
    soil:
      from_catalog: S1
```

Catalog keys `S1`--`S5` are built into the adapter. Explicit YAML fields override catalog defaults. Structured media IDs must not collide with raw `#material` IDs in `scene.materials`.

Normalized configuration, run manifests, and processed metadata preserve both the original Cole--Cole parameters and the Debye approximation metadata, including fit frequency range, pole count, `max_rel_error`, and `rms_rel_error`. For physical interpretation and reporting, use the original Cole--Cole metadata; Debye poles are the gprMax execution approximation.

## Run directory layout

```text
runs/<scenario>/<variant>/
  config/
    generated_tx_000.in
    generated_tx_001.in
    excitation_tx_000.txt
  raw/
    tx_000.out
    tx_001.out
  processed/
    snapshot.h5
    snapshot.npz
  logs/
    run_manifest.json
    gprmax_stdout_tx_000.txt
    gprmax_stderr_tx_000.txt
  figures/
    trace_preview.png
    spectrum_preview.png
    phase_map.png
    valid_band_mask.png
    processing_summary.json
```

## Processed HDF5 snapshot

The HDF5 writer creates these groups:

- `/snapshot/time_traces`: `float32 [Nt, Nr, Lt]`
- `/snapshot/frequency_tensor_raw`: `complex64 [Nt, Nr, Kf]`
- `/snapshot/frequency_tensor_cal`: `complex64 [Nt, Nr, Kf]` when normalization is enabled
- `/snapshot/source_spectra`: `complex64 [Nt, Kf]`
- `/snapshot/valid_band_mask`: `bool [Nt, Kf]`
- `/axis/tx_positions`: `float64 [Nt, 3]`
- `/axis/rx_positions`: `float64 [Nr, 3]`
- `/axis/time`: `float64 [Lt]`
- `/axis/frequencies`: `float64 [Kf]`
- `/axis/fda_center_frequencies`: `float64 [Nt]`
- `/scene/*`: material, geometry, domain, and grid metadata
- `/metadata/*`: normalized configuration, versions, seeds, and checksums

## Limitations

The first version does not model hardware T/R switching, circulators, receiver saturation, oscillator phase noise, real antenna coupling, true simultaneous MIMO, moving-platform effects, or measured-data calibration. It is an ideal full-wave acquisition layer for synthetic FDA-MIMO-GPR channel tensors.

## Real-run coordinate and diagnosis schema

Processed snapshots now distinguish requested and actual gprMax geometry:

```text
/axis/tx_positions_requested               float64 [Nt, 3]
/axis/rx_positions_requested               float64 [Nr, 3]
/axis/tx_positions_actual                  float64 [Nt, 3]
/axis/rx_positions_actual                  float64 [Nt, Nr, 3]
/axis/position_quantization_error_tx       float64 [Nt, 3]
/axis/position_quantization_error_rx       float64 [Nt, Nr, 3]
/metadata/axis_convention                  string
/metadata/actual_positions_available       bool
/metadata/run_evidence                     JSON
/metadata/processing_metrics               JSON
/metadata/numerical_dispersion             JSON
```

Scatter snapshots are written to `runs/<scene>/scatter/processed/scatter_snapshot.h5`:

```text
/scatter/time_traces                 float32 [Nt, Nr, Lt]
/scatter/frequency_tensor_raw         complex64 [Nt, Nr, Kf]
/scatter/frequency_tensor_cal         complex64 [Nt, Nr, Kf]
/scatter/valid_band_mask_pair         bool [Nt, Kf]
/target/ref_path                      string
/background/ref_path                  string
/metadata/subtraction_summary          JSON
```

`inspect-run` writes `run_analysis_summary.json` with sections for `variants`, `tensor`, `fda`, `coordinates`, `numerical_dispersion`, `scatter`, `real_run_checks`, and `recommended_next_actions`.
