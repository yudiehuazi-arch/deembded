"""差分混合模 S 参数（SDD / SCC / SCD / SDC）转换。

内部统一使用 skrf 的 ``se2gmm(p=2)`` 正交变换，端口含义：

    0 → d1, 1 → d2, 2 → c1, 3 → c2

因此混合模矩阵元素与通用命名（SDD21 = s[1, 0] 等）的对应关系集中在
``MIXED_MODE_ELEMENTS`` 一处声明，避免各处硬编码索引。
"""

from __future__ import annotations

from typing import Final, Mapping

import numpy as np
import skrf as rf

from .models import PortMapping
from .port_mapping import apply_port_mapping

__all__ = ["MIXED_MODE_ELEMENTS", "MixedModeConverter", "to_db"]

#: 混合模参数名 → 混合模矩阵中的 (行, 列) 索引
MIXED_MODE_ELEMENTS: Final[dict[str, tuple[int, int]]] = {
    "SDD11": (0, 0),
    "SDD21": (1, 0),
    "SDD12": (0, 1),
    "SDD22": (1, 1),
    "SCC11": (2, 2),
    "SCC21": (3, 2),
    "SCC12": (2, 3),
    "SCC22": (3, 3),
    "SCD21": (3, 0),
    "SCD11": (2, 0),
    "SCD12": (2, 1),
    "SCD22": (3, 1),
    "SDC21": (1, 2),
    "SDC11": (0, 2),
    "SDC12": (0, 3),
    "SDC22": (1, 3),
}

_ACTIVE_MINIMUM = 1e-12


def to_db(values: np.ndarray) -> np.ndarray:
    """幅度 → dB（下限 -240 dB 防止 log(0)）。"""

    return 20.0 * np.log10(np.maximum(np.abs(values), _ACTIVE_MINIMUM))


class MixedModeConverter:
    """把 4 端口单端网络转换为混合模量。

    只做“按需转换”：图表/预览只需要固定的一组 dB 曲线，避免为了取
    4 条曲线而计算整个相位/群时延矩阵。
    """

    def __init__(self, mapping: PortMapping, *, elements: Mapping[str, tuple[int, int]] | None = None) -> None:
        self.mapping = mapping
        self.elements = dict(elements or MIXED_MODE_ELEMENTS)

    def _mixed_network(self, network: rf.Network) -> rf.Network:
        work = apply_port_mapping(network, self.mapping)
        work.se2gmm(p=2)
        return work

    def db_traces(self, network: rf.Network) -> dict[str, np.ndarray]:
        """返回 {参数名: dB 数组}，用于图表与诊断。"""

        if network.nports != 4:
            raise ValueError("混合模转换仅适用于 4 端口网络。")
        mixed = self._mixed_network(network)
        s = np.asarray(mixed.s)
        return {name: to_db(s[:, row, col]) for name, (row, col) in self.elements.items()}

    def full_report(self, network: rf.Network) -> dict[str, object]:
        """返回含幅度(dB)与相位(deg)的完整报告（库接口，网页端不直接使用）。"""

        if network.nports == 2:
            return self._two_port_report(network)
        mixed = self._mixed_network(network)
        s = np.asarray(mixed.s)
        groups: dict[str, dict[str, dict[str, list[float]]]] = {"sdd": {}, "scc": {}, "scd": {}, "sdc": {}}
        for name, (row, col) in self.elements.items():
            family = f"s{name[1:3].lower()}"
            groups.setdefault(family, {})[name.lower()] = {
                "db": to_db(s[:, row, col]).astype(float).tolist(),
                "phase": np.angle(s[:, row, col], deg=True).astype(float).tolist(),
            }
        return {"freq_ghz": (np.asarray(mixed.f) / 1e9).astype(float).tolist(), **groups}

    @staticmethod
    def _two_port_report(network: rf.Network) -> dict[str, object]:
        s = np.asarray(network.s)
        entries: dict[str, dict[str, list[float]]] = {}
        for i in range(2):
            for j in range(2):
                name = f"s{i + 1}{j + 1}"
                entries[name] = {
                    "db": to_db(s[:, i, j]).astype(float).tolist(),
                    "phase": np.angle(s[:, i, j], deg=True).astype(float).tolist(),
                }
        return {
            "freq_ghz": (np.asarray(network.f) / 1e9).astype(float).tolist(),
            "se": entries,
        }
