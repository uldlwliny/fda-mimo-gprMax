# gprMax 兼容层设计：理想收发共址 TDM FDA-MIMO-GPR 快拍生成

## 1. 体制概述：理想收发共址 TDM FDA-MIMO-GPR

本兼容层实现一种理想化 FDA-MIMO-GPR 仿真体制，用于生成信号快拍的 full-wave simulation acquisition model。

### 1.1 阵列关系：Tx/Rx 共平台

发射与接收阵元位于同一平台（或同一近地表孔径），面向同一地下探测区域。支持两种共址模式。

**严格共址**：$\bm{s}_m = \bm{r}_m$，其中 $\bm{s}_m$ 为第 $m$ 个发射阵元位置，$\bm{r}_m$ 为对应接收阵元位置。对应理想共用孔径阵列，不要求显式实现真实 T/R switch 或 circulator。

**近共址偏移**：$\bm{s}_m \approx \bm{r}_m$，发射与接收共平台但不严格重合，通过小偏移提高收发隔离并降低自耦合。

两种模式下，完整通道由 Tx-Rx 索引对 $(m,n)$ 定义。即使收发共址，$m\neq n$ 的通道仍是近共址双基地通道，不应压缩为单站通道。

### 1.2 发射方式：单次激活一个 Tx

采用 TDM-MIMO 顺序发射。每次 gprMax forward run 仅激活一个发射阵元 $m$，其余保持非激活。第 $m$ 次发射的源项：

$$
\bm{J}_m(\bm{x},t) = \bm{p}_m s_m(t)\delta(\bm{x}-\bm{s}_m)
$$

其中 $\bm{p}_m$ 为发射极化方向，$s_m(t)$ 为源波形。

### 1.3 接收方式：所有 Rx 同步记录

第 $m$ 个 Tx 激活时，所有接收阵元 $n=1,\ldots,N_r$ 同步记录电磁场时间历史。单次 forward run 输出：

$$
\bm{y}_m(t) = [ y_{m1}(t), y_{m2}(t), \ldots, y_{mN_r}(t) ]^T
$$

完成全部 Tx 顺序发射后，得到时域通道张量：

$$
Y_t[m,n,\ell] = y_{mn}(t_\ell)
$$

其中 $\ell$ 为离散时间采样索引。

### 1.4 FDA 实现：Tx 索引关联的频率偏置

FDA 的核心机制：发射阵元索引与发射频率偏置绑定。不同 Tx 具有不同中心频率，各 Tx 频谱由索引独立调度。这与从同一宽带信号中抽取不同频率 bin 的方式不同。线性 FDA 调度：

$$
f_m = f_0 + (m-1)\Delta f
$$

其中 $f_0$ 为基准中心频率，$\Delta f$ 为频率步进。第 $m$ 个 Tx 的源波形：

$$
s_m(t) = w(t) \cos(2\pi f_m t + \phi_m)
$$

或复解析形式：

$$
s_m(t) = w(t) e^{j2\pi f_m t}
$$

在 gprMax 中，优先使用内置波形为不同 Tx 设定不同中心频率。若内置波形不满足调制需求，则使用自定义 excitation file。

### 1.5 快拍定义：$N_t$ 次顺序 Tx 形成一个快拍

FDA-MIMO-GPR 快拍在场景近似静止的短时间窗口内，通过 $N_t$ 次顺序发射形成通道集合，区别于所有 Tx 同时发射的瞬时记录。快拍张量：

$$
Y_t \in \mathbb{R}^{N_t \times N_r \times L_t}
$$

频域抽取后：

$$
Y_f \in \mathbb{C}^{N_t \times N_r \times K_f}
$$

多场景扩展：

$$
Y_f[s,m,n,k] \in \mathbb{C}
$$

其中 $s$ 为场景编号，$k$ 为频率 bin 索引。

## 2. 实现原理

### 2.1 gprMax 与兼容层的分工

gprMax 负责地下电磁传播的 full-wave forward simulation。它在给定介质、目标几何、源和接收点条件下，使用 FDTD 求解时域 Maxwell 方程，输出接收点处的电磁场时间历史。

兼容层不修改 Maxwell 方程、FDTD 更新格式或材料模型。它只负责 FDA-MIMO-GPR 体制层组织：阵列定义、FDA 发射调度、逐 Tx 输入文件生成、批量运行、receiver trace 读取、频域抽取、源谱归一化和张量封装。

二者组合可写为：

$$
\mathcal{A}_{\mathrm{FDA\text{-}MIMO\text{-}GPR}} = \mathcal{T}_{\mathrm{tensor}} \circ \mathcal{S}_{\mathrm{FDA\text{-}MIMO}} \circ \mathcal{F}_{\mathrm{gprMax}}
$$

其中 $\mathcal{F}_{\mathrm{gprMax}}$ 是 gprMax full-wave solver，$\mathcal{S}_{\mathrm{FDA\text{-}MIMO}}$ 是 FDA-MIMO 发射与接收调度，$\mathcal{T}_{\mathrm{tensor}}$ 是后处理与张量封装算子。

### 2.2 单 Tx full-wave run 的抽象形式

对第 $m$ 个发射阵元，gprMax 计算：

$$
y_{mn}(t) = \mathcal{L}_{\Omega,\varepsilon,\sigma,\mathcal{G}}[\bm{p}_m s_m(t)\delta(\bm{x}-\bm{s}_m)](\bm{r}_n,t)
$$

其中 $\Omega$ 为仿真区域，$\varepsilon$ 与 $\sigma$ 为介质参数，$\mathcal{G}$ 为地表、分层、目标与边界几何，$\mathcal{L}_{\Omega,\varepsilon,\sigma,\mathcal{G}}$ 为由地下场景决定的 full-wave 传播算子。

对所有接收点同步记录，得到：

$$
\bm{y}_m(t) = [\mathcal{L}[\bm{J}_m](\bm{r}_1,t), \ldots, \mathcal{L}[\bm{J}_m](\bm{r}_{N_r},t)]^T
$$

### 2.3 多 Tx 顺序发射与 MIMO 通道张量

对所有发射阵元重复上述过程，$m=1,2,\ldots,N_t$，保持同一地下场景、材料分布、目标几何、时间采样和接收阵列。将所有结果堆叠为：

$$
Y_t[m,n,\ell] = y_{mn}(t_\ell)
$$

该堆叠操作不制造新物理场，也不混合不相容数据。它只是将 TDM-MIMO 采集流程中的逐发射响应按 Tx-Rx 通道索引组织起来。

### 2.4 频域快拍与源谱归一化

时域输出经 Fourier transform 得到频域观测：

$$
Y_{\mathrm{rx}}[m,n,k] = \sum_{\ell=0}^{L_t-1} Y_t[m,n,\ell] \exp(-j2\pi f_k t_\ell)\Delta t
$$

由于不同 Tx 使用不同源波形或中心频率，原始频域观测包含源谱影响：

$$
Y_{\mathrm{rx}}[m,n,k] = H[m,n,k] S_m[k]
$$

因此需保存源谱 $S_m[k] = \mathcal{F}_t\{s_m(t)\}(f_k)$，并可选地输出源谱归一化后的等效通道：

$$
\widetilde{Y}[m,n,k] = \frac{Y_{\mathrm{rx}}[m,n,k]}{S_m[k]+\eta}
$$

其中 $\eta$ 为正则项，避免源谱接近零时放大数值误差。

同时输出有效频带 mask：

$$
M_{\mathrm{valid}}[m,k] = \mathbf{1}\left\{|S_m[k]| > \gamma \max_k |S_m[k]|\right\}
$$

后续分析只应在有效频带内使用 $\widetilde{Y}[m,n,k]$。

### 2.5 背景扣除与目标散射响应

收发共址 GPR 中，早时窗直达耦合、地表反射和背景响应可能显著强于目标散射。兼容层支持两组仿真：target-present 与 target-absent。

目标存在数据：$Y_{\mathrm{tar}}[m,n,k]$

背景数据：$Y_{\mathrm{bg}}[m,n,k]$

差分散射数据：$Y_{\mathrm{scat}}[m,n,k] = Y_{\mathrm{tar}}[m,n,k] - Y_{\mathrm{bg}}[m,n,k]$

该差分数据作为点目标定位、检测和 reduced-order model 拟合的主要输入。原始数据仍保存，以支持背景抑制方法和硬件效应分析。

### 2.6 为什么该组合生成的是 FDA-MIMO-GPR 信号

该兼容层生成的数据同时满足三个条件。

**GPR 条件**：地下传播由 gprMax 在给定土壤、地表、目标和边界条件下进行 full-wave FDTD 仿真，数据来自地下电磁传播场景。

**MIMO 条件**：数据具有显式 Tx-Rx 通道索引 $(m,n) \in \{1,\ldots,N_t\} \times \{1,\ldots,N_r\}$，并保存为通道张量 $Y[m,n,k]$。

**FDA 条件**：第 $m$ 个发射阵元具有索引相关的中心频率偏置 $f_m = f_0 + (m-1)\Delta f$。

因此，该数据属于具有 transmit-index-dependent frequency offsets 的 FDA-MIMO-GPR 仿真快拍，区别于普通 SFCW-GPR 或 MIMO-GPR。

### 2.7 与解析信号模型的关系

后续理论模型可写成 reduced-order 形式：

$$
y_{mn}(\omega_k) = \sum_{q=1}^{Q} \beta_q(\omega_k) G_r^{(0)}(\bm{r}_n,\bm{x}_q;\omega_k) G_t^{(0)}(\bm{x}_q,\bm{s}_m;\omega_{m,k}) + c_{mn}(\omega_k) + w_{mn}(\omega_k)
$$

其中 $\omega_{m,k} = \omega_k + \Delta\omega_m$。

该解析模型是 gprMax full-wave FDA-MIMO-GPR 数据的低阶结构解释模型，不应被视为 full-wave 真实模型。兼容层生成的 full-wave 数据用于检验解析模型预言的结构是否存在，包括：FDA 频偏诱导的 Tx-index-dependent 相位结构、字典相干性变化、跨频/跨通道协方差和参考介质失配残差。

## 3. 实现边界

### 3.1 第一版实现内容

1. 共平台 Tx/Rx 阵列定义，支持严格共址和近共址偏移。
2. TDM-MIMO 顺序发射流程。
3. 每个 Tx 使用不同中心频率或频谱偏置的 FDA 源波形。
4. 每次 forward run 中所有 Rx 同步记录。
5. 自动生成每个 Tx 对应的 gprMax input file。
6. 批量调用 gprMax。
7. 读取 gprMax HDF5 输出中的 receiver time histories。
8. 组装时域张量 $Y_t[m,n,\ell]$。
9. 抽取频域张量 $Y_f[m,n,k]$。
10. 保存源谱 $S_m[k]$、有效频带 mask、Tx/Rx 几何、FDA 调度、介质与目标 metadata。
11. 支持 target-present / target-absent 仿真和背景扣除。
12. 输出 HDF5 或 Zarr 格式的 channel tensor。（不是 B-scan 或成像结果。）

### 3.2 第一版暂不实现的内容

以下真实硬件效应不在第一版范围内。

1. 真实 T/R switch、circulator 或收发保护链路。
2. 发射泄漏、接收饱和和硬件动态范围限制。
3. 多通道本振相噪、频率合成器误差和采样时钟抖动。
4. 真实天线 mutual coupling，尤其是 FDA 频偏相关互耦。
5. 真实天线方向图、阻抗匹配和平台加载效应。
6. 发射机非线性、功率放大器失真和通道幅相不平衡。
7. 同时多 Tx 正交波形或真正 simultaneous MIMO。
8. 移动平台连续采集和运动补偿。
9. 实测数据校准链。
10. 完整硬件系统可制造性证明。

这些内容可作为后续 hardware impairment layer 或高阶仿真扩展，非 v0 兼容层目标。

### 3.3 必须避免的错误解释

1. **不得**把同一宽带 GPR 脉冲的不同频率 bin 直接解释为 FDA。FDA 要求发射阵元索引与频率偏置绑定，即不同 Tx 具有不同中心频率或发射频谱调度。
2. **不得**把输出图像、B-scan 或 migration result 作为 FDA-MIMO-GPR 原始数据。原始数据必须是 Tx-Rx-time 或 Tx-Rx-frequency channel tensor。
3. **不得**把顺序发射快拍解释为同时多发射快拍。本计划采用 TDM-MIMO；快拍成立的前提是场景在 $N_t$ 次顺序发射期间近似静止。
4. **不得**声称该兼容层验证了真实 FDA-MIMO-GPR 硬件。它验证的是一种理想化 full-wave FDA-MIMO-GPR acquisition model。
5. **不得**在源谱接近零的频点强行使用源谱归一化通道。必须保存有效频带 mask，并限制后续分析的频率范围。

### 3.4 第一版最小闭环

建议限定范围：

- 阵列：$N_t = N_r = 4$ 或 $N_t = N_r = 6$
- 阵列关系：严格共址或小偏移共址
- 场景：均匀 lossy half-space 或两层介质
- 目标：单个 PEC 球或简单介电异常体
- 发射：线性 FDA，$f_m = f_0 + (m-1)\Delta f$
- 接收：所有 Rx 同步记录指定场分量
- 输出：$Y_t[m,n,\ell]$、$Y_f[m,n,k]$、$S_m[k]$、$M_{\mathrm{valid}}[m,k]$、metadata
- 可选：target-present / target-absent 背景扣除

最小成功判据：

1. 从高层配置文件自动生成 $N_t$ 个 gprMax input files。
2. 每个 input file 只激活一个 Tx，且包含全部 Rx。
3. 每个 Tx 的源中心频率满足 FDA law。
4. gprMax 输出能被稳定读取。
5. 输出张量维度与配置一致。
6. HDF5/Zarr 文件保存完整 metadata。
7. 诊断图可展示 time traces、spectra、FDA 频偏下的通道相位差和有效频带 mask。
8. 重复运行时，配置、随机种子、软件版本和 checksum 可追踪。

### 3.5 推荐输出结构

```
runs/scene_001/
  config/
    scene.yaml
    generated_tx_000.in
    generated_tx_001.in
    ...
  raw/
    tx_000.out
    tx_001.out
    ...
  processed/
    snapshot.h5
    snapshot.npz
  logs/
    run_manifest.json
    gprmax_stdout_tx_000.txt
    checksums.sha256
  figures/
    trace_preview.png
    spectrum_preview.png
    phase_map.png
    valid_band_mask.png
```

`snapshot.h5` 建议包含：

```
/snapshot/time_traces              float32   [Nt, Nr, Lt]
/snapshot/frequency_tensor_raw     complex64 [Nt, Nr, Kf]
/snapshot/frequency_tensor_cal     complex64 [Nt, Nr, Kf]
/snapshot/source_spectra           complex64 [Nt, Kf]
/snapshot/valid_band_mask          bool      [Nt, Kf]

/axis/tx_positions                 float64   [Nt, 3]
/axis/rx_positions                 float64   [Nr, 3]
/axis/time                         float64   [Lt]
/axis/frequencies                  float64   [Kf]
/axis/fda_center_frequencies       float64   [Nt]

/scene/target_params               ...
/scene/material_table              ...
/scene/domain                      float64   [3]
/scene/grid_spacing                float64   [3]

/metadata/config_yaml              string
/metadata/gprmax_version           string
/metadata/adapter_version          string
/metadata/random_seed              int
/metadata/checksums                string
```

## 4. 结论

本兼容层理论定位：gprMax 提供地下 full-wave GPR forward operator，兼容层提供 FDA-MIMO 雷达采集算子，二者组合形成理想收发共址 TDM FDA-MIMO-GPR 快拍生成机制。

生成的数据满足 FDA、MIMO 和 GPR 三个必要条件：发射阵元索引相关频偏、多发射多接收通道张量、地下全波电磁传播。因此，它可作为后续 FDA-MIMO-GPR 信号模型验证、结构诊断、算法评估和 synthetic benchmark 建设的第一步数据基础。

## Real-run diagnostics architecture

Real-run products now carry requested and actual gprMax coordinates through parsing, processing, and HDF5 serialization. The parser reads source and receiver positions from raw `.out` HDF5 groups when available; processing compares them with requested YAML/rendered positions and records quantization errors.

`log_analysis.py` parses gprMax stdout to extract version, waveform frequency, grid/time metadata, and numerical-dispersion risk. `subtraction.py` validates target/background compatibility and writes scatter snapshots. `inspection.py` reads existing `runs/<scene>/` products and generates JSON, Markdown, CSV, and matplotlib diagnostics.

The design intentionally separates synthetic protocol validation from real-run inspection. Synthetic V1-V8 artifacts validate theory/reporting logic; real-run inspection currently supports V1-V4 evidence and explicitly marks V5-V8 as not evaluated unless the required real datasets are present.
