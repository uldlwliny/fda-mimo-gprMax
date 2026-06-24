# Real gprMax Run Analysis: long_window_target

**Decision:** `ACCEPTED_FOR_REAL_FULLWAVE_TARGET_SNAPSHOT`

## Run overview
- `target`: stage=real, raw=4, processed=True
- `background`: stage=absent, raw=0, processed=False

## FDA scheduling evidence
- Status: `PASS-CONFIG` / `PASS-SPECTRAL`
- Configured center frequencies (Hz): [300000000.0, 325000000.0, 350000000.0, 375000000.0]
- FFT bin spacing (Hz): 8330751.949012637

## MIMO tensor evidence
- Tensor: {'time_traces_shape': [4, 4, 6233], 'frequency_tensor_raw_shape': [4, 4, 121], 'frequency_tensor_cal_shape': [4, 4, 121], 'nan_count_cal': 40, 'channel_energy': [[290541.65625, 3576.343505859375, 743.8203735351562, 329.6942443847656], [15668.53125, 257510.234375, 3139.911376953125, 675.556640625], [1129.14013671875, 13949.4794921875, 230263.40625, 2793.165283203125], [393.88165283203125, 1028.967529296875, 12534.12109375, 207514.296875]], 'peak_time_index': [[284, 203, 201, 268], [189, 262, 187, 185], [172, 176, 244, 173], [214, 160, 164, 228]]}

## Coordinate consistency
- {'actual_positions_available': True, 'max_requested_actual_tx_error_m': 0.0, 'max_requested_actual_rx_error_m': 0.0, 'grid_quantization_warning': False, 'grid_spacing_min_m': 0.01}

## Numerical dispersion
- {'max_abs_phase_velocity_error_percent': 0.81, 'risk': 'LOW', 'warning': True, 'warnings': []}

## Target/background/scatter status
- Scatter: {'present': False}

## Decision and next actions
- run background variant
