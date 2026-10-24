"""Models for POST /briefings.

Every dossier field is optional on purpose. An empty object is a *valid*
dossier — the first-consultation case — and must produce a 200 with an
empty briefing, never a validation error. The only 422 on this endpoint is
a body that is not a JSON object at all, which the router checks before
this model ever runs.
"""

from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _none_to_empty(value: Any) -> Any:
    """Rails may serialize an empty association as JSON `null` instead of
    `[]` (an association backed by a column with no `default: []`). Regra 4
    treats an empty dossier as valid, and a null array is just another shape
    of empty — rejecting it would push a well-formed, merely-empty request
    into the 422 this endpoint reserves for "body is not a JSON object"."""
    return [] if value is None else value


def _to_optional_str(value: Any) -> Any:
    """Ids are quoted in the contract, but Rails may serialize them as
    integers. Normalize without turning an actual `None` into the string
    "None"."""
    return None if value is None else str(value)


OptionalId = Annotated[str | None, BeforeValidator(_to_optional_str)]


class Cid(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: str | None = None
    description: str | None = None


class Encounter(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: OptionalId = None
    recorded_at: str | None = None
    service: str | None = None
    cid: Cid | None = None
    sections: Annotated[list[dict[str, Any]], BeforeValidator(_none_to_empty)] = Field(
        default_factory=list
    )
    addenda: Annotated[list[dict[str, Any]], BeforeValidator(_none_to_empty)] = Field(
        default_factory=list
    )
    attachments: Annotated[list[str], BeforeValidator(_none_to_empty)] = Field(default_factory=list)


class Patient(BaseModel):
    model_config = ConfigDict(extra="ignore")

    age: int | None = None
    sex: str | None = None
    allergy_status: str | None = None
    allergies: Any | None = None
    background: dict[str, Any] | None = None


class Document(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: str | None = None
    issued_at: str | None = None
    encounter_id: OptionalId = None
    content: dict[str, Any] | None = None


class BriefingRequest(BaseModel):
    """The dossier. Carries no name, CPF, phone or address — the backend
    strips those before calling out, and sends age instead of birth date."""

    model_config = ConfigDict(extra="ignore")

    kind: str | None = None
    locale: str | None = None
    patient: Patient | None = None
    medications: dict[str, Any] | None = None
    encounters: Annotated[list[Encounter], BeforeValidator(_none_to_empty)] = Field(
        default_factory=list
    )
    documents: Annotated[list[Document], BeforeValidator(_none_to_empty)] = Field(
        default_factory=list
    )
    upcoming_appointment: dict[str, Any] | None = None


class Claim(BaseModel):
    text: str
    kind: str | None = None
    source_encounter_ids: Annotated[list[str], BeforeValidator(_none_to_empty)] = Field(
        default_factory=list
    )
    confidence: str | None = None


class EvolutionEntry(BaseModel):
    topic: str
    text: str
    source_encounter_ids: Annotated[list[str], BeforeValidator(_none_to_empty)] = Field(
        default_factory=list
    )
    confidence: str | None = None


class WatchPoint(BaseModel):
    text: str
    reason: str | None = None
    confidence: str | None = None


class SinceLast(BaseModel):
    encounter_id: str
    days_ago: int
    items: Annotated[list[Claim], BeforeValidator(_none_to_empty)] = Field(default_factory=list)


class BriefingResponse(BaseModel):
    summary: str
    since_last: SinceLast | None = None
    evolution: Annotated[list[EvolutionEntry], BeforeValidator(_none_to_empty)] = Field(
        default_factory=list
    )
    watch_points: Annotated[list[WatchPoint], BeforeValidator(_none_to_empty)] = Field(
        default_factory=list
    )
    model: str
    generated_at: str
