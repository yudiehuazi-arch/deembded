"""S 参数 ↔ 广义传输矩阵（T 矩阵）代数与级联反演。

数学约定见 ``docs/DEEMBED_GUIDE.md`` 第 2 章：

    T = [[inv(S21),      -inv(S21)·S22],
         [S11·inv(S21),   S12 - S11·inv(S21)·S22]]
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
import skrf as rf

from .errors import ComputationError
from .models import DeembedSide

__all__ = ["s_to_t", "t_to_s", "cascade_deembed", "deembed_network", "invert_matrix"]


def _split_blocks(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    n_total = matrix.shape[-1]
    n = n_total // 2
    if n_total % 2 != 0:
        raise ComputationError(f"矩阵维度必须为偶数端口，收到 {n_total}。")
    return (
        matrix[..., :n, :n],
        matrix[..., :n, n:],
        matrix[..., n:, :n],
        matrix[..., n:, n:],
    )


def _merge_blocks(top_left: np.ndarray, top_right: np.ndarray, bottom_left: np.ndarray, bottom_right: np.ndarray) -> np.ndarray:
    top = np.concatenate([top_left, top_right], axis=-1)
    bottom = np.concatenate([bottom_left, bottom_right], axis=-1)
    return np.concatenate([top, bottom], axis=-2)


def _safe_inverse(matrix: np.ndarray, *, context: str) -> np.ndarray:
    try:
        return np.linalg.inv(matrix)
    except np.linalg.LinAlgError as exc:
        raise ComputationError(f"{context} 矩阵求逆失败（奇异矩阵），请检查夹具数据与频段。") from exc


def invert_matrix(matrix: np.ndarray, *, context: str = "级联") -> np.ndarray:
    """对 T 矩阵逐频点求逆，失败时给出可读的领域错误。"""

    return _safe_inverse(np.asarray(matrix), context=context)


def s_to_t(s_matrix: np.ndarray) -> np.ndarray:
    """S → 广义 T 矩阵。输入形状 ``(..., 2N, 2N)``。"""

    s11, s12, s21, s22 = _split_blocks(np.asarray(s_matrix))
    inv_s21 = _safe_inverse(s21, context="S→T")
    t11 = inv_s21
    t12 = -(inv_s21 @ s22)
    t21 = s11 @ inv_s21
    t22 = s12 - (s11 @ inv_s21 @ s22)
    return _merge_blocks(t11, t12, t21, t22)


def t_to_s(t_matrix: np.ndarray) -> np.ndarray:
    """广义 T → S 矩阵。"""

    t11, t12, t21, t22 = _split_blocks(np.asarray(t_matrix))
    inv_t11 = _safe_inverse(t11, context="T→S")
    s11 = t21 @ inv_t11
    s12 = t22 - (t21 @ inv_t11 @ t12)
    s21 = inv_t11
    s22 = -(inv_t11 @ t12)
    return _merge_blocks(s11, s12, s21, s22)


def cascade_deembed(
    s_total: np.ndarray,
    s_left: np.ndarray | None = None,
    s_right: np.ndarray | None = None,
    side: DeembedSide | str = DeembedSide.BOTH,
) -> np.ndarray:
    """按去嵌范围执行 T 矩阵级联反演。

    ``side`` 语义：
    * ``both``  —— ``T_DUT = T_A⁻¹ · T_Total · T_B⁻¹``
    * ``left``  —— ``T_DUT = T_A⁻¹ · T_Total``
    * ``right`` —— ``T_DUT = T_Total · T_B⁻¹``
    """

    resolved_side = DeembedSide.parse(side, field="去嵌侧") if not isinstance(side, DeembedSide) else side
    t_total = s_to_t(s_total)

    if resolved_side is DeembedSide.LEFT and s_left is not None:
        return t_to_s(invert_matrix(s_to_t(s_left), context="左夹具") @ t_total)
    if resolved_side is DeembedSide.RIGHT and s_right is not None:
        return t_to_s(t_total @ invert_matrix(s_to_t(s_right), context="右夹具"))
    if resolved_side is DeembedSide.BOTH:
        t_dut = t_total
        if s_left is not None:
            t_dut = invert_matrix(s_to_t(s_left), context="左夹具") @ t_dut
        if s_right is not None:
            t_dut = t_dut @ invert_matrix(s_to_t(s_right), context="右夹具")
        return t_to_s(t_dut)
    return t_to_s(t_total)


def deembed_network(
    total: rf.Network,
    *,
    left: rf.Network | None = None,
    right: rf.Network | None = None,
    side: DeembedSide | str = DeembedSide.BOTH,
    z0: float | Sequence[float] | None = None,
) -> rf.Network:
    """在 ``rf.Network`` 层面执行级联反演，返回新的 DUT 网络。"""

    s_dut = cascade_deembed(total.s, left.s if left is not None else None, right.s if right is not None else None, side=side)
    reference = np.asarray(total.z0) if z0 is None else z0
    return rf.Network(frequency=total.frequency, s=s_dut, z0=reference)
