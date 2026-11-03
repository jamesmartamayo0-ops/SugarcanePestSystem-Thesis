"""ADMIN supervisory override across two independent technician chains.

These tests deliberately use the HTTP API against the guarded PostgreSQL test
database. ADMIN may perform technician-like work on either chain, while each
TECHNICIAN remains confined to their assigned records. ADMIN actions must not
silently reassign the work or change the actor's role.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text

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
from app.models.inspection import manila_today

CASES = "/api/v1/pest-cases"
FARMERS = "/api/v1/farmers"
FARMS = "/api/v1/farms"
INSPECTIONS = "/api/v1/inspections"
INTERVENTIONS = "/api/v1/interventions"
DASHBOARD = "/api/v1/dashboard/summary"
FARM_MAP = "/api/v1/dashboard/farm-map"
REPORTS = "/api/v1/reports/operational"
ADMIN_USERS = "/api/v1/admin/users"
LOGIN = "/api/v1/auth/login"
ORIGIN = "http://localhost:3000"
TEST_PASSWORD = "Integration-Test-Only-Password-123!"

STATUS_BY_KIND = {
    "inspection_scheduled": "INSPECTION_SCHEDULED",
    "under_intervention": "UNDER_INTERVENTION",
    "follow_up_due": "FOLLOW_UP_DUE",
    "field_validated": "FIELD_VALIDATED",
    "for_inspection": "FOR_INSPECTION",
    "reported": "REPORTED",
}


@pytest.fixture(scope="module")
def override_env(integration_app):
    suffix = uuid4().hex
    today = manila_today()
    now = datetime.now(timezone.utc)
    ids = {
        "users": [],
        "farmers": [],
        "farms": [],
        "cases": [],
        "inspections": [],
        "interventions": [],
    }
    names = {
        "admin": f"itest_override_admin_{suffix}",
        "tech_a": f"itest_override_tech_a_{suffix}",
        "tech_b": f"itest_override_tech_b_{suffix}",
    }

    with integration_app.app_context():
        assert db.session.scalar(text("SELECT current_database()")) == "sugarcane_pest_test"
        users = {}
        for key, role in (
            ("admin", UserRole.ADMIN),
            ("tech_a", UserRole.TECHNICIAN),
            ("tech_b", UserRole.TECHNICIAN),
        ):
            user = User(
                username=names[key],
                full_name=f"Override {key.replace('_', ' ').title()} {suffix[:8]}",
                role=role,
                is_active=True,
            )
            user.set_password(TEST_PASSWORD)
            db.session.add(user)
            db.session.flush()
            users[key] = user.id
            ids["users"].append(user.id)

        farmers = {}
        farms = {}
        for key in ("a", "b"):
            farmer = Farmer(
                full_name=f"itest_override_farmer_{key}_{suffix}",
                barangay="Tangculogan",
                contact_number="09170000000",
            )
            db.session.add(farmer)
            db.session.flush()
            ids["farmers"].append(farmer.id)
            farmers[key] = farmer.id

            farm = Farm(
                farmer_id=farmer.id,
                plot_identifier=f"itest_override_plot_{key}_{suffix}",
                barangay="Tangculogan",
                area_hectares=Decimal("4.00"),
                latitude=Decimal("9.60" if key == "a" else "9.70"),
                longitude=Decimal("123.10" if key == "a" else "123.20"),
            )
            db.session.add(farm)
            db.session.flush()
            ids["farms"].append(farm.id)
            farms[key] = farm.id

        db.session.commit()
        db.session.remove()

    def make_case(
        kind: str,
        chain: str,
        *,
        reporter: str | None = None,
        technician: str | None = None,
        label: str | None = None,
        isolated_farm: bool = False,
    ) -> dict:
        """Create one operational record with the workflow state needed by a test."""
        if kind not in STATUS_BY_KIND:
            raise AssertionError(f"Unsupported case kind: {kind}")
        chain = chain.lower()
        assert chain in ("a", "b")
        tech_key = technician or f"tech_{chain}"
        reporter_key = reporter or "admin"
        tag = label or kind
        with integration_app.app_context():
            assert (
                db.session.scalar(text("SELECT current_database()"))
                == "sugarcane_pest_test"
            )
            farm_id = farms[chain]
            farmer_id = farmers[chain]
            if isolated_farm:
                isolated_suffix = uuid4().hex
                farmer = Farmer(
                    full_name=f"itest_override_isolated_farmer_{chain}_{isolated_suffix}",
                    barangay="Tangculogan",
                    contact_number="09170000000",
                )
                db.session.add(farmer)
                db.session.flush()
                ids["farmers"].append(farmer.id)
                farmer_id = farmer.id
                farm = Farm(
                    farmer_id=farmer.id,
                    plot_identifier=f"itest_override_isolated_plot_{chain}_{isolated_suffix}",
                    barangay="Tangculogan",
                    area_hectares=Decimal("4.00"),
                )
                db.session.add(farm)
                db.session.flush()
                ids["farms"].append(farm.id)
                farm_id = farm.id

            case = PestCase(
                farm_id=farm_id,
                pest_name=f"itest_override_{tag}_{chain}_{uuid4().hex}",
                symptoms="Synthetic admin-override test record.",
                observed_on=today,
                reported_area_hectares=Decimal("1.00"),
                status=STATUS_BY_KIND[kind],
                reported_by_user_id=users[reporter_key],
            )
            db.session.add(case)
            db.session.flush()
            ids["cases"].append(case.id)

            inspection_id = None
            intervention_id = None
            if kind in ("inspection_scheduled", "field_validated"):
                completed = kind == "field_validated"
                inspection = Inspection(
                    pest_case_id=case.id,
                    scheduled_for=today,
                    assigned_to_user_id=users[tech_key],
                    scheduled_by_user_id=users["admin"],
                    inspected_on=today if completed else None,
                    findings="Synthetic inspection findings." if completed else None,
                    pest_confirmed=True if completed else None,
                    validated_area_hectares=Decimal("1.00") if completed else None,
                    completed_by_user_id=users[tech_key] if completed else None,
                    completed_at=now if completed else None,
                )
                db.session.add(inspection)
                db.session.flush()
                ids["inspections"].append(inspection.id)
                inspection_id = inspection.id
            elif kind in ("under_intervention", "follow_up_due"):
                completed = kind == "follow_up_due"
                intervention = Intervention(
                    pest_case_id=case.id,
                    method_category="CULTURAL",
                    method_description="Synthetic intervention planned for override tests.",
                    scheduled_for=today,
                    assigned_to_user_id=users[tech_key],
                    created_by_user_id=users["admin"],
                    performed_on=today if completed else None,
                    completion_notes="Synthetic completion notes." if completed else None,
                    follow_up_due_on=today + timedelta(days=7),
                    completed_by_user_id=users[tech_key] if completed else None,
                    completed_at=now if completed else None,
                )
                db.session.add(intervention)
                db.session.flush()
                ids["interventions"].append(intervention.id)
                intervention_id = intervention.id

            db.session.commit()
            result = {
                "case_id": case.id,
                "inspection_id": inspection_id,
                "intervention_id": intervention_id,
                "farm_id": farm_id,
                "farmer_id": farmer_id,
                "pest_name": case.pest_name,
            }
            db.session.remove()
            return result

    env = {
        "app": integration_app,
        "names": names,
        "ids": ids,
        "users": users,
        "farms": farms,
        "farmers": farmers,
        "today": today,
        "now": now,
        "make_case": make_case,
    }
    yield env

    with integration_app.app_context():
        db.session.rollback()
        assert db.session.scalar(text("SELECT current_database()")) == "sugarcane_pest_test"
        case_ids = list(ids["cases"])
        if case_ids:
            intervention_ids = list(
                db.session.scalars(
                    select(Intervention.id).where(
                        Intervention.pest_case_id.in_(case_ids)
                    )
                )
            )
            if intervention_ids:
                db.session.execute(
                    delete(FollowUp).where(
                        FollowUp.intervention_id.in_(intervention_ids)
                    )
                )
            db.session.execute(
                delete(Intervention).where(Intervention.pest_case_id.in_(case_ids))
            )
            db.session.execute(
                delete(Inspection).where(Inspection.pest_case_id.in_(case_ids))
            )
            db.session.execute(delete(PestCase).where(PestCase.id.in_(case_ids)))
        if ids["farms"]:
            db.session.execute(delete(Farm).where(Farm.id.in_(ids["farms"])))
        if ids["farmers"]:
            db.session.execute(delete(Farmer).where(Farmer.id.in_(ids["farmers"])))
        if ids["users"]:
            db.session.execute(
                delete(User).where(
                    User.id.in_(ids["users"]),
                    User.username.like("itest_override_%"),
                )
            )
        db.session.commit()
        db.session.remove()


def _client(env, role: str):
    client = env["app"].test_client()
    response = client.post(
        LOGIN,
        json={"username": env["names"][role], "password": TEST_PASSWORD},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 200
    token = response.get_json()["data"]["csrf_token"]
    return client, {"Origin": ORIGIN, "X-CSRF-Token": token}


def _row(env, model, row_id):
    with env["app"].app_context():
        db.session.remove()
        row = db.session.get(model, row_id)
        if row is None:
            db.session.remove()
            return None
        data = {column.name: getattr(row, column.name) for column in model.__table__.columns}
        db.session.remove()
        return data


def _follow_up(env, intervention_id):
    with env["app"].app_context():
        db.session.remove()
        row = db.session.scalar(
            select(FollowUp).where(FollowUp.intervention_id == intervention_id)
        )
        if row is None:
            db.session.remove()
            return None
        data = {column.name: getattr(row, column.name) for column in FollowUp.__table__.columns}
        db.session.remove()
        return data


def _findings_payload(env):
    return {
        "findings": "ADMIN supervisory field finding.",
        "pest_confirmed": True,
        "validated_area_hectares": "1.00",
        "inspected_on": env["today"].isoformat(),
    }


def test_admin_reads_and_performs_case_workflow_across_both_chains(override_env):
    client, headers = _client(override_env, "admin")
    a = override_env["make_case"]("reported", "a", reporter="admin", label="workflow")
    b = override_env["make_case"]("reported", "b", reporter="admin", label="workflow")

    assert client.get(CASES).status_code == 200
    assert client.get(f"{CASES}/{a['case_id']}").status_code == 200
    assert client.get(f"{CASES}/{b['case_id']}").status_code == 200
    assert client.get(f"{CASES}/{a['case_id']}/timeline").status_code == 200
    assert client.get(f"{CASES}/{b['case_id']}/timeline").status_code == 200

    for item in (a, b):
        submitted = client.post(
            f"{CASES}/{item['case_id']}/submit-for-inspection", headers=headers
        )
        assert submitted.status_code == 200
        assert _row(override_env, PestCase, item["case_id"])["status"] == "FOR_INSPECTION"

    for item, technician in ((a, "tech_a"), (b, "tech_b")):
        scheduled = client.post(
            f"{CASES}/{item['case_id']}/schedule-inspection",
            json={
                "scheduled_for": (override_env["today"] + timedelta(days=1)).isoformat(),
                "assigned_to_user_id": override_env["users"][technician],
            },
            headers=headers,
        )
        assert scheduled.status_code == 201
        body = scheduled.get_json()["data"]["inspection"]
        assert body["assigned_to_user_id"] == override_env["users"][technician]
        assert body["scheduled_by_user_id"] == override_env["users"]["admin"]


def test_admin_records_findings_for_both_inspections_without_reassigning(override_env):
    client, headers = _client(override_env, "admin")
    a = override_env["make_case"]("inspection_scheduled", "a")
    b = override_env["make_case"]("inspection_scheduled", "b")

    for item in (a, b):
        response = client.post(
            f"{INSPECTIONS}/{item['inspection_id']}/record-findings",
            json=_findings_payload(override_env),
            headers=headers,
        )
        assert response.status_code == 200
        inspection = _row(override_env, Inspection, item["inspection_id"])
        assert inspection["assigned_to_user_id"] == (
            override_env["users"]["tech_a" if item is a else "tech_b"]
        )
        assert inspection["completed_by_user_id"] == override_env["users"]["admin"]
        assert _row(override_env, PestCase, item["case_id"])["status"] == "FIELD_VALIDATED"

    repeated = client.post(
        f"{INSPECTIONS}/{a['inspection_id']}/record-findings",
        json=_findings_payload(override_env),
        headers=headers,
    )
    assert repeated.status_code == 409


def test_admin_reschedules_and_explicitly_reassigns_either_inspection(override_env):
    client, headers = _client(override_env, "admin")
    a = override_env["make_case"]("inspection_scheduled", "a", isolated_farm=True)
    b = override_env["make_case"]("inspection_scheduled", "b", isolated_farm=True)
    target_date = (override_env["today"] + timedelta(days=2)).isoformat()

    for item, target_technician in ((a, "tech_b"), (b, "tech_a")):
        response = client.put(
            f"{INSPECTIONS}/{item['inspection_id']}/schedule",
            json={
                "scheduled_for": target_date,
                "assigned_to_user_id": override_env["users"][target_technician],
            },
            headers=headers,
        )
        assert response.status_code == 200
        body = response.get_json()["data"]["inspection"]
        assert body["assigned_to_user_id"] == override_env["users"][target_technician]
        assert _row(override_env, Inspection, item["inspection_id"])[
            "assigned_to_user_id"
        ] == override_env["users"][target_technician]


def test_admin_updates_and_completes_each_intervention_without_reassigning(override_env):
    client, headers = _client(override_env, "admin")
    a = override_env["make_case"]("under_intervention", "a")
    b = override_env["make_case"]("under_intervention", "b")

    for item in (a, b):
        updated = client.put(
            f"{INTERVENTIONS}/{item['intervention_id']}/plan",
            json={
                "method_description": "ADMIN updated intervention plan.",
                "scheduled_for": override_env["today"].isoformat(),
            },
            headers=headers,
        )
        assert updated.status_code == 200
        assert _row(override_env, Intervention, item["intervention_id"])[
            "assigned_to_user_id"
        ] == override_env["users"]["tech_a" if item is a else "tech_b"]

        completed = client.post(
            f"{INTERVENTIONS}/{item['intervention_id']}/complete",
            json={
                "performed_on": override_env["today"].isoformat(),
                "completion_notes": "ADMIN supervisory completion.",
                "follow_up_due_on": (
                    override_env["today"] + timedelta(days=7)
                ).isoformat(),
            },
            headers=headers,
        )
        assert completed.status_code == 200
        intervention = _row(override_env, Intervention, item["intervention_id"])
        assert intervention["assigned_to_user_id"] == (
            override_env["users"]["tech_a" if item is a else "tech_b"]
        )
        assert intervention["completed_by_user_id"] == override_env["users"]["admin"]
        assert _row(override_env, PestCase, item["case_id"])["status"] == "FOLLOW_UP_DUE"

    repeated = client.post(
        f"{INTERVENTIONS}/{a['intervention_id']}/complete",
        json={
            "performed_on": override_env["today"].isoformat(),
            "completion_notes": "ADMIN repeated completion.",
            "follow_up_due_on": (override_env["today"] + timedelta(days=7)).isoformat(),
        },
        headers=headers,
    )
    assert repeated.status_code == 409


def test_admin_records_follow_up_for_both_completed_chains(override_env):
    client, headers = _client(override_env, "admin")
    a = override_env["make_case"]("follow_up_due", "a")
    b = override_env["make_case"]("follow_up_due", "b")

    for item, outcome in ((a, "RESOLVED"), (b, "REINTERVENTION_REQUIRED")):
        response = client.post(
            f"{INTERVENTIONS}/{item['intervention_id']}/record-follow-up",
            json={
                "observed_on": override_env["today"].isoformat(),
                "pest_observed": False,
                "observed_affected_area_hectares": 0,
                "assessment_notes": "ADMIN supervisory reassessment.",
                "outcome": outcome,
            },
            headers=headers,
        )
        assert response.status_code == 201
        follow_up = _follow_up(override_env, item["intervention_id"])
        assert follow_up["recorded_by_user_id"] == override_env["users"]["admin"]
        assert _row(override_env, Intervention, item["intervention_id"])[
            "assigned_to_user_id"
        ] == override_env["users"]["tech_a" if item is a else "tech_b"]
        expected_status = "CLOSED" if outcome == "RESOLVED" else "REINTERVENTION_REQUIRED"
        assert _row(override_env, PestCase, item["case_id"])["status"] == expected_status

    repeated = client.post(
        f"{INTERVENTIONS}/{a['intervention_id']}/record-follow-up",
        json={
            "observed_on": override_env["today"].isoformat(),
            "pest_observed": False,
            "observed_affected_area_hectares": 0,
            "assessment_notes": "ADMIN repeated reassessment.",
            "outcome": "RESOLVED",
        },
        headers=headers,
    )
    assert repeated.status_code == 409


def test_admin_starts_interventions_for_both_field_validated_claims(override_env):
    client, headers = _client(override_env, "admin")
    a = override_env["make_case"]("field_validated", "a")
    b = override_env["make_case"]("field_validated", "b")

    for item, technician in ((a, "tech_a"), (b, "tech_b")):
        response = client.post(
            f"{CASES}/{item['case_id']}/start-intervention",
            json={
                "method_category": "CULTURAL",
                "method_description": "ADMIN started intervention.",
                "scheduled_for": override_env["today"].isoformat(),
                "assigned_to_user_id": override_env["users"][technician],
            },
            headers=headers,
        )
        assert response.status_code == 201
        body = response.get_json()["data"]["intervention"]
        assert body["assigned_to_user_id"] == override_env["users"][technician]
        assert body["created_by_user_id"] == override_env["users"]["admin"]
        assert _row(override_env, PestCase, item["case_id"])["status"] == "UNDER_INTERVENTION"


def test_technician_a_can_only_act_on_chain_a(override_env):
    client, headers = _client(override_env, "tech_a")
    a = override_env["make_case"]("inspection_scheduled", "a")
    b = override_env["make_case"]("inspection_scheduled", "b")
    plan_a = override_env["make_case"]("under_intervention", "a")
    plan_b = override_env["make_case"]("under_intervention", "b")
    follow_a = override_env["make_case"]("follow_up_due", "a")
    follow_b = override_env["make_case"]("follow_up_due", "b")
    schedule_a = override_env["make_case"]("for_inspection", "a", reporter="tech_a")
    schedule_b = override_env["make_case"]("for_inspection", "b", reporter="tech_b")
    reschedule_a = override_env["make_case"]("inspection_scheduled", "a")
    reschedule_b = override_env["make_case"]("inspection_scheduled", "b")
    start_a = override_env["make_case"]("field_validated", "a")
    start_b = override_env["make_case"]("field_validated", "b")

    assert client.post(
        f"{INSPECTIONS}/{a['inspection_id']}/record-findings",
        json=_findings_payload(override_env),
        headers=headers,
    ).status_code == 200
    assert client.post(
        f"{INSPECTIONS}/{b['inspection_id']}/record-findings",
        json=_findings_payload(override_env),
        headers=headers,
    ).status_code == 403

    assert client.put(
        f"{INTERVENTIONS}/{plan_a['intervention_id']}/plan",
        json={"method_description": "Technician A update."},
        headers=headers,
    ).status_code == 200
    assert client.put(
        f"{INTERVENTIONS}/{plan_b['intervention_id']}/plan",
        json={"method_description": "Technician A cannot update B."},
        headers=headers,
    ).status_code == 403

    assert client.post(
        f"{INTERVENTIONS}/{plan_a['intervention_id']}/complete",
        json={
            "performed_on": override_env["today"].isoformat(),
            "completion_notes": "Technician A completion.",
            "follow_up_due_on": (override_env["today"] + timedelta(days=7)).isoformat(),
        },
        headers=headers,
    ).status_code == 200
    assert client.post(
        f"{INTERVENTIONS}/{plan_b['intervention_id']}/complete",
        json={
            "performed_on": override_env["today"].isoformat(),
            "completion_notes": "Technician A cannot complete B.",
            "follow_up_due_on": (override_env["today"] + timedelta(days=7)).isoformat(),
        },
        headers=headers,
    ).status_code == 403

    assert client.post(
        f"{INTERVENTIONS}/{follow_a['intervention_id']}/record-follow-up",
        json={
            "observed_on": override_env["today"].isoformat(),
            "pest_observed": False,
            "observed_affected_area_hectares": 0,
            "assessment_notes": "Technician A reassessment.",
            "outcome": "RESOLVED",
        },
        headers=headers,
    ).status_code == 201
    assert client.post(
        f"{INTERVENTIONS}/{follow_b['intervention_id']}/record-follow-up",
        json={
            "observed_on": override_env["today"].isoformat(),
            "pest_observed": False,
            "observed_affected_area_hectares": 0,
            "assessment_notes": "Technician A cannot reassess B.",
            "outcome": "RESOLVED",
        },
        headers=headers,
    ).status_code == 403

    assert client.put(
        f"{INSPECTIONS}/{reschedule_a['inspection_id']}/schedule",
        json={"scheduled_for": (override_env["today"] + timedelta(days=1)).isoformat()},
        headers=headers,
    ).status_code == 200
    assert client.put(
        f"{INSPECTIONS}/{reschedule_b['inspection_id']}/schedule",
        json={"scheduled_for": (override_env["today"] + timedelta(days=1)).isoformat()},
        headers=headers,
    ).status_code == 404

    assert client.post(
        f"{CASES}/{schedule_a['case_id']}/schedule-inspection",
        json={
            "scheduled_for": (override_env["today"] + timedelta(days=1)).isoformat(),
            "assigned_to_user_id": override_env["users"]["tech_a"],
        },
        headers=headers,
    ).status_code == 201
    assert client.post(
        f"{CASES}/{schedule_b['case_id']}/schedule-inspection",
        json={
            "scheduled_for": (override_env["today"] + timedelta(days=1)).isoformat(),
            "assigned_to_user_id": override_env["users"]["tech_a"],
        },
        headers=headers,
    ).status_code == 404

    assert client.post(
        f"{CASES}/{start_a['case_id']}/start-intervention",
        json={
            "method_category": "CULTURAL",
            "method_description": "Technician A starts own intervention.",
            "scheduled_for": override_env["today"].isoformat(),
            "assigned_to_user_id": override_env["users"]["tech_a"],
        },
        headers=headers,
    ).status_code == 201
    assert client.post(
        f"{CASES}/{start_b['case_id']}/start-intervention",
        json={
            "method_category": "CULTURAL",
            "method_description": "Technician A cannot start B.",
            "scheduled_for": override_env["today"].isoformat(),
            "assigned_to_user_id": override_env["users"]["tech_a"],
        },
        headers=headers,
    ).status_code == 404

    # Direct-ID privacy remains intact.
    for path in (
        f"{CASES}/{b['case_id']}",
        f"{CASES}/{b['case_id']}/timeline",
        f"{FARMERS}/{b['farmer_id']}",
        f"{FARMS}/{b['farm_id']}",
        f"{INSPECTIONS}/{b['inspection_id']}",
        f"{INTERVENTIONS}/{plan_b['intervention_id']}",
    ):
        assert client.get(path).status_code == 404

    # Search, dashboard, reports, and map stay scoped to chain A.
    search = client.get(CASES, query_string={"q": b["pest_name"]}).get_json()["data"][
        "pest_cases"
    ]
    assert search == []
    dashboard = client.get(DASHBOARD).get_json()["data"]["summary"]
    assert b["case_id"] not in {case["id"] for case in dashboard["recent_cases"]}
    report = client.get(REPORTS).get_json()["data"]["report"]
    assert b["case_id"] not in {row["case_id"] for row in report["cases"]}
    farm_map = client.get(FARM_MAP).get_json()["data"]
    map_farm_ids = {farm["id"] for farm in farm_map["farms"]}
    assert b["farm_id"] not in map_farm_ids
    assert a["farm_id"] in map_farm_ids


def test_technician_b_has_equivalent_isolation(override_env):
    client, headers = _client(override_env, "tech_b")
    a = override_env["make_case"]("inspection_scheduled", "a")
    b = override_env["make_case"]("inspection_scheduled", "b")
    plan_a = override_env["make_case"]("under_intervention", "a")
    plan_b = override_env["make_case"]("under_intervention", "b")
    follow_a = override_env["make_case"]("follow_up_due", "a")
    follow_b = override_env["make_case"]("follow_up_due", "b")
    schedule_a = override_env["make_case"]("for_inspection", "a", reporter="tech_a")
    schedule_b = override_env["make_case"]("for_inspection", "b", reporter="tech_b")
    start_a = override_env["make_case"]("field_validated", "a")
    start_b = override_env["make_case"]("field_validated", "b")

    assert client.post(
        f"{INSPECTIONS}/{b['inspection_id']}/record-findings",
        json=_findings_payload(override_env),
        headers=headers,
    ).status_code == 200
    assert client.post(
        f"{INSPECTIONS}/{a['inspection_id']}/record-findings",
        json=_findings_payload(override_env),
        headers=headers,
    ).status_code == 403

    assert client.put(
        f"{INTERVENTIONS}/{plan_b['intervention_id']}/plan",
        json={"method_description": "Technician B update."},
        headers=headers,
    ).status_code == 200
    assert client.put(
        f"{INTERVENTIONS}/{plan_a['intervention_id']}/plan",
        json={"method_description": "Technician B cannot update A."},
        headers=headers,
    ).status_code == 403

    assert client.post(
        f"{INTERVENTIONS}/{plan_b['intervention_id']}/complete",
        json={
            "performed_on": override_env["today"].isoformat(),
            "completion_notes": "Technician B completion.",
            "follow_up_due_on": (override_env["today"] + timedelta(days=7)).isoformat(),
        },
        headers=headers,
    ).status_code == 200
    assert client.post(
        f"{INTERVENTIONS}/{plan_a['intervention_id']}/complete",
        json={
            "performed_on": override_env["today"].isoformat(),
            "completion_notes": "Technician B cannot complete A.",
            "follow_up_due_on": (override_env["today"] + timedelta(days=7)).isoformat(),
        },
        headers=headers,
    ).status_code == 403

    assert client.post(
        f"{INTERVENTIONS}/{follow_b['intervention_id']}/record-follow-up",
        json={
            "observed_on": override_env["today"].isoformat(),
            "pest_observed": False,
            "observed_affected_area_hectares": 0,
            "assessment_notes": "Technician B reassessment.",
            "outcome": "RESOLVED",
        },
        headers=headers,
    ).status_code == 201
    assert client.post(
        f"{INTERVENTIONS}/{follow_a['intervention_id']}/record-follow-up",
        json={
            "observed_on": override_env["today"].isoformat(),
            "pest_observed": False,
            "observed_affected_area_hectares": 0,
            "assessment_notes": "Technician B cannot reassess A.",
            "outcome": "RESOLVED",
        },
        headers=headers,
    ).status_code == 403

    assert client.post(
        f"{CASES}/{schedule_b['case_id']}/schedule-inspection",
        json={
            "scheduled_for": (override_env["today"] + timedelta(days=1)).isoformat(),
            "assigned_to_user_id": override_env["users"]["tech_b"],
        },
        headers=headers,
    ).status_code == 201
    assert client.post(
        f"{CASES}/{schedule_a['case_id']}/schedule-inspection",
        json={
            "scheduled_for": (override_env["today"] + timedelta(days=1)).isoformat(),
            "assigned_to_user_id": override_env["users"]["tech_b"],
        },
        headers=headers,
    ).status_code == 404

    assert client.post(
        f"{CASES}/{start_b['case_id']}/start-intervention",
        json={
            "method_category": "CULTURAL",
            "method_description": "Technician B starts own intervention.",
            "scheduled_for": override_env["today"].isoformat(),
            "assigned_to_user_id": override_env["users"]["tech_b"],
        },
        headers=headers,
    ).status_code == 201
    assert client.post(
        f"{CASES}/{start_a['case_id']}/start-intervention",
        json={
            "method_category": "CULTURAL",
            "method_description": "Technician B cannot start A.",
            "scheduled_for": override_env["today"].isoformat(),
            "assigned_to_user_id": override_env["users"]["tech_b"],
        },
        headers=headers,
    ).status_code == 404

    for path in (
        f"{CASES}/{a['case_id']}",
        f"{FARMERS}/{a['farmer_id']}",
        f"{FARMS}/{a['farm_id']}",
        f"{INSPECTIONS}/{a['inspection_id']}",
        f"{INTERVENTIONS}/{plan_a['intervention_id']}",
    ):
        assert client.get(path).status_code == 404

    farm_map = client.get(FARM_MAP).get_json()["data"]
    map_farm_ids = {farm["id"] for farm in farm_map["farms"]}
    assert a["farm_id"] not in map_farm_ids
    assert b["farm_id"] in map_farm_ids


def test_admin_sees_everything_and_user_management_stays_admin_only(override_env):
    admin_client, _ = _client(override_env, "admin")
    tech_client, _ = _client(override_env, "tech_a")
    a = override_env["make_case"]("inspection_scheduled", "a")
    b = override_env["make_case"]("inspection_scheduled", "b")

    case_ids = {
        case["id"]
        for case in admin_client.get(CASES).get_json()["data"]["pest_cases"]
    }
    assert {a["case_id"], b["case_id"]} <= case_ids

    farmer_ids = {
        farmer["id"]
        for farmer in admin_client.get(FARMERS).get_json()["data"]["farmers"]
    }
    assert {a["farmer_id"], b["farmer_id"]} <= farmer_ids

    farm_ids = {
        farm["id"] for farm in admin_client.get(FARMS).get_json()["data"]["farms"]
    }
    assert {a["farm_id"], b["farm_id"]} <= farm_ids

    report_case_ids = {
        row["case_id"]
        for row in admin_client.get(REPORTS).get_json()["data"]["report"]["cases"]
    }
    assert {a["case_id"], b["case_id"]} <= report_case_ids

    map_farm_ids = {
        farm["id"]
        for farm in admin_client.get(FARM_MAP).get_json()["data"]["farms"]
    }
    assert {a["farm_id"], b["farm_id"]} <= map_farm_ids

    admin_me = admin_client.get("/api/v1/auth/me").get_json()["data"]["user"]
    tech_me = tech_client.get("/api/v1/auth/me").get_json()["data"]["user"]
    assert admin_me["role"] == "ADMIN"
    assert tech_me["role"] == "TECHNICIAN"

    assert admin_client.get(ADMIN_USERS).status_code == 200
    assert tech_client.get(ADMIN_USERS).status_code == 403
