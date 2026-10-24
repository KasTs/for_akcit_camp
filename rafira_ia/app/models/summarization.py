"""Pydantic models for the medical consultation summarization endpoint."""

from typing import Literal

from pydantic import BaseModel, Field

SummaryType = Literal["doctor", "patient"]


class SummarizationRequest(BaseModel):
    """Request payload for the summarization endpoint.

    Attributes:
        consultation_text: Full transcript of the medical consultation.
        summary_type: Target audience for the summary, either "doctor" or
            "patient".
        custom_prompt: Optional custom prompt overriding the default
            template.
    """

    consultation_text: str = Field(
        ..., description="Full transcript of the medical consultation.", min_length=1
    )
    summary_type: SummaryType = Field(
        ..., description="Target audience for the summary: 'doctor' or 'patient'."
    )
    custom_prompt: str | None = Field(
        default=None,
        description="Optional custom prompt that overrides the default template.",
    )


class SummarizationResponse(BaseModel):
    """Response payload returned after a successful summarization.

    Attributes:
        summary_type: The audience type used to generate the summary.
        summary: The generated summary text.
    """

    summary_type: SummaryType
    summary: str
