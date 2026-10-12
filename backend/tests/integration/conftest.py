import os
from pathlib import Path
from uuid import uuid4

import pytest
from flask_migrate import upgrade
from sqlalchemy import delete, func, select, text, update

from app import create_app
from app.extensions import db
from app.models import User, UserRole


EXPECTED_DATABASE = "sugarcane_pest_test"
EXPECTED_USER = "sugarcane_app"
EXPECTED_TABLES = {"alembic_version", "users", "farmers", "farms", "pest_cases", "inspections", "interventions", "follow_ups"}
EXPECTED_REVISION = "d6b8f2a1c4e7"
TEST_PASSWORD = "Integration-Test-Only-Password-123!"


def require_integration_environment() -> None:
    expected = {
        "RUN_POSTGRES_INTEGRATION": "1",
        "DB_PORT": "5434",
        "DB_NAME": EXPECTED_DATABASE,
        "DB_USER": EXPECTED_USER,
    }
    for key, value in expected.items():
        if os.environ.get(key) != value:
            raise RuntimeError(f"PostgreSQL integration guard: {key} must be {value}.")
    if os.environ.get("DB_HOST") not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("PostgreSQL integration guard: DB_HOST must be local.")


def require_disposable_connection(connection) -> None:
    actual_database, actual_user = connection.execute(
        text("SELECT current_database(), current_user")
    ).one()
    if (actual_database, actual_user) != (EXPECTED_DATABASE, EXPECTED_USER):
        raise RuntimeError("PostgreSQL integration guard: connected target is not disposable.")


def public_tables(connection) -> set[str]:
    return set(
        connection.execute(
            text("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public'")
        ).scalars()
    )


def require_migrated_schema(connection) -> None:
    require_disposable_connection(connection)
    if public_tables(connection) != EXPECTED_TABLES:
        raise RuntimeError("PostgreSQL integration guard: unexpected public tables.")
    revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if revision != EXPECTED_REVISION:
        raise RuntimeError("PostgreSQL integration guard: unexpected migration revision.")


@pytest.fixture(scope="session")
def integration_app():
    require_integration_environment()
    app = create_app()  # dotenv fills only missing values; process DB overrides win.
    app.testing = True
    if not app.config["DB_PASSWORD_CONFIGURED"]:
        raise RuntimeError("PostgreSQL integration guard: DB_PASSWORD is unavailable.")

    with app.app_context():
        with db.engine.connect() as connection:
            require_disposable_connection(connection)
            tables = public_tables(connection)
            if tables not in (set(), EXPECTED_TABLES):
                raise RuntimeError("PostgreSQL integration guard: unexpected pre-migration tables.")
            if tables == EXPECTED_TABLES:
                require_migrated_schema(connection)

        if not tables:
            migrations = Path(__file__).resolve().parents[2] / "migrations"
            upgrade(directory=str(migrations), revision=EXPECTED_REVISION)

        with db.engine.connect() as connection:
            require_migrated_schema(connection)

    yield app

    with app.app_context():
        with db.engine.connect() as connection:
            require_migrated_schema(connection)
            remaining = connection.execute(
                select(func.count()).select_from(User).where(User.username.like("itest_%"))
            ).scalar_one()
            if remaining != 0:
                raise RuntimeError("PostgreSQL integration guard: fake test users remain.")


@pytest.fixture
def create_integration_user(integration_app):
    user_ids: list[int] = []
    with integration_app.app_context():
        def create_user(role: UserRole = UserRole.ADMIN) -> tuple[int, str]:
            require_disposable_connection(db.session.connection())
            username = f"itest_{uuid4().hex}"
            user = User(
                username=username,
                full_name="Integration Test User",
                role=role,
                is_active=True,
            )
            user.set_password(TEST_PASSWORD)
            db.session.add(user)
            db.session.flush()
            user_id = user.id
            user_ids.append(user_id)
            db.session.commit()
            db.session.remove()
            return user_id, username

        yield create_user

        db.session.rollback()
        if user_ids:
            # The identity check runs on the same connection used for the DELETE.
            require_disposable_connection(db.session.connection())
            db.session.execute(
                delete(User).where(User.id.in_(user_ids), User.username.like("itest_%"))
            )
            db.session.commit()
        db.session.remove()


@pytest.fixture
def update_integration_user(create_integration_user):
    def update_user(user_id: int, **changes) -> None:
        require_disposable_connection(db.session.connection())
        db.session.execute(update(User).where(User.id == user_id).values(**changes))
        db.session.commit()
        db.session.remove()

    return update_user
