"""FastAPI 应用工厂与入口。

这一层只做三件事：
1. 组装依赖（配置 / 引擎 / 缓存 / 服务）；
2. 注册路由与异常处理器；
3. 托管前端静态文件。

所有算法都在 ``deembed`` 内核里，所有用例编排都在 ``backend.services`` 里。
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from deembed import DeembeddingEngine, build_default_engine

from .cache import NetworkCacheStore
from .config import Settings
from .exceptions import register_exception_handlers
from .routers import ALL_ROUTERS
from .services import DeembeddingService, ExportService, InspectionService, ServiceRegistry, TdrService
from .uploads import UploadReader

__all__ = ["create_app", "app"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("deembed.api")


def build_services(settings: Settings, engine: DeembeddingEngine) -> ServiceRegistry:
    """组装服务集合（测试可复用此函数以注入不同的配置/缓存）。"""

    caches = NetworkCacheStore.from_settings(settings)
    reader = UploadReader(settings)
    return ServiceRegistry(
        caches=caches,
        inspection=InspectionService(reader, engine, caches),
        deembedding=DeembeddingService(reader, engine, caches),
        tdr=TdrService(caches),
        export=ExportService(caches),
    )


def create_app(settings: Settings | None = None, engine: DeembeddingEngine | None = None) -> FastAPI:
    """创建应用实例（每次调用都得到独立的缓存与状态）。"""

    resolved_settings = settings or Settings.from_env()
    resolved_engine = engine or build_default_engine()

    app = FastAPI(
        title=resolved_settings.title,
        description=resolved_settings.description,
        version=resolved_settings.version,
    )
    app.state.settings = resolved_settings
    app.state.engine = resolved_engine
    app.state.services = build_services(resolved_settings, resolved_engine)

    register_exception_handlers(app)
    for router in ALL_ROUTERS:
        app.include_router(router)

    static_dir = Path(resolved_settings.static_dir)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(
            static_dir / "index.html",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
        )

    logger.info("RF De-embedding Workbench %s 已就绪（static=%s）", resolved_settings.version, static_dir)
    return app


#: 供 ``uvicorn backend.main:app`` 使用
app = create_app()
