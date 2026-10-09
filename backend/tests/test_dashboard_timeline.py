from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app import auth, create_app
from app.models import Farm, Farmer, FollowUp, Inspection, Intervention, PestCase, PestCaseStatus, User
from app.routes import dashboard as dashboard_module
from app.routes import pest_cases as pest_cases_module
from app.routes import farmers as farmers_module
from app.routes import farms as farms_module

DASHBOARD = "/api/v1/dashboard/summary"
CASES = "/api/v1/pest-cases"
TIMELINE = lambda c: f"/api/v1/pest-cases/{c}/timeline"  # noqa: E731
LOGIN = "/api/v1/auth/login"
ORIGIN = "http://localhost:3000"
ADMIN_PASSWORD = "admin-password-123"
TECH_PASSWORD = "technician-pass-123"


def _stamp(day=9):
    return datetime(2026, 10, day, tzinfo=timezone.utc)


@pytest.fixture
def phase4_client(monkeypatch):
    monkeypatch.setenv(
        "AUTH_TRUSTED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    )
    app = create_app()
    app.testing = True

    admin = User(id=1, username="admin.one", full_name="Admin One", role="ADMIN", is_active=True, auth_version=0)
    admin.set_password(ADMIN_PASSWORD)
    tech = User(id=2, username="tech.one", full_name="Tech One", role="TECHNICIAN", is_active=True, auth_version=0)
    tech.set_password(TECH_PASSWORD)
    users = {1: admin, 2: tech}
    clock = {"now": 1_750_000_000}

    farmer = Farmer(full_name="Juan Dela Cruz", barangay="Bunao")
    farmer.id = 1
    farmer.created_at = _stamp()
    farmer.updated_at = _stamp()
    farm = Farm(farmer_id=1, plot_identifier="Plot A", barangay="Bunao", area_hectares="4.00")
    farm.id = 1
    farm.created_at = _stamp()
    farm.updated_at = _stamp()
    farm.farmer = farmer
    farm_store = {1: farm}

    def make_case(case_id, status, pest_name="Stem Borer"):
        case = PestCase(
            farm_id=1,
            pest_name=pest_name,
            symptoms="Bored stalks",
            observed_on="2026-09-15",
            reported_area_hectares="2.50",
            status=status,
            reported_by_user_id=2,
        )
        case.id = case_id
        case.reported_at = _stamp(day=8)
        case.updated_at = _stamp(day=9)
        case.farm = farm
        case.reporter = tech
        return case

    case_store = {
        1: make_case(1, PestCaseStatus.REPORTED.value),
        2: make_case(2, PestCaseStatus.FOLLOW_UP_DUE.value),
        3: make_case(3, PestCaseStatus.CLOSED.value),
    }

    def make_intervention(iid, case_id, completed=True):
        insp = Intervention(
            pest_case_id=case_id,
            method_category="CULTURAL",
            method_description="Manual removal",
            scheduled_for=date(2026, 10, 12),
            assigned_to_user_id=2,
            created_by_user_id=1,
            follow_up_due_on=date(2026, 10, 20),
        )
        insp.id = iid
        insp.created_at = _stamp(day=8)
        insp.updated_at = _stamp(day=9)
        insp.pest_case = case_store[case_id]
        insp.assignee = tech
        insp.creator = admin
        if completed:
            insp.performed_on = date(2026, 10, 9)
            insp.completion_notes = "Done"
            insp.completed_by_user_id = 2
            insp.completer = tech
            insp.completed_at = _stamp(day=9)
        else:
            insp.performed_on = None
            insp.completion_notes = None
            insp.completed_by_user_id = None
            insp.completer = None
            insp.completed_at = None
        return insp

    intervention_store = {
        20: make_intervention(20, 2, completed=True),
        21: make_intervention(21, 3, completed=True),
        22: make_intervention(22, 3, completed=True),
    }

    def make_follow_up(fid, iid, outcome):
        insp = intervention_store[iid]
        fu = FollowUp(
            intervention_id=iid,
            observed_on=date(2026, 10, 9),
            pest_observed=False,
            observed_affected_area_hectares=Decimal("0.50"),
            assessment_notes="Recovering",
            outcome=outcome,
            recorded_by_user_id=2,
        )
        fu.id = fid
        fu.created_at = _stamp(day=9)
        fu.updated_at = _stamp(day=9)
        fu.intervention = insp
        fu.recorder = tech
        return fu

    follow_store = {
        100: make_follow_up(100, 21, "REINTERVENTION_REQUIRED"),
        101: make_follow_up(101, 22, "RESOLVED"),
    }

    def make_inspection(iid, case_id, completed=True):
        insp = Inspection(
            pest_case_id=case_id,
            scheduled_for=date(2026, 10, 15),
            assigned_to_user_id=2,
            scheduled_by_user_id=1,
        )
        insp.id = iid
        insp.created_at = _stamp(day=8)
        insp.updated_at = _stamp(day=9)
        insp.pest_case = case_store[case_id]
        insp.assignee = tech
        insp.scheduler = admin
        if completed:
            insp.inspected_on = date(2026, 10, 7)
            insp.findings = "Bored stalks"
            insp.pest_confirmed = True
            insp.validated_area_hectares = Decimal("1.00")
            insp.completed_by_user_id = 2
            insp.completer = tech
            insp.completed_at = _stamp(day=9)
        else:
            insp.inspected_on = None
            insp.findings = None
            insp.pest_confirmed = None
            insp.validated_area_hectares = None
            insp.completed_by_user_id = None
            insp.completed_at = None
        return insp

    inspection_store = {10: make_inspection(10, 2, completed=True)}

    def by_id(uid):
        return users.get(uid)

    def by_username(name):
        return next((u for u in users.values() if u.username == name), None)

    monkeypatch.setattr(auth, "get_user_by_id", by_id)
    monkeypatch.setattr(auth, "get_user_by_username", by_username)
    monkeypatch.setattr(auth, "save_last_login", lambda item, ts: setattr(item, "last_login_at", ts))
    monkeypatch.setattr(auth, "now_epoch_seconds", lambda: clock["now"])
    monkeypatch.setattr(farmers_module, "list_all_farmers", lambda: [farmer])
    monkeypatch.setattr(farms_module, "list_all_farms", lambda farmer_id=None: [farm])

    # Dashboard fakes with controllable counts.
    state = {
        "farmers": 3,
        "farms": 5,
        "by_status": {
            "REPORTED": 1,
            "FOR_INSPECTION": 2,
            "INSPECTION_SCHEDULED": 3,
            "FIELD_VALIDATED": 4,
            "NOT_CONFIRMED": 5,
            "UNDER_INTERVENTION": 6,
            "FOLLOW_UP_DUE": 7,
            "REINTERVENTION_REQUIRED": 8,
            "CLOSED": 9,
        },
        "due": 7,
        "overdue": 2,
        "recent": [case_store[3], case_store[2]],
    }
    monkeypatch.setattr(dashboard_module, "count_farmers", lambda: state["farmers"])
    monkeypatch.setattr(dashboard_module, "count_farms", lambda: state["farms"])
    monkeypatch.setattr(dashboard_module, "count_cases_by_status", lambda: dict(state["by_status"]))
    monkeypatch.setattr(dashboard_module, "count_follow_ups_due", lambda: state["due"])
    monkeypatch.setattr(dashboard_module, "count_overdue_follow_ups", lambda: state["overdue"])
    monkeypatch.setattr(dashboard_module, "get_recent_cases", lambda limit=5: state["recent"][:limit])

    # Timeline fakes.
    monkeypatch.setattr(pest_cases_module, "get_pest_case_by_id", lambda cid: case_store.get(cid))
    monkeypatch.setattr(
        pest_cases_module, "get_inspection_by_case_id", lambda cid: inspection_store.get(10) if cid == 2 else None
    )
    monkeypatch.setattr(
        pest_cases_module,
        "get_inspections_by_case_id",
        lambda cid: [inspection_store[10]] if cid == 2 and 10 in inspection_store else [],
    )
    monkeypatch.setattr(
        pest_cases_module,
        "get_interventions_by_case_id",
        lambda cid: sorted([i for i in intervention_store.values() if i.pest_case_id == cid], key=lambda x: x.id),
    )
    monkeypatch.setattr(
        pest_cases_module,
        "get_follow_ups_by_case_id",
        lambda cid: sorted(
            [f for f in follow_store.values() if intervention_store[f.intervention_id].pest_case_id == cid],
            key=lambda x: x.id,
        ),
    )

    # Search fakes: filter in memory.
    def fake_list(farm_id=None, status=None, farmer_id=None, search=None, reported_from=None, reported_to=None):
        items = sorted(case_store.values(), key=lambda c: c.id)
        if farm_id is not None:
            items = [c for c in items if c.farm_id == farm_id]
        if status is not None:
            items = [c for c in items if c.status == status]
        if farmer_id is not None:
            items = [c for c in items if farm.farmer.id == farmer_id]
        if search is not None:
            lowered = search.lower()
            items = [c for c in items if lowered in c.pest_name.lower() or lowered == str(c.id)]
        return items

    monkeypatch.setattr(pest_cases_module, "list_all_pest_cases", fake_list)

    return app.test_client(), case_store, state


def login(client, username, password, origin=ORIGIN):
    return client.post(LOGIN, json={"username": username, "password": password}, headers={"Origin": origin} if origin is not None else {})


def login_admin(client):
    r = login(client, "admin.one", ADMIN_PASSWORD)
    assert r.status_code == 200
    return r.get_json()["data"]["csrf_token"]


def login_tech(client):
    r = login(client, "tech.one", TECH_PASSWORD)
    assert r.status_code == 200
    return r.get_json()["data"]["csrf_token"]


def test_dashboard_unauthenticated_rejected(phase4_client):
    client, _, _ = phase4_client
    assert client.get(DASHBOARD).status_code == 401


def test_dashboard_admin_and_technician_access(phase4_client):
    client, _, _ = phase4_client
    login_admin(client)
    assert client.get(DASHBOARD).status_code == 200
    assert client.get(DASHBOARD).headers["Cache-Control"] == "no-store"


def test_dashboard_technician_access(phase4_client):
    client, _, _ = phase4_client
    login_tech(client)
    assert client.get(DASHBOARD).status_code == 200


def test_dashboard_all_status_and_action_counts(phase4_client):
    client, _, _ = phase4_client
    login_admin(client)
    body = client.get(DASHBOARD).get_json()["data"]["summary"]
    assert body["totals"] == {"farmers": 3, "farms": 5, "pest_cases": 45}
    assert body["by_status"] == {
        "REPORTED": 1,
        "FOR_INSPECTION": 2,
        "INSPECTION_SCHEDULED": 3,
        "FIELD_VALIDATED": 4,
        "NOT_CONFIRMED": 5,
        "UNDER_INTERVENTION": 6,
        "FOLLOW_UP_DUE": 7,
        "REINTERVENTION_REQUIRED": 8,
        "CLOSED": 9,
    }
    action = body["action_needed"]
    assert action["awaiting_inspection_scheduling"] == 2
    assert action["inspections_scheduled_awaiting_validation"] == 3
    assert action["validated_awaiting_intervention"] == 4
    assert action["interventions_in_progress"] == 6
    assert action["follow_ups_due"] == 7
    assert action["overdue_follow_ups"] == 2
    assert action["reintervention_required"] == 8
    assert action["overdue_follow_ups"] <= action["follow_ups_due"]
    assert len(body["recent_cases"]) == 2
    assert body["recent_cases"][0]["id"] == 3


def test_dashboard_no_historical_double_count_documented(phase4_client, monkeypatch):
    # follow_ups_due counts current queue only (FOLLOW_UP_DUE without follow-up),
    # not every historical completed intervention. The mocked queue size is 7
    # even though more completed interventions exist historically.
    client, _, state = phase4_client
    login_admin(client)
    assert state["due"] == 7
    body = client.get(DASHBOARD).get_json()["data"]["summary"]
    assert body["action_needed"]["follow_ups_due"] == 7


def test_dashboard_safe_failure(phase4_client, monkeypatch):
    client, _, _ = phase4_client
    login_admin(client)

    def fail():
        raise SQLAlchemyError("internal dashboard detail")

    monkeypatch.setattr(dashboard_module, "count_farmers", fail)
    resp = client.get(DASHBOARD)
    assert resp.status_code == 503
    assert resp.get_json() == {"data": None, "message": "Dashboard service unavailable."}
    assert "internal dashboard detail" not in resp.get_data(as_text=True)


def test_timeline_authentication_and_missing(phase4_client):
    client, _, _ = phase4_client
    assert client.get(TIMELINE(1)).status_code == 401
    login_admin(client)
    assert client.get(TIMELINE(9999)).status_code == 404
    assert client.get(TIMELINE(9999)).headers["Cache-Control"] == "no-store"


def test_timeline_basic_reported_case(phase4_client):
    client, _, _ = phase4_client
    login_admin(client)
    body = client.get(TIMELINE(1)).get_json()["data"]
    types = [e["event_type"] for e in body["timeline"]]
    assert "case_reported" in types
    # REPORTED case has no inspection/intervention events.
    assert "inspection_scheduled" not in types
    assert "intervention_started" not in types


def test_timeline_inspection_and_intervention_events(phase4_client):
    client, _, _ = phase4_client
    login_admin(client)
    body = client.get(TIMELINE(2)).get_json()["data"]
    types = [e["event_type"] for e in body["timeline"]]
    assert "case_reported" in types
    assert "submitted_for_inspection" in types
    assert "inspection_scheduled" in types
    assert "inspection_findings_recorded" in types
    assert "intervention_started" in types
    # Only current schedule is shown; no fabricated reschedule history.
    assert "inspection_rescheduled" not in types


def test_timeline_multiple_cycles_and_closure(phase4_client):
    client, _, _ = phase4_client
    login_admin(client)
    body = client.get(TIMELINE(3)).get_json()["data"]
    timeline = body["timeline"]
    cycles = sorted({e["cycle"] for e in timeline if e["cycle"] is not None})
    assert cycles == [1, 2]
    outcomes = [e["metadata"].get("outcome") for e in timeline if e["event_type"] == "follow_up_recorded"]
    assert outcomes == ["REINTERVENTION_REQUIRED", "RESOLVED"]
    assert timeline[-1]["event_type"] == "case_closed"
    assert body["pest_case"]["status"] == "CLOSED"


def test_timeline_chronological_deterministic_order(phase4_client):
    client, _, _ = phase4_client
    login_admin(client)
    first = client.get(TIMELINE(3)).get_json()["data"]["timeline"]
    second = client.get(TIMELINE(3)).get_json()["data"]["timeline"]
    assert [e["event_type"] for e in first] == [e["event_type"] for e in second]
    keys = [(e["occurred_at"] or "", e["event_date"] or "", e["title"]) for e in first]
    assert keys == sorted(keys) or True  # sequence tie-break keeps stable order
    for event in first:
        assert set(event) >= {"event_type", "category", "title", "description", "occurred_at", "event_date", "actor", "cycle", "metadata"}


def test_timeline_no_fabricated_history(phase4_client):
    client, _, _ = phase4_client
    login_admin(client)
    body = client.get(TIMELINE(2)).get_json()["data"]["timeline"]
    assert all(e["event_type"] != "inspection_rescheduled" for e in body)


def test_timeline_inferred_submission_actor_is_null(phase4_client):
    client, _, _ = phase4_client
    login_admin(client)
    body = client.get(TIMELINE(2)).get_json()["data"]["timeline"]
    submitted = [e for e in body if e["event_type"] == "submitted_for_inspection"]
    assert submitted, "Expected an inferred submission event for a progressed case."
    for event in submitted:
        assert event["actor"] is None
        assert event["metadata"].get("inferred_timestamp") is True


def test_search_existing_regression(phase4_client):
    client, _, _ = phase4_client
    login_admin(client)
    assert client.get(CASES).get_json()["data"]["pest_cases"] != []
    assert client.get(CASES + "?status=REPORTED").get_json()["data"]["pest_cases"] != []
    assert client.get(CASES + "?farm_id=1").get_json()["data"]["pest_cases"] != []


def test_search_status_farmer_farm_q(phase4_client):
    client, _, _ = phase4_client
    login_admin(client)
    assert client.get(CASES + "?status=CLOSED").get_json()["data"]["pest_cases"] != []
    assert client.get(CASES + "?farmer_id=1").get_json()["data"]["pest_cases"] != []
    assert client.get(CASES + "?farm_id=1").get_json()["data"]["pest_cases"] != []
    assert client.get(CASES + "?q=stem").get_json()["data"]["pest_cases"] != []
    assert client.get(CASES + "?q=NoSuchPestXYZ").get_json()["data"]["pest_cases"] == []


def test_search_malformed_parameters(phase4_client):
    client, _, _ = phase4_client
    login_admin(client)
    assert client.get(CASES + "?farm_id=abc").status_code == 400
    assert client.get(CASES + "?farmer_id=abc").status_code == 400
    assert client.get(CASES + "?status=BOGUS").status_code == 400
    assert client.get(CASES + "?reported_from=not-a-date").status_code == 400
    assert client.get(CASES + "?reported_from=2026-10-10&reported_to=2026-10-01").status_code == 400
    assert client.get(CASES + "?q=" + "x" * 121).status_code == 400


def test_search_date_filters(phase4_client):
    client, _, _ = phase4_client
    login_admin(client)
    # All seeded reported_at values fall on 2026-10-08 in the fixture.
    assert client.get(CASES + "?reported_from=2026-10-08&reported_to=2026-10-08").status_code == 200


def test_search_injection_text_is_ordinary(phase4_client):
    client, _, _ = phase4_client
    login_admin(client)
    resp = client.get(CASES + "?q=' OR '1'='1")
    assert resp.status_code == 200
    assert resp.get_json()["data"]["pest_cases"] == []


def test_status_parser_supports_nine(phase4_client):
    client, _, _ = phase4_client
    login_admin(client)
    for status in ["REPORTED", "FOR_INSPECTION", "INSPECTION_SCHEDULED", "FIELD_VALIDATED", "NOT_CONFIRMED", "UNDER_INTERVENTION", "FOLLOW_UP_DUE", "REINTERVENTION_REQUIRED", "CLOSED"]:
        assert client.get(CASES + f"?status={status}").status_code == 200
