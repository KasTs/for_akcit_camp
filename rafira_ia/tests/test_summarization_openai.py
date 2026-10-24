"""Tests for OpenAISummarizationService (app/services/summarization/openai.py).

The OpenAI SDK is fully mocked here — these tests must never touch the
network or require a real API key.

app.* imports are deferred into the `service` fixture rather than done at
module scope, per the project-wide rule in tests/conftest.py /
tests/test_security.py: Settings.model_config resolves env_file at
class-definition time, so an unguarded module-scope import of app.config
would leak the developer's real .env into the rest of the session. Mirrors
tests/test_briefing_openai.py, the sibling "real"-mode vendor service for
/briefings.
"""

from pathlib import Path

import pytest
from openai import OpenAIError


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content):
        self.message = FakeMessage(content)


class FakeCompletion:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]


@pytest.fixture
def service(monkeypatch):
    """Serviço com o cliente da OpenAI substituído; captura as chamadas.

    RAFIRA_ENV_FILE is pointed away from the developer's real .env before
    the first app.* import of the session (see tests/test_assemblyai.py).
    Returns a `build(**overrides)` factory instead of one fixed instance,
    since some tests need a second Settings with a different prompts_dir.
    """
    monkeypatch.setenv("RAFIRA_ENV_FILE", ".env.absent")

    from app.config import Settings
    from app.services.summarization import openai as module

    calls = {"count": 0, "content": "resumo gerado", "error": None}

    class FakeCreate:
        async def create(self, **kwargs):
            calls["count"] += 1
            calls["kwargs"] = kwargs
            if calls["error"] is not None:
                raise calls["error"]
            return FakeCompletion(calls["content"])

    class FakeClient:
        def __init__(self, *args, **kwargs):
            calls["init_kwargs"] = kwargs
            self.chat = type("Chat", (), {"completions": FakeCreate()})()

    monkeypatch.setattr(module, "AsyncOpenAI", FakeClient)

    def build(**overrides):
        settings = Settings(
            transcription_mode="real",
            assemblyai_api_key="aai-test",
            openai_api_key="sk-test",
            **overrides,
        )
        return module.OpenAISummarizationService(settings)

    return build, calls, module


def _default_prompt_text(filename):
    """Lê o mesmo arquivo que a implementação lê, para comparar por igualdade
    sem duplicar o conteúdo do prompt dentro do teste."""
    return Path("prompts", filename).read_text(encoding="utf-8").strip()


async def test_default_doctor_prompt_is_loaded_and_used_as_system_message(service):
    build, calls, _module = service
    built = build()

    result = await built.summarize("paciente relata melhora", "doctor")

    messages = calls["kwargs"]["messages"]
    assert messages[0] == {
        "role": "system",
        "content": _default_prompt_text("default_doctor.txt"),
    }
    assert messages[1] == {"role": "user", "content": "paciente relata melhora"}
    assert result == "resumo gerado"


async def test_default_patient_prompt_is_loaded_and_used_as_system_message(service):
    build, calls, _module = service
    built = build()

    await built.summarize("paciente relata melhora", "patient")

    messages = calls["kwargs"]["messages"]
    assert messages[0] == {
        "role": "system",
        "content": _default_prompt_text("default_patient.txt"),
    }


async def test_custom_prompt_overrides_default_and_the_file_is_not_read(service):
    build, calls, _module = service
    # Aponta para um diretório inexistente: se a implementação ainda tentasse
    # carregar o prompt padrão apesar do custom_prompt, isto levantaria
    # PromptNotFoundError e o teste falharia — provando comportamentalmente
    # que o arquivo não é lido quando custom_prompt é fornecido.
    built = build(prompts_dir=Path("/nonexistent/rafira-test-prompts-dir"))

    await built.summarize("texto", "doctor", custom_prompt="Resuma de forma bem curta.")

    messages = calls["kwargs"]["messages"]
    assert messages[0] == {"role": "system", "content": "Resuma de forma bem curta."}


async def test_missing_prompt_file_raises_prompt_not_found_error(service, tmp_path):
    build, calls, module = service
    built = build(prompts_dir=tmp_path)

    with pytest.raises(module.PromptNotFoundError, match="Prompt file not found"):
        await built.summarize("texto", "doctor")

    assert calls["count"] == 0


async def test_client_timeout_budget_is_comfortably_under_the_rails_deadline(service):
    """No Rails caller exists yet for /summaries (see docs/contract.md),
    but the same OpenAI backend and the same process-level risk apply as
    for /briefings: SDK defaults (timeout=600s, max_retries=2) can hold a
    call open for ~30 minutes across three attempts. Tied to
    Ai::BriefingClient::READ_TIMEOUT (90s) as the nearest established
    budget for an OpenAI call from this service."""
    build, calls, _module = service
    build()

    assert calls["init_kwargs"].get("max_retries") == 1
    timeout = calls["init_kwargs"].get("timeout")
    assert timeout is not None
    assert (calls["init_kwargs"]["max_retries"] + 1) * timeout < 90


async def test_openai_error_from_the_vendor_is_wrapped_as_summarization_failed_error(service):
    build, calls, module = service
    built = build()
    calls["error"] = OpenAIError("boom")

    with pytest.raises(module.SummarizationFailedError, match="boom"):
        await built.summarize("texto", "doctor")


@pytest.mark.parametrize("content", ["", None])
async def test_empty_or_blank_response_raises_summarization_failed_error(service, content):
    build, calls, module = service
    built = build()
    calls["content"] = content

    with pytest.raises(module.SummarizationFailedError, match="empty response from OpenAI"):
        await built.summarize("texto", "doctor")
