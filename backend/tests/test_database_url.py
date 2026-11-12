import pytest

from app import create_app
from app.config import database_url_from_env


def test_blank_database_url_is_ignored():
    assert database_url_from_env(None) is None
    assert database_url_from_env("   ") is None


@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+psycopg2"])
def test_database_url_uses_psycopg_driver(scheme):
    url = database_url_from_env(
        f"{scheme}://user:pw@ep-x-pooler.example.neon.tech/neondb?sslmode=require"
    )
    assert url.drivername == "postgresql+psycopg"
    assert url.host == "ep-x-pooler.example.neon.tech"
    assert url.database == "neondb"
    assert url.query["sslmode"] == "require"


def test_non_postgres_database_url_is_rejected():
    with pytest.raises(ValueError):
        database_url_from_env("mysql://user:pw@host/db")


def test_database_url_overrides_discrete_settings(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://neon_user:secret@db.example.com/neondb?sslmode=require"
    )
    app = create_app()
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    assert uri.drivername == "postgresql+psycopg"
    assert uri.username == "neon_user"
    assert uri.host == "db.example.com"
    assert app.config["DB_PASSWORD_CONFIGURED"] is True
