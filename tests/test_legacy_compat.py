"""v1 兼容层测试：``deembed.legacy`` 与 ``backend.deembed_engine``。

保证历史脚本的导入路径、函数签名与返回结构继续可用，并且结果与 v2
内核一致（v1 的数值行为已在重构时逐项对齐）。
"""

from __future__ import annotations

import numpy as np
import pytest
import skrf as rf

from backend import deembed_engine as shim
from deembed import legacy

LEGACY_FUNCTIONS = [
    "load_network_from_str",
    "network_to_touchstone_str",
    "align_frequencies",
    "generalized_s2t",
    "generalized_t2s",
    "uncoupled_lines_to_4port",
    "deembed_t_matrix",
    "file_based_deembed_2port",
    "file_based_deembed_4port",
    "adjust_fixture_delay_loss",
    "ieee370_2xthru_deembed_2port",
    "ieee370_2xthru_deembed_4port",
    "dual_2xthru_deembed_2port",
    "dual_2xthru_deembed_4port",
    "port_extension_deembed",
    "auto_detect_port_mapping",
    "compute_mixed_mode",
    "compute_tdr_profile",
    "quality_check",
    "extract_network_display_data",
]

LEGACY_PRESETS = [
    "se_dual_2xthru",
    "diff_dual_2xthru",
    "se_asym_2xthru",
    "diff_asym_2xthru",
    "se_asym_file",
    "diff_asym_file",
    "se_2xthru",
    "diff_2xthru",
    "se_file_based",
    "diff_file_based",
]


@pytest.mark.parametrize("name", LEGACY_FUNCTIONS + [f"generate_preset_{preset}" for preset in LEGACY_PRESETS])
def test_legacy_names_are_importable_from_both_paths(name):
    assert callable(getattr(legacy, name))
    assert callable(getattr(shim, name))
    assert getattr(shim, name) is getattr(legacy, name)


def test_legacy_preset_registry_matches_v2_ids():
    assert sorted(legacy.PRESETS) == sorted(LEGACY_PRESETS)
    assert sorted(shim.PRESETS) == sorted(LEGACY_PRESETS)
    assert sorted(legacy.PRESETS) == sorted(__import__("deembed").presets.preset_ids())


def test_legacy_preset_payload_keeps_v1_keys(se_preset):
    payload = legacy.generate_preset_se_dual_2xthru()
    assert {"id", "title", "description", "mode", "method", "total", "fix_l", "fix_r", "dut_ideal"} <= set(payload)
    assert payload["mode"] == "se"
    assert payload["method"] == "dual_2xthru"
    assert isinstance(payload["total"], rf.Network)
    assert payload["thru_2x_a"].nports == 2


def test_legacy_method_names_follow_v1_vocabulary():
    assert legacy.generate_preset_se_2xthru()["method"] == "2xthru"
    assert legacy.generate_preset_diff_2xthru()["method"] == "2xthru"
    assert legacy.generate_preset_se_file_based()["method"] == "file_based"


def test_dual_2xthru_recovers_ideal_dut(se_preset):
    payload = legacy.generate_preset_se_dual_2xthru()
    dut, fix_left, fix_right = legacy.dual_2xthru_deembed_2port(
        payload["total"], payload["thru_2x_a"], payload["thru_2x_b"]
    )
    assert dut.nports == 2
    assert fix_left.nports == 2 and fix_right.nports == 2
    np.testing.assert_allclose(dut.s, payload["dut_ideal"].s, rtol=1e-4, atol=1e-6)
    np.testing.assert_allclose(fix_left.s, payload["fix_l"].s, rtol=1e-6, atol=1e-9)


def test_dual_2xthru_4port_matches_engine(diff_preset):
    payload = legacy.generate_preset_diff_dual_2xthru()
    dut, _, _ = legacy.dual_2xthru_deembed_4port(payload["total"], payload["thru_2x_a"], payload["thru_2x_b"])
    np.testing.assert_allclose(dut.s, payload["dut_ideal"].s, rtol=1e-4, atol=1e-6)


def test_legacy_engine_results_match_v2_engine(se_preset, engine):
    """兼容层与 v2 引擎必须给出同一个 DUT（单一算法来源）。"""

    payload = legacy.generate_preset_se_dual_2xthru()
    legacy_dut, _, _ = legacy.dual_2xthru_deembed_2port(payload["total"], payload["thru_2x_a"], payload["thru_2x_b"])
    from deembed import DeembedRequest, NetworkTriplet

    triplet = NetworkTriplet(total=payload["total"], thru_a=payload["thru_2x_a"], thru_b=payload["thru_2x_b"])
    outcome = engine.run(DeembedRequest.from_triplet(triplet))
    np.testing.assert_allclose(legacy_dut.s, outcome.dut.s, rtol=1e-9, atol=1e-12)


def test_ieee370_legacy_wrapper_applies_corrections(se_preset):
    payload = legacy.generate_preset_se_asym_2xthru()
    plain, _, _ = legacy.ieee370_2xthru_deembed_2port(payload["total"], payload["thru_2x"])
    corrected, fix_l, fix_r = legacy.ieee370_2xthru_deembed_2port(
        payload["total"], payload["thru_2x"], delta_delay_ps_a=2.5, delta_loss_db_b=0.2
    )
    assert corrected.nports == 2
    assert not np.allclose(plain.s, corrected.s), "非对称修正应改变夹具与 DUT"
    assert not np.allclose(fix_l.s, fix_r.s)


def test_file_based_requires_fixture_files(diff_preset):
    from deembed import InvalidInputError

    payload = legacy.generate_preset_diff_dual_2xthru()
    with pytest.raises(InvalidInputError):
        legacy.file_based_deembed_4port(payload["total"])


def test_file_based_4port_supports_plts_mapping_where_v1_crashed(diff_preset):
    """v1 在 PLTS 映射下会抛 LinAlgError；v2 兼容层应正常返回。"""

    payload = legacy.generate_preset_diff_dual_2xthru()

    def to_plts_order(network):  # noqa: ANN001
        reordered = network.copy()
        reordered.renumber([0, 1, 2, 3], [0, 2, 1, 3])
        return reordered

    dut = legacy.file_based_deembed_4port(
        to_plts_order(payload["total"]),
        to_plts_order(payload["fix_l"]),
        to_plts_order(payload["fix_r"]),
        port_mapping="plts",
    )
    assert dut.nports == 4
    assert len(dut.f) == len(payload["total"].f)


def test_port_extension_wrapper_matches_settings():
    payload = legacy.generate_preset_se_dual_2xthru()
    plain = legacy.port_extension_deembed(payload["total"])
    np.testing.assert_allclose(plain.s, payload["total"].s, rtol=1e-12, atol=1e-15)  # v1：空参数即原样返回
    shifted = legacy.port_extension_deembed(payload["total"], delay_ps_left=20.0, delay_ps_right=10.0, loss_db_left=0.5)
    assert not np.allclose(plain.s, shifted.s)
    assert shifted.nports == payload["total"].nports


def test_analysis_helpers_keep_v1_shapes(diff_preset):
    payload = legacy.generate_preset_diff_dual_2xthru()
    network = payload["total"]

    mixed = legacy.compute_mixed_mode(network)
    assert set(mixed) == {"freq_ghz", "sdd", "scc", "scd", "sdc"}
    assert set(mixed["sdd"]["sdd21"]) == {"db", "phase"}
    assert len(mixed["freq_ghz"]) == len(network.f)

    quality = legacy.quality_check(network)
    assert set(quality) == {
        "status",
        "verdict",
        "max_singular_value",
        "passivity_pass",
        "passivity_margin_db",
        "reciprocity_error",
        "reciprocity_pass",
    }

    display = legacy.extract_network_display_data(network, max_points=50)
    assert display["nports"] == 4
    assert len(display["freq_ghz"]) <= 51
    assert set(display["params"]["S21"]) == {"mag_db", "phase_deg", "real", "imag", "group_delay_ps"}

    profile = legacy.compute_tdr_profile(network.f, network.s[:, 0, 0])
    assert set(profile) == {"time_ns", "step", "z_profile", "impulse"}
    assert len(profile["time_ns"]) == len(profile["z_profile"]) == len(profile["step"])


def test_auto_detect_returns_v1_strings():
    payload = legacy.generate_preset_diff_dual_2xthru()
    assert legacy.auto_detect_port_mapping(payload["total"]) == "sequential"
    assert legacy.auto_detect_port_mapping(payload["fix_l"]) == "sequential"


def test_matrix_helpers_round_trip(diff_preset):
    payload = legacy.generate_preset_diff_dual_2xthru()
    s = np.asarray(payload["total"].s)
    np.testing.assert_allclose(legacy.generalized_t2s(legacy.generalized_s2t(s)), s, rtol=1e-9, atol=1e-12)

    dut = legacy.deembed_t_matrix(payload["total"].s, payload["fix_l"].s, payload["fix_r"].s)
    assert dut.shape == s.shape


def test_adjust_fixture_delay_loss_is_positional_compatible(se_preset):
    payload = legacy.generate_preset_se_dual_2xthru()
    adjusted = legacy.adjust_fixture_delay_loss(payload["fix_l"], 5.0, 0.1)
    assert adjusted.nports == payload["fix_l"].nports
    np.testing.assert_allclose(adjusted.s[:, 0, 0], payload["fix_l"].s[:, 0, 0], rtol=1e-9, atol=1e-12)

    untouched = legacy.adjust_fixture_delay_loss(payload["fix_l"])
    np.testing.assert_allclose(untouched.s, payload["fix_l"].s, rtol=1e-12, atol=1e-15)


def test_align_frequencies_and_string_helpers(se_preset):
    payload = legacy.generate_preset_se_dual_2xthru()
    text = legacy.network_to_touchstone_str(payload["total"])
    parsed = legacy.load_network_from_str(text, "total.s2p")
    np.testing.assert_allclose(parsed.s, payload["total"].s, rtol=1e-6, atol=1e-9)

    aligned = legacy.align_frequencies([payload["total"], payload["thru_2x_a"]])
    assert len(aligned) == 2
    np.testing.assert_allclose(aligned[0].f, aligned[1].f, rtol=1e-12)
