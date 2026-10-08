"""内置工程预设：一键演练 + 测试数据源。

用法::

    from deembed import presets

    preset = presets.get_preset("se_dual_2xthru")
    outcome = engine.run(DeembedRequest.from_triplet(preset.to_triplet()))
"""

from __future__ import annotations

from typing import Callable, Final, Mapping

from .base import DemoPreset, PresetValidationError
from .differential import (
    diff_2xthru,
    diff_asym_2xthru,
    diff_asym_file,
    diff_dual_2xthru,
    diff_file_based,
    diff_skew_dual_2xthru,
)
from .single_ended import se_2xthru, se_asym_2xthru, se_asym_file, se_dual_2xthru, se_file_based

__all__ = ["DemoPreset", "PresetValidationError", "PRESETS", "get_preset", "list_presets", "preset_ids"]

#: 预设 id → 工厂函数（每次调用都重新生成，避免共享可变网络对象）
PRESETS: Final[Mapping[str, Callable[[], DemoPreset]]] = {
    "se_dual_2xthru": se_dual_2xthru,
    "diff_dual_2xthru": diff_dual_2xthru,
    "se_asym_2xthru": se_asym_2xthru,
    "diff_asym_2xthru": diff_asym_2xthru,
    "se_asym_file": se_asym_file,
    "diff_asym_file": diff_asym_file,
    "se_2xthru": se_2xthru,
    "diff_2xthru": diff_2xthru,
    "se_file_based": se_file_based,
    "diff_file_based": diff_file_based,
    "diff_skew_dual_2xthru": diff_skew_dual_2xthru,
}


def preset_ids() -> list[str]:
    return list(PRESETS.keys())


def get_preset(preset_id: str) -> DemoPreset:
    """按 id 生成预设；未知 id 抛出 ``KeyError``。"""

    factory = PRESETS[preset_id]
    return factory()


def list_presets() -> list[dict[str, str]]:
    """预设目录（id / 标题 / 描述 / 方法与拓扑），供前端下拉框使用。"""

    catalog: list[dict[str, str]] = []
    for preset_id, factory in PRESETS.items():
        preset = factory()
        catalog.append(
            {
                "id": preset.id,
                "title": preset.title,
                "description": preset.description,
                "method": preset.method.value,
                "topology": preset.topology,
            }
        )
    return catalog
