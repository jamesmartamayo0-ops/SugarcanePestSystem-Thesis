from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from threading import Event
from uuid import uuid4

from flask_migrate import downgrade, upgrade
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Farm, Farmer, FollowUp, Inspection, Intervention, PestCase, UserRole
from app.routes import follow_ups as follow_ups_module
from app.routes import pest_cases as pest_cases_module

CASES = "/api/v1/pest-cases"
INSPECTIONS = "/api/v1/inspections"
INTERVENTIONS = "/api/v1/interventions"
FOLLOW_UPS = "/api/v1/follow-ups"
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
        demo_case_ids = db.session.scalars(
            select(PestCase.id).where(PestCase.pest_name.like("itest_%"))
        ).all()
        if demo_case_ids:
            demo_intervention_ids = db.session.scalars(
                select(Intervention.id).where(Intervention.pest_case_id.in_(demo_case_ids))
            ).all()
            if demo_intervention_ids:
                db.session.execute(
                    delete(FollowUp).where(FollowUp.intervention_id.in_(demo_intervention_ids))
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


def start_for_case(client, headers, case_id, technician_id, **overrides):
    body = {
        "method_category": "CULTURAL",
        "method_description": "Manual removal of affected shoots",
        "scheduled_for": "2026-10-15",
        "assigned_to_user_id": technician_id,
    }
    body.update(overrides)
    return client.post(f"{CASES}/{case_id}/start-intervention", json=body, headers=headers)


def complete_intervention(client, headers, intervention_id, **overrides):
    body = {
        "performed_on": "2026-10-09",
        "completion_notes": "Cleared affected shoots",
        "follow_up_due_on": "2026-10-20",
    }
    body.update(overrides)
    return client.post(f"{INTERVENTIONS}/{intervention_id}/complete", json=body, headers=headers)


def record_follow_up(client, headers, intervention_id, **overrides):
    body = {
        "observed_on": "2026-10-09",
        "pest_observed": False,
        "observed_affected_area_hectares": 0.5,
        "assessment_notes": "Canopy recovering, no fresh damage",
        "outcome": "RESOLVED",
    }
    body.update(overrides)
    return client.post(
        f"{INTERVENTIONS}/{intervention_id}/record-follow-up", json=body, headers=headers
    )


def technician_id_for(app, username):
    from app.models import User

    with app.app_context():
        db.session.remove()
        user_id = db.session.scalar(select(User.id).where(User.username == username))
        db.session.remove()
        return user_id


def seed_follow_up_due_case(client, headers, farm_id, pest_name, tech_id):
    case_id = seed_validated_case(client, headers, farm_id, pest_name, tech_id)
    intervention_id = start_for_case(client, headers, case_id, tech_id).get_json()["data"]["intervention"]["id"]
    completed = complete_intervention(client, headers, intervention_id)
    assert completed.status_code == 200
    return case_id, intervention_id


def test_data_bearing_downgrade_and_reupgrade_with_phase_3e_records(
    integration_app, create_integration_user
):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    admin_token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(admin_token)
    try:
        _, farm_id = seed_farm(client, headers)
        tech_id = technician_id_for(integration_app, tech_name)

        # Ordinary FOLLOW_UP_DUE case (no follow-up yet).
        ordinary_case, _ = seed_follow_up_due_case(
            client, headers, farm_id, demo_value("case"), tech_id
        )
        # CLOSED case with follow-up.
        closed_case, closed_intervention = seed_follow_up_due_case(
            client, headers, farm_id, demo_value("case"), tech_id
        )
        recorded_closed = record_follow_up(
            client, headers, closed_intervention, outcome="RESOLVED", pest_observed=False
        )
        assert recorded_closed.status_code == 201
        # REINTERVENTION_REQUIRED case with follow-up.
        re_case, re_intervention = seed_follow_up_due_case(
            client, headers, farm_id, demo_value("case"), tech_id
        )
        recorded_re = record_follow_up(
            client, headers, re_intervention, outcome="REINTERVENTION_REQUIRED", pest_observed=True
        )
        assert recorded_re.status_code == 201

        with integration_app.app_context():
            db.session.remove()
            statuses = dict(
                db.session.execute(
                    select(PestCase.id, PestCase.status).where(
                        PestCase.id.in_([ordinary_case, closed_case, re_case])
                    )
                ).all()
            )
            assert statuses == {
                ordinary_case: "FOLLOW_UP_DUE",
                closed_case: "CLOSED",
                re_case: "REINTERVENTION_REQUIRED",
            }
            assert db.session.scalar(select(db.func.count()).select_from(FollowUp)) >= 2
            db.session.remove()

        migrations = Path(__file__).resolve().parents[2] / "migrations"
        with integration_app.app_context():
            db.session.remove()
            downgrade(directory=str(migrations), revision="e8f2a4c6d1b3")
            with db.engine.begin() as connection:
                statuses = dict(
                    connection.execute(
                        text("SELECT id, status FROM pest_cases WHERE id = ANY(:ids)"),
                        {"ids": [ordinary_case, closed_case, re_case]},
                    ).all()
                )
                # Both Phase 3E outcomes collapse to FOLLOW_UP_DUE before the
                # seven-status Phase 3D constraint is restored.
                assert statuses == {
                    ordinary_case: "FOLLOW_UP_DUE",
                    closed_case: "FOLLOW_UP_DUE",
                    re_case: "FOLLOW_UP_DUE",
                }
                assert connection.execute(
                    text("SELECT to_regclass('public.follow_ups')")
                ).scalar_one() is None
            # Old seven-status constraint rejects the Phase 3E values.
            with db.engine.connect() as connection:
                transaction = connection.begin()
                try:
                    connection.execute(
                        text("UPDATE pest_cases SET status = 'CLOSED' WHERE id = :id"),
                        {"id": ordinary_case},
                    )
                    raise AssertionError("Expected Phase 3D constraint to reject CLOSED.")
                except IntegrityError:
                    transaction.rollback()
                transaction = connection.begin()
                try:
                    connection.execute(
                        text(
                            "UPDATE pest_cases SET status = 'REINTERVENTION_REQUIRED' WHERE id = :id"
                        ),
                        {"id": ordinary_case},
                    )
                    raise AssertionError(
                        "Expected Phase 3D constraint to reject REINTERVENTION_REQUIRED."
                    )
                except IntegrityError:
                    transaction.rollback()
            # Re-upgrade restores the nine-status workflow (history itself is
            # documented as lost by the downgrade).
            upgrade(directory=str(migrations), revision="d6b8f2a1c4e7")
            with db.engine.connect() as connection:
                assert connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one() == "d6b8f2a1c4e7"
                assert connection.execute(
                    text("SELECT to_regclass('public.follow_ups')")
                ).scalar_one() == "follow_ups"
            db.session.remove()
    finally:
        cleanup_demo_rows(integration_app)


def test_one_follow_up_per_intervention_db_enforcement(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    admin_token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(admin_token)
    try:
        _, farm_id = seed_farm(client, headers)
        tech_id = technician_id_for(integration_app, tech_name)
        _, intervention_id = seed_follow_up_due_case(
            client, headers, farm_id, demo_value("pest"), tech_id
        )
        first = record_follow_up(client, headers, intervention_id)
        assert first.status_code == 201
        # API duplicate.
        assert record_follow_up(client, headers, intervention_id).status_code == 409
        # DB-level UNIQUE enforcement.
        with integration_app.app_context():
            db.session.remove()
            admin_id = db.session.scalar(
                select(PestCase.reported_by_user_id).where(PestCase.id.is_not(None)).limit(1)
            )
            try:
                db.session.add(
                    FollowUp(
                        intervention_id=intervention_id,
                        observed_on=date(2026, 10, 9),
                        pest_observed=False,
                        observed_affected_area_hectares=0.25,
                        assessment_notes="Second attempt",
                        outcome="RESOLVED",
                        recorded_by_user_id=tech_id,
                    )
                )
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
            else:
                raise AssertionError("Expected one-follow-up-per-intervention violation.")
            finally:
                db.session.remove()
            # Outcome check rejects bogus values at the DB layer.
            try:
                db.session.execute(
                    FollowUp.__table__.update()
                    .where(FollowUp.intervention_id == intervention_id)
                    .values(outcome="BOGUS")
                )
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
            else:
                raise AssertionError("Expected follow-up outcome check violation.")
            finally:
                db.session.remove()
            db.session.remove()
    finally:
        cleanup_demo_rows(integration_app)


def test_initial_workflow_ending_closed(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    admin_token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(admin_token)
    try:
        _, farm_id = seed_farm(client, headers)
        tech_id = technician_id_for(integration_app, tech_name)
        case_id, intervention_id = seed_follow_up_due_case(
            client, headers, farm_id, demo_value("pest"), tech_id
        )
        # Due queue contains the completed intervention before reassessment.
        due = client.get(f"{FOLLOW_UPS}/due", headers=headers).get_json()["data"]["due"]
        assert any(entry["intervention_id"] == intervention_id for entry in due)
        recorded = record_follow_up(client, headers, intervention_id, outcome="RESOLVED")
        assert recorded.status_code == 201
        assert recorded.headers["Cache-Control"] == "no-store"
        follow_up = recorded.get_json()["data"]["follow_up"]
        assert follow_up["outcome"] == "RESOLVED"
        assert follow_up["pest_case"]["status"] == "CLOSED"
        assert follow_up["recorded_by_user_id"] is not None
        # Queue no longer contains it; history does.
        due_after = client.get(f"{FOLLOW_UPS}/due", headers=headers).get_json()["data"]["due"]
        assert all(entry["intervention_id"] != intervention_id for entry in due_after)
        listed = client.get(f"{FOLLOW_UPS}?pest_case_id={case_id}", headers=headers).get_json()["data"]["follow_ups"]
        assert [entry["id"] for entry in listed] == [follow_up["id"]]
        detail = client.get(f"{FOLLOW_UPS}/{follow_up['id']}", headers=headers).get_json()["data"]["follow_up"]
        assert detail["pest_case"]["farm"]["farmer"]["full_name"].startswith("itest_")
        assert detail["intervention"]["id"] == intervention_id
        with integration_app.app_context():
            db.session.remove()
            status = db.session.scalar(select(PestCase.status).where(PestCase.id == case_id))
            assert status == "CLOSED"
            db.session.remove()
        # CLOSED cases cannot start another intervention and cannot record again.
        assert start_for_case(client, headers, case_id, tech_id).status_code == 409
        assert record_follow_up(client, headers, intervention_id).status_code == 409
    finally:
        cleanup_demo_rows(integration_app)


def test_repeat_intervention_workflow_with_eventual_closure(
    integration_app, create_integration_user
):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    admin_token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(admin_token)
    try:
        _, farm_id = seed_farm(client, headers)
        tech_id = technician_id_for(integration_app, tech_name)
        case_id, first_id = seed_follow_up_due_case(
            client, headers, farm_id, demo_value("pest"), tech_id
        )
        first_fu = record_follow_up(
            client, headers, first_id, outcome="REINTERVENTION_REQUIRED", pest_observed=True
        )
        assert first_fu.status_code == 201
        assert first_fu.get_json()["data"]["follow_up"]["pest_case"]["status"] == "REINTERVENTION_REQUIRED"
        # Direct start from FOLLOW_UP_DUE is forbidden; repeat starts from REINTERVENTION_REQUIRED.
        second = start_for_case(client, headers, case_id, tech_id)
        assert second.status_code == 201
        second_id = second.get_json()["data"]["intervention"]["id"]
        assert second_id != first_id
        assert second.get_json()["data"]["intervention"]["pest_case"]["status"] == "UNDER_INTERVENTION"
        # Old intervention keeps its follow-up; new pending has none yet.
        assert client.get(f"{FOLLOW_UPS}?intervention_id={first_id}", headers=headers).get_json()["data"]["follow_ups"] != []
        assert client.get(f"{FOLLOW_UPS}?intervention_id={second_id}", headers=headers).get_json()["data"]["follow_ups"] == []
        # Recording for the superseded first intervention is rejected as not-latest.
        assert record_follow_up(client, headers, first_id, outcome="RESOLVED").status_code in (404, 409)
        completed = complete_intervention(client, headers, second_id)
        assert completed.status_code == 200
        assert completed.get_json()["data"]["intervention"]["pest_case"]["status"] == "FOLLOW_UP_DUE"
        second_fu = record_follow_up(client, headers, second_id, outcome="RESOLVED")
        assert second_fu.status_code == 201
        assert second_fu.get_json()["data"]["follow_up"]["pest_case"]["status"] == "CLOSED"
        with integration_app.app_context():
            db.session.remove()
            interventions = db.session.scalars(
                select(Intervention).where(Intervention.pest_case_id == case_id).order_by(Intervention.id)
            ).all()
            assert [item.id for item in interventions] == [first_id, second_id]
            follow_ups = db.session.scalars(
                select(FollowUp)
                .join(Intervention, Intervention.id == FollowUp.intervention_id)
                .where(Intervention.pest_case_id == case_id)
                .order_by(FollowUp.id)
            ).all()
            assert len(follow_ups) == 2
            assert [item.outcome for item in follow_ups] == ["REINTERVENTION_REQUIRED", "RESOLVED"]
            assert db.session.scalar(select(PestCase.status).where(PestCase.id == case_id)) == "CLOSED"
            db.session.remove()
    finally:
        cleanup_demo_rows(integration_app)


def test_follow_up_permissions_and_filters(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    _, other_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    admin_token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(admin_token)
    try:
        _, farm_id = seed_farm(client, headers)
        tech_id = technician_id_for(integration_app, tech_name)
        _, intervention_id = seed_follow_up_due_case(
            client, headers, farm_id, demo_value("pest"), tech_id
        )
        other_client = integration_app.test_client()
        other_token = login(other_client, other_name).get_json()["data"]["csrf_token"]
        forbidden = other_client.post(
            f"{INTERVENTIONS}/{intervention_id}/record-follow-up",
            json={
                "observed_on": "2026-10-09",
                "pest_observed": True,
                "assessment_notes": "Trying as other tech",
                "outcome": "REINTERVENTION_REQUIRED",
            },
            headers=auth_headers(other_token),
        )
        assert forbidden.status_code == 403
        # Invalid outcome / area / dates / extra fields.
        assert record_follow_up(client, headers, intervention_id, outcome="BOGUS").status_code == 400
        assert record_follow_up(client, headers, intervention_id, observed_affected_area_hectares=99).status_code == 400
        assert record_follow_up(client, headers, intervention_id, observed_on="2099-01-01").status_code == 400
        bad = client.post(
            f"{INTERVENTIONS}/{intervention_id}/record-follow-up",
            json={**{"observed_on": "2026-10-09", "pest_observed": False, "assessment_notes": "ok", "outcome": "RESOLVED"}, "status": "CLOSED"},
            headers=headers,
        )
        assert bad.status_code == 400
        # Auth / filters.
        fresh = integration_app.test_client()
        assert fresh.get(FOLLOW_UPS).status_code == 401
        assert client.get(f"{FOLLOW_UPS}?outcome=BOGUS", headers=headers).status_code == 400
        assert client.get(f"{FOLLOW_UPS}/2147483647", headers=headers).status_code == 404
    finally:
        cleanup_demo_rows(integration_app)


def test_no_follow_up_modification_endpoints(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    client = integration_app.test_client()
    login(client, admin_name)
    rules = [rule for rule in client.application.url_map.iter_rules() if rule.rule.startswith("/api/v1/follow-ups")]
    assert rules
    assert all("PUT" not in rule.methods for rule in rules)
    assert all("PATCH" not in rule.methods for rule in rules)
    assert all("DELETE" not in rule.methods for rule in rules)
    record_rules = [rule for rule in client.application.url_map.iter_rules() if rule.rule.endswith("record-follow-up")]
    assert record_rules
    assert all("PUT" not in rule.methods for rule in record_rules)
    assert all("PATCH" not in rule.methods for rule in record_rules)
    assert all("DELETE" not in rule.methods for rule in record_rules)


def test_phase_3b_3c_3d_regressions_hold(integration_app, create_integration_user):
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
        started = start_for_case(client, headers, case_id, tech_id)
        assert started.status_code == 201
        intervention_id = started.get_json()["data"]["intervention"]["id"]
        completed = complete_intervention(client, headers, intervention_id)
        assert completed.status_code == 200
        assert completed.get_json()["data"]["intervention"]["pest_case"]["status"] == "FOLLOW_UP_DUE"
    finally:
        cleanup_demo_rows(integration_app)


def run_concurrent_follow_ups(monkeypatch, client_a, headers_a, client_b, headers_b, intervention_id, payload):
    winner_ready = Event()
    release_winner = Event()
    loser_attempting = Event()
    original_commit = follow_ups_module.commit_follow_up_changes
    original_acquire = follow_ups_module.acquire_follow_up_case_lock
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

    monkeypatch.setattr(follow_ups_module, "commit_follow_up_changes", coordinated_commit)
    monkeypatch.setattr(follow_ups_module, "acquire_follow_up_case_lock", observed_acquire)

    def attempt(client, headers):
        return client.post(
            f"{INTERVENTIONS}/{intervention_id}/record-follow-up", json=payload, headers=headers
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


def test_concurrent_duplicate_follow_ups_only_one_commits(
    integration_app, create_integration_user, monkeypatch
):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    setup = integration_app.test_client()
    setup_token = login(setup, admin_name).get_json()["data"]["csrf_token"]
    setup_headers = auth_headers(setup_token)
    try:
        _, farm_id = seed_farm(setup, setup_headers)
        tech_id = technician_id_for(integration_app, tech_name)
        _, intervention_id = seed_follow_up_due_case(
            setup, setup_headers, farm_id, demo_value("pest"), tech_id
        )
        client_a = integration_app.test_client()
        client_b = integration_app.test_client()
        headers_a = auth_headers(login(client_a, admin_name).get_json()["data"]["csrf_token"])
        headers_b = auth_headers(login(client_b, admin_name).get_json()["data"]["csrf_token"])
        payload = {
            "observed_on": "2026-10-09",
            "pest_observed": False,
            "assessment_notes": "Concurrent reassessment",
            "outcome": "RESOLVED",
        }
        first, second = run_concurrent_follow_ups(
            monkeypatch, client_a, headers_a, client_b, headers_b, intervention_id, payload
        )
        assert {first.status_code, second.status_code} == {201, 409}
        with integration_app.app_context():
            db.session.remove()
            count = db.session.scalar(
                select(db.func.count()).select_from(FollowUp).where(FollowUp.intervention_id == intervention_id)
            )
            assert count == 1
            case_id = db.session.scalar(
                select(Intervention.pest_case_id).where(Intervention.id == intervention_id)
            )
            assert db.session.scalar(select(PestCase.status).where(PestCase.id == case_id)) == "CLOSED"
            db.session.remove()
    finally:
        cleanup_demo_rows(integration_app)


def run_concurrent_repeat_starts(monkeypatch, client_a, headers_a, client_b, headers_b, case_id, tech_id):
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
                "method_description": "Concurrent repeat plan",
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


def test_concurrent_repeat_starts_only_one_commits(
    integration_app, create_integration_user, monkeypatch
):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    setup = integration_app.test_client()
    setup_token = login(setup, admin_name).get_json()["data"]["csrf_token"]
    setup_headers = auth_headers(setup_token)
    try:
        _, farm_id = seed_farm(setup, setup_headers)
        tech_id = technician_id_for(integration_app, tech_name)
        case_id, first_id = seed_follow_up_due_case(
            setup, setup_headers, farm_id, demo_value("pest"), tech_id
        )
        assert record_follow_up(
            setup, setup_headers, first_id, outcome="REINTERVENTION_REQUIRED", pest_observed=True
        ).status_code == 201
        client_a = integration_app.test_client()
        client_b = integration_app.test_client()
        headers_a = auth_headers(login(client_a, admin_name).get_json()["data"]["csrf_token"])
        headers_b = auth_headers(login(client_b, admin_name).get_json()["data"]["csrf_token"])
        first, second = run_concurrent_repeat_starts(
            monkeypatch, client_a, headers_a, client_b, headers_b, case_id, tech_id
        )
        assert {first.status_code, second.status_code} == {201, 409}
        with integration_app.app_context():
            db.session.remove()
            count = db.session.scalar(
                select(db.func.count()).select_from(Intervention).where(Intervention.pest_case_id == case_id)
            )
            assert count == 2
            db.session.remove()
    finally:
        cleanup_demo_rows(integration_app)


def test_follow_up_vs_competing_start_rollback_integrity(
    integration_app, create_integration_user, monkeypatch
):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    setup = integration_app.test_client()
    setup_token = login(setup, admin_name).get_json()["data"]["csrf_token"]
    setup_headers = auth_headers(setup_token)
    try:
        _, farm_id = seed_farm(setup, setup_headers)
        tech_id = technician_id_for(integration_app, tech_name)
        case_id, intervention_id = seed_follow_up_due_case(
            setup, setup_headers, farm_id, demo_value("pest"), tech_id
        )
        follow_up_ready = Event()
        release_follow_up = Event()
        start_attempting = Event()
        original_follow_commit = follow_ups_module.commit_follow_up_changes
        calls = {"commits": 0}

        def coordinated_follow_commit():
            calls["commits"] += 1
            if calls["commits"] == 1:
                follow_up_ready.set()
                assert release_follow_up.wait(timeout=10)
            return original_follow_commit()

        original_follow_acquire = follow_ups_module.acquire_follow_up_case_lock
        original_case_acquire = pest_cases_module.acquire_pest_case_transition_lock
        acquires = {"count": 0}

        def observed_follow_acquire(target):
            return original_follow_acquire(target)

        def observed_case_acquire(target):
            acquires["count"] += 1
            if acquires["count"] == 1:
                start_attempting.set()
            return original_case_acquire(target)

        monkeypatch.setattr(follow_ups_module, "commit_follow_up_changes", coordinated_follow_commit)
        monkeypatch.setattr(follow_ups_module, "acquire_follow_up_case_lock", observed_follow_acquire)
        monkeypatch.setattr(pest_cases_module, "acquire_pest_case_transition_lock", observed_case_acquire)

        client_a = integration_app.test_client()
        client_b = integration_app.test_client()
        headers_a = auth_headers(login(client_a, admin_name).get_json()["data"]["csrf_token"])
        headers_b = auth_headers(login(client_b, admin_name).get_json()["data"]["csrf_token"])

        def record():
            return client_a.post(
                f"{INTERVENTIONS}/{intervention_id}/record-follow-up",
                json={
                    "observed_on": "2026-10-09",
                    "pest_observed": False,
                    "assessment_notes": "Race winner reassessment",
                    "outcome": "RESOLVED",
                },
                headers=headers_a,
            )

        def compete():
            return client_b.post(
                f"{CASES}/{case_id}/start-intervention",
                json={
                    "method_category": "CULTURAL",
                    "method_description": "Race loser repeat",
                    "scheduled_for": "2026-10-15",
                    "assigned_to_user_id": tech_id,
                },
                headers=headers_b,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(record)
            assert follow_up_ready.wait(timeout=10)
            second = executor.submit(compete)
            try:
                assert start_attempting.wait(timeout=10)
                assert not second.done()
            finally:
                release_follow_up.set()
            first_result = first.result(timeout=10)
            second_result = second.result(timeout=10)

        assert first_result.status_code == 201
        # FOLLOW_UP_DUE cannot start directly; after the winner closes the
        # case the loser must also fail without modifying committed state.
        assert second_result.status_code == 409
        with integration_app.app_context():
            db.session.remove()
            status = db.session.scalar(select(PestCase.status).where(PestCase.id == case_id))
            assert status == "CLOSED"
            count = db.session.scalar(
                select(db.func.count()).select_from(Intervention).where(Intervention.pest_case_id == case_id)
            )
            assert count == 1
            fu_count = db.session.scalar(
                select(db.func.count()).select_from(FollowUp).where(FollowUp.intervention_id == intervention_id)
            )
            assert fu_count == 1
            notes = db.session.scalar(
                select(FollowUp.assessment_notes).where(FollowUp.intervention_id == intervention_id)
            )
            assert notes == "Race winner reassessment"
            db.session.remove()
    finally:
        cleanup_demo_rows(integration_app)
