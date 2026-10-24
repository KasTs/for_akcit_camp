import sys

import pytest
from fastapi.testclient import TestClient

ENV_KEYS = (
    "TRANSCRIPTION_MODE",
    "TRANSCRIPTION_API_TOKEN",
    "TRANSCRIPTION_STUB_DELAY_SEC",
    "BRIEFING_STUB_DELAY_SEC",
    "ASSEMBLYAI_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
)


@pytest.fixture
def make_client(monkeypatch):
    """Constrói um TestClient com ambiente controlado.

    Aponta RAFIRA_ENV_FILE para um arquivo inexistente para que o .env do
    desenvolvedor nunca vaze para dentro do teste, e limpa os caches de
    lru_cache de settings e dependencies antes de montar o app.
    """

    def _make(**env):
        monkeypatch.setenv("RAFIRA_ENV_FILE", ".env.absent")
        for key in ENV_KEYS:
            monkeypatch.delenv(key, raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, str(value))

        from app import dependencies
        from app.config import get_settings

        get_settings.cache_clear()
        for name in dir(dependencies):
            provider = getattr(dependencies, name)
            if hasattr(provider, "cache_clear"):
                provider.cache_clear()

        sys.modules.pop("app.main", None)
        from app.main import app

        return TestClient(app)

    return _make
