"""单端（2 端口）预设示例。"""

from __future__ import annotations

from ..models import FixtureCorrection, FixtureMethod
from .base import DemoPreset
from .builders import VELOCITY_FACTOR, delay_ps_for_length, line, propagation_medium, shunt_capacitor

__all__ = [
    "se_file_based",
    "se_2xthru",
    "se_asym_file",
    "se_asym_2xthru",
    "se_dual_2xthru",
]


def se_file_based() -> DemoPreset:
    """预设 1：单端 File-Based 去嵌（SMA 寄生电容 + 走线损耗）。"""

    medium = propagation_medium(loss_scale=0.06)
    sma = shunt_capacitor(medium, 0.08e-12)
    fix_left = sma**line(medium, 15e-3)
    fix_right = line(medium, 12e-3) ** sma
    dut = line(medium, 20e-3)
    return DemoPreset(
        id="se_file_based",
        title="单端 2-Port 夹具测量去嵌 (File-Based)",
        description="典型单端微带线测试夹具（含 SMA 接头寄生电容与走线损耗），去嵌前后对比插入损耗与回波损耗。",
        method=FixtureMethod.FIXTURE_FILES,
        topology="se",
        total=fix_left**dut**fix_right,
        dut_ideal=dut,
        fix_left=fix_left,
        fix_right=fix_right,
        tags=("file-based", "sma"),
    )


def se_2xthru() -> DemoPreset:
    """预设 2：单端 IEEE 370 2X Thru 对称劈半（AFR）。"""

    medium = propagation_medium()
    half = line(medium, 20e-3)
    thru = half**half.flipped()
    dut = line(medium, 25e-3)
    return DemoPreset(
        id="se_2xthru",
        title="单端 IEEE 370 2X Thru 自动夹具剥离 (AFR)",
        description="基于 IEEE 370 2X Thru 标准件自动劈半为 1X 左右夹具模型，消除夹具走线衰减与相位延迟。",
        method=FixtureMethod.SINGLE_2X_THRU,
        topology="se",
        total=half**dut**half.flipped(),
        dut_ideal=dut,
        thru_2x=thru,
        tags=("afr", "ieee370"),
    )


def se_asym_file() -> DemoPreset:
    """预设 3：单端非对称夹具文件（Fixture A ≠ B）。"""

    medium = propagation_medium(loss_scale=0.06)
    fix_a = shunt_capacitor(medium, 0.08e-12) ** line(medium, 12e-3)
    fix_b = line(medium, 24e-3) ** shunt_capacitor(medium, 0.04e-12)
    dut = line(medium, 30e-3)
    return DemoPreset(
        id="se_asym_file",
        title="单端非对称双边去嵌 (Fixture A ≠ B: 独立夹具文件)",
        description="左端夹具 12 mm（SMA 接头），右端夹具 24 mm（2.92 mm 接头），双边非对称全去嵌。",
        method=FixtureMethod.FIXTURE_FILES,
        topology="se",
        total=fix_a**dut**fix_b,
        dut_ideal=dut,
        fix_left=fix_a,
        fix_right=fix_b,
        fixture_symmetry="asymmetric",
        tags=("file-based", "asymmetric"),
    )


def se_asym_2xthru() -> DemoPreset:
    """预设 4：单端 2X Thru 非对称长度校正（PLTS Length A ≠ B）。"""

    medium = propagation_medium()
    fix_a = line(medium, 12e-3)
    fix_b = line(medium, 24e-3)
    thru = line(medium, 36e-3)
    dut = line(medium, 25e-3)
    delta_a = delay_ps_for_length(-6e-3, 3e8 * VELOCITY_FACTOR)
    delta_b = delay_ps_for_length(6e-3, 3e8 * VELOCITY_FACTOR)
    return DemoPreset(
        id="se_asym_2xthru",
        title="单端 2X Thru 非对称去嵌 (PLTS Length A ≠ B 长度校正)",
        description="2X Thru 总长 36 mm，实际左夹具 12 mm（33%）、右夹具 24 mm（67%），应用 PLTS 非对称长度校正。",
        method=FixtureMethod.SINGLE_2X_THRU,
        topology="se",
        total=fix_a**dut**fix_b,
        dut_ideal=dut,
        thru_2x=thru,
        fixture_symmetry="asymmetric",
        correction_a=FixtureCorrection(delay_ps=delta_a),
        correction_b=FixtureCorrection(delay_ps=delta_b),
        length_ratio_a=12.0 / 36.0,
        length_ratio_b=24.0 / 36.0,
        tags=("afr", "asymmetric", "plts"),
    )


def se_dual_2xthru() -> DemoPreset:
    """预设 5：单端独立双 2X Thru 分别劈半（网页默认场景）。"""

    medium = propagation_medium()
    fix_a = line(medium, 12e-3)
    fix_b = line(medium, 24e-3)
    thru_a = line(medium, 24e-3)   # A + A
    thru_b = line(medium, 48e-3)   # B + B
    dut = line(medium, 25e-3)
    return DemoPreset(
        id="se_dual_2xthru",
        title="单端独立双 2X Thru 劈半去嵌 (2X Thru A + 2X Thru B)",
        description="提供夹具 A 的 2X Thru 与夹具 B 的 2X Thru，分别独立劈半提取 1X A 与 1X B，再从待测文件中去嵌。",
        method=FixtureMethod.DUAL_2X_THRU,
        topology="se",
        total=fix_a**dut**fix_b,
        dut_ideal=dut,
        thru_2x=thru_a,
        thru_2x_a=thru_a,
        thru_2x_b=thru_b,
        fix_left=fix_a,
        fix_right=fix_b,
        fixture_symmetry="asymmetric",
        tags=("dual-2x-thru", "asymmetric"),
    )
