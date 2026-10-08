"""TDR 路由：输入网络与去嵌结果的阶跃阻抗。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form

from ..dependencies import get_tdr_service
from ..schemas import TdrStackPayload
from ..services import TdrService

__all__ = ["router"]

router = APIRouter(prefix="/api/tdr", tags=["tdr"])


@router.post("/input")
def input_network_tdr(
    inspection_token: str = Form(...),
    slot: str = Form(...),
    port: int = Form(1),
    port_mapping: str = Form("auto"),
    reference_z0: float = Form(50.0),
    window: str = Form("hamming"),
    dc_method: str = Form("linear"),
    rise_time_ps: float = Form(0.0),
    service: TdrService = Depends(get_tdr_service),
) -> TdrStackPayload:
    """计算 Total / 2X Thru A / 2X Thru B 的阶跃阻抗（slot=all 时三线叠加）。"""

    return service.input_stack(
        inspection_token=inspection_token,
        slot=slot,
        port=port,
        port_mapping=port_mapping,
        reference_z0=reference_z0,
        window=window,
        dc_method=dc_method,
        rise_time_ps=rise_time_ps,
    )


@router.post("/result")
def result_networks_tdr(
    inspection_token: str = Form(...),
    result_token: str = Form(...),
    port: int = Form(1),
    port_mapping: str = Form("auto"),
    reference_z0: float = Form(50.0),
    window: str = Form("hamming"),
    dc_method: str = Form("linear"),
    rise_time_ps: float = Form(0.0),
    service: TdrService = Depends(get_tdr_service),
) -> TdrStackPayload:
    """计算 Total / DUT / 1X 夹具 / 2X Thru 的阶跃阻抗对比。"""

    return service.result_stack(
        inspection_token=inspection_token,
        result_token=result_token,
        port=port,
        port_mapping=port_mapping,
        reference_z0=reference_z0,
        window=window,
        dc_method=dc_method,
        rise_time_ps=rise_time_ps,
    )
