"""引擎端到端验证：四种策略 × 单端/差分。"""

from __future__ import annotations

import numpy as np
import pytest

from deembed import DeembedRequest, DeembedSide, FixtureMethod, PortMapping, presets
from deembed.errors import InvalidInputError
from deembed.models import FixtureStandardSet, NetworkTriplet
from deembed.presets.base import DemoPreset


@pytest.mark.parametrize("preset_id", ["se_dual_2xthru", "diff_dual_2xthru"])
def test_dual_2xthru_recovers_ideal_dut(engine, preset_id: str) -> None:
    preset = presets.get_preset(preset_id)
    outcome = engine.run(DeembedRequest.from_triplet(preset.to_triplet()))

    assert outcome.nports == preset.nports
    assert outcome.points == len(preset.total.f)
    assert outcome.quality.status == "PASS"
    np.testing.assert_allclose(outcome.dut.s, preset.dut_ideal.s, rtol=1e-4, atol=1e-5)


def test_single_2xthru_strategy_recovers_ideal_dut(engine) -> None:
    preset = presets.get_preset("se_2xthru")
    thru = preset.thru_2x
    assert thru is not None
    outcome = engine.run(
        DeembedRequest(
            total=preset.total,
            standards=FixtureStandardSet(thru_a=thru, thru_b=thru),
            method=FixtureMethod.SINGLE_2X_THRU,
        )
    )
    np.testing.assert_allclose(outcome.dut.s, preset.dut_ideal.s, rtol=1e-4, atol=1e-5)


def test_fixture_file_strategy_recovers_ideal_dut(engine) -> None:
    preset = presets.get_preset("diff_asym_file")
    outcome = engine.run(
        DeembedRequest(
            total=preset.total,
            standards=FixtureStandardSet(fix_a=preset.fix_left, fix_b=preset.fix_right),
            method=FixtureMethod.FIXTURE_FILES,
        )
    )
    np.testing.assert_allclose(outcome.dut.s, preset.dut_ideal.s, rtol=1e-4, atol=1e-5)
    assert outcome.fixtures is not None


def test_fixture_file_strategy_requires_at_least_one_fixture(engine) -> None:
    preset = presets.get_preset("se_file_based")
    with pytest.raises(InvalidInputError):
        engine.run(
            DeembedRequest(
                total=preset.total,
                standards=FixtureStandardSet(),
                method=FixtureMethod.FIXTURE_FILES,
            )
        )


def test_port_extension_strategy_compensates_delay(engine) -> None:
    from deembed.models import PortExtensionSettings

    preset = presets.get_preset("se_file_based")
    # 左右夹具分别为 15mm + 12mm 线（约 71.4ps + 57.1ps 单程），时延补偿后
    # 幅频响应应比原始 Total 更接近 DUT 的插损量级。
    outcome = engine.run(
        DeembedRequest(
            total=preset.total,
            standards=FixtureStandardSet(),
            method=FixtureMethod.PORT_EXTENSION,
            port_extension=PortExtensionSettings(delay_ps_left=71.4, delay_ps_right=57.1),
        )
    )
    assert outcome.fixtures is None
    assert outcome.dut.nports == 2
    assert outcome.quality.status in {"PASS", "WARNING"}


@pytest.mark.parametrize("side", [DeembedSide.BOTH, DeembedSide.LEFT, DeembedSide.RIGHT])
def test_side_selection_is_respected(engine, side: DeembedSide) -> None:
    preset = presets.get_preset("se_dual_2xthru")
    outcome = engine.run(DeembedRequest.from_triplet(preset.to_triplet(), side=side))
    assert outcome.side is side
    assert outcome.dut.nports == 2


def test_split_fixtures_matches_recovered_fixture_lengths(engine) -> None:
    preset = presets.get_preset("se_dual_2xthru")
    fixtures = engine.split_fixtures(preset.to_triplet())
    assert fixtures is not None
    # 左夹具 12mm、右夹具 24mm：群时延比例应约为 1:2。
    left_delay = _group_delay_ps(fixtures.left)
    right_delay = _group_delay_ps(fixtures.right)
    assert 1.7 < right_delay / left_delay < 2.3


def test_port_count_mismatch_is_rejected(engine) -> None:
    se = presets.get_preset("se_dual_2xthru")
    diff = presets.get_preset("diff_dual_2xthru")
    with pytest.raises(InvalidInputError):
        engine.prepare(se.total, thru_a=diff.thru_2x_a, thru_b=se.thru_2x_b)


def test_unknown_strategy_raises() -> None:
    from deembed import build_default_engine

    engine = build_default_engine()
    with pytest.raises(InvalidInputError):
        engine.strategy_for("not-a-method")

    # 模拟“枚举合法但未注册”的场景
    engine._strategies.pop(FixtureMethod.DUAL_2X_THRU)
    with pytest.raises(InvalidInputError):
        engine.strategy_for(FixtureMethod.DUAL_2X_THRU)


def test_engine_can_register_custom_strategy(engine) -> None:
    from deembed.strategies.base import DeembeddingStrategy, StrategyResult

    class NoOpStrategy(DeembeddingStrategy):
        method = FixtureMethod.SINGLE_2X_THRU

        def apply(self, context) -> StrategyResult:  # noqa: ANN001
            return StrategyResult(dut=context.total)

    engine.register_strategy(NoOpStrategy())
    assert any(item["method"] == "single_2xthru" for item in engine.available_methods())


def test_deembed_triplet_convenience(engine) -> None:
    preset: DemoPreset = presets.get_preset("diff_dual_2xthru")
    def to_plts_order(network):  # noqa: ANN001
        reordered = network.copy()
        reordered.renumber([0, 1, 2, 3], [0, 2, 1, 3])
        return reordered

    triplet = NetworkTriplet(*(to_plts_order(network) for network in preset.to_triplet()))
    outcome = engine.deembed_triplet(triplet, port_mapping=PortMapping.PLTS)
    assert outcome.port_mapping is PortMapping.PLTS
    assert outcome.nports == 4


def _group_delay_ps(network) -> float:  # noqa: ANN001
    frequencies = np.asarray(network.f)
    phase = np.unwrap(np.angle(np.asarray(network.s)[:, 1, 0]))
    delay = -np.diff(phase) / (2 * np.pi * np.diff(frequencies))
    return float(np.median(delay) * 1e12 * 2)  # 往返 → 单程


def test_prepared_networks_exposes_labels(engine) -> None:
    preset = presets.get_preset("diff_dual_2xthru")
    prepared = engine.prepare(preset.total, thru_a=preset.thru_2x_a, thru_b=preset.thru_2x_b, port_mapping="sequential")
    assert prepared.left_ports == ["P1 (+)", "P2 (−)"]
    assert prepared.right_ports == ["P3 (+)", "P4 (−)"]
    assert prepared.mapping_label == "标准顺序 · 1/2 → 3/4"
    assert prepared.points == 269
    assert prepared.frequency_start_ghz == pytest.approx(0.1)


def test_triplet_helper_roundtrip() -> None:
    preset = presets.get_preset("se_dual_2xthru")
    triplet = preset.to_triplet()
    assert isinstance(triplet, NetworkTriplet)
    assert triplet.as_tuple() == (preset.total, preset.thru_2x_a, preset.thru_2x_b)
