"""应用配置（12-Factor：全部可通过环境变量覆盖）。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path

from .cache import CachePolicy

__all__ = ["Settings", "ROOT_DIR", "STATIC_DIR"]

ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT_DIR / "static"

_MEGABYTE = 1024 * 1024
_ENV_PREFIX = "DEEMBED_"


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(f"{_ENV_PREFIX}{name}")
    if raw is None or not raw.strip():
        return default
    try:
        return int(float(raw))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(f"{_ENV_PREFIX}{name}")
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """运行期配置。

    环境变量（可选）：
    ``DEEMBED_MAX_UPLOAD_MB``、``DEEMBED_CACHE_TTL_SECONDS``、
    ``DEEMBED_INSPECTION_CACHE_ITEMS/BYTES``、``DEEMBED_RESULT_CACHE_ITEMS/BYTES``。
    """

    title: str = "RF De-embedding Workbench"
    description: str = "Split independent 2X Thru A/B standards and de-embed a measured fixture-DUT-fixture network."
    version: str = "2.0.0"

    max_upload_bytes: int = 50 * _MEGABYTE
    static_dir: Path = field(default=STATIC_DIR)

    inspection_cache: CachePolicy = field(
        default_factory=lambda: CachePolicy(ttl_seconds=600.0, max_items=4, max_bytes=256 * _MEGABYTE)
    )
    result_cache: CachePolicy = field(
        default_factory=lambda: CachePolicy(ttl_seconds=600.0, max_items=2, max_bytes=384 * _MEGABYTE)
    )

    @property
    def max_upload_mb(self) -> int:
        return max(1, self.max_upload_bytes // _MEGABYTE)

    @classmethod
    def from_env(cls) -> "Settings":
        base = cls()
        ttl = _env_float("CACHE_TTL_SECONDS", base.inspection_cache.ttl_seconds)
        inspection = replace(
            base.inspection_cache,
            ttl_seconds=ttl,
            max_items=_env_int("INSPECTION_CACHE_ITEMS", base.inspection_cache.max_items),
            max_bytes=_env_int("INSPECTION_CACHE_BYTES", base.inspection_cache.max_bytes),
        )
        result = replace(
            base.result_cache,
            ttl_seconds=ttl,
            max_items=_env_int("RESULT_CACHE_ITEMS", base.result_cache.max_items),
            max_bytes=_env_int("RESULT_CACHE_BYTES", base.result_cache.max_bytes),
        )
        return replace(
            base,
            max_upload_bytes=_env_int("MAX_UPLOAD_MB", base.max_upload_mb) * _MEGABYTE,
            inspection_cache=inspection,
            result_cache=result,
        )
