"""``backend.deembed_engine`` 兼容入口。

v1 的算法实现曾是这一个 1000+ 行的单文件；v2 已拆分为 :mod:`deembed`
内核（类 + 策略 + 报告对象）。为了不破坏历史脚本与旧示例：

* 函数名、参数顺序与返回结构保持不变；
* 实现只有一份——全部委托给 :mod:`deembed.legacy`，再下沉到 v2 内核。

新代码请直接使用 ``deembed`` 包的类接口（``DeembeddingEngine`` 等）。
"""

from __future__ import annotations

from deembed.legacy import (  # noqa: F401 - 有意重导出，保持 v1 导入路径可用
    load_network_from_str,
    network_to_touchstone_str,
    align_frequencies,
    generalized_s2t,
    generalized_t2s,
    uncoupled_lines_to_4port,
    deembed_t_matrix,
    file_based_deembed_2port,
    file_based_deembed_4port,
    adjust_fixture_delay_loss,
    ieee370_2xthru_deembed_2port,
    ieee370_2xthru_deembed_4port,
    dual_2xthru_deembed_2port,
    dual_2xthru_deembed_4port,
    port_extension_deembed,
    auto_detect_port_mapping,
    compute_mixed_mode,
    compute_tdr_profile,
    quality_check,
    extract_network_display_data,
    generate_preset_se_file_based,
    generate_preset_se_2xthru,
    generate_preset_diff_file_based,
    generate_preset_diff_2xthru,
    generate_preset_se_asym_file,
    generate_preset_se_asym_2xthru,
    generate_preset_diff_asym_file,
    generate_preset_diff_asym_2xthru,
    generate_preset_se_dual_2xthru,
    generate_preset_diff_dual_2xthru,
    PRESETS,
)

__all__ = [
    load_network_from_str,
    network_to_touchstone_str,
    align_frequencies,
    generalized_s2t,
    generalized_t2s,
    uncoupled_lines_to_4port,
    deembed_t_matrix,
    file_based_deembed_2port,
    file_based_deembed_4port,
    adjust_fixture_delay_loss,
    ieee370_2xthru_deembed_2port,
    ieee370_2xthru_deembed_4port,
    dual_2xthru_deembed_2port,
    dual_2xthru_deembed_4port,
    port_extension_deembed,
    auto_detect_port_mapping,
    compute_mixed_mode,
    compute_tdr_profile,
    quality_check,
    extract_network_display_data,
    generate_preset_se_file_based,
    generate_preset_se_2xthru,
    generate_preset_diff_file_based,
    generate_preset_diff_2xthru,
    generate_preset_se_asym_file,
    generate_preset_se_asym_2xthru,
    generate_preset_diff_asym_file,
    generate_preset_diff_asym_2xthru,
    generate_preset_se_dual_2xthru,
    generate_preset_diff_dual_2xthru,
    PRESETS,
]
