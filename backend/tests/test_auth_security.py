from datetime import timezone

import pytest
from flask import jsonify
from sqlalchemy.exc import SQLAlchemyError

from app import auth, create_app
from app.auth import login_required, roles_required
from app.config import parse_trusted_origins
from app.models import User


LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"
LOGOUT = "/api/v1/auth/logout"
ORIGIN = "http://localhost:3000"
PASSWORD = "test-password-only"


@pytest.fixture
def auth_case(monkeypatch):
    # The real Flask/session pipeline runs, with an in-memory User repository.
    # No test request can reach PostgreSQL through the auth repository methods.
    monkeypatch.setenv("AUTH_TRUSTED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    app = create_app()
    app.testing = True
    user = User(
        id=1,
        username="admin.one",
        full_name="Test Admin",
        role="ADMIN",
        is_active=True,
        auth_version=0,
    )
    user.set_password(PASSWORD)
    users = {user.id: user}
    calls = {"id": 0, "username": 0, "save": 0}
    clock = {"now": 1_750_000_000}

    def by_id(user_id):
        calls["id"] += 1
        return users.get(user_id)

    def by_username(username):
        calls["username"] += 1
        return next((item for item in users.values() if item.username == username), None)

    def save_last_login(item, timestamp):
        calls["save"] += 1
        item.last_login_at = timestamp

    monkeypatch.setattr(auth, "get_user_by_id", by_id)
    monkeypatch.setattr(auth, "get_user_by_username", by_username)
    monkeypatch.setattr(auth, "save_last_login", save_last_login)
    monkeypatch.setattr(auth, "now_epoch_seconds", lambda: clock["now"])

    @app.get("/test/authenticated")
    @login_required
    def authenticated():
        return jsonify({"user_id": auth.g.current_user.id})

    @app.get("/test/admin")
    @roles_required("ADMIN")
    def admin_only():
        return jsonify({"allowed": True})

    @app.route("/test/mutation", methods=["POST", "PUT", "PATCH", "DELETE"])
    @login_required
    def mutation():
        return jsonify({"allowed": True})

    return app.test_client(), user, users, calls, clock


def login(client, origin=ORIGIN, username=" Admin.One ", password=PASSWORD):
    return client.post(
        LOGIN,
        json={"username": username, "password": password},
        headers={"Origin": origin} if origin is not None else {},
    )


def session_state(client):
    with client.session_transaction() as session:
        return dict(session)


def test_login_public_response_and_minimal_session(auth_case):
    client, user, _, calls, clock = auth_case
    response = login(client)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    body = response.get_json()
    assert body["message"] == "Login successful."
    assert body["data"]["user"] == {
        "id": 1, "username": "admin.one", "full_name": "Test Admin", "role": "ADMIN"
    }
    token = body["data"]["csrf_token"]
    assert len(token) == 64
    assert set(body["data"]) == {"user", "csrf_token"}
    assert all(field not in response.get_data(as_text=True) for field in ("password_hash", "auth_version", "issued_at"))
    state = session_state(client)
    assert state == {
        "_permanent": True,
        "user_id": 1,
        "auth_version": 0,
        "issued_at": clock["now"],
        "csrf_token": token,
    }
    assert user.last_login_at.tzinfo == timezone.utc
    assert calls["save"] == 1


def test_login_resets_existing_session(auth_case):
    client, _, _, _, _ = auth_case
    with client.session_transaction() as session:
        session["stale"] = "old"
    assert login(client).status_code == 200
    assert "stale" not in session_state(client)


@pytest.mark.parametrize("origin", [ORIGIN, "http://127.0.0.1:3000"])
def test_trusted_login_origins(auth_case, origin):
    client, _, _, _, _ = auth_case
    assert login(client, origin=origin).status_code == 200


@pytest.mark.parametrize("origin", [None, "http://evil.example", "http://localhost:3001", "null"])
def test_untrusted_or_missing_login_origin(auth_case, origin):
    client, _, _, calls, _ = auth_case
    response = login(client, origin=origin)
    assert response.status_code == 403
    assert calls["username"] == 0
    assert response.headers["Cache-Control"] == "no-store"


def test_origin_config_rejects_wildcards_and_paths():
    assert parse_trusted_origins(None) == (ORIGIN, "http://127.0.0.1:3000")
    for origin in ("*", "http://*.example.com", "http://localhost:3000/path", "http://localhost:bad"):
        with pytest.raises(ValueError):
            parse_trusted_origins(origin)


def test_generic_login_failures(auth_case):
    client, user, users, _, _ = auth_case
    unknown = login(client, username="missing")
    wrong = login(client, password="wrong-password")
    user.is_active = False
    inactive = login(client)
    for response in (unknown, wrong, inactive):
        assert response.status_code == 401
        assert response.get_json() == {"data": None, "message": "Invalid username or password."}
        assert response.headers["Cache-Control"] == "no-store"
    assert session_state(client) == {}
    assert users[1].last_login_at is None


@pytest.mark.parametrize("payload", [
    {}, {"password": PASSWORD}, {"username": "admin.one"},
    {"username": "bad name", "password": PASSWORD},
    {"username": 123, "password": PASSWORD},
    {"username": "admin.one", "password": 123},
    {"username": "admin.one", "password": PASSWORD, "extra": 1},
])
def test_invalid_login_payload(auth_case, payload):
    client, _, _, calls, _ = auth_case
    response = client.post(LOGIN, json=payload, headers={"Origin": ORIGIN})
    assert response.status_code == 400
    assert calls["username"] == 0


def test_non_json_login_rejected(auth_case):
    client, _, _, _, _ = auth_case
    response = client.post(LOGIN, data="username=admin.one", headers={"Origin": ORIGIN})
    assert response.status_code == 400


def test_me_reloads_user_once_and_preserves_csrf(auth_case):
    client, _, _, calls, _ = auth_case
    token = login(client).get_json()["data"]["csrf_token"]
    response = client.get(ME)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.get_json()["data"]["csrf_token"] == token
    assert response.get_json()["data"]["user"]["role"] == "ADMIN"
    assert calls["id"] == 1
    assert session_state(client)["csrf_token"] == token


def test_unauthenticated_me_and_decorators(auth_case):
    client, _, _, _, _ = auth_case
    for path in (ME, "/test/authenticated", "/test/admin"):
        assert client.get(path).status_code == 401
    assert client.post(LOGOUT, headers={"Origin": ORIGIN}).status_code == 401


def test_role_comes_from_current_user(auth_case):
    client, user, _, _, _ = auth_case
    login(client)
    with client.session_transaction() as session:
        session["role"] = "ADMIN"
    assert client.get("/test/admin").status_code == 200
    user.role = "TECHNICIAN"
    assert client.get("/test/admin").status_code == 403
    assert client.get("/test/authenticated").status_code == 200
    assert session_state(client)["user_id"] == 1


@pytest.mark.parametrize("change", ["deactivate", "version", "delete"])
def test_account_change_invalidates_session(auth_case, change):
    client, user, users, _, _ = auth_case
    assert login(client).status_code == 200
    if change == "deactivate":
        user.is_active = False
    elif change == "version":
        user.auth_version += 1
    else:
        users.clear()
    assert client.get(ME).status_code == 401
    assert session_state(client) == {}


@pytest.mark.parametrize("change", ["fresh", "expired", "missing", "malformed", "future"])
def test_absolute_session_expiration(auth_case, change):
    client, _, _, _, clock = auth_case
    login(client)
    with client.session_transaction() as session:
        if change == "expired":
            clock["now"] += 8 * 3600 + 1
        elif change == "missing":
            session.pop("issued_at")
        elif change == "malformed":
            session["issued_at"] = "yesterday"
        elif change == "future":
            session["issued_at"] = clock["now"] + 1
    assert client.get(ME).status_code == (200 if change == "fresh" else 401)
    if change != "fresh":
        assert session_state(client) == {}


@pytest.mark.parametrize("field,value", [
    ("user_id", "1"), ("user_id", None), ("auth_version", "0"),
    ("csrf_token", "invalid"),
])
def test_malformed_session_cleared(auth_case, field, value):
    client, _, _, _, _ = auth_case
    login(client)
    with client.session_transaction() as session:
        session[field] = value
    assert client.get(ME).status_code == 401
    assert session_state(client) == {}


def test_csrf_and_origin_protect_logout_without_clearing_session(auth_case):
    client, _, _, _, _ = auth_case
    token = login(client).get_json()["data"]["csrf_token"]
    for headers in (
        {"Origin": ORIGIN},
        {"Origin": ORIGIN, "X-CSRF-Token": "0" * 64},
        {"Origin": ORIGIN, "X-CSRF-Token": "malformed"},
        {"X-CSRF-Token": token},
        {"Origin": "http://evil.example", "X-CSRF-Token": token},
    ):
        response = client.post(LOGOUT, headers=headers)
        assert response.status_code == 403
        assert session_state(client)["csrf_token"] == token
    response = client.post(LOGOUT, headers={"Origin": ORIGIN, "X-CSRF-Token": token})
    assert response.status_code == 204
    assert response.data == b""
    assert response.headers["Cache-Control"] == "no-store"
    assert session_state(client) == {}
    assert client.get(ME).status_code == 401


def test_csrf_applies_to_future_unsafe_authenticated_routes(auth_case):
    client, _, _, _, _ = auth_case
    token = login(client).get_json()["data"]["csrf_token"]
    for method in ("post", "put", "patch", "delete"):
        send = getattr(client, method)
        assert send("/test/mutation", headers={"Origin": ORIGIN}).status_code == 403
        assert send("/test/mutation", headers={"Origin": ORIGIN, "X-CSRF-Token": token}).status_code == 200


def test_database_error_is_sanitized(auth_case, monkeypatch):
    client, _, _, _, _ = auth_case
    def fail(_):
        raise SQLAlchemyError("internal database detail")
    monkeypatch.setattr(auth, "get_user_by_username", fail)
    response = login(client)
    assert response.status_code == 503
    assert "internal database detail" not in response.get_data(as_text=True)


def test_missing_user_id_clears_partial_auth_state(auth_case):
    client, _, _, _, _ = auth_case
    login(client)
    with client.session_transaction() as session:
        session.pop("user_id")
    assert client.get(ME).status_code == 401
    assert session_state(client) == {}


def test_absolute_deadline_is_not_refreshed_by_me(auth_case):
    client, _, _, _, clock = auth_case
    login(client)
    clock["now"] += 8 * 3600
    assert client.get(ME).status_code == 200
    assert session_state(client)["issued_at"] == 1_750_000_000
    clock["now"] += 1
    assert client.get(ME).status_code == 401
    assert session_state(client) == {}


def test_current_user_lookup_error_is_sanitized(auth_case, monkeypatch):
    client, _, _, _, _ = auth_case
    login(client)
    def fail(_):
        raise SQLAlchemyError("internal database detail")
    monkeypatch.setattr(auth, "get_user_by_id", fail)
    response = client.get(ME)
    assert response.status_code == 503
    assert "internal database detail" not in response.get_data(as_text=True)


def test_login_timestamp_failure_does_not_create_session(auth_case, monkeypatch):
    client, _, _, _, _ = auth_case
    def fail(*_):
        raise SQLAlchemyError("internal database detail")
    monkeypatch.setattr(auth, "save_last_login", fail)
    response = login(client)
    assert response.status_code == 503
    assert "internal database detail" not in response.get_data(as_text=True)
    assert session_state(client) == {}
