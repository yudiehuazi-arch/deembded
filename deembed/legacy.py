"""v1 兼容层：保留 ``deembed_engine.py`` 的函数式接口。

v2 的对外契约是类与领域模型（:class:`~deembed.engine.DeembeddingEngine`、
策略对象、报告对象）。为了让历史脚本与旧示例继续可用，本模块提供与 v1
**同名同签名**的函数，内部全部委托给 v2 实现，因此不存在第二份算法。

约定：

* 去嵌函数返回 ``rf.Network`` 或 ``(dut, fix_left, fix_right)``，与 v1 一致；
* ``auto_detect_port_mapping`` 返回字符串（``"sequential"`` / ``"plts"``）；
* ``compute_mixed_mode`` / ``quality_check`` / ``extract_network_display_data``
  / ``compute_tdr_profile`` 的历史字典结构保持不变（仅供旧脚本使用，
  新代码请直接使用 :class:`~deembed.mixed_mode.MixedModeConverter`、
  :class:`~deembed.metrics.QualityAnalyzer`、
  :class:`~deembed.reporting.NetworkPreviewBuilder`、
  :class:`~deembed.tdr.TdrAnalyzer`）。
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
import skrf as rf
from skrf.network import concat_ports

from .engine import DeembeddingEngine, shared_engine
from .fixtures.corrections import adjust_fixture_delay_loss as _adjust_fixture_delay_loss
from .frequency import FrequencyAligner
from .matrices import cascade_deembed, s_to_t, t_to_s
from .metrics import quality_check
from .mixed_mode import MixedModeConverter
from .models import (
    DeembedRequest,
    DeembedSide,
    FixtureCorrection,
    FixtureMethod,
    FixtureStandardSet,
    PortExtensionSettings,
    PortMapping,
)
from .port_mapping import auto_detect_port_mapping as _auto_detect_port_mapping
from .port_mapping import resolve_port_mapping
from .presets import get_preset
from .touchstone import network_from_text, network_to_text

__all__ = [
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
    "generate_preset_se_file_based",
    "generate_preset_se_2xthru",
    "generate_preset_diff_file_based",
    "generate_preset_diff_2xthru",
    "generate_preset_se_asym_file",
    "generate_preset_se_asym_2xthru",
    "generate_preset_diff_asym_file",
    "generate_preset_diff_asym_2xthru",
    "generate_preset_se_dual_2xthru",
    "generate_preset_diff_dual_2xthru",
    "PRESETS",
]

_DEFAULT_ENGINE: DeembeddingEngine = shared_engine()
_ALIGNER = FrequencyAligner()
_HAS_OLD_API_HINT = "v1 兼容接口：新代码请使用 deembed 包的类接口。"


# ---------------------------------------------------------------------------
# Touchstone / 频率 / 矩阵
# ---------------------------------------------------------------------------
def load_network_from_str(content: str, filename: str = "network.s2p") -> rf.Network:
    """从 Touchstone 文本解析网络（v1 名称）。"""

    return network_from_text(content, filename)


def network_to_touchstone_str(ntwk: rf.Network, form: str = "ri") -> str:
    """序列化为 Touchstone 文本（v1 名称）。"""

    return network_to_text(ntwk, form)


def align_frequencies(ntwks: Sequence[rf.Network]) -> list[rf.Network]:
    """把若干网络对齐到共同频率网格（v2 实现：取公共频段交集）。"""

    return _ALIGNER.align(list(ntwks))


def generalized_s2t(s_mat: np.ndarray) -> np.ndarray:
    """S → T 矩阵（支持任意偶数端口的分块定义）。"""

    return s_to_t(s_mat)


def generalized_t2s(t_mat: np.ndarray) -> np.ndarray:
    """T → S 矩阵。"""

    return t_to_s(t_mat)


def uncoupled_lines_to_4port(line_a: rf.Network, line_b: rf.Network) -> rf.Network:
    """两条互不耦合的 2 端口线 → 一个 4 端口夹具网络。"""

    aligned = align_frequencies([line_a, line_b])
    return concat_ports([aligned[0], aligned[1]], port_order="second")


def deembed_t_matrix(
    s_total: np.ndarray,
    s_left: np.ndarray | None = None,
    s_right: np.ndarray | None = None,
    side: str = "both",
) -> np.ndarray:
    """T 矩阵级联反演（v1 名称，返回 S 矩阵）。"""

    return cascade_deembed(s_total, s_left, s_right, side=DeembedSide.parse(side, field="去嵌侧"))


# ---------------------------------------------------------------------------
# 去嵌入口
# ---------------------------------------------------------------------------
def _run(
    total: rf.Network,
    *,
    method: FixtureMethod,
    side: str = "both",
    z0: float = 50.0,
    port_mapping: str | PortMapping = PortMapping.AUTO,
    thru_a: rf.Network | None = None,
    thru_b: rf.Network | None = None,
    fix_a: rf.Network | None = None,
    fix_b: rf.Network | None = None,
    correction_a: FixtureCorrection | None = None,
    correction_b: FixtureCorrection | None = None,
    port_extension: PortExtensionSettings | None = None,
):
    request = DeembedRequest(
        total=total,
        standards=FixtureStandardSet(thru_a=thru_a, thru_b=thru_b, fix_a=fix_a, fix_b=fix_b),
        side=DeembedSide.parse(side, field="去嵌侧"),
        port_mapping=PortMapping.parse(port_mapping, field="端口映射") if not isinstance(port_mapping, PortMapping) else port_mapping,
        reference_z0=float(z0),
        method=method,
        correction_a=correction_a or FixtureCorrection(),
        correction_b=correction_b or FixtureCorrection(),
        port_extension=port_extension,
    )
    return _DEFAULT_ENGINE.run(request)


def _result_tuple(outcome) -> tuple[rf.Network, rf.Network, rf.Network]:
    if outcome.fixtures is None:
        raise RuntimeError("该去嵌方法不产生 1X 夹具模型。")
    return outcome.dut, outcome.fixtures.left, outcome.fixtures.right


def file_based_deembed_2port(
    total: rf.Network,
    fix_l: rf.Network | None = None,
    fix_r: rf.Network | None = None,
    side: str = "both",
) -> rf.Network:
    """使用已知 1X 夹具文件做 2 端口去嵌。"""

    return _run(total, method=FixtureMethod.FIXTURE_FILES, side=side, fix_a=fix_l, fix_b=fix_r).dut


def file_based_deembed_4port(
    total: rf.Network,
    fix_l: rf.Network | None = None,
    fix_r: rf.Network | None = None,
    side: str = "both",
    port_mapping: str = "sequential",
) -> rf.Network:
    """使用已知 1X 夹具文件做 4 端口去嵌。"""

    return _run(
        total, method=FixtureMethod.FIXTURE_FILES, side=side, port_mapping=port_mapping, fix_a=fix_l, fix_b=fix_r
    ).dut


def adjust_fixture_delay_loss(
    fixture_net: rf.Network,
    delta_delay_ps: float = 0.0,
    delta_loss_db: float = 0.0,
    vp_eff: float = 3e8 * 0.7,
) -> rf.Network:
    """非对称夹具的长度/损耗修正（v1 位置参数签名）。"""

    return _adjust_fixture_delay_loss(
        fixture_net, delta_delay_ps=delta_delay_ps, delta_loss_db=delta_loss_db, vp_eff=vp_eff
    )


def dual_2xthru_deembed_2port(
    total: rf.Network,
    thru_2x_a: rf.Network,
    thru_2x_b: rf.Network,
    side: str = "both",
    z0: float = 50.0,
) -> tuple[rf.Network, rf.Network, rf.Network]:
    """独立双 2X Thru 去嵌（单端）。"""

    outcome = _run(total, method=FixtureMethod.DUAL_2X_THRU, side=side, z0=z0, thru_a=thru_2x_a, thru_b=thru_2x_b)
    return _result_tuple(outcome)


def dual_2xthru_deembed_4port(
    total: rf.Network,
    thru_2x_a: rf.Network,
    thru_2x_b: rf.Network,
    side: str = "both",
    z0: float = 50.0,
    port_mapping: str = "sequential",
) -> tuple[rf.Network, rf.Network, rf.Network]:
    """独立双 2X Thru 去嵌（差分 4 端口）。"""

    outcome = _run(
        total,
        method=FixtureMethod.DUAL_2X_THRU,
        side=side,
        z0=z0,
        port_mapping=port_mapping,
        thru_a=thru_2x_a,
        thru_b=thru_2x_b,
    )
    return _result_tuple(outcome)


def _single_2xthru(
    total: rf.Network,
    thru_2x: rf.Network,
    *,
    side: str,
    z0: float,
    port_mapping: str,
    delta_delay_ps_a: float,
    delta_delay_ps_b: float,
    delta_loss_db_a: float,
    delta_loss_db_b: float,
    match_a_ne_b: bool,
) -> tuple[rf.Network, rf.Network, rf.Network]:
    correction_a = FixtureCorrection(delay_ps=delta_delay_ps_a, loss_db=delta_loss_db_a)
    correction_b = correction_a if match_a_ne_b else FixtureCorrection(delay_ps=delta_delay_ps_b, loss_db=delta_loss_db_b)
    outcome = _run(
        total,
        method=FixtureMethod.SINGLE_2X_THRU,
        side=side,
        z0=z0,
        port_mapping=port_mapping,
        thru_a=thru_2x,
        correction_a=correction_a,
        correction_b=correction_b,
    )
    return _result_tuple(outcome)


def ieee370_2xthru_deembed_2port(
    total: rf.Network,
    thru_2x: rf.Network,
    side: str = "both",
    z0: float = 50.0,
    delta_delay_ps_a: float = 0.0,
    delta_delay_ps_b: float = 0.0,
    delta_loss_db_a: float = 0.0,
    delta_loss_db_b: float = 0.0,
    match_a_ne_b: bool = False,
) -> tuple[rf.Network, rf.Network, rf.Network]:
    """单条 2X Thru 劈半去嵌（单端，支持非对称修正）。"""

    return _single_2xthru(
        total,
        thru_2x,
        side=side,
        z0=z0,
        port_mapping="sequential",
        delta_delay_ps_a=delta_delay_ps_a,
        delta_delay_ps_b=delta_delay_ps_b,
        delta_loss_db_a=delta_loss_db_a,
        delta_loss_db_b=delta_loss_db_b,
        match_a_ne_b=match_a_ne_b,
    )


def ieee370_2xthru_deembed_4port(
    total: rf.Network,
    thru_2x: rf.Network,
    side: str = "both",
    z0: float = 50.0,
    port_mapping: str = "sequential",
    delta_delay_ps_a: float = 0.0,
    delta_delay_ps_b: float = 0.0,
    delta_loss_db_a: float = 0.0,
    delta_loss_db_b: float = 0.0,
    match_a_ne_b: bool = False,
) -> tuple[rf.Network, rf.Network, rf.Network]:
    """单条 2X Thru 混合模劈半去嵌（差分 4 端口）。"""

    return _single_2xthru(
        total,
        thru_2x,
        side=side,
        z0=z0,
        port_mapping=port_mapping,
        delta_delay_ps_a=delta_delay_ps_a,
        delta_delay_ps_b=delta_delay_ps_b,
        delta_loss_db_a=delta_loss_db_a,
        delta_loss_db_b=delta_loss_db_b,
        match_a_ne_b=match_a_ne_b,
    )


def port_extension_deembed(
    total: rf.Network,
    delay_ps_left: float = 0.0,
    delay_ps_right: float = 0.0,
    loss_db_left: float = 0.0,
    loss_db_right: float = 0.0,
    side: str = "both",
) -> rf.Network:
    """端口延伸（电气延时/损耗）去嵌。

    与 v1 一致：四个参数全为 0 时返回原网络（v2 的策略会拒绝空请求，
    兼容层在此保留旧行为）。
    """

    if max(abs(delay_ps_left), abs(delay_ps_right), abs(loss_db_left), abs(loss_db_right)) < 1e-12:
        return total
    settings = PortExtensionSettings(
        delay_ps_left=delay_ps_left,
        delay_ps_right=delay_ps_right,
        loss_db_left=loss_db_left,
        loss_db_right=loss_db_right,
    )
    return _run(total, method=FixtureMethod.PORT_EXTENSION, side=side, port_extension=settings).dut


# ---------------------------------------------------------------------------
# 分析辅助
# ---------------------------------------------------------------------------
def auto_detect_port_mapping(ntwk: rf.Network) -> str:
    """自动识别 4 端口线序，返回 ``"sequential"`` 或 ``"plts"``。"""

    return _auto_detect_port_mapping(ntwk).value


def compute_mixed_mode(ntwk_4port: rf.Network, port_mapping: str = "sequential") -> dict:
    """混合模 S 参数（dB / 相位）报告，键名与 v1 一致。"""

    mapping = resolve_port_mapping(ntwk_4port, port_mapping)
    return MixedModeConverter(mapping).full_report(ntwk_4port)


def compute_tdr_profile(
    freq_hz: np.ndarray,
    s_param: np.ndarray,
    z0: float = 50.0,
    num_pts: int = 1024,
) -> dict[str, list[float]]:
    """v1 的 TDR 阶跃阻抗算法（保留旧输出键：time_ns/step/z_profile/impulse）。"""

    f = np.asarray(freq_hz, dtype=float)
    s = np.asarray(s_param, dtype=complex)

    df = float(np.median(np.diff(f)))
    f_max = float(f[-1])
    f_uniform = np.arange(0, f_max + df / 2, df)
    s_real = np.interp(f_uniform, f, np.real(s))
    s_imag = np.interp(f_uniform, f, np.imag(s))
    s_imag[0] = 0.0  # 反射系数的 DC 虚部为 0
    s_uniform = s_real + 1j * s_imag

    count = len(s_uniform)
    window = np.ones(count)
    window_len = max(int(0.2 * count), 4)
    window[-window_len:] = 0.5 * (1 + np.cos(np.linspace(0, np.pi, window_len)))
    spectrum = np.zeros(max(num_pts, 2 * (count - 1)), dtype=complex)
    spectrum[:count] = s_uniform * window
    spectrum[-count + 1 :] = np.conj(spectrum[1:count][::-1])

    impulse = np.fft.ifft(spectrum).real
    dt = 1.0 / (len(spectrum) * df)
    time_s = np.arange(len(spectrum)) * dt
    step = np.cumsum(impulse)

    if np.max(np.abs(step)) > 0:
        dc_value = float(np.real(s_uniform[0]))
        step_end = step[-1] if abs(step[-1]) > 1e-4 else 1.0
        if abs(dc_value) > 1e-2:
            step = step * (dc_value / step_end)

    rho = np.clip(step, -0.98, 0.98)
    impedance = z0 * (1.0 + rho) / (1.0 - rho)
    view_len = min(count * 2, len(time_s))
    return {
        "time_ns": (time_s[:view_len] * 1e9).tolist(),
        "step": step[:view_len].tolist(),
        "z_profile": impedance[:view_len].tolist(),
        "impulse": impulse[:view_len].tolist(),
    }


def extract_network_display_data(ntwk: rf.Network, max_points: int = 401) -> dict:
    """S 参数幅相 / 群时延 / Smith 坐标（v1 键名：freq_ghz + params）。"""

    frequency_ghz = ntwk.f / 1e9
    nports = int(ntwk.nports)
    if len(frequency_ghz) > max_points:
        step = len(frequency_ghz) // max_points + 1
        indices = list(range(0, len(frequency_ghz), step))
        if indices[-1] != len(frequency_ghz) - 1:
            indices.append(len(frequency_ghz) - 1)
    else:
        indices = list(range(len(frequency_ghz)))

    f_sub = frequency_ghz[indices]
    s_sub = ntwk.s[indices]
    params: dict[str, dict[str, list[float]]] = {}
    for i in range(nports):
        for j in range(nports):
            s_ij = s_sub[:, i, j]
            if i != j:
                unwrapped = np.unwrap(np.angle(ntwk.s[:, i, j]))
                group_delay = -np.diff(unwrapped) / (2 * np.pi * np.diff(ntwk.f)) * 1e12
                group_delay_sub = np.interp(f_sub, ntwk.f[:-1] / 1e9, group_delay)
            else:
                group_delay_sub = np.zeros_like(f_sub)
            params[f"S{i + 1}{j + 1}"] = {
                "mag_db": (20 * np.log10(np.maximum(np.abs(s_ij), 1e-12))).tolist(),
                "phase_deg": np.angle(s_ij, deg=True).tolist(),
                "real": s_ij.real.tolist(),
                "imag": s_ij.imag.tolist(),
                "group_delay_ps": group_delay_sub.tolist(),
            }
    return {"freq_ghz": f_sub.tolist(), "nports": nports, "params": params}


# ---------------------------------------------------------------------------
# 预设（演示数据）
# ---------------------------------------------------------------------------
#: v2 方法标识 → v1 方法标识（历史前端曾使用后者）
_LEGACY_METHOD_NAMES: dict[str, str] = {
    FixtureMethod.DUAL_2X_THRU.value: "dual_2xthru",
    FixtureMethod.SINGLE_2X_THRU.value: "2xthru",
    FixtureMethod.FIXTURE_FILES.value: "file_based",
    FixtureMethod.PORT_EXTENSION.value: "port_extension",
}


def _preset_factory(preset_id: str):
    def generate() -> dict[str, Any]:
        payload = get_preset(preset_id).to_dict()
        payload["method"] = _LEGACY_METHOD_NAMES.get(payload["method"], payload["method"])
        return payload

    generate.__name__ = f"generate_preset_{preset_id}"
    generate.__doc__ = f"内置预设 {preset_id}（v1 字典结构）。{_HAS_OLD_API_HINT}"
    return generate


generate_preset_se_file_based = _preset_factory("se_file_based")
generate_preset_se_2xthru = _preset_factory("se_2xthru")
generate_preset_diff_file_based = _preset_factory("diff_file_based")
generate_preset_diff_2xthru = _preset_factory("diff_2xthru")
generate_preset_se_asym_file = _preset_factory("se_asym_file")
generate_preset_se_asym_2xthru = _preset_factory("se_asym_2xthru")
generate_preset_diff_asym_file = _preset_factory("diff_asym_file")
generate_preset_diff_asym_2xthru = _preset_factory("diff_asym_2xthru")
generate_preset_se_dual_2xthru = _preset_factory("se_dual_2xthru")
generate_preset_diff_dual_2xthru = _preset_factory("diff_dual_2xthru")

#: v1 的预设注册表：id → 生成函数（返回字典）
PRESETS: dict[str, Any] = {
    "se_dual_2xthru": generate_preset_se_dual_2xthru,
    "diff_dual_2xthru": generate_preset_diff_dual_2xthru,
    "se_asym_2xthru": generate_preset_se_asym_2xthru,
    "diff_asym_2xthru": generate_preset_diff_asym_2xthru,
    "se_asym_file": generate_preset_se_asym_file,
    "diff_asym_file": generate_preset_diff_asym_file,
    "se_2xthru": generate_preset_se_2xthru,
    "diff_2xthru": generate_preset_diff_2xthru,
    "se_file_based": generate_preset_se_file_based,
    "diff_file_based": generate_preset_diff_file_based,
}
