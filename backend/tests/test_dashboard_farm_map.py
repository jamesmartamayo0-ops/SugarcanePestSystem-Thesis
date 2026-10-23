from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app import auth, create_app
from app.dashboard_farm_map import (
    ACTIVE_CASE_PRIORITY,
    build_farm_map_projection,
)
from app.models import User
from app.routes import dashboard as dashboard_module


FARM_MAP = "/api/v1/dashboard/farm-map"


def _stamp(day: int, hour: int = 0):
    return datetime(2026, 10, day, hour, tzinfo=timezone.utc)


def _farm(
    farm_id: int = 1,
    *,
    latitude: Decimal | None = Decimal("9.591111"),
    longitude: Decimal | None = Decimal("123.122778"),
):
    return {
        "farm_id": farm_id,
        "plot_identifier": f"Plot {farm_id}",
        "barangay": "Tangculogan",
        "area_hectares": Decimal("3.00"),
        "latitude": latitude,
        "longitude": longitude,
        "farmer_id": farm_id,
        "farmer_full_name": f"Farmer {farm_id}",
    }


def _case(
    case_id: int,
    status: str,
    *,
    farm_id: int = 1,
    updated_at=None,
    reported_area: str = "1.20",
    validated_area: str | None = None,
    inspection_completed: bool = False,
):
    return {
        "case_id": case_id,
        "farm_id": farm_id,
        "pest_name": f"Pest {case_id}",
        "status": status,
        "reported_area_hectares": Decimal(reported_area),
        "updated_at": updated_at or _stamp(10),
        "validated_area_hectares": (
            Decimal(validated_area) if validated_area is not None else None
        ),
        "inspection_completed_at": _stamp(9) if inspection_completed else None,
    }


@pytest.fixture
def farm_map_app(monkeypatch):
    monkeypatch.setenv(
        "AUTH_TRUSTED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    )
    app = create_app()
    app.testing = True
    users = {}
    for user_id, role in ((1, "ADMIN"), (2, "TECHNICIAN"), (3, "ADMIN")):
        user = User(
            id=user_id,
            username=f"map.user{user_id}",
            full_name=f"Map User {user_id}",
            role=role,
            is_active=True,
            auth_version=0,
        )
        user.set_password("farm-map-password")
        users[user_id] = user
    users[3].__dict__["role"] = "OBSERVER"

    monkeypatch.setattr(auth, "get_user_by_id", users.get)
    monkeypatch.setattr(auth, "now_epoch_seconds", lambda: 1_750_000_000)
    monkeypatch.setattr(
        dashboard_module,
        "load_farm_map_projection",
        lambda: {
            "summary": {
                "mapped_farms": 0,
                "unmapped_farms": 0,
                "active_cases": 0,
                "needs_attention_cases": 0,
            },
            "farms": [],
        },
    )

    def client_for(user_id=None):
        client = app.test_client()
        if user_id is not None:
            with client.session_transaction() as session:
                session["user_id"] = user_id
                session["auth_version"] = 0
                session["issued_at"] = 1_750_000_000
                session["csrf_token"] = "a" * 64
        return client

    return app, client_for


def test_farm_map_authorization(farm_map_app):
    _, client_for = farm_map_app
    assert client_for().get(FARM_MAP).status_code == 401
    assert client_for(1).get(FARM_MAP).status_code == 200
    assert client_for(2).get(FARM_MAP).status_code == 200
    assert client_for(3).get(FARM_MAP).status_code == 403


def test_farm_map_empty_contract_and_no_store(farm_map_app):
    _, client_for = farm_map_app
    response = client_for(1).get(FARM_MAP)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.get_json() == {
        "data": {
            "summary": {
                "mapped_farms": 0,
                "unmapped_farms": 0,
                "active_cases": 0,
                "needs_attention_cases": 0,
            },
            "farms": [],
        },
        "message": "Farm monitoring map retrieved.",
    }


def test_mapped_unmapped_and_no_case_projection():
    result = build_farm_map_projection(
        [_farm(1), _farm(2, latitude=None, longitude=None)], [], []
    )
    assert result["summary"] == {
        "mapped_farms": 1,
        "unmapped_farms": 1,
        "active_cases": 0,
        "needs_attention_cases": 0,
    }
    assert result["farms"][0]["location"] == {
        "latitude": 9.591111,
        "longitude": 123.122778,
    }
    assert result["farms"][0]["area_hectares"] == 3.0
    assert result["farms"][1]["location"] is None
    for farm in result["farms"]:
        assert farm["marker_state"] == "REGISTERED_NO_CASE"
        assert farm["case"] is None
        assert farm["has_active_case"] is False
        assert farm["needs_attention"] is False


@pytest.mark.parametrize("status", list(ACTIVE_CASE_PRIORITY))
def test_single_active_case_sets_marker_state(status):
    result = build_farm_map_projection([_farm()], [_case(1, status)], [])
    farm = result["farms"][0]
    assert farm["marker_state"] == status
    assert farm["case"]["status"] == status
    assert farm["has_active_case"] is True


def test_active_case_priority_is_authoritative():
    cases = [
        _case(case_id, status, updated_at=_stamp(20 - case_id))
        for case_id, status in enumerate(ACTIVE_CASE_PRIORITY, start=1)
    ]
    result = build_farm_map_projection([_farm()], cases, [])
    assert result["farms"][0]["marker_state"] == "REINTERVENTION_REQUIRED"


def test_active_case_outranks_newer_terminal_cases():
    cases = [
        _case(1, "REPORTED", updated_at=_stamp(1)),
        _case(2, "CLOSED", updated_at=_stamp(20)),
        _case(3, "NOT_CONFIRMED", updated_at=_stamp(21)),
    ]
    result = build_farm_map_projection([_farm()], cases, [])
    assert result["farms"][0]["case"]["id"] == 1


def test_same_priority_uses_updated_at_then_id_descending():
    cases = [
        _case(1, "FIELD_VALIDATED", updated_at=_stamp(9)),
        _case(2, "FIELD_VALIDATED", updated_at=_stamp(10)),
        _case(3, "FIELD_VALIDATED", updated_at=_stamp(10)),
    ]
    result = build_farm_map_projection([_farm()], cases, [])
    assert result["farms"][0]["case"]["id"] == 3


def test_terminal_selection_uses_updated_at_then_id_descending():
    cases = [
        _case(1, "CLOSED", updated_at=_stamp(9)),
        _case(2, "NOT_CONFIRMED", updated_at=_stamp(10)),
        _case(3, "CLOSED", updated_at=_stamp(10)),
    ]
    result = build_farm_map_projection([_farm()], cases, [])
    assert result["farms"][0]["case"]["id"] == 3
    assert result["farms"][0]["marker_state"] == "CLOSED"
    assert result["farms"][0]["has_active_case"] is False


def test_validated_area_belongs_to_selected_case_and_requires_completed_inspection():
    cases = [
        _case(
            1,
            "FIELD_VALIDATED",
            validated_area="1.25",
            inspection_completed=True,
        ),
        _case(
            2,
            "REPORTED",
            validated_area="9.99",
            inspection_completed=True,
        ),
    ]
    result = build_farm_map_projection([_farm()], cases, [])
    assert result["farms"][0]["case"]["id"] == 1
    assert result["farms"][0]["case"]["validated_area_hectares"] == 1.25

    incomplete = _case(
        3,
        "NOT_CONFIRMED",
        validated_area="0.00",
        inspection_completed=False,
    )
    result = build_farm_map_projection([_farm()], [incomplete], [])
    assert result["farms"][0]["case"]["validated_area_hectares"] is None


@pytest.mark.parametrize(
    ("status", "overdue", "expected"),
    [
        ("FOR_INSPECTION", False, True),
        ("FIELD_VALIDATED", False, True),
        ("REINTERVENTION_REQUIRED", False, True),
        ("FOLLOW_UP_DUE", True, True),
        ("REPORTED", False, False),
        ("INSPECTION_SCHEDULED", False, False),
        ("UNDER_INTERVENTION", False, False),
        ("FOLLOW_UP_DUE", False, False),
    ],
)
def test_needs_attention_matches_dashboard_categories(status, overdue, expected):
    case = _case(1, status)
    result = build_farm_map_projection([_farm()], [case], [1] if overdue else [])
    assert result["farms"][0]["needs_attention"] is expected
    assert result["summary"]["needs_attention_cases"] == int(expected)


def test_farm_flags_and_summary_count_cases_not_distinct_farms():
    cases = [
        _case(1, "REINTERVENTION_REQUIRED", farm_id=1),
        _case(2, "FOR_INSPECTION", farm_id=1),
        _case(3, "CLOSED", farm_id=1),
        _case(4, "REPORTED", farm_id=2),
    ]
    result = build_farm_map_projection(
        [_farm(1), _farm(2, latitude=None, longitude=None)], cases, []
    )
    assert result["summary"] == {
        "mapped_farms": 1,
        "unmapped_farms": 1,
        "active_cases": 3,
        "needs_attention_cases": 2,
    }
    assert result["farms"][0]["marker_state"] == "REINTERVENTION_REQUIRED"
    assert result["farms"][0]["has_active_case"] is True
    assert result["farms"][0]["needs_attention"] is True


def test_farm_map_database_failure_is_safe(farm_map_app, monkeypatch):
    _, client_for = farm_map_app

    def fail():
        raise SQLAlchemyError("internal farm map database detail")

    monkeypatch.setattr(dashboard_module, "load_farm_map_projection", fail)
    response = client_for(1).get(FARM_MAP)
    assert response.status_code == 503
    assert response.get_json() == {
        "data": None,
        "message": "Dashboard service unavailable.",
    }
    assert "internal farm map database detail" not in response.get_data(as_text=True)
