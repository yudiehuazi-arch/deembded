"""Touchstone 文本编解码。

职责边界：
* 从上传的字节流/文本推断端口数与解析为 ``skrf.Network``；
* 把 ``skrf.Network`` 序列化为 Touchstone 文本用于下载。

不涉及任何 Web 框架概念（不感知 UploadFile / HTTP）。
"""

from __future__ import annotations

import os
import re
import tempfile
from typing import Final

import skrf as rf

from .errors import InvalidInputError, UnsupportedPortCountError

__all__ = [
    "SUPPORTED_PORT_COUNTS",
    "SUPPORTED_PORT_HINT",
    "decode_touchstone_bytes",
    "infer_port_count",
    "network_from_text",
    "network_to_text",
    "TouchstoneCodec",
]

SUPPORTED_PORT_COUNTS: Final[frozenset[int]] = frozenset({2, 4})
SUPPORTED_PORT_HINT: Final[str] = "目前仅支持 S2P 或 S4P"

_EXTENSION_PATTERN = re.compile(r"\.s(\d+)p(?:\.txt)?$", re.IGNORECASE)
_PORT_COUNT_PATTERN = re.compile(r"\[\s*number\s+of\s+ports\s*\]\s*(\d+)", re.IGNORECASE)
_TOKEN_SPLIT_PATTERN = re.compile(r"[\s,]+")
_CANDIDATE_PORTS: Final[tuple[int, ...]] = (4, 2, 1)


def decode_touchstone_bytes(raw: bytes) -> str:
    """把上传字节解码为文本，优先 UTF-8（含 BOM），退回 ASCII。"""

    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            return raw.decode("ascii")
        except UnicodeDecodeError as exc:  # pragma: no cover - 取决于用户输入
            raise InvalidInputError("不是可识别的文本 Touchstone 文件。") from exc


def infer_port_count(filename: str, text: str) -> int:
    """从文件名或数据块推断端口数。

    依次尝试：``*.s2p/.s4p`` 扩展名 → ``[Number of Ports]`` 注释 → 数值列数。

    Raises:
        InvalidInputError: 无法唯一判断端口数时。
    """

    match = _EXTENSION_PATTERN.search(os.path.basename(filename or "").lower())
    if match:
        return int(match.group(1))

    match = _PORT_COUNT_PATTERN.search(text)
    if match:
        return int(match.group(1))

    numeric_tokens: list[float] = []
    for raw in text.splitlines():
        line = raw.split("!", 1)[0].strip()
        if not line or line.startswith(("#", "[")):
            continue
        for token in _TOKEN_SPLIT_PATTERN.split(line):
            if not token:
                continue
            try:
                numeric_tokens.append(float(token.replace("D", "E").replace("d", "e")))
            except ValueError:
                continue

    # Touchstone v1 每个频点的数值个数为 1 + 2*N*N。
    matches = [ports for ports in _CANDIDATE_PORTS if numeric_tokens and len(numeric_tokens) % (1 + 2 * ports * ports) == 0]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise InvalidInputError("文本数据无法唯一判断端口数，请保留 .s2p 或 .s4p 扩展名。")
    raise InvalidInputError("无法判断 Touchstone 端口数，请使用 .s2p 或 .s4p 文件名。")


def _touchstone_suffix(filename: str) -> str:
    """为 skrf 解析准备临时文件后缀（保持其端口数推断行为）。"""

    extension = os.path.splitext(filename)[1].lower()
    if extension and extension != ".snp":
        return extension
    return ".s2p"


def _parse_with_suffix(text: str, suffix: str) -> rf.Network:
    handle = tempfile.NamedTemporaryFile(suffix=suffix, mode="w", delete=False, encoding="utf-8")
    try:
        handle.write(text)
        handle.close()
        return rf.Network(handle.name)
    finally:
        if os.path.exists(handle.name):
            os.remove(handle.name)


def network_from_text(text: str, filename: str = "network.s2p") -> rf.Network:
    """把 Touchstone 文本解析为 ``rf.Network``。

    当扩展名缺失或不明确时，会先按 ``.s2p`` 尝试，失败后自动改用 ``.s4p``。
    """

    suffix = _touchstone_suffix(filename)
    try:
        return _parse_with_suffix(text, suffix)
    except Exception as primary_error:  # noqa: BLE001 - 需要回退到另一种端口数
        alternative = ".s4p" if suffix == ".s2p" else ".s2p"
        try:
            return _parse_with_suffix(text, alternative)
        except Exception:  # noqa: BLE001 - 抛出更贴近原因的原始异常
            raise InvalidInputError(str(primary_error)) from primary_error


def network_to_text(network: rf.Network, form: str = "ri") -> str:
    """把 ``rf.Network`` 导出为 Touchstone 文本（RI 格式用于下载）。"""

    suffix = f".s{network.nports}p"
    handle = tempfile.NamedTemporaryFile(suffix=suffix, mode="r+", delete=False)
    try:
        handle.close()
        network.write_touchstone(filename=handle.name, form=form)
        with open(handle.name, "r", encoding="utf-8") as stream:
            return stream.read()
    finally:
        if os.path.exists(handle.name):
            os.remove(handle.name)


def ensure_supported_port_count(ports: int, *, label: str = "") -> int:
    """校验端口数是否在支持范围内。"""

    if ports not in SUPPORTED_PORT_COUNTS:
        prefix = f"{label}：" if label else ""
        raise UnsupportedPortCountError(f"{prefix}{SUPPORTED_PORT_HINT}，检测到 {ports} 个端口。")
    return ports


class TouchstoneCodec:
    """面向对象封装的 Touchstone 编解码器（便于替换/测试）。"""

    def __init__(self, *, supported_port_counts: frozenset[int] = SUPPORTED_PORT_COUNTS) -> None:
        self.supported_port_counts = supported_port_counts

    def decode(self, raw: bytes) -> str:
        return decode_touchstone_bytes(raw)

    def infer_port_count(self, filename: str, text: str) -> int:
        return infer_port_count(filename, text)

    def parse(self, text: str, filename: str = "network.s2p") -> rf.Network:
        return network_from_text(text, filename)

    def serialize(self, network: rf.Network, form: str = "ri") -> str:
        return network_to_text(network, form=form)

    def parse_upload(self, raw: bytes, filename: str = "network.s2p") -> rf.Network:
        """上传字节 → 端口数校验 → ``rf.Network`` 的完整流程。"""

        text = self.decode(raw)
        ports = infer_port_count(filename, text)
        if ports not in self.supported_port_counts:
            raise UnsupportedPortCountError(f"{SUPPORTED_PORT_HINT}，检测到 {ports} 个端口。")
        return self.parse(text, filename)
