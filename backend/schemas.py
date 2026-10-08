"""HTTP 响应结构（TypedDict 形式）。

只描述“发送给前端的字段”，不承载业务逻辑：真正的计算在 ``deembed``
内核与服务层完成，这里保证字段名/类型在 IDE 与类型检查下可被验证。
"""

from __future__ import annotations

from typing import Any

# 说明：Python < 3.12 时 pydantic 要求使用 typing_extensions.TypedDict
# 作为 FastAPI 响应模型的注解类型。
from typing_extensions import NotRequired, TypedDict

__all__ = [
    "HealthPayload",
    "QualityPayload",
    "InspectionPayload",
    "DeembedPayload",
    "TdrStackPayload",
    "MethodInfo",
]


class MethodInfo(TypedDict):
    method: str
    description: str


class HealthPayload(TypedDict):
    status: str
    engine: str
    version: str
    methods: list[MethodInfo]


class QualityPayload(TypedDict):
    status: str
    verdict: str
    max_singular_value: float
    passivity_pass: bool
    passivity_margin_db: float
    reciprocity_error: float
    reciprocity_pass: bool


class InspectionPayload(TypedDict):
    success: bool
    inspection_token: str | None
    nports: int
    topology: str
    requested_mapping: str
    detected_mapping: str
    mapping_label: str
    left_ports: list[str]
    right_ports: list[str]
    file_previews: dict[str, Any]
    fixture_statistics: NotRequired[dict[str, Any] | None]
    frequency_start_ghz: float
    frequency_stop_ghz: float
    points: int


class DeembedPayload(TypedDict):
    success: bool
    result_token: str | None
    message: str
    topology: str
    side: str
    port_mapping: str | None
    mapping_label: str
    left_ports: list[str]
    right_ports: list[str]
    reference_z0: float
    frequency_start_ghz: float
    frequency_stop_ghz: float
    points: int
    quality: QualityPayload
    chart: dict[str, Any]
    nports: int
    dut_touchstone: NotRequired[str]
    fix_a_touchstone: NotRequired[str]
    fix_b_touchstone: NotRequired[str]


class TdrStackPayload(TypedDict):
    """TDR 响应。

    ``slot=all``（或 ``/api/tdr/result``）返回 ``series``（多网络对比）；
    单槽查询同时保留历史字段 ``impedance_ohm``，两种形态共用该模型。
    """

    success: bool
    time_ns: list[float]
    series: NotRequired[dict[str, list[float | None]]]
    impedance_ohm: NotRequired[list[float | None]]
    sample_step_ps: float
    reference_ohm: float
    parameter: str
    window: str
    dc_method: str
    rise_time_ps: float
    port_mapping: str
    slot: NotRequired[str]
