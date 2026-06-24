# FDA-MIMO-GPR gprMax Compatibility Layer — API Reference

> 本文档详细说明 `fda-mimo-gprmax` 包提供的 Python API、CLI 命令、场景 YAML 输入格式、内部模块职责以及核心数据流。重点关注兼容层的设计目的——在不修改 gprMax 源码的前提下，为其叠加 TDM FDA-MIMO-GPR 快照生成能力。

---

## 目录

1. [概述与设计理念](#1-概述与设计理念)
2. [安装与入口点](#2-安装与入口点)
3. [场景 YAML 输入格式](#3-场景-yaml-输入格式)
4. [CLI 命令参考](#4-cli-命令参考)
5. [Python API 模块参考](#5-python-api-模块参考)
6. [核心数据结构](#6-核心数据结构)
7. [输出产物格式](#7-输出产物格式)
8. [验证与协议体系](#8-验证与协议体系)
9. [兼容层的作用与设计边界](#9-兼容层的作用与设计边界)
10. [Cole--Cole 结构化介质 API](#10-cole-cole-结构化介质-api)

---

## 1. 概述与设计理念

### 1.1 核心问题

gprMax 是一个通用的 FDTD 全波电磁模拟器，本身**不**原生支持以下 FDA-MIMO-GPR 场景构建需求：

- **TDM-MIMO**：时分复用多输入多输出，同一时刻仅一个发射天线（Tx）激活，所有接收天线（Rx）同时记录
- **FDA（Frequency Diverse Array）**：每个 Tx 通道绑定一个不同的载波中心频率，形成频率分集
- **批量建模**：需要为每个激活的 Tx 生成一个独立的 gprMax 输入文件，并统一管理输出
- **通道张量构建**：将 gprMax 的逐 Tx 原始 HDF5 输出拼接为统一的多维张量

### 1.2 兼容层的设计原则

| 原则 | 说明 |
|------|------|
| **零侵入** | 不修改 gprMax 源码、不 monkey-patch、不包装 gprMax Python 类 |
| **文件级代理** | 输入层：注入 gprMax `.in` 文件内容；输出层：解析 gprMax 的 HDF5 `.out` 文件 |
| **显式管道** | 每一阶段（验证 → 渲染 → 执行 → 解析 → 处理 → 导出）为独立 CLI 子命令或 API 调用 |
| **安全默认** | 默认不执行真实 gprMax；`--dry-run` 和 `--geometry-only` 保护用户 |

### 1.3 高层数据流

```
scene.yaml
    │
    ▼
┌──────────────────────────┐
│  validate / load_scenario │  ←  YAML 语法语义验证
└──────────────────────────┘
    │
    ▼
┌──────────────────────────┐
│  render_scenario_inputs   │  ←  Nt 个 .in 文件（每 Tx 一个）
└──────────────────────────┘
    │
    ▼
┌──────────────────────────┐
│  run_plan / gprMax        │  ←  gprMax 全波 FDTD（可选）
└──────────────────────────┘
    │
    ▼
┌──────────────────────────┐
│  parse_tx_outputs         │  ←  HDF5 → TxTrace 列表
└──────────────────────────┘
    │
    ▼
┌──────────────────────────┐
│  make_snapshot            │  ←  [Nt, Nr, Lt]/[Nt, Nr, Kf] 张量
└──────────────────────────┘
    │                              ┌───────────────────────┐
    ├──→ write_processed_snapshot  →  snapshot.h5 / .npz
    ├──→ write_diagnostics         →  诊断图片 + JSON 摘要
    └──→ subtract_background       →  散射张量
```

---

## 2. 安装与入口点

### 2.1 安装

```bash
conda activate fda-mimo-gprMax
uv pip install -e '.[test]'
```

### 2.2 CLI 入口

```bash
fda-mimo-gprmax <command> [options]
```

注册于 `pyproject.toml`:

```toml
[project.scripts]
fda-mimo-gprmax = "fda_mimo_gprmax.cli:main"
```

### 2.3 Python 包入口

```python
from fda_mimo_gprmax import ScenarioConfig, ValidationError, load_scenario
```

### 2.4 依赖

| 依赖 | 用途 |
|------|------|
| `numpy>=1.24` | 张量运算、FFT |
| `h5py>=3.8` | gprMax HDF5 输出读写 |
| `PyYAML>=6.0` | 场景 YAML 解析 |
| `matplotlib>=3.7` | 诊断图生成 |
| `zarr>=2.16`（可选） | Zarr 格式导出（预留） |

---

## 3. 场景 YAML 输入格式

### 3.1 顶层结构

```yaml
name: scene_001_minimal
random_seed: 20260606
output:
  root: ../runs
  export_npz: true
  diagnostics: true
  valid_band_threshold: 0.001
  eta: 1.0e-12
  frequency_range: [0.0, 3.0e9]
  window: hann

domain:
  size: [0.60, 0.40, 0.30]
grid:
  spacing: [0.01, 0.01, 0.01]
time:
  window: 6.0e-9

scene:
  title: Minimal co-platform TDM FDA-MIMO-GPR scene
  materials:
    - "#material: 6 0.01 1 0 soil"
  geometry:
    - "#box: 0 0 0 0.60 0.40 0.14 soil"
  geometry_view: true

array:
  mode: offset
  rx_offset: [0.005, 0.0, 0.0]
  polarization: z
  tx_positions:
    - [0.22, 0.16, 0.15]
    - [0.26, 0.16, 0.15]
    - [0.30, 0.16, 0.15]
    - [0.34, 0.16, 0.15]

fda:
  type: linear
  f0: 1.0e9
  df: 2.5e7

waveform:
  mode: builtin
  shape: ricker
  amplitude: 1.0
  identifier_prefix: fda_ricker

receiver:
  component: Ez

variants:
  target:
    geometry:
      - "#sphere: 0.30 0.20 0.08 0.025 pec"
  background:
    geometry: []

execution:
  executable: ["python", "-m", "gprMax"]
  omp_threads: 4
  failure_policy: stop
```

### 3.2 字段详解

#### `domain` — FDTD 仿真域

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `size` | `[float, float, float]` | 是 | 域尺寸 `[x, y, z]`，单位 m，所有值 > 0 |

渲染为 gprMax 命令：`#domain: x y z`

#### `grid` — FDTD 网格离散

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `spacing` | `[float, float, float]` | 是 | 网格间距 `[dx, dy, dz]`，单位 m，所有值 > 0 |

渲染为：`#dx_dy_dz: dx dy dz`

#### `time` — 时间窗

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `window` | `float` | 是 | 仿真时间窗，单位 s，> 0 |

渲染为：`#time_window: T`

#### `array` — 天线阵列配置

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `mode` | `str` | 否（默认 `"explicit"`） | 阵列模式，见下文 |
| `tx_positions` | `[[float,float,float], ...]` | 是 | Tx 位置列表，`[Nt, 3]` |
| `rx_positions` | `[[float,float,float], ...]` | mode=explicit 时必需 | Rx 位置列表，`[Nr, 3]` |
| `rx_offset` | `[float,float,float]` | 否（默认 `[0,0,0]`） | mode=offset 时 Rx = Tx + offset |
| `polarization` | `str` | 否（默认 `"z"`） | 偶极子极化方向 `x`/`y`/`z` |

**mode 取值：**

| mode | 行为 |
|------|------|
| `"explicit"`（默认） | 独立指定 `tx_positions` 和 `rx_positions` |
| `"strict"` / `"strict-colocated"` | `rx_positions` 复制自 `tx_positions`，严格共址 |
| `"offset"` / `"near"` / `"near-colocated"` | `rx_positions = tx_positions + rx_offset`，近共址 |

**属性：**
- `Nt` — Tx 数量
- `Nr` — Rx 数量

#### `fda` — 频率分集阵列配置

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `type` / `kind` | `str` | 是 | `"linear"` 或 `"explicit"` / `"list"` |
| `f0` | `float` | linear 模式必需 | 起始频率，Hz |
| `df` | `float` | 否（默认 0） | 频率步进，Hz |
| `frequencies` | `[float, ...]` | explicit 模式必需 | 显式频率列表，长度必须等于 Nt |

**linear 模式**：`f_m = f0 + m * df`，`m = 0, 1, ..., Nt-1`

#### `waveform` — 源波形

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `mode` | `str` | 否（默认 `"builtin"`） | `"builtin"` 或 `"excitation_file"` |
| `shape` | `str` | 否（默认 `"ricker"`） | 波形形状：`ricker`/`gaussian`/`gaussiandot`/`sine` 等 |
| `amplitude` | `float` | 否（默认 1.0） | 幅度 |
| `identifier_prefix` | `str` | 否（默认 `"fda_src"`） | gprMax 波形标识符前缀 |
| `samples` | `[float, ...]` | excitation_file 模式必需 | 自定义波形采样 |
| `time` | `[float, ...]` | 否 | 采样时间轴 |

**builtin 模式渲染为：** `#waveform: shape amplitude frequency waveform_id`

**excitation_file 模式：** 为每个 Tx 写入独立的 `.txt` 文件，以 `#excitation_file:` 引用

波形 ID 格式：`{prefix}_{tx_index:03d}`（例如 `fda_ricker_000`）

#### `receiver` — 接收机配置

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `component` | `str` | 否（默认 `"Ez"`） | 记录分量：`Ex`/`Ey`/`Ez`/`Hx`/`Hy`/`Hz`/`Ix`/`Iy`/`Iz` |

#### `scene` — 场景描述

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `title` | `str` | 否 | 标题文本 |
| `materials` | `[str, ...]` | 否 | gprMax `#material` 命令列表 |
| `geometry` | `[str, ...]` | 否 | 所有变体共享的 gprMax 几何命令 |
| `geometry_view` | `bool` | 否（默认 false） | 是否生成 `#geometry_view` 命令 |

#### `variants` — 场景变体

```yaml
variants:
  target:
    geometry:
      - "#sphere: 0.30 0.20 0.08 0.025 pec"
  background:
    geometry: []
```

每个变体在渲染时将其 `geometry` 追加到共享的 `scene.geometry` 之后。变体名称用于目录命名。

支持两种语法：
- **映射语法**（如上）：`{name: {geometry: [...], ...}}`
- **列表语法**：`[{name: "target", geometry: [...]}]`

至少需要一个变体。

#### `execution` — gprMax 执行配置

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `executable` | `[str, ...]` | 否（默认 `["python", "-m", "gprMax"]`） | gprMax 可执行命令 |
| `extra_args` | `[str, ...]` | 否 | 额外命令行参数 |
| `gpu` | `[int, ...]` | 否 | GPU 设备列表 |
| `mpi` | `int`/`null` | 否 | MPI 进程数 |
| `omp_threads` | `int`/`null` | 否 | OMP 线程数 |
| `failure_policy` | `str` | 否（默认 `"stop"`） | `"stop"`（首失败停止）或 `"continue"` |

#### `output` — 输出配置

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `root` | `str` | 否（默认 `"runs"`） | 输出根目录 |
| `export_npz` | `bool` | 否（默认 true） | 同时导出 NPZ |
| `diagnostics` | `bool` | 否（默认 true） | 生成诊断图 |
| `valid_band_threshold` | `float` | 否（默认 1e-3） | 有效频带阈值（相对于源谱峰值） |
| `eta` | `float` | 否（默认 1e-12） | 归一化防零除参数 |
| `frequency_range` | `[float, float]`/`null` | 否 | FFT 频率范围 `[f_min, f_max]` |
| `window` | `str` | 否（默认 `"none"`） | FFT 窗函数：`none`/`rect`/`rectangular`/`hann`/`hamming` |

#### `media` — 结构化介质配置（可选）

`media` 用于在兼容层中声明非 gprMax 原生的物理介质模型。当前支持 `model: cole_cole`。兼容层会将 Cole--Cole 五参数物理模型确定性拟合为 gprMax 可执行的 multi-pole Debye 命令；旧式 `scene.materials` raw 字符串仍完全可用。

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

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `fit.n_poles` | `int` | 否（默认 12） | Debye 近似极点数 |
| `fit.frequency_min` | `float`/`null` | 否 | 拟合频带下限，Hz；缺省时由输出频带/FDA 频率推断 |
| `fit.frequency_max` | `float`/`null` | 否 | 拟合频带上限，Hz；缺省时由输出频带/FDA 频率推断 |
| `fit.num_frequencies` | `int` | 否（默认 256） | 拟合频点数量，采用对数均匀采样 |
| `fit.max_rel_error_warn` | `float` | 否（默认 0.05） | 最大相对误差 warning 阈值 |
| `fit.max_rel_error_fail` | `float` | 否（默认 0.15） | 最大相对误差 failure 阈值 |
| `fit.allow_poor_fit` | `bool` | 否（默认 false） | 是否允许超过 failure 阈值的近似继续渲染 |
| `materials.<id>.model` | `str` | 显式定义时是 | 当前为 `cole_cole` |
| `materials.<id>.eps_s` | `float` | 是 | 静态相对介电常数，`> 0` |
| `materials.<id>.eps_inf` | `float` | 是 | 高频极限相对介电常数，`> 0` 且 `eps_s >= eps_inf` |
| `materials.<id>.tau` | `float` | 是 | 特征弛豫时间，单位 s，`> 0` |
| `materials.<id>.alpha` | `float` | 是 | Cole--Cole 展宽因子，`0 <= alpha < 1` |
| `materials.<id>.sigma` | `float` | 否（默认 0） | 直流电导率，单位 S/m，`>= 0` |
| `materials.<id>.source` | `str` | 否 | 参数来源说明，进入 metadata |
| `materials.<id>.role` | `str` | 否 | 实验角色说明，进入 metadata |

也可以启用内置 catalog：

```yaml
media:
  use_default_catalog: true
  materials:
    soil:
      from_catalog: S1
```

Catalog keys 为 `S1`--`S5`，YAML 显式字段会覆盖 catalog 默认值。结构化介质 ID 采用 YAML key，例如 `soil`。如果 `media.materials.soil` 与 `scene.materials` 中的 raw `#material: ... soil` 同时出现，兼容层会拒绝该场景，以避免重复定义 gprMax 材料。

---

## 4. CLI 命令参考

### 4.1 `validate`

验证场景 YAML，返回 JSON。

```bash
fda-mimo-gprmax validate <scenario.yaml>
```

输出：

```json
{
  "ok": true,
  "name": "scene_001_minimal",
  "nt": 4,
  "nr": 4,
  "checksum": "abc123..."
}
```

错误退出码：`1`

### 4.2 `render`

渲染 gprMax 输入文件，不执行 gprMax。

```bash
fda-mimo-gprmax render <scenario.yaml> \
  --variant target
  --run-dir /path/to/run
  --geometry-only
```

在 `--run-dir/<variant>/config/` 下生成 `generated_tx_???.in` 和可选 `excitation_tx_???.txt`。

### 4.3 `run`

渲染 + 执行 gprMax。

```bash
fda-mimo-gprmax run <scenario.yaml> \
  --variant target
  --run-dir /path/to/run
  --dry-run
  --geometry-only
  --timeout 120
```

不带 `--dry-run` 时执行 gprMax 并等待完成。

### 4.4 `workflow`

端到端工作流：渲染 → 执行 → 解析 → 处理 → 诊断。

```bash
fda-mimo-gprmax workflow <scenario.yaml> \
  --variant target
  --run-dir runs/pair_smoke
  --dry-run
  --timeout 120
```

`--run-dir` 接受场景根目录，工作流自动追加 `<variant>/` 子目录。

### 4.5 `process`

从已存在的 gprMax 原始输出处理快照。

```bash
fda-mimo-gprmax process <scenario.yaml> \
  --variant target
  --raw-dir runs/scene_001/target/raw
  --processed-dir runs/scene_001/target/processed
  --no-normalize
  --no-diagnostics
```

### 4.6 `subtract`

目标变体减背景变体，产生散射张量。

```bash
fda-mimo-gprmax subtract <scenario.yaml> \
  --run-dir runs/pair_smoke
  --target-variant target
  --background-variant background
```

输出写入 `runs/pair_smoke/scatter/processed/scatter_snapshot.h5`。

### 4.7 `inspect-run`

检查现有的场景运行目录，生成分析报告。

```bash
fda-mimo-gprmax inspect-run <run_dir> \
  --variants target,background
  --with-scatter
  --paper-mode
  --output runs/my_run/diagnostics
```

输出：`run_analysis_summary.json`、`run_analysis_report.md`、CSV 表格、matplotlib 图。

### 4.8 `evidence`

运行验证证据套件（合成/确定性，快速）。

```bash
fda-mimo-gprmax evidence <scenario.yaml> \
  --output-dir output/evidence/latest
  --tolerance 1e-6
  --overwrite
  --include-smoke
  --timeout 120
```

默认仅运行 5 个合成 case。`--include-smoke` 可选启动真实 gprMax 冒烟测试。

### 4.9 `protocol`

第一阶段理论验证协议。

```bash
fda-mimo-gprmax protocol plan     <scenario.yaml> --output-root output/protocol --checks V1,V2,V3 --overwrite
fda-mimo-gprmax protocol analyze  <scenario.yaml> --output-root output/protocol --checks all       --overwrite
fda-mimo-gprmax protocol report                     --output-root output/protocol --checks all
fda-mimo-gprmax protocol run      <scenario.yaml> --output-root output/protocol --execute-real --timeout 120
```

不支持 `--execute-real` 时 `run` 仅生成计划 + 缓存状态检查，安全无副作用。

### 4.10 `protocol-real`

从已存在的运行产物分析真实运行协议。

```bash
fda-mimo-gprmax protocol-real <run_dir> \
  --with-scatter
  --output diagnostics
```

评估 V1–V4，V5–V8 标记为 `NOT_EVALUATED`。

### 4.11 全局标志

- `--version` — 输出版本

---

## 5. Python API 模块参考

### 5.1 `config` — 场景配置模型

**模块：** `fda_mimo_gprmax.config`

#### 核心类

| 类 | 作用 | 关键字段 |
|----|------|----------|
| `ScenarioConfig` | 顶层场景配置 | `name`, `domain`, `grid`, `time`, `array`, `fda`, `waveform`, `receiver`, `scene`, `media`, `variants`, `execution`, `processing`, `output_root` |
| `DomainConfig` | FDTD 域 | `size: tuple[float,float,float]` |
| `GridConfig` | 网格间距 | `spacing: tuple[float,float,float]` |
| `TimeConfig` | 时间窗 | `window: float` |
| `ArrayConfig` | 阵列几何 | `tx_positions: ndarray`, `rx_positions: ndarray`, `nt: int`, `nr: int`, `mode`, `polarization` |
| `FDAConfig` | FDA 频率 | `kind`, `f0`, `df`, `frequencies: tuple[float,...]` |
| `WaveformConfig` | 源波形 | `mode`, `shape`, `amplitude`, `identifier_prefix` |
| `ReceiverConfig` | 接收分量 | `component: str` |
| `SceneConfig` | 场景命令 | `title`, `materials`, `geometry`, `geometry_view` |
| `VariantConfig` | 场景变体 | `name`, `geometry`, `metadata` |
| `ExecutionConfig` | gprMax 执行 | `executable`, `gpu`, `mpi`, `omp_threads`, `failure_policy` |
| `ProcessingConfig` | 输出/FFT 配置 | `export_npz`, `diagnostics`, `valid_band_threshold`, `eta`, `frequency_range`, `window` |
| `MediaFitConfig` | 结构化介质拟合策略 | `n_poles`, `frequency_min`, `frequency_max`, `num_frequencies`, `max_rel_error_warn`, `max_rel_error_fail`, `allow_poor_fit` |
| `MediaConfig` | 结构化介质集合 | `materials`, `fit`, `use_default_catalog`, `debye_approximations`, `fit_frequencies_hz`, `warnings` |

#### 关键函数

```python
def load_scenario(path: str | Path) -> ScenarioConfig
```
加载并验证 YAML 场景文件。引发 `ValidationError`（`ValueError` 子类）。

#### ScenarioConfig 方法

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `.normalized_dict()` | `dict` | 归一化配置字典（用于 checksum/元数据） |
| `.normalized_json()` | `str` | 确定性的 JSON 序列化 |
| `.checksum()` | `str` | SHA-256 配置校验和 |
| `.metadata()` | `dict` | 完整元数据（含 checksum） |
| `.variant(name)` | `VariantConfig` | 按名称查找变体 |

#### 工具函数

```python
def stable_json(data: Any) -> str    # 确定性 JSON 序列化
def checksum_text(text: str) -> str  # SHA-256
```

### 5.2 `rendering` — gprMax 输入文件渲染

**模块：** `fda_mimo_gprmax.rendering`

#### 核心类

```python
@dataclass(frozen=True)
class RenderedInput:
    tx_index: int
    variant: str
    input_path: Path          # 生成的 .in 文件路径
    output_path: Path         # 期望的 .out 文件路径
    waveform_id: str
    center_frequency: float
    source_position: tuple[float, float, float]
    receiver_positions: list[list[float]]
    component: str
    excitation_path: Path | None
    checksum: str

@dataclass(frozen=True)
class RenderPlan:
    scenario_name: str
    variant: str
    run_dir: Path
    config_dir: Path
    raw_dir: Path
    logs_dir: Path
    processed_dir: Path
    figures_dir: Path
    inputs: tuple[RenderedInput, ...]
    config_checksum: str
    geometry_only_command_hint: list[str]
```

#### 关键函数

```python
def render_scenario_inputs(
    scenario: ScenarioConfig,
    variant_name: str | None = None,
    run_dir: str | Path | None = None
) -> RenderPlan
```
为指定变体创建目录结构，为每个 Tx 生成一个 `.in` 文件（及可选激励文件），返回包含所有元数据的 `RenderPlan`。

```python
def render_input_text(
    scenario: ScenarioConfig,
    variant: VariantConfig,
    tx_index: int,
    config_dir: Path
) -> tuple[str, Path | None, str]
```
返回 `(input_file_text, excitation_path, waveform_id)`。

```python
def write_render_manifest(plan: RenderPlan, scenario: ScenarioConfig) -> Path
```
将渲染计划写入 `logs/run_manifest.json`。

```python
def render_structured_media_commands(scenario: ScenarioConfig) -> list[str]
```
将 `scenario.media.debye_approximations` 渲染为 gprMax 可执行材料命令。返回命令会在 raw `scene.materials` 和几何命令之前写入每个 Tx 输入文件。

### 5.3 `running` — gprMax 执行

**模块：** `fda_mimo_gprmax.running`

#### 核心类

```python
@dataclass(frozen=True)
class CommandPlan:
    tx_index: int
    command: tuple[str, ...]
    cwd: Path
    env: dict[str, str]
    input_path: Path
    expected_output_path: Path
    stdout_path: Path
    stderr_path: Path
    geometry_only: bool

@dataclass(frozen=True)
class RunResult:
    tx_index: int
    command: tuple[str, ...]
    returncode: int
    elapsed_seconds: float
    stdout_path: Path
    stderr_path: Path
    output_path: Path
    output_exists: bool
    output_checksum: str | None
```

#### 关键函数

```python
def build_command_plan(
    scenario: ScenarioConfig,
    plan: RenderPlan,
    item: RenderedInput,
    geometry_only: bool = False
) -> CommandPlan

def run_command(command_plan: CommandPlan, timeout: float | None = None) -> RunResult

def run_plan(
    scenario: ScenarioConfig,
    plan: RenderPlan,
    geometry_only: bool = False,
    timeout: float | None = None
) -> list[RunResult]

def write_manifest(
    plan: RenderPlan, scenario: ScenarioConfig,
    command_plans: list[CommandPlan],
    results: list[RunResult] | None = None,
    stage: str = "planned"
) -> Path

def output_is_stale(item: RenderedInput, manifest: dict | None = None) -> bool
```

#### 执行流程

`run_plan` 的工作方式：
1. 为每个 RenderedInput 构建 CommandPlan
2. 写入阶段为 "planned" 的 manifest
3. 逐一执行，每次执行后写入 "running" 状态 manifest
4. 遇失败且 `failure_policy == "stop"` 时中断
5. 完成后写入 "complete" 或 "failed" 状态 manifest

#### 输出文件重定位

gprMax 将 `.out` 文件写入输入文件同目录 → `run_command` 将其移动到计划的 `raw/` 目录。

### 5.4 `parsing` — gprMax HDF5 输出解析

**模块：** `fda_mimo_gprmax.parsing`

#### 核心类

```python
@dataclass(frozen=True)
class OutputInfo:
    path: Path
    iterations: int
    dt: float
    nrx: int
    gprmax_version: str
    available_components: dict[int, list[str]]
    receiver_positions: ndarray
    source_position: ndarray | None
    warnings: list[str]
    attrs: dict

@dataclass(frozen=True)
class TxTrace:
    tx_index: int
    path: Path
    component: str
    traces: ndarray        # [Nr, Lt]
    dt: float
    time: ndarray          # [Lt]
    receiver_positions: ndarray
    attrs: dict
    source_position_actual: ndarray | None
    receiver_positions_actual: ndarray | None
    hdf5_attrs: dict
    warnings: list[str]
```

#### 关键函数

```python
def inspect_output(path: str | Path) -> OutputInfo
```
探测单个 gprMax `.out` 文件，返回结构信息和位置数据。

```python
def extract_component(
    path: str | Path,
    component: str,
    expected_nrx: int | None = None,
    tx_index: int = 0
) -> TxTrace
```
从单个 `.out` 中提取指定分量的时域轨迹。

```python
def parse_tx_outputs(
    paths: Sequence[str | Path],
    component: str,
    expected_nrx: int | None = None
) -> list[TxTrace]
```
解析所有 Tx 的输出，校验 dt 和轨迹长度的一致性。

#### 错误处理

`OutputParseError`（`RuntimeError` 子类）在以下情况引发：
- 文件不存在
- 缺少必需 HDF5 属性（`Iterations`、`dt`、`nrx`）
- 缺少接收机组
- 分量数据集不存在
- Tx 间 dt 不匹配
- 轨迹长度不匹配

### 5.5 `processing` — 张量处理

**模块：** `fda_mimo_gprmax.processing`

#### 核心类

```python
@dataclass(frozen=True)
class Snapshot:
    time_traces: ndarray                    # float32 [Nt, Nr, Lt]
    time: ndarray                           # float64 [Lt]
    frequencies: ndarray                    # float64 [Kf]
    frequency_tensor_raw: ndarray           # complex64 [Nt, Nr, Kf]
    source_spectra: ndarray                 # complex64 [Nt, Kf]
    valid_band_mask: ndarray                # bool [Nt, Kf]
    frequency_tensor_cal: ndarray | None    # complex64 [Nt, Nr, Kf]
    tx_positions: ndarray                   # float64 [Nt, 3]
    rx_positions: ndarray                   # float64 [Nr, 3]
    fda_center_frequencies: ndarray         # float64 [Nt]
    metadata: dict
    scatter_tensor: ndarray | None
    tx_positions_requested / ..._actual / ...           # 位置量化证据
    position_quantization_error_tx / ..._rx             # 位置误差
    coordinate_warnings: list[str]
```

#### 关键函数

```python
def assemble_time_tensor(
    outputs: Sequence[TxTrace],
    expected_nt: int | None = None,
    expected_nr: int | None = None
) -> tuple[ndarray, ndarray]
```
将 TxTrace 列表堆叠为 `[Nt, Nr, Lt]` 张量，返回 `(yt, time)`。

```python
def frequency_transform(
    time_traces: ndarray,       # [Nt, Nr, Lt]
    dt: float,
    window: str = "none",
    frequency_range: tuple[float, float] | None = None
) -> tuple[ndarray, ndarray]
```
实部 FFT，返回 `(yf, freqs)`。支持 Hann/Hamming 窗。

```python
def sample_builtin_waveform(
    shape: str,
    amplitude: float,
    center_frequency: float,
    time: ndarray
) -> ndarray

def sample_waveform(
    waveform: WaveformConfig,
    center_frequency: float,
    time: ndarray
) -> ndarray
```
在时域采样理论波形，用于源谱计算。

```python
def compute_source_spectra(
    scenario: ScenarioConfig,
    time: ndarray,
    frequencies: ndarray,
    full_frequency_range: tuple[float, float] | None = None
) -> ndarray
```
计算所有 Tx 的 FFT 源谱 `[Nt, Kf]`。

```python
def valid_band_mask(
    source_spectra: ndarray,
    threshold: float
) -> ndarray
```
源谱幅度 > `threshold * 峰值` 的频点标记为有效。

```python
def normalize_by_source(
    frequency_tensor: ndarray,    # [Nt, Nr, Kf]
    source_spectra: ndarray,      # [Nt, Kf]
    mask: ndarray,
    eta: float
) -> ndarray
```
源归一化：`Y_cal = Y_rx / (S + eta)`，无效频点置 NaN。

```python
def make_snapshot(
    outputs: Sequence[TxTrace],
    scenario: ScenarioConfig,
    normalize: bool = True
) -> Snapshot
```
端到端处理管道：组装 → FFT → 源谱 → 有效掩膜 → 归一化 → 坐标证据 → 运行元数据。返回完整的 `Snapshot` 对象。

```python
def subtract_background(
    target: Snapshot,
    background: Snapshot,
    calibrated: bool = False
) -> ndarray
```
目标减背景，返回散射张量。校验目标/背景的轴兼容性。

#### 坐标证据机制

`_coordinate_evidence()` 从 TxTrace 中提取：
- 请求位置 vs gprMax 实际位置
- 位置量化误差
- Tx 间 Rx 位置一致性检查

结果嵌入 Snapshot.metadata 用于后续 QA。

### 5.6 `serialization` — 快照序列化

**模块：** `fda_mimo_gprmax.serialization`

#### 关键函数

```python
def write_snapshot_h5(snapshot: Snapshot, path: str | Path) -> Path
```
写入 HDF5 快照。包含组：`/snapshot/`、`/axis/`、`/scene/`、`/metadata/`。

```python
def write_snapshot_npz(snapshot: Snapshot, path: str | Path) -> Path
```
写入 NPZ 压缩快照。

```python
def write_processed_snapshot(
    snapshot: Snapshot,
    processed_dir: str | Path,
    export_npz: bool = True
) -> dict[str, Path]
```
写入 `snapshot.h5` 和（可选）`snapshot.npz`。返回 `{"h5": Path, "npz": Path}`。

### 5.7 `subtraction` — 目标/背景减法

**模块：** `fda_mimo_gprmax.subtraction`

#### 核心类

```python
@dataclass(frozen=True)
class ScatterResult:
    output_path: Path
    summary: dict[str, Any]
```

#### 关键函数

```python
def validate_pair(
    target: dict,
    background: dict,
    coordinate_atol: float = 1e-9,
    source_atol: float = 1e-9
) -> list[str]
```
校验目标/背景快照的兼容性（形状、坐标、FDA 频率等），返回警告列表。

```python
def subtract_snapshots(
    target_snapshot: str | Path,
    background_snapshot: str | Path,
    output_path: str | Path,
    coordinate_atol: float = 1e-9,
    source_atol: float = 1e-9
) -> ScatterResult
```
加载两个 HDF5 快照 → 校验 → 相减（时域 + 频域 + 可校准）→ 写入散射 HDF5。

```python
def subtract_scene_run(
    scene_run_dir: str | Path,
    target_variant: str = "target",
    background_variant: str = "background"
) -> ScatterResult
```
基于场景目录布局自动定位快照的简化接口。

### 5.8 `diagnostics` — 诊断图生成

**模块：** `fda_mimo_gprmax.diagnostics`

#### 关键函数

```python
def write_diagnostics(
    snapshot: Snapshot,
    figures_dir: str | Path
) -> dict[str, Path]
```

生成：
- `trace_preview.png`：Tx0-Rx0 时域轨迹
- `spectrum_preview.png`：|Y(tx0,rx0)| vs |S(tx0)|
- `phase_map.png`：指定频点的相位矩阵图
- `valid_band_mask.png`：有效频带掩膜
- `processing_summary.json`：处理指标摘要

### 5.9 `validation` — 验证证据套件

**模块：** `fda_mimo_gprmax.validation`

#### 核心类

```python
@dataclass(frozen=True)
class ValidationResult:
    case_name: str
    claim: str
    passed: bool
    inputs/metrics/artifacts/errors/limitations: ...

@dataclass(frozen=True)
class ValidationSuiteResult:
    suite_name: str
    output_dir: Path
    results: tuple[ValidationResult, ...]
    artifacts: dict[str, str]
    passed: bool
```

#### 合成验证 Case

| Case | 函数 | 验证内容 |
|------|------|----------|
| 01_render_contract | `render_contract_case` | 每个 `.in` 文件恰好 1 个 Hertzian dipole、Nt 个 Rx、Tx 绑定 FDA 频率 |
| 02_parser_roundtrip | `parser_roundtrip_case` | 合成 HDF5 可解析为 Y_t[m,n,l] 且张量索引正确 |
| 03_fft_sanity | `fft_sanity_case` | 对齐 bin 的正弦波 FFT 峰值位于预期频点 |
| 04_normalization_sanity | `normalization_sanity_case` | 源归一化可恢复已知信道响应，无效频点置 NaN |
| 05_background_subtraction | `background_subtraction_case` | 目标-背景减法恢复已知散射，不兼容轴被拒绝 |

#### 关键函数

```python
def run_synthetic_validation_suite(
    scenario: ScenarioConfig | str | Path,
    output_dir: str | Path,
    tolerance: float = 1e-6,
    overwrite: bool = False,
    write_report_file: bool = True
) -> ValidationSuiteResult

def gprmax_smoke_validation_case(
    scenario: ScenarioConfig,
    output_dir: str | Path,
    timeout: float | None = None,
    tolerance: float = 1e-6
) -> ValidationResult
```

#### 报告工具

```python
def write_summary(suite: ValidationSuiteResult) -> Path    # summary.json
def write_report(suite: ValidationSuiteResult) -> Path      # validation_report.md
def write_json(path, data)
def write_csv(path, rows)
def write_markdown_table(path, rows)
```

### 5.10 `protocol` — 理论验证协议

**模块：** `fda_mimo_gprmax.protocol`

#### 核心枚举与类

```python
class ProtocolStatus(Enum): PASS, WARNING, FAIL

class ThresholdPolicy:         # 基于阈值的状态分类器
    pass_threshold: float
    warning_threshold: float | None
    greater_is_better: bool

class ProtocolCheckDefinition:  # V1-V8 检查定义
    check_id, slug, name, mandatory, enhanced, ...

class ProtocolPaths:            # 协议检查目录布局
    root, check_id, check_dir, configs, raw, processed, figures, reports

class ProtocolCheckResult:      # 单检查结果
    check_id, check_name, status, main_metric, threshold, metrics, ...

class FirstStageDecision:       # 第一阶段决策
    accepted, mandatory_passed, v5_at_least_warning, enhanced_pass_count, ...

class ProtocolSuiteResult:      # 协议套件结果
    output_root, results, decision, artifacts

class ScenarioPlanItem:         # 计划中的具体场景配置
    scenario_id, family, variant, check_ids, config_path, ...
```

#### V1–V8 检查

| 检查 | 函数 | 验证内容 | 通过条件 |
|------|------|----------|----------|
| V1 | `run_v1` | 源 FDA 频率调度 | max(|e_m|, |d_m|) ≤ 2 FFT bins |
| V2 | `run_v2` | 张量完整性 | 所有必需 HDF5 键存在且形状匹配 |
| V3 | `run_v3` | MIMO 几何 | path-arrival 相关性 > 0.5 且信道非复制 |
| V4 | `run_v4` | GPR 介质 | ε 延迟相关性 > 0.95，σ 衰减相关性 < -0.8 |
| V5 | `run_v5` | FDA 非简并 | D_Y > 0.05 |
| V6 | `run_v6` | 深度/频率耦合 | 到达时间-深度相关性 > 0.95 |
| V7 | `run_v7` | 字典非等价 | D_μ > 0.05 |
| V8 | `run_v8` | 随机介质协方差 | ρ_off > 0.20 |

#### 关键函数

```python
def analyze_protocol(scenario, output_root, checks="all", ...) -> ProtocolSuiteResult
def plan_protocol(scenario, output_root, checks="all", ...) -> dict
def execute_protocol_real_runs(scenario, output_root, checks, timeout, force) -> dict
def report_protocol(output_root, checks, paper_mode) -> ProtocolSuiteResult
def materialize_scenario_plan(scenario, output_root, checks) -> list[ScenarioPlanItem]
def protocol_cache_status(output_root, checks) -> dict
def load_protocol_results(output_root, checks) -> tuple[ProtocolCheckResult, ...]
def first_stage_decision(results, paper_mode, enhanced_required) -> FirstStageDecision
```

### 5.11 `inspection` — 运行产物检查

**模块：** `fda_mimo_gprmax.inspection`

#### 核心类

```python
@dataclass(frozen=True)
class InspectRunResult:
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]
```

#### 关键函数

```python
def inspect_run(
    scene_run_dir: str | Path,
    variants: list[str] | None = None,
    with_scatter: bool = False,
    paper_mode: bool = False,
    output: str | Path | None = None
) -> InspectRunResult
```

输出决策级别（由低到高）：
- `NOT_ACCEPTED`
- `ACCEPTED_FOR_ENGINEERING_SMOKE`
- `ACCEPTED_FOR_REAL_FULLWAVE_TARGET_SNAPSHOT`
- `ACCEPTED_FOR_TARGET_BACKGROUND_SCATTER`
- `ACCEPTED_FOR_STAGE1_REAL_VALIDATION`

### 5.12 `log_analysis` — gprMax 日志解析

**模块：** `fda_mimo_gprmax.log_analysis`

#### 核心类

```python
@dataclass(frozen=True)
class GprMaxStdoutSummary:
    tx_index: int
    gprmax_version: str | None
    domain_size/grid_cells/spatial_step/time_window_s/iterations/waveform_frequency_hz
    warnings: list[str]
    numerical_dispersion_warning: bool
    max_phase_velocity_error_percent: float | None
    dispersion_risk: str            # UNKNOWN / LOW / MODERATE / HIGH / SEVERE

@dataclass(frozen=True)
class DispersionSummary:
    warning: bool
    risk: str
    max_abs_phase_velocity_error_percent: float | None
```

#### 关键函数

```python
def parse_gprmax_stdout(path: str | Path) -> GprMaxStdoutSummary
def collect_run_log_summaries(logs_dir: str | Path) -> list[GprMaxStdoutSummary]
def summarize_numerical_dispersion(summaries) -> DispersionSummary
def dispersion_risk(error_percent: float | None) -> str
```

### 5.13 `media` — 结构化介质与 Cole--Cole 兼容层

**模块：** `fda_mimo_gprmax.media`

该模块负责把兼容层中的物理介质定义转换为 gprMax 可执行介质命令。当前新增能力是：用户以 Cole--Cole 五参数定义物理介质，兼容层在渲染前确定性拟合为 multi-pole Debye 模型。

#### 常量

```python
EPSILON_0 = 8.854187817e-12
C0 = 299792458.0
```

#### 核心类

```python
@dataclass(frozen=True)
class ColeColeMedium:
    material_id: str
    eps_s: float
    eps_inf: float
    tau: float
    alpha: float
    sigma: float = 0.0
    source: str | None = None
    role: str | None = None
    medium_type: str | None = None

@dataclass(frozen=True)
class DebyeApproximation:
    material_id: str
    eps_inf: float
    sigma: float
    delta_eps: tuple[float, ...]
    tau: tuple[float, ...]
    fit_frequencies_hz: tuple[float, ...]
    max_rel_error: float
    rms_rel_error: float
```

`ColeColeMedium` 校验规则：

- `material_id` 非空，且应适合作为 gprMax 材料 ID；
- `eps_s > 0`；
- `eps_inf > 0`；
- `eps_s >= eps_inf`；
- `tau > 0`；
- `0 <= alpha < 1`；
- `sigma >= 0`；
- 所有浮点数必须有限。

#### 复相对介电常数

```python
def cole_cole_complex_permittivity(
    freq_hz: np.ndarray | float,
    *,
    eps_s: float,
    eps_inf: float,
    tau: float,
    alpha: float,
    sigma: float,
) -> np.ndarray
```

实现的物理模型为：

```text
eps_r(f) = eps_inf
         + (eps_s - eps_inf) / (1 + (j 2 pi f tau) ** (1 - alpha))
         + sigma / (j 2 pi f epsilon_0)
```

返回值是**复相对介电常数**，不是绝对介电常数。频率必须为正有限值。

```python
def debye_complex_permittivity(
    freq_hz: np.ndarray | float,
    *,
    eps_inf: float,
    sigma: float,
    delta_eps: np.ndarray,
    tau: np.ndarray,
) -> np.ndarray
```

计算 multi-pole Debye 近似的复相对介电常数：

```text
eps_r_debye(f) = eps_inf
               + sum_q delta_eps_q / (1 + j 2 pi f tau_q)
               + sigma / (j 2 pi f epsilon_0)
```

```python
def complex_wavenumber_from_epsilon(
    freq_hz: np.ndarray | float,
    epsilon_r: np.ndarray,
) -> np.ndarray
```

计算 `k = omega / C0 * sqrt(epsilon_r)`，用于后续诊断或测试。

#### Cole--Cole 到 Debye 拟合

```python
def fit_cole_cole_to_debye(
    medium: ColeColeMedium,
    fit_frequencies_hz: np.ndarray,
    *,
    n_poles: int = 12,
    tau_min: float | None = None,
    tau_max: float | None = None,
    allow_negative_weights: bool = False,
) -> DebyeApproximation
```

拟合目标是扣除 `eps_inf` 与导电项后的 Cole--Cole 弛豫项。默认采用 log-spaced `tau_q` 网格，并优先使用 `scipy.optimize.nnls` 进行非负最小二乘；如果 SciPy 不可用，则使用确定性的 NumPy fallback。拟合质量通过：

```text
rel_error = |eps_debye - eps_cole_cole| / max(|eps_cole_cole|, 1e-12)
```

记录 `max_rel_error` 与 `rms_rel_error`。

#### gprMax 命令渲染

```python
def render_debye_material_commands(approx: DebyeApproximation) -> list[str]
```

返回 gprMax 可执行命令：

```text
#material: <eps_inf> <sigma> 1 0 <material_id>
#add_dispersion_debye: <n_poles> <delta_eps_1> <tau_1> ... <delta_eps_n> <tau_n> <material_id>
```

兼容层不会向 gprMax 输入文件写入非原生 `#cole_cole` 命令。

#### 默认 catalog

```python
DEFAULT_COLE_COLE_CATALOG
```

内置 `S1`--`S5` 五个 Cole--Cole 介质 anchor。YAML 中可以通过：

```yaml
media:
  use_default_catalog: true
  materials:
    soil:
      from_catalog: S1
```

调用 catalog；显式 YAML 字段会覆盖 catalog 默认值。

---

## 6. 核心数据结构

### 6.1 张量形状约定

| 张量 | 符号 | 形状 | 数据类型 | 含义 |
|------|------|------|----------|------|
| 时域信道 | Y_t | `[Nt, Nr, Lt]` | float32 | Nt 个发射、Nr 个接收、Lt 个时间采样 |
| 频域信道（原始） | Y_f | `[Nt, Nr, Kf]` | complex64 | FFT 后的频率张量 |
| 频域信道（校准） | Y_cal | `[Nt, Nr, Kf]` | complex64 | 源归一化后的频率张量 |
| 源谱 | S | `[Nt, Kf]` | complex64 | 各 Tx 的理论波形 FFT |
| 有效频带掩膜 | M | `[Nt, Kf]` | bool | 源谱幅度 > thresh × 峰值的频点 |
| 散射张量 | Y_scat | `[Nt, Nr, Kf]` | complex64 | Y_target - Y_background |

### 6.2 HDF5 快照布局（`snapshot.h5`）

```
/
├── snapshot/
│   ├── time_traces              float32 [Nt, Nr, Lt]
│   ├── frequency_tensor_raw     complex64 [Nt, Nr, Kf]
│   ├── frequency_tensor_cal     complex64 [Nt, Nr, Kf]  (可选)
│   ├── source_spectra           complex64 [Nt, Kf]
│   ├── valid_band_mask          bool [Nt, Kf]
│   └── scatter_tensor           complex64 [Nt, Nr, Kf]  (可选)
├── axis/
│   ├── tx_positions             float64 [Nt, 3]
│   ├── rx_positions             float64 [Nr, 3]
│   ├── tx_positions_requested   float64 [Nt, 3]
│   ├── rx_positions_requested   float64 [Nr, 3]
│   ├── tx_positions_actual      float64 [Nt, 3]
│   ├── rx_positions_actual      float64 [Nt, Nr, 3]
│   ├── position_quantization_error_tx    float64 [Nt, 3]
│   ├── position_quantization_error_rx    float64 [Nt, Nr, 3]
│   ├── time                     float64 [Lt]
│   ├── frequencies              float64 [Kf]
│   └── fda_center_frequencies   float64 [Nt]
├── scene/
│   ├── target_params            JSON
│   ├── material_table           JSON
│   ├── domain                   float64 [3]
│   └── grid_spacing             float64 [3]
└── metadata/
    ├── config                   JSON
    ├── config_yaml              string
    ├── adapter_version           string
    ├── gprmax_version            string
    ├── random_seed               int
    ├── axis_convention           string
    ├── actual_positions_available bool
    ├── coordinate_warnings       JSON
    ├── checksums                 JSON
    ├── run_evidence              JSON
    ├── processing_metrics        JSON
    ├── media                     JSON  (结构化介质存在时包含 Cole--Cole / Debye provenance)
    └── numerical_dispersion      JSON
```

### 6.3 散射 HDF5 布局（`scatter_snapshot.h5`）

```
/
├── scatter/
│   ├── time_traces               float32 [Nt, Nr, Lt]
│   ├── frequency_tensor_raw      complex64 [Nt, Nr, Kf]
│   ├── frequency_tensor_cal      complex64 [Nt, Nr, Kf] (可选)
│   └── valid_band_mask_pair      bool [Nt, Kf]
├── axis/
│   └── ... (同快照)
├── scene/
│   └── ...
├── target/
│   └── ref_path                  string
├── background/
│   └── ref_path                  string
└── metadata/
    ├── subtraction_summary        JSON
    └── config                     JSON
```

### 6.4 运行目录布局

```
runs/<scenario>/
├── <variant>/
│   ├── config/
│   │   ├── generated_tx_000.in
│   │   ├── generated_tx_001.in
│   │   ├── ...
│   │   └── excitation_tx_000.txt  (custom waveform 模式)
│   ├── raw/
│   │   ├── tx_000.out
│   │   ├── tx_001.out
│   │   └── ...
│   ├── processed/
│   │   ├── snapshot.h5
│   │   └── snapshot.npz
│   ├── logs/
│   │   ├── run_manifest.json
│   │   ├── gprmax_stdout_tx_000.txt
│   │   ├── gprmax_stderr_tx_000.txt
│   │   └── ...
│   └── figures/
│       ├── trace_preview.png
│       ├── spectrum_preview.png
│       ├── phase_map.png
│       ├── valid_band_mask.png
│       └── processing_summary.json
├── scatter/                          (subtract 后生成)
│   └── processed/
│       └── scatter_snapshot.h5
└── diagnostics/                      (inspect-run 后生成)
    ├── run_analysis_summary.json
    ├── run_analysis_report.md
    ├── tables/
    └── figures/
```

---

## 7. 输出产物格式

### 7.1 `run_manifest.json`

```json
{
  "stage": "complete",
  "scenario": { ... },
  "media": {
    "source_model": "cole_cole",
    "approximation_model": "multi_pole_debye",
    "materials": [],
    "debye_approximations": [],
    "fit_frequency_range": [50000000.0, 150000000.0],
    "fit_num_frequencies": 256,
    "fit_error_policy": {
      "warn": 0.05,
      "fail": 0.15,
      "allow_poor_fit": false
    }
  },
  "render_plan": {
    "inputs": [
      {
        "tx_index": 0,
        "input_path": "...",
        "output_path": "...",
        "checksum": "sha256..."
      }
    ]
  },
  "commands": [ ... ],
  "results": [
    {
      "tx_index": 0,
      "returncode": 0,
      "elapsed_seconds": 12.3,
      "output_exists": true,
      "output_checksum": "sha256..."
    }
  ],
  "checksums": { "manifest_basis": "sha256..." }
}
```

stage 取值为：`"rendered"` / `"planned"` / `"running"` / `"complete"` / `"failed"`。

### 7.2 `processing_summary.json`

```json
{
  "time_traces_shape": [4, 4, 1024],
  "frequency_tensor_raw_shape": [4, 4, 513],
  "valid_fraction": 0.18,
  "fft_bin_spacing_hz": 9765625.0,
  "fda_delta_f_hz": 25000000.0,
  "fft_resolution_ratio": 0.39,
  "can_resolve_fda_step_by_fft": false,
  "numerical_dispersion": {
    "risk": "LOW",
    "max_abs_phase_velocity_error_percent": 0.89
  }
}
```

### 7.3 `inspect-run` 产品

`run_analysis_summary.json` 包含：
- `scene`: 场景名称
- `decision`: 五级决策
- `variants`: 每个变体的运行状态
- `tensor`: 张量形状和能量信息
- `fda`: FDA 频率证据（`PASS-CONFIG` / `PASS-SPECTRAL` / `WARNING-SPECTRAL-UNRESOLVED`）
- `coordinates`: 请求 vs 实际位置误差
- `numerical_dispersion`: 色散风险
- `scatter`: 散射快照状态
- `real_run_checks`: V1–V8 标记

---

## 8. 验证与协议体系

### 8.1 合成验证套件

该套件**不依赖 gprMax**，在纯 Python 中运行：
- 01: 验证渲染器生成的 `.in` 文件结构
- 02: 合成 HDF5 → 解析器 → 张量索引正确
- 03: 归一化对齐的纯正弦波 → FFT 峰值正确
- 04: 已知信道 → 源归一化恢复 + 无效掩膜
- 05: 已知散射 → 减法恢复 + 不兼容轴拒绝

### 8.2 第一阶段验证协议（V1–V8）

| 等级 | 检查 | 必需性 | 证据类型 |
|------|------|--------|----------|
| 强制 | V1 FDA 频率调度 | mandatory | 源谱峰值误差 |
| 强制 | V2 张量完整 | mandatory | HDF5 结构检查 |
| 强制 | V3 MIMO 几何 | mandatory | 路径-到达时间相关性 |
| 强制 | V4 GPR 介质 | mandatory | ε-延迟 / σ-衰减趋势 |
| 建议 | V5 FDA 非简并 | must be ≥ warning | FDA vs non-FDA 差异 |
| 增强 | V6 深度-频率耦合 | enhanced | 深度-到达趋势 |
| 增强 | V7 字典非等价 | enhanced | 相干矩阵差异 |
| 增强 | V8 随机介质协方差 | enhanced | 非对角协方差比例 |

**准入门控：**
1. V1–V4 全部通过
2. V5 至少 warning
3. paper mode 下 V6–V8 至少 2 个通过

### 8.3 运行产物检查决策

`inspect-run` 根据已存在的运行产物给出递增的接受级别：

```
目标变体 raw + processed 存在
  → ACCEPTED_FOR_REAL_FULLWAVE_TARGET_SNAPSHOT
  + 背景变体完整 + 散射存在
    → ACCEPTED_FOR_TARGET_BACKGROUND_SCATTER
  + paper mode + FFT 可分辨 FDA + 色散 LOW
    → ACCEPTED_FOR_STAGE1_REAL_VALIDATION
```

---

## 9. 兼容层的作用与设计边界

### 9.1 兼容层做了什么

| 作用 | 对应模块 | 说明 |
|------|----------|------|
| **YAML 场景语言** | `config.py` | 定义专用于 FDA-MIMO-GPR 的 YAML 方言 |
| **批量输入渲染** | `rendering.py` | 将 1 个场景 → Nt 个 gprMax `.in` 文件 |
| **波形管理** | `rendering.py` / `processing.py` | 为每个 Tx 注入独立频率的波形命令；回读时重算理论源谱 |
| **结构化介质兼容** | `media.py` / `config.py` / `rendering.py` | 将 Cole--Cole 五参数物理介质拟合为 gprMax 可执行 multi-pole Debye 命令，并保留拟合误差 |
| **TDM 调度编码** | `rendering.py` | 每个 `.in` 文件仅激活一个 Tx，所有 Rx 记录 |
| **输出解析与校验** | `parsing.py` | 从 gprMax `.out` 提取分量、位置、元数据 |
| **FDA 张量组装** | `processing.py` | 逐 Tx 输出 → `[Nt, Nr, Lt/Kf]` 统一张量 |
| **源归一化** | `processing.py` | 通过源谱校准消除波形对信道的贡献 |
| **快照序列化** | `serialization.py` | HDF5 + NPZ 格式导出，含完整元数据 |
| **目标/背景减法** | `subtraction.py` | 目标减背景获取纯散射张量 |
| **执行管理** | `running.py` | 带 manifest 和容错策略的批量 gprMax 运行 |
| **坐标精度追踪** | `processing.py` | 请求 vs gprMax 实际位置的量化误差 |
| **数值色散分析** | `log_analysis.py` | 从 gprMax stdout 提取色散警告 |
| **验证证据套件** | `validation.py` | 确定性合成 case，不依赖 gprMax |
| **理论验证协议** | `protocol.py` | V1–V8 多维度模型无关的结构证据链 |
| **运行诊断** | `inspection.py` | 对已有运行产品进行决策分级和错误分析 |

### 9.2 兼容层**不**做什么（设计边界）

| 不做 | 原因 |
|------|------|
| 不修改 gprMax 源码 | 保持 pip 安装兼容，不 fork；Cole--Cole 通过兼容层转 Debye，而非 gprMax 原生实现 |
| 不实现 T/R 开关行为 | 理想共址模型，无硬件细节 |
| 不建模互耦 | 全波 FDTD 自身包含互耦，但兼容层不额外建模 |
| 不实现运动平台 | 当前为静态场景快照 |
| 不进行成像或定位 | 仅生成信道张量，下游处理独立进行 |
| 不提供降阶信号模型拟合 | 验证是模型独立的 |
| 不实现实时采集时序 | 离线逐 Tx 执行 |
| 不进行天线方向图建模 | 使用 Hertzian dipole 点源（gprMax 默认） |
| 不支持真正的同时 MIMO | TDM 方式模拟 MIMO，一次一个 Tx |

### 9.3 版本范围

**当前版本（0.1.0）支持：**
- 理想近共址 TDM FDA-MIMO-GPR
- 线性 FDA 频率步进
- 结构化 Cole--Cole 五参数介质定义与 multi-pole Debye 执行近似
- 内置 Ricker/高斯/正弦波形 + 自定义激励文件
- 三种阵列模式（显式、严格共址、偏移共址）
- 目标/背景变体
- 时域 + 频域信道张量
- 源频率归一化
- HDF5 + NPZ 输出
- 坐标量化误差追踪
- 合成验证套件（无 gprMax 依赖）
- 第一阶段理论验证协议（V1–V8）
- 运行产物分析与决策分级

**超出范围（未来可能）：**
- 硬件校准误差建模
- 振荡器相位噪声
- 非线性 Tx/Rx 特性
- 真实同时 MIMO
- 移动平台
- 实测数据导入/校准
- 成像或源定位
- 平行/共线极化分集（当前仅单极化）

---

## 10. Cole--Cole 结构化介质 API

本章汇总从 `docs/api_reference.md` 合并而来的 Cole--Cole 介质 API 内容，并按本文档原有格式扩展为完整说明。

### 10.1 物理模型与执行近似

当前 gprMax 版本支持 raw `#material`、`#add_dispersion_debye`、`#add_dispersion_lorentz`、`#add_dispersion_drude` 等命令，但**不原生读取 Cole--Cole 五参数命令**。兼容层的职责是：

1. 在 YAML 中保存 Cole--Cole 作为物理介质定义；
2. 在渲染阶段将其确定性拟合为 multi-pole Debye；
3. 将 Debye 近似写成 gprMax 可执行命令；
4. 在 manifest / HDF5 / NPZ metadata 中同时保留原始 Cole--Cole 参数和 Debye 近似误差。

Cole--Cole 物理模型为：

```text
eps_r(f) = eps_inf
         + (eps_s - eps_inf) / (1 + (j 2 pi f tau) ** (1 - alpha))
         + sigma / (j 2 pi f epsilon_0)
```

| 参数 | 含义 | 约束 |
|------|------|------|
| `eps_s` | 静态相对介电常数 | `> 0` |
| `eps_inf` | 高频极限相对介电常数 | `> 0` 且 `eps_s >= eps_inf` |
| `tau` | 特征弛豫时间，单位 s | `> 0` |
| `alpha` | Cole--Cole 展宽因子 | `0 <= alpha < 1` |
| `sigma` | 直流电导率，单位 S/m | `>= 0` |

Debye 执行近似为：

```text
eps_r_debye(f) = eps_inf
               + sum_q delta_eps_q / (1 + j 2 pi f tau_q)
               + sigma / (j 2 pi f epsilon_0)
```

渲染为 gprMax 输入命令：

```text
#material: <eps_inf> <sigma> 1 0 <material_id>
#add_dispersion_debye: <n> <delta_eps_1> <tau_1> ... <delta_eps_n> <tau_n> <material_id>
```

### 10.2 YAML 输入示例

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

几何命令仍引用同一个 material id：

```yaml
scene:
  materials: []
  geometry:
    - "#box: 0 0 0 0.60 0.40 0.14 soil"
```

### 10.3 Python API 快速参考

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
|------|------|
| `ColeColeMedium` | 不可变 Cole--Cole 物理介质定义 |
| `DebyeApproximation` | 不可变 multi-pole Debye 近似结果 |
| `cole_cole_complex_permittivity()` | 计算 Cole--Cole 复相对介电常数 |
| `debye_complex_permittivity()` | 计算 Debye 近似复相对介电常数 |
| `complex_wavenumber_from_epsilon()` | 由相对介电常数计算复波数 |
| `fit_cole_cole_to_debye()` | 将 Cole--Cole 弛豫项拟合为 Debye poles |
| `render_debye_material_commands()` | 生成 gprMax 可执行材料命令 |
| `DEFAULT_COLE_COLE_CATALOG` | 内置 `S1`--`S5` 介质 catalog |

### 10.4 元数据约定

结构化介质信息会出现在：

- `ScenarioConfig.normalized_dict()["media"]`；
- `run_manifest.json` 的顶层 `media` 字段；
- `snapshot.h5` 的 `/metadata/config` 与 `/metadata/media`；
- `snapshot.npz` 的 `metadata` JSON。

典型结构为：

```json
{
  "source_model": "cole_cole",
  "approximation_model": "multi_pole_debye",
  "materials": [
    {
      "material_id": "soil",
      "model": "cole_cole",
      "eps_s": 30.26,
      "eps_inf": 10.7,
      "tau": 9.55e-12,
      "alpha": 0.062,
      "sigma": 0.0,
      "source": "Schwing 2013",
      "role": "fine-grained lossy soil anchor"
    }
  ],
  "debye_approximations": [
    {
      "material_id": "soil",
      "eps_inf": 10.7,
      "sigma": 0.0,
      "delta_eps": [0.0],
      "tau": [0.0],
      "n_poles": 12,
      "fit_frequency_min_hz": 50000000.0,
      "fit_frequency_max_hz": 150000000.0,
      "fit_num_frequencies": 256,
      "max_rel_error": 0.0,
      "rms_rel_error": 0.0
    }
  ]
}
```

上例中的 `delta_eps` / `tau` 数值仅表示结构，实际值来自确定性拟合结果。论文、数据说明和物理解释应引用原始 Cole--Cole 参数；Debye poles 仅表示 gprMax 执行近似。

### 10.5 兼容性与限制

- 旧式 raw gprMax material 命令仍完全可用；
- 结构化 `media.materials.<id>` 不得与 raw `#material: ... <id>` 重复；
- 生成的 `.in` 文件不会包含 `#cole_cole` 等 gprMax 不认识的命令；
- 当前仅新增 `model: cole_cole` 的结构化定义；Lorentz/Drude 仍可通过 raw gprMax 命令手写；
- `max_rel_error` 超过 `max_rel_error_fail` 时默认拒绝场景，除非设置 `allow_poor_fit: true`。

---

> **文档版本：** 对应 `fda-mimo-gprmax>=0.1.0`
> **最后更新：** 2026-06-08
