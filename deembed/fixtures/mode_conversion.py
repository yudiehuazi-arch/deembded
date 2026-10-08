"""差分 2X Thru 劈半：保留模式转换（SDC / SCD）的混合模 NZC。

为什么需要它
------------
skrf 的 ``IEEEP370_MM_NZC_2xThru``（IEEE 370 Annex A 的混合模版本）把 2X Thru
转成混合模后，**分别**对 SDD 与 SCC 做标量 NZC 劈半，SDC/SCD 项被直接丢弃，
因此得到的 1X 夹具模型里没有任何模式转换。只要夹具存在 P/N 线长差（skew）
或 P/N 发射结构不对称，这部分模式转换就会残留在去嵌后的 DUT 中：SDD21 在
高频出现随频率增大的偏差（DUT 与夹具 skew 同向时表现为 *损耗偏大*）。

Keysight PLTS 自 2019 版起，AFR 提取的夹具模型包含模式转换
（AFR 配置中的 “AFR Mode Conversion” 对非单端数据自动开启）。

算法（IEEE 370 NZC 的 2×2 模式矩阵推广）
------------------------------------------
记模式基底为 ``[d, c]``，把 NZC 中的每个标量换成 2×2 矩阵：

1. 2X Thru → 混合模；SDD 与 SCC 各自按 IEEE 370 方式确定劈半点 ``x``
   （t21 冲激峰）与劈半面阻抗 ``z_x``（t11 阶跃阻抗在 x 处的取值）；
2. DD / CC 端口分别重归一化到 ``z_x,dd`` / ``z_x,cc``；
3. 时域门限：反射块的 2×2 元素分别在 ``x_dd``、``x_cc``、``(x_dd+x_cc)/2``
   处截断，得到左夹具外侧反射 ``A11`` 与右夹具外侧反射 ``B22``；
4. 逐频点矩阵代数（假设左右半段的传输矩阵相同，与标量 NZC 的
   ``e01 = e10`` 假设一致）::

       P = (S11 − A11)·S21⁻¹          → 右夹具 DUT 侧反射  B11 = K⁻¹·P·K
       R = (S22 − B22)·S12⁻¹          → 左夹具 DUT 侧反射  A22 = K⁻¹·R·K
       W = (I − R·P)·S21 ≈ (I − P·R)·S12 = K·Kᵀ

   ``K`` 取 ``W`` 的对称平方根：对角元沿频率连续选支（与 skrf 的标量
   ``e01`` 选支一致），非对角元（模式转换）在 DD/CC 传输近乎反相、
   无法从 2X Thru 观测时自动正则化到 0（退化为经典行为）；
5. 组装左右夹具、重归一化回 ``2·z0`` / ``z0/2`` 并转回单端。

当 2X Thru 不含模式转换时，所有矩阵均为对角阵，结果与经典 MM-NZC 等价。

已知局限：``W = K·Kᵀ`` 只确定 ``K`` 到一个正交变换；对称根对应“模式转换
沿夹具均匀分布，或 DD/CC 传播速度相同（带状线）”的情形，这也是仿真中
误差最小的情形。若是微带线（DD/CC 速度差明显）且 skew 集中在夹具某一端，
任何只依赖 2X Thru 的方法都存在不确定性。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import scipy.interpolate
import skrf as rf
from numpy.fft import fft, fftshift, ifftshift, irfft
from skrf.calibration.deembedding import IEEEP370

from ..errors import UnsupportedPortCountError
from ..models import FixturePair
from .base import Nzc2xThruExtractor

__all__ = [
    "ModeConversionSplitInfo",
    "ModeConversionNzc2xThruExtractor",
    "symmetric_sqrtm_continuous",
]

#: ``[d1, d2, c1, c2]``（skrf se2gmm 顺序）与 ``[d1, c1, d2, c2]``（按侧分块）之间的重排（自逆）
_SIDE_BLOCK_ORDER: Final[list[int]] = [0, 2, 1, 3]
#: 2X Thru 插值到谐波网格时的最大点数（与 skrf 保持一致）
_MAX_HARMONIC_POINTS: Final[int] = 10000
#: 对称平方根的正则化强度：|a+d| < rho·(|a|+|d|) 时模式转换项逐渐收缩到 0
_DEFAULT_REGULARIZATION: Final[float] = 0.1
_ROOT_ITERATIONS: Final[int] = 8


@dataclass(frozen=True)
class ModeConversionSplitInfo:
    """一次劈半的中间量（诊断用）。"""

    x_dd: int
    x_cc: int
    z_x_dd: float
    z_x_cc: float
    #: 2X Thru 的传输模式转换强度 max_f max(|SCD21|,|SDC21|)（dB）
    max_conversion_db: float


# ---------------------------------------------------------------------------
# 时域工具（与 skrf IEEEP370 的实现保持一致）
# ---------------------------------------------------------------------------
def _impulse(s: np.ndarray, f: np.ndarray, *, reflective: bool) -> np.ndarray:
    """补 DC 点后做 irfft，并把 t=0 移到数组中间（与 skrf 相同的约定）。"""

    dc = IEEEP370.DC(s, f) if reflective else IEEEP370.dc_interp(s, f)
    return fftshift(irfft(np.concatenate(([dc], s)), axis=0), axes=0)


def _split_point(s11: np.ndarray, s21: np.ndarray, f: np.ndarray, z0: float) -> tuple[int, float]:
    """IEEE 370 NZC 的劈半点（t21 峰值索引）与该处 TDR 阻抗。"""

    t21 = _impulse(s21, f, reflective=False)
    x = int(np.argmax(t21))
    step = IEEEP370.makeStep(_impulse(s11, f, reflective=True))
    z = -z0 * (step + 1) / (step - 1)
    return x, float(np.real(0.5 * (z[x - 1] + z[x])))


def _gate(s: np.ndarray, f: np.ndarray, x: int) -> np.ndarray:
    """时域截断：保留 t < x 的反射响应（劈半点之前 = 外侧夹具部分）。"""

    n = len(f)
    t = _impulse(s, f, reflective=True)
    t[x:] = 0
    return fft(ifftshift(t))[1 : n + 1]


def _symmetrize(m: np.ndarray) -> np.ndarray:
    return 0.5 * (m + np.swapaxes(m, -1, -2))


def symmetric_sqrtm_continuous(
    w: np.ndarray,
    *,
    regularization: float = _DEFAULT_REGULARIZATION,
    iterations: int = _ROOT_ITERATIONS,
) -> np.ndarray:
    """逐频点求 2×2 对称矩阵 ``W`` 的对称平方根 ``K``（``K·K = W``）。

    * 对角元初值取各自的标量平方根，并沿频率做符号连续（同 skrf 的 ``e01``）；
    * 不动点迭代 ``b = w12/(a+d)``、``a = ±√(w11 − b²)``、``d = ±√(w22 − b²)``；
    * ``a+d → 0``（DD 与 CC 半段传输近乎反相）时 ``w12`` 不含 ``b`` 的信息，
      用 Tikhonov 正则化把 ``b`` 平滑地收缩到 0。
    """

    w11 = np.asarray(w[:, 0, 0], dtype=complex)
    w22 = np.asarray(w[:, 1, 1], dtype=complex)
    w12 = 0.5 * (np.asarray(w[:, 0, 1], dtype=complex) + np.asarray(w[:, 1, 0], dtype=complex))

    a = np.sqrt(w11)
    d = np.sqrt(w22)
    for i in range(1, len(a)):
        if abs(-a[i] - a[i - 1]) < abs(a[i] - a[i - 1]):
            a[i] = -a[i]
        if abs(-d[i] - d[i - 1]) < abs(d[i] - d[i - 1]):
            d[i] = -d[i]

    b = np.zeros_like(a)
    for _ in range(max(1, iterations)):
        total = a + d
        eps2 = (regularization * (np.abs(a) + np.abs(d))) ** 2
        b = w12 * np.conj(total) / (np.abs(total) ** 2 + eps2)
        a_next = np.sqrt(w11 - b * b)
        d_next = np.sqrt(w22 - b * b)
        a = np.where(np.abs(-a_next - a) < np.abs(a_next - a), -a_next, a_next)
        d = np.where(np.abs(-d_next - d) < np.abs(d_next - d), -d_next, d_next)

    k = np.empty((len(a), 2, 2), dtype=complex)
    k[:, 0, 0] = a
    k[:, 0, 1] = b
    k[:, 1, 0] = b
    k[:, 1, 1] = d
    return k


def _max_conversion_db(mm: np.ndarray) -> float:
    """``max_f max(|SCD21|, |SDC21|)``（dB，下限 −200 dB）。"""

    if not len(mm):
        return -200.0
    conversion = float(np.max(np.maximum(np.abs(mm[:, 3, 0]), np.abs(mm[:, 1, 2]))))
    return float(20.0 * np.log10(max(conversion, 1e-10)))


# ---------------------------------------------------------------------------
# 劈半器
# ---------------------------------------------------------------------------
class ModeConversionNzc2xThruExtractor(Nzc2xThruExtractor):
    """差分 4 端口混合模 NZC 劈半（保留模式转换）。

    输入为“标准顺序”端口排布（1,2 = 左差分对；3,4 = 右差分对，P 线 1→3、
    N 线 2→4）；输出 ``FixturePair``：``left`` 为“外侧 → DUT 侧”，``right``
    为级联方向（端口 1/2 = DUT 侧，端口 3/4 = 外侧），可直接用于
    ``T_A⁻¹ · T_total · T_B⁻¹``。
    """

    port_count = 4

    def __init__(self, *, regularization: float = _DEFAULT_REGULARIZATION) -> None:
        self.regularization = float(regularization)

    def split(self, thru_2x: rf.Network, *, z0: float = 50.0) -> FixturePair:
        return self.split_with_info(thru_2x, z0=z0)[0]

    def split_with_info(self, thru_2x: rf.Network, *, z0: float = 50.0) -> tuple[FixturePair, ModeConversionSplitInfo]:
        if thru_2x.nports != 4:
            raise UnsupportedPortCountError("含模式转换的混合模劈半仅适用于差分 S4P 2X Thru。")

        z_dd, z_cc = 2.0 * float(z0), float(z0) / 2.0
        mixed = thru_2x.copy()
        mixed.se2gmm(p=2)  # → [d1, d2, c1, c2]，参考阻抗 [2·z0, 2·z0, z0/2, z0/2]
        f = np.asarray(mixed.frequency.f, dtype=float).copy()
        s = np.asarray(mixed.s, dtype=complex).copy()
        max_conversion_db = _max_conversion_db(s)

        # ---- 频率网格：去掉 DC 点；非谐波网格先插值到 f0·(1..N)（同 skrf） ----
        has_dc = bool(f[0] == 0)
        if has_dc:
            f, s = f[1:], s[1:]
        original_f: np.ndarray | None = None
        if f[1] - f[0] != f[0]:
            original_f = f
            projected = int(round(f[-1] / f[0]))
            if projected <= _MAX_HARMONIC_POINTS:
                harmonic = f[0] * (np.arange(projected) + 1)
            else:
                harmonic = f[-1] / _MAX_HARMONIC_POINTS * (np.arange(_MAX_HARMONIC_POINTS) + 1)
            s = scipy.interpolate.interp1d(f, s, axis=0, kind="cubic", fill_value="extrapolate")(harmonic)
            f = harmonic

        # ---- 1. 各模式的劈半点与劈半面阻抗 ----
        x_dd, z_x_dd = _split_point(s[:, 0, 0], s[:, 1, 0], f, z_dd)
        x_cc, z_x_cc = _split_point(s[:, 2, 2], s[:, 3, 2], f, z_cc)

        # ---- 2. 重归一化到劈半面阻抗，并按侧分块 ----
        work = rf.Network(frequency=rf.Frequency.from_f(f, unit="Hz"), s=s, z0=[z_dd, z_dd, z_cc, z_cc])
        work.renormalize([z_x_dd, z_x_dd, z_x_cc, z_x_cc])
        blocks = np.asarray(work.s)[:, _SIDE_BLOCK_ORDER][:, :, _SIDE_BLOCK_ORDER]
        s11, s12 = blocks[:, :2, :2], blocks[:, :2, 2:]
        s21, s22 = blocks[:, 2:, :2], blocks[:, 2:, 2:]

        # ---- 3. 时域门限得到外侧反射 ----
        x_cross = (x_dd + x_cc) // 2
        gates = ((x_dd, x_cross), (x_cross, x_cc))
        a11 = np.zeros_like(s11)
        b22 = np.zeros_like(s22)
        for row in range(2):
            for col in range(2):
                a11[:, row, col] = _gate(s11[:, row, col], f, gates[row][col])
                b22[:, row, col] = _gate(s22[:, row, col], f, gates[row][col])
        a11, b22 = _symmetrize(a11), _symmetrize(b22)

        # ---- 4. 逐频点矩阵代数 ----
        identity = np.eye(2)
        p = (s11 - a11) @ np.linalg.inv(s21)
        r = (s22 - b22) @ np.linalg.inv(s12)
        w = _symmetrize(0.5 * ((identity - r @ p) @ s21 + (identity - p @ r) @ s12))
        k = symmetric_sqrtm_continuous(w, regularization=self.regularization)
        k_inv = np.linalg.inv(k)
        a22 = _symmetrize(k_inv @ r @ k)
        b11 = _symmetrize(k_inv @ p @ k)

        terms = {"a11": a11, "a22": a22, "b11": b11, "b22": b22, "k": k}
        if original_f is not None:
            for name, values in terms.items():
                terms[name] = scipy.interpolate.interp1d(
                    f, values, axis=0, kind="cubic", fill_value="extrapolate", assume_sorted=True
                )(original_f)
            f = original_f
        if has_dc:
            for name, values in terms.items():
                dc = np.empty((1, 2, 2), dtype=complex)
                for row in range(2):
                    for col in range(2):
                        dc[0, row, col] = IEEEP370.dc_interp(values[:, row, col], f)
                terms[name] = np.concatenate((dc, values), axis=0)
            f = np.concatenate(([0.0], f))

        # ---- 5. 组装夹具并转回单端 ----
        frequency = rf.Frequency.from_f(f, unit="Hz")

        def assemble(outer_or_first: np.ndarray, transmission: np.ndarray, second: np.ndarray) -> rf.Network:
            matrix = np.empty((len(f), 4, 4), dtype=complex)
            matrix[:, :2, :2] = outer_or_first
            matrix[:, :2, 2:] = transmission
            matrix[:, 2:, :2] = transmission
            matrix[:, 2:, 2:] = second
            matrix = matrix[:, _SIDE_BLOCK_ORDER][:, :, _SIDE_BLOCK_ORDER]
            network = rf.Network(frequency=frequency, s=matrix, z0=[z_x_dd, z_x_dd, z_x_cc, z_x_cc])
            network.renormalize([z_dd, z_dd, z_cc, z_cc])
            network.gmm2se(p=2, z0_se=float(z0))
            return network

        left = assemble(terms["a11"], terms["k"], terms["a22"])
        right = assemble(terms["b11"], terms["k"], terms["b22"])  # 级联方向：端口 1/2 = DUT 侧
        info = ModeConversionSplitInfo(
            x_dd=x_dd,
            x_cc=x_cc,
            z_x_dd=z_x_dd,
            z_x_cc=z_x_cc,
            max_conversion_db=max_conversion_db,
        )
        return FixturePair(left=left, right=right), info
