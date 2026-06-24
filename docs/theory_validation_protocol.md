# gprMax–FDA-MIMO-GPR 兼容层一阶段验证协议

## 1. 文档目的

本文档用于定义 `gprMax–FDA-MIMO-GPR` 兼容层的第一阶段验收方案。其目标不是验证某一个具体解析信号模型是否精确成立，而是验证兼容层生成的数据是否具备 FDA-MIMO-GPR 体制所要求的不可约结构。

第一阶段验收围绕如下问题展开：

> 在不依赖某一特定解析信号模型的前提下，如何判断由 gprMax 兼容层生成的数据确实可以称为 FDA-MIMO-GPR 信号快拍？

因此，本阶段的核心验收对象是 full-wave 数据张量本身，而不是某个 Green's function 模型、Born 近似模型、点目标模型或协方差模型。只要数据在结构上同时满足发射索引相关频偏、MIMO Tx--Rx 通道索引、地下介质传播响应和非退化 FDA 结构，即可认为兼容层的第一阶段实现成功。

## 2. 一阶段验证总目标

兼容层的一阶段验证应证明以下四件事：

1. **格式正确**：能够从 gprMax 输出中稳定生成带完整元数据的 FDA-MIMO-GPR 快拍张量。
2. **体制正确**：数据同时包含 FDA、MIMO、GPR 三个体制要素。
3. **物理正确**：地下介质参数、几何路径和目标深度能够以合理方式影响时延、幅度、相位和频谱。
4. **结构非退化**：当 FDA 频偏非零时，生成数据不能退化为普通 TDM MIMO-GPR 的简单重命名。

第一阶段成功的标准可以概括为：

\[
Y_t[m,n,\ell]\in\mathbb R^{N_t\times N_r\times L_t}
\]

\[
Y_f[m,n,k]\in\mathbb C^{N_t\times N_r\times K_f}
\]

其中，索引 \(m\) 对应发射阵元或发射状态，索引 \(n\) 对应接收阵元，索引 \(\ell\) 对应时域采样，索引 \(k\) 对应频域采样。该张量必须可追溯至完整的发射位置、接收位置、FDA 频偏、源波形、地下介质、目标几何和仿真配置。

## 3. 验收原则

### 3.1 不以解析模型逐点拟合为验收标准

第一阶段不要求证明：

\[
Y_{\mathrm{model}}[m,n,k]=Y_{\mathrm{FDTD}}[m,n,k]
\]

这种要求过强，也不适合 full-wave FDTD 数据。gprMax 生成的是完整 Maxwell 方程时域数值解，包含天线近场、地表反射、界面波、目标散射、多径、数值色散和边界影响。解析信号模型通常只是低阶结构解释，不能作为兼容层成功与否的唯一标准。

### 3.2 以体制无关结构为验收标准

验收应基于 FDA-MIMO-GPR 的体制定义，而非某个具体论文中的观测方程。成功数据至少应满足：

\[
m\mapsto f_m
\]

即发射索引与发射频率绑定；

\[
(m,n)\mapsto y_{mn}(t)
\]

即每个 Tx--Rx 通道可独立索引；

\[
(\varepsilon,\sigma,\mathcal G)\mapsto Y[m,n,k]
\]

即地下介质和目标几何进入通道响应。

### 3.3 以退化对照确认 FDA 非退化性

必须包含 \(\Delta f=0\) 与 \(\Delta f\neq0\) 的同场景对照。若 \(\Delta f\neq0\) 数据与 \(\Delta f=0\) 数据在源谱、通道相位、频域响应、字典相干性或深度相关结构上完全不可区分，则不能认为 FDA 机制被有效实现。

## 4. 推荐基础场景

第一阶段不宜使用复杂场景。推荐采用三个最小场景族。

### 4.1 场景 A：均匀半空间 + 单目标

用途：验证基本体制结构。

建议参数：

- 阵列：\(N_t=N_r=6\)
- 阵列关系：严格共址或近共址
- 发射方式：TDM，每次只激活一个 Tx
- 接收方式：所有 Rx 同时记录
- 介质：空气 + 均匀 lossy half-space
- 目标：一个 PEC 小球或小立方体
- FDA：线性频偏

该场景用于 source FDA law check、tensor integrity check、MIMO geometry check 和 FDA degeneracy check。

### 4.2 场景 B：均匀半空间参数扫描

用途：验证 GPR medium dependence。

建议扫描：

\[
\varepsilon_r\in\{4,6,9\}
\]

\[
\sigma\in\{0.001,0.01,0.05\}\ \mathrm{S/m}
\]

该场景用于验证介电常数改变导致时延变化，电导率增大导致高频衰减和总能量下降。

### 4.3 场景 C：目标深度扫描

用途：验证 depth/frequency coupling。

建议目标深度：

\[
z\in\{0.30,0.45,0.60,0.75\}\ \mathrm{m}
\]

该场景用于验证目标深度变化是否改变跨 Tx 频偏相关相位结构和主要回波到达时间。

### 4.4 场景 D：弱随机介质样本

用途：验证 random-medium covariance check。

在均匀或分层背景上加入弱随机扰动：

\[
\varepsilon_r(\mathbf x)=\bar\varepsilon_r+\delta\varepsilon_r(\mathbf x)
\]

其中 \(\delta\varepsilon_r(\mathbf x)\) 可采用相关随机场或分块随机扰动。该场景用于验证介质扰动是否诱导跨频、跨 Tx、跨 Rx 的非对角协方差结构。

## 5. 必做验收项总览

第一阶段建议设置 8 个必做验收项：

| 编号 | 验收项 | 目标 | 成功判据 |
|---|---|---|---|
| V1 | Source FDA law check | 验证 Tx 索引与源频率绑定 | 源谱峰值满足 \(\widehat f_m\approx f_0+(m-1)\Delta f\) |
| V2 | Tensor integrity check | 验证张量与元数据完整 | 输出 \(Y_t,Y_f\) 维度正确，metadata 可追溯 |
| V3 | MIMO geometry check | 验证 Tx--Rx 多视角通道 | 能量、到达时间随几何路径变化 |
| V4 | GPR medium check | 验证地下介质进入传播响应 | \(\varepsilon_r\) 改变时延，\(\sigma\) 改变衰减 |
| V5 | FDA degeneracy check | 验证 \(\Delta f=0\) 退化关系 | \(\Delta f\neq0\) 与 \(\Delta f=0\) 可测不同 |
| V6 | Depth/frequency coupling check | 验证深度与 Tx 频偏耦合 | 深度变化改变跨 Tx 相位结构 |
| V7 | Dictionary non-equivalence check | 验证 FDA 数据不等价于普通 MIMO-GPR | FDA 与 non-FDA 字典相干性结构不同 |
| V8 | Random-medium covariance check | 验证介质扰动诱导结构化协方差 | 协方差存在跨频/跨通道非对角结构 |

## 6. V1：Source FDA law check

### 6.1 验收目的

验证兼容层确实为每个发射阵元生成了不同中心频率或频谱偏置的源波形，而不是在同一源波形后处理中伪造 FDA 频偏。

### 6.2 输入数据

对每个 Tx，保存其源波形：

\[
s_m(t_\ell)
\]

或保存源谱：

\[
S_m(f_k)
\]

### 6.3 计算方法

对每个 Tx 计算源谱峰值频率：

\[
\widehat f_m=\arg\max_f |S_m(f)|
\]

并与理论 FDA 频率比较：

\[
f_m=f_0+(m-1)\Delta f
\]

计算频率误差：

\[
e_m=\widehat f_m-f_m
\]

以及相邻 Tx 的频差误差：

\[
d_m=(\widehat f_{m+1}-\widehat f_m)-\Delta f
\]

### 6.4 成功判据

应满足：

\[
|e_m|\leq \eta_f
\]

\[
|d_m|\leq \eta_f
\]

其中 \(\eta_f\) 可取频率分辨率 \(\Delta f_{\mathrm{FFT}}\) 的 1--2 倍。

### 6.5 失败诊断

若所有 \(\widehat f_m\) 相同，说明 FDA 没有进入源波形定义。  
若 \(\widehat f_m\) 与理论频率线性关系错误，说明发射索引或频偏 law 映射错误。  
若源谱严重偏离预期，说明 gprMax 波形参数或自定义 excitation 文件生成错误。

### 6.6 输出文件

- `source_spectra.png`
- `source_fda_law.csv`
- `source_fda_law_check.json`

## 7. V2：Tensor integrity check

### 7.1 验收目的

验证兼容层能正确读取 gprMax 输出，并封装为带完整索引和元数据的 FDA-MIMO-GPR 快拍张量。

### 7.2 输入数据

每个发射仿真的 gprMax `.out` 文件，以及兼容层生成的 `snapshot.h5`。

### 7.3 必须存在的数据字段

`snapshot.h5` 至少应包含：

```text
/snapshot/time_traces            [Nt, Nr, Lt]
/snapshot/frequency_tensor_raw   [Nt, Nr, Kf]
/snapshot/frequency_tensor_cal   [Nt, Nr, Kf]
/axis/tx_positions               [Nt, 3]
/axis/rx_positions               [Nr, 3]
/axis/time                       [Lt]
/axis/frequencies                [Kf]
/axis/fda_frequencies            [Nt]
/metadata/config_yaml
/metadata/gprmax_version
/metadata/adapter_version
/metadata/random_seed
```

### 7.4 成功判据

应满足：

\[
\operatorname{shape}(Y_t)=(N_t,N_r,L_t)
\]

\[
\operatorname{shape}(Y_f)=(N_t,N_r,K_f)
\]

并且：

- 所有 Tx、Rx 索引均有对应坐标；
- 所有 Tx 均有对应 FDA 频率；
- 所有频率 bin 和时间采样均有单位；
- metadata 中保存原始配置文件；
- 同一配置重复运行时 manifest 和 checksum 可复核。

### 7.5 失败诊断

若缺少 Tx 或 Rx 维度，说明数据被错误压缩成 B-scan 或单通道数据。  
若频率轴缺失，说明 FFT 或频域抽取不完整。  
若 metadata 不足，数据不可复现，不能作为 benchmark-grade 组件。

### 7.6 输出文件

- `snapshot.h5`
- `snapshot_summary.json`
- `tensor_shape_check.json`
- `metadata_check.json`

## 8. V3：MIMO geometry check

### 8.1 验收目的

验证不同 Tx--Rx 几何通道具有不同响应，说明数据不是复制通道，也不是单通道 GPR 输出的重命名。

### 8.2 输入数据

时域张量：

\[
Y_t[m,n,\ell]
\]

Tx/Rx 坐标：

\[
\mathbf s_m,\quad \mathbf r_n
\]

目标位置：

\[
\mathbf x_q
\]

### 8.3 计算方法

计算通道能量矩阵：

\[
E_{mn}=\sum_\ell |Y_t[m,n,\ell]|^2
\]

计算主要回波到达时间：

\[
\widehat\tau_{mn}=\arg\max_{t_\ell\in\mathcal W}|Y_t[m,n,\ell]|
\]

其中 \(\mathcal W\) 是目标回波所在时间窗。若有 target-present 与 target-absent 数据，应优先使用背景扣除后的散射响应：

\[
Y_t^{\mathrm{scat}}=Y_t^{\mathrm{tar}}-Y_t^{\mathrm{bg}}
\]

可计算近似双基地路径长度：

\[
L_{mn}(\mathbf x)=\|\mathbf s_m-\mathbf x\|+\|\mathbf x-\mathbf r_n\|
\]

并检查 \(\widehat\tau_{mn}\) 与 \(L_{mn}\) 的排序相关性。

### 8.4 成功判据

- \(E_{mn}\) 应随通道几何发生变化；
- \(\widehat\tau_{mn}\) 应与近似路径长度存在正相关；
- 不同 \((m,n)\) 通道不应完全相同；
- 对称共址阵列中可出现近似互易结构，但不应破坏 Tx--Rx 独立索引。

### 8.5 失败诊断

若所有通道完全相同，说明 receiver 读取或 tensor stacking 出错。  
若能量矩阵呈现不合理突变，需检查 Tx/Rx 坐标、接收通道命名和 HDF5 读取顺序。  
若到达时间与路径长度完全无关，需检查目标时间窗、背景扣除或场景几何。

### 8.6 输出文件

- `channel_energy_matrix.png`
- `arrival_time_matrix.png`
- `path_length_vs_arrival_time.png`
- `mimo_geometry_check.json`

## 9. V4：GPR medium check

### 9.1 验收目的

验证地下介质参数确实进入 full-wave 通道响应。该项证明数据不是自由空间 FDA-MIMO，也不是与介质无关的形式化张量。

### 9.2 输入场景

固定阵列、FDA law 和目标位置，改变介质参数：

\[
\varepsilon_r\in\{4,6,9\}
\]

\[
\sigma\in\{0.001,0.01,0.05\}\ \mathrm{S/m}
\]

### 9.3 计算方法

对每组介质计算主要回波到达时间、总能量和高频能量比。

群时延可估计为：

\[
\widehat\tau_{mn}= -\frac{1}{2\pi}\frac{\partial}{\partial f}\arg Y_f[m,n,f]
\]

高频能量比可定义为：

\[
R_{\mathrm{HF}}=\frac{\sum_{f_k\in\mathcal B_{\mathrm{high}}}|Y_f[m,n,k]|^2}{\sum_{f_k\in\mathcal B_{\mathrm{all}}}|Y_f[m,n,k]|^2}
\]

### 9.4 成功判据

当 \(\varepsilon_r\) 增大时，有效传播速度应降低：

\[
v\approx \frac{c}{\sqrt{\varepsilon_r}}
\]

主要回波到达时间或群时延应整体增大。  
当 \(\sigma\) 增大时，信号总能量和高频能量比应下降。

### 9.5 失败诊断

若改变 \(\varepsilon_r\) 后时延不变，需检查材料定义是否被正确写入 gprMax input。  
若改变 \(\sigma\) 后衰减不变，需检查材料电导率单位、频段和时间窗。  
若趋势与预期相反，需检查目标回波窗是否被直达波或地表反射污染。

### 9.6 输出文件

- `epsilon_delay_trend.png`
- `conductivity_attenuation_trend.png`
- `medium_sweep_summary.csv`
- `gpr_medium_check.json`

## 10. V5：FDA degeneracy check

### 10.1 验收目的

验证兼容层在 \(\Delta f=0\) 时退化为普通 TDM MIMO-GPR，在 \(\Delta f\neq0\) 时产生可测的 FDA 结构变化。

### 10.2 输入场景

同一阵列、介质和目标下运行两组仿真：

\[
\Delta f=0
\]

\[
\Delta f\neq0
\]

### 10.3 计算方法

比较源谱、通道频谱、通道相位和响应向量。

定义差异度：

\[
D_Y=\frac{\|Y_{\Delta f\neq0}-Y_{\Delta f=0}\|_F}{\|Y_{\Delta f=0}\|_F}
\]

对校准后通道也计算：

\[
D_{\widetilde Y}=\frac{\|\widetilde Y_{\Delta f\neq0}-\widetilde Y_{\Delta f=0}\|_F}{\|\widetilde Y_{\Delta f=0}\|_F}
\]

同时检查源谱中心是否从同频变为随 Tx 偏移。

### 10.4 成功判据

- \(\Delta f=0\) 时所有 Tx 源谱中心一致；
- \(\Delta f\neq0\) 时源谱中心随 Tx 线性偏移；
- 接收数据中出现可测差异；
- 差异不仅存在于文件 metadata 中，也存在于通道频谱、相位或结构指标中。

### 10.5 失败诊断

若 \(D_Y\approx0\)，说明 FDA 频偏没有进入 gprMax 源波形或输出读取链路。  
若 raw data 有差异但 calibrated data 完全无差异，需要判断是否校准过程过度消除了 FDA 效应。  
若差异仅由源谱幅度造成，需进一步检查相位和深度耦合指标。

### 10.6 输出文件

- `fda_vs_nonfda_source_spectra.png`
- `fda_vs_nonfda_phase_difference.png`
- `fda_degeneracy_metrics.csv`
- `fda_degeneracy_check.json`

## 11. V6：Depth/frequency coupling check

### 11.1 验收目的

验证目标深度变化会改变 FDA 频偏相关的跨 Tx 相位结构。该项是判断“FDA 频偏进入地下传播链路”的关键结构测试。

### 11.2 输入场景

固定阵列、介质和 FDA law，扫描目标深度：

\[
z\in\{z_1,z_2,z_3,z_4\}
\]

### 11.3 计算方法

对同一 Rx 和频率 bin，计算跨 Tx 相位差：

\[
\Delta\phi_{m,m'}(n,k;z)=\arg Y_f[m,n,k;z]-\arg Y_f[m',n,k;z]
\]

也可以使用展开相位或群时延：

\[
\widehat\tau_{mn}(z)= -\frac{1}{2\pi}\frac{\partial}{\partial f}\arg Y_f[m,n,f;z]
\]

计算不同深度下的相位结构变化：

\[
D_\phi(z_i,z_j)=\|\Delta\Phi(z_i)-\Delta\Phi(z_j)\|_F
\]

### 11.4 成功判据

- 目标深度增加时，主要回波到达时间后移；
- 跨 Tx 相位差结构随深度变化；
- 变化趋势在多个 Rx 或多个有效频率 bin 上稳定存在；
- \(\Delta f=0\) 对照中该 FDA 频偏相关变化应显著减弱或消失。

### 11.5 失败诊断

若深度变化不影响相位结构，需检查目标是否在有效探测深度内、目标回波窗是否正确、频率 bin 是否落在有效源带宽内。  
若相位跳变严重，需采用相位展开、背景扣除或选择更稳定的频带。

### 11.6 输出文件

- `depth_arrival_time_trend.png`
- `depth_tx_phase_map.png`
- `depth_frequency_coupling_metrics.csv`
- `depth_frequency_coupling_check.json`

## 12. V7：Dictionary non-equivalence check

### 12.1 验收目的

验证 FDA-MIMO-GPR 数据的响应结构不等价于 ordinary TDM MIMO-GPR 数据。该项不要求某个解析 dictionary 正确，只要求 full-wave 数据在不同目标位置下形成的响应集合具有不同相干性结构。

### 12.2 输入场景

在多个候选目标位置 \(\mathbf x_i\) 上生成 target-present 与 target-absent 数据，提取散射响应：

\[
Y^{\mathrm{scat}}(\mathbf x_i)=Y^{\mathrm{tar}}(\mathbf x_i)-Y^{\mathrm{bg}}
\]

分别生成 \(\Delta f=0\) 和 \(\Delta f\neq0\) 两组数据。

### 12.3 计算方法

构造响应向量：

\[
\mathbf h(\mathbf x_i)=\operatorname{vec}\{Y^{\mathrm{scat}}[m,n,k;\mathbf x_i]\}
\]

计算相干性：

\[
\mu(\mathbf x_i,\mathbf x_j)=\frac{|\mathbf h(\mathbf x_i)^H\mathbf h(\mathbf x_j)|}{\|\mathbf h(\mathbf x_i)\|_2\|\mathbf h(\mathbf x_j)\|_2}
\]

比较 FDA 与 non-FDA 的相干性矩阵：

\[
\mathbf M_{\mathrm{FDA}}=[\mu_{ij}^{\mathrm{FDA}}]
\]

\[
\mathbf M_{0}=[\mu_{ij}^{\Delta f=0}]
\]

差异指标可定义为：

\[
D_\mu=\frac{\|\mathbf M_{\mathrm{FDA}}-\mathbf M_0\|_F}{\|\mathbf M_0\|_F}
\]

### 12.4 成功判据

- \(D_\mu\) 应显著大于数值误差水平；
- FDA 与 non-FDA 的相干性热图应可观察到结构差异；
- 差异在有效频带、目标深度扫描或横向扫描中具有稳定性；
- 不要求 FDA 一定降低全部相干性，但要求其响应结构不能完全等价于 \(\Delta f=0\) 数据。

### 12.5 失败诊断

若 \(D_\mu\approx0\)，说明 FDA 频偏没有改变响应结构，需检查频偏大小、源带宽、目标位置、频域抽取方式。  
若相干性矩阵噪声很大，需提高仿真精度、加强背景扣除或缩小分析频带。

### 12.6 输出文件

- `coherence_matrix_fda.png`
- `coherence_matrix_nonfda.png`
- `coherence_difference.png`
- `dictionary_non_equivalence_metrics.csv`
- `dictionary_non_equivalence_check.json`

## 13. V8：Random-medium covariance check

### 13.1 验收目的

验证随机介质扰动会诱导跨 Tx、Rx 和频率的结构化协方差，而不是独立白噪声式扰动。这是后续 clutter covariance、robust detection 和 single-snapshot 统计建模的基础。

### 13.2 输入场景

生成 \(S\) 个随机介质样本：

\[
\varepsilon_r^{(s)}(\mathbf x)=\bar\varepsilon_r+\delta\varepsilon_r^{(s)}(\mathbf x)
\]

对每个样本生成快拍：

\[
Y_s[m,n,k]
\]

### 13.3 计算方法

向量化：

\[
\mathbf y_s=\operatorname{vec}\{Y_s[m,n,k]\}
\]

估计样本协方差：

\[
\widehat{\mathbf R}=\frac{1}{S}\sum_{s=1}^{S}(\mathbf y_s-\bar{\mathbf y})(\mathbf y_s-\bar{\mathbf y})^H
\]

其中：

\[
\bar{\mathbf y}=\frac{1}{S}\sum_{s=1}^{S}\mathbf y_s
\]

可进一步计算非对角能量比：

\[
\rho_{\mathrm{off}}=\frac{\|\widehat{\mathbf R}-\operatorname{diag}(\widehat{\mathbf R})\|_F}{\|\widehat{\mathbf R}\|_F}
\]

以及跨频块相关、跨 Tx 块相关和跨 Rx 块相关。

### 13.4 成功判据

- \(\rho_{\mathrm{off}}\) 应显著大于纯独立噪声基线；
- 协方差热图应显示跨频、跨 Tx 或跨 Rx 的结构化块；
- 随随机介质相关长度、扰动强度变化，协方差结构应有可解释变化；
- 若使用 \(\Delta f=0\) 对照，FDA 与 non-FDA 的协方差结构应不完全相同。

### 13.5 失败诊断

若协方差近似对角，可能是随机扰动强度过小、样本数不足、频带选择不当或背景扣除过强。  
若协方差无稳定结构，需检查随机介质生成是否真正写入 gprMax input，以及不同样本之间是否只有随机噪声而无介质差异。

### 13.6 输出文件

- `covariance_heatmap.png`
- `covariance_block_summary.png`
- `random_medium_covariance_metrics.csv`
- `random_medium_covariance_check.json`

## 14. 统一诊断指标

建议所有验收项统一输出如下指标字段。

```json
{
  "check_name": "...",
  "status": "pass | warning | fail",
  "main_metric": 0.0,
  "threshold": 0.0,
  "scene_id": "...",
  "config_hash": "...",
  "gprmax_version": "...",
  "adapter_version": "...",
  "notes": "..."
}
```

各项验收可以根据指标设定 `pass/warning/fail`。建议不要一开始设置过硬阈值，而是采用“趋势正确 + 数值显著大于数值误差”的原则。第一阶段的重点是发现体制链路是否打通，而不是优化最终性能。

## 15. 推荐目录结构

每个验证任务建议形成独立目录：

```text
output/protocol/
  V1_source_fda_law/
    configs/
    raw/
    processed/
    figures/
    reports/
  V2_tensor_integrity/
  V3_mimo_geometry/
  V4_gpr_medium/
  V5_fda_degeneracy/
  V6_depth_frequency_coupling/
  V7_dictionary_non_equivalence/
  V8_random_medium_covariance/
```

每个目录至少包含：

```text
config.yaml
manifest.json
snapshot.h5
metrics.csv
check_result.json
figures/*.png
```

## 16. 一阶段通过条件

一阶段不要求所有高级结构指标完美，但应满足如下最低通过条件：

1. V1 必须通过。否则 FDA 频偏没有实现。
2. V2 必须通过。否则没有可复用快拍张量。
3. V3 必须通过。否则 MIMO 通道索引无效。
4. V4 必须通过。否则数据不能称为 GPR full-wave 数据。
5. V5 至少应达到 warning 以上。否则 FDA 与 non-FDA 数据不可区分。
6. V6、V7、V8 可作为增强验收项；若用于论文或 benchmark，应至少有两个达到 pass。

建议最终一阶段报告给出如下总表：

| 验收项 | 状态 | 主要指标 | 结论 |
|---|---|---|---|
| V1 | pass/fail | frequency-law error | FDA source law 是否成立 |
| V2 | pass/fail | tensor shape + metadata completeness | 快拍张量是否完整 |
| V3 | pass/fail | path-arrival correlation | MIMO 几何是否有效 |
| V4 | pass/fail | delay/attenuation trend | GPR 介质效应是否存在 |
| V5 | pass/warning/fail | FDA/non-FDA difference | FDA 是否非退化 |
| V6 | pass/warning/fail | phase-depth coupling | 深度频偏耦合是否存在 |
| V7 | pass/warning/fail | coherence-structure difference | 字典结构是否不同 |
| V8 | pass/warning/fail | off-diagonal covariance ratio | 随机介质协方差是否结构化 |

## 17. 论文或报告中的建议表述

可将一阶段验收原则表述为：

> The adapter is not validated by fitting a particular reduced-order signal model. Instead, it is validated through model-independent structural checks required by the FDA-MIMO-GPR acquisition principle: transmit-index-dependent frequency scheduling, independently indexed Tx--Rx channel acquisition, medium-dependent subsurface propagation, and non-degenerate FDA-induced channel structure relative to the \(\Delta f=0\) TDM MIMO-GPR limit.

中文表述可写为：

> 兼容层的成功不以某一解析信号模型的逐点拟合为标准，而以体制无关的结构验收为标准：发射索引相关频偏必须在源谱和接收数据中可观测，Tx--Rx 通道必须独立成矩阵，地下介质参数必须显著影响时延和衰减，且 \(\Delta f\neq0\) 时生成的通道张量不得退化为 \(\Delta f=0\) 的普通 TDM MIMO-GPR 张量。

## 18. 最终结论

第一阶段验证的核心是证明：兼容层生成的数据不是普通 GPR、普通 MIMO-GPR 或普通 FDA-MIMO 数据的重命名，而是同时具备 FDA、MIMO 和 GPR 三种体制要素的 full-wave 快拍张量。

成功的一阶段实现应满足：

\[
\text{Tx-index-dependent frequency scheduling}
\]

\[
\text{independently indexed Tx--Rx channel matrix}
\]

\[
\text{subsurface medium-dependent full-wave propagation}
\]

\[
\text{non-degenerate FDA structure relative to }\Delta f=0
\]

只有在这些结构验收成立后，后续解析信号模型、定位算法、检测算法、协方差建模和 benchmark 扩展才具有稳固的数据基础。
