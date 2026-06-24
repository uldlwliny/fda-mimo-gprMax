# FDA-MIMO-GPR Validation Evidence Report

Suite: `synthetic-validation`
Status: **PASS**

## Scope

This suite validates compatibility-layer semantics and I/O contracts: configuration semantics, render contract, HDF5 parsing, tensor indexing, FFT behavior, source normalization, and background subtraction. It does **not** validate hardware-realistic FDA-MIMO-GPR physics, antenna coupling, T/R switch behavior, platform motion, or measured-data calibration.

## Evidence Pyramid

1. Render contract: one Tx source, all Rx commands, Tx-bound FDA frequencies.
2. Parser round-trip: gprMax-like HDF5 receiver datasets map to `Y_t[m,n,l]`.
3. FFT sanity: known sinusoid peak appears at the expected frequency bin.
4. Source normalization: `Y_rx = H_true * S_m` recovers `H_true` on valid bands.
5. Background subtraction: known scatter is recovered and incompatible axes are rejected.

## Case Results

### 01_render_contract: PASS

**Claim:** Rendered gprMax inputs preserve TDM-MIMO source activation, all-Rx reception, and Tx-index-bound FDA frequencies.

**Metrics:**

```json
{
  "num_inputs": 4,
  "expected_inputs": 4,
  "rows": [
    {
      "tx_index": 0,
      "active_source_count": 1,
      "receiver_count": 4,
      "rendered_frequency_hz": 1000000000.0,
      "expected_frequency_hz": 1000000000.0,
      "frequency_error_hz": 0.0,
      "passed": true
    },
    {
      "tx_index": 1,
      "active_source_count": 1,
      "receiver_count": 4,
      "rendered_frequency_hz": 1025000000.0,
      "expected_frequency_hz": 1025000000.0,
      "frequency_error_hz": 0.0,
      "passed": true
    },
    {
      "tx_index": 2,
      "active_source_count": 1,
      "receiver_count": 4,
      "rendered_frequency_hz": 1050000000.0,
      "expected_frequency_hz": 1050000000.0,
      "frequency_error_hz": 0.0,
      "passed": true
    },
    {
      "tx_index": 3,
      "active_source_count": 1,
      "receiver_count": 4,
      "rendered_frequency_hz": 1075000000.0,
      "expected_frequency_hz": 1075000000.0,
      "frequency_error_hz": 0.0,
      "passed": true
    }
  ]
}
```

**Artifacts:**

- `csv`: `01_render_contract/render_contract_table.csv`
- `table`: `01_render_contract/render_contract_table.md`
- `figure`: `01_render_contract/tx_rx_fda_grid.png`

**Limitations:**

- This case validates compatibility-layer semantics and I/O contracts; it does not validate hardware-realistic FDA-MIMO-GPR physics.

### 02_parser_roundtrip: PASS

**Claim:** Synthetic gprMax-like HDF5 receiver datasets map to the expected Y_t[Tx,Rx,time] tensor indices.

**Metrics:**

```json
{
  "max_abs_error": 0.0,
  "tensor_shape": [
    4,
    4,
    16
  ],
  "tolerance": 1e-06
}
```

**Artifacts:**

- `csv`: `02_parser_roundtrip/yt_slice_l0.csv`
- `figure`: `02_parser_roundtrip/yt_index_map.png`

**Limitations:**

- This case validates compatibility-layer semantics and I/O contracts; it does not validate hardware-realistic FDA-MIMO-GPR physics.

### 03_fft_sanity: PASS

**Claim:** Frequency transform places a bin-aligned sinusoid peak at the expected FFT frequency bin.

**Metrics:**

```json
{
  "expected_frequency_hz": 62499999.99999999,
  "detected_frequency_hz": 62499999.99999999,
  "frequency_error_hz": 0.0,
  "tolerance": 1e-06
}
```

**Artifacts:**

- `csv`: `03_fft_sanity/spectrum.csv`
- `peak_summary`: `03_fft_sanity/peak_summary.json`
- `figure`: `03_fft_sanity/fft_peak.png`

**Limitations:**

- This case validates compatibility-layer semantics and I/O contracts; it does not validate hardware-realistic FDA-MIMO-GPR physics.

### 04_normalization_sanity: PASS

**Claim:** Source normalization recovers known channel response on valid bands and preserves invalid-band masking.

**Metrics:**

```json
{
  "max_valid_error": 1.3328003944934608e-07,
  "invalid_has_nan": true,
  "tolerance": 1e-06,
  "by_tx": [
    {
      "tx_index": 0,
      "max_valid_error": 1.2287812012345967e-07,
      "valid_bins": 11,
      "invalid_bins": 1
    },
    {
      "tx_index": 1,
      "max_valid_error": 1.3328003944934608e-07,
      "valid_bins": 11,
      "invalid_bins": 1
    },
    {
      "tx_index": 2,
      "max_valid_error": 1.3328003944934608e-07,
      "valid_bins": 11,
      "invalid_bins": 1
    },
    {
      "tx_index": 3,
      "max_valid_error": 1.3328003944934608e-07,
      "valid_bins": 11,
      "invalid_bins": 1
    }
  ]
}
```

**Artifacts:**

- `csv`: `04_normalization_sanity/normalization_error.csv`
- `figure`: `04_normalization_sanity/normalization_error.png`

**Limitations:**

- This case validates compatibility-layer semantics and I/O contracts; it does not validate hardware-realistic FDA-MIMO-GPR physics.

### 05_background_subtraction: PASS

**Claim:** Target/background subtraction recovers known scatter tensors and rejects incompatible axes.

**Metrics:**

```json
{
  "max_scatter_error": 1.2287812012345967e-07,
  "incompatible_rejected": true,
  "tolerance": 1e-06
}
```

**Artifacts:**

- `csv`: `05_background_subtraction/scatter_slice_k0.csv`
- `figure`: `05_background_subtraction/scatter_recovery.png`

**Limitations:**

- This case validates compatibility-layer semantics and I/O contracts; it does not validate hardware-realistic FDA-MIMO-GPR physics.
