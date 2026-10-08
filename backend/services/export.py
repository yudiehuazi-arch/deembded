"""Touchstone 导出服务（对应 ``GET /api/download/{result_token}/{key}``）。"""

from __future__ import annotations

from deembed import network_to_text

from ..cache import NetworkCacheStore
from deembed.errors import CacheExpiredError, DeembedError, ErrorCode

__all__ = ["ExportService", "EXPORT_LABELS"]

#: 结果缓存键 → 下载文件名前缀
EXPORT_LABELS = {
    "dut": "DUT_deembedded",
    "fix_a": "Fixture_A_1X",
    "fix_b": "Fixture_B_1X",
    "dut_alt": "DUT_deembedded_compare",
}


class ExportService:
    def __init__(self, caches: NetworkCacheStore) -> None:
        self.caches = caches

    def build_download(self, result_token: str, network_key: str) -> tuple[str, str]:
        """返回 (文件名, Touchstone 文本)。"""

        if network_key not in EXPORT_LABELS:
            raise DeembedError("未知的 Touchstone 导出类型。", code=ErrorCode.NOT_FOUND)
        networks = self.caches.results.get(result_token)
        if not networks:
            raise CacheExpiredError("计算结果下载缓存已过期，请重新运行去嵌。")
        network = networks.get(network_key)
        if network is None:
            raise CacheExpiredError("计算结果下载缓存已过期，请重新运行去嵌。")
        filename = f"{EXPORT_LABELS[network_key]}.s{network.nports}p"
        return filename, network_to_text(network, form="ri")
