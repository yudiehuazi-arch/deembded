"""应用服务层：把领域内核包装成 Web 用例。

服务只依赖 ``UploadReader``/``DeembeddingEngine``/``NetworkCacheStore``
等显式注入的协作者，便于测试时替换（例如换用内存缓存或合成数据）。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..cache import NetworkCacheStore
from .deembedding import DeembeddingService
from .export import ExportService
from .inspection import InspectionService
from .tdr import TdrService

__all__ = ["ServiceRegistry", "InspectionService", "DeembeddingService", "TdrService", "ExportService"]


@dataclass(frozen=True)
class ServiceRegistry:
    """一次应用生命周期内的服务集合（挂在 ``app.state.services``）。"""

    caches: NetworkCacheStore
    inspection: InspectionService
    deembedding: DeembeddingService
    tdr: TdrService
    export: ExportService
