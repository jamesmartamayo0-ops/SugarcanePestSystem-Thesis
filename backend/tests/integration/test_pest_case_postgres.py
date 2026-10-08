from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Event
from uuid import uuid4

from flask import request
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Farm, Farmer, PestCase, UserRole
from app.routes import pest_cases as pest_cases_module

CASES = "/api/v1/pest-cases"
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
        db.session.execute(
            delete(PestCase).where(PestCase.pest_name.like("itest_%"))
        )
        db.session.execute(
            delete(Farm).where(Farm.plot_identifier.like("itest_%"))
        )
        db.session.execute(
            delete(Farmer).where(Farmer.full_name.like("itest_%"))
        )
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


def seed_case(client, headers, farm_id, pest_name):
    response = client.post(
        CASES,
        json={
            "farm_id": farm_id,
            "pest_name": pest_name,
            "reported_area_hectares": 1,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.get_json()["data"]["pest_case"]["id"]


def run_ordered_edit_submission_race(
    monkeypatch,
    edit_client,
    edit_headers,
    submit_client,
    submit_headers,
    case_id,
    winner_method,
):
    winner_ready = Event()
    release_winner = Event()
    loser_attempting_lock = Event()
    original_commit = pest_cases_module.commit_pest_case_changes
    original_acquire = pest_cases_module.acquire_pest_case_transition_lock

    def coordinated_commit():
        if request.method == winner_method:
            winner_ready.set()
            assert release_winner.wait(timeout=10), "Timed out releasing winning request."
        original_commit()

    def observed_acquire(target_case_id):
        if request.method != winner_method:
            loser_attempting_lock.set()
        original_acquire(target_case_id)

    monkeypatch.setattr(pest_cases_module, "commit_pest_case_changes", coordinated_commit)
    monkeypatch.setattr(
        pest_cases_module, "acquire_pest_case_transition_lock", observed_acquire
    )

    def edit():
        return edit_client.put(
            f"{CASES}/{case_id}",
            json={"pest_name": "itest_concurrent_edit"},
            headers=edit_headers,
        )

    def submit():
        return submit_client.post(
            f"{CASES}/{case_id}/submit-for-inspection", headers=submit_headers
        )

    winner = edit if winner_method == "PUT" else submit
    loser = submit if winner_method == "PUT" else edit
    with ThreadPoolExecutor(max_workers=2) as executor:
        winner_future = executor.submit(winner)
        assert winner_ready.wait(timeout=10), "Winning request did not reach commit."
        loser_future = executor.submit(loser)
        try:
            assert loser_attempting_lock.wait(timeout=10), "Loser did not attempt the lock."
            assert not loser_future.done(), "Competing request bypassed the case lock."
        finally:
            release_winner.set()
        return winner_future.result(timeout=10), loser_future.result(timeout=10)


def test_real_pest_case_workflow_persistence(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    admin_token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(admin_token)
    pest_name = demo_value("pest")
    try:
        farmer_name, farm_id = seed_farm(client, headers)

        created = client.post(
            CASES,
            json={
                "farm_id": farm_id,
                "pest_name": pest_name,
                "symptoms": "Bored stalks observed",
                "observed_on": "2026-09-15",
                "reported_area_hectares": 2.5,
            },
            headers=headers,
        )
        assert created.status_code == 201
        assert created.headers["Cache-Control"] == "no-store"
        case = created.get_json()["data"]["pest_case"]
        assert set(case) == {
            "id", "farm_id", "pest_name", "symptoms", "observed_on",
            "reported_area_hectares", "status", "farm", "reporter",
            "reported_at", "updated_at",
        }
        assert case["status"] == "REPORTED"
        assert case["farm"]["id"] == farm_id
        assert case["farm"]["farmer"]["full_name"] == farmer_name
        assert case["reporter"]["username"] == admin_name
        case_id = case["id"]

        tech_client = integration_app.test_client()
        tech_token = login(tech_client, tech_name).get_json()["data"]["csrf_token"]
        assert tech_client.get(CASES).status_code == 200
        assert tech_client.get(f"{CASES}/{case_id}").status_code == 200
        updated = tech_client.put(
            f"{CASES}/{case_id}",
            json={"pest_name": pest_name, "reported_area_hectares": 3},
            headers=auth_headers(tech_token),
        )
        assert updated.status_code == 200

        submitted = client.post(
            f"{CASES}/{case_id}/submit-for-inspection", headers=headers
        )
        assert submitted.status_code == 200
        assert submitted.get_json()["data"]["pest_case"]["status"] == "FOR_INSPECTION"

        repeated = client.post(f"{CASES}/{case_id}/submit-for-inspection", headers=headers)
        assert repeated.status_code == 409
        assert repeated.get_json() == {
            "data": None,
            "message": "Pest case has already been submitted for inspection.",
        }

        late_edit = client.put(
            f"{CASES}/{case_id}", json={"pest_name": pest_name}, headers=headers
        )
        assert late_edit.status_code == 409

        filtered = client.get(f"{CASES}?status=FOR_INSPECTION").get_json()["data"]["pest_cases"]
        assert [entry["id"] for entry in filtered] == [case_id]
        by_farm = client.get(f"{CASES}?farm_id={farm_id}").get_json()["data"]["pest_cases"]
        assert [entry["id"] for entry in by_farm] == [case_id]

        db.session.remove()
        with db.engine.connect() as connection:
            row = connection.execute(
                select(
                    PestCase.pest_name,
                    PestCase.status,
                    PestCase.reported_area_hectares,
                    PestCase.reported_by_user_id,
                ).where(PestCase.id == case_id)
            ).one()
            assert row.pest_name == pest_name
            assert row.status == "FOR_INSPECTION"
            assert row.reported_area_hectares == Decimal("3.00")
            assert row.reported_by_user_id is not None
    finally:
        cleanup_demo_rows(integration_app)


def test_submission_wins_concurrent_edit_conflicts_without_changes(
    integration_app, create_integration_user, monkeypatch
):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    setup_client = integration_app.test_client()
    setup_token = login(setup_client, admin_name).get_json()["data"]["csrf_token"]
    setup_headers = auth_headers(setup_token)
    original_name = demo_value("pest")
    try:
        _, farm_id = seed_farm(setup_client, setup_headers)
        case_id = seed_case(setup_client, setup_headers, farm_id, original_name)
        edit_client = integration_app.test_client()
        submit_client = integration_app.test_client()
        edit_headers = auth_headers(
            login(edit_client, admin_name).get_json()["data"]["csrf_token"]
        )
        submit_headers = auth_headers(
            login(submit_client, admin_name).get_json()["data"]["csrf_token"]
        )

        submitted, edited = run_ordered_edit_submission_race(
            monkeypatch,
            edit_client,
            edit_headers,
            submit_client,
            submit_headers,
            case_id,
            winner_method="POST",
        )

        assert submitted.status_code == 200
        assert edited.status_code == 409
        assert edited.get_json() == {
            "data": None,
            "message": "Only REPORTED pest cases can be edited.",
        }
        with integration_app.app_context():
            db.session.remove()
            stored = db.session.execute(
                select(PestCase.pest_name, PestCase.status).where(PestCase.id == case_id)
            ).one()
            assert stored == (original_name, "FOR_INSPECTION")
            db.session.remove()
    finally:
        cleanup_demo_rows(integration_app)


def test_edit_wins_then_submission_uses_committed_record(
    integration_app, create_integration_user, monkeypatch
):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    setup_client = integration_app.test_client()
    setup_token = login(setup_client, admin_name).get_json()["data"]["csrf_token"]
    setup_headers = auth_headers(setup_token)
    try:
        _, farm_id = seed_farm(setup_client, setup_headers)
        case_id = seed_case(
            setup_client, setup_headers, farm_id, demo_value("pest")
        )
        edit_client = integration_app.test_client()
        submit_client = integration_app.test_client()
        edit_headers = auth_headers(
            login(edit_client, admin_name).get_json()["data"]["csrf_token"]
        )
        submit_headers = auth_headers(
            login(submit_client, admin_name).get_json()["data"]["csrf_token"]
        )

        edited, submitted = run_ordered_edit_submission_race(
            monkeypatch,
            edit_client,
            edit_headers,
            submit_client,
            submit_headers,
            case_id,
            winner_method="PUT",
        )

        assert edited.status_code == 200
        assert submitted.status_code == 200
        submitted_case = submitted.get_json()["data"]["pest_case"]
        assert submitted_case["pest_name"] == "itest_concurrent_edit"
        assert submitted_case["status"] == "FOR_INSPECTION"
        with integration_app.app_context():
            db.session.remove()
            stored = db.session.execute(
                select(PestCase.pest_name, PestCase.status).where(PestCase.id == case_id)
            ).one()
            assert stored == ("itest_concurrent_edit", "FOR_INSPECTION")
            db.session.remove()
    finally:
        cleanup_demo_rows(integration_app)


def test_real_reported_area_capped_and_validated(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    client = integration_app.test_client()
    token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(token)
    try:
        _, farm_id = seed_farm(client, headers)
        over = client.post(
            CASES,
            json={
                "farm_id": farm_id,
                "pest_name": demo_value("pest"),
                "reported_area_hectares": 4.01,
            },
            headers=headers,
        )
        assert over.status_code == 400
        assert over.get_json() == {
            "data": None,
            "message": "Reported area must not exceed the farm's recorded sugarcane area.",
        }
        for bad_area in (0, -1, 10000.01, "1.234", "many"):
            bad = client.post(
                CASES,
                json={
                    "farm_id": farm_id,
                    "pest_name": demo_value("pest"),
                    "reported_area_hectares": bad_area,
                },
                headers=headers,
            )
            assert bad.status_code == 400
        unknown = client.post(
            CASES,
            json={
                "farm_id": 2147483647,
                "pest_name": demo_value("pest"),
                "reported_area_hectares": 1,
            },
            headers=headers,
        )
        assert unknown.status_code == 404
        assert client.get(f"{CASES}/2147483647").status_code == 404
        assert client.get(f"{CASES}?status=BOGUS").status_code == 400
    finally:
        cleanup_demo_rows(integration_app)


def test_real_status_check_constraint_holds(integration_app, create_integration_user):
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
                    PestCase.__table__.update()
                    .where(PestCase.id == case_id)
                    .values(status="INSPECTED")
                )
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
            else:
                raise AssertionError("Expected status check constraint violation.")
            finally:
                db.session.remove()
            stored = db.session.scalar(
                select(PestCase.status).where(PestCase.id == case_id)
            )
            assert stored == "REPORTED"
            db.session.remove()
    finally:
        cleanup_demo_rows(integration_app)
