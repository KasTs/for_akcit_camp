"""Transcription backed by AssemblyAI.

The presigned URL goes straight to the vendor, which fetches the bytes
itself — the audio never passes through this process. That is why this
service holds no S3 permission and needs no local disk.

Unlike the Vosk-based double it replaces, AssemblyAI does diarize, so
`speaker` finally carries content. It carries the vendor's raw label
("Falante A"), not a role: mapping A to "profissional" is a guess, and a
wrong speaker attribution in a clinical record is worse than a generic one.
"""

import asyncio

import assemblyai as aai

from app.config import Settings
from app.core.exceptions import TranscriptionFailedError
from app.models.transcription import Segment, TranscriptionResponse


class AssemblyAITranscriptionService:
    def __init__(self, settings: Settings) -> None:
        aai.settings.api_key = settings.assemblyai_api_key

    async def transcribe(
        self, audio_url: str, content_type: str | None = None
    ) -> TranscriptionResponse:
        transcript = await asyncio.to_thread(self._run, audio_url)

        segments = [
            Segment(
                start=round(utterance.start / 1000, 2),
                end=round(utterance.end / 1000, 2),
                speaker=f"Falante {utterance.speaker}" if utterance.speaker else None,
                text=utterance.text,
            )
            for utterance in (transcript.utterances or [])
        ]

        return TranscriptionResponse(
            text=transcript.text or "",
            language="pt-BR",
            duration_sec=int(transcript.audio_duration or 0),
            provider="assemblyai",
            external_id=str(transcript.id),
            segments=segments,
        )

    def _run(self, audio_url: str):
        """Blocking SDK call, pushed to a thread by the caller."""
        config = aai.TranscriptionConfig(language_code="pt", speaker_labels=True)
        transcript = aai.Transcriber().transcribe(audio_url, config=config)

        if transcript.status == aai.TranscriptStatus.error:
            raise TranscriptionFailedError(transcript.error or "unknown error")

        return transcript
