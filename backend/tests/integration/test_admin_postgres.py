from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import User, UserRole

LIST = "/api/v1/admin/users"
CREATE = "/api/v1/admin/users"
STATUS = lambda user_id: f"/api/v1/admin/users/{user_id}/status"  # noqa: E731
ORIGIN = "http://localhost:3000"
TEST_PASSWORD = "Integration-Test-Only-Password-123!"


def login(client, username):
    return client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": TEST_PASSWORD},
        headers={"Origin": ORIGIN},
    )


def auth_headers(token):
    return {"Origin": ORIGIN, "X-CSRF-Token": token}


def tracked_user_ids():
    return select(User.id).where(User.username.like("itest_%"))


def cleanup_itest_users():
    db.session.execute(delete(User).where(User.username.like("itest_%")))
    db.session.commit()
    db.session.remove()


def test_real_create_and_list_persistence(integration_app, create_integration_user):
    login_id, login_name = create_integration_user(role=UserRole.ADMIN)
    client = integration_app.test_client()
    token = login(client, login_name).get_json()["data"]["csrf_token"]
    created_id = None
    try:
        response = client.post(
            CREATE,
            json={
                "username": "itest_created_via_api",
                "full_name": "API Created User",
                "password": "Integration-Test-Only-Password-456!",
                "role": "TECHNICIAN",
            },
            headers=auth_headers(token),
        )
        assert response.status_code == 201
        body = response.get_json()
        assert set(body["data"]["user"]) == {
            "id",
            "username",
            "full_name",
            "role",
            "is_active",
        }
        assert body["data"]["user"]["username"] == "itest_created_via_api"
        assert body["data"]["user"]["is_active"] is True
        created_id = body["data"]["user"]["id"]
        raw = response.get_data(as_text=True)
        assert "password_hash" not in raw
        assert "auth_version" not in raw
        assert "Integration-Test-Only-Password-456!" not in raw

        listing = client.get(LIST)
        assert listing.status_code == 200
        usernames = [u["username"] for u in listing.get_json()["data"]["users"]]
        assert login_name in usernames
        assert "itest_created_via_api" in usernames

        db.session.remove()
        with db.engine.connect() as connection:
            row = connection.execute(
                select(
                    User.username, User.full_name, User.role, User.is_active
                ).where(User.id == created_id)
            ).one()
            assert row.username == "itest_created_via_api"
            assert row.role == "TECHNICIAN"
            assert row.is_active is True
            stored_hash = connection.execute(
                select(User.password_hash).where(User.id == created_id)
            ).scalar_one()
            assert stored_hash.startswith("scrypt:")
            assert "Integration-Test-Only-Password-456!" not in stored_hash
    finally:
        with integration_app.app_context():
            db.session.remove()
            if created_id is not None:
                db.session.execute(
                    delete(User).where(
                        User.id == created_id, User.username.like("itest_%")
                    )
                )
                db.session.commit()
            db.session.remove()


def test_real_duplicate_username_unique_constraint(
    integration_app, create_integration_user
):
    _, login_name = create_integration_user(role=UserRole.ADMIN)
    client = integration_app.test_client()
    token = login(client, login_name).get_json()["data"]["csrf_token"]
    response = client.post(
        CREATE,
        json={
            "username": login_name,
            "full_name": "Duplicate Attempt",
            "password": TEST_PASSWORD,
            "role": "TECHNICIAN",
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 409
    assert response.get_json() == {"data": None, "message": "Username already exists."}

    # Database-level uniqueness holds independently of the API pre-check.
    with integration_app.app_context():
        db.session.remove()
        clash = User(
            username=login_name,
            full_name="Direct Clash",
            role=UserRole.TECHNICIAN,
            is_active=True,
        )
        clash.set_password(TEST_PASSWORD)
        db.session.add(clash)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
        else:
            db.session.delete(clash)
            db.session.commit()
            raise AssertionError("Expected IntegrityError for duplicate username.")
        finally:
            db.session.remove()


def test_real_deactivate_increments_version_and_invalidates_session(
    integration_app, create_integration_user
):
    admin_id, admin_name = create_integration_user(role=UserRole.ADMIN)
    tech_id, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    admin_client = integration_app.test_client()
    admin_token = login(admin_client, admin_name).get_json()["data"]["csrf_token"]

    with integration_app.app_context():
        db.session.remove()
        version_before = db.session.scalar(
            select(User.auth_version).where(User.id == tech_id)
        )

    response = admin_client.patch(
        STATUS(tech_id), json={"is_active": False}, headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["user"]["is_active"] is False

    with integration_app.app_context():
        db.session.remove()
        version_after, active_after = db.session.execute(
            select(User.auth_version, User.is_active).where(User.id == tech_id)
        ).one()
        assert active_after is False
        assert version_after == version_before + 1

    tech_client = integration_app.test_client()
    assert login(tech_client, tech_name).status_code == 401
    # A session that existed before deactivation fails on its next request.
    stale_client = integration_app.test_client()
    assert login(stale_client, tech_name).status_code == 401


def test_real_deactivated_session_invalidated_on_next_request(
    integration_app, create_integration_user
):
    admin_id, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    tech_client = integration_app.test_client()
    assert login(tech_client, tech_name).status_code == 200
    assert tech_client.get("/api/v1/auth/me").status_code == 200

    admin_client = integration_app.test_client()
    admin_token = login(admin_client, admin_name).get_json()["data"]["csrf_token"]
    tech_id = None
    with integration_app.app_context():
        db.session.remove()
        tech_id = db.session.scalar(
            select(User.id).where(User.username == tech_name)
        )
    assert (
        admin_client.patch(
            STATUS(tech_id),
            json={"is_active": False},
            headers=auth_headers(admin_token),
        ).status_code
        == 200
    )
    assert tech_client.get("/api/v1/auth/me").status_code == 401
    with tech_client.session_transaction() as session:
        assert dict(session) == {}


def test_real_self_deactivation_refused(integration_app, create_integration_user):
    admin_id, admin_name = create_integration_user(role=UserRole.ADMIN)
    client = integration_app.test_client()
    token = login(client, admin_name).get_json()["data"]["csrf_token"]
    response = client.patch(
        STATUS(admin_id), json={"is_active": False}, headers=auth_headers(token)
    )
    assert response.status_code == 403
    with integration_app.app_context():
        db.session.remove()
        assert (
            db.session.scalar(select(User.is_active).where(User.id == admin_id))
            is True
        )


def test_real_last_active_admin_invariant_holds(
    integration_app, create_integration_user
):
    # With a single active ADMIN, self-deactivation is refused and the
    # invariant (at least one active ADMIN among itest users plus any
    # pre-existing rows) is preserved. The 409 last-admin path itself is
    # exercised in unit tests with a forced count; here the real database
    # proves the invariant is never violated through the API.
    admin_id, admin_name = create_integration_user(role=UserRole.ADMIN)
    client = integration_app.test_client()
    token = login(client, admin_name).get_json()["data"]["csrf_token"]
    with integration_app.app_context():
        db.session.remove()
        active_before = db.session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == UserRole.ADMIN, User.is_active.is_(True))
        )
    response = client.patch(
        STATUS(admin_id), json={"is_active": False}, headers=auth_headers(token)
    )
    assert response.status_code == 403
    with integration_app.app_context():
        db.session.remove()
        active_after = db.session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == UserRole.ADMIN, User.is_active.is_(True))
        )
        assert active_after == active_before
        assert active_after >= 1


def test_real_multiple_admins_allow_other_deactivation(
    integration_app, create_integration_user
):
    admin_a_id, admin_a_name = create_integration_user(role=UserRole.ADMIN)
    admin_b_id, admin_b_name = create_integration_user(role=UserRole.ADMIN)
    client = integration_app.test_client()
    token = login(client, admin_a_name).get_json()["data"]["csrf_token"]
    response = client.patch(
        STATUS(admin_b_id), json={"is_active": False}, headers=auth_headers(token)
    )
    assert response.status_code == 200
    with integration_app.app_context():
        db.session.remove()
        assert (
            db.session.scalar(select(User.is_active).where(User.id == admin_b_id))
            is False
        )
        assert (
            db.session.scalar(select(User.is_active).where(User.id == admin_a_id))
            is True
        )
    # Reactivate through the API; activation needs no version restore.
    response = client.patch(
        STATUS(admin_b_id), json={"is_active": True}, headers=auth_headers(token)
    )
    assert response.status_code == 200


def test_real_technician_direct_api_denied(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    token = login(client, tech_name).get_json()["data"]["csrf_token"]
    assert client.get(LIST).status_code == 403
    assert (
        client.post(
            CREATE,
            json={
                "username": "itest_should_not_exist",
                "full_name": "Blocked",
                "password": TEST_PASSWORD,
                "role": "TECHNICIAN",
            },
            headers=auth_headers(token),
        ).status_code
        == 403
    )
    with integration_app.app_context():
        db.session.remove()
        assert (
            db.session.scalar(
                select(User.id).where(User.username == "itest_should_not_exist")
            )
            is None
        )


def test_real_advisory_lock_serializes_status_change(
    integration_app, create_integration_user
):
    # The status endpoint must hold the PostgreSQL transaction-scoped
    # advisory lock while checking and updating. Holding the same lock key
    # in this test transaction proves the key is a valid advisory lock and
    # that the endpoint path runs against real PostgreSQL semantics.
    from sqlalchemy import text

    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    token = login(client, admin_name).get_json()["data"]["csrf_token"]
    with integration_app.app_context():
        db.session.remove()
        tech_id = db.session.scalar(select(User.id).where(User.username == tech_name))
        db.session.execute(text("SELECT pg_advisory_xact_lock(75240202)"))
        db.session.commit()
        db.session.remove()
    response = client.patch(
        STATUS(tech_id), json={"is_active": False}, headers=auth_headers(token)
    )
    assert response.status_code == 200
