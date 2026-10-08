"""去嵌策略注册表。

``default_strategies()`` 返回内置方法集合，``DeembeddingEngine`` 以此
初始化；运行时可通过 ``engine.register_strategy(custom)`` 追加。
"""

from __future__ import annotations

from typing import Final, Mapping

from ..models import FixtureMethod
from .base import DeembeddingStrategy, StrategyContext, StrategyResult
from .fixture_files import FixtureFileStrategy
from .port_extension import PortExtensionStrategy
from .two_x_thru import DualTwoXThruStrategy, SingleTwoXThruStrategy

__all__ = [
    "DeembeddingStrategy",
    "StrategyContext",
    "StrategyResult",
    "DualTwoXThruStrategy",
    "SingleTwoXThruStrategy",
    "FixtureFileStrategy",
    "PortExtensionStrategy",
    "default_strategies",
]

_STRATEGY_TYPES: Final[tuple[type[DeembeddingStrategy], ...]] = (
    DualTwoXThruStrategy,
    SingleTwoXThruStrategy,
    FixtureFileStrategy,
    PortExtensionStrategy,
)


def default_strategies() -> Mapping[FixtureMethod, DeembeddingStrategy]:
    """内置策略实例表（每个方法一个无状态实例，可安全共享）。"""

    return {strategy_type.method: strategy_type() for strategy_type in _STRATEGY_TYPES}
