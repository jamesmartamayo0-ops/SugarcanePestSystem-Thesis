from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from pathlib import Path
from threading import Event
from uuid import uuid4

from flask_migrate import downgrade, upgrade
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Farm, Farmer, Inspection, Intervention, PestCase, UserRole
from app.routes import interventions as interventions_module
from app.routes import pest_cases as pest_cases_module

CASES = "/api/v1/pest-cases"
INSPECTIONS = "/api/v1/inspections"
INTERVENTIONS = "/api/v1/interventions"
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


def demo_value(prefix):
    return f"itest_{prefix}_{uuid4().hex}"


def cleanup_demo_rows(app):
    from app.models import FollowUp as _FollowUp

    with app.app_context():
        db.session.remove()
        demo_case_ids = db.session.scalars(
            select(PestCase.id).where(PestCase.pest_name.like("itest_%"))
        ).all()
        if demo_case_ids:
            demo_intervention_ids = db.session.scalars(
                select(Intervention.id).where(Intervention.pest_case_id.in_(demo_case_ids))
            ).all()
            if demo_intervention_ids:
                db.session.execute(
                    delete(_FollowUp).where(_FollowUp.intervention_id.in_(demo_intervention_ids))
                )
            db.session.execute(
                delete(Intervention).where(Intervention.pest_case_id.in_(demo_case_ids))
            )
            db.session.execute(
                delete(Inspection).where(Inspection.pest_case_id.in_(demo_case_ids))
            )
        db.session.execute(delete(PestCase).where(PestCase.pest_name.like("itest_%")))
        db.session.execute(delete(Farm).where(Farm.plot_identifier.like("itest_%")))
        db.session.execute(delete(Farmer).where(Farmer.full_name.like("itest_%")))
        db.session.commit()
        db.session.remove()


def seed_farm(client, headers):
    farmer_name = demo_value("farmer")
    plot = demo_value("plot")
    farmer_id = (
        client.post(
            "/api/v1/farmers",
            json={"full_name": farmer_name, "barangay": "Bunao"},
            headers=headers,
        )
        .get_json()["data"]["farmer"]["id"]
    )
    farm_id = (
        client.post(
            "/api/v1/farms",
            json={
                "farmer_id": farmer_id,
                "plot_identifier": plot,
                "barangay": "Bunao",
                "area_hectares": 4,
            },
            headers=headers,
        )
        .get_json()["data"]["farm"]["id"]
    )
    return farmer_name, farm_id


def seed_reported_case(client, headers, farm_id, pest_name):
    response = client.post(
        CASES,
        json={"farm_id": farm_id, "pest_name": pest_name, "reported_area_hectares": 1},
        headers=headers,
    )
    assert response.status_code == 201
    return response.get_json()["data"]["pest_case"]["id"]


def seed_for_inspection_case(client, headers, farm_id, pest_name):
    case_id = seed_reported_case(client, headers, farm_id, pest_name)
    submitted = client.post(f"{CASES}/{case_id}/submit-for-inspection", headers=headers)
    assert submitted.status_code == 200
    return case_id


def seed_validated_case(client, headers, farm_id, pest_name, tech_id):
    case_id = seed_for_inspection_case(client, headers, farm_id, pest_name)
    scheduled = client.post(
        f"{CASES}/{case_id}/schedule-inspection",
        json={"scheduled_for": "2026-10-15", "assigned_to_user_id": tech_id},
        headers=headers,
    )
    assert scheduled.status_code == 201
    inspection_id = scheduled.get_json()["data"]["inspection"]["id"]
    recorded = client.post(
        f"{INSPECTIONS}/{inspection_id}/record-findings",
        json={
            "findings": "Bored stalks observed",
            "pest_confirmed": True,
            "validated_area_hectares": 1,
            "inspected_on": "2026-10-07",
        },
        headers=headers,
    )
    assert recorded.status_code == 200
    return case_id


def seed_not_confirmed_case(client, headers, farm_id, pest_name, tech_id):
    case_id = seed_for_inspection_case(client, headers, farm_id, pest_name)
    scheduled = client.post(
        f"{CASES}/{case_id}/schedule-inspection",
        json={"scheduled_for": "2026-10-15", "assigned_to_user_id": tech_id},
        headers=headers,
    )
    assert scheduled.status_code == 201
    inspection_id = scheduled.get_json()["data"]["inspection"]["id"]
    recorded = client.post(
        f"{INSPECTIONS}/{inspection_id}/record-findings",
        json={
            "findings": "No damage observed",
            "pest_confirmed": False,
            "validated_area_hectares": 0,
            "inspected_on": "2026-10-07",
        },
        headers=headers,
    )
    assert recorded.status_code == 200
    return case_id


def start_for_case(client, headers, case_id, technician_id, **overrides):
    body = {
        "method_category": "CULTURAL",
        "method_description": "Manual removal of affected shoots",
        "scheduled_for": "2026-10-15",
        "assigned_to_user_id": technician_id,
    }
    body.update(overrides)
    return client.post(f"{CASES}/{case_id}/start-intervention", json=body, headers=headers)


def technician_id_for(app, username):
    from app.models import User

    with app.app_context():
        db.session.remove()
        user_id = db.session.scalar(select(User.id).where(User.username == username))
        db.session.remove()
        return user_id


def test_data_bearing_migration_downgrade_collapses_phase_3d_statuses(
    integration_app, create_integration_user
):
    _admin_id, admin_name = create_integration_user()
    tech_id, _tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    auth = login(client, admin_name)
    assert auth.status_code == 200
    headers = auth_headers(auth.get_json()["data"]["csrf_token"])
    farmer_name, farm_id = seed_farm(client, headers)
    pending_case = seed_validated_case(client, headers, farm_id, demo_value("case"), tech_id)
    started = start_for_case(client, headers, pending_case, tech_id)
    assert started.status_code == 201
    pending_id = started.get_json()["data"]["intervention"]["id"]
    done_case = seed_validated_case(client, headers, farm_id, demo_value("case"), tech_id)
    started2 = start_for_case(client, headers, done_case, tech_id)
    assert started2.status_code == 201
    done_id = started2.get_json()["data"]["intervention"]["id"]
    completed = client.post(
        f"{INTERVENTIONS}/{done_id}/complete",
        json={
            "performed_on": "2026-10-09",
            "completion_notes": "Cleared affected shoots",
            "follow_up_due_on": "2026-10-20",
        },
        headers=headers,
    )
    assert completed.status_code == 200

    migrations = Path(__file__).resolve().parents[2] / "migrations"
    try:
        with integration_app.app_context():
            db.session.remove()
            downgrade(directory=str(migrations), revision="f4a9c1d2e7b3")
            with db.engine.begin() as connection:
                statuses = dict(
                    connection.execute(
                        text(
                            "SELECT id, status FROM pest_cases "
                            "WHERE id = ANY(:case_ids)"
                        ),
                        {"case_ids": [pending_case, done_case]},
                    ).all()
                )
                assert statuses == {pending_case: "FIELD_VALIDATED", done_case: "FIELD_VALIDATED"}
                assert connection.execute(
                    text("SELECT to_regclass('public.interventions')")
                ).scalar_one() is None
                assert connection.execute(
                    text("SELECT to_regclass('public.follow_ups')")
                ).scalar_one() is None

            with db.engine.connect() as connection:
                transaction = connection.begin()
                try:
                    connection.execute(
                        text("UPDATE pest_cases SET status = 'UNDER_INTERVENTION' WHERE id = :id"),
                        {"id": pending_case},
                    )
                    raise AssertionError("Expected the Phase 3C status constraint to reject Phase 3D status.")
                except IntegrityError:
                    transaction.rollback()
    finally:
        with integration_app.app_context():
            db.session.remove()
            upgrade(directory=str(migrations), revision="d6b8f2a1c4e7")
            with db.engine.connect() as connection:
                assert connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one() == "d6b8f2a1c4e7"
                assert connection.execute(
                    text("SELECT to_regclass('public.interventions')")
                ).scalar_one() == "interventions"
                assert connection.execute(
                    text("SELECT to_regclass('public.follow_ups')")
                ).scalar_one() == "follow_ups"
            db.session.remove()
        cleanup_demo_rows(integration_app)


def test_real_intervention_start_workflow(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    admin_token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(admin_token)
    pest_name = demo_value("pest")
    try:
        _, farm_id = seed_farm(client, headers)
        tech_id = technician_id_for(integration_app, tech_name)
        case_id = seed_validated_case(client, headers, farm_id, pest_name, tech_id)

        started = start_for_case(client, headers, case_id, tech_id, follow_up_due_on="2026-10-25")
        assert started.status_code == 201
        assert started.headers["Cache-Control"] == "no-store"
        intervention = started.get_json()["data"]["intervention"]
        assert intervention["pest_case_id"] == case_id
        assert intervention["method_category"] == "CULTURAL"
        assert intervention["assigned_to_user_id"] == tech_id
        assert intervention["created_by_user_id"] is not None
        assert intervention["follow_up_due_on"] == "2026-10-25"
        assert intervention["pest_case"]["status"] == "UNDER_INTERVENTION"
        intervention_id = intervention["id"]

        listed = client.get(f"{INTERVENTIONS}?pest_case_id={case_id}").get_json()["data"]["interventions"]
        assert [entry["id"] for entry in listed] == [intervention_id]
        detail = client.get(f"{INTERVENTIONS}/{intervention_id}").get_json()["data"]["intervention"]
        assert detail["pest_case"]["farm"]["farmer"]["full_name"].startswith("itest_")
        assert detail["pest_case"]["status"] == "UNDER_INTERVENTION"

        duplicate = start_for_case(client, headers, case_id, tech_id)
        assert duplicate.status_code == 409

        with integration_app.app_context():
            db.session.remove()
            row = db.session.execute(
                select(PestCase.status).where(PestCase.id == case_id)
            ).scalar_one()
            assert row == "UNDER_INTERVENTION"
            db.session.remove()
    finally:
        cleanup_demo_rows(integration_app)


def test_start_rejects_non_validated_states(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    admin_token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(admin_token)
    try:
        _, farm_id = seed_farm(client, headers)
        tech_id = technician_id_for(integration_app, tech_name)
        # NOT_CONFIRMED must never start.
        rejected_case = seed_not_confirmed_case(client, headers, farm_id, demo_value("pest"), tech_id)
        assert start_for_case(client, headers, rejected_case, tech_id).status_code == 409
        # REPORTED cannot start.
        reported_id = seed_reported_case(client, headers, farm_id, demo_value("pest"))
        assert start_for_case(client, headers, reported_id, tech_id).status_code == 409
        # FOR_INSPECTION cannot start.
        queued_id = seed_for_inspection_case(client, headers, farm_id, demo_value("pest"))
        assert start_for_case(client, headers, queued_id, tech_id).status_code == 409
        # Nonexistent case.
        assert start_for_case(client, headers, 2147483647, tech_id).status_code == 404
    finally:
        cleanup_demo_rows(integration_app)


def test_start_validates_technician_assignment(integration_app, create_integration_user):
    admin_id, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    admin_token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(admin_token)
    try:
        _, farm_id = seed_farm(client, headers)
        tech_id = technician_id_for(integration_app, tech_name)
        case_id = seed_validated_case(client, headers, farm_id, demo_value("pest"), tech_id)
        assert start_for_case(client, headers, case_id, 2147483647).status_code == 404
        assert start_for_case(client, headers, case_id, admin_id).status_code == 400
        # Invalid category / description / dates / extra fields.
        assert start_for_case(client, headers, case_id, tech_id, method_category="SPRAY").status_code == 400
        assert start_for_case(client, headers, case_id, tech_id, method_description="   ").status_code == 400
        assert start_for_case(client, headers, case_id, tech_id, scheduled_for="not-a-date").status_code == 400
        bad = client.post(
            f"{CASES}/{case_id}/start-intervention",
            json={**{"method_category": "CULTURAL", "method_description": "Work", "scheduled_for": "2026-10-15", "assigned_to_user_id": tech_id}, "status": "UNDER_INTERVENTION"},
            headers=headers,
        )
        assert bad.status_code == 400
    finally:
        cleanup_demo_rows(integration_app)


def test_plan_edit_while_pending_then_locked_after_completion(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    _, tech2_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    admin_token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(admin_token)
    try:
        _, farm_id = seed_farm(client, headers)
        tech_id = technician_id_for(integration_app, tech_name)
        tech2_id = technician_id_for(integration_app, tech2_name)
        case_id = seed_validated_case(client, headers, farm_id, demo_value("pest"), tech_id)
        intervention_id = start_for_case(client, headers, case_id, tech_id).get_json()["data"]["intervention"]["id"]

        count_before = client.get(INTERVENTIONS).get_json()["data"]["interventions"]
        edited = client.put(
            f"{INTERVENTIONS}/{intervention_id}/plan",
            json={"scheduled_for": "2026-10-22", "assigned_to_user_id": tech2_id, "method_description": "Revised plan"},
            headers=headers,
        )
        assert edited.status_code == 200
        assert edited.get_json()["data"]["intervention"]["scheduled_for"] == "2026-10-22"
        assert edited.get_json()["data"]["intervention"]["assigned_to_user_id"] == tech2_id
        count_after = client.get(INTERVENTIONS).get_json()["data"]["interventions"]
        assert len(count_after) == len(count_before)
        with integration_app.app_context():
            db.session.remove()
            status = db.session.scalar(select(PestCase.status).where(PestCase.id == case_id))
            assert status == "UNDER_INTERVENTION"
            db.session.remove()

        # Complete as the newly assigned technician.
        tech_client = integration_app.test_client()
        tech_token = login(tech_client, tech2_name).get_json()["data"]["csrf_token"]
        done = tech_client.post(
            f"{INTERVENTIONS}/{intervention_id}/complete",
            json={
                "performed_on": "2026-10-09",
                "completion_notes": "Work completed",
                "follow_up_due_on": "2026-10-20",
            },
            headers=auth_headers(tech_token),
        )
        assert done.status_code == 200
        assert done.get_json()["data"]["intervention"]["pest_case"]["status"] == "FOLLOW_UP_DUE"
        late = client.put(
            f"{INTERVENTIONS}/{intervention_id}/plan",
            json={"scheduled_for": "2026-10-23"},
            headers=headers,
        )
        assert late.status_code == 409
    finally:
        cleanup_demo_rows(integration_app)


def test_completion_notes_dates_and_follow_up_validation(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    admin_token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(admin_token)
    try:
        _, farm_id = seed_farm(client, headers)
        tech_id = technician_id_for(integration_app, tech_name)
        case_id = seed_validated_case(client, headers, farm_id, demo_value("pest"), tech_id)
        intervention_id = start_for_case(client, headers, case_id, tech_id).get_json()["data"]["intervention"]["id"]
        tech_client = integration_app.test_client()
        tech_token = login(tech_client, tech_name).get_json()["data"]["csrf_token"]
        tech_headers = auth_headers(tech_token)
        base = {
            "performed_on": "2026-10-09",
            "completion_notes": "Cleared shoots",
            "follow_up_due_on": "2026-10-20",
        }
        assert tech_client.post(f"{INTERVENTIONS}/{intervention_id}/complete", json={**base, "completion_notes": "   "}, headers=tech_headers).status_code == 400
        assert tech_client.post(f"{INTERVENTIONS}/{intervention_id}/complete", json={**base, "performed_on": "2099-01-01"}, headers=tech_headers).status_code == 400
        assert tech_client.post(f"{INTERVENTIONS}/{intervention_id}/complete", json={**base, "follow_up_due_on": "2026-10-08"}, headers=tech_headers).status_code == 400
        assert tech_client.post(f"{INTERVENTIONS}/{intervention_id}/complete", json={"performed_on": "2026-10-09", "completion_notes": "Done"}, headers=tech_headers).status_code == 400
        assert tech_client.post(f"{INTERVENTIONS}/{intervention_id}/complete", json={**base, "status": "FOLLOW_UP_DUE"}, headers=tech_headers).status_code == 400
        with integration_app.app_context():
            db.session.remove()
            status = db.session.scalar(select(PestCase.status).where(PestCase.id == case_id))
            assert status == "UNDER_INTERVENTION"
            db.session.remove()

        # Reuse of the planned follow-up date succeeds.
        planned_id = start_for_case(
            client, headers, seed_validated_case(client, headers, farm_id, demo_value("pest"), tech_id),
            tech_id, follow_up_due_on="2026-10-25",
        ).get_json()["data"]["intervention"]["id"]
        reused = tech_client.post(
            f"{INTERVENTIONS}/{planned_id}/complete",
            json={"performed_on": "2026-10-09", "completion_notes": "Done", "reuse_planned_follow_up_date": True},
            headers=tech_headers,
        )
        assert reused.status_code == 200
        assert reused.get_json()["data"]["intervention"]["follow_up_due_on"] == "2026-10-25"
    finally:
        cleanup_demo_rows(integration_app)


def test_repeat_completion_returns_409(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    admin_token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(admin_token)
    try:
        _, farm_id = seed_farm(client, headers)
        tech_id = technician_id_for(integration_app, tech_name)
        case_id = seed_validated_case(client, headers, farm_id, demo_value("pest"), tech_id)
        intervention_id = start_for_case(client, headers, case_id, tech_id).get_json()["data"]["intervention"]["id"]
        payload = {
            "performed_on": "2026-10-09",
            "completion_notes": "Done",
            "follow_up_due_on": "2026-10-20",
        }
        assert client.post(f"{INTERVENTIONS}/{intervention_id}/complete", json=payload, headers=headers).status_code == 200
        repeated = client.post(f"{INTERVENTIONS}/{intervention_id}/complete", json=payload, headers=headers)
        assert repeated.status_code == 409
        assert repeated.get_json() == {"data": None, "message": "Intervention has already been completed."}
    finally:
        cleanup_demo_rows(integration_app)


def test_assigned_vs_unrelated_technician_permissions(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    _, other_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    admin_token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(admin_token)
    try:
        _, farm_id = seed_farm(client, headers)
        tech_id = technician_id_for(integration_app, tech_name)
        case_id = seed_validated_case(client, headers, farm_id, demo_value("pest"), tech_id)
        intervention_id = start_for_case(client, headers, case_id, tech_id).get_json()["data"]["intervention"]["id"]
        other_client = integration_app.test_client()
        other_token = login(other_client, other_name).get_json()["data"]["csrf_token"]
        forbidden = other_client.post(
            f"{INTERVENTIONS}/{intervention_id}/complete",
            json={
                "performed_on": "2026-10-09",
                "completion_notes": "Trying as other tech",
                "follow_up_due_on": "2026-10-20",
            },
            headers=auth_headers(other_token),
        )
        assert forbidden.status_code == 403
        assert other_client.put(
            f"{INTERVENTIONS}/{intervention_id}/plan",
            json={"scheduled_for": "2026-10-22"},
            headers=auth_headers(other_token),
        ).status_code == 403
        # ADMIN can complete regardless of assignment.
        assert client.post(
            f"{INTERVENTIONS}/{intervention_id}/complete",
            json={
                "performed_on": "2026-10-09",
                "completion_notes": "Admin completed",
                "follow_up_due_on": "2026-10-20",
            },
            headers=headers,
        ).status_code == 200
    finally:
        cleanup_demo_rows(integration_app)


def test_intervention_auth_origin_csrf_and_filters(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    client = integration_app.test_client()
    assert client.get(INTERVENTIONS).status_code == 401
    assert client.get(f"{INTERVENTIONS}/9999").status_code == 401
    token = login(client, admin_name).get_json()["data"]["csrf_token"]
    assert client.post(f"{CASES}/1/start-intervention", json={}).status_code == 403
    assert client.get(f"{INTERVENTIONS}?pest_case_id=abc").status_code == 400
    assert client.get(f"{INTERVENTIONS}?assigned_to_user_id=abc").status_code == 400
    assert client.get(f"{INTERVENTIONS}/2147483647").status_code == 404
    headers = auth_headers(token)
    assert client.get(INTERVENTIONS, headers=headers).status_code == 200


def test_no_delete_endpoints(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    client = integration_app.test_client()
    rules = [rule for rule in client.application.url_map.iter_rules() if rule.rule.startswith("/api/v1/interventions")]
    assert rules
    assert all("DELETE" not in rule.methods for rule in rules)
    start_rules = [rule for rule in client.application.url_map.iter_rules() if rule.rule.endswith("start-intervention")]
    assert start_rules
    assert all("DELETE" not in rule.methods for rule in start_rules)


def test_real_completion_state_and_pending_unique_constraints(integration_app, create_integration_user):
    admin_id, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(token)
    try:
        _, farm_id = seed_farm(client, headers)
        tech_id = technician_id_for(integration_app, tech_name)
        case_id = seed_validated_case(client, headers, farm_id, demo_value("pest"), tech_id)
        with integration_app.app_context():
            db.session.remove()
            first = Intervention(
                pest_case_id=case_id,
                method_category="CULTURAL",
                method_description="First plan",
                scheduled_for=date(2026, 10, 15),
                assigned_to_user_id=tech_id,
                created_by_user_id=admin_id,
            )
            db.session.add(first)
            db.session.commit()
            first_id = first.id
            db.session.remove()
            # Second pending intervention for the same case violates the partial unique index.
            try:
                db.session.add(
                    Intervention(
                        pest_case_id=case_id,
                        method_category="MECHANICAL",
                        method_description="Second plan",
                        scheduled_for=date(2026, 10, 16),
                        assigned_to_user_id=tech_id,
                        created_by_user_id=admin_id,
                    )
                )
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
            else:
                raise AssertionError("Expected pending intervention uniqueness violation.")
            finally:
                db.session.remove()
            # Status check still rejects bogus values.
            try:
                db.session.execute(
                    PestCase.__table__.update().where(PestCase.id == case_id).values(status="BOGUS")
                )
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
            else:
                raise AssertionError("Expected pest case status check violation.")
            finally:
                db.session.remove()
            # Completion-state check: pending row with notes but no completion must fail.
            try:
                db.session.execute(
                    Intervention.__table__.update()
                    .where(Intervention.id == first_id)
                    .values(completion_notes="partial without completion")
                )
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
            else:
                raise AssertionError("Expected intervention completion check violation.")
            finally:
                db.session.remove()
            # Category check rejects bogus values at the DB layer.
            try:
                db.session.execute(
                    Intervention.__table__.update()
                    .where(Intervention.id == first_id)
                    .values(method_category="BOGUS")
                )
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
            else:
                raise AssertionError("Expected intervention category check violation.")
            finally:
                db.session.remove()
            db.session.remove()
    finally:
        cleanup_demo_rows(integration_app)


def test_phase_3b_3c_regressions_hold(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    admin_token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(admin_token)
    try:
        _, farm_id = seed_farm(client, headers)
        tech_id = technician_id_for(integration_app, tech_name)
        case_id = seed_for_inspection_case(client, headers, farm_id, demo_value("pest"))
        scheduled = client.post(
            f"{CASES}/{case_id}/schedule-inspection",
            json={"scheduled_for": "2026-10-15", "assigned_to_user_id": tech_id},
            headers=headers,
        )
        assert scheduled.status_code == 201
        inspection_id = scheduled.get_json()["data"]["inspection"]["id"]
        recorded = client.post(
            f"{INSPECTIONS}/{inspection_id}/record-findings",
            json={
                "findings": "Regression check",
                "pest_confirmed": True,
                "validated_area_hectares": 1,
                "inspected_on": "2026-10-07",
            },
            headers=headers,
        )
        assert recorded.status_code == 200
        assert recorded.get_json()["data"]["inspection"]["pest_case"]["status"] == "FIELD_VALIDATED"
    finally:
        cleanup_demo_rows(integration_app)


def run_concurrent_starts(monkeypatch, client_a, headers_a, client_b, headers_b, case_id, tech_id):
    winner_ready = Event()
    release_winner = Event()
    loser_attempting = Event()
    original_commit = pest_cases_module.commit_pest_case_changes
    original_acquire = pest_cases_module.acquire_pest_case_transition_lock
    calls = {"acquires": 0, "commits": 0}

    def coordinated_commit():
        calls["commits"] += 1
        if calls["commits"] == 1:
            winner_ready.set()
            assert release_winner.wait(timeout=10)
        return original_commit()

    def observed_acquire(target):
        calls["acquires"] += 1
        if calls["acquires"] == 2:
            loser_attempting.set()
        return original_acquire(target)

    monkeypatch.setattr(pest_cases_module, "commit_pest_case_changes", coordinated_commit)
    monkeypatch.setattr(pest_cases_module, "acquire_pest_case_transition_lock", observed_acquire)

    def attempt(client, headers):
        return client.post(
            f"{CASES}/{case_id}/start-intervention",
            json={
                "method_category": "CULTURAL",
                "method_description": "Concurrent plan",
                "scheduled_for": "2026-10-15",
                "assigned_to_user_id": tech_id,
            },
            headers=headers,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(attempt, client_a, headers_a)
        assert winner_ready.wait(timeout=10)
        second = executor.submit(attempt, client_b, headers_b)
        try:
            assert loser_attempting.wait(timeout=10)
            assert not second.done()
        finally:
            release_winner.set()
        return first.result(timeout=10), second.result(timeout=10)


def test_concurrent_starts_only_one_commits(integration_app, create_integration_user, monkeypatch):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    setup = integration_app.test_client()
    setup_token = login(setup, admin_name).get_json()["data"]["csrf_token"]
    setup_headers = auth_headers(setup_token)
    try:
        _, farm_id = seed_farm(setup, setup_headers)
        tech_id = technician_id_for(integration_app, tech_name)
        case_id = seed_validated_case(setup, setup_headers, farm_id, demo_value("pest"), tech_id)
        client_a = integration_app.test_client()
        client_b = integration_app.test_client()
        headers_a = auth_headers(login(client_a, admin_name).get_json()["data"]["csrf_token"])
        headers_b = auth_headers(login(client_b, admin_name).get_json()["data"]["csrf_token"])
        first, second = run_concurrent_starts(monkeypatch, client_a, headers_a, client_b, headers_b, case_id, tech_id)
        assert {first.status_code, second.status_code} == {201, 409}
        with integration_app.app_context():
            db.session.remove()
            count = db.session.scalar(
                select(db.func.count()).select_from(Intervention).where(Intervention.pest_case_id == case_id)
            )
            assert count == 1
            db.session.remove()
    finally:
        cleanup_demo_rows(integration_app)


def run_concurrent_completions(monkeypatch, client_a, headers_a, client_b, headers_b, intervention_id, payload):
    winner_ready = Event()
    release_winner = Event()
    loser_attempting = Event()
    original_commit = interventions_module.commit_intervention_changes
    original_acquire = interventions_module.acquire_intervention_case_lock
    calls = {"acquires": 0, "commits": 0}

    def coordinated_commit():
        calls["commits"] += 1
        if calls["commits"] == 1:
            winner_ready.set()
            assert release_winner.wait(timeout=10)
        return original_commit()

    def observed_acquire(target):
        calls["acquires"] += 1
        if calls["acquires"] == 2:
            loser_attempting.set()
        return original_acquire(target)

    monkeypatch.setattr(interventions_module, "commit_intervention_changes", coordinated_commit)
    monkeypatch.setattr(interventions_module, "acquire_intervention_case_lock", observed_acquire)

    def attempt(client, headers):
        return client.post(f"{INTERVENTIONS}/{intervention_id}/complete", json=payload, headers=headers)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(attempt, client_a, headers_a)
        assert winner_ready.wait(timeout=10)
        second = executor.submit(attempt, client_b, headers_b)
        try:
            assert loser_attempting.wait(timeout=10)
            assert not second.done()
        finally:
            release_winner.set()
        return first.result(timeout=10), second.result(timeout=10)


def test_concurrent_completions_only_one_commits(integration_app, create_integration_user, monkeypatch):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    setup = integration_app.test_client()
    setup_token = login(setup, admin_name).get_json()["data"]["csrf_token"]
    setup_headers = auth_headers(setup_token)
    try:
        _, farm_id = seed_farm(setup, setup_headers)
        tech_id = technician_id_for(integration_app, tech_name)
        case_id = seed_validated_case(setup, setup_headers, farm_id, demo_value("pest"), tech_id)
        intervention_id = start_for_case(setup, setup_headers, case_id, tech_id).get_json()["data"]["intervention"]["id"]
        client_a = integration_app.test_client()
        client_b = integration_app.test_client()
        headers_a = auth_headers(login(client_a, admin_name).get_json()["data"]["csrf_token"])
        headers_b = auth_headers(login(client_b, admin_name).get_json()["data"]["csrf_token"])
        payload = {
            "performed_on": "2026-10-09",
            "completion_notes": "Concurrent completion",
            "follow_up_due_on": "2026-10-20",
        }
        first, second = run_concurrent_completions(monkeypatch, client_a, headers_a, client_b, headers_b, intervention_id, payload)
        assert {first.status_code, second.status_code} == {200, 409}
        with integration_app.app_context():
            db.session.remove()
            status = db.session.scalar(select(PestCase.status).where(PestCase.id == case_id))
            assert status == "FOLLOW_UP_DUE"
            db.session.remove()
    finally:
        cleanup_demo_rows(integration_app)


def test_plan_edit_races_completion_without_corruption(integration_app, create_integration_user, monkeypatch):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    setup = integration_app.test_client()
    setup_token = login(setup, admin_name).get_json()["data"]["csrf_token"]
    setup_headers = auth_headers(setup_token)
    try:
        _, farm_id = seed_farm(setup, setup_headers)
        tech_id = technician_id_for(integration_app, tech_name)
        case_id = seed_validated_case(setup, setup_headers, farm_id, demo_value("pest"), tech_id)
        intervention_id = start_for_case(setup, setup_headers, case_id, tech_id).get_json()["data"]["intervention"]["id"]

        completion_ready = Event()
        release_completion = Event()
        edit_attempting = Event()
        original_commit = interventions_module.commit_intervention_changes
        calls = {"commits": 0}

        def coordinated_commit():
            calls["commits"] += 1
            if calls["commits"] == 1:
                completion_ready.set()
                assert release_completion.wait(timeout=10)
            return original_commit()

        original_acquire = interventions_module.acquire_intervention_case_lock
        acquires = {"count": 0}

        def observed_acquire(target):
            acquires["count"] += 1
            if acquires["count"] == 2:
                edit_attempting.set()
            return original_acquire(target)

        monkeypatch.setattr(interventions_module, "commit_intervention_changes", coordinated_commit)
        monkeypatch.setattr(interventions_module, "acquire_intervention_case_lock", observed_acquire)

        client_a = integration_app.test_client()
        client_b = integration_app.test_client()
        headers_a = auth_headers(login(client_a, admin_name).get_json()["data"]["csrf_token"])
        headers_b = auth_headers(login(client_b, admin_name).get_json()["data"]["csrf_token"])

        def complete():
            return client_a.post(
                f"{INTERVENTIONS}/{intervention_id}/complete",
                json={
                    "performed_on": "2026-10-09",
                    "completion_notes": "Race winner notes",
                    "follow_up_due_on": "2026-10-20",
                },
                headers=headers_a,
            )

        def edit():
            return client_b.put(
                f"{INTERVENTIONS}/{intervention_id}/plan",
                json={"method_description": "Race loser edit"},
                headers=headers_b,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(complete)
            assert completion_ready.wait(timeout=10)
            second = executor.submit(edit)
            try:
                assert edit_attempting.wait(timeout=10)
                assert not second.done()
            finally:
                release_completion.set()
            first_result = first.result(timeout=10)
            second_result = second.result(timeout=10)

        assert first_result.status_code == 200
        assert second_result.status_code == 409
        with integration_app.app_context():
            db.session.remove()
            row = db.session.execute(
                select(
                    Intervention.method_description,
                    Intervention.completion_notes,
                    Intervention.performed_on,
                    PestCase.status,
                )
                .join(PestCase, PestCase.id == Intervention.pest_case_id)
                .where(Intervention.id == intervention_id)
            ).one()
            assert row.completion_notes == "Race winner notes"
            assert row.method_description != "Race loser edit"
            assert row.status == "FOLLOW_UP_DUE"
            db.session.remove()
    finally:
        cleanup_demo_rows(integration_app)
