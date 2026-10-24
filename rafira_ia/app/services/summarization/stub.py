"""Deterministic summarization stub. Network-free, no vendor key needed."""

from app.config import Settings

STUB_SUMMARIES = {
    "doctor": "Resumo técnico (stub): consulta registrada, sem intercorrências relatadas.",
    "patient": (
        "Resumo simplificado (stub): sua consulta foi registrada. Siga as orientações combinadas."
    ),
}


class StubSummarizationService:
    def __init__(self, settings: Settings) -> None:
        # settings is accepted, unused, and not stored: app/dependencies.py
        # constructs every stub/service the same way (`Cls(settings)`), and
        # nothing here varies by configuration — unlike the transcription
        # and briefing stubs, which do read a configurable delay off it.
        pass

    async def summarize(
        self,
        consultation_text: str,
        summary_type: str,
        custom_prompt: str | None = None,
    ) -> str:
        return STUB_SUMMARIES[summary_type]
