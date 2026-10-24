def test_health_reports_stub_mode_by_default(make_client):
    response = make_client().get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "mode": "stub"}


def test_health_reports_real_mode(make_client):
    client = make_client(
        TRANSCRIPTION_MODE="real",
        ASSEMBLYAI_API_KEY="aai-test",
        OPENAI_API_KEY="sk-test",
    )

    assert client.get("/health").json() == {"status": "ok", "mode": "real"}


def test_boots_in_stub_mode_without_any_vendor_key(make_client):
    """Dev e CI sobem o container sem chave nenhuma. Regressão crítica:
    hoje Settings declara as chaves como obrigatórias e mata o processo."""
    assert make_client().get("/health").status_code == 200


def test_real_mode_without_keys_fails_loudly(make_client):
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="ASSEMBLYAI_API_KEY"):
        make_client(TRANSCRIPTION_MODE="real")
