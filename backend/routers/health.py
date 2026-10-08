"""健康检查与方法清单。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from deembed import __version__

from ..config import Settings
from ..dependencies import get_engine, get_settings
from ..schemas import HealthPayload

__all__ = ["router"]

router = APIRouter(tags=["system"])


@router.get("/api/health", response_model=None)
def health(settings: Settings = Depends(get_settings), engine=Depends(get_engine)) -> HealthPayload:
    return {
        "status": "ok",
        "engine": "scikit-rf IEEE 370 NZC 2X Thru",
        "version": __version__,
        "methods": engine.available_methods(),
    }
