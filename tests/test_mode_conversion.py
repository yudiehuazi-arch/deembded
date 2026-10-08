"""含模式转换的混合模 NZC 劈半、skew 诊断与劈半算法选择。"""

from __future__ import annotations

import numpy as np
import pytest
import skrf as rf
from skrf.network import concat_ports

from deembed import DeembedRequest, NetworkTriplet, SplitAlgorithm, presets
from deembed.diagnostics import estimate_pn_skew_ps, max_mode_conversion_db, sdd21
from deembed.errors import InvalidInputError, UnsupportedPortCountError
from deembed.fixtures import (
    MixedModeNzc2xThruExtractor,
    ModeConversionNzc2xThruExtractor,
    SingleEndedNzc2xThruExtractor,
    adjust_fixture_delay_loss,
    get_extractor,
)
from deembed.fixtures.mode_conversion import symmetric_sqrtm_continuous
from deembed.matrices import deembed_network
from deembed.presets.builders import propagation_medium

MC = ModeConversionNzc2xThruExtractor()
CLASSIC = MixedModeNzc2xThruExtractor()


def _db(values: np.ndarray) -> np.ndarray:
    return 20 * np.log10(np.abs(values))


def _pair(medium: rf.media.DefinedGammaZ0, length_p: float, length_n: float) -> rf.Network:
    """两条不耦合的 50 Ω 线（P 线 1→3，N 线 2→4）。"""

    return concat_ports([medium.line(length_p, "m"), medium.line(length_n, "m")], port_order="second")


def _launch(medium: rf.media.DefinedGammaZ0, cap_p: float, cap_n: float) -> rf.Network:
    """P/N 不对称的发射端（各一个并联电容）→ 反射中的模式转换。"""

    return concat_ports([medium.shunt_capacitor(cap_p), medium.shunt_capacitor(cap_n)], port_order="second")


def _skewed_case(frequency: rf.Frequency, *, launches: bool) -> tuple[NetworkTriplet, rf.Network]:
    """夹具 A/B 与 DUT 都带同向 P/N skew；可选不对称发射端。"""

    medium = propagation_medium(frequency=frequency)
    fix_a = _pair(medium, 15.4e-3, 15e-3)
    fix_b = _pair(medium, 30.3e-3, 30e-3)  # 外侧 → DUT 侧
    if launches:
        fix_a = _launch(medium, 0.02e-12, 0.035e-12) ** fix_a
        fix_b = _launch(medium, 0.03e-12, 0.018e-12) ** fix_b
    dut = _pair(medium, 25.4e-3, 25e-3)
    triplet = NetworkTriplet(
        total=fix_a**dut**fix_b.flipped(),
        thru_a=fix_a**fix_a.flipped(),
        thru_b=fix_b**fix_b.flipped(),
    )
    return triplet, dut


def _deembed(triplet: NetworkTriplet, extractor) -> rf.Network:  # noqa: ANN001
    left = extractor.split(triplet.thru_a).left
    right = extractor.split(triplet.thru_b).right
    return deembed_network(triplet.total, left=left, right=right, side="both")


# ---------------------------------------------------------------------------
# 劈半器本身
# ---------------------------------------------------------------------------
def test_mode_conversion_split_reduces_to_classic_without_conversion(diff_preset) -> None:  # noqa: ANN001
    for thru in (diff_preset.thru_2x_a, diff_preset.thru_2x_b):
        mc = MC.split(thru)
        classic = CLASSIC.split(thru)
        np.testing.assert_allclose(mc.left.s, classic.left.s, atol=1e-9)
        np.testing.assert_allclose(mc.right.s, classic.right.s, atol=1e-9)
        np.testing.assert_allclose(mc.left.f, thru.f)


def test_fixture_models_reproduce_the_2x_thru_with_skew() -> None:
    preset = presets.get_preset("diff_skew_dual_2xthru")
    pair, info = MC.split_with_info(preset.thru_2x_a)
    residual = np.max(np.abs((pair.left**pair.right).s - preset.thru_2x_a.s))
    assert residual < 1e-2
    assert info.max_conversion_db > -10  # 2X Thru A 有明显的 SCD21
    assert info.z_x_dd == pytest.approx(100.0, rel=1e-3)
    assert info.z_x_cc == pytest.approx(25.0, rel=1e-3)
    # 经典算法丢弃了 SDC/SCD，无法自洽地复现 2X Thru
    classic = CLASSIC.split(preset.thru_2x_a)
    assert np.max(np.abs((classic.left**classic.right).s - preset.thru_2x_a.s)) > 0.1


def test_skew_preset_is_recovered_only_with_mode_conversion(engine) -> None:  # noqa: ANN001
    preset = presets.get_preset("diff_skew_dual_2xthru")
    truth = _db(sdd21(preset.dut_ideal))

    mc = engine.run(DeembedRequest.from_triplet(preset.to_triplet(), split_algorithm=SplitAlgorithm.MODE_CONVERSION))
    classic = engine.run(DeembedRequest.from_triplet(preset.to_triplet(), split_algorithm=SplitAlgorithm.CLASSIC))

    mc_error = _db(sdd21(mc.dut)) - truth
    classic_error = _db(sdd21(classic.dut)) - truth
    assert np.max(np.abs(mc_error)) < 0.02
    assert mc.quality.status == "PASS"
    # 夹具与 DUT skew 同向 → 经典算法 SDD21 偏低（损耗偏大），且随频率增大
    assert classic_error[-1] < -1.0
    quarter = len(classic_error) // 4
    assert classic_error[quarter] > classic_error[2 * quarter] > classic_error[-1]


def test_conversion_in_reflections_from_asymmetric_launches() -> None:
    frequency = rf.Frequency(0.05, 40, 800, unit="ghz")
    triplet, dut = _skewed_case(frequency, launches=True)
    truth = _db(sdd21(dut))
    # IEEE 370 NZC 的时域硬截断在最高频端对强反射不可靠（经典算法同样如此），只评估 90% 频段
    band = frequency.f <= 0.9 * frequency.f[-1]

    mc_dut = _deembed(triplet, MC)
    classic_dut = _deembed(triplet, CLASSIC)

    assert np.max(np.abs(_db(sdd21(mc_dut)) - truth)[band]) < 0.05
    assert np.max(np.abs(_db(sdd21(classic_dut)) - truth)[band]) > 0.3
    # 全矩阵（含 SDD11、SCD21 等）也应还原
    assert np.max(np.abs(mc_dut.s - dut.s)[band]) < 0.05
    assert np.max(np.abs(classic_dut.s - dut.s)[band]) > 0.1


@pytest.mark.parametrize(
    "frequency",
    [
        rf.Frequency(0.0, 40, 801, unit="ghz"),  # 含 DC 点
        rf.Frequency(0.05, 40, 800, unit="ghz"),  # 谐波网格（start == step）
        rf.Frequency(0.3e-3, 40, 1601, unit="ghz"),  # 非谐波网格 → 内部插值
    ],
)
def test_mode_conversion_split_handles_dc_and_grids(frequency: rf.Frequency) -> None:
    triplet, dut = _skewed_case(frequency, launches=False)
    mc_dut = _deembed(triplet, MC)
    np.testing.assert_allclose(mc_dut.f, dut.f)
    band = mc_dut.f > 0
    error = _db(sdd21(mc_dut))[band] - _db(sdd21(dut))[band]
    assert np.all(np.isfinite(mc_dut.s))
    assert np.max(np.abs(error[: int(0.95 * len(error))])) < 0.05


def test_mode_conversion_split_rejects_two_ports(se_preset) -> None:  # noqa: ANN001
    with pytest.raises(UnsupportedPortCountError):
        MC.split(se_preset.thru_2x_a)


def test_symmetric_sqrtm_recovers_continuous_root() -> None:
    f = np.linspace(0.1, 40, 400)
    a = 0.95 * np.exp(-1j * 0.21 * f)
    d = 0.93 * np.exp(-1j * 0.20 * f)
    b = 0.08 * np.exp(-1j * 0.205 * f) * np.sin(0.05 * f)
    k = np.zeros((len(f), 2, 2), dtype=complex)
    k[:, 0, 0], k[:, 0, 1], k[:, 1, 0], k[:, 1, 1] = a, b, b, d
    w = k @ k
    root = symmetric_sqrtm_continuous(w, regularization=0.0, iterations=30)
    np.testing.assert_allclose(root, k, atol=1e-9)


def test_symmetric_sqrtm_regularizes_unobservable_conversion() -> None:
    # DD 与 CC 半段传输反相（a = −d）：w12 不含 b 的信息，b 应收缩为 0 而不是发散
    a = np.full(5, 0.9 + 0j)
    w = np.zeros((5, 2, 2), dtype=complex)
    w[:, 0, 0] = a * a
    w[:, 1, 1] = a * a
    w[:, 0, 1] = w[:, 1, 0] = 1e-4  # 噪声
    root = symmetric_sqrtm_continuous(w)
    assert np.all(np.isfinite(root))
    assert np.max(np.abs(root[:, 0, 1])) < 1e-2


# ---------------------------------------------------------------------------
# 诊断
# ---------------------------------------------------------------------------
def test_skew_estimate_matches_construction() -> None:
    preset = presets.get_preset("diff_skew_dual_2xthru")
    per_mm = 1e-3 / (3e8 * 0.7) * 1e12  # ps / mm
    assert estimate_pn_skew_ps(preset.thru_2x_a) == pytest.approx(0.6 * per_mm, rel=0.01)
    assert estimate_pn_skew_ps(preset.thru_2x_b) == pytest.approx(0.4 * per_mm, rel=0.01)
    assert estimate_pn_skew_ps(preset.dut_ideal) == pytest.approx(0.3 * per_mm, rel=0.01)
    assert estimate_pn_skew_ps(preset.dut_ideal.flipped()) == pytest.approx(0.3 * per_mm, rel=0.01)
    swapped = preset.dut_ideal.copy()
    swapped.renumber([0, 1, 2, 3], [1, 0, 3, 2])  # P/N 互换 → skew 变号
    assert estimate_pn_skew_ps(swapped) == pytest.approx(-0.3 * per_mm, rel=0.01)


def test_diagnostics_handle_ideal_and_two_port_networks(diff_preset, se_preset) -> None:  # noqa: ANN001
    assert estimate_pn_skew_ps(se_preset.thru_2x_a) is None
    assert max_mode_conversion_db(se_preset.thru_2x_a) is None
    assert abs(estimate_pn_skew_ps(diff_preset.thru_2x_a)) < 1e-6
    assert max_mode_conversion_db(diff_preset.thru_2x_a) == pytest.approx(-200.0)


def test_engine_comparison_and_diagnostics(engine) -> None:  # noqa: ANN001
    preset = presets.get_preset("diff_skew_dual_2xthru")
    outcome = engine.run(DeembedRequest.from_triplet(preset.to_triplet(), compare_split_algorithms=True))
    assert outcome.split_algorithm is SplitAlgorithm.MODE_CONVERSION
    assert outcome.comparison_dut is not None
    assert "dut_alt" in outcome.display_networks()

    payload = outcome.diagnostics.to_payload()
    comparison = payload["comparison"]
    assert comparison["primary"] == "mc_nzc" and comparison["alternative"] == "classic_nzc"
    assert comparison["max_delta_db"] > 1.0  # 含模式转换 − 经典 > 0：经典结果偏低
    assert comparison["max_delta_ghz"] == pytest.approx(67.0)
    assert [round(point["freq_ghz"]) for point in comparison["checkpoints"]] == [17, 34, 50, 67]
    assert payload["thru_a"]["skew_ps"] == pytest.approx(2.857, abs=0.02)
    assert payload["dut"]["skew_ps"] == pytest.approx(1.429, abs=0.03)

    reverse = engine.run(
        DeembedRequest.from_triplet(
            preset.to_triplet(), split_algorithm=SplitAlgorithm.CLASSIC, compare_split_algorithms=True
        )
    )
    assert reverse.diagnostics.comparison.max_delta_db == pytest.approx(
        -outcome.diagnostics.comparison.max_delta_db, abs=1e-9
    )
    np.testing.assert_allclose(reverse.comparison_dut.s, outcome.dut.s, atol=1e-12)


def test_engine_skips_comparison_for_single_ended_and_by_default(engine, se_preset, diff_preset) -> None:  # noqa: ANN001
    se = engine.run(DeembedRequest.from_triplet(se_preset.to_triplet(), compare_split_algorithms=True))
    assert se.comparison_dut is None and se.diagnostics is None
    diff = engine.run(DeembedRequest.from_triplet(diff_preset.to_triplet()))
    assert diff.comparison_dut is None and diff.diagnostics is None
    assert "dut_alt" not in diff.display_networks()


# ---------------------------------------------------------------------------
# 算法选择与夹具校正
# ---------------------------------------------------------------------------
def test_extractor_registry_by_algorithm() -> None:
    assert isinstance(get_extractor(4), MixedModeNzc2xThruExtractor)  # 历史默认：经典
    assert isinstance(get_extractor(4, SplitAlgorithm.MODE_CONVERSION), ModeConversionNzc2xThruExtractor)
    assert isinstance(get_extractor(4, "classic_nzc"), MixedModeNzc2xThruExtractor)
    assert isinstance(get_extractor(2, "mc_nzc"), SingleEndedNzc2xThruExtractor)
    with pytest.raises(InvalidInputError):
        get_extractor(4, "magic")
    with pytest.raises(UnsupportedPortCountError):
        get_extractor(3, SplitAlgorithm.CLASSIC)


def test_split_algorithm_labels_and_alternative() -> None:
    assert SplitAlgorithm.MODE_CONVERSION.alternative is SplitAlgorithm.CLASSIC
    assert SplitAlgorithm.CLASSIC.alternative is SplitAlgorithm.MODE_CONVERSION
    assert "模式转换" in SplitAlgorithm.MODE_CONVERSION.label
    assert SplitAlgorithm.parse(" MC_NZC ", field="劈半算法") is SplitAlgorithm.MODE_CONVERSION


def test_fixture_correction_acts_on_the_dut_side() -> None:
    frequency = rf.Frequency(1, 10, 10, unit="ghz")
    s = np.tile(np.array([[0.1, 0.8], [0.8, 0.2]], dtype=complex), (10, 1, 1))
    fixture = rf.Network(frequency=frequency, s=s, z0=50)
    factor = np.exp(-1j * 2 * np.pi * frequency.f * 5e-12)

    left = adjust_fixture_delay_loss(fixture, delta_delay_ps=5.0)  # 外侧 → DUT 侧：端口 2
    np.testing.assert_allclose(left.s[:, 0, 0], 0.1)
    np.testing.assert_allclose(left.s[:, 1, 1], 0.2 * factor**2)
    np.testing.assert_allclose(left.s[:, 1, 0], 0.8 * factor)

    right = adjust_fixture_delay_loss(fixture, delta_delay_ps=5.0, dut_side="first")  # 级联方向：端口 1
    np.testing.assert_allclose(right.s[:, 0, 0], 0.1 * factor**2)
    np.testing.assert_allclose(right.s[:, 1, 1], 0.2)
    np.testing.assert_allclose(right.s[:, 0, 1], 0.8 * factor)

    with pytest.raises(InvalidInputError):
        adjust_fixture_delay_loss(fixture, delta_delay_ps=5.0, dut_side="middle")
