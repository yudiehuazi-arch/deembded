# RF De-embedding Workbench

基于 scikit-rf 的 S 参数去嵌网页工作台：上传 `Total`、`2X Thru A`、`2X Thru B` 三份 Touchstone，
分别劈半提取左右 1X 夹具，再对单端 S2P 或差分 S4P 网络做双边/单边去嵌，并支持混合模参数对比、
TDR 阶跃阻抗、无源性/互易性诊断与 Touchstone 导出。

## 启动

```bash
python -m pip install -r requirements.txt      # 运行依赖
python run_server.py                           # 默认 0.0.0.0:8000
```

浏览器打开 `http://localhost:8000`。环境变量：`DEEMBED_HOST` / `DEEMBED_PORT` / `DEEMBED_LOG_LEVEL`。

## 输入

- `Total`：Fixture A + DUT + Fixture B 的整体测量网络。
- `2X Thru A` / `2X Thru B`：左右两侧的背靠背校准标准件。
- 支持 S2P / S4P Touchstone。三份文件端口数必须一致；频率网格可以不同，服务端会取共同频段对齐。
- 差分 S4P 支持自动检测、标准顺序（[1,2 → 3,4]）与 PLTS 交叉（[1,3 → 2,4]）端口映射。
- 差分劈半算法（表单字段 `split_algorithm`）：`mc_nzc`（默认，混合模 NZC + 模式转换，夹具模型保留 SDC/SCD，
  对应 PLTS 2019+ AFR 的 Mode Conversion）或 `classic_nzc`（IEEE 370 经典 MM-NZC，丢弃模式转换）。
  与 PLTS 结果的差异排查见 `DEEMBED_GUIDE.md` §4.4–4.5。

## 输出

- 去嵌后的 DUT Touchstone（`.s2p` / `.s4p`）。
- 从 2X Thru 劈半得到的左右 1X 夹具文件。
- 差分 S4P 额外给出另一种劈半算法的 DUT（`dut_alt`，结果图“DUT · 对照算法”曲线，可下载），以及模式转换诊断：
  2X Thru A/B 与 DUT 的 P/N skew、`max |SCD21|,|SDC21|`、两种算法的 ΔSDD21。
- 自定义 S 参数幅度对比图、TDR 阶跃阻抗、无需导出的无源性/互易性诊断。

已解析网络会在服务进程内临时缓存最多 10 分钟，供后续计算与 TDR 复用；原始 Touchstone 不做长期存储，
服务重启即清空。质量指标是诊断提示，不能替代工程验证。

## 代码结构

```
deembed/                 # 与 Web 框架解耦的领域内核（可直接被脚本/CLI 复用）
├── engine.py            # DeembeddingEngine：prepare → strategy → quality 流水线
├── strategies/          # 去嵌策略（扩展点）：dual/single 2X Thru、夹具文件、端口延伸
├── fixtures/            # IEEE 370 Annex A 劈半与非对称（时延/损耗）修正
├── touchstone.py        # Touchstone 编解码与端口数校验
├── frequency.py         # 共同频段对齐、参考阻抗归一化与重采样
├── matrices.py          # S ↔ T 矩阵代数与级联反演
├── mixed_mode.py        # SDD/SCC/SCD/SDC 混合模转换
├── metrics.py           # IEEE 370 Annex C 无源性/互易性指标
├── reporting.py         # 预览曲线、结果图表、夹具诊断数据构建
├── tdr.py               # 时域阶跃阻抗（TDR）
├── presets/             # 10 个内置合成示例（演示与测试数据源）
├── legacy.py            # v1 函数式接口兼容层（单一实现，仅做名字/签名适配）
└── errors.py, models.py # 领域错误与数据模型（请求 / 结果 / 枚举）

backend/                 # FastAPI 服务层（只负责 HTTP、表单、缓存、序列化）
├── main.py              # create_app()：装配应用、路由、中间件
├── app.py               # 兼容入口（backend.main:app 的别名）
├── routers/             # health / inspection / deembedding / tdr 路由
├── services/            # 4 个业务服务：识别、去嵌、TDR、导出
├── schemas.py           # 响应结构（TypedDict 契约）
├── uploads.py, cache.py, config.py, dependencies.py, exceptions.py
└── deembed_engine.py    # v1 兼容入口（重导出 deembed.legacy）

static/                  # 前端（原生 ES Module，无构建步骤）
├── index.html
├── css/base.css, css/style.css
└── js/
    ├── main.js               # 入口：DOMContentLoaded → Workbench
    ├── workbench.js          # 组合根：文件 → 识别 → 去嵌 → 结果的主流程
    ├── controllers/          # ChartFlowController（抽象基类）+ Input/Result 图表流程
    ├── charts/               # 画布渲染、坐标换算、Y 轴范围、曲线构造、TDR 裁剪、ChartPanel
    ├── core/                 # api / state / storage / params / format / dom 工具
    ├── ui/                   # 上传、端口映射、快捷参数、图例、读数、状态栏、结果摘要、TDR 控件
    └── config/constants.js   # 颜色、标签、限制、API 路径
```

分层约定：`static/js` 只通过 HTTP 接口与后端交互；`backend` 不实现算法，只编排 `deembed`；
`deembed` 不 import FastAPI，也不读写请求对象。

## 测试

```bash
python -m pytest                       # 139 项后端/领域测试
npm install                            # 仅前端测试需要（jsdom）
npm test                               # 56 项前端测试（node:test + jsdom）
```

- `tests/`：矩阵与频域、端口映射、预设目录、引擎端到端、图表/指标构建、TDR、缓存、HTTP 契约、v1 兼容层。
- `tests/js/`：画布几何、坐标与缩放、TDR 裁剪、曲线构造、API 客户端、ChartPanel 交互、
  Workbench 集成（用真实 `static/index.html` + 真实接口响应样本驱动完整流程）。
- `tests/js/fixtures/generate_api_fixtures.py`：从内置预设重新生成前端测试用的真实接口响应。

## 扩展点

| 需求 | 落点 |
| :--- | :--- |
| 新增去嵌算法 | 实现 `deembed/strategies/base.py` 的 `DeembeddingStrategy`，在 `default_strategies()` 注册 |
| 新增夹具劈半方式 | 实现 `Nzc2xThruExtractor` 并加入 `EXTRACTORS` |
| 新增图表类型 | 在 `static/js/charts/` 增加纯函数构建器，控制器继承 `ChartFlowController` |
| 新增 HTTP 能力 | 在 `backend/services/` 加服务，在 `backend/routers/` 加路由并注册到 `ALL_ROUTERS` |
| 新增响应字段 | 先改 `backend/schemas.py` 的 TypedDict 契约，再改服务返回 |
| 新增领域错误 | 在 `deembed/errors.py` 定义 `ErrorCode`，在 `backend/exceptions.py` 映射 HTTP 状态码 |

## v1 兼容

历史脚本里的 `from backend.deembed_engine import dual_2xthru_deembed_2port` 等函数式接口仍然可用
（见 `deembed/legacy.py`），数值结果与 v1 逐项对齐；新代码建议直接使用 `deembed` 包的类接口。
