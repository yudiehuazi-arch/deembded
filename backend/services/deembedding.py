"""去嵌计算服务：组织上传/缓存、调用引擎并组装响应。

对应 ``POST /api/deembed``。
"""

from __future__ import annotations

import numpy as np
from fastapi import UploadFile

from deembed import DeembedRequest, DeembedSide, DeembeddingEngine, PortMapping, mapping_label, network_to_text, pair_labels
from deembed.errors import CacheExpiredError, ComputationError, DeembedError, InvalidInputError
from deembed.reporting import ChartDataBuilder

from ..cache import NetworkCacheStore
from ..schemas import DeembedPayload
from ..uploads import UploadReader

__all__ = ["DeembeddingService"]

_MESSAGE = "去嵌计算完成。请结合夹具标准件结构与测量条件检查结果。"


class DeembeddingService:
    def __init__(
        self,
        reader: UploadReader,
        engine: DeembeddingEngine,
        caches: NetworkCacheStore,
        *,
        chart_builder: ChartDataBuilder | None = None,
    ) -> None:
        self.reader = reader
        self.engine = engine
        self.caches = caches
        self.chart_builder = chart_builder or ChartDataBuilder()

    async def deembed(
        self,
        *,
        total: UploadFile | None,
        thru_a: UploadFile | None,
        thru_b: UploadFile | None,
        side: str = "both",
        port_mapping: str = "auto",
        reference_z0: float = 50.0,
        token: str | None = None,
    ) -> DeembedPayload:
        resolved_side = _resolve_side(side)
        requested_mapping = PortMapping.parse(
            port_mapping,
            field="S4P 端口映射",
            allowed=(PortMapping.AUTO, PortMapping.SEQUENTIAL, PortMapping.PLTS),
        )
        z0 = _resolve_reference_z0(reference_z0)

        if token:
            triplet = self.caches.inspection.get(token)
            if triplet is None:
                raise CacheExpiredError("文件识别缓存已过期，请重新选择或等待文件重新识别。")
        else:
            if total is None or thru_a is None or thru_b is None:
                raise InvalidInputError("请上传 Total、2X Thru A 与 2X Thru B，或使用有效的识别缓存。")
            triplet = await self.reader.read_triplet(total, thru_a, thru_b)

        try:
            outcome = self.engine.run(
                DeembedRequest.from_triplet(
                    triplet,
                    side=resolved_side,
                    port_mapping=requested_mapping,
                    reference_z0=z0,
                )
            )
        except DeembedError:
            raise
        except Exception as exc:  # noqa: BLE001 - 统一包装为 422
            raise ComputationError(f"去嵌计算失败：{type(exc).__name__}: {exc}") from exc

        chart = self.chart_builder.build(outcome.display_networks(), outcome.port_mapping)
        stored: dict[str, object] = {"dut": outcome.dut}
        if outcome.fixtures is not None:
            stored["fix_a"] = outcome.fixtures.left
            stored["fix_b"] = outcome.fixtures.right
        result_token = self.caches.results.store(stored)

        payload: DeembedPayload = {
            "success": True,
            "result_token": result_token,
            "message": _MESSAGE,
            "topology": "单端 S2P" if outcome.nports == 2 else "差分 S4P",
            "side": resolved_side.value,
            "port_mapping": outcome.port_mapping.value if outcome.nports == 4 else None,
            "mapping_label": mapping_label(outcome.nports, outcome.port_mapping),
            "left_ports": pair_labels(outcome.nports, outcome.port_mapping)[0],
            "right_ports": pair_labels(outcome.nports, outcome.port_mapping)[1],
            "reference_z0": float(z0),
            "frequency_start_ghz": outcome.frequency_start_hz / 1e9,
            "frequency_stop_ghz": outcome.frequency_stop_hz / 1e9,
            "points": outcome.points,
            "quality": outcome.quality.to_payload(),
            "chart": chart.to_payload(),
            "nports": outcome.nports,
        }
        if result_token is None:
            # 结果体积超出缓存预算时，退化为一次性内联返回，保持前端可用。
            payload["dut_touchstone"] = network_to_text(outcome.dut, form="ri")
            if outcome.fixtures is not None:
                payload["fix_a_touchstone"] = network_to_text(outcome.fixtures.left, form="ri")
                payload["fix_b_touchstone"] = network_to_text(outcome.fixtures.right, form="ri")
        return payload

    def result_networks(self, token: str | None) -> dict[str, object] | None:
        return self.caches.results.get(token)


def _resolve_side(side: str) -> DeembedSide:
    try:
        return DeembedSide.parse(side, field="去嵌侧")
    except DeembedError as exc:  # pragma: no cover - parse 已保证消息
        raise InvalidInputError("去嵌侧设置无效。") from exc


def _resolve_reference_z0(value: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidInputError("参考阻抗必须是大于 0 的有限数值。") from exc
    if not np.isfinite(numeric) or numeric <= 0:
        raise InvalidInputError("参考阻抗必须是大于 0 的有限数值。")
    return numeric
