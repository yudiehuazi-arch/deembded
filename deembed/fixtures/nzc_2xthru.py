"""IEEE 370 Annex A：2X Thru 非零长度标准件（NZC）劈半。

``skrf.calibration.deembedding`` 提供了 SE / MM 两种实现，本模块把
它们包装成统一的 :class:`Nzc2xThruExtractor` 接口：

* ``split()`` 返回 ``FixturePair(left, right)``，其中 ``right`` 已翻转
  （``flipped()``），即两个夹具都处在于 “外侧端口 → DUT 侧端口” 的方向；
* 端口映射（PLTS 交叉）在进入本模块之前已由引擎重排为标准顺序。
"""

from __future__ import annotations

from typing import Final, Mapping

import skrf as rf
from skrf.calibration import deembedding

from ..errors import UnsupportedPortCountError
from ..models import FixturePair

__all__ = [
    "Nzc2xThruExtractor",
    "SingleEndedNzc2xThruExtractor",
    "MixedModeNzc2xThruExtractor",
    "EXTRACTORS",
    "get_extractor",
]


class Nzc2xThruExtractor:
    """把一条 2X Thru 标准件劈成左右 1X 夹具模型。"""

    #: 适用的端口数
    port_count: int = 0

    def split(self, thru_2x: rf.Network, *, z0: float = 50.0) -> FixturePair:  # pragma: no cover - 抽象
        raise NotImplementedError


class SingleEndedNzc2xThruExtractor(Nzc2xThruExtractor):
    """单端 2 端口 NZC 劈半（``IEEEP370_SE_NZC_2xThru``）。"""

    port_count = 2

    def split(self, thru_2x: rf.Network, *, z0: float = 50.0) -> FixturePair:
        result = deembedding.IEEEP370_SE_NZC_2xThru(dummy_2xthru=thru_2x, z0=z0)
        return FixturePair(left=result.s_side1, right=result.s_side2.flipped())


class MixedModeNzc2xThruExtractor(Nzc2xThruExtractor):
    """差分 4 端口混合模 NZC 劈半（``IEEEP370_MM_NZC_2xThru``）。

    输入网络为“标准顺序”端口排布（1,2 = 左差分对；3,4 = 右差分对），
    与 ``port_order='second'`` 对应。
    """

    port_count = 4

    def split(self, thru_2x: rf.Network, *, z0: float = 50.0) -> FixturePair:
        result = deembedding.IEEEP370_MM_NZC_2xThru(dummy_2xthru=thru_2x, z0=z0, port_order="second")
        return FixturePair(left=result.se_side1, right=result.se_side2.flipped())


#: 端口数 → 劈半器实例
EXTRACTORS: Final[Mapping[int, Nzc2xThruExtractor]] = {
    2: SingleEndedNzc2xThruExtractor(),
    4: MixedModeNzc2xThruExtractor(),
}


def get_extractor(nports: int) -> Nzc2xThruExtractor:
    """按端口数获取劈半器，不支持时抛出领域异常。"""

    extractor = EXTRACTORS.get(nports)
    if extractor is None:
        raise UnsupportedPortCountError(f"2X Thru 劈半仅支持 S2P 或 S4P，收到 {nports} 端口。")
    return extractor
