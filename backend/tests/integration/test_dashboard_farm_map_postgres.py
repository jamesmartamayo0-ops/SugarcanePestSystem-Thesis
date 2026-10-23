from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import delete, text

from app.extensions import db
from app.models import Farm, Farmer, Inspection, Intervention, PestCase, UserRole
from app.models.intervention import manila_today


FARM_MAP = "/api/v1/dashboard/farm-map"
TEST_PASSWORD = "Integration-Test-Only-Password-123!"


def _login(client, username):
    return client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:3000"},
    )


def test_farm_map_projection_uses_real_postgres_rows(
    integration_app, create_integration_user
):
    admin_id, admin_name = create_integration_user(role=UserRole.ADMIN)
    tech_id, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    suffix = uuid4().hex
    farmer_ids = []
    farm_ids = []
    case_ids = []
    inspection_ids = []
    intervention_ids = []
    today = manila_today()

    try:
        with integration_app.app_context():
            assert (
                db.session.scalar(text("SELECT current_database()"))
                == "sugarcane_pest_test"
            )
            now = datetime.now(timezone.utc)

            def add_farm(mapped: bool):
                farmer = Farmer(
                    full_name=f"itest_map_farmer_{suffix}_{len(farmer_ids)}",
                    barangay="Tangculogan",
                )
                db.session.add(farmer)
                db.session.flush()
                farmer_ids.append(farmer.id)
                farm = Farm(
                    farmer_id=farmer.id,
                    plot_identifier=f"itest_map_plot_{suffix}_{len(farm_ids)}",
                    barangay="Tangculogan",
                    area_hectares=Decimal("3.00"),
                    latitude=Decimal("9.591111") if mapped else None,
                    longitude=Decimal("123.122778") if mapped else None,
                )
                db.session.add(farm)
                db.session.flush()
                farm_ids.append(farm.id)
                return farm

            def add_case(farm_id: int, status: str, pest_name: str, hour: int):
                case = PestCase(
                    farm_id=farm_id,
                    pest_name=f"itest_map_{pest_name}_{suffix}",
                    reported_area_hectares=Decimal("1.20"),
                    status=status,
                    reported_by_user_id=admin_id,
                    reported_at=now - timedelta(hours=2),
                    updated_at=now + timedelta(minutes=hour),
                )
                db.session.add(case)
                db.session.flush()
                case_ids.append(case.id)
                return case

            mapped_farm = add_farm(mapped=True)
            mapped_farm_id = mapped_farm.id
            add_case(mapped_farm.id, "REPORTED", "reported", 3)
            selected_case = add_case(
                mapped_farm.id, "FIELD_VALIDATED", "selected", 1
            )
            selected_case_id = selected_case.id
            add_case(mapped_farm.id, "CLOSED", "newer_terminal", 10)
            inspection = Inspection(
                pest_case_id=selected_case.id,
                scheduled_for=today,
                assigned_to_user_id=tech_id,
                scheduled_by_user_id=admin_id,
                inspected_on=today,
                findings="Confirmed field observation",
                pest_confirmed=True,
                validated_area_hectares=Decimal("1.25"),
                completed_by_user_id=tech_id,
                completed_at=now,
            )
            db.session.add(inspection)
            db.session.flush()
            inspection_ids.append(inspection.id)

            overdue_farm = add_farm(mapped=False)
            overdue_farm_id = overdue_farm.id
            overdue_case = add_case(
                overdue_farm.id, "FOLLOW_UP_DUE", "overdue", 1
            )
            today_farm = add_farm(mapped=True)
            today_farm_id = today_farm.id
            today_case = add_case(today_farm.id, "FOLLOW_UP_DUE", "due_today", 1)
            upcoming_farm = add_farm(mapped=True)
            upcoming_farm_id = upcoming_farm.id
            upcoming_case = add_case(
                upcoming_farm.id, "FOLLOW_UP_DUE", "upcoming", 1
            )

            for case, due_on in (
                (overdue_case, today - timedelta(days=1)),
                (today_case, today),
                (upcoming_case, today + timedelta(days=1)),
            ):
                intervention = Intervention(
                    pest_case_id=case.id,
                    method_category="CULTURAL",
                    method_description="Manual removal",
                    scheduled_for=today - timedelta(days=2),
                    assigned_to_user_id=tech_id,
                    created_by_user_id=admin_id,
                    performed_on=today - timedelta(days=2),
                    completion_notes="Completed for map integration test",
                    follow_up_due_on=due_on,
                    completed_by_user_id=tech_id,
                    completed_at=now - timedelta(days=2),
                )
                db.session.add(intervention)
                db.session.flush()
                intervention_ids.append(intervention.id)

            db.session.commit()
            db.session.remove()

        client = integration_app.test_client()
        assert _login(client, admin_name).status_code == 200
        response = client.get(FARM_MAP)
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"
        body = response.get_json()
        farms = {item["id"]: item for item in body["data"]["farms"]}

        mapped = farms[mapped_farm_id]
        assert mapped["location"] == {
            "latitude": 9.591111,
            "longitude": 123.122778,
        }
        assert mapped["marker_state"] == "FIELD_VALIDATED"
        assert mapped["case"]["id"] == selected_case_id
        assert mapped["case"]["validated_area_hectares"] == 1.25
        assert mapped["has_active_case"] is True
        assert mapped["needs_attention"] is True

        assert farms[overdue_farm_id]["location"] is None
        assert farms[overdue_farm_id]["needs_attention"] is True
        assert farms[today_farm_id]["needs_attention"] is False
        assert farms[upcoming_farm_id]["needs_attention"] is False
        assert body["data"]["summary"]["active_cases"] >= 5
        assert body["data"]["summary"]["needs_attention_cases"] >= 2

        tech_client = integration_app.test_client()
        assert _login(tech_client, tech_name).status_code == 200
        assert tech_client.get(FARM_MAP).status_code == 200
    finally:
        with integration_app.app_context():
            db.session.rollback()
            assert (
                db.session.scalar(text("SELECT current_database()"))
                == "sugarcane_pest_test"
            )
            if intervention_ids:
                db.session.execute(
                    delete(Intervention).where(Intervention.id.in_(intervention_ids))
                )
            if inspection_ids:
                db.session.execute(
                    delete(Inspection).where(Inspection.id.in_(inspection_ids))
                )
            if case_ids:
                db.session.execute(delete(PestCase).where(PestCase.id.in_(case_ids)))
            if farm_ids:
                db.session.execute(delete(Farm).where(Farm.id.in_(farm_ids)))
            if farmer_ids:
                db.session.execute(delete(Farmer).where(Farmer.id.in_(farmer_ids)))
            db.session.commit()
            db.session.remove()
