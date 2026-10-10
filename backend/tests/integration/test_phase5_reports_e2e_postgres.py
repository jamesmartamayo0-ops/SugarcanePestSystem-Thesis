from uuid import uuid4

from sqlalchemy import delete, select

from app.demo_data import DEMO_FARMERS, DEMO_FARMS, manila_today, seed_demo_data
from app.extensions import db
from app.models import Farm, Farmer, FollowUp, Inspection, Intervention, PestCase, User, UserRole

CASES = "/api/v1/pest-cases"
INSPECTIONS = "/api/v1/inspections"
INTERVENTIONS = "/api/v1/interventions"
DASHBOARD = "/api/v1/dashboard/summary"
REPORTS = "/api/v1/reports/operational"
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


def technician_id_for(app, username):
    from app.models import User

    with app.app_context():
        db.session.remove()
        user_id = db.session.scalar(select(User.id).where(User.username == username))
        db.session.remove()
        return user_id


def demo_technician_id(app):
    """Return the id of the "demo.tech" account, or None if absent."""
    with app.app_context():
        db.session.remove()
        try:
            return db.session.scalar(select(User.id).where(User.username == "demo.tech"))
        finally:
            db.session.remove()


def demo_dataset_case_ids(app):
    """Return PestCase ids owned by the deterministic Phase 5 demo dataset.

    Ownership is proven through the seeder's exact constants: farmers whose
    full_name is one of DEMO_FARMERS, farms whose plot_identifier is one of
    DEMO_FARMS *and* whose farmer is one of those demo farmers, and cases on
    those farms. Pest-name text is never used as an ownership criterion, so
    an unrelated case such as "Research Trial (Synthetic)" is excluded.
    """
    with app.app_context():
        db.session.remove()
        try:
            farmer_names = [name for name, _ in DEMO_FARMERS]
            farm_plots = [plot for _, plot, _, _ in DEMO_FARMS]
            demo_farmer_ids = db.session.scalars(
                select(Farmer.id).where(Farmer.full_name.in_(farmer_names))
            ).all()
            if not demo_farmer_ids:
                return []
            demo_farm_ids = db.session.scalars(
                select(Farm.id).where(
                    Farm.farmer_id.in_(demo_farmer_ids),
                    Farm.plot_identifier.in_(farm_plots),
                )
            ).all()
            if not demo_farm_ids:
                return []
            return db.session.scalars(
                select(PestCase.id).where(PestCase.farm_id.in_(demo_farm_ids))
            ).all()
        finally:
            db.session.remove()


def cleanup_demo_seed(app, demo_tech_existed_before):
    """Delete ONLY rows owned by the deterministic Phase 5 demo dataset.

    Demo cases are identified through exact DEMO_FARMERS / DEMO_FARMS
    membership (never pest-name text matching). Dependents are removed in
    FK-safe order: FollowUp -> Intervention + Inspection -> PestCase ->
    Farm -> Farmer. The "demo.tech" account is deleted only when the caller
    recorded that it did NOT exist before seeding (i.e. this run created
    it); a pre-existing account is always preserved. Never touches itest_*
    workflow rows or other users. No TRUNCATE.
    """
    with app.app_context():
        db.session.remove()
        try:
            farmer_names = [name for name, _ in DEMO_FARMERS]
            farm_plots = [plot for _, plot, _, _ in DEMO_FARMS]
            demo_farmer_ids = db.session.scalars(
                select(Farmer.id).where(Farmer.full_name.in_(farmer_names))
            ).all()
            demo_farm_ids = []
            if demo_farmer_ids:
                demo_farm_ids = db.session.scalars(
                    select(Farm.id).where(
                        Farm.farmer_id.in_(demo_farmer_ids),
                        Farm.plot_identifier.in_(farm_plots),
                    )
                ).all()
            demo_case_ids = []
            if demo_farm_ids:
                demo_case_ids = db.session.scalars(
                    select(PestCase.id).where(PestCase.farm_id.in_(demo_farm_ids))
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
                db.session.execute(
                    delete(PestCase).where(PestCase.id.in_(demo_case_ids))
                )
            if demo_farm_ids:
                db.session.execute(delete(Farm).where(Farm.id.in_(demo_farm_ids)))
            if demo_farmer_ids:
                db.session.execute(delete(Farmer).where(Farmer.id.in_(demo_farmer_ids)))
            if not demo_tech_existed_before:
                created_tech_id = db.session.scalar(
                    select(User.id).where(User.username == "demo.tech")
                )
                if created_tech_id is not None:
                    db.session.execute(delete(User).where(User.id == created_tech_id))
            db.session.commit()
        finally:
            db.session.remove()


def test_demo_seeder_inspection_chronology(integration_app, create_integration_user):
    # Exercises the REAL demo seeder (same implementation as `seed-demo-data`
    # and backend/scripts/seed_demo_data.py) and asserts chronology on the
    # actual seeded Inspection rows. Fails if the seeder regresses to
    # inspected_on preceding scheduled_for. Demo cases are identified through
    # exact DEMO_FARMERS / DEMO_FARMS membership, never pest-name text.
    create_integration_user(role=UserRole.ADMIN)
    create_integration_user(role=UserRole.TECHNICIAN)
    demo_tech_existed_before = demo_technician_id(integration_app) is not None
    cleanup_demo_seed(integration_app, demo_tech_existed_before)
    try:
        with integration_app.app_context():
            db.session.remove()
            result = seed_demo_data()
            assert result.get("seeded") is True
            today = manila_today()
            demo_case_ids = demo_dataset_case_ids(integration_app)
            assert demo_case_ids, "Expected seeded synthetic pest cases."
            completed = db.session.scalars(
                select(Inspection)
                .where(
                    Inspection.pest_case_id.in_(demo_case_ids),
                    Inspection.inspected_on.is_not(None),
                )
                .order_by(Inspection.id)
            ).all()
            assert len(completed) >= 1, "Expected seeded completed inspections."
            for inspection in completed:
                assert inspection.scheduled_for <= inspection.inspected_on <= today, (
                    f"Demo inspection #{inspection.id}: "
                    f"{inspection.scheduled_for} <= {inspection.inspected_on} <= {today}"
                )
            pending = db.session.scalars(
                select(Inspection).where(
                    Inspection.pest_case_id.in_(demo_case_ids),
                    Inspection.inspected_on.is_(None),
                )
            ).all()
            assert len(pending) == 1, "Expected one pending synthetic inspection."
            assert pending[0].completed_at is None
            assert pending[0].scheduled_for >= today
            db.session.remove()
    finally:
        cleanup_demo_seed(integration_app, demo_tech_existed_before)


def test_demo_cleanup_preserves_unrelated_records(integration_app, create_integration_user):
    # An unrelated synthetic-looking case on a NON-demo farm, a non-demo
    # technician, and a pre-existing demo.tech account must all survive the
    # narrowed demo cleanup. A demo.tech created during the run itself may
    # be removed once the caller proves it did not pre-exist.
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    tech_id = technician_id_for(integration_app, tech_name)
    client = integration_app.test_client()
    admin_token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(admin_token)
    demo_tech_id = None
    try:
        _, farm_id = seed_farm(client, headers)
        decoy_name = f"itest_research_trial_{uuid4().hex} (Synthetic)"
        decoy_id = client.post(
            CASES,
            json={"farm_id": farm_id, "pest_name": decoy_name, "reported_area_hectares": 1},
            headers=headers,
        ).get_json()["data"]["pest_case"]["id"]
        # Simulate a demo.tech account that predates this test run.
        with integration_app.app_context():
            db.session.remove()
            assert db.session.scalar(select(User.id).where(User.username == "demo.tech")) is None
            preexisting = User(
                username="demo.tech",
                full_name="Pre-existing Demo Account",
                role="TECHNICIAN",
                is_active=True,
            )
            preexisting.set_password(TEST_PASSWORD)
            db.session.add(preexisting)
            db.session.flush()
            demo_tech_id = preexisting.id
            db.session.commit()
            db.session.remove()
        # Pre-existing demo.tech is preserved along with the decoy case.
        cleanup_demo_seed(integration_app, demo_tech_existed_before=True)
        with integration_app.app_context():
            db.session.remove()
            assert db.session.get(PestCase, decoy_id) is not None
            assert db.session.get(User, demo_tech_id) is not None
            assert db.session.get(User, tech_id) is not None
            db.session.remove()
        # A demo.tech created during the run itself may be removed; the
        # decoy case and the unrelated technician still survive.
        cleanup_demo_seed(integration_app, demo_tech_existed_before=False)
        with integration_app.app_context():
            db.session.remove()
            assert db.session.get(User, demo_tech_id) is None
            assert db.session.get(PestCase, decoy_id) is not None
            assert db.session.get(User, tech_id) is not None
            db.session.remove()
        demo_tech_id = None
    finally:
        if demo_tech_id is not None:
            with integration_app.app_context():
                db.session.execute(delete(User).where(User.id == demo_tech_id))
                db.session.commit()
                db.session.remove()
        cleanup_demo_rows(integration_app)


def test_full_two_intervention_lifecycle_e2e(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    admin_token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(admin_token)
    try:
        _, farm_id = seed_farm(client, headers)
        tech_id = technician_id_for(integration_app, tech_name)
        pest_name = demo_value("pest")

        # 1-3. Report, submit, schedule.
        reported = client.post(
            CASES,
            json={"farm_id": farm_id, "pest_name": pest_name, "reported_area_hectares": 1},
            headers=headers,
        )
        assert reported.status_code == 201
        case_id = reported.get_json()["data"]["pest_case"]["id"]
        assert client.post(f"{CASES}/{case_id}/submit-for-inspection", headers=headers).status_code == 200
        scheduled = client.post(
            f"{CASES}/{case_id}/schedule-inspection",
            json={"scheduled_for": "2026-10-15", "assigned_to_user_id": tech_id},
            headers=headers,
        )
        assert scheduled.status_code == 201
        inspection_id = scheduled.get_json()["data"]["inspection"]["id"]

        # 4. Confirmed findings.
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

        # 5-6. First intervention cycle.
        first = client.post(
            f"{CASES}/{case_id}/start-intervention",
            json={
                "method_category": "CULTURAL",
                "method_description": "Manual removal of affected shoots",
                "scheduled_for": "2026-10-15",
                "assigned_to_user_id": tech_id,
            },
            headers=headers,
        )
        assert first.status_code == 201
        first_id = first.get_json()["data"]["intervention"]["id"]
        completed = client.post(
            f"{INTERVENTIONS}/{first_id}/complete",
            json={
                "performed_on": "2026-10-09",
                "completion_notes": "Cleared affected shoots",
                "follow_up_due_on": "2026-10-20",
            },
            headers=headers,
        )
        assert completed.status_code == 200

        # 7. First follow-up requires reintervention.
        follow1 = client.post(
            f"{INTERVENTIONS}/{first_id}/record-follow-up",
            json={
                "observed_on": "2026-10-09",
                "pest_observed": True,
                "observed_affected_area_hectares": 0.5,
                "assessment_notes": "Regrowth observed",
                "outcome": "REINTERVENTION_REQUIRED",
            },
            headers=headers,
        )
        assert follow1.status_code == 201

        # 8-10. Second intervention cycle resolving the case.
        second = client.post(
            f"{CASES}/{case_id}/start-intervention",
            json={
                "method_category": "MECHANICAL",
                "method_description": "Repeat removal of regrowth",
                "scheduled_for": "2026-10-15",
                "assigned_to_user_id": tech_id,
            },
            headers=headers,
        )
        assert second.status_code == 201
        second_id = second.get_json()["data"]["intervention"]["id"]
        assert second_id != first_id
        assert client.post(
            f"{INTERVENTIONS}/{second_id}/complete",
            json={
                "performed_on": "2026-10-09",
                "completion_notes": "Regrowth cleared",
                "follow_up_due_on": "2026-10-20",
            },
            headers=headers,
        ).status_code == 200
        follow2 = client.post(
            f"{INTERVENTIONS}/{second_id}/record-follow-up",
            json={
                "observed_on": "2026-10-09",
                "pest_observed": False,
                "assessment_notes": "Canopy recovering",
                "outcome": "RESOLVED",
            },
            headers=headers,
        )
        assert follow2.status_code == 201

        # 11. Closed with both histories retained.
        with integration_app.app_context():
            db.session.remove()
            assert db.session.scalar(select(PestCase.status).where(PestCase.id == case_id)) == "CLOSED"
            interventions = db.session.scalars(
                select(Intervention).where(Intervention.pest_case_id == case_id).order_by(Intervention.id)
            ).all()
            assert [i.id for i in interventions] == [first_id, second_id]
            follow_ups = db.session.scalars(
                select(FollowUp)
                .join(Intervention, Intervention.id == FollowUp.intervention_id)
                .where(Intervention.pest_case_id == case_id)
                .order_by(FollowUp.id)
            ).all()
            assert len(follow_ups) == 2
            db.session.remove()

        # 12. Timeline contains both cycles.
        timeline = client.get(f"{CASES}/{case_id}/timeline", headers=headers).get_json()["data"]["timeline"]
        assert sorted({e["cycle"] for e in timeline if e["cycle"] is not None}) == [1, 2]

        # 13-14. Dashboard and report reflect closure.
        dashboard = client.get(DASHBOARD, headers=headers).get_json()["data"]["summary"]
        assert dashboard["by_status"]["CLOSED"] >= 1
        report = client.get(REPORTS, headers=headers).get_json()["data"]["report"]
        assert report["summary"]["closed_cases"] >= 1
        assert report["intervention_summary"]["cases_with_repeat_intervention"] >= 1
        assert any(r["case_id"] == case_id and r["latest_intervention_cycle"] == 2 for r in report["cases"])
    finally:
        cleanup_demo_rows(integration_app)


def test_not_confirmed_path_e2e(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    admin_token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(admin_token)
    try:
        _, farm_id = seed_farm(client, headers)
        tech_id = technician_id_for(integration_app, tech_name)
        case_id = client.post(
            CASES,
            json={"farm_id": farm_id, "pest_name": demo_value("pest"), "reported_area_hectares": 1},
            headers=headers,
        ).get_json()["data"]["pest_case"]["id"]
        assert client.post(f"{CASES}/{case_id}/submit-for-inspection", headers=headers).status_code == 200
        inspection_id = client.post(
            f"{CASES}/{case_id}/schedule-inspection",
            json={"scheduled_for": "2026-10-15", "assigned_to_user_id": tech_id},
            headers=headers,
        ).get_json()["data"]["inspection"]["id"]
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
        assert recorded.get_json()["data"]["inspection"]["pest_case"]["status"] == "NOT_CONFIRMED"

        # Intervention rejected; no records created.
        assert client.post(
            f"{CASES}/{case_id}/start-intervention",
            json={
                "method_category": "CULTURAL",
                "method_description": "Should not start",
                "scheduled_for": "2026-10-15",
                "assigned_to_user_id": tech_id,
            },
            headers=headers,
        ).status_code == 409
        with integration_app.app_context():
            db.session.remove()
            assert db.session.scalar(select(PestCase.status).where(PestCase.id == case_id)) == "NOT_CONFIRMED"
            assert db.session.scalar(
                select(db.func.count()).select_from(Intervention).where(Intervention.pest_case_id == case_id)
            ) == 0
            db.session.remove()

        timeline = client.get(f"{CASES}/{case_id}/timeline", headers=headers).get_json()["data"]["timeline"]
        assert "inspection_findings_recorded" in [e["event_type"] for e in timeline]
        assert all(e["category"] != "FOLLOW_UP" for e in timeline)
        dashboard = client.get(DASHBOARD, headers=headers).get_json()["data"]["summary"]
        assert dashboard["by_status"]["NOT_CONFIRMED"] >= 1
        report = client.get(f"{REPORTS}?status=NOT_CONFIRMED", headers=headers).get_json()["data"]["report"]
        assert report["summary"]["not_confirmed_cases"] >= 1
        assert any(r["case_id"] == case_id for r in report["cases"])
    finally:
        cleanup_demo_rows(integration_app)


def test_report_filtering_and_overdue_semantics(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    admin_token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(admin_token)
    try:
        _, farm_id = seed_farm(client, headers)
        tech_id = technician_id_for(integration_app, tech_name)
        pest_name = demo_value("pest")
        case_id = client.post(
            CASES,
            json={"farm_id": farm_id, "pest_name": pest_name, "reported_area_hectares": 1},
            headers=headers,
        ).get_json()["data"]["pest_case"]["id"]
        assert client.post(f"{CASES}/{case_id}/submit-for-inspection", headers=headers).status_code == 200
        inspection_id = client.post(
            f"{CASES}/{case_id}/schedule-inspection",
            json={"scheduled_for": "2026-10-15", "assigned_to_user_id": tech_id},
            headers=headers,
        ).get_json()["data"]["inspection"]["id"]
        assert client.post(
            f"{INSPECTIONS}/{inspection_id}/record-findings",
            json={
                "findings": "Bored stalks",
                "pest_confirmed": True,
                "validated_area_hectares": 1,
                "inspected_on": "2026-10-07",
            },
            headers=headers,
        ).status_code == 200
        intervention_id = client.post(
            f"{CASES}/{case_id}/start-intervention",
            json={
                "method_category": "CULTURAL",
                "method_description": "Work",
                "scheduled_for": "2026-10-15",
                "assigned_to_user_id": tech_id,
            },
            headers=headers,
        ).get_json()["data"]["intervention"]["id"]
        assert client.post(
            f"{INTERVENTIONS}/{intervention_id}/complete",
            json={
                "performed_on": "2026-10-07",
                "completion_notes": "Done",
                "follow_up_due_on": "2026-10-08",
            },
            headers=headers,
        ).status_code == 200
        report = client.get(REPORTS, headers=headers).get_json()["data"]["report"]
        assert report["follow_up_summary"]["pending"] >= 1
        assert report["follow_up_summary"]["overdue"] <= report["follow_up_summary"]["pending"]
        filtered = client.get(f"{REPORTS}?status=FOLLOW_UP_DUE&farm_id={farm_id}", headers=headers)
        assert filtered.status_code == 200
        assert any(r["case_id"] == case_id for r in filtered.get_json()["data"]["report"]["cases"])
        assert client.get(f"{REPORTS}?status=BOGUS", headers=headers).status_code == 400
    finally:
        cleanup_demo_rows(integration_app)
