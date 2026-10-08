"""领域模型：枚举与不可变数据类。

这些类型是内核（deembed 包）与 Web 层（backend 包）之间的契约。
所有数据类均为 frozen，避免跨线程/跨请求共享状态被意外修改。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

import numpy as np
import skrf as rf

from .errors import InvalidInputError

__all__ = [
    "DeembedSide",
    "PortMapping",
    "FixtureMethod",
    "TdrWindow",
    "DcMethod",
    "NetworkTriplet",
    "FixturePair",
    "QualityReport",
    "FixtureCorrection",
    "FixtureStandardSet",
    "DeembedRequest",
    "DeembedOutcome",
]


class _StrEnum(str, Enum):
    """Python 3.11 之前的 str 枚举兼容基类（同时支持 ``== "x"`` 与 ``json`` 序列化）。"""

    def __str__(self) -> str:  # pragma: no cover - 简单转发
        return str(self.value)

    @classmethod
    def parse(cls, value: Any, *, field: str, allowed: Iterable[str] | None = None) -> "Any":
        """把外部输入（表单字符串）解析为枚举成员，失败时抛出领域异常。"""
        if isinstance(value, cls):
            return value
        candidates = list(allowed) if allowed is not None else [member.value for member in cls]
        text = str(value).strip().lower()
        for candidate in candidates:
            if text == str(candidate).lower():
                return cls(str(candidate))
        raise InvalidInputError(f"{field}设置无效。")


class DeembedSide(_StrEnum):
    """去嵌作用范围：双边 / 仅左 / 仅右。"""

    BOTH = "both"
    LEFT = "left"
    RIGHT = "right"


class PortMapping(_StrEnum):
    """4 端口差分映射约定。"""

    AUTO = "auto"
    SEQUENTIAL = "sequential"
    PLTS = "plts"
    SINGLE_ENDED = "single-ended"


class FixtureMethod(_StrEnum):
    """夹具建模（剥离）策略标识。

    新增算法时：实现 ``deembed.fixtures.base.FixtureModelProvider`` 并在
    ``DeembeddingEngine.register_provider`` 中注册即可，无需改动 API 层。
    """

    DUAL_2X_THRU = "dual_2xthru"      # 左右各一条独立 2X Thru 标准件，分别劈半
    SINGLE_2X_THRU = "single_2xthru"  # 单条 2X Thru，对称劈半后左右复用
    FIXTURE_FILES = "fixture_files"   # 用户直接提供左右 1X 夹具文件
    PORT_EXTENSION = "port_extension"  # 端口延伸（时延/损耗剥离），无需夹具文件


class TdrWindow(_StrEnum):
    HAMMING = "hamming"
    HANN = "hann"
    BLACKMAN = "blackman"
    NONE = "none"


class DcMethod(_StrEnum):
    LINEAR = "linear"
    HOLD = "hold"


@dataclass(frozen=True)
class NetworkTriplet:
    """一次计算所需的三个测量网络。"""

    total: rf.Network
    thru_a: rf.Network
    thru_b: rf.Network

    def __iter__(self):
        return iter((self.total, self.thru_a, self.thru_b))

    def as_tuple(self) -> tuple[rf.Network, rf.Network, rf.Network]:
        return (self.total, self.thru_a, self.thru_b)

    @property
    def nports(self) -> int:
        return int(self.total.nports)


@dataclass(frozen=True)
class FixturePair:
    """左右 1X 夹具模型。"""

    left: rf.Network
    right: rf.Network


@dataclass(frozen=True)
class FixtureCorrection:
    """PLTS 风格的非对称夹具长度/损耗校正参数。"""

    delay_ps: float = 0.0
    loss_db: float = 0.0

    @property
    def is_noop(self) -> bool:
        return abs(self.delay_ps) < 1e-4 and abs(self.loss_db) < 1e-4


@dataclass(frozen=True)
class FixtureStandardSet:
    """夹具建模所需的全部标准件输入（按方法按需填充）。"""

    thru_a: rf.Network | None = None
    thru_b: rf.Network | None = None
    fix_a: rf.Network | None = None
    fix_b: rf.Network | None = None

    @classmethod
    def from_triplet(cls, triplet: NetworkTriplet) -> "FixtureStandardSet":
        return cls(thru_a=triplet.thru_a, thru_b=triplet.thru_b)


@dataclass(frozen=True)
class QualityReport:
    """IEEE 370 Annex C 质量指标。"""

    status: str
    verdict: str
    max_singular_value: float
    passivity_pass: bool
    passivity_margin_db: float
    reciprocity_error: float
    reciprocity_pass: bool

    def to_payload(self) -> dict[str, Any]:
        """保持与旧接口一致的 JSON 字段（前端依赖这些小写键）。"""
        return {
            "status": self.status,
            "verdict": self.verdict,
            "max_singular_value": self.max_singular_value,
            "passivity_pass": self.passivity_pass,
            "passivity_margin_db": self.passivity_margin_db,
            "reciprocity_error": self.reciprocity_error,
            "reciprocity_pass": self.reciprocity_pass,
        }


@dataclass(frozen=True)
class DeembedRequest:
    """一次去嵌计算请求（框架无关的完整描述）。"""

    total: rf.Network
    standards: FixtureStandardSet
    side: DeembedSide = DeembedSide.BOTH
    port_mapping: PortMapping = PortMapping.AUTO
    reference_z0: float = 50.0
    method: FixtureMethod = FixtureMethod.DUAL_2X_THRU
    correction_a: FixtureCorrection = FixtureCorrection()
    correction_b: FixtureCorrection = FixtureCorrection()
    port_extension: "PortExtensionSettings | None" = None

    @classmethod
    def from_triplet(
        cls,
        triplet: NetworkTriplet,
        *,
        side: DeembedSide = DeembedSide.BOTH,
        port_mapping: PortMapping = PortMapping.AUTO,
        reference_z0: float = 50.0,
        method: FixtureMethod = FixtureMethod.DUAL_2X_THRU,
        **kwargs: Any,
    ) -> "DeembedRequest":
        return cls(
            total=triplet.total,
            standards=FixtureStandardSet.from_triplet(triplet),
            side=side,
            port_mapping=port_mapping,
            reference_z0=reference_z0,
            method=method,
            **kwargs,
        )


@dataclass(frozen=True)
class PortExtensionSettings:
    """端口延伸（Port Extension）去嵌参数。"""

    delay_ps_left: float = 0.0
    delay_ps_right: float = 0.0
    loss_db_left: float = 0.0
    loss_db_right: float = 0.0


@dataclass(frozen=True)
class DeembedOutcome:
    """去嵌结果。"""

    dut: rf.Network
    quality: QualityReport
    side: DeembedSide
    method: FixtureMethod
    port_mapping: PortMapping
    reference_z0: float
    total: rf.Network
    fixtures: FixturePair | None = None
    thru_a: rf.Network | None = None
    thru_b: rf.Network | None = None

    @property
    def nports(self) -> int:
        return int(self.dut.nports)

    @property
    def points(self) -> int:
        return int(len(self.dut.f))

    @property
    def frequency_start_hz(self) -> float:
        return float(np.asarray(self.dut.f)[0])

    @property
    def frequency_stop_hz(self) -> float:
        return float(np.asarray(self.dut.f)[-1])

    def display_networks(self) -> dict[str, rf.Network]:
        """结果图表要对比的网络曲线（缺少的标准件会被自动跳过）。"""
        networks: dict[str, rf.Network] = {"total": self.total, "dut": self.dut}
        if self.fixtures is not None:
            networks["fix_a"] = self.fixtures.left
            networks["fix_b"] = self.fixtures.right
        if self.thru_a is not None:
            networks["thru_a"] = self.thru_a
        if self.thru_b is not None:
            networks["thru_b"] = self.thru_b
        return networks


def validation_error(message: str) -> InvalidInputError:
    """便捷构造器，保持异常消息风格统一。"""

    return InvalidInputError(message)
