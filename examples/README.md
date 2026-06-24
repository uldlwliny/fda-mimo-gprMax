# Minimal FDA-MIMO-GPR Example

The example scenario is `minimal_fda_mimo_scene.yaml`. It defines a 4-Tx near-co-located co-platform array, a linear FDA law, a simple lossy half-space, and target/background variants.

## 1. Validate

```bash
conda activate gprMax
fda-mimo-gprmax validate examples/minimal_fda_mimo_scene.yaml
```

## 2. Dry-run render

Render and inspect inputs before running gprMax:

```bash
fda-mimo-gprmax workflow examples/minimal_fda_mimo_scene.yaml --dry-run
```

Generated files are written under `runs/scene_001_minimal/<variant>/config/`.

## 3. Optional full gprMax execution

After inspecting generated `.in` files:

```bash
fda-mimo-gprmax run examples/minimal_fda_mimo_scene.yaml --variant target
fda-mimo-gprmax run examples/minimal_fda_mimo_scene.yaml --variant background
```

This requires an installed and working gprMax environment.

## 4. Post-process raw outputs

```bash
fda-mimo-gprmax process examples/minimal_fda_mimo_scene.yaml --variant target
```

The processed snapshot is written to `processed/snapshot.h5` and `processed/snapshot.npz`.

## 5. Load a snapshot

```python
import h5py

with h5py.File('runs/scene_001_minimal/target/processed/snapshot.h5', 'r') as h5:
    yt = h5['/snapshot/time_traces'][...]
    yf = h5['/snapshot/frequency_tensor_raw'][...]
    freqs = h5['/axis/frequencies'][...]

print(yt.shape, yf.shape, freqs.shape)
```

## 6. Generate validation evidence

Run the fast synthetic evidence suite first:

```bash
fda-mimo-gprmax evidence examples/minimal_fda_mimo_scene.yaml \
  --output-dir output/evidence/minimal \
  --overwrite
```

This writes `summary.json`, `validation_report.md`, and per-case figures/tables. Optional real gprMax smoke validation is disabled by default; enable it only when the gprMax runtime is available:

```bash
fda-mimo-gprmax evidence examples/minimal_fda_mimo_scene.yaml \
  --output-dir output/evidence/minimal_smoke \
  --overwrite \
  --include-smoke \
  --timeout 120
```

## 7. Plan or analyze the theory validation protocol

Create a plan for the mandatory lightweight protocol checks without executing gprMax:

```bash
fda-mimo-gprmax protocol plan examples/minimal_fda_mimo_scene.yaml \
  --output-root output/protocol/minimal_protocol \
  --checks V1,V2,V3 \
  --overwrite
```

Generate a deterministic V1--V8 first-stage analysis product and report:

```bash
fda-mimo-gprmax protocol analyze examples/minimal_fda_mimo_scene.yaml \
  --output-root output/protocol/minimal_protocol \
  --checks all \
  --overwrite
```

Opt-in real gprMax execution remains explicit:

```bash
fda-mimo-gprmax protocol run examples/minimal_fda_mimo_scene.yaml \
  --output-root output/protocol/minimal_protocol_real \
  --checks V1,V2,V3 \
  --execute-real \
  --timeout 120
```
