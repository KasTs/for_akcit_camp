"""Tests for OpenAIBriefingService (app/services/briefing/openai.py).

The OpenAI SDK is fully mocked here — these tests must never touch the
network or require a real API key.

app.* imports are deferred into the `service` fixture (and routed through
the `module` it returns) rather than done at module scope, per the
project-wide rule in tests/conftest.py / tests/test_security.py:
Settings.model_config resolves env_file at class-definition time, so an
unguarded module-scope import of app.config would leak the developer's
real .env into the rest of the session. Mirrors tests/test_assemblyai.py's
fixture, the equivalent "real"-mode vendor service on the transcription
side. `BriefingRequest`, `EvolutionEntry` and `LlmBriefing` are read off
`module` instead of imported separately — openai.py already imports the
first two, making them module attributes, and defines the third.
"""

import pytest
from openai import OpenAIError


class FakeMessage:
    def __init__(self, parsed):
        self.parsed = parsed


class FakeChoice:
    def __init__(self, parsed):
        self.message = FakeMessage(parsed)


class FakeCompletion:
    def __init__(self, parsed):
        self.choices = [FakeChoice(parsed)]


@pytest.fixture
def service(monkeypatch):
    """Serviço com o cliente da OpenAI substituído; conta as chamadas.

    RAFIRA_ENV_FILE is pointed away from the developer's real .env before
    the first app.* import of the session (see tests/test_assemblyai.py).
    """
    monkeypatch.setenv("RAFIRA_ENV_FILE", ".env.absent")

    from app.config import Settings
    from app.services.briefing import openai as module

    calls = {"count": 0, "parsed": None, "error": None}

    class FakeParse:
        async def parse(self, **kwargs):
            calls["count"] += 1
            calls["kwargs"] = kwargs
            if calls["error"] is not None:
                raise calls["error"]
            return FakeCompletion(calls["parsed"])

    class FakeClient:
        def __init__(self, *args, **kwargs):
            calls["init_kwargs"] = kwargs
            self.beta = type(
                "Beta", (), {"chat": type("Chat", (), {"completions": FakeParse()})()}
            )()

    monkeypatch.setattr(module, "AsyncOpenAI", FakeClient)

    built = module.OpenAIBriefingService(
        Settings(
            transcription_mode="real",
            assemblyai_api_key="aai-test",
            openai_api_key="sk-test",
        )
    )
    return built, calls, module


def _dossier(module):
    return module.BriefingRequest.model_validate(
        {
            "patient": {"allergy_status": "unknown"},
            "encounters": [
                {"id": "812", "recorded_at": "2026-05-14T09:00:00", "service": "Retorno"}
            ],
        }
    )


async def test_empty_dossier_never_calls_the_vendor(service):
    """Regra 4 também economiza dinheiro: não se paga token para confirmar
    que não há nada a dizer."""
    built, calls, module = service

    result = await built.generate(module.BriefingRequest.model_validate({"encounters": []}))

    assert calls["count"] == 0
    assert result.since_last is None
    assert result.evolution == []


async def test_forged_encounter_id_is_dropped_from_the_model_output(service):
    """O ponto de a regra 2 ser verificada no servidor."""
    built, calls, module = service
    calls["parsed"] = module.LlmBriefing(
        summary="resumo",
        since_last_items=[],
        evolution=[
            module.EvolutionEntry(
                topic="real", text="ok", source_encounter_ids=["812"], confidence="high"
            ),
            module.EvolutionEntry(
                topic="forjado",
                text="inventado",
                source_encounter_ids=["999"],
                confidence="high",
            ),
        ],
        watch_points=[],
    )

    result = await built.generate(_dossier(module))

    assert [e.topic for e in result.evolution] == ["real"]


async def test_since_last_arithmetic_is_not_delegated_to_the_model(service):
    """days_ago e encounter_id são aritmética, calculada aqui."""
    built, calls, module = service
    calls["parsed"] = module.LlmBriefing(
        summary="resumo", since_last_items=[], evolution=[], watch_points=[]
    )

    result = await built.generate(_dossier(module))

    assert result.since_last.encounter_id == "812"
    assert isinstance(result.since_last.days_ago, int)
    assert result.model == "gpt-4o-mini"


async def test_missing_prompt_file_raises_prompt_not_found_error(service, tmp_path):
    """tmp_path existe mas está vazio: sem briefing_system.txt dentro dele."""
    _built, calls, module = service
    from app.config import Settings

    built = module.OpenAIBriefingService(
        Settings(
            transcription_mode="real",
            assemblyai_api_key="aai-test",
            openai_api_key="sk-test",
            prompts_dir=tmp_path,
        )
    )

    with pytest.raises(module.PromptNotFoundError, match="Prompt file not found"):
        await built.generate(_dossier(module))

    assert calls["count"] == 0


async def test_openai_error_from_parse_is_wrapped_as_briefing_failed_error(service):
    built, calls, module = service
    calls["error"] = OpenAIError("boom")

    with pytest.raises(module.BriefingFailedError, match="boom"):
        await built.generate(_dossier(module))


async def test_client_timeout_budget_is_comfortably_under_the_rails_deadline(service):
    """Ai::BriefingClient::READ_TIMEOUT (rafira-web) is 90s. The AsyncOpenAI
    SDK defaults (timeout=600s, max_retries=2) let this process keep an
    original call alive for up to ~30 minutes across three attempts —
    duplicated vendor spend and an orphaned in-flight request once Rails
    has already given up and re-enqueued the job."""
    _built, calls, _module = service

    assert calls["init_kwargs"].get("max_retries") == 1
    timeout = calls["init_kwargs"].get("timeout")
    assert timeout is not None
    # 2 total attempts (1 retry) at this per-attempt budget must still land
    # comfortably inside the 90s Rails gives the whole call.
    assert (calls["init_kwargs"]["max_retries"] + 1) * timeout < 90


async def test_parse_returning_no_parsed_content_raises_briefing_failed_error(service):
    """.parse() pode devolver uma completion sem `.parsed` preenchido — a
    fixture já começa com calls["parsed"] = None; este teste é o único que
    o deixa assim de propósito, em vez de sobrescrever com um LlmBriefing."""
    built, calls, module = service

    with pytest.raises(module.BriefingFailedError, match="empty response from OpenAI"):
        await built.generate(_dossier(module))

    assert calls["count"] == 1
