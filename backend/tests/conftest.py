import secrets
import os
from pathlib import Path

import pytest


INTEGRATION_TESTS = Path(__file__).parent / "integration"


def pytest_ignore_collect(collection_path, config):
    # Do not import or collect real-DB tests without the explicit opt-in.
    # Return True only for integration paths that must be skipped; otherwise
    # return None so pytest's other ignore mechanisms can still apply.
    if collection_path == INTEGRATION_TESTS:
        if os.environ.get("RUN_POSTGRES_INTEGRATION") != "1":
            return True
    return None


@pytest.fixture(autouse=True)
def isolated_app_environment(request, monkeypatch):
    monkeypatch.setenv("EVIDENCE_STORAGE", "local")
    if request.node.path.is_relative_to(INTEGRATION_TESTS):
        return
    # Tests never read the real backend .env or connect to the thesis database.
    monkeypatch.setattr("app.config.load_dotenv", lambda *args, **kwargs: False)
    monkeypatch.setenv("SECRET_KEY", secrets.token_hex(32))
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("DB_PASSWORD", "")
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_PORT", "99999")
    monkeypatch.setenv("DB_NAME", "nonexistent_test_database")
    monkeypatch.setenv("DB_USER", "test_user_only")
