"""图表/预览数据构建（纯计算，不依赖 Web 框架）。

这三类“报表对象”分别服务于：
* :class:`NetworkPreviewBuilder` —— 上传识别后每条输入曲线的轻量预览；
* :class:`ChartDataBuilder`      —— 去嵌结果对比图的曲线集合；
* :class:`FixtureStatisticsAnalyzer` —— 2X Thru 夹具诊断规则（交点频率）。

每个报表对象都实现 ``to_payload()``，Web 层直接 JSON 化返回，
因此前端字段与后端计算保持单一来源。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final, Mapping, Sequence

import numpy as np
import skrf as rf

from .mixed_mode import MixedModeConverter, to_db
from .models import PortMapping
from .frequency import sample_network

__all__ = [
    "DEFAULT_FIXTURE_RULES",
    "LevelCrossing",
    "FixtureRuleResult",
    "FixtureStatistics",
    "NetworkPreview",
    "ChartData",
    "NetworkPreviewBuilder",
    "ChartDataBuilder",
    "FixtureStatisticsAnalyzer",
    "downsample_indices",
    "level_crossings",
]

#: （规则文案, 被减参数, 减数参数, 目标差值 dB）
DEFAULT_FIXTURE_RULES: Final[tuple[tuple[str, str, str, float], ...]] = (
    ("SDD21 − SDD22 = 5 dB", "SDD21", "SDD22", 5.0),
    ("SDD12 − SDD11 = 5 dB", "SDD12", "SDD11", 5.0),
    ("SDD22 = SDD21", "SDD22", "SDD21", 0.0),
    ("SDD11 = SDD12", "SDD11", "SDD12", 0.0),
)

_CROSSING_TOLERANCE_DB: Final[float] = 1e-6


@dataclass(frozen=True)
class LevelCrossing:
    """差值曲线与目标电平的交点/重合区间。"""

    points_ghz: tuple[float, ...] = ()
    ranges_ghz: tuple[tuple[float, float], ...] = ()


@dataclass(frozen=True)
class FixtureRuleResult:
    label: str
    target_db: float
    crossing: LevelCrossing

    def to_payload(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "target_db": self.target_db,
            "points_ghz": list(self.crossing.points_ghz),
            "ranges_ghz": [list(item) for item in self.crossing.ranges_ghz],
        }


@dataclass(frozen=True)
class FixtureStatistics:
    thru_a: tuple[FixtureRuleResult, ...] = ()
    thru_b: tuple[FixtureRuleResult, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "thru_a": [rule.to_payload() for rule in self.thru_a],
            "thru_b": [rule.to_payload() for rule in self.thru_b],
        }


@dataclass(frozen=True)
class NetworkPreview:
    """单个网络的降采样预览。"""

    freq_ghz: list[float]
    series: dict[str, list[float]]

    def to_payload(self) -> dict[str, Any]:
        return {"freq_ghz": self.freq_ghz, "series": self.series}


@dataclass(frozen=True)
class ChartData:
    """多网络 × 多参数的曲线集合（前端图表直接消费）。"""

    freq_ghz: list[float]
    network_keys: list[str]
    series: dict[str, dict[str, list[float]]] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {"freq_ghz": self.freq_ghz, "network_keys": self.network_keys, "series": self.series}


def downsample_indices(count: int, max_points: int) -> np.ndarray:
    """等间隔抽样索引（保证包含首尾点）。"""

    step = max(1, int(np.ceil(count / max_points)))
    indices = np.arange(0, count, step, dtype=int)
    if len(indices) == 0 or indices[-1] != count - 1:
        indices = np.append(indices, count - 1)
    return indices


def level_crossings(
    freq_ghz: np.ndarray,
    difference_db: np.ndarray,
    target_db: float,
    tolerance_db: float = _CROSSING_TOLERANCE_DB,
) -> LevelCrossing:
    """返回差值曲线与目标电平的插值交点，以及连续重合区间。"""

    freq = np.asarray(freq_ghz, dtype=float).reshape(-1)
    residual = np.asarray(difference_db, dtype=float).reshape(-1) - float(target_db)
    n = min(len(freq), len(residual))
    points: list[float] = []
    ranges: list[tuple[float, float]] = []
    i = 0
    while i < n:
        if not np.isfinite(freq[i]) or not np.isfinite(residual[i]):
            i += 1
            continue
        if abs(residual[i]) <= tolerance_db:
            start = i
            end = i
            while (
                end + 1 < n
                and np.isfinite(freq[end + 1])
                and np.isfinite(residual[end + 1])
                and abs(residual[end + 1]) <= tolerance_db
            ):
                end += 1
            if end > start:
                ranges.append((float(freq[start]), float(freq[end])))
            else:
                points.append(float(freq[start]))
            i = end + 1
            continue
        if i + 1 < n and np.isfinite(freq[i + 1]) and np.isfinite(residual[i + 1]):
            next_residual = residual[i + 1]
            if abs(next_residual) > tolerance_db and residual[i] * next_residual < 0:
                fraction = -residual[i] / (next_residual - residual[i])
                points.append(float(freq[i] + fraction * (freq[i + 1] - freq[i])))
        i += 1
    return LevelCrossing(points_ghz=tuple(points), ranges_ghz=tuple(ranges))


class NetworkPreviewBuilder:
    """构建单个网络的预览曲线。"""

    def __init__(self, *, max_points: int = 500) -> None:
        self.max_points = max_points

    def mixed_mode_db(self, network: rf.Network, mapping: PortMapping) -> dict[str, np.ndarray]:
        return MixedModeConverter(mapping).db_traces(network)

    def build(
        self,
        network: rf.Network,
        port_mapping: PortMapping,
        *,
        mixed_mode_db: Mapping[str, np.ndarray] | None = None,
    ) -> NetworkPreview:
        indices = downsample_indices(len(network.f), self.max_points)
        series: dict[str, list[float]] = {}
        s = np.asarray(network.s)
        for i in range(network.nports):
            for j in range(network.nports):
                series[f"S{i + 1}{j + 1}"] = to_db(s[indices, i, j]).astype(float).tolist()

        if network.nports == 4:
            if mixed_mode_db is None:
                mixed = self.mixed_mode_db(sample_network(network, indices), port_mapping)
                mixed_indices = np.arange(len(indices), dtype=int)
            else:
                mixed = dict(mixed_mode_db)
                mixed_indices = indices
            for name, values in mixed.items():
                series[name] = np.asarray(values, dtype=float)[mixed_indices].astype(float).tolist()

        return NetworkPreview(
            freq_ghz=(np.asarray(network.f)[indices] / 1e9).astype(float).tolist(),
            series=series,
        )


class ChartDataBuilder:
    """构建结果对比图数据（网络 → 参数 → 曲线）。"""

    def __init__(self, *, max_points: int = 600) -> None:
        self.max_points = max_points

    def build(self, networks: Mapping[str, rf.Network], port_mapping: PortMapping) -> ChartData:
        if not networks:
            return ChartData(freq_ghz=[], network_keys=[], series={})

        reference = next(iter(networks.values()))
        indices = downsample_indices(len(reference.f), self.max_points)
        freq_ghz = (np.asarray(reference.f)[indices] / 1e9).astype(float).tolist()

        spectra: dict[str, dict[str, list[float]]] = {}
        for key, network in networks.items():
            current: dict[str, list[float]] = {}
            s = np.asarray(network.s)
            for i in range(network.nports):
                for j in range(network.nports):
                    current[f"S{i + 1}{j + 1}"] = to_db(s[indices, i, j]).astype(float).tolist()
            if network.nports == 4:
                mixed = MixedModeConverter(port_mapping).db_traces(sample_network(network, indices))
                for name, values in mixed.items():
                    current[name] = np.asarray(values, dtype=float).astype(float).tolist()
            spectra[key] = current

        parameters = list(spectra[next(iter(spectra))].keys())
        series = {
            parameter: {key: spectra[key][parameter] for key in spectra if parameter in spectra[key]}
            for parameter in parameters
        }
        return ChartData(freq_ghz=freq_ghz, network_keys=list(networks.keys()), series=series)


class FixtureStatisticsAnalyzer:
    """2X Thru 差分夹具诊断：交点频率与重合区间。"""

    def __init__(self, rules: Sequence[tuple[str, str, str, float]] = DEFAULT_FIXTURE_RULES) -> None:
        self.rules = tuple(rules)

    def analyze(
        self,
        network: rf.Network,
        port_mapping: PortMapping,
        *,
        mixed_mode_db: Mapping[str, np.ndarray] | None = None,
    ) -> list[FixtureRuleResult]:
        if network.nports != 4:
            return []
        values = dict(mixed_mode_db) if mixed_mode_db is not None else MixedModeConverter(port_mapping).db_traces(network)
        freq_ghz = np.asarray(network.f, dtype=float) / 1e9
        results: list[FixtureRuleResult] = []
        for label, first, second, target in self.rules:
            crossing = level_crossings(freq_ghz, values[first] - values[second], target)
            results.append(FixtureRuleResult(label=label, target_db=target, crossing=crossing))
        return results
