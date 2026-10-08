"""去嵌引擎：把校验、对齐、策略与质量检查串成一条流水线。

流水线（每一步都可单独测试）：

1. :meth:`DeembeddingEngine.prepare` —— 端口数校验、参考阻抗统一、
   共同频段对齐、端口映射解析与重排；
2. :meth:`DeembeddingEngine.run` —— 交给策略产出 1X 夹具并做 T 矩阵反演；
3. 结果还原到用户端口排布 + IEEE 370 Annex C 质量检查。

设计要点：引擎本身不感知 HTTP / 表单 / 缓存，只处理 ``rf.Network``，
因此同一份逻辑既服务 Web API，也能被脚本或未来的 CLI 复用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import skrf as rf

from .errors import InvalidInputError
from .frequency import FrequencyAligner, renormalize
from .metrics import QualityAnalyzer
from .models import (
    DeembedOutcome,
    DeembedRequest,
    FixtureCorrection,
    FixtureMethod,
    FixturePair,
    FixtureStandardSet,
    NetworkTriplet,
    PortMapping,
)
from .port_mapping import apply_port_mapping, mapping_label, pair_labels, resolve_port_mapping, restore_port_mapping
from .strategies import DeembeddingStrategy, StrategyContext, default_strategies
from .touchstone import SUPPORTED_PORT_COUNTS

__all__ = ["PreparedNetworks", "DeembeddingEngine", "build_default_engine", "shared_engine"]


@dataclass(frozen=True)
class PreparedNetworks:
    """流水线第一阶段输出：已归一化/对齐/重排的网络与生效端口映射。"""

    total: rf.Network
    standards: FixtureStandardSet
    port_mapping: PortMapping
    nports: int
    reference_z0: float

    @property
    def left_ports(self) -> list[str]:
        return pair_labels(self.nports, self.port_mapping)[0]

    @property
    def right_ports(self) -> list[str]:
        return pair_labels(self.nports, self.port_mapping)[1]

    @property
    def mapping_label(self) -> str:
        return mapping_label(self.nports, self.port_mapping)

    @property
    def points(self) -> int:
        return int(len(self.total.f))

    @property
    def frequency_start_ghz(self) -> float:
        return float(self.total.f[0] / 1e9)

    @property
    def frequency_stop_ghz(self) -> float:
        return float(self.total.f[-1] / 1e9)


class DeembeddingEngine:
    """去嵌计算门面（Facade）。

    Args:
        strategies: 方法 → 策略映射；默认使用内置策略。
        aligner: 频率对齐器，可替换为自定义插值策略。
        quality: 质量检查器，可替换为更严格的标准。
    """

    def __init__(
        self,
        *,
        strategies: Mapping[FixtureMethod, DeembeddingStrategy] | None = None,
        aligner: FrequencyAligner | None = None,
        quality: QualityAnalyzer | None = None,
    ) -> None:
        self._strategies: dict[FixtureMethod, DeembeddingStrategy] = dict(strategies or default_strategies())
        self.aligner = aligner or FrequencyAligner()
        self.quality = quality or QualityAnalyzer()

    # ------------------------------------------------------------- 注册/查询
    def register_strategy(self, strategy: DeembeddingStrategy) -> None:
        """注册（或覆盖）一种夹具建模方法。"""

        self._strategies[strategy.method] = strategy

    def strategy_for(self, method: FixtureMethod | str) -> DeembeddingStrategy:
        try:
            resolved = method if isinstance(method, FixtureMethod) else FixtureMethod.parse(method, field="去嵌方法")
        except InvalidInputError as exc:
            raise InvalidInputError(f"不支持的去嵌方法：{method}") from exc
        strategy = self._strategies.get(resolved)
        if strategy is None:
            raise InvalidInputError(f"尚未注册的去嵌方法：{resolved.value}")
        return strategy

    def available_methods(self) -> list[dict[str, str]]:
        """供 /api/health 等方法列表展示。"""

        return [{"method": method.value, "description": strategy.describe()} for method, strategy in self._strategies.items()]

    # ------------------------------------------------------------ 准备阶段
    def validate_port_counts(self, networks: Sequence[rf.Network]) -> int:
        """校验参与计算的网络端口数一致且受支持。"""

        counts = {int(network.nports) for network in networks}
        if len(counts) > 1:
            raise InvalidInputError("Total、2X Thru A、2X Thru B 的端口数必须一致；请勿混用 S2P 与 S4P。")
        nports = counts.pop() if counts else 0
        if nports not in SUPPORTED_PORT_COUNTS:
            raise InvalidInputError("目前仅支持单端 S2P 或差分 S4P 网络。")
        return nports

    def prepare(
        self,
        total: rf.Network,
        *,
        thru_a: rf.Network | None = None,
        thru_b: rf.Network | None = None,
        fix_a: rf.Network | None = None,
        fix_b: rf.Network | None = None,
        port_mapping: PortMapping | str = PortMapping.AUTO,
        reference_z0: float = 50.0,
        normalize_reference: bool = True,
    ) -> PreparedNetworks:
        """归一化参考阻抗、对齐频段并统一端口排布。

        Args:
            normalize_reference: 是否把网络参考阻抗统一到 ``reference_z0``。
                识别预览（inspect）需要保持原始参考阻抗，因此传入 ``False``。
        """

        slots: tuple[tuple[str, rf.Network | None], ...] = (
            ("thru_a", thru_a),
            ("thru_b", thru_b),
            ("fix_a", fix_a),
            ("fix_b", fix_b),
        )
        provided = [(name, network) for name, network in slots if network is not None]
        nports = self.validate_port_counts([total, *(network for _, network in provided)])

        factor = float(reference_z0)
        normalized = [
            renormalize(network, factor) if normalize_reference else network.copy()
            for network in [total, *(network for _, network in provided)]
        ]
        aligned = self.aligner.align(normalized)
        aligned_total = aligned[0]

        mapping = resolve_port_mapping(aligned_total, port_mapping)
        aligned_standards = {
            name: apply_port_mapping(network, mapping) for (name, _), network in zip(provided, aligned[1:])
        }
        standards = FixtureStandardSet(
            thru_a=aligned_standards.get("thru_a"),
            thru_b=aligned_standards.get("thru_b"),
            fix_a=aligned_standards.get("fix_a"),
            fix_b=aligned_standards.get("fix_b"),
        )
        return PreparedNetworks(
            total=apply_port_mapping(aligned_total, mapping),
            standards=standards,
            port_mapping=mapping,
            nports=nports,
            reference_z0=float(reference_z0),
        )

    # ------------------------------------------------------------ 计算阶段
    def run(self, request: DeembedRequest) -> DeembedOutcome:
        """执行完整去嵌流程。"""

        prepared = self.prepare(
            request.total,
            thru_a=request.standards.thru_a,
            thru_b=request.standards.thru_b,
            fix_a=request.standards.fix_a,
            fix_b=request.standards.fix_b,
            port_mapping=request.port_mapping,
            reference_z0=request.reference_z0,
        )
        context = StrategyContext(
            total=prepared.total,
            standards=prepared.standards,
            z0=prepared.reference_z0,
            side=request.side,
            correction_a=request.correction_a,
            correction_b=request.correction_b,
            port_extension=request.port_extension,
        )
        result = self.strategy_for(request.method).apply(context)

        dut = restore_port_mapping(result.dut, prepared.port_mapping)
        fixtures = None
        if result.fixtures is not None:
            fixtures = FixturePair(
                left=restore_port_mapping(result.fixtures.left, prepared.port_mapping),
                right=restore_port_mapping(result.fixtures.right, prepared.port_mapping),
            )

        return DeembedOutcome(
            dut=dut,
            quality=self.quality.analyze(dut),
            side=request.side,
            method=request.method,
            port_mapping=prepared.port_mapping,
            reference_z0=prepared.reference_z0,
            total=prepared.total,
            fixtures=fixtures,
            thru_a=prepared.standards.thru_a,
            thru_b=prepared.standards.thru_b,
        )

    # ------------------------------------------------------------ 便捷入口
    def split_fixtures(
        self,
        triplet: NetworkTriplet,
        *,
        port_mapping: PortMapping | str = PortMapping.AUTO,
        reference_z0: float = 50.0,
        corrections: tuple[FixtureCorrection, FixtureCorrection] | None = None,
    ) -> FixturePair | None:
        """只提取 1X 夹具模型（供“仅拆分夹具”类功能复用）。"""

        prepared = self.prepare(
            triplet.total,
            thru_a=triplet.thru_a,
            thru_b=triplet.thru_b,
            port_mapping=port_mapping,
            reference_z0=reference_z0,
        )
        correction_a, correction_b = corrections or (FixtureCorrection(), FixtureCorrection())
        result = self.strategy_for(FixtureMethod.DUAL_2X_THRU).apply(
            StrategyContext(
                total=prepared.total,
                standards=prepared.standards,
                z0=prepared.reference_z0,
                correction_a=correction_a,
                correction_b=correction_b,
            )
        )
        return result.fixtures

    def deembed_triplet(
        self,
        triplet: NetworkTriplet,
        *,
        side: str = "both",
        port_mapping: PortMapping | str = PortMapping.AUTO,
        reference_z0: float = 50.0,
        method: FixtureMethod | str = FixtureMethod.DUAL_2X_THRU,
    ) -> DeembedOutcome:
        """常用组合的便捷封装（Web 层默认走这里）。"""

        return self.run(
            DeembedRequest.from_triplet(
                triplet,
                side=side,
                port_mapping=port_mapping,
                reference_z0=reference_z0,
                method=method,
            )
        )


_DEFAULT_ENGINE: DeembeddingEngine | None = None


def build_default_engine() -> DeembeddingEngine:
    """创建默认引擎（每次调用返回新实例，便于测试隔离）。"""

    return DeembeddingEngine()


def shared_engine() -> DeembeddingEngine:
    """进程级共享引擎（引擎本身无状态，可安全并发使用）。"""

    global _DEFAULT_ENGINE
    if _DEFAULT_ENGINE is None:
        _DEFAULT_ENGINE = build_default_engine()
    return _DEFAULT_ENGINE
