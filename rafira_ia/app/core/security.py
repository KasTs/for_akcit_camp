"""Optional bearer-token authentication.

The contract has no authentication when TRANSCRIPTION_API_TOKEN is unset —
that is what the local stub and the dev compose rely on. When it *is* set,
every endpoint except /health requires it. Transcription::Client on the
Rails side already sends the header whenever its own env var is present, so
turning auth on is a config change on both sides, never a code change.
"""

import secrets

from fastapi import Depends, HTTPException, Request, status

from app.config import Settings, get_settings


async def require_token(
    request: Request,
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> None:
    """Reject the request when a token is configured and not presented.

    Uses compare_digest so a wrong token cannot be recovered by timing the
    comparison.
    """
    expected = settings.transcription_api_token
    if not expected:
        return

    header = request.headers.get("Authorization", "")
    scheme, _, presented = header.partition(" ")

    if scheme.lower() != "bearer" or not secrets.compare_digest(
        presented.encode(), expected.encode()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing bearer token",
        )
