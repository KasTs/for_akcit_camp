"""FastAPI dependency providers.

TRANSCRIPTION_MODE is resolved here, once, instead of branching inside the
handlers: the stub stops being an `if` and becomes a class that can be
tested on its own terms.
"""

from functools import lru_cache

from app.config import get_settings
from app.services.briefing.base import BriefingService
from app.services.briefing.stub import StubBriefingService
from app.services.summarization.base import SummarizationService
from app.services.summarization.stub import StubSummarizationService
from app.services.transcription.base import TranscriptionService
from app.services.transcription.stub import StubTranscriptionService


@lru_cache
def get_clinical_harness():
    from app.services.agent import ClinicalHarness, OpenAIDraftProvider, StubDraftProvider

    settings = get_settings()
    provider = (
        OpenAIDraftProvider(settings)
        if settings.transcription_mode == "real"
        else StubDraftProvider()
    )
    return ClinicalHarness(provider)


@lru_cache
def get_transcription_service() -> TranscriptionService:
    settings = get_settings()
    if settings.transcription_mode == "real":
        from app.services.transcription.assemblyai import AssemblyAITranscriptionService

        return AssemblyAITranscriptionService(settings)
    return StubTranscriptionService(settings)


@lru_cache
def get_briefing_service() -> BriefingService:
    settings = get_settings()
    if settings.transcription_mode == "real":
        from app.services.briefing.openai import OpenAIBriefingService

        return OpenAIBriefingService(settings)
    return StubBriefingService(settings)


@lru_cache
def get_summarization_service() -> SummarizationService:
    settings = get_settings()
    if settings.transcription_mode == "real":
        from app.services.summarization.openai import OpenAISummarizationService

        return OpenAISummarizationService(settings)
    return StubSummarizationService(settings)
