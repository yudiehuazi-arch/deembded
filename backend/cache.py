"""线程安全的 TTL + LRU + 字节预算缓存。

原实现用两组模块级 ``OrderedDict`` + 5 个近乎重复的函数维护解析网络缓存；
现在抽象为泛型 :class:`NetworkCache`，Web 层只声明“缓存什么、多大预算”。
"""

from __future__ import annotations

import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import Callable, Generic, Iterator, TypeVar

import numpy as np
import skrf as rf

from deembed.models import NetworkTriplet

T = TypeVar("T")

__all__ = ["CachePolicy", "NetworkCache", "NetworkCacheStore", "estimate_network_bytes"]


@dataclass(frozen=True)
class CachePolicy:
    """缓存预算：生存时间、条目上限与总字节上限。"""

    ttl_seconds: float
    max_items: int
    max_bytes: int

    def __post_init__(self) -> None:
        if self.ttl_seconds <= 0:
            raise ValueError("ttl_seconds 必须为正数")
        if self.max_items <= 0:
            raise ValueError("max_items 必须为正数")


@dataclass
class _Entry(Generic[T]):
    expires_at: float
    value: T
    size: int


class NetworkCache(Generic[T]):
    """TTL + LRU 缓存，附带条目大小预算。

    ``size_of`` 用于估算单条目的内存占用，超出预算的条目不会被缓存
    （``store`` 返回 ``None``，调用方回退到内联返回数据）。
    """

    def __init__(
        self,
        policy: CachePolicy,
        size_of: Callable[[T], int],
        *,
        clock: Callable[[], float] = time.monotonic,
        token_factory: Callable[[], str] = lambda: uuid.uuid4().hex,
    ) -> None:
        self.policy = policy
        self._size_of = size_of
        self._clock = clock
        self._token_factory = token_factory
        self._entries: OrderedDict[str, _Entry[T]] = OrderedDict()
        self._lock = Lock()

    # ------------------------------------------------------------------ 内部
    def _purge_expired(self, now: float) -> None:
        for token in [token for token, entry in self._entries.items() if entry.expires_at <= now]:
            del self._entries[token]

    def _trim(self, incoming_size: int) -> None:
        total = sum(entry.size for entry in self._entries.values())
        while self._entries and (len(self._entries) >= self.policy.max_items or total + incoming_size > self.policy.max_bytes):
            _, evicted = self._entries.popitem(last=False)
            total -= evicted.size

    # ------------------------------------------------------------------ API
    def store(self, value: T) -> str | None:
        """写入缓存并返回访问令牌；超出预算时返回 ``None``。"""

        size = int(self._size_of(value))
        if size > self.policy.max_bytes:
            return None
        now = self._clock()
        token = self._token_factory()
        with self._lock:
            self._purge_expired(now)
            self._trim(size)
            self._entries[token] = _Entry(expires_at=now + self.policy.ttl_seconds, value=value, size=size)
        return token

    def get(self, token: str | None) -> T | None:
        """读取缓存（命中即刷新 LRU 顺序）。"""

        if not token:
            return None
        now = self._clock()
        with self._lock:
            self._purge_expired(now)
            entry = self._entries.get(token)
            if entry is None:
                return None
            self._entries.move_to_end(token)
            return entry.value

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:  # pragma: no cover - 简单转发
        with self._lock:
            return len(self._entries)

    def __iter__(self) -> Iterator[str]:  # pragma: no cover - 简单转发
        with self._lock:
            return iter(list(self._entries.keys()))


def estimate_network_bytes(networks) -> int:
    """估算一组 ``rf.Network`` 的内存占用（s/f/z0 数组之和）。"""

    total = 0
    for network in networks:
        total += int(np.asarray(network.s).nbytes + np.asarray(network.f).nbytes + np.asarray(network.z0).nbytes)
    return total


class NetworkCacheStore:
    """应用级缓存集合：识别缓存（三个输入网络）与结果缓存（DUT/夹具）。"""

    def __init__(self, inspection: NetworkCache[NetworkTriplet], results: NetworkCache[dict[str, rf.Network]]) -> None:
        self.inspection = inspection
        self.results = results

    @classmethod
    def from_settings(cls, settings) -> "NetworkCacheStore":
        inspection = NetworkCache[NetworkTriplet](settings.inspection_cache, lambda triplet: estimate_network_bytes(list(triplet)))
        results = NetworkCache[dict[str, rf.Network]](
            settings.result_cache, lambda networks: estimate_network_bytes(list(networks.values()))
        )
        return cls(inspection=inspection, results=results)

    def clear(self) -> None:
        self.inspection.clear()
        self.results.clear()
