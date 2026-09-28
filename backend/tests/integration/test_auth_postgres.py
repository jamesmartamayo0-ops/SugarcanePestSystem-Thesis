from sqlalchemy import event, select, text

from app.extensions import db
from app.models import User

LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"
LOGOUT = "/api/v1/auth/logout"
ORIGIN = "http://localhost:3000"
TEST_PASSWORD = "Integration-Test-Only-Password-123!"


def login(client, username):
    return client.post(
        LOGIN,
        json={"username": username, "password": TEST_PASSWORD},
        headers={"Origin": ORIGIN},
    )


def session_state(client):
    with client.session_transaction() as session:
        return dict(session)


def test_real_login_uses_postgres_and_returns_public_fields(integration_app, create_integration_user):
    user_id, username = create_integration_user()
    client = integration_app.test_client()
    db.session.remove()
    user_selects = []

    def capture_select(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT") and "users" in statement.lower():
            user_selects.append(statement)

    event.listen(db.engine, "before_cursor_execute", capture_select)
    try:
        response = login(client, username)
    finally:
        event.remove(db.engine, "before_cursor_execute", capture_select)

    assert response.status_code == 200
    # Hard regression proof: exactly one users SELECT during login.
    # Pre-hardening behavior would trigger a second SELECT after commit
    # because SQLAlchemy expires the User object and refreshes it.
    assert len(user_selects) == 1, f"Expected exactly 1 users SELECT, got {len(user_selects)}: {user_selects}"
    # Confirm the SELECT is the login lookup, not unrelated SQL.
    select_statement = user_selects[0]
    assert "SELECT" in select_statement.upper()
    assert "users" in select_statement.lower()
    assert "WHERE" in select_statement.upper() or "where" in select_statement.lower()
    data = response.get_json()["data"]
    assert set(data) == {"user", "csrf_token"}
    assert data["user"] == {
        "id": user_id,
        "username": username,
        "full_name": "Integration Test User",
        "role": "ADMIN",
    }
    assert len(data["csrf_token"]) == 64
    assert "password_hash" not in response.get_data(as_text=True)
    assert client.get_cookie("sugarcane_session") is not None


def test_real_last_login_is_committed(integration_app, create_integration_user):
    user_id, username = create_integration_user()
    client = integration_app.test_client()
    assert login(client, username).status_code == 200
    db.session.remove()
    with db.engine.connect() as connection:
        assert connection.execute(text("SELECT current_database(), current_user")).one() == (
            "sugarcane_pest_test", "sugarcane_app"
        )
        persisted = connection.execute(
            select(User.last_login_at).where(User.id == user_id)
        ).scalar_one()
    assert persisted is not None


def test_real_expire_on_commit_login_survives(integration_app, create_integration_user):
    _, username = create_integration_user()
    assert db.session().expire_on_commit is True
    client = integration_app.test_client()
    # The real login commits last_login_at. SQLAlchemy then expires its User;
    # the 200 response proves login uses values captured before that commit.
    response = login(client, username)
    assert response.status_code == 200
    assert response.get_json()["data"]["user"]["username"] == username


def test_real_me_reloads_user_from_postgres(integration_app, create_integration_user):
    user_id, username = create_integration_user()
    client = integration_app.test_client()
    token = login(client, username).get_json()["data"]["csrf_token"]
    db.session.remove()
    user_selects = []

    def capture_select(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT") and "users" in statement.lower():
            user_selects.append(True)

    event.listen(db.engine, "before_cursor_execute", capture_select)
    try:
        response = client.get(ME)
    finally:
        event.remove(db.engine, "before_cursor_execute", capture_select)

    assert response.status_code == 200
    assert user_selects, "/me must reload the user from PostgreSQL."
    assert response.get_json()["data"] == {
        "user": {
            "id": user_id,
            "username": username,
            "full_name": "Integration Test User",
            "role": "ADMIN",
        },
        "csrf_token": token,
    }


def test_real_auth_version_change_invalidates_session(
    integration_app, create_integration_user, update_integration_user
):
    user_id, username = create_integration_user()
    client = integration_app.test_client()
    assert login(client, username).status_code == 200
    update_integration_user(user_id, auth_version=User.auth_version + 1)
    assert client.get(ME).status_code == 401
    assert session_state(client) == {}
    assert client.get_cookie("sugarcane_session") is None


def test_real_inactive_change_invalidates_session(
    integration_app, create_integration_user, update_integration_user
):
    user_id, username = create_integration_user()
    client = integration_app.test_client()
    assert login(client, username).status_code == 200
    update_integration_user(user_id, is_active=False)
    assert client.get(ME).status_code == 401
    assert session_state(client) == {}
    assert client.get_cookie("sugarcane_session") is None


def test_real_logout_clears_session(integration_app, create_integration_user):
    _, username = create_integration_user()
    client = integration_app.test_client()
    token = login(client, username).get_json()["data"]["csrf_token"]
    response = client.post(
        LOGOUT,
        headers={"Origin": ORIGIN, "X-CSRF-Token": token},
    )
    assert response.status_code == 204
    assert client.get(ME).status_code == 401
    assert session_state(client) == {}
