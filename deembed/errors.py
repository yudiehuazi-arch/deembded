"""领域错误定义。

设计约定：领域层不依赖任何 Web 框架，因此异常只携带一个稳定的 ``code``，
由 API 层（``backend.exceptions``）把 ``code`` 映射为 HTTP 状态码。
这样新增功能时只需扩展错误类型，无需在领域代码里写 HTTP 逻辑。
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "DeembedError",
    "InvalidInputError",
    "UnsupportedPortCountError",
    "FrequencyGridError",
    "FileTooLargeError",
    "CacheExpiredError",
    "ComputationError",
    "ErrorCode",
]


class ErrorCode:
    """错误码常量。API 层按这些码决定 HTTP 状态码。"""

    INVALID_INPUT = "invalid_input"          # -> 400
    FILE_TOO_LARGE = "file_too_large"        # -> 413
    CACHE_EXPIRED = "cache_expired"          # -> 410
    NOT_FOUND = "not_found"                  # -> 404
    COMPUTATION_FAILED = "computation_failed"  # -> 422
    INTERNAL = "internal_error"              # -> 500


class DeembedError(Exception):
    """去嵌领域异常基类。

    Attributes:
        code: 稳定错误码，供 API 层映射 HTTP 状态。
        details: 可选的结构化补充信息（日志/调试用）。
    """

    code: str = ErrorCode.INTERNAL

    def __init__(self, message: str, *, code: str | None = None, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        self.details = details or {}

    def __str__(self) -> str:  # pragma: no cover - 直接沿用基类消息
        return self.message


class InvalidInputError(DeembedError):
    """输入数据不合法（端口数、频率网格、参数取值等）。"""

    code = ErrorCode.INVALID_INPUT


class UnsupportedPortCountError(InvalidInputError):
    """端口数不在支持范围内。"""


class FrequencyGridError(InvalidInputError):
    """频率网格/共同频段不可用。"""


class FileTooLargeError(DeembedError):
    """上传文件超过体积上限。"""

    code = ErrorCode.FILE_TOO_LARGE


class CacheExpiredError(DeembedError):
    """服务端网络缓存缺失或已过期，需要重新上传/识别。"""

    code = ErrorCode.CACHE_EXPIRED


class ComputationError(DeembedError):
    """数值计算失败（矩阵求逆奇异、时域变换异常等）。"""

    code = ErrorCode.COMPUTATION_FAILED
