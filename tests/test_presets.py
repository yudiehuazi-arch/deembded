"""预设定目录与生成器完整性。"""

from __future__ import annotations

import pytest

from deembed import FixtureMethod, presets
from deembed.presets.base import PresetValidationError


def test_catalog_lists_all_presets() -> None:
    catalog = presets.list_presets()
    assert len(catalog) == 11
    assert {item["id"] for item in catalog} == set(presets.preset_ids())
    for item in catalog:
        assert item["title"] and item["description"]
        assert item["topology"] in {"se", "diff"}


@pytest.mark.parametrize("preset_id", presets.preset_ids())
def test_preset_is_self_consistent(preset_id: str) -> None:
    preset = presets.get_preset(preset_id)
    assert preset.id == preset_id
    assert preset.total.nports == preset.dut_ideal.nports
    assert preset.nports == (2 if preset.topology == "se" else 4)
    assert len(preset.total.f) == 269

    if preset.method in {FixtureMethod.DUAL_2X_THRU, FixtureMethod.SINGLE_2X_THRU}:
        assert preset.to_triplet() is not None
    if preset.method is FixtureMethod.FIXTURE_FILES:
        assert preset.fix_left is not None and preset.fix_right is not None
        assert preset.fix_left.nports == preset.nports
    if preset.topology == "diff":
        assert preset.total.nports == 4


def test_preset_instances_are_fresh_copies() -> None:
    first = presets.get_preset("se_dual_2xthru")
    second = presets.get_preset("se_dual_2xthru")
    assert first.total is not second.total


def test_to_dict_exposes_legacy_keys() -> None:
    payload = presets.get_preset("se_asym_2xthru").to_dict()
    assert payload["mode"] == "se"
    assert payload["method"] == "single_2xthru"
    assert payload["delta_delay_ps_a"] < 0 < payload["delta_delay_ps_b"]
    assert payload["length_ratio_a"] == pytest.approx(12 / 36)


def test_unknown_preset_raises() -> None:
    with pytest.raises(KeyError):
        presets.get_preset("nope")


def test_triplet_requires_standards() -> None:
    preset = presets.get_preset("se_file_based")
    with pytest.raises(PresetValidationError):
        preset.to_triplet()
