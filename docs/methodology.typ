#set text(lang: "zh", size: 10pt)
#set page(margin: (x: 2.0cm, y: 2.2cm))
#set par(justify: true, leading: 0.65em)
#set heading(numbering: "1.1")

#let v(x) = bold(x)
#let mat(x) = bold(x)

= 基于 gprMax 的 FDA-MIMO-GPR 快拍生成方法记录

== 方法定位

本文构造一个可复现的全波（full-wave）快拍生成流程。该流程以 gprMax 为地下电磁传播的全波正演后端，编写 Python 代码作为 FDA-MIMO 雷达采集体制的外部调度层，二者串联形成理想收发共址、时分发射的 FDA-MIMO-GPR 快拍生成算子。

该路线的必要性来自现有公开证据的结构性缺口。严格的 FDA-MIMO-GPR 证据需同时满足三项条件：发射索引相关的 FDA 频偏、多发多收通道索引、地下或 GPR 工作环境。公开文献中同时满足三者且具备可复现实验材料的基准（benchmark）仍然缺位——现有 MIMO-GPR 硬件缺乏阵元相关频偏，现有 FDA-MIMO 算法缺乏地下传播核，现有 gprMax/FDTD 工作缺乏 FDA-MIMO 体制的结合。因此，一个公开、可检查的 gprMax 兼容层可为后续快拍模型、定位算法和协方差分析提供更高层级的全波数据依据。

具体地：首先用 gprMax 计算地下全波响应，随后用兼容层组织 Tx 索引、Rx 索引和 FDA 频率调度，最后将逐发射、多接收的输出封装成显式通道张量。所得数据先被视为全波 FDA-MIMO-GPR 快拍，再用于检验低阶解析信号模型是否能解释其中的稳定结构。

== gprMax 物理正演

=== Maxwell 方程与地下介质传播

gprMax 是面向 GPR 的开源 FDTD 电磁仿真软件，在给定几何、材料、源和接收点后，在时域离散求解 Maxwell 方程。对于非磁性地下介质，基本连续模型为

$ nabla times E(x,t) = - mu_0 (partial H(x,t)) / (partial t) $

$ nabla times H(x,t) = J_s(x,t) + (partial D(x,t)) / (partial t) + sigma(x) E(x,t) $

其中 $E$ 与 $H$ 分别为电场和磁场，$J_s$ 为外加源电流，$sigma(x)$ 为电导率。材料关系为

$ D(x,t) = epsilon(x,t) * E(x,t) $

非色散介质中 $epsilon$ 取常数或分块常数，色散介质中 $epsilon$ 对应频率相关复介电性质。gprMax 已用于 GPR 波传播、非均匀土壤、色散材料和 GPU 加速仿真 [Warren2016; Giannopoulos2005; Giannakis2014; Warren2019]。

在雷达观测框架下，gprMax 提供地下全波正演算子。设仿真区域为 $Omega$，材料分布为 $epsilon, sigma$，地下几何和目标为 $cal(G)$。第 $m$ 个发射源的源项为

$ J_m(x,t) = p_m s_m(t) delta(x - s_m) $

其中 $s_m$ 为发射阵元位置，$p_m$ 为极化方向，$s_m(t)$ 为源波形。gprMax 计算所有接收点 $r_n$ 处的时间历史：

$ y_(m n)(t) = cal(L)_(Omega,epsilon,sigma,cal(G)) [ p_m s_m(t) delta(x-s_m) ] (r_n,t) $

此处 $cal(L)_(Omega,epsilon,sigma,cal(G))$ 表示由地下介质、边界条件、目标和数值网格共同确定的 全波传播算子，是对 gprMax 正演行为的算子抽象。

=== FDTD 离散意义

FDTD 方法将电磁场在空间网格和时间步上交错更新。忽略色散递推项后，形式化的 Yee 更新结构为

$ H^(q+1/2) = H^(q-1/2) - Delta t mu^(-1) op("curl")_h E^q $

$ E^(q+1) = A_e E^q + B_e ( op("curl")_h H^(q+1/2) - J_s^(q+1/2) ) $

其中 $q$ 为时间步，$op("curl")_h$ 为空间离散旋度，$A_e,B_e$ 含介电常数、电导率和时间步长。该离散结构说明，对于固定介质与目标几何，不同发射阵元和不同源波形仅对应不同的源项。逐 Tx 运行 gprMax 不改变物理传播方程，仅在同一地下场景中施加不同发射激励。

gprMax 贡献的是 GPR 物理层：地下介质中的传播、反射、散射、衰减和数值全波相互作用。FDA-MIMO-GPR 所需的发射阵元频率偏置、MIMO 通道张量和快拍索引均由兼容层补足。

== 兼容层雷达体制组织

=== 理想收发共址 TDM FDA-MIMO-GPR

当前实现采用理想收发共址 TDM FDA-MIMO-GPR。发射阵列和接收阵列位于同一平台或同一近地表孔径，支持严格共址与近共址偏移：

$ s_m = r_m quad "or" quad s_m approx r_m $

严格共址对应理想共用孔径。近共址偏移对应实际 GPR 系统中为收发隔离而设置的小几何偏移。两种情况下，完整数据均保留 Tx-Rx 通道索引 $(m,n)$。$m=n$ 时通道近似为自发自收或共址通道，$m != n$ 时通道为近共址双基地通道。兼容层保持完整矩阵结构，不将其压缩为单站 B-scan。

一个快拍由 $N_t$ 次顺序发射形成。第 $m$ 次发射仅激活第 $m$ 个 Tx，所有 $N_r$ 个 Rx 同步记录：

$ y_m(t) = [ y_(m 1)(t), y_(m 2)(t), dots, y_(m N_r)(t) ]^(top) $

全部 Tx 运行后，兼容层堆叠得到时域快拍张量：

$ Y_t[m,n,l] = y_(m n)(t_l), quad Y_t in RR^(N_t times N_r times L_t) $

频域抽取后得到

$ Y_f[m,n,k] = sum_(l=0)^(L_t-1) Y_t[m,n,l] exp(-j 2 pi f_k t_l) Delta t $

$ Y_f in CC^(N_t times N_r times K_f) $

=== FDA 频率调度

FDA 的定义性结构是发射阵元索引与发射频率偏置绑定。线性 FDA 调度为

$ f_m = f_0 + (m-1) Delta f $

该机制源于 FDA 文献中的基本设定 [Antonik2006; Wang2012; Secmen2007]。在自由空间、窄带和远场近似下，相邻阵元对目标的相位差为

$ Delta Phi = (2 pi f_0 d sin theta) / c + (2 pi Delta f r) / c $

其中第一项为常规阵列角度项，第二项与距离 $r$ 和频偏 $Delta f$ 有关，体现 FDA 区别于相控阵的距离相关发射维度。相应阵因子为

$ op("AF")(t,theta,r) = sum_(m=0)^(M-1) exp( j 2 pi (m Delta f t - f_0 (m d sin theta)/c - m Delta f r/c) ) $

上述公式用于说明发射索引-频率偏置-距离相关性机制。由于地下 GPR 不满足自由空间、远场和均匀传播假设，本文不将其直接作为 GPR 观测方程。兼容层采用这些公式定义的 FDA 频率调度原则，传播过程则交由 gprMax 的地下全波正演完成。

宽带 GPR 脉冲中，第 $m$ 个 Tx 的波形为

$ s_m(t) = w(t) cos(2 pi f_m t + phi_m) $

或复解析形式

$ s_m(t) = w(t) exp(j 2 pi f_m t) $

实现时，代码在每个 gprMax 输入文件中为第 $m$ 个 Tx 设置对应中心频率的源波形。FDA 频偏由此通过发射源本身的中心频率差异进入全波传播链路。

=== 兼容层与 gprMax 的组合算子

兼容层与 gprMax 的组合可形式化写为

$ cal(A)_("FDA-MIMO-GPR") = cal(T)_("tensor") circle cal(S)_("FDA-MIMO") circle cal(F)_("gprMax") $

其中 $cal(F)_("gprMax")$ 为地下全波正演算子，$cal(S)_("FDA-MIMO")$ 为外部定义的发射阵元、接收阵元和 FDA 频率调度，$cal(T)_("tensor")$ 为时间序列读取、频域抽取、源谱归一化、有效频带标记和 HDF5/NPZ 张量封装算子。

该组合能够称为 FDA-MIMO-GPR，是因为同时满足三项不可约条件。

+ GPR 条件：传播发生在地下场景，材料包含空气层、土壤层、电导率、目标和边界条件，响应由 FDTD 求解 Maxwell 方程获得。

+ MIMO 条件：数据保留显式 Tx-Rx 索引 $(m,n)$，形成 $N_t times N_r$ 通道矩阵，而非单通道或处理后图像。

+ FDA 条件：第 $m$ 个发射状态具有 Tx 索引相关频率 $f_m=f_0+(m-1)Delta f$，区别于同频 MIMO-GPR 或普通 SFCW-GPR。SFCW-GPR 的频率随脉冲或步进扫描变化，但同一频率步中所有发射通道不具有阵元相关偏置。FDA-MIMO-GPR 则要求发射索引与频偏绑定。

== 无特定信号模型依赖的验证与诊断

=== 诊断原则

公开文献中尚不存在被广泛接受的复杂介质 FDA-MIMO-GPR 快拍模型。代码先确认数据体制和物理来源，再将低阶模型作为后续解释工具。因此检验生成数据是否满足 FDA-MIMO-GPR 体制的不可约结构。诊断仅依赖公开公认的体制定义、Maxwell/FDTD 正演结果、通道张量索引、源谱和基本传播趋势。即从

$ "验证" quad y = H beta + c + w $

转化为

$ "验证" quad ("Tx-indexed frequency") + ("Tx-Rx channel matrix") + ("subsurface full-wave propagation") $

=== V1：FDA 频率律验证

FDA 体制最基本的验收是检查源频率是否随 Tx 索引变化。对配置或 gprMax 日志中的中心频率 $hat(f)_m$，检查

$ hat(f)_m approx f_0 + (m-1) Delta f $

并计算相邻频率差：

$ hat(f)_(m+1) - hat(f)_m approx Delta f $

FFT 时间窗足够长时，还可从源谱峰值直接验证：

$ tilde(f)_m = arg max_f |S_m(f)| $

若 $tilde(f)_m$ 也满足线性频率律，则给出 spectral pass。配置和日志满足 FDA law 但 FFT bin 间隔 $Delta f_("FFT")=1/T$ 大于 FDA 步进 $Delta f$ 时，给出 spectral unresolved warning，不判定为 FDA 失败。

=== V2：张量完整性验证

MIMO 体制要求数据具有独立可索引的发射和接收通道。诊断检查处理后文件是否包含

$ Y_t in RR^(N_t times N_r times L_t) $

$ Y_f in CC^(N_t times N_r times K_f) $

并检查以下元数据（metadata）是否完整：

$ s_m, r_n, f_m, S_m(f), t_l, f_k, Delta f, epsilon(x), sigma(x) $

若缺少 Tx/Rx 维度，或仅保存 B-scan、image、migration 输出，则不能构成 FDA-MIMO-GPR 快拍数据。

=== V3：MIMO 几何多视角验证

MIMO-GPR 的基本物理结果是不同 Tx-Rx 几何路径产生不同能量和到达时间。诊断计算通道能量矩阵

$ E_(m n) = sum_l |Y_t[m,n,l]|^2 $

和峰值时间矩阵

$ tau_(m n) = arg max_(t_l) |Y_t[m,n,l]| $

收发共址或近共址场景中，对角或近距离通道通常更强、更早，远距离通道通常更弱、更晚。若所有通道几乎完全相同，则说明 MIMO 索引可能被复制、覆盖或读取错误。该检查仅使用原始迹（raw trace）的几何响应，不使用目标散射模型。

=== V4：GPR 物理环境验证

GPR 条件要求信号对地下介质和数值传播条件敏感。诊断包含两类指标。

第一，介质与场景证据。从输入文件（input）、HDF5 与日志中读取材料、目标、domain、网格间距（grid spacing）、时间窗（time window）、source 和 receiver。若运行目录中仅有自由空间场景或缺少地下介质，则不能称为 GPR 结果。

第二，数值可信度证据。从 gprMax stdout 中解析 numerical dispersion warning，给出相速度误差风险等级。最大相速度误差过高时，该运行仍可作为工程冒烟测试（smoke test），但不应用于精细相位、群时延、Fisher 信息或 FDA 相干性结论。该诊断检验 FDTD 数据是否适合被物理解释，不要求任何具体信号模型成立。

=== V5：FDA 退化极限验证

FDA-MIMO-GPR 在 $Delta f=0$ 时应退化为普通 TDM MIMO-GPR。诊断应在同一场景下比较两组数据：

$ Y_("FDA") = Y |_(Delta f != 0), quad Y_("MIMO") = Y |_(Delta f = 0) $

若 $Delta f != 0$ 数据与 $Delta f=0$ 数据在源谱、频域相位或响应结构上完全不可分，则 FDA 频偏可能未进入真实传播链路。该验证依赖体制退化关系，不依赖 Born、点目标或 Green 函数模型。

=== V6：深度-频率耦合验证

FDA 的距离相关性在地下场景中不应直接套用自由空间公式，但体制上仍应产生 Tx 频偏与传播时延共同作用的结构。对不同目标深度 $z$ 的散射张量，可检查跨 Tx 相位差

$ Delta phi_(m,m')(n,k;z) = arg Y_f[m,n,k;z] - arg Y_f[m',n,k;z] $

是否随深度或有效传播时延变化。该检查仅依赖频率偏置参与传播相位累积这一体制事实，不要求具体路径模型精确。

=== V7：字典非等价验证

对候选位置响应向量

$ h(x) = vec { Y_("scat")(m,n,k;x) } $

可比较 FDA 与 non-FDA 情况下的归一化相干性

$ mu(x_i,x_j) = abs(h(x_i)^H h(x_j)) / (norm(h(x_i))_2 norm(h(x_j))_2) $

FDA 数据不必必然降低所有相干性，但其响应字典不能与 $Delta f=0$ MIMO-GPR 完全等价。该诊断检验体制维度是否带来响应空间变化，而非检验定位算法性能。

=== V8：随机介质协方差结构验证

在多组随机介质或弱扰动背景样本上，向量化观测为

$ y_s = vec { Y_s[m,n,k] } $

样本协方差估计为

$ hat(R) = 1/S sum_(s=1)^S (y_s - bar(y))(y_s - bar(y))^H $

介质扰动通过地下传播影响多 Tx、多 Rx 和多频响应时，$hat(R)$ 应表现出跨 Tx、跨 Rx 或跨频非对角结构，而非纯白噪声对角矩阵。该诊断检验全波数据是否能承载 FDA-MIMO-GPR 杂波/协方差（clutter/covariance）问题，与具体协方差解析公式无关。

== 当前运行产物

=== 原始 gprMax 输出

兼容层为每个 Tx 生成一个 gprMax 输入文件（input file）并运行对应正演求解。典型文件如下：

```
runs/<scene>/target/config/generated_tx_000.in
runs/<scene>/target/raw/tx_000.out
runs/<scene>/target/logs/gprmax_stdout_tx_000.txt
```

`.in` 文件记录材料、几何、source、receiver 和波形（waveform）。`.out` 文件为 gprMax HDF5 输出，包含各 receiver 的场时间历史。标准输出/标准错误保存版本、网格、迭代、材料、波形和数值色散信息。该层产物构成全波证据层。

=== 快拍张量文件

处理后的核心产物为

```
runs/<scene>/target/processed/snapshot.h5
runs/<scene>/background/processed/snapshot.h5
runs/<scene>/scatter/processed/scatter_snapshot.h5
```

`snapshot.h5` 至少包含

```
/axis/tx_positions_requested
/axis/tx_positions_actual
/axis/rx_positions_requested
/axis/rx_positions_actual
/axis/time
/axis/frequencies
/axis/fda_center_frequencies
/snapshot/time_traces
/snapshot/frequency_tensor_raw
/snapshot/frequency_tensor_cal
/snapshot/source_spectra
/snapshot/valid_band_mask
/scene/material_table
/scene/target_params
/metadata/run_evidence
/metadata/numerical_dispersion
```

其中 `/snapshot/time_traces` 对应 $Y_t[m,n,l]$，`/snapshot/frequency_tensor_raw` 对应 $Y_("rx")[m,n,k]$，`/snapshot/frequency_tensor_cal` 对应源谱归一化后的 $tilde(Y)[m,n,k]$，`/snapshot/valid_band_mask` 标记可用于可靠除谱和相位分析的频率区域。

`scatter_snapshot.h5` 保存

$ Y_("scat") = Y_("target") - Y_("background") $

该差分张量削弱直达耦合、地表响应和静态背景，是后续点目标定位、检测和低阶模型拟合的主要数据产品。

=== 诊断报告与表格

`inspect-run` 生成

```
runs/<scene>/diagnostics/run_analysis_report.md
runs/<scene>/diagnostics/run_analysis_summary.json
runs/<scene>/diagnostics/tables/*.csv
runs/<scene>/diagnostics/figures/*.png
```

这些产物记录 FDA law 证据、FFT 分辨率、MIMO 通道能量矩阵、峰值时间矩阵、坐标量化、数值色散、有效频带掩码（valid-band mask）、目标/背景/散射（target/background/scatter）完整性和最终接受等级。它们为每次仿真提供可追溯的工程与物理审计。

== 与后续快拍建模和定位算法的关系

=== 从全波数据到降阶快拍模型

后续理论可将全波散射张量（scatter tensor）解释为低阶模型的观测样本。点目标稀疏场景下，常见的降阶（reduced-order）形式为

$ y_(m n)(omega_k) = sum_(q=1)^Q beta_q(omega_k) G_r^(0)(r_n,x_q;omega_k) G_t^(0)(x_q,s_m;omega_(m,k)) + c_(m n)(omega_k) + w_(m n)(omega_k) $

其中 $G_t^(0),G_r^(0)$ 为参考介质传播核，$beta_q$ 为等效散射系数，$c_(m n)$ 为背景或介质残差项，$w_(m n)$ 为噪声。该式与逆散射（inverse scattering）文献中的 Born/Distorted Born 思路一致，观测被解释为发射传播、散射和接收传播的组合 [Chew1990; Cui2001; Li2004; Persico2005]。

该式并非兼容层生成数据的前提。兼容层先生成全波数据，低阶模型随后用于解释和压缩全波数据中的结构。模型合法性由此得到全波数据的结构诊断支持，而不完全依赖先验假设。

=== 定位算法的数据入口

定位算法使用向量化后的散射快拍作为数据入口：

$ y = vec { Y_("scat")[m,n,k] } $

给定候选位置 $x_g$ 的响应向量 $h(x_g)$，构造字典

$ H = [ h(x_1), h(x_2), dots, h(x_G) ] $

稀疏或剖面似然定位问题可写为

$ y approx H beta + w $

背景残差存在时则写为

$ y approx H beta + c + w $

$H$ 可来自参考介质解析格林（Green）函数字典、一组全波候选仿真或二者结合的混合字典（hybrid dictionary）。兼容层产物的价值在于提供可检验的全波目标响应，使算法不再仅依赖自定义解析模型生成的合成数据。

=== 协方差与杂波建模的数据入口

对多个随机背景、介质扰动或目标缺失场景生成样本后，得到

$ y_s = vec { Y_s[m,n,k] } $

全波样本协方差估计为

$ hat(R)_c = 1/S sum_(s=1)^S (y_s - bar(y))(y_s - bar(y))^H $

该协方差可用于检验介质诱导杂波（medium-induced clutter）的跨 Tx、跨 Rx 和跨频结构，也可作为协方差感知检测（covariance-aware detection）、AMF 或稳健定位算法的外部对照。相比单纯解析协方差，全波样本协方差提供更高层级的仿真证据。

=== 与期刊方法论叙述的关系

兼容层与 gprMax 组合的方法论贡献可概括为三点。

第一，实现了一个严格索引的 FDA-MIMO-GPR 全波快拍生成流程，补齐公开 gprMax 工作中缺少的 FDA-MIMO acquisition geometry。

第二，通过体制无关的诊断确认生成数据至少满足 FDA 调度、MIMO 通道矩阵和 GPR 地下传播三项基本条件，避免将尚未公认的解析信号模型作为唯一合法性来源。

第三，输出原始（raw）、校准（calibrated）与散射（scatter）张量，使得快拍信号建模、定位算法、协方差分析和参考介质失配研究具有同一套可复现全波数据基础。



== 当前实现边界

当前代码实现的是理想化收发共址 TDM FDA-MIMO-GPR。它不声称模拟真实 T/R switch、环形器（circulator）、发射泄漏、接收饱和、多通道本振相噪、频率合成器误差、真实天线互耦（mutual coupling）或平台加载效应。这些因素属于后续硬件非理想层（hardware impairment layer）。

此外，短时窗快速场景可用于工程冒烟测试和目标/背景/散射链路验证，但若 FFT 分辨率不足或 gprMax 报告较高数值色散风险，则不应据此做强相位结论。长时窗、低数值色散、坐标量化误差可控的场景更适合支持 FDA 频谱分辨和相位结构分析。

= 参考文献

#par(leading: 0.45em)[
[Antonik2006] P. Antonik, M. C. Wicks, H. D. Griffiths, and C. J. Baker, “Frequency diverse array radars,” IEEE Radar Conference, 2006.
[Secmen2007] M. Secmen, S. Demir, A. Hizal, and T. Eker, “Frequency diverse array antenna with periodic time modulated pattern in range and angle,” IEEE Radar Conference, 2007.
[Wang2012] W.-Q. Wang, “Range-angle-dependent beamforming by frequency diverse array antenna,” International Journal of Antennas and Propagation, 2012.
[Xu2015] J. Xu, G. Liao, S. Zhu, L. Huang, and H. C. So, “Joint range and angle estimation using MIMO radar with frequency diverse array,” IEEE Transactions on Signal Processing, 2015.
[Xiong2018] J. Xiong, W.-Q. Wang, and K. Gao, “FDA-MIMO radar range-angle estimation: CRLB, MSE, and resolution analysis,” IEEE Transactions on Aerospace and Electronic Systems, 2018.
[Warren2016] C. Warren, A. Giannopoulos, and I. Giannakis, “gprMax: Open source software to simulate electromagnetic wave propagation for ground penetrating radar,” Computer Physics Communications, 2016.
[Giannopoulos2005] A. Giannopoulos, “Modelling ground penetrating radar by GprMax,” Construction and Building Materials, 2005.
[Giannakis2014] I. Giannakis and A. Giannopoulos, “A novel piecewise linear recursive convolution approach for dispersive media using the finite-difference time-domain method,” IEEE Transactions on Antennas and Propagation, 2014.
[Warren2019] C. Warren et al., “A CUDA-based GPU engine for gprMax: open source FDTD electromagnetic simulation software,” Computer Physics Communications, 2019.
[Chew1990] W. C. Chew and Y. M. Wang, “Reconstruction of two-dimensional permittivity distribution using the distorted Born iterative method,” IEEE Transactions on Medical Imaging, 1990.
[Cui2001] T. J. Cui, W. C. Chew, A. A. Aydiner, and S. Chen, “Inverse scattering of two-dimensional dielectric objects buried in a lossy earth using the distorted Born iterative method,” IEEE Transactions on Geoscience and Remote Sensing, 2001.
[Li2004] F. Li, Q. H. Liu, and L. Song, “Three-dimensional reconstruction of objects buried in layered media using Born and distorted Born iterative methods,” IEEE Geoscience and Remote Sensing Letters, 2004.
[Persico2005] R. Persico, D. Bernini, and F. Soldovieri, “The role of the measurement configuration in inverse scattering from buried objects under the Born approximation,” IEEE Transactions on Antennas and Propagation, 2005.
]
