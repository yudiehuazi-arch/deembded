"""基于 IEEE 370 2X Thru 标准件的去嵌策略。"""

from __future__ import annotations

from typing import Mapping

import skrf as rf

from ..errors import InvalidInputError
from ..fixtures.corrections import adjust_fixture_delay_loss
from ..fixtures.nzc_2xthru import EXTRACTORS, Nzc2xThruExtractor, get_extractor
from ..matrices import deembed_network
from ..models import FixtureMethod, FixturePair
from .base import DeembeddingStrategy, StrategyContext, StrategyResult

__all__ = ["DualTwoXThruStrategy", "SingleTwoXThruStrategy"]


class _TwoXThruStrategyBase(DeembeddingStrategy):
    """2X Thru 策略公共逻辑：劈半 → 非对称校正 → 级联反演。"""

    def __init__(self, extractors: Mapping[int, Nzc2xThruExtractor] | None = None) -> None:
        self.extractors = dict(extractors or EXTRACTORS)

    def extractor_for(self, nports: int) -> Nzc2xThruExtractor:
        extractor = self.extractors.get(nports)
        if extractor is None:
            return get_extractor(nports)
        return extractor

    def apply(self, context: StrategyContext) -> StrategyResult:  # pragma: no cover - 由子类覆盖
        raise NotImplementedError

    def _finalize(self, context: StrategyContext, fixtures: FixturePair) -> StrategyResult:
        dut = deembed_network(context.total, left=fixtures.left, right=fixtures.right, side=context.side)
        return StrategyResult(dut=dut, fixtures=fixtures)

    def _correct(self, fixture: rf.Network, delay_ps: float, loss_db: float) -> rf.Network:
        return adjust_fixture_delay_loss(fixture, delta_delay_ps=delay_ps, delta_loss_db=loss_db)


class DualTwoXThruStrategy(_TwoXThruStrategyBase):
    """独立双 2X Thru 策略（网页端默认）。

    * 左夹具：2X Thru A 的 ``side1``；
    * 右夹具：2X Thru B 的 ``side2`` 翻转。
    """

    method = FixtureMethod.DUAL_2X_THRU

    def describe(self) -> str:
        return "独立双 2X Thru 分别劈半（A→1X A，B→1X B）"

    def apply(self, context: StrategyContext) -> StrategyResult:
        thru_a = context.standards.thru_a
        thru_b = context.standards.thru_b
        if thru_a is None or thru_b is None:
            raise InvalidInputError("请上传 Total、2X Thru A 与 2X Thru B，或使用有效的识别缓存。")
        extractor = self.extractor_for(context.nports)
        left = extractor.split(thru_a, z0=context.z0).left
        right = extractor.split(thru_b, z0=context.z0).right
        left = self._correct(left, context.correction_a.delay_ps, context.correction_a.loss_db)
        right = self._correct(right, context.correction_b.delay_ps, context.correction_b.loss_db)
        return self._finalize(context, FixturePair(left=left, right=right))


class SingleTwoXThruStrategy(_TwoXThruStrategyBase):
    """单条 2X Thru 对称劈半策略：左右夹具取自同一条标准件的两个半段。"""

    method = FixtureMethod.SINGLE_2X_THRU

    def describe(self) -> str:
        return "单条 2X Thru 对称劈半后左右复用"

    def apply(self, context: StrategyContext) -> StrategyResult:
        thru = context.standards.thru_a or context.standards.thru_b
        if thru is None:
            raise InvalidInputError("当前去嵌方法需要 2X Thru 标准件文件。")
        split = self.extractor_for(context.nports).split(thru, z0=context.z0)
        left = self._correct(split.left, context.correction_a.delay_ps, context.correction_a.loss_db)
        right = self._correct(split.right, context.correction_b.delay_ps, context.correction_b.loss_db)
        return self._finalize(context, FixturePair(left=left, right=right))
