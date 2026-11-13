"""End-to-end technician confidentiality checks against real PostgreSQL.

The dataset deliberately gives Technician A and Technician B one complete,
disjoint operational chain each. Every read path is exercised through the HTTP
API so the tests verify backend authorization rather than frontend hiding.
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, text

from app.extensions import db
from app.models import (
    Farm,
    Farmer,
    FollowUp,
    Inspection,
    Intervention,
    PestCase,
    User,
    UserRole,
)
from app.models.intervention import manila_today


CASES = "/api/v1/pest-cases"
FARMERS = "/api/v1/farmers"
FARMS = "/api/v1/farms"
INSPECTIONS = "/api/v1/inspections"
INTERVENTIONS = "/api/v1/interventions"
ELIGIBLE = "/api/v1/interventions/eligible-cases"
FOLLOW_UPS = "/api/v1/follow-ups"
DASHBOARD = "/api/v1/dashboard/summary"
FARM_MAP = "/api/v1/dashboard/farm-map"
REPORTS = "/api/v1/reports/operational"
TEST_PASSWORD = "Integration-Test-Only-Password-123!"


def _login(client, username):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.status_code == 200
    return response


@pytest.fixture(scope="module")
def privacy_env(integration_app):
    suffix = uuid4().hex
    ids = {
        "users": [],
        "farmers": [],
        "farms": [],
        "cases": [],
        "inspections": [],
        "interventions": [],
        "follow_ups": [],
    }
    names = {
        "admin": f"itest_privacy_admin_{suffix}",
        "tech_a": f"itest_privacy_tech_a_{suffix}",
        "tech_b": f"itest_privacy_tech_b_{suffix}",
    }

    with integration_app.app_context():
        assert (
            db.session.scalar(text("SELECT current_database()"))
            == "sugarcane_pest_test"
        )
        users = {}
        for key, role in (
            ("admin", UserRole.ADMIN),
            ("tech_a", UserRole.TECHNICIAN),
            ("tech_b", UserRole.TECHNICIAN),
        ):
            user = User(
                username=names[key],
                full_name=f"Privacy {key.replace('_', ' ').title()}",
                role=role,
                is_active=True,
            )
            user.set_password(TEST_PASSWORD)
            db.session.add(user)
            db.session.flush()
            users[key] = user.id
            ids["users"].append(user.id)

        today = manila_today()
        now = datetime.now(timezone.utc)

        def seed_chain(label, technician_id, latitude, longitude):
            farmer = Farmer(
                full_name=f"itest_privacy_farmer_{label}_{suffix}",
                barangay="Tangculogan",
                contact_number="09170000000",
            )
            db.session.add(farmer)
            db.session.flush()
            ids["farmers"].append(farmer.id)

            farm = Farm(
                farmer_id=farmer.id,
                plot_identifier=f"itest_privacy_plot_{label}_{suffix}",
                barangay="Tangculogan",
                area_hectares=Decimal("3.00"),
                latitude=Decimal(latitude),
                longitude=Decimal(longitude),
            )
            db.session.add(farm)
            db.session.flush()
            ids["farms"].append(farm.id)

            case = PestCase(
                farm_id=farm.id,
                pest_name=f"itest_privacy_pest_{label}_{suffix}",
                symptoms=f"itest_privacy_symptoms_{label}_{suffix}",
                observed_on=today,
                reported_area_hectares=Decimal("1.00"),
                status="CLOSED",
                reported_by_user_id=users["admin"],
            )
            db.session.add(case)
            db.session.flush()
            ids["cases"].append(case.id)

            inspection = Inspection(
                pest_case_id=case.id,
                scheduled_for=today,
                assigned_to_user_id=technician_id,
                scheduled_by_user_id=users["admin"],
                inspected_on=today,
                findings=f"itest_privacy_findings_{label}_{suffix}",
                pest_confirmed=True,
                validated_area_hectares=Decimal("1.00"),
                completed_by_user_id=technician_id,
                completed_at=now,
            )
            db.session.add(inspection)
            db.session.flush()
            ids["inspections"].append(inspection.id)

            intervention = Intervention(
                pest_case_id=case.id,
                method_category="CULTURAL",
                method_description=f"itest_privacy_intervention_{label}_{suffix}",
                scheduled_for=today,
                assigned_to_user_id=technician_id,
                created_by_user_id=users["admin"],
                performed_on=today,
                completion_notes=f"itest_privacy_completion_{label}_{suffix}",
                follow_up_due_on=today,
                completed_by_user_id=technician_id,
                completed_at=now,
            )
            db.session.add(intervention)
            db.session.flush()
            ids["interventions"].append(intervention.id)

            follow_up = FollowUp(
                intervention_id=intervention.id,
                observed_on=today,
                pest_observed=False,
                observed_affected_area_hectares=Decimal("0.00"),
                assessment_notes=f"itest_privacy_follow_up_{label}_{suffix}",
                outcome="RESOLVED",
                recorded_by_user_id=technician_id,
            )
            db.session.add(follow_up)
            db.session.flush()
            ids["follow_ups"].append(follow_up.id)

            return {
                "farmer_id": farmer.id,
                "farm_id": farm.id,
                "case_id": case.id,
                "inspection_id": inspection.id,
                "intervention_id": intervention.id,
                "follow_up_id": follow_up.id,
                "pest_name": case.pest_name,
                "farmer_name": farmer.full_name,
                "plot_identifier": farm.plot_identifier,
                "symptoms": case.symptoms,
            }

        chain_a = seed_chain("a", users["tech_a"], "9.600001", "123.100001")
        chain_b = seed_chain("b", users["tech_b"], "9.700002", "123.200002")
        db.session.commit()
        db.session.remove()

    env = {
        "app": integration_app,
        "names": names,
        "ids": ids,
        "a": chain_a,
        "b": chain_b,
    }
    yield env

    with integration_app.app_context():
        db.session.rollback()
        assert (
            db.session.scalar(text("SELECT current_database()"))
            == "sugarcane_pest_test"
        )
        if ids["follow_ups"]:
            db.session.execute(
                delete(FollowUp).where(FollowUp.id.in_(ids["follow_ups"]))
            )
        if ids["interventions"]:
            db.session.execute(
                delete(Intervention).where(Intervention.id.in_(ids["interventions"]))
            )
        if ids["inspections"]:
            db.session.execute(
                delete(Inspection).where(Inspection.id.in_(ids["inspections"]))
            )
        if ids["cases"]:
            db.session.execute(delete(PestCase).where(PestCase.id.in_(ids["cases"])))
        if ids["farms"]:
            db.session.execute(delete(Farm).where(Farm.id.in_(ids["farms"])))
        if ids["farmers"]:
            db.session.execute(delete(Farmer).where(Farmer.id.in_(ids["farmers"])))
        if ids["users"]:
            db.session.execute(
                delete(User).where(
                    User.id.in_(ids["users"]),
                    User.username.like("itest_privacy_%"),
                )
            )
        db.session.commit()
        db.session.remove()


def _client_for(env, role):
    client = env["app"].test_client()
    _login(client, env["names"][role])
    return client


def _ids(entries):
    return {entry["id"] for entry in entries}


DENIED = {"data": None, "message": "Permission denied."}


def _assert_denied(response):
    assert response.status_code == 403
    assert response.get_json() == DENIED


def _initial_report(inspection_id):
    return f"{INSPECTIONS}/{inspection_id}/initial-report"


def test_admin_retains_office_wide_access(privacy_env):
    client = _client_for(privacy_env, "admin")
    a = privacy_env["a"]
    b = privacy_env["b"]

    cases = client.get(CASES).get_json()["data"]["pest_cases"]
    case_ids = _ids(cases)
    assert {a["case_id"], b["case_id"]} <= case_ids
    assert client.get(f"{CASES}/{a['case_id']}").status_code == 200
    assert client.get(f"{CASES}/{b['case_id']}").status_code == 200

    farmers = _ids(client.get(FARMERS).get_json()["data"]["farmers"])
    assert {a["farmer_id"], b["farmer_id"]} <= farmers
    assert client.get(f"{FARMERS}/{a['farmer_id']}").status_code == 200
    assert client.get(f"{FARMERS}/{b['farmer_id']}").status_code == 200

    farms = _ids(client.get(FARMS).get_json()["data"]["farms"])
    assert {a["farm_id"], b["farm_id"]} <= farms
    assert client.get(f"{FARMS}/{a['farm_id']}").status_code == 200
    assert client.get(f"{FARMS}/{b['farm_id']}").status_code == 200

    inspections = _ids(client.get(INSPECTIONS).get_json()["data"]["inspections"])
    assert {a["inspection_id"], b["inspection_id"]} <= inspections
    assert client.get(f"{INSPECTIONS}/{b['inspection_id']}").status_code == 200

    interventions = _ids(
        client.get(INTERVENTIONS).get_json()["data"]["interventions"]
    )
    assert {a["intervention_id"], b["intervention_id"]} <= interventions
    assert client.get(f"{INTERVENTIONS}/{b['intervention_id']}").status_code == 200

    follow_ups = _ids(client.get(FOLLOW_UPS).get_json()["data"]["follow_ups"])
    assert {a["follow_up_id"], b["follow_up_id"]} <= follow_ups
    assert client.get(f"{FOLLOW_UPS}/{b['follow_up_id']}").status_code == 200

    farm_map = client.get(FARM_MAP).get_json()["data"]
    map_farms = {farm["id"]: farm for farm in farm_map["farms"]}
    assert map_farms[a["farm_id"]]["location"] is not None
    assert map_farms[b["farm_id"]]["location"] is not None


def test_technician_a_reads_assigned_case_only_through_its_inspection(privacy_env):
    client = _client_for(privacy_env, "tech_a")
    a = privacy_env["a"]
    b = privacy_env["b"]

    # Pest Case Records are ADMIN-only, even for the technician's own case.
    _assert_denied(client.get(CASES))
    _assert_denied(client.get(f"{CASES}/{a['case_id']}"))
    _assert_denied(client.get(f"{CASES}/{b['case_id']}"))
    _assert_denied(client.get(f"{CASES}/{a['case_id']}/timeline"))
    _assert_denied(client.get(f"{CASES}/{b['case_id']}/timeline"))

    # The assigned inspection carries the scoped case context instead.
    report = client.get(_initial_report(a["inspection_id"]))
    assert report.status_code == 200
    body = report.get_json()["data"]["initial_report"]
    assert body["id"] == a["case_id"]
    assert body["pest_name"] == a["pest_name"]
    assert body["symptoms"] == a["symptoms"]
    assert body["evidence_photos"] == []
    detail = client.get(f"{INSPECTIONS}/{a['inspection_id']}").get_json()["data"]["inspection"]
    assert detail["pest_case"]["farm"]["plot_identifier"] == a["plot_identifier"]
    assert detail["pest_case"]["farm"]["farmer"]["full_name"] == a["farmer_name"]

    unrelated = client.get(_initial_report(b["inspection_id"]))
    assert unrelated.status_code == 404
    assert b["symptoms"] not in unrelated.get_data(as_text=True)


def test_technician_a_cannot_directly_open_unrelated_records(privacy_env):
    client = _client_for(privacy_env, "tech_a")
    b = privacy_env["b"]

    _assert_denied(client.get(f"{FARMERS}/{b['farmer_id']}"))
    _assert_denied(client.get(f"{FARMS}/{b['farm_id']}"))
    assert client.get(f"{INSPECTIONS}/{b['inspection_id']}").status_code == 404
    assert client.get(_initial_report(b["inspection_id"])).status_code == 404
    assert client.get(f"{INTERVENTIONS}/{b['intervention_id']}").status_code == 404
    assert client.get(f"{FOLLOW_UPS}/{b['follow_up_id']}").status_code == 404


def test_technician_a_lists_hide_unrelated_records(privacy_env):
    client = _client_for(privacy_env, "tech_a")
    a = privacy_env["a"]
    b = privacy_env["b"]

    # Farmer and Farm Records are ADMIN-only, including the technician's own.
    _assert_denied(client.get(FARMERS))
    _assert_denied(client.get(f"{FARMERS}/{a['farmer_id']}"))
    _assert_denied(client.get(FARMS))
    _assert_denied(client.get(f"{FARMS}/{a['farm_id']}"))

    inspections = client.get(INSPECTIONS).get_json()["data"]["inspections"]
    assert [item["id"] for item in inspections] == [a["inspection_id"]]

    interventions = client.get(INTERVENTIONS).get_json()["data"]["interventions"]
    assert [item["id"] for item in interventions] == [a["intervention_id"]]

    follow_ups = client.get(FOLLOW_UPS).get_json()["data"]["follow_ups"]
    assert [item["id"] for item in follow_ups] == [a["follow_up_id"]]

    # Filters cannot widen the scope or reopen the administration lists.
    _assert_denied(client.get(f"{CASES}?farm_id={b['farm_id']}"))
    _assert_denied(client.get(f"{CASES}?farmer_id={b['farmer_id']}"))
    _assert_denied(client.get(f"{FARMS}?farmer_id={b['farmer_id']}"))
    assert client.get(f"{INSPECTIONS}?pest_case_id={b['case_id']}").get_json()[
        "data"
    ]["inspections"] == []
    assert client.get(f"{INSPECTIONS}?assigned_to_user_id=0").status_code == 400


def test_intervention_eligible_cases_are_scoped(privacy_env):
    a = privacy_env["a"]
    b = privacy_env["b"]
    ours = {a["case_id"], b["case_id"]}
    app = privacy_env["app"]

    def set_status(status):
        with app.app_context():
            assert (
                db.session.scalar(text("SELECT current_database()"))
                == "sugarcane_pest_test"
            )
            db.session.execute(
                PestCase.__table__.update()
                .where(PestCase.id.in_(list(ours)))
                .values(status=status)
            )
            db.session.commit()
            db.session.remove()

    set_status("FIELD_VALIDATED")
    try:
        tech_a = _client_for(privacy_env, "tech_a")
        eligible = tech_a.get(ELIGIBLE)
        assert eligible.status_code == 200
        assert _ids(eligible.get_json()["data"]["pest_cases"]) == {a["case_id"]}
        assert b["pest_name"] not in eligible.get_data(as_text=True)

        tech_b = _client_for(privacy_env, "tech_b")
        assert _ids(tech_b.get(ELIGIBLE).get_json()["data"]["pest_cases"]) == {
            b["case_id"]
        }

        admin = _client_for(privacy_env, "admin")
        assert ours <= _ids(admin.get(ELIGIBLE).get_json()["data"]["pest_cases"])
    finally:
        set_status("CLOSED")


def test_technician_a_search_cannot_reveal_case_b(privacy_env):
    client = _client_for(privacy_env, "tech_a")
    b = privacy_env["b"]

    for query in (
        b["pest_name"],
        b["farmer_name"],
        b["plot_identifier"],
        str(b["case_id"]),
    ):
        response = client.get(CASES, query_string={"q": query})
        _assert_denied(response)
        assert b["pest_name"] not in response.get_data(as_text=True)

    admin = _client_for(privacy_env, "admin")
    found = admin.get(CASES, query_string={"q": b["pest_name"]}).get_json()["data"][
        "pest_cases"
    ]
    assert [case["id"] for case in found] == [b["case_id"]]


def test_technician_a_dashboard_and_reports_are_scoped(privacy_env):
    client = _client_for(privacy_env, "tech_a")
    a = privacy_env["a"]
    b = privacy_env["b"]

    dashboard = client.get(DASHBOARD).get_json()["data"]["summary"]
    assert dashboard["totals"] == {"farmers": 1, "farms": 1, "pest_cases": 1}
    assert dashboard["by_status"]["CLOSED"] == 1
    assert {case["id"] for case in dashboard["recent_cases"]} == {a["case_id"]}
    assert b["case_id"] not in {case["id"] for case in dashboard["recent_cases"]}

    report = client.get(REPORTS).get_json()["data"]["report"]
    assert report["summary"]["total_cases"] == 1
    assert report["summary"]["closed_cases"] == 1
    assert [row["case_id"] for row in report["cases"]] == [a["case_id"]]
    assert b["case_id"] not in {row["case_id"] for row in report["cases"]}

    filtered = client.get(
        REPORTS, query_string={"farm_id": b["farm_id"]}
    ).get_json()["data"]["report"]
    assert filtered["summary"]["total_cases"] == 0
    assert filtered["cases"] == []


def test_technician_a_farm_map_excludes_farm_b_coordinates(privacy_env):
    client = _client_for(privacy_env, "tech_a")
    a = privacy_env["a"]
    b = privacy_env["b"]

    response = client.get(FARM_MAP)
    assert response.status_code == 200
    raw = response.get_data(as_text=True)
    body = response.get_json()["data"]
    farms = {farm["id"]: farm for farm in body["farms"]}

    assert set(farms) == {a["farm_id"]}
    assert farms[a["farm_id"]]["location"] == {
        "latitude": 9.600001,
        "longitude": 123.100001,
    }
    assert b["farm_id"] not in farms
    assert b["plot_identifier"] not in raw
    assert "9.700002" not in raw
    assert "123.200002" not in raw


def test_technician_b_has_equivalent_isolation(privacy_env):
    client = _client_for(privacy_env, "tech_b")
    a = privacy_env["a"]
    b = privacy_env["b"]

    _assert_denied(client.get(CASES))
    _assert_denied(client.get(f"{CASES}/{b['case_id']}"))
    _assert_denied(client.get(f"{CASES}/{a['case_id']}"))
    _assert_denied(client.get(FARMERS))
    _assert_denied(client.get(f"{FARMERS}/{a['farmer_id']}"))
    _assert_denied(client.get(FARMS))
    _assert_denied(client.get(f"{FARMS}/{a['farm_id']}"))
    own_report = client.get(_initial_report(b["inspection_id"]))
    assert own_report.status_code == 200
    assert own_report.get_json()["data"]["initial_report"]["id"] == b["case_id"]
    assert client.get(_initial_report(a["inspection_id"])).status_code == 404
    assert client.get(f"{INSPECTIONS}/{a['inspection_id']}").status_code == 404
    assert client.get(f"{INTERVENTIONS}/{a['intervention_id']}").status_code == 404
    assert client.get(f"{FOLLOW_UPS}/{a['follow_up_id']}").status_code == 404

    dashboard = client.get(DASHBOARD).get_json()["data"]["summary"]
    assert dashboard["totals"] == {"farmers": 1, "farms": 1, "pest_cases": 1}
    assert {case["id"] for case in dashboard["recent_cases"]} == {b["case_id"]}
    report = client.get(REPORTS).get_json()["data"]["report"]
    assert [row["case_id"] for row in report["cases"]] == [b["case_id"]]

    farm_map = client.get(FARM_MAP).get_json()["data"]
    map_farms = {farm["id"]: farm for farm in farm_map["farms"]}
    assert set(map_farms) == {b["farm_id"]}
    assert map_farms[b["farm_id"]]["location"] == {
        "latitude": 9.700002,
        "longitude": 123.200002,
    }
