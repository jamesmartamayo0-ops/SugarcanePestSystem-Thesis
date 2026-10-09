from uuid import uuid4

from sqlalchemy import delete, select

from app.extensions import db
from app.models import Farm, Farmer, FollowUp, Inspection, Intervention, PestCase, UserRole

CASES = "/api/v1/pest-cases"
INSPECTIONS = "/api/v1/inspections"
INTERVENTIONS = "/api/v1/interventions"
DASHBOARD = "/api/v1/dashboard/summary"
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


def seed_farm(client, headers, farmer_name=None, plot=None):
    farmer_name = farmer_name or demo_value("farmer")
    plot = plot or demo_value("plot")
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
    return farmer_name, farm_id, farmer_id


def seed_reported_case(client, headers, farm_id, pest_name):
    response = client.post(
        CASES,
        json={"farm_id": farm_id, "pest_name": pest_name, "reported_area_hectares": 1},
        headers=headers,
    )
    assert response.status_code == 201
    return response.get_json()["data"]["pest_case"]["id"]


def seed_validated_case(client, headers, farm_id, pest_name, tech_id):
    case_id = seed_reported_case(client, headers, farm_id, pest_name)
    assert client.post(f"{CASES}/{case_id}/submit-for-inspection", headers=headers).status_code == 200
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


def test_dashboard_counts_using_real_rows(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    admin_token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(admin_token)
    try:
        _, farm_id = seed_farm(client, headers)[:2]
        tech_id = technician_id_for(integration_app, tech_name)
        reported_id = seed_reported_case(client, headers, farm_id, demo_value("pest"))
        validated_id = seed_validated_case(client, headers, farm_id, demo_value("pest"), tech_id)
        assert validated_id != reported_id
        before = client.get(DASHBOARD, headers=headers).get_json()["data"]["summary"]
        assert before["totals"]["farmers"] >= 1
        assert before["totals"]["farms"] >= 1
        assert before["totals"]["pest_cases"] >= 2
        assert set(before["by_status"]) == {
            "REPORTED",
            "FOR_INSPECTION",
            "INSPECTION_SCHEDULED",
            "FIELD_VALIDATED",
            "NOT_CONFIRMED",
            "UNDER_INTERVENTION",
            "FOLLOW_UP_DUE",
            "REINTERVENTION_REQUIRED",
            "CLOSED",
        }
        assert sum(before["by_status"].values()) == before["totals"]["pest_cases"]
        assert before["action_needed"]["awaiting_inspection_scheduling"] >= 0
        assert client.get(DASHBOARD, headers=headers).headers["Cache-Control"] == "no-store"
    finally:
        cleanup_demo_rows(integration_app)


def test_dashboard_overdue_and_no_double_count(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    admin_token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(admin_token)
    try:
        _, farm_id = seed_farm(client, headers)[:2]
        tech_id = technician_id_for(integration_app, tech_name)
        # Overdue queue item (performed 2026-10-07, due 2026-10-08 < Manila today).
        overdue_case = seed_validated_case(client, headers, farm_id, demo_value("pest"), tech_id)
        overdue_intervention = start_for_case(client, headers, overdue_case, tech_id).get_json()["data"]["intervention"]["id"]
        assert complete_intervention(client, headers, overdue_intervention, performed_on="2026-10-07", follow_up_due_on="2026-10-08").status_code == 200
        # Repeat cycle: first follow-up requires reintervention, second completes and closes.
        # Historical completed interventions must not double-count the queue.
        repeat_case = seed_validated_case(client, headers, farm_id, demo_value("pest"), tech_id)
        first_id = start_for_case(client, headers, repeat_case, tech_id).get_json()["data"]["intervention"]["id"]
        assert complete_intervention(client, headers, first_id).status_code == 200
        assert record_follow_up(client, headers, first_id, outcome="REINTERVENTION_REQUIRED", pest_observed=True).status_code == 201
        second_id = start_for_case(client, headers, repeat_case, tech_id).get_json()["data"]["intervention"]["id"]
        assert complete_intervention(client, headers, second_id).status_code == 200
        summary = client.get(DASHBOARD, headers=headers).get_json()["data"]["summary"]
        assert summary["action_needed"]["overdue_follow_ups"] >= 1
        assert summary["action_needed"]["overdue_follow_ups"] <= summary["action_needed"]["follow_ups_due"]
        # Closing the repeat case removes it from the queue without touching history.
        assert record_follow_up(client, headers, second_id, outcome="RESOLVED").status_code == 201
        after = client.get(DASHBOARD, headers=headers).get_json()["data"]["summary"]
        assert after["by_status"]["CLOSED"] >= 1
        with integration_app.app_context():
            db.session.remove()
            count = db.session.scalar(
                select(db.func.count()).select_from(Intervention).where(Intervention.pest_case_id == repeat_case)
            )
            assert count == 2
            db.session.remove()
    finally:
        cleanup_demo_rows(integration_app)


def test_timeline_full_repeat_cycle_to_closure(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    admin_token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(admin_token)
    try:
        _, farm_id = seed_farm(client, headers)[:2]
        tech_id = technician_id_for(integration_app, tech_name)
        case_id = seed_validated_case(client, headers, farm_id, demo_value("pest"), tech_id)
        first_id = start_for_case(client, headers, case_id, tech_id).get_json()["data"]["intervention"]["id"]
        assert complete_intervention(client, headers, first_id).status_code == 200
        assert record_follow_up(client, headers, first_id, outcome="REINTERVENTION_REQUIRED", pest_observed=True).status_code == 201
        second_id = start_for_case(client, headers, case_id, tech_id).get_json()["data"]["intervention"]["id"]
        assert complete_intervention(client, headers, second_id).status_code == 200
        assert record_follow_up(client, headers, second_id, outcome="RESOLVED").status_code == 201
        body = client.get(f"{CASES}/{case_id}/timeline", headers=headers).get_json()["data"]
        assert body["pest_case"]["status"] == "CLOSED"
        timeline = body["timeline"]
        assert [e["event_type"] for e in timeline if e["event_type"] == "case_reported"]
        assert "inspection_scheduled" in [e["event_type"] for e in timeline]
        cycles = sorted({e["cycle"] for e in timeline if e["cycle"] is not None})
        assert cycles == [1, 2]
        outcomes = [e["metadata"].get("outcome") for e in timeline if e["event_type"] == "follow_up_recorded"]
        assert outcomes == ["REINTERVENTION_REQUIRED", "RESOLVED"]
        assert timeline[-1]["event_type"] == "case_closed"
        # Deterministic ordering across requests.
        again = client.get(f"{CASES}/{case_id}/timeline", headers=headers).get_json()["data"]["timeline"]
        assert [e["event_type"] for e in timeline] == [e["event_type"] for e in again]
        # Missing case.
        assert client.get(f"{CASES}/2147483647/timeline", headers=headers).status_code == 404
        # No fabricated reschedule history.
        assert all(e["event_type"] != "inspection_rescheduled" for e in timeline)
    finally:
        cleanup_demo_rows(integration_app)


def test_search_across_real_data_and_combined_filters(integration_app, create_integration_user):
    _, admin_name = create_integration_user(role=UserRole.ADMIN)
    _, tech_name = create_integration_user(role=UserRole.TECHNICIAN)
    client = integration_app.test_client()
    admin_token = login(client, admin_name).get_json()["data"]["csrf_token"]
    headers = auth_headers(admin_token)
    try:
        farmer_name, farm_id, farmer_id = seed_farm(client, headers)
        tech_id = technician_id_for(integration_app, tech_name)
        pest_name = demo_value("pest")
        case_id = seed_reported_case(client, headers, farm_id, pest_name)
        # q matches pest name, farmer name, plot, and numeric ID.
        assert any(c["id"] == case_id for c in client.get(f"{CASES}?q={pest_name}", headers=headers).get_json()["data"]["pest_cases"])
        assert any(c["id"] == case_id for c in client.get(f"{CASES}?q={farmer_name}", headers=headers).get_json()["data"]["pest_cases"])
        assert any(c["id"] == case_id for c in client.get(f"{CASES}?q={case_id}", headers=headers).get_json()["data"]["pest_cases"])
        assert client.get(f"{CASES}?q=NoSuchPestXYZ123", headers=headers).get_json()["data"]["pest_cases"] == []
        # Combined status + farm + farmer + q.
        combined = client.get(
            f"{CASES}?status=REPORTED&farm_id={farm_id}&farmer_id={farmer_id}&q={pest_name}",
            headers=headers,
        )
        assert combined.status_code == 200
        assert any(c["id"] == case_id for c in combined.get_json()["data"]["pest_cases"])
        # Mismatched combined filter yields empty.
        empty = client.get(f"{CASES}?status=CLOSED&farm_id={farm_id}&q={pest_name}", headers=headers)
        assert empty.get_json()["data"]["pest_cases"] == []
        # Malformed and impossible filters.
        assert client.get(f"{CASES}?status=BOGUS", headers=headers).status_code == 400
        assert client.get(f"{CASES}?farm_id=abc", headers=headers).status_code == 400
        assert client.get(f"{CASES}?farmer_id=abc", headers=headers).status_code == 400
        assert client.get(f"{CASES}?reported_from=not-a-date", headers=headers).status_code == 400
        assert client.get(f"{CASES}?reported_from=2026-10-10&reported_to=2026-10-01", headers=headers).status_code == 400
        assert client.get(f"{CASES}?q={'x' * 121}", headers=headers).status_code == 400
        # Injection-like text is ordinary search text.
        injection = client.get(f"{CASES}?q=' OR '1'='1", headers=headers)
        assert injection.status_code == 200
        # Existing behavior preserved.
        assert client.get(f"{CASES}?status=REPORTED", headers=headers).status_code == 200
        # Date filter returns the reported case.
        assert any(
            c["id"] == case_id
            for c in client.get(f"{CASES}?reported_from=2026-01-01&reported_to=2026-12-31", headers=headers).get_json()["data"]["pest_cases"]
        )
        # Case-insensitive match.
        assert any(
            c["id"] == case_id
            for c in client.get(f"{CASES}?q={pest_name.upper()}", headers=headers).get_json()["data"]["pest_cases"]
        )
        _ = tech_id
    finally:
        cleanup_demo_rows(integration_app)
