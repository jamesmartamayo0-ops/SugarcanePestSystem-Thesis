from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app import auth, create_app
from app.models import Farm, Farmer, FollowUp, Intervention, PestCase, PestCaseStatus, User
from app.models.follow_up import (
    manila_today,
    normalize_assessment_notes,
    normalize_follow_up_observed_on,
    normalize_follow_up_outcome,
    normalize_observed_area,
    normalize_pest_observed,
)
from app.routes import follow_ups as follow_ups_module
from app.routes import pest_cases as pest_cases_module
from app.routes import farmers as farmers_module
from app.routes import farms as farms_module

FOLLOW_UPS = "/api/v1/follow-ups"
DUE = "/api/v1/follow-ups/due"
RECORD = lambda i: f"/api/v1/interventions/{i}/record-follow-up"  # noqa: E731
START = lambda c: f"/api/v1/pest-cases/{c}/start-intervention"  # noqa: E731
LOGIN = "/api/v1/auth/login"
ORIGIN = "http://localhost:3000"
ADMIN_PASSWORD = "admin-password-123"
TECH_PASSWORD = "technician-pass-123"
TECH2_PASSWORD = "technician-two-pass-123"


def _stamp():
    return datetime(2026, 10, 10, tzinfo=timezone.utc)


@pytest.fixture
def follow_up_client(monkeypatch):
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
        9: make_case(9, PestCaseStatus.CLOSED.value),
        10: make_case(10, PestCaseStatus.REINTERVENTION_REQUIRED.value),
        11: make_case(11, PestCaseStatus.REINTERVENTION_REQUIRED.value),
        13: make_case(13, PestCaseStatus.FOLLOW_UP_DUE.value),
        14: make_case(14, PestCaseStatus.FOLLOW_UP_DUE.value),
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
        20: make_intervention(20, 5, assigned=2, completed=False),
        21: make_intervention(21, 6, assigned=2, completed=True),
        23: make_intervention(23, 9, assigned=2, completed=True),
        24: make_intervention(24, 10, assigned=2, completed=True),
        25: make_intervention(25, 11, assigned=2, completed=True),
        29: make_intervention(29, 14, assigned=4, completed=True),
        30: make_intervention(30, 13, assigned=2, completed=True),
        31: make_intervention(31, 13, assigned=2, completed=True),
    }
    # Older completed for case 13 has earlier performed date; latest is 31.
    intervention_store[30].performed_on = date(2026, 10, 8)
    intervention_store[31].performed_on = date(2026, 10, 9)

    def make_follow_up(fu_id, intervention_id, outcome="RESOLVED", recorder=2):
        insp = intervention_store[intervention_id]
        fu = FollowUp(
            intervention_id=intervention_id,
            observed_on=date(2026, 10, 9),
            pest_observed=False,
            observed_affected_area_hectares=Decimal("0.50"),
            assessment_notes="Canopy recovering, no fresh damage",
            outcome=outcome,
            recorded_by_user_id=recorder,
        )
        fu.id = fu_id
        fu.created_at = _stamp()
        fu.updated_at = _stamp()
        fu.intervention = insp
        fu.recorder = users[recorder]
        return fu

    follow_up_store = {
        101: make_follow_up(101, 23, outcome="RESOLVED"),
        102: make_follow_up(102, 24, outcome="REINTERVENTION_REQUIRED"),
    }
    state = {"next_follow_up_id": 200, "next_intervention_id": 40}

    def by_id(uid):
        return users.get(uid)

    def by_username(name):
        return next((u for u in users.values() if u.username == name), None)

    def fake_lock(cid):
        locks["cases"].append(cid)

    def fake_user(uid):
        return users.get(uid)

    # --- follow_ups module fakes ---
    def fake_intervention_by_id(iid):
        return intervention_store.get(iid)

    def fake_case_for_update(cid):
        return case_store.get(cid)

    def fake_intervention_for_update(iid):
        return intervention_store.get(iid)

    def fake_follow_up_by_id(fid):
        for item in follow_up_store.values():
            if item.id == fid:
                return item
        return None

    def fake_follow_up_for_update(iid):
        for item in follow_up_store.values():
            if item.intervention_id == iid:
                return item
        return None

    def fake_latest_id(cid):
        completed = [
            item.id
            for item in intervention_store.values()
            if item.pest_case_id == cid and item.completed_at is not None
        ]
        return max(completed) if completed else None

    def fake_farm(fid):
        return farm_store.get(fid)

    def fake_list(pest_case_id=None, intervention_id=None, outcome=None):
        items = sorted(follow_up_store.values(), key=lambda x: x.id)
        if outcome is not None:
            items = [x for x in items if x.outcome == outcome]
        if intervention_id is not None:
            items = [x for x in items if x.intervention_id == intervention_id]
        if pest_case_id is not None:
            items = [x for x in items if x.intervention.pest_case_id == pest_case_id]
        return items

    def fake_due():
        out = []
        for item in sorted(intervention_store.values(), key=lambda x: x.id):
            if item.completed_at is None:
                continue
            case = case_store.get(item.pest_case_id)
            if case is None or case.status != PestCaseStatus.FOLLOW_UP_DUE.value:
                continue
            if any(fu.intervention_id == item.id for fu in follow_up_store.values()):
                continue
            out.append(item)
        return out

    monkeypatch.setattr(auth, "get_user_by_id", by_id)
    monkeypatch.setattr(auth, "get_user_by_username", by_username)
    monkeypatch.setattr(auth, "save_last_login", lambda item, ts: setattr(item, "last_login_at", ts))
    monkeypatch.setattr(auth, "now_epoch_seconds", lambda: clock["now"])
    monkeypatch.setattr(follow_ups_module, "get_intervention_by_id", fake_intervention_by_id)
    monkeypatch.setattr(follow_ups_module, "get_case_for_update", fake_case_for_update)
    monkeypatch.setattr(follow_ups_module, "get_intervention_for_update", fake_intervention_for_update)
    monkeypatch.setattr(follow_ups_module, "get_follow_up_by_id", fake_follow_up_by_id)
    monkeypatch.setattr(follow_ups_module, "get_follow_up_for_update_by_intervention", fake_follow_up_for_update)
    monkeypatch.setattr(follow_ups_module, "get_latest_completed_intervention_id", fake_latest_id)
    monkeypatch.setattr(follow_ups_module, "get_farm_by_id", fake_farm)
    monkeypatch.setattr(follow_ups_module, "list_all_follow_ups", fake_list)
    monkeypatch.setattr(follow_ups_module, "list_due_interventions", fake_due)
    monkeypatch.setattr(follow_ups_module, "acquire_follow_up_case_lock", fake_lock)
    monkeypatch.setattr(follow_ups_module, "commit_follow_up_changes", lambda: None)
    monkeypatch.setattr(follow_ups_module, "get_follow_up_by_intervention_id", fake_follow_up_for_update)

    # --- pest_cases module fakes (repeat start) ---
    def fake_pest_case_by_id(cid):
        return case_store.get(cid)

    def fake_pest_case_for_update(cid):
        return case_store.get(cid)

    def fake_pending_by_case(cid):
        for item in intervention_store.values():
            if item.pest_case_id == cid and item.completed_at is None:
                return item
        return None

    def fake_latest_obj(cid):
        completed = [
            item for item in intervention_store.values()
            if item.pest_case_id == cid and item.completed_at is not None
        ]
        if not completed:
            return None
        return max(completed, key=lambda x: x.id)

    def fake_fu_by_intervention(iid):
        for item in follow_up_store.values():
            if item.intervention_id == iid:
                return item
        return None

    monkeypatch.setattr(pest_cases_module, "get_pest_case_by_id", fake_pest_case_by_id)
    monkeypatch.setattr(pest_cases_module, "get_pest_case_for_update", fake_pest_case_for_update)
    monkeypatch.setattr(pest_cases_module, "get_pending_intervention_by_case_id", fake_pending_by_case)
    monkeypatch.setattr(pest_cases_module, "get_latest_completed_intervention_by_case_id", fake_latest_obj)
    monkeypatch.setattr(pest_cases_module, "get_follow_up_by_intervention_id", fake_fu_by_intervention)
    monkeypatch.setattr(pest_cases_module, "acquire_pest_case_transition_lock", fake_lock)
    monkeypatch.setattr(pest_cases_module, "commit_pest_case_changes", lambda: None)
    monkeypatch.setattr(pest_cases_module, "get_user_by_id", fake_user)
    monkeypatch.setattr(pest_cases_module, "get_inspection_by_case_id", lambda cid: None)
    monkeypatch.setattr(pest_cases_module, "list_case_evidence_photos", lambda cid: [])
    monkeypatch.setattr(farmers_module, "list_all_farmers", lambda: [])
    monkeypatch.setattr(farms_module, "list_all_farms", lambda farmer_id=None: [])

    from app.extensions import db as _db

    orig_add = _db.session.add

    def fake_add(obj):
        if isinstance(obj, FollowUp):
            # Enforce one-follow-up-per-intervention like the UNIQUE constraint.
            for existing in follow_up_store.values():
                if existing.intervention_id == obj.intervention_id:
                    from sqlalchemy.exc import IntegrityError as _IE

                    raise _IE("duplicate follow-up", params=None, orig=None)
            if obj.id is None:
                obj.id = state["next_follow_up_id"]
                state["next_follow_up_id"] += 1
            insp = intervention_store.get(obj.intervention_id)
            if insp is not None:
                obj.intervention = insp
            if obj.recorded_by_user_id in users:
                obj.recorder = users[obj.recorded_by_user_id]
            if obj.created_at is None:
                obj.created_at = _stamp()
            if obj.updated_at is None:
                obj.updated_at = _stamp()
            follow_up_store[obj.id] = obj
            return
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

    return app.test_client(), case_store, intervention_store, follow_up_store, farm_store, users, locks


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


def record_payload(**overrides):
    base = {
        "observed_on": "2026-10-09",
        "pest_observed": False,
        "observed_affected_area_hectares": 0.5,
        "assessment_notes": "Canopy recovering, no fresh damage",
        "outcome": "RESOLVED",
    }
    base.update(overrides)
    return base


def test_unauthenticated_follow_up_endpoints_return_401(follow_up_client):
    client, _, _, _, _, _, _ = follow_up_client
    assert client.get(FOLLOW_UPS).status_code == 401
    assert client.get(f"{FOLLOW_UPS}/101").status_code == 401
    assert client.get(DUE).status_code == 401
    assert client.post(RECORD(21), json={}, headers={"Origin": ORIGIN}).status_code == 401


def test_unsafe_requests_require_origin_and_csrf(follow_up_client):
    client, _, _, _, _, _, _ = follow_up_client
    token = login_admin(client)
    assert client.get(FOLLOW_UPS).status_code == 200
    assert client.get(DUE).status_code == 200
    payload = record_payload()
    assert client.post(RECORD(21), json=payload).status_code == 403
    assert client.post(RECORD(21), json=payload, headers={"Origin": ORIGIN}).status_code == 403
    assert client.post(RECORD(21), json=payload, headers={"Origin": ORIGIN, "X-CSRF-Token": "0" * 64}).status_code == 403
    ok = client.post(RECORD(21), json=payload, headers={"Origin": ORIGIN, "X-CSRF-Token": token})
    assert ok.status_code == 201
    assert ok.headers["Cache-Control"] == "no-store"


def test_list_and_detail_with_references(follow_up_client):
    client, _, _, _, _, _, _ = follow_up_client
    login_admin(client)
    body = client.get(FOLLOW_UPS).get_json()
    assert set(body) == {"data", "message"}
    assert len(body["data"]["follow_ups"]) == 2
    entry = body["data"]["follow_ups"][0]
    assert entry["pest_case"]["farm"]["farmer"]["full_name"] == "Juan Dela Cruz"
    assert entry["intervention"]["method_category"] == "CULTURAL"
    assert entry["assigned_to"]["full_name"] == "Tech One"
    assert entry["recorded_by"]["username"] == "tech.one"
    assert client.get(f"{FOLLOW_UPS}?outcome=RESOLVED").get_json()["data"]["follow_ups"] != []
    assert client.get(f"{FOLLOW_UPS}?intervention_id=24").get_json()["data"]["follow_ups"] != []
    assert client.get(f"{FOLLOW_UPS}?pest_case_id=9").get_json()["data"]["follow_ups"] != []
    assert client.get(f"{FOLLOW_UPS}?outcome=BOGUS").status_code == 400
    assert client.get(f"{FOLLOW_UPS}?pest_case_id=abc").status_code == 400
    assert client.get(f"{FOLLOW_UPS}/101").status_code == 200
    assert client.get(f"{FOLLOW_UPS}/9999").status_code == 404


def test_due_queue_only_follow_up_due(follow_up_client):
    client, _, _, _, _, _, _ = follow_up_client
    login_admin(client)
    body = client.get(DUE).get_json()["data"]["due"]
    ids = {entry["intervention_id"] for entry in body}
    # 21 (case 6 FOLLOW_UP_DUE, no follow-up), 29 (case 14), 31 (latest for case 13)
    assert {21, 29, 31} <= ids
    # 20 pending, 23 closed, 24 reintervention must not appear.
    assert 20 not in ids and 23 not in ids and 24 not in ids
    for entry in body:
        assert entry["case_status"] == "FOLLOW_UP_DUE"
        assert entry["performed_on"] is not None
        assert entry["follow_up_due_on"] is not None
        assert entry["due_state"] in {"UPCOMING", "DUE_TODAY", "OVERDUE"}


def test_assigned_vs_unrelated_technician(follow_up_client):
    client, _, _, _, _, _, _ = follow_up_client
    token2 = login_tech2(client)
    headers2 = {"Origin": ORIGIN, "X-CSRF-Token": token2}
    # Intervention 21 assigned to tech.one; tech.two must be rejected.
    assert client.post(RECORD(21), json=record_payload(), headers=headers2).status_code == 403
    token1 = login_tech(client)
    headers1 = {"Origin": ORIGIN, "X-CSRF-Token": token1}
    assert client.post(RECORD(21), json=record_payload(), headers=headers1).status_code == 201


def test_admin_can_record_for_inactive_assignee(follow_up_client):
    client, cases, _, _, _, _, _ = follow_up_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    resp = client.post(RECORD(29), json=record_payload(outcome="RESOLVED"), headers=headers)
    assert resp.status_code == 201
    assert resp.get_json()["data"]["follow_up"]["pest_case"]["status"] == "CLOSED"
    assert cases[14].status == "CLOSED"


def test_incomplete_intervention_rejected(follow_up_client):
    client, _, _, _, _, _, _ = follow_up_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    r = client.post(RECORD(20), json=record_payload(), headers=headers)
    assert r.status_code == 409
    assert r.get_json() == {"data": None, "message": "Intervention has not been completed."}


def test_incorrect_case_status_rejected(follow_up_client):
    client, _, _, _, _, _, _ = follow_up_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    # Intervention 20 is pending under UNDER_INTERVENTION, not FOLLOW_UP_DUE.
    assert client.post(RECORD(20), json=record_payload(), headers=headers).status_code == 409
    # Intervention 23 belongs to CLOSED case.
    assert client.post(RECORD(23), json=record_payload(), headers=headers).status_code == 409


def test_latest_intervention_enforced(follow_up_client):
    client, _, _, _, _, _, _ = follow_up_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    # 30 is older completed for case 13; latest is 31.
    r = client.post(RECORD(30), json=record_payload(), headers=headers)
    assert r.status_code == 409
    assert r.get_json() == {
        "data": None,
        "message": "Follow-up can only be recorded for the latest completed intervention.",
    }


def test_duplicate_follow_up_returns_409(follow_up_client):
    client, _, _, _, _, _, _ = follow_up_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    first = client.post(RECORD(21), json=record_payload(), headers=headers)
    assert first.status_code == 201
    dup = client.post(RECORD(21), json=record_payload(outcome="REINTERVENTION_REQUIRED"), headers=headers)
    assert dup.status_code == 409
    assert dup.get_json() == {
        "data": None,
        "message": "Follow-up has already been recorded for this intervention.",
    }


def test_strict_payload_allowlist(follow_up_client):
    client, _, _, _, _, _, _ = follow_up_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    assert client.post(RECORD(21), json={**record_payload(), "status": "CLOSED"}, headers=headers).status_code == 400
    assert client.post(RECORD(21), json={**record_payload(), "recorded_by_user_id": 1}, headers=headers).status_code == 400
    missing = record_payload()
    del missing["outcome"]
    assert client.post(RECORD(21), json=missing, headers=headers).status_code == 400
    assert client.post(RECORD(21), json={}, headers=headers).status_code == 400


def test_strict_dates_future_and_order(follow_up_client):
    client, cases, _, _, _, _, _ = follow_up_client
    token = login_tech(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    good = record_payload()
    future = (manila_today() + timedelta(days=1)).isoformat()
    assert client.post(RECORD(21), json={**good, "observed_on": future}, headers=headers).status_code == 400
    assert client.post(RECORD(21), json={**good, "observed_on": "not-a-date"}, headers=headers).status_code == 400
    # Before performed_on (2026-10-09).
    assert client.post(RECORD(21), json={**good, "observed_on": "2026-10-08"}, headers=headers).status_code == 400
    assert cases[6].status == "FOLLOW_UP_DUE"


def test_area_validation(follow_up_client):
    client, _, _, _, _, _, _ = follow_up_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    assert client.post(RECORD(21), json=record_payload(observed_affected_area_hectares=-1), headers=headers).status_code == 400
    # Farm area is 4.00 ha; 99 ha must be rejected.
    assert client.post(RECORD(21), json=record_payload(observed_affected_area_hectares=99), headers=headers).status_code == 400
    assert client.post(RECORD(21), json=record_payload(observed_affected_area_hectares=True), headers=headers).status_code == 400
    # Null/omitted area is allowed.
    assert client.post(RECORD(21), json={k: v for k, v in record_payload().items() if k != "observed_affected_area_hectares"}, headers=headers).status_code == 201


def test_invalid_outcome_rejected(follow_up_client):
    client, _, _, _, _, _, _ = follow_up_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    assert client.post(RECORD(21), json=record_payload(outcome="CURED"), headers=headers).status_code == 400
    assert client.post(RECORD(21), json=record_payload(outcome="resolved"), headers=headers).status_code == 400
    assert client.post(RECORD(21), json=record_payload(outcome=""), headers=headers).status_code == 400


def test_pest_observed_must_be_bool(follow_up_client):
    client, _, _, _, _, _, _ = follow_up_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    assert client.post(RECORD(21), json=record_payload(pest_observed="yes"), headers=headers).status_code == 400
    assert client.post(RECORD(21), json=record_payload(pest_observed=1), headers=headers).status_code == 400


def test_resolved_transitions_to_closed(follow_up_client):
    client, cases, _, _, _, _, _ = follow_up_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    resp = client.post(RECORD(21), json=record_payload(outcome="RESOLVED", pest_observed=False), headers=headers)
    assert resp.status_code == 201
    body = resp.get_json()["data"]["follow_up"]
    assert body["outcome"] == "RESOLVED"
    assert body["pest_case"]["status"] == "CLOSED"
    assert cases[6].status == "CLOSED"


def test_reintervention_outcome_transitions(follow_up_client):
    client, cases, _, _, _, _, _ = follow_up_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    resp = client.post(
        RECORD(21),
        json=record_payload(outcome="REINTERVENTION_REQUIRED", pest_observed=True),
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.get_json()["data"]["follow_up"]["outcome"] == "REINTERVENTION_REQUIRED"
    assert cases[6].status == "REINTERVENTION_REQUIRED"


def test_repeat_intervention_start_from_reintervention(follow_up_client):
    client, cases, interventions, _, _, _, _ = follow_up_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    before = len(interventions)
    resp = client.post(
        START(10),
        json={
            "method_category": "MECHANICAL",
            "method_description": "Repeat removal of regrowth",
            "scheduled_for": "2026-10-15",
            "assigned_to_user_id": 2,
        },
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.get_json()["data"]["intervention"]["pest_case"]["status"] == "UNDER_INTERVENTION"
    assert cases[10].status == "UNDER_INTERVENTION"
    assert len(interventions) == before + 1


def test_repeat_start_blocked_without_follow_up(follow_up_client):
    client, _, _, _, _, _, _ = follow_up_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    # Case 11 is REINTERVENTION_REQUIRED but intervention 25 has no follow-up.
    assert client.post(
        START(11),
        json={
            "method_category": "CULTURAL",
            "method_description": "Repeat work",
            "scheduled_for": "2026-10-15",
            "assigned_to_user_id": 2,
        },
        headers=headers,
    ).status_code == 409


def test_closed_and_not_confirmed_cannot_start(follow_up_client):
    client, _, _, _, _, _, _ = follow_up_client
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    payload = {
        "method_category": "CULTURAL",
        "method_description": "Work",
        "scheduled_for": "2026-10-15",
        "assigned_to_user_id": 2,
    }
    assert client.post(START(9), json=payload, headers=headers).status_code == 409
    assert client.post(START(2), json=payload, headers=headers).status_code == 409
    # FOLLOW_UP_DUE cannot start directly.
    assert client.post(START(6), json=payload, headers=headers).status_code == 409


def test_no_follow_up_modification_or_deletion_endpoints(follow_up_client):
    client, _, _, _, _, _, _ = follow_up_client
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


def test_database_errors_sanitized(follow_up_client, monkeypatch):
    client, _, _, _, _, _, _ = follow_up_client
    login_admin(client)

    def fail_list(*_a, **_k):
        raise SQLAlchemyError("internal follow-up detail")

    monkeypatch.setattr(follow_ups_module, "list_all_follow_ups", fail_list)
    resp = client.get(FOLLOW_UPS)
    assert resp.status_code == 503
    assert resp.get_json() == {"data": None, "message": "Follow-up service unavailable."}
    assert "internal follow-up detail" not in resp.get_data(as_text=True)


def test_model_normalization_helpers():
    assert normalize_follow_up_observed_on(manila_today().isoformat()) == manila_today()
    with pytest.raises(ValueError):
        normalize_follow_up_observed_on((manila_today() + timedelta(days=1)).isoformat())
    assert normalize_pest_observed(True) is True
    with pytest.raises(ValueError):
        normalize_pest_observed("yes")
    assert normalize_observed_area(None) is None
    assert normalize_observed_area(0) == Decimal("0.00")
    with pytest.raises(ValueError):
        normalize_observed_area(-1)
    assert normalize_assessment_notes("  Recovering  ") == "Recovering"
    with pytest.raises(ValueError):
        normalize_assessment_notes("   ")
    assert normalize_follow_up_outcome("RESOLVED") == "RESOLVED"
    with pytest.raises(ValueError):
        normalize_follow_up_outcome("CURED")


def test_model_relationship_and_constraints():
    assert FollowUp.__tablename__ == "follow_ups"
    names = {c.name for c in FollowUp.__table__.constraints}
    assert {
        "uq_follow_ups_intervention_id",
        "ck_follow_ups_outcome",
        "ck_follow_ups_notes_nonblank",
        "ck_follow_ups_notes_max",
        "ck_follow_ups_area_range",
    } <= names
    fks = {(e.column.table.name, e.ondelete) for e in FollowUp.__table__.foreign_keys}
    assert ("interventions", "RESTRICT") in fks
    assert ("users", "RESTRICT") in fks
    assert "REINTERVENTION_REQUIRED" in {s.value for s in PestCaseStatus}
    assert "CLOSED" in {s.value for s in PestCaseStatus}
    item = FollowUp(
        intervention_id=21,
        observed_on=date(2026, 10, 9),
        pest_observed=False,
        observed_affected_area_hectares=Decimal("0.50"),
        assessment_notes="Recovering",
        outcome="RESOLVED",
        recorded_by_user_id=1,
    )
    assert item.observed_on == date(2026, 10, 9)
    with pytest.raises(ValueError):
        item.assessment_notes = "   "
    with pytest.raises(ValueError):
        item.outcome = "BOGUS"
