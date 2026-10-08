"""文件识别服务：解析上传文件、输出端口映射/预览/夹具诊断。

对应 ``POST /api/inspect``。
"""

from __future__ import annotations

from typing import Any

from fastapi import UploadFile

from deembed import DeembeddingEngine, NetworkTriplet, PortMapping, resolve_port_mapping
from deembed.mixed_mode import MixedModeConverter
from deembed.reporting import FixtureStatisticsAnalyzer, NetworkPreviewBuilder

from ..cache import NetworkCacheStore
from deembed.errors import CacheExpiredError
from ..schemas import InspectionPayload
from ..uploads import UploadReader

__all__ = ["InspectionService"]

_ALLOWED_MAPPINGS = (PortMapping.AUTO, PortMapping.SEQUENTIAL, PortMapping.PLTS)


class InspectionService:
    """识别三个输入网络并生成前端所需的映射/预览数据。"""

    def __init__(
        self,
        reader: UploadReader,
        engine: DeembeddingEngine,
        caches: NetworkCacheStore,
        *,
        preview_builder: NetworkPreviewBuilder | None = None,
        statistics_analyzer: FixtureStatisticsAnalyzer | None = None,
    ) -> None:
        self.reader = reader
        self.engine = engine
        self.caches = caches
        self.preview_builder = preview_builder or NetworkPreviewBuilder()
        self.statistics_analyzer = statistics_analyzer or FixtureStatisticsAnalyzer()

    async def inspect(
        self,
        *,
        total: UploadFile | None,
        thru_a: UploadFile | None,
        thru_b: UploadFile | None,
        port_mapping: str = "auto",
        token: str | None = None,
    ) -> InspectionPayload:
        requested = PortMapping.parse(port_mapping, field="S4P 端口映射", allowed=_ALLOWED_MAPPINGS)

        cached = self.caches.inspection.get(token)
        if cached is not None:
            triplet = cached
        else:
            if total is None or thru_a is None or thru_b is None:
                raise CacheExpiredError("文件识别缓存已过期或输入文件缺失，请重新选择三个文件。")
            triplet = await self.reader.read_triplet(total, thru_a, thru_b)

        effective = resolve_port_mapping(triplet.total, requested)
        previews = self._build_previews(triplet, effective)
        statistics = self._build_statistics(triplet, effective)

        # 频段信息以“对齐后的 Total 网格”为准（不改变参考阻抗）。
        prepared = self.engine.prepare(
            triplet.total,
            thru_a=triplet.thru_a,
            thru_b=triplet.thru_b,
            port_mapping=requested,
            reference_z0=50.0,
            normalize_reference=False,
        )

        payload: InspectionPayload = {
            "success": True,
            "inspection_token": self.caches.inspection.store(triplet),
            "nports": int(triplet.total.nports),
            "topology": "单端 S2P" if triplet.total.nports == 2 else "差分 S4P",
            "requested_mapping": requested.value,
            "detected_mapping": effective.value,
            "mapping_label": prepared.mapping_label,
            "left_ports": prepared.left_ports,
            "right_ports": prepared.right_ports,
            "file_previews": previews,
            "fixture_statistics": statistics,
            "frequency_start_ghz": prepared.frequency_start_ghz,
            "frequency_stop_ghz": prepared.frequency_stop_ghz,
            "points": prepared.points,
        }
        return payload

    # ------------------------------------------------------------------ 内部
    def _build_previews(self, triplet: NetworkTriplet, mapping: PortMapping) -> dict[str, Any]:
        converter = MixedModeConverter(mapping)
        mixed_a = converter.db_traces(triplet.thru_a) if triplet.total.nports == 4 else None
        mixed_b = converter.db_traces(triplet.thru_b) if triplet.total.nports == 4 else None
        return {
            "thru_a": self.preview_builder.build(triplet.thru_a, mapping, mixed_mode_db=mixed_a).to_payload(),
            "total": self.preview_builder.build(triplet.total, mapping).to_payload(),
            "thru_b": self.preview_builder.build(triplet.thru_b, mapping, mixed_mode_db=mixed_b).to_payload(),
        }

    def _build_statistics(self, triplet: NetworkTriplet, mapping: PortMapping) -> dict[str, Any] | None:
        if triplet.total.nports != 4:
            return None
        return {
            "thru_a": [rule.to_payload() for rule in self.statistics_analyzer.analyze(triplet.thru_a, mapping)],
            "thru_b": [rule.to_payload() for rule in self.statistics_analyzer.analyze(triplet.thru_b, mapping)],
        }
