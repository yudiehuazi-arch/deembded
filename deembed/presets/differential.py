"""差分（4 端口）预设示例。"""

from __future__ import annotations

from ..models import FixtureCorrection, FixtureMethod
from .base import DemoPreset
from skrf.network import concat_ports

from .builders import VELOCITY_FACTOR, delay_ps_for_length, line, propagation_medium, transmission_line_pair

__all__ = [
    "diff_file_based",
    "diff_2xthru",
    "diff_asym_file",
    "diff_asym_2xthru",
    "diff_dual_2xthru",
]


def diff_file_based() -> DemoPreset:
    """预设 6：差分 4 端口全耦合夹具 File-Based 去嵌。"""

    medium = propagation_medium()
    fix_left = transmission_line_pair(medium, 16e-3)
    fix_right = transmission_line_pair(medium, 14e-3)
    dut = _skewed_pair(medium)
    return DemoPreset(
        id="diff_file_based",
        title="差分 4-Port 全耦合夹具去嵌 (File-Based)",
        description="4 端口差分网络去嵌，支持 PLTS 交叉或标准顺序端口排布，展示 SDD21/SDD11 改善及 SCD21 模态转换。",
        method=FixtureMethod.FIXTURE_FILES,
        topology="diff",
        total=fix_left**dut**fix_right,
        dut_ideal=dut,
        fix_left=fix_left,
        fix_right=fix_right,
        tags=("file-based", "diff"),
    )


def diff_2xthru() -> DemoPreset:
    """预设 7：差分 4 端口 IEEE 370 混合模 2X Thru 对称劈半。"""

    medium = propagation_medium()
    half = transmission_line_pair(medium, 15e-3)
    thru = half**half.flipped()
    dut = transmission_line_pair(medium, 28e-3)
    return DemoPreset(
        id="diff_2xthru",
        title="差分 4-Port IEEE 370 2X Thru 混合模 AFR 去嵌",
        description="利用 4 端口差分 2X Thru 标准件，通过 IEEE 370 算法剥离差分夹具对，获取纯净 DUT 的 SDD/SCC 响应。",
        method=FixtureMethod.SINGLE_2X_THRU,
        topology="diff",
        total=half**dut**half.flipped(),
        dut_ideal=dut,
        thru_2x=thru,
        tags=("afr", "diff", "ieee370"),
    )


def diff_asym_file() -> DemoPreset:
    """预设 8：差分非对称夹具文件（Fixture A ≠ B）。"""

    medium = propagation_medium()
    fix_a = transmission_line_pair(medium, 12e-3)
    fix_b = transmission_line_pair(medium, 24e-3)
    dut = transmission_line_pair(medium, 30e-3)
    return DemoPreset(
        id="diff_asym_file",
        title="差分 4-Port 非对称双边去嵌 (Fixture A ≠ B)",
        description="左侧差分夹具 12 mm、右侧差分夹具 24 mm，双边消除完全不对称的差分测试夹具。",
        method=FixtureMethod.FIXTURE_FILES,
        topology="diff",
        total=fix_a**dut**fix_b,
        dut_ideal=dut,
        fix_left=fix_a,
        fix_right=fix_b,
        fixture_symmetry="asymmetric",
        tags=("file-based", "diff", "asymmetric"),
    )


def diff_asym_2xthru() -> DemoPreset:
    """预设 9：差分 2X Thru 非对称长度校正（PLTS Length A ≠ B）。"""

    medium = propagation_medium()
    fix_a = transmission_line_pair(medium, 12e-3)
    fix_b = transmission_line_pair(medium, 24e-3)
    thru = transmission_line_pair(medium, 36e-3)
    dut = transmission_line_pair(medium, 25e-3)
    delta_a = delay_ps_for_length(-6e-3, 3e8 * VELOCITY_FACTOR)
    delta_b = delay_ps_for_length(6e-3, 3e8 * VELOCITY_FACTOR)
    return DemoPreset(
        id="diff_asym_2xthru",
        title="差分 2X Thru 非对称去嵌 (PLTS Length A ≠ B 长度校正)",
        description="差分 2X Thru 总长 36 mm，实际左夹具 12 mm（33%）、右夹具 24 mm（67%），劈半后分别做长度校正。",
        method=FixtureMethod.SINGLE_2X_THRU,
        topology="diff",
        total=fix_a**dut**fix_b,
        dut_ideal=dut,
        thru_2x=thru,
        fixture_symmetry="asymmetric",
        correction_a=FixtureCorrection(delay_ps=delta_a),
        correction_b=FixtureCorrection(delay_ps=delta_b),
        length_ratio_a=12.0 / 36.0,
        length_ratio_b=24.0 / 36.0,
        tags=("afr", "diff", "asymmetric", "plts"),
    )


def diff_dual_2xthru() -> DemoPreset:
    """预设 10：差分独立双 2X Thru 分别劈半。"""

    medium = propagation_medium()
    fix_a = transmission_line_pair(medium, 12e-3)
    fix_b = transmission_line_pair(medium, 24e-3)
    thru_a = transmission_line_pair(medium, 24e-3)
    thru_b = transmission_line_pair(medium, 48e-3)
    dut = transmission_line_pair(medium, 25e-3)
    return DemoPreset(
        id="diff_dual_2xthru",
        title="差分 4-Port 独立双 2X Thru 劈半去嵌 (2X Thru A + 2X Thru B)",
        description="提供差分 2X Thru A 与 2X Thru B，分别劈半提取差分 1X A 与 1X B，实现非对称差分对完全去嵌。",
        method=FixtureMethod.DUAL_2X_THRU,
        topology="diff",
        total=fix_a**dut**fix_b,
        dut_ideal=dut,
        thru_2x=thru_a,
        thru_2x_a=thru_a,
        thru_2x_b=thru_b,
        fix_left=fix_a,
        fix_right=fix_b,
        fixture_symmetry="asymmetric",
        tags=("dual-2x-thru", "diff", "asymmetric"),
    )


def _skewed_pair(medium: "object", length_a: float = 30e-3, length_b: float = 30.2e-3):
    """构造带轻微偏斜的差分对（用于演示 SCD21 模态转换）。"""

    return concat_ports([line(medium, length_a), line(medium, length_b)], port_order="second")
