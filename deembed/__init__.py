"""deembed —— 与 Web 框架解耦的 S 参数去嵌内核。

分层：

```
deembed/
├── touchstone.py       Touchstone 编解码
├── frequency.py        频率网格对齐 / 参考阻抗归一化
├── matrices.py         S ↔ T 矩阵代数与级联反演
├── port_mapping.py     差分端口映射约定
├── mixed_mode.py       混合模（SDD/SCC/SCD/SDC）转换
├── metrics.py          IEEE 370 Annex C 质量指标
├── reporting.py        图表/预览/夹具诊断数据
├── diagnostics.py      差分 skew / 模式转换诊断与劈半算法对照
├── tdr.py              时域反射阶跃阻抗
├── fixtures/           2X Thru 劈半（经典 NZC / 含模式转换）与非对称校正
├── strategies/         可插拔去嵌策略（扩展点）
├── engine.py           引擎门面：prepare → strategy → quality
└── presets/            内置合成示例（演示与测试）
```

上层（``backend`` 包）只负责 HTTP、表单校验、缓存与序列化。
"""

from __future__ import annotations

import warnings

# skrf 的 NZC 劈半在做内部插值时会对非均匀频率网格发出 RuntimeWarning，
# 该插值是其实现的一部分（结果会再插值回原网格），不影响计算正确性。
# 与历史版本保持一致，集中在此处静音，避免污染服务日志。
warnings.filterwarnings("ignore", category=RuntimeWarning, module="skrf")

from . import legacy
from .engine import DeembeddingEngine, PreparedNetworks, build_default_engine, shared_engine
from .errors import (
    CacheExpiredError,
    ComputationError,
    DeembedError,
    ErrorCode,
    FileTooLargeError,
    FrequencyGridError,
    InvalidInputError,
    UnsupportedPortCountError,
)
from .metrics import QualityAnalyzer
from .mixed_mode import MixedModeConverter
from .models import (
    DcMethod,
    DeembedOutcome,
    DeembedRequest,
    DeembedSide,
    FixtureCorrection,
    FixtureMethod,
    FixturePair,
    FixtureStandardSet,
    NetworkTriplet,
    PortExtensionSettings,
    PortMapping,
    QualityReport,
    SplitAlgorithm,
    TdrWindow,
)
from .diagnostics import ModeConversionDiagnostics, build_mode_conversion_diagnostics, estimate_pn_skew_ps
from .port_mapping import auto_detect_port_mapping, mapping_label, pair_labels, resolve_port_mapping
from .reporting import ChartDataBuilder, FixtureStatisticsAnalyzer, NetworkPreviewBuilder
from .tdr import TdrAnalyzer, TdrSettings, TdrStack, TdrTrace
from .touchstone import TouchstoneCodec, network_from_text, network_to_text

__version__ = "2.0.0"

__all__ = [
    "__version__",
    # 引擎与请求模型
    "DeembeddingEngine",
    "PreparedNetworks",
    "build_default_engine",
    "shared_engine",
    "DeembedRequest",
    "DeembedOutcome",
    "NetworkTriplet",
    "FixturePair",
    "FixtureStandardSet",
    "FixtureCorrection",
    "PortExtensionSettings",
    "QualityReport",
    "QualityAnalyzer",
    # 枚举
    "DeembedSide",
    "FixtureMethod",
    "SplitAlgorithm",
    "PortMapping",
    "TdrWindow",
    "DcMethod",
    # 组件
    "TouchstoneCodec",
    "network_from_text",
    "network_to_text",
    "MixedModeConverter",
    "TdrAnalyzer",
    "TdrSettings",
    "TdrStack",
    "TdrTrace",
    "NetworkPreviewBuilder",
    "ChartDataBuilder",
    "FixtureStatisticsAnalyzer",
    "ModeConversionDiagnostics",
    "build_mode_conversion_diagnostics",
    "estimate_pn_skew_ps",
    "auto_detect_port_mapping",
    "resolve_port_mapping",
    "pair_labels",
    "mapping_label",
    # 错误
    "DeembedError",
    "ErrorCode",
    "InvalidInputError",
    "UnsupportedPortCountError",
    "FrequencyGridError",
    "FileTooLargeError",
    "CacheExpiredError",
    "ComputationError",
    # v1 兼容层（函数式接口）
    "legacy",
]
