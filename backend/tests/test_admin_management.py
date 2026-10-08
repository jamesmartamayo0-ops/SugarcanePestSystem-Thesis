import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import auth, create_app
from app.models import User
from app.routes import admin as admin_module

LIST = "/api/v1/admin/users"
CREATE = "/api/v1/admin/users"
STATUS = lambda user_id: f"/api/v1/admin/users/{user_id}/status"  # noqa: E731
LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"
ORIGIN = "http://localhost:3000"
ADMIN_PASSWORD = "admin-password-123"
TECH_PASSWORD = "technician-pass-123"


@pytest.fixture
def admin_case(monkeypatch):
    monkeypatch.setenv(
        "AUTH_TRUSTED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    )
    app = create_app()
    app.testing = True

    admin = User(
        id=1,
        username="admin.one",
        full_name="Admin One",
        role="ADMIN",
        is_active=True,
        auth_version=0,
    )
    admin.set_password(ADMIN_PASSWORD)
    technician = User(
        id=2,
        username="tech.one",
        full_name="Tech One",
        role="TECHNICIAN",
        is_active=True,
        auth_version=0,
    )
    technician.set_password(TECH_PASSWORD)
    users = {admin.id: admin, technician.id: technician}
    state = {"next_id": 3, "force_integrity_error": False, "locks": 0}
    clock = {"now": 1_750_000_000}

    def by_id(user_id):
        return users.get(user_id)

    def by_username(username):
        return next((u for u in users.values() if u.username == username), None)

    def save_last_login(item, timestamp):
        item.last_login_at = timestamp

    def fake_list():
        return sorted(users.values(), key=lambda u: u.id)

    def fake_taken(username):
        return any(u.username == username for u in users.values())

    def fake_count():
        return sum(
            1 for u in users.values() if u.role == "ADMIN" and bool(u.is_active)
        )

    def fake_persist(user):
        if state["force_integrity_error"]:
            raise IntegrityError("INSERT", {}, Exception("duplicate"))
        if any(u.username == user.username for u in users.values()):
            raise IntegrityError("INSERT", {}, Exception("duplicate"))
        user.id = state["next_id"]
        state["next_id"] += 1
        users[user.id] = user
        return admin_module._admin_public_user(user)

    def fake_commit():
        return None

    def fake_lock():
        state["locks"] += 1

    monkeypatch.setattr(auth, "get_user_by_id", by_id)
    monkeypatch.setattr(auth, "get_user_by_username", by_username)
    monkeypatch.setattr(auth, "save_last_login", save_last_login)
    monkeypatch.setattr(auth, "now_epoch_seconds", lambda: clock["now"])
    monkeypatch.setattr(admin_module, "list_all_users", fake_list)
    monkeypatch.setattr(admin_module, "username_taken", fake_taken)
    monkeypatch.setattr(admin_module, "count_active_admins", fake_count)
    monkeypatch.setattr(admin_module, "persist_new_user", fake_persist)
    monkeypatch.setattr(admin_module, "commit_status_change", fake_commit)
    monkeypatch.setattr(admin_module, "acquire_admin_status_lock", fake_lock)

    return app.test_client(), users, state, clock


def login(client, username, password, origin=ORIGIN):
    return client.post(
        LOGIN,
        json={"username": username, "password": password},
        headers={"Origin": origin} if origin is not None else {},
    )


def login_admin(client):
    response = login(client, "admin.one", ADMIN_PASSWORD)
    assert response.status_code == 200
    return response.get_json()["data"]["csrf_token"]


def login_technician(client):
    response = login(client, "tech.one", TECH_PASSWORD)
    assert response.status_code == 200
    return response.get_json()["data"]["csrf_token"]


def test_unauthenticated_admin_endpoints_return_401(admin_case):
    client, _, _, _ = admin_case
    assert client.get(LIST).status_code == 401
    assert (
        client.post(CREATE, json={}, headers={"Origin": ORIGIN}).status_code == 401
    )
    assert (
        client.patch(
            STATUS(2), json={"is_active": False}, headers={"Origin": ORIGIN}
        ).status_code
        == 401
    )


def test_technician_direct_api_access_denied(admin_case):
    client, _, _, _ = admin_case
    token = login_technician(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    assert client.get(LIST).status_code == 403
    assert (
        client.post(
            CREATE,
            json={
                "username": "tech.two",
                "full_name": "Tech Two",
                "password": "technician-pass-456",
                "role": "TECHNICIAN",
            },
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        client.patch(STATUS(2), json={"is_active": False}, headers=headers).status_code
        == 403
    )


def test_admin_allowed_and_session_role_tampering_cannot_bypass(admin_case):
    client, users, _, _ = admin_case
    login_admin(client)
    with client.session_transaction() as session:
        session["role"] = "TECHNICIAN"
    assert client.get(LIST).status_code == 200
    users[1].role = "TECHNICIAN"
    assert client.get(LIST).status_code == 403
    assert client.get(ME).status_code == 200


def test_admin_unsafe_requires_origin_and_csrf(admin_case):
    client, _, _, _ = admin_case
    token = login_admin(client)
    payload = {
        "username": "tech.two",
        "full_name": "Tech Two",
        "password": "technician-pass-456",
        "role": "TECHNICIAN",
    }
    # Missing/bad origin.
    assert client.post(CREATE, json=payload).status_code == 403
    assert (
        client.post(
            CREATE,
            json=payload,
            headers={"Origin": "http://evil.example", "X-CSRF-Token": token},
        ).status_code
        == 403
    )
    # Missing/bad CSRF.
    assert client.post(CREATE, json=payload, headers={"Origin": ORIGIN}).status_code == 403
    assert (
        client.post(
            CREATE,
            json=payload,
            headers={"Origin": ORIGIN, "X-CSRF-Token": "0" * 64},
        ).status_code
        == 403
    )
    assert (
        client.post(
            CREATE,
            json=payload,
            headers={"Origin": ORIGIN, "X-CSRF-Token": "malformed"},
        ).status_code
        == 403
    )
    # Correct pair allowed.
    response = client.post(
        CREATE, json=payload, headers={"Origin": ORIGIN, "X-CSRF-Token": token}
    )
    assert response.status_code == 201

    status_headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    assert (
        client.patch(STATUS(2), json={"is_active": False}).status_code == 403
    )
    assert (
        client.patch(
            STATUS(2),
            json={"is_active": False},
            headers={"Origin": ORIGIN},
        ).status_code
        == 403
    )
    assert (
        client.patch(
            STATUS(2), json={"is_active": False}, headers=status_headers
        ).status_code
        == 200
    )


def test_list_deterministic_public_fields(admin_case):
    client, _, _, _ = admin_case
    login_admin(client)
    response = client.get(LIST)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    body = response.get_json()
    assert set(body) == {"data", "message"}
    assert set(body["data"]) == {"users"}
    ids = [entry["id"] for entry in body["data"]["users"]]
    assert ids == sorted(ids) == [1, 2]
    for entry in body["data"]["users"]:
        assert set(entry) == {"id", "username", "full_name", "role", "is_active"}
    raw = response.get_data(as_text=True)
    for forbidden in ("password", "password_hash", "auth_version", "csrf", "session"):
        assert forbidden not in raw


def test_create_technician_and_admin(admin_case):
    client, users, _, _ = admin_case
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    for username, role in (("tech.two", "TECHNICIAN"), ("admin.two", "ADMIN")):
        response = client.post(
            CREATE,
            json={
                "username": username,
                "full_name": "New Staff",
                "password": "a-strong-password-123",
                "role": role,
            },
            headers=headers,
        )
        assert response.status_code == 201
        assert response.headers["Cache-Control"] == "no-store"
        body = response.get_json()
        assert body["data"]["user"]["role"] == role
        assert body["data"]["user"]["is_active"] is True
        assert set(body["data"]["user"]) == {
            "id",
            "username",
            "full_name",
            "role",
            "is_active",
        }
        raw = response.get_data(as_text=True)
        assert "a-strong-password-123" not in raw
        assert "password_hash" not in raw
        assert "auth_version" not in raw
    assert users[3].check_password("a-strong-password-123")
    assert users[3].password_hash.startswith("scrypt:")
    assert "a-strong-password-123" not in users[3].password_hash


def test_create_normalizes_username(admin_case):
    client, users, _, _ = admin_case
    token = login_admin(client)
    response = client.post(
        CREATE,
        json={
            "username": "  Tech.Two  ",
            "full_name": "Tech Two",
            "password": "a-strong-password-123",
            "role": "TECHNICIAN",
        },
        headers={"Origin": ORIGIN, "X-CSRF-Token": token},
    )
    assert response.status_code == 201
    assert response.get_json()["data"]["user"]["username"] == "tech.two"
    assert users[3].username == "tech.two"


@pytest.mark.parametrize(
    "payload",
    [
        {"username": "bad name", "full_name": "X", "password": "a-strong-password-123", "role": "TECHNICIAN"},
        {"username": "", "full_name": "X", "password": "a-strong-password-123", "role": "TECHNICIAN"},
        {"username": "x" * 65, "full_name": "X", "password": "a-strong-password-123", "role": "TECHNICIAN"},
        {"username": "tech.two", "full_name": "", "password": "a-strong-password-123", "role": "TECHNICIAN"},
        {"username": "tech.two", "full_name": "  ", "password": "a-strong-password-123", "role": "TECHNICIAN"},
        {"username": "tech.two", "full_name": "x" * 161, "password": "a-strong-password-123", "role": "TECHNICIAN"},
        {"username": "tech.two", "full_name": "X", "password": "short", "role": "TECHNICIAN"},
        {"username": "tech.two", "full_name": "X", "password": "a-strong-password-123", "role": "FARMER"},
        {"username": "tech.two", "full_name": "X", "password": "a-strong-password-123", "role": "farmer"},
        {"username": "tech.two", "full_name": "X", "password": "a-strong-password-123", "role": 123},
        {"username": "tech.two", "full_name": "X", "password": 123, "role": "TECHNICIAN"},
    ],
)
def test_create_invalid_payload_rejected(admin_case, payload):
    client, _, _, _ = admin_case
    token = login_admin(client)
    response = client.post(
        CREATE, json=payload, headers={"Origin": ORIGIN, "X-CSRF-Token": token}
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "payload",
    [
        {"username": "tech.two", "full_name": "X", "role": "TECHNICIAN"},
        {"username": "tech.two", "password": "a-strong-password-123", "role": "TECHNICIAN"},
        {"full_name": "X", "password": "a-strong-password-123", "role": "TECHNICIAN"},
        {"username": "tech.two", "full_name": "X", "password": "a-strong-password-123"},
        {
            "username": "tech.two",
            "full_name": "X",
            "password": "a-strong-password-123",
            "role": "TECHNICIAN",
            "extra": 1,
        },
    ],
)
def test_create_missing_or_extra_fields_rejected(admin_case, payload):
    client, _, _, _ = admin_case
    token = login_admin(client)
    response = client.post(
        CREATE, json=payload, headers={"Origin": ORIGIN, "X-CSRF-Token": token}
    )
    assert response.status_code == 400


def test_create_duplicate_username_conflict(admin_case):
    client, _, _, _ = admin_case
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    response = client.post(
        CREATE,
        json={
            "username": "Tech.One",
            "full_name": "Duplicate",
            "password": "a-strong-password-123",
            "role": "TECHNICIAN",
        },
        headers=headers,
    )
    assert response.status_code == 409
    assert response.get_json() == {"data": None, "message": "Username already exists."}


def test_create_integrity_error_race_sanitized(admin_case, monkeypatch):
    client, _, state, _ = admin_case
    token = login_admin(client)
    state["force_integrity_error"] = True
    response = client.post(
        CREATE,
        json={
            "username": "brand.new",
            "full_name": "Brand New",
            "password": "a-strong-password-123",
            "role": "TECHNICIAN",
        },
        headers={"Origin": ORIGIN, "X-CSRF-Token": token},
    )
    assert response.status_code == 409
    assert response.get_json() == {"data": None, "message": "Username already exists."}
    assert "duplicate" not in response.get_data(as_text=True)


def test_status_deactivate_and_reactivate_technician(admin_case):
    client, users, _, _ = admin_case
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    version_before = users[2].auth_version
    response = client.patch(STATUS(2), json={"is_active": False}, headers=headers)
    assert response.status_code == 200
    body = response.get_json()
    assert body["data"]["user"] == {
        "id": 2,
        "username": "tech.one",
        "full_name": "Tech One",
        "role": "TECHNICIAN",
        "is_active": False,
    }
    assert users[2].auth_version == version_before + 1
    assert "password_hash" not in response.get_data(as_text=True)

    response = client.patch(STATUS(2), json={"is_active": True}, headers=headers)
    assert response.status_code == 200
    assert response.get_json()["data"]["user"]["is_active"] is True
    # Activation does not decrement the version bump.
    assert users[2].auth_version == version_before + 1


def test_status_self_deactivation_forbidden(admin_case):
    client, users, _, _ = admin_case
    token = login_admin(client)
    response = client.patch(
        STATUS(1),
        json={"is_active": False},
        headers={"Origin": ORIGIN, "X-CSRF-Token": token},
    )
    assert response.status_code == 403
    assert users[1].is_active is True


def test_status_unknown_user_not_found(admin_case):
    client, _, _, _ = admin_case
    token = login_admin(client)
    response = client.patch(
        STATUS(9999),
        json={"is_active": False},
        headers={"Origin": ORIGIN, "X-CSRF-Token": token},
    )
    assert response.status_code == 404


@pytest.mark.parametrize("payload", [{}, {"is_active": True, "extra": 1}, {"is_active": 1}, {"is_active": "false"}, {"is_active": None}])
def test_status_invalid_payload_rejected(admin_case, payload):
    client, _, _, _ = admin_case
    token = login_admin(client)
    response = client.patch(
        STATUS(2), json=payload, headers={"Origin": ORIGIN, "X-CSRF-Token": token}
    )
    assert response.status_code == 400


def test_status_last_active_admin_conflict(admin_case, monkeypatch):
    # Force the last-admin invariant path: non-self active ADMIN target while
    # the live count reports a single remaining active ADMIN. The advisory
    # lock must be acquired before the check.
    client, users, state, _ = admin_case
    other = User(
        id=3,
        username="admin.two",
        full_name="Admin Two",
        role="ADMIN",
        is_active=True,
        auth_version=0,
    )
    other.set_password("another-strong-pass-123")
    users[3] = other
    monkeypatch.setattr(admin_module, "count_active_admins", lambda: 1)
    token = login_admin(client)
    locks_before = state["locks"]
    response = client.patch(
        STATUS(3),
        json={"is_active": False},
        headers={"Origin": ORIGIN, "X-CSRF-Token": token},
    )
    assert response.status_code == 409
    assert response.get_json() == {
        "data": None,
        "message": "Cannot deactivate the last active administrator.",
    }
    assert state["locks"] == locks_before + 1
    assert users[3].is_active is True


def test_status_admin_deactivation_uses_lock(admin_case):
    client, users, state, _ = admin_case
    other = User(
        id=3,
        username="admin.two",
        full_name="Admin Two",
        role="ADMIN",
        is_active=True,
        auth_version=0,
    )
    other.set_password("another-strong-pass-123")
    users[3] = other
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    locks_before = state["locks"]
    response = client.patch(STATUS(3), json={"is_active": False}, headers=headers)
    assert response.status_code == 200
    assert state["locks"] == locks_before + 1
    assert users[3].auth_version == 1


def test_second_active_admin_permits_deactivating_other_admin(admin_case):
    client, users, _, _ = admin_case
    other = User(
        id=3,
        username="admin.two",
        full_name="Admin Two",
        role="ADMIN",
        is_active=True,
        auth_version=0,
    )
    other.set_password("another-strong-pass-123")
    users[3] = other
    token = login_admin(client)
    response = client.patch(
        STATUS(3),
        json={"is_active": False},
        headers={"Origin": ORIGIN, "X-CSRF-Token": token},
    )
    assert response.status_code == 200
    assert users[3].is_active is False


def test_deactivated_session_invalidated_on_next_request(admin_case):
    client, users, _, _ = admin_case
    tech_token = login_technician(client)
    assert client.get(ME).status_code == 200
    users[2].is_active = False
    assert client.get(ME).status_code == 401
    with client.session_transaction() as session:
        assert dict(session) == {}
    # Deactivated account cannot log in again.
    assert login(client, "tech.one", TECH_PASSWORD).status_code == 401
    assert tech_token is not None


def test_admin_database_errors_sanitized(admin_case, monkeypatch):
    client, _, _, _ = admin_case
    login_admin(client)

    def fail_list():
        raise SQLAlchemyError("internal list detail")

    monkeypatch.setattr(admin_module, "list_all_users", fail_list)
    response = client.get(LIST)
    assert response.status_code == 503
    assert response.get_json() == {"data": None, "message": "Administrator service unavailable."}
    assert "internal list detail" not in response.get_data(as_text=True)

    def fail_lookup(_user_id):
        raise SQLAlchemyError("internal lookup detail")

    monkeypatch.setattr(auth, "get_user_by_id", fail_lookup)
    # load_current_user converts a lookup failure into a sanitized 503.
    response = client.get(LIST)
    assert response.status_code == 503
    assert "internal lookup detail" not in response.get_data(as_text=True)
