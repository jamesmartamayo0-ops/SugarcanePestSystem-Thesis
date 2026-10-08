from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app import auth, create_app
from app.models import Farm, Farmer
from app.models.farm import normalize_area_hectares
from app.models.farmer import normalize_barangay, normalize_contact_number
from app.routes import farmers as farmers_module
from app.routes import farms as farms_module
from app.models import User

FARMERS = "/api/v1/farmers"
FARMER = lambda farmer_id: f"/api/v1/farmers/{farmer_id}"  # noqa: E731
FARMS = "/api/v1/farms"
FARM = lambda farm_id: f"/api/v1/farms/{farm_id}"  # noqa: E731
LOGIN = "/api/v1/auth/login"
ORIGIN = "http://localhost:3000"
ADMIN_PASSWORD = "admin-password-123"
TECH_PASSWORD = "technician-pass-123"


def _stamp():
    return datetime(2026, 10, 8, tzinfo=timezone.utc)


@pytest.fixture
def farm_case(monkeypatch):
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
    users = {admin.id: admin, technician.id: technician}
    clock = {"now": 1_750_000_000}

    farmer_store = {}
    farm_store = {}
    state = {"next_farmer_id": 1, "next_farm_id": 1}

    def seed_farmer(full_name="Juan Dela Cruz", barangay="Bunao", contact_number="09171234567"):
        farmer = Farmer(full_name=full_name, barangay=barangay, contact_number=contact_number)
        farmer.id = state["next_farmer_id"]
        state["next_farmer_id"] += 1
        farmer.created_at = _stamp()
        farmer.updated_at = _stamp()
        farmer_store[farmer.id] = farmer
        return farmer

    def seed_farm(farmer, plot="Plot A", barangay="Bunao", area="2.50"):
        farm = Farm(
            farmer_id=farmer.id, plot_identifier=plot, barangay=barangay, area_hectares=area
        )
        farm.id = state["next_farm_id"]
        state["next_farm_id"] += 1
        farm.created_at = _stamp()
        farm.updated_at = _stamp()
        farm.farmer = farmer
        farm_store[farm.id] = farm
        return farm

    first = seed_farmer()
    seed_farm(first, plot="Plot A", area="2.50")
    seed_farm(first, plot="Plot B", area="1.25")

    def by_id(user_id):
        return users.get(user_id)

    def by_username(username):
        return next((u for u in users.values() if u.username == username), None)

    # --- farmers helpers ---
    def fake_list_farmers():
        return sorted(farmer_store.values(), key=lambda f: f.id)

    def fake_get_farmer(farmer_id):
        return farmer_store.get(farmer_id)

    def fake_persist_farmer(farmer):
        farmer.id = state["next_farmer_id"]
        state["next_farmer_id"] += 1
        farmer.created_at = _stamp()
        farmer.updated_at = _stamp()
        farmer_store[farmer.id] = farmer
        return farmers_module._farmer_summary(farmer)

    # --- farms helpers ---
    def fake_list_farms(farmer_id=None):
        farms = sorted(farm_store.values(), key=lambda f: f.id)
        if farmer_id is not None:
            farms = [f for f in farms if f.farmer_id == farmer_id]
        return farms

    def fake_get_farm(farm_id):
        return farm_store.get(farm_id)

    def fake_plot_taken(farmer_id, plot_identifier, exclude_id=None):
        return any(
            f.farmer_id == farmer_id
            and f.plot_identifier == plot_identifier
            and f.id != exclude_id
            for f in farm_store.values()
        )

    def fake_persist_farm(farm):
        farm.id = state["next_farm_id"]
        state["next_farm_id"] += 1
        farm.created_at = _stamp()
        farm.updated_at = _stamp()
        farm.farmer = farmer_store[farm.farmer_id]
        farm_store[farm.id] = farm
        return farms_module._farm_public(farm)

    monkeypatch.setattr(auth, "get_user_by_id", by_id)
    monkeypatch.setattr(auth, "get_user_by_username", by_username)
    monkeypatch.setattr(auth, "save_last_login", lambda item, ts: setattr(item, "last_login_at", ts))
    monkeypatch.setattr(auth, "now_epoch_seconds", lambda: clock["now"])
    monkeypatch.setattr(farmers_module, "list_all_farmers", fake_list_farmers)
    monkeypatch.setattr(farmers_module, "get_farmer_by_id", fake_get_farmer)
    monkeypatch.setattr(farmers_module, "persist_new_farmer", fake_persist_farmer)
    monkeypatch.setattr(farmers_module, "commit_farmer_changes", lambda: None)
    monkeypatch.setattr(farms_module, "list_all_farms", fake_list_farms)
    monkeypatch.setattr(farms_module, "get_farm_by_id", fake_get_farm)
    monkeypatch.setattr(farms_module, "get_farmer_by_id", fake_get_farmer)
    monkeypatch.setattr(farms_module, "plot_taken", fake_plot_taken)
    monkeypatch.setattr(farms_module, "persist_new_farm", fake_persist_farm)
    monkeypatch.setattr(farms_module, "commit_farm_changes", lambda: None)

    return app.test_client(), farmer_store, farm_store, state


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


def test_unauthenticated_farmer_and_farm_endpoints_return_401(farm_case):
    client, _, _, _ = farm_case
    assert client.get(FARMERS).status_code == 401
    assert client.get(FARMER(1)).status_code == 401
    assert client.post(FARMERS, json={}, headers={"Origin": ORIGIN}).status_code == 401
    assert client.put(FARMER(1), json={}, headers={"Origin": ORIGIN}).status_code == 401
    assert client.get(FARMS).status_code == 401
    assert client.get(FARM(1)).status_code == 401
    assert client.post(FARMS, json={}, headers={"Origin": ORIGIN}).status_code == 401
    assert client.put(FARM(1), json={}, headers={"Origin": ORIGIN}).status_code == 401


def test_technician_can_use_farmer_and_farm_workflow(farm_case):
    client, _, _, _ = farm_case
    token = login_technician(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    assert client.get(FARMERS).status_code == 200
    assert client.get(FARMER(1)).status_code == 200
    assert client.get(FARMS).status_code == 200
    assert client.get(FARM(1)).status_code == 200
    response = client.post(
        FARMERS,
        json={"full_name": "Maria Santos", "barangay": "Taclobo", "contact_number": "09180001111"},
        headers=headers,
    )
    assert response.status_code == 201
    response = client.post(
        FARMS,
        json={"farmer_id": 1, "plot_identifier": "Plot C", "barangay": "Bunao", "area_hectares": 3},
        headers=headers,
    )
    assert response.status_code == 201


def test_unsafe_requests_require_origin_and_csrf(farm_case):
    client, _, _, _ = farm_case
    token = login_admin(client)
    payload = {"full_name": "Maria Santos", "barangay": "Taclobo"}
    assert client.post(FARMERS, json=payload).status_code == 403
    assert client.post(FARMERS, json=payload, headers={"Origin": ORIGIN}).status_code == 403
    assert (
        client.post(
            FARMERS, json=payload, headers={"Origin": ORIGIN, "X-CSRF-Token": "0" * 64}
        ).status_code
        == 403
    )
    response = client.post(
        FARMERS, json=payload, headers={"Origin": ORIGIN, "X-CSRF-Token": token}
    )
    assert response.status_code == 201


def test_farmer_list_shape_and_detail_relationship(farm_case):
    client, _, _, _ = farm_case
    login_admin(client)
    response = client.get(FARMERS)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    body = response.get_json()
    assert set(body) == {"data", "message"}
    assert len(body["data"]["farmers"]) == 1
    entry = body["data"]["farmers"][0]
    assert set(entry) == {"id", "full_name", "barangay", "contact_number", "farm_count"}
    assert entry["farm_count"] == 2

    detail = client.get(FARMER(1)).get_json()["data"]["farmer"]
    assert set(detail) == {
        "id", "full_name", "barangay", "contact_number", "farms", "created_at", "updated_at",
    }
    assert [farm["plot_identifier"] for farm in detail["farms"]] == ["Plot A", "Plot B"]
    assert detail["farms"][0]["area_hectares"] == 2.5


def test_farmer_detail_unknown_returns_404(farm_case):
    client, _, _, _ = farm_case
    login_admin(client)
    assert client.get(FARMER(9999)).status_code == 404


def test_create_farmer_trims_and_persists(farm_case):
    client, store, _, _ = farm_case
    token = login_admin(client)
    response = client.post(
        FARMERS,
        json={"full_name": "  Maria Santos  ", "barangay": "  Taclobo ", "contact_number": ""},
        headers={"Origin": ORIGIN, "X-CSRF-Token": token},
    )
    assert response.status_code == 201
    body = response.get_json()
    assert set(body["data"]["farmer"]) == {
        "id", "full_name", "barangay", "contact_number", "farm_count",
    }
    assert body["data"]["farmer"]["full_name"] == "Maria Santos"
    assert body["data"]["farmer"]["barangay"] == "Taclobo"
    assert body["data"]["farmer"]["contact_number"] is None
    assert store[body["data"]["farmer"]["id"]].full_name == "Maria Santos"


@pytest.mark.parametrize(
    "payload",
    [
        {"full_name": "Maria", "barangay": "Taclobo", "extra": 1},
        {"full_name": "Maria"},
        {"barangay": "Taclobo"},
        {"full_name": "", "barangay": "Taclobo"},
        {"full_name": "   ", "barangay": "Taclobo"},
        {"full_name": "x" * 161, "barangay": "Taclobo"},
        {"full_name": "Maria", "barangay": ""},
        {"full_name": "Maria", "barangay": "x" * 121},
        {"full_name": "Maria", "barangay": "Taclobo", "contact_number": "abc"},
        {"full_name": "Maria", "barangay": "Taclobo", "contact_number": "123"},
        {"full_name": "Maria", "barangay": "Taclobo", "contact_number": "x" * 33},
        {"full_name": "Maria", "barangay": "Taclobo", "contact_number": 12345},
        {"full_name": 123, "barangay": "Taclobo"},
    ],
)
def test_create_farmer_invalid_payload_rejected(farm_case, payload):
    client, _, _, _ = farm_case
    token = login_admin(client)
    response = client.post(
        FARMERS, json=payload, headers={"Origin": ORIGIN, "X-CSRF-Token": token}
    )
    assert response.status_code == 400
    assert response.get_json()["data"] is None


def test_update_farmer_and_unknown_farmer(farm_case):
    client, store, _, _ = farm_case
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    response = client.put(FARMER(1), json={"barangay": "Camanjac", "contact_number": None}, headers=headers)
    assert response.status_code == 200
    assert response.get_json()["data"]["farmer"]["barangay"] == "Camanjac"
    assert store[1].barangay == "Camanjac"
    assert store[1].contact_number is None
    assert client.put(FARMER(9999), json={"barangay": "Camanjac"}, headers=headers).status_code == 404
    assert client.put(FARMER(1), json={}, headers=headers).status_code == 400
    assert client.put(FARMER(1), json={"barangay": "Camanjac", "extra": 1}, headers=headers).status_code == 400
    assert client.put(FARMER(1), json={"contact_number": "bad"}, headers=headers).status_code == 400


def test_farm_list_shape_and_filter(farm_case):
    client, _, _, _ = farm_case
    login_admin(client)
    body = client.get(FARMS).get_json()
    assert len(body["data"]["farms"]) == 2
    entry = body["data"]["farms"][0]
    assert set(entry) == {
        "id", "farmer_id", "plot_identifier", "barangay",
        "area_hectares", "farmer", "created_at", "updated_at",
    }
    assert set(entry["farmer"]) == {"id", "full_name", "barangay"}
    assert entry["farmer"]["full_name"] == "Juan Dela Cruz"

    filtered = client.get(FARMS + "?farmer_id=1").get_json()
    assert len(filtered["data"]["farms"]) == 2
    assert client.get(FARMS + "?farmer_id=9999").get_json()["data"]["farms"] == []
    assert client.get(FARMS + "?farmer_id=abc").status_code == 400
    assert client.get(FARMS + "?farmer_id=-3").status_code == 400


def test_create_farm_persists_relationship(farm_case):
    client, _, farm_store, _ = farm_case
    token = login_admin(client)
    response = client.post(
        FARMS,
        json={"farmer_id": 1, "plot_identifier": "  Plot C ", "barangay": "Bunao", "area_hectares": "3.75"},
        headers={"Origin": ORIGIN, "X-CSRF-Token": token},
    )
    assert response.status_code == 201
    body = response.get_json()["data"]["farm"]
    assert body["plot_identifier"] == "Plot C"
    assert body["area_hectares"] == 3.75
    assert body["farmer"]["id"] == 1
    assert farm_store[body["id"]].farmer_id == 1


def test_create_farm_unknown_farmer_returns_404(farm_case):
    client, _, _, _ = farm_case
    token = login_admin(client)
    response = client.post(
        FARMS,
        json={"farmer_id": 9999, "plot_identifier": "Plot Z", "barangay": "Bunao", "area_hectares": 1},
        headers={"Origin": ORIGIN, "X-CSRF-Token": token},
    )
    assert response.status_code == 404
    assert response.get_json() == {"data": None, "message": "Farmer not found."}


def test_create_farm_duplicate_plot_conflict(farm_case):
    client, _, _, _ = farm_case
    token = login_admin(client)
    response = client.post(
        FARMS,
        json={"farmer_id": 1, "plot_identifier": "Plot A", "barangay": "Bunao", "area_hectares": 1},
        headers={"Origin": ORIGIN, "X-CSRF-Token": token},
    )
    assert response.status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        {"farmer_id": 1, "plot_identifier": "Plot Z", "barangay": "Bunao"},
        {"farmer_id": 1, "plot_identifier": "Plot Z", "barangay": "Bunao", "area_hectares": 1, "extra": 1},
        {"farmer_id": "1", "plot_identifier": "Plot Z", "barangay": "Bunao", "area_hectares": 1},
        {"farmer_id": True, "plot_identifier": "Plot Z", "barangay": "Bunao", "area_hectares": 1},
        {"farmer_id": 1, "plot_identifier": "", "barangay": "Bunao", "area_hectares": 1},
        {"farmer_id": 1, "plot_identifier": "x" * 121, "barangay": "Bunao", "area_hectares": 1},
        {"farmer_id": 1, "plot_identifier": "Plot Z", "barangay": "", "area_hectares": 1},
        {"farmer_id": 1, "plot_identifier": "Plot Z", "barangay": "Bunao", "area_hectares": 0},
        {"farmer_id": 1, "plot_identifier": "Plot Z", "barangay": "Bunao", "area_hectares": -2},
        {"farmer_id": 1, "plot_identifier": "Plot Z", "barangay": "Bunao", "area_hectares": 10000.01},
        {"farmer_id": 1, "plot_identifier": "Plot Z", "barangay": "Bunao", "area_hectares": "1.234"},
        {"farmer_id": 1, "plot_identifier": "Plot Z", "barangay": "Bunao", "area_hectares": "many"},
        {"farmer_id": 1, "plot_identifier": "Plot Z", "barangay": "Bunao", "area_hectares": True},
        {"farmer_id": 1, "plot_identifier": "Plot Z", "barangay": "Bunao", "area_hectares": None},
    ],
)
def test_create_farm_invalid_payload_rejected(farm_case, payload):
    client, _, _, _ = farm_case
    token = login_admin(client)
    response = client.post(
        FARMS, json=payload, headers={"Origin": ORIGIN, "X-CSRF-Token": token}
    )
    assert response.status_code == 400


def test_update_farm_and_farmer_id_immutable(farm_case):
    client, _, farm_store, _ = farm_case
    token = login_admin(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
    response = client.put(FARM(1), json={"area_hectares": 4.5, "barangay": "Camanjac"}, headers=headers)
    assert response.status_code == 200
    assert response.get_json()["data"]["farm"]["area_hectares"] == 4.5
    assert farm_store[1].area_hectares == Decimal("4.50")

    # farmer_id cannot be changed through the update endpoint.
    assert client.put(FARM(1), json={"farmer_id": 2}, headers=headers).status_code == 400
    assert farm_store[1].farmer_id == 1
    # Renaming to a sibling plot conflicts.
    assert client.put(FARM(1), json={"plot_identifier": "Plot B"}, headers=headers).status_code == 409
    # Unknown farm.
    assert client.put(FARM(9999), json={"barangay": "X"}, headers=headers).status_code == 404
    # Empty and invalid payloads.
    assert client.put(FARM(1), json={}, headers=headers).status_code == 400
    assert client.put(FARM(1), json={"area_hectares": 0}, headers=headers).status_code == 400


def test_farmer_and_farm_database_errors_sanitized(farm_case, monkeypatch):
    client, _, _, _ = farm_case
    login_admin(client)

    def fail_farmers():
        raise SQLAlchemyError("internal farmer detail")

    monkeypatch.setattr(farmers_module, "list_all_farmers", fail_farmers)
    response = client.get(FARMERS)
    assert response.status_code == 503
    assert response.get_json() == {"data": None, "message": "Farmer service unavailable."}
    assert "internal farmer detail" not in response.get_data(as_text=True)

    def fail_farms(_farmer_id=None):
        raise SQLAlchemyError("internal farm detail")

    monkeypatch.setattr(farms_module, "list_all_farms", fail_farms)
    response = client.get(FARMS)
    assert response.status_code == 503
    assert response.get_json() == {"data": None, "message": "Farm service unavailable."}
    assert "internal farm detail" not in response.get_data(as_text=True)


def test_no_delete_endpoints_registered(farm_case):
    client, _, _, _ = farm_case
    rules = [
        rule for rule in client.application.url_map.iter_rules()
        if rule.rule.startswith("/api/v1/farmers") or rule.rule.startswith("/api/v1/farms")
    ]
    assert rules, "Expected farmer/farm routes to be registered."
    assert all("DELETE" not in rule.methods for rule in rules)


def test_model_normalization_helpers():
    assert normalize_contact_number("") is None
    assert normalize_contact_number("  ") is None
    assert normalize_contact_number(None) is None
    assert normalize_contact_number("0917 123 4567") == "0917 123 4567"
    with pytest.raises(ValueError):
        normalize_contact_number("abc")
    with pytest.raises(ValueError):
        normalize_contact_number("123")
    with pytest.raises(ValueError):
        normalize_barangay("   ")
    assert normalize_area_hectares("2.5") == Decimal("2.50")
    assert normalize_area_hectares(3) == Decimal("3.00")
    for bad in ("0", "-1", "10000.01", "1.234", "many", "", True, None, float("nan")):
        with pytest.raises(ValueError):
            normalize_area_hectares(bad)


def test_model_relationship_and_constraints():
    assert Farmer.__table__.name == "farmers"
    assert Farm.__table__.name == "farms"
    names = {constraint.name for constraint in Farm.__table__.constraints}
    assert {"uq_farms_farmer_plot", "ck_farms_area_positive", "ck_farms_area_max"} <= names
    fk = next(
        constraint
        for constraint in Farm.__table__.constraints
        if getattr(constraint, "elements", None)
    )
    assert fk.ondelete == "RESTRICT"
    assert Farmer.farms.property.back_populates == "farmer"
    assert "delete" not in Farmer.farms.property.cascade
    farmer = Farmer(full_name="Juan", barangay="Bunao")
    assert farmer.farms == []
