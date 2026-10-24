"""Bounded, source-addressable contracts for the clinical harness."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Task = Literal["doctor_summary", "patient_summary", "clinical_question"]


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=120)
    kind: Literal["transcript", "history", "exam_report", "approved_summary", "guideline"]
    text: str = Field(min_length=1, max_length=60000)
    recorded_at: str | None = None
    title: str = Field(min_length=1, max_length=300)
    url: str | None = Field(default=None, max_length=2000)
    version: str | None = Field(default=None, max_length=120)


class AgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: Task
    sources: list[Source] = Field(min_length=1, max_length=50)
    question: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_context(self):
        if len({source.id for source in self.sources}) != len(self.sources):
            raise ValueError("source ids must be unique")
        if sum(len(source.text) for source in self.sources) > 150000:
            raise ValueError("context exceeds character budget")
        if self.task == "clinical_question" and not (self.question or "").strip():
            raise ValueError("clinical_question requires a question")
        if self.task == "patient_summary" and (
            len(self.sources) != 1 or self.sources[0].kind != "approved_summary"
        ):
            raise ValueError("patient_summary requires exactly one approved summary")
        if self.task != "clinical_question" and any(s.kind == "guideline" for s in self.sources):
            raise ValueError("summaries must only use patient documentation")
        return self


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    quote: str = Field(min_length=1, max_length=1500)


class ClinicalClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=3000)
    kind: Literal["recorded_fact", "hypothesis", "suggestion"]
    citations: list[Citation] = Field(min_length=1, max_length=8)


class AgentDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[ClinicalClaim] = Field(max_length=30)
    missing_data: list[str] = Field(max_length=15)
    limitations: list[str] = Field(max_length=15)
    abstained: bool


class AgentResponse(AgentDraft):
    summary: str
    model: str
    generated_at: str
    harness_version: str
    requires_review: bool = True
    steps: list[str]
