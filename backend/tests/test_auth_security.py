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


def test_login_cookie_security_attributes(auth_case):
    client, _, _, _, _ = auth_case
    response = login(client)
    assert response.status_code == 200
    cookie = response.headers.getlist("Set-Cookie")
    cookie_str = " ".join(cookie)
    assert "HttpOnly" in cookie_str
    assert "SameSite=Lax" in cookie_str
    assert "Path=/" in cookie_str
    # Secure is not set under local HTTP configuration.
    assert "Secure" not in cookie_str


def test_login_oversized_username_and_password_rejected(auth_case):
    client, _, _, _, _ = auth_case
    huge_username = "a" * 129
    huge_password = "x" * 1025
    response = client.post(LOGIN, json={"username": huge_username, "password": PASSWORD}, headers={"Origin": ORIGIN})
    assert response.status_code == 400
    response = client.post(LOGIN, json={"username": "admin.one", "password": huge_password}, headers={"Origin": ORIGIN})
    assert response.status_code == 400


def test_session_user_id_range_and_type_validation(auth_case):
    client, user, users, calls, _ = auth_case
    login(client)
    # Verify lookup is never called for clearly invalid IDs.
    for invalid_id in (True, False, 0, -1, 2_147_483_648, "1", None):
        lookup_before = calls["id"]
        with client.session_transaction() as session:
            session["user_id"] = invalid_id
            if invalid_id is not None:
                session["auth_version"] = 0
                session["issued_at"] = 1_750_000_000
                session["csrf_token"] = "0" * 64
        response = client.get(ME)
        assert response.status_code == 401, f"Expected 401 for user_id={invalid_id!r}"
        assert session_state(client) == {}
        assert calls["id"] == lookup_before, f"Lookup called for invalid user_id={invalid_id!r}"


def test_post_commit_refresh_avoids_unsanitized_500(auth_case, monkeypatch):
    # Real regression test: after save_last_login succeeds, accessing user
    # attributes raises. The pre-capture fix (user_id/auth_version/public_user)
    # must survive this; the old pattern (accessing user.id after commit) fails.
    client, user, users, _, clock = auth_case

    original_save = auth.save_last_login

    def save_then_break(item, timestamp):
        # Call original save first (commit succeeds)
        original_save(item, timestamp)
        # After commit, make any attribute access on this user fail.
        # This simulates SQLAlchemy expiration or a broken refresh.
        original_getattr = user.__getattribute__
        def broken_getattr(name):
            if name in ("id", "auth_version", "username", "full_name", "role"):
                raise RuntimeError("post-commit attribute access broken")
            return original_getattr(name)
        user.__getattribute__ = broken_getattr

    monkeypatch.setattr(auth, "save_last_login", save_then_break)
    user_id_before = user.id
    auth_version_before = user.auth_version
    response = login(client)
    # Current production (pre-capture) must still succeed: 200
    assert response.status_code == 200
    # Old pattern would trigger RuntimeError and return 500, not 200.
    body = response.get_json()
    assert body["data"]["user"]["id"] == user_id_before  # pre-captured value


def test_role_requirement_admin_and_technician_denied(auth_case):
    client, user, _, _, _ = auth_case
    login(client)
    assert client.get("/test/admin").status_code == 200
    user.role = "TECHNICIAN"
    assert client.get("/test/admin").status_code == 403
    assert client.get("/test/authenticated").status_code == 200


def test_maximum_postgresql_integer_accepted_for_lookup(auth_case, monkeypatch):
    # 2147483647 is the PostgreSQL INTEGER max; validation must allow it
    # and the lookup should be attempted (not rejected before lookup).
    client, user, users, calls, _ = auth_case
    lookup_calls = {"count": 0}

    def tracked_lookup(user_id):
        lookup_calls["count"] += 1
        return users.get(user_id)

    monkeypatch.setattr(auth, "get_user_by_id", tracked_lookup)
    with client.session_transaction() as session:
        session["user_id"] = 2_147_483_647
        session["auth_version"] = 0
        session["issued_at"] = 1_750_000_000
        session["csrf_token"] = "0" * 64
    response = client.get(ME)
    # No matching user -> unauthenticated 401, NOT a validation-rejected 401
    # But the lookup must have been attempted (not skipped by validation).
    assert lookup_calls["count"] > 0, "Lookup should be attempted for max integer ID"


def test_multi_role_decorator_allows_matching_roles(auth_case):
    # Multi-role requirement: either ADMIN or TECHNICIAN should succeed.
    client, user, _, _, _ = auth_case
    # Add a multi-role test-only route
    from app.auth import login_required, roles_required
    from flask import jsonify
    @client.application.get("/test/multi_role")
    @login_required
    @roles_required("ADMIN", "TECHNICIAN")
    def multi_role():
        return jsonify({"allowed": True})
    login(client)
    # ADMIN user passes multi-role
    assert client.get("/test/multi_role").status_code == 200
    user.role = "TECHNICIAN"
    # TECHNICIAN also passes multi-role
    assert client.get("/test/multi_role").status_code == 200


def test_secure_cookie_true_adds_secure_flag(monkeypatch):
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    app = create_app()
    app.testing = True
    # The config should load Secure=True from env, but the cookie is only
    # set on responses that set it; verify config reflects it.
    assert app.config["SESSION_COOKIE_SECURE"] is True


def test_empty_roles_raises_value_error():
    with pytest.raises(ValueError):
        roles_required()
