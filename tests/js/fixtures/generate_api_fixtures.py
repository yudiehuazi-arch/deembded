"""生成前端测试所需的真实 API 响应样本。

运行方式（仓库根目录）::

    python3 tests/js/fixtures/generate_api_fixtures.py

流程：用内置差分预设 ``diff_dual_2xthru`` 走完整 HTTP 路径
``/api/inspect`` → ``/api/deembed`` → ``/api/tdr/input`` → ``/api/tdr/result``，
并把响应写入本目录的 JSON 文件（前端 jsdom 集成测试以此为 fetch 桩）。

为控制仓库体积，脚本只做等比抽点（保持首尾与曲线形状），
字段结构、键名与真实接口完全一致。
"""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:  # 允许直接以脚本方式运行
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend.config import Settings  # noqa: E402
from backend.main import create_app  # noqa: E402
from deembed import network_to_text, presets  # noqa: E402

FIXTURES_DIR = pathlib.Path(__file__).parent

#: 抽点后保留的频点 / 时间点数量
CHART_POINTS = 48
TDR_POINTS = 96


def _upload(name: str, network: Any) -> tuple[str, bytes, str]:
    return (name, network_to_text(network).encode("utf-8"), "text/plain")


def _thin(values: list[Any], limit: int) -> list[Any]:
    """等比抽点：保留首尾点，其余均匀取样。"""

    if len(values) <= limit:
        return values
    step = (len(values) - 1) / (limit - 1)
    return [values[round(index * step)] for index in range(limit)]


def _round(values: list[Any], digits: int = 4) -> list[Any]:
    return [None if value is None else round(float(value), digits) for value in values]


def _thin_chart(payload: dict[str, Any]) -> dict[str, Any]:
    chart = payload.get("chart") or {}
    frequencies = chart.get("freq_ghz") or []
    kept = _thin(frequencies, CHART_POINTS)
    payload["chart"] = {
        "freq_ghz": _round(kept, 6),
        "series": {
            parameter: {network: _round(_thin(values, CHART_POINTS)) for network, values in networks.items()}
            for parameter, networks in (chart.get("series") or {}).items()
        },
    }
    return payload


def _thin_tdr(payload: dict[str, Any]) -> dict[str, Any]:
    payload["time_ns"] = _round(_thin(payload.get("time_ns") or [], TDR_POINTS), 6)
    if "series" in payload:
        payload["series"] = {key: _round(_thin(values, TDR_POINTS)) for key, values in payload["series"].items()}
    if "impedance_ohm" in payload:
        payload["impedance_ohm"] = _round(_thin(payload["impedance_ohm"], TDR_POINTS))
    return payload


def _thin_payload(payload: dict[str, Any], key: str) -> dict[str, Any]:
    """对带 freq_ghz + series 的预览对象等比抽点。"""

    frequencies = payload.get(key) or payload.get("freq_ghz") or []
    thinned = _round(_thin(frequencies, CHART_POINTS), 6)
    payload["freq_ghz"] = thinned
    payload["series"] = {
        parameter: _round(_thin(values, CHART_POINTS)) for parameter, values in (payload.get("series") or {}).items()
    }
    payload.pop(key, None) if key != "freq_ghz" else None
    return payload


def _thin_inspection(payload: dict[str, Any]) -> dict[str, Any]:
    payload["file_previews"] = {
        slot: _thin_payload(preview, "freq_ghz") for slot, preview in (payload.get("file_previews") or {}).items()
    }
    return payload


def main() -> None:
    preset = presets.get_preset("diff_dual_2xthru")
    triplet = preset.to_triplet()
    client = TestClient(create_app(settings=Settings(max_upload_bytes=8 * 1024 * 1024)))

    files = {
        "total": _upload("total.s4p", triplet.total),
        "thru_a": _upload("thru_a.s4p", triplet.thru_a),
        "thru_b": _upload("thru_b.s4p", triplet.thru_b),
    }
    inspection = client.post("/api/inspect", files=files, data={"port_mapping": "auto"}).json()
    token = inspection["inspection_token"]

    deembed = client.post(
        "/api/deembed",
        data={"inspection_token": token, "side": "both", "port_mapping": "auto", "reference_z0": "50"},
    ).json()

    tdr_common = {
        "inspection_token": token,
        "port": "1",
        "port_mapping": "auto",
        "reference_z0": "50",
        "window": "hamming",
        "dc_method": "linear",
        "rise_time_ps": "0",
    }
    tdr_input = client.post("/api/tdr/input", data={**tdr_common, "slot": "all"}).json()
    tdr_result = client.post("/api/tdr/result", data={**tdr_common, "result_token": deembed["result_token"]}).json()

    fixtures: dict[str, dict[str, Any]] = {
        "inspect.json": _thin_inspection(inspection),
        "deembed.json": _thin_chart(deembed),
        "tdr_input.json": _thin_tdr(tdr_input),
        "tdr_result.json": _thin_tdr(tdr_result),
    }
    for name, payload in fixtures.items():
        path = FIXTURES_DIR / name
        path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"{name}: {path.stat().st_size / 1024:.1f} KiB")


if __name__ == "__main__":
    main()
