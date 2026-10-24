"""FastAPI application entry point for the Rafira AI service."""

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings, get_settings
from app.routers import agent, briefing, summarization, transcription

# Validate settings at app creation time to fail fast on configuration errors
get_settings()

app = FastAPI(
    title="RAFIRA AI",
    description=(
        "Serviço de IA da Rafira: transcrição de consultas, briefing de "
        "retorno e resumo de consulta. Contrato em docs/contract.md."
    ),
    version="2.0.0",
)

app.include_router(transcription.router)
app.include_router(briefing.router)
app.include_router(summarization.router)
app.include_router(agent.router)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Render every error as {"error": ...}, never FastAPI's {"detail": ...}.

    The Rails client puts this body verbatim into Transcript#failure_reason,
    which the professional actually reads.
    """
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


def _validation_error_message(errors: list[dict]) -> str:
    """Render pydantic/FastAPI validation errors without echoing the body.

    `errors()` entries carry `input` (and sometimes `ctx`, `url`) alongside
    `loc`/`msg` — and for a `missing` error, `input` is the *parent
    object*, not the missing field's value, so a `str(exc)` naively built
    from the whole exception can carry a full request body — patient name,
    CPF, chief complaint — into a response body the Rails client writes
    into a field a clinician reads. Only `loc` and `msg` ever describe the
    failure without repeating what was submitted.
    """
    parts = []
    for error in errors:
        location = ".".join(str(piece) for piece in error["loc"])
        parts.append(f"{location}: {error['msg']}" if location else error["msg"])
    return "; ".join(parts)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"error": _validation_error_message(exc.errors())})


@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
    """Same treatment as RequestValidationError above, for routes that
    validate the body by hand instead of declaring a Pydantic model
    parameter.

    POST /briefings does this deliberately, to control the exact 422
    message for a body that isn't a JSON object at all — but that means it
    bypasses FastAPI's own automatic conversion of pydantic errors into
    RequestValidationError. Without this handler, a dossier that is a JSON
    object but carries a field of the wrong type would surface as a bare
    FastAPI/Starlette 500, not the {"error": ...} shape every other failure
    on this service returns.
    """
    return JSONResponse(status_code=422, content={"error": _validation_error_message(exc.errors())})


@app.get("/health", tags=["Health"], summary="Health check")
async def health_check(
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> dict[str, str]:
    """Report liveness and the mode the process is running in.

    Answers "ok" regardless of which endpoints are usable in the current
    mode: it means the process is up, not that every endpoint is fully
    implemented in that mode.
    """
    return {"status": "ok", "mode": settings.transcription_mode}
