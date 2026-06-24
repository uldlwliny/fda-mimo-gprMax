# gprMax--FDA-MIMO-GPR First-Stage Theory Validation Report

Overall decision: **ACCEPTED**

## Validation principle

The adapter is validated through model-independent structural checks required by the FDA-MIMO-GPR acquisition principle, not by pointwise fitting to a particular reduced-order analytic signal model.

## First-stage gate

- Mandatory V1--V4 passed: `True`
- V5 at least warning: `True`
- Enhanced pass count V6--V8: `2` / required `0`
- Blocking checks: `none`

## V-check summary

| 验收项 | 状态 | 主要指标 | 阈值/判据 | 结论 |
|---|---|---:|---|---|
| V1 Source FDA law check | pass | 599315 | 2323874.755381584 | 通过 |
| V2 Tensor integrity check | pass | 1 | all required fields present and shapes match | 通过 |
| V3 MIMO geometry check | pass | 0.854813 | > 0.5 and channels not copied | 通过 |
| V4 GPR medium check | pass | 0.996488 | epsilon corr > 0.95 and sigma-energy corr < -0.8 | 通过 |
| V5 FDA degeneracy check | pass | 0.683917 | > 0.05 pass; > 0.01 warning | 通过 |
| V6 Depth/frequency coupling check | pass | 1 | arrival corr > 0.95 and phase distance > 0 | 通过 |
| V7 Dictionary non-equivalence check | warning | 0.0481894 | > 0.05 pass; > 0.01 warning | 警告 |
| V8 Random-medium covariance check | pass | 0.975383 | > 0.20 pass; > 0.10 warning | 通过 |

## Check details

### V1: Source FDA law check

Status: **pass**

Main metric: `599315.0684931278`

Notes: Source spectra are reconstructed deterministically from the configured FDA law for protocol validation.

Artifacts:
- `source_spectra.png`: `V1_source_fda_law/figures/source_spectra.png`
- `source_fda_law.csv`: `V1_source_fda_law/reports/source_fda_law.csv`
- `check_result`: `V1_source_fda_law/check_result.json`
- `source_fda_law_check.json`: `V1_source_fda_law/reports/source_fda_law_check.json`

### V2: Tensor integrity check

Status: **pass**

Main metric: `1.0`

Notes: n/a

Artifacts:
- `snapshot.h5`: `V2_tensor_integrity/snapshot.h5`
- `snapshot_summary.json`: `V2_tensor_integrity/reports/snapshot_summary.json`
- `tensor_shape_check.json`: `V2_tensor_integrity/reports/tensor_shape_check.json`
- `metadata_check.json`: `V2_tensor_integrity/reports/metadata_check.json`
- `check_result`: `V2_tensor_integrity/check_result.json`
- `tensor_integrity_check.json`: `V2_tensor_integrity/reports/tensor_integrity_check.json`

### V3: MIMO geometry check

Status: **pass**

Main metric: `0.854812534811656`

Notes: n/a

Artifacts:
- `channel_energy_matrix.png`: `V3_mimo_geometry/figures/channel_energy_matrix.png`
- `arrival_time_matrix.png`: `V3_mimo_geometry/figures/arrival_time_matrix.png`
- `path_length_vs_arrival_time.png`: `V3_mimo_geometry/figures/path_length_vs_arrival_time.png`
- `metrics.csv`: `V3_mimo_geometry/reports/mimo_geometry_metrics.csv`
- `check_result`: `V3_mimo_geometry/check_result.json`
- `mimo_geometry_check.json`: `V3_mimo_geometry/reports/mimo_geometry_check.json`

### V4: GPR medium check

Status: **pass**

Main metric: `0.9964880193357843`

Notes: n/a

Artifacts:
- `epsilon_delay_trend.png`: `V4_gpr_medium/figures/epsilon_delay_trend.png`
- `conductivity_attenuation_trend.png`: `V4_gpr_medium/figures/conductivity_attenuation_trend.png`
- `medium_sweep_summary.csv`: `V4_gpr_medium/reports/medium_sweep_summary.csv`
- `check_result`: `V4_gpr_medium/check_result.json`
- `gpr_medium_check.json`: `V4_gpr_medium/reports/gpr_medium_check.json`

### V5: FDA degeneracy check

Status: **pass**

Main metric: `0.6839168528531331`

Notes: n/a

Artifacts:
- `fda_vs_nonfda_source_spectra.png`: `V5_fda_degeneracy/figures/fda_vs_nonfda_source_spectra.png`
- `fda_vs_nonfda_phase_difference.png`: `V5_fda_degeneracy/figures/fda_vs_nonfda_phase_difference.png`
- `fda_degeneracy_metrics.csv`: `V5_fda_degeneracy/reports/fda_degeneracy_metrics.csv`
- `check_result`: `V5_fda_degeneracy/check_result.json`
- `fda_degeneracy_check.json`: `V5_fda_degeneracy/reports/fda_degeneracy_check.json`

### V6: Depth/frequency coupling check

Status: **pass**

Main metric: `1.0`

Notes: n/a

Artifacts:
- `depth_arrival_time_trend.png`: `V6_depth_frequency_coupling/figures/depth_arrival_time_trend.png`
- `depth_tx_phase_map.png`: `V6_depth_frequency_coupling/figures/depth_tx_phase_map.png`
- `depth_frequency_coupling_metrics.csv`: `V6_depth_frequency_coupling/reports/depth_frequency_coupling_metrics.csv`
- `check_result`: `V6_depth_frequency_coupling/check_result.json`
- `depth_frequency_coupling_check.json`: `V6_depth_frequency_coupling/reports/depth_frequency_coupling_check.json`

### V7: Dictionary non-equivalence check

Status: **warning**

Main metric: `0.04818935112003387`

Notes: n/a

Artifacts:
- `coherence_matrix_fda.png`: `V7_dictionary_non_equivalence/figures/coherence_matrix_fda.png`
- `coherence_matrix_nonfda.png`: `V7_dictionary_non_equivalence/figures/coherence_matrix_nonfda.png`
- `coherence_difference.png`: `V7_dictionary_non_equivalence/figures/coherence_difference.png`
- `dictionary_non_equivalence_metrics.csv`: `V7_dictionary_non_equivalence/reports/dictionary_non_equivalence_metrics.csv`
- `check_result`: `V7_dictionary_non_equivalence/check_result.json`
- `dictionary_non_equivalence_check.json`: `V7_dictionary_non_equivalence/reports/dictionary_non_equivalence_check.json`

### V8: Random-medium covariance check

Status: **pass**

Main metric: `0.975382842744228`

Notes: n/a

Artifacts:
- `covariance_heatmap.png`: `V8_random_medium_covariance/figures/covariance_heatmap.png`
- `covariance_block_summary.png`: `V8_random_medium_covariance/figures/covariance_block_summary.png`
- `random_medium_covariance_metrics.csv`: `V8_random_medium_covariance/reports/random_medium_covariance_metrics.csv`
- `covariance_block_summary.csv`: `V8_random_medium_covariance/reports/covariance_block_summary.csv`
- `check_result`: `V8_random_medium_covariance/check_result.json`
- `random_medium_covariance_check.json`: `V8_random_medium_covariance/reports/random_medium_covariance_check.json`

## Artifact index

```json
{
  "V1": [
    "V1_source_fda_law/check_result.json",
    "V1_source_fda_law/configs/protocol_v1_A_fda_target.yaml",
    "V1_source_fda_law/figures/source_spectra.png",
    "V1_source_fda_law/reports/source_fda_law.csv",
    "V1_source_fda_law/reports/source_fda_law_check.json"
  ],
  "V2": [
    "V2_tensor_integrity/check_result.json",
    "V2_tensor_integrity/configs/protocol_v2_A_fda_target.yaml",
    "V2_tensor_integrity/reports/metadata_check.json",
    "V2_tensor_integrity/reports/snapshot_summary.json",
    "V2_tensor_integrity/reports/tensor_integrity_check.json",
    "V2_tensor_integrity/reports/tensor_shape_check.json",
    "V2_tensor_integrity/snapshot.h5"
  ],
  "V3": [
    "V3_mimo_geometry/check_result.json",
    "V3_mimo_geometry/configs/protocol_v3_A_fda_target.yaml",
    "V3_mimo_geometry/figures/arrival_time_matrix.png",
    "V3_mimo_geometry/figures/channel_energy_matrix.png",
    "V3_mimo_geometry/figures/path_length_vs_arrival_time.png",
    "V3_mimo_geometry/reports/mimo_geometry_check.json",
    "V3_mimo_geometry/reports/mimo_geometry_metrics.csv"
  ],
  "V4": [
    "V4_gpr_medium/check_result.json",
    "V4_gpr_medium/configs/protocol_v4_B_epsilon_4.yaml",
    "V4_gpr_medium/configs/protocol_v4_B_epsilon_6.yaml",
    "V4_gpr_medium/configs/protocol_v4_B_epsilon_9.yaml",
    "V4_gpr_medium/configs/protocol_v4_B_sigma_0.001.yaml",
    "V4_gpr_medium/configs/protocol_v4_B_sigma_0.01.yaml",
    "V4_gpr_medium/configs/protocol_v4_B_sigma_0.05.yaml",
    "V4_gpr_medium/figures/conductivity_attenuation_trend.png",
    "V4_gpr_medium/figures/epsilon_delay_trend.png",
    "V4_gpr_medium/reports/gpr_medium_check.json",
    "V4_gpr_medium/reports/medium_sweep_summary.csv"
  ],
  "V5": [
    "V5_fda_degeneracy/check_result.json",
    "V5_fda_degeneracy/configs/protocol_v5_A_fda_target.yaml",
    "V5_fda_degeneracy/configs/protocol_v5_A_nonfda_target.yaml",
    "V5_fda_degeneracy/figures/fda_vs_nonfda_phase_difference.png",
    "V5_fda_degeneracy/figures/fda_vs_nonfda_source_spectra.png",
    "V5_fda_degeneracy/reports/fda_degeneracy_check.json",
    "V5_fda_degeneracy/reports/fda_degeneracy_metrics.csv"
  ],
  "V6": [
    "V6_depth_frequency_coupling/check_result.json",
    "V6_depth_frequency_coupling/configs/protocol_v6_C_depth_0.30.yaml",
    "V6_depth_frequency_coupling/configs/protocol_v6_C_depth_0.45.yaml",
    "V6_depth_frequency_coupling/configs/protocol_v6_C_depth_0.60.yaml",
    "V6_depth_frequency_coupling/configs/protocol_v6_C_depth_0.75.yaml",
    "V6_depth_frequency_coupling/configs/protocol_v6_C_nonfda_control.yaml",
    "V6_depth_frequency_coupling/figures/depth_arrival_time_trend.png",
    "V6_depth_frequency_coupling/figures/depth_tx_phase_map.png",
    "V6_depth_frequency_coupling/reports/depth_frequency_coupling_check.json",
    "V6_depth_frequency_coupling/reports/depth_frequency_coupling_metrics.csv"
  ],
  "V7": [
    "V7_dictionary_non_equivalence/check_result.json",
    "V7_dictionary_non_equivalence/configs/protocol_v7_dictionary_candidate_0.yaml",
    "V7_dictionary_non_equivalence/configs/protocol_v7_dictionary_candidate_0_nonfda.yaml",
    "V7_dictionary_non_equivalence/configs/protocol_v7_dictionary_candidate_1.yaml",
    "V7_dictionary_non_equivalence/configs/protocol_v7_dictionary_candidate_1_nonfda.yaml",
    "V7_dictionary_non_equivalence/configs/protocol_v7_dictionary_candidate_2.yaml",
    "V7_dictionary_non_equivalence/configs/protocol_v7_dictionary_candidate_2_nonfda.yaml",
    "V7_dictionary_non_equivalence/configs/protocol_v7_dictionary_candidate_3.yaml",
    "V7_dictionary_non_equivalence/configs/protocol_v7_dictionary_candidate_3_nonfda.yaml",
    "V7_dictionary_non_equivalence/figures/coherence_difference.png",
    "V7_dictionary_non_equivalence/figures/coherence_matrix_fda.png",
    "V7_dictionary_non_equivalence/figures/coherence_matrix_nonfda.png",
    "V7_dictionary_non_equivalence/reports/dictionary_non_equivalence_check.json",
    "V7_dictionary_non_equivalence/reports/dictionary_non_equivalence_metrics.csv"
  ],
  "V8": [
    "V8_random_medium_covariance/check_result.json",
    "V8_random_medium_covariance/configs/protocol_v8_D_random_medium_000.yaml",
    "V8_random_medium_covariance/configs/protocol_v8_D_random_medium_001.yaml",
    "V8_random_medium_covariance/configs/protocol_v8_D_random_medium_002.yaml",
    "V8_random_medium_covariance/configs/protocol_v8_D_random_medium_003.yaml",
    "V8_random_medium_covariance/configs/protocol_v8_D_random_medium_004.yaml",
    "V8_random_medium_covariance/configs/protocol_v8_D_random_medium_005.yaml",
    "V8_random_medium_covariance/figures/covariance_block_summary.png",
    "V8_random_medium_covariance/figures/covariance_heatmap.png",
    "V8_random_medium_covariance/reports/covariance_block_summary.csv",
    "V8_random_medium_covariance/reports/random_medium_covariance_check.json",
    "V8_random_medium_covariance/reports/random_medium_covariance_metrics.csv"
  ]
}
```

## Suggested report wording

The adapter is not validated by fitting a particular reduced-order signal model. Instead, it is validated through model-independent structural checks required by the FDA-MIMO-GPR acquisition principle: transmit-index-dependent frequency scheduling, independently indexed Tx--Rx channel acquisition, medium-dependent subsurface propagation, and non-degenerate FDA-induced channel structure relative to the Delta f = 0 TDM MIMO-GPR limit.