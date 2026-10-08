"""上传文件 → 领域网络对象。

把 FastAPI 的 ``UploadFile`` 适配为 ``rf.Network``/``NetworkTriplet``，
所有校验消息与历史版本保持一致（前端会原样展示）。
"""

from __future__ import annotations

from pathlib import Path

import skrf as rf
from fastapi import UploadFile

from deembed.errors import FileTooLargeError, InvalidInputError
from deembed.models import NetworkTriplet
from deembed.touchstone import (
    SUPPORTED_PORT_COUNTS,
    decode_touchstone_bytes,
    infer_port_count,
    network_from_text,
)

from .config import Settings

__all__ = ["UploadReader"]


class UploadReader:
    """读取并解析上传的 Touchstone 文件。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def read_network(self, upload: UploadFile, label: str) -> rf.Network:
        """读取单个上传文件并解析为 ``rf.Network``。"""

        filename = Path(upload.filename or f"{label}.s2p").name
        raw = await upload.read()
        if not raw:
            raise InvalidInputError(f"{label} 文件为空。")
        if len(raw) > self.settings.max_upload_bytes:
            raise FileTooLargeError(f"{label} 文件超过 {self.settings.max_upload_mb} MB 限制。")

        try:
            text = decode_touchstone_bytes(raw)
        except InvalidInputError as exc:
            raise InvalidInputError(f"{label} 不是可识别的文本 Touchstone 文件。") from exc

        try:
            nports = infer_port_count(filename, text)
        except InvalidInputError as exc:
            raise InvalidInputError(f"{label}：{exc}") from exc
        if nports not in SUPPORTED_PORT_COUNTS:
            raise InvalidInputError(f"{label}：目前仅支持 S2P 或 S4P，检测到 {nports} 个端口。")

        try:
            return network_from_text(text, f"{label}.s{nports}p")
        except InvalidInputError as exc:
            raise InvalidInputError(f"{label} 解析失败：{exc}") from exc

    async def read_triplet(
        self,
        total: UploadFile | None,
        thru_a: UploadFile | None,
        thru_b: UploadFile | None,
    ) -> NetworkTriplet:
        """读取三个必需文件并校验端口数一致性。"""

        if total is None or thru_a is None or thru_b is None:
            raise InvalidInputError("请上传 Total、2X Thru A 与 2X Thru B，或使用有效的识别缓存。")
        total_net = await self.read_network(total, "Total")
        thru_a_net = await self.read_network(thru_a, "2X Thru A")
        thru_b_net = await self.read_network(thru_b, "2X Thru B")
        counts = {int(total_net.nports), int(thru_a_net.nports), int(thru_b_net.nports)}
        if len(counts) != 1:
            raise InvalidInputError("Total、2X Thru A、2X Thru B 的端口数必须一致；请勿混用 S2P 与 S4P。")
        if counts.pop() not in SUPPORTED_PORT_COUNTS:
            raise InvalidInputError("目前仅支持单端 S2P 或差分 S4P 网络。")
        return NetworkTriplet(total=total_net, thru_a=thru_a_net, thru_b=thru_b_net)
