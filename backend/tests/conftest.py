import secrets

import pytest


@pytest.fixture(autouse=True)
def isolated_app_environment(monkeypatch):
    # Tests never read the real backend .env or connect to the thesis database.
    monkeypatch.setattr("app.config.load_dotenv", lambda *args, **kwargs: False)
    monkeypatch.setenv("SECRET_KEY", secrets.token_hex(32))
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("DB_PASSWORD", "")
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_PORT", "99999")
    monkeypatch.setenv("DB_NAME", "nonexistent_test_database")
    monkeypatch.setenv("DB_USER", "test_user_only")
