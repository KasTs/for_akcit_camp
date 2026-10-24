"""Pydantic models for POST /transcriptions.

Contract consumer: backend/app/services/transcription/client.rb in
rafira-web. audio_url is a presigned GET the vendor fetches directly — the
bytes never pass through the Rails process, and never through this one
either.
"""

from pydantic import BaseModel, Field


class Segment(BaseModel):
    """One diarized chunk of the transcript.

    speaker is None when the provider has no diarization. The frontend
    already treats a missing speaker as a normal, expected state, so this
    must stay honest rather than guess a role.
    """

    start: float
    end: float
    speaker: str | None = None
    text: str


class TranscriptionRequest(BaseModel):
    audio_url: str = Field(..., description="Presigned GET URL for the audio.")
    content_type: str | None = Field(
        default=None, description="MIME type reported by the browser recorder."
    )


class TranscriptionResponse(BaseModel):
    text: str
    language: str
    duration_sec: int
    provider: str
    external_id: str
    segments: list[Segment] = Field(default_factory=list)
