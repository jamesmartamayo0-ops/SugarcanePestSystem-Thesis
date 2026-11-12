import io
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from flask import g
from sqlalchemy.exc import SQLAlchemyError

from app import auth, create_app, evidence
from app.models import Farm, Farmer, PestCase, PestCaseEvidencePhoto, PestCaseStatus, User
from app.models.pest_case import (
    normalize_observed_on,
    normalize_pest_name,
    normalize_reported_area,
    normalize_symptoms,
)
from app.routes import farmers as farmers_module
from app.routes import farms as farms_module
from app.routes import pest_cases as pest_cases_module

CASES = "/api/v1/pest-cases"
CASE = lambda case_id: f"/api/v1/pest-cases/{case_id}"  # noqa: E731
SUBMIT = lambda case_id: f"/api/v1/pest-cases/{case_id}/submit-for-inspection"  # noqa: E731
LOGIN = "/api/v1/auth/login"
ORIGIN = "http://localhost:3000"
ADMIN_PASSWORD = "admin-password-123"
TECH_PASSWORD = "technician-pass-123"
TECH2_PASSWORD = "technician-two-pass-123"
PHOTOS = lambda case_id: f"/api/v1/pest-cases/{case_id}/evidence-photos"  # noqa: E731
PHOTO = lambda case_id, photo_id: f"/api/v1/pest-cases/{case_id}/evidence-photos/{photo_id}"  # noqa: E731
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _stamp():
    return datetime(2026, 10, 9, tzinfo=timezone.utc)


@pytest.fixture
def pest_case(monkeypatch):
    monkeypatch.setenv(
        "AUTH_TRUSTED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    )
    app = create_app()
    app.testing = True

    admin = User(
        id=1, username="admin.one", full_name="Admin One",
        role="ADMIN", is_active=True, auth_version=0,
    )
    admin.set_password(ADMIN_PASSWORD)
    technician = User(
        id=2, username="tech.one", full_name="Tech One",
        role="TECHNICIAN", is_active=True, auth_version=0,
    )
    technician.set_password(TECH_PASSWORD)
    technician_two = User(
        id=3, username="tech.two", full_name="Tech Two",
        role="TECHNICIAN", is_active=True, auth_version=0,
    )
    technician_two.set_password(TECH2_PASSWORD)
    users = {admin.id: admin, technician.id: technician, technician_two.id: technician_two}
    clock = {"now": 1_750_000_000}
    locks = {"transitions": 0}

    farmer = Farmer(full_name="Juan Dela Cruz", barangay="Bunao")
    farmer.id = 1
    farmer.created_at = _stamp()
    farmer.updated_at = _stamp()

    farm = Farm(farmer_id=1, plot_identifier="Plot A", barangay="Bunao", area_hectares="4.00")
    farm.id = 1
    farm.created_at = _stamp()
    farm.updated_at = _stamp()
    farm.farmer = farmer
    small_farm = Farm(farmer_id=1, plot_identifier="Plot B", barangay="Bunao", area_hectares="1.00")
    small_farm.id = 2
    small_farm.created_at = _stamp()
    small_farm.updated_at = _stamp()
    small_farm.farmer = farmer
    farm_store = {farm.id: farm, small_farm.id: small_farm}

    case_store = {}
    state = {"next_case_id": 1}

    def seed_case(**overrides):
        values = {
            "farm_id": 1,
            "pest_name": "Stem Borer",
            "symptoms": "Bored stalks observed",
            "observed_on": "2026-09-15",
            "reported_area_hectares": "2.50",
            "status": PestCaseStatus.REPORTED.value,
            "reported_by_user_id": 2,
        }
        values.update(overrides)
        case = PestCase(**values)
        case.id = state["next_case_id"]
        state["next_case_id"] += 1
        case.reported_at = _stamp()
        case.updated_at = _stamp()
        case.farm = farm_store[case.farm_id]
        case.reporter = users[case.reported_by_user_id]
        case_store[case.id] = case
        return case

    seed_case()

    def by_id(user_id):
        return users.get(user_id)

    def by_username(username):
        return next((u for u in users.values() if u.username == username), None)

    def fake_list(farm_id=None, status=None, farmer_id=None, search=None, reported_from=None, reported_to=None):
        cases = sorted(case_store.values(), key=lambda c: c.id)
        if farm_id is not None:
            cases = [c for c in cases if c.farm_id == farm_id]
        if status is not None:
            cases = [c for c in cases if c.status == status]
        if farmer_id is not None:
            cases = [c for c in cases if farm_store.get(c.farm_id) is not None and farm_store[c.farm_id].farmer_id == farmer_id]
        if search is not None:
            lowered = search.lower()
            filtered = []
            for c in cases:
                farm = farm_store.get(c.farm_id)
                haystacks = [
                    (c.pest_name or "").lower(),
                    (c.symptoms or "").lower(),
                    (farm.plot_identifier or "").lower() if farm else "",
                    (farm.barangay or "").lower() if farm else "",
                ]
                if any(lowered in h for h in haystacks) or lowered == str(c.id):
                    filtered.append(c)
            cases = filtered
        return cases

    def fake_get(case_id):
        # Mirror assignment scope at the route boundary: a technician only
        # sees a case assigned to them (or one they reported and nobody owns).
        user = getattr(g, "current_user", None)
        if user is not None and user.role == "TECHNICIAN" and user.id != 2:
            case = case_store.get(case_id)
            if case is not None and case.reported_by_user_id != user.id:
                return None
        return case_store.get(case_id)

    def fake_get_farm(farm_id):
        return farm_store.get(farm_id)

    def fake_lock(case_id):
        locks["transitions"] += 1

    def fake_persist(case):
        case.id = state["next_case_id"]
        state["next_case_id"] += 1
        case.reported_at = _stamp()
        case.updated_at = _stamp()
        case.farm = farm_store[case.farm_id]
        case.reporter = users[case.reported_by_user_id]
        case_store[case.id] = case
        return pest_cases_module._pest_case_detail(case)

    monkeypatch.setattr(auth, "get_user_by_id", by_id)
    monkeypatch.setattr(auth, "get_user_by_username", by_username)
    monkeypatch.setattr(auth, "save_last_login", lambda item, ts: setattr(item, "last_login_at", ts))
    monkeypatch.setattr(auth, "now_epoch_seconds", lambda: clock["now"])
    monkeypatch.setattr(pest_cases_module, "list_all_pest_cases", fake_list)
    monkeypatch.setattr(pest_cases_module, "get_pest_case_by_id", fake_get)
    monkeypatch.setattr(pest_cases_module, "get_pest_case_for_update", fake_get)
    monkeypatch.setattr(pest_cases_module, "get_farm_by_id", fake_get_farm)
    monkeypatch.setattr(pest_cases_module, "persist_new_pest_case", fake_persist)
    monkeypatch.setattr(pest_cases_module, "commit_pest_case_changes", lambda: None)
    monkeypatch.setattr(pest_cases_module, "acquire_pest_case_transition_lock", fake_lock)
    monkeypatch.setattr(pest_cases_module, "get_inspection_by_case_id", lambda case_id: None)
    monkeypatch.setattr(pest_cases_module, "list_case_evidence_photos", lambda case_id: [])
    # Regression fakes keep neighboring modules off the database.
    monkeypatch.setattr(farmers_module, "list_all_farmers", lambda: [farmer])
    monkeypatch.setattr(farms_module, "list_all_farms", lambda farmer_id=None: [farm])

    return app.test_client(), case_store, farm_store, locks


def login(client, username, password, origin=ORIGIN):
    return client.post(
        LOGIN,
        json={"username": username, "password": password},
        headers={"Origin": origin} if origin is not None else {},
    )


def login_admin(client):
    response = login(client, "admin.one", ADMIN_PASSWORD)
    assert response.status_code == 200
    return response.get_json()["data"]["csrf_token"]


def login_technician(client):
    response = login(client, "tech.one", TECH_PASSWORD)
    assert response.status_code == 200
    return response.get_json()["data"]["csrf_token"]


def login_technician_two(client):
    response = login(client, "tech.two", TECH2_PASSWORD)
    assert response.status_code == 200
    return response.get_json()["data"]["csrf_token"]


def test_unauthenticated_pest_case_endpoints_return_401(pest_case):
    client, _, _, _ = pest_case
    assert client.get(CASES).status_code == 401
    assert client.get(CASE(1)).status_code == 401
    assert client.post(CASES, json={}, headers={"Origin": ORIGIN}).status_code == 401
    assert client.put(CASE(1), json={}, headers={"Origin": ORIGIN}).status_code == 401
    assert client.post(SUBMIT(1), json={}, headers={"Origin": ORIGIN}).status_code == 401


def test_technician_can_manage_pest_cases(pest_case):
    client, _, _, _ = pest_case
    token = login_technician(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    assert client.get(CASES).status_code == 200
    assert client.get(CASE(1)).status_code == 200
    response = client.post(
        CASES,
        json={"farm_id": 1, "pest_name": "White Grub", "reported_area_hectares": 1},
        headers=headers,
    )
    assert response.status_code == 201
    assert client.put(CASE(2), json={"pest_name": "White Grub Larva"}, headers=headers).status_code == 200
    assert client.post(SUBMIT(2), headers=headers).status_code == 200


def test_unsafe_requests_require_origin_and_csrf(pest_case):
    client, _, _, _ = pest_case
    token = login_admin(client)
    payload = {"farm_id": 1, "pest_name": "White Grub", "reported_area_hectares": 1}
    assert client.post(CASES, json=payload).status_code == 403
    assert client.post(CASES, json=payload, headers={"Origin": ORIGIN}).status_code == 403
    assert (
        client.post(
            CASES, json=payload, headers={"Origin": ORIGIN, "X-CSRF-Token": "0" * 64}
        ).status_code
        == 403
    )
    response = client.post(
        CASES, json=payload, headers={"Origin": ORIGIN, "X-CSRF-Token": token}
    )
    assert response.status_code == 201
    assert client.post(SUBMIT(1)).status_code == 403
    assert (
        client.post(
            SUBMIT(1), headers={"Origin": ORIGIN, "X-CSRF-Token": token}
        ).status_code
        == 200
    )


def test_list_shape_filters_and_detail(pest_case):
    client, _, _, _ = pest_case
    login_admin(client)
    body = client.get(CASES).get_json()
    assert set(body) == {"data", "message"}
    assert len(body["data"]["pest_cases"]) == 1
    entry = body["data"]["pest_cases"][0]
    assert set(entry) == {
        "id", "farm_id", "pest_name", "reported_area_hectares",
        "status", "observed_on", "reported_at",
    }
    assert entry["status"] == "REPORTED"
    assert entry["observed_on"] == "2026-09-15"
    assert client.get(CASES + "?farm_id=1").get_json()["data"]["pest_cases"] != []
    assert client.get(CASES + "?farm_id=9999").get_json()["data"]["pest_cases"] == []
    assert client.get(CASES + "?status=REPORTED").get_json()["data"]["pest_cases"] != []
    assert client.get(CASES + "?status=FOR_INSPECTION").get_json()["data"]["pest_cases"] == []
    assert client.get(CASES + "?farm_id=abc").status_code == 400
    assert client.get(CASES + "?status=INSPECTED").status_code == 400
    assert client.get(CASES + "?status=reported").status_code == 400

    detail = client.get(CASE(1)).get_json()["data"]["pest_case"]
    assert set(detail) == set(entry) | {
        "symptoms",
        "confirmed_pest_name",
        "evidence_photos",
        "farm",
        "reporter",
        "updated_at",
    }
    assert detail["confirmed_pest_name"] is None
    assert detail["evidence_photos"] == []
    assert set(detail["farm"]) == {
        "id", "plot_identifier", "barangay", "area_hectares", "farmer",
    }
    assert detail["farm"]["farmer"] == {"id": 1, "full_name": "Juan Dela Cruz", "barangay": "Bunao"}
    assert detail["reporter"] == {"id": 2, "username": "tech.one", "full_name": "Tech One"}
    assert client.get(CASE(9999)).status_code == 404


def test_create_case_records_reporter_and_reported_status(pest_case):
    client, store, _, _ = pest_case
    token = login_technician(client)
    response = client.post(
        CASES,
        json={
            "farm_id": 1,
            "pest_name": "  Asiatic   Corn Borer  ",
            "symptoms": "Wilting shoots",
            "observed_on": "2026-09-20",
            "reported_area_hectares": "3.75",
        },
        headers={"Origin": ORIGIN, "X-CSRF-Token": token},
    )
    assert response.status_code == 201
    assert response.headers["Cache-Control"] == "no-store"
    body = response.get_json()["data"]["pest_case"]
    assert body["pest_name"] == "Asiatic Corn Borer"
    assert body["status"] == "REPORTED"
    assert body["reporter"]["id"] == 2
    assert body["reported_at"].startswith("2026-10-09")
    assert store[body["id"]].reported_by_user_id == 2
    assert store[body["id"]].reported_area_hectares == Decimal("3.75")


def test_create_case_without_optional_fields(pest_case):
    client, _, _, _ = pest_case
    token = login_admin(client)
    response = client.post(
        CASES,
        json={"farm_id": 1, "pest_name": "Rats", "reported_area_hectares": 0.5},
        headers={"Origin": ORIGIN, "X-CSRF-Token": token},
    )
    assert response.status_code == 201
    body = response.get_json()["data"]["pest_case"]
    assert body["symptoms"] is None
    assert body["observed_on"] is None


def test_create_case_without_suspected_pest_is_valid(pest_case):
    client, store, _, _ = pest_case
    token = login_technician(client)
    symptoms = "Naay buslot sa stem ug nag-yellow ang ubang dahon."
    response = client.post(
        CASES,
        json={
            "farm_id": 1,
            "symptoms": symptoms,
            "observed_on": "2026-09-20",
            "reported_area_hectares": 1.5,
        },
        headers={"Origin": ORIGIN, "X-CSRF-Token": token},
    )
    assert response.status_code == 201
    body = response.get_json()["data"]["pest_case"]
    assert body["pest_name"] is None
    assert body["symptoms"] == symptoms
    assert store[body["id"]].pest_name is None
    assert store[body["id"]].symptoms == symptoms

    listing = client.get(CASES).get_json()["data"]["pest_cases"]
    entry = next(item for item in listing if item["id"] == body["id"])
    assert entry["pest_name"] is None
    detail = client.get(CASE(body["id"])).get_json()["data"]["pest_case"]
    assert detail["pest_name"] is None
    assert detail["symptoms"] == symptoms


def test_create_case_with_known_suspected_pest_preserved(pest_case):
    client, store, _, _ = pest_case
    token = login_technician(client)
    response = client.post(
        CASES,
        json={"farm_id": 1, "pest_name": "  Stem   Borer ", "reported_area_hectares": 1},
        headers={"Origin": ORIGIN, "X-CSRF-Token": token},
    )
    assert response.status_code == 201
    body = response.get_json()["data"]["pest_case"]
    assert body["pest_name"] == "Stem Borer"
    assert store[body["id"]].pest_name == "Stem Borer"


def test_create_case_blank_suspected_pest_is_unknown(pest_case):
    client, store, _, _ = pest_case
    token = login_technician(client)
    response = client.post(
        CASES,
        json={"farm_id": 1, "pest_name": "   ", "reported_area_hectares": 1},
        headers={"Origin": ORIGIN, "X-CSRF-Token": token},
    )
    assert response.status_code == 201
    body = response.get_json()["data"]["pest_case"]
    assert body["pest_name"] is None
    assert store[body["id"]].pest_name is None


def _install_evidence_store(monkeypatch):
    photo_store = []

    def fake_list(case_id):
        return [photo for photo in photo_store if photo.pest_case_id == case_id]

    def fake_persist(photos):
        for photo in photos:
            photo.id = len(photo_store) + 1
            photo.uploaded_at = _stamp()
            photo_store.append(photo)

    def fake_get(case_id, photo_id):
        return next(
            (
                photo
                for photo in photo_store
                if photo.pest_case_id == case_id and photo.id == photo_id
            ),
            None,
        )

    monkeypatch.setattr(pest_cases_module, "list_case_evidence_photos", fake_list)
    monkeypatch.setattr(pest_cases_module, "persist_evidence_photos", fake_persist)
    monkeypatch.setattr(pest_cases_module, "get_case_evidence_photo", fake_get)
    return photo_store


def _photo_headers(token):
    return {"Origin": ORIGIN, "X-CSRF-Token": token}


def _upload(client, token, filename="evidence.png", data=PNG_BYTES, field="photos"):
    return client.post(
        PHOTOS(1),
        data={field: (io.BytesIO(data), filename)},
        headers=_photo_headers(token),
        content_type="multipart/form-data",
    )


def test_valid_evidence_photo_upload_and_view(pest_case, monkeypatch, tmp_path):
    client, _, _, _ = pest_case
    client.application.config["EVIDENCE_UPLOAD_DIR"] = str(tmp_path)
    photo_store = _install_evidence_store(monkeypatch)
    token = login_technician(client)

    response = _upload(client, token)
    assert response.status_code == 201
    photos = response.get_json()["data"]["pest_case"]["evidence_photos"]
    assert len(photos) == 1
    assert photos[0]["original_filename"] == "evidence.png"
    assert photos[0]["content_type"] == "image/png"
    assert photo_store[0].uploaded_by_user_id == 2
    assert len(list(tmp_path.iterdir())) == 1

    photo_id = photos[0]["id"]
    viewed = client.get(PHOTO(1, photo_id))
    assert viewed.status_code == 200
    assert viewed.mimetype == "image/png"
    assert viewed.data == PNG_BYTES


def test_evidence_photo_invalid_type_rejected(pest_case, monkeypatch, tmp_path):
    client, _, _, _ = pest_case
    client.application.config["EVIDENCE_UPLOAD_DIR"] = str(tmp_path)
    _install_evidence_store(monkeypatch)
    token = login_technician(client)
    response = _upload(client, token, filename="notes.txt", data=b"not an image")
    assert response.status_code == 400
    assert "JPEG, PNG, or WebP" in response.get_json()["message"]
    assert list(tmp_path.iterdir()) == []


def test_evidence_photo_over_limit_rejected(pest_case, monkeypatch, tmp_path):
    client, _, _, _ = pest_case
    client.application.config["EVIDENCE_UPLOAD_DIR"] = str(tmp_path)
    _install_evidence_store(monkeypatch)
    token = login_technician(client)
    oversized = b"\xff\xd8\xff" + b"0" * (5 * 1024 * 1024)
    response = _upload(client, token, data=oversized)
    assert response.status_code == 400
    assert "5 MiB" in response.get_json()["message"]
    assert list(tmp_path.iterdir()) == []


def test_more_than_three_evidence_photos_rejected(pest_case, monkeypatch, tmp_path):
    client, _, _, _ = pest_case
    client.application.config["EVIDENCE_UPLOAD_DIR"] = str(tmp_path)
    _install_evidence_store(monkeypatch)
    token = login_technician(client)
    response = client.post(
        PHOTOS(1),
        data={
            "photos": [
                (io.BytesIO(PNG_BYTES), "one.png"),
                (io.BytesIO(PNG_BYTES), "two.png"),
                (io.BytesIO(PNG_BYTES), "three.png"),
                (io.BytesIO(PNG_BYTES), "four.png"),
            ]
        },
        headers=_photo_headers(token),
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert "at most 3" in response.get_json()["message"]
    assert list(tmp_path.iterdir()) == []


def test_unrelated_technician_cannot_view_evidence(pest_case, monkeypatch, tmp_path):
    client, _, _, _ = pest_case
    client.application.config["EVIDENCE_UPLOAD_DIR"] = str(tmp_path)
    _install_evidence_store(monkeypatch)
    token = login_technician(client)
    upload = _upload(client, token)
    photo_id = upload.get_json()["data"]["pest_case"]["evidence_photos"][0]["id"]

    outsider = client.application.test_client()
    login_technician_two(outsider)
    response = outsider.get(PHOTO(1, photo_id))
    assert response.status_code == 404


def test_create_case_unknown_farm_returns_404(pest_case):
    client, _, _, _ = pest_case
    token = login_admin(client)
    response = client.post(
        CASES,
        json={"farm_id": 9999, "pest_name": "Rats", "reported_area_hectares": 1},
        headers={"Origin": ORIGIN, "X-CSRF-Token": token},
    )
    assert response.status_code == 404
    assert response.get_json() == {"data": None, "message": "Farm not found."}


def test_create_case_area_capped_by_farm_area(pest_case):
    client, _, _, _ = pest_case
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    exact = client.post(
        CASES,
        json={"farm_id": 1, "pest_name": "Rats", "reported_area_hectares": "4.00"},
        headers=headers,
    )
    assert exact.status_code == 201
    over = client.post(
        CASES,
        json={"farm_id": 1, "pest_name": "Rats", "reported_area_hectares": "4.01"},
        headers=headers,
    )
    assert over.status_code == 400
    assert over.get_json() == {
        "data": None,
        "message": "Reported area must not exceed the farm's recorded sugarcane area.",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"farm_id": 1, "pest_name": "Rats"},
        {"pest_name": "Rats", "reported_area_hectares": 1},
        {"farm_id": 1, "pest_name": "Rats", "reported_area_hectares": 1, "extra": 1},
        {"farm_id": 1, "pest_name": "Rats", "reported_area_hectares": 1, "status": "REPORTED"},
        {"farm_id": 1, "pest_name": "Rats", "reported_area_hectares": 1, "status": "FOR_INSPECTION"},
        {"farm_id": "1", "pest_name": "Rats", "reported_area_hectares": 1},
        {"farm_id": True, "pest_name": "Rats", "reported_area_hectares": 1},
        {"farm_id": 1, "pest_name": "x" * 121, "reported_area_hectares": 1},
        {"farm_id": 1, "pest_name": 123, "reported_area_hectares": 1},
        {"farm_id": 1, "pest_name": "Rats", "reported_area_hectares": 0},
        {"farm_id": 1, "pest_name": "Rats", "reported_area_hectares": -1},
        {"farm_id": 1, "pest_name": "Rats", "reported_area_hectares": 10000.01},
        {"farm_id": 1, "pest_name": "Rats", "reported_area_hectares": "1.234"},
        {"farm_id": 1, "pest_name": "Rats", "reported_area_hectares": "many"},
        {"farm_id": 1, "pest_name": "Rats", "reported_area_hectares": True},
        {"farm_id": 1, "pest_name": "Rats", "reported_area_hectares": None},
        {"farm_id": 1, "pest_name": "Rats", "reported_area_hectares": 1, "symptoms": "x" * 2001},
        {"farm_id": 1, "pest_name": "Rats", "reported_area_hectares": 1, "symptoms": 123},
        {"farm_id": 1, "pest_name": "Rats", "reported_area_hectares": 1, "observed_on": "20-09-2026"},
        {"farm_id": 1, "pest_name": "Rats", "reported_area_hectares": 1, "observed_on": "9999-01-01"},
        {"farm_id": 1, "pest_name": "Rats", "reported_area_hectares": 1, "observed_on": 20260920},
    ],
)
def test_create_case_invalid_payload_rejected(pest_case, payload):
    client, _, _, _ = pest_case
    token = login_admin(client)
    response = client.post(
        CASES, json=payload, headers={"Origin": ORIGIN, "X-CSRF-Token": token}
    )
    assert response.status_code == 400
    assert response.get_json()["data"] is None


def test_update_case_while_reported(pest_case):
    client, store, _, _ = pest_case
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    response = client.put(
        CASE(1),
        json={"pest_name": "Stem Borer Moth", "symptoms": None, "reported_area_hectares": 3},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["pest_case"]["pest_name"] == "Stem Borer Moth"
    assert store[1].symptoms is None
    assert client.put(CASE(9999), json={"pest_name": "X"}, headers=headers).status_code == 404
    assert client.put(CASE(1), json={}, headers=headers).status_code == 400
    assert client.put(CASE(1), json={"status": "FOR_INSPECTION"}, headers=headers).status_code == 400
    assert client.put(CASE(1), json={"pest_name": "X", "status": "REPORTED"}, headers=headers).status_code == 400
    assert store[1].status == "REPORTED"


def test_update_case_revalidates_area_against_farm(pest_case):
    client, store, _, _ = pest_case
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    # Farm 2 holds only 1.00 ha; the 2.50 ha report no longer fits there.
    response = client.put(CASE(1), json={"farm_id": 2}, headers=headers)
    assert response.status_code == 400
    assert store[1].farm_id == 1
    response = client.put(CASE(1), json={"farm_id": 2, "reported_area_hectares": 0.75}, headers=headers)
    assert response.status_code == 200
    assert store[1].farm_id == 2
    assert store[1].reported_area_hectares == Decimal("0.75")
    assert client.put(CASE(1), json={"farm_id": 9999}, headers=headers).status_code == 404


def test_update_rejected_after_submission(pest_case):
    client, _, _, _ = pest_case
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    assert client.post(SUBMIT(1), headers=headers).status_code == 200
    response = client.put(CASE(1), json={"pest_name": "Late Edit"}, headers=headers)
    assert response.status_code == 409
    assert response.get_json() == {
        "data": None,
        "message": "Only REPORTED pest cases can be edited.",
    }


def test_submit_for_inspection_transition(pest_case):
    client, store, _, locks = pest_case
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    locks_before = locks["transitions"]
    response = client.post(SUBMIT(1), headers=headers)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.get_json()["data"]["pest_case"]["status"] == "FOR_INSPECTION"
    assert store[1].status == "FOR_INSPECTION"
    assert locks["transitions"] == locks_before + 1
    assert client.get(CASES + "?status=FOR_INSPECTION").get_json()["data"]["pest_cases"] != []


def test_submit_repeated_transition_conflicts(pest_case):
    client, _, _, _ = pest_case
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    assert client.post(SUBMIT(1), headers=headers).status_code == 200
    repeated = client.post(SUBMIT(1), headers=headers)
    assert repeated.status_code == 409
    assert repeated.get_json() == {
        "data": None,
        "message": "Pest case has already been submitted for inspection.",
    }
    assert client.post(SUBMIT(9999), headers=headers).status_code == 404
    assert (
        client.post(
            SUBMIT(1), json={"status": "FOR_INSPECTION"}, headers=headers
        ).status_code
        == 400
    )


def test_pest_case_database_errors_sanitized(pest_case, monkeypatch):
    client, _, _, _ = pest_case
    login_admin(client)

    def fail_list(*_args, **_kwargs):
        raise SQLAlchemyError("internal case detail")

    monkeypatch.setattr(pest_cases_module, "list_all_pest_cases", fail_list)
    response = client.get(CASES)
    assert response.status_code == 503
    assert response.get_json() == {"data": None, "message": "Pest case service unavailable."}
    assert "internal case detail" not in response.get_data(as_text=True)

    def fail_lookup(_case_id):
        raise SQLAlchemyError("internal lookup detail")

    monkeypatch.setattr(pest_cases_module, "get_pest_case_by_id", fail_lookup)
    response = client.get(CASE(1))
    assert response.status_code == 503
    assert "internal lookup detail" not in response.get_data(as_text=True)


def test_public_serialization_leaks_nothing(pest_case):
    client, _, _, _ = pest_case
    login_admin(client)
    for response in (client.get(CASES), client.get(CASE(1))):
        assert response.status_code == 200
        raw = response.get_data(as_text=True)
        for forbidden in ("password", "password_hash", "auth_version", "csrf", "session"):
            assert forbidden not in raw


def test_no_delete_endpoints_registered(pest_case):
    client, _, _, _ = pest_case
    rules = [
        rule
        for rule in client.application.url_map.iter_rules()
        if rule.rule.startswith("/api/v1/pest-cases")
    ]
    assert rules, "Expected pest case routes to be registered."
    assert all("DELETE" not in rule.methods for rule in rules)


def test_neighboring_farmer_farm_endpoints_regressed(pest_case):
    client, _, _, _ = pest_case
    login_admin(client)
    assert client.get("/api/v1/farmers").status_code == 200
    assert client.get("/api/v1/farms").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200


def test_model_normalization_helpers():
    assert normalize_pest_name("  Asiatic   Corn\nBorer ") == "Asiatic Corn Borer"
    assert normalize_pest_name("   ") is None
    assert normalize_pest_name(None) is None
    assert normalize_symptoms("") is None
    assert normalize_symptoms(None) is None
    assert normalize_observed_on("") is None
    assert normalize_observed_on("2026-09-15") == date(2026, 9, 15)
    with pytest.raises(ValueError):
        normalize_observed_on("15/09/2026")
    with pytest.raises(ValueError):
        normalize_observed_on((date.today() + timedelta(days=1)).isoformat())
    with pytest.raises(ValueError):
        normalize_reported_area("1.234")
    with pytest.raises(ValueError):
        normalize_reported_area(0)


def test_model_relationship_and_constraints():
    assert PestCase.__table__.name == "pest_cases"
    assert {status.value for status in PestCaseStatus} == {
        "REPORTED",
        "FOR_INSPECTION",
        "INSPECTION_SCHEDULED",
        "NOT_CONFIRMED",
        "FIELD_VALIDATED",
        "UNDER_INTERVENTION",
        "FOLLOW_UP_DUE",
        "REINTERVENTION_REQUIRED",
        "CLOSED",
    }
    names = {constraint.name for constraint in PestCase.__table__.constraints}
    assert {
        "ck_pest_cases_area_positive",
        "ck_pest_cases_area_max",
        "ck_pest_cases_status",
    } <= names
    foreign_keys = [element for table in (PestCase.__table__,) for element in table.foreign_keys]
    targets = {(element.column.table.name, element.ondelete) for element in foreign_keys}
    assert ("farms", "RESTRICT") in targets
    assert ("users", "RESTRICT") in targets
    case = PestCase(
        farm_id=1,
        pest_name="Rats",
        reported_area_hectares=1,
        status="REPORTED",
        reported_by_user_id=2,
    )
    assert case.status == "REPORTED"
    with pytest.raises(ValueError):
        case.status = "INSPECTED"


class _FakeBlobStore:
    def __init__(self):
        self.objects = {}
        self.sizes = {}
        self.deleted = []

    def head_blob(self, name):
        body, content_type = self.objects[name]
        return SimpleNamespace(
            size=self.sizes.get(name, len(body)),
            content_type=content_type,
        )

    def get_blob(self, name, *, access):
        assert access == "private"
        body, content_type = self.objects[name]
        return SimpleNamespace(
            body=body,
            metadata=SimpleNamespace(size=len(body), content_type=content_type),
        )

    def delete_blob(self, name):
        self.deleted.append(name)
        self.objects.pop(name, None)


def _install_blob_evidence(monkeypatch, client):
    client.application.config["EVIDENCE_STORAGE"] = "blob"
    photo_store = _install_evidence_store(monkeypatch)
    blob_store = _FakeBlobStore()
    monkeypatch.setattr(evidence, "_blob_sdk", lambda: blob_store)
    return photo_store, blob_store


def _blob_key(case_id=1, extension="png"):
    return f"ev/{case_id}/{'a' * 32}.{extension}"


def _authorize_upload(client, token, case_id=1):
    return client.post(
        f"/api/v1/pest-cases/{case_id}/evidence-photos/upload-authorize",
        json={},
        headers=_photo_headers(token),
    )


def _finalize(client, token, photos, case_id=1):
    return client.post(
        f"/api/v1/pest-cases/{case_id}/evidence-photos/finalize",
        json={"photos": photos},
        headers=_photo_headers(token),
    )


def test_evidence_config_reports_storage_mode(pest_case):
    client, _, _, _ = pest_case
    login_technician(client)
    local = client.get(f"/api/v1/pest-cases/1/evidence-photos/config")
    assert local.status_code == 200
    local_data = local.get_json()["data"]
    assert local_data["storage"] == "local"
    assert local_data["max_photos"] == 3
    assert local_data["max_bytes"] == 5 * 1024 * 1024

    client.application.config["EVIDENCE_STORAGE"] = "blob"
    blob = client.get(f"/api/v1/pest-cases/1/evidence-photos/config")
    assert blob.status_code == 200
    assert blob.get_json()["data"]["storage"] == "blob"


def test_blob_upload_authorize_finalize_and_private_download(
    pest_case, monkeypatch
):
    client, _, _, _ = pest_case
    photo_store, blob_store = _install_blob_evidence(monkeypatch, client)
    key = _blob_key()
    blob_store.objects[key] = (PNG_BYTES, "image/png")
    token = login_technician(client)

    authorized = _authorize_upload(client, token)
    assert authorized.status_code == 200
    assert authorized.get_json()["data"]["prefix"] == "ev/1/"

    finalized = _finalize(
        client,
        token,
        [{"pathname": key, "original_filename": "../evidence.png"}],
    )
    assert finalized.status_code == 201
    assert len(photo_store) == 1
    photo = photo_store[0]
    assert photo.stored_name == key
    assert photo.original_filename == "evidence.png"
    assert photo.content_type == "image/png"
    assert photo.byte_size == len(PNG_BYTES)

    download = client.get(f"{PHOTOS(1)}/{photo.id}/authorize-download")
    assert download.status_code == 200
    data = download.get_json()["data"]
    assert data["storage"] == "blob"
    assert data["pathname"] == key
    assert "https://" not in json.dumps(download.get_json())
    assert "blob.vercel-storage.com" not in json.dumps(download.get_json())

    outsider = client.application.test_client()
    login_technician_two(outsider)
    assert (
        outsider.get(f"{PHOTOS(1)}/{photo.id}/authorize-download").status_code
        == 404
    )

    admin = client.application.test_client()
    login_admin(admin)
    assert admin.get(f"{PHOTOS(1)}/{photo.id}/authorize-download").status_code == 200


def test_blob_finalize_is_idempotent_for_recorded_object(
    pest_case, monkeypatch
):
    client, _, _, _ = pest_case
    photo_store, blob_store = _install_blob_evidence(monkeypatch, client)
    key = _blob_key()
    blob_store.objects[key] = (PNG_BYTES, "image/png")
    token = login_technician(client)
    photo = {"pathname": key, "original_filename": "evidence.png"}

    assert _finalize(client, token, [photo]).status_code == 201
    assert _finalize(client, token, [photo]).status_code == 409
    assert len(photo_store) == 1
    assert key not in blob_store.deleted


@pytest.mark.parametrize(
    ("extension", "head_type", "body", "oversized"),
    [
        ("png", "image/png", b"not an image", False),
        ("png", "image/jpeg", PNG_BYTES, False),
        ("jpg", "image/png", PNG_BYTES, False),
        ("png", "image/png", PNG_BYTES, True),
    ],
)
def test_blob_finalize_rejects_invalid_objects(
    pest_case, monkeypatch, extension, head_type, body, oversized
):
    client, _, _, _ = pest_case
    photo_store, blob_store = _install_blob_evidence(monkeypatch, client)
    key = _blob_key(extension=extension)
    blob_store.objects[key] = (body, head_type)
    if oversized:
        blob_store.sizes[key] = 5 * 1024 * 1024 + 1
    token = login_technician(client)

    response = _finalize(
        client,
        token,
        [{"pathname": key, "original_filename": "evidence.png"}],
    )
    assert response.status_code == 400
    assert photo_store == []
    assert key in blob_store.deleted


def test_blob_finalize_rejects_wrong_case_key(pest_case, monkeypatch):
    client, _, _, _ = pest_case
    photo_store, blob_store = _install_blob_evidence(monkeypatch, client)
    key = _blob_key(case_id=2)
    blob_store.objects[key] = (PNG_BYTES, "image/png")
    token = login_technician(client)

    response = _finalize(
        client,
        token,
        [{"pathname": key, "original_filename": "evidence.png"}],
    )
    assert response.status_code == 400
    assert photo_store == []


def test_blob_finalize_rejects_more_than_three(pest_case, monkeypatch):
    client, _, _, _ = pest_case
    photo_store, blob_store = _install_blob_evidence(monkeypatch, client)
    for index in range(3):
        photo_store.append(
            PestCaseEvidencePhoto(
                id=index + 1,
                pest_case_id=1,
                stored_name=f"ev/1/{'b' * 32}.png",
                original_filename="existing.png",
                content_type="image/png",
                byte_size=len(PNG_BYTES),
                uploaded_by_user_id=2,
            )
        )
    key = _blob_key()
    blob_store.objects[key] = (PNG_BYTES, "image/png")
    token = login_technician(client)

    assert _authorize_upload(client, token).status_code == 400
    response = _finalize(
        client,
        token,
        [{"pathname": key, "original_filename": "evidence.png"}],
    )
    assert response.status_code == 400
    assert len(photo_store) == 3
    assert key in blob_store.deleted


def test_blob_finalize_rejects_wrong_workflow_state(pest_case, monkeypatch):
    client, store, _, _ = pest_case
    photo_store, blob_store = _install_blob_evidence(monkeypatch, client)
    store[1].status = PestCaseStatus.FIELD_VALIDATED.value
    key = _blob_key()
    blob_store.objects[key] = (PNG_BYTES, "image/png")
    token = login_technician(client)

    response = _finalize(
        client,
        token,
        [{"pathname": key, "original_filename": "evidence.png"}],
    )
    assert response.status_code == 409
    assert photo_store == []


def test_blob_admin_can_finalize_evidence(pest_case, monkeypatch):
    client, _, _, _ = pest_case
    photo_store, blob_store = _install_blob_evidence(monkeypatch, client)
    key = _blob_key()
    blob_store.objects[key] = (PNG_BYTES, "image/png")
    token = login_admin(client)

    assert _authorize_upload(client, token).status_code == 200
    response = _finalize(
        client,
        token,
        [{"pathname": key, "original_filename": "evidence.png"}],
    )
    assert response.status_code == 201
    assert len(photo_store) == 1


def test_blob_authorization_requires_scope_and_csrf(pest_case, monkeypatch):
    client, _, _, _ = pest_case
    _install_blob_evidence(monkeypatch, client)
    token = login_technician(client)

    assert (
        client.post(
            "/api/v1/pest-cases/1/evidence-photos/upload-authorize",
            json={},
        ).status_code
        == 403
    )

    outsider = client.application.test_client()
    outsider_token = login_technician_two(outsider)
    assert _authorize_upload(outsider, outsider_token).status_code == 404

    admin = client.application.test_client()
    admin_token = login_admin(admin)
    assert _authorize_upload(admin, admin_token).status_code == 200


def test_blob_mode_disables_multipart_evidence_endpoint(pest_case, monkeypatch):
    client, _, _, _ = pest_case
    _install_blob_evidence(monkeypatch, client)
    token = login_technician(client)
    assert _upload(client, token).status_code == 409
