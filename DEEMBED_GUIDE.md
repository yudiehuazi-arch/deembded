# RF-DeEmbed Studio | 网页版 S 参数去嵌专业工具平台

**RF-DeEmbed Studio** 是一款面向射频微波与高速数字互连（SI/PI）工程的专业网页版 S 参数去嵌（De-embedding）与校准分析工具。本工具严格遵循 **IEEE 370-2020** 行业标准协议，深度融合 **Keysight PLTS (Physical Layer Test System)** 的工程实践与核心算法，完整覆盖**单端去嵌、差分去嵌、单边去嵌与双边去嵌**四大核心应用场景。

---

## 目录
1. [核心架构与功能特性](#1-核心架构与功能特性)
2. [S 参数去嵌理论与数学公式推导](#2-s-参数去嵌理论与数学公式推导)
   - 2.1 传输矩阵（T-Matrix）级联代数与求逆
   - 2.2 单端 2-Port 去嵌矩阵公式
   - 2.3 差分 4-Port 广义传输矩阵推导
   - 2.4 单边去嵌与双边去嵌的数学定义
   - 2.5 非对称夹具去嵌（Fixture A ≠ Fixture B）数学原理
3. [差分混合模 S 参数（Mixed-Mode S-Parameters）](#3-差分混合模-s-参数mixed-mode-s-parameters)
4. [去嵌标准协议与 Keysight PLTS 对比](#4-去嵌标准协议与-keysight-plts-对比)
   - 4.1 IEEE 370-2020 标准协议解析
   - 4.2 Keysight PLTS AFR（自动夹具剥离）与非对称校正（Length A ≠ B & Match A ≠ B）
   - 4.3 差分端口映射规则（PLTS 交叉排布 vs 标准顺序排布）
5. [时域反射 TDR 与阻抗剖面（$Z(t)$）计算](#5-时域反射-tdr-与阻抗剖面zt计算)
6. [IEEE 370 Annex C 物理法则质量检验](#6-ieee-370-annex-c-物理法则质量检验)
7. [内置典型工程预设与一键演练](#7-内置典型工程预设与一键演练)
8. [Web 界面与交互操作说明](#8-web-界面与交互操作说明)

---

## 1. 核心架构与功能特性

```
+---------------------------------------------------------------------------------+
|                       RF-DeEmbed Studio Web Platform                            |
+---------------------------------------------------------------------------------+
|                                                                                 |
|  [前端展示层 (Frontend)]                                                        |
|  * 科学仪器风格暗色 UI (Keysight / R&S 风格)                                     |
|  * 动态拓扑示意图 (交互式高亮双边/单边去嵌参考面)                               |
|  * 交互式高分辨率图表:                                                           |
|    - 幅频响应 (Magnitude S-dB: S21, S11, SDD21, SDD11)                          |
|    - 相位与群时延 (Phase deg & Group Delay ps)                                  |
|    - 差分混合模 (SDD, SCC, SCD, SDC)                                            |
|    - 时域反射与阻抗剖面 (TDR Step & Z(t))                                       |
|    - 史密斯圆图 (Smith Chart)                                                   |
|  * Touchstone 文件拖拽解析与一键下载导出 (.s2p / .s4p)                           |
|                                                                                 |
|  [接口层 (Backend / FastAPI)]                                                   |
|  * 仅负责 HTTP、表单校验、内存缓存与 JSON 序列化                                 |
|  * routers/ 健康检查 / 识别 / 去嵌 / TDR；services/ 四个业务服务                  |
|  * schemas.py 以 TypedDict 固化响应契约；cache.py 提供 TTL + LRU 网络缓存         |
|                                                                                 |
|  [领域内核 (deembed / 与框架无关)]                                              |
|  * engine.py：prepare → strategy → quality 三段式流水线                          |
|  * strategies/：去嵌策略注册表（扩展点，新增算法无需改动 API 层）                 |
|  * fixtures/：IEEE 370 Annex A 2X Thru 劈半 (SE_NZC / MM_NZC) + 非对称修正        |
|  * matrices / frequency / mixed_mode / metrics / tdr / reporting：算法组件       |
|  * presets/：10 个内置合成示例；legacy.py：v1 函数式接口兼容层                    |
|  * 传输矩阵 (T-Matrix) 全矩阵求逆级联算法、广义混合模正交变换                     |
|    ($S_{mm} = M S M^{-1}$)、IFFT 加窗与 DC 外推阻抗、Annex C 质量检验             |
+---------------------------------------------------------------------------------+
```

### 1.1 代码结构与扩展点

前端为**原生 ES Module**（无构建步骤），后端为**分层 Python 包**，均避免单文件堆积：

| 目录 | 职责 | 典型扩展方式 |
| :--- | :--- | :--- |
| `deembed/strategies/` | 去嵌算法策略 | 实现 `DeembeddingStrategy` 并在 `default_strategies()` 注册 |
| `deembed/fixtures/` | 劈半与夹具修正 | 实现 `Nzc2xThruExtractor` 并加入 `EXTRACTORS` |
| `deembed/reporting.py`、`tdr.py` | 图表/时域数据构建 | 新增 `to_payload()` 报表对象 |
| `backend/services/`、`backend/routers/` | HTTP 编排 | 加服务 + 路由，注册到 `ALL_ROUTERS` |
| `backend/schemas.py` | 响应契约 | 先改 TypedDict，再改服务返回 |
| `static/js/controllers/` | 图表交互流程 | 继承 `ChartFlowController`（模式切换 + 请求竞态已内置） |
| `static/js/charts/` | 纯函数绘图与坐标 | 增加渲染/构建模块，`ChartPanel` 负责交互 |
| `static/js/ui/` | 面板渲染 | 只读写 DOM 与状态，不直接发起请求 |

测试：`python -m pytest`（139 项，领域 + HTTP 契约 + v1 兼容）与 `npm test`（56 项，前端纯函数 + 交互 + 集成）。

### 核心功能矩阵
| 功能维度 | 支持选项 | 说明 |
| :--- | :--- | :--- |
| **拓扑类型** | 单端 2-Port / 差分 4-Port | 支持 Touchstone `.s2p` 与 `.s4p` |
| **去嵌边选择** | **双边去嵌** / **单边左去嵌** / **单边右去嵌** | 用户可精准指定剥除哪一侧的测试夹具 |
| **去嵌算法** | 基于夹具文件 (File-Based) / 2X Thru AFR / 端口延伸 | 兼容 PLTS 参考面平移与 IEEE 370 2X Thru 规范 |
| **端口映射** | 标准顺序排布 [1,2->3,4] / PLTS 交叉排布 [1,3->2,4] | 彻底规避端口次序混乱引起的差分/共模错位 |
| **质量检验** | 无源性判定 ($\sigma \le 1.0$)、互易性残差、因果性评估 | 严格遵循 IEEE 370 Annex C 物理法则 |
| **数据输出** | 去嵌后 DUT Touchstone、提取的 1X 左右夹具、全频点 CSV | 一键生成并直接下载 |

---

## 2. S 参数去嵌理论与数学公式推导

### 2.1 传输矩阵（T-Matrix）级联代数与求逆
散射参数（S 参数）定义了端口反射波与入射波的线性关系：
$$\mathbf{b} = \mathbf{S} \cdot \mathbf{a}$$
当多个微波网络在物理上**级联（Cascade）**串联时，由于中间交界面的波满足 $\mathbf{b}_{out, A} = \mathbf{a}_{in, DUT}$ 和 $\mathbf{a}_{out, A} = \mathbf{b}_{in, DUT}$，S 矩阵本身无法直接相乘。

为此，引入**散射传输矩阵（Scattering Transfer Matrix，即 T 矩阵或波级联矩阵）**，它直接将输入端波向量与输出端波向量关联：
$$\begin{bmatrix} a_1 \\ b_1 \end{bmatrix} = \mathbf{T} \begin{bmatrix} b_2 \\ a_2 \end{bmatrix} = \begin{bmatrix} T_{11} & T_{12} \\ T_{21} & T_{22} \end{bmatrix} \begin{bmatrix} b_2 \\ a_2 \end{bmatrix}$$

对于由左夹具 $\mathbf{T}_A$、待测件 $\mathbf{T}_{DUT}$、右夹具 $\mathbf{T}_B$ 组成的整体复合网络，其级联关系满足优雅的矩阵相乘：
$$\mathbf{T}_{Total} = \mathbf{T}_A \cdot \mathbf{T}_{DUT} \cdot \mathbf{T}_B$$

### 2.2 单端 2-Port 去嵌矩阵公式
单端 2 端口 S 参数转 T 参数的互换关系式为：
$$T_{11} = \frac{1}{S_{21}}, \quad T_{12} = -\frac{S_{22}}{S_{21}}$$
$$T_{21} = \frac{S_{11}}{S_{21}}, \quad T_{22} = S_{12} - \frac{S_{11} S_{22}}{S_{21}}$$

逆变换（T 参数转 S 参数）：
$$S_{11} = \frac{T_{21}}{T_{11}}, \quad S_{12} = T_{22} - \frac{T_{21} T_{12}}{T_{11}}$$
$$S_{21} = \frac{1}{T_{11}}, \quad S_{22} = -\frac{T_{12}}{T_{11}}$$

### 2.3 差分 4-Port 广义传输矩阵推导
对于 4 端口差分网络，左侧 2 个端口为输入端，右侧 2 个端口为输出端。将 $4\times 4$ 的 S 矩阵按 $2\times 2$ 划分子块：
$$\mathbf{S} = \begin{bmatrix} \mathbf{S}_{LL} & \mathbf{S}_{LR} \\ \mathbf{S}_{RL} & \mathbf{S}_{RR} \end{bmatrix}$$
其中：
$$\mathbf{S}_{LL} = \begin{bmatrix} S_{11} & S_{12} \\ S_{21} & S_{22} \end{bmatrix}, \quad \mathbf{S}_{LR} = \begin{bmatrix} S_{13} & S_{14} \\ S_{23} & S_{24} \end{bmatrix}$$
$$\mathbf{S}_{RL} = \begin{bmatrix} S_{31} & S_{32} \\ S_{41} & S_{42} \end{bmatrix}, \quad \mathbf{S}_{RR} = \begin{bmatrix} S_{33} & S_{34} \\ S_{43} & S_{44} \end{bmatrix}$$

根据波向量方程可严密导出广义分块传输矩阵 $\mathbf{T}$：
$$\mathbf{T}_{11} = \mathbf{S}_{RL}^{-1}$$
$$\mathbf{T}_{12} = -\mathbf{S}_{RL}^{-1} \cdot \mathbf{S}_{RR}$$
$$\mathbf{T}_{21} = \mathbf{S}_{LL} \cdot \mathbf{S}_{RL}^{-1}$$
$$\mathbf{T}_{22} = \mathbf{S}_{LR} - \mathbf{S}_{LL} \cdot \mathbf{S}_{RL}^{-1} \cdot \mathbf{S}_{RR}$$

同样满足全矩阵相乘关系 $\mathbf{T}_{Total} = \mathbf{T}_A \cdot \mathbf{T}_{DUT} \cdot \mathbf{T}_B$。
由于该矩阵形式保留了全部非对角互阻抗项，**即使左夹具或右夹具内部存在极强的差分线对间耦合串扰（Crosstalk），通过该广义逆矩阵也能被 100% 精确消除**。

### 2.4 单边去嵌与双边去嵌的数学定义
根据线性代数求逆法则，针对不同工况，去嵌公式精准定义如下：

1. **双边去嵌（Double-Sided De-embedding: Both Left & Right）**：
   同时消除待测件两侧的夹具效应：
   $$\mathbf{T}_{DUT} = \mathbf{T}_A^{-1} \cdot \mathbf{T}_{Total} \cdot \mathbf{T}_B^{-1}$$

2. **单边左去嵌（Single-Sided: Left Only）**：
   测试中仅左侧包含夹具（例如使用单边同轴适配器、或探针测试左端，右端直连仪器标准端口）：
   $$\mathbf{T}_{DUT} = \mathbf{T}_A^{-1} \cdot \mathbf{T}_{Total}$$
   此时，保留待测件与右侧夹具的真实连接特性。

3. **单边右去嵌（Single-Sided: Right Only）**：
   仅右侧包含夹具效应：
   $$\mathbf{T}_{DUT} = \mathbf{T}_{Total} \cdot \mathbf{T}_B^{-1}$$

### 2.5 非对称夹具去嵌（Fixture A ≠ Fixture B）数学原理
在工程实际中，待测件两端的夹具经常无法做到镜像对称：
- **左右走线物理长度或时延不相等（Length A ≠ B）**：例如因测试板布局限制，左侧微带线长 12 mm，右侧微带线长 24 mm；
- **左右端接口连接器类型或阻抗不一致（Match A ≠ B）**：左端为 2.92 mm 高频测试座，右端为板载 SMA 或差分测试探针焊盘；
- **工艺制造公差造成的线宽与介电常数漂移**。

在此场景下，若仍假设 $\mathbf{T}_A = \mathbf{T}_B$（50%:50% 对称劈半），将引入严重的过补偿或欠补偿失真。针对 **Fixture A ≠ B**，本工具提供两种标准解决途径：

#### 途径一：独立双夹具文件去嵌（Separate Fixture Files）
用户分别提供左夹具 $\mathbf{T}_A$ 与右夹具 $\mathbf{T}_B$ 的实测或仿真文件，双边去嵌直接按独立求逆执行：
$$\mathbf{T}_{DUT} = \mathbf{T}_A^{-1} \cdot \mathbf{T}_{Total} \cdot \mathbf{T}_B^{-1} \quad (\mathbf{T}_A \neq \mathbf{T}_B)$$

#### 途径二：Keysight PLTS 风格 2X Thru 非对称校正（Length A ≠ B & Match A ≠ B）
当用户只有一条定长 2X Thru 标准件（总时延 $\tau_{2X}$）时：
1. **长度/时延比例分配（Length A ≠ B）**：
   设定左侧占比 $k_A = L_A / L_{total}$ 与右侧占比 $k_B = 1 - k_A$。则相对于对称劈半（$50\%$）的时延偏差为：
   $$\Delta \tau_A = (k_A - 0.5) \cdot \tau_{2X}, \quad \Delta \tau_B = (k_B - 0.5) \cdot \tau_{2X}$$
   利用 2X Thru 提取的复传播常数 $\gamma(f) = \alpha(f) + j\beta(f)$ 对标称劈半模型进行非对称重构：
   $$S_{21, A}(f) = S_{21, nom}(f) \cdot e^{-\gamma(f) \cdot \Delta L_A}$$
   $$S_{21, B}(f) = S_{21, nom}(f) \cdot e^{-\gamma(f) \cdot \Delta L_B}$$
2. **发射端反射分别提取（Match A ≠ B）**：
   时域门限直接从整体测量值 $S_{11, Total}$ 提取左侧夹具发射端反射 $S_{11, A}$，从 $S_{22, Total}$ 提取右侧夹具发射端反射 $S_{22, B}$，彻底消除两端接头失配差异。

---

## 3. 差分混合模 S 参数（Mixed-Mode S-Parameters）

在高速差分互连中，单端 S 参数无法直观表达差模与共模信号的传输特性。通过正交模态转换矩阵 $\mathbf{M}$，将单端参数变换为混合模参数：
$$\mathbf{S}_{mm} = \mathbf{M} \cdot \mathbf{S}_{se} \cdot \mathbf{M}^{-1}$$

对于标准顺序端口 [1, 2 为输入差分对，3, 4 为输出差分对]，转换矩阵为：
$$\mathbf{M} = \frac{1}{\sqrt{2}} \begin{bmatrix} 
1 & -1 & 0 & 0 \\
0 & 0 & 1 & -1 \\
1 & 1 & 0 & 0 \\
0 & 0 & 1 & 1
\end{bmatrix}$$

转换后得到标准的混合模分块矩阵：
$$\mathbf{S}_{mm} = \begin{bmatrix} 
\mathbf{S}_{DD} & \mathbf{S}_{DC} \\ 
\mathbf{S}_{CD} & \mathbf{S}_{CC} 
\end{bmatrix} = \begin{bmatrix} 
SDD_{11} & SDD_{12} & SDC_{11} & SDC_{12} \\
SDD_{21} & SDD_{22} & SDC_{21} & SDC_{22} \\
SCD_{11} & SCD_{12} & SCC_{11} & SCC_{12} \\
SCD_{21} & SCD_{22} & SCC_{21} & SCC_{22}
\end{bmatrix}$$

### 关键工程参数解读：
- **$SDD_{21}$（差模插入损耗）**：高速差分信号的有效传输通道衰减。去嵌后，夹具的介质损耗与导体趋肤效应损耗被剥除，曲线显著上抬，真实展示 DUT 的高频带宽。
- **$SDD_{11}$（差模回波损耗）**：差分输入阻抗匹配程度。
- **$SCD_{21}$（模态转换 Differential to Common）**：差模信号转换为共模噪声的幅度，是衡量走线非对称性（Asymmetry/Skew）和 EMI 电磁辐射的核心指标。
- **$SCC_{21}$（共模插入损耗）**：共模噪声在通道中的透射能力。

---

## 4. 去嵌标准协议与 Keysight PLTS 对比

### 4.1 IEEE 370-2020 标准协议解析
IEEE 370 是针对 50 GHz 高速 PCB 与互连去嵌的权威国际标准，核心包括：
- **Annex A: 2X Thru 剥离算法（Bifurcation Method）**：
  在 PCB 上加工一条由两个对称半夹具背靠背直连的测试线（2X Thru，即 FIX-FIX）。
  - **NZC（Non-Zero-Length Thru）**：通过时域冲激响应群时延计算一半时延 $\tau_{1X} = \frac{1}{2} \tau_{2X}$，利用时域门限法剥离反射与传输，生成左 1X 夹具与右 1X 夹具。
  - **ZC（Impedance Correction）**：通过待测件阶跃阻抗迭代校正 2X Thru 标准件与实际走线之间的工艺阻抗偏差。
- **Annex B: 1X Reflect（Open / Short）**：
  在夹具末端设计开路（Open）或短路（Short）参考面，利用单端反射剥除时延。
- **Annex C: 质量验证指标（Quality Metrics）**：
  对去嵌后纯净 DUT 的物理可信度进行严苛筛查。

### 4.2 Keysight PLTS AFR（自动夹具剥离）对比
是德科技（Keysight）PLTS 软件在业界被广泛用于高速测试夹具去嵌。本工具在算法与操作体验上高度对标 PLTS：
1. **AFR 模式对标**：本工具的 `IEEE 370 2X Thru` 模式完全对应 PLTS 的 `Automatic Fixture Removal (AFR) 2X Thru Wizard`。
2. **参考面平移对标**：本工具的 `File-Based` 模式对应 PLTS 的 `Reference Plane Adjustment`，支持直接输入左/右夹具文件进行 T 矩阵消去。
3. **单边/双边自由控制**：PLTS 允许用户勾选 "Port 1 Correct" 或 "Port 2 Correct"，本工具提供一键切换【双边去嵌】、【单边左去嵌】、【单边右去嵌】。

### 4.3 差分端口映射规则
不同仪器厂商和软件对 4 端口差分测试文件的端口定义存在经典差异：
- **PLTS 交叉排布（PLTS Crossed）**：
  - 左侧差分对：端口 1（正极），端口 3（负极）
  - 右侧差分对：端口 2（正极），端口 4（负极）
- **标准顺序排布（Sequential）**：
  - 左侧差分对：端口 1（正极），端口 2（负极）
  - 右侧差分对：端口 3（正极），端口 4（负极）

本工具在界面中内置了端口映射下拉选择器与动态连线图示，后端自动执行矩阵索引重排（Renumbering），从根本上杜绝了差分/共模计算错乱的问题。

---

## 5. 时域反射 TDR 与阻抗剖面（$Z(t)$）计算

为了让工程师直观观察夹具去除的效果，本工具提供了完整的时域反射计（TDR）与瞬时特征阻抗剖面算法：
1. **频域扩展与 DC 外推**：利用 Hermite 对称性和低频插值补齐至 0 Hz（DC 点）。
2. **汉宁加权窗函数（Hann Window）**：对高频截断边缘进行平滑衰减，有效消除 IFFT 带来的吉布斯振荡（Gibbs Ringing）。
3. **快速傅里叶反变换（IFFT）**：求解时域冲激响应 $h(t)$ 与阶跃响应 $V_{step}(t) = \int_0^t h(\tau) d\tau$。
4. **瞬时阻抗剖面公式**：
   $$Z(t) = Z_0 \cdot \frac{1 + \rho(t)}{1 - \rho(t)} = Z_0 \cdot \frac{1 + V_{step}(t)}{1 - V_{step}(t)}$$
   （对于差分系统，$Z_{diff}(t) = 2 \cdot Z(t)$，基准为 $100\,\Omega$）。

**去嵌直观效果**：
在去嵌前的时域波形上，可以清晰看到左夹具约 150~200 ps 的传输时延以及连接器的阻抗尖峰；**去嵌完成后，时延被精准剥除，DUT 的特征阻抗直接从 $t = 0\,\text{ns}$ 处起始**，证明参考面已精准平移至待测芯片管脚或连接器界面！

---

## 6. IEEE 370 Annex C 物理法则质量检验

去嵌过程涉及矩阵求逆与数值外推，不良的测量噪声或夹具模型偏差可能导致非物理伪影。本工具自动执行以下物理法则检验：

1. **无源性检验（Passivity Check）**：
   根据能量守恒定律，无源网络不能向外界无中生有产生能量。在任意频率 $f$ 下，散射矩阵的最大奇异值 $\sigma_{max}(\mathbf{S})$ 必须满足：
   $$\sigma_{max}(\mathbf{S}(f)) \le 1.0$$
   即矩阵 $\mathbf{I} - \mathbf{S}^\dagger \mathbf{S}$ 必须为半正定矩阵。
   - 若 $\sigma_{max} \le 1.005$（允许微小浮点容限），判定为 **PASS**；
   - 若超标，系统将高亮红色警示，提示夹具损耗过度去嵌。

2. **互易性检验（Reciprocity Check）**：
   对于非铁氧体的无源对称各向同性器件，传输必须对称：
   $$S_{ij}(f) = S_{ji}(f)$$
   系统统计全频段最大非对称误差 $\max |S_{ij} - S_{ji}|$，残差低于 $0.05$ 判定合格。

3. **因果性检验（Causality Check）**：
   根据 Kramers-Kronig 关系，时域响应在输入信号到达前（$t < 0$）必须恒等于 0。系统计算非因果区能量占比以评估去嵌质量。

---

## 7. 内置典型工程预设与一键演练

为便于用户立即体验，工具内置了 4 个典型工业级工程预设：

1. **预设 1: 单端 2-Port 夹具测量去嵌 (File-Based S2P)**
   - 拓扑: 单端 2-Port，0.1 ~ 20.0 GHz。
   - 场景: 包含 SMA 接头寄生电容（0.08 pF）与微带线损耗的夹具，中间连接 20 mm 待测走线。
   - 演示效果: 去嵌后 $S_{21}$ 插入损耗完全恢复，回波损耗消除接头反射。

2. **预设 2: 单端 IEEE 370 2X Thru 自动劈半去嵌 (AFR S2P)**
   - 场景: 用户仅有一条 2X Thru 走线测量文件与整体测量文件。
   - 演示效果: 自动劈半生成 1X 左夹具与 1X 右夹具，去嵌后残差 $< 0.05\%$。

3. **预设 3: 差分 4-Port 全耦合夹具去嵌 (File-Based S4P)**
   - 场景: 4 端口差分对互连，包含线间耦合串扰。
   - 演示效果: SDD21 插入损耗改善，时延完全去除，清晰展示 SCD21 模式转换。

4. **预设 4: 差分 4-Port IEEE 370 2X Thru 混合模 AFR 去嵌**
   - 场景: 4 端口差分 2X Thru 标准件，支持 PLTS 交叉端口与顺序端口。

---

## 8. Web 界面与交互操作说明

1. **运行环境**：
   - 服务已在本地 `http://0.0.0.0:8000` 启动，并在用户界面作为实时预览（Live Preview）展示。
2. **快速上手三步曲**：
   - **第一步**：在左侧【典型工程预设示例】下拉框中选择示例，点击【载入预设】（如首选推荐的“单端/差分独立双 2X Thru 分别劈半”），或直接拖拽本地 `.s2p` / `.s4p` 文件到上传区；
   - **第二步**：在【去嵌作用边】中切换 **双边去嵌**、**单边左去嵌** 或 **单边右去嵌**，观察下方拓扑图的动态参考面变化；
   - **第三步**：点击大按钮 **⚡ 执行去嵌计算**，右侧大屏即刻更新幅频曲线、相位时延、混合模、时域 TDR、史密斯圆图与质量校验分数。

3. **三区域参数手动调取系统 (Three-Region S-Parameter Recall Engine)**：
   图表分析区划分为清晰解耦的三个区域，支持针对任意网络手动输入调取所需的 S 参数代码（如 4 端口模式下可自由输入 `S11`, `SDD21`, `SCD21`, `SCC21`, `S21`, `S31` 等，用逗号或空格分隔）：
   - **区域一：DUT 去嵌前 (Total / 原始测量)**：
     - 支持独立开关控制启用/隐藏。
     - 手动输入框自由输入任意待分析 S 参数（如 `SDD21, SDD11`）。
     - 提供快捷标签一键点选添加或移除（`SDD21`, `SDD11`, `SDD22`, `SCD21`, `SDC21`, `SCC21`, `S11`, `S21` 等）。
     - 曲线以优雅虚线绘制，直观展现夹具未剥离时的原始测量衰减。
   - **区域二：DUT 去嵌后 (De-embedded DUT / 纯净器件)**：
     - 支持独立开关控制启用/隐藏。
     - 手动输入框自由调取去嵌后的目标参数（如 `SDD21, SDD11, SCD21`）。
     - 曲线以高亮粗实线绘制，直观凸显纯净器件的高频传输与匹配性能。
   - **区域三：去嵌夹具 (Fixtures: 1X & 2X)**：
     - 支持独立开关控制启用/隐藏。
     - 自由勾选作用夹具对象（`1X Fix A (左夹具)`, `1X Fix B (右夹具)`, `2X Thru A`, `2X Thru B`）。
     - 手动输入框调取指定夹具的 S 参数（如 `SDD21`, `S11`, `S21`, `SCD21` 等）。
     - 曲线以点划线绘制，直观验证夹具提取的对称性与劈半守恒关系。
   - **下方常用组合模版**：
     - `⚡ 去嵌前后插损对比`：快速同时调出去嵌前后的 SDD21/S21。
     - `↩️ 插损 + 回损全貌`：同时调出 SDD21 + SDD11。
     - `🔄 模态转换深度分析`：调出 SDD21 + SCD21 + SCC21，评估差分对失衡。
     - `🎛️ 夹具劈半前后校验`：调出 1X 夹具 vs 2X Thru 标准件插损与回损。
     - `🗑️ 清空所有曲线`：一键重置清空。

4. **宽频自适应与 67 GHz 毫米波支持 (Broadband Auto-Scaling)**：
   - 系统支持从 10 MHz 直达 **67.0 GHz**（涵盖 1.85mm VNA 同轴接头、PCIe 5.0/6.0、56G/112G PAM4 乃至 V-Band 毫米波全频段）；
   - S 参数曲线坐标轴完全按导入文件频宽动态自适应展开，无任何人为 20 GHz 截断；
   - 右上方提供 `🔍 全频自适应` 与 `重置缩放` 快捷控件，随时恢复全频段宏观全貌。

5. **标频 Mark 点分析系统 (RF Marker Analysis System)**：
   - **交互式光标吸附**：鼠标直接点击图表曲线任意位置，当前选中的活动 Mark 点将即刻以高精度吸附至光标频点；
   - **多标记点管理**：支持添加 `M1`, `M2`, `M3`, `M4` 等多个独立标记，并可在表格中手动键入任意精确数值（如 `28.000 GHz` 或 `53.125 GHz`）；
   - **🎯 寻峰值 (Peak Search) 与 📉 寻谷底 (Valley Search)**：一键沿当前活动主曲线快速定位谐振峰点或极小谷底点；
   - **Δ 相对差值模式 (Delta Mode)**：开启后自动计算 $M_2 - M_1$ 的频差 $\Delta f$、去嵌后插损差以及去嵌前后改善量差值 $\Delta \text{Gain}$；
   - **高频标准特征频点快速直达**：提供 `10.0 GHz`、`16.0 GHz (PCIe 5.0)`、`28.0 GHz (56G PAM4)`、`32.0 GHz (PCIe 6.0)`、`53.1 GHz (112G PAM4)` 和 `67.0 GHz (VNA Max)` 快捷 Chip 按钮；
   - **动态响应报表**：Mark 点表格动态生成当前图表上绘制的所有曲线对应频点的精确 dB 读数，并自动计算去嵌净增益 $\Delta \text{Gain} = \text{DUT} - \text{Total}$。

6. **导出文件**：
   - 切换到【数据导出与下载】标签页，可一键下载标准 Touchstone（`.s2p` / `.s4p`）格式的去嵌后 DUT 文件、拆分提取的 1X 夹具文件，以及全频点 CSV 报表。
