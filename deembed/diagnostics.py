"""差分去嵌诊断：P/N skew、2X Thru 模式转换强度与两种劈半算法的差异。

这些指标用来回答“为什么本工具与 PLTS AFR 的 SDD21 不一致”这类问题：

* 夹具 P/N skew 或发射结构不对称 → 2X Thru 出现 SCD21/SDC21（模式转换）；
* 经典 IEEE 370 MM-NZC 丢弃模式转换，PLTS 2019+ AFR 与本工具的
  “混合模 NZC + 模式转换”保留模式转换；
* 两种算法的 SDD21 差值随频率的变化，直接给出模式转换对结果的影响量级。

所有函数只接受 **标准顺序** 的单端 4 端口网络（1,2 = 左差分对，3,4 = 右差分对；
P 线 1→3、N 线 2→4），即引擎完成端口映射重排之后的网络。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Sequence

import numpy as np
import skrf as rf

from .models import SplitAlgorithm

__all__ = [
    "PathDiagnostics",
    "SplitComparison",
    "ModeConversionDiagnostics",
    "estimate_pn_skew_ps",
    "max_mode_conversion_db",
    "sdd21",
    "compare_sdd21",
    "build_mode_conversion_diagnostics",
]

#: 估计 skew 时只使用传输幅度高于该值的频点（线性幅度，≈ −26 dB）
_MIN_TRANSMISSION: Final[float] = 0.05
#: 估计 skew 时使用的频段上限（占最高频率的比例），避开高频谐振/耦合影响
_SKEW_BAND_FRACTION: Final[float] = 0.5
#: 对照算法 SDD21 差值的检查点（占最高频率的比例）
_CHECKPOINT_FRACTIONS: Final[tuple[float, ...]] = (0.25, 0.5, 0.75, 1.0)
_FLOOR: Final[float] = 1e-15
#: 模式转换强度的显示下限（−200 dB），完全对称的理想网络不再显示 −300 dB
_CONVERSION_FLOOR: Final[float] = 1e-10


def _finite_or_none(value: float | None, digits: int) -> float | None:
    if value is None or not np.isfinite(value):
        return None
    return round(float(value), digits) + 0.0  # + 0.0：把 -0.0 规范为 0.0


def sdd21(network: rf.Network) -> np.ndarray:
    """标准顺序单端 4 端口 → 复数 SDD21。"""

    mixed = network.copy()
    mixed.se2gmm(p=2)
    return np.asarray(mixed.s[:, 1, 0])


def estimate_pn_skew_ps(network: rf.Network) -> float | None:
    """估计 P 线与 N 线的传输时延差 ``τ_P − τ_N``（ps，正值表示 P 线更长）。

    方法：``∠(S42·S31*) = ω·(τ_P − τ_N)``，在低频到半带宽内（且两条线传输
    幅度足够大）对展开相位做过原点的最小二乘直线拟合。耦合对称的差分对
    不会引入相位差，因此该估计对远端串扰不敏感。
    """

    if network.nports != 4 or len(network.f) < 4:
        return None
    f = np.asarray(network.f, dtype=float)
    s = np.asarray(network.s)
    s_p = s[:, 2, 0]
    s_n = s[:, 3, 1]
    valid = (f > 0) & (np.abs(s_p) > _MIN_TRANSMISSION) & (np.abs(s_n) > _MIN_TRANSMISSION)
    valid &= f <= _SKEW_BAND_FRACTION * float(f[-1])
    indices = np.flatnonzero(valid)
    if len(indices) < 3:
        return None
    # 只取最低频开始的连续区段，避免跨越无效频点展开相位
    breaks = np.flatnonzero(np.diff(indices) != 1)
    if len(breaks):
        indices = indices[: breaks[0] + 1]
    if len(indices) < 3:
        return None
    omega = 2 * np.pi * f[indices]
    phase = np.unwrap(np.angle(s_n[indices] * np.conj(s_p[indices])))
    skew_s = float(np.sum(omega * phase) / np.sum(omega * omega))
    return skew_s * 1e12


def max_mode_conversion_db(network: rf.Network) -> float | None:
    """传输模式转换强度 ``max_f max(|SCD21|, |SDC21|)``（dB）。

    2X Thru 的该值低于约 −40 dB 时，夹具模式转换对 SDD21 的影响通常可以忽略；
    −30 dB 以上就值得用“混合模 NZC + 模式转换”与经典算法对照一下。
    """

    if network.nports != 4 or not len(network.f):
        return None
    mixed = network.copy()
    mixed.se2gmm(p=2)
    s = np.asarray(mixed.s)
    conversion = float(np.max(np.maximum(np.abs(s[:, 3, 0]), np.abs(s[:, 1, 2]))))
    return float(20 * np.log10(max(conversion, _CONVERSION_FLOOR)))


@dataclass(frozen=True)
class PathDiagnostics:
    """单个差分通道（2X Thru 或去嵌后的 DUT）的诊断量。"""

    skew_ps: float | None
    max_conversion_db: float | None

    @classmethod
    def from_network(cls, network: rf.Network | None) -> "PathDiagnostics":
        if network is None or network.nports != 4:
            return cls(skew_ps=None, max_conversion_db=None)
        return cls(skew_ps=estimate_pn_skew_ps(network), max_conversion_db=max_mode_conversion_db(network))

    def to_payload(self) -> dict[str, Any]:
        return {
            "skew_ps": _finite_or_none(self.skew_ps, 3),
            "max_conversion_db": _finite_or_none(self.max_conversion_db, 2),
        }


@dataclass(frozen=True)
class SplitComparison:
    """主算法与对照算法得到的 DUT SDD21 之差（主 − 对照，dB）。"""

    primary: SplitAlgorithm
    alternative: SplitAlgorithm
    #: 绝对值最大的差值（保留符号）及其频率
    max_delta_db: float
    max_delta_ghz: float
    #: (频率 GHz, 差值 dB) 检查点
    checkpoints: tuple[tuple[float, float], ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "primary": self.primary.value,
            "primary_label": self.primary.label,
            "alternative": self.alternative.value,
            "alternative_label": self.alternative.label,
            "max_delta_db": _finite_or_none(self.max_delta_db, 4),
            "max_delta_ghz": _finite_or_none(self.max_delta_ghz, 4),
            "checkpoints": [
                {"freq_ghz": _finite_or_none(freq, 4), "delta_db": _finite_or_none(delta, 4)}
                for freq, delta in self.checkpoints
            ],
        }


def compare_sdd21(
    primary: rf.Network,
    alternative: rf.Network,
    *,
    primary_algorithm: SplitAlgorithm,
    alternative_algorithm: SplitAlgorithm,
    fractions: Sequence[float] = _CHECKPOINT_FRACTIONS,
) -> SplitComparison:
    """比较两份（标准顺序）DUT 的 SDD21 幅度。"""

    f_ghz = np.asarray(primary.f, dtype=float) / 1e9
    delta = 20 * np.log10(np.maximum(np.abs(sdd21(primary)), _FLOOR)) - 20 * np.log10(
        np.maximum(np.abs(sdd21(alternative)), _FLOOR)
    )
    worst = int(np.argmax(np.abs(delta)))
    checkpoints = []
    for fraction in fractions:
        index = int(np.argmin(np.abs(f_ghz - fraction * f_ghz[-1])))
        checkpoints.append((float(f_ghz[index]), float(delta[index])))
    return SplitComparison(
        primary=primary_algorithm,
        alternative=alternative_algorithm,
        max_delta_db=float(delta[worst]),
        max_delta_ghz=float(f_ghz[worst]),
        checkpoints=tuple(checkpoints),
    )


@dataclass(frozen=True)
class ModeConversionDiagnostics:
    """一次差分去嵌的模式转换诊断汇总。"""

    thru_a: PathDiagnostics
    thru_b: PathDiagnostics
    dut: PathDiagnostics
    comparison: SplitComparison | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "thru_a": self.thru_a.to_payload(),
            "thru_b": self.thru_b.to_payload(),
            "dut": self.dut.to_payload(),
            "comparison": self.comparison.to_payload() if self.comparison is not None else None,
        }


def build_mode_conversion_diagnostics(
    *,
    thru_a: rf.Network | None,
    thru_b: rf.Network | None,
    dut: rf.Network,
    comparison_dut: rf.Network | None,
    primary_algorithm: SplitAlgorithm,
) -> ModeConversionDiagnostics:
    """汇总 2X Thru / DUT 的 skew 与模式转换，以及两种算法的 SDD21 差值。"""

    comparison = None
    if comparison_dut is not None:
        comparison = compare_sdd21(
            dut,
            comparison_dut,
            primary_algorithm=primary_algorithm,
            alternative_algorithm=primary_algorithm.alternative,
        )
    return ModeConversionDiagnostics(
        thru_a=PathDiagnostics.from_network(thru_a),
        thru_b=PathDiagnostics.from_network(thru_b),
        dut=PathDiagnostics.from_network(dut),
        comparison=comparison,
    )
