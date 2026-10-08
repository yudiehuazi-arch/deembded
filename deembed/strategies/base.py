"""去嵌策略接口（引擎的扩展点）。

一个策略负责回答：**“左右 1X 夹具模型从哪里来？”**

* :class:`~deembed.strategies.two_x_thru.DualTwoXThruStrategy` —— 两条 2X Thru 分别劈半；
* :class:`~deembed.strategies.two_x_thru.SingleTwoXThruStrategy` —— 单条 2X Thru 对称劈半；
* :class:`~deembed.strategies.fixture_files.FixtureFileStrategy` —— 用户直接给出左右 1X 夹具文件；
* :class:`~deembed.strategies.port_extension.PortExtensionStrategy` —— 无夹具文件的时延/损耗剥离。

新增方法只需继承 :class:`DeembeddingStrategy` 并注册：
``engine.register_strategy(MyStrategy())``。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import skrf as rf

from ..models import DeembedSide, FixtureCorrection, FixtureMethod, FixturePair, FixtureStandardSet, PortExtensionSettings

__all__ = ["StrategyContext", "StrategyResult", "DeembeddingStrategy"]


@dataclass(frozen=True)
class StrategyContext:
    """策略执行所需上下文（已重归一化、已对齐频段、端口已统一排列）。"""

    total: rf.Network
    standards: FixtureStandardSet
    z0: float = 50.0
    side: DeembedSide = DeembedSide.BOTH
    correction_a: FixtureCorrection = FixtureCorrection()
    correction_b: FixtureCorrection = FixtureCorrection()
    port_extension: PortExtensionSettings | None = None

    @property
    def nports(self) -> int:
        return int(self.total.nports)


@dataclass(frozen=True)
class StrategyResult:
    """策略输出。``fixtures`` 为 ``None`` 表示该方法不产生夹具模型（如端口延伸）。"""

    dut: rf.Network
    fixtures: FixturePair | None = None


class DeembeddingStrategy(ABC):
    """夹具建模 + 级联反演策略。"""

    #: 与 ``FixtureMethod`` 对应的标识
    method: FixtureMethod

    @abstractmethod
    def apply(self, context: StrategyContext) -> StrategyResult:  # pragma: no cover - 抽象方法
        raise NotImplementedError

    def describe(self) -> str:
        """用于健康检查 / 前端展示的方法说明。"""

        return self.method.value
