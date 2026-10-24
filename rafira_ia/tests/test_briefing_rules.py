import pytest

DOSSIER = {
    "kind": "return_briefing",
    "patient": {"allergy_status": "unknown"},
    "encounters": [
        {
            "id": "780",
            "recorded_at": "2026-01-10T09:00:00",
            "service": "Primeira consulta",
        },
        {
            "id": "812",
            "recorded_at": "2026-05-14T09:00:00",
            "service": "Consulta de retorno",
            "cid": {"code": "I21.9", "description": "Infarto agudo do miocárdio"},
        },
    ],
    "documents": [{"kind": "pedido_exames", "encounter_id": "812"}],
}


@pytest.fixture
def client(make_client):
    return make_client(BRIEFING_STUB_DELAY_SEC=0)


def test_rule_4_empty_dossier_yields_an_empty_briefing(client):
    body = client.post("/briefings", json={"encounters": []}).json()

    assert body["since_last"] is None
    assert body["evolution"] == []
    assert body["watch_points"] == []
    assert body["model"] == "stub"
    assert "Nenhum encontro anterior" in body["summary"]


def test_rule_4_absent_encounters_key_behaves_the_same(client):
    assert client.post("/briefings", json={}).json()["since_last"] is None


def test_rule_1_unknown_allergy_status_becomes_a_watch_point(client):
    """Ausência nunca é negação: 'ninguém perguntou' vai para watch_points,
    nunca vira silêncio nem virar 'paciente nega alergias'."""
    body = client.post("/briefings", json=DOSSIER).json()

    assert [w["reason"] for w in body["watch_points"]] == ["missing_data"]
    assert "alergias" in body["watch_points"][0]["text"].lower()


def test_rule_1_known_allergy_status_produces_no_watch_point(client):
    dossier = {**DOSSIER, "patient": {"allergy_status": "none_reported"}}

    assert client.post("/briefings", json=dossier).json()["watch_points"] == []


def test_rule_2_every_evolution_entry_cites_a_real_encounter(client):
    body = client.post("/briefings", json=DOSSIER).json()
    known = {"780", "812"}

    assert body["evolution"]
    for entry in body["evolution"]:
        assert entry["source_encounter_ids"]
        assert set(entry["source_encounter_ids"]) <= known


def test_rule_2_since_last_items_cite_only_the_latest_encounter(client):
    body = client.post("/briefings", json=DOSSIER).json()

    assert body["since_last"]["encounter_id"] == "812"
    for item in body["since_last"]["items"]:
        assert item["source_encounter_ids"] == ["812"]


def test_stub_does_no_cross_encounter_synthesis(client):
    """Uma entrada por encontro, citando só o próprio id. Síntese entre
    encontros é capacidade do modo real — não construir UI contra isso."""
    body = client.post("/briefings", json=DOSSIER).json()

    assert len(body["evolution"]) == 2
    assert [e["source_encounter_ids"] for e in body["evolution"]] == [["780"], ["812"]]


def test_rule_3_restates_the_cid_exactly_as_filed(client):
    """Regression guard for CID *attribution*, not just presence: joining
    every entry's text before asserting (the old shape of this test) would
    stay green even if encounter 812's CID leaked onto encounter 780's
    entry — precisely the misattribution rule 3 exists to prevent."""
    body = client.post("/briefings", json=DOSSIER).json()
    entries_by_source = {tuple(e["source_encounter_ids"]): e["text"] for e in body["evolution"]}

    assert "I21.9" in entries_by_source[("812",)]
    assert "Infarto agudo do miocárdio" in entries_by_source[("812",)]
    assert "I21.9" not in entries_by_source[("780",)]
    assert "Infarto agudo do miocárdio" not in entries_by_source[("780",)]


def test_rule_2_encounter_without_an_id_produces_no_citing_entry(client):
    """An id-less encounter is a legal request — every dossier field is
    optional — but under the stub's 1:1 granularity (no cross-encounter
    synthesis, see the module docstring) it has no id of its own left to
    cite. Real mode agrees for the same reason: known_encounter_ids
    excludes falsy ids, so keep_sourced drops any entry citing "" exactly
    the same way. A document that would only match that same empty id
    must not produce a since_last claim citing "" either."""
    dossier = {
        "encounters": [{"recorded_at": "2026-05-14T09:00:00", "service": "Retorno"}],
        "documents": [{"kind": "pedido_exames", "encounter_id": ""}],
    }

    body = client.post("/briefings", json=dossier).json()

    assert body["evolution"] == []
    assert body["since_last"]["items"] == []


def test_days_ago_is_always_an_int_even_with_a_broken_timestamp(client):
    dossier = {"encounters": [{"id": "1", "recorded_at": "não é data"}]}

    assert client.post("/briefings", json=dossier).json()["since_last"]["days_ago"] == 0


def test_documents_from_older_encounters_are_not_since_last(client):
    dossier = {**DOSSIER, "documents": [{"kind": "receita", "encounter_id": "780"}]}

    assert client.post("/briefings", json=dossier).json()["since_last"]["items"] == []
