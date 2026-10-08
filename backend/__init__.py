"""Web 层：FastAPI 应用、路由、服务编排与缓存。

算法在 ``deembed`` 包中；本包只处理 HTTP 语义。
"""

from __future__ import annotations

__all__ = ["create_app"]


def create_app(*args, **kwargs):
    """延迟导入应用工厂，避免 import backend 时立即加载 FastAPI。"""

    from .main import create_app as factory

    return factory(*args, **kwargs)
