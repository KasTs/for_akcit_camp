"""Tests for the app-wide 422 handlers (app/main.py).

Finding 2 of the final whole-branch review: both handlers built the error
message with `str(exc)`. Pydantic's own `missing` error carries the
*parent object* as `input` — so a `missing` error on any field echoes the
whole submitted body back, clinical free text included. On the Rails side,
`Transcription::Client.sanitized` / `Ai::BriefingClient.sanitized` strip
markup and URL-shaped tokens and truncate at 300 characters; neither
touches free text, and the sanitized string still lands in
`Transcript#failure_reason`, a field a clinician reads.

These tests post an obviously PHI-shaped string and assert it never
reaches the response body, while the response still names the offending
field so the 422 stays useful for debugging a genuine integration bug.
"""

SUMMARIES_PHI_TEXT = "Paciente Maria da Silva, CPF 123.456.789-00, relata dor toracica."
BRIEFINGS_PHI_TEXT = "Queixa: dor toracica ao esforco, paciente Maria"


def test_summaries_422_does_not_echo_the_submitted_text(make_client):
    """A missing `summary_type` used to pull the whole body — including
    `consultation_text` — into pydantic's `input`, which str(exc) then
    rendered verbatim into the response."""
    client = make_client()

    response = client.post("/summaries", json={"consultation_text": SUMMARIES_PHI_TEXT})

    assert response.status_code == 422
    body = response.json()
    assert SUMMARIES_PHI_TEXT not in body["error"]
    assert "summary_type" in body["error"]


def test_briefings_422_does_not_echo_the_submitted_text(make_client):
    """A wrongly-typed `sections` field used to surface as `input_value` in
    str(exc), carrying the section text straight into the response.

    Uses the reviewer's own reproduction string: short enough that
    pydantic's str(exc) does not truncate it, so a naive "not in" check
    cannot pass by accident of truncation the way it would with a longer
    string (verified against the pinned pydantic while writing this test)."""
    client = make_client(BRIEFING_STUB_DELAY_SEC=0)

    response = client.post(
        "/briefings",
        json={"encounters": [{"id": "1", "sections": BRIEFINGS_PHI_TEXT}]},
    )

    assert response.status_code == 422
    body = response.json()
    assert BRIEFINGS_PHI_TEXT not in body["error"]
    assert "sections" in body["error"]
