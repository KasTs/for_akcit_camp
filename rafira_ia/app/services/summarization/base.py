"""Protocol both summarization implementations satisfy."""

from typing import Protocol


class SummarizationService(Protocol):
    async def summarize(
        self,
        consultation_text: str,
        summary_type: str,
        custom_prompt: str | None = None,
    ) -> str: ...
