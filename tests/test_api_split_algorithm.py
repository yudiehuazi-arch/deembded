"""``/api/deembed`` 的差分劈半算法选择、对照曲线与模式转换诊断。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from deembed import network_from_text, presets


@pytest.fixture(scope="module")
def skew_preset():
    return presets.get_preset("diff_skew_dual_2xthru")


def _files(preset, upload_factory) -> dict:  # noqa: ANN001
    extension = "s2p" if preset.nports == 2 else "s4p"
    return {
        "total": upload_factory(preset.total, f"Total.{extension}"),
        "thru_a": upload_factory(preset.thru_2x_a, f"ThruA.{extension}"),
        "thru_b": upload_factory(preset.thru_2x_b, f"ThruB.{extension}"),
    }


def _form(**extra: str) -> dict[str, str]:
    return {"side": "both", "port_mapping": "auto", "reference_z0": "50", **extra}


def test_differential_default_uses_mode_conversion_and_returns_comparison(
    client: TestClient, skew_preset, upload_factory  # noqa: ANN001
) -> None:
    response = client.post("/api/deembed", files=_files(skew_preset, upload_factory), data=_form())
    assert response.status_code == 200
    payload = response.json()

    assert payload["split_algorithm"] == "mc_nzc"
    assert payload["comparison_algorithm"] == "classic_nzc"
    assert "模式转换" in payload["split_algorithm_label"]
    assert payload["comparison_label"] == "IEEE 370 经典 MM-NZC"
    assert payload["quality"]["status"] == "PASS"
    assert "dut_alt" in payload["chart"]["network_keys"]
    assert "dut_alt" in payload["chart"]["series"]["SDD21"]

    diagnostics = payload["diagnostics"]
    assert diagnostics["thru_a"]["skew_ps"] == pytest.approx(2.857, abs=0.02)
    assert diagnostics["thru_b"]["skew_ps"] == pytest.approx(1.905, abs=0.02)
    assert diagnostics["comparison"]["max_delta_db"] > 1.0
    assert len(diagnostics["comparison"]["checkpoints"]) == 4

    download = client.get(f"/api/download/{payload['result_token']}/dut_alt")
    assert download.status_code == 200
    assert 'filename="DUT_deembedded_compare.s4p"' in download.headers["content-disposition"]
    assert network_from_text(download.text, "DUT_deembedded_compare.s4p").nports == 4


def test_classic_algorithm_can_be_selected(client: TestClient, skew_preset, upload_factory) -> None:  # noqa: ANN001
    response = client.post(
        "/api/deembed", files=_files(skew_preset, upload_factory), data=_form(split_algorithm="classic_nzc")
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["split_algorithm"] == "classic_nzc"
    assert payload["comparison_algorithm"] == "mc_nzc"
    assert payload["diagnostics"]["comparison"]["max_delta_db"] < -1.0
    # 经典算法在该示例上 SDD21 偏低：DUT 曲线低于对照曲线
    sdd21 = payload["chart"]["series"]["SDD21"]
    assert sdd21["dut"][-1] < sdd21["dut_alt"][-1] - 1.0


def test_invalid_split_algorithm_is_rejected(client: TestClient, skew_preset, upload_factory) -> None:  # noqa: ANN001
    response = client.post(
        "/api/deembed", files=_files(skew_preset, upload_factory), data=_form(split_algorithm="magic")
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "差分劈半算法设置无效。"


def test_single_ended_ignores_split_algorithm(client: TestClient, se_preset, upload_factory) -> None:  # noqa: ANN001
    response = client.post(
        "/api/deembed", files=_files(se_preset, upload_factory), data=_form(split_algorithm="classic_nzc")
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["split_algorithm"] is None
    assert payload["split_algorithm_label"] == "IEEE 370 SE-NZC"
    assert payload["comparison_algorithm"] is None
    assert payload["diagnostics"] is None
    assert "dut_alt" not in payload["chart"]["network_keys"]
    missing = client.get(f"/api/download/{payload['result_token']}/dut_alt")
    assert missing.status_code == 410
