from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_bytes():
    return lambda name: (FIXTURES / name).read_bytes()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Tests must never touch the network."""
    import urllib.request

    def boom(*a, **k):
        raise AssertionError("network access attempted in tests")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
