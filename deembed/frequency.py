"""频率网格处理：归一化、共同频段对齐与抽样。

原先散落在 ``app.py``（``_align_to_total_grid`` / ``_renormalize``）与
``deembed_engine.py``（``align_frequencies``）中的逻辑在此统一，避免两套
互相矛盾的插值策略。
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
import skrf as rf

from .errors import FrequencyGridError, InvalidInputError

__all__ = ["MIN_FREQUENCY_POINTS", "renormalize", "sample_network", "FrequencyAligner", "validate_frequency_axis"]

MIN_FREQUENCY_POINTS = 8
_FREQ_ABSOLUTE_TOLERANCE = 1.0  # Hz，用于判断两个网格是否“相同”


def validate_frequency_axis(network: rf.Network, *, label: str = "网络") -> np.ndarray:
    """校验频率轴：有限、严格递增且点数足够。"""

    frequencies = np.asarray(network.f, dtype=float)
    if len(frequencies) < MIN_FREQUENCY_POINTS:
        raise FrequencyGridError(f"{label}至少需要 {MIN_FREQUENCY_POINTS} 个频率点才能进行可靠的 2X Thru 劈半。")
    if not np.all(np.isfinite(frequencies)) or np.any(np.diff(frequencies) <= 0):
        raise InvalidInputError("频率点必须为有限值且严格递增。")
    return frequencies


def renormalize(network: rf.Network, z0: float) -> rf.Network:
    """把网络参考阻抗统一到 ``z0``（必要时复制后重归一化）。"""

    result = network.copy()
    if not np.allclose(np.asarray(result.z0), z0, rtol=1e-6, atol=1e-6):
        result.renormalize(z0)
    return result


def sample_network(network: rf.Network, indices: np.ndarray) -> rf.Network:
    """按索引抽样（用于图表降采样），保留采样后的 z0。"""

    frequencies = np.asarray(network.f, dtype=float)[indices]
    z0 = np.asarray(network.z0)
    sampled_z0 = z0[indices] if z0.ndim > 1 else z0
    return rf.Network(
        frequency=rf.Frequency.from_f(frequencies, unit="hz"),
        s=np.asarray(network.s)[indices],
        z0=sampled_z0,
    )


class FrequencyAligner:
    """把多个网络对齐到同一个频率网格。

    对齐策略（与网页端行为一致）：
    1. 取所有网络频率范围的交集 ``[f_min, f_max]``（无重叠即报错）；
    2. 以第一个网络（通常是 Total）落在交集内的频点作为公共网格；
    3. 其余网络线性插值到该网格。

    之所以选 Total 的频点而不是重新采样，是为了让去嵌结果与原始测量
    频点一一对应，避免引入额外的插值误差。
    """

    def __init__(self, *, min_points: int = MIN_FREQUENCY_POINTS) -> None:
        self.min_points = min_points

    def common_band(self, networks: Sequence[rf.Network]) -> tuple[float, float]:
        """返回所有频率范围的交集。"""

        if not networks:
            return (0.0, 0.0)
        f_min = max(float(np.asarray(network.f)[0]) for network in networks)
        f_max = min(float(np.asarray(network.f)[-1]) for network in networks)
        if f_max <= f_min:
            raise FrequencyGridError("Total、2X Thru A、2X Thru B 的频率范围没有重叠。")
        return f_min, f_max

    def common_grid(self, networks: Sequence[rf.Network]) -> np.ndarray:
        """公共网格（以首个网络在交集内的频点为准）。"""

        for network in networks:
            validate_frequency_axis(network)
        f_min, f_max = self.common_band(networks)
        base = np.asarray(networks[0].f, dtype=float)
        grid = base[(base >= f_min) & (base <= f_max)]
        if len(grid) < self.min_points:
            raise FrequencyGridError(f"三份文件的共同频段内不足 {self.min_points} 个 Total 频率点，无法稳定计算。")
        return grid

    def align(self, networks: Sequence[rf.Network]) -> list[rf.Network]:
        """把整组网络对齐到公共网格，返回新的网络列表。"""

        if not networks:
            return []
        grid = self.common_grid(networks)
        frequency = rf.Frequency.from_f(grid, unit="hz")
        aligned: list[rf.Network] = []
        for network in networks:
            current = np.asarray(network.f, dtype=float)
            if len(current) == len(grid) and np.allclose(current, grid, rtol=1e-12, atol=_FREQ_ABSOLUTE_TOLERANCE):
                aligned.append(network.copy())
                continue
            try:
                aligned.append(network.interpolate(frequency, kind="linear"))
            except Exception as exc:  # noqa: BLE001 - 转成领域错误
                raise FrequencyGridError(f"频率网格插值失败：{exc}") from exc
        return aligned
