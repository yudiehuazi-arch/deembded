"""HTTP 路由集合（每个模块负责一组端点）。"""

from __future__ import annotations

from . import deembedding, health, inspection, tdr

__all__ = ["health", "inspection", "deembedding", "tdr", "ALL_ROUTERS"]

#: ``create_app`` 依此顺序注册路由
ALL_ROUTERS = (health.router, inspection.router, deembedding.router, tdr.router)
