# Sim 工程后续增强任务说明：修复真实 gprMax 闭环、全量测试与自动诊断能力

## 0. 任务定位

本任务面向 `fda-mimo-gprmax` 工程。当前工程已经完成了理想收发共址 TDM FDA-MIMO-GPR 兼容层的初版能力：可以从场景 YAML 渲染 gprMax input files，逐 Tx 调用 gprMax，解析 `.out` HDF5，组装 `Y_t[m,n,t]` 与 `Y_f[m,n,k]`，并输出 HDF5/NPZ 和基础诊断图。

当前 `runs/scene_001_minimal/target/` 已经形成真实 gprMax target variant 闭环；但检查发现仍存在若干必须修复的细节问题。除此之外，工程需要增加一套完整测试矩阵和一个面向 `runs/` 产物的自动读取、分析和诊断能力，使 agent 或用户能够像人工审阅一样快速判断一次仿真是否真正构成 FDA-MIMO-GPR 快拍。

本说明文档的目标是指导 agent 完成三类工作：

1. 修复当前真实运行中暴露的所有细节问题；
2. 运行并扩展全量测试，验证完整代码能力；
3. 增加一个独立诊断命令或 skill-like 能力，对 `runs/` 下的产物进行自动读取、解读、风险判断和报告生成。

除非特别说明，不要改变当前工程的基本体制定义：

- 理想收发共址或近共址 TDM FDA-MIMO-GPR；
- Tx/Rx 共平台；
- 单次只激活一个 Tx；
- 所有 Rx 同时记录；
- 第 `m` 个 Tx 使用 `f_m = f_0 + (m-1) Δf` 的源波形；
- 完成 `N_t` 次 sequential Tx 后形成一个快拍。

---

## 1. 当前真实运行结果暴露的问题

当前 `runs/scene_001_minimal/target/` 已经具备真实 gprMax 输出：

```text
runs/scene_001_minimal/target/
  config/generated_tx_000.in ... generated_tx_003.in
  raw/tx_000.out ... tx_003.out
  logs/gprmax_stdout_tx_000.txt ...
  processed/snapshot.h5
  processed/snapshot.npz
  figures/trace_preview.png
  figures/spectrum_preview.png
  figures/phase_map.png
  figures/valid_band_mask.png
  figures/processing_summary.json
```

已经确认的正面结果：

- 4 个 Tx 均成功调用 gprMax，return code 为 0；
- 每个 Tx 对应一个 input file；
- 每个 input file 中只激活一个 `#hertzian_dipole`，同时包含 4 个 `#rx`；
- FDA 频率调度已进入 input 和 stdout：`1.000, 1.025, 1.050, 1.075 GHz`；
- 已输出 `Y_t ∈ R^{4×4×313}` 和 `Y_f ∈ C^{4×4×19}`；
- `snapshot.h5` 已包含 axis、scene、snapshot、metadata 等基本组。

必须修复或增强的问题如下。

### 1.1 requested 坐标与 actual gprMax 坐标不一致

当前配置中 Rx 相对 Tx 偏移为 `0.005 m`，但 gprMax 网格步长为 `0.01 m`。gprMax 实际输出中的 receiver positions 被量化到了网格点，导致：

```text
requested rx positions: 0.225, 0.265, 0.305, 0.345
actual rx positions:    0.220, 0.260, 0.300, 0.340
```

这会导致 HDF5 metadata 与真实 gprMax 仿真坐标不一致。该问题必须修复。

### 1.2 background variant 尚未真实运行

当前 `runs/scene_001_minimal/background/` 只有 dry-run manifest 和 rendered inputs，没有真实 `.out` 与 `processed/snapshot.h5`。因此当前还不能形成真实背景扣除：

```math
Y_{scat} = Y_{target} - Y_{background}
```

必须补齐 background 的真实运行、处理、scatter tensor 生成和诊断。

### 1.3 FFT 频率分辨率不足以分辨 FDA 步进

当前 time window 为 `6 ns`，得到频率分辨率约为：

```math
\Delta f_{FFT} \approx 166\,\mathrm{MHz}
```

而 FDA 步进为 `25 MHz`。因此虽然 input/stdout 已经证明每个 Tx 的中心频率不同，但在 processed `source_spectra` 的离散 FFT bin 中，4 个 Tx 的谱峰会落入同一个 bin，无法用 `argmax |S_m(f)|` 直接验证 `25 MHz` 频移。

必须提供一种处理策略：

- 要么延长 time window，使 `Δf_FFT << Δf`；
- 要么在 V1 的 real-run 验收中使用 input/stdout/metadata 中的 waveform center frequency 作为直接证据，FFT 谱峰仅作为辅助证据；
- 最好二者都实现：默认 real physical validation 配置使用较长 time window，并在报告中同时给出 configured center frequencies 与 measured spectral peaks。

### 1.4 数值色散警告需要被捕获并进入报告

gprMax stdout 显示 soil 中估计最大物理相速度误差约为 `7–8%`。这不影响最小闭环，但会影响相位、群时延和 FDA 相位结构判断。必须在自动诊断中解析 stdout，提取 numerical dispersion warning，并在报告中标注风险等级。

### 1.5 当前 V1–V8 报告仍主要是 synthetic protocol validation

`output/protocol/theory_protocol_latest/` 里的 V1–V8 报告是 protocol 的合成验收，不能等同于真实 gprMax full-wave 数据验收。必须新增 real-run analysis 模式，直接读取 `runs/.../processed/snapshot.h5` 和 raw `.out`，并给出真实运行产物的 V1–V4 或 V1–V8 可行范围内的验收结论。

### 1.6 HDF5 需要保存更完整的实际运行证据

当前 HDF5 保存了基本 axis、scene、metadata，但需要增强为 benchmark-grade 方向：

- 保存 requested 与 actual Tx/Rx positions；
- 保存 gprMax version；
- 保存每个 Tx input file checksum；
- 保存每个 `.out` file checksum；
- 保存 stdout/stderr 路径或文本摘要；
- 保存 source waveform configured center frequencies；
- 保存 actual receiver positions from `.out`；
- 保存 numerical dispersion diagnostics；
- 保存 effective FFT resolution 与 valid-band 信息。

---

## 2. 修复任务 A：actual coordinate metadata

### 2.1 目标

解析真实 gprMax `.out` 文件中的 source/receiver actual positions，并在 processed HDF5 中保存。不要只使用 YAML requested 坐标。

### 2.2 需要检查的代码位置

优先检查：

```text
src/fda_mimo_gprmax/parsing.py
src/fda_mimo_gprmax/processing.py
src/fda_mimo_gprmax/serialization.py
src/fda_mimo_gprmax/config.py
```

### 2.3 设计要求

在 parser 层读取每个 raw `.out` 文件中的实际坐标。gprMax HDF5 通常包含 receiver groups 和 source groups，具体字段名需要兼容当前版本。实现时要做到：

1. 不假设只有一个固定路径；
2. 若找不到 actual positions，返回 warning，而不是静默使用 requested；
3. 保存 per-Tx actual source position 和 per-Tx/per-Rx actual receiver position；
4. 检查不同 Tx 文件中 Rx positions 是否一致；
5. 若 requested 与 actual 偏差超过阈值，报告 warning。

推荐数据结构：

```python
@dataclass
class ParsedTxOutput:
    tx_index: int
    time: np.ndarray
    traces: np.ndarray          # [Nr, Lt]
    component: str
    source_position_actual: np.ndarray | None      # [3]
    receiver_positions_actual: np.ndarray | None   # [Nr, 3]
    hdf5_attrs: dict[str, Any]
    warnings: list[str]
```

若当前已有类似结构，请扩展而非重写。

### 2.4 HDF5 输出要求

在 `snapshot.h5` 中增加以下 datasets：

```text
/axis/tx_positions_requested               float64 [Nt, 3]
/axis/rx_positions_requested               float64 [Nr, 3]
/axis/tx_positions_actual                  float64 [Nt, 3]
/axis/rx_positions_actual                  float64 [Nt, Nr, 3] 或 [Nr, 3]
/axis/position_quantization_error_tx       float64 [Nt, 3]
/axis/position_quantization_error_rx       float64 [Nt, Nr, 3] 或 [Nr, 3]
```

保留原 `/axis/tx_positions` 与 `/axis/rx_positions` 以兼容旧代码，但应明确其语义。建议：

- `/axis/tx_positions` 指向 actual；
- `/axis/rx_positions` 指向 actual；
- requested 单独保存；
- 在 `/metadata/axis_convention` 中写明。

### 2.5 验收标准

新增或修改测试：

```text
tests/test_parsing.py
tests/test_serialization.py
tests/test_running.py
```

至少覆盖：

1. mock HDF5 中含 actual positions 时能正确读取；
2. actual positions 与 requested 不一致时生成 warning；
3. processed snapshot 中同时存在 requested 与 actual；
4. 若 actual 缺失，不影响旧 mock 数据处理，但报告中标注 `actual_positions_available=false`。

---

## 3. 修复任务 B：background 与 scatter tensor 闭环

### 3.1 目标

增加真实 target/background 成对运行和差分输出能力。最终应能从同一个 scenario 自动生成：

```text
runs/<scene>/target/processed/snapshot.h5
runs/<scene>/background/processed/snapshot.h5
runs/<scene>/scatter/processed/scatter_snapshot.h5
```

或在 scene 根目录下生成：

```text
runs/<scene>/processed/scatter_snapshot.h5
```

### 3.2 CLI 设计建议

保留现有命令，同时增加更高层命令：

```bash
fda-mimo-gprmax workflow examples/minimal_fda_mimo_scene.yaml --variant target
fda-mimo-gprmax workflow examples/minimal_fda_mimo_scene.yaml --variant background
fda-mimo-gprmax subtract examples/minimal_fda_mimo_scene.yaml --target-variant target --background-variant background
```

或者增加：

```bash
fda-mimo-gprmax workflow-pair examples/minimal_fda_mimo_scene.yaml --target-variant target --background-variant background
```

`subtract` 命令最小即可，不要过度设计。

### 3.3 差分公式

读取 target 和 background 的 `snapshot.h5`：

```math
Y_t^{scat} = Y_t^{target} - Y_t^{background}
```

```math
Y_f^{scat} = Y_f^{target} - Y_f^{background}
```

对 calibrated tensor 同样执行：

```math
\widetilde Y_f^{scat} = \widetilde Y_f^{target} - \widetilde Y_f^{background}
```

但应注意：若 calibrated tensor 含 NaN 或 valid-band mask 不一致，应先形成联合 mask：

```math
M_{valid}^{pair} = M_{valid}^{target} \land M_{valid}^{background}
```

无效频点保留 NaN，不要强行填零。

### 3.4 scatter HDF5 输出结构

建议：

```text
/scatter/time_traces                 float32 [Nt, Nr, Lt]
/scatter/frequency_tensor_raw         complex64 [Nt, Nr, Kf]
/scatter/frequency_tensor_cal         complex64 [Nt, Nr, Kf]
/scatter/valid_band_mask_pair         bool [Nt, Kf]

/target/ref_path                      string
/background/ref_path                  string

/axis/...                             复制并校验一致
/scene/...                            复制 target scene，同时注明 background scene has no targets
/metadata/subtraction_summary          string/json
```

### 3.5 一致性检查

在 subtraction 前必须检查：

- `Nt, Nr, Lt, Kf` 完全一致；
- `time` 轴一致；
- `frequencies` 轴一致；
- FDA center frequencies 一致；
- actual Tx/Rx positions 一致或差异低于阈值；
- source spectra 一致或差异低于阈值；
- gprMax domain/grid/time_window 一致。

若不一致，命令应失败并输出明确错误。

### 3.6 验收标准

新增测试：

```text
tests/test_subtraction.py
```

覆盖：

1. target/background mock snapshots 维度一致时成功输出 scatter；
2. time/frequency axis 不一致时报错；
3. valid mask 联合逻辑正确；
4. NaN 处理正确；
5. scatter 能量小于 target 总能量或报告给出能量比。

---

## 4. 修复任务 C：频率分辨率与 FDA law 真实验收

### 4.1 目标

让 real-run V1 能区分两类证据：

1. 配置证据：input/stdout/metadata 中的 Tx center frequency；
2. 频谱证据：FFT 后 source spectra 的峰值或中心频率估计。

### 4.2 需要新增的诊断量

在 processing summary 和 report 中写入：

```text
fft_bin_spacing_hz
fda_delta_f_hz
fft_resolution_ratio = fft_bin_spacing_hz / fda_delta_f_hz
can_resolve_fda_step_by_fft = fft_bin_spacing_hz <= fda_delta_f_hz / q
```

建议默认 `q=2` 或 `q=5`。

### 4.3 real-run V1 判据

V1 不应仅依赖 FFT peak。建议分层判据：

- `PASS-CONFIG`: rendered input 和 run stdout 中 center frequencies 符合 FDA law；
- `PASS-SPECTRAL`: processed source spectra 的估计频率也能分辨 FDA step；
- `WARNING-SPECTRAL-UNRESOLVED`: 配置正确，但 FFT 分辨率不足以分辨 FDA step；
- `FAIL`: input/stdout/metadata 中 center frequencies 不符合 FDA law。

当前 runs 应给出：

```text
V1: PASS-CONFIG, WARNING-SPECTRAL-UNRESOLVED
```

不要把这种情况误判为 FDA 失败。

### 4.4 推荐修改 minimal scene

为真实物理验收新增一个更稳妥配置，例如：

```text
examples/minimal_fda_mimo_scene_long_window.yaml
```

建议：

- `time_window >= 100 ns`；
- `dx <= 0.005 m`，或降低频率范围；
- `rx_offset` 与网格对齐，例如 `0.01 m`，或者网格也设为 `0.005 m`。

保留原 minimal scene 作为 quick smoke test，不要用它做严肃相位/频率验收。

---

## 5. 修复任务 D：数值色散与 gprMax stdout 解析

### 5.1 目标

自动读取每个 `logs/gprmax_stdout_tx_*.txt`，提取 gprMax 版本、网格、时间窗、迭代数、材料、source frequency、numerical dispersion warnings 等信息，形成机器可读诊断摘要。

### 5.2 新增模块建议

增加：

```text
src/fda_mimo_gprmax/log_analysis.py
```

核心函数：

```python
def parse_gprmax_stdout(path: Path) -> GprMaxStdoutSummary: ...
def collect_run_log_summaries(logs_dir: Path) -> list[GprMaxStdoutSummary]: ...
def summarize_numerical_dispersion(summaries) -> DispersionSummary: ...
```

推荐数据结构：

```python
@dataclass
class GprMaxStdoutSummary:
    tx_index: int
    gprmax_version: str | None
    domain_size: tuple[float, float, float] | None
    grid_cells: tuple[int, int, int] | None
    spatial_step: tuple[float, float, float] | None
    time_window_s: float | None
    iterations: int | None
    waveform_frequency_hz: float | None
    warnings: list[str]
    numerical_dispersion_warning: bool
    max_phase_velocity_error_percent: float | None
```

### 5.3 风险等级

建议在诊断报告中按如下规则标注：

```text
abs(max_phase_velocity_error_percent) < 2%       -> LOW
2% <= error < 5%                                 -> MODERATE
5% <= error < 10%                                -> HIGH
>= 10%                                           -> SEVERE
```

当前 runs 约 `7–8%`，应标注为 `HIGH`。

### 5.4 验收标准

新增测试：

```text
tests/test_log_analysis.py
```

覆盖：

1. 能从当前 stdout 样式中提取 gprMax version；
2. 能提取 Tx waveform frequency；
3. 能识别 numerical dispersion warning；
4. 能给出 risk level；
5. 空日志或不完整日志不崩溃，而返回 warning。

---

## 6. 修复任务 E：真实 runs 诊断命令 / skill-like 能力

### 6.1 目标

增加一个命令，可以直接读取 `runs/<scene>/` 下的真实产物，输出类似人工审阅的诊断报告。该能力不应只打印 JSON，而应生成：

```text
runs/<scene>/diagnostics/run_analysis_report.md
runs/<scene>/diagnostics/run_analysis_summary.json
runs/<scene>/diagnostics/tables/*.csv
runs/<scene>/diagnostics/figures/*.png
```

### 6.2 CLI 设计

建议增加命令：

```bash
fda-mimo-gprmax inspect-run runs/scene_001_minimal
```

可选参数：

```bash
fda-mimo-gprmax inspect-run runs/scene_001_minimal --variants target,background --with-scatter
fda-mimo-gprmax inspect-run runs/scene_001_minimal --paper-mode
fda-mimo-gprmax inspect-run runs/scene_001_minimal --output runs/scene_001_minimal/diagnostics
```

如果更希望统一为 `diagnose`：

```bash
fda-mimo-gprmax diagnose-run runs/scene_001_minimal
```

命名二选一，建议 `inspect-run`，因为它强调读取产物、解释产物、生成报告。

### 6.3 报告内容要求

报告至少包含以下章节。

#### 6.3.1 Run overview

- scene name；
- variants present；
- target/background/scatter 是否完整；
- gprMax 是否真实运行或 dry-run；
- Tx 数、Rx 数、time samples、frequency bins；
- HDF5/NPZ 是否存在；
- raw `.out` 文件数量与 checksum 状态。

#### 6.3.2 FDA scheduling evidence

- 从 config/input/stdout/metadata 收集的 Tx center frequencies；
- 与 FDA law 的误差；
- FFT spectral peak 是否能分辨；
- FFT bin spacing 与 FDA step ratio；
- 判据：`PASS-CONFIG`, `PASS-SPECTRAL`, `WARNING-SPECTRAL-UNRESOLVED`, `FAIL`。

#### 6.3.3 MIMO tensor evidence

- `Y_t` 和 `Y_f` shape；
- 通道能量矩阵 `E[m,n]`；
- 峰值到达时间矩阵 `T_peak[m,n]`；
- 通道是否非空、是否存在复制通道、是否有 NaN；
- 对角/非对角能量比。

#### 6.3.4 GPR physical evidence

- material table；
- domain/grid/time window；
- target information；
- numerical dispersion warnings；
- early-time coupling 是否支配；
- 是否存在 background/scatter 数据。

#### 6.3.5 Coordinate consistency

- requested vs actual Tx/Rx positions；
- 最大坐标偏差；
- 是否发生网格量化；
- Rx offset 是否低于 grid spacing；
- 坐标一致性判据。

#### 6.3.6 Source normalization and valid-band mask

- source spectra shape；
- valid fraction；
- NaN count in calibrated tensor；
- invalid bins list；
- 是否应要求 downstream algorithms 使用 valid mask。

#### 6.3.7 Target/background/scatter status

- target 是否完整；
- background 是否完整；
- scatter 是否存在；
- 若不存在，给出下一步命令；
- 若存在，给出能量比：

```math
\rho_{scat/target}=\frac{\|Y_{scat}\|_F}{\|Y_{target}\|_F}
```

#### 6.3.8 Decision and next actions

给出分级结论：

```text
ACCEPTED_FOR_ENGINEERING_SMOKE
ACCEPTED_FOR_REAL_FULLWAVE_TARGET_SNAPSHOT
ACCEPTED_FOR_TARGET_BACKGROUND_SCATTER
ACCEPTED_FOR_STAGE1_REAL_VALIDATION
NOT_ACCEPTED
```

当前 runs 应大致判为：

```text
ACCEPTED_FOR_REAL_FULLWAVE_TARGET_SNAPSHOT
```

但不应判为：

```text
ACCEPTED_FOR_TARGET_BACKGROUND_SCATTER
ACCEPTED_FOR_STAGE1_REAL_VALIDATION
```

### 6.4 JSON summary schema

`run_analysis_summary.json` 应至少包含：

```json
{
  "scene": "scene_001_minimal",
  "decision": "ACCEPTED_FOR_REAL_FULLWAVE_TARGET_SNAPSHOT",
  "variants": {
    "target": { "has_raw": true, "has_processed": true, "run_stage": "real" },
    "background": {
      "has_raw": false,
      "has_processed": false,
      "run_stage": "dry-run"
    }
  },
  "tensor": {
    "time_traces_shape": [4, 4, 313],
    "frequency_tensor_raw_shape": [4, 4, 19],
    "frequency_tensor_cal_shape": [4, 4, 19],
    "nan_count_cal": 16
  },
  "fda": {
    "configured_center_frequencies_hz": [1.0e9, 1.025e9, 1.05e9, 1.075e9],
    "delta_f_hz": 25e6,
    "fft_bin_spacing_hz": 165.9e6,
    "spectral_resolution_status": "WARNING_UNRESOLVED"
  },
  "coordinates": {
    "actual_positions_available": true,
    "max_requested_actual_rx_error_m": 0.005,
    "grid_quantization_warning": true
  },
  "numerical_dispersion": {
    "warning": true,
    "risk": "HIGH",
    "max_abs_phase_velocity_error_percent": 8.27
  },
  "recommended_next_actions": [
    "run background variant",
    "generate scatter snapshot",
    "increase time_window",
    "align rx_offset with grid or reduce grid spacing"
  ]
}
```

### 6.5 诊断图建议

新增或复用：

```text
diagnostics/figures/channel_energy_matrix.png
diagnostics/figures/peak_time_matrix.png
diagnostics/figures/fda_source_centers.png
diagnostics/figures/requested_vs_actual_geometry.png
diagnostics/figures/source_spectra_with_fft_bins.png
diagnostics/figures/valid_band_mask.png
diagnostics/figures/target_background_scatter_energy.png    # 若 scatter 存在
```

不要使用 seaborn。使用 matplotlib。每张图独立生成，不使用 subplot。

### 6.6 测试要求

新增：

```text
tests/test_inspect_run.py
```

覆盖：

1. 对 mock run directory 可生成 report；
2. target 完整、background dry-run 时 decision 正确；
3. 缺少 processed snapshot 时能诊断而不崩溃；
4. requested/actual 坐标偏差能进入 JSON；
5. numerical dispersion warning 能进入 JSON；
6. paper-mode 下要求更严格。

---

## 7. 修复任务 F：真实 V1–V4 / V1–V8 验收迁移

### 7.1 目标

把 `output/protocol/theory_protocol_latest/` 中的 synthetic V1–V8 与真实 `runs/` 产物区分开。新增 real-run protocol analysis。

### 7.2 CLI 建议

保留现有：

```bash
fda-mimo-gprmax protocol analyze examples/minimal_fda_mimo_scene.yaml --output-root output/protocol/latest
```

增加：

```bash
fda-mimo-gprmax protocol-real runs/scene_001_minimal --checks V1,V2,V3,V4
```

或者在现有 protocol 命令中加入：

```bash
fda-mimo-gprmax protocol report --from-run runs/scene_001_minimal --checks V1,V2,V3,V4
```

若改动 CLI 成本较高，可先通过 `inspect-run --paper-mode` 实现，后续再并入 protocol。

### 7.3 real-run checks 最小集

当前真实产物优先支持 V1–V4：

- V1 Source FDA law check；
- V2 Tensor integrity check；
- V3 MIMO geometry check；
- V4 GPR medium/run physical sanity check。

V5–V8 需要更多数据：

- V5 FDA degeneracy check 需要 `Δf=0` 对照真实运行；
- V6 Depth/frequency coupling 需要不同目标深度真实运行；
- V7 Dictionary non-equivalence 需要候选点或多位置响应数据；
- V8 Random-medium covariance 需要多个随机介质场景。

报告中必须明确：当前 runs 只能支持 V1–V4 的真实验收，不要把 synthetic V1–V8 误写为 real full-wave V1–V8。

---

## 8. 全量测试矩阵

完成上述修复后，必须运行完整测试。测试分为五层。

### 8.1 静态与单元测试

```bash
python -m pytest -q
```

若未安装包：

```bash
PYTHONPATH=src python -m pytest -q
```

推荐安装：

```bash
python -m pip install -e '.[test]'
python -m pytest -q
```

要求：所有非 integration tests 通过。

### 8.2 CLI smoke tests

```bash
fda-mimo-gprmax validate examples/minimal_fda_mimo_scene.yaml
fda-mimo-gprmax render examples/minimal_fda_mimo_scene.yaml --variant target --run-dir runs/smoke_scene
fda-mimo-gprmax run examples/minimal_fda_mimo_scene.yaml --variant target --run-dir runs/smoke_scene --dry-run
fda-mimo-gprmax evidence examples/minimal_fda_mimo_scene.yaml --output-dir output/evidence/latest --overwrite
```

要求：命令返回 0；输出 JSON `ok=true` 或 suite passed。

### 8.3 gprMax real smoke test

在 gprMax 已安装环境下运行：

```bash
fda-mimo-gprmax workflow examples/minimal_fda_mimo_scene.yaml --variant target --run-dir runs/real_smoke --timeout 120
fda-mimo-gprmax inspect-run runs/real_smoke
```

要求：

- raw `.out` 数量等于 `Nt`；
- processed `snapshot.h5` 存在；
- decision 至少为 `ACCEPTED_FOR_REAL_FULLWAVE_TARGET_SNAPSHOT`；
- 若 FFT 分辨率不足，应报告 warning 而不是 fail。

### 8.4 target/background/scatter integration test

```bash
fda-mimo-gprmax workflow examples/minimal_fda_mimo_scene.yaml --variant target --run-dir runs/pair_smoke --timeout 120
fda-mimo-gprmax workflow examples/minimal_fda_mimo_scene.yaml --variant background --run-dir runs/pair_smoke --timeout 120
fda-mimo-gprmax subtract examples/minimal_fda_mimo_scene.yaml --run-dir runs/pair_smoke
fda-mimo-gprmax inspect-run runs/pair_smoke --with-scatter
```

要求：

- target/background/scatter 三者完整；
- scatter HDF5 存在；
- target/background axes 一致；
- decision 至少为 `ACCEPTED_FOR_TARGET_BACKGROUND_SCATTER`。

### 8.5 长时窗/细网格物理验收

新增一个更适合物理验收的场景，例如：

```text
examples/minimal_fda_mimo_scene_long_window.yaml
```

运行：

```bash
fda-mimo-gprmax workflow examples/minimal_fda_mimo_scene_long_window.yaml --variant target --run-dir runs/long_window_target --timeout 600
fda-mimo-gprmax inspect-run runs/long_window_target --paper-mode
```

要求：

- FFT bin spacing 足以分辨 FDA step 或报告接近可分辨；
- 数值色散风险降低到 MODERATE 或 LOW；
- requested/actual 坐标偏差可接受；
- real-run V1–V4 通过。

---

## 9. 文档更新要求

修改或新增以下文档：

```text
docs/real_run_diagnostics.md
docs/testing.md
docs/validation.md
docs/schema.md
docs/Design.md
README.md
```

### 9.1 README 必须增加

- 快速运行 target 的命令；
- target/background/scatter 成对运行命令；
- inspect-run 命令；
- 当前体制边界：理想收发共址 TDM，不包含真实 T/R switch、相噪、互耦、硬件校准误差；
- 如何解释 `PASS-CONFIG` 与 `WARNING-SPECTRAL-UNRESOLVED`。

### 9.2 schema.md 必须增加

- requested vs actual positions；
- scatter snapshot schema；
- log analysis summary schema；
- run diagnosis summary schema。

### 9.3 validation.md 必须区分

- synthetic validation；
- real gprMax smoke validation；
- target/background/scatter validation；
- real-run Stage-1 validation。

不要把 synthetic V1–V8 与 real full-wave V1–V8 混写。

---

## 10. 最终交付物

完成任务后，agent 应交付：

1. 修改后的源码；
2. 新增测试；
3. 更新文档；
4. 一份新的真实运行输出，例如：

```text
runs/scene_001_minimal_fixed/
  target/
  background/
  scatter/
  diagnostics/
```

5. 一份测试报告：

```text
output/test_reports/full_test_report.md
```

报告至少列出：

- pytest 结果；
- CLI smoke 结果；
- gprMax real smoke 结果；
- target/background/scatter 结果；
- inspect-run decision；
- 当前仍存在的 warning；
- 是否达到下一阶段可用门槛。

---

## 11. 验收门槛

满足以下条件即可认为本轮增强成功：

- `pytest -q` 通过；
- target real gprMax workflow 成功；
- background real gprMax workflow 成功；
- scatter snapshot 生成成功；
- requested/actual 坐标均保存；
- inspect-run 能生成 Markdown 与 JSON 报告；
- 报告能正确指出 FFT 分辨率、数值色散、坐标量化等 warning；
- synthetic protocol 与 real-run diagnosis 在文档和输出中被明确区分。
- 数值色散风险不高于 MODERATE；
- FFT bin spacing 足以解释 FDA step，或报告采用更合理的中心频率证据；
- target/background/scatter 完整；
- actual Tx/Rx geometry 与 requested geometry 偏差受控；
- real-run V1–V4 通过；
- 至少一个 `Δf=0` real baseline 和一个 `Δf≠0` real FDA case 可用于 V5；
- 报告中不得声称当前实现覆盖真实硬件互耦、相噪或 T/R switch。

---

## 12. 推荐实现顺序

严格按以下顺序执行，避免同时改动过多导致定位困难：

1. 增加 actual coordinate parsing 与 HDF5 serialization；
2. 增加 log/stdout analysis；
3. 增加 inspect-run 命令，先只支持 target；
4. 增加 background workflow 与 subtract 命令；
5. 扩展 inspect-run 支持 target/background/scatter；
6. 修改 V1 real-run 判据，区分 configured FDA law 与 spectral resolvability；
7. 新增长时窗或细网格 example；
8. 扩展 tests；
9. 更新 docs；
10. 跑完整测试矩阵并生成 final test report。

每一步都应保持已有测试通过。

---

## 13. 给 agent 的最终执行提示

请不要把本任务理解为“继续美化工程”。本轮目标是把工程从“能生成 target 快拍”推进到“能被审阅、复核、诊断的真实 gprMax FDA-MIMO-GPR 数据生成工具”。核心不是增加更多场景，而是让每个产物都可追溯、可解释、可诊断。

尤其注意三条红线：

1. 不要把 requested geometry 当作 actual geometry；
2. 不要把 synthetic V1–V8 报告当作真实 gprMax 验收；
3. 不要忽略数值色散、FFT 分辨率和背景扣除状态。

最终输出应允许用户执行：

```bash
fda-mimo-gprmax workflow examples/minimal_fda_mimo_scene.yaml --variant target
fda-mimo-gprmax workflow examples/minimal_fda_mimo_scene.yaml --variant background
fda-mimo-gprmax subtract examples/minimal_fda_mimo_scene.yaml
fda-mimo-gprmax inspect-run runs/scene_001_minimal --with-scatter
```

并获得一份能够直接解释如下问题的报告：

- gprMax 是否真实运行；
- FDA law 是否进入源波形；
- MIMO 通道张量是否完整；
- 地下介质和目标是否进入仿真；
- requested/actual 坐标是否一致；
- background/scatter 是否完整；
- 频率分辨率是否足以观察 FDA step；
- 数值色散风险是否可接受；
- 当前结果可支持哪一层结论，不能支持哪一层结论。
