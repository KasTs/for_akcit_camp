"""POST /transcriptions."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.exceptions import GENERIC_ERROR_MESSAGE, TranscriptionFailedError
from app.core.security import require_token
from app.dependencies import get_transcription_service
from app.models.transcription import TranscriptionRequest, TranscriptionResponse
from app.services.transcription.base import TranscriptionService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Transcription"], dependencies=[Depends(require_token)])


@router.post("/transcriptions", response_model=TranscriptionResponse)
async def transcribe(
    request: TranscriptionRequest,
    service: TranscriptionService = Depends(get_transcription_service),  # noqa: B008
) -> TranscriptionResponse:
    """Transcribe the audio at a presigned URL.

    Any non-2xx is final for the caller: the Rails job treats a definite
    answer as the result, not as something to retry (retrying a file that
    will never transcribe just spends the vendor's money for the same
    outcome). Only transport failures are retried, by ApplicationJob.
    """
    try:
        return await service.transcribe(request.audio_url, request.content_type)
    except TranscriptionFailedError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=error.reason) from error
    except Exception as error:
        logger.exception("Unexpected error in POST /transcriptions")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=GENERIC_ERROR_MESSAGE
        ) from error
