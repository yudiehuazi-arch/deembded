"""4 端口差分映射约定：识别、重排与文案。

端口约定：
* ``sequential``：左差分对 = (1,2)，右差分对 = (3,4)；
* ``plts``      ：左差分对 = (1,3)，右差分对 = (2,4)。

两者之间只差一次端口 2/3 的交换（对合变换，执行两次即还原）。
"""

from __future__ import annotations

from typing import Final, Sequence

import numpy as np
import skrf as rf

from .errors import InvalidInputError
from .models import PortMapping

__all__ = [
    "PLTS_PORT_ORDER",
    "auto_detect_port_mapping",
    "resolve_port_mapping",
    "apply_port_mapping",
    "restore_port_mapping",
    "pair_labels",
    "mapping_label",
]

# skrf 的 renumber(from, to) 语义：端口 from[i] 移动到位置 to[i]。
PLTS_PORT_ORDER: Final[list[int]] = [0, 2, 1, 3]
_DETECTION_FREQUENCY_POINTS: Final[int] = 60


def auto_detect_port_mapping(network: rf.Network) -> PortMapping:
    """按直通通道强度自动判断 4 端口映射约定。

    sequential 下主通道为 S31/S42，plts 下为 S21/S43；比较前若干频点的
    平均幅度即可稳定区分。
    """

    if network.nports != 4:
        return PortMapping.SEQUENTIAL
    count = min(len(network.f), _DETECTION_FREQUENCY_POINTS)
    plts_through = float(np.mean(np.abs(network.s[:count, 1, 0])))
    sequential_through = float(np.mean(np.abs(network.s[:count, 2, 0])))
    return PortMapping.PLTS if plts_through > sequential_through else PortMapping.SEQUENTIAL


def resolve_port_mapping(network: rf.Network, requested: PortMapping | str) -> PortMapping:
    """把用户请求（可能为 ``auto``）解析为生效映射。"""

    if network.nports == 2:
        return PortMapping.SINGLE_ENDED
    if isinstance(requested, PortMapping):
        mapping = requested
    else:
        mapping = PortMapping.parse(
            requested,
            field="S4P 端口映射",
            allowed=[PortMapping.AUTO, PortMapping.SEQUENTIAL, PortMapping.PLTS],
        )
    if mapping is PortMapping.AUTO:
        return auto_detect_port_mapping(network)
    if mapping is PortMapping.SINGLE_ENDED:
        raise InvalidInputError("S4P 端口映射设置无效。")
    return mapping


def apply_port_mapping(network: rf.Network, mapping: PortMapping) -> rf.Network:
    """把 PLTS 交叉排布的网络重排为标准顺序，便于内部统一处理。"""

    work = network.copy()
    if mapping is PortMapping.PLTS and work.nports == 4:
        work.renumber(PLTS_PORT_ORDER, [0, 1, 2, 3])
    return work


def restore_port_mapping(network: rf.Network, mapping: PortMapping) -> rf.Network:
    """把内部标准顺序的结果还原回用户原始端口排布。"""

    return apply_port_mapping(network, mapping)


def pair_labels(nports: int, mapping: PortMapping) -> tuple[list[str], list[str]]:
    """返回左/右差分对的端口显示标签（用于前端映射面板）。"""

    if nports == 2:
        return ["P1"], ["P2"]
    if mapping is PortMapping.PLTS:
        return ["P1 (+)", "P3 (−)"], ["P2 (+)", "P4 (−)"]
    return ["P1 (+)", "P2 (−)"], ["P3 (+)", "P4 (−)"]


def mapping_label(nports: int, mapping: PortMapping) -> str:
    """人类可读的映射说明（前端直接展示）。"""

    if nports == 2:
        return "单端双端口"
    return "PLTS 交叉 · 1/3 → 2/4" if mapping is PortMapping.PLTS else "标准顺序 · 1/2 → 3/4"


def renumber_sequence(network: rf.Network, order: Sequence[int]) -> rf.Network:
    """按给定端口顺序返回重排后的副本（供未来扩展使用）。"""

    work = network.copy()
    work.renumber(list(order), list(range(len(order))))
    return work
