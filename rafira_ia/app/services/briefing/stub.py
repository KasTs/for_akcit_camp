"""Deterministic briefing stub.

Unlike the /transcriptions stub, this builds every field *from the request
body* — that is the only thing a stub can honestly guarantee without a model
behind it. It never invents clinical content.

Two limits worth knowing when debugging against it:

- No cross-encounter synthesis. evolution is strictly one entry per
  encounter, citing only that encounter's own id, even though the contract's
  own example shows an entry citing three ids. That is a real-mode
  capability; this 1:1 granularity is a conservative simplification, not the
  shape to build a UI against.
- Fields accepted and ignored: medications, patient.background/sex/age,
  encounters[].sections/addenda/attachments, documents[].content/issued_at,
  locale, upcoming_appointment. Two dossiers differing only in an ignored
  field produce identical responses.
"""

import asyncio

from app.config import Settings
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

MODEL_NAME = "stub"


class StubBriefingService:
    def __init__(self, settings: Settings) -> None:
        self._delay = settings.briefing_stub_delay_sec

    async def generate(self, dossier: BriefingRequest) -> BriefingResponse:
        await asyncio.sleep(self._delay)

        if not dossier.encounters:
            return empty_briefing(MODEL_NAME)

        known = known_encounter_ids(dossier)
        last = dossier.encounters[-1]
        last_id = last.id or ""

        # Only documents tied to the most recent encounter are eligible:
        # that is the one citation that is actually true for a "what's new
        # since last time" claim. kind is "note", not "pending" — this stub
        # cannot know a document's real workflow state, and refuses to
        # assert one it would only be guessing at.
        items = [
            Claim(
                text=f'Documento "{document.kind or "documento"}" registrado no último encontro.',
                kind="note",
                source_encounter_ids=[last_id],
                confidence="high",
            )
            for document in dossier.documents
            if document.encounter_id == last_id
        ]
        # Rule 2 again: a document whose only eligible citation is an
        # id-less last encounter (last_id == "") must not survive either.
        items = keep_sourced(items, known)

        evolution = []
        for encounter in dossier.encounters:
            service = encounter.service or "Atendimento"
            recorded = encounter.recorded_at or "data não informada"
            text = f"{service} registrado em {recorded}."
            if encounter.cid and encounter.cid.description:
                # Quoting the chart, not proposing a diagnosis (rule 3).
                text += f" CID registrado: {encounter.cid.code} — {encounter.cid.description}."
            evolution.append(
                EvolutionEntry(
                    topic=service,
                    text=text,
                    source_encounter_ids=[encounter.id or ""],
                    confidence="high",
                )
            )
        # Rule 2, enforced the same way the real path enforces it (see
        # validation.py): an encounter with no id has no id of its own left
        # to cite under this stub's 1:1 granularity, so its entry is
        # dropped here rather than shipped citing "".
        evolution = keep_sourced(evolution, known)

        watch_points = []
        allergy_status = dossier.patient.allergy_status if dossier.patient else None
        if allergy_status in (None, "unknown"):
            watch_points.append(
                WatchPoint(
                    text="Status de alergias não informado no dossiê.",
                    reason="missing_data",
                    confidence="high",
                )
            )

        return BriefingResponse(
            summary=(
                f"{len(dossier.encounters)} encontro(s) considerado(s) no período "
                f"observado, o mais recente em "
                f"{last.recorded_at or 'data não informada'}."
            ),
            since_last=SinceLast(
                encounter_id=last_id, days_ago=days_ago(last.recorded_at), items=items
            ),
            evolution=evolution,
            watch_points=watch_points,
            model=MODEL_NAME,
            generated_at=generated_at(),
        )
