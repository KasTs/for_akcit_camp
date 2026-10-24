"""Tests for AssemblyAITranscriptionService (app/services/transcription/assemblyai.py).

The AssemblyAI SDK is fully mocked here — these tests must never touch the
network or require a real API key.
"""

import pytest


class FakeUtterance:
    def __init__(self, start, end, speaker, text):
        self.start, self.end, self.speaker, self.text = start, end, speaker, text


class FakeTranscript:
    def __init__(self, status="completed", utterances=None, error=None):
        self.status = status
        self.utterances = utterances
        self.error = error
        self.id = "aai-123"
        self.text = "texto completo"
        self.audio_duration = 42


@pytest.fixture
def service(monkeypatch):
    """Constrói o serviço com o SDK da AssemblyAI totalmente mockado.

    Settings.model_config resolves env_file at class-definition time (see
    tests/test_security.py), so RAFIRA_ENV_FILE must point away from the
    developer's real .env before the *first* import of app.config in the
    whole test session — this fixture collects alphabetically before the
    others that already guard this, so it must guard it too.
    """
    monkeypatch.setenv("RAFIRA_ENV_FILE", ".env.absent")

    import assemblyai as aai

    from app.config import Settings
    from app.services.transcription.assemblyai import AssemblyAITranscriptionService

    captured = {}

    class FakeTranscriber:
        def transcribe(self, audio_url, config=None):
            captured["audio_url"] = audio_url
            captured["config"] = config
            return captured["transcript"]

    monkeypatch.setattr(aai, "Transcriber", FakeTranscriber)
    monkeypatch.setattr(aai.settings, "api_key", None, raising=False)

    built = AssemblyAITranscriptionService(
        Settings(
            transcription_mode="real",
            assemblyai_api_key="aai-test",
            openai_api_key="sk-test",
        )
    )
    return built, captured


@pytest.mark.asyncio
async def test_maps_utterances_to_contract_segments(service):
    built, captured = service
    captured["transcript"] = FakeTranscript(
        utterances=[
            FakeUtterance(0, 4500, "A", "Bom dia."),
            FakeUtterance(4500, 12000, "B", "Melhorei o sono."),
        ]
    )

    result = await built.transcribe("https://x/a.webm")

    assert result.provider == "assemblyai"
    assert result.language == "pt-BR"
    assert result.duration_sec == 42
    assert result.external_id == "aai-123"
    assert [s.model_dump() for s in result.segments] == [
        {"start": 0.0, "end": 4.5, "speaker": "Falante A", "text": "Bom dia."},
        {"start": 4.5, "end": 12.0, "speaker": "Falante B", "text": "Melhorei o sono."},
    ]


@pytest.mark.asyncio
async def test_passes_the_presigned_url_straight_to_the_vendor(service):
    """O áudio nunca passa por este processo — o vendor busca a URL."""
    built, captured = service
    captured["transcript"] = FakeTranscript(utterances=[])

    await built.transcribe("https://bucket/rec.webm?X-Amz-Signature=abc")

    assert captured["audio_url"] == "https://bucket/rec.webm?X-Amz-Signature=abc"
    assert captured["config"].language_code == "pt"
    assert captured["config"].speaker_labels is True


@pytest.mark.asyncio
async def test_no_utterances_yields_empty_segments(service):
    built, captured = service
    captured["transcript"] = FakeTranscript(utterances=None)

    assert (await built.transcribe("https://x/a")).segments == []


@pytest.mark.asyncio
async def test_vendor_error_status_raises(service):
    import assemblyai as aai

    from app.core.exceptions import TranscriptionFailedError

    built, captured = service
    captured["transcript"] = FakeTranscript(status=aai.TranscriptStatus.error, error="bad audio")

    with pytest.raises(TranscriptionFailedError, match="bad audio"):
        await built.transcribe("https://x/a")
