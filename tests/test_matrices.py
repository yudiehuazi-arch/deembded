"""S ↔ T 矩阵代数的正确性验证。"""

from __future__ import annotations

import numpy as np
import pytest
import skrf as rf

from deembed.errors import ComputationError
from deembed.matrices import cascade_deembed, deembed_network, s_to_t, t_to_s
from deembed.models import DeembedSide


def _random_passive_network(nports: int, points: int = 12, seed: int = 7) -> rf.Network:
    rng = np.random.default_rng(seed)
    freq = rf.Frequency.from_f(np.linspace(1e9, 20e9, points), unit="hz")
    # 通过对角占优构造一个“类无源”网络，避免奇异矩阵干扰代数验证。
    raw = rng.normal(scale=0.15, size=(points, nports, nports)) + 1j * rng.normal(scale=0.15, size=(points, nports, nports))
    return rf.Network(frequency=freq, s=raw, z0=50.0)


@pytest.mark.parametrize("nports", [2, 4])
def test_s_to_t_roundtrip(nports: int) -> None:
    network = _random_passive_network(nports)
    reconstructed = t_to_s(s_to_t(network.s))
    np.testing.assert_allclose(reconstructed, network.s, rtol=1e-10, atol=1e-12)


def test_cascade_deembed_recovers_middle_network() -> None:
    left = _random_passive_network(2, seed=1)
    dut = _random_passive_network(2, seed=2)
    right = _random_passive_network(2, seed=3)
    total = left**dut**right

    recovered = deembed_network(total, left=left, right=right, side=DeembedSide.BOTH)
    np.testing.assert_allclose(recovered.s, dut.s, rtol=1e-8, atol=1e-10)


def test_single_sided_deembedding_keeps_other_side() -> None:
    left = _random_passive_network(2, seed=4)
    dut = _random_passive_network(2, seed=5)
    right = _random_passive_network(2, seed=6)
    total = left**dut**right

    left_only = deembed_network(total, left=left, side=DeembedSide.LEFT)
    np.testing.assert_allclose(left_only.s, (dut**right).s, rtol=1e-8, atol=1e-10)

    right_only = deembed_network(total, right=right, side=DeembedSide.RIGHT)
    np.testing.assert_allclose(right_only.s, (left**dut).s, rtol=1e-8, atol=1e-10)


def test_cascade_deembed_without_fixtures_is_identity() -> None:
    total = _random_passive_network(2, seed=8)
    np.testing.assert_allclose(cascade_deembed(total.s, side=DeembedSide.BOTH), total.s, atol=1e-12)


def test_singular_matrix_raises_domain_error() -> None:
    singular = np.zeros((3, 4, 4), dtype=complex)
    with pytest.raises(ComputationError):
        s_to_t(singular)
