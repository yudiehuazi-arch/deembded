"""领域异常 → HTTP 响应的统一映射。

领域层只抛出 ``deembed.errors.DeembedError`` 及其子类，并携带稳定的
``code``；这里集中把 ``code`` 翻译成状态码与 JSON 结构，保证前端拿到的
仍然是 ``{"detail": "..."}``。
"""

from __future__ import annotations

import logging
from typing import Final

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from deembed.errors import DeembedError, ErrorCode

__all__ = ["STATUS_BY_CODE", "status_for", "register_exception_handlers"]

logger = logging.getLogger("deembed.api")

STATUS_BY_CODE: Final[dict[str, int]] = {
    ErrorCode.INVALID_INPUT: 400,
    ErrorCode.FILE_TOO_LARGE: 413,
    ErrorCode.CACHE_EXPIRED: 410,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.COMPUTATION_FAILED: 422,
    ErrorCode.INTERNAL: 500,
}


def status_for(error: DeembedError) -> int:
    return STATUS_BY_CODE.get(error.code, 500)


def register_exception_handlers(app: FastAPI) -> None:
    """注册领域异常处理器（API 层唯一的错误出口）。"""

    @app.exception_handler(DeembedError)
    async def _handle_domain_error(request: Request, exc: DeembedError) -> JSONResponse:  # noqa: ANN202
        status_code = status_for(exc)
        if status_code >= 500:
            logger.exception("领域层内部错误：%s", exc.message)
        return JSONResponse(status_code=status_code, content={"detail": exc.message})
