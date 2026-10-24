"""Shared contract pieces for both briefing implementations."""

from datetime import datetime, timezone
from typing import Protocol

from app.models.briefing import BriefingRequest, BriefingResponse

EMPTY_SUMMARY = "Nenhum encontro anterior registrado para este paciente no período observado."


class BriefingService(Protocol):
    async def generate(self, dossier: BriefingRequest) -> BriefingResponse: ...


def generated_at() -> str:
    # timezone.utc, not the datetime.UTC alias: the alias needs Python 3.11+
    # and the local dev interpreter is 3.10.13. Same object either way.
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: UP017


def days_ago(recorded_at: str | None) -> int:
    """Always a non-negative int, never None.

    The contract types this as an integer and clients are written against
    that. recorded_at should always be a real DB timestamp coming out of the
    dossier builder, so a missing or unparseable value signals a bug
    upstream — not a legitimate "we don't know". Falling back to 0 keeps the
    type honest instead of degrading it to null.

    A trailing "Z" is normalized to "+00:00" before parsing: 3.12 (the
    image and CI) accepts a "Z" suffix in fromisoformat, but the local dev
    interpreter is 3.10.13, which raises ValueError on it — same input,
    silently different answers (17 vs. the swallowed-exception 0). Rails'
    default ActiveSupport encoding already emits "+00:00", so this is dev
    confusion rather than a production bug, but it costs nothing to remove.
    """
    if recorded_at and recorded_at.endswith("Z"):
        recorded_at = recorded_at[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(recorded_at) if recorded_at else None
    except (TypeError, ValueError):
        parsed = None

    if parsed is None:
        return 0

    now = datetime.now(timezone.utc) if parsed.tzinfo else datetime.now()  # noqa: UP017
    return max((now - parsed).days, 0)


def empty_briefing(model: str) -> BriefingResponse:
    """Rule 4: a first consultation, or nothing since last time.

    A short honest summary and empty lists. Inventing content to avoid an
    empty screen is the worst possible outcome here.
    """
    return BriefingResponse(
        summary=EMPTY_SUMMARY,
        since_last=None,
        evolution=[],
        watch_points=[],
        model=model,
        generated_at=generated_at(),
    )
