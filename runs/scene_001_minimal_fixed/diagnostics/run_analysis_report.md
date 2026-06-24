# Real gprMax Run Analysis: scene_001_minimal_fixed

**Decision:** `ACCEPTED_FOR_TARGET_BACKGROUND_SCATTER`

## Run overview
- `target`: stage=real, raw=4, processed=True
- `background`: stage=real, raw=4, processed=True

## FDA scheduling evidence
- Status: `PASS-CONFIG` / `WARNING-SPECTRAL-UNRESOLVED`
- Configured center frequencies (Hz): [1000000000.0, 1025000000.0, 1050000000.0, 1075000000.0]
- FFT bin spacing (Hz): 165896411.81532228

## MIMO tensor evidence
- Tensor: {'time_traces_shape': [4, 4, 313], 'frequency_tensor_raw_shape': [4, 4, 19], 'frequency_tensor_cal_shape': [4, 4, 19], 'nan_count_cal': 16, 'channel_energy': [[263010.8125, 1338.8763427734375, 525.4775390625, 303.8253173828125], [1319.7208251953125, 253222.5, 1321.370361328125, 521.3313598632812], [524.38818359375, 1303.9879150390625, 244008.78125, 1303.9879150390625], [304.9429931640625, 521.7120971679688, 1288.7567138671875, 235321.03125]], 'peak_time_index': [[62, 80, 84, 90], [78, 61, 78, 82], [81, 76, 59, 76], [85, 79, 74, 58]]}

## Coordinate consistency
- {'actual_positions_available': True, 'max_requested_actual_tx_error_m': 0.0, 'max_requested_actual_rx_error_m': 0.0050000000000000044, 'grid_quantization_warning': True, 'grid_spacing_min_m': 0.01}

## Numerical dispersion
- {'max_abs_phase_velocity_error_percent': 8.27, 'risk': 'HIGH', 'warning': True, 'warnings': ["WARNING: Potentially significant numerical dispersion. Estimated largest physical phase-velocity error is -7.15% in material 'soil' whose wavelength sampled by 4 cells. Maximum significant frequency estimated as 2.82024e+09Hz", "WARNING: Potentially significant numerical dispersion. Estimated largest physical phase-velocity error is -8.27% in material 'soil' whose wavelength sampled by 4 cells. Maximum significant frequency estimated as 2.98614e+09Hz", "WARNING: Potentially significant numerical dispersion. Estimated largest physical phase-velocity error is -8.27% in material 'soil' whose wavelength sampled by 4 cells. Maximum significant frequency estimated as 2.98614e+09Hz", "WARNING: Potentially significant numerical dispersion. Estimated largest physical phase-velocity error is -8.27% in material 'soil' whose wavelength sampled by 4 cells. Maximum significant frequency estimated as 2.98614e+09Hz"]}

## Target/background/scatter status
- Scatter: {'path': 'runs/scene_001_minimal_fixed/scatter/processed/scatter_snapshot.h5', 'time_traces_shape': [4, 4, 313], 'frequency_tensor_raw_shape': [4, 4, 19], 'summary': {'background_path': 'runs/scene_001_minimal_fixed/background/processed/snapshot.h5', 'frequency_tensor_raw_shape': [4, 4, 19], 'scatter_energy_fro': 224.24887084960938, 'scatter_to_target_energy_ratio': 0.00045009916640207943, 'target_energy_fro': 498221.03125, 'target_path': 'runs/scene_001_minimal_fixed/target/processed/snapshot.h5', 'time_traces_shape': [4, 4, 313], 'valid_fraction_pair': 0.9473684210526315, 'warnings': []}}

## Decision and next actions
- increase time_window or use configured center-frequency evidence
- align Tx/Rx coordinates with grid or reduce grid spacing
- reduce numerical dispersion by refining grid or lowering frequency
