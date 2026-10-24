"""Protocol both transcription implementations satisfy."""

from typing import Protocol

from app.models.transcription import TranscriptionResponse


class TranscriptionService(Protocol):
    async def transcribe(
        self, audio_url: str, content_type: str | None = None
    ) -> TranscriptionResponse: ...
