# FDA-MIMO-GPR Compatibility Layer API Reference

本文档概述当前项目的核心 API，并重点说明结构化 Cole--Cole 介质兼容层。

## 1. 入口点

CLI:

```bash
fda-mimo-gprmax validate <scenario.yaml>
fda-mimo-gprmax render <scenario.yaml> --variant target
fda-mimo-gprmax workflow <scenario.yaml> --dry-run
```

Python:

```python
from fda_mimo_gprmax import load_scenario, ScenarioConfig, ValidationError
```

## 2. 场景配置 API

`fda_mimo_gprmax.config` 提供：

- `load_scenario(path) -> ScenarioConfig`
- `ScenarioConfig.normalized_dict()`
- `ScenarioConfig.metadata()`
- `ScenarioConfig.checksum()`

主要配置对象包括 `DomainConfig`、`GridConfig`、`TimeConfig`、`ArrayConfig`、`FDAConfig`、`WaveformConfig`、`ReceiverConfig`、`SceneConfig`、`ExecutionConfig`、`ProcessingConfig`、`MediaConfig`。

## 3. Cole--Cole 结构化介质 API

模块：`fda_mimo_gprmax.media`

### 3.1 物理模型

结构化介质使用 Cole--Cole 五参数复相对介电常数：

```text
eps_r(f) = eps_inf
         + (eps_s - eps_inf) / (1 + (j 2 pi f tau) ** (1 - alpha))
         + sigma / (j 2 pi f epsilon_0)
```

字段含义：

- `eps_s`：静态相对介电常数；
- `eps_inf`：高频极限相对介电常数；
- `tau`：特征弛豫时间，单位 s；
- `alpha`：Cole--Cole 展宽因子，满足 `0 <= alpha < 1`；
- `sigma`：直流电导率，单位 S/m。

### 3.2 核心对象

```python
from fda_mimo_gprmax.media import (
    ColeColeMedium,
    DebyeApproximation,
    cole_cole_complex_permittivity,
    debye_complex_permittivity,
    complex_wavenumber_from_epsilon,
    fit_cole_cole_to_debye,
    render_debye_material_commands,
    DEFAULT_COLE_COLE_CATALOG,
)
```

| 对象 | 说明 |
|---|---|
| `ColeColeMedium` | 不可变 Cole--Cole 物理介质定义 |
| `DebyeApproximation` | 不可变 multi-pole Debye 近似结果 |
| `cole_cole_complex_permittivity()` | 计算 Cole--Cole 复相对介电常数 |
| `debye_complex_permittivity()` | 计算 Debye 近似复相对介电常数 |
| `complex_wavenumber_from_epsilon()` | 由相对介电常数计算复波数 |
| `fit_cole_cole_to_debye()` | 将 Cole--Cole 弛豫项拟合为 Debye poles |
| `render_debye_material_commands()` | 生成 gprMax 可执行的材料命令 |
| `DEFAULT_COLE_COLE_CATALOG` | 内置 `S1`--`S5` 介质 catalog |

### 3.3 YAML 输入格式

显式 Cole--Cole 定义：

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
```

Catalog 定义：

```yaml
media:
  use_default_catalog: true
  materials:
    soil:
      from_catalog: S1
```

YAML 显式字段会覆盖 catalog 默认值。结构化介质 ID 采用 YAML key，例如 `soil`。

### 3.4 gprMax 命令渲染

兼容层不会向 gprMax 写入非原生命令，例如 `#cole_cole`。它会把 Cole--Cole 物理模型拟合为 multi-pole Debye，并渲染为：

```text
#material: <eps_inf> <sigma> 1 0 <material_id>
#add_dispersion_debye: <n> <delta_eps_1> <tau_1> ... <delta_eps_n> <tau_n> <material_id>
```

这些结构化介质命令会出现在 raw `scene.materials` 和几何命令之前。

### 3.5 元数据约定

`ScenarioConfig.normalized_dict()`、`run_manifest.json`、`snapshot.h5` 的 `/metadata/config` 与 `/metadata/media` 会保留：

- `source_model: cole_cole`
- `approximation_model: multi_pole_debye`
- 原始 Cole--Cole 参数；
- Debye pole 参数；
- 拟合频率范围与频点数；
- `max_rel_error`、`rms_rel_error`；
- warning/failure 阈值与 `allow_poor_fit`。

物理解释、论文表述和数据说明应以原始 Cole--Cole 参数为准；Debye poles 只是 gprMax 执行近似。

## 4. 渲染与运行 API

`fda_mimo_gprmax.rendering`:

- `render_scenario_inputs(scenario, variant_name=None, run_dir=None) -> RenderPlan`
- `render_input_text(scenario, variant, tx_index, config_dir)`
- `render_structured_media_commands(scenario)`

`fda_mimo_gprmax.running`:

- `build_command_plan()`
- `run_command()`
- `run_plan()`
- `write_manifest()`

## 5. 处理与序列化 API

`fda_mimo_gprmax.parsing`:

- `inspect_output()`
- `extract_component()`
- `parse_tx_outputs()`

`fda_mimo_gprmax.processing`:

- `assemble_time_tensor()`
- `frequency_transform()`
- `make_snapshot()`
- `subtract_background()`

`fda_mimo_gprmax.serialization`:

- `write_snapshot_h5()`
- `write_snapshot_npz()`
- `write_processed_snapshot()`

`fda_mimo_gprmax.subtraction`:

- `subtract_snapshots()`
- `subtract_scene_run()`

## 6. 输出张量形状

- `/snapshot/time_traces`: `[Nt, Nr, Lt]`
- `/snapshot/frequency_tensor_raw`: `[Nt, Nr, Kf]`
- `/snapshot/frequency_tensor_cal`: `[Nt, Nr, Kf]`，可选
- `/snapshot/source_spectra`: `[Nt, Kf]`
- `/snapshot/valid_band_mask`: `[Nt, Kf]`

## 7. 兼容性说明

旧式 raw gprMax material 命令仍完全可用：

```yaml
scene:
  materials:
    - "#material: 6 0.01 1 0 soil"
```

如果结构化 `media.materials.soil` 与 raw `#material: ... soil` 同时出现，兼容层会拒绝该场景，避免重复定义 gprMax 材料 ID。
