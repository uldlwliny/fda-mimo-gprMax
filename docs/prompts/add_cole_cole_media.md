# 任务：为 fda-mimo-gprMax 兼容层追加 Cole–Cole 五参数介质定义功能

## 背景

当前工程 `fda-mimo-gprMax` 是一个 gprMax 兼容层，用于生成 FDA-MIMO-GPR 场景、逐发射通道渲染 gprMax 输入、运行仿真、提取频域通道张量。现有实现主要通过 `scene.materials` 直接透传原生 gprMax `#material` 字符串，例如：

```yaml
scene:
  materials:
    - "#material: 6 0.01 1 0 soil"
```

这种写法只能表达 gprMax 原生材料参数，不能直接表达 FDA-MIMO-GPR 数值实验中常用的 Cole–Cole 五参数频散介质。因此需要在兼容层中增加结构化介质定义能力：用户在 YAML 中写 Cole–Cole 五参数，兼容层负责将其转换为 gprMax 可执行的色散材料命令，同时完整保留原始 Cole–Cole 参数和数值近似误差。

本任务不要修改 gprMax 内核。应通过兼容层实现 Cole–Cole 到 gprMax 可接受材料命令的转换。

## 总体目标

在 `fda-mimo-gprMax` 中增加一个结构化介质层，使场景 YAML 可以直接定义 Cole–Cole 五参数介质，并在渲染 gprMax 输入文件时自动转换为 gprMax 可执行的多极 Debye 近似材料。

需要实现：

1. Cole–Cole 五参数解析；
2. Cole–Cole 复相对介电常数计算；
3. Cole–Cole 到多极 Debye 模型的数值拟合；
4. gprMax 输入命令渲染；
5. manifest / metadata / HDF5 或 NPZ 元数据中记录原始 Cole–Cole 参数、Debye 近似参数和拟合误差；
6. 单元测试、渲染测试和最小示例；
7. 保持旧版 `scene.materials` 原始字符串透传方式完全兼容。

## 建议修改位置

当前工程主要文件可能包括：

```text
src/fda_mimo_gprmax/config.py
src/fda_mimo_gprmax/rendering.py
src/fda_mimo_gprmax/serialization.py
src/fda_mimo_gprmax/validation.py
src/fda_mimo_gprmax/protocol.py
examples/minimal_fda_mimo_scene.yaml
tests/
```

建议新增：

```text
src/fda_mimo_gprmax/media.py
tests/test_media.py
tests/test_rendering_cole_cole.py
examples/minimal_cole_cole_scene.yaml
```

必要时同步更新：

```text
docs/schema.md
README.md
```

## 一、实现 `media.py`

新增 `src/fda_mimo_gprmax/media.py`，至少包含以下内容。

### 1. 常量

```python
EPSILON_0 = 8.854187817e-12
C0 = 299792458.0
```

### 2. 数据结构

实现不可变 dataclass：

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


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
```

参数含义：

- `material_id`：gprMax 材料名称，例如 `soil`；
- `eps_s`：静态相对介电常数；
- `eps_inf`：高频极限相对介电常数；
- `tau`：特征弛豫时间，单位为秒；
- `alpha`：Cole–Cole 展宽因子；
- `sigma`：直流电导率，单位为 S/m；
- `source`：参数来源说明；
- `role`：该介质在实验中的角色说明。

校验规则：

- `material_id` 非空，且适合作为 gprMax 材料 id；
- `eps_s > 0`；
- `eps_inf > 0`；
- `eps_s >= eps_inf`；
- `tau > 0`；
- `0 <= alpha < 1`；
- `sigma >= 0`；
- 所有浮点数必须有限。

实现 Debye 近似结果结构：

```python
@dataclass(frozen=True)
class DebyeApproximation:
    material_id: str
    eps_inf: float
    sigma: float
    delta_eps: Tuple[float, ...]
    tau: Tuple[float, ...]
    fit_frequencies_hz: Tuple[float, ...]
    max_rel_error: float
    rms_rel_error: float
```

### 3. Cole–Cole 复相对介电常数函数

实现：

```python
import numpy as np


def cole_cole_complex_permittivity(
    freq_hz: np.ndarray | float,
    *,
    eps_s: float,
    eps_inf: float,
    tau: float,
    alpha: float,
    sigma: float,
) -> np.ndarray:
    """Return complex relative permittivity of a conductive Cole-Cole medium.

    The implemented model is

        eps_r(f) = eps_inf
                 + (eps_s - eps_inf) / (1 + (j 2 pi f tau) ** (1 - alpha))
                 + sigma / (j 2 pi f epsilon_0)

    The function returns complex relative permittivity, not absolute permittivity.
    """
    freq = np.asarray(freq_hz, dtype=float)
    if np.any(freq <= 0) or not np.all(np.isfinite(freq)):
        raise ValueError("freq_hz must contain positive finite frequencies")
    omega = 2.0 * np.pi * freq
    delta_eps = eps_s - eps_inf
    return (
        eps_inf
        + delta_eps / (1.0 + (1j * omega * tau) ** (1.0 - alpha))
        + sigma / (1j * omega * EPSILON_0)
    )
```

注意：

1. 必须使用 `sigma / (1j * omega * EPSILON_0)` 的符号约定；
2. 函数返回复相对介电常数；
3. 不要返回绝对介电常数；
4. 不要把电导率项写成 `-1j * sigma / (omega * EPSILON_0)` 之外的等价但难以比对的形式，建议保持上述公式。

### 4. 复波数函数

可选但建议实现：

```python
def complex_wavenumber_from_epsilon(
    freq_hz: np.ndarray | float,
    epsilon_r: np.ndarray,
) -> np.ndarray:
    """Return complex wavenumber k = omega / c0 * sqrt(epsilon_r)."""
    freq = np.asarray(freq_hz, dtype=float)
    omega = 2.0 * np.pi * freq
    return omega / C0 * np.sqrt(epsilon_r)
```

该函数用于后续诊断和测试，不一定直接参与 gprMax 渲染。

### 5. Cole–Cole 到多极 Debye 近似

实现：

```python
def fit_cole_cole_to_debye(
    medium: ColeColeMedium,
    fit_frequencies_hz: np.ndarray,
    *,
    n_poles: int = 12,
    tau_min: float | None = None,
    tau_max: float | None = None,
    allow_negative_weights: bool = False,
) -> DebyeApproximation:
    ...
```

目标近似形式为：

```text
epsilon_r_debye(f)
=
eps_inf
+
sum_q delta_eps_q / (1 + j * 2*pi*f*tau_q)
+
sigma / (j * 2*pi*f*epsilon_0)
```

拟合目标为 Cole–Cole 模型扣除 `eps_inf` 与 `sigma` 后的复弛豫项：

```python
eps_cc = cole_cole_complex_permittivity(...)
y = eps_cc - medium.eps_inf - medium.sigma / (1j * omega * EPSILON_0)
```

设计矩阵：

```python
A[:, q] = 1.0 / (1.0 + 1j * omega * tau_q)
```

由于 `delta_eps_q` 是实数，应把实部和虚部堆叠成实值最小二乘问题：

```python
A_real = np.vstack([A.real, A.imag])
y_real = np.concatenate([y.real, y.imag])
```

拟合要求：

1. 默认 `delta_eps_q >= 0`，优先使用 `scipy.optimize.nnls`；
2. 如果 SciPy 不可用，则使用 `numpy.linalg.lstsq`，随后把负权重截断为 0，再在正权重子集上做一次非负近似或普通最小二乘；
3. `tau_q` 默认采用 log-spaced 网格；
4. 如果用户没有指定 `tau_min` / `tau_max`，根据拟合频带自动设置：

```python
f_min = float(np.min(fit_frequencies_hz))
f_max = float(np.max(fit_frequencies_hz))
tau_min = min(medium.tau / 100.0, 1.0 / (2.0 * np.pi * f_max * 100.0))
tau_max = max(medium.tau * 100.0, 100.0 / (2.0 * np.pi * f_min))
```

并保证 `tau_min > 0`、`tau_max > tau_min`。

5. `fit_frequencies_hz` 应覆盖 FDA 中心频率和 `output.frequency_range` 所需频带；
6. 默认可使用对数均匀采样，数量至少 128 个频点；
7. 拟合误差定义为：

```python
eps_debye = debye_complex_permittivity(...)
rel_error = np.abs(eps_debye - eps_cc) / np.maximum(np.abs(eps_cc), 1e-12)
max_rel_error = float(np.max(rel_error))
rms_rel_error = float(np.sqrt(np.mean(rel_error**2)))
```

8. 如果 `max_rel_error > 0.05`，应发出 warning；
9. 如果 `max_rel_error > 0.15`，配置校验阶段默认失败，除非 YAML 中设置 `allow_poor_fit: true`。

### 6. Debye 复相对介电常数函数

实现：

```python
def debye_complex_permittivity(
    freq_hz: np.ndarray | float,
    *,
    eps_inf: float,
    sigma: float,
    delta_eps: np.ndarray,
    tau: np.ndarray,
) -> np.ndarray:
    freq = np.asarray(freq_hz, dtype=float)
    omega = 2.0 * np.pi * freq
    out = np.full_like(freq, complex(eps_inf), dtype=complex)
    for de, tq in zip(delta_eps, tau):
        out = out + de / (1.0 + 1j * omega * tq)
    out = out + sigma / (1j * omega * EPSILON_0)
    return out
```

### 7. gprMax 命令渲染

实现：

```python
def render_debye_material_commands(approx: DebyeApproximation) -> list[str]:
    ...
```

输出形式应为当前 gprMax 版本可执行的命令。预期类似：

```text
#material: <eps_inf> <sigma> 1 0 <material_id>
#add_dispersion_debye: <n_poles> <delta_eps_1> <tau_1> ... <delta_eps_n> <tau_n> <material_id>
```

重要要求：

1. 请在当前项目使用的 gprMax 版本文档或源码中确认 `#add_dispersion_debye` 的确切参数顺序；
2. 如果当前 gprMax 版本的命令格式不同，以实际版本为准；
3. 测试中至少断言渲染文本包含：
   - `#material:`；
   - `#add_dispersion_debye:`；
   - `material_id`；
   - 正确的 pole 数；
4. 不要把原始 Cole–Cole 参数直接写成 gprMax 不认识的命令；
5. gprMax 输入文件中应只出现 gprMax 能执行的材料命令。

## 二、扩展 YAML schema

保持旧格式完全可用：

```yaml
scene:
  materials:
    - "#material: 6 0.01 1 0 soil"
```

新增结构化格式。建议支持：

```yaml
media:
  fit:
    n_poles: 12
    frequency_min: 5.0e7
    frequency_max: 1.5e8
    num_frequencies: 256
    max_rel_error_fail: 0.15
    max_rel_error_warn: 0.05
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
  geometry:
    - "#box: 0 0 0 0.60 0.40 0.14 soil"
```

也支持默认 catalog：

```yaml
media:
  use_default_catalog: true
  materials:
    soil:
      from_catalog: S1
```

## 三、内置默认介质 catalog

在 `media.py` 或单独的 `media_catalog.py` 中内置以下默认介质。注意：这些参数直接写入本工程，不依赖外部项目。

```python
DEFAULT_COLE_COLE_CATALOG = {
    "S1": {
        "medium_type": "Dry lunar regolith / dry low-loss soil analog",
        "model": "cole_cole",
        "eps_s": 3.05,
        "eps_inf": 3.00,
        "tau": 1.0e-6,
        "alpha": 0.30,
        "sigma": 1.0e-14,
        "source": "Strangway 1974",
        "role": "low-loss propagation-dominated baseline",
    },
    "S2": {
        "medium_type": "Basalt / moist-dispersive analog",
        "model": "cole_cole",
        "eps_s": 1000.0,
        "eps_inf": 8.0,
        "tau": 1.0e-6,
        "alpha": 0.30,
        "sigma": 1.0e-8,
        "source": "Olhoeft 1973",
        "role": "strongly dispersive anchor",
    },
    "S3": {
        "medium_type": "Water ice / frozen ground anchor",
        "model": "cole_cole",
        "eps_s": 91.0,
        "eps_inf": 3.15,
        "tau": 2.5e-5,
        "alpha": 0.0,
        "sigma": 1.0e-8,
        "source": "Auty 1952",
        "role": "low-loss but highly polar medium",
    },
    "S4": {
        "medium_type": "Water-bearing kaolinite / concrete-like engineering anchor",
        "model": "cole_cole",
        "eps_s": 35.6,
        "eps_inf": 2.0,
        "tau": 5.0e-12,
        "alpha": 0.20,
        "sigma": 0.08,
        "source": "Mansour 2020",
        "role": "lossy engineering medium",
    },
    "S5": {
        "medium_type": "Fine-grained clay / pavement-soil anchor",
        "model": "cole_cole",
        "eps_s": 30.26,
        "eps_inf": 10.7,
        "tau": 9.55e-12,
        "alpha": 0.062,
        "sigma": 0.0,
        "source": "Schwing 2013",
        "role": "fine-grained lossy soil anchor",
    },
}
```

Catalog 使用规则：

1. `from_catalog: S1` 表示复制 `DEFAULT_COLE_COLE_CATALOG["S1"]`；
2. YAML 中显式给出的字段覆盖 catalog 默认值；
3. `material_id` 采用 YAML key，例如 `soil`；
4. 如果 `from_catalog` 不存在，应报错并列出可用 keys。

## 四、修改 `config.py`

新增配置类：

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MediaFitConfig:
    n_poles: int = 12
    frequency_min: float | None = None
    frequency_max: float | None = None
    num_frequencies: int = 256
    max_rel_error_warn: float = 0.05
    max_rel_error_fail: float = 0.15
    allow_poor_fit: bool = False


@dataclass(frozen=True)
class MediaConfig:
    materials: tuple[ColeColeMedium, ...] = ()
    fit: MediaFitConfig = field(default_factory=MediaFitConfig)
    use_default_catalog: bool = False
```

将其加入：

```python
@dataclass(frozen=True)
class ScenarioConfig:
    ...
    media: MediaConfig = field(default_factory=MediaConfig)
```

配置解析规则：

1. `media` 缺失时，行为与旧版完全一致；
2. `media.materials` 存在时，解析结构化介质；
3. `scene.materials` 仍保留为 raw gprMax 命令；
4. 渲染顺序应为：
   - 结构化 `media` 渲染出的材料命令；
   - 旧版 `scene.materials` 原始命令；
   - `scene.geometry`；
   - `variant.geometry`；
5. 如果结构化介质与 raw `scene.materials` 使用同一个 `material_id`，应报错，避免重复定义；
6. 如果 `scene.geometry` 或 `variant.geometry` 引用了不存在的材料 id，不要求完整解析几何命令，但至少不要破坏旧行为。

`ScenarioConfig.normalized_dict()` 与 metadata 必须包含：

```json
{
  "media": {
    "fit": {
      "n_poles": 12,
      "frequency_min": 50000000.0,
      "frequency_max": 150000000.0,
      "num_frequencies": 256,
      "max_rel_error_warn": 0.05,
      "max_rel_error_fail": 0.15,
      "allow_poor_fit": false
    },
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
        "max_rel_error": 0.0,
        "rms_rel_error": 0.0
      }
    ]
  }
}
```

上面的 `debye_approximations` 数值只是结构示意，实际应写入拟合得到的 pole 参数。

注意：配置 checksum 必须随 Cole–Cole 参数变化而变化。

## 五、修改 `rendering.py`

当前逻辑可能类似：

```python
lines.extend(scenario.scene.materials)
```

应改为：

```python
lines.extend(render_structured_media_commands(scenario))
lines.extend(scenario.scene.materials)
```

其中 `render_structured_media_commands(scenario)` 应：

1. 根据 `scenario.media` 生成 Debye 近似；
2. 渲染 gprMax 命令；
3. 保证每个 Tx 输入文件中的介质命令完全一致；
4. 将 Debye 近似结果写入 `run_manifest.json`；
5. 不要在每个 Tx 中重新产生非确定性结果；
6. 对同一个 scenario 多次 render，结果 checksum 必须完全一致。

建议将介质拟合结果缓存在 scenario 派生结构或 render 上下文中，避免每个 Tx 文件重复计算并产生微小差异。

## 六、修改 manifest / serialization

`run_manifest.json` 中增加：

```json
{
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
  }
}
```

HDF5 / NPZ metadata 中也应保留同样信息，至少在 `/metadata/normalized_config` 中可恢复。

要求：

1. 必须保留原始 Cole–Cole 参数；
2. 必须保留 Debye 近似参数；
3. 必须保留拟合频带和拟合误差；
4. 不要只保留渲染后的 gprMax 命令；
5. 后续论文、数据说明和可重复实验应以原始 Cole–Cole 参数作为物理介质定义，以 Debye poles 作为 gprMax 执行近似。

## 七、示例文件

新增：

```text
examples/minimal_cole_cole_scene.yaml
```

内容可基于 `examples/minimal_fda_mimo_scene.yaml`，将原始 `scene.materials` 替换为结构化 `media`：

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
  title: Minimal Cole-Cole FDA-MIMO-GPR scene
  materials: []
  geometry:
    - "#box: 0 0 0 0.60 0.40 0.14 soil"
  geometry_view: true
```

另加一个 catalog 版本示例：

```yaml
media:
  use_default_catalog: true
  fit:
    n_poles: 12
    frequency_min: 5.0e7
    frequency_max: 1.5e8
    num_frequencies: 256
  materials:
    soil:
      from_catalog: S1

scene:
  title: Minimal catalog Cole-Cole FDA-MIMO-GPR scene
  materials: []
  geometry:
    - "#box: 0 0 0 0.60 0.40 0.14 soil"
  geometry_view: true
```

## 八、测试要求

新增 `tests/test_media.py`。

### 1. `test_cole_cole_reference_values_s5`

使用 S5 参数：

```python
params = dict(
    eps_s=30.26,
    eps_inf=10.7,
    tau=9.55e-12,
    alpha=0.062,
    sigma=0.0,
)
freq = np.array([50e6, 70e6, 90e6, 110e6, 130e6, 150e6])
```

手工公式：

```python
omega = 2.0 * np.pi * freq
expected = (
    params["eps_inf"]
    + (params["eps_s"] - params["eps_inf"])
      / (1.0 + (1j * omega * params["tau"]) ** (1.0 - params["alpha"]))
    + params["sigma"] / (1j * omega * EPSILON_0)
)
```

断言：

```python
actual = cole_cole_complex_permittivity(freq, **params)
np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)
```

### 2. `test_cole_cole_reference_values_s1`

使用 S1 参数：

```python
params = dict(
    eps_s=3.05,
    eps_inf=3.00,
    tau=1.0e-6,
    alpha=0.30,
    sigma=1.0e-14,
)
freq = np.array([50e6, 70e6, 90e6, 110e6, 130e6, 150e6])
```

使用同样手工公式断言。

### 3. `test_debye_fit_reconstructs_debye_case`

构造 `alpha=0` 的 Debye 情况：

```python
medium = ColeColeMedium(
    material_id="ice",
    eps_s=91.0,
    eps_inf=3.15,
    tau=2.5e-5,
    alpha=0.0,
    sigma=1.0e-8,
)
```

频带可用 `np.logspace(6, 9, 256)`。断言：

```python
approx = fit_cole_cole_to_debye(medium, freq, n_poles=12)
assert approx.max_rel_error < 1e-3
```

如果实现中允许把 `medium.tau` 强制纳入 pole grid，则可收紧到 `1e-6`。

### 4. `test_debye_fit_cole_cole_reasonable_error`

使用 S1 或 S5，断言：

```python
assert approx.max_rel_error < 0.15
assert all(x >= -1e-12 for x in approx.delta_eps)
```

### 5. `test_invalid_cole_cole_params_rejected`

以下输入必须报错：

- `alpha >= 1`；
- `alpha < 0`；
- `tau <= 0`；
- `eps_s < eps_inf`；
- `eps_inf <= 0`；
- `eps_s <= 0`；
- `sigma < 0`；
- 非有限浮点数。

新增 `tests/test_rendering_cole_cole.py`。

### 6. `test_render_cole_cole_material_commands`

加载 `minimal_cole_cole_scene.yaml`；render 后每个 `generated_tx_*.in` 包含：

- `#material:`；
- `#add_dispersion_debye:`；
- `soil`；
- `#box: ... soil`。

### 7. `test_render_cole_cole_deterministic`

同一个 scenario 渲染两次；输入文件 checksum 一致。

### 8. `test_manifest_contains_cole_cole_metadata`

`run_manifest.json` 中包含：

- 原始 Cole–Cole 参数；
- Debye poles；
- `max_rel_error`；
- `rms_rel_error`；
- 拟合频带；
- 拟合 pole 数。

### 9. `test_legacy_raw_materials_still_work`

旧版 YAML 不含 `media`；旧测试全部通过；`scene.materials` 原样透传。

### 10. `test_material_id_collision_rejected`

`media.materials.soil` 与 `scene.materials` 中 `#material: ... soil` 同时出现时应报错。

运行全量测试：

```bash
pytest -q
```

并确保原有测试不回退。

## 九、文档更新

更新 `docs/schema.md`、`README.md` 与 `api_reference.md`，说明：

1. 旧式 raw gprMax material 命令仍可用；
2. 推荐新式结构化 `media.materials`；
3. 当前支持 `model: cole_cole`；
4. 五参数含义：
   - `eps_s`：静态相对介电常数；
   - `eps_inf`：高频极限相对介电常数；
   - `tau`：特征弛豫时间；
   - `alpha`：Cole–Cole 展宽因子；
   - `sigma`：直流电导率；
5. 兼容层内部将 Cole–Cole 近似为多极 Debye 后交给 gprMax；
6. manifest 会保留原始 Cole–Cole 参数和 Debye 近似误差；
7. 如果需要严格理论值，应以 metadata 中的 Cole–Cole 原始参数作为物理定义，而不是把 Debye poles 误认为原始介质模型。

## 十、验收标准

本任务完成后应满足：

1. 用户可以在 YAML 中直接写 Cole–Cole 五参数介质；
2. 渲染出的 gprMax `.in` 文件可以由当前 gprMax 版本执行；
3. 原始 Cole–Cole 参数、Debye 近似参数、拟合频带、拟合误差全部进入 manifest；
4. 原有 `scene.materials` raw 字符串工作流不受影响；
5. 旧测试与新增测试全部通过；
6. 示例 `examples/minimal_cole_cole_scene.yaml` 能完成 render；
7. 如果安装了 gprMax，示例能实际运行并输出通道张量；
8. 文档明确说明：这是兼容层中的 Cole–Cole 到 Debye 近似，不是 gprMax 内核的原生 Cole–Cole 实现。

## 十一、注意事项

- 不要删除或重命名现有 public API；
- 不要改变现有 FDA 频率调度逻辑；
- 不要改变 Tx/Rx 轴顺序；
- 不要把 receiver 数量误当成独立 FDTD solve 数量；
- 不要只保存 Debye 近似而丢失 Cole–Cole 原始参数；
- 不要把 SFCW 或普通 MIMO-GPR 逻辑混入 FDA-MIMO 调度；
- 所有随机或拟合相关过程必须确定性；
- 所有新增错误信息应明确指出 YAML 路径与非法参数名；
- 代码注释和文档中应明确区分“物理介质模型 Cole–Cole”和“gprMax 执行近似 multi-pole Debye”。
