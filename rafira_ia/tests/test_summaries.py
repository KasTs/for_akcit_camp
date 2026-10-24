import pytest


@pytest.fixture
def client(make_client):
    return make_client()


def test_stub_summarizes_without_any_vendor_key(client):
    response = client.post(
        "/summaries",
        json={"consultation_text": "paciente relata melhora", "summary_type": "doctor"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary_type"] == "doctor"
    assert body["summary"]


def test_invalid_summary_type_is_422(client):
    response = client.post("/summaries", json={"consultation_text": "x", "summary_type": "nurse"})

    assert response.status_code == 422
    assert "error" in response.json()


def test_empty_consultation_text_is_422(client):
    response = client.post("/summaries", json={"consultation_text": "", "summary_type": "doctor"})

    assert response.status_code == 422


def test_old_path_is_gone(client):
    assert client.post("/api/v1/summarize", json={}).status_code == 404
