"""Deterministic, network-free transcription stub.

This is what dev and CI run. It must never depend on anything the container
does not already have at build time, and its output must not vary between
calls (external_id excepted) — the Rails suite is written against it.
"""

import asyncio
import uuid

from app.config import Settings
from app.models.transcription import Segment, TranscriptionResponse

FIXTURE_SEGMENTS = (
    (0.0, 4.5, "profissional", "Bom dia. Como você está se sentindo essa semana?"),
    (
        4.5,
        12.0,
        "paciente",
        "Tenho notado uma melhora no sono, mas ainda sinto ansiedade antes das consultas.",
    ),
)


class StubTranscriptionService:
    def __init__(self, settings: Settings) -> None:
        self._delay = settings.transcription_stub_delay_sec

    async def transcribe(
        self, audio_url: str, content_type: str | None = None
    ) -> TranscriptionResponse:
        await asyncio.sleep(self._delay)
        segments = [
            Segment(start=start, end=end, speaker=speaker, text=text)
            for start, end, speaker, text in FIXTURE_SEGMENTS
        ]
        return TranscriptionResponse(
            text=" ".join(segment.text for segment in segments),
            language="pt-BR",
            duration_sec=42,
            provider="stub",
            external_id=str(uuid.uuid4()),
            segments=segments,
        )
