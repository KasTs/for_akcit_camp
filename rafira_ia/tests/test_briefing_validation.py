"""Tests for the rule-2 validator (app/services/briefing/validation.py).

Regra 2: toda afirmação cita a fonte, e a citação só vale se resolver a um
encontro de fato presente no request — um id plausível mas inexistente
(o que um LLM produz sem esforço) não basta.

app.* imports are deferred into each test/helper body rather than done at
module scope, per the project-wide rule in tests/conftest.py /
tests/test_security.py (Settings.model_config resolves env_file at
class-definition time, so an unguarded module-scope import of app.config —
even a transitive one — would leak the developer's real .env into the rest
of the session). Neither app.models.briefing nor
app.services.briefing.validation imports app.config today, but the
standing constraint defers unconditionally, the same way
tests/test_briefing_gate.py already does for these same models.
"""


def _dossier(*ids):
    from app.models.briefing import BriefingRequest

    return BriefingRequest.model_validate({"encounters": [{"id": i} for i in ids]})


def _entry(*ids):
    from app.models.briefing import EvolutionEntry

    return EvolutionEntry(topic="t", text="x", source_encounter_ids=list(ids))


def test_known_ids_come_from_the_request_only():
    from app.services.briefing.validation import known_encounter_ids

    assert known_encounter_ids(_dossier("780", "812")) == {"780", "812"}


def test_entry_citing_a_real_id_is_kept():
    from app.services.briefing.validation import keep_sourced

    known = {"812"}

    assert keep_sourced([_entry("812")], known) == [_entry("812")]


def test_entry_citing_a_forged_id_is_dropped():
    """O ponto inteiro da regra 2: um LLM inventa id com naturalidade."""
    from app.services.briefing.validation import keep_sourced

    known = {"812"}

    assert keep_sourced([_entry("999")], known) == []


def test_entry_mixing_real_and_forged_ids_is_dropped_entirely():
    """Não se corrige o id nem se devolve pela metade."""
    from app.services.briefing.validation import keep_sourced

    known = {"812"}

    assert keep_sourced([_entry("812", "999")], known) == []


def test_entry_citing_nothing_is_dropped():
    """Afirmação sem fonte é exatamente o que a regra proíbe."""
    from app.services.briefing.validation import keep_sourced

    assert keep_sourced([_entry()], {"812"}) == []


def test_dropping_everything_is_an_acceptable_outcome():
    """Regra 4: honestamente vazio é melhor que conteúdo inventado."""
    from app.services.briefing.validation import keep_sourced

    assert keep_sourced([_entry("999"), _entry("998")], {"812"}) == []
