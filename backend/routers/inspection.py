"""文件识别路由：``POST /api/inspect``。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile

from ..dependencies import get_inspection_service
from ..schemas import InspectionPayload
from ..services import InspectionService

__all__ = ["router"]

router = APIRouter(tags=["inspection"])


@router.post("/api/inspect")
async def inspect_files(
    total: UploadFile | None = File(None),
    thru_a: UploadFile | None = File(None),
    thru_b: UploadFile | None = File(None),
    port_mapping: str = Form("auto"),
    inspection_token: str | None = Form(None),
    service: InspectionService = Depends(get_inspection_service),
) -> InspectionPayload:
    """识别端口数/端口映射/共同频段，并返回预览曲线与夹具诊断。"""

    return await service.inspect(
        total=total,
        thru_a=thru_a,
        thru_b=thru_b,
        port_mapping=port_mapping,
        token=inspection_token,
    )
