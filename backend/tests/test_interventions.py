from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app import auth, create_app
from app.models import Farm, Farmer, Intervention, PestCase, PestCaseStatus, User
from app.models.intervention import (
    manila_today,
    normalize_completion_notes,
    normalize_follow_up_due_on,
    normalize_method_category,
    normalize_method_description,
    normalize_performed_on,
)
from app.models.intervention import (
    normalize_scheduled_for as normalize_intervention_scheduled_for,
)
from app.routes import interventions as interventions_module
from app.routes import pest_cases as pest_cases_module
from app.routes import farmers as farmers_module
from app.routes import farms as farms_module

INTERVENTIONS = "/api/v1/interventions"
INTERVENTION = lambda i: f"/api/v1/interventions/{i}"  # noqa: E731
PLAN = lambda i: f"/api/v1/interventions/{i}/plan"  # noqa: E731
COMPLETE = lambda i: f"/api/v1/interventions/{i}/complete"  # noqa: E731
START = lambda c: f"/api/v1/pest-cases/{c}/start-intervention"  # noqa: E731
LOGIN = "/api/v1/auth/login"
ORIGIN = "http://localhost:3000"
ADMIN_PASSWORD = "admin-password-123"
TECH_PASSWORD = "technician-pass-123"
TECH2_PASSWORD = "technician-two-pass-123"


def _stamp():
    return datetime(2026, 10, 10, tzinfo=timezone.utc)


@pytest.fixture
def intervention_client(monkeypatch):
    monkeypatch.setenv(
        "AUTH_TRUSTED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    )
    app = create_app()
    app.testing = True

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
        1: make_case(1, PestCaseStatus.FIELD_VALIDATED.value),
        2: make_case(2, PestCaseStatus.NOT_CONFIRMED.value),
        3: make_case(3, PestCaseStatus.REPORTED.value),
        4: make_case(4, PestCaseStatus.FIELD_VALIDATED.value),
        5: make_case(5, PestCaseStatus.UNDER_INTERVENTION.value),
        6: make_case(6, PestCaseStatus.FOLLOW_UP_DUE.value),
        7: make_case(7, PestCaseStatus.INSPECTION_SCHEDULED.value),
    }

    def make_intervention(insp_id, case_id, assigned=2, creator=1, completed=False):
        insp = Intervention(
            pest_case_id=case_id,
            method_category="CULTURAL",
            method_description="Manual removal of affected shoots",
            scheduled_for=date(2026, 10, 12),
            assigned_to_user_id=assigned,
            created_by_user_id=creator,
            follow_up_due_on=date(2026, 10, 20),
        )
        insp.id = insp_id
        insp.created_at = _stamp()
        insp.updated_at = _stamp()
        insp.pest_case = case_store[case_id]
        insp.assignee = users[assigned]
        insp.creator = users[creator]
        if completed:
            insp.performed_on = date(2026, 10, 9)
            insp.completion_notes = "Cleared affected shoots"
            insp.follow_up_due_on = date(2026, 10, 20)
            insp.completed_by_user_id = 2
            insp.completer = users[2]
            insp.completed_at = _stamp()
        else:
            insp.performed_on = None
            insp.completion_notes = None
            insp.completed_by_user_id = None
            insp.completer = None
            insp.completed_at = None
        return insp

    intervention_store = {
        20: make_intervention(20, 5, assigned=2),
        21: make_intervention(21, 6, assigned=2, completed=True),
    }
    state = {"next_intervention_id": 30}

    def by_id(uid):
        return users.get(uid)

    def by_username(name):
        return next((u for u in users.values() if u.username == name), None)

    def fake_list(pest_case_id=None, assigned_to=None):
        items = sorted(intervention_store.values(), key=lambda x: x.id)
        if pest_case_id is not None:
            items = [x for x in items if x.pest_case_id == pest_case_id]
        if assigned_to is not None:
            items = [x for x in items if x.assigned_to_user_id == assigned_to]
        return items

    def fake_get(iid):
        return intervention_store.get(iid)

    def fake_get_for_update(iid):
        return intervention_store.get(iid)

    def fake_case_for_update(cid):
        return case_store.get(cid)

    def fake_case_by_id(cid):
        return case_store.get(cid)

    def fake_lock(cid):
        locks["cases"].append(cid)

    def fake_user(uid):
        return users.get(uid)

    def fake_pending_by_case(cid):
        for item in intervention_store.values():
            if item.pest_case_id == cid and item.completed_at is None:
                return item
        return None

    monkeypatch.setattr(auth, "get_user_by_id", by_id)
    monkeypatch.setattr(auth, "get_user_by_username", by_username)
    monkeypatch.setattr(auth, "save_last_login", lambda item, ts: setattr(item, "last_login_at", ts))
    monkeypatch.setattr(auth, "now_epoch_seconds", lambda: clock["now"])
    # interventions module fakes
    monkeypatch.setattr(interventions_module, "list_all_interventions", fake_list)
    monkeypatch.setattr(interventions_module, "get_intervention_by_id", fake_get)
    monkeypatch.setattr(interventions_module, "get_intervention_for_update", fake_get_for_update)
    monkeypatch.setattr(interventions_module, "get_case_for_update", fake_case_for_update)
    monkeypatch.setattr(interventions_module, "acquire_intervention_case_lock", fake_lock)
    monkeypatch.setattr(interventions_module, "get_user_by_id", fake_user)
    monkeypatch.setattr(interventions_module, "commit_intervention_changes", lambda: None)
    # pest_cases module fakes (start endpoint)
    monkeypatch.setattr(pest_cases_module, "get_pest_case_by_id", fake_case_by_id)
    monkeypatch.setattr(pest_cases_module, "get_pest_case_for_update", fake_case_for_update)
    monkeypatch.setattr(pest_cases_module, "get_pending_intervention_by_case_id", fake_pending_by_case)
    monkeypatch.setattr(pest_cases_module, "acquire_pest_case_transition_lock", fake_lock)
    monkeypatch.setattr(pest_cases_module, "commit_pest_case_changes", lambda: None)
    monkeypatch.setattr(pest_cases_module, "get_user_by_id", fake_user)
    monkeypatch.setattr(farmers_module, "list_all_farmers", lambda: [])
    monkeypatch.setattr(farms_module, "list_all_farms", lambda farmer_id=None: [])

    from app.extensions import db as _db

    orig_add = _db.session.add

    def fake_add(obj):
        if isinstance(obj, Intervention):
            if obj.id is None:
                obj.id = state["next_intervention_id"]
                state["next_intervention_id"] += 1
            if obj.pest_case_id in case_store:
                obj.pest_case = case_store[obj.pest_case_id]
            if obj.assigned_to_user_id in users:
                obj.assignee = users[obj.assigned_to_user_id]
            if getattr(obj, "created_by_user_id", None) in users:
                obj.creator = users[obj.created_by_user_id]
            if obj.created_at is None:
                obj.created_at = _stamp()
            if obj.updated_at is None:
                obj.updated_at = _stamp()
            intervention_store[obj.id] = obj
            return
        return orig_add(obj)

    monkeypatch.setattr(_db.session, "add", fake_add)
    monkeypatch.setattr(_db.session, "flush", lambda *a, **k: None)
    monkeypatch.setattr(_db.session, "commit", lambda *a, **k: None)
    monkeypatch.setattr(_db.session, "rollback", lambda *a, **k: None)

    return app.test_client(), case_store, intervention_store, farm_store, users, locks


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


def start_payload(**overrides):
    base = {
        "method_category": "CULTURAL",
        "method_description": "Manual removal of affected shoots",
        "scheduled_for": "2026-10-15",
        "assigned_to_user_id": 2,
    }
    base.update(overrides)
    return base


def test_unauthenticated_intervention_endpoints_return_401(intervention_client):
    client, _, _, _, _, _ = intervention_client
    assert client.get(INTERVENTIONS).status_code == 401
    assert client.get(INTERVENTION(20)).status_code == 401
    assert client.post(START(1), json={}, headers={"Origin": ORIGIN}).status_code == 401
    assert client.put(PLAN(20), json={}, headers={"Origin": ORIGIN}).status_code == 401
    assert client.post(COMPLETE(20), json={}, headers={"Origin": ORIGIN}).status_code == 401


def test_unsafe_requests_require_origin_and_csrf(intervention_client):
    client, _, _, _, _, _ = intervention_client
    token = login_admin(client)
    assert client.get(INTERVENTIONS).status_code == 200
    payload = start_payload()
    assert client.post(START(1), json=payload).status_code == 403
    assert client.post(START(1), json=payload, headers={"Origin": ORIGIN}).status_code == 403
    assert client.post(START(1), json=payload, headers={"Origin": ORIGIN, "X-CSRF-Token": "0" * 64}).status_code == 403
    assert client.put(PLAN(20), json={"scheduled_for": "2026-10-16"}).status_code == 403
    assert client.post(COMPLETE(20), json={}).status_code == 403
    ok = client.post(START(1), json=payload, headers={"Origin": ORIGIN, "X-CSRF-Token": token})
    assert ok.status_code == 201
    assert ok.headers["Cache-Control"] == "no-store"


def test_start_happy_path_and_atomic_transition(intervention_client):
    client, cases, interventions, _, _, locks = intervention_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    before = len(locks["cases"])
    resp = client.post(START(1), json=start_payload(), headers=headers)
    assert resp.status_code == 201
    assert resp.headers["Cache-Control"] == "no-store"
    body = resp.get_json()["data"]["intervention"]
    assert body["pest_case_id"] == 1
    assert body["method_category"] == "CULTURAL"
    assert body["assigned_to_user_id"] == 2
    assert body["created_by_user_id"] == 1
    assert body["pest_case"]["status"] == "UNDER_INTERVENTION"
    assert cases[1].status == "UNDER_INTERVENTION"
    assert len(locks["cases"]) == before + 1
    assert locks["cases"][-1] == 1


def test_start_requires_field_validated(intervention_client):
    client, _, _, _, _, _ = intervention_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    # NOT_CONFIRMED must never start.
    r = client.post(START(2), json=start_payload(), headers=headers)
    assert r.status_code == 409
    # REPORTED rejected.
    assert client.post(START(3), json=start_payload(), headers=headers).status_code == 409
    # UNDER_INTERVENTION with pending intervention rejected as duplicate.
    assert client.post(START(5), json=start_payload(), headers=headers).status_code == 409
    # FOLLOW_UP_DUE cannot restart in Phase 3D.
    assert client.post(START(6), json=start_payload(), headers=headers).status_code == 409
    # INSPECTION_SCHEDULED rejected.
    assert client.post(START(7), json=start_payload(), headers=headers).status_code == 409
    assert client.post(START(9999), json=start_payload(), headers=headers).status_code == 404


def test_duplicate_start_returns_409(intervention_client):
    client, _, _, _, _, _ = intervention_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    assert client.post(START(4), json=start_payload(), headers=headers).status_code == 201
    dup = client.post(START(4), json=start_payload(), headers=headers)
    assert dup.status_code == 409
    assert dup.get_json() == {"data": None, "message": "Intervention has already been started for this case."}


def test_start_validates_technician(intervention_client):
    client, _, _, _, _, _ = intervention_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    assert client.post(START(1), json=start_payload(assigned_to_user_id=9999), headers=headers).status_code == 404
    assert client.post(START(1), json=start_payload(assigned_to_user_id=1), headers=headers).status_code == 400
    assert client.post(START(1), json=start_payload(assigned_to_user_id=4), headers=headers).status_code == 400


def test_start_rejects_invalid_category_description_dates_fields(intervention_client):
    client, _, _, _, _, _ = intervention_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    assert client.post(START(1), json=start_payload(method_category="CHEMICAL_SPRAY"), headers=headers).status_code == 400
    assert client.post(START(1), json=start_payload(method_description="   "), headers=headers).status_code == 400
    assert client.post(START(1), json=start_payload(method_description="x" * 2001), headers=headers).status_code == 400
    assert client.post(START(1), json=start_payload(scheduled_for="not-a-date"), headers=headers).status_code == 400
    assert client.post(START(1), json=start_payload(follow_up_due_on="not-a-date"), headers=headers).status_code == 400
    # Client-controlled status/completion fields rejected.
    assert client.post(START(1), json={**start_payload(), "status": "UNDER_INTERVENTION"}, headers=headers).status_code == 400
    assert client.post(START(1), json={**start_payload(), "performed_on": "2026-10-09"}, headers=headers).status_code == 400
    assert client.post(START(1), json={**start_payload(), "completed_at": "2026-10-09"}, headers=headers).status_code == 400
    # Missing required field.
    missing = start_payload()
    del missing["scheduled_for"]
    assert client.post(START(1), json=missing, headers=headers).status_code == 400


def test_list_and_detail_filters(intervention_client):
    client, _, _, _, _, _ = intervention_client
    login_admin(client)
    body = client.get(INTERVENTIONS).get_json()
    assert set(body) == {"data", "message"}
    assert len(body["data"]["interventions"]) == 2
    entry = body["data"]["interventions"][0]
    assert entry["pest_case"]["farm"]["farmer"]["full_name"] == "Juan Dela Cruz"
    assert entry["method_category"] == "CULTURAL"
    assert client.get(f"{INTERVENTIONS}?pest_case_id=5").get_json()["data"]["interventions"] != []
    assert client.get(f"{INTERVENTIONS}?pest_case_id=9999").get_json()["data"]["interventions"] == []
    assert client.get(f"{INTERVENTIONS}?assigned_to_user_id=2").get_json()["data"]["interventions"] != []
    assert client.get(f"{INTERVENTIONS}?assigned_to_user_id=3").get_json()["data"]["interventions"] == []
    assert client.get(f"{INTERVENTIONS}?pest_case_id=abc").status_code == 400
    assert client.get(INTERVENTION(20)).status_code == 200
    assert client.get(INTERVENTION(9999)).status_code == 404


def test_plan_edit_while_pending(intervention_client):
    client, cases, interventions, _, _, _ = intervention_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    count_before = len(interventions)
    resp = client.put(
        PLAN(20),
        json={"scheduled_for": "2026-10-22", "assigned_to_user_id": 3, "method_description": "Updated plan"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.get_json()["data"]["intervention"]
    assert body["scheduled_for"] == "2026-10-22"
    assert body["assigned_to_user_id"] == 3
    assert body["method_description"] == "Updated plan"
    assert len(interventions) == count_before
    assert cases[5].status == "UNDER_INTERVENTION"
    assert client.put(PLAN(9999), json={"scheduled_for": "2026-10-22"}, headers=headers).status_code == 404
    assert client.put(PLAN(20), json={}, headers=headers).status_code == 400
    assert client.put(PLAN(20), json={"status": "FOLLOW_UP_DUE"}, headers=headers).status_code == 400
    assert client.put(PLAN(20), json={"performed_on": "2026-10-09"}, headers=headers).status_code == 400


def test_plan_reassignment_requires_active_technician(intervention_client):
    client, _, _, _, _, _ = intervention_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    assert client.put(PLAN(20), json={"assigned_to_user_id": 9999}, headers=headers).status_code == 404
    assert client.put(PLAN(20), json={"assigned_to_user_id": 1}, headers=headers).status_code == 400
    assert client.put(PLAN(20), json={"assigned_to_user_id": 4}, headers=headers).status_code == 400


def test_completed_intervention_cannot_be_edited(intervention_client):
    client, _, _, _, _, _ = intervention_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    r = client.put(PLAN(21), json={"scheduled_for": "2026-10-22"}, headers=headers)
    assert r.status_code == 409
    assert r.get_json() == {"data": None, "message": "Completed interventions cannot be edited."}


def test_plan_permission_assigned_vs_unrelated(intervention_client):
    client, _, _, _, _, _ = intervention_client
    token2 = login_tech2(client)
    headers2 = {"Origin": ORIGIN, "X-CSRF-Token": token2}
    r = client.put(PLAN(20), json={"scheduled_for": "2026-10-22"}, headers=headers2)
    assert r.status_code == 403
    token1 = login_tech(client)
    headers1 = {"Origin": ORIGIN, "X-CSRF-Token": token1}
    assert client.put(PLAN(20), json={"scheduled_for": "2026-10-22"}, headers=headers1).status_code == 200


def test_complete_happy_path_admin_and_transition(intervention_client):
    client, cases, interventions, _, _, _ = intervention_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    resp = client.post(
        COMPLETE(20),
        json={
            "performed_on": "2026-10-09",
            "completion_notes": "Cleared affected shoots",
            "follow_up_due_on": "2026-10-20",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.get_json()["data"]["intervention"]
    assert body["performed_on"] == "2026-10-09"
    assert body["follow_up_due_on"] == "2026-10-20"
    assert body["completed_by_user_id"] == 1
    assert body["pest_case"]["status"] == "FOLLOW_UP_DUE"
    assert cases[5].status == "FOLLOW_UP_DUE"


def test_complete_with_reused_planned_date(intervention_client):
    client, _, _, _, _, _ = intervention_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    resp = client.post(
        COMPLETE(20),
        json={
            "performed_on": "2026-10-09",
            "completion_notes": "Cleared affected shoots",
            "reuse_planned_follow_up_date": True,
        },
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["intervention"]["follow_up_due_on"] == "2026-10-20"


def test_complete_requires_follow_up_date(intervention_client):
    client, _, _, _, _, _ = intervention_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    r = client.post(
        COMPLETE(20),
        json={"performed_on": "2026-10-09", "completion_notes": "Done"},
        headers=headers,
    )
    assert r.status_code == 400


def test_complete_validates_notes_and_dates(intervention_client):
    client, cases, _, _, _, _ = intervention_client
    token = login_tech(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    good = {
        "performed_on": "2026-10-09",
        "completion_notes": "Cleared shoots",
        "follow_up_due_on": "2026-10-20",
    }
    assert client.post(COMPLETE(20), json={**good, "completion_notes": "   "}, headers=headers).status_code == 400
    assert client.post(COMPLETE(20), json={**good, "completion_notes": "x" * 2001}, headers=headers).status_code == 400
    future = (manila_today() + timedelta(days=1)).isoformat()
    assert client.post(COMPLETE(20), json={**good, "performed_on": future}, headers=headers).status_code == 400
    assert client.post(COMPLETE(20), json={**good, "follow_up_due_on": "2026-10-08"}, headers=headers).status_code == 400
    assert client.post(COMPLETE(20), json={**good, "status": "FOLLOW_UP_DUE"}, headers=headers).status_code == 400
    missing = dict(good)
    del missing["performed_on"]
    assert client.post(COMPLETE(20), json=missing, headers=headers).status_code == 400
    assert cases[5].status == "UNDER_INTERVENTION"


def test_repeat_completion_returns_409(intervention_client):
    client, _, _, _, _, _ = intervention_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    payload = {
        "performed_on": "2026-10-09",
        "completion_notes": "Already done",
        "follow_up_due_on": "2026-10-20",
    }
    assert client.post(COMPLETE(21), json=payload, headers=headers).status_code == 409
    repeated = client.post(COMPLETE(21), json=payload, headers=headers)
    assert repeated.status_code == 409
    assert repeated.get_json() == {"data": None, "message": "Intervention has already been completed."}


def test_assigned_vs_unrelated_completion_permissions(intervention_client):
    client, _, _, _, _, _ = intervention_client
    token2 = login_tech2(client)
    headers2 = {"Origin": ORIGIN, "X-CSRF-Token": token2}
    payload = {
        "performed_on": "2026-10-09",
        "completion_notes": "Trying as other tech",
        "follow_up_due_on": "2026-10-20",
    }
    assert client.post(COMPLETE(20), json=payload, headers=headers2).status_code == 403
    token1 = login_tech(client)
    headers1 = {"Origin": ORIGIN, "X-CSRF-Token": token1}
    assert client.post(COMPLETE(20), json=payload, headers=headers1).status_code == 200


def test_no_delete_endpoints_registered(intervention_client):
    client, _, _, _, _, _ = intervention_client
    rules = [rule for rule in client.application.url_map.iter_rules() if rule.rule.startswith("/api/v1/interventions")]
    assert rules, "Expected intervention routes to be registered."
    assert all("DELETE" not in rule.methods for rule in rules)
    start_rules = [rule for rule in client.application.url_map.iter_rules() if rule.rule.endswith("start-intervention")]
    assert start_rules
    assert all("DELETE" not in rule.methods for rule in start_rules)


def test_neighboring_endpoints_regressed(intervention_client):
    client, _, _, _, _, _ = intervention_client
    login_admin(client)
    assert client.get("/api/v1/farmers").status_code == 200
    assert client.get("/api/v1/farms").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200


def test_database_errors_sanitized(intervention_client, monkeypatch):
    client, _, _, _, _, _ = intervention_client
    login_admin(client)

    def fail_list(*_a, **_k):
        raise SQLAlchemyError("internal intervention detail")

    monkeypatch.setattr(interventions_module, "list_all_interventions", fail_list)
    resp = client.get(INTERVENTIONS)
    assert resp.status_code == 503
    assert resp.get_json() == {"data": None, "message": "Intervention service unavailable."}
    assert "internal intervention detail" not in resp.get_data(as_text=True)


def test_model_normalization_helpers():
    assert normalize_method_category("CULTURAL") == "CULTURAL"
    with pytest.raises(ValueError):
        normalize_method_category("SPRAYING")
    assert normalize_method_description("  Clear shoots  ") == "Clear shoots"
    with pytest.raises(ValueError):
        normalize_method_description("   ")
    assert normalize_completion_notes("  Done  ") == "Done"
    assert normalize_completion_notes(None) is None
    with pytest.raises(ValueError):
        normalize_completion_notes("   ")
    assert normalize_intervention_scheduled_for("2026-10-12") == date(2026, 10, 12)
    with pytest.raises(ValueError):
        normalize_intervention_scheduled_for("12/10/2026")
    assert normalize_follow_up_due_on(None) is None
    assert normalize_performed_on(manila_today().isoformat()) == manila_today()
    with pytest.raises(ValueError):
        normalize_performed_on((manila_today() + timedelta(days=1)).isoformat())


def test_model_relationship_and_constraints():
    assert Intervention.__tablename__ == "interventions"
    names = {c.name for c in Intervention.__table__.constraints}
    assert {
        "ck_interventions_method_category",
        "ck_interventions_description_nonblank",
        "ck_interventions_description_max",
        "ck_interventions_completion_state",
        "ck_interventions_notes_nonblank",
        "ck_interventions_notes_max",
        "ck_interventions_follow_up_required",
        "ck_interventions_follow_up_order",
    } <= names
    index_names = {index.name for index in Intervention.__table__.indexes}
    assert {"uq_interventions_pending_case", "ix_interventions_pest_case_id", "ix_interventions_assigned_to_user_id"} <= index_names
    fks = {(e.column.table.name, e.ondelete) for e in Intervention.__table__.foreign_keys}
    assert ("pest_cases", "RESTRICT") in fks
    assert ("users", "RESTRICT") in fks
    assert "UNDER_INTERVENTION" in {s.value for s in PestCaseStatus}
    assert "FOLLOW_UP_DUE" in {s.value for s in PestCaseStatus}
    item = Intervention(
        pest_case_id=1,
        method_category="CULTURAL",
        method_description="Clear shoots",
        scheduled_for=date(2026, 10, 12),
        assigned_to_user_id=2,
        created_by_user_id=1,
    )
    assert item.scheduled_for == date(2026, 10, 12)
    with pytest.raises(ValueError):
        item.method_description = "   "
    with pytest.raises(ValueError):
        item.method_category = "BOGUS"
