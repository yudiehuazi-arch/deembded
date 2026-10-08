"""时域反射（TDR）阶跃阻抗变换。

流程（对应 ``docs/DEEMBED_GUIDE.md`` 第 5 章）：
均匀频率网格 → DC 外推 → 可选上升时间高斯低通 → 加窗 → IFFT 阶跃响应
→ ``Z(t) = Z0·(1+ρ)/(1−ρ)``。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Mapping

import numpy as np
import skrf as rf

from .errors import ComputationError, InvalidInputError
from .frequency import renormalize
from .models import DcMethod, PortMapping, TdrWindow
from .port_mapping import apply_port_mapping

__all__ = ["TdrSettings", "TdrTrace", "TdrStack", "TdrAnalyzer"]

_MAX_UNIFORM_POINTS: Final[int] = 32768
_MAX_DISPLAY_POINTS: Final[int] = 6000
_REFERENCE_Z0_MAX: Final[float] = 1000.0
_RISE_TIME_MAX_PS: Final[float] = 10000.0
_MIN_FREQUENCY_POINTS: Final[int] = 8
_GAUSSIAN_RISE_TIME_CONSTANT: Final[float] = 3.005

_WINDOW_MAP: Final[dict[TdrWindow, str | None]] = {
    TdrWindow.HAMMING: "hamming",
    TdrWindow.HANN: "hann",
    TdrWindow.BLACKMAN: "blackman",
    TdrWindow.NONE: None,
}


@dataclass(frozen=True)
class TdrSettings:
    """一次 TDR 变换的全部可选设置。"""

    port: int = 1
    window: TdrWindow = TdrWindow.HAMMING
    dc_method: DcMethod = DcMethod.LINEAR
    rise_time_ps: float = 0.0

    @classmethod
    def from_form(
        cls,
        *,
        port: int | str = 1,
        window: str = "hamming",
        dc_method: str = "linear",
        rise_time_ps: float | str = 0.0,
    ) -> "TdrSettings":
        try:
            parsed_port = int(port)
        except (TypeError, ValueError) as exc:
            raise InvalidInputError("TDR 端口必须为 1 或 2。") from exc
        try:
            parsed_rise = float(rise_time_ps)
        except (TypeError, ValueError) as exc:
            raise InvalidInputError("TDR 上升时间须为 0–10000 ps。") from exc
        return cls(
            port=parsed_port,
            window=TdrWindow.parse(window, field="TDR 窗函数"),
            dc_method=DcMethod.parse(dc_method, field="TDR 低频外推"),
            rise_time_ps=parsed_rise,
        )

    @property
    def skrf_window(self) -> str | None:
        return _WINDOW_MAP[self.window]

    def summary(self) -> dict[str, Any]:
        """回显给前端的设置字段。"""

        return {"window": self.window.value, "dc_method": self.dc_method.value, "rise_time_ps": float(self.rise_time_ps)}


@dataclass(frozen=True)
class TdrTrace:
    """单条网络的阶跃阻抗曲线。"""

    time_ns: list[float]
    impedance_ohm: list[float | None]
    parameter: str
    reference_ohm: float
    sample_step_ps: float

    def to_payload(self) -> dict[str, Any]:
        return {
            "time_ns": self.time_ns,
            "impedance_ohm": self.impedance_ohm,
            "parameter": self.parameter,
            "reference_ohm": self.reference_ohm,
            "sample_step_ps": self.sample_step_ps,
        }


@dataclass(frozen=True)
class TdrStack:
    """多条网络共享同一时间轴的 TDR 对比结果。"""

    traces: Mapping[str, TdrTrace]

    def to_payload(self, *, extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
        first = next(iter(self.traces.values()), None)
        payload: dict[str, Any] = {
            "time_ns": first.time_ns if first else [],
            "series": {key: trace.impedance_ohm for key, trace in self.traces.items()},
            "sample_step_ps": first.sample_step_ps if first else 0.0,
            "reference_ohm": first.reference_ohm if first else 0.0,
            "parameter": first.parameter if first else "",
        }
        if extra:
            payload.update(extra)
        return payload


class TdrAnalyzer:
    """阶跃阻抗变换器。

    与原实现保持一致的数值细节：均匀化采用中值频率步进、低频段线性外推
    或首点延拓、可选高斯上升时间整形、skrf 的加窗阶跃响应。
    """

    def __init__(self, *, max_uniform_points: int = _MAX_UNIFORM_POINTS, max_display_points: int = _MAX_DISPLAY_POINTS) -> None:
        self.max_uniform_points = max_uniform_points
        self.max_display_points = max_display_points

    # ---------------------------------------------------------------- 校验
    def validate(self, settings: TdrSettings, reference_z0: float) -> None:
        if settings.port not in (1, 2):
            raise InvalidInputError("TDR 端口必须为 1 或 2。")
        if not np.isfinite(reference_z0) or reference_z0 <= 0 or reference_z0 > _REFERENCE_Z0_MAX:
            raise InvalidInputError("TDR 单端参考阻抗须为 0–1000 Ω 范围内的有限正数。")
        if not np.isfinite(settings.rise_time_ps) or settings.rise_time_ps < 0 or settings.rise_time_ps > _RISE_TIME_MAX_PS:
            raise InvalidInputError("TDR 上升时间须为 0–10000 ps。")

    # ---------------------------------------------------------------- 反射
    def reflection(
        self,
        network: rf.Network,
        *,
        port: int,
        port_mapping: PortMapping,
        reference_z0: float,
    ) -> tuple[np.ndarray, str, float]:
        """返回（反射系数 γ, 参数名, 参考阻抗）。

        S2P 使用单端 S11/S22；S4P 先按端口映射重排再做混合模变换，
        取 SDD11/SDD22，差模参考阻抗为 2·Z0。
        """

        work = renormalize(network, reference_z0)
        if work.nports == 2:
            index = port - 1
            return np.asarray(work.s[:, index, index], dtype=complex), f"S{port}{port}", float(reference_z0)
        if work.nports != 4:
            raise InvalidInputError("TDR 目前仅支持 S2P 或 S4P 网络。")
        work = apply_port_mapping(work, port_mapping)
        work.se2gmm(p=2)
        index = port - 1
        return np.asarray(work.s[:, index, index], dtype=complex), f"SDD{port}{port}", float(2.0 * reference_z0)

    # ------------------------------------------------------------ 单条变换
    def step_impedance(
        self,
        network: rf.Network,
        *,
        settings: TdrSettings,
        port_mapping: PortMapping,
        reference_z0: float = 50.0,
    ) -> TdrTrace:
        self.validate(settings, reference_z0)

        frequency = np.asarray(network.f, dtype=float)
        if len(frequency) < _MIN_FREQUENCY_POINTS or not np.all(np.isfinite(frequency)) or np.any(np.diff(frequency) <= 0):
            raise InvalidInputError("TDR 需要至少 8 个严格递增的有效频率点。")

        gamma, parameter, reference_ohm = self.reflection(
            network, port=settings.port, port_mapping=port_mapping, reference_z0=float(reference_z0)
        )
        if not np.all(np.isfinite(gamma.real)) or not np.all(np.isfinite(gamma.imag)):
            raise ComputationError(f"{parameter} 包含无效复数数据，无法生成 TDR。")

        f_max = float(frequency[-1])
        median_df = float(np.median(np.diff(frequency)))
        if f_max <= 0 or median_df <= 0:
            raise InvalidInputError("TDR 频率范围或频率步进无效。")

        points = int(np.clip(round(f_max / median_df) + 1, 16, self.max_uniform_points))
        uniform_f = np.linspace(0.0, f_max, points, dtype=float)
        uniform_gamma = np.interp(uniform_f, frequency, gamma.real) + 1j * np.interp(uniform_f, frequency, gamma.imag)
        self._apply_dc_extrapolation(uniform_gamma, uniform_f, frequency, gamma, settings.dc_method)
        self._apply_rise_time(uniform_gamma, uniform_f, settings.rise_time_ps)

        one_port = rf.Network(
            frequency=rf.Frequency.from_f(uniform_f, unit="hz"),
            s=uniform_gamma[:, None, None],
            z0=float(reference_z0),
        )
        try:
            time_s, gamma_step = one_port.step_response(window=settings.skrf_window)
        except Exception as exc:  # noqa: BLE001 - 转成领域错误
            raise ComputationError(f"TDR 时域变换失败：{type(exc).__name__}: {exc}") from exc

        gamma_step = np.asarray(gamma_step).reshape(len(time_s), -1)[:, 0]
        time_s = np.asarray(time_s, dtype=float)
        impedance = self._impedance_profile(gamma_step, reference_ohm)

        positive = np.flatnonzero(time_s >= 0.0)
        if not len(positive):
            raise ComputationError("TDR 变换未生成非负时间数据。")
        if len(positive) > self.max_display_points:
            positions = np.linspace(0, len(positive) - 1, self.max_display_points).round().astype(int)
            positive = positive[positions]

        plotted_time = time_s[positive]
        plotted_impedance = impedance[positive]
        native_step_ps = float((time_s[1] - time_s[0]) * 1e12) if len(time_s) > 1 else 0.0
        return TdrTrace(
            time_ns=(plotted_time * 1e9).astype(float).tolist(),
            impedance_ohm=[float(value) if np.isfinite(value) else None for value in plotted_impedance],
            parameter=parameter,
            reference_ohm=reference_ohm,
            sample_step_ps=native_step_ps,
        )

    # ------------------------------------------------------------ 多条变换
    def stack(
        self,
        networks: Mapping[str, rf.Network],
        *,
        settings: TdrSettings,
        port_mapping: PortMapping,
        reference_z0: float = 50.0,
    ) -> TdrStack:
        traces: dict[str, TdrTrace] = {}
        for key, network in networks.items():
            traces[key] = self.step_impedance(
                network, settings=settings, port_mapping=port_mapping, reference_z0=reference_z0
            )
        return TdrStack(traces=traces)

    # ---------------------------------------------------------------- 内部
    @staticmethod
    def _apply_dc_extrapolation(
        uniform_gamma: np.ndarray,
        uniform_f: np.ndarray,
        frequency: np.ndarray,
        gamma: np.ndarray,
        dc_method: DcMethod,
    ) -> None:
        """补齐未测量的 DC → 首个频点区间。"""

        if frequency[0] > 0:
            if dc_method is DcMethod.LINEAR and len(frequency) >= 2:
                slope = (gamma[1] - gamma[0]) / (frequency[1] - frequency[0])
                gamma_dc = float(np.real(gamma[0] - frequency[0] * slope))
            else:
                gamma_dc = float(np.real(gamma[0]))
            low = uniform_f < frequency[0]
            ratio = np.clip(uniform_f[low] / frequency[0], 0.0, 1.0)
            uniform_gamma[low] = gamma_dc + (gamma[0] - gamma_dc) * ratio
        else:
            uniform_gamma[0] = float(np.real(gamma[0]))

    @staticmethod
    def _apply_rise_time(uniform_gamma: np.ndarray, uniform_f: np.ndarray, rise_time_ps: float) -> None:
        rise_time_s = float(rise_time_ps) * 1e-12
        if rise_time_s > 0:
            uniform_gamma *= np.exp(-_GAUSSIAN_RISE_TIME_CONSTANT * np.square(uniform_f * rise_time_s))

    @staticmethod
    def _impedance_profile(gamma_step: np.ndarray, reference_ohm: float) -> np.ndarray:
        denominator = 1.0 - gamma_step
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            impedance = reference_ohm * (1.0 + gamma_step) / denominator
        return np.real(impedance)
