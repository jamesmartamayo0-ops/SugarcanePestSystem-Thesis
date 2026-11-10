from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app import auth, create_app
from app.models import Farm, Farmer, Inspection, PestCase, PestCaseStatus, User
from app.models.inspection import (
    manila_today,
    normalize_findings,
    normalize_inspected_on,
    normalize_scheduled_for,
    normalize_validated_area,
)
import app.models.inspection as inspection_model
from app.routes import inspections as inspections_module
from app.routes import pest_cases as pest_cases_module
from app.routes import farmers as farmers_module
from app.routes import farms as farms_module

INSPECTIONS = "/api/v1/inspections"
INSPECTION = lambda i: f"/api/v1/inspections/{i}"  # noqa: E731
RESCHEDULE = lambda i: f"/api/v1/inspections/{i}/schedule"  # noqa: E731
FINDINGS = lambda i: f"/api/v1/inspections/{i}/record-findings"  # noqa: E731
SCHEDULE = lambda c: f"/api/v1/pest-cases/{c}/schedule-inspection"  # noqa: E731
LOGIN = "/api/v1/auth/login"
ORIGIN = "http://localhost:3000"
ADMIN_PASSWORD = "admin-password-123"
TECH_PASSWORD = "technician-pass-123"
TECH2_PASSWORD = "technician-two-pass-123"


def _stamp():
    return datetime(2026, 10, 10, tzinfo=timezone.utc)


@pytest.fixture
def inspection_client(monkeypatch):
    monkeypatch.setenv(
        "AUTH_TRUSTED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    )
    app = create_app()
    app.testing = True
    monkeypatch.setattr(inspection_model, "manila_today", lambda: date(2026, 10, 10))

    admin = User(id=1, username="admin.one", full_name="Admin One", role="ADMIN", is_active=True, auth_version=0)
    admin.set_password(ADMIN_PASSWORD)
    tech1 = User(id=2, username="tech.one", full_name="Tech One", role="TECHNICIAN", is_active=True, auth_version=0)
    tech1.set_password(TECH_PASSWORD)
    tech2 = User(id=3, username="tech.two", full_name="Tech Two", role="TECHNICIAN", is_active=True, auth_version=0)
    tech2.set_password(TECH2_PASSWORD)
    inactive = User(id=4, username="tech.off", full_name="Tech Off", role="TECHNICIAN", is_active=False, auth_version=0)
    inactive.set_password(TECH_PASSWORD)
    users = {u.id: u for u in (admin, tech1, tech2, inactive)}
    clock = {"now": 1_750_000_000}
    locks = {"cases": []}

    farmer = Farmer(full_name="Juan Dela Cruz", barangay="Bunao")
    farmer.id = 1
    farmer.created_at = _stamp()
    farmer.updated_at = _stamp()
    farm = Farm(farmer_id=1, plot_identifier="Plot A", barangay="Bunao", area_hectares="4.00")
    farm.id = 1
    farm.created_at = _stamp()
    farm.updated_at = _stamp()
    farm.farmer = farmer
    farm_store = {farm.id: farm}

    def make_case(case_id, status, farm_id=1, reporter=2):
        case = PestCase(
            farm_id=farm_id,
            pest_name="Stem Borer",
            symptoms="Bored stalks",
            observed_on="2026-09-15",
            reported_area_hectares="2.50",
            status=status,
            reported_by_user_id=reporter,
        )
        case.id = case_id
        case.reported_at = _stamp()
        case.updated_at = _stamp()
        case.farm = farm_store[case.farm_id]
        case.reporter = users[case.reported_by_user_id]
        return case

    case_store = {
        1: make_case(1, PestCaseStatus.FOR_INSPECTION.value),
        2: make_case(2, PestCaseStatus.REPORTED.value),
        3: make_case(3, PestCaseStatus.INSPECTION_SCHEDULED.value),
        4: make_case(4, PestCaseStatus.FIELD_VALIDATED.value),
        5: make_case(5, PestCaseStatus.FOR_INSPECTION.value),
    }

    def make_inspection(insp_id, case_id, assigned=2, scheduler=1, completed=False):
        insp = Inspection(
            pest_case_id=case_id,
            scheduled_for=date(2026, 10, 12),
            assigned_to_user_id=assigned,
            scheduled_by_user_id=scheduler,
        )
        insp.id = insp_id
        insp.created_at = _stamp()
        insp.updated_at = _stamp()
        insp.pest_case = case_store[case_id]
        insp.assignee = users[assigned]
        insp.scheduler = users[scheduler]
        insp.completer = None
        if completed:
            insp.inspected_on = date(2026, 10, 7)
            insp.findings = "Severe boring observed"
            insp.pest_confirmed = True
            insp.validated_area_hectares = Decimal("1.00")
            insp.completed_by_user_id = 2
            insp.completer = users[2]
            insp.completed_at = _stamp()
        else:
            insp.inspected_on = None
            insp.findings = None
            insp.pest_confirmed = None
            insp.validated_area_hectares = None
            insp.completed_by_user_id = None
            insp.completed_at = None
        return insp

    inspection_store = {
        10: make_inspection(10, 3, assigned=2),
        11: make_inspection(11, 4, assigned=2, completed=True),
    }
    state = {"next_inspection_id": 20}

    def by_id(uid):
        return users.get(uid)

    def by_username(name):
        return next((u for u in users.values() if u.username == name), None)

    def fake_list(pest_case_id=None, assigned_to=None):
        items = sorted(inspection_store.values(), key=lambda x: x.id)
        if pest_case_id is not None:
            items = [x for x in items if x.pest_case_id == pest_case_id]
        if assigned_to is not None:
            items = [x for x in items if x.assigned_to_user_id == assigned_to]
        return items

    def fake_get(iid):
        return inspection_store.get(iid)

    def fake_get_for_update(iid):
        return inspection_store.get(iid)

    def fake_case_for_update(cid):
        return case_store.get(cid)

    def fake_case_by_id(cid):
        return case_store.get(cid)

    def fake_lock(cid):
        locks["cases"].append(cid)

    def fake_user(uid):
        return users.get(uid)

    def fake_farm(fid):
        return farm_store.get(fid)

    def fake_techs():
        return [u for u in sorted(users.values(), key=lambda x: x.id) if u.role == "TECHNICIAN" and u.is_active]

    # pest_cases schedule helpers share the same stores.
    def fake_pest_case_for_update(cid):
        return case_store.get(cid)

    def fake_inspection_by_case(cid):
        for item in inspection_store.values():
            if item.pest_case_id == cid:
                return item
        return None

    monkeypatch.setattr(auth, "get_user_by_id", by_id)
    monkeypatch.setattr(auth, "get_user_by_username", by_username)
    monkeypatch.setattr(auth, "save_last_login", lambda item, ts: setattr(item, "last_login_at", ts))
    monkeypatch.setattr(auth, "now_epoch_seconds", lambda: clock["now"])
    # inspections module fakes
    monkeypatch.setattr(inspections_module, "list_all_inspections", fake_list)
    monkeypatch.setattr(inspections_module, "get_inspection_by_id", fake_get)
    monkeypatch.setattr(inspections_module, "get_inspection_for_update", fake_get_for_update)
    monkeypatch.setattr(inspections_module, "get_case_for_update", fake_case_for_update)
    monkeypatch.setattr(inspections_module, "acquire_inspection_case_lock", fake_lock)
    monkeypatch.setattr(inspections_module, "get_user_by_id", fake_user)
    monkeypatch.setattr(inspections_module, "get_farm_by_id", fake_farm)
    monkeypatch.setattr(inspections_module, "list_active_technicians", fake_techs)
    monkeypatch.setattr(inspections_module, "commit_inspection_changes", lambda: None)
    # pest_cases module fakes (schedule endpoint + neighbor regression)
    monkeypatch.setattr(pest_cases_module, "get_pest_case_by_id", fake_case_by_id)
    monkeypatch.setattr(pest_cases_module, "get_pest_case_for_update", fake_pest_case_for_update)
    monkeypatch.setattr(pest_cases_module, "get_inspection_by_case_id", fake_inspection_by_case)
    monkeypatch.setattr(pest_cases_module, "acquire_pest_case_transition_lock", fake_lock)
    monkeypatch.setattr(pest_cases_module, "commit_pest_case_changes", lambda: None)
    monkeypatch.setattr(pest_cases_module, "get_farm_by_id", fake_farm)
    monkeypatch.setattr(pest_cases_module, "get_user_by_id", fake_user)
    monkeypatch.setattr(farmers_module, "list_all_farmers", lambda: [])
    monkeypatch.setattr(farms_module, "list_all_farms", lambda farmer_id=None: [])

    # Simulate persistence for schedule endpoint: after route creates Inspection
    # via constructor + db.session.add, our fake stores must capture it. The route
    # uses db.session.add/flush/commit which are real SQLAlchemy calls that would
    # fail without DB. Instead patch db.session.add to capture into store.
    from app.extensions import db as _db

    orig_add = _db.session.add

    def fake_add(obj):
        if isinstance(obj, Inspection):
            if obj.id is None:
                obj.id = state["next_inspection_id"]
                state["next_inspection_id"] += 1
            # Wire relationships for serializer.
            if obj.pest_case_id in case_store:
                obj.pest_case = case_store[obj.pest_case_id]
            if obj.assigned_to_user_id in users:
                obj.assignee = users[obj.assigned_to_user_id]
            if getattr(obj, "scheduled_by_user_id", None) in users:
                obj.scheduler = users[obj.scheduled_by_user_id]
            if obj.created_at is None:
                obj.created_at = _stamp()
            if obj.updated_at is None:
                obj.updated_at = _stamp()
            inspection_store[obj.id] = obj
            return
        return orig_add(obj)

    monkeypatch.setattr(_db.session, "add", fake_add)
    monkeypatch.setattr(_db.session, "flush", lambda *a, **k: None)
    monkeypatch.setattr(_db.session, "commit", lambda *a, **k: None)
    monkeypatch.setattr(_db.session, "rollback", lambda *a, **k: None)

    return app.test_client(), case_store, inspection_store, farm_store, users, locks


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


def login_tech2(client):
    r = login(client, "tech.two", TECH2_PASSWORD)
    assert r.status_code == 200
    return r.get_json()["data"]["csrf_token"]


def test_unauthenticated_inspection_endpoints_return_401(inspection_client):
    client, _, _, _, _, _ = inspection_client
    assert client.get(INSPECTIONS).status_code == 401
    assert client.get(INSPECTION(10)).status_code == 401
    assert client.get(f"{INSPECTIONS}/technicians").status_code == 401
    assert client.post(SCHEDULE(1), json={}, headers={"Origin": ORIGIN}).status_code == 401
    assert client.put(RESCHEDULE(10), json={}, headers={"Origin": ORIGIN}).status_code == 401
    assert client.post(FINDINGS(10), json={}, headers={"Origin": ORIGIN}).status_code == 401


def test_unsafe_requests_require_origin_and_csrf(inspection_client):
    client, _, _, _, _, _ = inspection_client
    token = login_admin(client)
    assert client.get(INSPECTIONS).status_code == 200
    payload = {"scheduled_for": "2026-10-15", "assigned_to_user_id": 2}
    assert client.post(SCHEDULE(1), json=payload).status_code == 403
    assert client.post(SCHEDULE(1), json=payload, headers={"Origin": ORIGIN}).status_code == 403
    assert client.post(SCHEDULE(1), json=payload, headers={"Origin": ORIGIN, "X-CSRF-Token": "0" * 64}).status_code == 403
    assert client.put(RESCHEDULE(10), json={"scheduled_for": "2026-10-16"}).status_code == 403
    assert client.post(FINDINGS(10), json={}).status_code == 403
    ok = client.post(SCHEDULE(5), json=payload, headers={"Origin": ORIGIN, "X-CSRF-Token": token})
    assert ok.status_code == 201
    assert ok.headers["Cache-Control"] == "no-store"


def test_schedule_inspection_happy_path_and_lock(inspection_client):
    client, cases, inspections, _, _, locks = inspection_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    before = len(locks["cases"])
    resp = client.post(SCHEDULE(1), json={"scheduled_for": "2026-10-15", "assigned_to_user_id": 2}, headers=headers)
    assert resp.status_code == 201
    assert resp.headers["Cache-Control"] == "no-store"
    body = resp.get_json()["data"]["inspection"]
    assert body["pest_case_id"] == 1
    assert body["scheduled_for"] == "2026-10-15"
    assert body["assigned_to_user_id"] == 2
    assert body["scheduled_by_user_id"] == 1
    assert body["created_at"] is not None
    assert body["updated_at"] is not None
    assert cases[1].status == "INSPECTION_SCHEDULED"
    assert len(locks["cases"]) == before + 1
    assert locks["cases"][-1] == 1


def test_schedule_rejects_invalid_states_and_duplicates(inspection_client):
    client, _, _, _, _, _ = inspection_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    payload = {"scheduled_for": "2026-10-15", "assigned_to_user_id": 2}
    # REPORTED case cannot be scheduled.
    assert client.post(SCHEDULE(2), json=payload, headers=headers).status_code == 409
    # Already scheduled case (has pending inspection).
    assert client.post(SCHEDULE(3), json=payload, headers=headers).status_code == 409
    # Completed case.
    assert client.post(SCHEDULE(4), json=payload, headers=headers).status_code == 409
    # Duplicate scheduling on same eligible case.
    assert client.post(SCHEDULE(1), json=payload, headers=headers).status_code == 201
    dup = client.post(SCHEDULE(1), json=payload, headers=headers)
    assert dup.status_code == 409
    assert dup.get_json() == {
        "data": None,
        "message": "This case already has a scheduled inspection. Open the existing inspection to reschedule the date or change the assigned technician.",
    }
    assert client.post(SCHEDULE(9999), json=payload, headers=headers).status_code == 404


def test_schedule_validates_technician(inspection_client):
    client, _, _, _, _, _ = inspection_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    base = {"scheduled_for": "2026-10-15"}
    assert client.post(SCHEDULE(1), json={**base, "assigned_to_user_id": 9999}, headers=headers).status_code == 404
    # ADMIN user is not an eligible technician.
    r = client.post(SCHEDULE(1), json={**base, "assigned_to_user_id": 1}, headers=headers)
    assert r.status_code == 400
    # Inactive technician rejected.
    r = client.post(SCHEDULE(1), json={**base, "assigned_to_user_id": 4}, headers=headers)
    assert r.status_code == 400
    # Invalid payload shapes.
    assert client.post(SCHEDULE(1), json={"scheduled_for": "2026-10-15"}, headers=headers).status_code == 400
    assert client.post(SCHEDULE(1), json={"scheduled_for": "not-a-date", "assigned_to_user_id": 2}, headers=headers).status_code == 400
    assert client.post(SCHEDULE(1), json={"scheduled_for": "2026-10-15", "assigned_to_user_id": 2, "status": "INSPECTION_SCHEDULED"}, headers=headers).status_code == 400


def test_schedule_accepts_today_and_future_but_rejects_past(inspection_client, monkeypatch):
    client, _, _, _, _, _ = inspection_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    monkeypatch.setattr(inspection_model, "manila_today", lambda: date(2026, 10, 10))

    past = client.post(
        SCHEDULE(1),
        json={"scheduled_for": "2026-10-09", "assigned_to_user_id": 2},
        headers=headers,
    )
    assert past.status_code == 400
    assert past.get_json()["message"] == "Scheduled inspection date cannot be in the past."

    today = client.post(
        SCHEDULE(1),
        json={"scheduled_for": "2026-10-10", "assigned_to_user_id": 2},
        headers=headers,
    )
    assert today.status_code == 201

    future = client.post(
        SCHEDULE(5),
        json={"scheduled_for": "2026-10-11", "assigned_to_user_id": 2},
        headers=headers,
    )
    assert future.status_code == 201


def test_list_and_detail_filters(inspection_client):
    client, _, _, _, _, _ = inspection_client
    login_admin(client)
    body = client.get(INSPECTIONS).get_json()
    assert set(body) == {"data", "message"}
    assert len(body["data"]["inspections"]) == 2
    entry = body["data"]["inspections"][0]
    assert entry["pest_case"]["farm"]["farmer"]["full_name"] == "Juan Dela Cruz"
    assert client.get(f"{INSPECTIONS}?pest_case_id=3").get_json()["data"]["inspections"] != []
    assert client.get(f"{INSPECTIONS}?pest_case_id=9999").get_json()["data"]["inspections"] == []
    assert client.get(f"{INSPECTIONS}?assigned_to_user_id=2").get_json()["data"]["inspections"] != []
    assert client.get(f"{INSPECTIONS}?assigned_to_user_id=3").get_json()["data"]["inspections"] == []
    assert client.get(f"{INSPECTIONS}?pest_case_id=abc").status_code == 400
    assert client.get(INSPECTION(10)).status_code == 200
    assert client.get(INSPECTION(9999)).status_code == 404
    techs = client.get(f"{INSPECTIONS}/technicians").get_json()["data"]["technicians"]
    assert {t["id"] for t in techs} == {2, 3}


def test_reschedule_only_while_pending(inspection_client):
    client, cases, inspections, _, _, _ = inspection_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    count_before = len(inspections)
    resp = client.put(RESCHEDULE(10), json={"scheduled_for": "2026-10-20", "assigned_to_user_id": 3}, headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["inspection"]["scheduled_for"] == "2026-10-20"
    assert resp.get_json()["data"]["inspection"]["assigned_to_user_id"] == 3
    assert len(inspections) == count_before
    assert cases[3].status == "INSPECTION_SCHEDULED"
    # Completed inspection cannot be rescheduled.
    assert client.put(RESCHEDULE(11), json={"scheduled_for": "2026-10-20"}, headers=headers).status_code == 409
    assert client.put(RESCHEDULE(9999), json={"scheduled_for": "2026-10-20"}, headers=headers).status_code == 404
    assert client.put(RESCHEDULE(10), json={}, headers=headers).status_code == 400
    assert client.put(RESCHEDULE(10), json={"status": "FIELD_VALIDATED"}, headers=headers).status_code == 400


def test_only_administrator_can_reschedule_or_reassign(inspection_client):
    client, cases, inspections, _, _, _ = inspection_client
    token = login_tech(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    response = client.put(
        RESCHEDULE(10),
        json={"scheduled_for": "2026-10-20", "assigned_to_user_id": 3},
        headers=headers,
    )
    assert response.status_code == 403
    assert inspections[10].scheduled_for == date(2026, 10, 12)
    assert inspections[10].assigned_to_user_id == 2
    assert cases[3].status == "INSPECTION_SCHEDULED"


def test_only_administrator_can_create_an_inspection_schedule(inspection_client):
    client, cases, inspections, _, _, _ = inspection_client
    token = login_tech(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    response = client.post(
        SCHEDULE(1),
        json={"scheduled_for": "2026-10-20", "assigned_to_user_id": 2},
        headers=headers,
    )
    assert response.status_code == 403
    assert cases[1].status == "FOR_INSPECTION"
    assert all(item.pest_case_id != 1 for item in inspections.values())


def test_pending_reschedule_rejects_past_date(inspection_client, monkeypatch):
    client, _, _, _, _, _ = inspection_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    monkeypatch.setattr(inspection_model, "manila_today", lambda: date(2026, 10, 10))
    response = client.put(
        RESCHEDULE(10),
        json={"scheduled_for": "2026-10-09"},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.get_json()["message"] == "Scheduled inspection date cannot be in the past."


def test_record_findings_confirmed_and_not_confirmed(inspection_client):
    client, cases, inspections, _, _, _ = inspection_client
    token = login_tech(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    # Confirmed path on pending inspection 10.
    resp = client.post(
        FINDINGS(10),
        json={
            "findings": "Bored stalks with frass",
            "pest_confirmed": True,
            "validated_area_hectares": "1.25",
            "inspected_on": "2026-10-07",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.get_json()["data"]["inspection"]
    assert body["pest_confirmed"] is True
    assert body["validated_area_hectares"] == 1.25
    assert body["pest_case"]["status"] == "FIELD_VALIDATED"
    assert cases[3].status == "FIELD_VALIDATED"
    assert cases[3].reported_area_hectares == Decimal("2.50")
    assert inspections[10].completed_by_user_id == 2


def test_record_findings_not_confirmed_requires_zero(inspection_client):
    client, cases, _, _, _, _ = inspection_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    resp = client.post(
        FINDINGS(10),
        json={
            "findings": "No damage seen",
            "pest_confirmed": False,
            "validated_area_hectares": 0,
            "inspected_on": "2026-10-07",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["inspection"]["pest_case"]["status"] == "NOT_CONFIRMED"
    assert cases[3].status == "NOT_CONFIRMED"


def test_record_findings_validation_and_server_status(inspection_client):
    client, cases, _, _, _, _ = inspection_client
    token = login_tech(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    good = {
        "findings": "Bored stalks",
        "pest_confirmed": True,
        "validated_area_hectares": 1,
        "inspected_on": "2026-10-07",
    }
    # Blank findings.
    r = client.post(FINDINGS(10), json={**good, "findings": "   "}, headers=headers)
    assert r.status_code == 400
    # Client-supplied status rejected by allowlist.
    r = client.post(FINDINGS(10), json={**good, "status": "FIELD_VALIDATED"}, headers=headers)
    assert r.status_code == 400
    # Missing field.
    missing = dict(good)
    del missing["inspected_on"]
    assert client.post(FINDINGS(10), json=missing, headers=headers).status_code == 400
    # Future inspection date.
    future = (manila_today() + timedelta(days=1)).isoformat()
    r = client.post(FINDINGS(10), json={**good, "inspected_on": future}, headers=headers)
    assert r.status_code == 400
    # Confirmed with zero area.
    r = client.post(FINDINGS(10), json={**good, "validated_area_hectares": 0}, headers=headers)
    assert r.status_code == 400
    # Not confirmed with positive area.
    r = client.post(
        FINDINGS(10),
        json={**good, "pest_confirmed": False, "validated_area_hectares": 1},
        headers=headers,
    )
    assert r.status_code == 400
    # Precision beyond 2 decimals.
    r = client.post(FINDINGS(10), json={**good, "validated_area_hectares": "1.234"}, headers=headers)
    assert r.status_code == 400
    # Exceeds farm area (farm is 4.00 ha).
    r = client.post(FINDINGS(10), json={**good, "validated_area_hectares": "4.01"}, headers=headers)
    assert r.status_code == 400
    assert cases[3].status == "INSPECTION_SCHEDULED"


def test_repeated_findings_returns_409(inspection_client):
    client, _, _, _, _, _ = inspection_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    payload = {
        "findings": "Already recorded",
        "pest_confirmed": True,
        "validated_area_hectares": 1,
        "inspected_on": "2026-10-07",
    }
    assert client.post(FINDINGS(11), json=payload, headers=headers).status_code == 409
    repeated = client.post(FINDINGS(11), json=payload, headers=headers)
    assert repeated.status_code == 409
    assert repeated.get_json() == {"data": None, "message": "Inspection findings have already been recorded."}


def test_assigned_vs_unrelated_technician_permissions(inspection_client):
    client, _, _, _, _, _ = inspection_client
    token2 = login_tech2(client)
    headers2 = {"Origin": ORIGIN, "X-CSRF-Token": token2}
    payload = {
        "findings": "Trying as other tech",
        "pest_confirmed": True,
        "validated_area_hectares": 1,
        "inspected_on": "2026-10-07",
    }
    r = client.post(FINDINGS(10), json=payload, headers=headers2)
    assert r.status_code == 403
    # Assigned technician succeeds.
    token1 = login_tech(client)
    headers1 = {"Origin": ORIGIN, "X-CSRF-Token": token1}
    assert client.post(FINDINGS(10), json=payload, headers=headers1).status_code == 200


def test_transaction_rollback_on_invalid_findings(inspection_client):
    client, cases, inspections, _, _, _ = inspection_client
    token = login_tech(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    before_status = cases[3].status
    before_findings = inspections[10].findings
    r = client.post(
        FINDINGS(10),
        json={
            "findings": "x" * 2001,
            "pest_confirmed": True,
            "validated_area_hectares": 1,
            "inspected_on": "2026-10-07",
        },
        headers=headers,
    )
    assert r.status_code == 400
    assert cases[3].status == before_status
    assert inspections[10].findings == before_findings


def test_no_delete_endpoints_registered(inspection_client):
    client, _, _, _, _, _ = inspection_client
    rules = [rule for rule in client.application.url_map.iter_rules() if rule.rule.startswith("/api/v1/inspections")]
    assert rules, "Expected inspection routes to be registered."
    assert all("DELETE" not in rule.methods for rule in rules)
    pest_rules = [rule for rule in client.application.url_map.iter_rules() if rule.rule.startswith("/api/v1/pest-cases")]
    assert all("DELETE" not in rule.methods for rule in pest_rules)


def test_neighboring_endpoints_regressed(inspection_client):
    client, _, _, _, _, _ = inspection_client
    login_admin(client)
    assert client.get("/api/v1/farmers").status_code == 200
    assert client.get("/api/v1/farms").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200


def test_database_errors_sanitized(inspection_client, monkeypatch):
    client, _, _, _, _, _ = inspection_client
    login_admin(client)

    def fail_list(*_a, **_k):
        raise SQLAlchemyError("internal inspection detail")

    monkeypatch.setattr(inspections_module, "list_all_inspections", fail_list)
    resp = client.get(INSPECTIONS)
    assert resp.status_code == 503
    assert resp.get_json() == {"data": None, "message": "Inspection service unavailable."}
    assert "internal inspection detail" not in resp.get_data(as_text=True)


def test_model_normalization_helpers():
    assert normalize_scheduled_for("2026-10-12") == date(2026, 10, 12)
    with pytest.raises(ValueError):
        normalize_scheduled_for("12/10/2026")
    assert normalize_findings("  Bored stalks  ") == "Bored stalks"
    with pytest.raises(ValueError):
        normalize_findings("   ")
    assert normalize_validated_area(0) == Decimal("0.00")
    assert normalize_validated_area("1.25") == Decimal("1.25")
    with pytest.raises(ValueError):
        normalize_validated_area("1.234")
    with pytest.raises(ValueError):
        normalize_validated_area(-1)
    assert normalize_inspected_on(manila_today().isoformat()) == manila_today()
    with pytest.raises(ValueError):
        normalize_inspected_on((manila_today() + timedelta(days=1)).isoformat())


def test_model_relationship_and_constraints():
    assert Inspection.__table__.name == "inspections"
    names = {c.name for c in Inspection.__table__.constraints}
    assert {
        "uq_inspections_pest_case_id",
        "ck_inspections_validated_range",
        "ck_inspections_completion_state",
        "ck_inspections_findings_nonblank",
        "ck_inspections_confirmed_area",
    } <= names
    fks = {(e.column.table.name, e.ondelete) for e in Inspection.__table__.foreign_keys}
    assert ("pest_cases", "RESTRICT") in fks
    assert ("users", "RESTRICT") in fks
    insp = Inspection(pest_case_id=1, scheduled_for=date(2026, 10, 12), assigned_to_user_id=2, scheduled_by_user_id=1)
    assert insp.scheduled_for == date(2026, 10, 12)
    with pytest.raises(ValueError):
        insp.validated_area_hectares = "1.234"
