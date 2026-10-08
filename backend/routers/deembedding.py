"""去嵌计算与结果导出路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import PlainTextResponse

from ..dependencies import get_deembedding_service, get_export_service
from ..schemas import DeembedPayload
from ..services import DeembeddingService, ExportService

__all__ = ["router"]

router = APIRouter(tags=["deembedding"])


@router.post("/api/deembed")
async def run_deembed(
    total: UploadFile | None = File(None),
    thru_a: UploadFile | None = File(None),
    thru_b: UploadFile | None = File(None),
    side: str = Form("both"),
    port_mapping: str = Form("auto"),
    reference_z0: float = Form(50.0),
    split_algorithm: str = Form("mc_nzc"),
    inspection_token: str | None = Form(None),
    service: DeembeddingService = Depends(get_deembedding_service),
) -> DeembedPayload:
    """执行 2X Thru 劈半 + T 矩阵去嵌，返回曲线数据与质量指标。

    ``split_algorithm``（仅差分 S4P 生效）：``mc_nzc`` = 混合模 NZC + 模式转换（默认），
    ``classic_nzc`` = IEEE 370 经典 MM-NZC。差分结果会附带另一种算法的 DUT 作对照。
    """

    return await service.deembed(
        total=total,
        thru_a=thru_a,
        thru_b=thru_b,
        side=side,
        port_mapping=port_mapping,
        reference_z0=reference_z0,
        split_algorithm=split_algorithm,
        token=inspection_token,
    )


@router.get("/api/download/{result_token}/{network_key}")
def download_result(
    result_token: str,
    network_key: str,
    service: ExportService = Depends(get_export_service),
) -> PlainTextResponse:
    """下载去嵌 DUT 或某个 1X 夹具的 Touchstone 文件。"""

    filename, content = service.build_download(result_token, network_key)
    return PlainTextResponse(
        content,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
