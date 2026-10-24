"""Briefing synthesis backed by OpenAI.

The model is asked for prose and citations only. Everything that is
arithmetic — which encounter is the latest, how many days ago it was — is
computed here: a model has no business guessing at a subtraction, and the
contract types days_ago as an int that clients rely on.

Rule 2 is enforced after the model answers, not merely requested in the
prompt. See validation.py.
"""

import json
import logging

from openai import AsyncOpenAI, OpenAIError
from pydantic import BaseModel, Field

from app.config import Settings
from app.core.exceptions import BriefingFailedError, PromptNotFoundError
from app.models.briefing import (
    BriefingRequest,
    BriefingResponse,
    Claim,
    EvolutionEntry,
    SinceLast,
    WatchPoint,
)
from app.services.briefing.base import days_ago, empty_briefing, generated_at
from app.services.briefing.validation import keep_sourced, known_encounter_ids

logger = logging.getLogger(__name__)

PROMPT_FILENAME = "briefing_system.txt"


class LlmBriefing(BaseModel):
    """What the model is asked to produce — prose and citations only."""

    summary: str
    since_last_items: list[Claim] = Field(default_factory=list)
    evolution: list[EvolutionEntry] = Field(default_factory=list)
    watch_points: list[WatchPoint] = Field(default_factory=list)


class OpenAIBriefingService:
    def __init__(self, settings: Settings) -> None:
        # Ai::BriefingClient::READ_TIMEOUT on the Rails side (rafira-web)
        # is 90s. The AsyncOpenAI SDK defaults (timeout=600s, max_retries=2)
        # would let this process keep an original call alive for up to
        # ~30 minutes across three attempts — long after Rails has given up
        # and re-enqueued the job, spending vendor money twice for the same
        # answer. 30s per attempt x up to 2 attempts stays comfortably
        # under that 90s budget; keep this tied to Rails' number if it ever
        # changes.
        self._client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=30.0, max_retries=1)
        self._model = settings.openai_model
        self._prompts_dir = settings.prompts_dir

    async def generate(self, dossier: BriefingRequest) -> BriefingResponse:
        # Rule 4, applied before spending anything: an empty dossier has a
        # known answer, and no token needs to be paid to confirm it.
        if not dossier.encounters:
            return empty_briefing(self._model)

        parsed = await self._ask(dossier)
        known = known_encounter_ids(dossier)

        last = dossier.encounters[-1]

        return BriefingResponse(
            summary=parsed.summary,
            since_last=SinceLast(
                encounter_id=last.id or "",
                days_ago=days_ago(last.recorded_at),
                items=keep_sourced(parsed.since_last_items, known),
            ),
            evolution=keep_sourced(parsed.evolution, known),
            watch_points=parsed.watch_points,
            model=self._model,
            generated_at=generated_at(),
        )

    async def _ask(self, dossier: BriefingRequest) -> LlmBriefing:
        try:
            completion = await self._client.beta.chat.completions.parse(
                model=self._model,
                messages=[
                    {"role": "system", "content": self._system_prompt()},
                    {
                        "role": "user",
                        "content": json.dumps(
                            dossier.model_dump(), ensure_ascii=False, default=str
                        ),
                    },
                ],
                response_format=LlmBriefing,
                temperature=0.2,
            )
        except OpenAIError as error:
            logger.warning("OpenAI briefing request failed: %s", error)
            raise BriefingFailedError(str(error)) from error

        parsed = completion.choices[0].message.parsed
        if parsed is None:
            logger.warning("OpenAI briefing response had no parsed content")
            raise BriefingFailedError("empty response from OpenAI")

        return parsed

    def _system_prompt(self) -> str:
        path = self._prompts_dir / PROMPT_FILENAME
        if not path.is_file():
            logger.warning("Briefing prompt file not found: %s", path)
            raise PromptNotFoundError(str(path))
        return path.read_text(encoding="utf-8").strip()
