"""Application configuration loaded from environment variables."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Mode = Literal["stub", "real"]


class Settings(BaseSettings):
    """Runtime configuration sourced from environment variables.

    TRANSCRIPTION_MODE governs all three endpoints — it is one "are we
    allowed to reach a real backend" decision, not one per job. The name is
    imprecise for a service with three jobs, and stays anyway: it is what
    rafira-web's compose already sets, and renaming would cost churn for a
    cosmetic gain.
    """

    transcription_mode: Mode = "stub"
    transcription_stub_delay_sec: float = 2.0
    briefing_stub_delay_sec: float = 1.0
    transcription_api_token: str | None = None

    assemblyai_api_key: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    prompts_dir: Path = Path("prompts")

    model_config = SettingsConfigDict(
        env_file=os.getenv("RAFIRA_ENV_FILE", ".env"),
        extra="ignore",
    )

    @model_validator(mode="after")
    def _require_vendor_keys_in_real_mode(self) -> "Settings":
        """Fail at boot, naming the variable, instead of at first request.

        Vendor keys are optional on purpose: stub mode is what dev and CI
        run, and must never require an account with anybody.
        """
        if self.transcription_mode != "real":
            return self

        missing = [
            name
            for name, value in (
                ("ASSEMBLYAI_API_KEY", self.assemblyai_api_key),
                ("OPENAI_API_KEY", self.openai_api_key),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"TRANSCRIPTION_MODE=real requires: {', '.join(missing)}")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return a cached instance of the application settings."""
    return Settings()
