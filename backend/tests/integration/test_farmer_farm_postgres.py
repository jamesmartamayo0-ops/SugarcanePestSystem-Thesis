from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from flask_migrate import downgrade, upgrade
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Farm, Farmer, UserRole

FARMERS = "/api/v1/farmers"
FARMS = "/api/v1/farms"
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


def demo_name(prefix):
    return f"itest_{prefix}_{uuid4().hex}"


def cleanup_demo_rows(app):
    with app.app_context():
        db.session.remove()
        db.session.execute(
            delete(Farm).where(Farm.plot_identifier.like("itest_%"))
        )
        db.session.execute(
            delete(Farmer).where(Farmer.full_name.like("itest_%"))
        )
        db.session.commit()
        db.session.remove()


def coordinate_schema(connection):
    columns = {
        row.column_name: row
        for row in connection.execute(
            text(
                "SELECT column_name, data_type, numeric_precision, numeric_scale, "
                "is_nullable FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'farms' "
                "AND column_name IN ('latitude', 'longitude')"
            )
        ).all()
    }
    constraints = set(
        connection.execute(
            text(
                "SELECT constraint_name FROM information_schema.table_constraints "
                "WHERE table_schema = 'public' AND table_name = 'farms' "
                "AND constraint_name IN "
                "('ck_farms_latitude_range', 'ck_farms_longitude_range', "
                "'ck_farms_coordinates_pair')"
            )
        ).scalars()
    )
    return columns, constraints


def assert_gis_coordinate_schema(connection):
    columns, constraints = coordinate_schema(connection)
    assert set(columns) == {"latitude", "longitude"}
    for column in columns.values():
        assert column.data_type == "numeric"
        assert column.numeric_precision == 9
        assert column.numeric_scale == 6
        assert column.is_nullable == "YES"
    assert constraints == {
        "ck_farms_latitude_range",
        "ck_farms_longitude_range",
        "ck_farms_coordinates_pair",
    }


def assert_no_gis_coordinate_schema(connection):
    columns, constraints = coordinate_schema(connection)
    assert columns == {}
    assert constraints == set()


def test_real_farmer_and_farm_workflow_persistence(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    client = integration_app.test_client()
    token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(token)
    farmer_name = demo_name("farmer")
    plot = f"itest_{uuid4().hex}"
    try:
        created = client.post(
            FARMERS,
            json={"full_name": farmer_name, "barangay": "Bunao", "contact_number": "09171234567"},
            headers=headers,
        )
        assert created.status_code == 201
        farmer = created.get_json()["data"]["farmer"]
        assert set(farmer) == {"id", "full_name", "barangay", "contact_number", "farm_count"}
        assert farmer["full_name"] == farmer_name
        assert farmer["farm_count"] == 0
        farmer_id = farmer["id"]

        farm_response = client.post(
            FARMS,
            json={
                "farmer_id": farmer_id,
                "plot_identifier": plot,
                "barangay": "Bunao",
                "area_hectares": 2.5,
            },
            headers=headers,
        )
        assert farm_response.status_code == 201
        farm = farm_response.get_json()["data"]["farm"]
        assert farm["farmer_id"] == farmer_id
        assert farm["plot_identifier"] == plot
        assert farm["area_hectares"] == 2.5
        assert farm["latitude"] is None
        assert farm["longitude"] is None
        assert farm["farmer"] == {"id": farmer_id, "full_name": farmer_name, "barangay": "Bunao"}
        farm_id = farm["id"]

        detail = client.get(f"{FARMERS}/{farmer_id}").get_json()["data"]["farmer"]
        assert [entry["plot_identifier"] for entry in detail["farms"]] == [plot]

        filtered = client.get(f"{FARMS}?farmer_id={farmer_id}").get_json()["data"]["farms"]
        assert [entry["id"] for entry in filtered] == [farm_id]

        updated = client.put(
            f"{FARMERS}/{farmer_id}",
            json={"barangay": "Camanjac"},
            headers=headers,
        )
        assert updated.status_code == 200
        assert updated.get_json()["data"]["farmer"]["barangay"] == "Camanjac"

        updated_farm = client.put(
            f"{FARMS}/{farm_id}", json={"area_hectares": "3.75"}, headers=headers
        )
        assert updated_farm.status_code == 200
        assert updated_farm.get_json()["data"]["farm"]["area_hectares"] == 3.75

        db.session.remove()
        with db.engine.connect() as connection:
            stored_farmer = connection.execute(
                select(Farmer.full_name, Farmer.barangay).where(Farmer.id == farmer_id)
            ).one()
            assert (stored_farmer.full_name, stored_farmer.barangay) == (farmer_name, "Camanjac")
            stored_area = connection.execute(
                select(Farm.area_hectares).where(Farm.id == farm_id)
            ).scalar_one()
            assert stored_area == Decimal("3.75")
    finally:
        cleanup_demo_rows(integration_app)


def test_real_farm_coordinate_workflow_and_constraints(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    client = integration_app.test_client()
    token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(token)
    farmer_name = demo_name("farmer")
    plot = f"itest_{uuid4().hex}"
    try:
        farmer_id = (
            client.post(
                FARMERS,
                json={"full_name": farmer_name, "barangay": "Bunao"},
                headers=headers,
            )
            .get_json()["data"]["farmer"]["id"]
        )
        created = client.post(
            FARMS,
            json={
                "farmer_id": farmer_id,
                "plot_identifier": plot,
                "barangay": "Bunao",
                "area_hectares": 2.5,
                "latitude": 9.589321,
                "longitude": 123.121234,
            },
            headers=headers,
        )
        assert created.status_code == 201
        farm = created.get_json()["data"]["farm"]
        farm_id = farm["id"]
        assert farm["latitude"] == 9.589321
        assert farm["longitude"] == 123.121234

        unrelated = client.put(
            f"{FARMS}/{farm_id}", json={"barangay": "Camanjac"}, headers=headers
        )
        assert unrelated.status_code == 200
        assert unrelated.get_json()["data"]["farm"]["latitude"] == 9.589321

        changed = client.put(
            f"{FARMS}/{farm_id}",
            json={"latitude": 9.600001, "longitude": 123.200002},
            headers=headers,
        )
        assert changed.status_code == 200

        db.session.remove()
        with db.engine.connect() as connection:
            coordinates = connection.execute(
                select(Farm.latitude, Farm.longitude).where(Farm.id == farm_id)
            ).one()
            assert coordinates == (Decimal("9.600001"), Decimal("123.200002"))

        invalid_values = (
            {"latitude": Decimal("-90.000001"), "longitude": Decimal("123")},
            {"latitude": Decimal("90.000001"), "longitude": Decimal("123")},
            {"latitude": Decimal("9"), "longitude": Decimal("-180.000001")},
            {"latitude": Decimal("9"), "longitude": Decimal("180.000001")},
            {"latitude": None, "longitude": Decimal("123")},
        )
        with integration_app.app_context():
            for values in invalid_values:
                with pytest.raises(IntegrityError):
                    db.session.execute(update(Farm).where(Farm.id == farm_id).values(**values))
                    db.session.commit()
                db.session.rollback()

        cleared = client.put(
            f"{FARMS}/{farm_id}",
            json={"latitude": None, "longitude": None},
            headers=headers,
        )
        assert cleared.status_code == 200
        assert cleared.get_json()["data"]["farm"]["latitude"] is None
        assert cleared.get_json()["data"]["farm"]["longitude"] is None
    finally:
        cleanup_demo_rows(integration_app)


def test_gis_1_migration_upgrade_downgrade_and_reupgrade(
    integration_app, create_integration_user
):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    client = integration_app.test_client()
    token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(token)
    farmer_name = demo_name("farmer")
    plot = f"itest_{uuid4().hex}"
    migrations = Path(__file__).resolve().parents[2] / "migrations"
    old_revision = "c9d4e6a8b2f1"
    gis_revision = "d6b8f2a1c4e7"
    try:
        farmer_id = (
            client.post(
                FARMERS,
                json={"full_name": farmer_name, "barangay": "Bunao"},
                headers=headers,
            )
            .get_json()["data"]["farmer"]["id"]
        )
        created = client.post(
            FARMS,
            json={
                "farmer_id": farmer_id,
                "plot_identifier": plot,
                "barangay": "Bunao",
                "area_hectares": 2.5,
            },
            headers=headers,
        )
        assert created.status_code == 201
        farm_id = created.get_json()["data"]["farm"]["id"]

        with integration_app.app_context():
            db.session.remove()
            with db.engine.connect() as connection:
                assert connection.execute(
                    text("SELECT current_database(), current_user")
                ).one() == ("sugarcane_pest_test", "sugarcane_app")

            # Establish the pre-GIS starting revision with an existing Farm row.
            downgrade(directory=str(migrations), revision=old_revision)
            with db.engine.connect() as connection:
                assert connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one() == old_revision
                assert_no_gis_coordinate_schema(connection)
                assert connection.execute(
                    text("SELECT count(*) FROM farms WHERE id = :farm_id"),
                    {"farm_id": farm_id},
                ).scalar_one() == 1

            upgrade(directory=str(migrations), revision=gis_revision)
            with db.engine.connect() as connection:
                assert connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one() == gis_revision
                assert_gis_coordinate_schema(connection)
                assert connection.execute(
                    text("SELECT latitude, longitude FROM farms WHERE id = :farm_id"),
                    {"farm_id": farm_id},
                ).one() == (None, None)

            downgrade(directory=str(migrations), revision=old_revision)
            with db.engine.connect() as connection:
                assert connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one() == old_revision
                assert_no_gis_coordinate_schema(connection)
                assert connection.execute(
                    text("SELECT count(*) FROM farms WHERE id = :farm_id"),
                    {"farm_id": farm_id},
                ).scalar_one() == 1

            upgrade(directory=str(migrations), revision=gis_revision)
            with db.engine.connect() as connection:
                assert connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one() == gis_revision
                assert_gis_coordinate_schema(connection)
                assert connection.execute(
                    text("SELECT latitude, longitude FROM farms WHERE id = :farm_id"),
                    {"farm_id": farm_id},
                ).one() == (None, None)
            db.session.remove()
    finally:
        with integration_app.app_context():
            db.session.remove()
            upgrade(directory=str(migrations), revision=gis_revision)
            db.session.remove()
        cleanup_demo_rows(integration_app)


def test_real_duplicate_plot_unique_constraint(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    client = integration_app.test_client()
    token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(token)
    farmer_name = demo_name("farmer")
    plot = f"itest_{uuid4().hex}"
    try:
        farmer_id = (
            client.post(
                FARMERS,
                json={"full_name": farmer_name, "barangay": "Bunao"},
                headers=headers,
            )
            .get_json()["data"]["farmer"]["id"]
        )
        first = client.post(
            FARMS,
            json={
                "farmer_id": farmer_id,
                "plot_identifier": plot,
                "barangay": "Bunao",
                "area_hectares": 1,
            },
            headers=headers,
        )
        assert first.status_code == 201
        duplicate = client.post(
            FARMS,
            json={
                "farmer_id": farmer_id,
                "plot_identifier": plot,
                "barangay": "Bunao",
                "area_hectares": 1,
            },
            headers=headers,
        )
        assert duplicate.status_code == 409

        with integration_app.app_context():
            db.session.remove()
            clash = Farm(
                farmer_id=farmer_id,
                plot_identifier=plot,
                barangay="Bunao",
                area_hectares=Decimal("1.00"),
            )
            db.session.add(clash)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
            else:
                db.session.delete(clash)
                db.session.commit()
                raise AssertionError("Expected IntegrityError for duplicate plot.")
            finally:
                db.session.remove()
    finally:
        cleanup_demo_rows(integration_app)


def test_real_technician_cannot_use_farmer_or_farm_records(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    admin_client = integration_app.test_client()
    admin_token = login(admin_client, admin_name).get_json()["data"]["csrf_token"]
    farmer_name = demo_name("farmer")
    plot = f"itest_{uuid4().hex}"
    try:
        farmer_id = (
            admin_client.post(
                FARMERS,
                json={"full_name": farmer_name, "barangay": "Taclobo"},
                headers=auth_headers(admin_token),
            )
            .get_json()["data"]["farmer"]["id"]
        )
        farm_id = (
            admin_client.post(
                FARMS,
                json={
                    "farmer_id": farmer_id,
                    "plot_identifier": plot,
                    "barangay": "Taclobo",
                    "area_hectares": 1.5,
                },
                headers=auth_headers(admin_token),
            )
            .get_json()["data"]["farm"]["id"]
        )

        tech_client = integration_app.test_client()
        tech_token = login(tech_client, tech_name).get_json()["data"]["csrf_token"]
        tech_headers = auth_headers(tech_token)
        denied = [
            tech_client.get(FARMERS),
            tech_client.get(f"{FARMERS}/{farmer_id}"),
            tech_client.post(
                FARMERS,
                json={"full_name": demo_name("farmer"), "barangay": "Taclobo"},
                headers=tech_headers,
            ),
            tech_client.put(
                f"{FARMERS}/{farmer_id}", json={"barangay": "Bunao"}, headers=tech_headers
            ),
            tech_client.get(FARMS),
            tech_client.get(f"{FARMS}?farmer_id={farmer_id}"),
            tech_client.get(f"{FARMS}/{farm_id}"),
            tech_client.post(
                FARMS,
                json={
                    "farmer_id": farmer_id,
                    "plot_identifier": f"itest_{uuid4().hex}",
                    "barangay": "Taclobo",
                    "area_hectares": 1.5,
                },
                headers=tech_headers,
            ),
            tech_client.put(
                f"{FARMS}/{farm_id}", json={"area_hectares": 1}, headers=tech_headers
            ),
        ]
        for response in denied:
            assert response.status_code == 403
            assert response.get_json() == {"data": None, "message": "Permission denied."}

        # Nothing the technician attempted reached the database.
        farmer = admin_client.get(f"{FARMERS}/{farmer_id}").get_json()["data"]["farmer"]
        assert farmer["barangay"] == "Taclobo"
        assert [farm["plot_identifier"] for farm in farmer["farms"]] == [plot]
        farm = admin_client.get(f"{FARMS}/{farm_id}").get_json()["data"]["farm"]
        assert farm["area_hectares"] == 1.5
    finally:
        cleanup_demo_rows(integration_app)


def test_real_unknown_farmer_and_invalid_area(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    client = integration_app.test_client()
    token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(token)
    assert client.get(f"{FARMERS}/2147483647").status_code == 404
    response = client.post(
        FARMS,
        json={
            "farmer_id": 2147483647,
            "plot_identifier": f"itest_{uuid4().hex}",
            "barangay": "Bunao",
            "area_hectares": 1,
        },
        headers=headers,
    )
    assert response.status_code == 404
    farmer_name = demo_name("farmer")
    try:
        farmer_id = (
            client.post(
                FARMERS,
                json={"full_name": farmer_name, "barangay": "Bunao"},
                headers=headers,
            )
            .get_json()["data"]["farmer"]["id"]
        )
        for bad_area in (0, -1, 10000.01, "1.234", "many"):
            bad = client.post(
                FARMS,
                json={
                    "farmer_id": farmer_id,
                    "plot_identifier": f"itest_{uuid4().hex}",
                    "barangay": "Bunao",
                    "area_hectares": bad_area,
                },
                headers=headers,
            )
            assert bad.status_code == 400
    finally:
        cleanup_demo_rows(integration_app)
