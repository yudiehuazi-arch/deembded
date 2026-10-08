"""预设示例的公共构建工具（合成微带线 / 差分对 / 接头寄生）。"""

from __future__ import annotations

from typing import Final

import numpy as np
import skrf as rf
from skrf.network import concat_ports

__all__ = [
    "PRESET_FREQUENCY",
    "VELOCITY_FACTOR",
    "PRESET_FREQUENCY_START_GHZ",
    "PRESET_FREQUENCY_STOP_GHZ",
    "PRESET_FREQUENCY_POINTS",
    "propagation_medium",
    "line",
    "coupled_pair",
    "shunt_capacitor",
    "transmission_line_pair",
    "delay_ps_for_length",
]

PRESET_FREQUENCY_START_GHZ: Final[float] = 0.1
PRESET_FREQUENCY_STOP_GHZ: Final[float] = 67.0
PRESET_FREQUENCY_POINTS: Final[int] = 269
VELOCITY_FACTOR: Final[float] = 0.7


def _frequency() -> rf.Frequency:
    return rf.Frequency(PRESET_FREQUENCY_START_GHZ, PRESET_FREQUENCY_STOP_GHZ, PRESET_FREQUENCY_POINTS, unit="ghz")


#: 预设示例共用的频段（0.1 – 67 GHz，269 点）
PRESET_FREQUENCY = _frequency()


def propagation_medium(loss_scale: float = 0.08, *, frequency: rf.Frequency | None = None) -> rf.media.DefinedGammaZ0:
    """带 ``jβ + α√f`` 传播常数的 50 Ω 介质（模拟 PCB 走线）。"""

    freq = frequency or PRESET_FREQUENCY
    gamma = 1j * 2 * np.pi * np.asarray(freq.f) / (3e8 * VELOCITY_FACTOR) + loss_scale * np.sqrt(np.asarray(freq.f) / 1e9)
    return rf.media.DefinedGammaZ0(freq, z0=50, gamma=gamma)


def line(medium: rf.media.DefinedGammaZ0, length_m: float) -> rf.Network:
    """按长度生成一段均匀传输线。"""

    return medium.line(length_m, "m")


def shunt_capacitor(medium: rf.media.DefinedGammaZ0, capacitance_f: float) -> rf.Network:
    """接头/过孔寄生电容（shunt C 二端口）。"""

    return medium.shunt_capacitor(capacitance_f)


def coupled_pair(segment: rf.Network) -> rf.Network:
    """把单端线段复制为两条互不耦合的差分通道：端口 1/2 在左，3/4 在右。"""

    return concat_ports([segment, segment.copy()], port_order="second")


def transmission_line_pair(medium: rf.media.DefinedGammaZ0, length_m: float) -> rf.Network:
    return coupled_pair(line(medium, length_m))


def delay_ps_for_length(length_m: float, velocity: float = 3e8 * VELOCITY_FACTOR) -> float:
    """长度为 ``length_m`` 的走线对应的单程时延（ps）。"""

    return float(length_m / velocity * 1e12)
