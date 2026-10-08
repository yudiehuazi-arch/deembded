"""IEEE 370 Annex C 质量指标：无源性与互易性。"""

from __future__ import annotations

from typing import Final

import numpy as np
import skrf as rf

from .models import QualityReport

__all__ = ["QualityAnalyzer"]

_PASSIVITY_TOLERANCE: Final[float] = 1.005   # 允许 0.5% 浮点容限
_RECIPROCITY_TOLERANCE: Final[float] = 0.05  # |Sij - Sji| 残差阈值


class QualityAnalyzer:
    """计算去嵌结果的物理可信度指标。

    阈值可通过构造参数调整，便于未来接入更严格的验收标准（如因果性）。
    """

    def __init__(
        self,
        *,
        passivity_tolerance: float = _PASSIVITY_TOLERANCE,
        reciprocity_tolerance: float = _RECIPROCITY_TOLERANCE,
    ) -> None:
        self.passivity_tolerance = passivity_tolerance
        self.reciprocity_tolerance = reciprocity_tolerance

    def max_singular_values(self, network: rf.Network) -> np.ndarray:
        """逐频点最大奇异值 σmax(S)。"""

        s = np.asarray(network.s)
        return np.linalg.svd(s, compute_uv=False).max(axis=-1)

    def reciprocity_error(self, network: rf.Network) -> float:
        """max |Sij − Sji|。"""

        s = np.asarray(network.s)
        n_ports = s.shape[-1]
        error = 0.0
        for i in range(n_ports):
            for j in range(i + 1, n_ports):
                difference = float(np.max(np.abs(s[:, i, j] - s[:, j, i]))) if len(s) else 0.0
                error = max(error, difference)
        return error

    def analyze(self, network: rf.Network) -> QualityReport:
        """执行完整质量检查并给出中文结论。"""

        max_sv = float(np.max(self.max_singular_values(network))) if len(network.s) else 0.0
        passivity_pass = bool(max_sv <= self.passivity_tolerance)
        passivity_margin_db = float(20 * np.log10(max_sv)) if max_sv > 0 else 0.0

        recip_err = self.reciprocity_error(network)
        reciprocity_pass = bool(recip_err <= self.reciprocity_tolerance)

        if passivity_pass and reciprocity_pass:
            status = "PASS"
            verdict = "满足无源性与互易性，去嵌网络物理特性良好 (Physically Valid)"
        elif passivity_pass:
            status = "WARNING"
            verdict = "无源性合格，但互易性存在微弱偏差 (Reciprocity Warning)"
        else:
            status = "FAIL"
            verdict = f"无源性超标 (Max SV = {max_sv:.4f} > 1.0)，请检查夹具模型或频段设置"

        return QualityReport(
            status=status,
            verdict=verdict,
            max_singular_value=max_sv,
            passivity_pass=passivity_pass,
            passivity_margin_db=passivity_margin_db,
            reciprocity_error=float(recip_err),
            reciprocity_pass=reciprocity_pass,
        )


def quality_check(network: rf.Network) -> dict:
    """兼容旧调用的函数式入口。"""

    return QualityAnalyzer().analyze(network).to_payload()
