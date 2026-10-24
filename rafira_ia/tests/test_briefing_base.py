"""Tests for shared briefing helpers (app/services/briefing/base.py).

app.* imports are deferred into each test body rather than done at module
scope, per the project-wide rule in tests/conftest.py / tests/test_security.py:
Settings.model_config resolves env_file at class-definition time, so an
unguarded module-scope import of app.config — even a transitive one —
would leak the developer's real .env into the rest of the session.
app.services.briefing.base does not import app.config today, but the
standing constraint defers unconditionally regardless.
"""

from datetime import datetime, timedelta, timezone


def test_days_ago_parses_a_trailing_z_suffix():
    """datetime.fromisoformat parses a trailing "Z" on Python 3.12 (the
    image and CI) but raises ValueError on it on Python 3.10.13 (what the
    team runs locally) — and the surrounding except swallows that into a
    silent 0, so the same request looks fine in the image and wrong on a
    laptop. Rails' default ActiveSupport encoding emits "+00:00" instead,
    which is why this is dev-confusion rather than a production bug — but
    normalizing "Z" to "+00:00" before parsing costs nothing and removes
    the discrepancy."""
    from app.services.briefing.base import days_ago

    # timezone.utc, not the datetime.UTC alias: same reason as base.py's own
    # generated_at() — the alias needs Python 3.11+, and the local dev
    # interpreter is 3.10.13.
    now = datetime.now(timezone.utc)  # noqa: UP017
    ten_days_ago = (now - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")

    assert days_ago(ten_days_ago) == 10


def test_days_ago_still_handles_an_explicit_utc_offset():
    """Regression guard: Rails' own encoding ("...-03:00" / "...+00:00")
    must keep working exactly as before this fix."""
    from app.services.briefing.base import days_ago

    now = datetime.now(timezone.utc)  # noqa: UP017 — see the note above
    five_days_ago = (now - timedelta(days=5)).isoformat()

    assert days_ago(five_days_ago) == 5


def test_days_ago_falls_back_to_zero_for_unparseable_input():
    """Trava de regressão: o fallback continua existindo depois da
    normalização do sufixo Z — uma string que não é data nenhuma ainda cai
    para 0 em vez de propagar a exceção."""
    from app.services.briefing.base import days_ago

    assert days_ago("não é data") == 0
    assert days_ago(None) == 0
