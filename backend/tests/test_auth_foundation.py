from datetime import timedelta

import pytest
from sqlalchemy import CheckConstraint, UniqueConstraint

from app import create_app
from app.config import session_cookie_secure_from_env, validate_secret_key
from app.models import User, UserRole, normalize_username
from app.models.user import MIN_PASSWORD_LENGTH


def test_username_normalization_and_model_assignment():
    assert normalize_username("  Tech.One  ") == "tech.one"
    user = User(username="  Tech.One  ", full_name="  Field Technician  ", role=UserRole.TECHNICIAN)
    assert user.username == "tech.one"
    assert user.full_name == "Field Technician"


@pytest.mark.parametrize("username", ["", "  ", "name with space", "name@", "x" * 65])
def test_invalid_usernames_are_rejected(username):
    with pytest.raises(ValueError):
        normalize_username(username)


def test_password_is_hashed_and_checked():
    user = User(username="tech", full_name="Technician", role=UserRole.TECHNICIAN)
    password = "x" * MIN_PASSWORD_LENGTH
    user.set_password(password)

    assert user.password_hash.startswith("scrypt:")
    assert password not in user.password_hash
    assert user.check_password(password)
    assert not user.check_password("y" * MIN_PASSWORD_LENGTH)
    assert "password_hash" not in repr(user)


def test_password_minimum_and_role_values():
    user = User(username="tech", full_name="Technician", role=UserRole.TECHNICIAN)
    with pytest.raises(ValueError, match="at least 12 characters"):
        user.set_password("x" * (MIN_PASSWORD_LENGTH - 1))
    assert {role.value for role in UserRole} == {"ADMIN", "TECHNICIAN"}
    with pytest.raises(ValueError, match="Invalid user role"):
        user.role = "FARMER"


def test_named_model_constraints():
    constraints = User.__table__.constraints
    names = {constraint.name for constraint in constraints}
    assert {"uq_users_username", "ck_users_role", "ck_users_username_format"} <= names
    assert any(isinstance(constraint, UniqueConstraint) and constraint.name == "uq_users_username" for constraint in constraints)
    assert any(isinstance(constraint, CheckConstraint) and constraint.name == "ck_users_role" for constraint in constraints)


@pytest.mark.parametrize("value", [None, "", "  ", "CHANGE_ME", "your-secret-key", "example-secret-key"])
def test_placeholder_secret_keys_are_rejected(value):
    with pytest.raises(ValueError, match="strong SECRET_KEY"):
        validate_secret_key(value)


def test_session_configuration_and_cli_registration(monkeypatch):
    app = create_app()
    assert app.config["SESSION_COOKIE_NAME"] == "sugarcane_session"
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert app.config["SESSION_COOKIE_PATH"] == "/"
    assert app.config["SESSION_COOKIE_SECURE"] is False
    assert app.config["PERMANENT_SESSION_LIFETIME"] == timedelta(hours=8)
    assert app.config["SESSION_REFRESH_EACH_REQUEST"] is False
    assert "create-admin" in app.cli.commands
    assert not app.cli.commands["create-admin"].params

    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    assert create_app().config["SESSION_COOKIE_SECURE"] is True


def test_invalid_secure_cookie_configuration_is_rejected():
    assert session_cookie_secure_from_env(None) is False
    with pytest.raises(ValueError, match="must be true or false"):
        session_cookie_secure_from_env("sometimes")
