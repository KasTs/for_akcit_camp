"""Private service-to-service clinical workflow endpoint."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings, get_settings
from app.core.security import require_token
from app.dependencies import get_clinical_harness
from app.models.agent import AgentRequest, AgentResponse
from app.services.agent import AgentFailure, ClinicalHarness

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Clinical harness"], dependencies=[Depends(require_token)])


def require_private_configuration(settings: Settings = Depends(get_settings)):  # noqa: B008
    if settings.transcription_mode == "real" and not settings.transcription_api_token:
        raise HTTPException(
            status_code=503, detail="Configure o token privado antes de habilitar o harness real."
        )


@router.post(
    "/agent/runs",
    response_model=AgentResponse,
    dependencies=[Depends(require_private_configuration)],
)
async def create_run(
    payload: AgentRequest,
    harness: ClinicalHarness = Depends(get_clinical_harness),  # noqa: B008
):
    try:
        return await harness.run(payload)
    except AgentFailure as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except Exception as error:
        # Never log exception messages: provider errors may contain patient content.
        logger.error("Clinical harness failed (%s)", type(error).__name__)
        raise HTTPException(status_code=500, detail="Falha interna na execução de IA.") from error
