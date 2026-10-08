"""夹具修正：PLTS 非对称长度/损耗校正与端口延伸。"""

from __future__ import annotations

from typing import Final

import numpy as np
import skrf as rf

from ..errors import InvalidInputError
from ..models import DeembedSide, PortExtensionSettings

__all__ = ["adjust_fixture_delay_loss", "port_extension", "SPEED_OF_LIGHT"]

SPEED_OF_LIGHT: Final[float] = 3e8
_DEFAULT_VELOCITY_FACTOR: Final[float] = 0.7
_NOOP_TOLERANCE: Final[float] = 1e-4
_DB_PER_NEPER: Final[float] = 8.686


def adjust_fixture_delay_loss(
    fixture: rf.Network,
    *,
    delta_delay_ps: float = 0.0,
    delta_loss_db: float = 0.0,
    vp_eff: float = SPEED_OF_LIGHT * _DEFAULT_VELOCITY_FACTOR,
) -> rf.Network:
    """按 PLTS 方式平移参考面：正向偏移为加长夹具。

    仅调整“DUT 侧端口”（2 端口网络的端口 2；4 端口网络的端口 3/4），
    因为夹具的外侧端口始终与仪器参考面重合。
    """

    if abs(delta_delay_ps) < _NOOP_TOLERANCE and abs(delta_loss_db) < _NOOP_TOLERANCE:
        return fixture

    delta_tau = delta_delay_ps * 1e-12
    f = np.asarray(fixture.f, dtype=float)
    f0 = float(f[-1]) if f[-1] > 0 else 1.0

    phase_shift = np.exp(-1j * 2 * np.pi * f * delta_tau)
    if abs(delta_loss_db) > _NOOP_TOLERANCE:
        loss_factor = np.exp(-(delta_loss_db / _DB_PER_NEPER) * np.sqrt(np.maximum(f, 0) / f0))
    else:
        loss_factor = np.ones_like(f)
    factor = phase_shift * loss_factor

    s_adjusted = np.asarray(fixture.s).copy()
    if fixture.nports == 2:
        s_adjusted[:, 1, 0] *= factor
        s_adjusted[:, 0, 1] *= factor
        s_adjusted[:, 1, 1] *= factor**2
    elif fixture.nports == 4:
        for i in (0, 1):
            for j in (2, 3):
                s_adjusted[:, i, j] *= factor
                s_adjusted[:, j, i] *= factor
        for i in (2, 3):
            for j in (2, 3):
                s_adjusted[:, i, j] *= factor**2

    return rf.Network(frequency=fixture.frequency, s=s_adjusted, z0=fixture.z0)


def port_extension(
    total: rf.Network,
    settings: PortExtensionSettings,
    *,
    side: DeembedSide = DeembedSide.BOTH,
) -> rf.Network:
    """端口延伸去嵌：按频率相关的时延/损耗因子剥离夹具。

    ``delay_ps``/``loss_db`` 为“夹具造成的附加时延与损耗”，去嵌时按
    传输相位与幅度补偿回参考面。
    """

    frequency = np.asarray(total.f, dtype=float)
    f0 = float(frequency[-1]) if len(frequency) and frequency[-1] > 0 else 1.0

    left_active = side in (DeembedSide.BOTH, DeembedSide.LEFT)
    right_active = side in (DeembedSide.BOTH, DeembedSide.RIGHT)

    delay_left = settings.delay_ps_left * 1e-12 if left_active else 0.0
    delay_right = settings.delay_ps_right * 1e-12 if right_active else 0.0
    loss_left = settings.loss_db_left if left_active else 0.0
    loss_right = settings.loss_db_right if right_active else 0.0

    gamma_left = _propagation_factor(frequency, f0, delay_left, loss_left)
    gamma_right = _propagation_factor(frequency, f0, delay_right, loss_right)

    s_corrected = np.asarray(total.s).copy()
    nports = total.nports
    if nports == 2:
        s_corrected[:, 0, 0] *= gamma_left**2
        s_corrected[:, 1, 1] *= gamma_right**2
        s_corrected[:, 1, 0] *= gamma_left * gamma_right
        s_corrected[:, 0, 1] *= gamma_left * gamma_right
    elif nports == 4:
        for port in (0, 1):
            s_corrected[:, port, port] *= gamma_left**2
        for port in (2, 3):
            s_corrected[:, port, port] *= gamma_right**2
        for port_left in (0, 1):
            for port_right in (2, 3):
                s_corrected[:, port_left, port_right] *= gamma_left * gamma_right
                s_corrected[:, port_right, port_left] *= gamma_left * gamma_right
    else:  # pragma: no cover - 由上层校验端口数
        raise InvalidInputError("端口延伸仅支持 S2P 或 S4P 网络。")

    return rf.Network(frequency=total.frequency, s=s_corrected, z0=total.z0)


def _propagation_factor(frequency: np.ndarray, f0: float, delay_s: float, loss_db: float) -> np.ndarray:
    """单侧夹具的相位/幅度补偿因子。"""

    theta = 2 * np.pi * frequency * delay_s
    alpha = (loss_db / _DB_PER_NEPER) * np.sqrt(np.maximum(frequency, 0) / f0)
    return np.exp(alpha + 1j * theta)
