"""缓存策略（TTL / LRU / 字节预算）行为验证。"""

from __future__ import annotations

import numpy as np
import pytest
import skrf as rf

from backend.cache import CachePolicy, NetworkCache, NetworkCacheStore, estimate_network_bytes
from backend.config import Settings
from deembed.models import NetworkTriplet


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _value(size: int) -> list[int]:
    return list(range(size))


def test_store_and_get_roundtrip() -> None:
    cache = NetworkCache[list[int]](CachePolicy(ttl_seconds=10, max_items=2, max_bytes=1024), len)
    token = cache.store([1, 2, 3])
    assert token is not None
    assert cache.get(token) == [1, 2, 3]


def test_ttl_expiry() -> None:
    clock = FakeClock()
    cache = NetworkCache[list[int]](CachePolicy(ttl_seconds=5, max_items=4, max_bytes=1024), len, clock=clock)
    token = cache.store([1])
    clock.advance(6)
    assert cache.get(token) is None


def test_lru_eviction_keeps_recent() -> None:
    cache = NetworkCache[list[int]](CachePolicy(ttl_seconds=100, max_items=2, max_bytes=1024), len)
    first = cache.store([1])
    second = cache.store([1, 2])
    cache.get(first)  # 刷新 first 的 LRU 位置
    third = cache.store([1, 2, 3])
    assert cache.get(second) is None
    assert cache.get(first) is not None
    assert cache.get(third) is not None


def test_byte_budget_eviction() -> None:
    cache = NetworkCache[bytes](CachePolicy(ttl_seconds=100, max_items=10, max_bytes=10), len)
    first = cache.store(b"123456")
    second = cache.store(b"abcdef")
    assert cache.get(first) is None
    assert cache.get(second) == b"abcdef"


def test_oversized_value_is_not_cached() -> None:
    cache = NetworkCache[bytes](CachePolicy(ttl_seconds=100, max_items=4, max_bytes=4), len)
    assert cache.store(b"0123456789") is None


def test_unknown_or_missing_token_returns_none() -> None:
    cache = NetworkCache[list[int]](CachePolicy(ttl_seconds=10, max_items=2, max_bytes=100), len)
    assert cache.get("missing") is None
    assert cache.get(None) is None


def test_estimate_network_bytes_counts_arrays() -> None:
    freq = rf.Frequency.from_f(np.linspace(1e9, 2e9, 10), unit="hz")
    network = rf.Network(frequency=freq, s=np.zeros((10, 2, 2), dtype=complex), z0=50.0)
    assert estimate_network_bytes([network]) >= 10 * 4 * 16


def test_store_from_settings_creates_two_caches() -> None:
    store = NetworkCacheStore.from_settings(Settings())
    assert isinstance(store.inspection, NetworkCache)
    assert isinstance(store.results, NetworkCache)

    token = store.inspection.store(
        NetworkTriplet(total=_dummy_network(), thru_a=_dummy_network(), thru_b=_dummy_network())
    )
    assert store.inspection.get(token) is not None
    store.clear()
    assert len(store.inspection) == 0
    assert len(store.results) == 0


def test_policy_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        CachePolicy(ttl_seconds=0, max_items=1, max_bytes=1)
    with pytest.raises(ValueError):
        CachePolicy(ttl_seconds=1, max_items=0, max_bytes=1)


def _dummy_network() -> rf.Network:
    freq = rf.Frequency.from_f(np.linspace(1e9, 2e9, 8), unit="hz")
    return rf.Network(frequency=freq, s=np.zeros((8, 2, 2), dtype=complex), z0=50.0)
