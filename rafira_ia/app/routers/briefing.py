"""POST /briefings."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.core.exceptions import GENERIC_ERROR_MESSAGE, BriefingFailedError, PromptNotFoundError
from app.core.security import require_token
from app.dependencies import get_briefing_service
from app.models.briefing import BriefingRequest, BriefingResponse
from app.services.briefing.base import BriefingService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Briefing"], dependencies=[Depends(require_token)])

NOT_AN_OBJECT = {"error": "request body must be a JSON object"}


@router.post("/briefings", response_model=BriefingResponse)
async def briefings(
    request: Request,
    service: BriefingService = Depends(get_briefing_service),  # noqa: B008
):
    """Synthesize a return-visit briefing from a dossier.

    A body that is not a JSON object gets 422 — deliberately *not* the same
    as an empty-but-valid dossier ({} or {"encounters": []}, both 200 per
    rule 4). Conflating "malformed" with "legitimately empty" would let a
    bad request, or a serialization bug on the Rails side, hide behind a
    plausible-looking empty briefing instead of surfacing as an error.

    response_model=BriefingResponse is for the OpenAPI schema only — every
    return below is a hand-built JSONResponse (needed for the custom 422
    body above), and FastAPI never runs response_model serialization
    against a Response returned directly, so this cannot change what a
    caller actually receives.
    """
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001 — any parse failure is the same answer
        return JSONResponse(status_code=422, content=NOT_AN_OBJECT)

    if not isinstance(payload, dict):
        return JSONResponse(status_code=422, content=NOT_AN_OBJECT)

    dossier = BriefingRequest.model_validate(payload)

    try:
        result: BriefingResponse = await service.generate(dossier)
    except BriefingFailedError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=error.reason) from error
    except PromptNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)
        ) from error
    except Exception as error:
        logger.exception("Unexpected error in POST /briefings")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=GENERIC_ERROR_MESSAGE
        ) from error

    return JSONResponse(status_code=200, content=result.model_dump())
