"""2X Thru 劈半器的公共接口。"""

from __future__ import annotations

import skrf as rf

from ..models import FixturePair

__all__ = ["Nzc2xThruExtractor"]


class Nzc2xThruExtractor:
    """把一条 2X Thru 标准件劈成左右 1X 夹具模型。

    ``split()`` 返回的 ``FixturePair`` 处于级联方向：``left`` 为“外侧 → DUT 侧”，
    ``right`` 为“DUT 侧 → 外侧”，满足 ``Total = left ** DUT ** right``。
    """

    #: 适用的端口数
    port_count: int = 0

    def split(self, thru_2x: rf.Network, *, z0: float = 50.0) -> FixturePair:  # pragma: no cover - 抽象
        raise NotImplementedError
