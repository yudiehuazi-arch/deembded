"""频率对齐与端口映射行为验证。"""

from __future__ import annotations

import numpy as np
import pytest
import skrf as rf

from deembed.errors import FrequencyGridError, InvalidInputError
from deembed.frequency import FrequencyAligner, renormalize, sample_network
from deembed.models import PortMapping
from deembed.port_mapping import (
    apply_port_mapping,
    auto_detect_port_mapping,
    mapping_label,
    pair_labels,
    resolve_port_mapping,
)


def _network(start_ghz: float, stop_ghz: float, points: int, nports: int = 2) -> rf.Network:
    freq = rf.Frequency.from_f(np.linspace(start_ghz * 1e9, stop_ghz * 1e9, points), unit="hz")
    rng = np.random.default_rng(points)
    s = rng.normal(scale=0.1, size=(points, nports, nports)) + 0j
    return rf.Network(frequency=freq, s=s, z0=50.0)


def test_align_uses_total_grid_inside_common_band() -> None:
    total = _network(1.0, 20.0, 100)
    thru_a = _network(2.0, 18.0, 41)
    thru_b = _network(0.5, 22.0, 200)

    aligned = FrequencyAligner().align([total, thru_a, thru_b])

    expected = np.asarray(total.f)[(np.asarray(total.f) >= 2e9) & (np.asarray(total.f) <= 18e9)]
    for network in aligned:
        np.testing.assert_allclose(np.asarray(network.f), expected, atol=1.0)


def test_align_requires_overlap() -> None:
    with pytest.raises(FrequencyGridError):
        FrequencyAligner().align([_network(1.0, 5.0, 20), _network(6.0, 10.0, 20)])


def test_align_requires_enough_points() -> None:
    with pytest.raises(FrequencyGridError):
        FrequencyAligner().align([_network(1.0, 5.0, 5), _network(1.0, 5.0, 20)])


def test_frequency_axis_must_be_increasing() -> None:
    network = _network(1.0, 20.0, 20)
    broken = rf.Network(frequency=rf.Frequency.from_f(np.linspace(1e9, 20e9, 20), unit="hz"), s=network.s, z0=50.0)
    broken.f[-1] = broken.f[-2] - 1e9
    with pytest.raises(InvalidInputError):
        FrequencyAligner().align([broken])


def test_renormalize_and_sample_preserve_shape() -> None:
    network = _network(1.0, 10.0, 30)
    network.z0 = 75.0
    fixed = renormalize(network, 50.0)
    assert np.allclose(fixed.z0, 50.0)
    assert np.allclose(network.z0, 75.0)  # 原对象未被修改

    sampled = sample_network(fixed, np.array([0, 5, 29]))
    assert sampled.nports == fixed.nports
    assert len(sampled.f) == 3


def test_auto_detect_distinguishes_port_conventions() -> None:
    sequential = _network(1.0, 10.0, 20, nports=4)
    sequential.s[:, 2, 0] = 0.9   # 1→3 直通
    sequential.s[:, 1, 0] = 0.01
    assert auto_detect_port_mapping(sequential) is PortMapping.SEQUENTIAL

    plts = _network(1.0, 10.0, 20, nports=4)
    plts.s[:, 1, 0] = 0.9         # 1→2 直通
    plts.s[:, 2, 0] = 0.01
    assert auto_detect_port_mapping(plts) is PortMapping.PLTS


def test_resolve_and_apply_mapping_is_involutive() -> None:
    network = _network(1.0, 10.0, 12, nports=4)
    mapping = resolve_port_mapping(network, "plts")
    assert mapping is PortMapping.PLTS

    swapped = apply_port_mapping(network, mapping)
    restored = apply_port_mapping(swapped, mapping)
    np.testing.assert_allclose(restored.s, network.s, atol=1e-12)


def test_resolve_rejects_invalid_mapping_and_labels() -> None:
    network = _network(1.0, 10.0, 12, nports=4)
    with pytest.raises(InvalidInputError):
        resolve_port_mapping(network, "banana")

    assert pair_labels(4, PortMapping.PLTS) == (["P1 (+)", "P3 (−)"], ["P2 (+)", "P4 (−)"])
    assert mapping_label(4, PortMapping.SEQUENTIAL) == "标准顺序 · 1/2 → 3/4"
    assert mapping_label(2, PortMapping.SINGLE_ENDED) == "单端双端口"
