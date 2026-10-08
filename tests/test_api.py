"""HTTP 接口契约测试（字段名/状态码/错误语义）。"""

from __future__ import annotations

import numpy as np
import pytest
import skrf as rf
from fastapi.testclient import TestClient

from deembed import network_from_text, network_to_text


def _inspect(client: TestClient, preset, upload_factory, port_mapping: str = "auto"):  # noqa: ANN001
    files = {
        "total": upload_factory(preset.total, "Total.s2p" if preset.nports == 2 else "Total.s4p"),
        "thru_a": upload_factory(preset.thru_2x_a, "ThruA.s2p" if preset.nports == 2 else "ThruA.s4p"),
        "thru_b": upload_factory(preset.thru_2x_b, "ThruB.s2p" if preset.nports == 2 else "ThruB.s4p"),
    }
    return client.post("/api/inspect", files=files, data={"port_mapping": port_mapping})


def test_health_reports_methods(client: TestClient) -> None:
    payload = client.get("/api/health").json()
    assert payload["status"] == "ok"
    assert {item["method"] for item in payload["methods"]} == {
        "dual_2xthru",
        "single_2xthru",
        "fixture_files",
        "port_extension",
    }
    assert payload["version"]


def test_index_page_is_served(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "RF De-embedding Workbench" in response.text
    assert response.headers["cache-control"].startswith("no-store")


def test_inspect_returns_mapping_and_previews(client: TestClient, se_preset, upload_factory) -> None:  # noqa: ANN001
    response = _inspect(client, se_preset, upload_factory)
    assert response.status_code == 200
    payload = response.json()

    assert payload["success"] is True
    assert payload["nports"] == 2
    assert payload["detected_mapping"] == "single-ended"
    assert payload["mapping_label"] == "单端双端口"
    assert payload["points"] == 269
    assert set(payload["file_previews"]) == {"total", "thru_a", "thru_b"}
    assert payload["fixture_statistics"] is None
    assert payload["inspection_token"]


def test_inspect_diff_network_reports_fixture_statistics(client: TestClient, diff_preset, upload_factory) -> None:  # noqa: ANN001
    response = _inspect(client, diff_preset, upload_factory, port_mapping="auto")
    payload = response.json()
    assert payload["nports"] == 4
    assert payload["detected_mapping"] in {"sequential", "plts"}
    statistics = payload["fixture_statistics"]
    assert set(statistics) == {"thru_a", "thru_b"}
    assert len(statistics["thru_a"]) == 4
    assert {"label", "target_db", "points_ghz", "ranges_ghz"} == set(statistics["thru_a"][0])
    preview_series = payload["file_previews"]["thru_a"]["series"]
    assert {"SDD21", "SCD21", "S11"} <= set(preview_series)


def test_inspect_rejects_invalid_mapping(client: TestClient, se_preset, upload_factory) -> None:  # noqa: ANN001
    response = _inspect(client, se_preset, upload_factory, port_mapping="banana")
    assert response.status_code == 400
    assert response.json()["detail"] == "S4P 端口映射设置无效。"


def test_inspect_rejects_missing_files(client: TestClient) -> None:
    response = client.post("/api/inspect", data={"port_mapping": "auto"})
    assert response.status_code == 410


def test_inspect_rejects_port_count_mismatch(client: TestClient, se_preset, diff_preset, upload_factory) -> None:  # noqa: ANN001
    files = {
        "total": upload_factory(se_preset.total, "Total.s2p"),
        "thru_a": upload_factory(diff_preset.thru_2x_a, "ThruA.s4p"),
        "thru_b": upload_factory(se_preset.thru_2x_b, "ThruB.s2p"),
    }
    response = client.post("/api/inspect", files=files, data={"port_mapping": "auto"})
    assert response.status_code == 400
    assert "端口数必须一致" in response.json()["detail"]


def test_inspect_rejects_empty_and_garbage_files(client: TestClient) -> None:
    empty = client.post(
        "/api/inspect",
        files={"total": ("Total.s2p", b"", "text/plain"), "thru_a": ("A.s2p", b"", "text/plain"), "thru_b": ("B.s2p", b"", "text/plain")},
        data={"port_mapping": "auto"},
    )
    assert empty.status_code == 400
    assert "文件为空" in empty.json()["detail"]

    garbage = client.post(
        "/api/inspect",
        files={
            "total": ("Total.s2p", b"\xff\xfe\x00\x01", "text/plain"),
            "thru_a": ("A.s2p", b"\xff\xfe\x00\x01", "text/plain"),
            "thru_b": ("B.s2p", b"\xff\xfe\x00\x01", "text/plain"),
        },
        data={"port_mapping": "auto"},
    )
    assert garbage.status_code == 400


def test_deembed_with_inspection_token(client: TestClient, se_preset, upload_factory) -> None:  # noqa: ANN001
    token = _inspect(client, se_preset, upload_factory).json()["inspection_token"]
    response = client.post(
        "/api/deembed",
        data={"inspection_token": token, "side": "both", "port_mapping": "auto", "reference_z0": "50"},
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["success"] is True
    assert payload["topology"] == "单端 S2P"
    assert payload["port_mapping"] is None  # S2P 不返回映射
    assert payload["left_ports"] == ["P1"]
    assert payload["right_ports"] == ["P2"]
    assert payload["quality"]["status"] == "PASS"
    assert payload["nports"] == 2
    assert set(payload["chart"]["network_keys"]) == {"total", "dut", "fix_a", "fix_b", "thru_a", "thru_b"}
    assert {"S11", "S21"} <= set(payload["chart"]["series"])
    assert payload["result_token"]

    download = client.get(f"/api/download/{payload['result_token']}/dut")
    assert download.status_code == 200
    assert 'filename="DUT_deembedded.s2p"' in download.headers["content-disposition"]
    restored = network_from_text(download.text, "DUT_deembedded.s2p")
    assert restored.nports == 2
    assert len(restored.f) == payload["points"]


def test_deembed_rejects_expired_token(client: TestClient) -> None:
    response = client.post(
        "/api/deembed",
        data={"inspection_token": "does-not-exist", "side": "both", "port_mapping": "auto", "reference_z0": "50"},
    )
    assert response.status_code == 410


def test_deembed_validates_inputs(client: TestClient, se_preset, upload_factory) -> None:  # noqa: ANN001
    files = {
        "total": upload_factory(se_preset.total, "Total.s2p"),
        "thru_a": upload_factory(se_preset.thru_2x_a, "ThruA.s2p"),
        "thru_b": upload_factory(se_preset.thru_2x_b, "ThruB.s2p"),
    }
    bad_side = client.post("/api/deembed", files=files, data={"side": "sideways", "port_mapping": "auto", "reference_z0": "50"})
    assert bad_side.status_code == 400
    assert bad_side.json()["detail"] == "去嵌侧设置无效。"

    bad_z0 = client.post("/api/deembed", files=files, data={"side": "both", "port_mapping": "auto", "reference_z0": "0"})
    assert bad_z0.status_code == 400
    assert "参考阻抗" in bad_z0.json()["detail"]


def test_deembed_requires_files_or_token(client: TestClient) -> None:
    response = client.post("/api/deembed", data={"side": "both", "port_mapping": "auto", "reference_z0": "50"})
    assert response.status_code == 400


def test_download_unknown_key_and_expired_token(client: TestClient, se_preset, upload_factory) -> None:  # noqa: ANN001
    unknown = client.get("/api/download/some-token/spiral")
    assert unknown.status_code == 404
    assert unknown.json()["detail"] == "未知的 Touchstone 导出类型。"

    expired = client.get("/api/download/some-token/dut")
    assert expired.status_code == 410


def test_tdr_input_and_result_flow(client: TestClient, se_preset, upload_factory) -> None:  # noqa: ANN001
    token = _inspect(client, se_preset, upload_factory).json()["inspection_token"]
    result = client.post(
        "/api/deembed",
        data={"inspection_token": token, "side": "both", "port_mapping": "auto", "reference_z0": "50"},
    ).json()

    common = {
        "port": "1",
        "port_mapping": "auto",
        "reference_z0": "50",
        "window": "hamming",
        "dc_method": "linear",
        "rise_time_ps": "0",
    }
    input_tdr = client.post("/api/tdr/input", data={"inspection_token": token, "slot": "all", **common})
    assert input_tdr.status_code == 200
    input_payload = input_tdr.json()
    assert input_payload["slot"] == "all"
    assert set(input_payload["series"]) == {"total", "thru_a", "thru_b"}
    assert input_payload["parameter"] == "S11"

    single = client.post("/api/tdr/input", data={"inspection_token": token, "slot": "thru_a", **common})
    assert single.status_code == 200
    assert single.json()["slot"] == "thru_a"

    result_tdr = client.post(
        "/api/tdr/result",
        data={"inspection_token": token, "result_token": result["result_token"], **common},
    )
    assert result_tdr.status_code == 200
    assert set(result_tdr.json()["series"]) == {"total", "dut", "fix_a", "fix_b", "thru_a", "thru_b"}

    unknown_slot = client.post("/api/tdr/input", data={"inspection_token": token, "slot": "ghost", **common})
    assert unknown_slot.status_code == 400

    expired = client.post("/api/tdr/input", data={"inspection_token": "nope", "slot": "all", **common})
    assert expired.status_code == 410


def test_tdr_stack_shares_time_axis_across_mixed_grids(client: TestClient, se_preset, upload_factory) -> None:  # noqa: ANN001
    """三份文件频率网格不同时，叠加的 TDR 曲线必须共享同一条时间轴（等长）。"""

    resampled = se_preset.thru_2x_a.interpolate(rf.Frequency.from_f(np.linspace(0.2e9, 60e9, 301), unit="hz"))
    files = {
        "total": upload_factory(se_preset.total, "Total.s2p"),
        "thru_a": upload_factory(resampled, "ThruA.s2p"),
        "thru_b": upload_factory(se_preset.thru_2x_b, "ThruB.s2p"),
    }
    token = client.post("/api/inspect", files=files, data={"port_mapping": "auto"}).json()["inspection_token"]
    result = client.post(
        "/api/deembed",
        data={"inspection_token": token, "side": "both", "port_mapping": "auto", "reference_z0": "50"},
    ).json()

    settings = {"port": "1", "port_mapping": "auto", "reference_z0": "50", "window": "hamming", "dc_method": "linear", "rise_time_ps": "0"}
    stack = client.post("/api/tdr/input", data={"inspection_token": token, "slot": "all", **settings}).json()
    assert {len(values) for values in stack["series"].values()} == {len(stack["time_ns"])}

    result_stack = client.post(
        "/api/tdr/result",
        data={"inspection_token": token, "result_token": result["result_token"], **settings},
    ).json()
    assert {len(values) for values in result_stack["series"].values()} == {len(result_stack["time_ns"])}


def test_tdr_validates_settings(client: TestClient, se_preset, upload_factory) -> None:  # noqa: ANN001
    token = _inspect(client, se_preset, upload_factory).json()["inspection_token"]
    base = {"inspection_token": token, "slot": "all", "port": "1", "port_mapping": "auto", "reference_z0": "50"}

    bad_window = client.post("/api/tdr/input", data={**base, "window": "triangle", "dc_method": "linear", "rise_time_ps": "0"})
    assert bad_window.status_code == 400

    bad_rise = client.post("/api/tdr/input", data={**base, "window": "hamming", "dc_method": "linear", "rise_time_ps": "99999"})
    assert bad_rise.status_code == 400

    bad_z0 = client.post("/api/tdr/input", data={**base, "reference_z0": "-5", "window": "hamming", "dc_method": "linear", "rise_time_ps": "0"})
    assert bad_z0.status_code == 400


def test_file_too_large_returns_413(client: TestClient, se_preset) -> None:  # noqa: ANN001
    from backend.config import Settings
    from backend.main import create_app

    tiny = create_app(settings=Settings(max_upload_bytes=1024))
    with TestClient(tiny) as tiny_client:
        oversized = network_to_text(se_preset.total).encode("utf-8") * 2
        response = tiny_client.post(
            "/api/inspect",
            files={"total": ("Total.s2p", oversized, "text/plain"), "thru_a": ("A.s2p", b"x", "text/plain"), "thru_b": ("B.s2p", b"x", "text/plain")},
            data={"port_mapping": "auto"},
        )
    assert response.status_code == 413
    assert "MB 限制" in response.json()["detail"]


def test_differential_deembed_returns_mixed_mode_chart(client: TestClient, diff_preset, upload_factory) -> None:  # noqa: ANN001
    token = _inspect(client, diff_preset, upload_factory).json()["inspection_token"]
    response = client.post(
        "/api/deembed",
        data={"inspection_token": token, "side": "both", "port_mapping": "sequential", "reference_z0": "50"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["port_mapping"] == "sequential"
    assert {"SDD21", "SCC21", "SCD21"} <= set(payload["chart"]["series"])
    for values in payload["chart"]["series"]["SDD21"].values():
        assert all(isinstance(item, float) for item in values[:5])
    assert payload["left_ports"] == ["P1 (+)", "P2 (−)"]


def test_health_and_static_assets_are_reachable(client: TestClient) -> None:
    assert client.get("/api/health").status_code == 200
    static = client.get("/static/index.html")
    assert static.status_code == 200
    assert "text/html" in static.headers["content-type"]


@pytest.fixture(autouse=True)
def _silence_numpy_warnings() -> None:
    import warnings

    warnings.filterwarnings("ignore", category=RuntimeWarning)
    _ = np
