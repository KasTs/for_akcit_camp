"""Tests for POST /briefings (app/models/briefing.py) and its entry gate.

Most of these tests validate BriefingRequest directly, without going
through a route. Two of them — added once the route existed (Task 7) — go
through make_client to check the entry gate itself: a body that is not a
JSON object is 422, deliberately never confused with a legitimately empty
dossier (200, per rule 4). app.* is imported inside each test body rather
than at module scope, per the project-wide rule in tests/conftest.py /
tests/test_security.py.
"""

import pytest


def test_empty_object_is_a_valid_dossier():
    """Regra 4: primeira consulta é dossiê legítimo, não erro."""
    from app.models.briefing import BriefingRequest

    assert BriefingRequest.model_validate({}).encounters == []


def test_encounter_id_is_normalized_to_string():
    """O Rails pode serializar o id como inteiro; o contrato fala em string."""
    from app.models.briefing import BriefingRequest

    dossier = BriefingRequest.model_validate({"encounters": [{"id": 812}]})

    assert dossier.encounters[0].id == "812"


def test_document_encounter_id_is_normalized_to_string():
    from app.models.briefing import BriefingRequest

    dossier = BriefingRequest.model_validate({"documents": [{"encounter_id": 812}]})

    assert dossier.documents[0].encounter_id == "812"


def test_unknown_fields_are_accepted_and_ignored():
    """O dossiê carrega campos que este serviço não usa; nunca rejeitar por isso."""
    from app.models.briefing import BriefingRequest

    dossier = BriefingRequest.model_validate(
        {"medications": {"in_use": []}, "upcoming_appointment": {"date": "2026-08-29"}}
    )

    assert dossier.encounters == []


@pytest.mark.parametrize("field", ["encounters", "documents"])
def test_null_top_level_list_is_treated_as_empty(field):
    """Regra 4: um array nulo é só outra forma de vazio — o Rails emite isso
    de graça para uma associação sem `default: []`. Rejeitar aqui faria o
    dossiê cair no 422 reservado para "corpo não é objeto JSON", exatamente
    a confusão que o contrato proíbe (Ruling 17)."""
    from app.models.briefing import BriefingRequest

    dossier = BriefingRequest.model_validate({field: None})

    assert getattr(dossier, field) == []


@pytest.mark.parametrize("field", ["sections", "addenda", "attachments"])
def test_null_encounter_list_field_is_treated_as_empty(field):
    """Mesma regra 4, um nível abaixo: um encontro presente cujo campo de
    lista veio nulo continua sendo um encontro válido, não um erro."""
    from app.models.briefing import BriefingRequest

    dossier = BriefingRequest.model_validate({"encounters": [{"id": 1, field: None}]})

    assert getattr(dossier.encounters[0], field) == []


def test_null_list_fields_are_treated_as_empty_on_response_models():
    """Ruling 18: a T8 faz parse do retorno do LLM direto nesses modelos
    (response_format=LlmBriefing) — um `null` vindo do modelo não pode virar
    exceção em produção, mesmo que hoje nada além dos testes os construa."""
    from app.models.briefing import BriefingResponse, Claim, EvolutionEntry, SinceLast

    assert Claim(text="x", source_encounter_ids=None).source_encounter_ids == []
    assert EvolutionEntry(topic="t", text="x", source_encounter_ids=None).source_encounter_ids == []
    assert SinceLast(encounter_id="1", days_ago=0, items=None).items == []

    response = BriefingResponse(
        summary="s",
        evolution=None,
        watch_points=None,
        model="m",
        generated_at="2026-01-01T00:00:00Z",
    )
    assert response.evolution == []
    assert response.watch_points == []


def test_empty_encounters_list_still_validates():
    """Trava de regressão: `[]` explícito não pode ser afetado pela nova
    coerção de `None` — precisa continuar passando direto como antes."""
    from app.models.briefing import BriefingRequest

    assert BriefingRequest.model_validate({"encounters": []}).encounters == []


@pytest.mark.parametrize("raw, expected", [(None, None), (812, "812"), ("abc", "abc")])
def test_encounter_id_coercion_is_unchanged(raw, expected):
    """Trava de regressão para o fold do finding 3 (Encounter._coerce_id e
    Document._coerce_encounter_id viram um único helper): None continua
    virando None (nunca a string "None"); int e str seguem como antes."""
    from app.models.briefing import Encounter

    assert Encounter(id=raw).id == expected


@pytest.mark.parametrize("raw, expected", [(None, None), (812, "812"), ("abc", "abc")])
def test_document_encounter_id_coercion_is_unchanged(raw, expected):
    from app.models.briefing import Document

    assert Document(encounter_id=raw).encounter_id == expected


@pytest.mark.parametrize("body", [[], "texto", 42, None])
def test_non_object_body_is_422_with_the_contract_message(make_client, body):
    """Deliberadamente diferente de dossiê vazio: confundir os dois deixaria
    um bug de serialização do lado Rails se esconder atrás de um briefing
    vazio plausível."""
    response = make_client(BRIEFING_STUB_DELAY_SEC=0).post("/briefings", json=body)

    assert response.status_code == 422
    assert response.json() == {"error": "request body must be a JSON object"}


def test_malformed_json_is_422_with_the_same_message(make_client):
    response = make_client(BRIEFING_STUB_DELAY_SEC=0).post(
        "/briefings",
        content=b"{not json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert response.json() == {"error": "request body must be a JSON object"}


def test_malformed_nested_field_is_422_not_a_bare_500(make_client):
    """The body *is* a JSON object, so it clears the gate above, but a
    field that fails BriefingRequest's own validation must still come back
    as {"error": ...} — never a bare FastAPI/Starlette 500.

    The router calls BriefingRequest.model_validate(...) by hand (so it can
    control the exact 422 message for the "not an object" case above),
    which bypasses FastAPI's own automatic conversion of pydantic errors
    into RequestValidationError. Without an app-wide handler for
    pydantic's own ValidationError, this would violate the project's
    blanket rule that every error body is {"error": ...}."""
    response = make_client(BRIEFING_STUB_DELAY_SEC=0).post(
        "/briefings", json={"patient": {"age": "not-a-number"}}
    )

    assert response.status_code == 422
    assert "error" in response.json()
