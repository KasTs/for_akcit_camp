"""Tests for optional bearer-token authentication (app/core/security.py).

Covers:

- the health-endpoint bypass — /health must never require the token, even
  once one is configured.
- direct unit tests of require_token, called as a plain async function
  instead of through a route.
- route-level auth against POST /transcriptions, now that the route and the
  {"error": ...} exception handler its 401 response relies on both exist
  (added in Task 3).
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

# Mirrors tests/conftest.py's ENV_KEYS. Settings.model_config resolves
# env_file at class-definition time, so the *first* import of app.config
# in the whole test session must happen with RAFIRA_ENV_FILE pointed away
# from the developer's real .env — otherwise it (and any real vendor
# key/mode already exported in the shell) leaks into the Settings()
# instances these tests construct directly. Cleared the same way
# conftest.make_client protects the app-level tests.
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
def security(monkeypatch):
    """Import app.core.security and app.config with a clean environment.

    Returns a namespace with `require_token` and `Settings` so tests can
    call the dependency directly and build Settings instances by hand.
    """
    monkeypatch.setenv("RAFIRA_ENV_FILE", ".env.absent")
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    from app.config import Settings
    from app.core.security import require_token

    return SimpleNamespace(require_token=require_token, Settings=Settings)


def _request(authorization: str | None = None) -> SimpleNamespace:
    """Minimal stand-in for fastapi.Request.

    require_token only ever calls request.headers.get("Authorization", ""),
    so a plain object exposing a dict as `.headers` is enough — no need for
    a real Request or TestClient round-trip.
    """
    headers = {"Authorization": authorization} if authorization is not None else {}
    return SimpleNamespace(headers=headers)


def test_health_is_never_authenticated(make_client):
    """O healthcheck do ECS não carrega token."""
    client = make_client(TRANSCRIPTION_API_TOKEN="s3cr3t")

    assert client.get("/health").status_code == 200


async def test_require_token_allows_request_when_no_token_configured(security):
    settings = security.Settings(transcription_api_token=None)

    assert await security.require_token(_request(), settings) is None


async def test_require_token_rejects_missing_header_when_token_configured(security):
    settings = security.Settings(transcription_api_token="s3cr3t")

    with pytest.raises(HTTPException) as exc_info:
        await security.require_token(_request(), settings)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "invalid or missing bearer token"


async def test_require_token_rejects_wrong_value(security):
    settings = security.Settings(transcription_api_token="s3cr3t")

    with pytest.raises(HTTPException) as exc_info:
        await security.require_token(_request("Bearer wrong"), settings)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "invalid or missing bearer token"


async def test_require_token_accepts_matching_bearer_token(security):
    settings = security.Settings(transcription_api_token="s3cr3t")

    result = await security.require_token(_request("Bearer s3cr3t"), settings)

    assert result is None


async def test_require_token_accepts_lowercase_scheme(security):
    settings = security.Settings(transcription_api_token="s3cr3t")

    result = await security.require_token(_request("bearer s3cr3t"), settings)

    assert result is None


async def test_require_token_rejects_non_ascii_token(security):
    """A non-ASCII presented token must yield 401, not crash the request.

    secrets.compare_digest raises TypeError when either argument is a str
    containing non-ASCII characters. ASGI servers commonly decode header
    values as Latin-1, so a raw high-byte octet in the Authorization header
    reaches require_token as a non-ASCII str whenever a client (or an
    attacker) sends one in an otherwise well-formed "Bearer <token>" header
    -- this is reachable input, not a hypothetical. It must compare as just
    another wrong token (401), never raise an unhandled TypeError.
    """
    settings = security.Settings(transcription_api_token="s3cr3t")

    with pytest.raises(HTTPException) as exc_info:
        await security.require_token(_request("Bearer tok\xe9n"), settings)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "invalid or missing bearer token"


def test_no_token_configured_allows_post_to_transcriptions(make_client):
    client = make_client(TRANSCRIPTION_STUB_DELAY_SEC=0)

    response = client.post("/transcriptions", json={"audio_url": "https://x/a.webm"})

    assert response.status_code == 200


def test_missing_header_rejects_post_to_transcriptions(make_client):
    client = make_client(TRANSCRIPTION_API_TOKEN="s3cr3t", TRANSCRIPTION_STUB_DELAY_SEC=0)

    response = client.post("/transcriptions", json={"audio_url": "https://x/a.webm"})

    assert response.status_code == 401
    assert response.json() == {"error": "invalid or missing bearer token"}


def test_correct_bearer_header_allows_post_to_transcriptions(make_client):
    client = make_client(TRANSCRIPTION_API_TOKEN="s3cr3t", TRANSCRIPTION_STUB_DELAY_SEC=0)

    response = client.post(
        "/transcriptions",
        json={"audio_url": "https://x/a.webm"},
        headers={"Authorization": "Bearer s3cr3t"},
    )

    assert response.status_code == 200


def test_wrong_token_value_rejects_post_to_transcriptions(make_client):
    client = make_client(TRANSCRIPTION_API_TOKEN="s3cr3t", TRANSCRIPTION_STUB_DELAY_SEC=0)

    response = client.post(
        "/transcriptions",
        json={"audio_url": "https://x/a.webm"},
        headers={"Authorization": "Bearer wrong"},
    )

    assert response.status_code == 401
    assert response.json() == {"error": "invalid or missing bearer token"}
