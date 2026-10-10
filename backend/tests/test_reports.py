from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app import auth, create_app
from app.models import Farm, Farmer, PestCase, PestCaseStatus, User
from app.routes import farmers as farmers_module
from app.routes import farms as farms_module
from app.routes import pest_cases as pest_cases_module
from app.routes import reports as reports_module

REPORTS = "/api/v1/reports/operational"
LOGIN = "/api/v1/auth/login"
ORIGIN = "http://localhost:3000"
ADMIN_PASSWORD = "admin-password-123"
TECH_PASSWORD = "technician-pass-123"


def _stamp():
    return datetime(2026, 10, 9, tzinfo=timezone.utc)


@pytest.fixture
def reports_client(monkeypatch):
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

    def make_case(case_id, status):
        case = PestCase(
            farm_id=1,
            pest_name="Stem Borer",
            symptoms="Bored stalks",
            observed_on="2026-09-15",
            reported_area_hectares="2.50",
            status=status,
            reported_by_user_id=2,
        )
        case.id = case_id
        case.reported_at = _stamp()
        case.updated_at = _stamp()
        case.farm = farm
        case.reporter = tech
        return case

    cases = [
        make_case(1, PestCaseStatus.REPORTED.value),
        make_case(2, PestCaseStatus.CLOSED.value),
        make_case(3, PestCaseStatus.NOT_CONFIRMED.value),
        make_case(4, PestCaseStatus.UNDER_INTERVENTION.value),
        make_case(5, PestCaseStatus.FOLLOW_UP_DUE.value),
        make_case(6, PestCaseStatus.REINTERVENTION_REQUIRED.value),
    ]

    class FakeIntervention:
        def __init__(self, iid, case_id, completed, due=None):
            self.id = iid
            self.pest_case_id = case_id
            self.completed_at = _stamp() if completed else None
            self.follow_up_due_on = due

    class FakeFollowUp:
        def __init__(self, iid, outcome):
            self.intervention_id = iid
            self.outcome = outcome

    from datetime import date

    interventions = [
        FakeIntervention(20, 4, False, None),
        FakeIntervention(21, 5, True, date(2026, 10, 20)),
        FakeIntervention(22, 5, True, date(2026, 10, 1)),
        FakeIntervention(23, 6, True, date(2026, 10, 20)),
        FakeIntervention(24, 2, True, date(2026, 10, 20)),
    ]
    follow_ups = [
        FakeFollowUp(23, "REINTERVENTION_REQUIRED"),
        FakeFollowUp(24, "RESOLVED"),
    ]

    def by_id(uid):
        return users.get(uid)

    def by_username(name):
        return next((u for u in users.values() if u.username == name), None)

    captured = {}

    def fake_filtered(status=None, farmer_id=None, farm_id=None, reported_from=None, reported_to=None):
        captured["filters"] = {
            "status": status,
            "farmer_id": farmer_id,
            "farm_id": farm_id,
            "reported_from": reported_from,
            "reported_to": reported_to,
        }
        items = list(cases)
        if status is not None:
            items = [c for c in items if c.status == status]
        if farm_id is not None:
            items = [c for c in items if c.farm_id == farm_id]
        return items

    monkeypatch.setattr(auth, "get_user_by_id", by_id)
    monkeypatch.setattr(auth, "get_user_by_username", by_username)
    monkeypatch.setattr(auth, "save_last_login", lambda item, ts: setattr(item, "last_login_at", ts))
    monkeypatch.setattr(auth, "now_epoch_seconds", lambda: clock["now"])
    monkeypatch.setattr(reports_module, "get_filtered_cases", fake_filtered)
    monkeypatch.setattr(reports_module, "get_interventions_for_cases", lambda ids: [i for i in interventions if i.pest_case_id in ids])
    monkeypatch.setattr(
        reports_module,
        "get_follow_ups_for_interventions",
        lambda ids: [f for f in follow_ups if f.intervention_id in ids],
    )
    monkeypatch.setattr(farmers_module, "list_all_farmers", lambda: [])
    monkeypatch.setattr(farms_module, "list_all_farms", lambda farmer_id=None: [])
    monkeypatch.setattr(pest_cases_module, "list_all_pest_cases", lambda *a, **k: [])

    return app.test_client(), captured


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


def test_reports_unauthenticated(reports_client):
    client, _ = reports_client
    assert client.get(REPORTS).status_code == 401


def test_reports_admin_and_technician(reports_client):
    client, _ = reports_client
    login_admin(client)
    assert client.get(REPORTS).status_code == 200
    assert client.get(REPORTS).headers["Cache-Control"] == "no-store"
    client2_token = login_tech(client)
    assert client2_token
    assert client.get(REPORTS).status_code == 200


def test_reports_totals_and_nine_statuses(reports_client):
    client, _ = reports_client
    login_admin(client)
    body = client.get(REPORTS).get_json()["data"]["report"]
    assert body["summary"]["total_cases"] == 6
    assert set(body["by_status"]) == {
        "REPORTED", "FOR_INSPECTION", "INSPECTION_SCHEDULED", "FIELD_VALIDATED",
        "NOT_CONFIRMED", "UNDER_INTERVENTION", "FOLLOW_UP_DUE",
        "REINTERVENTION_REQUIRED", "CLOSED",
    }
    assert sum(body["by_status"].values()) == 6


def test_reports_open_closed_not_confirmed(reports_client):
    client, _ = reports_client
    login_admin(client)
    summary = client.get(REPORTS).get_json()["data"]["report"]["summary"]
    assert summary["closed_cases"] == 1
    assert summary["not_confirmed_cases"] == 1
    assert summary["open_cases"] == 4
    assert summary["under_intervention"] == 1


def test_reports_follow_up_semantics(reports_client):
    client, _ = reports_client
    login_admin(client)
    follow = client.get(REPORTS).get_json()["data"]["report"]["follow_up_summary"]
    assert follow["completed"] == 2
    assert follow["resolved"] == 1
    assert follow["reintervention_required"] == 1
    assert follow["overdue"] <= follow["pending"]


def test_reports_intervention_repeat(reports_client):
    client, _ = reports_client
    login_admin(client)
    inter = client.get(REPORTS).get_json()["data"]["report"]["intervention_summary"]
    assert inter["total_records"] == 5
    assert inter["completed"] == 4
    assert inter["pending"] == 1
    assert inter["cases_with_repeat_intervention"] == 1


def test_reports_case_rows_shape(reports_client):
    client, _ = reports_client
    login_admin(client)
    cases = client.get(REPORTS).get_json()["data"]["report"]["cases"]
    assert len(cases) == 6
    row = next(c for c in cases if c["case_id"] == 1)
    assert set(row) == {
        "case_id", "farmer", "farm", "barangay", "pest_name", "current_status",
        "reported_at", "reported_area_hectares", "latest_intervention_cycle",
        "latest_follow_up_outcome",
    }
    assert row["farmer"] == "Juan Dela Cruz"
    assert "effectiveness" not in str(cases).lower()
    assert "efficacy" not in str(cases).lower()


def test_reports_filters_forwarded(reports_client):
    client, captured = reports_client
    login_admin(client)
    assert client.get(REPORTS + "?status=CLOSED").status_code == 200
    assert captured["filters"]["status"] == "CLOSED"
    assert client.get(REPORTS + "?farmer_id=1&farm_id=1").status_code == 200
    assert captured["filters"]["farmer_id"] == 1
    assert captured["filters"]["farm_id"] == 1
    assert client.get(REPORTS + "?reported_from=2026-10-01&reported_to=2026-10-09").status_code == 200


def test_reports_malformed_filters(reports_client):
    client, _ = reports_client
    login_admin(client)
    assert client.get(REPORTS + "?status=BOGUS").status_code == 400
    assert client.get(REPORTS + "?farm_id=abc").status_code == 400
    assert client.get(REPORTS + "?farmer_id=abc").status_code == 400
    assert client.get(REPORTS + "?reported_from=not-a-date").status_code == 400
    assert client.get(REPORTS + "?reported_from=2026-10-10&reported_to=2026-10-01").status_code == 400


def test_reports_sanitized_failure(reports_client, monkeypatch):
    client, _ = reports_client
    login_admin(client)

    def fail(*a, **k):
        raise SQLAlchemyError("internal report detail")

    monkeypatch.setattr(reports_module, "get_filtered_cases", fail)
    resp = client.get(REPORTS)
    assert resp.status_code == 503
    assert resp.get_json() == {"data": None, "message": "Report service unavailable."}
    assert "internal report detail" not in resp.get_data(as_text=True)
