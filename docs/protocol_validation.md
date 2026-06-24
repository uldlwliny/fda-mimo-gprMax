# First-Stage Theory Validation Protocol

This document describes the implementation-facing workflow for `docs/theory_validation_protocol.md`. The protocol validates the gprMax--FDA-MIMO-GPR compatibility layer through model-independent structural checks rather than pointwise fitting to a specific analytic signal model.

## Scope

The protocol checks whether generated data has the required first-stage structure:

- Tx-index-dependent frequency scheduling;
- independently indexed Tx--Rx channel matrix;
- subsurface medium-dependent full-wave propagation;
- non-degenerate FDA structure relative to the `Delta f = 0` TDM MIMO-GPR limit.

It does **not** prove a particular Green's-function, Born, point-target, dictionary, covariance, localization, or measured-data model is exact.

## CLI workflow

The protocol CLI has four modes:

```bash
# 1. Plan configs/manifests without gprMax execution
PYTHONPATH=src fda-mimo-gprmax protocol plan examples/minimal_fda_mimo_scene.yaml \
  --output-root output/protocol/minimal_protocol \
  --checks V1,V2,V3 \
  --overwrite

# 2. Analyze deterministic/cached protocol evidence and write reports
PYTHONPATH=src fda-mimo-gprmax protocol analyze examples/minimal_fda_mimo_scene.yaml \
  --output-root output/protocol/minimal_protocol \
  --checks all \
  --overwrite

# 3. Regenerate reports from existing check_result.json files
PYTHONPATH=src fda-mimo-gprmax protocol report \
  --output-root output/protocol/minimal_protocol \
  --checks all

# 4. Opt-in real gprMax execution for planned scenarios
PYTHONPATH=src fda-mimo-gprmax protocol run examples/minimal_fda_mimo_scene.yaml \
  --output-root output/protocol/minimal_protocol_real \
  --checks V1,V2,V3 \
  --execute-real \
  --timeout 120
```

Without `--execute-real`, `protocol run` is safe: it creates the plan and reports cache status without invoking gprMax.

## Output layout

Protocol outputs follow the structure recommended by `docs/theory_validation_protocol.md`:

```text
output/protocol/<run_name>/
  protocol_plan_manifest.json
  protocol_plan.json
  first_stage_summary.json
  first_stage_protocol_report.md
  V1_source_fda_law/
    configs/
    raw/
    processed/
    figures/
    reports/
    check_result.json
  V2_tensor_integrity/
  ...
  V8_random_medium_covariance/
```

Each check writes protocol-specific artifacts such as `source_fda_law.csv`, `tensor_shape_check.json`, `mimo_geometry_check.json`, or `random_medium_covariance_check.json`.

## Scenario families

| Family | Purpose | Checks |
|---|---|---|
| A: homogeneous half-space + single target | Basic FDA/MIMO tensor structure and FDA/non-FDA control | V1, V2, V3, V5 |
| B: medium sweep | Epsilon delay and conductivity attenuation trends | V4 |
| C: target-depth sweep | Depth/frequency phase coupling | V6 |
| Dictionary candidates | FDA vs non-FDA response coherence structure | V7 |
| D: weak random-medium samples | Structured covariance induced by medium perturbations | V8 |

The current default planning path materializes small deterministic configs for these families. Real full-wave execution is opt-in and cache-aware.

## V1--V8 metrics

| Check | Main evidence | Status interpretation |
|---|---|---|
| V1 Source FDA law | source peak frequency errors `e_m`, adjacent-step errors `d_m` | V1 must pass; otherwise FDA source scheduling is not established |
| V2 Tensor integrity | snapshot fields, tensor shapes, axes, metadata | V2 must pass; otherwise no reusable FDA-MIMO-GPR snapshot exists |
| V3 MIMO geometry | channel energy, arrival time, bistatic path correlation | V3 must pass; otherwise Tx--Rx indexing may be invalid |
| V4 GPR medium | epsilon-delay trend and sigma-attenuation trend | V4 must pass; otherwise data cannot be considered medium-dependent GPR |
| V5 FDA degeneracy | FDA/non-FDA tensor and phase differences | V5 must be at least warning; otherwise FDA may be degenerate |
| V6 Depth/frequency coupling | depth arrival trend and cross-Tx phase-map changes | Enhanced evidence, especially for paper/benchmark use |
| V7 Dictionary non-equivalence | FDA/non-FDA coherence matrix difference `D_mu` | Enhanced evidence that FDA response structure is not ordinary MIMO-GPR |
| V8 Random-medium covariance | off-diagonal covariance ratio and block summaries | Enhanced evidence for structured clutter/covariance modeling |

## First-stage acceptance gate

Default acceptance follows `docs/theory_validation_protocol.md`:

1. V1, V2, V3, and V4 must pass.
2. V5 must be at least warning.
3. V6--V8 are enhanced checks. In `--paper-mode`, at least two of V6, V7, and V8 must pass unless explicitly overridden.

## Integration safety

Real gprMax protocol tests are marked `slow` and `integration` and are skipped by default. Enable them only when the local gprMax environment is ready:

```bash
RUN_GPRMAX_PROTOCOL_INTEGRATION=1 PYTHONPATH=src pytest -q -m integration tests/test_protocol.py
```

The default unit tests and protocol synthetic tests do not run gprMax.
