"""Route-level tests for the unified error-handling shape (app/routers/*).

Finding 3 of the final whole-branch review: `app/core/exceptions.py` says
"Each one becomes a specific HTTP status in a router," but three of the
four domain exceptions were never named by any router — only ever caught
by a blind `except Exception` — so an internal bug and a genuine vendor
failure were indistinguishable to the caller. The Rails client treats any
non-2xx as final and never retries (only a transport failure is retried,
by ApplicationJob), so a recoverable internal bug would be permanently
recorded as a failed transcription or briefing. `PromptNotFoundError` was
also inconsistent: 500 in summarization.py, but 502 in briefing.py (where
it fell through to the blind `except Exception`) — same failure, two
answers, and the 502 sends an operator to check OpenAI's status page for
what is actually a missing file inside our own image.

Each concrete stub service's own method is monkeypatched to raise, rather
than going through app.dependency_overrides — this exercises exactly what
get_..._service() hands the router without needing to know how the DI
container is wired.

app.* imports are deferred into each test body rather than done at module
scope, per the project-wide rule in tests/conftest.py / tests/test_security.py.
"""


def _raise(exc):
    async def _raiser(self, *args, **kwargs):
        raise exc

    return _raiser


# ---------------------------------------------------------------- 502s ----


def test_transcription_failed_error_is_502_with_the_reason(make_client, monkeypatch):
    from app.core.exceptions import TranscriptionFailedError
    from app.services.transcription.stub import StubTranscriptionService

    monkeypatch.setattr(
        StubTranscriptionService, "transcribe", _raise(TranscriptionFailedError("vendor down"))
    )
    client = make_client(TRANSCRIPTION_STUB_DELAY_SEC=0)

    response = client.post("/transcriptions", json={"audio_url": "https://x/a.webm"})

    assert response.status_code == 502
    assert response.json() == {"error": "vendor down"}


def test_summarization_failed_error_is_502_with_the_reason(make_client, monkeypatch):
    from app.core.exceptions import SummarizationFailedError
    from app.services.summarization.stub import StubSummarizationService

    monkeypatch.setattr(
        StubSummarizationService, "summarize", _raise(SummarizationFailedError("vendor down"))
    )
    client = make_client()

    response = client.post("/summaries", json={"consultation_text": "x", "summary_type": "doctor"})

    assert response.status_code == 502
    assert response.json() == {"error": "vendor down"}


def test_briefing_failed_error_is_502_with_the_reason(make_client, monkeypatch):
    from app.core.exceptions import BriefingFailedError
    from app.services.briefing.stub import StubBriefingService

    monkeypatch.setattr(StubBriefingService, "generate", _raise(BriefingFailedError("vendor down")))
    client = make_client(BRIEFING_STUB_DELAY_SEC=0)

    response = client.post("/briefings", json={"encounters": [{"id": "1"}]})

    assert response.status_code == 502
    assert response.json() == {"error": "vendor down"}


# ------------------------------------------------------- PromptNotFoundError --


def test_prompt_not_found_is_500_in_summarization(make_client, monkeypatch):
    from app.core.exceptions import PromptNotFoundError
    from app.services.summarization.stub import StubSummarizationService

    monkeypatch.setattr(
        StubSummarizationService, "summarize", _raise(PromptNotFoundError("prompts/x.txt"))
    )
    client = make_client()

    response = client.post("/summaries", json={"consultation_text": "x", "summary_type": "doctor"})

    assert response.status_code == 500
    assert "prompts/x.txt" in response.json()["error"]


def test_prompt_not_found_is_500_in_briefing(make_client, monkeypatch):
    """Previously fell through to the blind `except Exception` in
    briefing.py and came back as a 502."""
    from app.core.exceptions import PromptNotFoundError
    from app.services.briefing.stub import StubBriefingService

    monkeypatch.setattr(
        StubBriefingService,
        "generate",
        _raise(PromptNotFoundError("prompts/briefing_system.txt")),
    )
    client = make_client(BRIEFING_STUB_DELAY_SEC=0)

    response = client.post("/briefings", json={"encounters": [{"id": "1"}]})

    assert response.status_code == 500
    assert "prompts/briefing_system.txt" in response.json()["error"]


# ------------------------------------------------------- generic 500s --


def test_unexpected_error_is_500_and_does_not_leak_in_transcription(make_client, monkeypatch):
    from app.core.exceptions import GENERIC_ERROR_MESSAGE
    from app.services.transcription.stub import StubTranscriptionService

    monkeypatch.setattr(
        StubTranscriptionService, "transcribe", _raise(ValueError("db password is hunter2"))
    )
    client = make_client(TRANSCRIPTION_STUB_DELAY_SEC=0)

    response = client.post("/transcriptions", json={"audio_url": "https://x/a.webm"})

    assert response.status_code == 500
    assert response.json() == {"error": GENERIC_ERROR_MESSAGE}


def test_unexpected_error_is_500_and_does_not_leak_in_summarization(make_client, monkeypatch):
    from app.core.exceptions import GENERIC_ERROR_MESSAGE
    from app.services.summarization.stub import StubSummarizationService

    monkeypatch.setattr(
        StubSummarizationService, "summarize", _raise(ValueError("db password is hunter2"))
    )
    client = make_client()

    response = client.post("/summaries", json={"consultation_text": "x", "summary_type": "doctor"})

    assert response.status_code == 500
    assert response.json() == {"error": GENERIC_ERROR_MESSAGE}


def test_unexpected_error_is_500_and_does_not_leak_in_briefing(make_client, monkeypatch):
    from app.core.exceptions import GENERIC_ERROR_MESSAGE
    from app.services.briefing.stub import StubBriefingService

    monkeypatch.setattr(
        StubBriefingService, "generate", _raise(ValueError("db password is hunter2"))
    )
    client = make_client(BRIEFING_STUB_DELAY_SEC=0)

    response = client.post("/briefings", json={"encounters": [{"id": "1"}]})

    assert response.status_code == 500
    assert response.json() == {"error": GENERIC_ERROR_MESSAGE}


# --------------------------------------------------- /briefings response_model --


def test_briefings_has_a_response_model_for_the_openapi_schema(make_client):
    """It is the most complex endpoint and, before this fix, the only one
    of the three without a response_model — so /docs showed an empty `{}`
    response schema for it (verified against the shipped schema) even
    though the README points people at /docs. The route still returns a
    hand-built JSONResponse at runtime (see the docstring below), so this
    only has to prove the *schema* now names BriefingResponse, not that
    runtime serialization changed."""
    client = make_client(BRIEFING_STUB_DELAY_SEC=0)

    schema = client.get("/openapi.json").json()

    response_schema = schema["paths"]["/briefings"]["post"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert "BriefingResponse" in response_schema.get("$ref", "")
    assert "BriefingResponse" in schema["components"]["schemas"]
