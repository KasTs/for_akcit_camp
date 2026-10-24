"""POST /summaries."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.exceptions import GENERIC_ERROR_MESSAGE, PromptNotFoundError, SummarizationFailedError
from app.core.security import require_token
from app.dependencies import get_summarization_service
from app.models.summarization import SummarizationRequest, SummarizationResponse
from app.services.summarization.base import SummarizationService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Summarization"], dependencies=[Depends(require_token)])


@router.post("/summaries", response_model=SummarizationResponse)
async def summarize(
    request: SummarizationRequest,
    service: SummarizationService = Depends(get_summarization_service),  # noqa: B008
) -> SummarizationResponse:
    """Summarize one consultation transcript for a doctor or a patient."""
    try:
        summary = await service.summarize(
            consultation_text=request.consultation_text,
            summary_type=request.summary_type,
            custom_prompt=request.custom_prompt,
        )
    except SummarizationFailedError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=error.reason) from error
    except PromptNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)
        ) from error
    except Exception as error:
        logger.exception("Unexpected error in POST /summaries")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=GENERIC_ERROR_MESSAGE
        ) from error

    return SummarizationResponse(summary_type=request.summary_type, summary=summary)
