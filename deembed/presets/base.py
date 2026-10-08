"""预设示例的数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import skrf as rf

from ..models import FixtureCorrection, FixtureMethod, NetworkTriplet

__all__ = ["DemoPreset", "PresetValidationError"]


class PresetValidationError(ValueError):
    """预设定义不完整（开发期错误）。"""


@dataclass(frozen=True)
class DemoPreset:
    """一套可直接运行的合成示例。

    字段刻意覆盖四种去嵌方法所需的全部输入，便于测试直接消费：
    ``total`` + ``thru_2x_a``/``thru_2x_b``（双 2X Thru）或 ``thru_2x``（单条）
    或 ``fix_left``/``fix_right``（夹具文件）。
    """

    id: str
    title: str
    description: str
    method: FixtureMethod
    topology: str  # "se"（单端） | "diff"（差分）
    total: rf.Network
    dut_ideal: rf.Network
    thru_2x: rf.Network | None = None
    thru_2x_a: rf.Network | None = None
    thru_2x_b: rf.Network | None = None
    fix_left: rf.Network | None = None
    fix_right: rf.Network | None = None
    fixture_symmetry: str = "symmetric"
    correction_a: FixtureCorrection = FixtureCorrection()
    correction_b: FixtureCorrection = FixtureCorrection()
    length_ratio_a: float | None = None
    length_ratio_b: float | None = None
    tags: tuple[str, ...] = ()

    # ------------------------------------------------------------------ 便捷
    def to_triplet(self) -> NetworkTriplet:
        """构造引擎需要的三网络输入（用于 dual / single 2X Thru 方法）。"""

        thru_a = self.thru_2x_a or self.thru_2x
        thru_b = self.thru_2x_b or self.thru_2x
        if thru_a is None or thru_b is None:
            raise PresetValidationError(f"预设 {self.id} 缺少 2X Thru 标准件，无法构造 NetworkTriplet。")
        return NetworkTriplet(total=self.total, thru_a=thru_a, thru_b=thru_b)

    @property
    def nports(self) -> int:
        return int(self.total.nports)

    def to_dict(self) -> dict[str, Any]:
        """兼容旧接口的字典形式（键名与历史版本保持一致）。"""

        payload: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "mode": self.topology,
            "method": self.method.value,
            "fixture_symmetry": self.fixture_symmetry,
            "total": self.total,
            "fix_l": self.fix_left,
            "fix_r": self.fix_right,
            "thru_2x": self.thru_2x,
            "dut_ideal": self.dut_ideal,
        }
        if self.thru_2x_a is not None:
            payload["thru_2x_a"] = self.thru_2x_a
        if self.thru_2x_b is not None:
            payload["thru_2x_b"] = self.thru_2x_b
        if not self.correction_a.is_noop:
            payload["delta_delay_ps_a"] = self.correction_a.delay_ps
            payload["delta_loss_db_a"] = self.correction_a.loss_db
        if not self.correction_b.is_noop:
            payload["delta_delay_ps_b"] = self.correction_b.delay_ps
            payload["delta_loss_db_b"] = self.correction_b.loss_db
        if self.length_ratio_a is not None:
            payload["length_ratio_a"] = self.length_ratio_a
        if self.length_ratio_b is not None:
            payload["length_ratio_b"] = self.length_ratio_b
        return payload


def _unused_field_marker() -> None:  # pragma: no cover - 避免导入 lint 告警
    _ = field
