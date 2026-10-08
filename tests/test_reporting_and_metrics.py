"""报表构建与质量指标的单元测试。"""

from __future__ import annotations

import numpy as np
import pytest
import skrf as rf

from deembed.metrics import QualityAnalyzer
from deembed.models import PortMapping
from deembed.reporting import (
    ChartDataBuilder,
    FixtureStatisticsAnalyzer,
    NetworkPreviewBuilder,
    downsample_indices,
    level_crossings,
)


def _two_port() -> rf.Network:
    freq = rf.Frequency.from_f(np.linspace(0.1e9, 20e9, 64), unit="hz")
    rng = np.random.default_rng(11)
    s = rng.normal(scale=0.2, size=(64, 2, 2)) + 1j * rng.normal(scale=0.05, size=(64, 2, 2))
    return rf.Network(frequency=freq, s=s, z0=50.0)


def test_downsample_indices_keeps_endpoints() -> None:
    indices = downsample_indices(1000, 100)
    assert indices[0] == 0
    assert indices[-1] == 999
    assert len(indices) <= 101


def test_level_crossings_handles_points_and_ranges() -> None:
    freq = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    difference = np.array([-1.0, 0.0, 1.0, 0.0, -1.0])

    crossing = level_crossings(freq, difference, 0.0)
    assert crossing.points_ghz == (1.0, 3.0)

    flat = level_crossings(np.array([0.0, 1.0, 2.0]), np.array([0.0, 0.0, 0.0]), 0.0)
    assert flat.ranges_ghz == ((0.0, 2.0),)


def test_preview_contains_all_single_ended_parameters() -> None:
    preview = NetworkPreviewBuilder(max_points=16).build(_two_port(), PortMapping.SINGLE_ENDED)
    assert set(preview.series) == {"S11", "S12", "S21", "S22"}
    assert len(preview.freq_ghz) <= 17
    assert all(len(values) == len(preview.freq_ghz) for values in preview.series.values())


def test_chart_builder_keeps_network_dimension() -> None:
    networks = {"total": _two_port(), "dut": _two_port()}
    chart = ChartDataBuilder(max_points=32).build(networks, PortMapping.SINGLE_ENDED)
    assert chart.network_keys == ["total", "dut"]
    assert set(chart.series["S21"]) == {"total", "dut"}
    assert len(chart.freq_ghz) == len(chart.series["S21"]["total"])


def test_fixture_statistics_skips_two_port_networks() -> None:
    assert FixtureStatisticsAnalyzer().analyze(_two_port(), PortMapping.SINGLE_ENDED) == []


def test_quality_analyzer_flags_passive_and_reciprocal_network() -> None:
    analyzer = QualityAnalyzer()
    reciprocal = _two_port()
    reciprocal.s[:, 1, 0] = reciprocal.s[:, 0, 1]
    reciprocal.s[:, 0, 0] = 0.05
    reciprocal.s[:, 1, 1] = 0.05
    reciprocal.s[:, 1, 0] = 0.5
    reciprocal.s[:, 0, 1] = 0.5

    report = analyzer.analyze(reciprocal)
    assert report.passivity_pass is True
    assert report.reciprocity_pass is True
    assert report.status == "PASS"

    active = _two_port()
    active.s[:] = 2.0
    assert analyzer.analyze(active).passivity_pass is False


def test_quality_payload_keys_are_stable() -> None:
    payload = QualityAnalyzer().analyze(_two_port()).to_payload()
    assert set(payload) == {
        "status",
        "verdict",
        "max_singular_value",
        "passivity_pass",
        "passivity_margin_db",
        "reciprocity_error",
        "reciprocity_pass",
    }
    assert isinstance(payload["max_singular_value"], float)


@pytest.mark.parametrize("tolerance", [1.0, 1.005, 1.01])
def test_quality_tolerance_is_configurable(tolerance: float) -> None:
    network = _two_port()
    network.s[:] = 0.0
    network.s[:, 0, 0] = 1.002
    network.s[:, 1, 1] = 1.002
    report = QualityAnalyzer(passivity_tolerance=tolerance).analyze(network)
    assert report.passivity_pass is (1.002 <= tolerance)
