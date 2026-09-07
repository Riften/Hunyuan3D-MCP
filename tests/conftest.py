import pytest


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    for name in (
        "HY3D_API_KEY",
        "HY3D_PROXY",
        "HY3D_TIMEOUT_SECONDS",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "https_proxy",
        "http_proxy",
        "all_proxy",
        "no_proxy",
    ):
        monkeypatch.delenv(name, raising=False)
