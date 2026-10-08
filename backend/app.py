"""兼容入口（已弃用）。

历史版本的应用入口是 ``backend.app:app``；重构后应用工厂位于
``backend.main``，这里保留一个转发，避免外部部署脚本失效。
"""

from __future__ import annotations

from .main import app, create_app

__all__ = ["app", "create_app"]
