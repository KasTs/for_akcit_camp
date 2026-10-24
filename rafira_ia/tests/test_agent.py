from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.models.agent import AgentDraft, AgentRequest, Citation, ClinicalClaim
from app.services.agent import AgentFailure, ClinicalHarness, OpenAIDraftProvider


def context(task="doctor_summary"):
    return {
        "task": task,
        "sources": [
            {
                "id": "transcript:1",
                "kind": "transcript",
                "title": "Consulta",
                "text": "Paciente relata melhora do sono.",
            }
        ],
    }


def draft(source_id="transcript:1", quote="melhora do sono", kind="recorded_fact"):
    return AgentDraft(
        claims=[
            ClinicalClaim(
                text="Relata melhora do sono.",
                kind=kind,
                citations=[Citation(source_id=source_id, quote=quote)],
            )
        ],
        missing_data=[],
        limitations=[],
        abstained=False,
    )


def test_stub_summary_is_sourced_and_review_required(make_client):
    response = make_client().post("/agent/runs", json=context())
    assert response.status_code == 200
    result = response.json()
    assert result["requires_review"] is True
    assert result["claims"][0]["citations"][0]["source_id"] == "transcript:1"
    assert result["steps"][-1] == "awaiting_human_review"


def test_no_evidence_abstains(make_client):
    payload = context("clinical_question")
    payload["question"] = "Devo modificar o tratamento?"
    result = make_client().post("/agent/runs", json=payload).json()
    assert result["abstained"] is True
    assert result["claims"] == []


@pytest.mark.parametrize("sources", [[], context()["sources"] * 2])
def test_invalid_context_rejected(make_client, sources):
    assert (
        make_client()
        .post("/agent/runs", json={"task": "doctor_summary", "sources": sources})
        .status_code
        == 422
    )


def test_patient_summary_rejects_unapproved_sources(make_client):
    assert make_client().post("/agent/runs", json=context("patient_summary")).status_code == 422


def test_patient_summary_uses_only_approved_text(make_client):
    payload = context("patient_summary")
    payload["sources"][0]["kind"] = "approved_summary"
    result = make_client().post("/agent/runs", json=payload).json()
    assert result["claims"][0]["text"] == payload["sources"][0]["text"]


def test_agent_auth(make_client):
    client = make_client(TRANSCRIPTION_API_TOKEN="secret")
    assert client.post("/agent/runs", json=context()).status_code == 401
    assert (
        client.post(
            "/agent/runs", json=context(), headers={"Authorization": "Bearer secret"}
        ).status_code
        == 200
    )


def test_real_harness_requires_private_service_token(make_client):
    client = make_client(
        TRANSCRIPTION_MODE="real", ASSEMBLYAI_API_KEY="test-only", OPENAI_API_KEY="test-only"
    )
    assert client.post("/agent/runs", json=context()).status_code == 503


def test_unexpected_failure_does_not_expose_patient_data(make_client):
    from app.dependencies import get_clinical_harness

    client = make_client()
    harness = SimpleNamespace(run=AsyncMock(side_effect=RuntimeError("private-patient-name")))
    client.app.dependency_overrides[get_clinical_harness] = lambda: harness
    response = client.post("/agent/runs", json=context())
    assert response.status_code == 500
    assert "private-patient-name" not in response.text


@pytest.mark.parametrize(
    "bad_draft", [draft(source_id="foreign:7"), draft(quote="não existe"), draft(kind="suggestion")]
)
@pytest.mark.asyncio
async def test_harness_rejects_unsupported_outputs(bad_draft):
    provider = SimpleNamespace(model="fake", generate=AsyncMock(return_value=bad_draft))
    with pytest.raises(AgentFailure):
        await ClinicalHarness(provider).run(AgentRequest.model_validate(context()))


@pytest.mark.asyncio
async def test_no_evidence_never_contacts_provider():
    provider = SimpleNamespace(model="fake", generate=AsyncMock())
    request = AgentRequest.model_validate(
        {**context("clinical_question"), "question": "Tratamento?"}
    )
    await ClinicalHarness(provider).run(request)
    provider.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_suggestion_requires_real_guideline_citation():
    payload = {**context("clinical_question"), "question": "Tratamento?"}
    payload["sources"].append(
        {
            "id": "g1",
            "kind": "guideline",
            "title": "Protocolo",
            "text": "Avaliar o contexto antes de decidir.",
        }
    )
    answer = draft(source_id="g1", quote="Avaliar o contexto", kind="suggestion")
    provider = SimpleNamespace(model="fake", generate=AsyncMock(return_value=answer))
    result = await ClinicalHarness(provider).run(AgentRequest.model_validate(payload))
    assert not result.abstained


@pytest.mark.asyncio
async def test_guideline_cannot_establish_patient_fact():
    payload = {**context("clinical_question"), "question": "Tratamento?"}
    payload["sources"].append(
        {"id": "g1", "kind": "guideline", "title": "Protocolo", "text": "sono"}
    )
    provider = SimpleNamespace(model="fake", generate=AsyncMock(return_value=draft("g1", "sono")))
    with pytest.raises(AgentFailure):
        await ClinicalHarness(provider).run(AgentRequest.model_validate(payload))


def test_context_budget():
    payload = context()
    payload["sources"] = [
        {**payload["sources"][0], "id": str(i), "text": "a" * 60000} for i in range(3)
    ]
    with pytest.raises(ValidationError, match="character budget"):
        AgentRequest.model_validate(payload)


@pytest.mark.asyncio
async def test_real_provider_uses_structured_schema_and_single_call(monkeypatch):
    import openai

    parsed = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=draft()))])
    parse = AsyncMock(return_value=parsed)

    def constructor(**kwargs):
        return SimpleNamespace(
            beta=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse)))
        )

    monkeypatch.setattr(openai, "AsyncOpenAI", constructor)
    service = OpenAIDraftProvider(Settings(openai_api_key="test"))
    result = await service.generate(AgentRequest.model_validate(context()))
    assert result == draft()
    parse.assert_awaited_once()
    assert parse.call_args.kwargs["response_format"] is AgentDraft
    assert parse.call_args.kwargs["max_tokens"] == 3500


def test_question_required(make_client):
    assert make_client().post("/agent/runs", json=context("clinical_question")).status_code == 422


@pytest.mark.asyncio
async def test_refusal_and_error_are_safe(monkeypatch):
    import openai

    parse = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(parsed=None))]
        )
    )
    monkeypatch.setattr(
        openai,
        "AsyncOpenAI",
        lambda **kwargs: SimpleNamespace(
            beta=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse)))
        ),
    )
    service = OpenAIDraftProvider(Settings(openai_api_key="test"))
    with pytest.raises(AgentFailure, match="estruturado"):
        await service.generate(AgentRequest.model_validate(context()))
    parse.side_effect = openai.APIConnectionError(
        request=__import__("httpx").Request("POST", "https://example.org")
    )
    with pytest.raises(AgentFailure, match="Falha no provedor"):
        await service.generate(AgentRequest.model_validate(context()))
