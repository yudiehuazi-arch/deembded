"""IEEE 370 Annex A：2X Thru 非零长度标准件（NZC）劈半。

``skrf.calibration.deembedding`` 提供了 SE / MM 两种实现，本模块把
它们包装成统一的 :class:`Nzc2xThruExtractor` 接口：

* ``split()`` 返回 ``FixturePair(left, right)``，两者都处于 **级联方向**：
  ``left`` 为“外侧端口 → DUT 侧端口”，``right`` 为“DUT 侧端口 → 外侧端口”
  （skrf 的 ``s_side2`` 是“外侧 → DUT 侧”，这里再翻转一次），因此可直接用于
  ``Total = left ** DUT ** right``；
* 端口映射（PLTS 交叉）在进入本模块之前已由引擎重排为标准顺序；
* 差分 S4P 有两种劈半算法（:class:`~deembed.models.SplitAlgorithm`）：
  经典 MM-NZC（本模块，丢弃模式转换）与保留模式转换的推广版本
  （:mod:`deembed.fixtures.mode_conversion`）。
"""

from __future__ import annotations

from typing import Final, Mapping

import skrf as rf
from skrf.calibration import deembedding

from ..errors import UnsupportedPortCountError
from ..models import FixturePair, SplitAlgorithm
from .base import Nzc2xThruExtractor
from .mode_conversion import ModeConversionNzc2xThruExtractor

__all__ = [
    "Nzc2xThruExtractor",
    "SingleEndedNzc2xThruExtractor",
    "MixedModeNzc2xThruExtractor",
    "ModeConversionNzc2xThruExtractor",
    "EXTRACTORS",
    "EXTRACTOR_SETS",
    "get_extractor",
]


class SingleEndedNzc2xThruExtractor(Nzc2xThruExtractor):
    """单端 2 端口 NZC 劈半（``IEEEP370_SE_NZC_2xThru``）。"""

    port_count = 2

    def split(self, thru_2x: rf.Network, *, z0: float = 50.0) -> FixturePair:
        result = deembedding.IEEEP370_SE_NZC_2xThru(dummy_2xthru=thru_2x, z0=z0)
        return FixturePair(left=result.s_side1, right=result.s_side2.flipped())


class MixedModeNzc2xThruExtractor(Nzc2xThruExtractor):
    """差分 4 端口混合模 NZC 劈半（``IEEEP370_MM_NZC_2xThru``，经典算法）。

    输入网络为“标准顺序”端口排布（1,2 = 左差分对；3,4 = 右差分对），
    与 ``port_order='second'`` 对应。SDD 与 SCC 独立劈半，SDC/SCD 被丢弃，
    因此夹具模型不含模式转换。
    """

    port_count = 4

    def split(self, thru_2x: rf.Network, *, z0: float = 50.0) -> FixturePair:
        result = deembedding.IEEEP370_MM_NZC_2xThru(dummy_2xthru=thru_2x, z0=z0, port_order="second")
        return FixturePair(left=result.se_side1, right=result.se_side2.flipped())


_SINGLE_ENDED = SingleEndedNzc2xThruExtractor()

#: 端口数 → 劈半器实例（经典 IEEE 370 实现，保持历史接口）
EXTRACTORS: Final[Mapping[int, Nzc2xThruExtractor]] = {
    2: _SINGLE_ENDED,
    4: MixedModeNzc2xThruExtractor(),
}

#: 劈半算法 → (端口数 → 劈半器)。单端 S2P 两种算法相同。
EXTRACTOR_SETS: Final[Mapping[SplitAlgorithm, Mapping[int, Nzc2xThruExtractor]]] = {
    SplitAlgorithm.CLASSIC: EXTRACTORS,
    SplitAlgorithm.MODE_CONVERSION: {2: _SINGLE_ENDED, 4: ModeConversionNzc2xThruExtractor()},
}


def get_extractor(nports: int, algorithm: SplitAlgorithm | str = SplitAlgorithm.CLASSIC) -> Nzc2xThruExtractor:
    """按端口数（与劈半算法）获取劈半器，不支持时抛出领域异常。"""

    resolved = algorithm if isinstance(algorithm, SplitAlgorithm) else SplitAlgorithm.parse(algorithm, field="劈半算法")
    extractor = EXTRACTOR_SETS[resolved].get(nports)
    if extractor is None:
        raise UnsupportedPortCountError(f"2X Thru 劈半仅支持 S2P 或 S4P，收到 {nports} 端口。")
    return extractor
