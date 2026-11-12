import inspect
import secrets

import pytest

from app import demo_data


def test_demo_seed_requires_matching_explicit_database(monkeypatch):
    monkeypatch.delenv("DEMO_SEED_DATABASE", raising=False)
    monkeypatch.setenv("DB_NAME", "production_db")
    with pytest.raises(RuntimeError):
        demo_data._require_demo_database()

    monkeypatch.setenv("DEMO_SEED_DATABASE", "production_db")
    demo_data._require_demo_database()

    monkeypatch.setenv("DB_NAME", "different_db")
    with pytest.raises(RuntimeError):
        demo_data._require_demo_database()


def test_demo_technician_password_is_required(monkeypatch):
    monkeypatch.delenv("DEMO_TECH_PASSWORD", raising=False)
    with pytest.raises(RuntimeError):
        demo_data._demo_tech_password()

    value = secrets.token_urlsafe(24)
    monkeypatch.setenv("DEMO_TECH_PASSWORD", value)
    assert demo_data._demo_tech_password() == value


def test_source_contains_no_fixed_demo_password():
    assert "Demo-Technician-Password" not in inspect.getsource(demo_data)
