"""pytest 公共夹具：合成网络、Touchstone 文件与测试客户端。"""

from __future__ import annotations

from typing import Callable

import pytest
import skrf as rf
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from deembed import build_default_engine, network_to_text, presets
from deembed.presets.base import DemoPreset

#: 测试用时间预算：合成示例在 CI 上单次去嵌约 1 秒
pytest_plugins: tuple[str, ...] = ()


@pytest.fixture(scope="session")
def se_preset() -> DemoPreset:
    """单端独立双 2X Thru 示例（2 端口）。"""

    return presets.get_preset("se_dual_2xthru")


@pytest.fixture(scope="session")
def diff_preset() -> DemoPreset:
    """差分独立双 2X Thru 示例（4 端口）。"""

    return presets.get_preset("diff_dual_2xthru")


@pytest.fixture(scope="session")
def se_two_port_pair() -> tuple[rf.Network, rf.Network, rf.Network]:
    """两个可级联的 2 端口网络与它们的乘积。"""

    se = presets.get_preset("se_2xthru")
    left = se.thru_2x
    assert left is not None
    right = left.flipped()
    return left, right, left**right


@pytest.fixture()
def upload_factory() -> Callable[[rf.Network, str], tuple[str, bytes, str]]:
    """把 ``rf.Network`` 转成 TestClient 可用的上传三元组。"""

    def build(network: rf.Network, filename: str) -> tuple[str, bytes, str]:
        return (filename, network_to_text(network).encode("utf-8"), "text/plain")

    return build


@pytest.fixture()
def client() -> TestClient:
    """独立缓存的应用实例（每个测试互不影响）。"""

    app = create_app(settings=Settings(max_upload_bytes=8 * 1024 * 1024))
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def engine():
    return build_default_engine()
