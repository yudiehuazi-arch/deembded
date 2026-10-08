"""TDR 服务：输入网络与去嵌结果的时域阶跃阻抗。

对应 ``POST /api/tdr/input`` 与 ``POST /api/tdr/result``。
"""

from __future__ import annotations

import skrf as rf

from deembed import NetworkTriplet, PortMapping, TdrAnalyzer, TdrSettings, resolve_port_mapping
from deembed.frequency import renormalize

from ..cache import NetworkCacheStore
from deembed.errors import CacheExpiredError, InvalidInputError
from ..schemas import TdrStackPayload

__all__ = ["TdrService"]

_INPUT_SLOTS = ("total", "thru_a", "thru_b")
_ALLOWED_MAPPINGS = (PortMapping.AUTO, PortMapping.SEQUENTIAL, PortMapping.PLTS)


class TdrService:
    def __init__(self, caches: NetworkCacheStore, analyzer: TdrAnalyzer | None = None) -> None:
        self.caches = caches
        self.analyzer = analyzer or TdrAnalyzer()

    # ------------------------------------------------------------------ 输入
    def input_stack(
        self,
        *,
        inspection_token: str | None,
        slot: str,
        port: int | str,
        port_mapping: str,
        reference_z0: float,
        window: str,
        dc_method: str,
        rise_time_ps: float | str,
    ) -> TdrStackPayload:
        triplet = self.caches.inspection.get(inspection_token)
        if triplet is None:
            raise CacheExpiredError("输入网络缓存已过期，请重新选择三个文件。")

        requested = PortMapping.parse(port_mapping, field="S4P 端口映射", allowed=_ALLOWED_MAPPINGS)
        settings = TdrSettings.from_form(port=port, window=window, dc_method=dc_method, rise_time_ps=rise_time_ps)
        mapping = resolve_port_mapping(triplet.total, requested)
        self.analyzer.validate(settings, float(reference_z0))

        if slot == "all":
            networks = {key: _prepared(network, reference_z0) for key, network in _triplet_items(triplet)}
            stack = self.analyzer.stack(networks, settings=settings, port_mapping=mapping, reference_z0=float(reference_z0))
            payload = stack.to_payload()
            payload.update({"success": True, "slot": "all", "port_mapping": mapping.value, **settings.summary()})
            return payload  # type: ignore[return-value]

        if slot not in _INPUT_SLOTS:
            raise InvalidInputError("未知的输入网络类型。")
        network = dict(_triplet_items(triplet))[slot]
        trace = self.analyzer.step_impedance(
            _prepared(network, reference_z0), settings=settings, port_mapping=mapping, reference_z0=float(reference_z0)
        )
        payload = trace.to_payload()
        payload.update({"success": True, "slot": slot, "port_mapping": mapping.value, **settings.summary()})
        return payload  # type: ignore[return-value]

    # ------------------------------------------------------------------ 结果
    def result_stack(
        self,
        *,
        inspection_token: str | None,
        result_token: str | None,
        port: int | str,
        port_mapping: str,
        reference_z0: float,
        window: str,
        dc_method: str,
        rise_time_ps: float | str,
    ) -> TdrStackPayload:
        triplet = self.caches.inspection.get(inspection_token)
        if triplet is None:
            raise CacheExpiredError("输入网络缓存已过期，请重新识别并运行去嵌。")
        computed = self.caches.results.get(result_token)
        if computed is None:
            raise CacheExpiredError("去嵌结果缓存已过期，请重新运行计算。")

        requested = PortMapping.parse(port_mapping, field="S4P 端口映射", allowed=_ALLOWED_MAPPINGS)
        settings = TdrSettings.from_form(port=port, window=window, dc_method=dc_method, rise_time_ps=rise_time_ps)
        mapping = resolve_port_mapping(triplet.total, requested)

        networks: dict[str, rf.Network] = {key: _prepared(network, reference_z0) for key, network in _triplet_items(triplet)}
        for key, network in computed.items():
            networks[key] = renormalize(network, float(reference_z0))

        stack = self.analyzer.stack(networks, settings=settings, port_mapping=mapping, reference_z0=float(reference_z0))
        payload = stack.to_payload()
        payload.update({"success": True, "port_mapping": mapping.value, **settings.summary()})
        return payload  # type: ignore[return-value]


def _triplet_items(triplet: NetworkTriplet) -> tuple[tuple[str, rf.Network], ...]:
    return (("total", triplet.total), ("thru_a", triplet.thru_a), ("thru_b", triplet.thru_b))


def _prepared(network: rf.Network, reference_z0: float) -> rf.Network:
    """TDR 输入统一重归一化到参考阻抗。"""

    return renormalize(network, float(reference_z0))
