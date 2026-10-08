"""FastAPI 依赖注入：从 ``app.state`` 取出服务与配置。

路由函数只依赖这些 provider，因此测试可以通过 ``create_app(settings)``
注入不同配置，或直接覆盖依赖来替换服务实现。
"""

from __future__ import annotations

from fastapi import Request

from deembed import DeembeddingEngine

from .cache import NetworkCacheStore
from .config import Settings
from .services import DeembeddingService, ExportService, InspectionService, ServiceRegistry, TdrService

__all__ = [
    "get_settings",
    "get_engine",
    "get_caches",
    "get_services",
    "get_inspection_service",
    "get_deembedding_service",
    "get_tdr_service",
    "get_export_service",
]


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_engine(request: Request) -> DeembeddingEngine:
    return request.app.state.engine


def get_caches(request: Request) -> NetworkCacheStore:
    return request.app.state.services.caches


def get_services(request: Request) -> ServiceRegistry:
    return request.app.state.services


def get_inspection_service(request: Request) -> InspectionService:
    return request.app.state.services.inspection


def get_deembedding_service(request: Request) -> DeembeddingService:
    return request.app.state.services.deembedding


def get_tdr_service(request: Request) -> TdrService:
    return request.app.state.services.tdr


def get_export_service(request: Request) -> ExportService:
    return request.app.state.services.export
