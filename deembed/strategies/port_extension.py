"""端口延伸策略：不做夹具文件剥离，只补偿时延与损耗。"""

from __future__ import annotations

from ..errors import InvalidInputError
from ..fixtures.corrections import port_extension
from ..models import FixtureMethod, PortExtensionSettings
from .base import DeembeddingStrategy, StrategyContext, StrategyResult

__all__ = ["PortExtensionStrategy"]


class PortExtensionStrategy(DeembeddingStrategy):
    """按左右两侧的时延/损耗直接补偿测量参考面。"""

    method = FixtureMethod.PORT_EXTENSION

    def describe(self) -> str:
        return "端口延伸（时延 / 损耗剥离，无夹具文件）"

    def apply(self, context: StrategyContext) -> StrategyResult:
        settings = context.port_extension or PortExtensionSettings()
        if not any(
            abs(value) > 0
            for value in (settings.delay_ps_left, settings.delay_ps_right, settings.loss_db_left, settings.loss_db_right)
        ) and context.side is not None:
            raise InvalidInputError("端口延伸至少需要设置一个非零的时延或损耗。")

        return StrategyResult(dut=port_extension(context.total, settings, side=context.side), fixtures=None)
