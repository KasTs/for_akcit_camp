def test_missing_audio_url_is_422(make_client):
    response = make_client().post("/transcriptions", json={})

    assert response.status_code == 422
    assert "error" in response.json()


def test_stub_returns_the_contract_shape(make_client):
    client = make_client(TRANSCRIPTION_STUB_DELAY_SEC=0)

    body = client.post(
        "/transcriptions",
        json={"audio_url": "https://x/a.webm", "content_type": "audio/webm"},
    ).json()

    assert set(body) == {
        "text",
        "language",
        "duration_sec",
        "provider",
        "external_id",
        "segments",
    }
    assert body["language"] == "pt-BR"
    assert body["provider"] == "stub"
    assert body["duration_sec"] == 42
    assert isinstance(body["external_id"], str) and body["external_id"]


def test_stub_segments_carry_speakers(make_client):
    client = make_client(TRANSCRIPTION_STUB_DELAY_SEC=0)

    segments = client.post("/transcriptions", json={"audio_url": "https://x/a.webm"}).json()[
        "segments"
    ]

    assert [s["speaker"] for s in segments] == ["profissional", "paciente"]
    assert all(set(s) == {"start", "end", "speaker", "text"} for s in segments)


def test_stub_is_deterministic_except_for_external_id(make_client):
    """CI e as specs do Rails dependem disso."""
    client = make_client(TRANSCRIPTION_STUB_DELAY_SEC=0)
    payload = {"audio_url": "https://x/a.webm"}

    first = client.post("/transcriptions", json=payload).json()
    second = client.post("/transcriptions", json=payload).json()

    first.pop("external_id")
    second.pop("external_id")
    assert first == second


def test_stub_needs_no_network_and_no_vendor_key(make_client):
    client = make_client(TRANSCRIPTION_STUB_DELAY_SEC=0)

    assert client.post("/transcriptions", json={"audio_url": "https://x/a"}).status_code == 200
