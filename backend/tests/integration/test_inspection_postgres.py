from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from pathlib import Path
from threading import Event
from uuid import uuid4

from flask import request
from flask_migrate import downgrade, upgrade
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Farm, Farmer, Inspection, PestCase, UserRole
from app.routes import inspections as inspections_module
from app.routes import pest_cases as pest_cases_module

CASES = "/api/v1/pest-cases"
INSPECTIONS = "/api/v1/inspections"
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
    with app.app_context():
        db.session.remove()
        # Remove inspections whose pest case is a demo row.
        demo_case_ids = db.session.scalars(
            select(PestCase.id).where(PestCase.pest_name.like("itest_%"))
        ).all()
        if demo_case_ids:
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


def seed_technician(create_integration_user):
    _tech_id, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    return tech_name


def schedule_for_case(client, headers, case_id, technician_id, scheduled_for="2026-10-15"):
    return client.post(
        f"{CASES}/{case_id}/schedule-inspection",
        json={"scheduled_for": scheduled_for, "assigned_to_user_id": technician_id},
        headers=headers,
    )


def technician_id_for(app, username):
    from app.models import User

    with app.app_context():
        db.session.remove()
        user_id = db.session.scalar(select(User.id).where(User.username == username))
        db.session.remove()
        return user_id


def test_data_bearing_migration_downgrade_collapses_phase_3c_statuses(
    integration_app, create_integration_user
):
    _admin_id, admin_name = create_integration_user()
    tech_id, _tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    auth = login(client, admin_name)
    assert auth.status_code == 200
    headers = auth_headers(auth.get_json()["data"]["csrf_token"])
    farmer_name, farm_id = seed_farm(client, headers)
    case_ids = [
        seed_for_inspection_case(client, headers, farm_id, demo_value("case"))
        for _ in range(3)
    ]
    inspection_ids = []
    for case_id in case_ids:
        scheduled = schedule_for_case(client, headers, case_id, tech_id)
        assert scheduled.status_code == 201
        inspection_ids.append(scheduled.get_json()["data"]["inspection"]["id"])

    for inspection_id, confirmed, area in (
        (inspection_ids[1], True, 1),
        (inspection_ids[2], False, 0),
    ):
        recorded = client.post(
            f"{INSPECTIONS}/{inspection_id}/record-findings",
            json={
                "findings": "Migration downgrade regression record.",
                "pest_confirmed": confirmed,
                "validated_area_hectares": area,
                "inspected_on": "2026-10-08",
            },
            headers=headers,
        )
        assert recorded.status_code == 200

    migrations = Path(__file__).resolve().parents[2] / "migrations"
    try:
        with integration_app.app_context():
            db.session.remove()
            downgrade(directory=str(migrations), revision="e7a3c9d51f24")
            with db.engine.begin() as connection:
                statuses = connection.execute(
                    text(
                        "SELECT id, status FROM pest_cases "
                        "WHERE id = ANY(:case_ids) ORDER BY id"
                    ),
                    {"case_ids": case_ids},
                ).all()
                assert statuses == [(case_id, "FOR_INSPECTION") for case_id in case_ids]
                assert connection.execute(
                    text("SELECT to_regclass('public.inspections')")
                ).scalar_one() is None

            with db.engine.connect() as connection:
                transaction = connection.begin()
                try:
                    connection.execute(
                        text("UPDATE pest_cases SET status = 'FIELD_VALIDATED' WHERE id = :id"),
                        {"id": case_ids[0]},
                    )
                    raise AssertionError("Expected the Phase 3B status constraint to reject Phase 3C status.")
                except IntegrityError:
                    transaction.rollback()
    finally:
        with integration_app.app_context():
            db.session.remove()
            upgrade(directory=str(migrations), revision="f4a9c1d2e7b3")
            with db.engine.connect() as connection:
                assert connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one() == "f4a9c1d2e7b3"
                assert connection.execute(
                    text("SELECT to_regclass('public.inspections')")
                ).scalar_one() == "inspections"
            db.session.remove()
        cleanup_demo_rows(integration_app)


def test_real_inspection_scheduling_workflow(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    admin_token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(admin_token)
    pest_name = demo_value("pest")
    try:
        _, farm_id = seed_farm(client, headers)
        case_id = seed_for_inspection_case(client, headers, farm_id, pest_name)
        tech_id = technician_id_for(integration_app, tech_name)

        scheduled = schedule_for_case(client, headers, case_id, tech_id)
        assert scheduled.status_code == 201
        assert scheduled.headers["Cache-Control"] == "no-store"
        inspection = scheduled.get_json()["data"]["inspection"]
        assert inspection["pest_case_id"] == case_id
        assert inspection["assigned_to_user_id"] == tech_id
        assert inspection["scheduled_by_user_id"] is not None
        assert inspection["pest_case"]["status"] == "INSPECTION_SCHEDULED"
        inspection_id = inspection["id"]

        # Case status transitioned atomically.
        listed = client.get(f"{INSPECTIONS}?pest_case_id={case_id}").get_json()["data"]["inspections"]
        assert [entry["id"] for entry in listed] == [inspection_id]
        detail = client.get(f"{INSPECTIONS}/{inspection_id}").get_json()["data"]["inspection"]
        assert detail["pest_case"]["farm"]["farmer"]["full_name"].startswith("itest_")
        assert detail["pest_case"]["reported_area_hectares"] == 1.0

        # Duplicate scheduling prevented.
        duplicate = schedule_for_case(client, headers, case_id, tech_id)
        assert duplicate.status_code == 409

        with integration_app.app_context():
            db.session.remove()
            row = db.session.execute(
                select(PestCase.status, PestCase.reported_area_hectares).where(PestCase.id == case_id)
            ).one()
            assert row.status == "INSPECTION_SCHEDULED"
            assert row.reported_area_hectares == Decimal("1.00")
            db.session.remove()
    finally:
        cleanup_demo_rows(integration_app)


def test_schedule_validates_technician_and_case(integration_app, create_integration_user):
    admin_id, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    admin_token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(admin_token)
    try:
        _, farm_id = seed_farm(client, headers)
        case_id = seed_for_inspection_case(client, headers, farm_id, demo_value("pest"))
        tech_id = technician_id_for(integration_app, tech_name)
        # Nonexistent case.
        assert schedule_for_case(client, headers, 2147483647, tech_id).status_code == 404
        # Nonexistent technician.
        assert schedule_for_case(client, headers, case_id, 2147483647).status_code == 404
        # ADMIN is not an eligible technician.
        assert schedule_for_case(client, headers, case_id, admin_id).status_code == 400
        # REPORTED case cannot be scheduled.
        reported_id = seed_reported_case(client, headers, farm_id, demo_value("pest"))
        assert schedule_for_case(client, headers, reported_id, tech_id).status_code == 409
        # Invalid date.
        bad = client.post(
            f"{CASES}/{case_id}/schedule-inspection",
            json={"scheduled_for": "not-a-date", "assigned_to_user_id": tech_id},
            headers=headers,
        )
        assert bad.status_code == 400
    finally:
        cleanup_demo_rows(integration_app)


def test_reschedule_only_while_pending(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    _, tech2_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    admin_token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(admin_token)
    try:
        _, farm_id = seed_farm(client, headers)
        case_id = seed_for_inspection_case(client, headers, farm_id, demo_value("pest"))
        tech_id = technician_id_for(integration_app, tech_name)
        tech2_id = technician_id_for(integration_app, tech2_name)
        inspection_id = schedule_for_case(client, headers, case_id, tech_id).get_json()["data"]["inspection"]["id"]

        count_before = client.get(INSPECTIONS).get_json()["data"]["inspections"]
        rescheduled = client.put(
            f"{INSPECTIONS}/{inspection_id}/schedule",
            json={"scheduled_for": "2026-10-20", "assigned_to_user_id": tech2_id},
            headers=headers,
        )
        assert rescheduled.status_code == 200
        assert rescheduled.get_json()["data"]["inspection"]["scheduled_for"] == "2026-10-20"
        assert rescheduled.get_json()["data"]["inspection"]["assigned_to_user_id"] == tech2_id
        count_after = client.get(INSPECTIONS).get_json()["data"]["inspections"]
        assert len(count_after) == len(count_before)
        # Status unchanged.
        with integration_app.app_context():
            db.session.remove()
            status = db.session.scalar(select(PestCase.status).where(PestCase.id == case_id))
            assert status == "INSPECTION_SCHEDULED"
            db.session.remove()

        # After findings, reschedule must conflict.
        tech_client = integration_app.test_client()
        tech_token = login(tech_client, tech2_name).get_json()["data"]["csrf_token"]
        recorded = tech_client.post(
            f"{INSPECTIONS}/{inspection_id}/record-findings",
            json={
                "findings": "Bored stalks observed",
                "pest_confirmed": True,
                "validated_area_hectares": 1,
                "inspected_on": "2026-10-07",
            },
            headers=auth_headers(tech_token),
        )
        assert recorded.status_code == 200
        late = client.put(
            f"{INSPECTIONS}/{inspection_id}/schedule",
            json={"scheduled_for": "2026-10-21"},
            headers=headers,
        )
        assert late.status_code == 409
    finally:
        cleanup_demo_rows(integration_app)


def test_record_findings_confirmed_vs_not_confirmed(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    admin_token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(admin_token)
    try:
        _, farm_id = seed_farm(client, headers)
        tech_id = technician_id_for(integration_app, tech_name)

        confirmed_case = seed_for_inspection_case(client, headers, farm_id, demo_value("pest"))
        confirmed_id = schedule_for_case(client, headers, confirmed_case, tech_id).get_json()["data"]["inspection"]["id"]
        tech_client = integration_app.test_client()
        tech_token = login(tech_client, tech_name).get_json()["data"]["csrf_token"]
        confirmed = tech_client.post(
            f"{INSPECTIONS}/{confirmed_id}/record-findings",
            json={
                "findings": "Frass and bored stalks",
                "pest_confirmed": True,
                "validated_area_hectares": "1.25",
                "inspected_on": "2026-10-07",
            },
            headers=auth_headers(tech_token),
        )
        assert confirmed.status_code == 200
        assert confirmed.get_json()["data"]["inspection"]["pest_case"]["status"] == "FIELD_VALIDATED"

        clear_case = seed_for_inspection_case(client, headers, farm_id, demo_value("pest"))
        clear_id = schedule_for_case(client, headers, clear_case, tech_id).get_json()["data"]["inspection"]["id"]
        cleared = tech_client.post(
            f"{INSPECTIONS}/{clear_id}/record-findings",
            json={
                "findings": "No damage observed",
                "pest_confirmed": False,
                "validated_area_hectares": 0,
                "inspected_on": "2026-10-07",
            },
            headers=auth_headers(tech_token),
        )
        assert cleared.status_code == 200
        assert cleared.get_json()["data"]["inspection"]["pest_case"]["status"] == "NOT_CONFIRMED"

        with integration_app.app_context():
            db.session.remove()
            rows = {
                row_id: (status, area)
                for row_id, status, area in db.session.execute(
                    select(PestCase.id, PestCase.status, PestCase.reported_area_hectares).where(
                        PestCase.id.in_([confirmed_case, clear_case])
                    )
                ).all()
            }
            assert rows[confirmed_case][0] == "FIELD_VALIDATED"
            assert rows[confirmed_case][1] == Decimal("1.00")
            assert rows[clear_case][0] == "NOT_CONFIRMED"
            assert rows[clear_case][1] == Decimal("1.00")
            validated = db.session.scalar(
                select(Inspection.validated_area_hectares).where(Inspection.id == confirmed_id)
            )
            assert validated == Decimal("1.25")
            cleared_validated = db.session.scalar(
                select(Inspection.validated_area_hectares).where(Inspection.id == clear_id)
            )
            assert cleared_validated == Decimal("0.00")
            db.session.remove()
    finally:
        cleanup_demo_rows(integration_app)


def test_validated_area_rules_and_precision(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    admin_token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(admin_token)
    try:
        _, farm_id = seed_farm(client, headers)
        case_id = seed_for_inspection_case(client, headers, farm_id, demo_value("pest"))
        tech_id = technician_id_for(integration_app, tech_name)
        inspection_id = schedule_for_case(client, headers, case_id, tech_id).get_json()["data"]["inspection"]["id"]
        tech_client = integration_app.test_client()
        tech_token = login(tech_client, tech_name).get_json()["data"]["csrf_token"]
        tech_headers = auth_headers(tech_token)
        base = {
            "findings": "Bored stalks",
            "pest_confirmed": True,
            "validated_area_hectares": 1,
            "inspected_on": "2026-10-07",
        }
        assert tech_client.post(f"{INSPECTIONS}/{inspection_id}/record-findings", json={**base, "validated_area_hectares": 0}, headers=tech_headers).status_code == 400
        assert tech_client.post(f"{INSPECTIONS}/{inspection_id}/record-findings", json={**base, "pest_confirmed": False, "validated_area_hectares": 1}, headers=tech_headers).status_code == 400
        assert tech_client.post(f"{INSPECTIONS}/{inspection_id}/record-findings", json={**base, "validated_area_hectares": "1.234"}, headers=tech_headers).status_code == 400
        assert tech_client.post(f"{INSPECTIONS}/{inspection_id}/record-findings", json={**base, "validated_area_hectares": "4.01"}, headers=tech_headers).status_code == 400
        assert tech_client.post(f"{INSPECTIONS}/{inspection_id}/record-findings", json={**base, "findings": "   "}, headers=tech_headers).status_code == 400
        assert tech_client.post(f"{INSPECTIONS}/{inspection_id}/record-findings", json={**base, "status": "FIELD_VALIDATED"}, headers=tech_headers).status_code == 400
        # Failed attempts leave the case pending.
        with integration_app.app_context():
            db.session.remove()
            status = db.session.scalar(select(PestCase.status).where(PestCase.id == case_id))
            assert status == "INSPECTION_SCHEDULED"
            db.session.remove()
    finally:
        cleanup_demo_rows(integration_app)


def test_repeated_findings_returns_409(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    admin_token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(admin_token)
    try:
        _, farm_id = seed_farm(client, headers)
        case_id = seed_for_inspection_case(client, headers, farm_id, demo_value("pest"))
        tech_id = technician_id_for(integration_app, tech_name)
        inspection_id = schedule_for_case(client, headers, case_id, tech_id).get_json()["data"]["inspection"]["id"]
        payload = {
            "findings": "Bored stalks observed",
            "pest_confirmed": True,
            "validated_area_hectares": 1,
            "inspected_on": "2026-10-07",
        }
        assert client.post(f"{INSPECTIONS}/{inspection_id}/record-findings", json=payload, headers=headers).status_code == 200
        repeated = client.post(f"{INSPECTIONS}/{inspection_id}/record-findings", json=payload, headers=headers)
        assert repeated.status_code == 409
        assert repeated.get_json() == {"data": None, "message": "Inspection findings have already been recorded."}
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
        case_id = seed_for_inspection_case(client, headers, farm_id, demo_value("pest"))
        tech_id = technician_id_for(integration_app, tech_name)
        inspection_id = schedule_for_case(client, headers, case_id, tech_id).get_json()["data"]["inspection"]["id"]
        other_client = integration_app.test_client()
        other_token = login(other_client, other_name).get_json()["data"]["csrf_token"]
        forbidden = other_client.post(
            f"{INSPECTIONS}/{inspection_id}/record-findings",
            json={
                "findings": "Trying as other tech",
                "pest_confirmed": True,
                "validated_area_hectares": 1,
                "inspected_on": "2026-10-07",
            },
            headers=auth_headers(other_token),
        )
        assert forbidden.status_code == 403
        # ADMIN can record regardless of assignment.
        assert client.post(
            f"{INSPECTIONS}/{inspection_id}/record-findings",
            json={
                "findings": "Admin recorded",
                "pest_confirmed": False,
                "validated_area_hectares": 0,
                "inspected_on": "2026-10-07",
            },
            headers=headers,
        ).status_code == 200
    finally:
        cleanup_demo_rows(integration_app)


def test_inspection_auth_origin_csrf_and_filters(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    client = integration_app.test_client()
    assert client.get(INSPECTIONS).status_code == 401
    assert client.get(f"{INSPECTIONS}/technicians").status_code == 401
    token = login(client, admin_name).get_json()["data"]["csrf_token"]
    assert client.post(f"{CASES}/1/schedule-inspection", json={}).status_code == 403
    assert client.get(f"{INSPECTIONS}?pest_case_id=abc").status_code == 400
    assert client.get(f"{INSPECTIONS}?assigned_to_user_id=abc").status_code == 400
    assert client.get(f"{INSPECTIONS}/2147483647").status_code == 404
    headers = auth_headers(token)
    assert client.get(INSPECTIONS, headers=headers).status_code == 200
    assert client.get(f"{INSPECTIONS}/technicians", headers=headers).status_code == 200


def test_no_delete_endpoints(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    client = integration_app.test_client()
    rules = [rule for rule in client.application.url_map.iter_rules() if rule.rule.startswith("/api/v1/inspections")]
    assert rules
    assert all("DELETE" not in rule.methods for rule in rules)


def test_real_status_check_constraints_hold(integration_app, create_integration_user):
    admin_id, admin_name = create_integration_user(role=UserRole.ADMIN)
    client = integration_app.test_client()
    token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(token)
    try:
        _, farm_id = seed_farm(client, headers)
        with integration_app.app_context():
            db.session.remove()
            case = PestCase(
                farm_id=farm_id,
                pest_name=demo_value("pest"),
                reported_area_hectares=Decimal("1.00"),
                status="REPORTED",
                reported_by_user_id=admin_id,
            )
            db.session.add(case)
            db.session.commit()
            case_id = case.id
            db.session.remove()
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
            # Inspection completion-state check: pending row with findings must fail.
            inspection = Inspection(
                pest_case_id=case_id,
                scheduled_for=date(2026, 10, 15),
                assigned_to_user_id=admin_id,
                scheduled_by_user_id=admin_id,
            )
            # Bypass ORM validators to test the DB CHECK directly.
            db.session.add(inspection)
            db.session.commit()
            inspection_id = inspection.id
            db.session.remove()
            try:
                db.session.execute(
                    Inspection.__table__.update()
                    .where(Inspection.id == inspection_id)
                    .values(findings="partial without completion")
                )
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
            else:
                raise AssertionError("Expected inspection completion check violation.")
            finally:
                db.session.remove()
            db.session.remove()
    finally:
        cleanup_demo_rows(integration_app)


def run_concurrent_schedules(monkeypatch, client_a, headers_a, client_b, headers_b, case_id, tech_id):
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
            f"{CASES}/{case_id}/schedule-inspection",
            json={"scheduled_for": "2026-10-15", "assigned_to_user_id": tech_id},
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


def test_concurrent_scheduling_only_one_commits(integration_app, create_integration_user, monkeypatch):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    setup = integration_app.test_client()
    setup_token = login(setup, admin_name).get_json()["data"]["csrf_token"]
    setup_headers = auth_headers(setup_token)
    try:
        _, farm_id = seed_farm(setup, setup_headers)
        case_id = seed_for_inspection_case(setup, setup_headers, farm_id, demo_value("pest"))
        tech_id = technician_id_for(integration_app, tech_name)
        client_a = integration_app.test_client()
        client_b = integration_app.test_client()
        headers_a = auth_headers(login(client_a, admin_name).get_json()["data"]["csrf_token"])
        headers_b = auth_headers(login(client_b, admin_name).get_json()["data"]["csrf_token"])
        first, second = run_concurrent_schedules(monkeypatch, client_a, headers_a, client_b, headers_b, case_id, tech_id)
        assert {first.status_code, second.status_code} == {201, 409}
        with integration_app.app_context():
            db.session.remove()
            count = db.session.scalar(
                select(db.func.count()).select_from(Inspection).where(Inspection.pest_case_id == case_id)
            )
            assert count == 1
            db.session.remove()
    finally:
        cleanup_demo_rows(integration_app)


def run_concurrent_findings(monkeypatch, client_a, headers_a, client_b, headers_b, inspection_id, payload):
    winner_ready = Event()
    release_winner = Event()
    loser_attempting = Event()
    original_commit = inspections_module.commit_inspection_changes
    original_acquire = inspections_module.acquire_inspection_case_lock
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

    monkeypatch.setattr(inspections_module, "commit_inspection_changes", coordinated_commit)
    monkeypatch.setattr(inspections_module, "acquire_inspection_case_lock", observed_acquire)

    def attempt(client, headers):
        return client.post(f"{INSPECTIONS}/{inspection_id}/record-findings", json=payload, headers=headers)

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


def test_concurrent_findings_only_one_commits(integration_app, create_integration_user, monkeypatch):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    setup = integration_app.test_client()
    setup_token = login(setup, admin_name).get_json()["data"]["csrf_token"]
    setup_headers = auth_headers(setup_token)
    try:
        _, farm_id = seed_farm(setup, setup_headers)
        case_id = seed_for_inspection_case(setup, setup_headers, farm_id, demo_value("pest"))
        tech_id = technician_id_for(integration_app, admin_name) if False else None
        # Use an admin-schedulable technician.
        _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
        tech_id = technician_id_for(integration_app, tech_name)
        inspection_id = schedule_for_case(setup, setup_headers, case_id, tech_id).get_json()["data"]["inspection"]["id"]
        client_a = integration_app.test_client()
        client_b = integration_app.test_client()
        headers_a = auth_headers(login(client_a, admin_name).get_json()["data"]["csrf_token"])
        headers_b = auth_headers(login(client_b, admin_name).get_json()["data"]["csrf_token"])
        payload = {
            "findings": "Concurrent field notes",
            "pest_confirmed": True,
            "validated_area_hectares": 1,
            "inspected_on": "2026-10-07",
        }
        first, second = run_concurrent_findings(monkeypatch, client_a, headers_a, client_b, headers_b, inspection_id, payload)
        assert {first.status_code, second.status_code} == {200, 409}
        with integration_app.app_context():
            db.session.remove()
            status = db.session.scalar(select(PestCase.status).where(PestCase.id == case_id))
            assert status == "FIELD_VALIDATED"
            db.session.remove()
    finally:
        cleanup_demo_rows(integration_app)
