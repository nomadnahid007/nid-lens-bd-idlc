import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def _force_demo_mode(monkeypatch):
    """Tests must be hermetic — deterministic, offline, and free — regardless
    of whatever APP_MODE the developer's own .env happens to be set to.
    Without this, switching a local .env to live mode makes `pytest` silently
    send real Gemini API calls using meaningless synthetic test images."""
    monkeypatch.setenv("APP_MODE", "demo")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
