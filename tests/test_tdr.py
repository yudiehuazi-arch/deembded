"""TDR 阶跃阻抗变换的单元测试。"""

from __future__ import annotations

import numpy as np
import pytest
import skrf as rf

from deembed.errors import ComputationError, InvalidInputError
from deembed.models import DcMethod, PortMapping, TdrWindow
from deembed.tdr import TdrAnalyzer, TdrSettings


def _matched_line_network(points: int = 129) -> rf.Network:
    """理想 50 Ω 匹配负载：反射为 0，阶跃阻抗应恒等于 50 Ω。"""

    freq = rf.Frequency.from_f(np.linspace(0.0, 20e9, points), unit="hz")
    s = np.zeros((points, 2, 2), dtype=complex)
    return rf.Network(frequency=freq, s=s, z0=50.0)


def _mismatched_network(z0_reflection: float = 0.2, points: int = 129) -> rf.Network:
    freq = rf.Frequency.from_f(np.linspace(0.0, 20e9, points), unit="hz")
    s = np.zeros((points, 2, 2), dtype=complex)
    s[:, 0, 0] = z0_reflection
    return rf.Network(frequency=freq, s=s, z0=50.0)


def test_matched_network_gives_reference_impedance() -> None:
    analyzer = TdrAnalyzer()
    trace = analyzer.step_impedance(
        _matched_line_network(),
        settings=TdrSettings(window=TdrWindow.NONE),
        port_mapping=PortMapping.SINGLE_ENDED,
        reference_z0=50.0,
    )
    assert trace.parameter == "S11"
    assert trace.reference_ohm == 50.0
    finite = [value for value in trace.impedance_ohm if value is not None]
    assert finite
    assert all(abs(value - 50.0) < 1.0 for value in finite)


def test_reflection_maps_to_expected_impedance() -> None:
    analyzer = TdrAnalyzer()
    trace = analyzer.step_impedance(
        _mismatched_network(0.2),
        settings=TdrSettings(window=TdrWindow.NONE),
        port_mapping=PortMapping.SINGLE_ENDED,
        reference_z0=50.0,
    )
    # Z = 50 * (1 + 0.2) / (1 - 0.2) = 75 Ω
    finite = [value for value in trace.impedance_ohm if value is not None]
    assert any(abs(value - 75.0) < 2.0 for value in finite)


def test_differential_network_uses_double_reference() -> None:
    analyzer = TdrAnalyzer()
    diff = _matched_line_network()
    diff.s = np.zeros((len(diff.f), 4, 4), dtype=complex)
    from skrf.network import Network

    diff = Network(frequency=diff.frequency, s=diff.s, z0=50.0)
    trace = analyzer.step_impedance(
        diff,
        settings=TdrSettings(window=TdrWindow.NONE),
        port_mapping=PortMapping.SEQUENTIAL,
        reference_z0=50.0,
    )
    assert trace.parameter == "SDD11"
    assert trace.reference_ohm == 100.0


@pytest.mark.parametrize("window", [TdrWindow.HAMMING, TdrWindow.HANN, TdrWindow.BLACKMAN, TdrWindow.NONE])
def test_all_windows_run(window: TdrWindow) -> None:
    trace = TdrAnalyzer().step_impedance(
        _matched_line_network(),
        settings=TdrSettings(window=window, dc_method=DcMethod.HOLD),
        port_mapping=PortMapping.SINGLE_ENDED,
        reference_z0=50.0,
    )
    assert len(trace.time_ns) == len(trace.impedance_ohm)
    assert trace.sample_step_ps > 0


def test_settings_and_input_validation() -> None:
    analyzer = TdrAnalyzer()
    with pytest.raises(InvalidInputError):
        TdrSettings.from_form(window="triangle")
    with pytest.raises(InvalidInputError):
        TdrSettings.from_form(dc_method="magic")
    with pytest.raises(InvalidInputError):
        TdrSettings.from_form(port="abc")
    with pytest.raises(InvalidInputError):
        analyzer.validate(TdrSettings(port=3), 50.0)
    with pytest.raises(InvalidInputError):
        analyzer.validate(TdrSettings(), 0.0)
    with pytest.raises(InvalidInputError):
        analyzer.validate(TdrSettings(rise_time_ps=20000), 50.0)


def test_display_points_are_capped() -> None:
    analyzer = TdrAnalyzer(max_display_points=50)
    trace = analyzer.step_impedance(
        _matched_line_network(points=2000),
        settings=TdrSettings(window=TdrWindow.NONE),
        port_mapping=PortMapping.SINGLE_ENDED,
        reference_z0=50.0,
    )
    assert len(trace.time_ns) <= 50


def test_invalid_frequency_axis_rejected() -> None:
    network = _matched_line_network(points=4)
    with pytest.raises(InvalidInputError):
        TdrAnalyzer().step_impedance(
            network,
            settings=TdrSettings(),
            port_mapping=PortMapping.SINGLE_ENDED,
            reference_z0=50.0,
        )


def test_stack_reuses_first_trace_metadata() -> None:
    analyzer = TdrAnalyzer()
    stack = analyzer.stack(
        {"a": _matched_line_network(), "b": _mismatched_network()},
        settings=TdrSettings(window=TdrWindow.NONE),
        port_mapping=PortMapping.SINGLE_ENDED,
        reference_z0=50.0,
    )
    payload = stack.to_payload()
    assert payload["parameter"] == "S11"
    assert set(payload["series"]) == {"a", "b"}
    assert len(payload["time_ns"]) == len(payload["series"]["a"])


def test_non_finite_data_raises_computation_error() -> None:
    network = _matched_line_network()
    network.s[:, 0, 0] = np.nan
    with pytest.raises(ComputationError):
        TdrAnalyzer().step_impedance(
            network,
            settings=TdrSettings(),
            port_mapping=PortMapping.SINGLE_ENDED,
            reference_z0=50.0,
        )
