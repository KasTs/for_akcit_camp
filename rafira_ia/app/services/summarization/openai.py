"""Consultation summarization backed by OpenAI.

Distinct job from /briefings: this summarizes ONE consultation transcript
for a doctor or a patient; the briefing synthesizes several encounters from
a structured dossier.
"""

from openai import AsyncOpenAI, OpenAIError

from app.config import Settings
from app.core.exceptions import PromptNotFoundError, SummarizationFailedError

DEFAULT_PROMPT_FILENAMES = {
    "doctor": "default_doctor.txt",
    "patient": "default_patient.txt",
}


class OpenAISummarizationService:
    def __init__(self, settings: Settings) -> None:
        # No Rails caller exists yet for /summaries (see docs/contract.md),
        # so there is no established Rails-side read timeout for this
        # endpoint specifically. Tied instead to Ai::BriefingClient::READ_TIMEOUT
        # (90s) — the nearest established budget for a synchronous OpenAI
        # call from this service — rather than leaving the AsyncOpenAI SDK
        # defaults (timeout=600s, max_retries=2) in place, which could hold
        # a call open for ~30 minutes across three attempts.
        self._client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=30.0, max_retries=1)
        self._model = settings.openai_model
        self._prompts_dir = settings.prompts_dir

    async def summarize(
        self,
        consultation_text: str,
        summary_type: str,
        custom_prompt: str | None = None,
    ) -> str:
        system_prompt = custom_prompt or self._load_default_prompt(summary_type)

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": consultation_text},
                ],
                temperature=0.3,
            )
        except OpenAIError as error:
            raise SummarizationFailedError(str(error)) from error

        summary = response.choices[0].message.content
        if not summary:
            raise SummarizationFailedError("empty response from OpenAI")

        return summary.strip()

    def _load_default_prompt(self, summary_type: str) -> str:
        path = self._prompts_dir / DEFAULT_PROMPT_FILENAMES[summary_type]
        if not path.is_file():
            raise PromptNotFoundError(str(path))
        return path.read_text(encoding="utf-8").strip()
