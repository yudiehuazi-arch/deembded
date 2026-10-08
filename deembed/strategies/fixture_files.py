"""File-Based 去嵌策略：直接使用用户提供的左右 1X 夹具文件。"""

from __future__ import annotations

from ..errors import InvalidInputError
from ..matrices import deembed_network
from ..models import FixtureMethod, FixturePair
from .base import DeembeddingStrategy, StrategyContext, StrategyResult

__all__ = ["FixtureFileStrategy"]


class FixtureFileStrategy(DeembeddingStrategy):
    """对应 PLTS 的 Reference Plane Adjustment / T 矩阵级联反演。

    ``side=both`` 时要求左右夹具齐全；单边去嵌允许只提供一侧。
    """

    method = FixtureMethod.FIXTURE_FILES

    def describe(self) -> str:
        return "夹具文件直接级联反演（PLTS 参考面平移）"

    def apply(self, context: StrategyContext) -> StrategyResult:
        left = context.standards.fix_a
        right = context.standards.fix_b
        if left is None and right is None:
            raise InvalidInputError("File-Based 去嵌需要至少一个 1X 夹具文件。")
        for label, fixture in (("左夹具", left), ("右夹具", right)):
            if fixture is not None and fixture.nports != context.nports:
                raise InvalidInputError(f"{label}的端口数与 Total 不一致，请检查文件。")

        dut = deembed_network(context.total, left=left, right=right, side=context.side)
        fixtures = FixturePair(left=left, right=right) if left is not None and right is not None else None
        return StrategyResult(dut=dut, fixtures=fixtures)
